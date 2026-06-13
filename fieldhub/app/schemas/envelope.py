"""dji http envelope - every device-facing response uses this shape."""

from typing import Any

from pydantic import BaseModel

CODE_OK = 0
CODE_ERROR = 1


class HttpResultResponse(BaseModel):
    """demo envelope: code 0 = success, non-zero = failure with message."""

    code: int = CODE_OK
    message: str = "success"
    data: Any = None


def ok(data: Any = None) -> HttpResultResponse:
    """success envelope."""
    return HttpResultResponse(data=data)


def error(message: str, code: int = CODE_ERROR) -> HttpResultResponse:
    """failure envelope."""
    return HttpResultResponse(code=code, message=message)
