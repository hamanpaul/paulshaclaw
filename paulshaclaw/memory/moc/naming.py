from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from paulshaclaw.memory.moc import frontmatter_io


def slugify(title: str) -> str:
    """Convert title to kebab-case slug."""
    if not title or not title.strip():
        return "untitled"
    slug = title.lower()
    slug = re.sub(r'[^\w\s-]', '', slug)
    slug = re.sub(r'[\s_]+', '-', slug)
    slug = slug.strip('-')
    return slug if slug else "untitled"


def _title(fm: dict[str, Any], body: str) -> str:
    """Extract title from frontmatter, markdown heading, or fallback."""
    if "title" in fm and fm["title"]:
        return str(fm["title"])
    
    lines = body.strip().split('\n')
    for line in lines:
        line = line.strip()
        if line.startswith('#'):
            heading = line.lstrip('#').strip()
            if heading:
                return heading
            break
    
    artifact_kind = fm.get("artifact_kind", "unknown")
    project = fm.get("project", "unknown")
    return f"{artifact_kind}-{project}"


def target_name(fm: dict[str, Any], body: str) -> str:
    """Generate target filename: <slug>--<slice_id>.md"""
    title = _title(fm, body)
    slug = slugify(title)
    slice_id = fm.get("slice_id", "unknown")
    return f"{slug}--{slice_id}.md"


def reconcile(memory_root: Path) -> list[str]:
    """Scan knowledge files, rename to target names, dedup by slice_id."""
    warnings: list[str] = []
    knowledge_dir = memory_root / "knowledge"
    
    if not knowledge_dir.exists():
        return warnings
    
    slice_map: dict[str, list[Path]] = {}
    
    for md_file in knowledge_dir.rglob("*.md"):
        try:
            text = md_file.read_text(encoding="utf-8")
            fm, body = frontmatter_io.read(text)
            
            if fm.get("memory_layer") != "knowledge":
                continue
            
            slice_id = fm.get("slice_id")
            if not slice_id:
                warnings.append(f"No slice_id in {md_file}")
                continue
            
            if slice_id not in slice_map:
                slice_map[slice_id] = []
            slice_map[slice_id].append(md_file)
            
        except Exception as e:
            warnings.append(f"Error processing {md_file}: {e}")
    
    for slice_id, paths in slice_map.items():
        if len(paths) > 1:
            paths.sort(key=lambda p: p.stat().st_mtime, reverse=True)
            keep = paths[0]
            for remove in paths[1:]:
                remove.unlink()
                warnings.append(f"Removed duplicate {remove}")
            paths = [keep]
        
        if paths:
            md_file = paths[0]
            try:
                text = md_file.read_text(encoding="utf-8")
                fm, body = frontmatter_io.read(text)
                
                new_name = target_name(fm, body)
                new_path = md_file.parent / new_name
                
                if md_file != new_path:
                    if new_path.exists():
                        warnings.append(f"Target {new_path} already exists, skipping rename")
                    else:
                        md_file.rename(new_path)
                        
            except Exception as e:
                warnings.append(f"Error renaming {md_file}: {e}")
    
    return warnings
