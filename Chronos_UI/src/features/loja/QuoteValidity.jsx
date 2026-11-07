import { useState } from "react";
import MobileDialog from "../../components/ui/MobileDialog";
import { CORE_API_URL, SHOP_API_URL } from "../../shared/chronosConfig";
import { jsonRequest, useResource } from "../experience/experienceData";
import "../nexus/registrationProfile.css";

export default function QuoteValidity({ tenant, core = false }) {
  const [open, setOpen] = useState(false);
  return <><button type="button" onClick={() => setOpen(true)}>Validade dos orçamentos</button>{open && <Editor key={tenant} tenant={tenant} core={core} onClose={() => setOpen(false)} />}</>;
}
function Editor({ tenant, core, onClose }) {
  const url = core ? `${CORE_API_URL}/core/tenants/${encodeURIComponent(tenant)}/quote-validity` : `${SHOP_API_URL}/shop/quote-validity?tenant_id=${encodeURIComponent(tenant)}`;
  const resource = useResource(url);
  const [edited, setEdited] = useState(null), [busy, setBusy] = useState(false), [error, setError] = useState("");
  const value = edited || resource.data || { mode: "days", days: 7, text: "" };
  async function save(event) {
    event.preventDefault(); if (busy) return; setBusy(true); setError("");
    try { await jsonRequest(url, "PUT", { ...value, days: Number(value.days) }); onClose(); } catch (e) { setError(e.message); } finally { setBusy(false); }
  }
  return <MobileDialog title="Validade dos orçamentos" onClose={() => { if (!busy) onClose(); }}><form className="registration-fields" onSubmit={save}>
    <p>Configuração da empresa para novos orçamentos. Orçamentos já emitidos mantêm a validade original.</p>
    {(error || resource.error) && <p role="alert">{error || resource.error}</p>}
    {resource.loading ? <p>Carregando...</p> : <><label>Tipo de validade<select value={value.mode} onChange={e => setEdited({ ...value, mode: e.target.value })}><option value="days">Quantidade de dias</option><option value="text">Texto personalizado</option></select></label>
    {value.mode === "days" ? <label>Validade em dias<input required type="number" min="1" max="365" step="1" value={value.days} onChange={e => setEdited({ ...value, days: e.target.value })} /></label> : <label>Texto da validade<textarea required maxLength={300} rows={4} value={value.text} placeholder="Orçamento válido enquanto durarem os estoques" onChange={e => setEdited({ ...value, text: e.target.value })} /></label>}
    <small>O texto personalizado substitui o prazo automático em dias. Ofertas promocionais continuam limitadas à data de término da promoção.</small>
    <button type="submit" disabled={busy || !!resource.error}>{busy ? "Salvando..." : "Salvar validade"}</button></>}
  </form></MobileDialog>;
}
