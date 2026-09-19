import assert from 'node:assert/strict';
import { test } from 'node:test';
import { createApp } from '../src/createApp.js';
import { createStore } from '../src/store.js';

const SECRET = 'test-secret';

function startServer(store) {
  const app = createApp({ toolGatewaySecret: SECRET, store });
  return new Promise((resolve) => {
    const server = app.listen(0, '127.0.0.1', () => {
      const { port } = server.address();
      resolve({
        base: `http://127.0.0.1:${port}`,
        close: () =>
          new Promise((r, j) => server.close((err) => (err ? j(err) : r()))),
      });
    });
  });
}

async function post(base, path, { body, idempotencyKey, secret = SECRET } = {}) {
  const headers = {
    'Content-Type': 'application/json',
    'x-tool-gateway-secret': secret,
  };
  if (idempotencyKey) headers['Idempotency-Key'] = idempotencyKey;
  const res = await fetch(`${base}${path}`, {
    method: 'POST',
    headers,
    body: JSON.stringify(body ?? {}),
  });
  const json = await res.json();
  return { status: res.status, json };
}

test('rejects missing tool gateway secret', async () => {
  const store = createStore();
  const { base, close } = await startServer(store);
  try {
    const res = await fetch(`${base}/api/tools/book_slot`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        tenant_id: 't1',
        customer_name: 'A',
        customer_phone: '+923001234567',
        slot_start_time: '2026-09-20T09:00:00',
      }),
    });
    assert.equal(res.status, 401);
  } finally {
    await close();
  }
});

test('book then same Idempotency-Key returns same appointment (no double book)', async () => {
  const store = createStore();
  const { base, close } = await startServer(store);
  try {
    const body = {
      tenant_id: 't1',
      agent_id: 'a1',
      customer_name: 'Sara',
      customer_phone: '+923001112233',
      slot_start_time: '2026-09-20T11:00:00',
      service_name: 'Consult',
    };
    const key = 'idem-book-1';

    const first = await post(base, '/api/tools/book_slot', {
      body,
      idempotencyKey: key,
    });
    assert.equal(first.status, 200);
    assert.equal(first.json.success, true);
    assert.ok(first.json.appointment_id);

    const second = await post(base, '/api/tools/book_slot', {
      body,
      idempotencyKey: key,
    });
    assert.equal(second.status, 200);
    assert.deepEqual(second.json, first.json);

    assert.equal(store.listAppointments().length, 1);
  } finally {
    await close();
  }
});

test('different idempotency keys create two appointments', async () => {
  const store = createStore();
  const { base, close } = await startServer(store);
  try {
    const baseBody = {
      tenant_id: 't1',
      customer_name: 'Ali',
      customer_phone: '+923009998887',
      slot_start_time: '2026-09-21T09:00:00',
    };
    const a = await post(base, '/api/tools/book_slot', {
      body: baseBody,
      idempotencyKey: 'k-a',
    });
    const b = await post(base, '/api/tools/book_slot', {
      body: { ...baseBody, slot_start_time: '2026-09-21T14:00:00' },
      idempotencyKey: 'k-b',
    });
    assert.equal(a.json.success, true);
    assert.equal(b.json.success, true);
    assert.notEqual(a.json.appointment_id, b.json.appointment_id);
    assert.equal(store.listAppointments().length, 2);
  } finally {
    await close();
  }
});

test('cancel is idempotent', async () => {
  const store = createStore();
  const { base, close } = await startServer(store);
  try {
    await post(base, '/api/tools/book_slot', {
      body: {
        tenant_id: 't1',
        customer_name: 'Noor',
        customer_phone: '03001234567',
        slot_start_time: '2026-09-22T10:00:00',
      },
      idempotencyKey: 'book-n',
    });

    const cancelBody = {
      tenant_id: 't1',
      customer_phone: '03001234567',
      reason: 'changed plans',
    };
    const c1 = await post(base, '/api/tools/cancel_appointment', {
      body: cancelBody,
      idempotencyKey: 'cancel-n',
    });
    const c2 = await post(base, '/api/tools/cancel_appointment', {
      body: cancelBody,
      idempotencyKey: 'cancel-n',
    });
    assert.equal(c1.json.success, true);
    assert.deepEqual(c2.json, c1.json);
    assert.equal(store.listAppointments()[0].status, 'cancelled');
  } finally {
    await close();
  }
});

test('check_availability works without idempotency', async () => {
  const store = createStore();
  const { base, close } = await startServer(store);
  try {
    const r = await post(base, '/api/tools/check_availability', {
      body: { tenant_id: 't1', date: '2026-09-25', time_of_day: 'morning' },
    });
    assert.equal(r.status, 200);
    assert.equal(r.json.success, true);
    assert.ok(Array.isArray(r.json.slots) && r.json.slots.length > 0);
  } finally {
    await close();
  }
});
