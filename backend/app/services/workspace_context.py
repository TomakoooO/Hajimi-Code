from pathlib import Path

from app.core.config import settings

_active_workspace_root = Path(settings.workspace_root).resolve()
_global_search_roots = [
    Path(settings.workspace_root).resolve(),
    Path(settings.workspace_root).resolve().parent,
]
_workspace_mappings: dict[str, str] = {}


def get_workspace_root() -> Path:
    return _active_workspace_root


def get_workspace_mappings() -> dict[str, str]:
    return dict(_workspace_mappings)


def set_workspace_root(path: str, project_name: str | None = None) -> dict:
    candidate = Path(path).resolve()
    if not candidate.exists() or not candidate.is_dir():
        raise ValueError(f"workspace does not exist: {candidate}")

    global _active_workspace_root
    _active_workspace_root = candidate
    settings.workspace_root = str(candidate)

    if project_name:
        _workspace_mappings[project_name] = str(candidate)

    return {
        "workspace_root": str(candidate),
        "project_name": project_name,
        "mappings": get_workspace_mappings(),
    }


def _list_child_names(path: Path, limit: int = 200) -> set[str]:
    names: set[str] = set()
    try:
        for idx, child in enumerate(path.iterdir()):
            if idx >= limit:
                break
            names.add(child.name.lower())
    except Exception:
        return set()
    return names


def _dedupe_paths(paths: list[Path]) -> list[Path]:
    seen: set[Path] = set()
    out: list[Path] = []
    for p in paths:
        rp = p.resolve()
        if rp in seen:
            continue
        seen.add(rp)
        out.append(rp)
    return out


def switch_workspace_by_project_name(project_name: str, top_level_entries: list[str] | None = None) -> dict:
    if not project_name.strip():
        raise ValueError("project_name is required")

    mapped = _workspace_mappings.get(project_name)
    if mapped:
        return set_workspace_root(mapped, project_name=project_name)

    matches: list[Path] = []
    for base in _global_search_roots:
        if not base.exists() or not base.is_dir():
            continue
        # Local IDE mode: search recursively under backend-visible roots.
        if base.name == project_name:
            matches.append(base)
        try:
            matches.extend([p for p in base.iterdir() if p.is_dir() and p.name == project_name])
        except Exception:
            pass
        try:
            matches.extend([p for p in base.rglob(project_name) if p.is_dir()])
        except Exception:
            pass

    unique_matches = _dedupe_paths(matches)
    if not unique_matches:
        return {
            "workspace_root": str(get_workspace_root()),
            "project_name": project_name,
            "switched": False,
            "reason": "project not found under backend-visible roots",
            "mappings": get_workspace_mappings(),
        }

    # If frontend gives top-level entries, use them as a lightweight fingerprint.
    expected = {x.strip().lower() for x in (top_level_entries or []) if x.strip()}
    if expected:
        ranked = sorted(
            unique_matches,
            key=lambda p: (
                -len(expected.intersection(_list_child_names(p))),
                len(p.parts),
            ),
        )
        match = ranked[0]
    else:
        # fallback: nearest path depth
        match = sorted(unique_matches, key=lambda p: len(p.parts))[0]

    payload = set_workspace_root(str(match), project_name=project_name)
    payload["switched"] = True
    payload["matched_by"] = "fingerprint" if expected else "name"
    return payload
