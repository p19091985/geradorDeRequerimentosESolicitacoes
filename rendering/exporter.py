from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from capture_html_screenshot import (
    DEFAULT_PDF_RESOLUTION,
    DEFAULT_SCALE_FACTOR,
    DEFAULT_TARGET_WIDTH,
    DEFAULT_VIEWPORT_WIDTH,
    capture_html_screenshot,
    convert_png_to_jpg,
    convert_png_to_pdf,
)


@dataclass(slots=True)
class GenerationSettings:
    output_dir: Path
    viewport_width: int = DEFAULT_VIEWPORT_WIDTH
    scale_factor: int = DEFAULT_SCALE_FACTOR
    target_width: int | None = DEFAULT_TARGET_WIDTH
    pdf_resolution: float = DEFAULT_PDF_RESOLUTION
    create_png: bool = True
    create_jpg: bool = False
    create_pdf: bool = True


def export_html_outputs(
    html_path: Path,
    settings: GenerationSettings,
    base_output_name: str | None = None,
) -> dict[str, Path]:
    """Export an HTML document to the requested output formats."""
    html_path = html_path.resolve()
    output_dir = settings.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    base_name = base_output_name or html_path.stem

    png_path = output_dir / f"{base_name}.png"
    created_png = capture_html_screenshot(
        html_path=html_path,
        output_path=png_path,
        viewport_width=settings.viewport_width,
        scale_factor=settings.scale_factor,
        target_width=settings.target_width,
    )

    created_files: dict[str, Path] = {}
    if settings.create_png:
        created_files["png"] = created_png
    if settings.create_jpg:
        created_files["jpg"] = convert_png_to_jpg(
            created_png,
            output_dir / f"{base_name}.jpg",
        )
    if settings.create_pdf:
        created_files["pdf"] = convert_png_to_pdf(
            created_png,
            output_dir / f"{base_name}.pdf",
            resolution=settings.pdf_resolution,
        )

    if not settings.create_png and created_png.exists():
        created_png.unlink()

    return created_files
