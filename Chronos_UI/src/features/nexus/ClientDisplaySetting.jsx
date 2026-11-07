import { useState } from "react";
import MobileDialog from "../../components/ui/MobileDialog";
import { CORE_API_URL, NEXUS_API_URL } from "../../shared/chronosConfig";
import { jsonRequest, useResource } from "../experience/experienceData";
import "./registrationProfile.css";

export default function ClientDisplaySetting({ tenant, core = false }) {
  const [open, setOpen] = useState(false);
  return <><button type="button" onClick={() => setOpen(true)}>Nome principal dos clientes</button>{open && <Editor key={tenant} tenant={tenant} core={core} onClose={() => setOpen(false)} />}</>;
}
function Editor({ tenant, core, onClose }) {
  const url = core ? `${CORE_API_URL}/core/tenants/${encodeURIComponent(tenant)}/client-display` : `${NEXUS_API_URL}/nexus/client-display?empresa_id=${encodeURIComponent(tenant)}`;
  const resource = useResource(url);
  const [mode, setMode] = useState(null), [busy, setBusy] = useState(false), [error, setError] = useState("");
  async function save(event) {
    event.preventDefault(); if (busy) return;
    setBusy(true); setError("");
    try { await jsonRequest(url, "PUT", { mode: mode || resource.data?.mode || "person" }); onClose(); }
    catch (e) { setError(e.message); } finally { setBusy(false); }
  }
  return <MobileDialog title="Nome principal dos clientes" onClose={() => { if (!busy) onClose(); }}><form className="registration-fields" onSubmit={save}>
    <p>Escolha o nome que aparece primeiro nos cadastros e seleções desta empresa.</p>
    {(error || resource.error) && <p role="alert">{error || resource.error}</p>}
    {resource.loading ? <p>Carregando…</p> : <><label>Exibir primeiro<select value={mode || resource.data?.mode || "person"} onChange={e => setMode(e.target.value)}><option value="person">Nome da pessoa (B2C)</option><option value="company">Nome da empresa (B2B)</option></select></label>
    <p>Se o nome escolhido estiver vazio, será utilizado o outro nome automaticamente. Os campos do cadastro continuam separados.</p>
    <small>Novos pedidos e orçamentos usam essa preferência. Documentos já gerados mantêm o nome registrado.</small>
    <button type="submit" disabled={busy || !!resource.error}>{busy ? "Salvando…" : "Salvar preferência"}</button></>}
  </form></MobileDialog>;
}
