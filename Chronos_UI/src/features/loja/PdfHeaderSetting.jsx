import { useState } from "react";
import MobileDialog from "../../components/ui/MobileDialog";
import { CORE_API_URL, SHOP_API_URL } from "../../shared/chronosConfig";
import { jsonRequest, useResource } from "../experience/experienceData";
import "../nexus/registrationProfile.css";

export default function PdfHeaderSetting({ tenant, core = false }) {
  const [open, setOpen] = useState(false);
  return <><button type="button" onClick={() => setOpen(true)}>Cabeçalho dos PDFs</button>{open && <Editor key={tenant} tenant={tenant} core={core} onClose={() => setOpen(false)} />}</>;
}
function Editor({ tenant, core, onClose }) {
  const url = core ? `${CORE_API_URL}/core/tenants/${encodeURIComponent(tenant)}/pdf-header` : `${SHOP_API_URL}/shop/pdf-header?tenant_id=${encodeURIComponent(tenant)}`;
  const resource = useResource(url);
  const [edited, setEdited] = useState(null), [busy, setBusy] = useState(false), [error, setError] = useState("");
  const lines = edited || resource.data?.lines || ["", "", ""];
  async function save(event) {
    event.preventDefault(); if (busy) return;
    setBusy(true); setError("");
    try { await jsonRequest(url, "PUT", { lines }); onClose(); }
    catch (e) { setError(e.message); } finally { setBusy(false); }
  }
  return <MobileDialog title="Cabeçalho dos PDFs" onClose={() => { if (!busy) onClose(); }}><form className="registration-fields" onSubmit={save}>
    <p>Personalize as três linhas abaixo do nome da empresa nos PDFs de orçamento e comprovante de pagamento.</p>
    {(error || resource.error) && <p role="alert">{error || resource.error}</p>}
    {resource.loading ? <p>Carregando…</p> : <>
      {resource.data?.lines == null && <small>Você ainda usa os dados automáticos da empresa. Ao salvar, os textos abaixo substituem essas informações no cabeçalho.</small>}
      {lines.map((line, index) => <label key={index}>Linha {index + 1}<input maxLength={70} value={line} placeholder={["Nome da empresa", "Texto opcional", "Informações adicionais"][index]} onChange={e => setEdited(lines.map((value, i) => i === index ? e.target.value : value))} /></label>)}
      <small>Linhas vazias ficam sem texto. Logo, nome e cores da empresa são mantidos. Baixe o PDF novamente após salvar para ver a alteração.</small>
      <button type="submit" disabled={busy || !!resource.error}>{busy ? "Salvando…" : "Salvar cabeçalho"}</button>
    </>}
  </form></MobileDialog>;
}
