"""Shared image utility helpers."""

import hashlib


def compute_image_hash(image_path: str) -> str:
    """Return the SHA-256 hex digest of the file at *image_path*.

    Reads in 4 KiB chunks to keep memory usage constant regardless of
    file size.

    Args:
        image_path: Absolute or relative path to the image file.

    Returns:
        Lowercase hex string of the SHA-256 digest.
    """
    hash_obj = hashlib.sha256()
    with open(image_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_obj.update(chunk)
    return hash_obj.hexdigest()
