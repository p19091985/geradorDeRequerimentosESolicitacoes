from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ExportPreset:
    id: str
    nome: str
    scale_factor: int
    pdf_ppi: float
    create_pdf: bool = True
    create_jpg: bool = False
    create_png: bool = False


EXPORT_PRESETS: tuple[ExportPreset, ...] = (
    ExportPreset(
        id="rascunho",
        nome="Rascunho",
        scale_factor=2,
        pdf_ppi=150.0,
        create_pdf=True,
    ),
    ExportPreset(
        id="normal",
        nome="Normal",
        scale_factor=4,
        pdf_ppi=300.0,
        create_pdf=True,
    ),
    ExportPreset(
        id="alta",
        nome="Alta resolucao",
        scale_factor=10,
        pdf_ppi=2600.0,
        create_pdf=True,
        create_png=True,
    ),
    ExportPreset(
        id="arquivo-leve",
        nome="Arquivo leve",
        scale_factor=2,
        pdf_ppi=120.0,
        create_pdf=True,
        create_jpg=True,
    ),
)


def get_export_preset(preset_id: str) -> ExportPreset:
    for preset in EXPORT_PRESETS:
        if preset.id == preset_id:
            return preset
    return EXPORT_PRESETS[1]
