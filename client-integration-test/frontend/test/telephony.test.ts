import { afterEach, beforeEach, expect, test, vi } from 'vitest';
import { mountTelephonyPanel } from '../src/telephonyPanel';

const $ = <T extends HTMLElement = HTMLElement>(selector: string) => document.querySelector<T>(selector)!;
let number: { id: string; e164_number: string; assigned_agent_id: string | null; routing_status: string };
let ready = false;
let failAssignment: 'provider' | 'timeout' | null = null;
let request: ReturnType<typeof vi.fn>;

beforeEach(async () => {
  number = { id: 'number-1', e164_number: '+15551234567', assigned_agent_id: null, routing_status: 'not_configured' };
  ready = false;
  failAssignment = null;
  request = vi.fn(async (input: string) => {
    const path = new URL(input).pathname;
    if (path.endsWith('/status')) return Response.json({ connection: { platform_status: 'active' }, readiness: { is_ready: ready, reasons: ready ? [] : ['Number routing is incomplete.'] } });
    if (path.endsWith('/numbers')) return Response.json({ managed: [number], owned: [{ e164_number: number.e164_number }] });
    if (path.endsWith('/assign')) {
      number.assigned_agent_id = 'agent-1';
      if (failAssignment === 'timeout') throw new DOMException('signal timed out', 'TimeoutError');
      if (failAssignment === 'provider') return Response.json({ error: 'livekit_sip_dispatch_rule_failed', message: 'Routing failed.', assignmentSaved: true, routingStatus: 'not_configured' }, { status: 502 });
      number.routing_status = 'ready';
      ready = true;
      return Response.json({ assigned: number, routing: { routing_status: 'ready' } });
    }
    return Response.json({});
  });
  vi.stubGlobal('fetch', request);
  document.body.innerHTML = '<div id="telephony-root"></div>';
  mountTelephonyPanel({ backendOrigin: 'http://localhost:3100', getAgentId: () => 'agent-1' });
  await vi.waitFor(() => expect($<HTMLButtonElement>('#tel-refresh-btn').disabled).toBe(false));
  await vi.waitFor(() => expect(document.querySelector('[data-id="number-1"]')).not.toBeNull());
});

afterEach(() => { vi.unstubAllGlobals(); });

function selectNumber() {
  $('[data-id="number-1"]').click();
  $<HTMLInputElement>('#tel-to-number').value = '+15550001111';
  $('#tel-to-number').dispatchEvent(new Event('input', { bubbles: true }));
}

test('unrouted numbers block calls and already managed numbers cannot be imported again', () => {
  selectNumber();
  expect($<HTMLButtonElement>('#tel-outbound-btn').disabled).toBe(true);
  expect($('#tel-call-hint').textContent).toContain('ready routing');
  expect($<HTMLButtonElement>('[data-import]').disabled).toBe(true);
  expect($('[data-import]').textContent).toContain('Already managed');
});

test('routing failure refreshes the saved assignment and keeps outbound disabled', async () => {
  selectNumber();
  failAssignment = 'provider';
  $('#tel-assign-btn').click();
  await vi.waitFor(() => expect($('#tel-feedback').textContent).toContain('assign failed'));
  expect($('#tel-managed').textContent).toContain('agent-1');
  expect($('#tel-managed').textContent).toContain('not_configured');
  expect($('#tel-log').textContent).toContain('"assignmentSaved": true');
  expect($<HTMLButtonElement>('#tel-outbound-btn').disabled).toBe(true);
  expect($<HTMLButtonElement>('[data-import]').disabled).toBe(true);
});

test('timeout describes an unknown outcome, reloads state, and never retries a call', async () => {
  selectNumber();
  failAssignment = 'timeout';
  $('#tel-assign-btn').click();
  await vi.waitFor(() => expect($('#tel-feedback').textContent).toContain('server may still complete'));
  expect($('#tel-managed').textContent).toContain('agent-1');
  expect(request.mock.calls.filter(([path]) => path.endsWith('/assign'))).toHaveLength(1);
  expect(request.mock.calls.filter(([path]) => path.endsWith('/outbound'))).toHaveLength(0);
});

test('calls unlock only after assignment, routing, and refreshed readiness pass', async () => {
  selectNumber();
  $('#tel-assign-btn').click();
  await vi.waitFor(() => expect($('#tel-feedback').textContent).toContain('assignment and routing ready'));
  expect($<HTMLButtonElement>('#tel-outbound-btn').disabled).toBe(false);
  $<HTMLInputElement>('#tel-agent-id').value = 'different-agent';
  $('#tel-agent-id').dispatchEvent(new Event('input', { bubbles: true }));
  expect($<HTMLButtonElement>('#tel-outbound-btn').disabled).toBe(true);
});
