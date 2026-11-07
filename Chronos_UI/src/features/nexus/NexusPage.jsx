import { clientName, clientSecondary } from "../../shared/clientNames";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowLeft, ArrowRight, CalendarDays, CheckCircle2, FileText, GitMerge, KeyRound, ListChecks, Loader2, MessageCircle,
  Pencil, Plus, Search, Trash2, UserPlus, UsersRound, X,
} from "lucide-react";
import { authFetch, isPublicPage } from "../../auth";
import CollapsibleSection from "../../components/ui/CollapsibleSection";
import ContactAvatar from "../../components/ui/ContactAvatar";
import {
  AGENDA_PATH, CORE_API_URL, DEFAULT_CORE_TENANT_SLUG, NEXUS_API_URL, NEXUS_PATH,
} from "../../shared/chronosConfig";
import { formatClientIdentity, formatClientPhone, isLidValue, normalizeSearch } from "../../shared/chatUtils";
import { emptyNexusForm, nexusStatusLabels } from "../../shared/nexusUtils";
import "./nexusMobile.css";
import { RegistrationFields, RegistrationProfileButton } from "./RegistrationProfile";
import { useResource } from "../experience/experienceData";

export default function NexusPage({ currentTenantSlug, mobile = false }) {
  const profile = useResource(`${NEXUS_API_URL}/nexus/registration-profile?empresa_id=${encodeURIComponent(currentTenantSlug)}`);
  const [mobileView, setMobileView] = useState("list");
  const shell = useRef(null);
  const listScroll = useRef(0);
  const [activePanel, setActivePanel] = useState("base");
  const [clients, setClients] = useState([]);
  const [displayPreference, setDisplayPreference] = useState("person");
  const [statusOptions, setStatusOptions] = useState({ conversation: [], order: [], art: [] });
  const [selectedClientId, setSelectedClientId] = useState(null);
  const [form, setForm] = useState(emptyNexusForm);
  const [searchTerm, setSearchTerm] = useState("");
  const [tagFilter, setTagFilter] = useState("");
  const [tags, setTags] = useState([]);
  const [feedback, setFeedback] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [isMergeDialogOpen, setIsMergeDialogOpen] = useState(false);
  const [mergeCandidates, setMergeCandidates] = useState([]);
  const [mergeTargetId, setMergeTargetId] = useState("");

  useEffect(() => {
    if (!mobile) return;
    const body = shell.current?.closest(".mobile-module-body");
    if (body) body.scrollTop = mobileView === "list" ? listScroll.current : 0;
    if (mobileView === "detail") shell.current?.querySelector(".nexus-detail-title")?.focus({ preventScroll: true });
  }, [mobile, mobileView]);

  function openMobileDetail() {
    if (!mobile) return;
    listScroll.current = shell.current?.closest(".mobile-module-body")?.scrollTop || 0;
    setActivePanel("base");
    setMobileView("detail");
  }

  const selectedClient = clients.find((client) => client.id === selectedClientId) || (mobile && selectedClientId ? form : null);
  const registrationLink = form.registration_token
    ? `${window.location.origin}/ChronosNexus/cadastro/${encodeURIComponent(form.registration_token)}`
    : "";

  async function loadNexusData(nextSearch = searchTerm, nextTag = tagFilter) {
    setIsLoading(true);
    try {
      const params = new URLSearchParams({
        empresa_id: currentTenantSlug,
        search: nextSearch,
        tag: nextTag,
      });
      const [clientsResponse, statusResponse, tagsResponse] = await Promise.all([
        authFetch(`${NEXUS_API_URL}/nexus/clients?${params.toString()}`),
        authFetch(`${NEXUS_API_URL}/nexus/status-options`),
        authFetch(`${NEXUS_API_URL}/nexus/tags?empresa_id=${encodeURIComponent(currentTenantSlug)}`),
      ]);
      const clientsData = await clientsResponse.json();
      const statusData = await statusResponse.json();
      const tagsData = await tagsResponse.json();
      const nextClients = clientsData.clients || [];
      setClients(nextClients);
      setDisplayPreference(clientsData.display_preference || "person");
      setStatusOptions(statusData || { conversation: [], order: [], art: [] });
      setTags(tagsData.tags || []);
      if (selectedClientId && !(mobile && mobileView === "detail") && !nextClients.some((client) => client.id === selectedClientId)) {
        setSelectedClientId(null);
      }
    } catch {
      setFeedback("Nexus API indisponivel.");
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => {
    loadNexusData().catch(() => undefined);
  }, [currentTenantSlug]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      loadNexusData(searchTerm, tagFilter).catch(() => undefined);
    }, 250);
    return () => window.clearTimeout(timer);
  }, [searchTerm, tagFilter]);

  function editClient(client) {
    openMobileDetail();
    setSelectedClientId(client.id);
    setForm({
      ...emptyNexusForm,
      ...client,
      tags: (client.tags || []).join(", "),
    });
    setFeedback("");
  }

  function startNewClient() {
    openMobileDetail();
    setSelectedClientId(null);
    setForm(emptyNexusForm);
    setFeedback("");
  }

  function updateForm(field, value) {
    setForm((current) => ({ ...current, [field]: value }));
  }

  async function saveClient(event) {
    event.preventDefault();
    setIsSaving(true);
    setFeedback("");
    try {
      const payload = {
        ...form,
        registration_answers: Object.fromEntries((profile.data?.fields || []).map(field=>[field.id,form.registration_answers?.[field.id] || ""])),
        tags: form.tags
          .split(",")
          .map((tag) => tag.trim())
          .filter(Boolean),
      };
      const response = await authFetch(`${NEXUS_API_URL}/nexus/clients?empresa_id=${encodeURIComponent(currentTenantSlug)}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await response.json();
      if (!response.ok) {
        setFeedback(data.detail || "Nao foi possivel salvar o cliente.");
        return;
      }
      setFeedback("Cliente salvo no Nexus.");
      setSelectedClientId(data.client.id);
      setForm({ ...emptyNexusForm, ...data.client, tags: (data.client.tags || []).join(", ") });
      await loadNexusData();
    } catch {
      setFeedback("Nao foi possivel chamar a Nexus API.");
    } finally {
      setIsSaving(false);
    }
  }

  async function removeSelectedClient() {
    if (!selectedClientId) return;
    setIsSaving(true);
    try {
      await authFetch(
        `${NEXUS_API_URL}/nexus/clients/${encodeURIComponent(selectedClientId)}?empresa_id=${encodeURIComponent(currentTenantSlug)}`,
        { method: "DELETE" }
      );
      setFeedback("Cliente removido.");
      startNewClient();
      if (mobile) setMobileView("list");
      await loadNexusData();
    } catch {
      setFeedback("Nao foi possivel remover o cliente.");
    } finally {
      setIsSaving(false);
    }
  }

  async function openMergeDialog() {
    if (!selectedClientId) return;
    setIsSaving(true);
    setFeedback("");
    try {
      const response = await authFetch(`${NEXUS_API_URL}/nexus/clients?empresa_id=${encodeURIComponent(currentTenantSlug)}`);
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Nao foi possivel carregar os clientes.");
      const candidates = (data.clients || []).filter((client) => client.id !== selectedClientId);
      setMergeCandidates(candidates);
      setMergeTargetId(candidates[0]?.id || "");
      setIsMergeDialogOpen(true);
    } catch (error) {
      setFeedback(error.message || "Nao foi possivel abrir a mesclagem.");
    } finally {
      setIsSaving(false);
    }
  }

  async function mergeSelectedClient() {
    if (!selectedClientId || !mergeTargetId) return;
    const target = mergeCandidates.find((client) => client.id === mergeTargetId);
    if (!target) return;
    setIsSaving(true);
    setFeedback("");
    try {
      const response = await authFetch(
        `${NEXUS_API_URL}/nexus/clients/${encodeURIComponent(mergeTargetId)}/merge?empresa_id=${encodeURIComponent(currentTenantSlug)}`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ duplicate_client_id: selectedClientId }),
        }
      );
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Nao foi possivel mesclar os clientes.");
      setIsMergeDialogOpen(false);
      setSelectedClientId(data.client.id);
      setForm({ ...emptyNexusForm, ...data.client, tags: (data.client.tags || []).join(", ") });
      setFeedback(`${selectedClient?.name || "Cadastro"} foi mesclado em ${data.client.name}.`);
      await loadNexusData();
    } catch (error) {
      setFeedback(error.message || "Nao foi possivel mesclar os clientes.");
    } finally {
      setIsSaving(false);
    }
  }

  function renderStatusSelect(field, options) {
    return (
      <label className="nexus-field">
        <span>{field === "conversation_status" ? "Conversa" : field === "order_status" ? "Pedido" : "Arte"}</span>
        <select value={form[field]} onChange={(event) => updateForm(field, event.target.value)}>
          {options.map((option) => (
            <option key={option} value={option}>
              {nexusStatusLabels[option] || option}
            </option>
          ))}
        </select>
      </label>
    );
  }

  const boards = [
    ["Andamento da conversa", "conversation_status", statusOptions.conversation || []],
    ["Andamento do pedido", "order_status", statusOptions.order || []],
    ["Andamento da arte", "art_status", statusOptions.art || []],
  ];

  return (
    <section ref={shell} className={`nexus-shell${mobile ? " nexus-mobile" : ""}`}>
      {(!mobile || mobileView === "list") && <aside className="nexus-sidebar">
        <header className="nexus-header">
          <div>
            <span>Chronos Nexus</span>
            <h1>Clientes</h1>
          </div>
          <RegistrationProfileButton tenant={currentTenantSlug} onSaved={profile.reload} />
          <button type="button" onClick={startNewClient} title="Novo cliente" aria-label="Novo cliente">
            <Plus size={18} />
            {mobile && "Novo"}
          </button>
        </header>

        <label className="search-box nexus-search">
          <Search size={17} />
          <input
            value={searchTerm}
            onChange={(event) => setSearchTerm(event.target.value)}
            placeholder="Buscar cliente, telefone, CPF ou CNPJ"
            aria-label="Buscar clientes"
          />
        </label>

        <select className="nexus-tag-filter" aria-label="Filtrar por tag" value={tagFilter} onChange={(event) => setTagFilter(event.target.value)}>
          <option value="">Todas as tags</option>
          {tags.map((tag) => (
            <option key={tag} value={tag}>
              {tag}
            </option>
          ))}
        </select>

        {mobile && <p className="nexus-list-caption">{clients.length} {clients.length === 1 ? "cliente" : "clientes"} · Toque para abrir o cadastro</p>}
        <div className="nexus-client-list">
          {clients.map((client) => (
            <button
              key={client.id}
              type="button"
              className={`nexus-client-row ${client.id === selectedClientId ? "active" : ""}`}
              onClick={() => editClient(client)}
            >
              <ContactAvatar name={clientName(client, displayPreference)} src={`${NEXUS_API_URL}/nexus/clients/${encodeURIComponent(client.id)}/avatar?empresa_id=${encodeURIComponent(currentTenantSlug)}`} />
              <strong>{clientName(client, displayPreference)}</strong>{clientSecondary(client, displayPreference) && <small>{clientSecondary(client, displayPreference)}</small>}
              <small>{formatClientPhone(client)}</small>
              <em>{nexusStatusLabels[client.registration_status] || client.registration_status || "Pre-cadastro"}</em>
            </button>
          ))}
          {!isLoading && clients.length === 0 && <p className="core-empty">Nenhum cliente cadastrado.</p>}
          {isLoading && <p className="core-empty">Carregando clientes...</p>}
        </div>
      </aside>}

      {(!mobile || mobileView === "detail") && <section className="nexus-detail">
        {mobile && <div className="nexus-mobile-toolbar">
          <button type="button" onClick={() => setMobileView("list")}><ArrowLeft size={18} />Clientes</button>
          <button type="submit" form="nexus-client-form" disabled={isSaving}>{isSaving ? "Salvando..." : "Salvar"}</button>
        </div>}
        <header className="nexus-detail-header">
          <div className="nexus-client-identity">
            <ContactAvatar name={clientName(form, displayPreference)} src={selectedClientId ? `${NEXUS_API_URL}/nexus/clients/${encodeURIComponent(selectedClientId)}/avatar?empresa_id=${encodeURIComponent(currentTenantSlug)}` : null} />
            <div>
            <span>{selectedClient ? "Editando cliente" : "Novo cadastro"}</span>
            <h2 className="nexus-detail-title" tabIndex={mobile ? -1 : undefined}>{clientName(form, displayPreference)}</h2>
            </div>
          </div>
          {mobile && selectedClientId && <details className="nexus-mobile-actions"><summary>Mais ações</summary><div className="nexus-header-actions">
            <button type="button" onClick={openMergeDialog} disabled={isSaving}><GitMerge size={16} />Mesclar</button>
            <button type="button" className="nexus-danger" onClick={removeSelectedClient} disabled={isSaving}><Trash2 size={16} />Apagar</button>
          </div></details>}
          {!mobile && <div className="nexus-header-actions">
            {selectedClientId && (
              <button type="button" className="nexus-merge-button" onClick={openMergeDialog} disabled={isSaving}>
                <GitMerge size={16} />
                Mesclar
              </button>
            )}
            {selectedClientId && (
              <button type="button" className="nexus-danger" onClick={removeSelectedClient} disabled={isSaving}>
                <Trash2 size={16} />
                Apagar
              </button>
            )}
            <button type="submit" form="nexus-client-form" disabled={isSaving}>
              {isSaving ? "Salvando..." : "Salvar"}
            </button>
          </div>}
        </header>

        {mobile && feedback && <p className="nexus-feedback" role="status">{feedback}</p>}
        {!mobile && <div className="nexus-board">
          {boards.map(([title, field]) => (
            <div className="nexus-status-card" key={field}>
              <ListChecks size={18} />
              <span>{title}</span>
              <strong>{nexusStatusLabels[form[field]] || form[field]}</strong>
              <small>{clients.filter((client) => client[field] === form[field]).length} neste status</small>
            </div>
          ))}
        </div>}

        {registrationLink && (
          <div className="nexus-registration-link">
            <KeyRound size={18} />
            <span>{registrationLink}</span>
            <button type="button" onClick={() => navigator.clipboard?.writeText(registrationLink)}>
              Copiar link
            </button>
          </div>
        )}

        <form id="nexus-client-form" className="nexus-form" onSubmit={saveClient}>
        <RegistrationFields fields={profile.data?.fields} values={form.registration_answers} onChange={values=>updateForm("registration_answers",values)} />

          <CollapsibleSection
            className="nexus-panel"
            title="Cadastro base"
            description="Nome, telefone, documento e os dados principais do cliente."
            summary="Identificação e contato"
            open={activePanel === "base"}
            onOpenChange={(isOpen) => setActivePanel(isOpen ? "base" : null)}
          >
            <div className="nexus-form-grid">
              <label className="nexus-field">
                <span>Nome do cliente</span>
                <input value={form.name} onChange={(event) => updateForm("name", event.target.value)} required />
              </label>
              <label className="nexus-field">
                <span>Numero do cliente</span>
                <input type="tel" value={form.phone} onChange={(event) => updateForm("phone", event.target.value)} required />
              </label>
              {form.whatsapp_lid && (
                <label className="nexus-field">
                  <span>Identificador WhatsApp</span>
                  <input value={`LID interno: ${form.whatsapp_lid}`} readOnly />
                </label>
              )}
              <label className="nexus-field">
                <span>CPF ou CNPJ</span>
                <input value={form.fiscal_document} onChange={(event) => updateForm("fiscal_document", event.target.value)} />
              </label>
              <label className="nexus-field">
                <span>Nome da empresa</span>
                <input value={form.company_name} onChange={(event) => updateForm("company_name", event.target.value)} />
              </label>
              <label className="nexus-field">
                <span>E-mail</span>
                <input type="email" value={form.email} onChange={(event) => updateForm("email", event.target.value)} />
              </label>
              <label className="nexus-field">
                <span>Origem</span>
                <input value={form.source} onChange={(event) => updateForm("source", event.target.value)} />
              </label>
              <label className="nexus-field">
                <span>Status do cadastro</span>
                <select value={form.registration_status} onChange={(event) => updateForm("registration_status", event.target.value)}>
                  <option value="pre-cadastro">Pre-cadastro</option>
                  <option value="cadastro-completo">Cadastro completo</option>
                </select>
              </label>
              <label className="nexus-field">
                <span>Vendedor</span>
                <input value={form.assigned_seller_name} onChange={(event) => updateForm("assigned_seller_name", event.target.value)} />
              </label>
            </div>
          </CollapsibleSection>

          <CollapsibleSection
            className="nexus-panel"
            title="Endereço"
            description="Informações usadas para entrega, atendimento e cadastro completo."
            summary="Localização e entrega"
            open={activePanel === "address"}
            onOpenChange={(isOpen) => setActivePanel(isOpen ? "address" : null)}
          >
            <div className="nexus-form-grid address">
              <label className="nexus-field">
                <span>CEP</span>
                <input value={form.cep} onChange={(event) => updateForm("cep", event.target.value)} />
              </label>
              <label className="nexus-field wide">
                <span>Endereco</span>
                <input value={form.address_street} onChange={(event) => updateForm("address_street", event.target.value)} />
              </label>
              <label className="nexus-field">
                <span>Numero</span>
                <input value={form.address_number} onChange={(event) => updateForm("address_number", event.target.value)} />
              </label>
              <label className="nexus-field">
                <span>Complemento</span>
                <input value={form.address_complement} onChange={(event) => updateForm("address_complement", event.target.value)} />
              </label>
              <label className="nexus-field">
                <span>Bairro</span>
                <input value={form.address_neighborhood} onChange={(event) => updateForm("address_neighborhood", event.target.value)} />
              </label>
              <label className="nexus-field">
                <span>Cidade</span>
                <input value={form.address_city} onChange={(event) => updateForm("address_city", event.target.value)} />
              </label>
              <label className="nexus-field">
                <span>UF</span>
                <input value={form.address_state} onChange={(event) => updateForm("address_state", event.target.value)} />
              </label>
            </div>
          </CollapsibleSection>

          <CollapsibleSection
            className="nexus-panel"
            title="Status e tags"
            description="Etapas do atendimento, pedido, arte e etiquetas usadas no Zap e Flow."
            summary="Fluxo comercial"
            open={activePanel === "status"}
            onOpenChange={(isOpen) => setActivePanel(isOpen ? "status" : null)}
          >
            <div className="nexus-form-grid">
              {renderStatusSelect("conversation_status", statusOptions.conversation || [])}
              {renderStatusSelect("order_status", statusOptions.order || [])}
              {renderStatusSelect("art_status", statusOptions.art || [])}
              <label className="nexus-field wide">
                <span>Tags para Zap e Flow</span>
                <input
                  value={form.tags}
                  onChange={(event) => updateForm("tags", event.target.value)}
                  placeholder="orcamento, arte, urgente"
                />
              </label>
              <label className="nexus-field wide">
                <span>Observacoes</span>
                <textarea value={form.notes} onChange={(event) => updateForm("notes", event.target.value)} />
              </label>
            </div>
          </CollapsibleSection>
        </form>

        {mobile && selectedClientId && <CollapsibleSection className="nexus-panel nexus-mobile-status" title="Resumo do atendimento" summary="Conversa, pedido e arte">
          <div className="nexus-board">{boards.map(([title, field]) => <div className="nexus-status-card" key={field}>
            <ListChecks size={18} /><span>{title}</span><strong>{nexusStatusLabels[form[field]] || form[field]}</strong>
            <small>{clients.filter((client) => client[field] === form[field]).length} neste status</small>
          </div>)}</div>
        </CollapsibleSection>}
        {!mobile && feedback && <small className="nexus-feedback" role="status">{feedback}</small>}
      </section>}

      {isMergeDialogOpen && selectedClient && (
        <div className="nexus-merge-backdrop" role="presentation" onPointerDown={(event) => { if (event.target === event.currentTarget) setIsMergeDialogOpen(false); }}>
          <section className="nexus-merge-dialog" role="dialog" aria-modal="true" aria-labelledby="nexus-merge-title">
            <header>
              <div>
                <span>Mesclagem manual</span>
                <h2 id="nexus-merge-title">Escolha o cliente principal</h2>
              </div>
              <button type="button" onClick={() => setIsMergeDialogOpen(false)} aria-label="Fechar"><X size={18} /></button>
            </header>
            <p><strong>{clientName(selectedClient, displayPreference)}</strong> sera mantido como cadastro vinculado e deixara de aparecer na lista normal.</p>
            <label className="nexus-field">
              <span>Cliente principal</span>
              <select value={mergeTargetId} onChange={(event) => setMergeTargetId(event.target.value)}>
                {mergeCandidates.map((client) => (
                  <option value={client.id} key={client.id}>{clientName(client, displayPreference)} · {clientSecondary(client, displayPreference)} · {formatClientPhone(client)}</option>
                ))}
              </select>
            </label>
            {mergeCandidates.length === 0 ? (
              <small>Nao ha outro cliente disponivel para mesclar.</small>
            ) : (
              <button type="button" className="nexus-merge-confirm" onClick={mergeSelectedClient} disabled={isSaving || !mergeTargetId}>
                <GitMerge size={17} />
                {isSaving ? "Mesclando..." : "Mesclar no cliente escolhido"}
              </button>
            )}
          </section>
        </div>
      )}
    </section>
  );
}

export function NexusPublicRegistrationPage({ token }) {
  const [fields,setFields]=useState([]);
  const [form, setForm] = useState({
    name: "",
    fiscal_document: "",
    company_name: "",
    email: "",
    cep: "",
    address_street: "",
    address_number: "",
    address_complement: "",
    address_neighborhood: "",
    address_city: "",
    address_state: "",
    notes: "",
  });
  const [phone, setPhone] = useState("");
  const [status, setStatus] = useState("loading");
  const [feedback, setFeedback] = useState("");

  useEffect(() => {
    async function loadPublicRegistration() {
      try {
        const response = await authFetch(`${NEXUS_API_URL}/nexus/public-registration/${encodeURIComponent(token)}`);
        const data = await response.json();
        if (!response.ok) {
          setStatus("invalid");
          setFeedback(data.detail || "Link de cadastro invalido.");
          return;
        }
        setFields(data.fields || []);
        setForm((current) => ({ ...current, ...(data.client || {}) }));
        setPhone(data.client?.phone || "");
        setStatus("ready");
      } catch {
        setStatus("invalid");
        setFeedback("Nao foi possivel abrir este cadastro.");
      }
    }
    loadPublicRegistration();
  }, [token]);

  function updatePublicForm(field, value) {
    setForm((current) => ({ ...current, [field]: value }));
  }

  async function submitPublicRegistration(event) {
    event.preventDefault();
    setStatus("saving");
    setFeedback("");
    try {
      const response = await authFetch(`${NEXUS_API_URL}/nexus/public-registration/${encodeURIComponent(token)}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({...form, registration_answers:Object.fromEntries(fields.map(field=>[field.id,form.registration_answers?.[field.id] || ""]))}),
      });
      const data = await response.json();
      if (!response.ok) {
        setFeedback(data.detail || "Nao foi possivel concluir o cadastro.");
        setStatus("ready");
        return;
      }
      setPhone(data.client?.phone || phone);
      setStatus("completed");
    } catch {
      setFeedback("Nao foi possivel enviar o cadastro.");
      setStatus("ready");
    }
  }

  if (status === "loading") {
    return (
      <section className="nexus-public-page">
        <Loader2 className="spin" size={36} />
        <strong>Carregando cadastro...</strong>
      </section>
    );
  }

  if (status === "invalid") {
    return (
      <section className="nexus-public-page">
        <X size={38} />
        <strong>Link indisponivel</strong>
        <span>{feedback}</span>
      </section>
    );
  }

  if (status === "completed") {
    return (
      <section className="nexus-public-page">
        <CheckCircle2 size={42} />
        <strong>Cadastro recebido</strong>
        <span>Obrigado. Seus dados foram vinculados ao atendimento.</span>
      </section>
    );
  }

  return (
    <section className="nexus-public-page">
      <form className="nexus-public-form" onSubmit={submitPublicRegistration}>
        <header>
          <span>Chronos Nexus</span>
          <h1>Complete seu cadastro</h1>
          <small>Cadastro vinculado ao seu atendimento.</small>
        </header>
        <div className="nexus-form-grid">
          <label className="nexus-field">
            <span>Nome</span>
            <input value={form.name} onChange={(event) => updatePublicForm("name", event.target.value)} required />
          </label>
          <label className="nexus-field"><span>Telefone do atendimento</span><input type="tel" readOnly value={phone} /></label>
          <label className="nexus-field">
            <span>CPF ou CNPJ</span>
            <input value={form.fiscal_document || ""} onChange={(event) => updatePublicForm("fiscal_document", event.target.value)} />
          </label>
          <label className="nexus-field">
            <span>Empresa</span>
            <input value={form.company_name || ""} onChange={(event) => updatePublicForm("company_name", event.target.value)} />
          </label>
          <label className="nexus-field">
            <span>E-mail</span>
            <input type="email" value={form.email || ""} onChange={(event) => updatePublicForm("email", event.target.value)} />
          </label>
          <label className="nexus-field">
            <span>CEP</span>
            <input value={form.cep || ""} onChange={(event) => updatePublicForm("cep", event.target.value)} />
          </label>
          <label className="nexus-field wide">
            <span>Endereco</span>
            <textarea rows={3} value={form.address_street || ""} onChange={(event) => updatePublicForm("address_street", event.target.value)} />
          </label>
          <label className="nexus-field">
            <span>Numero</span>
            <input value={form.address_number || ""} onChange={(event) => updatePublicForm("address_number", event.target.value)} />
          </label>
          <label className="nexus-field">
            <span>Complemento</span>
            <textarea rows={3} value={form.address_complement || ""} onChange={(event) => updatePublicForm("address_complement", event.target.value)} />
          </label>
          <label className="nexus-field">
            <span>Bairro</span>
            <input value={form.address_neighborhood || ""} onChange={(event) => updatePublicForm("address_neighborhood", event.target.value)} />
          </label>
          <label className="nexus-field">
            <span>Cidade</span>
            <input value={form.address_city || ""} onChange={(event) => updatePublicForm("address_city", event.target.value)} />
          </label>
          <label className="nexus-field">
            <span>UF</span>
            <input value={form.address_state || ""} onChange={(event) => updatePublicForm("address_state", event.target.value)} />
          </label>
          <label className="nexus-field wide">
            <span>Observacoes</span>
            <textarea value={form.notes || ""} onChange={(event) => updatePublicForm("notes", event.target.value)} />
          </label>
        </div>
        <RegistrationFields fields={fields} values={form.registration_answers} onChange={values=>updatePublicForm("registration_answers",values)} enforceRequired />
        {feedback && <small className="nexus-feedback">{feedback}</small>}
        <button type="submit" disabled={status === "saving"}>
          {status === "saving" ? "Enviando..." : "Enviar cadastro"}
        </button>
      </form>
    </section>
  );
}
