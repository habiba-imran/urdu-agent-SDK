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
    if (path.endsWith('/status')) return Response.json({ tenantId: 'demo-tenant', connection: { platform_status: 'active' }, readiness: { is_ready: ready, reasons: ready ? [] : ['Number routing is incomplete.'] } });
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

afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); });

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
  expect($('#tel-outbound-btn').textContent).toBe('Routing not ready');
  expect($('#tel-call-hint').textContent).toContain('Agent assignment is saved');
  expect($('#tel-call-hint').textContent).toContain('another tenant');
  expect($<HTMLButtonElement>('#tel-outbound-btn').title).toBe($('#tel-call-hint').textContent);
  expect($('#tel-status').textContent).toContain('demo-tenant');
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
  expect($('#tel-outbound-btn').textContent).toBe('Place outbound call');
  $<HTMLInputElement>('#tel-agent-id').value = 'different-agent';
  $('#tel-agent-id').dispatchEvent(new Event('input', { bubbles: true }));
  expect($<HTMLButtonElement>('#tel-outbound-btn').disabled).toBe(true);
});

test('a pending assignment shows progress while refresh, calls and search remain usable', async () => {
  selectNumber();
  const upstream = request.getMockImplementation()!;
  let finish!: (response: Response) => void;
  request.mockImplementation((input: string) => new URL(input).pathname.endsWith('/assign')
    ? new Promise<Response>(resolve => { finish = resolve; }) : upstream(input));
  $('#tel-assign-btn').click();
  expect($<HTMLButtonElement>('#tel-assign-btn').disabled).toBe(true);
  expect($<HTMLButtonElement>('#tel-sync-btn').disabled).toBe(true);
  expect($<HTMLButtonElement>('#tel-refresh-btn').disabled).toBe(false);
  expect($<HTMLButtonElement>('#tel-calls-btn').disabled).toBe(false);
  expect($<HTMLButtonElement>('#tel-search-btn').disabled).toBe(false);
  expect($<HTMLInputElement>('#tel-country').disabled).toBe(false);
  expect($('#tel-progress').hidden).toBe(false);
  expect($('#tel-progress-action').textContent).toContain('Configuring agent routing');
  $('#tel-calls-btn').click();
  await vi.waitFor(() => expect($('#tel-log').textContent).toContain('recent calls'));
  expect($<HTMLButtonElement>('#tel-assign-btn').disabled).toBe(true);
  finish(Response.json({ message: 'Routing conflict' }, { status: 409 }));
  await vi.waitFor(() => expect($('#tel-feedback').textContent).toContain('Routing conflict'));
  expect($('#tel-progress').hidden).toBe(true);
});

test('hung reads time out, unlock their controls, and ignore a late response', async () => {
  const upstream = request.getMockImplementation()!;
  let finish!: (response: Response) => void;
  let hang = true;
  request.mockImplementation((input: string) => new URL(input).pathname.endsWith('/numbers') && hang
    ? new Promise<Response>(resolve => { finish = resolve; }) : upstream(input));
  vi.useFakeTimers();
  $('#tel-refresh-btn').click();
  expect($<HTMLInputElement>('#tel-number-id').disabled).toBe(false);
  expect($<HTMLButtonElement>('#tel-connect-btn').disabled).toBe(false);
  await vi.advanceTimersByTimeAsync(20001);
  expect($('#tel-feedback').textContent).toContain('timed out after 20 seconds');
  expect($<HTMLButtonElement>('#tel-refresh-btn').disabled).toBe(false);
  expect($('#tel-progress').hidden).toBe(true);
  finish(Response.json({ managed: [{ id: 'late-record', e164_number: '+15550009999' }], owned: [] }));
  await vi.advanceTimersByTimeAsync(1);
  expect($('#tel-managed').textContent).not.toContain('+15550009999');
  hang = false;
  $('#tel-refresh-btn').click();
  await vi.advanceTimersByTimeAsync(1);
  expect($('#tel-managed').textContent).toContain('+15551234567');
});

test('a response with a stalled body also reaches the read deadline', async () => {
  const upstream = request.getMockImplementation()!;
  request.mockImplementation((input: string) => new URL(input).pathname.endsWith('/calls')
    ? Promise.resolve({ ok: true, text: () => new Promise(() => {}) } as Response) : upstream(input));
  vi.useFakeTimers();
  $('#tel-calls-btn').click();
  await vi.advanceTimersByTimeAsync(20001);
  expect($('#tel-feedback').textContent).toContain('timed out after 20 seconds');
  expect($<HTMLButtonElement>('#tel-calls-btn').disabled).toBe(false);
  expect($('#tel-progress').hidden).toBe(true);
});

test('a hung mutation expires without an automatic retry and clears progress', async () => {
  selectNumber();
  const upstream = request.getMockImplementation()!;
  request.mockImplementation((input: string) => new URL(input).pathname.endsWith('/assign')
    ? new Promise<Response>(() => {}) : upstream(input));
  vi.useFakeTimers();
  $('#tel-assign-btn').click();
  await vi.advanceTimersByTimeAsync(1000);
  expect($('#tel-progress-elapsed').textContent).toContain('1s elapsed');
  await vi.advanceTimersByTimeAsync(149001);
  expect($('#tel-feedback').textContent).toContain('server may still complete');
  expect($<HTMLButtonElement>('#tel-assign-btn').disabled).toBe(false);
  expect($<HTMLInputElement>('#tel-number-id').disabled).toBe(false);
  expect($('#tel-progress').hidden).toBe(true);
  expect(request.mock.calls.filter(([path]) => path.endsWith('/assign'))).toHaveLength(1);
  expect(request.mock.calls.filter(([path]) => path.endsWith('/outbound'))).toHaveLength(0);
});

test('overlapping refresh events share their in-flight read requests', async () => {
  const upstream = request.getMockImplementation()!;
  let finish!: (response: Response) => void;
  request.mockImplementation((input: string) => new URL(input).pathname.endsWith('/numbers')
    ? new Promise<Response>(resolve => { finish = resolve; }) : upstream(input));
  const before = request.mock.calls.filter(([path]) => path.endsWith('/numbers')).length;
  $('#tel-refresh-btn').click();
  $('#tel-refresh-btn').dispatchEvent(new MouseEvent('click'));
  expect(request.mock.calls.filter(([path]) => path.endsWith('/numbers'))).toHaveLength(before + 1);
  finish(Response.json({ managed: [number], owned: [] }));
  await vi.waitFor(() => expect($('#tel-progress').hidden).toBe(true));
});
