-- Ensure Telnyx provider number IDs are unique per tenant so inventory sync can
-- upsert by the provider resource identity while preserving tenant isolation.
create unique index if not exists telephony_phone_numbers_provider_number_per_tenant_uidx
  on telephony_phone_numbers (tenant_id, provider_number_id)
  where provider_number_id is not null;
