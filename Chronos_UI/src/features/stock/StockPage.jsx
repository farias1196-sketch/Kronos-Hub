import MobileDialog from "../../components/ui/MobileDialog";
import "./stockMobile.css";
import React, { useEffect, useRef, useState } from "react";
import {
  Archive, ArrowRight, Bot, CalendarDays, Camera, CheckCircle2, CreditCard, FileText,
  GitBranch, GripVertical, Headphones, Image, ListChecks, Loader2, Mic, MessageCircle,
  Minus, MoreVertical, Package, Pencil, Plus, Search, Send, Settings, Smile, Square,
  StickyNote, Store, Trash2, UserRound, UserPlus, UsersRound, Video, X, Zap,
} from "lucide-react";
import { authFetch } from "../../auth";
import {
  AGENDA_API_URL, API_URL, CORE_API_URL, DEFAULT_CORE_TENANT_SLUG, DEFAULT_EMPRESA_ID,
  HERA_API_URL, NEXUS_API_URL, PAY_API_URL, PROMO_API_URL, SHOP_API_URL, STOCK_API_URL,
} from "../../shared/chronosConfig";
import { normalizeSearch } from "../../shared/chatUtils";
import { formatMoney } from "../core/coreUtils";
import StockCategoryAttributes from "./StockCategoryAttributes";
import StockImportExportPanel from "./StockImportExportPanel";

function operationProfileLabel(item) {
  const artDays = Number(item?.art_lead_days || 0);
  const productionDays = Number(item?.production_lead_days || 0);
  if (artDays && productionDays) return "Arte e produção";
  if (artDays) return "Arte";
  if (productionDays) return "Produção";
  return "Pronta-entrega";
}

