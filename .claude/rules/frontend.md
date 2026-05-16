---
paths:
  - "frontend/**/*"
  - "WebAPI/templates/**/*"
  - "WebAPI/static/**/*"
---

# Frontend Rules

- The browser UI is a Vite/React app in `frontend/`, but production serving happens through Flask from `frontend/dist`.
- After changing React UI code, run `cd frontend && npm run build` so Flask-served output stays current.
- Keep frontend routes and backend expectations aligned. The current app includes login, signup, reset password, stream, gallery, and settings flows.
- Prefer changes that preserve touch-friendly admin workflows and existing auth assumptions.
- Run `cd frontend && npm run lint` when feasible after frontend changes.
