import { useState } from "react";
import MobileDialog from "../../components/ui/MobileDialog";
import { SHOP_API_URL } from "../../shared/chronosConfig";
import { jsonRequest, useResource } from "../experience/experienceData";
import "../nexus/registrationProfile.css";

export const orderLabel = order => order.order_number != null ? `${order.order_prefix || ""}${order.order_number}` : order.id;

export function OrderNumberingButton({ tenant }) {
  const [open, setOpen] = useState(false);
  return <><button type="button" onClick={() => setOpen(true)}>Numeração dos pedidos</button>{open && <NumberingEditor key={tenant} tenant={tenant} onClose={() => setOpen(false)} />}</>;
}

function NumberingEditor({ tenant, onClose }) {
  const url = `${SHOP_API_URL}/shop/order-numbering?tenant_id=${encodeURIComponent(tenant)}`;
  const resource = useResource(url);
  const [edited, setEdited] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const config = edited || resource.data || { prefix: "", last_number: 0 };
  async function save(event) {
    event.preventDefault();
    if (busy) return;
    setBusy(true); setError("");
    try {
      await jsonRequest(url, "PUT", { prefix: config.prefix, last_number: Number(config.last_number) });
      onClose();
    } catch (e) { setError(e.message); } finally { setBusy(false); }
  }
  return <MobileDialog title="Numeração dos pedidos" onClose={() => { if (!busy) onClose(); }}>
    <form className="registration-fields" onSubmit={save}>
      <p>Defina a sequência desta empresa. Ela será usada nos novos pedidos do CHRONOS Fácil e da Loja.</p>
      {(error || resource.error) && <p role="alert">{error || resource.error}</p>}
      {resource.loading ? <p>Carregando...</p> : <>
        <label>Texto antes do número<input maxLength={40} placeholder="Ex.: PED-" value={config.prefix} onChange={e => setEdited({ ...config, prefix: e.target.value })} /></label>
        <label>Último número utilizado<input required type="number" inputMode="numeric" min={resource.data?.last_number || 0} max={2147483646} step={1} value={config.last_number} onChange={e => setEdited({ ...config, last_number: e.target.value })} /></label>
        <p aria-live="polite">Próximos pedidos: {[1, 2, 3].map(offset => `${config.prefix}${Number(config.last_number) + offset}`).join(", ")}</p>
        <small>Os pedidos existentes e a numeração dos orçamentos permanecem iguais.</small>
        <button type="submit" disabled={busy || !!resource.error}>{busy ? "Salvando..." : "Salvar numeração"}</button>
      </>}
    </form>
  </MobileDialog>;
}
