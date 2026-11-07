-- Alguns IDs históricos são descritivos e passam de 64 caracteres.
-- Preservá-los evita quebrar sessões, auditoria e referências já gravadas.

ALTER TABLE tenant_members ALTER COLUMN id TYPE VARCHAR(160);
ALTER TABLE audit_logs ALTER COLUMN id TYPE VARCHAR(160);
ALTER TABLE audit_logs ALTER COLUMN actor_member_id TYPE VARCHAR(160);
ALTER TABLE audit_logs ALTER COLUMN entity_id TYPE VARCHAR(160);
ALTER TABLE nexus_client_events ALTER COLUMN id TYPE VARCHAR(160);
