import logging
import os
from logging.handlers import RotatingFileHandler


def configure_logging(
    log_file_path: str | None = None,
    level: int = logging.INFO,
) -> None:
    """Configure the root logger with a RotatingFileHandler and a StreamHandler.

    This should be called once from the application entry point (app.py /
    app_modes.py) before any other module is imported so that all subsequent
    ``logging.getLogger(__name__)`` calls inherit the same handlers and
    formatting.

    Args:
        log_file_path: Absolute or relative path for the rotating log file.
            Defaults to ``./PhotoFrame.log`` in the repo root when *None*.
        level: Logging level applied to the root logger and both handlers.
    """
    root = logging.getLogger()

    # Avoid duplicate handlers if called more than once (e.g. in tests).
    if root.handlers:
        return

    root.setLevel(level)

    fmt = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # --- File handler (rotating, max 5 MB, keep 3 backups) ---
    if log_file_path is None:
        log_file_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "PhotoFrame.log"
        )

    try:
        log_dir = os.path.dirname(os.path.abspath(log_file_path))
        os.makedirs(log_dir, exist_ok=True)
        file_handler = RotatingFileHandler(
            log_file_path,
            maxBytes=5 * 1024 * 1024,
            backupCount=3,
            encoding="utf-8",
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(fmt)
        root.addHandler(file_handler)
    except Exception as exc:
        # If the file can't be opened, fall back to console-only logging.
        print(f"[logging_setup] Could not open log file {log_file_path!r}: {exc}")

    # --- Console handler ---
    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_handler.setFormatter(logging.Formatter("%(levelname)s - %(message)s"))
    root.addHandler(console_handler)
