import { describe, expect, it, vi } from 'vitest';
import { AwaazLabsUvaVoice, type MetricsEvent } from './index.js';

function setup() {
  const client = new AwaazLabsUvaVoice({ publishableKey: 'pk_test', sessionEndpoint: 'https://host.example/v1/session' });
  const access = client as unknown as {
    emitLatencyEvents: (event: MetricsEvent) => void;
    tryParseMetrics: (text: string) => MetricsEvent | null;
  };
  return { client, access };
}

describe('Phase 1 additive diagnostic compatibility', () => {
  it('preserves legacy forwarding while a dual subscriber can process each turn once', () => {
    const { client, access } = setup();
    const turn = vi.fn();
    const aggregate = vi.fn();
    const legacy = vi.fn();
    client.on('turn_latency', turn);
    client.on('metrics_updated', legacy);
    client.on('metrics_updated', (event) => {
      if (event.type === 'metrics_updated') aggregate(event);
    });
    const event: MetricsEvent = { type: 'turn_latency', speechId: 'sp1', generation_id: 'generation_1',
      outcome: 'cancelled_speculation', humanization_policy_version: 'baseline', e2eMs: null };
    access.emitLatencyEvents(event);
    access.emitLatencyEvents({ type: 'metrics_updated', turnCount: 0, sampleCounts: { e2e: 0 } });
    expect(turn).toHaveBeenCalledExactlyOnceWith(event);
    expect(aggregate).toHaveBeenCalledTimes(1);
    expect(legacy).toHaveBeenCalledTimes(2);
  });

  it('retains all additive fields and unavailable values without interpreting policy', () => {
    const { access } = setup();
    const event: MetricsEvent = { type: 'turn_latency', session_id: 'session_1', outcome: 'provider_error',
      stages: { first_speakable_chunk_ready: null }, providerSnapshot: { language: 'ur', channel: 'telephony' },
      e2eMs: null, tools: [{ tool_call_id: 'tool_1', outcome: 'tool_outcome_unknown' }] };
    expect(access.tryParseMetrics(JSON.stringify(event))).toEqual(event);
  });

  it('continues to accept old workers and rejects unrelated or malformed data', () => {
    const { access } = setup();
    expect(access.tryParseMetrics('{"type":"turn_latency","e2eMs":500}')).toEqual({ type: 'turn_latency', e2eMs: 500 });
    expect(access.tryParseMetrics('{"type":"unrelated"}')).toBeNull();
    expect(access.tryParseMetrics('invalid')).toBeNull();
  });
});