export default function StockPage({ path, currentTenantSlug, mobile = false }) {
  const [items, setItems] = useState([]);
  const [searchTerm, setSearchTerm] = useState("");
  const [status, setStatus] = useState("Carregando estoque...");
  const [movementItem, setMovementItem] = useState(null);
  const [movementType, setMovementType] = useState("withdraw");
  const [movementQuantity, setMovementQuantity] = useState("1");
  const [movementReason, setMovementReason] = useState("");
  const [movementStatus, setMovementStatus] = useState("");
  const [isSavingMovement, setIsSavingMovement] = useState(false);
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
  const [categories, setCategories] = useState([]);
  const [suppliers, setSuppliers] = useState([]);
  const [serviceResources, setServiceResources] = useState([]);
  const [taxonomyStatus, setTaxonomyStatus] = useState("");
  const [resourceStatus, setResourceStatus] = useState("");
  const [newServiceResource, setNewServiceResource] = useState({
    name: "",
    kind: "equipment",
    quantity: "1",
    status: "active",
    unavailable_until: "",
    notes: "",
  });
  const [newCategoryName, setNewCategoryName] = useState("");
  const [newFamilyNames, setNewFamilyNames] = useState({});
  const [newSupplier, setNewSupplier] = useState({
    name: "",
    document: "",
    contact_name: "",
    phone: "",
    email: "",
    cep: "",
    address: "",
    city: "",
    state: "",
  });
  const [familyCategoryId, setFamilyCategoryId] = useState("");
  const [isSavingTaxonomy, setIsSavingTaxonomy] = useState(false);
  const [quickTaxonomyModal, setQuickTaxonomyModal] = useState(null);
  const [quickTaxonomyName, setQuickTaxonomyName] = useState("");
  const [isSavingQuickTaxonomy, setIsSavingQuickTaxonomy] = useState(false);
  const [newItemSizeDraft, setNewItemSizeDraft] = useState("");
  const [newItemColorDraft, setNewItemColorDraft] = useState("");
  const [variantStockRows, setVariantStockRows] = useState(null);
  const [newItem, setNewItem] = useState({
    name: "",
    sku: "",
    description: "",
    category: "",
    family: "",
    size: "",
    sizes: [],
    colors: [],
    unit: "UN",
    quantity: "0",
    min_quantity: "0",
    cost_price: "0",
    supplier: "",
    location: "",
    art_lead_days: "0",
    production_lead_days: "0",
    attributes: {},
  });
  const [createStatus, setCreateStatus] = useState("");
  const [isCreatingItem, setIsCreatingItem] = useState(false);
  const [deletingItemId, setDeletingItemId] = useState("");
  const [editingItem, setEditingItem] = useState(null);
  const [editForm, setEditForm] = useState(null);
  const [familyEditMeta, setFamilyEditMeta] = useState(null);
  const [familyEditRows, setFamilyEditRows] = useState([]);
  const [editStatus, setEditStatus] = useState("");
  const [isSavingEdit, setIsSavingEdit] = useState(false);
  const normalizedStockPath = path.toLowerCase();
  const activeSection = normalizedStockPath.includes("/resources")
    ? "resources"
    : normalizedStockPath.includes("/importar")
      ? "import-export"
    : normalizedStockPath.includes("/categories")
      ? "categories"
      : normalizedStockPath.includes("/internal")
        ? "internal"
        : "sale";
  const stockTenantId = currentTenantSlug || DEFAULT_CORE_TENANT_SLUG;
  const sectionConfig =
    activeSection === "categories"
      ? {
          title: "Categorias, famílias e fornecedores",
          description: "Organize cadastros auxiliares usados no estoque para venda.",
          tableDescription: "Taxonomia e fornecedores usados pelo estoque, loja e Hera AI.",
        }
      : activeSection === "import-export"
      ? {
          title: "Importar e exportar",
          description: "Use uma planilha mestre para cadastrar e atualizar o estoque em lote.",
          tableDescription: "",
        }
      : activeSection === "resources"
      ? {
          title: "Recursos p/ atendimento",
          description: "Salas, cadeiras, macas, maquinas e recursos usados pela Agenda.",
          tableDescription: "Recursos fisicos que limitam atendimentos simultaneos.",
        }
      : activeSection === "internal"
      ? {
          title: "Estoque interno",
          description: "Materiais de uso operacional, produção, embalagem e escritório.",
          tableDescription: "Itens que sustentam operação, produção e almoxarifado.",
        }
      : {
          title: "Estoque para venda",
          description: "Produtos e itens que entram em orçamento, loja, promoções e pedidos.",
          tableDescription: "Itens comerciais disponíveis para venda e composição de orçamento.",
        };

  async function loadStock() {
    try {
      const response = await authFetch(`${STOCK_API_URL}/stock/items?tenant_id=${encodeURIComponent(stockTenantId)}`);
      const data = await response.json();
      setItems(data.items || []);
      setStatus("Estoque carregado.");
    } catch {
      setItems([]);
      setStatus("Stock API indisponivel.");
    }
  }

  async function loadCategories() {
    try {
      const response = await authFetch(`${STOCK_API_URL}/stock/categories?tenant_id=${encodeURIComponent(stockTenantId)}`);
      const data = await response.json();
      setCategories(data.categories || []);
      setTaxonomyStatus("Categorias carregadas.");
    } catch {
      setCategories([]);
      setTaxonomyStatus("Nao foi possivel carregar categorias.");
    }
  }

  async function loadSuppliers() {
    try {
      const response = await authFetch(`${STOCK_API_URL}/stock/suppliers?tenant_id=${encodeURIComponent(stockTenantId)}`);
      const data = await response.json();
      setSuppliers(data.suppliers || []);
    } catch {
      setSuppliers([]);
    }
  }

  async function loadServiceResources() {
    try {
      const response = await authFetch(`${STOCK_API_URL}/stock/service-resources?tenant_id=${encodeURIComponent(stockTenantId)}`);
      const data = await response.json();
      setServiceResources(data.resources || []);
      setResourceStatus("Recursos carregados.");
    } catch {
      setServiceResources([]);
      setResourceStatus("Nao foi possivel carregar recursos.");
    }
  }

  function refreshStockData() {
    loadStock().catch(() => undefined);
    loadCategories().catch(() => undefined);
    loadSuppliers().catch(() => undefined);
    loadServiceResources().catch(() => undefined);
  }

  useEffect(() => {
    refreshStockData();
  }, [stockTenantId]);

  const normalizedSearch = normalizeSearch(searchTerm);
  const filteredItems = items.filter((item) => {
    if (!normalizedSearch) return true;
    return [item.display_name, item.name, item.description, item.sku, item.category, item.family, item.size, item.color, ...(item.colors || []), item.supplier, item.location, ...Object.values(item.attributes || {})]
      .map(normalizeSearch)
      .some((value) => value.includes(normalizedSearch));
  });
  const visibleItems = filteredItems.filter((item) => item.kind === activeSection);
  const filteredServiceResources = serviceResources.filter((resource) => {
    if (!normalizedSearch) return true;
    return [resource.name, resource.kind, resource.status, resource.unavailable_until, resource.notes]
      .map(normalizeSearch)
      .some((value) => value.includes(normalizedSearch));
  });

  function openMovementModal(item, type) {
    setMovementItem(item);
    setMovementType(type);
    setMovementQuantity("1");
    setMovementReason("");
    setMovementStatus("");
  }

  function openCreateModal() {
    setNewItem({
      name: "",
      sku: "",
      description: "",
      category: "",
      family: "",
      size: "",
      sizes: [],
      colors: [],
      unit: "UN",
      quantity: "0",
      min_quantity: "0",
      cost_price: "0",
      supplier: "",
      location: "",
      art_lead_days: "0",
      production_lead_days: "0",
      attributes: {},
    });
    setNewItemSizeDraft("");
    setNewItemColorDraft("");
    setVariantStockRows(null);
    setQuickTaxonomyModal(null);
    setCreateStatus("");
    setIsCreateModalOpen(true);
  }

  function closeCreateModal() {
    if (isCreatingItem) return;
    setIsCreateModalOpen(false);
    setCreateStatus("");
    setVariantStockRows(null);
    setQuickTaxonomyModal(null);
  }

  function updateNewItem(field, value) {
    setNewItem((currentItem) => ({
      ...currentItem,
      [field]: value,
      ...(field === "category" ? { family: "", attributes: {} } : {}),
    }));
  }

  function updateNewItemAttribute(key, value) {
    setNewItem((currentItem) => ({ ...currentItem, attributes: { ...currentItem.attributes, [key]: value } }));
  }

  function preventNumberWheel(event) {
    if (event.target?.type === "number") {
      event.target.blur();
    }
  }

  function addNewItemColor() {
    const color = newItemColorDraft.trim();
    if (!color) return;
    setNewItem((currentItem) => {
      const normalizedColors = currentItem.colors.map((itemColor) => normalizeSearch(itemColor));
      if (normalizedColors.includes(normalizeSearch(color))) return currentItem;
      return { ...currentItem, colors: [...currentItem.colors, color] };
    });
    setNewItemColorDraft("");
  }

  function removeNewItemColor(color) {
    setNewItem((currentItem) => ({ ...currentItem, colors: currentItem.colors.filter((itemColor) => itemColor !== color) }));
  }

  function addNewItemSize() {
    const size = newItemSizeDraft.trim();
    if (!size) return;
    setNewItem((currentItem) => {
      const normalizedSizes = currentItem.sizes.map((itemSize) => normalizeSearch(itemSize));
      if (normalizedSizes.includes(normalizeSearch(size))) return currentItem;
      return { ...currentItem, sizes: [...currentItem.sizes, size], size: currentItem.size || size };
    });
    setNewItemSizeDraft("");
  }

  function removeNewItemSize(size) {
    setNewItem((currentItem) => {
      const sizes = currentItem.sizes.filter((itemSize) => itemSize !== size);
      return { ...currentItem, sizes, size: currentItem.size === size ? sizes[0] || "" : currentItem.size };
    });
  }

  function openQuickTaxonomyModal(type) {
    if (type === "family" && !newItem.category) {
      setCreateStatus("Selecione ou crie uma categoria antes da família.");
      return;
    }
    setQuickTaxonomyModal(type);
    setQuickTaxonomyName("");
    setCreateStatus("");
  }

  function closeQuickTaxonomyModal() {
    if (isSavingQuickTaxonomy) return;
    setQuickTaxonomyModal(null);
    setQuickTaxonomyName("");
  }

  async function submitQuickTaxonomy(event) {
    event.preventDefault();
    const name = quickTaxonomyName.trim();
    if (!name) return;
    setIsSavingQuickTaxonomy(true);
    try {
      if (quickTaxonomyModal === "category") {
        const response = await authFetch(`${STOCK_API_URL}/stock/categories`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ tenant_id: stockTenantId, name }),
        });
        const data = await response.json();
        if (!response.ok || !data.ok) throw new Error(data.detail || "Nao foi possivel criar categoria.");
        setCategories((currentCategories) => [...currentCategories, data.category]);
        updateNewItem("category", data.category.name);
        setCreateStatus(`Categoria criada: ${data.category.name}.`);
      }
      if (quickTaxonomyModal === "family") {
        const category = categories.find((item) => item.name === newItem.category);
        if (!category) throw new Error("Categoria nao encontrada.");
        const response = await authFetch(`${STOCK_API_URL}/stock/categories/${category.id}/families`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ tenant_id: stockTenantId, name }),
        });
        const data = await response.json();
        if (!response.ok || !data.ok) throw new Error(data.detail || "Nao foi possivel criar familia.");
        setCategories((currentCategories) => currentCategories.map((currentCategory) => (currentCategory.id === data.category.id ? data.category : currentCategory)));
        updateNewItem("family", data.family.name);
        setCreateStatus(`Família criada: ${data.family.name}.`);
      }
      if (quickTaxonomyModal === "supplier") {
        const response = await authFetch(`${STOCK_API_URL}/stock/suppliers`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ tenant_id: stockTenantId, name }),
        });
        const data = await response.json();
        if (!response.ok || !data.ok) throw new Error(data.detail || "Nao foi possivel criar fornecedor.");
        setSuppliers((currentSuppliers) => [...currentSuppliers, data.supplier]);
        updateNewItem("supplier", data.supplier.name);
        setCreateStatus(`Fornecedor criado: ${data.supplier.name}.`);
      }
      closeQuickTaxonomyModal();
    } catch (error) {
      setCreateStatus(error.message || "Nao foi possivel salvar.");
    } finally {
      setIsSavingQuickTaxonomy(false);
    }
  }

  async function createCategory(event) {
    event.preventDefault();
    if (!newCategoryName.trim()) return;
    setIsSavingTaxonomy(true);
    setTaxonomyStatus("Criando categoria...");
    try {
      const response = await authFetch(`${STOCK_API_URL}/stock/categories`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tenant_id: stockTenantId, name: newCategoryName }),
      });
      const data = await response.json();
      if (!response.ok || !data.ok) throw new Error(data.detail || "Nao foi possivel criar categoria.");
      setCategories((currentCategories) => [...currentCategories, data.category]);
      setNewCategoryName("");
      setTaxonomyStatus(`Categoria criada: ${data.category.name}.`);
    } catch (error) {
      setTaxonomyStatus(error.message || "Nao foi possivel criar categoria.");
    } finally {
      setIsSavingTaxonomy(false);
    }
  }

  async function deleteCategory(category) {
    const confirmed = window.confirm(`Apagar a categoria "${category.name}"?`);
    if (!confirmed) return;
    setIsSavingTaxonomy(true);
    try {
      const response = await authFetch(`${STOCK_API_URL}/stock/categories/${category.id}?tenant_id=${encodeURIComponent(stockTenantId)}`, { method: "DELETE" });
      const data = await response.json();
      if (!response.ok || !data.ok) throw new Error(data.detail || "Nao foi possivel apagar categoria.");
      setCategories((currentCategories) => currentCategories.filter((currentCategory) => currentCategory.id !== category.id));
      setTaxonomyStatus(`Categoria apagada: ${category.name}.`);
    } catch (error) {
      setTaxonomyStatus(error.message || "Nao foi possivel apagar categoria.");
    } finally {
      setIsSavingTaxonomy(false);
    }
  }

  async function createFamily(event, category) {
    event.preventDefault();
    const familyName = (newFamilyNames[category.id] || "").trim();
    if (!familyName) return;
    setIsSavingTaxonomy(true);
    setTaxonomyStatus("Criando familia...");
    try {
      const response = await authFetch(`${STOCK_API_URL}/stock/categories/${category.id}/families`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tenant_id: stockTenantId, name: familyName }),
      });
      const data = await response.json();
      if (!response.ok || !data.ok) throw new Error(data.detail || "Nao foi possivel criar familia.");
      setCategories((currentCategories) => currentCategories.map((currentCategory) => (currentCategory.id === data.category.id ? data.category : currentCategory)));
      setNewFamilyNames((currentNames) => ({ ...currentNames, [category.id]: "" }));
      setTaxonomyStatus(`Familia criada: ${data.family.name}.`);
    } catch (error) {
      setTaxonomyStatus(error.message || "Nao foi possivel criar familia.");
    } finally {
      setIsSavingTaxonomy(false);
    }
  }

  async function deleteFamily(category, family) {
    const confirmed = window.confirm(`Apagar a familia "${family.name}"?`);
    if (!confirmed) return;
    setIsSavingTaxonomy(true);
    try {
      const response = await authFetch(
        `${STOCK_API_URL}/stock/categories/${category.id}/families/${family.id}?tenant_id=${encodeURIComponent(stockTenantId)}`,
        { method: "DELETE" }
      );
      const data = await response.json();
      if (!response.ok || !data.ok) throw new Error(data.detail || "Nao foi possivel apagar familia.");
      setCategories((currentCategories) => currentCategories.map((currentCategory) => (currentCategory.id === data.category.id ? data.category : currentCategory)));
      setTaxonomyStatus(`Familia apagada: ${family.name}.`);
    } catch (error) {
      setTaxonomyStatus(error.message || "Nao foi possivel apagar familia.");
    } finally {
      setIsSavingTaxonomy(false);
    }
  }

  function updateNewSupplier(field, value) {
    setNewSupplier((currentSupplier) => ({ ...currentSupplier, [field]: value }));
  }

  async function createSupplier(event) {
    event.preventDefault();
    if (!newSupplier.name.trim()) return;
    setIsSavingTaxonomy(true);
    setTaxonomyStatus("Criando fornecedor...");
    try {
      const response = await authFetch(`${STOCK_API_URL}/stock/suppliers`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tenant_id: stockTenantId, ...newSupplier }),
      });
      const data = await response.json();
      if (!response.ok || !data.ok) throw new Error(data.detail || "Nao foi possivel criar fornecedor.");
      setSuppliers((currentSuppliers) => [...currentSuppliers, data.supplier]);
      setNewSupplier({
        name: "",
        document: "",
        contact_name: "",
        phone: "",
        email: "",
        cep: "",
        address: "",
        city: "",
        state: "",
      });
      setTaxonomyStatus(`Fornecedor criado: ${data.supplier.name}.`);
    } catch (error) {
      setTaxonomyStatus(error.message || "Nao foi possivel criar fornecedor.");
    } finally {
      setIsSavingTaxonomy(false);
    }
  }

  async function deleteSupplier(supplier) {
    const confirmed = window.confirm(`Apagar o fornecedor "${supplier.name}"?`);
    if (!confirmed) return;
    setIsSavingTaxonomy(true);
    try {
      const response = await authFetch(`${STOCK_API_URL}/stock/suppliers/${supplier.id}?tenant_id=${encodeURIComponent(stockTenantId)}`, { method: "DELETE" });
      const data = await response.json();
      if (!response.ok || !data.ok) throw new Error(data.detail || "Nao foi possivel apagar fornecedor.");
      setSuppliers((currentSuppliers) => currentSuppliers.filter((currentSupplier) => currentSupplier.id !== supplier.id));
      setItems((currentItems) => currentItems.map((item) => (item.supplier === supplier.name ? { ...item, supplier: "" } : item)));
      setTaxonomyStatus(`Fornecedor apagado: ${supplier.name}.`);
    } catch (error) {
      setTaxonomyStatus(error.message || "Nao foi possivel apagar fornecedor.");
    } finally {
      setIsSavingTaxonomy(false);
    }
  }

  function updateNewServiceResource(field, value) {
    setNewServiceResource((currentResource) => ({ ...currentResource, [field]: value }));
  }

  async function createServiceResource(event) {
    event.preventDefault();
    if (!newServiceResource.name.trim()) return;
    setIsSavingTaxonomy(true);
    setResourceStatus("Criando recurso...");
    try {
      const response = await authFetch(`${STOCK_API_URL}/stock/service-resources`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          tenant_id: stockTenantId,
          ...newServiceResource,
          quantity: Number(newServiceResource.quantity) || 1,
        }),
      });
      const data = await response.json();
      if (!response.ok || !data.ok) throw new Error(data.detail || "Nao foi possivel criar recurso.");
      setServiceResources((currentResources) => [...currentResources, data.resource]);
      setNewServiceResource({ name: "", kind: "equipment", quantity: "1", status: "active", unavailable_until: "", notes: "" });
      setResourceStatus(`Recurso criado: ${data.resource.name}.`);
    } catch (error) {
      setResourceStatus(error.message || "Nao foi possivel criar recurso.");
    } finally {
      setIsSavingTaxonomy(false);
    }
  }

  async function updateServiceResource(resource, updates) {
    setResourceStatus("Atualizando recurso...");
    try {
      const response = await authFetch(`${STOCK_API_URL}/stock/service-resources/${resource.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tenant_id: stockTenantId, ...updates }),
      });
      const data = await response.json();
      if (!response.ok || !data.ok) throw new Error(data.detail || "Nao foi possivel atualizar recurso.");
      setServiceResources((currentResources) => currentResources.map((currentResource) => (currentResource.id === data.resource.id ? data.resource : currentResource)));
      setResourceStatus(`Recurso atualizado: ${data.resource.name}.`);
    } catch (error) {
      setResourceStatus(error.message || "Nao foi possivel atualizar recurso.");
    }
  }

  async function deleteServiceResource(resource) {
    const confirmed = window.confirm(`Apagar o recurso "${resource.name}"?`);
    if (!confirmed) return;
    setResourceStatus("Apagando recurso...");
    try {
      const response = await authFetch(`${STOCK_API_URL}/stock/service-resources/${resource.id}?tenant_id=${encodeURIComponent(stockTenantId)}`, { method: "DELETE" });
      const data = await response.json();
      if (!response.ok || !data.ok) throw new Error(data.detail || "Nao foi possivel apagar recurso.");
      setServiceResources((currentResources) => currentResources.filter((currentResource) => currentResource.id !== resource.id));
      setResourceStatus(`Recurso apagado: ${resource.name}.`);
    } catch (error) {
      setResourceStatus(error.message || "Nao foi possivel apagar recurso.");
    }
  }

  async function submitCreateItem(event) {
    event.preventDefault();
    if (activeSection === "sale" && !variantStockRows) {
      if (!newItem.category) {
        setCreateStatus("Selecione ou crie uma categoria.");
        return;
      }
      if (!newItem.family) {
        setCreateStatus("Selecione ou crie uma família.");
        return;
      }
      const sizes = newItem.sizes.length ? newItem.sizes : newItem.size.trim() ? [newItem.size.trim()] : [""];
      const colors = newItem.colors.length ? newItem.colors : [""];
      const rows = sizes.flatMap((size) =>
        colors.map((color, index) => ({
          id: `${size || "sem-tamanho"}:${color || "sem-cor"}:${index}`,
          size,
          color,
          quantity: "",
          cost_price: "",
        }))
      );
      setVariantStockRows(rows);
      setCreateStatus("Informe estoque e custo de cada variação.");
      return;
    }
    if (activeSection !== "sale" && !newItem.name.trim() && !newItem.family.trim() && !newItem.size.trim()) {
      setCreateStatus("Informe familia, tamanho ou nome do produto.");
      return;
    }
    setIsCreatingItem(true);
    setCreateStatus("Criando produto...");
    try {
      const rowsToCreate = activeSection === "sale" && variantStockRows ? variantStockRows : [{ size: newItem.size, color: newItem.colors[0] || "", quantity: newItem.quantity, cost_price: newItem.cost_price }];
      const createdItems = [];
      for (const [index, row] of rowsToCreate.entries()) {
        const skuPrefix = newItem.sku.trim().toUpperCase();
        const generatedSku = activeSection === "sale" && skuPrefix ? `${skuPrefix}-${String(index + 1).padStart(3, "0")}` : newItem.sku;
        const response = await authFetch(`${STOCK_API_URL}/stock/items`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            kind: activeSection,
            tenant_id: stockTenantId,
            name: newItem.name,
            sku: generatedSku,
            description: newItem.description,
            category: newItem.category,
            family: newItem.family,
            size: row.size || newItem.size,
            color: row.color || "",
            colors: row.color ? [row.color] : newItem.colors,
            unit: newItem.unit,
            quantity: Number(row.quantity) || 0,
            min_quantity: Number(newItem.min_quantity) || 0,
            cost_price: Number(row.cost_price) || 0,
            supplier: activeSection === "sale" ? newItem.supplier : "",
            location: activeSection === "sale" ? "" : newItem.location,
            art_lead_days: activeSection === "sale" ? Number(newItem.art_lead_days) || 0 : 0,
            production_lead_days: activeSection === "sale" ? Number(newItem.production_lead_days) || 0 : 0,
            attributes: newItem.attributes,
          }),
        });
        const data = await response.json();
        if (!response.ok || !data.ok) {
          throw new Error(data.detail || "Nao foi possivel criar este produto.");
        }
        createdItems.push(data.item);
      }
      setItems((currentItems) => [...currentItems, ...createdItems]);
      setStatus(`${createdItems.length} produto(s) criado(s).`);
      setIsCreateModalOpen(false);
      setVariantStockRows(null);
    } catch (error) {
      setCreateStatus(error.message || "Nao foi possivel criar este produto.");
    } finally {
      setIsCreatingItem(false);
    }
  }

  async function deleteStockItem(item) {
    const confirmed = window.confirm(`Apagar "${item.name}" do estoque?`);
    if (!confirmed) return;
    setDeletingItemId(item.id);
    try {
      const response = await authFetch(`${STOCK_API_URL}/stock/items/${item.id}?tenant_id=${encodeURIComponent(stockTenantId)}`, { method: "DELETE" });
      const data = await response.json();
      if (!response.ok || !data.ok) {
        throw new Error(data.detail || "Nao foi possivel apagar este item.");
      }
      setItems((currentItems) => currentItems.filter((currentItem) => currentItem.id !== item.id));
      setStatus(`Item apagado: ${item.name}.`);
    } catch (error) {
      setStatus(error.message || "Nao foi possivel apagar este item.");
    } finally {
      setDeletingItemId("");
    }
  }

  function openEditItem(item) {
    setEditingItem(item);
    setFamilyEditMeta(null);
    setFamilyEditRows([]);
    setEditForm({
      name: item.name || "",
      sku: item.sku || "",
      description: item.description || "",
      category: item.category || "",
      family: item.family || "",
      size: item.size || "",
      color: item.color || "",
      unit: item.unit || "UN",
      quantity: String(item.quantity ?? 0),
      min_quantity: String(item.min_quantity ?? 0),
      cost_price: String(item.cost_price ?? 0),
      supplier: item.supplier || "",
      location: item.location || "",
      art_lead_days: String(item.art_lead_days ?? 0),
      production_lead_days: String(item.production_lead_days ?? 0),
      attributes: item.attributes || {},
    });
    setEditStatus("");
  }

  function closeEditItem() {
    if (isSavingEdit) return;
    setEditingItem(null);
    setEditForm(null);
    setEditStatus("");
  }

  function updateEditForm(field, value) {
    setEditForm((currentForm) => ({ ...currentForm, [field]: value }));
  }

  function updateEditAttribute(key, value) {
    setEditForm((currentForm) => ({ ...currentForm, attributes: { ...(currentForm.attributes || {}), [key]: value } }));
  }

  async function submitEditItem(event) {
    event.preventDefault();
    if (!editingItem || !editForm) return;
    setIsSavingEdit(true);
    setEditStatus("Salvando item...");
    try {
      const response = await authFetch(`${STOCK_API_URL}/stock/items/${editingItem.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          tenant_id: stockTenantId,
          ...editForm,
          colors: editForm.color ? [editForm.color] : [],
          quantity: Number(editForm.quantity) || 0,
          min_quantity: Number(editForm.min_quantity) || 0,
          cost_price: Number(editForm.cost_price) || 0,
          art_lead_days: editingItem.kind === "sale" ? Number(editForm.art_lead_days) || 0 : 0,
          production_lead_days: editingItem.kind === "sale" ? Number(editForm.production_lead_days) || 0 : 0,
        }),
      });
      const data = await response.json();
      if (!response.ok || !data.ok) throw new Error(data.detail || "Nao foi possivel editar item.");
      setItems((currentItems) => currentItems.map((item) => (item.id === data.item.id ? data.item : item)));
      setStatus(`Item editado: ${data.item.display_name || data.item.name}.`);
      closeEditItem();
    } catch (error) {
      setEditStatus(error.message || "Nao foi possivel editar item.");
    } finally {
      setIsSavingEdit(false);
    }
  }

  function openFamilyEditor(item) {
    const rows = items
      .filter((stockItem) => stockItem.kind === "sale" && stockItem.category === item.category && stockItem.family === item.family)
      .map((stockItem) => ({
        id: stockItem.id,
        sku: stockItem.sku || "",
        size: stockItem.size || "",
        color: stockItem.color || "",
        quantity: String(stockItem.quantity ?? 0),
        min_quantity: String(stockItem.min_quantity ?? 0),
        cost_price: String(stockItem.cost_price ?? 0),
        unit: stockItem.unit || "UN",
        supplier: stockItem.supplier || "",
        description: stockItem.description || "",
      }));
    setFamilyEditMeta({ category: item.category, family: item.family });
    setFamilyEditRows(rows);
    setEditingItem(null);
    setEditForm(null);
    setEditStatus("");
  }

  function closeFamilyEditor() {
    if (isSavingEdit) return;
    setFamilyEditMeta(null);
    setFamilyEditRows([]);
    setEditStatus("");
  }

  function updateFamilyEditRow(rowId, field, value) {
    setFamilyEditRows((currentRows) => currentRows.map((row) => (row.id === rowId ? { ...row, [field]: value } : row)));
  }

  async function submitFamilyEdit(event) {
    event.preventDefault();
    if (!familyEditMeta || familyEditRows.length === 0) return;
    setIsSavingEdit(true);
    setEditStatus("Salvando família...");
    try {
      const updatedItems = [];
      for (const row of familyEditRows) {
        const response = await authFetch(`${STOCK_API_URL}/stock/items/${row.id}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            tenant_id: stockTenantId,
            category: familyEditMeta.category,
            family: familyEditMeta.family,
            sku: row.sku,
            size: row.size,
            color: row.color,
            colors: row.color ? [row.color] : [],
            quantity: Number(row.quantity) || 0,
            min_quantity: Number(row.min_quantity) || 0,
            cost_price: Number(row.cost_price) || 0,
            unit: row.unit,
            supplier: row.supplier,
            description: row.description,
          }),
        });
        const data = await response.json();
        if (!response.ok || !data.ok) throw new Error(data.detail || "Nao foi possivel editar uma variação.");
        updatedItems.push(data.item);
      }
      setItems((currentItems) => currentItems.map((item) => updatedItems.find((updatedItem) => updatedItem.id === item.id) || item));
      setStatus(`${updatedItems.length} variação(ões) editada(s) em ${familyEditMeta.family}.`);
      closeFamilyEditor();
    } catch (error) {
      setEditStatus(error.message || "Nao foi possivel editar família.");
    } finally {
      setIsSavingEdit(false);
    }
  }

  function closeMovementModal() {
    if (isSavingMovement) return;
    setMovementItem(null);
    setMovementStatus("");
  }

  async function submitMovement(event) {
    event.preventDefault();
    if (!movementItem) return;
    const quantity = Number(movementQuantity);
    if (!Number.isFinite(quantity) || quantity <= 0) {
      setMovementStatus("Informe uma quantidade valida.");
      return;
    }
    if (movementType === "withdraw" && quantity > Number(movementItem.quantity)) {
      setMovementStatus("A retirada nao pode ser maior que o saldo atual.");
      return;
    }
    setIsSavingMovement(true);
    setMovementStatus(movementType === "add" ? "Adicionando item..." : "Retirando item...");
    try {
      const response = await authFetch(`${STOCK_API_URL}/stock/items/${movementItem.id}/${movementType === "add" ? "add" : "withdraw"}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          quantity,
          tenant_id: stockTenantId,
          reason: movementReason,
          requested_by: "Chronos UI",
        }),
      });
      const data = await response.json();
      if (!response.ok || !data.ok) {
        throw new Error(data.detail || "Nao foi possivel movimentar este item.");
      }
      setItems((currentItems) => currentItems.map((item) => (item.id === data.item.id ? data.item : item)));
      setStatus(`${movementType === "add" ? "Entrada" : "Retirada"} registrada: ${quantity} ${movementItem.unit} de ${movementItem.name}.`);
      setMovementItem(null);
    } catch (error) {
      setMovementStatus(error.message || "Nao foi possivel movimentar este item.");
    } finally {
      setIsSavingMovement(false);
    }
  }

  return (
    <section className={`stock-page ${mobile ? "stock-mobile" : ""}`}>
      <header className="stock-header">
        <div>
          <span>Chronos Stock</span>
          <h1>{sectionConfig.title}</h1>
          <p>{sectionConfig.description}</p>
        </div>
        <div className="stock-header-actions">
          {activeSection !== "categories" && activeSection !== "resources" && activeSection !== "import-export" && (
            <button type="button" onClick={openCreateModal}>
              <Plus size={16} />
              Novo produto
            </button>
          )}
          <button type="button" onClick={refreshStockData}>
            <Package size={16} />
            Atualizar
          </button>
        </div>
      </header>

      {activeSection !== "import-export" && <section className="stock-toolbar">
        <label>
          <Search size={17} />
          <input
            aria-label="Buscar no estoque"
            value={searchTerm}
            onChange={(event) => setSearchTerm(event.target.value)}
            placeholder={
              activeSection === "resources"
                ? "Pesquisar recurso, status ou observacao"
                : activeSection === "sale"
                  ? "Pesquisar item, SKU, categoria ou fornecedor"
                  : "Pesquisar item, SKU, categoria ou local"
            }
          />
        </label>
        <small>{activeSection === "resources" ? resourceStatus : status}</small>
      </section>}

      {activeSection === "categories" ? (
        <StockTaxonomyPage
          categories={categories}
          suppliers={suppliers}
          status={taxonomyStatus}
          newCategoryName={newCategoryName}
          newFamilyNames={newFamilyNames}
          newSupplier={newSupplier}
          familyCategoryId={familyCategoryId}
          isSaving={isSavingTaxonomy}
          onNewCategoryName={setNewCategoryName}
          onNewFamilyName={(categoryId, value) => setNewFamilyNames((currentNames) => ({ ...currentNames, [categoryId]: value }))}
          onNewSupplier={updateNewSupplier}
          onFamilyCategoryId={setFamilyCategoryId}
          onCreateCategory={createCategory}
          onCreateFamily={createFamily}
          onCreateSupplier={createSupplier}
          onDeleteCategory={deleteCategory}
          onDeleteFamily={deleteFamily}
          onDeleteSupplier={deleteSupplier}
          tenantId={stockTenantId}
          onAttributesChanged={loadCategories}
        />
      ) : activeSection === "resources" ? (
        <StockServiceResourcesPage
          resources={filteredServiceResources}
          status={resourceStatus}
          newResource={newServiceResource}
          isSaving={isSavingTaxonomy}
          onNewResource={updateNewServiceResource}
          onCreateResource={createServiceResource}
          onUpdateResource={updateServiceResource}
          onDeleteResource={deleteServiceResource}
        />
      ) : activeSection === "import-export" ? (
        <StockImportExportPanel tenantId={stockTenantId} onImported={refreshStockData} />
      ) : (
        <main className="stock-tables single">
          <StockTable
            mobile={mobile}
            title={sectionConfig.title}
            description={sectionConfig.tableDescription}
            items={visibleItems}
            kind={activeSection}
            onMovement={openMovementModal}
            onEdit={openEditItem}
            onEditFamily={openFamilyEditor}
            onDelete={deleteStockItem}
            deletingItemId={deletingItemId}
          />
        </main>
      )}

      {isCreateModalOpen && (
        <StockDialog mobile={mobile} title="Novo produto" onClose={closeCreateModal} backdrop="stock-withdraw-backdrop">
          <form className="stock-withdraw-modal stock-create-modal" onSubmit={submitCreateItem} onMouseDown={(event) => event.stopPropagation()} onWheelCapture={preventNumberWheel}>
            <header>
              <div>
                <span>{activeSection === "internal" ? "Estoque interno" : "Estoque para venda"}</span>
                <strong>Novo produto</strong>
              </div>
              <button type="button" onClick={closeCreateModal} aria-label="Fechar novo produto">
                <X size={18} />
              </button>
            </header>
            {variantStockRows ? (
              <div className="stock-variant-step">
                <p>Informe estoque e custo para cada variação. O preço de venda fica na Loja.</p>
                <div className="stock-variant-list">
                  {variantStockRows.map((row) => (
                    <div className="stock-variant-row" key={row.id}>
                      <strong>
                        {newItem.family || "Produto"} {row.size || "sem tamanho"} {row.color || "sem cor"}
                      </strong>
                      <label>
                        Estoque
                        <input
                          type="number"
                          min="0"
                          step="0.001"
                          value={row.quantity}
                          onChange={(event) =>
                            setVariantStockRows((currentRows) =>
                              currentRows.map((currentRow) => (currentRow.id === row.id ? { ...currentRow, quantity: event.target.value } : currentRow))
                            )
                          }
                          placeholder="Qtd"
                        />
                      </label>
                      <label>
                        Preço de compra
                        <input
                          type="number"
                          min="0"
                          step="0.01"
                          value={row.cost_price}
                          onChange={(event) =>
                            setVariantStockRows((currentRows) =>
                              currentRows.map((currentRow) => (currentRow.id === row.id ? { ...currentRow, cost_price: event.target.value } : currentRow))
                            )
                          }
                          placeholder="R$"
                        />
                      </label>
                    </div>
                  ))}
                </div>
              </div>
            ) : (
            <div className={`stock-create-grid ${activeSection === "sale" ? "sale-scale" : ""}`}>
              {activeSection !== "sale" && (
                <label>
                  Nome
                  <input value={newItem.name} onChange={(event) => updateNewItem("name", event.target.value)} autoFocus />
                </label>
              )}
              <label className={activeSection === "sale" ? "stock-create-compact" : ""}>
                {activeSection === "sale" ? "Prefixo SKU" : "SKU"}
                <input value={newItem.sku} onChange={(event) => updateNewItem("sku", event.target.value)} autoFocus={activeSection === "sale"} />
              </label>
              <label>
                Categoria
                <div className="stock-select-plus">
                  <select value={newItem.category} onChange={(event) => updateNewItem("category", event.target.value)}>
                    <option value="">Selecionar categoria</option>
                    {categories.map((category) => (
                      <option key={category.id} value={category.name}>
                        {category.name}
                      </option>
                    ))}
                  </select>
                  <button type="button" onClick={() => openQuickTaxonomyModal("category")} aria-label="Criar categoria">
                    <Plus size={14} />
                  </button>
                </div>
              </label>
              <label>
                Família
                <div className="stock-select-plus">
                  <select value={newItem.family} onChange={(event) => updateNewItem("family", event.target.value)} disabled={!newItem.category}>
                    <option value="">Selecionar família</option>
                    {(categories.find((category) => category.name === newItem.category)?.families || []).map((family) => (
                      <option key={family.id} value={family.name}>
                        {family.name}
                      </option>
                    ))}
                  </select>
                  <button type="button" onClick={() => openQuickTaxonomyModal("family")} aria-label="Criar família">
                    <Plus size={14} />
                  </button>
                </div>
              </label>
              <StockAttributeFields
                categoryName={newItem.category}
                categories={categories}
                attributes={newItem.attributes}
                onChange={updateNewItemAttribute}
                className="stock-create-wide"
              />
              {activeSection === "sale" && (
                <label>
                  Fornecedor
                  <div className="stock-select-plus">
                    <select value={newItem.supplier} onChange={(event) => updateNewItem("supplier", event.target.value)}>
                      <option value="">Selecionar fornecedor</option>
                      {suppliers.map((supplier) => (
                        <option key={supplier.id} value={supplier.name}>
                          {supplier.name}
                        </option>
                      ))}
                    </select>
                    <button type="button" onClick={() => openQuickTaxonomyModal("supplier")} aria-label="Criar fornecedor">
                      <Plus size={14} />
                    </button>
                  </div>
                </label>
              )}
              {activeSection === "sale" && (
                <fieldset className="stock-operation-profile stock-create-wide">
                  <legend>Operação do pedido</legend>
                  <label>
                    Arte (dias úteis)
                    <input type="number" min="0" max="365" step="1" value={newItem.art_lead_days} onChange={(event) => updateNewItem("art_lead_days", event.target.value)} />
                  </label>
                  <label>
                    Produção após aprovação (dias úteis)
                    <input type="number" min="0" max="365" step="1" value={newItem.production_lead_days} onChange={(event) => updateNewItem("production_lead_days", event.target.value)} />
                  </label>
                  <small>{operationProfileLabel(newItem)}</small>
                </fieldset>
              )}
              <div className="stock-variation-field">
                <label>
                  Tamanhos / divisões
                  <div className="stock-product-color-input">
                    <input
                      value={newItemSizeDraft}
                      onChange={(event) => setNewItemSizeDraft(event.target.value)}
                      onKeyDown={(event) => {
                        if (event.key === "Enter") {
                          event.preventDefault();
                          addNewItemSize();
                        }
                      }}
                      placeholder="Ex: 30x40"
                    />
                    <button type="button" onClick={addNewItemSize} aria-label="Adicionar tamanho ao produto">
                      <Plus size={14} />
                    </button>
                  </div>
                </label>
                <div className="stock-product-color-list">
                  {newItem.sizes.map((size) => (
                    <span key={size}>
                      {size}
                      <button type="button" onClick={() => removeNewItemSize(size)} aria-label={`Remover tamanho ${size}`}>
                        <X size={12} />
                      </button>
                    </span>
                  ))}
                  {newItem.sizes.length === 0 && <small>Sem tamanhos cadastrados.</small>}
                </div>
              </div>
              <div className="stock-variation-field">
                <label>
                  Cores
                  <div className="stock-product-color-input">
                    <input
                      value={newItemColorDraft}
                      onChange={(event) => setNewItemColorDraft(event.target.value)}
                      onKeyDown={(event) => {
                        if (event.key === "Enter") {
                          event.preventDefault();
                          addNewItemColor();
                        }
                      }}
                      placeholder="Ex: Preto"
                    />
                    <button type="button" onClick={addNewItemColor} aria-label="Adicionar cor ao produto">
                      <Plus size={14} />
                    </button>
                  </div>
                </label>
                <div className="stock-product-color-list">
                  {newItem.colors.map((color) => (
                    <span key={color}>
                      {color}
                      <button type="button" onClick={() => removeNewItemColor(color)} aria-label={`Remover cor ${color}`}>
                        <X size={12} />
                      </button>
                    </span>
                  ))}
                  {newItem.colors.length === 0 && <small>Sem cores cadastradas para este produto.</small>}
                </div>
              </div>
              <label className={activeSection === "sale" ? "stock-create-compact" : ""}>
                Unidade
                <input value={newItem.unit} onChange={(event) => updateNewItem("unit", event.target.value)} placeholder="UN, KG, M2, L..." />
              </label>
              {activeSection !== "sale" && (
                <label>
                Quantidade inicial
                <input type="number" min="0" step="0.001" value={newItem.quantity} onChange={(event) => updateNewItem("quantity", event.target.value)} />
              </label>
              )}
              <label className={activeSection === "sale" ? "stock-create-compact" : ""}>
                Quantidade minima
                <input type="number" min="0" step="0.001" value={newItem.min_quantity} onChange={(event) => updateNewItem("min_quantity", event.target.value)} />
              </label>
              {activeSection !== "sale" && (
                <label>
                  Preço de compra
                  <input type="number" min="0" step="0.01" value={newItem.cost_price} onChange={(event) => updateNewItem("cost_price", event.target.value)} />
                </label>
              )}
              {activeSection !== "sale" && (
                <label className="stock-create-wide">
                  Local
                  <input value={newItem.location} onChange={(event) => updateNewItem("location", event.target.value)} />
                </label>
              )}
              <label className="stock-create-wide stock-create-description">
                Descrição breve
                <textarea value={newItem.description} onChange={(event) => updateNewItem("description", event.target.value)} placeholder="Observação curta para loja, orçamento ou Hera AI" />
              </label>
            </div>
            )}
            {createStatus && <small>{createStatus}</small>}
            <footer>
              {variantStockRows ? (
                <button type="button" onClick={() => setVariantStockRows(null)}>
                  Voltar
                </button>
              ) : (
                <button type="button" onClick={closeCreateModal}>
                  Cancelar
                </button>
              )}
              <button type="submit" disabled={isCreatingItem}>
                {isCreatingItem ? "Criando..." : variantStockRows ? "Criar variações" : activeSection === "sale" ? "Continuar" : "Criar produto"}
              </button>
            </footer>
          </form>
        </StockDialog>
      )}

      {quickTaxonomyModal && (
        <StockDialog mobile={mobile} title="Novo cadastro" onClose={closeQuickTaxonomyModal} backdrop="stock-mini-backdrop">
          <form className="stock-mini-modal" onSubmit={submitQuickTaxonomy} onMouseDown={(event) => event.stopPropagation()}>
            <header>
              <strong>{quickTaxonomyModal === "category" ? "Nova categoria" : quickTaxonomyModal === "family" ? "Nova família" : "Novo fornecedor"}</strong>
              <button type="button" onClick={closeQuickTaxonomyModal} aria-label="Fechar">
                <X size={16} />
              </button>
            </header>
            {quickTaxonomyModal === "family" && <small>Categoria: {newItem.category}</small>}
            <input
              value={quickTaxonomyName}
              onChange={(event) => setQuickTaxonomyName(event.target.value)}
              placeholder={quickTaxonomyModal === "category" ? "Ex: Sacola plastica" : quickTaxonomyModal === "family" ? "Ex: Bolsa vazada" : "Ex: Plastimax"}
              autoFocus
            />
            <footer>
              <button type="button" onClick={closeQuickTaxonomyModal}>
                Cancelar
              </button>
              <button type="submit" disabled={isSavingQuickTaxonomy || !quickTaxonomyName.trim()}>
                Salvar
              </button>
            </footer>
          </form>
        </StockDialog>
      )}

      {editingItem && editForm && (
        <StockDialog mobile={mobile} title="Editar item" onClose={closeEditItem} backdrop="stock-withdraw-backdrop">
          <form className="stock-withdraw-modal stock-edit-modal" onSubmit={submitEditItem} onMouseDown={(event) => event.stopPropagation()} onWheelCapture={preventNumberWheel}>
            <header>
              <div>
                <span>{editingItem.kind === "sale" ? "Estoque para venda" : "Estoque interno"}</span>
                <strong>Editar item</strong>
              </div>
              <button type="button" onClick={closeEditItem} aria-label="Fechar edição">
                <X size={18} />
              </button>
            </header>
            <div className="stock-edit-grid">
              <label>
                Categoria
                <select
                  value={editForm.category}
                  onChange={(event) => setEditForm((currentForm) => ({ ...currentForm, category: event.target.value, family: "", attributes: {} }))}
                >
                  <option value="">Selecionar categoria</option>
                  {categories.map((category) => <option key={category.id} value={category.name}>{category.name}</option>)}
                </select>
              </label>
              <label>
                Família
                <select value={editForm.family} onChange={(event) => updateEditForm("family", event.target.value)}>
                  <option value="">Sem família</option>
                  {(categories.find((category) => category.name === editForm.category)?.families || []).map((family) => <option key={family.id} value={family.name}>{family.name}</option>)}
                </select>
              </label>
              <label>
                SKU
                <input value={editForm.sku} onChange={(event) => updateEditForm("sku", event.target.value)} autoFocus />
              </label>
              <label>
                Tamanho
                <input value={editForm.size} onChange={(event) => updateEditForm("size", event.target.value)} />
              </label>
              <label>
                Cor
                <input value={editForm.color} onChange={(event) => updateEditForm("color", event.target.value)} />
              </label>
              <label>
                Unidade
                <input value={editForm.unit} onChange={(event) => updateEditForm("unit", event.target.value)} />
              </label>
              <label>
                Estoque
                <input type="number" min="0" step="0.001" value={editForm.quantity} onChange={(event) => updateEditForm("quantity", event.target.value)} />
              </label>
              <label>
                Mínimo
                <input type="number" min="0" step="0.001" value={editForm.min_quantity} onChange={(event) => updateEditForm("min_quantity", event.target.value)} />
              </label>
              <label>
                Preço de compra
                <input type="number" min="0" step="0.01" value={editForm.cost_price} onChange={(event) => updateEditForm("cost_price", event.target.value)} />
              </label>
              {editingItem.kind === "sale" && (
                <label className="stock-edit-wide">
                  Fornecedor
                  <select value={editForm.supplier} onChange={(event) => updateEditForm("supplier", event.target.value)}>
                    <option value="">Sem fornecedor</option>
                    {suppliers.map((supplier) => (
                      <option key={supplier.id} value={supplier.name}>
                        {supplier.name}
                      </option>
                    ))}
                  </select>
                </label>
              )}
              {editingItem.kind === "sale" && (
                <fieldset className="stock-operation-profile stock-edit-wide">
                  <legend>Operação do pedido</legend>
                  <label>
                    Arte (dias úteis)
                    <input type="number" min="0" max="365" step="1" value={editForm.art_lead_days} onChange={(event) => updateEditForm("art_lead_days", event.target.value)} />
                  </label>
                  <label>
                    Produção após aprovação (dias úteis)
                    <input type="number" min="0" max="365" step="1" value={editForm.production_lead_days} onChange={(event) => updateEditForm("production_lead_days", event.target.value)} />
                  </label>
                  <small>{operationProfileLabel(editForm)}</small>
                </fieldset>
              )}
              <StockAttributeFields
                categoryName={editForm.category}
                categories={categories}
                attributes={editForm.attributes}
                onChange={updateEditAttribute}
                className="stock-edit-wide"
              />
              <label className="stock-edit-wide">
                Descrição breve
                <textarea value={editForm.description} onChange={(event) => updateEditForm("description", event.target.value)} />
              </label>
            </div>
            {editStatus && <small>{editStatus}</small>}
            <footer>
              <button type="button" onClick={closeEditItem}>
                Cancelar
              </button>
              <button type="submit" disabled={isSavingEdit}>
                {isSavingEdit ? "Salvando..." : "Salvar edição"}
              </button>
            </footer>
          </form>
        </StockDialog>
      )}

      {familyEditMeta && (
        <StockDialog mobile={mobile} title="Editar família" onClose={closeFamilyEditor} backdrop="stock-withdraw-backdrop">
          <form className="stock-withdraw-modal stock-family-edit-modal" onSubmit={submitFamilyEdit} onMouseDown={(event) => event.stopPropagation()} onWheelCapture={preventNumberWheel}>
            <header>
              <div>
                <span>{familyEditMeta.category || "Categoria"}</span>
                <strong>Editar família</strong>
              </div>
              <button type="button" onClick={closeFamilyEditor} aria-label="Fechar edição da família">
                <X size={18} />
              </button>
            </header>
            <p>{familyEditMeta.family || "Família"} · {familyEditRows.length} variação(ões)</p>
            <div className="stock-family-edit-list">
              {familyEditRows.map((row) => (
                <div className="stock-family-edit-row" key={row.id}>
                  <input value={row.sku} onChange={(event) => updateFamilyEditRow(row.id, "sku", event.target.value)} title="SKU" placeholder="SKU" />
                  <input value={row.size} onChange={(event) => updateFamilyEditRow(row.id, "size", event.target.value)} title="Tamanho" placeholder="Tam." />
                  <input value={row.color} onChange={(event) => updateFamilyEditRow(row.id, "color", event.target.value)} title="Cor" placeholder="Cor" />
                  <input type="number" min="0" step="0.001" value={row.quantity} onChange={(event) => updateFamilyEditRow(row.id, "quantity", event.target.value)} title="Estoque" placeholder="Qtd" />
                  <input type="number" min="0" step="0.01" value={row.cost_price} onChange={(event) => updateFamilyEditRow(row.id, "cost_price", event.target.value)} title="Preço de compra" placeholder="Compra" />
                </div>
              ))}
            </div>
            {editStatus && <small>{editStatus}</small>}
            <footer>
              <button type="button" onClick={closeFamilyEditor}>
                Cancelar
              </button>
              <button type="submit" disabled={isSavingEdit}>
                {isSavingEdit ? "Salvando..." : "Salvar família"}
              </button>
            </footer>
          </form>
        </StockDialog>
      )}

      {movementItem && (
        <StockDialog mobile={mobile} title="Movimentar estoque" onClose={closeMovementModal} backdrop="stock-withdraw-backdrop">
          <form className="stock-withdraw-modal" onSubmit={submitMovement} onMouseDown={(event) => event.stopPropagation()} onWheelCapture={preventNumberWheel}>
            <header>
              <div>
                <span>{movementItem.kind === "sale" ? "Estoque para venda" : "Estoque interno"}</span>
                <strong>{movementType === "add" ? "Adicionar produto" : "Retirar produto"}</strong>
              </div>
              <button type="button" onClick={closeMovementModal} aria-label="Fechar movimentacao">
                <X size={18} />
              </button>
            </header>
            <p>
              {movementItem.name} · saldo atual {movementItem.quantity} {movementItem.unit}
            </p>
            <label>
              Quantidade em {movementItem.unit}
              <input
                type="number"
                min="0.001"
                step="0.001"
                max={movementType === "withdraw" ? movementItem.quantity : undefined}
                value={movementQuantity}
                onChange={(event) => setMovementQuantity(event.target.value)}
                autoFocus
              />
            </label>
            <label>
              Motivo da movimentacao
              <textarea
                value={movementReason}
                onChange={(event) => setMovementReason(event.target.value)}
                placeholder={movementType === "add" ? "Ex: compra, devolucao, ajuste de saldo..." : "Ex: uso na producao, teste, perda..."}
              />
            </label>
            {movementStatus && <small>{movementStatus}</small>}
            <footer>
              <button type="button" onClick={closeMovementModal}>
                Cancelar
              </button>
              <button type="submit" disabled={isSavingMovement}>
                {isSavingMovement ? "Registrando..." : movementType === "add" ? "Confirmar entrada" : "Confirmar retirada"}
              </button>
            </footer>
          </form>
        </StockDialog>
      )}
    </section>
  );
}

