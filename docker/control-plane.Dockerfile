# control_plane/app.py — the token-mint service. Build from the REPO ROOT:
#   docker build -f docker/control-plane.Dockerfile -t uva-control-plane .
#
# Minimal deps (docker/requirements-control-plane.txt), NOT the monolithic top-level
# requirements.txt — this service never imports livekit-agents/numpy/openai/python-socketio,
# all worker-only. Verified by grepping control_plane/*.py's real imports (2026-07-18).
#
# control_plane/app.py imports `admin.audit.record_mint_rejection` (a real cross-module
# dependency — the two "separate services" share this one function) — so `admin/__init__.py`
# and `admin/audit.py` ARE copied into this image, deliberately, not the rest of admin/
# (app.py/auth.py/queries.py/security.py, which would pull in PyJWT this service never needs).
FROM python:3.12-slim

WORKDIR /app

COPY docker/requirements-control-plane.txt .
RUN pip install --no-cache-dir -r requirements-control-plane.txt

COPY control_plane/ control_plane/
COPY admin/__init__.py admin/audit.py admin/
COPY scripts/dbconn.py scripts/

# Real env vars this service reads at runtime — see docs/62-GUIDE-PROD-ENV-VARS.md for the
# full inventory with defaults/required-ness. NOT baked in here; supplied by the deploy platform:
#   SUPABASE_DB_URL, LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET, CP_TENANT_SECRETS

EXPOSE 8000
CMD ["uvicorn", "control_plane.app:app", "--host", "0.0.0.0", "--port", "8000"]
