"""One-time idempotent startup migrations for the DigitalPhotoFrame."""
from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_KNOWN_SOURCE_DIRS = {"local_images", "google_photos", "immich"}


def run_migrations(images_root: str | Path) -> None:
    """
    Idempotent startup migration:
    1. Move files/dirs in images_root/ that aren't known source dirs → images_root/local_images/
    2. Ensure images_root/local_images/ exists.
    """
    images_root = Path(images_root).resolve()
    local_images = images_root / "local_images"
    local_images.mkdir(parents=True, exist_ok=True)

    if not images_root.exists():
        logger.info("[Migration] images_root does not exist yet: %s", images_root)
        return

    for entry in list(images_root.iterdir()):
        if entry.name in _KNOWN_SOURCE_DIRS:
            continue
        # Move files and unknown dirs into local_images/
        dest = local_images / entry.name
        if not dest.exists():
            try:
                entry.rename(dest)
                logger.info("[Migration] Moved %s → %s", entry, dest)
            except Exception:
                logger.exception("[Migration] Failed to move %s → %s", entry, dest)
        else:
            logger.debug(
                "[Migration] Skipping %s — destination %s already exists", entry, dest
            )
