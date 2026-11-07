import OrderPaymentPdf from "./OrderPaymentPdf";
import PromotionTools, { productOptionLabel, replacePromotion } from "./PromotionTools";
import { ProductExtras, withProductExtra } from "./ProductExtras";
import { OrderNumberingButton, orderLabel } from "./OrderNumbering";
import { useEffect, useState } from "react";
import {
  Archive, CheckCircle2, CircleAlert, CreditCard, Download, FileText, Image, Loader2, Minus, Package,
  Pencil, Plus, Search, Settings, ShoppingBag, ShoppingCart, Store, Trash2, X,
} from "lucide-react";
import { authFetch } from "../../auth";
import {
  DEFAULT_CORE_TENANT_SLUG, LOJA_PATH, MEDIA_API_URL, PROMO_API_URL, SHOP_API_URL, STOCK_API_URL,
} from "../../shared/chronosConfig";
import { formatMoney } from "../core/coreUtils";

import AuthenticatedImage from "../../AuthenticatedImage";
import MobileActionPanel from "../../components/ui/MobileActionPanel";
import MobileDialog from "../../components/ui/MobileDialog";
import "./lojaMobile.css";

export default function LojaPage({ currentTenantSlug, currentTenant, mobile = false }) {
  const [mobileAction, setMobileAction] = useState(null);
  const [config, setConfig] = useState(null);
  const [products, setProducts] = useState([]);
  const [carts, setCarts] = useState([]);
  const [quotes, setQuotes] = useState([]);
  const [orders, setOrders] = useState([]);
  const [transactions, setTransactions] = useState([]);
  const [refunds, setRefunds] = useState([]);
  const [activeTab, setActiveTab] = useState(mobile ? "products" : "domain");
  const [status, setStatus] = useState("Carregando loja...");
  const [mediaStatus, setMediaStatus] = useState(null);
  const [isSaving, setIsSaving] = useState(false);
  const [editingProductId, setEditingProductId] = useState(null);
  const [cartForm, setCartForm] = useState({ client_name: "", client_phone: "", source: "flow" });
  const [cartItemForm, setCartItemForm] = useState({ cart_id: "", product_id: "", stock_item_id: "", quantity: "1", extra_ids: [] });
  const [cartTotalsForm, setCartTotalsForm] = useState({ discount: "0", freight: "0", notes: "" });
  const [paymentForm, setPaymentForm] = useState({ order_id: "", amount: "", method: "manual", reference: "" });
  const [refundForm, setRefundForm] = useState({ order_id: "", amount: "", reason: "" });

  const tenantId = currentTenantSlug || DEFAULT_CORE_TENANT_SLUG;
  const publicUrl = window.location.origin + LOJA_PATH + "/" + encodeURIComponent(config?.chronos_slug || tenantId);

  async function loadLoja() {
    setStatus("Carregando loja...");
    try {
      const [configResponse, productsResponse] = await Promise.all([
        authFetch(`${SHOP_API_URL}/shop/config?tenant_id=${encodeURIComponent(tenantId)}`),
        authFetch(`${SHOP_API_URL}/shop/products?tenant_id=${encodeURIComponent(tenantId)}`),
      ]);
      const configData = await configResponse.json();
      const productsData = await productsResponse.json();
      if (!configResponse.ok) throw new Error(configData.detail || "Nao foi possivel carregar configuracao.");
      if (!productsResponse.ok) throw new Error(productsData.detail || "Nao foi possivel carregar produtos.");
      setConfig(configData.config);
      setProducts(productsData.products || []);
      setStatus("Loja carregada.");
    } catch (error) {
      setConfig(null);
      setProducts([]);
      setStatus(error.message || "Loja API indisponivel.");
    }
  }

  async function loadCommercial() {
    try {
      const [cartsResponse, quotesResponse, ordersResponse, transactionsResponse, refundsResponse] = await Promise.all([
        authFetch(`${SHOP_API_URL}/shop/carts?tenant_id=${encodeURIComponent(tenantId)}`),
        authFetch(`${SHOP_API_URL}/shop/quotes?tenant_id=${encodeURIComponent(tenantId)}`),
        authFetch(`${SHOP_API_URL}/shop/orders?tenant_id=${encodeURIComponent(tenantId)}`),
        authFetch(`${SHOP_API_URL}/shop/transactions?tenant_id=${encodeURIComponent(tenantId)}`),
        authFetch(`${SHOP_API_URL}/shop/refunds?tenant_id=${encodeURIComponent(tenantId)}`),
      ]);
      const cartsData = await cartsResponse.json();
      const quotesData = await quotesResponse.json();
      const ordersData = await ordersResponse.json();
      const transactionsData = await transactionsResponse.json();
      const refundsData = await refundsResponse.json();
      setCarts(cartsData.carts || []);
      setQuotes(quotesData.quotes || []);
      setOrders(ordersData.orders || []);
      setTransactions(transactionsData.transactions || []);
      setRefunds(refundsData.refunds || []);
      setCartItemForm((current) => ({ ...current, cart_id: current.cart_id || (cartsData.carts || [])[0]?.id || "" }));
      setPaymentForm((current) => ({ ...current, order_id: current.order_id || (ordersData.orders || [])[0]?.id || "" }));
      setRefundForm((current) => ({ ...current, order_id: current.order_id || (ordersData.orders || [])[0]?.id || "" }));
    } catch {
      setCarts([]);
      setQuotes([]);
      setOrders([]);
      setTransactions([]);
      setRefunds([]);
    }
  }

  async function loadMediaStatus() {
    try {
      const [storageResponse, summaryResponse] = await Promise.all([
        authFetch(`${MEDIA_API_URL}/media/storage-status`),
        authFetch(`${MEDIA_API_URL}/media/summary?tenant_id=${encodeURIComponent(tenantId)}`),
      ]);
      const storageData = await storageResponse.json();
      const summaryData = await summaryResponse.json();
      if (!storageResponse.ok || !summaryResponse.ok) throw new Error("Armazenamento indisponível.");
      setMediaStatus({ storage: storageData, summary: summaryData });
    } catch {
      setMediaStatus({ error: "Chronos Media indisponivel." });
    }
  }

  useEffect(() => {
    loadLoja().catch(() => undefined);
    loadCommercial().catch(() => undefined);
    loadMediaStatus().catch(() => undefined);
  }, [tenantId]);

  function updateConfig(field, value) {
    setConfig((currentConfig) => ({ ...(currentConfig || {}), tenant_id: tenantId, [field]: value }));
  }

  function updateProductVariantPrice(productId, stockItemId, field, value) {
    setProducts((currentProducts) =>
      currentProducts.map((product) => {
        if (product.id !== productId) return product;
        const variantPrices = product.variant_prices || {};
        const currentVariant = variantPrices[stockItemId] || {};
        return {
          ...product,
          variant_prices: {
            ...variantPrices,
            [stockItemId]: {
              sale_price: currentVariant.sale_price || 0,
              promotional_price: currentVariant.promotional_price || 0,
              quantity_prices: currentVariant.quantity_prices || [],
              sellable: currentVariant.sellable ?? true,
              ...currentVariant,
              [field]: field === "sellable" ? value : field === "quantity_prices" ? value : Number(value) || 0,
            },
          },
          variants: (product.variants || []).map((variant) =>
            String(variant.stock_item_id) === String(stockItemId)
              ? {
                  ...variant,
                  [field]: field === "sellable" ? value : field === "quantity_prices" ? value : Number(value) || 0,
                }
              : variant
          ),
        };
      })
    );
  }

  function updateQuantityPriceTier(productId, stockItemId, tierIndex, field, value) {
    const product = products.find((item) => item.id === productId);
    const variant = product?.variants?.find((item) => String(item.stock_item_id) === String(stockItemId));
    const tiers = [...(variant?.quantity_prices || [])];
    if (!tiers[tierIndex]) return;
    tiers[tierIndex] = { ...tiers[tierIndex], [field]: Number(value) || 0 };
    updateProductVariantPrice(productId, stockItemId, "quantity_prices", tiers);
  }

  function addQuantityPriceTier(productId, stockItemId) {
    const product = products.find((item) => item.id === productId);
    const variant = product?.variants?.find((item) => String(item.stock_item_id) === String(stockItemId));
    const tiers = [...(variant?.quantity_prices || [])];
    const lastMinimum = Math.max(0, ...tiers.map((tier) => Number(tier.minimum_quantity) || 0));
    updateProductVariantPrice(productId, stockItemId, "quantity_prices", [...tiers, { minimum_quantity: lastMinimum ? lastMinimum + 1 : 1, unit_price: 0 }]);
  }

  function removeQuantityPriceTier(productId, stockItemId, tierIndex) {
    const product = products.find((item) => item.id === productId);
    const variant = product?.variants?.find((item) => String(item.stock_item_id) === String(stockItemId));
    updateProductVariantPrice(productId, stockItemId, "quantity_prices", (variant?.quantity_prices || []).filter((_, index) => index !== tierIndex));
  }

  function variantPriceLabel(variant) {
    if (variant?.promotion) return `${formatMoney(variant.promotion.package_price)} / pacote de ${variant.promotion.package_quantity} unidades`;
    const tiers = [...(variant?.quantity_prices || [])].sort((left, right) => Number(left.minimum_quantity) - Number(right.minimum_quantity));
    if (tiers.length) return `A partir de ${formatMoney(tiers[0].unit_price || 0)} em ${tiers[0].minimum_quantity}+`;
    return formatMoney(variant?.promotional_price || variant?.sale_price || 0);
  }

  function quantityPricePreview(variant, rawQuantity) {
    const quantity = Number(rawQuantity) || 0;
    const tiers = [...(variant?.quantity_prices || [])].sort((left, right) => Number(left.minimum_quantity) - Number(right.minimum_quantity));
    if (!tiers.length) return variantPriceLabel(variant);
    if (quantity < Number(tiers[0].minimum_quantity)) return `Minimo: ${tiers[0].minimum_quantity} ${variant?.unit || "UN"}`;
    const appliedTier = [...tiers].reverse().find((tier) => quantity >= Number(tier.minimum_quantity));
    const unitPrice = Number(variant?.promotional_price) > 0 ? variant.promotional_price : appliedTier?.unit_price;
    return `${formatMoney(unitPrice || 0)} por ${variant?.unit || "UN"}`;
  }

  async function saveConfig(event) {
    event.preventDefault();
    if (!config) return;
    setIsSaving(true);
    setStatus("Salvando configuracao...");
    try {
      const response = await authFetch(`${SHOP_API_URL}/shop/config`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...config, tenant_id: tenantId }),
      });
      const data = await response.json();
      if (!response.ok || !data.ok) throw new Error(data.detail || "Nao foi possivel salvar configuracao.");
      setConfig(data.config);
      setStatus("Configuracao da loja salva.");
    } catch (error) {
      setStatus(error.message || "Nao foi possivel salvar configuracao.");
    } finally {
      setIsSaving(false);
    }
  }

  async function importProducts() {
    setIsSaving(true);
    setStatus("Sincronizando produtos do estoque...");
    try {
      const response = await authFetch(`${SHOP_API_URL}/shop/products/import-from-stock?tenant_id=${encodeURIComponent(tenantId)}`, { method: "POST" });
      const data = await response.json();
      if (!response.ok || !data.ok) throw new Error(data.detail || "Nao foi possivel sincronizar produtos.");
      setProducts(data.products || []);
      setStatus(`${data.imported || 0} familia(s) nova(s) importada(s) do estoque.`);
    } catch (error) {
      setStatus(error.message || "Nao foi possivel sincronizar produtos.");
    } finally {
      setIsSaving(false);
    }
  }

  async function updateProduct(product, updates) {
    setIsSaving(true);
    setStatus("Salvando produto...");
    try {
      const response = await authFetch(`${SHOP_API_URL}/shop/products/${encodeURIComponent(product.id)}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tenant_id: tenantId, ...updates }),
      });
      const data = await response.json();
      if (!response.ok || !data.ok) throw new Error(data.detail || "Nao foi possivel salvar produto.");
      setProducts((currentProducts) => currentProducts.map((item) => (item.id === data.product.id ? data.product : item)));
      setStatus(`Produto salvo: ${data.product.public_name}.`);
    } catch (error) {
      setStatus(error.message || "Nao foi possivel salvar produto.");
    } finally {
      setIsSaving(false);
    }
  }

  async function uploadProductImage(product, file) {
    if (!product || !file) return;
    setIsSaving(true);
    setStatus("Enviando imagem para o Chronos Media...");
    try {
      const form = new FormData();
      form.append("tenant_id", tenantId);
      form.append("media_type", "product");
      form.append("title", file.name);
      form.append("description", `Imagem de vitrine para ${product.public_name || product.family}`);
      form.append("tags", "loja,produto,vitrine");
      form.append("cache_ttl_days", "30");
      form.append("file", file);
      const response = await authFetch(`${MEDIA_API_URL}/media/upload`, { method: "POST", body: form });
      const data = await response.json();
      if (!response.ok || !data.ok) throw new Error(data.detail || "Nao foi possivel enviar imagem.");
      const imageUrl = `${MEDIA_API_URL}${data.media.cache_url}`;
      await updateProduct(product, { image_url: imageUrl });
      await loadMediaStatus();
      setStatus("Imagem salva no armazenamento local do CHRONOS.");
    } catch (error) {
      setStatus(error.message || "Nao foi possivel enviar imagem.");
    } finally {
      setIsSaving(false);
    }
  }

  async function createCart(event) {
    event.preventDefault();
    setIsSaving(true);
    setStatus("Criando carrinho...");
    try {
      const response = await authFetch(`${SHOP_API_URL}/shop/carts`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tenant_id: tenantId, ...cartForm }),
      });
      const data = await response.json();
      if (!response.ok || !data.ok) throw new Error(data.detail || "Nao foi possivel criar carrinho.");
      setCartForm({ client_name: "", client_phone: "", source: "flow" });
      setCartItemForm((current) => ({ ...current, cart_id: data.cart.id }));
      setStatus(`Carrinho criado para ${data.cart.client_name || "cliente"}.`);
      await loadCommercial();
    } catch (error) {
      setStatus(error.message || "Nao foi possivel criar carrinho.");
    } finally {
      setIsSaving(false);
    }
  }

  async function addCartItem(event) {
    event.preventDefault();
    if (!cartItemForm.cart_id || !cartItemForm.product_id || !cartItemForm.stock_item_id) return;
    setIsSaving(true);
    setStatus("Adicionando item...");
    try {
      const response = await authFetch(`${SHOP_API_URL}/shop/carts/${encodeURIComponent(cartItemForm.cart_id)}/items`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tenant_id: tenantId, ...cartItemForm, quantity: Number(cartItemForm.quantity) || 1 }),
      });
      const data = await response.json();
      if (!response.ok || !data.ok) throw new Error(data.detail || "Nao foi possivel adicionar item.");
      setStatus(`Item adicionado: ${data.item.product_name}.`);
      await loadCommercial();
    } catch (error) {
      setStatus(error.message || "Nao foi possivel adicionar item.");
    } finally {
      setIsSaving(false);
    }
  }

  async function saveCartTotals(cartId) {
    if (!cartId) return;
    setIsSaving(true);
    setStatus("Atualizando totais...");
    try {
      const response = await authFetch(`${SHOP_API_URL}/shop/carts/${encodeURIComponent(cartId)}/totals`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          tenant_id: tenantId,
          discount: Number(cartTotalsForm.discount) || 0,
          freight: Number(cartTotalsForm.freight) || 0,
          notes: cartTotalsForm.notes,
        }),
      });
      const data = await response.json();
      if (!response.ok || !data.ok) throw new Error(data.detail || "Nao foi possivel atualizar carrinho.");
      setStatus("Carrinho atualizado.");
      await loadCommercial();
    } catch (error) {
      setStatus(error.message || "Nao foi possivel atualizar carrinho.");
    } finally {
      setIsSaving(false);
    }
  }

  async function deleteCartItem(cartId, itemId) {
    setIsSaving(true);
    setStatus("Removendo item...");
    try {
      const response = await authFetch(`${SHOP_API_URL}/shop/carts/${encodeURIComponent(cartId)}/items/${encodeURIComponent(itemId)}?tenant_id=${encodeURIComponent(tenantId)}`, {
        method: "DELETE",
      });
      const data = await response.json();
      if (!response.ok || !data.ok) throw new Error(data.detail || "Nao foi possivel remover item.");
      setStatus("Item removido.");
      await loadCommercial();
    } catch (error) {
      setStatus(error.message || "Nao foi possivel remover item.");
    } finally {
      setIsSaving(false);
    }
  }


  async function createQuote(cartId) {
    setIsSaving(true);
    setStatus("Gerando orcamento...");
    try {
      const response = await authFetch(`${SHOP_API_URL}/shop/quotes`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tenant_id: tenantId, cart_id: cartId, valid_days: 7 }),
      });
      const data = await response.json();
      if (!response.ok || !data.ok) throw new Error(data.detail || "Nao foi possivel gerar orcamento.");
      setStatus("Orcamento gerado.");
      await loadCommercial();
    } catch (error) {
      setStatus(error.message || "Nao foi possivel gerar orcamento.");
    } finally {
      setIsSaving(false);
    }
  }

  async function createOrderFromQuote(quoteId) {
    setIsSaving(true);
    setStatus("Criando pedido...");
    try {
      const response = await authFetch(`${SHOP_API_URL}/shop/orders`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tenant_id: tenantId, quote_id: quoteId }),
      });
      const data = await response.json();
      if (!response.ok || !data.ok) throw new Error(data.detail || "Nao foi possivel criar pedido.");
      setPaymentForm((current) => ({ ...current, order_id: data.order.id, amount: String(data.order.total || "") }));
      setStatus("Pedido criado.");
      await loadCommercial();
    } catch (error) {
      setStatus(error.message || "Nao foi possivel criar pedido.");
    } finally {
      setIsSaving(false);
    }
  }

  async function downloadQuotePdf(quote) {
    setIsSaving(true);
    setStatus("Preparando PDF...");
    try {
      const response = await authFetch(`${SHOP_API_URL}/shop/quotes/${encodeURIComponent(quote.id)}/pdf?tenant_id=${encodeURIComponent(tenantId)}`);
      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(data.detail || "Nao foi possivel gerar o PDF.");
      }
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `orcamento-${quote.id}.pdf`;
      link.click();
      URL.revokeObjectURL(url);
      setStatus("PDF do orcamento baixado.");
    } catch (error) {
      setStatus(error.message || "Nao foi possivel gerar o PDF.");
    } finally {
      setIsSaving(false);
    }
  }

  async function createTransaction(event) {
    event.preventDefault();
    if (!paymentForm.order_id || !paymentForm.amount) return;
    setIsSaving(true);
    setStatus("Registrando pagamento...");
    try {
      const response = await authFetch(`${SHOP_API_URL}/shop/transactions`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tenant_id: tenantId, ...paymentForm, amount: Number(paymentForm.amount) || 0, status: "paid" }),
      });
      const data = await response.json();
      if (!response.ok || !data.ok) throw new Error(data.detail || "Nao foi possivel registrar pagamento.");
      setPaymentForm((current) => ({ ...current, amount: "", reference: "" }));
      setStatus("Pagamento registrado.");
      await loadCommercial();
    } catch (error) {
      setStatus(error.message || "Nao foi possivel registrar pagamento.");
    } finally {
      setIsSaving(false);
    }
  }

  async function createRefund(event) {
    event.preventDefault();
    if (!refundForm.order_id || !refundForm.amount) return;
    setIsSaving(true);
    setStatus("Registrando devolucao...");
    try {
      const response = await authFetch(`${SHOP_API_URL}/shop/refunds`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tenant_id: tenantId, ...refundForm, amount: Number(refundForm.amount) || 0 }),
      });
      const data = await response.json();
      if (!response.ok || !data.ok) throw new Error(data.detail || "Nao foi possivel registrar devolucao.");
      setRefundForm((current) => ({ ...current, amount: "", reason: "" }));
      setStatus("Devolucao registrada.");
      await loadCommercial();
    } catch (error) {
      setStatus(error.message || "Nao foi possivel registrar devolucao.");
    } finally {
      setIsSaving(false);
    }
  }

  const publishedProducts = products.filter((product) => product.published);
  const selectedCartProduct = products.find((product) => product.id === cartItemForm.product_id) || null;
  const selectedCart = carts.find((cart) => cart.id === cartItemForm.cart_id) || carts[0] || null;

  return (
    <section className={`loja-page ${mobile ? "loja-mobile" : ""}`}>
      <header className="loja-header">
        <div>
          <span>Chronos Loja</span>
          <h1>Vitrine virtual</h1>
          <p>Configure dominio, produtos publicados e catalogo publico da empresa.</p>
        </div>
        <div className="loja-header-card">
          <small>{currentTenant?.name || tenantId}</small>
          <strong>{config?.store_name || "Minha loja"}</strong>
          <span>{publishedProducts.length} publicado(s)</span>
        </div>
        <MobileActionPanel mobile={mobile} title="Armazenamento de imagens">
        <div className="loja-media-card">
          <small>Chronos Media</small>
          <strong>{mediaStatus?.storage?.ok ? "Armazenamento local" : "Armazenamento indisponível"}</strong>
          <span>{mediaStatus?.summary?.originals_ready || 0} arquivo(s) salvo(s)</span>
          {!!mediaStatus?.summary?.originals_missing && <span>{mediaStatus.summary.originals_missing} arquivo(s) precisam de restauração</span>}
        </div>
        </MobileActionPanel>
      </header>

      <nav className="loja-tabs">
        {[
          ["domain", "Dominio e vitrine", Settings],
          ["products", "Produtos", Store],
          ["operations", "Operacoes", CreditCard],
          ["preview", "Previa catalogo", Search],
        ].map(([tab, label, Icon]) => (
          <button key={tab} type="button" className={activeTab === tab ? "active" : ""} onClick={() => setActiveTab(tab)}>
            <Icon size={16} />
            {label}
          </button>
        ))}
      </nav>

      <small className="loja-status">{status}</small>

      {activeTab === "domain" && (
        <form className="loja-panel loja-domain-form" onSubmit={saveConfig}>
          <section>
            <h2>Configuracao de dominio</h2>
            <div className="loja-form-grid">
              <label>
                Nome da loja
                <input value={config?.store_name || ""} onChange={(event) => updateConfig("store_name", event.target.value)} />
              </label>
              <label>
                Slug Chronos
                <input value={config?.chronos_slug || ""} onChange={(event) => updateConfig("chronos_slug", event.target.value)} placeholder="nome-da-empresa" />
              </label>
              <label>
                Modo de dominio
                <select value={config?.use_chronos_domain ? "chronos" : "custom"} onChange={(event) => updateConfig("use_chronos_domain", event.target.value === "chronos")}>
                  <option value="chronos">Dominio Chronos</option>
                  <option value="custom">Dominio do cliente</option>
                </select>
              </label>
              <label>
                Dominio proprio
                <input value={config?.custom_domain || ""} onChange={(event) => updateConfig("custom_domain", event.target.value)} placeholder="cliente.com.br" />
              </label>
              <label>
                WhatsApp da loja
                <input value={config?.whatsapp || ""} onChange={(event) => updateConfig("whatsapp", event.target.value)} />
              </label>
              <label>
                Modelo da vitrine
                <select value={config?.theme || "default"} onChange={(event) => updateConfig("theme", event.target.value)}>
                  <option value="default">Nenhum modelo selecionado</option>
                </select>
              </label>
              <label>
                Chamada principal
                <input value={config?.banner_title || ""} onChange={(event) => updateConfig("banner_title", event.target.value)} />
              </label>
              <label>
                Subtitulo
                <input value={config?.banner_subtitle || ""} onChange={(event) => updateConfig("banner_subtitle", event.target.value)} />
              </label>
            </div>
          </section>
          <section className="loja-url-card">
            <span>URL publica</span>
            <strong>{publicUrl || "Configure um slug ou dominio."}</strong>
            <small>Sem um modelo de vitrine selecionado, este endereco mostra "Loja em desenvolvimento".</small>
          </section>
          <footer>
            <button type="submit" disabled={isSaving || !config}>
              {isSaving ? "Salvando..." : "Salvar vitrine"}
            </button>
          </footer>
        </form>
      )}

      {activeTab === "products" && (
        <section className="loja-panel">
          <header className="loja-panel-header">
            <div>
              <h2>Configuracao de produtos</h2>
              <p>Familias do estoque viram produtos publicos com variacoes compraveis.</p>
            </div>
            <button type="button" onClick={importProducts} disabled={isSaving}>
              <Package size={16} />
              Sincronizar Stock
            </button>
          </header>
          <div className="loja-product-list">
            {products.map((product) => {
              const isEditing = editingProductId === product.id;
              return (
                <article className={`loja-product-row ${product.published ? "published" : ""}`} key={product.id}>
                  <div className="loja-product-main">
                    <span>{product.category}</span>
                    <strong>{product.public_name || product.family}</strong>
                    <small>{product.variants?.length || 0} variacao(oes) · {product.public_category || product.category}</small>
                  </div>
                  <div className="loja-product-actions">
                    {product.promotion ? <PromotionTools hideSearch tenant={tenantId} products={products} product={product} variant={product.variants[0]} onPick={() => {}} onSaved={saved => setProducts(current => replacePromotion(current, saved))} /> : <>
                    <button type="button" className={product.published ? "active" : ""} onClick={() => updateProduct(product, { published: !product.published })}>
                      {product.published ? "Publicado" : "Oculto"}
                    </button>
                    <button type="button" onClick={() => setEditingProductId(isEditing ? null : product.id)}>
                      <Pencil size={15} />
                      Editar
                    </button></>}
                  </div>
                  {isEditing && (
                    <ProductEditor mobile={mobile} feedback={status} onClose={() => setEditingProductId(null)}>
                    <div className="loja-product-editor">
                      <label>
                        Nome publico
                        <input value={product.public_name || ""} onChange={(event) => setProducts((current) => current.map((item) => (item.id === product.id ? { ...item, public_name: event.target.value } : item)))} />
                      </label>
                      <label>
                        Categoria publica
                        <input value={product.public_category || ""} onChange={(event) => setProducts((current) => current.map((item) => (item.id === product.id ? { ...item, public_category: event.target.value } : item)))} />
                      </label>
                      <label>
                        Ordem
                        <input type="number" value={product.order || 0} onChange={(event) => setProducts((current) => current.map((item) => (item.id === product.id ? { ...item, order: Number(event.target.value) || 0 } : item)))} />
                      </label>
                      <label>
                        Imagem URL
                        <input value={product.image_url || ""} onChange={(event) => setProducts((current) => current.map((item) => (item.id === product.id ? { ...item, image_url: event.target.value } : item)))} />
                      </label>
                      <label>
                        Upload imagem
                        <input type="file" accept="image/*" onChange={(event) => uploadProductImage(product, event.target.files?.[0])} />
                      </label>
                      <label className="wide">
                        Descricao publica
                        <textarea value={product.public_description || ""} onChange={(event) => setProducts((current) => current.map((item) => (item.id === product.id ? { ...item, public_description: event.target.value } : item)))} />
                      </label>
                      <div className="loja-variant-editor wide">
                        <strong>Precos da vitrine por variacao</strong>
                        {(product.variants || []).map((variant) => (
                          <div className="loja-variant-price-row" key={variant.stock_item_id}>
                            <span>{[variant.sku, variant.size, variant.color].filter(Boolean).join(" · ") || "Variação"}</span>
                            <label>
                              Venda
                              <input
                                type="number"
                                min="0"
                                step="0.01"
                                value={variant.sale_price || ""}
                                onChange={(event) => updateProductVariantPrice(product.id, variant.stock_item_id, "sale_price", event.target.value)}
                              />
                            </label>
                            <PromotionTools hideSearch tenant={tenantId} products={products} product={product} variant={variant} onPick={() => {}} onSaved={saved => setProducts(current => replacePromotion(current, saved))} />
                            <label className="loja-variant-toggle">
                              <input
                                type="checkbox"
                                checked={variant.sellable ?? true}
                                onChange={(event) => updateProductVariantPrice(product.id, variant.stock_item_id, "sellable", event.target.checked)}
                              />
                              Vender
                            </label>
                            <section className="loja-quantity-prices">
                              <header>
                                <strong>Precos por quantidade</strong>
                                <button type="button" className="loja-quantity-price-add" onClick={() => addQuantityPriceTier(product.id, variant.stock_item_id)} title="Adicionar faixa de quantidade" aria-label="Adicionar faixa de quantidade">
                                  <Plus size={14} />
                                </button>
                              </header>
                              {(variant.quantity_prices || []).map((tier, tierIndex) => (
                                <div className="loja-quantity-price-row" key={`${variant.stock_item_id}-${tierIndex}`}>
                                  <label>
                                    A partir de
                                    <input type="number" min="1" step="1" value={tier.minimum_quantity || ""} onChange={(event) => updateQuantityPriceTier(product.id, variant.stock_item_id, tierIndex, "minimum_quantity", event.target.value)} />
                                  </label>
                                  <label>
                                    Valor unitario
                                    <input type="number" min="0" step="0.01" value={tier.unit_price || ""} onChange={(event) => updateQuantityPriceTier(product.id, variant.stock_item_id, tierIndex, "unit_price", event.target.value)} />
                                  </label>
                                  <button type="button" className="loja-quantity-price-remove" onClick={() => removeQuantityPriceTier(product.id, variant.stock_item_id, tierIndex)} title="Remover faixa" aria-label="Remover faixa">
                                    <Trash2 size={14} />
                                  </button>
                                </div>
                              ))}
                              {(variant.quantity_prices || []).length === 0 && <small>Sem faixas configuradas: usa o preço de venda.</small>}
                            </section>
                          </div>
                        ))}
                      </div>
                      <button type="button" onClick={() => updateProduct(product, product)}>
                        Salvar produto
                      </button>
                    </div>
                    </ProductEditor>
                  )}
                </article>
              );
            })}
            {products.length === 0 && <p className="loja-empty">Nenhuma familia encontrada no estoque de venda.</p>}
          </div>
        </section>
      )}

      {activeTab === "operations" && (
        <section className="loja-commerce-grid">
          <MobileActionPanel mobile={mobile} title="Novo carrinho" open={mobileAction === "Novo carrinho"} onOpen={() => setMobileAction("Novo carrinho")} onClose={() => setMobileAction(null)} feedback={status}>
          <form className="loja-panel loja-commerce-panel" onSubmit={createCart}>
            <header>
              <h2>Novo carrinho</h2>
              <span>{carts.length} carrinho(s)</span>
            </header>
            <label>
              Cliente
              <input value={cartForm.client_name} onChange={(event) => setCartForm((current) => ({ ...current, client_name: event.target.value }))} placeholder="Nome do cliente" />
            </label>
            <label>
              Telefone
              <input value={cartForm.client_phone} onChange={(event) => setCartForm((current) => ({ ...current, client_phone: event.target.value }))} placeholder="+55..." />
            </label>
            <button type="submit" disabled={isSaving}>
              <Plus size={15} />
              Criar carrinho
            </button>
          </form>
          </MobileActionPanel>

          <MobileActionPanel mobile={mobile} title="Adicionar item" open={mobileAction === "Adicionar item"} onOpen={() => setMobileAction("Adicionar item")} onClose={() => setMobileAction(null)} feedback={status}>
          <form className="loja-panel loja-commerce-panel" onSubmit={addCartItem}>
            <header>
              <h2>Adicionar item</h2>
              <span>{publishedProducts.length} produto(s) publicado(s)</span>
            </header>
            <label>
              Carrinho
              <select value={cartItemForm.cart_id} onChange={(event) => setCartItemForm((current) => ({ ...current, cart_id: event.target.value }))}>
                <option value="">Selecionar carrinho</option>
                {carts.map((cart) => (
                  <option key={cart.id} value={cart.id}>
                    {cart.client_name || cart.client_phone || cart.id} · {formatMoney(cart.total || 0)}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Produto
              <select value={cartItemForm.product_id} onChange={(event) => setCartItemForm((current) => ({ ...current, product_id: event.target.value, stock_item_id: "", extra_ids: [] }))}>
                <option value="">Selecionar produto</option>
                {publishedProducts.map((product) => (
                  <option key={product.id} value={product.id}>
                    {productOptionLabel(product)}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Variacao
              <select value={cartItemForm.stock_item_id} onChange={(event) => setCartItemForm((current) => ({ ...current, stock_item_id: event.target.value, extra_ids: [] }))}>
                <option value="">Selecionar variacao</option>
                {(selectedCartProduct?.variants || []).filter((variant) => variant.sellable).map((variant) => (
                  <option key={variant.stock_item_id} value={variant.stock_item_id}>
                    {[variant.sku, variant.size, variant.color].filter(Boolean).join(" · ") || variant.stock_item_id} · {variantPriceLabel(variant)}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Quantidade
              <input type="number" min="0.001" step="0.001" value={cartItemForm.quantity} onChange={(event) => setCartItemForm((current) => ({ ...current, quantity: event.target.value }))} />
              <PromotionTools tenant={tenantId} products={products} product={selectedCartProduct} variant={selectedCartProduct?.variants?.find(v => v.stock_item_id === cartItemForm.stock_item_id)} onPick={product => setCartItemForm(current => ({ ...current, product_id: product.id, stock_item_id: product.variants[0]?.stock_item_id || "", quantity: String(product.promotion?.package_quantity || 1), extra_ids: [] }))} onSaved={product => setProducts(current => replacePromotion(current, product))} />
              <ProductExtras key={`${tenantId}:${cartItemForm.stock_item_id}`} tenant={tenantId} productId={cartItemForm.product_id} variant={selectedCartProduct?.variants?.find(v => v.stock_item_id === cartItemForm.stock_item_id)} quantity={cartItemForm.quantity} selected={cartItemForm.extra_ids || []} onChange={extra_ids => setCartItemForm(current => ({ ...current, extra_ids }))} onCreated={extra => setProducts(current => withProductExtra(current, cartItemForm.product_id, extra))} />
              {cartItemForm.stock_item_id && <small className="loja-quantity-price-preview">{quantityPricePreview((selectedCartProduct?.variants || []).find((variant) => String(variant.stock_item_id) === String(cartItemForm.stock_item_id)), cartItemForm.quantity)}</small>}
            </label>
            <button type="submit" disabled={isSaving || !cartItemForm.cart_id || !cartItemForm.product_id || !cartItemForm.stock_item_id}>
              <Plus size={15} />
              Adicionar
            </button>
          </form>
          </MobileActionPanel>

          <section className="loja-panel loja-commerce-panel loja-commerce-wide">
            <header>
              <h2>Carrinhos</h2>
              <button type="button" onClick={loadCommercial}>Atualizar</button>
            </header>
            <div className="loja-commerce-list">
              {carts.map((cart) => (
                <article key={cart.id}>
                  <div>
                    <strong>{cart.client_name || cart.client_phone || "Cliente sem nome"}</strong>
                    <span>{cart.items_count || 0} item(ns) · {cart.status}</span>
                  </div>
                  <b>{formatMoney(cart.total || 0)}</b>
                  <button type="button" onClick={() => { setCartItemForm((current) => ({ ...current, cart_id: cart.id })); if (mobile) setMobileAction("Adicionar item"); }}>Usar</button>
                  <button type="button" onClick={() => createQuote(cart.id)} disabled={isSaving || !cart.items_count}>Orcamento</button>
                  <div className="loja-cart-items">
                    {(cart.items || []).map((item) => (
                      <span key={item.id}>
                        {item.quantity}x {item.product_name}{item.extras?.length > 0 && <> · {item.extras.map(extra => `${extra.description}: ${formatMoney(extra.unit_price)}/un`).join(" · ")}</>}
                        <button type="button" onClick={() => deleteCartItem(cart.id, item.id)} title="Remover item">
                          <X size={12} />
                        </button>
                      </span>
                    ))}
                    {(cart.items || []).length === 0 && <small>Sem itens</small>}
                  </div>
                </article>
              ))}
              {carts.length === 0 && <p className="loja-empty">Nenhum carrinho criado.</p>}
            </div>
            {selectedCart && (
              <div className="loja-cart-totals">
                <label>
                  Desconto
                  <input type="number" min="0" step="0.01" value={cartTotalsForm.discount} onChange={(event) => setCartTotalsForm((current) => ({ ...current, discount: event.target.value }))} />
                </label>
                <label>
                  Frete
                  <input type="number" min="0" step="0.01" value={cartTotalsForm.freight} onChange={(event) => setCartTotalsForm((current) => ({ ...current, freight: event.target.value }))} />
                </label>
                <label>
                  Observacoes
                  <input value={cartTotalsForm.notes} onChange={(event) => setCartTotalsForm((current) => ({ ...current, notes: event.target.value }))} />
                </label>
                <button type="button" onClick={() => saveCartTotals(selectedCart.id)} disabled={isSaving}>Salvar totais</button>
              </div>
            )}
          </section>

          <section className="loja-panel loja-commerce-panel">
            <header>
              <h2>Orcamentos</h2>
              <span>{quotes.length}</span>
            </header>
            <div className="loja-commerce-list compact">
              {quotes.map((quote) => (
                <article key={quote.id}>
                  <div>
                    <strong>{quote.cart_snapshot?.client_name || quote.id}</strong>
                    <span>{quote.status} · {quote.validity_text || "Válido até"} {quote.valid_until}</span>
                    <span>Vendedor: {quote.cart_snapshot?.seller_name || "Não informado"}</span>
                  </div>
                  <b>{formatMoney(quote.cart_snapshot?.total || 0)}</b>
                  <button type="button" onClick={() => downloadQuotePdf(quote)} disabled={isSaving} title="Baixar PDF do orcamento"><Download size={15} /></button>
                  <button type="button" onClick={() => createOrderFromQuote(quote.id)} disabled={isSaving}>Pedido</button>
                </article>
              ))}
              {quotes.length === 0 && <p className="loja-empty">Nenhum orcamento.</p>}
            </div>
          </section>

          <section className="loja-panel loja-commerce-panel">
            <header>
              <h2>Pedidos</h2>
              <OrderNumberingButton tenant={tenantId} />
              <span>{orders.length}</span>
            </header>
            <div className="loja-commerce-list compact">
              {orders.map((order) => (
                <article key={order.id}>
                  <div>
                    <strong>{order.client_name || orderLabel(order)}</strong>
                    <span>Pedido {orderLabel(order)}</span><OrderPaymentPdf tenant={tenantId} order={order} />
                    <span>{order.status} · pagamento {order.payment_status}</span>
                    <span>Vendedor: {order.seller_name || "Não informado"}</span>
                  </div>
                  <b>{formatMoney(order.total || 0)}</b>
                  <button type="button" onClick={() => { setPaymentForm((current) => ({ ...current, order_id: order.id, amount: String(order.total || "") })); if (mobile) setMobileAction("Pagamento manual"); }}>Pagar</button>
                </article>
              ))}
              {orders.length === 0 && <p className="loja-empty">Nenhum pedido.</p>}
            </div>
          </section>

          <MobileActionPanel mobile={mobile} title="Pagamento manual" open={mobileAction === "Pagamento manual"} onOpen={() => setMobileAction("Pagamento manual")} onClose={() => setMobileAction(null)} feedback={status}>
          <form className="loja-panel loja-commerce-panel" onSubmit={createTransaction}>
            <header>
              <h2>Pagamento manual</h2>
              <span>{transactions.length} transacao(oes)</span>
            </header>
            <label>
              Pedido
              <select value={paymentForm.order_id} onChange={(event) => setPaymentForm((current) => ({ ...current, order_id: event.target.value }))}>
                <option value="">Selecionar pedido</option>
                {orders.map((order) => <option key={order.id} value={order.id}>{orderLabel(order)} · {order.client_name || "Cliente"} · {formatMoney(order.total || 0)}</option>)}
              </select>
            </label>
            <label>
              Valor
              <input type="number" min="0.01" step="0.01" value={paymentForm.amount} onChange={(event) => setPaymentForm((current) => ({ ...current, amount: event.target.value }))} />
            </label>
            <label>
              Metodo
              <input value={paymentForm.method} onChange={(event) => setPaymentForm((current) => ({ ...current, method: event.target.value }))} />
            </label>
            <label>
              Referencia
              <input value={paymentForm.reference} onChange={(event) => setPaymentForm((current) => ({ ...current, reference: event.target.value }))} />
            </label>
            <button type="submit" disabled={isSaving || !paymentForm.order_id || !paymentForm.amount}>Registrar pagamento</button>
          </form>
          </MobileActionPanel>

          <MobileActionPanel mobile={mobile} title="Devolucao" open={mobileAction === "Devolucao"} onOpen={() => setMobileAction("Devolucao")} onClose={() => setMobileAction(null)} feedback={status}>
          <form className="loja-panel loja-commerce-panel" onSubmit={createRefund}>
            <header>
              <h2>Devolucao</h2>
              <span>{refunds.length} registro(s)</span>
            </header>
            <label>
              Pedido
              <select value={refundForm.order_id} onChange={(event) => setRefundForm((current) => ({ ...current, order_id: event.target.value }))}>
                <option value="">Selecionar pedido</option>
                {orders.map((order) => <option key={order.id} value={order.id}>{order.client_name || order.id}</option>)}
              </select>
            </label>
            <label>
              Valor
              <input type="number" min="0.01" step="0.01" value={refundForm.amount} onChange={(event) => setRefundForm((current) => ({ ...current, amount: event.target.value }))} />
            </label>
            <label className="wide">
              Motivo
              <input value={refundForm.reason} onChange={(event) => setRefundForm((current) => ({ ...current, reason: event.target.value }))} />
            </label>
            <button type="submit" disabled={isSaving || !refundForm.order_id || !refundForm.amount}>Registrar devolucao</button>
          </form>
          </MobileActionPanel>
        </section>
      )}

      {activeTab === "preview" && (
        <section className="loja-preview">
          <header>
            <span>{config?.store_name || "Minha loja"}</span>
            <h2>{config?.banner_title || "Catalogo online"}</h2>
            <p>{config?.banner_subtitle || "Produtos publicados aparecem aqui."}</p>
          </header>
          <div className="loja-preview-grid">
            {publishedProducts.map((product) => (
              <article className="loja-preview-card" key={product.id}>
                <div className="loja-preview-media">{product.image_url ? <AuthenticatedImage src={product.image_url} alt="" /> : <Store size={28} />}</div>
                <span>{product.public_category || product.category}</span>
                <strong>{product.public_name || product.family}</strong>
                <p>{product.public_description || "Sem descricao publica."}</p>
                <div className="loja-variant-pills">
                  {(product.variants || []).slice(0, 6).map((variant) => (
                    <small key={variant.stock_item_id}>
                      {[variant.size, variant.color].filter(Boolean).join(" · ") || variant.sku}
                      {` · ${variantPriceLabel(variant)}`}
                    </small>
                  ))}
                </div>
              </article>
            ))}
            {publishedProducts.length === 0 && <p className="loja-empty">Publique produtos para ver a previa do catalogo.</p>}
          </div>
        </section>
      )}
    </section>
  );
}

function ProductEditor({ mobile, onClose, children, feedback }) {
  return mobile ? <MobileDialog title="Editar produto" onClose={onClose}><p role="status">{feedback}</p>{children}</MobileDialog> : children;
}

export function LojaPublicPage() {
  const storeSlug = window.location.pathname.split("/").filter(Boolean).at(-1) || "";
  const cartStorageKey = `chronos-public-cart:${storeSlug}`;
  const [store, setStore] = useState(null);
  const [products, setProducts] = useState([]);
  const [selectedCategory, setSelectedCategory] = useState("Todos");
  const [selections, setSelections] = useState({});
  const [quantities, setQuantities] = useState({});
  const [cartSession, setCartSession] = useState(null);
  const [cart, setCart] = useState(null);
  const [cartOpen, setCartOpen] = useState(false);
  const [checkoutOpen, setCheckoutOpen] = useState(false);
  const [checkoutForm, setCheckoutForm] = useState({ client_name: "", client_phone: "", email: "", company_name: "", notes: "" });
  const [status, setStatus] = useState("Carregando catalogo...");
  const [submitting, setSubmitting] = useState(false);
  const [quoteResult, setQuoteResult] = useState(null);

  const request = (path, options) => authFetch(`${SHOP_API_URL}${path}`, options);

  useEffect(() => {
    let active = true;
    async function loadCatalog() {
      try {
        const response = await request(`/public/${encodeURIComponent(storeSlug)}/catalog`);
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || "Nao foi possivel abrir esta loja.");
        if (!active) return;
        setStore(data.store || null);
        setProducts(data.products || []);
        setStatus("");
      } catch (error) {
        if (active) setStatus(error.message || "Loja indisponivel.");
      }
    }
    loadCatalog();
    return () => { active = false; };
  }, [storeSlug]);

  useEffect(() => {
    let saved = null;
    try {
      saved = JSON.parse(window.localStorage.getItem(cartStorageKey) || "null");
    } catch {
      window.localStorage.removeItem(cartStorageKey);
    }
    if (!saved?.id || !saved?.token) return;
    let active = true;
    request(`/public/${encodeURIComponent(storeSlug)}/carts/${encodeURIComponent(saved.id)}?token=${encodeURIComponent(saved.token)}`)
      .then(async (response) => {
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || "Carrinho indisponivel.");
        if (active) {
          setCartSession(saved);
          setCart(data.cart || null);
        }
      })
      .catch(() => window.localStorage.removeItem(cartStorageKey));
    return () => { active = false; };
  }, [cartStorageKey, storeSlug]);

  const categories = ["Todos", ...Array.from(new Set(products.map((product) => product.public_category || product.category).filter(Boolean)))];
  const visibleProducts = products.filter((product) => selectedCategory === "Todos" || (product.public_category || product.category) === selectedCategory);
  const cartItemsCount = (cart?.items || []).reduce((total, item) => total + Number(item.quantity || 0), 0);

  function selectedVariant(product) {
    const selectedId = selections[product.id];
    return product.variants?.find((variant) => String(variant.stock_item_id) === String(selectedId)) || product.variants?.[0] || null;
  }

  function productPriceLabel(product) {
    if (product.promotion) return `${formatMoney(product.promotion.package_price)} / pacote de ${product.promotion.package_quantity} unidades`;
    const prices = (product.variants || []).flatMap((variant) => {
      const tiers = variant.quantity_prices || [];
      if (tiers.length) return [Math.min(...tiers.map((tier) => Number(tier.unit_price) || 0))];
      const price = Number(variant.promotional_price) || Number(variant.sale_price) || 0;
      return price > 0 ? [price] : [];
    }).filter((price) => price > 0);
    return prices.length ? `A partir de ${formatMoney(Math.min(...prices))}` : "Sob consulta";
  }

  function variantLabel(variant) {
    return [variant?.size, variant?.color, variant?.sku].filter(Boolean).join(" · ") || "Variacao padrao";
  }

  async function ensureCart() {
    if (cartSession?.id && cartSession?.token) return cartSession;
    const response = await request(`/public/${encodeURIComponent(storeSlug)}/carts`, { method: "POST" });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "Nao foi possivel criar o carrinho.");
    const nextSession = { id: data.cart.id, token: data.token };
    window.localStorage.setItem(cartStorageKey, JSON.stringify(nextSession));
    setCartSession(nextSession);
    setCart(data.cart);
    return nextSession;
  }

  async function addToCart(product) {
    const variant = selectedVariant(product);
    if (!variant) return;
    const quantity = Math.max(1, Number(quantities[product.id] || product.promotion?.package_quantity || 1));
    setSubmitting(true);
    setStatus("");
    try {
      const session = await ensureCart();
      const response = await request(`/public/${encodeURIComponent(storeSlug)}/carts/${encodeURIComponent(session.id)}/items`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token: session.token, product_id: product.id, stock_item_id: variant.stock_item_id, quantity }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Nao foi possivel adicionar o produto.");
      setCart(data.cart);
      setCartOpen(true);
    } catch (error) {
      setStatus(error.message || "Nao foi possivel atualizar o carrinho.");
    } finally {
      setSubmitting(false);
    }
  }

  async function updateCartItem(item, quantity) {
    if (!cartSession || quantity <= 0) return;
    setSubmitting(true);
    try {
      const response = await request(`/public/${encodeURIComponent(storeSlug)}/carts/${encodeURIComponent(cartSession.id)}/items/${encodeURIComponent(item.id)}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token: cartSession.token, product_id: item.product_id, stock_item_id: item.stock_item_id, quantity }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Nao foi possivel atualizar o item.");
      setCart(data.cart);
    } catch (error) {
      setStatus(error.message || "Nao foi possivel atualizar o carrinho.");
    } finally {
      setSubmitting(false);
    }
  }

  async function removeCartItem(item) {
    if (!cartSession) return;
    setSubmitting(true);
    try {
      const response = await request(`/public/${encodeURIComponent(storeSlug)}/carts/${encodeURIComponent(cartSession.id)}/items/${encodeURIComponent(item.id)}?token=${encodeURIComponent(cartSession.token)}`, { method: "DELETE" });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Nao foi possivel remover o item.");
      setCart(data.cart);
    } catch (error) {
      setStatus(error.message || "Nao foi possivel atualizar o carrinho.");
    } finally {
      setSubmitting(false);
    }
  }

  async function requestQuote(event) {
    event.preventDefault();
    if (!cartSession) return;
    setSubmitting(true);
    setStatus("");
    try {
      const response = await request(`/public/${encodeURIComponent(storeSlug)}/checkout`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...checkoutForm, cart_id: cartSession.id, token: cartSession.token }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Nao foi possivel enviar sua solicitacao.");
      setQuoteResult(data.quote);
      window.localStorage.removeItem(cartStorageKey);
      setCart(null);
      setCartSession(null);
    } catch (error) {
      setStatus(error.message || "Nao foi possivel enviar sua solicitacao.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <section className="loja-public-page">
      <header className="loja-public-header">
        <a className="loja-public-brand" href={`/ChronosLoja/${encodeURIComponent(storeSlug)}`}>
          <Store size={22} aria-hidden="true" />
          <span>{store?.store_name || "Loja Chronos"}</span>
        </a>
        <button className="loja-public-cart-trigger" type="button" onClick={() => setCartOpen(true)} aria-label="Abrir carrinho" title="Carrinho">
          <ShoppingCart size={19} aria-hidden="true" />
          <span>Carrinho</span>
          {cartItemsCount > 0 && <b>{cartItemsCount}</b>}
        </button>
      </header>

      {status && <p className="loja-public-status"><CircleAlert size={17} aria-hidden="true" />{status}</p>}

      {store && (
        <main className="loja-public-main">
          <section className="loja-public-intro">
            <span>Catalogo online</span>
            <h1>{store.banner_title || store.store_name}</h1>
            {store.banner_subtitle && <p>{store.banner_subtitle}</p>}
          </section>

          <nav className="loja-public-categories" aria-label="Categorias de produtos">
            {categories.map((category) => (
              <button key={category} type="button" className={selectedCategory === category ? "active" : ""} onClick={() => setSelectedCategory(category)}>{category}</button>
            ))}
          </nav>

          <section className="loja-public-products" aria-label="Produtos">
            {visibleProducts.map((product) => {
              const variant = selectedVariant(product);
              const quantity = quantities[product.id] || product.promotion?.package_quantity || 1;
              const sellable = Boolean(variant) && Number(variant.promotional_price || variant.sale_price || 0) > 0 || Boolean(variant?.quantity_prices?.length);
              return (
                <article className="loja-public-product" key={product.id}>
                  <div className="loja-public-product-media">
                    {product.image_url ? <img src={product.image_url} alt={product.public_name || product.family || "Produto"} /> : <Package size={34} aria-hidden="true" />}
                    {product.highlight && <span>Destaque</span>}
                  </div>
                  <div className="loja-public-product-info">
                    <small>{product.public_category || product.category}</small>
                    <h2>{product.public_name || product.family}</h2>
                    {product.public_description && <p>{product.public_description}</p>}
                    <strong>{productPriceLabel(product)}</strong>
                    {product.variants?.length > 1 && (
                      <label>
                        Variacao
                        <select value={variant?.stock_item_id || ""} onChange={(event) => setSelections((current) => ({ ...current, [product.id]: event.target.value }))}>
                          {product.variants.map((item) => <option key={item.stock_item_id} value={item.stock_item_id}>{variantLabel(item)}</option>)}
                        </select>
                      </label>
                    )}
                    {variant?.quantity_prices?.length > 0 && <small className="loja-public-tier">Quantidade minima: {Math.min(...variant.quantity_prices.map((tier) => Number(tier.minimum_quantity)))} {variant.unit || "UN"}</small>}
                    <div className="loja-public-buy-row">
                      <label className="loja-public-quantity">
                        Quantidade
                        <input type="number" min={product.promotion?.package_quantity || 1} step={product.promotion?.package_quantity || 1} value={quantity} onChange={(event) => setQuantities((current) => ({ ...current, [product.id]: event.target.value }))} />
                      </label>
                      <button type="button" onClick={() => addToCart(product)} disabled={submitting || !sellable}>{sellable ? "Adicionar" : "Consulte-nos"}</button>
                    </div>
                  </div>
                </article>
              );
            })}
            {!visibleProducts.length && <p className="loja-public-empty">Nenhum produto publicado nesta categoria.</p>}
          </section>
        </main>
      )}

      {cartOpen && <button type="button" className="loja-public-backdrop" aria-label="Fechar carrinho" onClick={() => setCartOpen(false)} />}
      <aside className={`loja-public-cart ${cartOpen ? "is-open" : ""}`} aria-label="Carrinho de compras">
        <header>
          <div><span>Seu carrinho</span><strong>{cartItemsCount} item(ns)</strong></div>
          <button type="button" onClick={() => setCartOpen(false)} aria-label="Fechar carrinho" title="Fechar"><X size={19} aria-hidden="true" /></button>
        </header>
        {!cart?.items?.length && <div className="loja-public-cart-empty"><ShoppingBag size={30} aria-hidden="true" /><p>Adicione os produtos que deseja orcar.</p></div>}
        {!!cart?.items?.length && <>
          <div className="loja-public-cart-items">
            {cart.items.map((item) => (
              <article key={item.id}>
                <div><strong>{item.product_name}</strong><small>{[item.size, item.color, item.sku].filter(Boolean).join(" · ")}</small><span>{formatMoney(item.unit_price)} por {item.unit || "UN"}</span></div>
                <div className="loja-public-cart-item-actions">
                  <div><button type="button" onClick={() => updateCartItem(item, Number(item.quantity) - (item.promotion?.package_quantity || 1))} disabled={submitting || Number(item.quantity) <= (item.promotion?.package_quantity || 1)} aria-label="Diminuir quantidade" title="Diminuir"><Minus size={14} /></button><b>{item.quantity}</b><button type="button" onClick={() => updateCartItem(item, Number(item.quantity) + (item.promotion?.package_quantity || 1))} disabled={submitting} aria-label="Aumentar quantidade" title="Aumentar"><Plus size={14} /></button></div>
                  <button type="button" onClick={() => removeCartItem(item)} disabled={submitting} aria-label="Remover item" title="Remover"><Trash2 size={15} /></button>
                </div>
              </article>
            ))}
          </div>
          <footer><div><span>Subtotal</span><strong>{formatMoney(cart.subtotal)}</strong></div><div><span>Total estimado</span><strong>{formatMoney(cart.total)}</strong></div><button type="button" onClick={() => { setCartOpen(false); setCheckoutOpen(true); }}>Solicitar orcamento</button></footer>
        </>}
      </aside>

      {checkoutOpen && <div className="loja-public-modal-wrap" role="presentation"><button type="button" className="loja-public-backdrop" aria-label="Fechar formulario" onClick={() => setCheckoutOpen(false)} /><form className="loja-public-checkout" onSubmit={requestQuote}>
        <header><div><span>Solicitar orcamento</span><h2>Para onde enviamos a proposta?</h2></div><button type="button" onClick={() => setCheckoutOpen(false)} aria-label="Fechar formulario" title="Fechar"><X size={19} /></button></header>
        {!quoteResult ? <><label>Nome<input required value={checkoutForm.client_name} onChange={(event) => setCheckoutForm((current) => ({ ...current, client_name: event.target.value }))} /></label><label>WhatsApp ou telefone<input required inputMode="tel" value={checkoutForm.client_phone} onChange={(event) => setCheckoutForm((current) => ({ ...current, client_phone: event.target.value }))} /></label><label>E-mail <small>opcional</small><input type="email" value={checkoutForm.email} onChange={(event) => setCheckoutForm((current) => ({ ...current, email: event.target.value }))} /></label><label>Empresa <small>opcional</small><input value={checkoutForm.company_name} onChange={(event) => setCheckoutForm((current) => ({ ...current, company_name: event.target.value }))} /></label><label>Observacoes <small>opcional</small><textarea rows="3" value={checkoutForm.notes} onChange={(event) => setCheckoutForm((current) => ({ ...current, notes: event.target.value }))} /></label><button type="submit" disabled={submitting}>{submitting ? "Enviando..." : "Enviar solicitacao"}</button></> : <div className="loja-public-checkout-success"><CheckCircle2 size={34} aria-hidden="true" /><h3>Solicitacao enviada</h3><p>Recebemos seu pedido de orcamento. {quoteResult.validity_text || "A proposta fica válida até"} {quoteResult.valid_until && new Date(`${quoteResult.valid_until}T12:00:00`).toLocaleDateString("pt-BR")}.</p><button type="button" onClick={() => setCheckoutOpen(false)}>Concluir</button></div>}
      </form></div>}
    </section>
  );
}
