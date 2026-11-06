"""Errors that carry a plain-English explanation and a suggested fix for the UI."""


class UnifierrError(Exception):
    status_code = 400

    def __init__(self, message: str, *, explanation: str | None = None, fix: str | None = None,
                 status_code: int | None = None):
        super().__init__(message)
        self.message = message
        self.explanation = explanation
        self.fix = fix
        if status_code:
            self.status_code = status_code

    def to_dict(self) -> dict:
        return {"error": self.message, "explanation": self.explanation, "fix": self.fix}


class NotFound(UnifierrError):
    status_code = 404


class ServiceUnavailable(UnifierrError):
    """An external app (Radarr, qBittorrent, ...) could not be reached or answered with an error."""
    status_code = 502
