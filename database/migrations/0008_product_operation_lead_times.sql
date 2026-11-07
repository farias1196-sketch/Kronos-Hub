-- Lead times per sellable item. Zero means the respective stage does not exist.
ALTER TABLE stock_items
    ADD COLUMN IF NOT EXISTS art_lead_days SMALLINT NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS production_lead_days SMALLINT NOT NULL DEFAULT 0;

ALTER TABLE stock_items
    DROP CONSTRAINT IF EXISTS stock_items_art_lead_days_check,
    DROP CONSTRAINT IF EXISTS stock_items_production_lead_days_check;

ALTER TABLE stock_items
    ADD CONSTRAINT stock_items_art_lead_days_check CHECK (art_lead_days BETWEEN 0 AND 365),
    ADD CONSTRAINT stock_items_production_lead_days_check CHECK (production_lead_days BETWEEN 0 AND 365);
