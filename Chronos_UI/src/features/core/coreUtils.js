import { CORE_API_URL } from "../../shared/chronosConfig";

export function buildFiscalForm(tenant) {
  return {
    name: tenant.name || "",
    trade_name: tenant.trade_name || "",
    document: tenant.document || "",
    email: tenant.email || "",
    phone: tenant.phone || "",
    theme_slug: tenant.theme_slug || "rosa-branco",
    fiscal_cnpj: tenant.fiscal_cnpj || "",
    fiscal_state_registration: tenant.fiscal_state_registration || "",
    fiscal_municipal_registration: tenant.fiscal_municipal_registration || "",
    fiscal_tax_regime: tenant.fiscal_tax_regime || "",
    fiscal_cnae: tenant.fiscal_cnae || "",
    fiscal_email: tenant.fiscal_email || "",
    fiscal_phone: tenant.fiscal_phone || "",
    fiscal_responsible_name: tenant.fiscal_responsible_name || "",
    fiscal_zip_code: tenant.fiscal_zip_code || "",
    fiscal_street: tenant.fiscal_street || "",
    fiscal_number: tenant.fiscal_number || "",
    fiscal_complement: tenant.fiscal_complement || "",
    fiscal_neighborhood: tenant.fiscal_neighborhood || "",
    fiscal_city: tenant.fiscal_city || "",
    fiscal_state: tenant.fiscal_state || "",
    fiscal_country: tenant.fiscal_country || "Brasil",
    fiscal_notes: tenant.fiscal_notes || "",
  };
}

export function buildMemberForm() {
  return {
    name: "",
    email: "",
    role: "OPERATOR",
    title: "",
    department: "",
    temporary_password: "",
  };
}

export function formatRole(role) {
  const labels = { OWNER: "Dono", ADMIN: "Administrador", MANAGER: "Gestor", OPERATOR: "Atendente", VIEWER: "Leitura" };
  return labels[role] || role;
}

export function formatUserStatus(status) {
  const labels = { ACTIVE: "Ativo", INVITED: "Convite pendente", DISABLED: "Desativado" };
  return labels[status] || status;
}

export function formatAuditAction(action) {
  const labels = {
    "core.auth.login": "Login",
    "core.auth.first_password_change": "Senha inicial trocada",
    "core.company.logo_update": "Logo atualizada",
    "core.company.fiscal_update": "Dados fiscais salvos",
    "core.member.upsert": "Membro salvo",
    "core.member.password_update": "Senha de membro atualizada",
    "core.member.status_update": "Status de membro alterado",
    "core.billing.invoice_prepare": "Fatura preparada",
  };
  return labels[action] || action;
}

export function formatDateTime(value) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("pt-BR", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" });
}

export function formatMoney(value) {
  return Number(value || 0).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

export function buildCoreAssetUrl(value) {
  if (!value) return "";
  if (String(value).startsWith("http")) return value;
  return `${CORE_API_URL}${value}`;
}
