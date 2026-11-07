-- Mapeia identificadores históricos para o tenant canônico sem alterar a fonte.
CREATE TABLE IF NOT EXISTS tenant_source_aliases (
    source_system VARCHAR(80) NOT NULL,
    source_tenant_id VARCHAR(128) NOT NULL,
    tenant_id VARCHAR(64) NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (source_system, source_tenant_id)
);

CREATE INDEX IF NOT EXISTS idx_tenant_source_aliases_tenant
ON tenant_source_aliases(tenant_id);
