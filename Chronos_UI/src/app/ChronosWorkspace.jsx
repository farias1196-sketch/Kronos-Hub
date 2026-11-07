import { useState } from "react";
import { logout } from "../auth";
import CorePage from "../features/core/CorePage";
import NexusPage, { NexusPublicRegistrationPage } from "../features/nexus/NexusPage";
import StockPage from "../features/stock/StockPage";
import LojaPage, { LojaPublicPage } from "../features/loja/LojaPage";
import AgendaPage, { AgendaPublicPage } from "../features/agenda/AgendaPage";
import "./localWorkspace.css";

const tabs = [
  ["Core", "/ChronosCore"], ["Clientes", "/ChronosNexus"], ["Estoque", "/ChronosStock"],
  ["Loja", "/ChronosLoja"], ["Agenda", "/ChronosAgenda"],
];

export default function ChronosWorkspace() {
  const path = window.location.pathname;
  const [tenant, setTenant] = useState(() => {
    try { return JSON.parse(localStorage.getItem("chronos-session"))?.tenant ?? null; }
    catch { return null; }
  });
  const [moduleName, subpath, value] = path.split("/").filter(Boolean);
  if (moduleName === "ChronosNexus" && subpath === "cadastro" && value)
    return <NexusPublicRegistrationPage token={decodeURIComponent(value)} />;
  if (moduleName === "ChronosAgenda" && subpath === "public" && value)
    return <AgendaPublicPage storeSlug={decodeURIComponent(value)} />;
  if (moduleName === "ChronosLoja" && subpath) return <LojaPublicPage />;
  if (!tenant?.slug) return <a href="/ChronosCore/login">Entrar na empresa</a>;
  const props = {currentTenant: tenant, currentTenantSlug: tenant.slug, path};
  const pages = {
    ChronosCore: <CorePage {...props} onTenantLoaded={setTenant} />,
    ChronosNexus: <NexusPage {...props} />,
    ChronosStock: <StockPage {...props} />,
    ChronosLoja: <LojaPage {...props} />,
    ChronosAgenda: <AgendaPage {...props} />,
  };
  const active = moduleName ?? "ChronosCore";
  return <div className="local-workspace">
    <header><strong>Chronos Hub</strong><span>{tenant.trade_name || tenant.name || tenant.slug}</span>
      <button type="button" onClick={logout}>Sair</button></header>
    <nav aria-label="Módulos do CRM">{tabs.map(([label, href]) => <a key={href} href={href}
      aria-current={href === "/" + active ? "page" : undefined}>{label}</a>)}</nav>
    <main>{pages[active] ?? <p>Este módulo está fora da distribuição local.</p>}</main>
  </div>;
}
