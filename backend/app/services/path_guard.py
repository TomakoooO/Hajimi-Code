from pathlib import Path

from fastapi import HTTPException

from app.services.workspace_context import get_workspace_root

ALLOWED_EXT = {
    ".py",
    ".ts",
    ".js",
    ".vue",
    ".json",
    ".md",
    ".css",
    ".scss",
    ".html",
    ".yml",
    ".yaml",
    ".txt",
}


def resolve_safe_file_path(raw_path: str) -> Path:
    if not raw_path.strip():
        raise HTTPException(status_code=400, detail="path is required")

    workspace_root = get_workspace_root().resolve()
    input_path = Path(raw_path)
    candidate = input_path if input_path.is_absolute() else (workspace_root / input_path)
    candidate = candidate.resolve()

    if workspace_root not in candidate.parents and candidate != workspace_root:
        raise HTTPException(status_code=403, detail="path out of workspace")

    if candidate.suffix and candidate.suffix.lower() not in ALLOWED_EXT:
        raise HTTPException(status_code=400, detail=f"file extension not allowed: {candidate.suffix}")

    if not candidate.exists() or not candidate.is_file():
        raise HTTPException(status_code=404, detail="file not found")

    return candidate
