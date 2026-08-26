"""HTTP 层稳定且不泄露底层异常的错误模型。"""

from pydantic import BaseModel, ConfigDict, Field


class _StrictFrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class ApiErrorDetail(_StrictFrozenModel):
    code: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9_]+$")
    message: str = Field(min_length=1, max_length=256)


class ApiErrorResponse(_StrictFrozenModel):
    error: ApiErrorDetail


class BusinessApiError(RuntimeError):
    """只携带可公开稳定 code/message 的 HTTP 业务错误。"""

    def __init__(self, *, status_code: int, code: str, message: str) -> None:
        self.status_code = status_code
        self.code = code
        self.public_message = message
        super().__init__(code)
