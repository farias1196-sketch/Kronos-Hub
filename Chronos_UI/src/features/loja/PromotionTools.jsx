import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import MobileDialog from "../../components/ui/MobileDialog";
import { SHOP_API_URL } from "../../shared/chronosConfig";
import { jsonRequest, searchText, money } from "../experience/experienceData";
import "./promotions.css";
import "../nexus/registrationProfile.css";

export const promotionInvalid = product => Boolean(product?.promotion && (product.promotion.invalid || product.promotion.ends_on < new Intl.DateTimeFormat("en-CA", { timeZone: "America/Sao_Paulo", year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date())));
export const productOptionLabel = product => `${promotionInvalid(product) ? "Promoção inválida — " : ""}${product.public_name || product.family}`;
export const replacePromotion = (products, product) => [...products.filter(p => p.id !== product.id), product];

export default function PromotionTools({ tenant, products, product, variant, onPick, onSaved, hideSearch = false }) {
  const [search, setSearch] = useState("");
  const [editing, setEditing] = useState(null);
  useEffect(() => {
    if (!hideSearch && product?.promotion) {
      onPick(product);
      if (promotionInvalid(product)) setEditing(product);
    }
  }, [product?.id, product?.promotion?.revision, hideSearch]);
  const matches = search.trim() ? products.filter(p => p.promotion && searchText(p.public_name).includes(searchText(search))) : [];
  return <div className="promotion-tools">
    {!hideSearch && <label>Buscar promoção<input type="search" value={search} onChange={e => setSearch(e.target.value)} placeholder="Nome, tamanho ou quantidade" /></label>}
    {search.trim() && <div className="promotion-results">{matches.map(p => <button className={promotionInvalid(p) ? "promotion-invalid" : ""} type="button" key={p.id} onClick={() => { onPick(p); if (promotionInvalid(p)) setEditing(p); }}><strong>{productOptionLabel(p)}</strong><span>{p.promotion.package_quantity.toLocaleString("pt-BR")} unidades · {money(p.promotion.package_price)} · até {p.promotion.ends_on.split("-").reverse().join("/")}</span></button>)}{!matches.length && <small>Nenhuma promoção encontrada.</small>}</div>}
    {product?.promotion ? <div className={promotionInvalid(product) ? "promotion-invalid" : ""}><strong>{promotionInvalid(product) ? "Promoção inválida" : "Oferta promocional"}</strong><p>{product.promotion.package_quantity.toLocaleString("pt-BR")} unidades por {money(product.promotion.package_price)}. Validade: {product.promotion.ends_on.split("-").reverse().join("/")}.</p><button type="button" onClick={() => setEditing(product)}>{promotionInvalid(product) ? "Validar novamente" : "Editar valor / renovar"}</button></div> : variant && <button type="button" onClick={() => setEditing({ ...product, selectedVariant: variant })}>Criar promoção</button>}
    {editing && createPortal(<PromotionEditor key={editing.id} tenant={tenant} product={editing} onClose={() => setEditing(null)} onSaved={saved => { onSaved(saved); onPick(saved); setEditing(null); }} />, document.body)}
  </div>;
}

function PromotionEditor({ tenant, product, onClose, onSaved }) {
  const promotion = product.promotion;
  const [name, setName] = useState(`Promocional ${product.public_name || product.family} ${product.selectedVariant?.size || ""}`);
  const [quantity, setQuantity] = useState(String(promotion?.package_quantity || 1000));
  const [price, setPrice] = useState(String(promotion?.package_price || ""));
  const [busy, setBusy] = useState(false), [error, setError] = useState("");
  async function save(event) {
    event.preventDefault(); event.stopPropagation(); if (busy) return;
    setBusy(true); setError("");
    try {
      const url = `${SHOP_API_URL}/shop/promotions${promotion ? `/${encodeURIComponent(promotion.id)}/renew` : ""}?tenant_id=${encodeURIComponent(tenant)}`;
      const payload = promotion ? { package_price: Number(price) } : { product_id: product.id, stock_item_id: product.selectedVariant.stock_item_id, name: name.trim(), package_quantity: Number(quantity), package_price: Number(price) };
      const result = await jsonRequest(url, "POST", payload);
      if (!result.product) throw new Error("Produto original indisponível. Atualize o catálogo.");
      onSaved(result.product);
    } catch (e) { setError(e.message); } finally { setBusy(false); }
  }
  return <MobileDialog title={promotion ? "Validar promoção" : "Criar promoção"} onClose={() => { if (!busy) onClose(); }}><form className="registration-fields" onSubmit={save}>
    {promotion ? <><p>Deseja tornar esta promoção válida novamente?</p><strong>{product.public_name}</strong><p>{promotion.package_quantity.toLocaleString("pt-BR")} unidades por pacote. Mantenha o valor ou informe o valor correto abaixo.</p></> : <><label>Nome da promoção<input required maxLength={200} value={name} onChange={e => setName(e.target.value)} /></label><label>Unidades por pacote<input type="number" required min="1" step="1" value={quantity} onChange={e => setQuantity(e.target.value)} /></label></>}
    <label>Valor do pacote (R$)<input required type="number" min="0.01" step="0.01" inputMode="decimal" value={price} onChange={e => setPrice(e.target.value)} /></label>
    <p>Validade de um mês a partir de hoje. Pedidos e orçamentos anteriores mantêm os valores registrados.</p>
    {error && <p role="alert">{error}</p>}
    <button type="submit" disabled={busy}>{busy ? "Salvando..." : promotion ? "Confirmar e validar por um mês" : "Criar promoção por um mês"}</button>
    <button type="button" disabled={busy} onClick={onClose}>Cancelar</button>
  </form></MobileDialog>;
}
