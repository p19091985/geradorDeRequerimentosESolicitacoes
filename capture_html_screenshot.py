from __future__ import annotations

import argparse
import html
import json
import math
import re
import shutil
import subprocess
import tempfile
import textwrap
from pathlib import Path

from PIL import Image
from playwright.sync_api import Page, sync_playwright

from core.template_catalog import load_default_template_path

Image.MAX_IMAGE_PIXELS = None


DEFAULT_VIEWPORT_WIDTH = 1600
DEFAULT_SCALE_FACTOR = 2
DEFAULT_TARGET_WIDTH = 15360
DEFAULT_PDF_RESOLUTION = 2600.0
MAX_BROWSER_RENDER_VIEWPORT_WIDTH = 8192
MAX_BROWSER_CAPTURE_OUTPUT_HEIGHT = 4000
BROWSER_RENDER_WAIT_MS = 3000
PLAYWRIGHT_RENDER_WAIT_MS = 600
BROWSER_CANDIDATES = (
    "google-chrome-stable",
    "google-chrome",
    "chromium",
    "chromium-browser",
)

def resolve_default_html_input() -> str:
    source_dir = Path("documentos_em_elaboracao")
    if source_dir.is_dir():
        html_paths = sorted(
            (
                path
                for path in source_dir.rglob("*")
                if path.is_file() and path.suffix.lower() in {".html", ".htm"}
            ),
            key=lambda path: (str(path.parent).lower(), path.name.lower()),
        )
        if html_paths:
            return str(html_paths[0])

    try:
        fallback = load_default_template_path()
        if fallback.is_file():
            return str(fallback)
    except Exception:
        pass

    return str(Path("template/template-solicitacao.html"))


def find_browser() -> str:
    for candidate in BROWSER_CANDIDATES:
        browser_path = shutil.which(candidate)
        if browser_path:
            return browser_path
    raise FileNotFoundError(
        "Nenhum navegador compatível foi encontrado. "
        "Instale google-chrome, google-chrome-stable ou chromium."
    )


def _run_browser_command(args: list[str]) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        args,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        command = " ".join(args)
        raise RuntimeError(
            "Falha ao executar o navegador.\n"
            f"Comando: {command}\n"
            f"Saída padrão:\n{result.stdout}\n"
            f"Saída de erro:\n{result.stderr}"
        )
    return result


def _build_measurement_wrapper(target_uri: str, viewport_width: int) -> str:
    escaped_uri = html.escape(target_uri, quote=True)
    return textwrap.dedent(
        f"""\
        <!doctype html>
        <html>
        <body style="margin:0">
        <iframe
          id="frame"
          src="{escaped_uri}"
          style="width:{viewport_width}px;border:0;display:block"
        ></iframe>
        <script>
        const frame = document.getElementById("frame");
        frame.addEventListener("load", () => {{
          setTimeout(() => {{
            try {{
              const doc = frame.contentDocument;
              const root = doc.documentElement;
              const body = doc.body;
              const width = Math.ceil(Math.max(
                body.scrollWidth,
                body.offsetWidth,
                root.clientWidth,
                root.scrollWidth,
                root.offsetWidth
              ));
              const height = Math.ceil(Math.max(
                body.scrollHeight,
                body.offsetHeight,
                root.clientHeight,
                root.scrollHeight,
                root.offsetHeight
              ));
              document.body.innerHTML =
                '<pre id="size">' + JSON.stringify({{ width, height }}) + "</pre>";
            }} catch (error) {{
              document.body.innerHTML =
                '<pre id="size">ERR:' + error.message + "</pre>";
            }}
          }}, 300);
        }});
        </script>
        </body>
        </html>
        """
    )


