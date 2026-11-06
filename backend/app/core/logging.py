import logging
import re

_SECRET_RE = re.compile(r"(?i)(api[_-]?key|apikey|password|token|X-Api-Key|X-Plex-Token)([=:\"'\s]+)([^&\s\"',]+)")


def redact(text: str) -> str:
    """Mask API keys / passwords / tokens in free text (logs shown in the UI)."""
    return _SECRET_RE.sub(lambda m: f"{m.group(1)}{m.group(2)}***", text)


class RedactingFilter(logging.Filter):
    """Masks API keys / passwords / tokens that sneak into log lines."""

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        redacted = redact(msg)
        if redacted != msg:
            record.msg, record.args = redacted, ()
        return True


def setup_logging(level: str) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    handler.addFilter(RedactingFilter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())
    # httpx logs full URLs (which may include tokens) at INFO.
    logging.getLogger("httpx").setLevel(logging.WARNING)
