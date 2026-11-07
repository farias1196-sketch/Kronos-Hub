import { useState } from "react";
import { createPortal } from "react-dom";
import MobileDialog from "../../components/ui/MobileDialog";
import { SHOP_API_URL } from "../../shared/chronosConfig";
import { shopPrice, saleMoney } from "../../shared/shopPrices";
import { jsonRequest } from "../experience/experienceData";
import "../nexus/registrationProfile.css";

export function CreateProductExtra({ tenant, productId, stockItemId, onCreated }) {
  const [family, setFamily] = useState(false);
  const [open, setOpen] = useState(false);
  const [description, setDescription] = useState("");
  const [amount, setAmount] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function save(event) {
    event.preventDefault(); event.stopPropagation();
    if (busy) return;
    setBusy(true); setError("");
    try {
      const result = await jsonRequest(`${SHOP_API_URL}/shop/products/${encodeURIComponent(productId)}/extras?tenant_id=${encodeURIComponent(tenant)}`, "POST", { description: description.trim(), unit_price: Number(amount), stock_item_id: stockItemId, apply_to_family: family });
      onCreated(result.extra); setOpen(false); setDescription(""); setAmount("");
    } catch (e) { setError(e.message); } finally { setBusy(false); }
  }
  return <><button type="button" onClick={() => { setError(""); setOpen(true); }}>Cadastrar adicional</button>{open && createPortal(<MobileDialog title="Cadastrar adicional do produto" onClose={() => { if (!busy) setOpen(false); }}><form className="registration-fields" onSubmit={save}>
    <p>O adicional ficará salvo para usar novamente nos próximos orçamentos desta empresa.</p>
    <label>Descrição do adicional<input required maxLength={200} value={description} onChange={e => setDescription(e.target.value)} /></label>
    <label>Valor adicional por unidade (R$)<input required type="number" min="0.0001" step="0.0001" inputMode="decimal" value={amount} onChange={e => setAmount(e.target.value)} /></label>
    <label className="registration-check"><input type="checkbox" checked={family} onChange={e => setFamily(e.target.checked)} />Aplicar à família inteira</label>
    <small>Desmarcado: somente esta variação. Marcado: todas as variações desta família.</small>
    <small>O valor será multiplicado pela quantidade do item.</small>
    {error && <p role="alert">{error}</p>}
    <button type="submit" disabled={busy || !description.trim()}>{busy ? "Salvando..." : "Salvar e selecionar adicional"}</button>
  </form></MobileDialog>, document.body)}</>;
}

export function ProductExtras({ tenant, productId, variant, quantity, selected, onChange, onCreated }) {
  if (!variant) return null;
  const options = variant.registered_extras || [];
  const toggle = option => onChange(selected.includes(option.id) ? selected.filter(id => id !== option.id) : [...selected.filter(id => option.group !== "color" || !options.some(item => item.id === id && item.group === "color")), option.id]);
  return <fieldset className="registration-fields"><legend>Adicionais do produto</legend>{options.map(option => {
    const price = shopPrice(option, quantity);
    return <label className="registration-check" key={option.id}><input type="checkbox" checked={selected.includes(option.id)} disabled={!selected.includes(option.id) && (!price.eligible || option.on_request)} onChange={() => toggle(option)} />{option.description} · {option.on_request ? "Sob consulta" : price.eligible ? `${saleMoney(price.price)} / unidade` : `A partir de ${price.minimum} unidades`}</label>;
  })}<CreateProductExtra tenant={tenant} productId={productId} stockItemId={variant.stock_item_id} onCreated={extra => { onCreated(extra); onChange([...new Set([...selected, extra.id])]); }} /></fieldset>;
}

export const withProductExtra = (products, productId, extra) => products.map(product => product.id !== productId ? product : { ...product, variants: product.variants.map(variant => extra.stock_item_id && String(variant.stock_item_id) !== extra.stock_item_id ? variant : ({ ...variant, registered_extras: [...(variant.registered_extras || []).filter(item => item.id !== extra.id), extra] })) });
