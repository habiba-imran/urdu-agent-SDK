# tenant_portal_api — tenant dashboard + telephony API. Build from the REPO ROOT:
#   docker build -f docker/tenant-portal-api.Dockerfile -t uva-tenant-portal .
#
# Cross-package imports (must be in the image, not only tenant_portal_api/):
#   - control_plane.secrets / secrets_db / mint  (HMAC + machine auth)
#   - worker.providers.capabilities + worker.providers.tts.*_options  (picker validation)
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY tenant_portal_api/ tenant_portal_api/
COPY control_plane/ control_plane/
COPY worker/__init__.py worker/
COPY worker/providers/ worker/providers/
COPY scripts/ scripts/

# Wave 2: declares this process a hosted deployment, so missing signing secrets,
# an unset CORS allowlist, or a telephony mock-auth switch fail at startup
# instead of silently falling back to development defaults (F-C1/F-C3/F-M18).
ENV UVA_ENV=production

EXPOSE 8000
CMD ["uvicorn", "tenant_portal_api.app:app", "--host", "0.0.0.0", "--port", "8000"]
