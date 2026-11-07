export function clientName(client, preference = "person") {
  const person = String(client?.name || "").trim();
  const company = String(client?.company_name || "").trim();
  return (preference === "company" ? company || person : person || company) || "Cliente sem nome";
}
export function clientSecondary(client, preference = "person") {
  const secondary = String(preference === "company" ? client?.name || "" : client?.company_name || "").trim();
  return secondary === clientName(client, preference) ? "" : secondary;
}

export function draftClientName(draft, clients = [], preference = "person") {
  const current = clients.find(client => client.id === draft.client_id);
  return clientName(current || {
    name: draft.client_person_name || draft.client_name,
    company_name: draft.client_company_name,
  }, preference);
}
