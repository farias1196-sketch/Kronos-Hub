import React, { useRef, useState } from "react";
import { Download, FileSpreadsheet, Loader2, RefreshCw, Upload } from "lucide-react";
import { authFetch } from "../../auth";
import { STOCK_API_URL } from "../../shared/chronosConfig";

function saveResponseAsFile(response, fallbackName) {
  return response.blob().then((blob) => {
    const contentDisposition = response.headers.get("Content-Disposition") || "";
    const filename = contentDisposition.match(/filename="?([^";]+)"?/i)?.[1] || fallbackName;
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = filename;
    anchor.click();
    URL.revokeObjectURL(url);
  });
}

export default function StockImportExportPanel({ tenantId, onImported }) {
  const fileInputRef = useRef(null);
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState(null);
  const [status, setStatus] = useState("");
  const [isBusy, setIsBusy] = useState(false);
  const downloadLock = useRef(false);
  const [downloading, setDownloading] = useState(null);
  const [downloadStatus, setDownloadStatus] = useState("");
  const [duplicateStrategy, setDuplicateStrategy] = useState("skip");

  async function download(endpoint, filename) {
    if (downloadLock.current) return;
    downloadLock.current = true;
    setDownloading(endpoint);
    setDownloadStatus("Preparando o CSV. Aguarde, o download começará automaticamente.");
    try {
      const response = await authFetch(`${STOCK_API_URL}${endpoint}?tenant_id=${encodeURIComponent(tenantId)}`);
      if (!response.ok) {
        const data = await response.json().catch(() => null);
        throw new Error(typeof data?.detail === "string" ? data.detail : "Não foi possível gerar o arquivo. Tente novamente.");
      }
      await saveResponseAsFile(response, filename);
      setDownloadStatus("Arquivo gerado. Download iniciado.");
    } catch (error) {
      setDownloadStatus(error.message || "Não foi possível baixar o arquivo. Tente novamente.");
    } finally {
      downloadLock.current = false;
      setDownloading(null);
    }
  }

  async function createPreview() {
    if (!file) {
      setStatus("Selecione um CSV antes de validar.");
      return;
    }
    setIsBusy(true);
    setStatus("Lendo e validando o CSV...");
    setPreview(null);
    try {
      const body = new FormData();
      body.append("file", file);
      body.append("tenant_id", tenantId);
      const response = await authFetch(`${STOCK_API_URL}/stock/import-export/preview?tenant_id=${encodeURIComponent(tenantId)}`, {
        method: "POST",
        body,
      });
      const data = await response.json();
      if (!response.ok || !data.ok) throw new Error(data.detail || "Nao foi possivel validar o arquivo.");
      setPreview(data);
      setStatus(data.summary.errors ? "Foram encontrados erros no arquivo." : "Previa pronta para confirmacao.");
    } catch (error) {
      setStatus(error.message || "Nao foi possivel validar o arquivo.");
    } finally {
      setIsBusy(false);
    }
  }

  async function commitImport() {
    if (!preview?.preview_id || preview.summary.errors) return;
    setIsBusy(true);
    setStatus("Importando produtos...");
    try {
      const response = await authFetch(`${STOCK_API_URL}/stock/import-export/commit`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tenant_id: tenantId, preview_id: preview.preview_id, duplicate_strategy: duplicateStrategy }),
      });
      const data = await response.json();
      if (!response.ok || !data.ok) throw new Error(data.detail || "Nao foi possivel importar o arquivo.");
      setStatus(`${data.created} criado(s), ${data.updated} atualizado(s), ${data.skipped} ignorado(s) e ${data.shop_updated || 0} preço(s), ${data.extras_updated || 0} adicional(is)/acabamento(s) e ${data.promotions_updated || 0} promoção(ões) da Loja atualizado(s). ${data.warning || ""}`);
      setPreview(null);
      setFile(null);
      if (fileInputRef.current) fileInputRef.current.value = "";
      onImported?.();
    } catch (error) {
      setStatus(error.message || "Nao foi possivel importar o arquivo.");
    } finally {
      setIsBusy(false);
    }
  }

  return (
    <main className="stock-import-export">
      <section className="stock-import-card">
        <header>
          <div>
            <FileSpreadsheet size={22} />
            <strong>Planilha mestre do estoque</strong>
          </div>
          <span>Stock e Loja em um único CSV.</span>
        </header>
        <p>Baixe o modelo para cadastrar muitos produtos de uma vez. Células customizadas vazias significam que aquele atributo não se aplica ao item.</p>
        <div className="stock-import-actions">
          <button type="button" disabled={!!downloading} aria-busy={downloading === "/stock/import-export/template"} onClick={() => download("/stock/import-export/template", "chronos-stock-modelo.csv")}>
            {downloading === "/stock/import-export/template" ? <Loader2 size={16} className="is-spinning" aria-hidden="true" /> : <Download size={16} />}
            {downloading === "/stock/import-export/template" ? "Gerando modelo..." : "Baixar modelo CSV"}
          </button>
          <button type="button" disabled={!!downloading} aria-busy={downloading === "/stock/import-export/products"} onClick={() => download("/stock/import-export/products", "chronos-stock-produtos.csv")}>
            {downloading === "/stock/import-export/products" ? <Loader2 size={16} className="is-spinning" aria-hidden="true" /> : <Download size={16} />}
            {downloading === "/stock/import-export/products" ? "Gerando exportação..." : "Exportar estoque atual"}
          </button>
        </div>
        {downloadStatus && <small className="stock-import-status" role="status">{downloadStatus}</small>}
        <small>Acabamentos: separe os tipos com |. Faixas de quantidade: 100:2,3456 | 200:2,10. Preço promocional vazio remove somente o desconto direto da variação; faixas vazias removem as faixas. Preserve loja_produto_id para atualizar a Loja.</small>
        <small>O arquivo reúne produtos, acabamentos, adicionais e promoções em linhas identificadas pela coluna registro. Cada promoção tem sua própria linha, preço do pacote e validade. Preserve os identificadores e registro_versao. Excluir uma linha do arquivo não apaga o cadastro.</small>
      </section>

      <section className="stock-import-card">
        <header>
          <div>
            <Upload size={22} />
            <strong>Importar CSV</strong>
          </div>
          <span>Primeiro valida, depois grava.</span>
        </header>
        <label className="stock-import-file">
          <input ref={fileInputRef} type="file" accept=".csv,text/csv" onChange={(event) => setFile(event.target.files?.[0] || null)} />
          <span>{file ? file.name : "Selecionar arquivo CSV"}</span>
          <Upload size={16} />
        </label>
        <div className="stock-import-actions">
          <button type="button" className="primary" onClick={createPreview} disabled={isBusy || !file}>
            {isBusy ? <Loader2 size={16} className="is-spinning" /> : <RefreshCw size={16} />}
            Validar arquivo
          </button>
        </div>
        {status && <small className="stock-import-status">{status}</small>}
      </section>

      {preview && (
        <section className="stock-import-preview">
          <header>
            <div>
              <strong>Conferência da importação</strong>
              <span>A prévia expira em {preview.expires_in_minutes} minutos.</span>
            </div>
            <div className="stock-import-summary">
              <b>{preview.summary.ready}<small>prontos</small></b>
              <b className={preview.summary.errors ? "danger" : ""}>{preview.summary.errors}<small>erros</small></b>
              <b>{preview.summary.duplicates}<small>SKUs já existentes</small></b>
            </div>
          </header>
          {preview.errors.length > 0 && (
            <div className="stock-import-errors">
              {preview.errors.map((error) => <p key={`${error.row}-${error.message}`}><b>Linha {error.row}:</b> {error.message}</p>)}
            </div>
          )}
          <p>{preview.summary.shop_updates || 0} variação(ões) com preços da Loja, {preview.summary.extra_updates || 0} adicional(is)/acabamento(s) e {preview.summary.promotion_updates || 0} promoção(ões). Para aplicar correções nos SKUs existentes, selecione “Atualizar produtos pelo SKU”.</p>
          {preview.rows?.length > 0 && <details><summary>Conferir produtos (até 50 linhas)</summary>{preview.rows.map(row => <article key={row.row} style={{ padding: "12px 0", borderBottom: "1px solid var(--chronos-border)", overflowWrap: "anywhere" }}><strong>{row.sku} · {row.name}</strong><p>Custo: {row.cost_price} · Acabamentos: {(row.finishes || []).join(", ") || "Nenhum"}</p>{row.shop_prices && <p>Venda: {row.shop_prices.sale_price} · Promoção: {row.shop_prices.promotional_price ?? "Nenhuma"} · Faixas: {row.shop_prices.quantity_prices.map(tier => `${tier.minimum_quantity}: ${tier.unit_price}`).join(" | ") || "Nenhuma"}</p>}</article>)}</details>}
          {!preview.summary.errors && (
            <footer>
              {(preview.summary.duplicates > 0 || preview.summary.extra_updates > 0 || preview.summary.promotion_updates > 0) && (
                <label>
                  SKUs existentes
                  <select value={duplicateStrategy} onChange={(event) => setDuplicateStrategy(event.target.value)}>
                    <option value="skip">Ignorar linhas já cadastradas</option>
                    <option value="update">Atualizar produtos pelo SKU</option>
                  </select>
                </label>
              )}
              <button type="button" className="primary" onClick={commitImport} disabled={isBusy || preview.summary.ready === 0}>
                {isBusy ? <Loader2 size={16} className="is-spinning" /> : <Upload size={16} />}
                Confirmar importação
              </button>
            </footer>
          )}
        </section>
      )}
    </main>
  );
}
