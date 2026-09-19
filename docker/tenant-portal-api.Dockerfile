# tenant_portal_api — tenant dashboard + telephony API. Build from the REPO ROOT:
#   docker build -f docker/tenant-portal-api.Dockerfile -t uva-tenant-portal .
#
# Imports control_plane.secrets / secrets_db / mint (HMAC + machine auth). Those modules
# must be in the image — not only tenant_portal_api/.
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY tenant_portal_api/ tenant_portal_api/
COPY control_plane/ control_plane/
COPY scripts/ scripts/

EXPOSE 8000
CMD ["uvicorn", "tenant_portal_api.app:app", "--host", "0.0.0.0", "--port", "8000"]
