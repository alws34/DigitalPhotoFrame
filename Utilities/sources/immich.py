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
        # Validate by calling server info
        try:
            resp = requests.get(
                f"{self._base_url}/api/server-info",
                headers=self._headers(),
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

    def sync_album(
        self, remote_id: str, local_path: Path, existing_files: set[str]
    ) -> SyncResult:
        local_path.mkdir(parents=True, exist_ok=True)
        result = SyncResult()

        resp = requests.get(
            f"{self._base_url}/api/albums/{remote_id}",
            headers=self._headers(),
            params={"withAssets": "true"},
            timeout=30,
        )
        resp.raise_for_status()
        album_data = resp.json()
        assets = album_data.get("assets", [])

        remote_ids: set[str] = set()
        for asset in assets:
            asset_id = asset["id"]
            original_path = asset.get("originalPath", "")
            ext = Path(original_path).suffix.lower() or ".jpg"
            if ext not in SUPPORTED_EXTENSIONS:
                continue
            filename = f"{asset_id}{ext}"
            remote_ids.add(filename)

            if filename not in existing_files:
                try:
                    _download_asset(
                        f"{self._base_url}/api/assets/{asset_id}/original",
                        local_path / filename,
                        self._headers(),
                    )
                    result.added += 1
                    existing_files.add(filename)
                except Exception as e:
                    result.errors.append(f"Failed to download {filename}: {e}")
                    logging.warning("[Immich] %s", result.errors[-1])

        for fname in list(existing_files):
            if fname not in remote_ids:
                try:
                    (local_path / fname).unlink(missing_ok=True)
                    result.removed += 1
                    existing_files.discard(fname)
                except Exception as e:
                    result.errors.append(f"Failed to remove {fname}: {e}")

        return result


def _download_asset(url: str, dest: Path, headers: dict) -> None:
    dl_headers = {**headers, "Accept": "application/octet-stream"}
    with requests.get(url, headers=dl_headers, stream=True, timeout=120) as r:
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_content(chunk_size=65536):
                f.write(chunk)
