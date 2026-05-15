# Albums & Multi-Source Provider — Design Spec

**Date:** 2026-05-15
**Branch:** dockerization
**Status:** Approved

---

## Overview

Add a multi-source photo/video provider system to DigitalPhotoFrame. Sources (Google Photos, Immich, local folders) sync media to local disk. The frame server plays from local files, unchanged. A new `AlbumManager` coordinates sources, sync, and active album selection. MQTT is expanded to expose all settings as HA entities.

---

## 1. Folder Structure

```
Images/
  local_images/         ← today's flat Images/ contents move here
    Unsorted/           ← files not in a named subfolder
    Vacation 2025/      ← user-created subfolders = local albums
  google_photos/
    Family 2024/        ← synced from Google Photos
    Dogs/
  immich/
    Favorites/          ← synced from Immich
```

Each leaf folder = one album. Album = folder. Frame server always reads local files.

---

## 2. Architecture

```
Utilities/
  sources/
    __init__.py
    base.py             ← ImageSource ABC + SyncResult + Album dataclasses
    local.py            ← LocalFolderSource
    google_photos.py    ← GooglePhotosSource (OAuth2 + Photos API)
    immich.py           ← ImmichSource (base URL + API key)
  AlbumManager.py       ← registry, sync scheduler, active album state

WebAPI/routes/
  albums.py             ← /api/albums/*
  sources.py            ← /api/sources/*
```

**Data flow:**
1. Admin UI configures sources
2. `AlbumManager` background thread syncs → downloads to source subfolders
3. Frame server calls `AlbumManager.get_active_image_dir()` → plays that local path
4. MQTT `select` entity changes active album → same call path via `config_events`

**Video support:** preserved. Sync downloads both images and videos (`.jpg .jpeg .png .gif .mp4 .mov`). Frame server video handling unchanged.

---

## 3. ImageSource ABC (`Utilities/sources/base.py`)

```python
@dataclass
class Album:
    remote_id: str
    name: str
    cover_url: str | None
    media_count: int

@dataclass
class SyncResult:
    added: int
    removed: int
    errors: list[str]

class ImageSource(ABC):
    source_type: str  # "google_photos" | "immich" | "local"

    @abstractmethod
    def authenticate(self, credentials: dict) -> bool: ...

    @abstractmethod
    def list_albums(self) -> list[Album]: ...

    @abstractmethod
    def sync_album(
        self,
        remote_id: str,
        local_path: Path,
        existing_files: set[str],
    ) -> SyncResult: ...
```

`LocalFolderSource.sync_album` is a no-op (returns empty `SyncResult`) — local files are already on disk, just rescans.

---

## 4. AlbumManager (`Utilities/AlbumManager.py`)

**Responsibilities:**
- Hold registry of configured `ImageSource` instances
- Background sync thread: runs on startup (if `albums.sync_on_startup`) then every `albums.sync_interval_hours`
- `get_active_image_dir() -> Path` — returns playback path for frame server
- `set_active_album(album_id: str)` — `"all"` returns `Images/` root (existing behavior); specific id returns album's `local_path`
- Fires `config_events` hook on active album change so frame server and MQTT react
- Exposes `get_sync_status() -> dict` for admin UI polling

**"All Photos" mode:** returns `Images/` root → frame server `os.walk` pools everything, identical to today.

**Manual sync:** `POST /api/sources/<id>/sync` → queues immediate sync run for that source.

---

## 5. DB Schema

Two new tables in existing SQLite DB:

```sql
CREATE TABLE sources (
    id               TEXT PRIMARY KEY,
    source_type      TEXT NOT NULL,      -- "google_photos" | "immich" | "local"
    name             TEXT NOT NULL,
    config_json      TEXT,               -- non-sensitive: base_url, client_id, etc.
    credentials_enc  TEXT,               -- Fernet-encrypted JSON: tokens, api_key
    enabled          INTEGER DEFAULT 1,
    last_synced_at   REAL,
    created_at       REAL
);

CREATE TABLE albums (
    id             TEXT PRIMARY KEY,     -- "{source_id}:{remote_id}"
    source_id      TEXT NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
    remote_id      TEXT NOT NULL,        -- remote API id or folder name
    name           TEXT NOT NULL,
    local_path     TEXT NOT NULL,        -- relative: Images/google_photos/Family 2024/
    cover_image    TEXT,
    media_count    INTEGER DEFAULT 0,
    subscribed     INTEGER DEFAULT 1,
    last_synced_at REAL,
    created_at     REAL
);
```

Settings (`app_settings` DB table) gains new section:

```json
"albums": {
  "active_album_id": "all",
  "sync_interval_hours": 6,
  "sync_on_startup": true,
  "sync_delete_removed": true
}
```

---

## 6. Encryption

- Library: `cryptography` (Fernet symmetric)
- Key file: `.pf_secret_key` in repo root — auto-generated on first startup if missing
- `.gitignore` must exclude `.pf_secret_key`
- Only `sources.credentials_enc` is encrypted; `config_json` is plaintext
- If key file is lost, re-auth required (acceptable)
- `AlbumManager` owns encrypt/decrypt helpers; no other module touches raw credentials

---

## 7. Settings: JSON → DB Only

`config_store.py` already uses DB as primary. Changes:
- On startup: if `photoframe_settings.json` exists → migrate to DB (already implemented) → rename to `photoframe_settings.json.migrated`
- Remove JSON fallback path after migration runs once
- `photoframe_settings.example.json` kept as documentation only, never read at runtime
- `save_settings()` / `load_settings()` become pure-DB

---

## 8. Sync System

**Per-album sync logic:**

