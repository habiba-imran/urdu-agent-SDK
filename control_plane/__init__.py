"""Control plane — the token mint. The whole security model lives here (Phase 2).

A stolen client bundle is worthless because the client never holds a provider key or a long-lived
token; it can only ask this server, which authenticates the host platform by HMAC and mints a
LiveKit JWT scoped to one room for <=120s. See docs/22-PHASE-2-CONTROL-PLANE.md.
"""
