const currency = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL", minimumFractionDigits: 2, maximumFractionDigits: 4 });
export const saleMoney = (value) => currency.format(value);

export function quantityTiers(variant) {
  const tiers = new Map();
  for (const item of variant?.quantity_prices || []) {
    const minimum = Number(item.minimum_quantity), price = Number(item.unit_price);
    if (Number.isFinite(minimum) && minimum > 0 && Number.isFinite(price) && price >= 0) tiers.set(minimum, price);
  }
  return [...tiers].sort(([a], [b]) => a - b).map(([minimum_quantity, unit_price]) => ({ minimum_quantity, unit_price }));
}

// Same precedence as Loja's resolve_variant_price; the server calculates the final order.
export function shopPrice(variant, quantity) {
  if (variant?.promotion) {
    const p = variant.promotion, count = quantity === undefined ? p.package_quantity : Number(quantity);
    return { minimum: p.package_quantity, price: p.package_price / p.package_quantity, eligible: !p.invalid && count > 0 && count % p.package_quantity === 0 };
  }
  const tiers = quantityTiers(variant);
  const minimum = tiers[0]?.minimum_quantity || 0;
  const count = quantity === undefined ? (minimum || 1) : Number(quantity);
  const tier = tiers.findLast((item) => count >= item.minimum_quantity);
  const promotion = Number(variant?.promotional_price);
  const price = promotion > 0 ? promotion : tiers.length ? tier?.unit_price : Number(variant?.sale_price);
  return { minimum, price: Number.isFinite(price) && price > 0 ? price : null, eligible: count > 0 && count >= minimum && Number.isFinite(price) && price > 0 };
}

export function shopPriceLabel(variant, quantity) {
  if (variant?.promotion) return `${variant.promotion.invalid ? "Promoção inválida · " : ""}${saleMoney(variant.promotion.package_price)} / pacote de ${variant.promotion.package_quantity} unidades`;
  const { price, minimum } = shopPrice(variant, quantity);
  if (quantity !== undefined && Number(quantity) < minimum) return `Mínimo de ${minimum.toLocaleString("pt-BR")} ${variant.unit || "UN"}`;
  if (price === null) return "Preço não cadastrado na Loja";
  return `${saleMoney(price)} / ${variant.unit || "UN"}${quantity === undefined && minimum ? ` · a partir de ${minimum.toLocaleString("pt-BR")} ${variant.unit || "UN"}` : ""}`;
}
