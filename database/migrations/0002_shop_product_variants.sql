-- Produtos públicos podem representar uma família com diversas variações vendáveis.
ALTER TABLE shop_products ALTER COLUMN stock_item_id DROP NOT NULL;
ALTER TABLE shop_products ADD COLUMN IF NOT EXISTS stock_family_id VARCHAR(64);
ALTER TABLE shop_products
    ADD CONSTRAINT fk_shop_products_family
    FOREIGN KEY (tenant_id, stock_family_id)
    REFERENCES stock_families(tenant_id, id)
    ON DELETE CASCADE;

CREATE TABLE IF NOT EXISTS shop_product_variants (
    id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    shop_product_id VARCHAR(64) NOT NULL,
    stock_item_id VARCHAR(64) NOT NULL,
    sale_price NUMERIC(18,4) NOT NULL DEFAULT 0,
    promotional_price NUMERIC(18,4),
    sellable BOOLEAN NOT NULL DEFAULT TRUE,
    presentation JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (tenant_id, shop_product_id) REFERENCES shop_products(tenant_id, id) ON DELETE CASCADE,
    FOREIGN KEY (tenant_id, stock_item_id) REFERENCES stock_items(tenant_id, id) ON DELETE CASCADE,
    UNIQUE (tenant_id, shop_product_id, stock_item_id)
);

CREATE INDEX IF NOT EXISTS idx_shop_product_variants_product ON shop_product_variants(tenant_id, shop_product_id);

DROP TRIGGER IF EXISTS trg_shop_product_variants_updated_at ON shop_product_variants;
CREATE TRIGGER trg_shop_product_variants_updated_at
BEFORE UPDATE ON shop_product_variants
FOR EACH ROW EXECUTE FUNCTION chronos_set_updated_at();
