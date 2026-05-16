---
paths:
  - "FrameServer/**/*"
  - "FrameGUI/**/*"
  - "Utilities/Weather/**/*"
  - "Utilities/MQTT/**/*"
  - "Utilities/screen_scheduler.py"
  - "Utilities/brightness.py"
  - "app.py"
---

# Frame And Runtime Rules

- This code runs in a long-lived display/streaming process. Favor resilience over cleverness.
- Do not add blocking I/O, network access, or heavy allocations inside render loops, transition generators, or per-frame overlay work.
- Preserve both fullscreen GUI mode and headless mode unless the task explicitly changes one of them.
- Keep weather, MQTT, and hardware integrations fail-soft: catch/log exceptions and keep the app alive.
- Be careful with image/frame copies and conversions; extra copies can hurt performance on Raspberry Pi class hardware.
- When changing stream, overlay, or runtime behavior, prefer a headless smoke test with `env/bin/python app.py --headless`.
