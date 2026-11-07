import PdfHeaderSetting from "../loja/PdfHeaderSetting";
import ClientDisplaySetting from "../nexus/ClientDisplaySetting";
import QuoteValidity from "../loja/QuoteValidity";
import { useEffect, useState } from "react";
import { CheckCircle2, CreditCard, FileText, Image, KeyRound, Loader2, Power, UserPlus, UsersRound } from "lucide-react";
import { authFetch, logout } from "../../auth";
import AuthenticatedImage from "../../AuthenticatedImage";
import CompanyExperiencePreference from "../../components/ui/CompanyExperiencePreference";
import CollapsibleSection from "../../components/ui/CollapsibleSection";
import { CORE_API_URL } from "../../shared/chronosConfig";
import { CoreField, CoreReadonly } from "./CoreFields";
import { chronosThemes } from "../../themeConfig";
import {
  buildCoreAssetUrl, buildFiscalForm, buildMemberForm, formatAuditAction,
  formatDateTime, formatMoney, formatRole, formatUserStatus,
} from "./coreUtils";

export default function CorePage({ currentTenantSlug, onTenantLoaded, onThemePreview }) {
  const [selectedTenant, setSelectedTenant] = useState(null);
  const [fiscalForm, setFiscalForm] = useState({});
  const [memberForm, setMemberForm] = useState(buildMemberForm());
  const [memberPasswords, setMemberPasswords] = useState({});
  const [auditLogs, setAuditLogs] = useState([]);
  const [status, setStatus] = useState("loading");
  const [error, setError] = useState("");
  const [saveFeedback, setSaveFeedback] = useState("");
  const [memberFeedback, setMemberFeedback] = useState("");
  const [isSavingFiscal, setIsSavingFiscal] = useState(false);
  const [isSavingTheme, setIsSavingTheme] = useState(false);
  const [isSavingMember, setIsSavingMember] = useState(false);
  const [isUploadingLogo, setIsUploadingLogo] = useState(false);

  async function loadCore() {
    setStatus("loading");
    setError("");
    try {
      const response = await authFetch(`${CORE_API_URL}/core/tenants/${encodeURIComponent(currentTenantSlug)}`);
      if (!response.ok) throw new Error("Empresa nao encontrada.");
      const data = await response.json();
      setSelectedTenant(data.tenant || null);
      setFiscalForm(buildFiscalForm(data.tenant || {}));
      onTenantLoaded?.(data.tenant || null);
      loadAuditLogs(currentTenantSlug).catch(() => setAuditLogs([]));
      setStatus("ready");
    } catch {
      setStatus("error");
      setSelectedTenant(null);
      setError("Nao foi possivel carregar os dados da sua empresa.");
    }
  }

  useEffect(() => {
    loadCore();
  }, [currentTenantSlug]);

  async function loadAuditLogs(slug = currentTenantSlug) {
    const response = await authFetch(`${CORE_API_URL}/core/tenants/${encodeURIComponent(slug)}/audit?limit=30`);
    if (!response.ok) return;
    const data = await response.json();
    setAuditLogs(data.logs || []);
  }

  async function uploadLogo(file) {
    if (!file || isUploadingLogo) return;
    setIsUploadingLogo(true);
    setError("");
    try {
      const form = new FormData();
      form.append("file", file);
      const response = await authFetch(`${CORE_API_URL}/core/tenants/${encodeURIComponent(currentTenantSlug)}/logo`, {
        method: "POST",
        body: form,
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Nao foi possivel salvar a logo.");
      setSelectedTenant(data.tenant || null);
      setFiscalForm(buildFiscalForm(data.tenant || {}));
      onTenantLoaded?.(data.tenant || null);
      loadAuditLogs().catch(() => undefined);
    } catch (err) {
      setError(err.message || "Nao foi possivel salvar a logo.");
    } finally {
      setIsUploadingLogo(false);
    }
  }

  async function saveFiscalData() {
    if (isSavingFiscal) return;
    setIsSavingFiscal(true);
    setSaveFeedback("");
    setError("");
    try {
      const response = await authFetch(`${CORE_API_URL}/core/tenants/${encodeURIComponent(currentTenantSlug)}/fiscal`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(fiscalForm),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Nao foi possivel salvar os dados.");
      setSelectedTenant(data.tenant || null);
      setFiscalForm(buildFiscalForm(data.tenant || {}));
      onTenantLoaded?.(data.tenant || null);
      setSaveFeedback("Dados da empresa salvos.");
      loadAuditLogs().catch(() => undefined);
    } catch (err) {
      setError(err.message || "Nao foi possivel salvar os dados.");
    } finally {
      setIsSavingFiscal(false);
    }
  }

  async function saveTheme(themeSlug) {
    if (isSavingTheme || themeSlug === selectedTenant?.theme_slug) return;

    const previousTheme = selectedTenant?.theme_slug || "rosa-branco";
    setFiscalForm((current) => ({ ...current, theme_slug: themeSlug }));
    onThemePreview?.(themeSlug);
    setIsSavingTheme(true);
    setSaveFeedback("");
    setError("");
    try {
      const response = await authFetch(`${CORE_API_URL}/core/tenants/${encodeURIComponent(currentTenantSlug)}/fiscal`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ theme_slug: themeSlug }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Nao foi possivel salvar a paleta.");
      if (data.tenant?.theme_slug !== themeSlug) {
        throw new Error("O Core local ainda nao reconhece a paleta selecionada. Reinicie o Core API no ADM > Servicos.");
      }
      setSelectedTenant(data.tenant);
      setFiscalForm(buildFiscalForm(data.tenant));
      onTenantLoaded?.(data.tenant);
      setSaveFeedback("Paleta da empresa salva.");
      loadAuditLogs().catch(() => undefined);
    } catch (err) {
      setFiscalForm((current) => ({ ...current, theme_slug: previousTheme }));
      onThemePreview?.(previousTheme);
      setError(err.message || "Nao foi possivel salvar a paleta.");
    } finally {
      setIsSavingTheme(false);
    }
  }

  async function addMember() {
    if (isSavingMember) return;
    setIsSavingMember(true);
    setMemberFeedback("");
    setError("");
    try {
      const response = await authFetch(`${CORE_API_URL}/core/tenants/${encodeURIComponent(currentTenantSlug)}/members`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(memberForm),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Nao foi possivel adicionar o membro.");
      setSelectedTenant(data.tenant || null);
      onTenantLoaded?.(data.tenant || null);
      setMemberForm(buildMemberForm());
      setMemberFeedback(memberForm.temporary_password ? "Membro criado com senha provisoria." : "Convite criado para o membro.");
      loadAuditLogs().catch(() => undefined);
    } catch (err) {
      setError(err.message || "Nao foi possivel adicionar o membro.");
    } finally {
      setIsSavingMember(false);
    }
  }

  async function updateMemberPassword(memberId) {
    const password = memberPasswords[memberId] || "";
    if (!password) return;
    setMemberFeedback("");
    setError("");
    try {
      const response = await authFetch(
        `${CORE_API_URL}/core/tenants/${encodeURIComponent(currentTenantSlug)}/members/${encodeURIComponent(memberId)}/password`,
        {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ password }),
        }
      );
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Nao foi possivel trocar a senha.");
      setSelectedTenant(data.tenant || null);
      onTenantLoaded?.(data.tenant || null);
      setMemberPasswords((current) => ({ ...current, [memberId]: "" }));
      setMemberFeedback("Senha provisoria atualizada. O membro devera trocar no acesso.");
      loadAuditLogs().catch(() => undefined);
    } catch (err) {
      setError(err.message || "Nao foi possivel trocar a senha.");
    }
  }

  async function toggleMember(member, active) {
    setMemberFeedback("");
    setError("");
    try {
      const response = await authFetch(
        `${CORE_API_URL}/core/tenants/${encodeURIComponent(currentTenantSlug)}/members/${encodeURIComponent(member.id)}/status`,
        {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ active }),
        }
      );
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Nao foi possivel alterar o status.");
      setSelectedTenant(data.tenant || null);
      onTenantLoaded?.(data.tenant || null);
      setMemberFeedback(active ? "Membro ativado." : "Membro desativado.");
      loadAuditLogs().catch(() => undefined);
    } catch (err) {
      setError(err.message || "Nao foi possivel alterar o status.");
    }
  }

  async function prepareCurrentInvoice() {
    setSaveFeedback("");
    setError("");
    try {
      const response = await authFetch(`${CORE_API_URL}/core/tenants/${encodeURIComponent(currentTenantSlug)}/billing/prepare-current`, {
        method: "POST",
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Nao foi possivel preparar a fatura.");
      setSelectedTenant(data.tenant || null);
      onTenantLoaded?.(data.tenant || null);
      setSaveFeedback("Fatura mensal preparada.");
      loadAuditLogs().catch(() => undefined);
    } catch (err) {
      setError(err.message || "Nao foi possivel preparar a fatura.");
    }
  }

  return (
    <section className="core-shell">
      <aside className="core-company-panel mine-only">
        <header className="core-header">
          <div>
            <span>Chronos Core</span>
            <h1>Minha empresa</h1>
          </div>
          <button type="button" onClick={loadCore} aria-label="Atualizar Core">
            <Loader2 className={status === "loading" ? "spin" : ""} size={18} />
          </button>
        </header>

        <div className="core-summary-grid">
          <CoreMetric label="equipe" value={selectedTenant?.members?.length ?? "-"} />
          <CoreMetric label="modulos" value={selectedTenant?.modules?.length ?? "-"} />
          <CoreMetric label="status" value={selectedTenant?.status ?? "-"} />
          <CoreMetric label="ia semanal" value={selectedTenant?.subscription?.ai_weekly_credits ?? 0} />
        </div>

        <div className="core-company-card">
          {selectedTenant ? (
            <>
              <span className="core-company-avatar">
                {(selectedTenant.trade_name || selectedTenant.name || "?").slice(0, 2).toUpperCase()}
              </span>
              <strong>{selectedTenant.trade_name || selectedTenant.name}</strong>
              <small>{selectedTenant.email || "Sem e-mail"}</small>
              <small>{selectedTenant.subscription?.package_name || "Sem plano de IA vinculado"}</small>
              <button type="button" onClick={logout}>
                Login / trocar empresa
              </button>
            </>
          ) : (
            <small className={status === "error" ? "core-error" : "core-empty"}>
              {status === "error" ? error : "Carregando sua empresa..."}
            </small>
          )}
        </div>
        <CompanyExperiencePreference tenant={selectedTenant} slug={currentTenantSlug} onSaved={tenant => { setSelectedTenant(tenant); onTenantLoaded?.(tenant); }} />
      </aside>

      <CoreTenantDetail
        error={error}
        fiscalForm={fiscalForm}
        memberFeedback={memberFeedback}
        memberForm={memberForm}
        memberPasswords={memberPasswords}
        auditLogs={auditLogs}
        isUploadingLogo={isUploadingLogo}
        isSavingMember={isSavingMember}
        isSavingFiscal={isSavingFiscal}
        isSavingTheme={isSavingTheme}
        onAddMember={addMember}
        onUploadLogo={uploadLogo}
        onChangeFiscalField={(field, value) =>
          setFiscalForm((current) => ({
            ...current,
            [field]: value,
          }))
        }
        onChangeMemberField={(field, value) =>
          setMemberForm((current) => ({
            ...current,
            [field]: value,
          }))
        }
        onChangeMemberPassword={(memberId, value) =>
          setMemberPasswords((current) => ({
            ...current,
            [memberId]: value,
          }))
        }
        onToggleMember={toggleMember}
        onUpdateMemberPassword={updateMemberPassword}
        onPrepareCurrentInvoice={prepareCurrentInvoice}
        onSaveFiscal={saveFiscalData}
        onSelectTheme={saveTheme}
        saveFeedback={saveFeedback}
        tenant={selectedTenant}
      />
    </section>
  );
}

function CoreMetric({ label, value }) {
  return (
    <div className="core-metric">
      <strong>{value}</strong>
      <span>{label}</span>
    </div>
  );
}

function CoreTenantDetail({
  tenant,
  error,
  fiscalForm,
  memberFeedback,
  memberForm,
  memberPasswords,
  auditLogs,
  isSavingMember,
  isUploadingLogo,
  isSavingFiscal,
  isSavingTheme,
  onAddMember,
  onChangeFiscalField,
  onChangeMemberField,
  onChangeMemberPassword,
  onSaveFiscal,
  onSelectTheme,
  onToggleMember,
  onUpdateMemberPassword,
  onPrepareCurrentInvoice,
  onUploadLogo,
  saveFeedback,
}) {
  const [activePanel, setActivePanel] = useState(null);

  if (!tenant) {
    return (
      <section className="core-detail empty">
        <UsersRound size={48} />
        <strong>Selecione uma empresa</strong>
        <span>Os dados centrais da empresa aparecem aqui.</span>
      </section>
    );
  }

  return (
    <section className="core-detail">
      <header className="core-detail-header">
        <div className="core-logo-preview">
          {tenant.logo_url ? (
            <img src={buildCoreAssetUrl(tenant.logo_url)} alt="" />
          ) : (
            <span>{(tenant.trade_name || tenant.name).slice(0, 2).toUpperCase()}</span>
          )}
        </div>
        <div>
          <span>{tenant.slug}</span>
          <h2>{tenant.trade_name || tenant.name}</h2>
          <p>{tenant.email || "Sem e-mail"} · {tenant.phone || "Sem telefone"}</p>
        </div>
        <strong className={`core-status ${String(tenant.status).toLowerCase()}`}>{tenant.status}</strong>
      </header>

      <QuoteValidity tenant={tenant.slug} core /><ClientDisplaySetting tenant={tenant.slug} core /><PdfHeaderSetting tenant={tenant.slug} core /><div className="core-detail-grid">
        <CollapsibleSection
          className="core-info-block"
          title="Dados da empresa"
          description="Logo, nome, documento e canais principais de contato."
          summary="Cadastro principal"
          open={activePanel === "company"}
          onOpenChange={(isOpen) => setActivePanel(isOpen ? "company" : null)}
        >
          <label className="core-logo-upload">
            <input
              type="file"
              accept="image/png"
              disabled={isUploadingLogo}
              onChange={(event) => {
                const file = event.target.files?.[0];
                onUploadLogo(file);
                event.target.value = "";
              }}
            />
            <Image size={17} />
            <span>{isUploadingLogo ? "Salvando logo..." : "Enviar logo PNG"}</span>
          </label>
          <div className="core-form-grid">
            <CoreField label="Razao social" value={fiscalForm.name} onChange={(value) => onChangeFiscalField("name", value)} />
            <CoreField label="Nome fantasia" value={fiscalForm.trade_name} onChange={(value) => onChangeFiscalField("trade_name", value)} />
            <CoreField label="Documento" value={fiscalForm.document} onChange={(value) => onChangeFiscalField("document", value)} />
            <CoreField label="E-mail principal" value={fiscalForm.email} onChange={(value) => onChangeFiscalField("email", value)} />
            <CoreField label="Telefone principal" value={fiscalForm.phone} onChange={(value) => onChangeFiscalField("phone", value)} />
            <CoreReadonly label="Dono" value={tenant.owner_name || "Nao informado"} />
            <CoreReadonly label="WhatsApp recuperacao" value={tenant.recovery_phone || "Nao informado"} />
          </div>
        </CollapsibleSection>

        <CollapsibleSection
          className="core-info-block"
          title="Identidade visual"
          description="Defina a paleta fixa da empresa para o Chronos e seus documentos comerciais."
          summary={(chronosThemes.find((theme) => theme.id === fiscalForm.theme_slug) || chronosThemes[0]).label}
          open={activePanel === "identity"}
          onOpenChange={(isOpen) => setActivePanel(isOpen ? "identity" : null)}
        >
          <div className="core-theme-picker" role="radiogroup" aria-label="Paleta de cores da empresa">
            {chronosThemes.map((theme) => (
              <button
                className={`core-theme-choice ${theme.id === fiscalForm.theme_slug ? "active" : ""}`}
                type="button"
                key={theme.id}
                role="radio"
                aria-checked={theme.id === fiscalForm.theme_slug}
                onClick={() => onSelectTheme(theme.id)}
                disabled={isSavingTheme}
              >
                <span className="core-theme-choice-swatch" style={{ background: theme.swatch }} />
                <span>{theme.label}</span>
              </button>
            ))}
          </div>
          <small className="core-helper-text">A paleta e salva automaticamente ao selecionar.</small>
          {saveFeedback && <small className="core-success">{saveFeedback}</small>}
        </CollapsibleSection>

        <CollapsibleSection
          className="core-info-block"
          title="Plano e limites"
          description="Consulte assinatura, mensalidade e créditos de IA da empresa."
          summary={tenant.subscription?.package_name || "Sem plano"}
          open={activePanel === "plan"}
          onOpenChange={(isOpen) => setActivePanel(isOpen ? "plan" : null)}
        >
          <dl>
            <div><dt>Plano de IA</dt><dd>{tenant.subscription?.package_name || "Sem plano"}</dd></div>
            <div><dt>Status</dt><dd>{tenant.subscription?.status || "Sem assinatura"}</dd></div>
            <div><dt>Valor mensal</dt><dd>{formatMoney(tenant.subscription?.monthly_price)}</dd></div>
            <div><dt>Creditos IA semanais</dt><dd>{tenant.subscription?.ai_weekly_credits ?? 0}</dd></div>
          </dl>
        </CollapsibleSection>
      </div>

      <CollapsibleSection
        className="core-info-block"
        title="Dados fiscais para nota"
        description="CNPJ, inscrições, endereço e observações que aparecem em documentos da empresa."
        summary="Informações fiscais"
        open={activePanel === "fiscal"}
        onOpenChange={(isOpen) => setActivePanel(isOpen ? "fiscal" : null)}
      >
        <div className="core-block-title-row collapsible-content-action">
          <button className="core-save-button" type="button" onClick={onSaveFiscal} disabled={isSavingFiscal}>
            <CheckCircle2 size={17} />
            {isSavingFiscal ? "Salvando..." : "Salvar dados"}
          </button>
        </div>
        <div className="core-form-grid fiscal">
          <CoreField label="CNPJ" value={fiscalForm.fiscal_cnpj} onChange={(value) => onChangeFiscalField("fiscal_cnpj", value)} />
          <CoreField label="Inscricao estadual" value={fiscalForm.fiscal_state_registration} onChange={(value) => onChangeFiscalField("fiscal_state_registration", value)} />
          <CoreField label="Inscricao municipal" value={fiscalForm.fiscal_municipal_registration} onChange={(value) => onChangeFiscalField("fiscal_municipal_registration", value)} />
          <CoreField label="Regime tributario" value={fiscalForm.fiscal_tax_regime} onChange={(value) => onChangeFiscalField("fiscal_tax_regime", value)} />
          <CoreField label="CNAE principal" value={fiscalForm.fiscal_cnae} onChange={(value) => onChangeFiscalField("fiscal_cnae", value)} />
          <CoreField label="E-mail fiscal" value={fiscalForm.fiscal_email} onChange={(value) => onChangeFiscalField("fiscal_email", value)} />
          <CoreField label="Telefone fiscal" value={fiscalForm.fiscal_phone} onChange={(value) => onChangeFiscalField("fiscal_phone", value)} />
          <CoreField label="Responsavel fiscal" value={fiscalForm.fiscal_responsible_name} onChange={(value) => onChangeFiscalField("fiscal_responsible_name", value)} />
          <CoreField label="CEP" value={fiscalForm.fiscal_zip_code} onChange={(value) => onChangeFiscalField("fiscal_zip_code", value)} />
          <CoreField label="Rua" value={fiscalForm.fiscal_street} onChange={(value) => onChangeFiscalField("fiscal_street", value)} />
          <CoreField label="Numero" value={fiscalForm.fiscal_number} onChange={(value) => onChangeFiscalField("fiscal_number", value)} />
          <CoreField label="Complemento" value={fiscalForm.fiscal_complement} onChange={(value) => onChangeFiscalField("fiscal_complement", value)} />
          <CoreField label="Bairro" value={fiscalForm.fiscal_neighborhood} onChange={(value) => onChangeFiscalField("fiscal_neighborhood", value)} />
          <CoreField label="Cidade" value={fiscalForm.fiscal_city} onChange={(value) => onChangeFiscalField("fiscal_city", value)} />
          <CoreField label="Estado" value={fiscalForm.fiscal_state} onChange={(value) => onChangeFiscalField("fiscal_state", value)} />
          <CoreField label="Pais" value={fiscalForm.fiscal_country} onChange={(value) => onChangeFiscalField("fiscal_country", value)} />
          <CoreField
            className="wide"
            label="Observacoes fiscais"
            value={fiscalForm.fiscal_notes}
            onChange={(value) => onChangeFiscalField("fiscal_notes", value)}
          />
        </div>
        {saveFeedback && <small className="core-success">{saveFeedback}</small>}
        {error && <small className="core-error">{error}</small>}
      </CollapsibleSection>

      <CollapsibleSection
        className="core-info-block"
        title="Módulos liberados"
        description="Veja quais áreas do Chronos estão disponíveis para esta empresa."
        summary={`${(tenant.modules || []).length} módulo(s) ativo(s)`}
        open={activePanel === "modules"}
        onOpenChange={(isOpen) => setActivePanel(isOpen ? "modules" : null)}
      >
        <div className="core-module-grid">
          {(tenant.modules || []).map((module) => (
            <span className="core-module-pill" key={module.slug} style={{ "--module-color": module.color }}>
              {module.name}
            </span>
          ))}
        </div>
      </CollapsibleSection>

      <CollapsibleSection
        className="core-info-block"
        title="Equipe"
        description="Adicione pessoas, defina papéis e acompanhe os acessos da empresa."
        summary={`${(tenant.members || []).length} pessoa(s) vinculada(s)`}
        open={activePanel === "team"}
        onOpenChange={(isOpen) => setActivePanel(isOpen ? "team" : null)}
      >
        <div className="core-team-create">
          <div className="core-block-title-row">
            <div>
              <strong>Adicionar pessoa</strong>
              <small>Senha provisoria obriga troca no primeiro acesso.</small>
            </div>
            <button className="core-save-button" type="button" onClick={onAddMember} disabled={isSavingMember}>
              <UserPlus size={17} />
              {isSavingMember ? "Adicionando..." : "Adicionar"}
            </button>
          </div>
          <div className="core-form-grid fiscal">
            <CoreField label="Nome" value={memberForm.name} onChange={(value) => onChangeMemberField("name", value)} />
            <CoreField label="E-mail" value={memberForm.email} onChange={(value) => onChangeMemberField("email", value)} />
            <label className="core-field">
              <span>Papel</span>
              <select value={memberForm.role} onChange={(event) => onChangeMemberField("role", event.target.value)}>
                <option value="ADMIN">Administrador</option>
                <option value="MANAGER">Gestor</option>
                <option value="OPERATOR">Atendente</option>
                <option value="VIEWER">Leitura</option>
              </select>
            </label>
            <CoreField label="Senha provisoria" value={memberForm.temporary_password} onChange={(value) => onChangeMemberField("temporary_password", value)} />
            <CoreField label="Cargo" value={memberForm.title} onChange={(value) => onChangeMemberField("title", value)} />
            <CoreField label="Departamento" value={memberForm.department} onChange={(value) => onChangeMemberField("department", value)} />
          </div>
          <p className="core-helper-text">
            O WhatsApp de recuperacao sera cadastrado pela pessoa no primeiro login. A validacao sai pelo WhatsApp da empresa conectado no Chronos Zap.
          </p>
        </div>
        {memberFeedback && <small className="core-success">{memberFeedback}</small>}
        <div className="core-member-list">
          {(tenant.members || []).map((member) => (
            <div className="core-member-row" key={member.id}>
              <span>{(member.name || "?").slice(0, 1).toUpperCase()}</span>
              <div>
                <strong>{member.name}</strong>
                <small>{member.email}</small>
                <small>
                  {formatRole(member.role)} · {member.active ? formatUserStatus(member.status) : "Desativado"} ·{" "}
                  {member.password_configured ? "senha configurada" : "sem senha"}
                  {member.must_change_password ? " · troca obrigatoria" : ""}
                </small>
                <small>Permissoes: {(member.effective_permissions || []).length}</small>
              </div>
              <div className="core-member-actions">
                <input
                  type="password"
                  value={memberPasswords[member.id] || ""}
                  onChange={(event) => onChangeMemberPassword(member.id, event.target.value)}
                  placeholder="nova senha"
                />
                <button type="button" onClick={() => onUpdateMemberPassword(member.id)} title="Definir senha provisoria">
                  <KeyRound size={15} />
                </button>
                <button
                  type="button"
                  onClick={() => onToggleMember(member, !member.active)}
                  title={member.active ? "Desativar membro" : "Ativar membro"}
                >
                  <Power size={15} />
                </button>
              </div>
            </div>
          ))}
        </div>
      </CollapsibleSection>

      <CollapsibleSection
        className="core-info-block"
        title="Cobranças"
        description="Prepare a fatura mensal e consulte as cobranças já emitidas."
        summary={`${(tenant.billing?.invoices || []).length} fatura(s)`}
        open={activePanel === "billing"}
        onOpenChange={(isOpen) => setActivePanel(isOpen ? "billing" : null)}
      >
        <div className="core-block-title-row collapsible-content-action">
          <button className="core-save-button" type="button" onClick={onPrepareCurrentInvoice}>
            <CreditCard size={17} />
            Preparar fatura
          </button>
        </div>
        <div className="core-billing-grid">
          <CoreReadonly label="Plano de IA" value={tenant.subscription?.package_name || "Sem plano"} />
          <CoreReadonly label="Status" value={tenant.subscription?.status || "Sem assinatura"} />
          <CoreReadonly label="Mensalidade" value={formatMoney(tenant.subscription?.monthly_price)} />
          <CoreReadonly label="Creditos IA semanais" value={tenant.subscription?.ai_weekly_credits ?? 0} />
        </div>
        <div className="core-invoice-list">
          {(tenant.billing?.invoices || []).map((invoice) => (
            <div className="core-invoice-row" key={invoice.id}>
              <FileText size={17} />
              <div>
                <strong>{invoice.title}</strong>
                <small>{invoice.billing_month} · vencimento {invoice.due_date || "sem data"}</small>
              </div>
              <em>{formatMoney(invoice.amount)}</em>
              <span>{invoice.status}</span>
            </div>
          ))}
          {(tenant.billing?.invoices || []).length === 0 && (
            <small className="core-empty">Nenhuma fatura preparada ainda.</small>
          )}
        </div>
      </CollapsibleSection>

      <CollapsibleSection
        className="core-info-block"
        title="Auditoria da empresa"
        description="Histórico recente de alterações feitas na conta."
        summary={`${(auditLogs || []).length} evento(s) recente(s)`}
        open={activePanel === "audit"}
        onOpenChange={(isOpen) => setActivePanel(isOpen ? "audit" : null)}
      >
        <div className="core-audit-list">
          {(auditLogs || []).map((log) => (
            <div className="core-audit-row" key={log.id}>
              <span>{formatAuditAction(log.action)}</span>
              <strong>{log.entity}</strong>
              <small>{formatDateTime(log.created_at)}</small>
            </div>
          ))}
          {(auditLogs || []).length === 0 && <small className="core-empty">Nenhum evento registrado ainda.</small>}
        </div>
      </CollapsibleSection>
    </section>
  );
}
