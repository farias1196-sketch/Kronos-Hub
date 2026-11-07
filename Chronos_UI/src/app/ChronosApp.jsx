import { useEffect, useState } from "react";
import "../styles.css";
import { isPublicPage, restoreSession } from "../auth";
import ChronosWorkspace from "./ChronosWorkspace";
import CoreLoginPage from "../features/core/CoreLoginPage";
import { loginDestination, rememberExperience, useMobileExperience } from "../shared/experienceRoutes";

const CORE_LOGIN_PATH = "/ChronosCore/login";

export default function ChronosApp() {
  const isCoreLogin = /^\/ChronosCore\/login\/?$/i.test(window.location.pathname);
  const [ready, setReady] = useState(isPublicPage());
  const [error, setError] = useState("");

  useEffect(() => {
    if (isPublicPage()) return;
    let active = true;

    async function validateSession() {
      try {
        const valid = await restoreSession();
        if (!active) return;
        if (valid) {
          setError("");
          setReady(true);
        } else {
          rememberExperience(window.location.pathname);
          window.location.replace(CORE_LOGIN_PATH);
        }
      } catch {
        if (!active) return;
        setReady(false);
        setError("Nao foi possivel conectar ao Core. Os modulos permanecem bloqueados.");
      }
    }

    const onCoreUnavailable = () => {
      if (!active) return;
      setReady(false);
      setError("Nao foi possivel conectar ao Core. Os modulos permanecem bloqueados.");
    };
    const onVisibilityChange = () => {
      if (document.visibilityState === "visible") validateSession();
    };

    validateSession();
    const healthTimer = window.setInterval(validateSession, 10000);
    window.addEventListener("chronos-core-unavailable", onCoreUnavailable);
    window.addEventListener("focus", validateSession);
    document.addEventListener("visibilitychange", onVisibilityChange);
    return () => {
      active = false;
      window.clearInterval(healthTimer);
      window.removeEventListener("chronos-core-unavailable", onCoreUnavailable);
      window.removeEventListener("focus", validateSession);
      document.removeEventListener("visibilitychange", onVisibilityChange);
    };
  }, []);

  if (isCoreLogin) {
    return (
      <main className="chronos-login-shell">
        {useMobileExperience() && <div className="mobile-login-label">CHRONOS Mobile <span>Acesse sua empresa pelo celular ou tablet</span></div>}
        <CoreLoginPage onAuthenticated={() => window.location.assign("/ChronosNexus")} />
      </main>
    );
  }

  if (!ready) return <main className="core-login-page"><p role="status">{error || "Verificando sessao..."}</p>{error && <button onClick={() => window.location.reload()}>Tentar novamente</button>}</main>;
  return <ChronosWorkspace />;
}