| Source | Change detection | Download method |
|--------|-----------------|-----------------|
| `GooglePhotosSource` | `mediaItem.id` not in local filenames | `baseUrl` + `=d` param (full res) |
| `ImmichSource` | asset `id` not in local filenames | `GET /api/assets/{id}/original` |
| `LocalFolderSource` | N/A — no-op | N/A |

**File naming:** `{remote_media_id}.{ext}` — stable across renames on remote.

**Deletion:** if remote item removed from album → delete local file on next sync (when `sync_delete_removed: true`).

**Error handling:** sync errors logged + stored; never crash frame loop.

---

## 9. API Routes

### Sources (`/api/sources`)

```
GET    /api/sources                       list sources + auth status
POST   /api/sources                       add source {type, name, config}
PUT    /api/sources/<id>                  update config/name
DELETE /api/sources/<id>                  remove + delete local files
POST   /api/sources/<id>/sync            trigger immediate sync
GET    /api/sources/<id>/remote-albums    list albums available on remote
POST   /api/sources/<id>/auth/start      begin OAuth → returns redirect URL
GET    /api/sources/<id>/auth/callback   OAuth callback (Google redirects here)
```

### Albums (`/api/albums`)

```
GET    /api/albums                        list subscribed albums + sync status
POST   /api/albums                        subscribe {source_id, remote_id, name}
DELETE /api/albums/<id>                   unsubscribe + delete local files
GET    /api/albums/active                 get active album id + metadata
PUT    /api/albums/active                 set active {"album_id": "all" | "<id>"}
```

**Google OAuth:** callback at `/api/sources/google/auth/callback`. Exchanges code for tokens, encrypts, stores in DB.

**Immich auth:** base URL + API key in `POST /api/sources` body. Validated immediately via `GET /api/server-info`.

---

## 10. MQTT Expansion

**Strategy:** auto-generate HA entities from `SETTINGS_SCHEMA` (already in `config_store.py`) instead of hand-coding each entity.

**Type → HA entity mapping:**

| Schema type | HA entity |
|-------------|-----------|
| `bool` | `switch` |
| `int` / `float` | `number` (min/max/step from schema) |
| `enum` / `color` | `select` (choices from schema) |
| `str`, `password`, `numeric_string` | **skip** |

**Topic structure:**
```
state:   photoframe/{device_id}/settings/{dotted.path}
command: photoframe/{device_id}/cmd/settings/{dotted.path}
```

**Skip list (not exposed via MQTT):**
- `mqtt.*` (circular)
- `backend_configs.supersecretkey`, `backend_configs.host`, `backend_configs.server_port`
- `system.*`
- `autoupdate.repo_path`, `autoupdate.remote`, `autoupdate.branch`

**Album select entity** (dynamic, outside schema):
- Options: `["All Photos"] + [album.name for subscribed albums]`
- Rebuilds discovery payload when `AlbumManager` fires albums-changed event
- Command maps to `AlbumManager.set_active_album()`

**On command received:** parse dotted path → validate via `get_field_schema()` → load settings → update nested key → `save_settings()` → publish updated state → existing `config_events` hot-reload chain fires.

**`mqtt_bridge.py` refactor:** replace hand-coded entity blocks with schema-driven generator loop. Existing brightness/screen-power/service/restart entities migrate to same pattern.

---

## 11. Frontend

New **Albums** page (alongside Gallery, Stream, Settings):

```
Albums
├── Active Album selector    dropdown: "All Photos" | subscribed album names
├── [Sync All] button
│
├── Per source card
│   ├── Name, type icon, auth status
│   ├── [Sync Now]  [Re-auth]  [Remove Source]
│   └── Subscribed album rows: name · count · last synced · spinner if syncing
│       └── [Unsubscribe] per row
│
└── Browse & Subscribe panel
    └── Remote album list with [Subscribe] per album (fetched from source)
```

**Add Source flow:**
- Google Photos → [Connect] → OAuth URL opens in new tab → tab closes on callback → UI polls until auth confirmed
- Immich → modal: base URL + API key → validate on submit → save
- Local → no config needed, auto-discovers `Images/local_images/` subfolders

**Sync status polling:** `GET /api/albums` returns `sync_in_progress` + `last_synced_at` per album. Frontend polls every 5s while any sync in progress (same pattern as stream snapshot).

**Settings page:** `albums.*` settings (sync interval, sync on startup, delete removed) added as new "Albums" tab in existing settings form — schema-driven, no custom components needed.

---

## 12. app.py Wiring

```python
# Startup sequence (simplified)
encryption_key = load_or_create_key(".pf_secret_key")
album_manager = AlbumManager(db_path, images_root="Images/", key=encryption_key)
album_manager.start()  # begins background sync thread + startup sync

frame_server = PhotoFrameServer(...)
frame_server.set_image_dir_resolver(album_manager.get_active_image_dir)

mqtt_bridge = MqttBridge(view, settings, album_manager=album_manager)
```

Frame server change: `get_active_image_dir` replaces direct `IMAGE_DIR` setting read at the one call site where the shuffled list is built.

---

## 13. One-time Migration (startup, idempotent)

1. **Images dir:** move any files/folders in `Images/` that aren't known source dirs (`local_images/`, `google_photos/`, `immich/`) → `Images/local_images/`. Log clearly.
2. **Settings JSON:** if `photoframe_settings.json` exists → migrate to DB → rename to `photoframe_settings.json.migrated`.
3. **`.gitignore`:** ensure `.pf_secret_key` is excluded.

---

## Out of Scope (future)

- iCloud Photos (no official API; `pyicloud` too fragile)
- Per-album playback setting overrides
- Scheduled album rotation (time-of-day, day-of-week)
- Weighted album shuffle