def measure_html_page(
    html_path: Path,
    browser: str | None = None,
    viewport_width: int = DEFAULT_VIEWPORT_WIDTH,
) -> tuple[int, int]:
    html_path = html_path.resolve()
    browser = browser or find_browser()
    with sync_playwright() as playwright:
        browser_instance = playwright.chromium.launch(
            executable_path=browser,
            headless=True,
        )
        try:
            context = browser_instance.new_context(
                viewport={"width": viewport_width, "height": 900},
            )
            page = context.new_page()
            page.goto(html_path.as_uri(), wait_until="load")
            page.wait_for_timeout(PLAYWRIGHT_RENDER_WAIT_MS)
            width, height = _measure_page_dimensions(page)
        finally:
            browser_instance.close()

    if width <= 0 or height <= 0:
        raise RuntimeError(
            "As dimensões calculadas pelo navegador são inválidas: "
            f"{width}x{height}."
        )
    return width, height


def _measure_page_dimensions(page: Page) -> tuple[int, int]:
    size_data = page.evaluate(
        """() => {
            const root = document.documentElement;
            const body = document.body;
            return {
                width: Math.ceil(Math.max(
                    body.scrollWidth,
                    body.offsetWidth,
                    root.clientWidth,
                    root.scrollWidth,
                    root.offsetWidth
                )),
                height: Math.ceil(Math.max(
                    body.scrollHeight,
                    body.offsetHeight,
                    root.clientHeight,
                    root.scrollHeight,
                    root.offsetHeight
                ))
            };
        }"""
    )
    return int(size_data["width"]), int(size_data["height"])


def _resolve_capture_viewport_width(
    measured_width: int,
    requested_viewport_width: int,
    target_width: int | None,
    scale_factor: int,
) -> int:
    if target_width is None:
        return max(measured_width, requested_viewport_width)

    minimum_direct_render_width = math.ceil(target_width / max(1, scale_factor))
    return max(
        measured_width,
        requested_viewport_width,
        min(MAX_BROWSER_RENDER_VIEWPORT_WIDTH, minimum_direct_render_width),
    )


def _write_wrapper_html(contents: str, prefix: str) -> Path:
    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".html",
        prefix=prefix,
        delete=False,
        encoding="utf-8",
    ) as wrapper_file:
        wrapper_file.write(contents)
        return Path(wrapper_file.name)


def _build_capture_wrapper(
    target_uri: str,
    viewport_width: int,
    viewport_height: int,
    scroll_top: int = 0,
) -> str:
    escaped_uri = html.escape(target_uri, quote=True)
    return textwrap.dedent(
        f"""\
        <!doctype html>
        <html>
        <head>
        <meta charset="utf-8">
        <style>
        html, body {{
          margin: 0;
          padding: 0;
          overflow: hidden;
          background: white;
        }}
        iframe {{
          display: block;
          width: {viewport_width}px;
          height: {viewport_height}px;
          border: 0;
        }}
        </style>
        </head>
        <body>
        <iframe id="frame" src="{escaped_uri}"></iframe>
        <script>
        const frame = document.getElementById("frame");
        const scrollTop = {scroll_top};
        const applyScroll = () => {{
          try {{
            const win = frame.contentWindow;
            const doc = win.document;
            win.scrollTo(0, scrollTop);
            doc.documentElement.scrollTop = scrollTop;
            doc.body.scrollTop = scrollTop;
          }} catch (error) {{
            console.error(error);
          }}
        }};
        frame.addEventListener("load", () => {{
          setTimeout(() => {{
            applyScroll();
            setTimeout(applyScroll, 150);
            setTimeout(applyScroll, 300);
          }}, 300);
        }});
        </script>
        </body>
        </html>
        """
    )


def _capture_uri_screenshot(
    uri: str,
    output_path: Path,
    browser: str,
    viewport_width: int,
    viewport_height: int,
    scale_factor: int,
) -> Path:
    output_path = output_path.resolve()
    _run_browser_command(
        [
            browser,
            "--headless",
            "--disable-gpu",
            "--hide-scrollbars",
            "--allow-file-access-from-files",
            "--no-first-run",
            "--disable-extensions",
            "--run-all-compositor-stages-before-draw",
            f"--virtual-time-budget={BROWSER_RENDER_WAIT_MS}",
            f"--force-device-scale-factor={scale_factor}",
            f"--window-size={viewport_width},{viewport_height}",
            f"--screenshot={output_path}",
            uri,
        ]
    )
    if not output_path.is_file():
        raise RuntimeError(
            "O navegador terminou a execução, mas o arquivo PNG não foi criado."
        )
    return output_path


