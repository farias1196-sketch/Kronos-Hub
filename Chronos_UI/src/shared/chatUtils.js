export function normalizeSearch(value) {
  return String(value || "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .trim();
}

export function isGroupConversation(conversation) {
  return String(conversation?.remote_jid || "").includes("@g.us");
}

export function isStatusConversation(conversation) {
  const remoteJid = String(conversation?.remote_jid || conversation?.contact_id || "");
  return remoteJid.includes("status@broadcast") || remoteJid === "status";
}

export function isLidValue(value) {
  return String(value || "").startsWith("lid:") || String(value || "").length > 13;
}

export function formatClientPhone(client) {
  if (!client?.phone) return "Telefone nao informado";
  if (isLidValue(client.phone) || client.whatsapp_lid) return "Telefone ainda nao identificado";
  return client.phone;
}

export function formatClientIdentity(client) {
  if (client?.whatsapp_lid) return `LID interno: ${client.whatsapp_lid}`;
  if (isLidValue(client?.phone)) return `LID interno: ${String(client.phone).replace("lid:", "")}`;
  return client?.phone || "Sem identificador";
}

function normalizeDigits(value) {
  return String(value || "").replace(/\D/g, "");
}

export function findConversationForClient(conversations, client) {
  if (!client) return null;
  const clientDigits = normalizeDigits(client.phone);
  const clientLid = normalizeDigits(client.whatsapp_lid || (isLidValue(client.phone) ? client.phone : ""));
  const exactTokens = [client.id, client.phone, client.whatsapp_jid, client.whatsapp_lid]
    .filter(Boolean)
    .map((value) => String(value).toLowerCase());

  return conversations.find((conversation) => {
    const values = [conversation.id, conversation.phone, conversation.contact_id, conversation.remote_jid, conversation.display_name]
      .filter(Boolean);
    const lowered = values.map((value) => String(value).toLowerCase());
    if (exactTokens.some((token) => lowered.includes(token))) return true;
    const conversationDigits = values.map(normalizeDigits).filter(Boolean);
    return (clientDigits && conversationDigits.some((digits) => digits === clientDigits || digits.endsWith(clientDigits))) ||
      (clientLid && conversationDigits.some((digits) => digits === clientLid || digits.endsWith(clientLid)));
  }) || null;
}
