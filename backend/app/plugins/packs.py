"""Registry of code-shipped pack manifests.

Packs are data only: JSON/YAML manifests under `pack_manifests/`. They never
execute code and may reference only agents they define plus existing
skill/tool slugs.
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from app.runtime.models import PackManifest

MANIFEST_DIR = Path(__file__).with_name("pack_manifests")


class PackNotFound(KeyError):
    """Requested pack name is not registered."""


def _load_manifest(path: Path) -> PackManifest:
    if path.suffix == ".json":
        raw = json.loads(path.read_text(encoding="utf-8"))
    elif path.suffix in {".yaml", ".yml"}:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    else:
        raise ValueError(f"unsupported pack manifest type: {path.name}")
    if not isinstance(raw, dict):
        raise ValueError(f"pack manifest must be an object: {path.name}")
    return PackManifest.model_validate(raw)


def load_packs(directory: Path = MANIFEST_DIR) -> dict[str, PackManifest]:
    packs: dict[str, PackManifest] = {}
    if not directory.exists():
        return packs
    for path in sorted(directory.iterdir()):
        if path.suffix not in {".json", ".yaml", ".yml"}:
            continue
        manifest = _load_manifest(path)
        if manifest.name in packs:
            raise ValueError(f"duplicate pack name: {manifest.name}")
        packs[manifest.name] = manifest
    return packs


PACKS: dict[str, PackManifest] = load_packs()


def list_packs() -> list[PackManifest]:
    return [PACKS[name] for name in sorted(PACKS)]


def get_pack(name: str) -> PackManifest:
    try:
        return PACKS[name]
    except KeyError as exc:
        raise PackNotFound(name) from exc
