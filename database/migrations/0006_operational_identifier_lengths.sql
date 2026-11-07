-- Produtos e referências legadas podem usar IDs descritivos maiores que 64.
-- Todos os campos relacionais correspondentes precisam aceitar o mesmo contrato.

ALTER TABLE nexus_clients ALTER COLUMN id TYPE VARCHAR(160);
ALTER TABLE nexus_contact_points ALTER COLUMN id TYPE VARCHAR(160);
ALTER TABLE nexus_contact_points ALTER COLUMN client_id TYPE VARCHAR(160);
ALTER TABLE nexus_client_tags ALTER COLUMN client_id TYPE VARCHAR(160);
ALTER TABLE nexus_client_merges ALTER COLUMN id TYPE VARCHAR(160);
ALTER TABLE nexus_client_merges ALTER COLUMN primary_client_id TYPE VARCHAR(160);
ALTER TABLE nexus_client_merges ALTER COLUMN merged_client_id TYPE VARCHAR(160);
ALTER TABLE nexus_client_events ALTER COLUMN client_id TYPE VARCHAR(160);

ALTER TABLE stock_categories ALTER COLUMN id TYPE VARCHAR(160);
ALTER TABLE stock_families ALTER COLUMN id TYPE VARCHAR(160);
ALTER TABLE stock_families ALTER COLUMN category_id TYPE VARCHAR(160);
ALTER TABLE stock_items ALTER COLUMN id TYPE VARCHAR(160);
ALTER TABLE stock_items ALTER COLUMN category_id TYPE VARCHAR(160);
ALTER TABLE stock_items ALTER COLUMN family_id TYPE VARCHAR(160);
ALTER TABLE stock_tier_prices ALTER COLUMN id TYPE VARCHAR(160);
ALTER TABLE stock_tier_prices ALTER COLUMN stock_item_id TYPE VARCHAR(160);
ALTER TABLE stock_movements ALTER COLUMN id TYPE VARCHAR(160);
ALTER TABLE stock_movements ALTER COLUMN stock_item_id TYPE VARCHAR(160);
ALTER TABLE stock_movements ALTER COLUMN reference_id TYPE VARCHAR(160);

ALTER TABLE shop_products ALTER COLUMN id TYPE VARCHAR(160);
ALTER TABLE shop_products ALTER COLUMN stock_item_id TYPE VARCHAR(160);
ALTER TABLE shop_products ALTER COLUMN stock_family_id TYPE VARCHAR(160);
ALTER TABLE shop_product_variants ALTER COLUMN id TYPE VARCHAR(160);
ALTER TABLE shop_product_variants ALTER COLUMN shop_product_id TYPE VARCHAR(160);
ALTER TABLE shop_product_variants ALTER COLUMN stock_item_id TYPE VARCHAR(160);
ALTER TABLE shop_carts ALTER COLUMN id TYPE VARCHAR(160);
ALTER TABLE shop_carts ALTER COLUMN client_id TYPE VARCHAR(160);
ALTER TABLE shop_cart_items ALTER COLUMN id TYPE VARCHAR(160);
ALTER TABLE shop_cart_items ALTER COLUMN cart_id TYPE VARCHAR(160);
ALTER TABLE shop_cart_items ALTER COLUMN stock_item_id TYPE VARCHAR(160);
ALTER TABLE shop_quotes ALTER COLUMN id TYPE VARCHAR(160);
ALTER TABLE shop_quotes ALTER COLUMN client_id TYPE VARCHAR(160);
ALTER TABLE shop_quote_items ALTER COLUMN id TYPE VARCHAR(160);
ALTER TABLE shop_quote_items ALTER COLUMN quote_id TYPE VARCHAR(160);
ALTER TABLE shop_quote_items ALTER COLUMN stock_item_id TYPE VARCHAR(160);
ALTER TABLE shop_orders ALTER COLUMN id TYPE VARCHAR(160);
ALTER TABLE shop_orders ALTER COLUMN quote_id TYPE VARCHAR(160);
ALTER TABLE shop_orders ALTER COLUMN client_id TYPE VARCHAR(160);
ALTER TABLE shop_order_items ALTER COLUMN id TYPE VARCHAR(160);
ALTER TABLE shop_order_items ALTER COLUMN order_id TYPE VARCHAR(160);
ALTER TABLE shop_order_items ALTER COLUMN stock_item_id TYPE VARCHAR(160);
ALTER TABLE shop_refunds ALTER COLUMN id TYPE VARCHAR(160);
ALTER TABLE shop_refunds ALTER COLUMN order_id TYPE VARCHAR(160);

ALTER TABLE pay_charges ALTER COLUMN id TYPE VARCHAR(160);
ALTER TABLE pay_charges ALTER COLUMN order_id TYPE VARCHAR(160);
ALTER TABLE pay_charges ALTER COLUMN client_id TYPE VARCHAR(160);
ALTER TABLE pay_transactions ALTER COLUMN id TYPE VARCHAR(160);
ALTER TABLE pay_transactions ALTER COLUMN charge_id TYPE VARCHAR(160);
ALTER TABLE fiscal_invoices ALTER COLUMN id TYPE VARCHAR(160);
ALTER TABLE fiscal_invoices ALTER COLUMN order_id TYPE VARCHAR(160);
ALTER TABLE logistics_shipments ALTER COLUMN id TYPE VARCHAR(160);
ALTER TABLE logistics_shipments ALTER COLUMN order_id TYPE VARCHAR(160);
ALTER TABLE zap_conversations ALTER COLUMN id TYPE VARCHAR(160);
ALTER TABLE zap_conversations ALTER COLUMN client_id TYPE VARCHAR(160);
ALTER TABLE zap_messages ALTER COLUMN id TYPE VARCHAR(160);
ALTER TABLE zap_messages ALTER COLUMN conversation_id TYPE VARCHAR(160);
ALTER TABLE zap_messages ALTER COLUMN client_id TYPE VARCHAR(160);
ALTER TABLE zap_message_queue ALTER COLUMN id TYPE VARCHAR(160);
ALTER TABLE zap_message_queue ALTER COLUMN conversation_id TYPE VARCHAR(160);
ALTER TABLE zap_message_queue ALTER COLUMN message_id TYPE VARCHAR(160);
