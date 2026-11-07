-- Zap operational records not covered by the original unified schema.
CREATE TABLE IF NOT EXISTS zap_connection_events (
    id VARCHAR(160) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    status VARCHAR(30) NOT NULL,
    previous_status VARCHAR(30),
    connected_phone VARCHAR(50),
    last_error TEXT,
    occurred_at TIMESTAMPTZ NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (tenant_id, id)
);

CREATE TABLE IF NOT EXISTS zap_outbound_message_queue (
    id VARCHAR(160) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    kind VARCHAR(30) NOT NULL,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    status VARCHAR(30) NOT NULL DEFAULT 'PENDING',
    attempts INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 4,
    last_error TEXT,
    external_message_id VARCHAR(255),
    next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (tenant_id, id)
);

CREATE INDEX IF NOT EXISTS idx_zap_connection_events_recent
ON zap_connection_events(tenant_id, occurred_at DESC);

CREATE INDEX IF NOT EXISTS idx_zap_outbound_queue_due
ON zap_outbound_message_queue(tenant_id, status, next_attempt_at, created_at);
