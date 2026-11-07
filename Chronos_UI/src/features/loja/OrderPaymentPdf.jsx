import { useState } from "react";
import { Download, Loader2 } from "lucide-react";
import { authFetch } from "../../auth";
import { SHOP_API_URL } from "../../shared/chronosConfig";

export default function OrderPaymentPdf({ tenant, order }) {
  const [busy, setBusy] = useState(false), [error, setError] = useState("");
  async function download() {
    if (busy) return;
    setBusy(true); setError("");
    try {
      const response = await authFetch(`${SHOP_API_URL}/shop/orders/${encodeURIComponent(order.id)}/payment-pdf?tenant_id=${encodeURIComponent(tenant)}`, { cache: "no-store" });
      if (!response.ok) { const data = await response.json().catch(() => ({})); throw new Error(typeof data.detail === "string" ? data.detail : "Não foi possível gerar o comprovante."); }
      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement("a"); link.href = url; link.download = `CHRONOS-comprovante-${order.id}.pdf`;
      document.body.append(link); link.click(); link.remove(); setTimeout(() => URL.revokeObjectURL(url), 60000);
    } catch (e) { setError(e.message); } finally { setBusy(false); }
  }
  return <div><button type="button" disabled={busy} onClick={download}>{busy ? <Loader2 size={16} className="is-spinning" /> : <Download size={16} />}{busy ? "Gerando comprovante..." : "Baixar comprovante (PDF)"}</button>{error && <p role="alert">{error}</p>}</div>;
}
