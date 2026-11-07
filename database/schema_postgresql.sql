-- Chronos Hub 2.0: schema relacional unificado para PostgreSQL.
-- O banco deve ser criado com UTF8. Valores monetários usam NUMERIC, nunca FLOAT.

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS chronos_schema_migrations (
    version TEXT PRIMARY KEY,
    checksum TEXT NOT NULL,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE OR REPLACE FUNCTION chronos_set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Core: empresa, identidade, membros e permissões.
CREATE TABLE IF NOT EXISTS tenants (
    id VARCHAR(64) PRIMARY KEY,
    slug VARCHAR(96) UNIQUE NOT NULL,
    name VARCHAR(255) NOT NULL,
    trade_name VARCHAR(255),
    document VARCHAR(20),
    email VARCHAR(255),
    phone VARCHAR(30),
    status VARCHAR(30) NOT NULL DEFAULT 'TRIAL',
    theme_slug VARCHAR(50) NOT NULL DEFAULT 'rosa-branco',
    logo_url TEXT,
    fiscal_data JSONB NOT NULL DEFAULT '{}'::jsonb,
    settings JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS users (
    id VARCHAR(64) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'ACTIVE',
    recovery_phone VARCHAR(30),
    recovery_phone_verified BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS tenant_members (
    id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    user_id VARCHAR(64) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role VARCHAR(50) NOT NULL DEFAULT 'OPERATOR',
    title VARCHAR(100),
    department VARCHAR(100),
    password_hash VARCHAR(255),
    permissions JSONB NOT NULL DEFAULT '[]'::jsonb,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    must_change_password BOOLEAN NOT NULL DEFAULT FALSE,
    invited_at TIMESTAMPTZ,
    invite_accepted_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (tenant_id, user_id),
    UNIQUE (tenant_id, id)
);

CREATE TABLE IF NOT EXISTS app_modules (
    slug VARCHAR(64) PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    full_name VARCHAR(160) NOT NULL,
    description TEXT,
    status VARCHAR(30) NOT NULL DEFAULT 'ACTIVE',
    visible BOOLEAN NOT NULL DEFAULT TRUE,
    settings JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS tenant_modules (
    tenant_id VARCHAR(64) NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    module_slug VARCHAR(64) NOT NULL REFERENCES app_modules(slug) ON DELETE CASCADE,
    status VARCHAR(30) NOT NULL DEFAULT 'ACTIVE',
    show_in_menu BOOLEAN NOT NULL DEFAULT TRUE,
    settings JSONB NOT NULL DEFAULT '{}'::jsonb,
    PRIMARY KEY (tenant_id, module_slug)
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    actor_member_id VARCHAR(64),
    module_slug VARCHAR(64),
    action VARCHAR(100) NOT NULL,
    entity_type VARCHAR(100),
    entity_id VARCHAR(64),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Nexus: CRM e pontos de contato vinculáveis manualmente.
CREATE TABLE IF NOT EXISTS nexus_clients (
    id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    company_name VARCHAR(255),
    fiscal_document VARCHAR(20),
    email VARCHAR(255),
    notes TEXT,
    address JSONB NOT NULL DEFAULT '{}'::jsonb,
    source VARCHAR(50) NOT NULL DEFAULT 'manual',
    registration_status VARCHAR(50) NOT NULL DEFAULT 'complete',
    assigned_member_id VARCHAR(64),
    assigned_seller_name VARCHAR(255),
    conversation_status VARCHAR(50) NOT NULL DEFAULT 'novo',
    order_status VARCHAR(50) NOT NULL DEFAULT 'sem_pedido',
    art_status VARCHAR(50) NOT NULL DEFAULT 'sem_arte',
    art_briefing TEXT,
    art_link TEXT,
    art_notes TEXT,
    custom_fields JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (tenant_id, id)
);

CREATE TABLE IF NOT EXISTS nexus_contact_points (
    id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    client_id VARCHAR(64) NOT NULL,
    channel VARCHAR(30) NOT NULL,
    value VARCHAR(255) NOT NULL,
    normalized_value VARCHAR(255) NOT NULL,
    is_primary BOOLEAN NOT NULL DEFAULT FALSE,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (tenant_id, client_id) REFERENCES nexus_clients(tenant_id, id) ON DELETE CASCADE,
    UNIQUE (tenant_id, channel, normalized_value)
);

CREATE TABLE IF NOT EXISTS nexus_tags (
    id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL,
    color VARCHAR(20),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (tenant_id, name),
    UNIQUE (tenant_id, id)
);

CREATE TABLE IF NOT EXISTS nexus_client_tags (
    tenant_id VARCHAR(64) NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    client_id VARCHAR(64) NOT NULL,
    tag_id VARCHAR(64) NOT NULL,
    PRIMARY KEY (tenant_id, client_id, tag_id),
    FOREIGN KEY (tenant_id, client_id) REFERENCES nexus_clients(tenant_id, id) ON DELETE CASCADE,
    FOREIGN KEY (tenant_id, tag_id) REFERENCES nexus_tags(tenant_id, id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS nexus_client_merges (
    id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    primary_client_id VARCHAR(64) NOT NULL,
    merged_client_id VARCHAR(64) NOT NULL,
    merged_by_member_id VARCHAR(64),
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (tenant_id, primary_client_id) REFERENCES nexus_clients(tenant_id, id) ON DELETE RESTRICT,
    FOREIGN KEY (tenant_id, merged_client_id) REFERENCES nexus_clients(tenant_id, id) ON DELETE RESTRICT,
    CHECK (primary_client_id <> merged_client_id)
);

-- Stock: famílias, itens/variações, atributos e faixas de preço.
CREATE TABLE IF NOT EXISTS stock_categories (
    id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL,
    slug VARCHAR(100) NOT NULL,
    description TEXT,
    custom_columns JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (tenant_id, slug),
    UNIQUE (tenant_id, id)
);

CREATE TABLE IF NOT EXISTS stock_families (
    id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    category_id VARCHAR(64),
    name VARCHAR(255) NOT NULL,
    slug VARCHAR(255) NOT NULL,
    description TEXT,
    attributes JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (tenant_id, category_id) REFERENCES stock_categories(tenant_id, id) ON DELETE SET NULL,
    UNIQUE (tenant_id, slug),
    UNIQUE (tenant_id, id)
);

CREATE TABLE IF NOT EXISTS stock_items (
    id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    category_id VARCHAR(64),
    family_id VARCHAR(64),
    sku VARCHAR(100) NOT NULL,
    name VARCHAR(255) NOT NULL,
    display_name VARCHAR(255),
    description TEXT,
    kind VARCHAR(30) NOT NULL DEFAULT 'sale',
    unit VARCHAR(12) NOT NULL DEFAULT 'UN',
    quantity NUMERIC(14,2) NOT NULL DEFAULT 0,
    min_quantity NUMERIC(14,2) NOT NULL DEFAULT 0,
    cost_price NUMERIC(18,4) NOT NULL DEFAULT 0,
    supplier VARCHAR(255),
    location VARCHAR(255),
    width NUMERIC(10,2),
    height NUMERIC(10,2),
    depth NUMERIC(10,2),
    weight_grams NUMERIC(12,3),
    attributes JSONB NOT NULL DEFAULT '{}'::jsonb,
    status VARCHAR(30) NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (tenant_id, category_id) REFERENCES stock_categories(tenant_id, id) ON DELETE SET NULL,
    FOREIGN KEY (tenant_id, family_id) REFERENCES stock_families(tenant_id, id) ON DELETE SET NULL,
    UNIQUE (tenant_id, sku),
    UNIQUE (tenant_id, id)
);

CREATE TABLE IF NOT EXISTS stock_tier_prices (
    id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    stock_item_id VARCHAR(64) NOT NULL,
    min_quantity NUMERIC(14,2) NOT NULL,
    unit_price NUMERIC(18,4) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (tenant_id, stock_item_id) REFERENCES stock_items(tenant_id, id) ON DELETE CASCADE,
    UNIQUE (stock_item_id, min_quantity),
    CHECK (min_quantity > 0),
    CHECK (unit_price >= 0)
);

CREATE TABLE IF NOT EXISTS stock_movements (
    id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    stock_item_id VARCHAR(64) NOT NULL,
    movement_type VARCHAR(30) NOT NULL,
    quantity_delta NUMERIC(14,2) NOT NULL,
    balance_after NUMERIC(14,2),
    reference_type VARCHAR(50),
    reference_id VARCHAR(64),
    notes TEXT,
    created_by_member_id VARCHAR(64),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (tenant_id, stock_item_id) REFERENCES stock_items(tenant_id, id) ON DELETE RESTRICT
);

-- Loja: publicação, carrinhos, orçamentos e pedidos.
CREATE TABLE IF NOT EXISTS shop_configs (
    tenant_id VARCHAR(64) PRIMARY KEY REFERENCES tenants(id) ON DELETE CASCADE,
    store_name VARCHAR(255),
    public_slug VARCHAR(120),
    custom_domain VARCHAR(255),
    domain_status VARCHAR(50) NOT NULL DEFAULT 'not_configured',
    whatsapp VARCHAR(30),
    selected_template VARCHAR(80),
    settings JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (public_slug)
);

CREATE TABLE IF NOT EXISTS shop_products (
    id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    stock_item_id VARCHAR(64) NOT NULL,
    public_name VARCHAR(255),
    public_description TEXT,
    public_category VARCHAR(100),
    image_url TEXT,
    published BOOLEAN NOT NULL DEFAULT FALSE,
    highlight BOOLEAN NOT NULL DEFAULT FALSE,
    display_order INTEGER NOT NULL DEFAULT 0,
    visible_stock BOOLEAN NOT NULL DEFAULT FALSE,
    presentation JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (tenant_id, stock_item_id) REFERENCES stock_items(tenant_id, id) ON DELETE CASCADE,
    UNIQUE (tenant_id, stock_item_id),
    UNIQUE (tenant_id, id)
);

CREATE TABLE IF NOT EXISTS shop_carts (
    id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    client_id VARCHAR(64),
    status VARCHAR(30) NOT NULL DEFAULT 'open',
    source VARCHAR(50) NOT NULL DEFAULT 'shop',
    snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (tenant_id, client_id) REFERENCES nexus_clients(tenant_id, id) ON DELETE SET NULL,
    UNIQUE (tenant_id, id)
);

CREATE TABLE IF NOT EXISTS shop_cart_items (
    id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    cart_id VARCHAR(64) NOT NULL,
    stock_item_id VARCHAR(64) NOT NULL,
    quantity NUMERIC(14,2) NOT NULL,
    selected_options JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (tenant_id, cart_id) REFERENCES shop_carts(tenant_id, id) ON DELETE CASCADE,
    FOREIGN KEY (tenant_id, stock_item_id) REFERENCES stock_items(tenant_id, id) ON DELETE RESTRICT,
    CHECK (quantity > 0)
);

CREATE TABLE IF NOT EXISTS shop_quotes (
    id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    client_id VARCHAR(64),
    seller_member_id VARCHAR(64),
    quote_number BIGINT NOT NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'draft',
    subtotal NUMERIC(14,2) NOT NULL DEFAULT 0,
    discount NUMERIC(14,2) NOT NULL DEFAULT 0,
    freight NUMERIC(14,2) NOT NULL DEFAULT 0,
    total NUMERIC(14,2) NOT NULL DEFAULT 0,
    notes TEXT,
    layout_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
    expires_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (tenant_id, client_id) REFERENCES nexus_clients(tenant_id, id) ON DELETE SET NULL,
    UNIQUE (tenant_id, quote_number),
    UNIQUE (tenant_id, id)
);

CREATE TABLE IF NOT EXISTS shop_quote_items (
    id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    quote_id VARCHAR(64) NOT NULL,
    stock_item_id VARCHAR(64),
    sku VARCHAR(100) NOT NULL,
    name VARCHAR(255) NOT NULL,
    quantity NUMERIC(14,2) NOT NULL,
    unit_price NUMERIC(18,4) NOT NULL,
    total NUMERIC(14,2) NOT NULL,
    options JSONB NOT NULL DEFAULT '{}'::jsonb,
    FOREIGN KEY (tenant_id, quote_id) REFERENCES shop_quotes(tenant_id, id) ON DELETE CASCADE,
    FOREIGN KEY (tenant_id, stock_item_id) REFERENCES stock_items(tenant_id, id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS shop_orders (
    id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    quote_id VARCHAR(64),
    client_id VARCHAR(64),
    seller_member_id VARCHAR(64),
    order_number BIGINT NOT NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'new',
    subtotal NUMERIC(14,2) NOT NULL DEFAULT 0,
    discount NUMERIC(14,2) NOT NULL DEFAULT 0,
    freight NUMERIC(14,2) NOT NULL DEFAULT 0,
    total NUMERIC(14,2) NOT NULL DEFAULT 0,
    notes TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (tenant_id, quote_id) REFERENCES shop_quotes(tenant_id, id) ON DELETE SET NULL,
    FOREIGN KEY (tenant_id, client_id) REFERENCES nexus_clients(tenant_id, id) ON DELETE SET NULL,
    UNIQUE (tenant_id, order_number),
    UNIQUE (tenant_id, id)
);

CREATE TABLE IF NOT EXISTS shop_order_items (
    id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    order_id VARCHAR(64) NOT NULL,
    stock_item_id VARCHAR(64),
    sku VARCHAR(100) NOT NULL,
    name VARCHAR(255) NOT NULL,
    quantity NUMERIC(14,2) NOT NULL,
    unit_price NUMERIC(18,4) NOT NULL,
    total NUMERIC(14,2) NOT NULL,
    options JSONB NOT NULL DEFAULT '{}'::jsonb,
    FOREIGN KEY (tenant_id, order_id) REFERENCES shop_orders(tenant_id, id) ON DELETE CASCADE,
    FOREIGN KEY (tenant_id, stock_item_id) REFERENCES stock_items(tenant_id, id) ON DELETE SET NULL
);

-- Agenda.
CREATE TABLE IF NOT EXISTS agenda_services (
    id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    duration_minutes INTEGER NOT NULL,
    price NUMERIC(14,2) NOT NULL DEFAULT 0,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    settings JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (tenant_id, id),
    CHECK (duration_minutes > 0)
);

CREATE TABLE IF NOT EXISTS agenda_appointments (
    id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    client_id VARCHAR(64),
    service_id VARCHAR(64),
    assigned_member_id VARCHAR(64),
    starts_at TIMESTAMPTZ NOT NULL,
    ends_at TIMESTAMPTZ NOT NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'scheduled',
    notes TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (tenant_id, client_id) REFERENCES nexus_clients(tenant_id, id) ON DELETE SET NULL,
    FOREIGN KEY (tenant_id, service_id) REFERENCES agenda_services(tenant_id, id) ON DELETE SET NULL,
    CHECK (ends_at > starts_at)
);

-- Zap/Flow: uma conversa pode apontar para o mesmo cliente em qualquer canal.
CREATE TABLE IF NOT EXISTS zap_conversations (
    id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    client_id VARCHAR(64),
    channel VARCHAR(30) NOT NULL DEFAULT 'whatsapp',
    external_conversation_id VARCHAR(255),
    contact_point VARCHAR(255),
    display_name VARCHAR(255),
    last_message TEXT,
    last_message_at TIMESTAMPTZ,
    unread_count INTEGER NOT NULL DEFAULT 0,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (tenant_id, client_id) REFERENCES nexus_clients(tenant_id, id) ON DELETE SET NULL,
    UNIQUE (tenant_id, channel, external_conversation_id),
    UNIQUE (tenant_id, id)
);

CREATE TABLE IF NOT EXISTS zap_messages (
    id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    conversation_id VARCHAR(64) NOT NULL,
    client_id VARCHAR(64),
    channel VARCHAR(30) NOT NULL DEFAULT 'whatsapp',
    direction VARCHAR(15) NOT NULL,
    external_message_id VARCHAR(255),
    text TEXT,
    media JSONB NOT NULL DEFAULT '{}'::jsonb,
    status VARCHAR(30) NOT NULL DEFAULT 'received',
    raw_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (tenant_id, conversation_id) REFERENCES zap_conversations(tenant_id, id) ON DELETE CASCADE,
    FOREIGN KEY (tenant_id, client_id) REFERENCES nexus_clients(tenant_id, id) ON DELETE SET NULL,
    UNIQUE (tenant_id, external_message_id),
    UNIQUE (tenant_id, id)
);

CREATE TABLE IF NOT EXISTS zap_message_queue (
    id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    conversation_id VARCHAR(64),
    message_id VARCHAR(64),
    queue_type VARCHAR(50) NOT NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'QUEUED',
    priority INTEGER NOT NULL DEFAULT 0,
    attempts INTEGER NOT NULL DEFAULT 0,
    available_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    last_error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (tenant_id, conversation_id) REFERENCES zap_conversations(tenant_id, id) ON DELETE CASCADE,
    FOREIGN KEY (tenant_id, message_id) REFERENCES zap_messages(tenant_id, id) ON DELETE SET NULL
);

-- Pay, fiscal e conectores externos. Segredos são cifrados pela aplicação antes da gravação.
CREATE TABLE IF NOT EXISTS integration_connections (
    id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    provider VARCHAR(50) NOT NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'disconnected',
    account_reference VARCHAR(255),
    secret_ciphertext TEXT,
    settings JSONB NOT NULL DEFAULT '{}'::jsonb,
    connected_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (tenant_id, provider)
);

CREATE TABLE IF NOT EXISTS pay_charges (
    id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    order_id VARCHAR(64),
    client_id VARCHAR(64),
    provider VARCHAR(50) NOT NULL,
    external_charge_id VARCHAR(255),
    payment_method VARCHAR(50),
    status VARCHAR(30) NOT NULL DEFAULT 'pending',
    amount NUMERIC(14,2) NOT NULL,
    due_date DATE,
    paid_at TIMESTAMPTZ,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (tenant_id, order_id) REFERENCES shop_orders(tenant_id, id) ON DELETE SET NULL,
    FOREIGN KEY (tenant_id, client_id) REFERENCES nexus_clients(tenant_id, id) ON DELETE SET NULL,
    UNIQUE (tenant_id, provider, external_charge_id),
    UNIQUE (tenant_id, id),
    CHECK (amount >= 0)
);

CREATE TABLE IF NOT EXISTS pay_transactions (
    id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    charge_id VARCHAR(64) NOT NULL,
    provider_transaction_id VARCHAR(255),
    status VARCHAR(30) NOT NULL,
    amount NUMERIC(14,2) NOT NULL,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (tenant_id, charge_id) REFERENCES pay_charges(tenant_id, id) ON DELETE CASCADE,
    UNIQUE (tenant_id, provider_transaction_id),
    CHECK (amount >= 0)
);

CREATE TABLE IF NOT EXISTS fiscal_invoices (
    id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    order_id VARCHAR(64),
    provider VARCHAR(50),
    invoice_number INTEGER,
    series INTEGER,
    model VARCHAR(10),
    access_key VARCHAR(44),
    status VARCHAR(30) NOT NULL DEFAULT 'draft',
    total_products NUMERIC(14,2) NOT NULL DEFAULT 0,
    total_invoice NUMERIC(14,2) NOT NULL DEFAULT 0,
    xml_url TEXT,
    danfe_url TEXT,
    provider_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    error_message TEXT,
    issued_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (tenant_id, order_id) REFERENCES shop_orders(tenant_id, id) ON DELETE RESTRICT,
    UNIQUE (tenant_id, access_key),
    CHECK (total_products >= 0),
    CHECK (total_invoice >= 0)
);

CREATE TABLE IF NOT EXISTS logistics_shipments (
    id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    order_id VARCHAR(64),
    provider VARCHAR(50) NOT NULL DEFAULT 'melhor_envio',
    external_shipment_id VARCHAR(255),
    status VARCHAR(30) NOT NULL DEFAULT 'draft',
    service_name VARCHAR(255),
    tracking_code VARCHAR(100),
    quoted_amount NUMERIC(14,2),
    commission_amount NUMERIC(14,2),
    label_url TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (tenant_id, order_id) REFERENCES shop_orders(tenant_id, id) ON DELETE SET NULL,
    UNIQUE (tenant_id, provider, external_shipment_id),
    CHECK (quoted_amount IS NULL OR quoted_amount >= 0),
    CHECK (commission_amount IS NULL OR commission_amount >= 0)
);

CREATE TABLE IF NOT EXISTS webhook_events (
    id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    provider VARCHAR(50) NOT NULL,
    event_type VARCHAR(100) NOT NULL,
    external_event_id VARCHAR(255),
    signature VARCHAR(255),
    status VARCHAR(30) NOT NULL DEFAULT 'received',
    attempts INTEGER NOT NULL DEFAULT 0,
    payload JSONB NOT NULL,
    error_message TEXT,
    processed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (tenant_id, provider, external_event_id)
);

CREATE TABLE IF NOT EXISTS data_revisions (
    tenant_id VARCHAR(64) PRIMARY KEY REFERENCES tenants(id) ON DELETE CASCADE,
    revision BIGINT NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Índices de acesso por empresa e índices GIN apenas em dados realmente variáveis.
CREATE INDEX IF NOT EXISTS idx_members_tenant_active ON tenant_members(tenant_id, active);
CREATE INDEX IF NOT EXISTS idx_audit_logs_tenant_created ON audit_logs(tenant_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_nexus_clients_tenant_name ON nexus_clients(tenant_id, name);
CREATE INDEX IF NOT EXISTS idx_contact_points_tenant_value ON nexus_contact_points(tenant_id, normalized_value);
CREATE INDEX IF NOT EXISTS idx_stock_items_tenant_category ON stock_items(tenant_id, category_id);
CREATE INDEX IF NOT EXISTS idx_stock_items_tenant_family ON stock_items(tenant_id, family_id);
CREATE INDEX IF NOT EXISTS idx_stock_tier_prices_item ON stock_tier_prices(tenant_id, stock_item_id, min_quantity);
CREATE INDEX IF NOT EXISTS idx_shop_products_public ON shop_products(tenant_id, published, display_order);
CREATE INDEX IF NOT EXISTS idx_shop_orders_tenant_status ON shop_orders(tenant_id, status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_appointments_tenant_start ON agenda_appointments(tenant_id, starts_at);
CREATE INDEX IF NOT EXISTS idx_zap_conversations_tenant_recent ON zap_conversations(tenant_id, last_message_at DESC);
CREATE INDEX IF NOT EXISTS idx_zap_messages_conversation_time ON zap_messages(tenant_id, conversation_id, created_at);
CREATE INDEX IF NOT EXISTS idx_zap_queue_ready ON zap_message_queue(tenant_id, status, priority DESC, available_at);
CREATE INDEX IF NOT EXISTS idx_pay_charges_tenant_status ON pay_charges(tenant_id, status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_webhook_events_unprocessed ON webhook_events(tenant_id, provider, status, created_at);
CREATE INDEX IF NOT EXISTS idx_stock_attributes_gin ON stock_items USING GIN (attributes);
CREATE INDEX IF NOT EXISTS idx_webhook_payload_gin ON webhook_events USING GIN (payload);

DO $$
DECLARE table_name TEXT;
BEGIN
    FOREACH table_name IN ARRAY ARRAY[
        'tenants', 'users', 'tenant_members', 'stock_categories', 'stock_families',
        'stock_items', 'shop_configs', 'shop_products', 'shop_carts', 'shop_quotes',
        'shop_orders', 'agenda_services', 'agenda_appointments', 'zap_conversations',
        'zap_message_queue', 'integration_connections', 'pay_charges', 'fiscal_invoices',
        'logistics_shipments'
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
