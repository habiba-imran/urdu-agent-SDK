# Evidence — M11 portal route matrix vs interim decision

**Decision:** Create agents forbidden. Edits / reveal / telephony / Test Studio **undecided** (record only).

| Route | Auth | Mutates? | Today | Vs interim |
|---|---|---|---|---|
| `POST /portal/agents` | owner JWT | create agent | **403** unless `PORTAL_ALLOW_AGENT_CREATE=1` | PASS |
| `PATCH /portal/agents/{id}` | owner JWT | update agent | allowed | undecided — allowed |
| `DELETE /portal/agents/{id}` | owner JWT | archive | allowed | undecided — allowed |
| `PUT /portal/credentials/allowed-origins` | owner | origins | allowed | undecided |
| `GET` credentials + secret reveal | owner | read secret | reveal **default on** | undecided |
| `POST /portal/credentials/rotate-secret` | owner | rotate | **default off** | undecided |
| `POST /portal/test-studio/session` | portal | mint via CP | allowed | undecided |
| `POST /portal/telephony/**` | portal | telephony ops | allowed | undecided |
| `POST /machine/agents` | HMAC | create | allowed + agent cap | PASS (by design) |

## RLS (agents)

`0002_rls.sql`: policy `tenant_isolation_agents` is **SELECT only**; grants to `authenticated` are **SELECT** only — no INSERT/UPDATE/DELETE on `agents`. Browser PostgREST cannot create agents via RLS. **PASS** M11-C2 for agents.

## Note

`0015_telephony_rls_grants.sql` grants authenticated INSERT/UPDATE on many telephony tables. Dashboard appears to use portal API for telephony (not raw `.from()` writes) — Ehsan should keep it that way; Habiba does not change `dashboard/`.
