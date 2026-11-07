import { CORE_API_URL } from "./shared/chronosConfig.js";
import { clearChatCache } from "./shared/chatCache.js";
import { rememberExperience } from "./shared/experienceRoutes.js";

const TOKEN_KEY = "chronos-token";
const SESSION_KEY = "chronos-session";
let redirecting = false;

function storedSession() {
  try {
    return JSON.parse(localStorage.getItem(SESSION_KEY) || "null");
  } catch {
    return null;
  }
}

export function isPublicPage(path = window.location.pathname) {
  return /^\/ChronosCore\/login\/?$/i.test(path)
    || /^\/ChronosNexus\/cadastro\//i.test(path)
    || /^\/ChronosAgenda\/public\//i.test(path)
    || /^\/ChronosLoja\/[^/]+\/?$/i.test(path);
}

export function saveSession(data) {
  if (!data.token) throw new Error("O Core nao retornou o token de acesso.");
  localStorage.setItem(TOKEN_KEY, data.token);
  localStorage.setItem(SESSION_KEY, JSON.stringify({ user: data.user, tenant: data.tenant, permissions: data.permissions }));
  localStorage.setItem("chronos-current-tenant-slug", data.tenant.slug);
  redirecting = false;
}

export function clearSession() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(SESSION_KEY);
  localStorage.removeItem("chronos-current-tenant-slug");
  clearChatCache().catch(() => undefined);
}

export function logout() {
  clearSession();
  window.location.assign("/ChronosCore/login");
}

export async function authFetch(input, options = {}) {
  const url = new URL(input, window.location.origin);
  if (url.origin !== window.location.origin || !url.pathname.startsWith("/api/")) {
    throw new Error("Destino fora das APIs locais.");
  }
  const routePath = url.pathname.replace(/^\/api\/[^/]+/, "");
  const publicRequest = /^\/public\//.test(routePath) || /^\/nexus\/(public-registration|public\/register)\//.test(routePath) || /^\/core\/auth\/(login|select-tenant|change-first-password|tenant-options)$/.test(routePath) || routePath === "/health" || routePath === "/notices/active" || (routePath.startsWith("/media/cache/") && url.searchParams.has("asset_signature"));
  const token = localStorage.getItem(TOKEN_KEY);
  const headers = new Headers(options.headers);
  let body = options.body;
  if (token && !publicRequest) {
    headers.set("Authorization", `Bearer ${token}`);
    const session = storedSession();
    if (session?.tenant && !routePath.startsWith("/core/auth/")) {
      const slug = session.tenant.slug;
      const tenant = slug;
      for (const key of ["tenant_id", "empresa_id", "tenant_slug", "current_slug"]) {
        if (url.searchParams.has(key)) url.searchParams.set(key, ["tenant_id", "empresa_id"].includes(key) ? tenant : slug);
      }
      if (body instanceof FormData) {
        const scopedBody = new FormData();
        for (const [key, value] of body.entries()) scopedBody.append(key, ["tenant_id", "empresa_id"].includes(key) ? tenant : value);
        body = scopedBody;
      } else if (typeof body === "string" && headers.get("Content-Type")?.includes("application/json")) {
        const data = JSON.parse(body);
        for (const key of ["tenant_id", "empresa_id"]) if (key in data) data[key] = tenant;
        body = JSON.stringify(data);
      }
    }
  }
  const response = await fetch(url, { ...options, headers, body });
  // An old in-flight response must not log out a newer login or tenant switch.
  if (response.status === 401 && !publicRequest && token === localStorage.getItem(TOKEN_KEY)) {
    clearSession();
    if (!isPublicPage() && !redirecting) {
      redirecting = true;
      rememberExperience(window.location.pathname);
      window.location.replace("/ChronosCore/login");
    }
  }
  return response;
}

export async function restoreSession() {
  const checkedToken = localStorage.getItem(TOKEN_KEY);
  if (!checkedToken) return false;
  const response = await authFetch(`${CORE_API_URL}/core/auth/me`);
  if (!response.ok) {
    if (response.status !== 401) throw new Error("Nao foi possivel verificar sua sessao.");
    return false;
  }
  const data = await response.json();
  if (checkedToken !== localStorage.getItem(TOKEN_KEY)) return Boolean(localStorage.getItem(TOKEN_KEY));
  localStorage.setItem(SESSION_KEY, JSON.stringify(data));
  localStorage.setItem("chronos-current-tenant-slug", data.tenant.slug);
  return true;
}

export async function switchTenant(slug) {
  const response = await authFetch(`${CORE_API_URL}/core/auth/switch-tenant`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ tenant: slug }),
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.detail || "Sem acesso a empresa.");
  saveSession(data);
  window.location.assign("/ChronosCore");
}
