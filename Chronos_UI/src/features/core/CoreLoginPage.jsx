import { useEffect, useState } from "react";
import { authFetch, saveSession } from "../../auth";
import { CORE_API_URL } from "../../shared/chronosConfig";
import { CoreField } from "./CoreFields";

export default function CoreLoginPage({ onAuthenticated }) {
  const [step, setStep] = useState("tenant");
  const [tenantInput, setTenantInput] = useState("");
  const [tenantOptions, setTenantOptions] = useState([]);
  const [isSearchingTenants, setIsSearchingTenants] = useState(false);
  const [tenant, setTenant] = useState(null);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [status, setStatus] = useState("idle");
  const [error, setError] = useState("");

  useEffect(() => {
    const query = tenantInput.trim();
    if (query.length < 3) {
      setTenantOptions([]);
      return undefined;
    }

    const controller = new AbortController();
    const timer = window.setTimeout(async () => {
      setIsSearchingTenants(true);
      try {
        const response = await authFetch(`${CORE_API_URL}/core/auth/tenant-options?q=${encodeURIComponent(query)}`, {
          signal: controller.signal,
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || "Nao foi possivel procurar a empresa.");
        setTenantOptions(data.tenants || []);
      } catch (err) {
        if (err.name !== "AbortError") setTenantOptions([]);
      } finally {
        if (!controller.signal.aborted) setIsSearchingTenants(false);
      }
    }, 250);

    return () => {
      controller.abort();
      window.clearTimeout(timer);
    };
  }, [tenantInput]);

  function chooseTenant(option) {
    setTenant(option);
    setTenantInput(option.name);
    setTenantOptions([]);
    setError("");
  }

  async function selectTenant(event) {
    event.preventDefault();
    if (!tenant) {
      setError("Selecione uma empresa da lista para continuar.");
      return;
    }
    setStatus("loading");
    setError("");
    try {
      const response = await authFetch(`${CORE_API_URL}/core/auth/select-tenant`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tenant: tenant.slug }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Empresa nao encontrada.");
      setTenant(data.tenant || tenant);
      setStep("access");
    } catch (err) {
      setError(err.message || "Nao foi possivel selecionar a empresa.");
    } finally {
      setStatus("idle");
    }
  }

  async function login(event) {
    event.preventDefault();
    setStatus("loading");
    setError("");
    try {
      const response = await authFetch(`${CORE_API_URL}/core/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tenant_slug: tenant.slug, email, password }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error("E-mail ou senha invalidos para esta empresa.");
      if (data.mustChangePassword) {
        setStep("change");
        return;
      }
      saveSession(data);
      onAuthenticated(data.tenant);
    } catch (err) {
      setError(err.message || "Nao foi possivel entrar.");
    } finally {
      setStatus("idle");
    }
  }

  async function changeFirstPassword(event) {
    event.preventDefault();
    setStatus("loading");
    setError("");
    try {
      const response = await authFetch(`${CORE_API_URL}/core/auth/change-first-password`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          tenant_slug: tenant.slug,
          email,
          current_password: password,
          new_password: newPassword,
        }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Nao foi possivel trocar a senha.");
      setPassword(newPassword);
      saveSession(data);
      onAuthenticated(data.tenant);
    } catch (err) {
      setError(err.message || "Nao foi possivel trocar a senha.");
    } finally {
      setStatus("idle");
    }
  }

  return (
    <section className="core-login-page">
      <div className="core-login-card">
        <span>Chronos Core</span>
        <h1>{step === "tenant" ? "Selecionar empresa" : step === "change" ? "Trocar senha" : tenant?.name}</h1>
        {step === "tenant" && (
          <form onSubmit={selectTenant}>
            <label className="core-field">
              <span>Empresa</span>
              <input
                autoComplete="organization"
                value={tenantInput}
                onChange={(event) => {
                  setTenantInput(event.target.value);
                  setTenant(null);
                  setError("");
                }}
                placeholder="Digite ao menos 3 letras"
              />
            </label>
            {tenantInput.trim().length >= 3 && (
              <div className="core-tenant-options" role="listbox" aria-label="Empresas encontradas">
                {isSearchingTenants ? (
                  <small>Procurando empresa...</small>
                ) : tenantOptions.length ? (
                  tenantOptions.map((option) => (
                    <button
                      type="button"
                      className={tenant?.slug === option.slug ? "selected" : ""}
                      key={option.slug}
                      onClick={() => chooseTenant(option)}
                    >
                      <strong>{option.name}</strong>
                      {option.trade_name && option.trade_name !== option.name && <small>{option.trade_name}</small>}
                    </button>
                  ))
                ) : (
                  <small>Nenhuma empresa encontrada com esse inicio.</small>
                )}
              </div>
            )}
            <button className="core-save-button" type="submit" disabled={status === "loading" || !tenant}>
              {status === "loading" ? "Verificando..." : "Continuar"}
            </button>
          </form>
        )}
        {step === "access" && (
          <form onSubmit={login}>
            <CoreField label="E-mail" value={email} onChange={setEmail} />
            <CoreField label="Senha" value={password} onChange={setPassword} type="password" />
            <button className="core-save-button" type="submit" disabled={status === "loading"}>
              {status === "loading" ? "Entrando..." : "Entrar"}
            </button>
          </form>
        )}
        {step === "change" && (
          <form onSubmit={changeFirstPassword}>
            <p>Esta senha e provisoria. Defina uma nova senha para liberar o acesso.</p>
            <CoreField label="Nova senha" value={newPassword} onChange={setNewPassword} type="password" />
            <button className="core-save-button" type="submit" disabled={status === "loading"}>
              {status === "loading" ? "Salvando..." : "Salvar nova senha"}
            </button>
          </form>
        )}
        {error && <small className="core-error">{error}</small>}
      </div>
    </section>
  );
}
