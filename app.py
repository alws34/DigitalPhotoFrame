#!/usr/bin/env python3
"""Digital Photo Frame — entry point."""

from __future__ import annotations

import argparse
import logging
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def _abs_path(p: str) -> str:
    return p if os.path.isabs(p) else os.path.abspath(os.path.join(BASE_DIR, p))


def main() -> None:
    p = argparse.ArgumentParser(description="Digital Photo Frame")
    p.add_argument(
        "--settings",
        default="photoframe_settings.json",
        help="Path to settings JSON file.",
    )
    p.add_argument(
        "--headless", action="store_true", help="Run without GUI (backend server only)."
    )
    p.add_argument(
        "--display",
        choices=["pygame", "qt"],
        help="Display backend: pygame (lightweight) or qt (PySide6).",
    )
    p.add_argument(
        "--width", type=int, default=None, help="Headless mode: override stream width."
    )
    p.add_argument(
        "--height",
        type=int,
        default=None,
        help="Headless mode: override stream height.",
    )
    args = p.parse_args()

    from Utilities import config_events
    from Utilities.config_store import apply_system_timezone, load_settings

    settings = load_settings(json_path=_abs_path(args.settings))
    apply_system_timezone(settings)
    config_events.on_settings_changed(apply_system_timezone)
    config_events.start_watcher()

    from logging_setup import configure_logging

    log_file = settings.get("system", {}).get("log_file_path") or "PhotoFrame.log"
    configure_logging(log_file_path=_abs_path(log_file), level=logging.INFO)

    from app_modes import _run_gui, _run_headless, _run_pygame

    if args.headless:
        _run_headless(settings, _abs_path(args.settings), args.width, args.height)
        return

    if args.display == "pygame":
        _run_pygame(settings, _abs_path(args.settings))
        return

    if args.display == "qt":
        _run_gui(settings, _abs_path(args.settings))
        return

    try:
        import pygame  # noqa: F401

        _run_pygame(settings, _abs_path(args.settings))
    except ImportError:
        _run_gui(settings, _abs_path(args.settings))


if __name__ == "__main__":
    main()
