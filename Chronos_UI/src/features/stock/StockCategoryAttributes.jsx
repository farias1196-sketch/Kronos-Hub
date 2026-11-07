import React, { useEffect, useMemo, useState } from "react";
import { Columns3, Plus, Trash2 } from "lucide-react";
import { authFetch } from "../../auth";
import { STOCK_API_URL } from "../../shared/chronosConfig";

const emptyDraft = { name: "", type: "text", role: "information", options: "", required: false };

const typeLabels = { text: "Texto", number: "Número", select: "Lista de opções", boolean: "Sim ou não" };
const roleLabels = {
  information: "Informação",
  variant: "Variação",
  pricing_input: "Referência comercial",
  promotion_tag: "Promoção",
};

export default function StockCategoryAttributes({ categories, tenantId, onChanged }) {
  const [categoryId, setCategoryId] = useState("");
  const [draft, setDraft] = useState(emptyDraft);
  const [status, setStatus] = useState("");
  const [isSaving, setIsSaving] = useState(false);

  useEffect(() => {
    if (!categoryId && categories[0]) setCategoryId(categories[0].id);
    if (categoryId && !categories.some((category) => category.id === categoryId)) setCategoryId(categories[0]?.id || "");
  }, [categories, categoryId]);

  const selectedCategory = useMemo(() => categories.find((category) => category.id === categoryId) || null, [categories, categoryId]);
  const activeAttributes = (selectedCategory?.attributes || []).filter((attribute) => attribute.active !== false);

  function updateDraft(field, value) {
    setDraft((current) => ({ ...current, [field]: value }));
  }

  async function createAttribute(event) {
    event.preventDefault();
    if (!selectedCategory || !draft.name.trim()) return;
    setIsSaving(true);
    setStatus("Criando coluna...");
    try {
      const response = await authFetch(`${STOCK_API_URL}/stock/categories/${selectedCategory.id}/attributes`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          tenant_id: tenantId,
          name: draft.name,
          type: draft.type,
          role: draft.role,
          options: draft.type === "select" ? draft.options.split(",").map((option) => option.trim()).filter(Boolean) : [],
          required: draft.required,
        }),
      });
      const data = await response.json();
      if (!response.ok || !data.ok) throw new Error(data.detail || "Nao foi possivel criar a coluna.");
      setDraft(emptyDraft);
      setStatus(`Coluna criada: ${data.attribute.name}.`);
      onChanged?.();
    } catch (error) {
      setStatus(error.message || "Nao foi possivel criar a coluna.");
    } finally {
      setIsSaving(false);
    }
  }

  async function archiveAttribute(attribute) {
    if (!selectedCategory || !window.confirm(`Desativar a coluna "${attribute.name}"? Produtos já cadastrados não serão apagados.`)) return;
    setIsSaving(true);
    try {
      const response = await authFetch(`${STOCK_API_URL}/stock/categories/${selectedCategory.id}/attributes/${attribute.id}?tenant_id=${encodeURIComponent(tenantId)}`, { method: "DELETE" });
      const data = await response.json();
      if (!response.ok || !data.ok) throw new Error(data.detail || "Nao foi possivel desativar a coluna.");
      setStatus(`Coluna desativada: ${attribute.name}.`);
      onChanged?.();
    } catch (error) {
      setStatus(error.message || "Nao foi possivel desativar a coluna.");
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <section className="stock-attribute-editor">
      <header>
        <div>
          <Columns3 size={20} />
          <div>
            <strong>Colunas da categoria</strong>
            <span>Defina os dados adicionais usados somente nos produtos desta categoria.</span>
          </div>
        </div>
        <select value={categoryId} onChange={(event) => setCategoryId(event.target.value)} aria-label="Categoria para editar colunas">
          {categories.map((category) => <option key={category.id} value={category.id}>{category.name}</option>)}
        </select>
      </header>
      {!selectedCategory ? <p>Crie uma categoria antes de adicionar colunas personalizadas.</p> : (
        <>
          <form onSubmit={createAttribute}>
            <label>
              Nome da coluna
              <input value={draft.name} onChange={(event) => updateDraft("name", event.target.value)} placeholder="Ex: Material" />
            </label>
            <label>
              Tipo
              <select value={draft.type} onChange={(event) => updateDraft("type", event.target.value)}>
                {Object.entries(typeLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
              </select>
            </label>
            <label>
              Uso
              <select value={draft.role} onChange={(event) => updateDraft("role", event.target.value)}>
                {Object.entries(roleLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
              </select>
            </label>
            {draft.type === "select" && (
              <label>
                Opções
                <input value={draft.options} onChange={(event) => updateDraft("options", event.target.value)} placeholder="Algodão, Poliéster, Couro" />
              </label>
            )}
            <label className="stock-attribute-check">
              <input type="checkbox" checked={draft.required} onChange={(event) => updateDraft("required", event.target.checked)} />
              Obrigatória
            </label>
            <button type="submit" disabled={isSaving || !draft.name.trim()}>
              <Plus size={16} />
              Criar coluna
            </button>
          </form>
          <small>{status || "Referência comercial registra uma informação do produto; o preço final é definido na Loja."}</small>
          <div className="stock-attribute-list">
            {activeAttributes.map((attribute) => (
              <div key={attribute.id}>
                <span><b>{attribute.name}</b><small>custom.{attribute.key}</small></span>
                <span>{typeLabels[attribute.type] || attribute.type}</span>
                <span>{roleLabels[attribute.role] || attribute.role}</span>
                <span>{attribute.required ? "Obrigatória" : "Opcional"}</span>
                <button type="button" onClick={() => archiveAttribute(attribute)} title="Desativar coluna" aria-label={`Desativar coluna ${attribute.name}`} disabled={isSaving}>
                  <Trash2 size={15} />
                </button>
              </div>
            ))}
            {activeAttributes.length === 0 && <p>Nenhuma coluna adicional nesta categoria.</p>}
          </div>
        </>
      )}
    </section>
  );
}
