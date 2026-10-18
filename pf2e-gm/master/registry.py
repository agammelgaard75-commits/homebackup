"""Discover tool metadata from each tool's own folder."""

from dataclasses import dataclass
import json
from pathlib import Path


@dataclass(frozen=True)
class Tool:
    slug: str
    name: str
    purpose: str
    folder: Path
    implemented: bool


def discover_tools(root: Path) -> list[Tool]:
    tools = []
    seen_slugs = set()
    for folder in sorted(root.iterdir()):
        if not folder.is_dir():
            continue
        manifest = folder / "tool.json"
        if not manifest.is_file():
            continue
        data = json.loads(manifest.read_text(encoding="utf-8"))
        tool = Tool(**{key: data[key] for key in ("slug", "name", "purpose")}, folder=folder, implemented=(folder / "tool.py").is_file())
        if not tool.slug or not all(c.islower() or c.isdigit() or c == "-" for c in tool.slug):
            raise ValueError(f"Invalid tool slug in {manifest}")
        if not tool.name.strip() or not tool.purpose.strip():
            raise ValueError(f"Empty tool name or purpose in {manifest}")
        if tool.slug in seen_slugs:
            raise ValueError(f"Duplicate tool slug: {tool.slug}")
        seen_slugs.add(tool.slug)
        tools.append(tool)
    return tools
