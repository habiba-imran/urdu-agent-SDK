# Client Handoff Guide

> **Superseded (P2-C1).** Historical host-backend / web-client example trees were
> deleted. This document is a redirect only.

## Canonical sources

| Audience | Source |
|---|---|
| Client engineers using the console | Dashboard `/docs` (Quickstart, Backend setup, Credentials, Going live) |
| Repo-local starter | `client-deliverables-final/` (+ `host-backend-starter/`) |
| npm packages | `@awaazlabs-uva/voice`, `@awaazlabs-uva/agents` |

## What the client receives from AwaazLabs-UVA

- `publishableKey` (browser-safe)
- `tenantId`
- raw tenant HMAC secret (**backend only** — never in browser code)
- provisioned `agentId`(s)
- session upstream URL for the host backend

## Do not use

- Removed example trees (former examples/ and demo-app paths)
- Dashboard Test Studio `/dev-mint` as a production integration pattern

Start at `client-deliverables-final/README.md` or the in-dashboard docs.
