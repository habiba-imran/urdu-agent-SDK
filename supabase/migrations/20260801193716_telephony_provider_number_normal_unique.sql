-- Replace partial provider-number uniqueness with a normal tenant-scoped unique
-- constraint so ON CONFLICT (tenant_id, provider_number_id) can be inferred
-- without a partial-index predicate. PostgreSQL unique constraints allow multiple
-- NULL provider_number_id values, so imported/pre-provider rows remain valid.

do $$
declare
  duplicate_group_count bigint;
begin
  lock table telephony_phone_numbers in share row exclusive mode;

  select count(*) into duplicate_group_count
  from (
    select tenant_id, provider_number_id
    from telephony_phone_numbers
    where provider_number_id is not null
    group by tenant_id, provider_number_id
    having count(*) > 1
  ) duplicates;

  if duplicate_group_count > 0 then
    raise exception
      using
        errcode = '23505',
        message = 'Cannot add telephony provider-number unique constraint: duplicate provider IDs exist.',
        detail = duplicate_group_count || ' duplicate tenant/provider-number group(s) must be resolved first.',
        hint = 'Deduplicate telephony_phone_numbers rows with the same tenant_id and provider_number_id before applying this migration.';
  end if;
end $$;

drop index if exists telephony_phone_numbers_provider_number_per_tenant_uidx;

do $$
begin
  if not exists (
    select 1
    from pg_constraint
    where conrelid = 'telephony_phone_numbers'::regclass
      and conname = 'telephony_phone_numbers_provider_number_per_tenant_key'
  ) then
    alter table telephony_phone_numbers
      add constraint telephony_phone_numbers_provider_number_per_tenant_key
      unique (tenant_id, provider_number_id);
  end if;
end $$;
