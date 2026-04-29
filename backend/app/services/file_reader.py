from pathlib import Path

from fastapi import HTTPException

from app.core.config import settings
from app.services.path_guard import resolve_safe_file_path


def read_code_by_address(path: str, start_line: int = 1, end_line: int | None = None) -> dict:
    file_path: Path = resolve_safe_file_path(path)
    content = file_path.read_text(encoding="utf-8", errors="replace")

    if len(content.encode("utf-8")) > settings.max_read_file_size:
        raise HTTPException(status_code=413, detail="file too large")

    lines = content.splitlines()
    total_lines = len(lines)
    end = end_line or total_lines
    end = min(end, total_lines)
    start = min(start_line, end) if total_lines else 1
    snippet = "\n".join(lines[start - 1 : end])

    return {
        "path": str(file_path),
        "language": file_path.suffix.lstrip(".") or "plaintext",
        "start_line": start,
        "end_line": end,
        "total_lines": total_lines,
        "content": snippet,
    }
