"""Shared media-type extension constants.

Import ``SUPPORTED_MEDIA_EXTENSIONS`` wherever the application needs to
enumerate displayable files.  Both :mod:`Utilities.observer` and
:mod:`FrameServer.PhotoFrameServer` consume this tuple so that a single
edit keeps them in sync.
"""

#: Tuple of lower-case file extensions (with leading dot) that the photo
#: frame can display or play.  All consumers should call
#: ``file.lower().endswith(SUPPORTED_MEDIA_EXTENSIONS)`` for case-insensitive
#: matching.
SUPPORTED_MEDIA_EXTENSIONS: tuple[str, ...] = (
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".bmp",
    ".webp",
    ".heic",
    ".heif",
    ".mov",
    ".mp4",
)
