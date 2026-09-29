import { randomUUID } from 'node:crypto';
import express from 'express';
import { createStore } from './store.js';

function readIdempotencyKey(req) {
  const header = req.get('Idempotency-Key') || req.get('idempotency-key');
  const body = req.body?.idempotency_key || req.body?.idempotencyKey;
  const raw = (header || body || '').trim();
  return raw || null;
}

function requireToolAuth(secret) {
  return (req, res, next) => {
    if (!secret) {
      res.status(503).json({
        success: false,
        error: 'TOOL_GATEWAY_SECRET is not configured',
      });
      return;
    }
    const headerSecret =
      req.get('x-tool-gateway-secret') ||
      (req.get('authorization')?.startsWith('Bearer ')
        ? req.get('authorization').slice(7).trim()
        : undefined);
    if (!headerSecret || headerSecret !== secret) {
      res.status(401).json({ success: false, error: 'unauthorized' });
      return;
    }
    next();
  };
}

/**
 * @param {{ toolGatewaySecret: string, store?: ReturnType<typeof createStore> }} config
 */
export function createApp(config) {
  const store = config.store || createStore();
  const app = express();
  app.use(express.json({ limit: '64kb' }));

  app.get('/', (_req, res) => {
    res.type('text').send(
      'uva-host-tools OK\n' +
        'Try GET /healthz\n' +
        'Worker POSTs to /api/tools/* (not browser GET)\n',
    );
  });

  app.get('/healthz', (_req, res) => {
    res.json({ ok: true, service: 'uva-host-tools' });
  });

  const tools = express.Router();
  tools.use(requireToolAuth(config.toolGatewaySecret));

  tools.post('/lookup_business_info', (req, res) => {
    const query = String(req.body?.query || '').trim();
    res.json({
      success: true,
      answer: query
        ? `Demo knowledge base has no docs yet. You asked: ${query}`
        : 'Demo knowledge base has no docs yet.',
    });
  });

  tools.post('/check_availability', (req, res) => {
    const date = String(req.body?.date || '').trim() || new Date().toISOString().slice(0, 10);
    const slots = ['09:00', '11:00', '14:00', '16:00'].map((t) => `${date}T${t}:00`);
    res.json({
      success: true,
      available: true,
      date,
      slots,
      voiceSummary: `Open slots on ${date}: 9 AM, 11 AM, 2 PM, and 4 PM.`,
    });
  });

  tools.post('/book_slot', (req, res) => {
    handleWrite(req, res, store, () => {
      const tenantId = String(req.body?.tenant_id || req.body?.tenantId || '').trim();
      const customerName = String(
        req.body?.customer_name || req.body?.customerName || '',
      ).trim();
      const customerPhone = String(
        req.body?.customer_phone || req.body?.customerPhone || '',
      ).trim();
      const slotStartTime = String(
        req.body?.slot_start_time || req.body?.slotStartTime || '',
      ).trim();
      const serviceName = String(
        req.body?.service_name || req.body?.serviceName || '',
      ).trim();

      if (!customerName || !customerPhone || !slotStartTime) {
        return {
          status: 400,
          body: {
            success: false,
            error: 'customer_name, customer_phone, and slot_start_time are required',
          },
        };
      }

      const appt = store.saveAppointment({
        id: randomUUID(),
        tenant_id: tenantId,
        agent_id: String(req.body?.agent_id || req.body?.agentId || ''),
        customer_name: customerName,
        customer_phone: customerPhone,
        slot_start_time: slotStartTime,
        service_name: serviceName || null,
        status: 'confirmed',
        created_at: new Date().toISOString(),
      });

      return {
        status: 200,
        body: {
          success: true,
          appointment_id: appt.id,
          confirmation_code: appt.id.slice(0, 8).toUpperCase(),
          slot_start_time: appt.slot_start_time,
          customer_name: appt.customer_name,
          customer_phone: appt.customer_phone,
        },
      };
    });
  });

  tools.post('/reschedule_appointment', (req, res) => {
    handleWrite(req, res, store, () => {
      const tenantId = String(req.body?.tenant_id || req.body?.tenantId || '').trim();
      const customerPhone = String(
        req.body?.customer_phone || req.body?.customerPhone || '',
      ).trim();
      const newSlot = String(
        req.body?.new_slot_start_time || req.body?.newSlotStartTime || '',
      ).trim();

      if (!customerPhone || !newSlot) {
        return {
          status: 400,
          body: {
            success: false,
            error: 'customer_phone and new_slot_start_time are required',
          },
        };
      }

      const existing = store.findOpenByPhone(tenantId, customerPhone);
      if (!existing) {
        return {
          status: 404,
          body: { success: false, error: 'no confirmed appointment for this phone' },
        };
      }

      existing.slot_start_time = newSlot;
      existing.updated_at = new Date().toISOString();
      store.saveAppointment(existing);

      return {
        status: 200,
        body: {
          success: true,
          appointment_id: existing.id,
          slot_start_time: existing.slot_start_time,
          customer_phone: existing.customer_phone,
        },
      };
    });
  });

  tools.post('/cancel_appointment', (req, res) => {
    handleWrite(req, res, store, () => {
      const tenantId = String(req.body?.tenant_id || req.body?.tenantId || '').trim();
      const customerPhone = String(
        req.body?.customer_phone || req.body?.customerPhone || '',
      ).trim();

      if (!customerPhone) {
        return {
          status: 400,
          body: { success: false, error: 'customer_phone is required' },
        };
      }

      const existing = store.findOpenByPhone(tenantId, customerPhone);
      if (!existing) {
        return {
          status: 404,
          body: { success: false, error: 'no confirmed appointment for this phone' },
        };
      }

      existing.status = 'cancelled';
      existing.reason = String(req.body?.reason || '').trim() || null;
      existing.updated_at = new Date().toISOString();
      store.saveAppointment(existing);

      return {
        status: 200,
        body: {
          success: true,
          appointment_id: existing.id,
          status: 'cancelled',
          customer_phone: existing.customer_phone,
        },
      };
    });
  });

  /** Test/ops helper — list in-memory appointments (not used by worker). */
  tools.get('/_debug/appointments', (_req, res) => {
    res.json({ appointments: store.listAppointments() });
  });

  app.use('/api/tools', tools);
  app.locals.store = store;
  return app;
}

function handleWrite(req, res, store, run) {
  const tenantId = String(req.body?.tenant_id || req.body?.tenantId || '').trim();
  const idemKey = readIdempotencyKey(req);

  if (idemKey) {
    const gate = store.beginIdempotent(tenantId, idemKey);
    if (gate.hit && gate.response) {
      res.status(200).json(gate.response);
      return;
    }
    if (gate.hit && gate.inProgress) {
      res.status(409).json({
        success: false,
        error: 'idempotency_key already in progress',
      });
      return;
    }
  }

  let outcome;
  try {
    outcome = run();
  } catch (err) {
    if (idemKey) store.abortIdempotent(tenantId, idemKey);
    res.status(500).json({
      success: false,
      error: err instanceof Error ? err.message : String(err),
    });
    return;
  }

  if (idemKey && outcome.status >= 200 && outcome.status < 300 && outcome.body?.success) {
    store.completeIdempotent(tenantId, idemKey, outcome.body);
  } else if (idemKey) {
    store.abortIdempotent(tenantId, idemKey);
  }

  res.status(outcome.status).json(outcome.body);
}
