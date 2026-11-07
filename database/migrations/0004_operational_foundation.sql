-- Complementos necessários para a virada operacional do Hub 2 para PostgreSQL.

CREATE TABLE IF NOT EXISTS billing_plans (
    slug VARCHAR(96) PRIMARY KEY,
    name VARCHAR(160) NOT NULL,
    monthly_price NUMERIC(14,2) NOT NULL DEFAULT 0,
    ai_weekly_credits INTEGER NOT NULL DEFAULT 0,
    ai_monthly_credits INTEGER NOT NULL DEFAULT 0,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    settings JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (monthly_price >= 0),
    CHECK (ai_weekly_credits >= 0),
    CHECK (ai_monthly_credits >= 0)
);

CREATE TABLE IF NOT EXISTS tenant_subscriptions (
    id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    plan_slug VARCHAR(96) REFERENCES billing_plans(slug) ON DELETE SET NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'TRIAL',
    starts_at TIMESTAMPTZ,
    ends_at TIMESTAMPTZ,
    provider VARCHAR(50),
    provider_subscription_id VARCHAR(255),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (tenant_id),
    UNIQUE (provider, provider_subscription_id)
);

CREATE TABLE IF NOT EXISTS billing_invoices (
    id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    subscription_id VARCHAR(64) REFERENCES tenant_subscriptions(id) ON DELETE SET NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'draft',
    amount NUMERIC(14,2) NOT NULL DEFAULT 0,
    due_date DATE,
    paid_at TIMESTAMPTZ,
    provider VARCHAR(50),
    provider_invoice_id VARCHAR(255),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (provider, provider_invoice_id),
    CHECK (amount >= 0)
);

CREATE TABLE IF NOT EXISTS nexus_client_events (
    id VARCHAR(96) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    client_id VARCHAR(64) NOT NULL,
    event_type VARCHAR(100) NOT NULL,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (tenant_id, client_id) REFERENCES nexus_clients(tenant_id, id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS stock_suppliers (
    id VARCHAR(96) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    document VARCHAR(30),
    contact_name VARCHAR(255),
    phone VARCHAR(30),
    email VARCHAR(255),
    address JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (tenant_id, name)
);

CREATE TABLE IF NOT EXISTS stock_service_resources (
    id VARCHAR(96) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'active',
    settings JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (tenant_id, name)
);

CREATE TABLE IF NOT EXISTS shop_refunds (
    id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    order_id VARCHAR(64) NOT NULL,
    amount NUMERIC(14,2) NOT NULL,
    reason TEXT,
    items JSONB NOT NULL DEFAULT '[]'::jsonb,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (tenant_id, order_id) REFERENCES shop_orders(tenant_id, id) ON DELETE RESTRICT,
    CHECK (amount > 0)
);

CREATE TABLE IF NOT EXISTS data_migration_runs (
    id VARCHAR(64) PRIMARY KEY,
    source_name VARCHAR(100) NOT NULL,
    source_fingerprint VARCHAR(128) NOT NULL,
    status VARCHAR(30) NOT NULL,
    report JSONB NOT NULL DEFAULT '{}'::jsonb,
    started_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMPTZ,
    UNIQUE (source_name, source_fingerprint)
);

CREATE TABLE IF NOT EXISTS data_migration_counts (
    run_id VARCHAR(64) NOT NULL REFERENCES data_migration_runs(id) ON DELETE CASCADE,
    entity_name VARCHAR(100) NOT NULL,
    source_count INTEGER NOT NULL DEFAULT 0,
    imported_count INTEGER NOT NULL DEFAULT 0,
    skipped_count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (run_id, entity_name)
);

CREATE INDEX IF NOT EXISTS idx_nexus_client_events_tenant_client
ON nexus_client_events(tenant_id, client_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_subscriptions_tenant_status
ON tenant_subscriptions(tenant_id, status);
CREATE INDEX IF NOT EXISTS idx_billing_invoices_tenant_status
ON billing_invoices(tenant_id, status, due_date);

DO $$
DECLARE table_name TEXT;
BEGIN
    FOREACH table_name IN ARRAY ARRAY[
        'billing_plans', 'tenant_subscriptions', 'billing_invoices',
        'stock_suppliers', 'stock_service_resources'
    ]
    LOOP
        EXECUTE format('DROP TRIGGER IF EXISTS trg_%1$s_updated_at ON %1$I', table_name);
        EXECUTE format(
            'CREATE TRIGGER trg_%1$s_updated_at BEFORE UPDATE ON %1$I FOR EACH ROW EXECUTE FUNCTION chronos_set_updated_at()',
            table_name
        );
    END LOOP;
END;
$$;
