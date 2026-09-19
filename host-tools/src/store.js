/**
 * In-memory appointment + idempotency store (demo / local proof only).
 * Replace with your real DB when Finova calendar ships.
 */

export function createStore() {
  /** @type {Map<string, object>} */
  const appointments = new Map();
  /** @type {Map<string, { status: string, response: object, createdAt: number }>} */
  const idempotency = new Map();

  function idemKey(tenantId, key) {
    return `${tenantId || '-'}::${key}`;
  }

  return {
    listAppointments() {
      return [...appointments.values()];
    },

    getAppointment(id) {
      return appointments.get(id) || null;
    },

    findOpenByPhone(tenantId, phone) {
      const digits = String(phone || '').replace(/\D/g, '');
      for (const appt of appointments.values()) {
        if (appt.tenant_id !== tenantId) continue;
        if (appt.status !== 'confirmed') continue;
        if (String(appt.customer_phone || '').replace(/\D/g, '') === digits) {
          return appt;
        }
      }
      return null;
    },

    saveAppointment(appt) {
      appointments.set(appt.id, appt);
      return appt;
    },

    /**
     * @returns {{ hit: true, response: object } | { hit: false } | { hit: true, inProgress: true }}
     */
    beginIdempotent(tenantId, key) {
      if (!key) return { hit: false };
      const full = idemKey(tenantId, key);
      const existing = idempotency.get(full);
      if (!existing) {
        idempotency.set(full, {
          status: 'in_progress',
          response: null,
          createdAt: Date.now(),
        });
        return { hit: false };
      }
      if (existing.status === 'completed' && existing.response) {
        return { hit: true, response: existing.response };
      }
      return { hit: true, inProgress: true };
    },

    completeIdempotent(tenantId, key, response) {
      if (!key) return;
      idempotency.set(idemKey(tenantId, key), {
        status: 'completed',
        response,
        createdAt: Date.now(),
      });
    },

    abortIdempotent(tenantId, key) {
      if (!key) return;
      const full = idemKey(tenantId, key);
      const existing = idempotency.get(full);
      if (existing?.status === 'in_progress') {
        idempotency.delete(full);
      }
    },

    reset() {
      appointments.clear();
      idempotency.clear();
    },
  };
}
