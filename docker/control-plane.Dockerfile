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
FROM python:3.12.14-slim

WORKDIR /app

COPY docker/requirements-control-plane.txt .
RUN pip install --no-cache-dir -r requirements-control-plane.txt

COPY control_plane/ control_plane/
COPY admin/__init__.py admin/audit.py admin/
COPY scripts/dbconn.py scripts/

# Real env vars this service reads at runtime — see docs/62-GUIDE-PROD-ENV-VARS.md for the
# full inventory with defaults/required-ness. NOT baked in here; supplied by the deploy platform:
#   SUPABASE_DB_URL, LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET, CP_TENANT_SECRETS

# Wave 2: declares this process a hosted deployment, so missing signing secrets,
# an unset CORS allowlist, or a telephony mock-auth switch fail at startup
# instead of silently falling back to development defaults (F-C1/F-C3/F-M18).
ENV UVA_ENV=production

EXPOSE 8000

# F-M9: images ran as root. A dedicated unprivileged user owns the app directory.
RUN useradd --system --create-home --uid 10001 uva && chown -R uva:uva /app
USER uva

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=3).status==200 else 1)"

CMD ["uvicorn", "control_plane.app:app", "--host", "0.0.0.0", "--port", "8000"]
