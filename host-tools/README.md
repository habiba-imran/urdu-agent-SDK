# UVA host-tools (F-C7 idempotent calendar stub)

**Not self-serve.** This is a small standalone Express host so you can prove worker → tools POSTs with `Idempotency-Key` without depending on `self-serve-demo-UI`.

Replace the in-memory store with Finova’s real calendar when you have one. Keep the same route paths and idempotency behaviour.

## Routes (match `worker/tools.py`)

| Method | Path | Notes |
|---|---|---|
| POST | `/api/tools/lookup_business_info` | Stub FAQ answer |
| POST | `/api/tools/check_availability` | Fake open slots |
| POST | `/api/tools/book_slot` | **Idempotent** write |
| POST | `/api/tools/reschedule_appointment` | **Idempotent** write |
| POST | `/api/tools/cancel_appointment` | **Idempotent** write |
| GET | `/healthz` | Liveness |
| GET | `/api/tools/_debug/appointments` | List in-memory rows (auth required) |

Auth: header `x-tool-gateway-secret` must equal `TOOL_GATEWAY_SECRET`.

Writes also accept body `idempotency_key` (worker sends both header + body).

## Run locally

```bash
cd host-tools
cp .env.example .env
# edit TOOL_GATEWAY_SECRET if you want
npm install
npm test
npm run dev
```

Listens on `http://127.0.0.1:3010` by default.

## Point a test agent at it

On the agent row (portal / SQL):

- `tools_base_url` = `http://127.0.0.1:3010` (or your ngrok/public URL if the worker is remote)
- `tools_auth_secret` = same value as `TOOL_GATEWAY_SECRET`

Worker resolve uses `x-tool-gateway-secret` from that secret.

## Prove idempotency without a full voice call

```bash
SECRET=dev-tool-gateway-secret-change-me
curl -s -X POST http://127.0.0.1:3010/api/tools/book_slot \
  -H "Content-Type: application/json" \
  -H "x-tool-gateway-secret: $SECRET" \
  -H "Idempotency-Key: demo-1" \
  -d '{"tenant_id":"t1","customer_name":"Sara","customer_phone":"+923001112233","slot_start_time":"2026-09-20T11:00:00"}'

# Same key again → same appointment_id, still one row in _debug/appointments
curl -s -X POST http://127.0.0.1:3010/api/tools/book_slot \
  -H "Content-Type: application/json" \
  -H "x-tool-gateway-secret: $SECRET" \
  -H "Idempotency-Key: demo-1" \
  -d '{"tenant_id":"t1","customer_name":"Sara","customer_phone":"+923001112233","slot_start_time":"2026-09-20T11:00:00"}'
```

## What this does / does not do

| Does | Does not |
|---|---|
| Accept worker tool paths | Google Calendar / real CRM |
| Dedupe on `Idempotency-Key` | Replace Ehsan A.4 mint phone |
| In-memory appointments for local proof | Live on Render until you deploy it |
