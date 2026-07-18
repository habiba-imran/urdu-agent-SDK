# admin/app.py — the super-admin portal backend. Build from the REPO ROOT:
#   docker build -f docker/admin.Dockerfile -t uva-admin .
#
# Minimal deps (docker/requirements-admin.txt), NOT the monolithic top-level requirements.txt —
# this service never imports livekit-agents/numpy/openai/python-socketio, all worker-only.
# Verified by grepping admin/*.py's real imports (2026-07-18). No livekit package needed at
# all here (control_plane needs livekit-api for token minting; admin never mints a token).
FROM python:3.12-slim

WORKDIR /app

COPY docker/requirements-admin.txt .
RUN pip install --no-cache-dir -r requirements-admin.txt

COPY admin/ admin/
COPY scripts/dbconn.py scripts/

# Real env vars this service reads at runtime — see docs/62-GUIDE-PROD-ENV-VARS.md for the
# full inventory. NOT baked in here; supplied by the deploy platform:
#   SUPABASE_DB_URL, ADMIN_JWT_SECRET, ADMIN_PORTAL_ORIGINS
# ADMIN_JWT_SECRET MUST be set explicitly in prod — admin/app.py's auto-generate-if-absent
# fallback (_ensure_admin_jwt_secret) writes to a local .env.local file, which is dev-only-safe
# and actively broken in a container: either the write fails (read-only filesystem, common on
# managed platforms) or it silently succeeds and evaporates on the next redeploy, minting a new
# secret and invalidating every existing admin session each time. Do not rely on it in prod.

EXPOSE 8001
CMD ["uvicorn", "admin.app:app", "--host", "0.0.0.0", "--port", "8001"]
