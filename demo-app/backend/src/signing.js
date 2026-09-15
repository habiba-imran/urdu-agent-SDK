import crypto from 'node:crypto';

export function createSessionSignature({ tenantId, timestamp, nonce, agentId, secret }) {
  return crypto
    .createHmac('sha256', secret)
    .update(`${tenantId}.${timestamp}.${nonce}.${agentId}`)
    .digest('hex');
}

export function createControlPlaneHeaders({ tenantId, agentId, secret, origin }) {
  const timestamp = String(Math.floor(Date.now() / 1000));
  const nonce = crypto.randomUUID();
  const signature = createSessionSignature({
    tenantId,
    timestamp,
    nonce,
    agentId,
    secret,
  });

  const headers = {
    'Content-Type': 'application/json',
    'X-Tenant-Id': tenantId,
    'X-Timestamp': timestamp,
    'X-Nonce': nonce,
    'X-Signature': signature,
  };

  if (origin) {
    headers.Origin = origin;
  }

  return headers;
}
