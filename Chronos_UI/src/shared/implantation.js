export const stages = {
  1: { title: "CHRONOS Fácil 1", goal: "Vender com organização", modules: [] },
  2: { title: "CHRONOS Fácil 2", goal: "Conectar atendimento e operação", modules: ["conversas", "flow", "stock", "agenda"] },
  3: { title: "CHRONOS Fácil 3", goal: "Integrar pagamentos, logística e vendas", modules: ["conversas", "flow", "stock", "agenda", "pay", "log", "loja", "promo"] },
  4: { title: "CHRONOS Hub completo", goal: "Dominar os módulos e introduzir a Hera", modules: ["core", "nexus", "conversas", "flow", "stock", "agenda", "pay", "log", "loja", "promo", "hera"] },
};
export function companyStage(tenant) {
  const assigned = tenant?.implementation_stage;
  return Number.isInteger(assigned) && stages[assigned] ? assigned : tenant?.chronos_facil === true ? 1 : 4;
}
export function stagePath(path, stage) {
  if (stage === 4) return /^\/ChronosFacil(?:\/|$)/i.test(path) ? "/ChronosCore" : path;
  if (/\/login(?:\/|$)|\/cadastro\/|\/public\//i.test(path)) return path;
  if (/^\/ChronosLoja\/[^/]+\/?$/i.test(path)) return path;
  const roots = { ChronosZap: "conversas", ChronosFlow: "flow", ChronosStock: "stock", ChronosAgenda: "agenda", ChronosPay: "pay", ChronosLog: "log", ChronosLoja: "loja", ChronosPromocoes: "promo", ChronosNexus: "clientes", ChronosCore: "configuracoes" };
  const [, root, section, ...rest] = path.split("/");
  let id, tail;
  if (/^ChronosFacil$/i.test(root)) { id = section || "pedidos"; tail = rest; }
  else if (/^ChronosMobile$/i.test(root)) { id = ({ nexus: "clientes", core: "configuracoes", inicio: "pedidos", perfil: "configuracoes" })[section] || section || "pedidos"; tail = rest; }
  else { id = Object.entries(roots).find(([key]) => key.toLowerCase() === root?.toLowerCase())?.[1]; tail = [section, ...rest].filter(Boolean); if (id === "conversas" && tail[0] === "chat") tail.shift(); }
  const basics = ["pedidos", "novo-pedido", "clientes", "produtos", "relatorio", "equipe", "configuracoes"];
  if (!id || ![...basics, ...stages[stage].modules].includes(id)) return "/ChronosFacil/pedidos";
  return `/ChronosFacil/${id}${tail.length ? "/" + tail.join("/") : ""}`;
}
