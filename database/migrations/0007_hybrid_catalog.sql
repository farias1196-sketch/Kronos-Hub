-- Catálogo híbrido: campos comerciais e financeiros normalizados, atributos
-- específicos de cada segmento em JSONB e snapshots derivados para leitura.

CREATE TABLE IF NOT EXISTS stock_category_attribute_definitions (
    id VARCHAR(96) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    category_id VARCHAR(160) NOT NULL,
    field_key VARCHAR(96) NOT NULL,
    label VARCHAR(160) NOT NULL,
    value_type VARCHAR(30) NOT NULL DEFAULT 'text',
    required BOOLEAN NOT NULL DEFAULT FALSE,
    options JSONB NOT NULL DEFAULT '[]'::jsonb,
    display_order INTEGER NOT NULL DEFAULT 0,
    settings JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (tenant_id, category_id) REFERENCES stock_categories(tenant_id, id) ON DELETE CASCADE,
    UNIQUE (tenant_id, category_id, field_key)
);

CREATE TABLE IF NOT EXISTS catalog_snapshots (
    tenant_id VARCHAR(64) NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    version BIGSERIAL NOT NULL,
    checksum CHAR(64) NOT NULL,
    payload JSONB NOT NULL,
    generated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (tenant_id, version),
    UNIQUE (tenant_id, checksum)
);

CREATE INDEX IF NOT EXISTS idx_catalog_snapshot_current
ON catalog_snapshots(tenant_id, generated_at DESC);
CREATE INDEX IF NOT EXISTS idx_attribute_definitions_category
ON stock_category_attribute_definitions(tenant_id, category_id, display_order);

DROP TRIGGER IF EXISTS trg_stock_category_attribute_definitions_updated_at ON stock_category_attribute_definitions;
CREATE TRIGGER trg_stock_category_attribute_definitions_updated_at
BEFORE UPDATE ON stock_category_attribute_definitions
FOR EACH ROW EXECUTE FUNCTION chronos_set_updated_at();
