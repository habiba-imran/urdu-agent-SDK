"""A new call reads current settings and cannot switch to another tenant's duplicate number."""
import asyncio
from types import SimpleNamespace

from worker.telephony_runtime import resolve_session_metadata


def test_dispatch_revalidation_stays_in_ui_tenant():
    observed = []
    class DuplicateNumberDb:
        def execute(self, query, params):
            # A disabled historical row for the same E.164 must never replace
            # the UI-selected tenant/agent with its old Gemini configuration.
            observed.append((query, params))
            return SimpleNamespace(fetchone=lambda: ('ui-tenant', 'ui-agent', 'owned', 'ready'))

    resolved = resolve_session_metadata(job_metadata={
        'tenant_id': 'ui-tenant', 'agent_id': 'ui-agent',
        'direction': 'inbound', 'e164_number': '+13144621603',
    }, db_conn=DuplicateNumberDb())
    assert resolved['tenant_id'] == 'ui-tenant'
    assert resolved['agent_id'] == 'ui-agent'
    query, params = observed[0]
    assert 'n.tenant_id = %s' in query
    assert 'n.disabled_at is null' in query
    assert params == ('+13144621603', 'ui-tenant')


def test_new_call_bypasses_short_agent_configuration_cache(monkeypatch):
    import worker.main as main
    class ConfigurationRead(Exception):
        pass
    observed = {}
    def load(agent, tenant, **kwargs):
        observed.update(agent=agent, tenant=tenant, **kwargs)
        raise ConfigurationRead
    monkeypatch.setattr(main, 'load_agent_session_bundle', load)
    try:
        asyncio.run(main.build_session({'agent_id': 'ui-agent', 'tenant_id': 'ui-tenant'}, room_name='ui-config-test'))
    except ConfigurationRead:
        pass
    else:
        raise AssertionError('Expected configuration read before provider construction')
    assert observed == {'agent': 'ui-agent', 'tenant': 'ui-tenant', 'use_cache': False}
