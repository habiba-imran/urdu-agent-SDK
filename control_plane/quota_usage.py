"""Include active sessions in monthly admission and worker enforcement."""
def active_minutes(conn, tenant_id: str) -> float:
    row = conn.execute(
        "select coalesce(sum(greatest(0, least(7200, extract(epoch from "
        "(now() - greatest(started_at, date_trunc('month', now())))))) / 60.0), 0) "
        "from sessions where tenant_id = %s and ended_at is null", (tenant_id,)
    ).fetchone()
    return float(row[0] or 0) if row else 0.0


def monthly_exhausted(conn, tenant_id: str) -> bool:
    row = conn.execute(
        "select t.max_minutes_month, case when q.period_start < date_trunc('month', now())::date "
        "then 0 else coalesce(q.minutes_this_month, 0) end from tenants t "
        "left join quota_state q on q.tenant_id = t.id where t.id = %s", (tenant_id,)
    ).fetchone()
    return bool(row and row[0] is not None and float(row[1] or 0) + active_minutes(conn, tenant_id) >= float(row[0]))
