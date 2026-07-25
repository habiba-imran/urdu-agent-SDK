---
name: Release Checklist
about: Standard production release verification checklist for Hamza & Habiba
title: 'Release Checklist: v'
labels: release
assignees: ''
---

## 🚀 Release Verification Checklist

### Pre-Deployment Verification
- [ ] All feature PRs merged cleanly into `staging` branch
- [ ] CI pipeline (`.github/workflows/ci.yml`) passed 100% on `staging`
- [ ] Local/staging end-to-end voice test completed (`/v1/session` -> LiveKit -> Worker speech output)
- [ ] Database migrations reviewed and applied to staging Supabase instance

### Render Deployment Status
- [ ] `uva-control-plane` healthy on Render (`GET /healthz` returns `200 OK`)
- [ ] `uva-voice-worker` registered with `LIVEKIT_AGENT_NAME` matching control plane
- [ ] `uva-admin-portal` healthy on Render (`GET /healthz` returns `200 OK`)

### Security & Quotas
- [ ] `CP_ALLOWED_ORIGINS` configured (no wildcard `*` CORS in production)
- [ ] Secrets set directly in Render environment variables (never committed to git)
- [ ] Session closeout verified (`quota_state.concurrent_now` decrements after call ends)
- [ ] Admin portal restricted to `ADMIN_PORTAL_ORIGINS`

### SDK & Client Artifacts
- [ ] `@awaazlabs-uva/voice` package built and version bumped
- [ ] `examples/web-client/` verified against deployed endpoints
- [ ] Documentation (`sdk/README.md`, `docs/`) up to date

### Post-Deployment Health Check
- [ ] Run `python scripts/reconcile_sessions.py --dry-run` to confirm zero quota drift
- [ ] Perform live test call against production URL
- [ ] Both Hamza (Runtime/Security) and Habiba (SDK/Dashboard/Docs) sign off on release
