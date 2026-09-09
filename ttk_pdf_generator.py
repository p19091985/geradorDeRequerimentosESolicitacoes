"""
Gerador de PDF com Janelas Múltiplas: Central de Controle, Editor HTML e Navegador Embutido.

Usa PySide6 para coordenar 3 janelas independentes.
A captura a 10x de resolução via Playwright headless (módulo capture_html_screenshot)
permanece, usando o conteúdo exato sendo editado.
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import threading
import traceback
from pathlib import Path

from PySide6.QtCore import Qt, Signal, QUrl, QTimer, QSize
from PySide6.QtGui import (
    QAction,
    QColor,
    QDesktopServices,
    QFont,
    QTextCursor,
    QSyntaxHighlighter,
    QTextCharFormat,
)
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QStatusBar,
    QTextEdit,
    QToolBar,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtWebEngineWidgets import QWebEngineView

from capture_html_screenshot import (
    DEFAULT_PDF_RESOLUTION,
    DEFAULT_VIEWPORT_WIDTH,
)
from ai.prompt_assistant import write_review_prompt
from core.export_presets import EXPORT_PRESETS, get_export_preset
from core.paths import (
    FINISHED_DOC_SUFFIXES,
    GENERATED_DOCS_DIR_NAME,
    HTML_SUFFIXES,
    SOURCE_HTML_DIR_NAME,
    build_unique_path,
    ensure_html_suffix,
    generated_docs_dir,
    source_html_dir,
)
from core.template_catalog import (
    TemplateDefinition,
    load_template_catalog,
    load_template_content,
)
from core.template_variables import (
    extract_template_variables,
    humanize_variable_name,
    merge_template_variables,
    render_template_variables,
)
from rendering.exporter import (
    GenerationSettings,
    export_html_outputs,
)
from storage.document_metadata import (
    VALID_STATUSES,
    DocumentMetadata,
    copy_document_metadata,
    delete_document_metadata,
    load_document_metadata,
    metadata_search_blob,
    rename_document_metadata,
    save_document_metadata,
    touch_document_metadata,
    upsert_document_metadata,
    utc_now,
)
from storage.document_archive import archive_document
from storage.document_history import create_document_snapshot, history_dir_for
from storage.export_manifest import write_generation_manifest
from storage.html_files import read_html_file, write_html_file

# ---------------------------------------------------------------------------
# Syntax highlighter for basic HTML in the editor
# ---------------------------------------------------------------------------
class HtmlHighlighter(QSyntaxHighlighter):
    """Minimal HTML syntax highlighter for the source editor."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rules: list[tuple[str, QTextCharFormat]] = []

        tag_format = QTextCharFormat()
        tag_format.setForeground(QColor("#1976D2"))
        tag_format.setFontWeight(QFont.Weight.Bold)
        self._rules.append((r"</?[a-zA-Z][^>]*>", tag_format))

        attr_format = QTextCharFormat()
        attr_format.setForeground(QColor("#7B1FA2"))
        self._rules.append((r'\b[a-zA-Z\-]+(?==)', attr_format))

        string_format = QTextCharFormat()
        string_format.setForeground(QColor("#388E3C"))
        self._rules.append((r'"[^"]*"', string_format))
        self._rules.append((r"'[^']*'", string_format))

        comment_format = QTextCharFormat()
        comment_format.setForeground(QColor("#9E9E9E"))
        comment_format.setFontItalic(True)
        self._rules.append((r"<!--.*?-->", comment_format))

        entity_format = QTextCharFormat()
        entity_format.setForeground(QColor("#E65100"))
        self._rules.append((r"&[a-zA-Z#0-9]+;", entity_format))

    def highlightBlock(self, text: str) -> None:
        import re
        for pattern, fmt in self._rules:
            for match in re.finditer(pattern, text):
                self.setFormat(match.start(), match.end() - match.start(), fmt)


# ---------------------------------------------------------------------------
# Line number area for the editor
# ---------------------------------------------------------------------------
class LineNumberArea(QWidget):
    def __init__(self, editor: "HtmlSourceEditor"):
        super().__init__(editor)
        self._editor = editor

    def sizeHint(self):
        return self._editor.line_number_area_size()

    def paintEvent(self, event):
        self._editor.line_number_area_paint(event)