function StockTaxonomyPage({
  categories,
  suppliers,
  status,
  newCategoryName,
  newFamilyNames,
  newSupplier,
  familyCategoryId,
  isSaving,
  onNewCategoryName,
  onNewFamilyName,
  onNewSupplier,
  onFamilyCategoryId,
  onCreateCategory,
  onCreateFamily,
  onCreateSupplier,
  onDeleteCategory,
  onDeleteFamily,
  onDeleteSupplier,
  tenantId,
  onAttributesChanged,
}) {
  const selectedFamilyCategory = categories.find((category) => category.id === familyCategoryId) || categories[0] || null;
  const selectedCategoryId = selectedFamilyCategory?.id || "";
  const flatFamilies = categories.flatMap((category) =>
    (category.families || []).map((family) => ({
      ...family,
      category,
    }))
  );

  return (
    <main className="stock-taxonomy">
      <section className="stock-taxonomy-status">
        <small>{status}</small>
      </section>

      <section className="stock-taxonomy-lists">
        <article className="stock-taxonomy-panel">
          <header>
            <div>
              <strong>Categorias cadastradas</strong>
              <span>{categories.length} no total</span>
            </div>
          </header>
          <form className="stock-taxonomy-inline-form" onSubmit={onCreateCategory}>
            <label>
              Nova categoria
              <input value={newCategoryName} onChange={(event) => onNewCategoryName(event.target.value)} placeholder="Ex: Sacola plastica" />
            </label>
            <button type="submit" disabled={isSaving || !newCategoryName.trim()} title="Criar categoria" aria-label="Criar categoria">
              <Plus size={15} />
            </button>
          </form>
          <div className="stock-taxonomy-list">
            {categories.map((category) => (
              <div className="stock-taxonomy-row" key={category.id}>
                <span>{category.name}</span>
                <button type="button" onClick={() => onDeleteCategory(category)} title="Apagar categoria" aria-label={`Apagar categoria ${category.name}`}>
                  <X size={14} />
                </button>
              </div>
            ))}
            {categories.length === 0 && <p>Nenhuma categoria cadastrada.</p>}
          </div>
        </article>

        <article className="stock-taxonomy-panel">
          <header>
            <div>
              <strong>Famílias cadastradas</strong>
              <span>{flatFamilies.length} no total</span>
            </div>
          </header>
          <form className="stock-taxonomy-inline-form family" onSubmit={(event) => selectedFamilyCategory && onCreateFamily(event, selectedFamilyCategory)}>
            <label>
              Categoria
              <select value={selectedCategoryId} onChange={(event) => onFamilyCategoryId(event.target.value)}>
                {categories.map((category) => (
                  <option key={category.id} value={category.id}>
                    {category.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Nova família
              <input
                value={newFamilyNames[selectedCategoryId] || ""}
                onChange={(event) => onNewFamilyName(selectedCategoryId, event.target.value)}
                placeholder="Ex: Bolsa vazada"
                disabled={!selectedCategoryId}
              />
            </label>
            <button type="submit" disabled={isSaving || !selectedCategoryId || !(newFamilyNames[selectedCategoryId] || "").trim()} title="Criar família" aria-label="Criar família">
              <Plus size={15} />
            </button>
          </form>
          <div className="stock-taxonomy-list">
            {flatFamilies.map((family) => (
              <div className="stock-taxonomy-row family" key={`${family.category.id}:${family.id}`}>
                <span>{family.name}</span>
                <small>{family.category.name}</small>
                <button type="button" onClick={() => onDeleteFamily(family.category, family)} title="Apagar família" aria-label={`Apagar família ${family.name}`}>
                  <X size={14} />
                </button>
              </div>
            ))}
            {flatFamilies.length === 0 && <p>Nenhuma família cadastrada.</p>}
          </div>
        </article>

        <article className="stock-taxonomy-panel">
          <header>
            <div>
              <strong>Fornecedores cadastrados</strong>
              <span>{suppliers.length} no total</span>
            </div>
          </header>
          <form className="stock-taxonomy-inline-form supplier" onSubmit={onCreateSupplier}>
            <label>
              Fornecedor
              <input value={newSupplier.name} onChange={(event) => onNewSupplier("name", event.target.value)} placeholder="Nome do fornecedor" />
            </label>
            <label>
              CNPJ / documento
              <input value={newSupplier.document} onChange={(event) => onNewSupplier("document", event.target.value)} placeholder="Documento do fornecedor" />
            </label>
            <label>
              Contato
              <input value={newSupplier.contact_name} onChange={(event) => onNewSupplier("contact_name", event.target.value)} placeholder="Pessoa de contato" />
            </label>
            <label>
              Telefone
              <input value={newSupplier.phone} onChange={(event) => onNewSupplier("phone", event.target.value)} placeholder="WhatsApp ou telefone" />
            </label>
            <label>
              E-mail
              <input value={newSupplier.email} onChange={(event) => onNewSupplier("email", event.target.value)} placeholder="financeiro@..." />
            </label>
            <label>
              CEP
              <input value={newSupplier.cep} onChange={(event) => onNewSupplier("cep", event.target.value)} />
            </label>
            <label className="wide">
              Endereço
              <input value={newSupplier.address} onChange={(event) => onNewSupplier("address", event.target.value)} />
            </label>
            <label>
              Cidade
              <input value={newSupplier.city} onChange={(event) => onNewSupplier("city", event.target.value)} />
            </label>
            <label>
              UF
              <input value={newSupplier.state} onChange={(event) => onNewSupplier("state", event.target.value)} />
            </label>
            <button type="submit" disabled={isSaving || !newSupplier.name.trim()} title="Criar fornecedor" aria-label="Criar fornecedor">
              <Plus size={15} />
            </button>
          </form>
          <div className="stock-taxonomy-list">
            {suppliers.map((supplier) => (
              <div className="stock-taxonomy-row supplier" key={supplier.id}>
                <span>{supplier.name}</span>
                <small>{[supplier.document, supplier.phone, supplier.city].filter(Boolean).join(" · ") || "Sem dados extras"}</small>
                <button type="button" onClick={() => onDeleteSupplier(supplier)} title="Apagar fornecedor" aria-label={`Apagar fornecedor ${supplier.name}`}>
                  <X size={14} />
                </button>
              </div>
            ))}
            {suppliers.length === 0 && <p>Nenhum fornecedor cadastrado.</p>}
          </div>
        </article>
      </section>
      <StockCategoryAttributes categories={categories} tenantId={tenantId} onChanged={onAttributesChanged} />
    </main>
  );
}

function StockAttributeFields({ categoryName, categories, attributes, onChange, className = "" }) {
  const category = categories.find((item) => item.name === categoryName);
  const definitions = (category?.attributes || []).filter((attribute) => attribute.active !== false);
  if (!categoryName || definitions.length === 0) return null;

  return (
    <fieldset className={`stock-custom-fields ${className}`}>
      <legend>Dados da categoria</legend>
      <div>
        {definitions.map((attribute) => {
          const value = attributes?.[attribute.key] ?? (attribute.type === "boolean" ? false : "");
          if (attribute.type === "boolean") {
            return (
              <label className="stock-custom-check" key={attribute.id}>
                <input type="checkbox" checked={Boolean(value)} onChange={(event) => onChange(attribute.key, event.target.checked)} />
                {attribute.name}{attribute.required ? " *" : ""}
              </label>
            );
          }
          if (attribute.type === "select") {
            return (
              <label key={attribute.id}>
                {attribute.name}{attribute.required ? " *" : ""}
                <select value={value} onChange={(event) => onChange(attribute.key, event.target.value)} required={attribute.required}>
                  <option value="">Não se aplica</option>
                  {(attribute.options || []).map((option) => <option key={option} value={option}>{option}</option>)}
                </select>
              </label>
            );
          }
          return (
            <label key={attribute.id}>
              {attribute.name}{attribute.required ? " *" : ""}
              <input
                type={attribute.type === "number" ? "number" : "text"}
                step={attribute.type === "number" ? "any" : undefined}
                value={value}
                onChange={(event) => onChange(attribute.key, event.target.value)}
                required={attribute.required}
                placeholder="Não se aplica"
              />
            </label>
          );
        })}
      </div>
    </fieldset>
  );
}

function StockTable({ mobile = false, title, description, items, kind, onMovement, onEdit, onEditFamily, onDelete, deletingItemId }) {
  if (mobile) return <StockMobileCards {...{ items, kind, onMovement, onEdit, onEditFamily, onDelete, deletingItemId }} />;
  const hasActions = true;
  return (
    <section className="stock-table-card">
      <header>
        <div>
          <strong>{title}</strong>
          <span>{description}</span>
        </div>
        <b>{items.length}</b>
      </header>
      <div className="stock-table-wrap">
        <table className="stock-table">
          <thead>
            <tr>
              <th>Item</th>
              <th>SKU</th>
              <th>Categoria</th>
              <th>Família</th>
              <th>Tamanho</th>
              <th>Cores</th>
              <th>Qtd</th>
              <th>Min.</th>
              <th>Compra</th>
              <th>{kind === "sale" ? "Fornecedor" : "Local"}</th>
              {hasActions && <th>Acoes</th>}
            </tr>
          </thead>
          <tbody>
            {items.map((item) => (
              <tr key={item.id} className={Number(item.quantity) <= Number(item.min_quantity) ? "low" : ""}>
                <td>
                  <strong>{item.display_name || item.name}</strong>
                  <small>{item.description || item.unit}</small>
                  {Object.keys(item.attributes || {}).length > 0 && <small>{Object.entries(item.attributes).map(([key, value]) => `${key}: ${value === true ? "sim" : value === false ? "não" : value}`).join(" · ")}</small>}
                  {Number(item.quantity) <= Number(item.min_quantity) && <em className="stock-minimum-alert">Estoque minimo</em>}
                </td>
                <td>{item.sku || "-"}</td>
                <td>{item.category || "-"}</td>
                <td>{item.family || "-"}</td>
                <td>{item.size || "-"}</td>
                <td>{(item.colors?.length ? item.colors : item.color ? [item.color] : []).join(", ") || "-"}</td>
                <td>{item.quantity}</td>
                <td>{item.min_quantity}</td>
                <td>{formatMoney(item.cost_price)}</td>
                <td>{kind === "sale" ? item.supplier || "-" : item.location || "-"}</td>
                {hasActions && (
                  <td>
                    <div className="stock-row-actions">
                      <button
                        type="button"
                        className="stock-withdraw-button add"
                        onClick={() => onMovement(item, "add")}
                        title="Adicionar"
                        aria-label={`Adicionar ${item.name}`}
                      >
                        <Plus size={15} />
                      </button>
                      <button
                        type="button"
                        className="stock-withdraw-button"
                        onClick={() => onMovement(item, "withdraw")}
                        title="Retirar"
                        aria-label={`Retirar ${item.name}`}
                      >
                        <Minus size={15} />
                      </button>
                      <button
                        type="button"
                        className="stock-withdraw-button edit"
                        onClick={() => onEdit(item)}
                        title="Editar"
                        aria-label={`Editar ${item.name}`}
                      >
                        <Pencil size={15} />
                      </button>
                      {kind === "sale" && (
                        <button
                          type="button"
                          className="stock-withdraw-button family"
                          onClick={() => onEditFamily(item)}
                          title="Editar família"
                          aria-label={`Editar família ${item.family || item.name}`}
                        >
                          <ListChecks size={15} />
                        </button>
                      )}
                      <button
                        type="button"
                        className="stock-withdraw-button danger"
                        disabled={deletingItemId === item.id}
                        onClick={() => onDelete(item)}
                        title="Apagar"
                        aria-label={`Apagar ${item.name}`}
                      >
                        <X size={15} />
                      </button>
                    </div>
                  </td>
                )}
              </tr>
            ))}
            {items.length === 0 && (
              <tr>
                <td colSpan={hasActions ? 12 : 11} className="stock-empty">Nenhum item encontrado.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function StockServiceResourcesPage({ resources, status, newResource, isSaving, onNewResource, onCreateResource, onUpdateResource, onDeleteResource }) {
  const statusLabels = {
    active: "Ativo",
    maintenance: "Manutencao",
    disabled: "Desabilitado",
  };
  const kindLabels = {
    equipment: "Equipamento",
    space: "Espaco",
    room: "Sala",
    chair: "Cadeira",
    machine: "Maquina",
    other: "Outro",
  };

  return (
    <main className="stock-resources">
      <section className="stock-resource-create">
        <header>
          <div>
            <strong>Novo recurso</strong>
            <span>Cadastre o que limita ou organiza a agenda: sala, cadeira, maca, maquina ou equipamento.</span>
          </div>
        </header>
        <form onSubmit={onCreateResource}>
          <label className="wide">
            Nome do recurso
            <input value={newResource.name} onChange={(event) => onNewResource("name", event.target.value)} placeholder="Ex: Maca sala 1" />
          </label>
          <label>
            Tipo
            <select value={newResource.kind} onChange={(event) => onNewResource("kind", event.target.value)}>
              <option value="equipment">Equipamento</option>
              <option value="space">Espaco</option>
              <option value="room">Sala</option>
              <option value="chair">Cadeira</option>
              <option value="machine">Maquina</option>
              <option value="other">Outro</option>
            </select>
          </label>
          <label>
            Quantidade
            <input type="number" min="1" step="1" value={newResource.quantity} onChange={(event) => onNewResource("quantity", event.target.value)} />
          </label>
          <label>
            Status inicial
            <select value={newResource.status} onChange={(event) => onNewResource("status", event.target.value)}>
              <option value="active">Ativo</option>
              <option value="maintenance">Manutencao</option>
              <option value="disabled">Desabilitado</option>
            </select>
          </label>
          <label>
            Previsao de retorno
            <input type="date" value={newResource.unavailable_until} onChange={(event) => onNewResource("unavailable_until", event.target.value)} />
          </label>
          <label className="wide">
            Observacoes
            <textarea value={newResource.notes} onChange={(event) => onNewResource("notes", event.target.value)} placeholder="Ex: cadeira compartilhada entre corte e barba" />
          </label>
          <button type="submit" disabled={isSaving || !newResource.name.trim()}>
            <Plus size={16} />
            Criar recurso
          </button>
        </form>
      </section>

      <section className="stock-resource-list-card">
        <header>
          <div>
            <strong>Recursos p/ atendimento</strong>
            <span>{resources.length} recurso(s) cadastrado(s)</span>
          </div>
          <small>{status}</small>
        </header>
        <div className="stock-resource-list">
          {resources.map((resource) => (
            <article className={`stock-resource-card ${resource.status}`} key={resource.id}>
              <div className="stock-resource-main">
                <span>{kindLabels[resource.kind] || resource.kind || "Recurso"}</span>
                <strong>{resource.name}</strong>
                <small>
                  {resource.quantity} disponivel(is)
                  {resource.unavailable_until ? ` · retorno ${resource.unavailable_until}` : ""}
                </small>
                {resource.notes && <p>{resource.notes}</p>}
              </div>
              <div className="stock-resource-controls">
                <select value={resource.status} onChange={(event) => onUpdateResource(resource, { status: event.target.value })}>
                  <option value="active">Ativo</option>
                  <option value="maintenance">Manutencao</option>
                  <option value="disabled">Desabilitado</option>
                </select>
                <input
                  type="date"
                  value={resource.unavailable_until || ""}
                  onChange={(event) => onUpdateResource(resource, { unavailable_until: event.target.value })}
                  title="Previsao de retorno"
                />
                <button type="button" className="stock-resource-delete" onClick={() => onDeleteResource(resource)} title="Apagar recurso" aria-label={`Apagar ${resource.name}`}>
                  <X size={15} />
                </button>
              </div>
              <em>{statusLabels[resource.status] || resource.status}</em>
            </article>
          ))}
          {resources.length === 0 && <div className="stock-empty taxonomy">Nenhum recurso encontrado.</div>}
        </div>
      </section>
    </main>
  );
}


function StockDialog({ mobile, title, onClose, backdrop, children }) {
  return mobile ? <MobileDialog title={title} onClose={onClose}><div className="stock-mobile-form">{children}</div></MobileDialog> : <div className={backdrop} role="dialog" aria-modal="true" onMouseDown={onClose}>{children}</div>;
}

function StockMobileCards({ items, kind, onMovement, onEdit, onEditFamily, onDelete, deletingItemId }) {
  return <section className="stock-mobile-list" aria-label="Itens do estoque"><small>{items.length} item(ns) encontrado(s)</small>{!items.length && <p>Nenhum item encontrado.</p>}{items.map(item => <article className="stock-mobile-card" key={item.id}>
    <header><h2>{item.display_name || item.name}</h2><small>{item.sku || "Sem SKU"}</small><p>{[item.size, ...(item.colors?.length ? item.colors : [item.color])].filter(Boolean).join(" · ")}</p></header>
    <dl className="stock-mobile-balance"><div><dt>Saldo disponível</dt><dd>{Number(item.quantity).toLocaleString("pt-BR")} <small>{item.unit}</small></dd></div><div><dt>Estoque mínimo</dt><dd>{Number(item.min_quantity).toLocaleString("pt-BR")} <small>{item.unit}</small></dd></div></dl>
    {Number(item.quantity) <= Number(item.min_quantity) && <span className="stock-mobile-alert">Estoque no mínimo ou abaixo</span>}
    <div className="stock-mobile-actions"><button onClick={() => onMovement(item,"add")}><Plus size={17} />Entrada</button><button onClick={() => onMovement(item,"withdraw")} disabled={Number(item.quantity) <= 0}><Minus size={17} />Saída</button><button onClick={() => onEdit(item)}><Pencil size={17} />Editar</button></div>
    <details><summary>Detalhes do item</summary><dl className="stock-mobile-facts">{[["Categoria",item.category],["Família",item.family],["Custo de compra",formatMoney(item.cost_price)],[kind === "sale" ? "Fornecedor" : "Local",kind === "sale" ? item.supplier : item.location],["Descrição",item.description],["Acabamentos",(item.finishes || []).join(", ")],["Operação",operationProfileLabel(item)],...Object.entries(item.attributes || {}).map(([key,value])=>[key,value === true ? "Sim" : value === false ? "Não" : typeof value === "object" ? JSON.stringify(value) : value])].map(([label,value])=><div key={label}><dt>{label}</dt><dd>{value || "Não informado"}</dd></div>)}</dl>{kind === "sale" && <p className="stock-mobile-note">Os preços de venda e as faixas por quantidade são definidos na Loja.</p>}<div className="stock-mobile-detail-actions">{kind === "sale" && <button onClick={()=>onEditFamily(item)}><ListChecks size={17} />Editar família</button>}<button disabled={deletingItemId === item.id} onClick={()=>onDelete(item)}><Trash2 size={17} />Apagar item</button></div></details>
  </article>)}</section>;
}
