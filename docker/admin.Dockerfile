# admin/app.py — the super-admin portal backend. Build from the REPO ROOT:
#   docker build -f docker/admin.Dockerfile -t uva-admin .
#
# Minimal deps (docker/requirements-admin.txt), NOT the monolithic top-level requirements.txt —
# this service never imports livekit-agents/numpy/openai/python-socketio, all worker-only.
# Verified by grepping admin/*.py's real imports (2026-07-18). No livekit package needed at
# all here (control_plane needs livekit-api for token minting; admin never mints a token).
FROM python:3.12.14-slim

WORKDIR /app

COPY docker/requirements-admin.txt .
RUN pip install --no-cache-dir -r requirements-admin.txt

COPY admin/ admin/
# Shared Wave 2 helpers this service imports (hosted detection, login throttle, security
# headers). Only these files - not the whole control_plane package, which would pull in
# the mint and its livekit dependency this image deliberately does not install.
COPY control_plane/__init__.py control_plane/runtime_env.py control_plane/login_guard.py control_plane/security_headers.py control_plane/
COPY scripts/dbconn.py scripts/

# Real env vars this service reads at runtime — see docs/62-GUIDE-PROD-ENV-VARS.md for the
# full inventory. NOT baked in here; supplied by the deploy platform:
#   SUPABASE_DB_URL, ADMIN_JWT_SECRET, ADMIN_PORTAL_ORIGINS
# ADMIN_JWT_SECRET MUST be set explicitly in prod — admin/app.py's auto-generate-if-absent
# fallback (_ensure_admin_jwt_secret) writes to a local .env.local file, which is dev-only-safe
# and actively broken in a container: either the write fails (read-only filesystem, common on
# managed platforms) or it silently succeeds and evaporates on the next redeploy, minting a new
# secret and invalidating every existing admin session each time. Do not rely on it in prod.

# Wave 2: declares this process a hosted deployment, so missing signing secrets,
# an unset CORS allowlist, or a telephony mock-auth switch fail at startup
# instead of silently falling back to development defaults (F-C1/F-C3/F-M18).
ENV UVA_ENV=production

EXPOSE 8001
# F-M9: images ran as root. A dedicated unprivileged user owns the app directory.
RUN useradd --system --create-home --uid 10001 uva && chown -R uva:uva /app
USER uva

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \n  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8001/healthz', timeout=3).status==200 else 1)"

CMD ["uvicorn", "admin.app:app", "--host", "0.0.0.0", "--port", "8001"]