class HtmlSourceEditor(QPlainTextEdit):
    """Plain text editor with line numbers for HTML source editing."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._line_area = LineNumberArea(self)

        font = QFont("Monospace", 10)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self.setFont(font)
        self.setTabStopDistance(self.fontMetrics().horizontalAdvance(" ") * 4)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)

        self._highlighter = HtmlHighlighter(self.document())

        self.blockCountChanged.connect(self._update_line_area_width)
        self.updateRequest.connect(self._update_line_area)
        self._update_line_area_width()

    def line_number_area_size(self):
        digits = max(3, len(str(self.blockCount())))
        width = 12 + self.fontMetrics().horizontalAdvance("9") * digits
        return QSize(width, 0)

    def line_number_area_paint(self, event):
        from PySide6.QtGui import QPainter
        painter = QPainter(self._line_area)
        painter.fillRect(event.rect(), QColor("#2B2B2B"))
        painter.setPen(QColor("#858585"))
        painter.setFont(self.font())

        block = self.firstVisibleBlock()
        block_number = block.blockNumber()
        top = round(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + round(self.blockBoundingRect(block).height())

        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                painter.drawText(
                    0, top,
                    self._line_area.width() - 6,
                    self.fontMetrics().height(),
                    Qt.AlignmentFlag.AlignRight,
                    str(block_number + 1),
                )
            block = block.next()
            top = bottom
            bottom = top + round(self.blockBoundingRect(block).height())
            block_number += 1
        painter.end()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        cr = self.contentsRect()
        self._line_area.setGeometry(
            cr.left(), cr.top(),
            self.line_number_area_size().width(), cr.height()
        )

    def _update_line_area_width(self):
        self.setViewportMargins(self.line_number_area_size().width(), 0, 0, 0)

    def _update_line_area(self, rect, dy):
        if dy:
            self._line_area.scroll(0, dy)
        else:
            self._line_area.update(0, rect.y(), self._line_area.width(), rect.height())
        if rect.contains(self.viewport().rect()):
            self._update_line_area_width()


# ---------------------------------------------------------------------------
# Sub-windows: Editor and Browser
# ---------------------------------------------------------------------------
class EditorWindow(QMainWindow):
    """Janela flutuante independente para o Editor HTML."""
    content_changed = Signal(str)
    dirty_changed = Signal(bool)
    save_requested = Signal()

    def __init__(self, parent_controller: "ControlPanelWindow"):
        super().__init__()
        self.parent_controller = parent_controller
        self.setWindowTitle("Editor de Código HTML")
        self.resize(700, 800)
        self._dirty = False

        self._editor = HtmlSourceEditor()
        self.setCentralWidget(self._editor)

        # Toolbar
        toolbar = QToolBar("Editor Principal")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        self._act_save = QAction("💾 Salvar (Ctrl+S)", self)
        self._act_save.setShortcut("Ctrl+S")
        self._act_save.triggered.connect(self.save_requested.emit)
        toolbar.addAction(self._act_save)

        self._act_refresh = QAction("▶ Atualizar Preview (F5)", self)
        self._act_refresh.setShortcut("F5")
        self._act_refresh.triggered.connect(self._trigger_update)
        toolbar.addAction(self._act_refresh)

        toolbar.addSeparator()
        toolbar.addWidget(QLabel("Buscar:"))
        self._search_input = QLineEdit()
        self._search_input.setFixedWidth(150)
        self._search_input.returnPressed.connect(self._find_next)
        toolbar.addWidget(self._search_input)

        self._act_find_next = QAction("Proximo", self)
        self._act_find_next.setShortcut("Ctrl+F")
        self._act_find_next.triggered.connect(self._find_next)
        toolbar.addAction(self._act_find_next)

        toolbar.addWidget(QLabel("Substituir:"))
        self._replace_input = QLineEdit()
        self._replace_input.setFixedWidth(150)
        toolbar.addWidget(self._replace_input)

        self._act_replace = QAction("Substituir", self)
        self._act_replace.triggered.connect(self._replace_current)
        toolbar.addAction(self._act_replace)

        # Live typing update timer
        self._typing_timer = QTimer(self)
        self._typing_timer.setSingleShot(True)
        self._typing_timer.setInterval(500) # 500ms debounce
        self._typing_timer.timeout.connect(self._trigger_update)
        
        self._editor.textChanged.connect(self._on_text_changed)

        self._apply_dark_theme()

    def get_content(self) -> str:
        return self._editor.toPlainText()

    def set_content(self, text: str) -> None:
        self._editor.blockSignals(True)
        self._editor.setPlainText(text)
        self._editor.blockSignals(False)
        self.mark_saved()
        self._trigger_update()

    def _on_text_changed(self):
        self._set_dirty(True)
        self._typing_timer.start()

    def _trigger_update(self):
        self.content_changed.emit(self.get_content())

    def is_dirty(self) -> bool:
        return self._dirty

    def mark_saved(self) -> None:
        self._set_dirty(False)

    def _set_dirty(self, dirty: bool) -> None:
        if self._dirty == dirty:
            return
        self._dirty = dirty
        self.dirty_changed.emit(dirty)

    def _find_next(self) -> None:
        term = self._search_input.text()
        if not term:
            return
        if self._editor.find(term):
            return
        cursor = self._editor.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.Start)
        self._editor.setTextCursor(cursor)
        self._editor.find(term)

    def _replace_current(self) -> None:
        term = self._search_input.text()
        if not term:
            return
        cursor = self._editor.textCursor()
        if cursor.hasSelection() and cursor.selectedText() == term:
            cursor.insertText(self._replace_input.text())
        self._find_next()

    def _apply_dark_theme(self) -> None:
        self.setStyleSheet("""
            QMainWindow { background-color: #1E1E1E; }
            QToolBar { background-color: #2D2D30; border: none; padding: 4px; }
            QToolBar QToolButton {
                background-color: #3C3C3C; color: #D4D4D4;
                border: 1px solid #555; border-radius: 4px; padding: 6px;
            }
            QToolBar QToolButton:hover { background-color: #505050; }
            QPlainTextEdit {
                background-color: #1E1E1E; color: #D4D4D4;
                border: 1px solid #333; selection-background-color: #264F78;
            }
            QLineEdit {
                background-color: #1E1E1E; color: #D4D4D4;
                border: 1px solid #555; border-radius: 3px; padding: 4px;
            }
        """)

    def closeEvent(self, event):
        self.hide()
        event.ignore()


class BrowserWindow(QMainWindow):
    """Janela flutuante independente para o Navegador Chromium (Preview)."""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Preview do Documento (Navegador)")
        self.resize(800, 900)

        self._browser = QWebEngineView()
        self.setCentralWidget(self._browser)

    def update_preview(self, html_content: str, base_url: QUrl):
        self._browser.setHtml(html_content, base_url)

    def closeEvent(self, event):
        self.hide()
        event.ignore()


class TemplateVariablesDialog(QDialog):
    def __init__(self, variables: list[str], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Preencher variaveis do template")
        self._inputs: dict[str, QLineEdit] = {}

        layout = QVBoxLayout(self)
        form_layout = QFormLayout()
        for variable in variables:
            field = QLineEdit()
            field.setPlaceholderText(f"{{{{{variable}}}}}")
            self._inputs[variable] = field
            form_layout.addRow(f"{humanize_variable_name(variable)}:", field)

        layout.addLayout(form_layout)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def values(self) -> dict[str, str]:
        return {
            variable: field.text().strip()
            for variable, field in self._inputs.items()
        }


class MetadataDialog(QDialog):
    def __init__(self, metadata: DocumentMetadata, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Metadados do documento")

        layout = QVBoxLayout(self)
        form_layout = QFormLayout()

        self._title_input = QLineEdit(metadata.titulo)
        self._type_input = QLineEdit(metadata.tipo)
        self._interested_input = QLineEdit(metadata.interessado)
        self._tags_input = QLineEdit(", ".join(metadata.tags))
        self._status_input = QComboBox()
        self._status_input.addItems(VALID_STATUSES)
        self._status_input.setCurrentText(metadata.status)
        self._template_input = QLineEdit(metadata.template_origem)

        form_layout.addRow("Titulo:", self._title_input)
        form_layout.addRow("Tipo:", self._type_input)
        form_layout.addRow("Interessado:", self._interested_input)
        form_layout.addRow("Tags:", self._tags_input)
        form_layout.addRow("Status:", self._status_input)
        form_layout.addRow("Template:", self._template_input)
        layout.addLayout(form_layout)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def metadata_updates(self) -> dict:
        tags = [
            tag.strip()
            for tag in self._tags_input.text().split(",")
            if tag.strip()
        ]
        return {
            "titulo": self._title_input.text().strip(),
            "tipo": self._type_input.text().strip(),
            "interessado": self._interested_input.text().strip(),
            "tags": tags,
            "status": self._status_input.currentText(),
            "template_origem": self._template_input.text().strip(),
        }


# ---------------------------------------------------------------------------
# Main Controller Application Window
# ---------------------------------------------------------------------------
class ControlPanelWindow(QMainWindow):
    """Central de controle principal (Estilo Lazarus/Delphi menu list)."""

    capture_finished = Signal(dict)
    batch_finished = Signal(list)
    capture_error = Signal(str)
    log_signal = Signal(str)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Controlador — Gerador de PDF 10x")
        self.setMinimumSize(800, 500)
        self.resize(1180, 760)

        self._current_file: Path | None = None
        self._last_finished_html_path: Path | None = None
        self._temp_dir = tempfile.mkdtemp(prefix="html_preview_")
        self._worker_thread: threading.Thread | None = None
        self._pending_generation_manifest: dict | None = None
        self._pending_manifest_output_dir: Path | None = None
        self._pending_manifest_base_name: str | None = None
        self._autosave_timer = QTimer(self)
        self._autosave_timer.setSingleShot(True)
        self._autosave_timer.setInterval(2500)
        self._autosave_timer.timeout.connect(self._autosave_file)

        # Child Windows
        self._editor_win = EditorWindow(self)
        self._browser_win = BrowserWindow()

        # Connections from children
        self._editor_win.content_changed.connect(self._sync_preview)
        self._editor_win.dirty_changed.connect(self._on_editor_dirty_changed)
        self._editor_win.save_requested.connect(self._save_file)

        self._build_ui()
        self._connect_signals()
        self._apply_selected_preset()
        self._apply_dark_theme()
        self._load_default_file()

    # ----- UI construction -----

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(12)

        documents_layout = QHBoxLayout()
        documents_layout.setSpacing(12)

        todo_group = QGroupBox(f"Documentos em Elaboracao ({SOURCE_HTML_DIR_NAME})")
        todo_layout = QVBoxLayout(todo_group)
        todo_filter_row = QHBoxLayout()
        self._source_search_input = QLineEdit()
        self._source_search_input.setPlaceholderText("Buscar por nome, conteudo ou metadados")
        self._source_status_filter = QComboBox()
        self._source_status_filter.addItems(["todos", *VALID_STATUSES])
        self._source_type_filter = QComboBox()
        self._source_type_filter.addItem("todos")
        self._source_template_filter = QComboBox()
        self._source_template_filter.addItem("todos")
        todo_filter_row.addWidget(self._source_search_input, stretch=1)
        todo_filter_row.addWidget(self._source_status_filter)
        todo_filter_row.addWidget(self._source_type_filter)
        todo_filter_row.addWidget(self._source_template_filter)
        todo_layout.addLayout(todo_filter_row)

        self._todo_list = QListWidget()
        self._todo_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self._todo_list.setMinimumHeight(190)
        todo_layout.addWidget(self._todo_list)

        todo_row_1 = QHBoxLayout()
        self._btn_reload_source = QPushButton("Recarregar")
        self._btn_new_source = QPushButton("Novo HTML")
        self._btn_duplicate_source = QPushButton("Duplicar")
        todo_row_1.addWidget(self._btn_reload_source)
        todo_row_1.addWidget(self._btn_new_source)
        todo_row_1.addWidget(self._btn_duplicate_source)
        todo_layout.addLayout(todo_row_1)

        todo_row_2 = QHBoxLayout()
        self._btn_rename_source = QPushButton("Renomear")
        self._btn_delete_source = QPushButton("Excluir")
        self._btn_open_source = QPushButton("Abrir / Editar")
        self._btn_open_source.setStyleSheet(
            "font-weight: bold; background-color: #0078D4; color: white;"
        )
        self._btn_open_source_folder = QPushButton("Abrir Pasta")
        todo_row_2.addWidget(self._btn_rename_source)
        todo_row_2.addWidget(self._btn_delete_source)
        todo_row_2.addWidget(self._btn_open_source)
        todo_row_2.addWidget(self._btn_open_source_folder)
        todo_layout.addLayout(todo_row_2)

        todo_row_3 = QHBoxLayout()
        self._btn_metadata_source = QPushButton("Metadados")
        self._btn_archive_source = QPushButton("Arquivar")
        self._btn_history_source = QPushButton("Histórico")
        self._btn_ai_source = QPushButton("Prompt IA")
        todo_row_3.addWidget(self._btn_metadata_source)
        todo_row_3.addWidget(self._btn_archive_source)
        todo_row_3.addWidget(self._btn_history_source)
        todo_row_3.addWidget(self._btn_ai_source)
        todo_layout.addLayout(todo_row_3)

        done_group = QGroupBox(f"Documentos Finalizados ({GENERATED_DOCS_DIR_NAME})")
        done_layout = QVBoxLayout(done_group)
        done_filter_row = QHBoxLayout()
        self._done_search_input = QLineEdit()
        self._done_search_input.setPlaceholderText("Buscar por nome, conteudo ou metadados")
        self._done_status_filter = QComboBox()
        self._done_status_filter.addItems(["todos", *VALID_STATUSES])
        self._done_type_filter = QComboBox()
        self._done_type_filter.addItem("todos")
        self._done_template_filter = QComboBox()
        self._done_template_filter.addItem("todos")
        done_filter_row.addWidget(self._done_search_input, stretch=1)
        done_filter_row.addWidget(self._done_status_filter)
        done_filter_row.addWidget(self._done_type_filter)
        done_filter_row.addWidget(self._done_template_filter)
        done_layout.addLayout(done_filter_row)

        self._done_list = QListWidget()
        self._done_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self._done_list.setMinimumHeight(190)
        done_layout.addWidget(self._done_list)

        done_row_1 = QHBoxLayout()
        self._btn_reload_done = QPushButton("Recarregar")
        self._btn_new_done = QPushButton("Novo HTML")
        self._btn_duplicate_done = QPushButton("Duplicar")
        done_row_1.addWidget(self._btn_reload_done)
        done_row_1.addWidget(self._btn_new_done)
        done_row_1.addWidget(self._btn_duplicate_done)
        done_layout.addLayout(done_row_1)

        done_row_2 = QHBoxLayout()
        self._btn_rename_done = QPushButton("Renomear")
        self._btn_delete_done = QPushButton("Excluir")
        self._btn_open_done = QPushButton("Abrir")
        self._btn_open_done_folder = QPushButton("Abrir Pasta")
        done_row_2.addWidget(self._btn_rename_done)
        done_row_2.addWidget(self._btn_delete_done)
        done_row_2.addWidget(self._btn_open_done)
        done_row_2.addWidget(self._btn_open_done_folder)
        done_layout.addLayout(done_row_2)

        done_row_3 = QHBoxLayout()
        self._btn_metadata_done = QPushButton("Metadados")
        self._btn_archive_done = QPushButton("Arquivar")
        self._btn_history_done = QPushButton("Histórico")
        done_row_3.addWidget(self._btn_metadata_done)
        done_row_3.addWidget(self._btn_archive_done)
        done_row_3.addWidget(self._btn_history_done)
        done_layout.addLayout(done_row_3)

        documents_layout.addWidget(todo_group, stretch=1)
        documents_layout.addWidget(done_group, stretch=1)
        main_layout.addLayout(documents_layout)

        # Settings panel
        settings_group = QGroupBox("Configurações de Geração em Alta Resolução")
        settings_layout = QVBoxLayout(settings_group)
        settings_layout.setSpacing(12)

        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Preset:"))
        self._preset_input = QComboBox()
        for preset in EXPORT_PRESETS:
            self._preset_input.addItem(preset.nome, preset.id)
        self._preset_input.setCurrentIndex(2)
        row1.addWidget(self._preset_input)

        row1.addWidget(QLabel("Fator de Escala da Tela (Ex: 10x):"))
        self._scale_factor_input = QLineEdit("10")
        self._scale_factor_input.setFixedWidth(60)
        row1.addWidget(self._scale_factor_input)

        row1.addWidget(QLabel("PDF ppi:"))
        self._pdf_ppi_input = QLineEdit(str(int(DEFAULT_PDF_RESOLUTION)))
        self._pdf_ppi_input.setFixedWidth(60)
        row1.addWidget(self._pdf_ppi_input)
        row1.addStretch()
        settings_layout.addLayout(row1)

        row2 = QHBoxLayout()
        self._chk_pdf = QCheckBox("Gerar PDF")
        self._chk_pdf.setChecked(True)
        self._chk_jpg = QCheckBox("Gerar JPG")
        self._chk_png = QCheckBox("Gerar PNG")
        row2.addWidget(self._chk_pdf)
        row2.addWidget(self._chk_jpg)
        row2.addWidget(self._chk_png)
        row2.addStretch()
        settings_layout.addLayout(row2)

        row3 = QHBoxLayout()
        row3.addWidget(QLabel("Pasta oficial de saída:"))
        self._output_dir_input = QLineEdit(str(self._generated_docs_dir()))
        self._output_dir_input.setReadOnly(True)
        row3.addWidget(self._output_dir_input)
        self._btn_open_output_dir = QPushButton("Abrir Pasta")
        row3.addWidget(self._btn_open_output_dir)
        settings_layout.addLayout(row3)

        main_layout.addWidget(settings_group)

        # Action panel
        action_layout = QHBoxLayout()
        self._progress = QProgressBar()
        self._progress.setRange(0, 0)
        self._progress.setVisible(False)
        self._progress.setFixedHeight(12)
        action_layout.addWidget(self._progress, stretch=1)
        
        self._btn_capture = QPushButton("📸 Gerar Arquivos / Capturar Edição")
        self._btn_capture.setMinimumHeight(40)
        self._btn_capture.setMinimumWidth(250)
        self._btn_capture.setStyleSheet("font-weight: bold; background-color: #107C10; color: white;")
        action_layout.addWidget(self._btn_capture)
        self._btn_batch_capture = QPushButton("Exportar Lote")
        self._btn_batch_capture.setMinimumHeight(40)
        action_layout.addWidget(self._btn_batch_capture)
        
        main_layout.addLayout(action_layout)

        # Log
        self._log = QTextEdit()
        self._log.setReadOnly(True)
        self._log.setMaximumHeight(150)
        self._log.setStyleSheet(
            "background-color: #1E1E1E; color: #D4D4D4; "
            "font-family: Monospace; font-size: 11px; border: 1px solid #333;"
        )
        main_layout.addWidget(self._log)

        # Status bar
        self._status = QStatusBar()
        self.setStatusBar(self._status)
        self._status.showMessage(
            "Pronto. Gerencie os documentos nas pastas oficiais e exporte para documentos_finalizados."
        )

    def _connect_signals(self) -> None:
        self._btn_reload_source.clicked.connect(self._reload_source_directory)
        self._btn_new_source.clicked.connect(
            lambda: self._create_html_document(self._todo_list, self._source_html_dir())
        )
        self._btn_duplicate_source.clicked.connect(
            lambda: self._duplicate_selected_document(self._todo_list, self._source_html_dir())
        )
        self._btn_rename_source.clicked.connect(
            lambda: self._rename_selected_document(self._todo_list, self._source_html_dir())
        )
        self._btn_delete_source.clicked.connect(
            lambda: self._delete_selected_document(self._todo_list, self._source_html_dir())
        )
        self._btn_open_source.clicked.connect(
            lambda: self._open_selected_document(self._todo_list)
        )
        self._btn_open_source_folder.clicked.connect(
            lambda: self._open_directory(self._source_html_dir())
        )
        self._btn_metadata_source.clicked.connect(
            lambda: self._edit_selected_metadata(self._todo_list)
        )
        self._btn_archive_source.clicked.connect(
            lambda: self._archive_selected_document(self._todo_list, self._source_html_dir())
        )
        self._btn_history_source.clicked.connect(
            lambda: self._open_history_for_selected(self._todo_list)
        )
        self._btn_ai_source.clicked.connect(
            lambda: self._write_ai_prompt_for_selected(self._todo_list)
        )

        self._btn_reload_done.clicked.connect(self._reload_generated_directory)
        self._btn_new_done.clicked.connect(
            lambda: self._create_html_document(self._done_list, self._generated_docs_dir())
        )
        self._btn_duplicate_done.clicked.connect(
            lambda: self._duplicate_selected_document(self._done_list, self._generated_docs_dir())
        )
        self._btn_rename_done.clicked.connect(
            lambda: self._rename_selected_document(self._done_list, self._generated_docs_dir())
        )
        self._btn_delete_done.clicked.connect(
            lambda: self._delete_selected_document(self._done_list, self._generated_docs_dir())
        )
        self._btn_open_done.clicked.connect(
            lambda: self._open_selected_document(self._done_list)
        )
        self._btn_open_done_folder.clicked.connect(
            lambda: self._open_directory(self._generated_docs_dir())
        )
        self._btn_metadata_done.clicked.connect(
            lambda: self._edit_selected_metadata(self._done_list)
        )
        self._btn_archive_done.clicked.connect(
            lambda: self._archive_selected_document(self._done_list, self._generated_docs_dir())
        )
        self._btn_history_done.clicked.connect(
            lambda: self._open_history_for_selected(self._done_list)
        )
        self._btn_open_output_dir.clicked.connect(
            lambda: self._open_directory(self._generated_docs_dir())
        )
        self._btn_capture.clicked.connect(self._start_capture)
        self._btn_batch_capture.clicked.connect(self._start_batch_capture)
        self._preset_input.currentIndexChanged.connect(self._apply_selected_preset)
        self._source_search_input.textChanged.connect(lambda _: self._reload_source_directory())
        self._source_status_filter.currentTextChanged.connect(
            lambda _: self._reload_source_directory()
        )
        self._source_type_filter.currentTextChanged.connect(lambda _: self._reload_source_directory())
        self._source_template_filter.currentTextChanged.connect(
            lambda _: self._reload_source_directory()
        )
        self._done_search_input.textChanged.connect(lambda _: self._reload_generated_directory())
        self._done_status_filter.currentTextChanged.connect(
            lambda _: self._reload_generated_directory()
        )
        self._done_type_filter.currentTextChanged.connect(lambda _: self._reload_generated_directory())
        self._done_template_filter.currentTextChanged.connect(
            lambda _: self._reload_generated_directory()
        )

        self._todo_list.itemDoubleClicked.connect(
            lambda _: self._open_selected_document(self._todo_list)
        )
        self._done_list.itemDoubleClicked.connect(
            lambda _: self._open_selected_document(self._done_list)
        )
        self._todo_list.itemSelectionChanged.connect(
            lambda: self._handle_list_selection(self._todo_list, self._done_list)
        )
        self._done_list.itemSelectionChanged.connect(
            lambda: self._handle_list_selection(self._done_list, self._todo_list)
        )

        self.capture_finished.connect(self._on_capture_finished)
        self.batch_finished.connect(self._on_batch_finished)
        self.capture_error.connect(self._on_capture_error)
        self.log_signal.connect(self._append_log)

    def _apply_dark_theme(self) -> None:
        self.setStyleSheet("""
            QMainWindow { background-color: #1E1E1E; }
            QWidget { background-color: #252526; color: #D4D4D4; }
            QGroupBox {
                border: 1px solid #3C3C3C; border-radius: 6px;
                margin-top: 10px; padding: 12px 10px 10px 10px;
                font-size: 13px; font-weight: bold; color: #D4D4D4;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0 6px; left: 10px;
            }
            QLabel { background: transparent; }
            QLineEdit, QListWidget {
                background-color: #3C3C3C; border: 1px solid #555;
                border-radius: 3px; padding: 4px; color: #D4D4D4;
            }
            QComboBox {
                background-color: #3C3C3C; border: 1px solid #555;
                border-radius: 3px; padding: 4px; color: #D4D4D4;
            }
            QLineEdit:focus, QListWidget:focus, QComboBox:focus { border-color: #0078D4; }
            QCheckBox { spacing: 6px; background: transparent; }
            QCheckBox::indicator {
                width: 16px; height: 16px;
                border: 1px solid #555; border-radius: 3px;
                background-color: #3C3C3C;
            }
            QCheckBox::indicator:checked { background-color: #0078D4; border-color: #0078D4; }
            QPushButton {
                background-color: #3C3C3C; border: 1px solid #555;
                border-radius: 4px; padding: 6px 12px; color: #D4D4D4;
            }
            QPushButton:hover { background-color: #505050; }
            QPushButton:pressed { background-color: #0078D4; color: white;}
            QProgressBar { background-color: #3C3C3C; border: none; border-radius: 3px; }
            QProgressBar::chunk { background-color: #107C10; border-radius: 3px; }
            QStatusBar { background-color: #007ACC; color: white; font-size: 11px; padding: 2px; }
        """)

    # ----- File list operations -----

    def _load_default_file(self) -> None:
        self._reload_all_directories()

    def _source_html_dir(self) -> Path:
        return source_html_dir()

    def _generated_docs_dir(self) -> Path:
        return generated_docs_dir()

    def _reload_all_directories(self) -> None:
        self._reload_source_directory()
        self._reload_generated_directory()
        self._refresh_output_dir_hint()

    def _reload_source_directory(self) -> None:
        paths = self._reload_directory(
            list_widget=self._todo_list,
            base_dir=self._source_html_dir(),
            suffixes=HTML_SUFFIXES,
            search_text=self._source_search_input.text(),
            status_filter=self._source_status_filter.currentText(),
            type_filter=self._source_type_filter.currentText(),
            template_filter=self._source_template_filter.currentText(),
        )
        self._refresh_metadata_filter_options(
            self._source_html_dir(),
            self._source_type_filter,
            self._source_template_filter,
        )
        if paths:
            self._status.showMessage(
                f"{len(paths)} documento(s) carregado(s) em {SOURCE_HTML_DIR_NAME}."
            )
        elif self._current_file and self._current_file.is_relative_to(self._source_html_dir()):
            self._clear_current_document()
        self._refresh_output_dir_hint()

    def _reload_generated_directory(self) -> None:
        paths = self._reload_directory(
            list_widget=self._done_list,
            base_dir=self._generated_docs_dir(),
            suffixes=FINISHED_DOC_SUFFIXES,
            search_text=self._done_search_input.text(),
            status_filter=self._done_status_filter.currentText(),
            type_filter=self._done_type_filter.currentText(),
            template_filter=self._done_template_filter.currentText(),
        )
        self._refresh_metadata_filter_options(
            self._generated_docs_dir(),
            self._done_type_filter,
            self._done_template_filter,
        )
        if paths:
            self._status.showMessage(
                f"{len(paths)} documento(s) carregado(s) em {GENERATED_DOCS_DIR_NAME}."
            )
        self._refresh_output_dir_hint()

    def _reload_directory(
        self,
        list_widget: QListWidget,
        base_dir: Path,
        suffixes: set[str],
        search_text: str = "",
        status_filter: str = "todos",
        type_filter: str = "todos",
        template_filter: str = "todos",
    ) -> list[Path]:
        previously_selected = self._selected_path(list_widget)
        list_widget.clear()

        paths = sorted(
            (
                path.resolve()
                for path in base_dir.rglob("*")
                if path.is_file() and path.suffix.lower() in suffixes
                and ".historico" not in path.parts
                and not path.name.endswith(".meta.json")
                and self._document_matches_filters(
                    path,
                    base_dir,
                    search_text,
                    status_filter,
                    type_filter,
                    template_filter,
                )
            ),
            key=lambda path: (str(path.parent).lower(), path.name.lower()),
        )

        for path in paths:
            relative_label = str(path.relative_to(base_dir))
            item = QListWidgetItem(relative_label)
            item.setData(Qt.ItemDataRole.UserRole, path)
            item.setToolTip(str(path))
            list_widget.addItem(item)

        if paths:
            self._select_path_in_list(
                list_widget,
                previously_selected if previously_selected in paths else paths[0],
            )
            self._append_log(
                f"Lista atualizada em {base_dir}: {len(paths)} arquivo(s)."
            )
        else:
            self._append_log(f"Nenhum arquivo compatível encontrado em {base_dir}.")

        return paths

    def _document_matches_filters(
        self,
        path: Path,
        base_dir: Path,
        search_text: str,
        status_filter: str,
        type_filter: str,
        template_filter: str,
    ) -> bool:
        metadata = load_document_metadata(path)
        if status_filter != "todos" and metadata.status != status_filter:
            return False
        if type_filter != "todos" and metadata.tipo != type_filter:
            return False
        if template_filter != "todos" and metadata.template_origem != template_filter:
            return False

        query = search_text.strip().lower()
        if not query:
            return True

        parts = [
            str(path.relative_to(base_dir)).lower(),
            metadata_search_blob(path),
        ]
        if path.suffix.lower() in HTML_SUFFIXES:
            try:
                parts.append(read_html_file(path).lower())
            except Exception:
                pass
        return query in " ".join(parts)

    def _refresh_metadata_filter_options(
        self,
        base_dir: Path,
        type_combo: QComboBox,
        template_combo: QComboBox,
    ) -> None:
        current_type = type_combo.currentText()
        current_template = template_combo.currentText()
        types: set[str] = set()
        templates: set[str] = set()

        for path in base_dir.rglob("*"):
            if (
                not path.is_file()
                or path.name.endswith(".meta.json")
                or ".historico" in path.parts
            ):
                continue
            metadata = load_document_metadata(path)
            if metadata.tipo:
                types.add(metadata.tipo)
            if metadata.template_origem:
                templates.add(metadata.template_origem)

        self._reset_combo_options(type_combo, ["todos", *sorted(types)], current_type)
        self._reset_combo_options(template_combo, ["todos", *sorted(templates)], current_template)

    def _reset_combo_options(
        self,
        combo: QComboBox,
        options: list[str],
        current_value: str,
    ) -> None:
        combo.blockSignals(True)
        combo.clear()
        combo.addItems(options)
        combo.setCurrentText(current_value if current_value in options else "todos")
        combo.blockSignals(False)

    def _selected_path(self, list_widget: QListWidget) -> Path | None:
        item = list_widget.currentItem()
        if item is None and list_widget.selectedItems():
            item = list_widget.selectedItems()[0]
        if item is None:
            return None
        return item.data(Qt.ItemDataRole.UserRole)

    def _select_path_in_list(self, list_widget: QListWidget, path: Path | None) -> None:
        if path is None:
            return
        for index in range(list_widget.count()):
            item = list_widget.item(index)
            if item.data(Qt.ItemDataRole.UserRole) == path.resolve():
                list_widget.setCurrentItem(item)
                item.setSelected(True)
                break

    def _handle_list_selection(
        self,
        active_list: QListWidget,
        inactive_list: QListWidget,
    ) -> None:
        if not active_list.selectedItems():
            self._refresh_output_dir_hint()
            return

        inactive_list.blockSignals(True)
        inactive_list.clearSelection()
        inactive_list.blockSignals(False)
        self._refresh_output_dir_hint()

    def _resolve_managed_path(
        self,
        base_dir: Path,
        raw_name: str,
        ensure_html: bool = False,
    ) -> Path:
        normalized = raw_name.strip().replace("\\", "/").lstrip("/")
        if ensure_html:
            normalized = ensure_html_suffix(normalized)
        target_path = (base_dir / normalized).resolve()
        if not target_path.is_relative_to(base_dir.resolve()):
            raise ValueError("O caminho informado precisa ficar dentro da pasta gerenciada.")
        return target_path

    def _choose_template(self) -> TemplateDefinition | None:
        try:
            templates = load_template_catalog(Path.cwd())
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Catalogo de templates invalido",
                f"Nao foi possivel carregar os templates:\n{exc}",
            )
            return None

        if not templates:
            QMessageBox.warning(
                self,
                "Nenhum template",
                "Nenhum template HTML valido foi encontrado.",
            )
            return None

        labels = [template.display_label for template in templates]
        label_to_template = dict(zip(labels, templates))
        selected_label, confirmed = QInputDialog.getItem(
            self,
            "Escolher template",
            "Template para o novo documento:",
            labels,
            0,
            False,
        )
        if not confirmed:
            return None
        return label_to_template[selected_label]

    def _create_html_document(self, list_widget: QListWidget, base_dir: Path) -> None:
        file_name, confirmed = QInputDialog.getText(
            self,
            "Novo documento HTML",
            "Nome do novo arquivo HTML:",
            text="novo-documento.html",
        )
        if not confirmed or not file_name.strip():
            return

        try:
            target_path = self._resolve_managed_path(base_dir, file_name, ensure_html=True)
        except ValueError as exc:
            QMessageBox.warning(self, "Nome inválido", str(exc))
            return

        if target_path.exists():
            QMessageBox.warning(
                self,
                "Arquivo existente",
                f"Já existe um arquivo com este nome:\n{target_path.name}",
            )
            return

        template = self._choose_template()
        if template is None:
            return

        try:
            template_content = load_template_content(template, Path.cwd())
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Erro ao carregar template",
                f"Nao foi possivel abrir o template selecionado:\n{exc}",
            )
            return

        variable_values: dict[str, str] = {}
        variables = merge_template_variables(
            template.variaveis,
            extract_template_variables(template_content),
        )
        if variables:
            dialog = TemplateVariablesDialog(variables, self)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
            variable_values = dialog.values()
            template_content = render_template_variables(template_content, variable_values)

        target_path.parent.mkdir(parents=True, exist_ok=True)
        write_html_file(target_path, template_content)
        status = (
            "finalizado"
            if base_dir.resolve() == self._generated_docs_dir().resolve()
            else "rascunho"
        )
        save_document_metadata(
            target_path,
            DocumentMetadata.for_document(
                target_path,
                status=status,
                template_origem=template.id,
                titulo=variable_values.get("titulo", target_path.stem),
            ),
        )
        self._reload_list_for_widget(list_widget)
        self._select_path_in_list(list_widget, target_path)
        self._append_log(f"Novo documento criado: {target_path} | template: {template.nome}")
        self._open_html_document(target_path)

    def _duplicate_selected_document(self, list_widget: QListWidget, base_dir: Path) -> None:
        source_path = self._selected_path(list_widget)
        if source_path is None:
            QMessageBox.warning(self, "Nenhum arquivo", "Selecione um documento primeiro.")
            return

        try:
            relative_parent = source_path.relative_to(base_dir).parent
        except ValueError:
            relative_parent = Path()

        duplicate_name = f"{source_path.stem}-copia{source_path.suffix}"
        duplicate_path = build_unique_path((base_dir / relative_parent / duplicate_name).resolve())
        duplicate_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, duplicate_path)
        copy_document_metadata(source_path, duplicate_path)

        self._reload_list_for_widget(list_widget)
        self._select_path_in_list(list_widget, duplicate_path)
        self._append_log(f"Documento duplicado: {duplicate_path}")

    def _rename_selected_document(self, list_widget: QListWidget, base_dir: Path) -> None:
        source_path = self._selected_path(list_widget)
        if source_path is None:
            QMessageBox.warning(self, "Nenhum arquivo", "Selecione um documento primeiro.")
            return

        current_name = str(source_path.relative_to(base_dir))
        new_name, confirmed = QInputDialog.getText(
            self,
            "Renomear documento",
            "Novo nome do arquivo:",
            text=current_name,
        )
        if not confirmed or not new_name.strip():
            return

        try:
            target_path = self._resolve_managed_path(
                base_dir,
                new_name,
                ensure_html=source_path.suffix.lower() in HTML_SUFFIXES and not Path(new_name).suffix,
            )
        except ValueError as exc:
            QMessageBox.warning(self, "Nome inválido", str(exc))
            return

        if target_path == source_path:
            return
        if target_path.exists():
            QMessageBox.warning(
                self,
                "Arquivo existente",
                f"Já existe um arquivo com este nome:\n{target_path.name}",
            )
            return

        target_path.parent.mkdir(parents=True, exist_ok=True)
        source_path.rename(target_path)
        rename_document_metadata(source_path, target_path)
        if self._current_file == source_path:
            self._current_file = target_path
            self._editor_win.setWindowTitle(f"Editor: {target_path.name}")
            self._browser_win.setWindowTitle(f"Preview: {target_path.name}")

        self._reload_list_for_widget(list_widget)
        self._select_path_in_list(list_widget, target_path)
        self._append_log(f"Documento renomeado para: {target_path}")
        self._refresh_output_dir_hint()

    def _delete_selected_document(self, list_widget: QListWidget, base_dir: Path) -> None:
        target_path = self._selected_path(list_widget)
        if target_path is None:
            QMessageBox.warning(self, "Nenhum arquivo", "Selecione um documento primeiro.")
            return

        answer = QMessageBox.question(
            self,
            "Excluir documento",
            f"Excluir permanentemente o arquivo?\n{target_path.name}",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        target_path.unlink(missing_ok=False)
        delete_document_metadata(target_path)
        if self._current_file == target_path:
            self._clear_current_document()

        self._reload_list_for_widget(list_widget)
        self._append_log(f"Documento excluído: {target_path}")
        self._refresh_output_dir_hint()

    def _edit_selected_metadata(self, list_widget: QListWidget) -> None:
        target_path = self._selected_path(list_widget)
        if target_path is None:
            QMessageBox.warning(self, "Nenhum arquivo", "Selecione um documento primeiro.")
            return

        dialog = MetadataDialog(load_document_metadata(target_path), self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        upsert_document_metadata(target_path, **dialog.metadata_updates())
        self._reload_list_for_widget(list_widget)
        self._select_path_in_list(list_widget, target_path)
        self._append_log(f"Metadados atualizados: {target_path}")

    def _archive_selected_document(self, list_widget: QListWidget, base_dir: Path) -> None:
        target_path = self._selected_path(list_widget)
        if target_path is None:
            QMessageBox.warning(self, "Nenhum arquivo", "Selecione um documento primeiro.")
            return

        answer = QMessageBox.question(
            self,
            "Arquivar documento",
            f"Mover para a pasta de arquivados?\n{target_path.name}",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        archived_path = archive_document(target_path, base_dir)
        if self._current_file == target_path:
            self._clear_current_document()
        self._reload_list_for_widget(list_widget)
        self._append_log(f"Documento arquivado: {archived_path}")

    def _open_history_for_selected(self, list_widget: QListWidget) -> None:
        target_path = self._selected_path(list_widget)
        if target_path is None:
            QMessageBox.warning(self, "Nenhum arquivo", "Selecione um documento primeiro.")
            return

        history_dir = history_dir_for(target_path)
        history_dir.mkdir(parents=True, exist_ok=True)
        self._open_directory(history_dir)

    def _write_ai_prompt_for_selected(self, list_widget: QListWidget) -> None:
        target_path = self._selected_path(list_widget)
        if target_path is None or target_path.suffix.lower() not in HTML_SUFFIXES:
            QMessageBox.warning(self, "Nenhum HTML", "Selecione um documento HTML primeiro.")
            return

        prompt_path = write_review_prompt(target_path, read_html_file(target_path))
        self._append_log(f"Prompt IA gerado: {prompt_path}")
        QMessageBox.information(
            self,
            "Prompt IA gerado",
            f"Arquivo criado para revisao externa:\n{prompt_path.name}",
        )

    def _reload_list_for_widget(self, list_widget: QListWidget) -> None:
        if list_widget is self._todo_list:
            self._reload_source_directory()
        else:
            self._reload_generated_directory()

    def _open_selected_document(self, list_widget: QListWidget) -> None:
        path = self._selected_path(list_widget)
        if path is None:
            QMessageBox.warning(self, "Nenhum arquivo", "Selecione um documento primeiro.")
            return

        if path.suffix.lower() in HTML_SUFFIXES:
            self._open_html_document(path)
            return

        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(path))):
            QMessageBox.warning(
                self,
                "Falha ao abrir",
                f"Não foi possível abrir o arquivo externamente:\n{path}",
            )

    def _open_directory(self, directory: Path) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(directory.resolve())))

    # ----- Multi-window synchronization -----

    def _open_html_document(self, path: Path) -> None:
        try:
            content = read_html_file(path)
        except Exception as exc:
            QMessageBox.critical(self, "Erro ao abrir", f"Falha ao ler {path.name}:\n{exc}")
            return

        self._current_file = path
        self._editor_win.setWindowTitle(f"Editor: {path.name}")
        self._browser_win.setWindowTitle(f"Preview: {path.name}")
        
        # Load content into editor. The signal will cascade to browser
        self._editor_win.set_content(content)
        
        # Position windows nicely if they are hidden
        if not self._editor_win.isVisible() or not self._browser_win.isVisible():
            main_geom = self.geometry()
            self._browser_win.setGeometry(main_geom.right() + 10, main_geom.top(), 800, 900)
            self._editor_win.setGeometry(main_geom.right() + 820, main_geom.top(), 700, 900)
            
        self._editor_win.show()
        self._editor_win.raise_()
        self._browser_win.show()
        self._browser_win.raise_()
        
        self._status.showMessage(f"Editando: {path.name}")
        self._append_log(f"Aberto para edição: {path.name}")
        self._refresh_output_dir_hint()

    def _clear_current_document(self) -> None:
        self._current_file = None
        self._editor_win.setWindowTitle("Editor de Código HTML")
        self._browser_win.setWindowTitle("Preview do Documento (Navegador)")
        self._editor_win.set_content("")
        self._browser_win.update_preview("", QUrl())
        self._refresh_output_dir_hint()

    def _sync_preview(self, html_content: str) -> None:
        """Called automatically when the editor content changes."""
        if not self._current_file:
            return

        if self._editor_win.is_dirty():
            self._autosave_timer.start()
            
        temp_path = Path(self._temp_dir) / "live_preview.html"
        write_html_file(temp_path, html_content)

        base_url = QUrl.fromLocalFile(str(self._current_file.parent) + "/")
        self._browser_win.update_preview(html_content, base_url)

    def _on_editor_dirty_changed(self, dirty: bool) -> None:
        if dirty and self._current_file:
            self._status.showMessage("Alteracoes nao salvas. Autosave em instantes...")
            self._autosave_timer.start()
        else:
            self._autosave_timer.stop()

    def _autosave_file(self) -> None:
        if not self._current_file or not self._editor_win.is_dirty():
            return
        try:
            write_html_file(self._current_file, self._editor_win.get_content())
            self._editor_win.mark_saved()
            touch_document_metadata(self._current_file)
            self._status.showMessage(f"Autosave concluido: {self._current_file.name}")
            self._append_log(f"Autosave: {self._current_file}")
            self._refresh_output_dir_hint()
        except Exception as exc:
            self._append_log(f"Falha no autosave: {exc}")

    def _save_file(self) -> None:
        if not self._current_file:
            return
        try:
            create_document_snapshot(self._current_file, "salvar")
            write_html_file(self._current_file, self._editor_win.get_content())
            self._editor_win.mark_saved()
            touch_document_metadata(self._current_file)
            self._status.showMessage(f"Salvo: {self._current_file}")
            self._append_log(f"Arquivo salvo: {self._current_file}")
            self._refresh_output_dir_hint()
        except Exception as exc:
            QMessageBox.critical(self, "Erro ao salvar", str(exc))

    # ----- Capture (10x logic) -----

    def _apply_selected_preset(self) -> None:
        preset_id = self._preset_input.currentData()
        preset = get_export_preset(str(preset_id))
        self._scale_factor_input.setText(str(preset.scale_factor))
        self._pdf_ppi_input.setText(str(int(preset.pdf_ppi)))
        self._chk_pdf.setChecked(preset.create_pdf)
        self._chk_jpg.setChecked(preset.create_jpg)
        self._chk_png.setChecked(preset.create_png)

    def _output_dir_for_path(self, path: Path | None) -> Path:
        generated_root = self._generated_docs_dir().resolve()
        if path is None:
            return generated_root

        resolved_path = path.resolve()
        source_root = self._source_html_dir().resolve()
        if resolved_path.is_relative_to(source_root):
            relative_parent = resolved_path.relative_to(source_root).parent
            return (generated_root / relative_parent).resolve()
        if resolved_path.is_relative_to(generated_root):
            relative_parent = resolved_path.relative_to(generated_root).parent
            return (generated_root / relative_parent).resolve()
        return generated_root

    def _refresh_output_dir_hint(self) -> None:
        candidate = (
            self._current_file
            or self._selected_path(self._todo_list)
            or self._selected_path(self._done_list)
        )
        self._output_dir_input.setText(str(self._output_dir_for_path(candidate)))

    def _mirror_supporting_assets(self, source_dir: Path, target_dir: Path) -> None:
        source_dir = source_dir.resolve()
        target_dir = target_dir.resolve()
        if source_dir == target_dir:
            return

        for item in source_dir.iterdir():
            if item.suffix.lower() in HTML_SUFFIXES:
                continue

            target_item = target_dir / item.name
            if target_item.exists():
                continue

            try:
                os.symlink(item, target_item, target_is_directory=item.is_dir())
                continue
            except OSError:
                pass

            if item.is_dir():
                shutil.copytree(item, target_item, dirs_exist_ok=True)
            else:
                shutil.copy2(item, target_item)

    def _start_capture(self) -> None:
        if self._worker_thread and self._worker_thread.is_alive():
            return

        # Always capture what's in the editor, NOT just the loaded file on disk,
        # so live edits are reflected.
        content = self._editor_win.get_content()
        if not content.strip() and not self._current_file:
            QMessageBox.warning(self, "Nenhum arquivo ativo", "Abra o Editor para um arquivo primeiro.")
            return
            
        # If the editor has no active content (window closed etc), fallback to reading file directly
        if not content.strip() and self._current_file:
            content = read_html_file(self._current_file)

        if not (self._chk_pdf.isChecked() or self._chk_jpg.isChecked() or self._chk_png.isChecked()):
            QMessageBox.warning(self, "Nenhum formato", "Selecione ao menos um formato na lista.")
            return

        try:
            scale_factor = int(self._scale_factor_input.text().strip())
            pdf_ppi = float(self._pdf_ppi_input.text().strip())
        except ValueError:
            QMessageBox.critical(self, "Erro numérico", "Valores nas configurações estão inválidos.")
            return

        # Captura na proporção exata sendo visualizada no momento
        viewport_width = max(DEFAULT_VIEWPORT_WIDTH, self._browser_win.width())
        # O None faz com que a largura alvo seja (viewport * scale_factor)
        target_width = None

        output_dir = self._output_dir_for_path(self._current_file)
        output_dir.mkdir(parents=True, exist_ok=True)
        self._output_dir_input.setText(str(output_dir))

        temp_html = Path(self._temp_dir) / "capture_source.html"
        write_html_file(temp_html, content)

        if self._current_file and self._current_file.parent != Path(self._temp_dir):
            self._mirror_supporting_assets(self._current_file.parent, Path(self._temp_dir))
            self._mirror_supporting_assets(self._current_file.parent, output_dir)

        base_name = self._current_file.stem if self._current_file else "captura"
        finished_html_path = output_dir / f"{base_name}.html"
        if self._current_file:
            create_document_snapshot(self._current_file, "exportar")
        write_html_file(finished_html_path, content)
        source_metadata = (
            load_document_metadata(self._current_file)
            if self._current_file
            else DocumentMetadata.for_document(finished_html_path)
        )
        upsert_document_metadata(
            finished_html_path,
            titulo=source_metadata.titulo or finished_html_path.stem,
            tipo=source_metadata.tipo,
            interessado=source_metadata.interessado,
            tags=source_metadata.tags,
            status="finalizado",
            template_origem=source_metadata.template_origem,
        )
        self._last_finished_html_path = finished_html_path
        requested_formats = [
            extension
            for extension, enabled in {
                "html": True,
                "png": self._chk_png.isChecked(),
                "jpg": self._chk_jpg.isChecked(),
                "pdf": self._chk_pdf.isChecked(),
            }.items()
            if enabled
        ]
        self._pending_generation_manifest = {
            "origem": str(self._current_file) if self._current_file else "",
            "html_final": str(finished_html_path),
            "template": source_metadata.template_origem,
            "gerado_em": utc_now(),
            "formatos_solicitados": requested_formats,
            "configuracao": {
                "viewport_width": viewport_width,
                "scale_factor": scale_factor,
                "target_width": target_width,
                "pdf_resolution": pdf_ppi,
            },
        }
        self._pending_manifest_output_dir = output_dir
        self._pending_manifest_base_name = base_name
        self._reload_generated_directory()
        self._select_path_in_list(self._done_list, finished_html_path)

        self._set_capturing(True)
        self._append_log(
            f"Capturando na proporção da tela | Escala {scale_factor}x | destino {output_dir}"
        )

        self._worker_thread = threading.Thread(
            target=self._capture_worker,
            args=(
                temp_html,
                GenerationSettings(
                    output_dir=output_dir,
                    viewport_width=viewport_width,
                    scale_factor=scale_factor,
                    target_width=target_width,
                    pdf_resolution=pdf_ppi,
                    create_png=self._chk_png.isChecked(),
                    create_jpg=self._chk_jpg.isChecked(),
                    create_pdf=self._chk_pdf.isChecked(),
                ),
                base_name,
            ),
            daemon=True,
        )
        self._worker_thread.start()

    def _paths_from_list_widget(self, list_widget: QListWidget) -> list[Path]:
        items = list_widget.selectedItems()
        if not items:
            items = [list_widget.item(index) for index in range(list_widget.count())]
        return [
            item.data(Qt.ItemDataRole.UserRole)
            for item in items
            if item is not None and item.data(Qt.ItemDataRole.UserRole) is not None
        ]

    def _start_batch_capture(self) -> None:
        if self._worker_thread and self._worker_thread.is_alive():
            return

        paths = [
            path
            for path in [
                *self._paths_from_list_widget(self._todo_list),
                *self._paths_from_list_widget(self._done_list),
            ]
            if path.suffix.lower() in HTML_SUFFIXES
        ]
        if not paths:
            QMessageBox.warning(self, "Nenhum HTML", "Nenhum documento HTML disponivel para lote.")
            return

        if not (self._chk_pdf.isChecked() or self._chk_jpg.isChecked() or self._chk_png.isChecked()):
            QMessageBox.warning(self, "Nenhum formato", "Selecione ao menos um formato na lista.")
            return

        try:
            scale_factor = int(self._scale_factor_input.text().strip())
            pdf_ppi = float(self._pdf_ppi_input.text().strip())
        except ValueError:
            QMessageBox.critical(self, "Erro numérico", "Valores nas configurações estão inválidos.")
            return

        answer = QMessageBox.question(
            self,
            "Exportar lote",
            f"Exportar {len(paths)} documento(s) HTML visivel(is)/selecionado(s)?",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        jobs = [
            {
                "html_path": path,
                "output_dir": self._output_dir_for_path(path),
                "base_name": path.stem,
            }
            for path in paths
        ]

        self._set_capturing(True)
        self._append_log(f"Iniciando exportacao em lote: {len(jobs)} documento(s).")
        self._worker_thread = threading.Thread(
            target=self._batch_capture_worker,
            args=(
                jobs,
                scale_factor,
                pdf_ppi,
                self._chk_png.isChecked(),
                self._chk_jpg.isChecked(),
                self._chk_pdf.isChecked(),
            ),
            daemon=True,
        )
        self._worker_thread.start()

    def _batch_capture_worker(
        self,
        jobs: list[dict],
        scale_factor: int,
        pdf_ppi: float,
        create_png: bool,
        create_jpg: bool,
        create_pdf: bool,
    ) -> None:
        try:
            results: list[dict] = []
            for job in jobs:
                html_path: Path = job["html_path"]
                output_dir: Path = job["output_dir"]
                base_name: str = job["base_name"]
                output_dir.mkdir(parents=True, exist_ok=True)

                self.log_signal.emit(f"Lote: preparando {html_path.name}...")
                create_document_snapshot(html_path, "lote")
                content = read_html_file(html_path)
                finished_html_path = output_dir / f"{base_name}.html"
                write_html_file(finished_html_path, content)
                self._mirror_supporting_assets(html_path.parent, output_dir)

                source_metadata = load_document_metadata(html_path)
                upsert_document_metadata(
                    finished_html_path,
                    titulo=source_metadata.titulo or finished_html_path.stem,
                    tipo=source_metadata.tipo,
                    interessado=source_metadata.interessado,
                    tags=source_metadata.tags,
                    status="finalizado",
                    template_origem=source_metadata.template_origem,
                )

                settings = GenerationSettings(
                    output_dir=output_dir,
                    viewport_width=DEFAULT_VIEWPORT_WIDTH,
                    scale_factor=scale_factor,
                    target_width=None,
                    pdf_resolution=pdf_ppi,
                    create_png=create_png,
                    create_jpg=create_jpg,
                    create_pdf=create_pdf,
                )
                created = export_html_outputs(
                    html_path=finished_html_path,
                    settings=settings,
                    base_output_name=base_name,
                )
                for file_path in created.values():
                    upsert_document_metadata(Path(file_path), status="finalizado")

                requested_formats = [
                    extension
                    for extension, enabled in {
                        "html": True,
                        "png": create_png,
                        "jpg": create_jpg,
                        "pdf": create_pdf,
                    }.items()
                    if enabled
                ]
                manifest_path = write_generation_manifest(
                    output_dir,
                    base_name,
                    {
                        "origem": str(html_path),
                        "html_final": str(finished_html_path),
                        "template": source_metadata.template_origem,
                        "gerado_em": utc_now(),
                        "formatos_solicitados": requested_formats,
                        "configuracao": {
                            "viewport_width": DEFAULT_VIEWPORT_WIDTH,
                            "scale_factor": scale_factor,
                            "target_width": None,
                            "pdf_resolution": pdf_ppi,
                        },
                        "arquivos_gerados": {
                            extension: str(path)
                            for extension, path in created.items()
                        },
                    },
                )
                results.append(
                    {
                        "html": finished_html_path,
                        "created": created,
                        "manifest": manifest_path,
                    }
                )
            self.batch_finished.emit(results)
        except Exception:
            self.capture_error.emit(traceback.format_exc())

    def _capture_worker(
        self,
        html_path: Path,
        settings: GenerationSettings,
        base_name: str,
    ) -> None:
        try:
            target_str = (
                f"{settings.target_width}px"
                if settings.target_width
                else f"automático ({settings.scale_factor}x)"
            )
            self.log_signal.emit(f"Playwright: renderizando DOM (largura: {target_str})...")
            created = export_html_outputs(
                html_path=html_path,
                settings=settings,
                base_output_name=base_name,
            )
            for extension in created:
                self.log_signal.emit(f"{extension.upper()} finalizado.")

            self.capture_finished.emit(created)
        except Exception:
            self.capture_error.emit(traceback.format_exc())

    def _on_capture_finished(self, created: dict) -> None:
        self._worker_thread = None
        self._set_capturing(False)
        for file_path in created.values():
            upsert_document_metadata(Path(file_path), status="finalizado")
        if (
            self._pending_generation_manifest is not None
            and self._pending_manifest_output_dir is not None
            and self._pending_manifest_base_name is not None
        ):
            self._pending_generation_manifest["arquivos_gerados"] = {
                extension: str(path)
                for extension, path in created.items()
            }
            manifest_path = write_generation_manifest(
                self._pending_manifest_output_dir,
                self._pending_manifest_base_name,
                self._pending_generation_manifest,
            )
            self._append_log(f"Manifesto gerado: {manifest_path}")
        self._pending_generation_manifest = None
        self._pending_manifest_output_dir = None
        self._pending_manifest_base_name = None
        self._reload_generated_directory()
        self._select_path_in_list(self._done_list, self._last_finished_html_path)
        for file_path in created.values():
            self._append_log(f"Gerado: {file_path}")
        self._append_log("✅ Processo concluído com sucesso!")
        QMessageBox.information(self, "Sucesso", "Arquivos gerados/capturados.")

    def _on_batch_finished(self, results: list) -> None:
        self._worker_thread = None
        self._set_capturing(False)
        self._reload_generated_directory()
        for result in results:
            self._append_log(f"Lote HTML: {result['html']}")
            for file_path in result["created"].values():
                self._append_log(f"Lote gerado: {file_path}")
            self._append_log(f"Lote manifesto: {result['manifest']}")
        QMessageBox.information(
            self,
            "Lote concluido",
            f"Exportacao em lote concluida: {len(results)} documento(s).",
        )

    def _on_capture_error(self, error_text: str) -> None:
        self._worker_thread = None
        self._set_capturing(False)
        self._pending_generation_manifest = None
        self._pending_manifest_output_dir = None
        self._pending_manifest_base_name = None
        self._reload_generated_directory()
        self._select_path_in_list(self._done_list, self._last_finished_html_path)
        self._append_log(f"❌ Erro:\n{error_text}")
        QMessageBox.critical(self, "Erro crítico", "Falha no motor de renderização.")

    def _set_capturing(self, is_capturing: bool) -> None:
        self._progress.setVisible(is_capturing)
        self._btn_capture.setEnabled(not is_capturing)
        self._btn_batch_capture.setEnabled(not is_capturing)
        if is_capturing:
            self._status.showMessage("Processando imagem de escala gigapixel, aguarde...")
        else:
            self._status.showMessage("Pronto para editar e exportar novos documentos.")

    def _append_log(self, message: str) -> None:
        self._log.append(message)
        sbr = self._log.verticalScrollBar()
        sbr.setValue(sbr.maximum())

    def closeEvent(self, event) -> None:
        if self._current_file and self._editor_win.is_dirty():
            try:
                write_html_file(self._current_file, self._editor_win.get_content())
                touch_document_metadata(self._current_file)
            except Exception:
                pass
        self._editor_win.close()
        self._browser_win.close()
        import shutil
        try:
            shutil.rmtree(self._temp_dir, ignore_errors=True)
        except Exception:
            pass
        super().closeEvent(event)


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Gerador de PDF Multi-Janela")
    # Para suportar rendering de fontes adequadamente em high DPI
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    
    window = ControlPanelWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
