import { useCallback, useEffect, useState } from "react";
import { authFetch } from "../../auth";

export async function requestData(url, options = {}) {
  const response = await authFetch(url, options);
  const data = await response.json().catch(() => null);
  if (!response.ok || data?.ok === false || !data) {
    const detail = typeof data?.detail === "string" ? data.detail : "Não foi possível concluir a operação. Tente novamente.";
    throw new Error(response.status === 403 ? "Seu usuário não tem permissão para esta operação." : detail);
  }
  return data;
}

export function jsonRequest(url, method, body) {
  return requestData(url, { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
}

export function useResource(url) {
  const [revision, setRevision] = useState(0);
  const [state, setState] = useState({ url: null, data: null, loading: true, error: "" });
  useEffect(() => {
    if (!url) return;
    const controller = new AbortController();
    setState({ url, data: null, loading: true, error: "" });
    requestData(url, { signal: controller.signal }).then(
      (data) => { if (!controller.signal.aborted) setState({ url, data, loading: false, error: "" }); },
      (error) => { if (!controller.signal.aborted) setState({ url, data: null, loading: false, error: error.message }); },
    );
    return () => controller.abort();
  }, [url, revision]);
  const reload = useCallback(() => setRevision((value) => value + 1), []);
  return { ...(state.url === url ? state : { data: null, loading: Boolean(url), error: "" }), reload };
}

export const money = (value) => new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" }).format(Number(value) || 0);
export const searchText = (value) => String(value || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
export function localDay(date = new Date()) {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}
export const statusLabel = (value) => ({ new: "Novo", pending: "Pendente", partial: "Parcial", draft: "Em aberto", sent: "Enviado", approved: "Aprovado", refused: "Recusado", expired: "Vencido", paid: "Pago", art: "Em arte", production: "Em produção", ready_delivery: "Pronto para entrega", finished: "Concluído", canceled: "Cancelado", scheduled: "Agendado", confirmed: "Confirmado", done: "Concluído", completed: "Concluído", no_show: "Não compareceu" })[value] || value || "Em aberto";
