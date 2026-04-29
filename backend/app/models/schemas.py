from pydantic import BaseModel, Field


class CodeReadRequest(BaseModel):
    path: str = Field(..., description="代码地址（相对或绝对路径）")
    start_line: int = Field(1, ge=1)
    end_line: int | None = Field(default=None, ge=1)


class CodeRef(BaseModel):
    path: str


class CodeSnippet(BaseModel):
    path: str
    start_line: int = Field(1, ge=1)
    end_line: int = Field(1, ge=1)
    language: str = "plaintext"
    content: str = ""


class ChatFile(BaseModel):
    path: str
    language: str = "plaintext"
    content: str = ""


class ChatAskRequest(BaseModel):
    message: str = Field(..., min_length=1)
    session_id: str | None = None
    code_refs: list[CodeRef] = Field(default_factory=list)
    snippets: list[CodeSnippet] = Field(default_factory=list)
    files: list[ChatFile] = Field(default_factory=list)
    model: str | None = None


class DiffPreviewRequest(BaseModel):
    before: str
    after: str


class TimelineReplayQuery(BaseModel):
    request_id: str
