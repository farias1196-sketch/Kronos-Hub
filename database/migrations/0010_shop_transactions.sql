-- Ledger operacional da Loja para pagamentos registrados no atendimento.
CREATE TABLE IF NOT EXISTS shop_transactions (
    id VARCHAR(160) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    order_id VARCHAR(160) NOT NULL,
    amount NUMERIC(14,2) NOT NULL,
    method VARCHAR(50) NOT NULL DEFAULT 'manual',
    status VARCHAR(30) NOT NULL DEFAULT 'paid',
    reference VARCHAR(255),
    notes TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (tenant_id, order_id) REFERENCES shop_orders(tenant_id, id) ON DELETE CASCADE,
    UNIQUE (tenant_id, id),
    CHECK (amount >= 0)
);

CREATE INDEX IF NOT EXISTS idx_shop_transactions_order
ON shop_transactions(tenant_id, order_id, created_at DESC);
