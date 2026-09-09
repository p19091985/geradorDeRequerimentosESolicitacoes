from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def manifest_path_for(output_dir: Path, base_name: str) -> Path:
    return output_dir / f"{base_name}.manifest.json"


def write_generation_manifest(
    output_dir: Path,
    base_name: str,
    manifest: dict[str, Any],
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = manifest_path_for(output_dir, base_name)
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest_path
