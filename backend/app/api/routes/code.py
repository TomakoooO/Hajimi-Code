from fastapi import APIRouter, HTTPException

from app.core.response import err, ok
from app.models.schemas import CodeReadRequest, DiffPreviewRequest
from app.services.diff_service import build_diff_lines
from app.services.file_reader import read_code_by_address

router = APIRouter()


@router.post("/code/read")
def read_code(req: CodeReadRequest) -> dict:
    try:
        data = read_code_by_address(path=req.path, start_line=req.start_line, end_line=req.end_line)
        return ok(data)
    except HTTPException as exc:
        return err(code=20001, message=exc.detail, status=exc.status_code)


@router.post("/code/diff-preview")
def diff_preview(req: DiffPreviewRequest) -> dict:
    lines = build_diff_lines(req.before, req.after)
    return ok(
        {
            "legend": {"add": "green", "del": "red", "ctx": "normal"},
            "lines": lines,
        }
    )
