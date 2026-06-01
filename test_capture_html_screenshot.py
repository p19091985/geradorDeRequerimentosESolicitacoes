from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
import subprocess
from unittest import mock

from PIL import Image

from capture_html_screenshot import (
    DEFAULT_PDF_RESOLUTION,
    DEFAULT_SCALE_FACTOR,
    DEFAULT_VIEWPORT_WIDTH,
    MAX_BROWSER_RENDER_VIEWPORT_WIDTH,
    _resolve_capture_viewport_width,
    capture_html_screenshot,
    measure_html_page,
    render_document_assets,
)
from rendering.exporter import GenerationSettings, export_html_outputs


ROOT_DIR = Path(__file__).resolve().parent
HTML_FILE = ROOT_DIR / "template" / "template-solicitacao.html"


def find_last_ink_row(
    image_path: Path,
    darkness_threshold: int = 240,
    min_dark_pixels: int = 10,
) -> int:
    Image.MAX_IMAGE_PIXELS = None
    with Image.open(image_path) as image:
        grayscale = image.convert("L")
        width, height = grayscale.size
        last_ink_row = -1
        for y in range(height):
            row = grayscale.crop((0, y, width, y + 1))
            dark_pixels = sum(row.histogram()[:darkness_threshold])
            if dark_pixels > min_dark_pixels:
                last_ink_row = y
        return last_ink_row


