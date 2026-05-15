"""Immich self-hosted photo library source."""
from __future__ import annotations

import logging
from pathlib import Path

import requests

from .base import Album, ImageSource, SyncResult

SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".mp4", ".mov"}


class ImmichSource(ImageSource):
    source_type = "immich"

    def __init__(self) -> None:
        self._base_url: str = ""
        self._api_key: str = ""

    def authenticate(self, credentials: dict) -> bool:
        self._base_url = credentials.get("base_url", "").rstrip("/")
        self._api_key = credentials.get("api_key", "")
        if not self._base_url or not self._api_key:
            return False
        # Validate API key using album.read — avoids requiring user.read permission
        try:
            resp = requests.get(
                f"{self._base_url}/api/albums",
                headers=self._headers(),
                params={"take": 1},
                timeout=10,
            )
            return resp.status_code == 200
        except Exception as e:
            logging.warning("[Immich] Auth validation failed: %s", e)
            return False

    @property
    def is_authenticated(self) -> bool:
        return bool(self._base_url and self._api_key)

    def get_credentials(self) -> dict:
        return {"base_url": self._base_url, "api_key": self._api_key}

    def _headers(self) -> dict:
        return {"x-api-key": self._api_key, "Accept": "application/json"}

    def list_albums(self) -> list[Album]:
        resp = requests.get(
            f"{self._base_url}/api/albums",
            headers=self._headers(),
            timeout=15,
        )
        resp.raise_for_status()
        albums: list[Album] = []
        for a in resp.json():
            albums.append(
                Album(
                    remote_id=a["id"],
                    name=a.get("albumName", a["id"]),
                    cover_url=None,
                    media_count=a.get("assetCount", 0),
                )
            )
        return albums

    # ------------------------------------------------------------------
    # Asset helpers for streaming cache
    # ------------------------------------------------------------------

    def list_album_assets(self, remote_id: str) -> list[tuple[str, str]]:
        """Return ordered list of (asset_id, ext) for all assets in an album."""
        resp = requests.get(
            f"{self._base_url}/api/albums/{remote_id}",
            headers=self._headers(),
            params={"withAssets": "true"},
            timeout=60,
        )
        resp.raise_for_status()
        assets = []
        for item in resp.json().get("assets", []):
            ext = Path(item.get("originalPath", "")).suffix.lower() or ".jpg"
            if ext in SUPPORTED_EXTENSIONS:
                assets.append((item["id"], ext))
        return assets

    def download_asset(self, asset_id: str, dest: Path) -> None:
        """Download a single asset to dest (caller handles atomic rename)."""
        url = f"{self._base_url}/api/assets/{asset_id}/original"
        headers = {**self._headers(), "Accept": "application/octet-stream"}
        with requests.get(url, headers=headers, stream=True, timeout=120) as r:
            r.raise_for_status()
            dest.parent.mkdir(parents=True, exist_ok=True)
            with open(dest, "wb") as f:
                for chunk in r.iter_content(chunk_size=65536):
                    f.write(chunk)

    def sync_album(
        self, remote_id: str, local_path: Path, existing_files: set[str]
    ) -> SyncResult:
        # Immich albums are streamed via ImmichStreamingCache — no bulk download.
        local_path.mkdir(parents=True, exist_ok=True)
        return SyncResult()
