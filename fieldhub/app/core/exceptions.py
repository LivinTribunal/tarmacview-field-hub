"""hub api errors surfaced as dji envelope responses."""


class HubApiError(Exception):
    """error rendered as a non-zero HttpResultResponse envelope."""

    def __init__(self, code: int, message: str, http_status: int = 200):
        """store envelope code, message, and the http status to emit."""
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status