class CaptureHtmlScreenshotTests(unittest.TestCase):
    def assert_footer_visible(self, image_path: Path, minimum_ratio: float = 0.90) -> None:
        Image.MAX_IMAGE_PIXELS = None
        with Image.open(image_path) as image:
            last_ink_row = find_last_ink_row(image_path)
            self.assertGreater(last_ink_row, 0)
            self.assertGreater(
                last_ink_row / image.height,
                minimum_ratio,
                f"O rodapé visível terminou cedo demais em {image_path}.",
            )

    def test_measure_html_page_returns_positive_dimensions(self) -> None:
        width, height = measure_html_page(
            HTML_FILE,
            viewport_width=DEFAULT_VIEWPORT_WIDTH,
        )
        self.assertGreaterEqual(width, 1000)
        self.assertGreaterEqual(height, 1000)

    def test_resolve_capture_viewport_width_prefers_high_resolution_browser_width(
        self,
    ) -> None:
        self.assertEqual(
            _resolve_capture_viewport_width(
                measured_width=1600,
                requested_viewport_width=1600,
                target_width=15360,
                scale_factor=2,
            ),
            7680,
        )
        self.assertEqual(
            _resolve_capture_viewport_width(
                measured_width=1600,
                requested_viewport_width=1600,
                target_width=65536,
                scale_factor=2,
            ),
            MAX_BROWSER_RENDER_VIEWPORT_WIDTH,
        )

    def test_capture_html_screenshot_creates_valid_png(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_file = Path(temp_dir) / "solcitacao-test.png"
            measured_width, measured_height = measure_html_page(
                HTML_FILE,
                viewport_width=DEFAULT_VIEWPORT_WIDTH,
            )

            created_file = capture_html_screenshot(
                HTML_FILE,
                output_path=output_file,
                viewport_width=DEFAULT_VIEWPORT_WIDTH,
                scale_factor=DEFAULT_SCALE_FACTOR,
            )

            self.assertEqual(created_file, output_file.resolve())
            self.assertTrue(created_file.exists())

            with Image.open(created_file) as image:
                self.assertEqual(image.format, "PNG")
                self.assertEqual(
                    image.size,
                    (
                        measured_width * DEFAULT_SCALE_FACTOR,
                        measured_height * DEFAULT_SCALE_FACTOR,
                    ),
                )
                preview = image.convert("RGB").resize((64, 64))
                colors = preview.getcolors(maxcolors=64 * 64)
                self.assertIsNotNone(colors)
                self.assertGreater(len(colors), 10)

    def test_tiled_capture_keeps_footer_visible_in_png(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_file = Path(temp_dir) / "footer-visible.png"
            with mock.patch(
                "capture_html_screenshot.MAX_BROWSER_CAPTURE_OUTPUT_HEIGHT",
                1000,
            ):
                created_file = capture_html_screenshot(
                    HTML_FILE,
                    output_path=output_file,
                    viewport_width=DEFAULT_VIEWPORT_WIDTH,
                    scale_factor=DEFAULT_SCALE_FACTOR,
                    target_width=2048,
                )

            self.assertTrue(created_file.exists())
            with Image.open(created_file) as image:
                self.assertEqual(image.format, "PNG")
                self.assertEqual(image.width, 2048)
            self.assert_footer_visible(created_file)

    def test_render_document_assets_creates_jpg_and_pdf_with_target_width(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            created_files = render_document_assets(
                HTML_FILE,
                base_output_name="solcitacao-8k-test",
                output_dir=temp_root,
                viewport_width=DEFAULT_VIEWPORT_WIDTH,
                scale_factor=DEFAULT_SCALE_FACTOR,
                target_width=2048,
                pdf_resolution=DEFAULT_PDF_RESOLUTION,
                create_jpg=True,
                create_pdf=True,
            )

            self.assertIn("png", created_files)
            self.assertIn("jpg", created_files)
            self.assertIn("pdf", created_files)

            with Image.open(created_files["png"]) as png_image:
                self.assertEqual(png_image.format, "PNG")
                self.assertEqual(png_image.width, 2048)

            with Image.open(created_files["jpg"]) as jpg_image:
                self.assertEqual(jpg_image.format, "JPEG")
                self.assertEqual(jpg_image.width, 2048)

            pdf_bytes = created_files["pdf"].read_bytes()
            self.assertTrue(pdf_bytes.startswith(b"%PDF"))
            pdfimages_output = subprocess.run(
                ["pdfimages", "-list", str(created_files["pdf"])],
                check=True,
                capture_output=True,
                text=True,
            ).stdout
            self.assertIn("2600", pdfimages_output)

    def test_export_html_outputs_can_generate_only_pdf(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            settings = GenerationSettings(
                output_dir=temp_root,
                target_width=1024,
                pdf_resolution=2600.0,
                create_png=False,
                create_jpg=False,
                create_pdf=True,
            )

            created_files = export_html_outputs(HTML_FILE, settings)

            self.assertIn("pdf", created_files)
            self.assertNotIn("png", created_files)
            self.assertTrue(created_files["pdf"].exists())
            self.assertFalse((temp_root / "solcitacao.png").exists())

            pdfimages_output = subprocess.run(
                ["pdfimages", "-list", str(created_files["pdf"])],
                check=True,
                capture_output=True,
                text=True,
            ).stdout
            self.assertIn("2600", pdfimages_output)

    def test_export_html_outputs_can_generate_only_jpg_without_persisting_png(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            settings = GenerationSettings(
                output_dir=temp_root,
                target_width=1024,
                create_png=False,
                create_jpg=True,
                create_pdf=False,
            )

            created_files = export_html_outputs(HTML_FILE, settings)

            self.assertIn("jpg", created_files)
            self.assertNotIn("png", created_files)
            self.assertTrue(created_files["jpg"].exists())
            self.assertFalse((temp_root / "solcitacao.png").exists())

            with Image.open(created_files["jpg"]) as jpg_image:
                self.assertEqual(jpg_image.format, "JPEG")
                self.assertEqual(jpg_image.width, 1024)

    def test_export_html_outputs_keeps_footer_visible_in_pdf_for_gui_flow(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            settings = GenerationSettings(
                output_dir=temp_root,
                target_width=2048,
                pdf_resolution=2600.0,
                create_png=False,
                create_jpg=False,
                create_pdf=True,
            )

            with mock.patch(
                "capture_html_screenshot.MAX_BROWSER_CAPTURE_OUTPUT_HEIGHT",
                1000,
            ):
                created_files = export_html_outputs(HTML_FILE, settings)

            pdf_path = created_files["pdf"]
            rasterized_prefix = temp_root / "pdf_preview"
            subprocess.run(
                [
                    "pdftoppm",
                    "-jpeg",
                    "-f",
                    "1",
                    "-singlefile",
                    str(pdf_path),
                    str(rasterized_prefix),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            rasterized_pdf = rasterized_prefix.with_suffix(".jpg")
            self.assertTrue(rasterized_pdf.exists())
            self.assert_footer_visible(rasterized_pdf, minimum_ratio=0.90)


if __name__ == "__main__":
    unittest.main()
