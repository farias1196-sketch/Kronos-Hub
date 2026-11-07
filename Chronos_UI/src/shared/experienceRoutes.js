export const MOBILE_PATH = "/ChronosMobile";
export const EASY_PATH = "/ChronosFacil";

export const mobileRouteMap = [
  ["ChronosCore", "core"], ["ChronosNexus", "nexus"], ["ChronosZap", "conversas"],
  ["ChronosHera", "hera"], ["ChronosStock", "stock"], ["ChronosPay", "pay"],
  ["ChronosLog", "log"], ["ChronosAgenda", "agenda"], ["ChronosLoja", "loja"],
  ["ChronosPromocoes", "promo"], ["ChronosFlow", "flow"],
];

export function isMobileDevice() {
  const agent = globalThis.navigator;
  return Boolean(window.matchMedia?.("(max-width: 1024px)").matches || agent?.userAgentData?.mobile
    || /Android|iPhone|iPad|iPod/i.test(agent?.userAgent || "")
    || /Macintosh/i.test(agent?.userAgent || "") && agent?.maxTouchPoints > 1);
}

export function useMobileExperience() {
  try { if (sessionStorage.getItem("chronos-display-mode") === "desktop") return false; } catch { /* Use device detection. */ }
  return isMobileDevice();
}

export function chooseDesktopExperience() {
  try { sessionStorage.setItem("chronos-display-mode", "desktop"); } catch { /* Explicit routes still work on desktop. */ }
}

function isCustomerOrLoginPath(path) {
  return /^\/ChronosCore\/login\/?$/i.test(path) || /^\/ChronosNexus\/cadastro\//i.test(path)
    || /^\/ChronosAgenda\/public\//i.test(path) || /^\/ChronosLoja\/[^/]+\/?$/i.test(path);
}

export function toMobilePath(path) {
  if (experienceFromPath(path) || isCustomerOrLoginPath(path)) return path;
  if (path === "/") return MOBILE_PATH;
  const [, root, ...rest] = path.split("/");
  const entry = mobileRouteMap.find(([desktop]) => desktop.toLowerCase() === root?.toLowerCase());
  if (!entry) return path;
  if (entry[1] === "conversas" && rest[0]?.toLowerCase() === "chat") rest.shift();
  return `${MOBILE_PATH}/${entry[1]}${rest.length ? `/${rest.join("/")}` : ""}`;
}

export function toDesktopPath(path) {
  const [, , section, ...rest] = path.split("/");
  const entry = mobileRouteMap.find(([, mobile]) => mobile === section?.toLowerCase());
  if (!entry) return path;
  if (entry[1] === "conversas" && !rest.length) rest.push("chat");
  return `/${entry[0]}${rest.length ? `/${rest.join("/")}` : ""}`;
}

export function resolveExperiencePath(path, mobile = useMobileExperience()) {
  return mobile ? toMobilePath(path) : path;
}

export function experienceFromPath(path) {
  if (/^\/ChronosMobile(?:\/|$)/i.test(path)) return "mobile";
  if (/^\/ChronosFacil(?:\/|$)/i.test(path)) return "easy";
  return null;
}

export function rememberExperience(path) {
  if (!experienceFromPath(path)) return;
  try { sessionStorage.setItem("chronos-return-to", path); } catch { /* Storage may be blocked. */ }
}

export function loginDestination() {
  try {
    const path = sessionStorage.getItem("chronos-return-to");
    sessionStorage.removeItem("chronos-return-to");
    if (experienceFromPath(path || "") && !/[?#\\]/.test(path)) return path;
  } catch { /* Use the viewport default. */ }
  return useMobileExperience() ? MOBILE_PATH : "/ChronosCore";
}

// Apply the company default only at entry points; preserve links to specific work.
export function companyLandingPath(path, tenant) {
  return tenant?.chronos_facil === true && /^\/(?:ChronosCore|ChronosMobile(?:\/core)?)?\/?$/i.test(path) ? EASY_PATH : path;
}