def _stitch_vertical_images(image_paths: list[Path], output_path: Path) -> Path:
    if not image_paths:
        raise ValueError("Nenhuma imagem foi fornecida para montagem vertical.")

    opened_images: list[Image.Image] = []
    try:
        for image_path in image_paths:
            image = Image.open(image_path)
            image.load()
            opened_images.append(image)

        width = opened_images[0].width
        mode = opened_images[0].mode
        total_height = sum(image.height for image in opened_images)
        stitched = Image.new(mode, (width, total_height))

        current_y = 0
        for image in opened_images:
            if image.width != width:
                raise RuntimeError("As imagens capturadas possuem larguras distintas.")
            stitched.paste(image, (0, current_y))
            current_y += image.height

        stitched.save(output_path, format="PNG")
        return output_path
    finally:
        for image in opened_images:
            image.close()


def _capture_html_screenshot_tiled(
    html_path: Path,
    output_path: Path,
    browser: str,
    width: int,
    height: int,
    scale_factor: int,
) -> Path:
    tile_height = max(200, MAX_BROWSER_CAPTURE_OUTPUT_HEIGHT // scale_factor)
    tile_top_offsets = list(range(0, height, tile_height))

    with tempfile.TemporaryDirectory(prefix="capture_html_tiles_") as temp_dir:
        temp_root = Path(temp_dir)
        tile_paths: list[Path] = []

        for index, tile_top in enumerate(tile_top_offsets):
            current_tile_height = min(tile_height, height - tile_top)
            wrapper_path = _write_wrapper_html(
                _build_capture_wrapper(
                    target_uri=html_path.as_uri(),
                    viewport_width=width,
                    viewport_height=current_tile_height,
                    scroll_top=tile_top,
                ),
                prefix="capture_tile_",
            )
            tile_path = temp_root / f"tile_{index:03d}.png"
            try:
                _capture_uri_screenshot(
                    uri=wrapper_path.resolve().as_uri(),
                    output_path=tile_path,
                    browser=browser,
                    viewport_width=width,
                    viewport_height=current_tile_height,
                    scale_factor=scale_factor,
                )
            finally:
                wrapper_path.unlink(missing_ok=True)
            tile_paths.append(tile_path)

        return _stitch_vertical_images(tile_paths, output_path)


def capture_html_screenshot(
    html_path: Path,
    output_path: Path | None = None,
    browser: str | None = None,
    viewport_width: int = DEFAULT_VIEWPORT_WIDTH,
    scale_factor: int = DEFAULT_SCALE_FACTOR,
    target_width: int | None = None,
) -> Path:
    html_path = html_path.resolve()
    if not html_path.is_file():
        raise FileNotFoundError(f"Arquivo HTML não encontrado: {html_path}")

    browser = browser or find_browser()
    output_path = (output_path or html_path.with_suffix(".png")).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as playwright:
        browser_instance = playwright.chromium.launch(
            executable_path=browser,
            headless=True,
        )
        try:
            context = browser_instance.new_context(
                viewport={"width": viewport_width, "height": 900},
                device_scale_factor=scale_factor,
            )
            page = context.new_page()
            page.goto(html_path.as_uri(), wait_until="load")
            page.wait_for_timeout(PLAYWRIGHT_RENDER_WAIT_MS)

            width, height = _measure_page_dimensions(page)
            capture_viewport_width = _resolve_capture_viewport_width(
                measured_width=width,
                requested_viewport_width=viewport_width,
                target_width=target_width,
                scale_factor=scale_factor,
            )

            if capture_viewport_width > max(width, viewport_width):
                page.close()
                context.close()

                context = browser_instance.new_context(
                    viewport={"width": capture_viewport_width, "height": 900},
                    device_scale_factor=1,
                )
                page = context.new_page()
                page.goto(html_path.as_uri(), wait_until="load")
                page.wait_for_timeout(PLAYWRIGHT_RENDER_WAIT_MS)
                width, height = _measure_page_dimensions(page)

            effective_scale_factor = scale_factor
            if target_width is not None:
                effective_scale_factor = max(
                    scale_factor,
                    math.ceil(target_width / width),
                )

            page.close()
            context.close()

            context = browser_instance.new_context(
                viewport={
                    "width": width,
                    "height": min(
                        max(400, height),
                        max(400, MAX_BROWSER_CAPTURE_OUTPUT_HEIGHT // effective_scale_factor),
                    ),
                },
                device_scale_factor=effective_scale_factor,
            )
            page = context.new_page()
            page.goto(html_path.as_uri(), wait_until="load")
            page.wait_for_timeout(PLAYWRIGHT_RENDER_WAIT_MS)

            if height * effective_scale_factor > MAX_BROWSER_CAPTURE_OUTPUT_HEIGHT:
                _capture_playwright_tiled_screenshot(
                    page=page,
                    output_path=output_path,
                    width=width,
                    height=height,
                    scale_factor=effective_scale_factor,
                )
            else:
                page.screenshot(path=str(output_path), full_page=True)
        finally:
            browser_instance.close()

    if target_width is not None:
        resize_image_to_width(output_path, target_width, image_format="PNG")

    return output_path


def _capture_playwright_tiled_screenshot(
    page: Page,
    output_path: Path,
    width: int,
    height: int,
    scale_factor: int,
) -> Path:
    tile_height = max(200, MAX_BROWSER_CAPTURE_OUTPUT_HEIGHT // scale_factor)
    with tempfile.TemporaryDirectory(prefix="capture_html_tiles_") as temp_dir:
        temp_root = Path(temp_dir)
        tile_paths: list[Path] = []

        for index, tile_top in enumerate(range(0, height, tile_height)):
            current_tile_height = min(tile_height, height - tile_top)
            tile_path = temp_root / f"tile_{index:03d}.png"
            page.set_viewport_size(
                {
                    "width": width,
                    "height": current_tile_height,
                }
            )
            page.evaluate("(scrollTop) => window.scrollTo(0, scrollTop)", tile_top)
            page.wait_for_timeout(PLAYWRIGHT_RENDER_WAIT_MS)
            page.screenshot(path=str(tile_path))
            tile_paths.append(tile_path)

        return _stitch_vertical_images(tile_paths, output_path)


def resize_image_to_width(
    image_path: Path,
    target_width: int,
    image_format: str | None = None,
) -> Path:
    image_path = image_path.resolve()
    with Image.open(image_path) as image:
        if image.width == target_width:
            if image_format:
                image.save(image_path, format=image_format)
            return image_path

        target_height = round((target_width / image.width) * image.height)
        resized = image.resize((target_width, target_height), Image.Resampling.LANCZOS)
        save_kwargs: dict[str, object] = {}
        if image_format == "JPEG":
            resized = resized.convert("RGB")
            save_kwargs = {"quality": 95, "subsampling": 0, "optimize": True}
        elif image_format == "PDF":
            resized = resized.convert("RGB")
            save_kwargs = {"resolution": 300.0}
        resized.save(image_path, format=image_format, **save_kwargs)
    return image_path


def convert_png_to_jpg(png_path: Path, jpg_path: Path | None = None) -> Path:
    png_path = png_path.resolve()
    jpg_path = (jpg_path or png_path.with_suffix(".jpg")).resolve()
    with Image.open(png_path) as image:
        rgb_image = image.convert("RGB")
        rgb_image.save(
            jpg_path,
            format="JPEG",
            quality=95,
            subsampling=0,
            optimize=True,
        )
    return jpg_path


def convert_png_to_pdf(
    png_path: Path,
    pdf_path: Path | None = None,
    resolution: float = DEFAULT_PDF_RESOLUTION,
) -> Path:
    png_path = png_path.resolve()
    pdf_path = (pdf_path or png_path.with_suffix(".pdf")).resolve()
    with Image.open(png_path) as image:
        rgb_image = image.convert("RGB")
        rgb_image.save(pdf_path, format="PDF", resolution=resolution)
    return pdf_path


def render_document_assets(
    html_path: Path,
    base_output_name: str | None = None,
    output_dir: Path | None = None,
    browser: str | None = None,
    viewport_width: int = DEFAULT_VIEWPORT_WIDTH,
    scale_factor: int = DEFAULT_SCALE_FACTOR,
    target_width: int = DEFAULT_TARGET_WIDTH,
    pdf_resolution: float = DEFAULT_PDF_RESOLUTION,
    create_jpg: bool = True,
    create_pdf: bool = True,
) -> dict[str, Path]:
    html_path = html_path.resolve()
    base_name = base_output_name or html_path.stem
    resolved_output_dir = (output_dir or html_path.parent).resolve()
    resolved_output_dir.mkdir(parents=True, exist_ok=True)
    png_path = resolved_output_dir / f"{base_name}.png"

    created_png = capture_html_screenshot(
        html_path=html_path,
        output_path=png_path,
        browser=browser,
        viewport_width=viewport_width,
        scale_factor=scale_factor,
        target_width=target_width,
    )

    created_files: dict[str, Path] = {"png": created_png}
    if create_jpg:
        created_files["jpg"] = convert_png_to_jpg(
            created_png,
            resolved_output_dir / f"{base_name}.jpg",
        )
    if create_pdf:
        created_files["pdf"] = convert_png_to_pdf(
            created_png,
            resolved_output_dir / f"{base_name}.pdf",
            resolution=pdf_resolution,
        )
    return created_files


def parse_args() -> argparse.Namespace:
    default_html = resolve_default_html_input()
    parser = argparse.ArgumentParser(
        description=(
            "Renderiza um arquivo HTML local no navegador headless e salva "
            "capturas em alta resolução."
        )
    )
    parser.add_argument(
        "html_file",
        nargs="?",
        default=default_html,
        help=f"Arquivo HTML de entrada. Padrão: {default_html}",
    )
    parser.add_argument(
        "-o",
        "--output",
        help="Arquivo PNG de saída. Padrão: mesmo nome do HTML, na raiz.",
    )
    parser.add_argument(
        "--viewport-width",
        type=int,
        default=DEFAULT_VIEWPORT_WIDTH,
        help=f"Largura base do viewport em CSS pixels. Padrão: {DEFAULT_VIEWPORT_WIDTH}",
    )
    parser.add_argument(
        "--scale-factor",
        type=int,
        default=DEFAULT_SCALE_FACTOR,
        help=f"Fator de escala para alta resolução. Padrão: {DEFAULT_SCALE_FACTOR}",
    )
    parser.add_argument(
        "--target-width",
        type=int,
        default=DEFAULT_TARGET_WIDTH,
        help=(
            "Largura final desejada em pixels. O navegador amplia a renderização "
            "automaticamente para chegar o mais perto possível dessa definição. "
            f"Padrão: {DEFAULT_TARGET_WIDTH} (16K UHD)."
        ),
    )
    parser.add_argument(
        "--jpg",
        action="store_true",
        help="Gera também uma versão em JPG.",
    )
    parser.add_argument(
        "--pdf",
        action="store_true",
        help="Gera também uma versão em PDF embutindo a renderização 8K.",
    )
    parser.add_argument(
        "--pdf-resolution",
        type=float,
        default=DEFAULT_PDF_RESOLUTION,
        help=(
            "Resolução lógica do PDF em ppi. "
            f"Padrão: {DEFAULT_PDF_RESOLUTION}."
        ),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    html_path = Path(args.html_file)
    output_path = Path(args.output).resolve() if args.output else None

    if args.jpg or args.pdf:
        base_output_name = output_path.stem if output_path else None
        output_dir = output_path.parent if output_path else None
        created_files = render_document_assets(
            html_path=html_path,
            base_output_name=base_output_name,
            output_dir=output_dir,
            viewport_width=args.viewport_width,
            scale_factor=args.scale_factor,
            target_width=args.target_width,
            pdf_resolution=args.pdf_resolution,
            create_jpg=args.jpg,
            create_pdf=args.pdf,
        )
        for created_file in created_files.values():
            print(created_file)
        return 0

    created_file = capture_html_screenshot(
        html_path=html_path,
        output_path=output_path,
        viewport_width=args.viewport_width,
        scale_factor=args.scale_factor,
        target_width=args.target_width,
    )
    print(created_file)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
