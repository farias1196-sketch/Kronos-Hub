"""PostgreSQL persistence adapter that preserves the Nexus API contract."""

from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import Any

from .postgres import get_connection, transaction


CONVERSATION_STATUSES = {"novo", "em_atendimento", "aguardando_cliente", "pausado", "finalizado"}
ORDER_STATUSES = {"sem_pedido", "orcamento", "aguardando_pagamento", "em_arte", "em_producao", "pronto_para_entrega", "entregue", "cancelado"}
ART_STATUSES = {"sem_arte", "aguardando_briefing", "criando", "aguardando_aprovacao", "aprovada", "reprovada"}


def clean(value: object) -> str:
    return "" if value is None else str(value).strip()


def normalized_phone(value: object) -> str:
    text = clean(value)
    if text.lower().startswith("lid:"):
        return text.lower()
    digits = "".join(char for char in text if char.isdigit())
    return digits or text.lower()


def row_id(prefix: str, *parts: object) -> str:
    raw = "-".join(clean(part).lower() for part in parts if clean(part))
    safe = "".join(char for char in raw.replace(" ", "-") if char.isalnum() or char in "-_.")
    return f"{prefix}_{safe or 'sem-id'}"


def now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def iso(value: datetime | None) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z") if value else ""


def tags(value: object) -> list[str]:
    source = value.split(",") if isinstance(value, str) else (value or [])
    result: list[str] = []
    for item in source:
        tag = clean(item).lower()
        if tag and tag not in result:
            result.append(tag)
    return result


def registration_tags(value: object, status: str) -> list[str]:
    result = [tag for tag in tags(value) if tag not in {"pre-cadastro", "cadastro-completo"}]
    if status:
        result.append(status)
    return result


def validate(value: object, allowed: set[str], fallback: str) -> str:
    value = clean(value)
    if not value:
        return fallback
    if value not in allowed:
        raise ValueError(f"Status invalido: {value}.")
    return value


async def tenant_id(connection: Any, slug: str) -> str:
    value = await connection.fetchval("SELECT id FROM tenants WHERE slug = $1", slug)
    if not value:
        raise ValueError("Empresa nao encontrada.")
    return str(value)


async def serialize_client(connection: Any, row: Any) -> dict[str, Any]:
    client = dict(row)
    client_id = str(client["id"])
    tenant = str(client["tenant_id"])
    address = dict(client.pop("address") or {})
    custom = dict(client.pop("custom_fields") or {})
    points = await connection.fetch(
        """SELECT id, channel, value, normalized_value, is_primary, metadata, created_at, updated_at
             FROM nexus_contact_points WHERE tenant_id=$1 AND client_id=$2
             ORDER BY is_primary DESC, channel, value""", tenant, client_id,
    )
    whatsapp = next((point for point in points if point["channel"] == "whatsapp" and point["is_primary"]), None)
    if not whatsapp:
        whatsapp = next((point for point in points if point["channel"] == "whatsapp"), None)
    client.update({
        "empresa_id": str(client.pop("tenant_slug")),
        "phone": str(whatsapp["value"]) if whatsapp else "",
        "cep": clean(address.get("zip_code")),
        "address_street": clean(address.get("street")),
        "address_number": clean(address.get("number")),
        "address_complement": clean(address.get("complement")),
        "address_neighborhood": clean(address.get("neighborhood")),
        "address_city": clean(address.get("city")),
        "address_state": clean(address.get("state")),
        "registration_token": clean(custom.get("registration_token")),
        "registration_answers": custom.get("registration_answers") or {},
        "registration_completed_at": clean(custom.get("registration_completed_at")),
        "whatsapp_lid": clean(custom.get("whatsapp_lid")),
        "whatsapp_jid": clean(custom.get("whatsapp_jid")),
        "assigned_seller_id": clean(custom.get("assigned_seller_id")) or clean(client.get("assigned_member_id")),
        "merged_into_client_id": clean(client.pop("merged_into_client_id", "")),
        "merged_at": iso(client.pop("merged_at", None)),
        "created_at": iso(client.get("created_at")),
        "updated_at": iso(client.get("updated_at")),
    })
    client["assigned_member_id"] = clean(client.get("assigned_member_id"))
    client["tags"] = [str(item["name"]) for item in await connection.fetch(
        """SELECT tag.name FROM nexus_client_tags client_tag
             JOIN nexus_tags tag ON tag.tenant_id=client_tag.tenant_id AND tag.id=client_tag.tag_id
             WHERE client_tag.tenant_id=$1 AND client_tag.client_id=$2 ORDER BY tag.name""", tenant, client_id,
    )]
    return client


async def fetch_client(connection: Any, slug: str, client_id: str, *, include_merged: bool = True) -> dict[str, Any] | None:
    clause = "" if include_merged else "AND merge.merged_client_id IS NULL"
    row = await connection.fetchrow(
        f"""SELECT client.*, tenant.slug AS tenant_slug, merge.primary_client_id AS merged_into_client_id, merge.created_at AS merged_at
              FROM nexus_clients client JOIN tenants tenant ON tenant.id=client.tenant_id
              LEFT JOIN nexus_client_merges merge ON merge.tenant_id=client.tenant_id AND merge.merged_client_id=client.id
             WHERE tenant.slug=$1 AND client.id=$2 {clause}""", slug, client_id,
    )
    return await serialize_client(connection, row) if row else None


async def list_clients(slug: str, search: str = "", tag: str = "") -> list[dict[str, Any]]:
    filters = ["tenant.slug=$1", "merge.merged_client_id IS NULL"]
    args: list[Any] = [slug]
    if search:
        args.append(f"%{search.lower()}%")
        marker = f"${len(args)}"
        filters.append(f"(lower(client.name) LIKE {marker} OR lower(coalesce(client.company_name,'')) LIKE {marker} OR lower(coalesce(client.fiscal_document,'')) LIKE {marker} OR lower(coalesce(client.email,'')) LIKE {marker} OR EXISTS (SELECT 1 FROM nexus_contact_points phone WHERE phone.tenant_id=client.tenant_id AND phone.client_id=client.id AND lower(phone.value) LIKE {marker}))")
    if tag:
        args.append(clean(tag).lower())
        marker = f"${len(args)}"
        filters.append(f"EXISTS (SELECT 1 FROM nexus_client_tags ct JOIN nexus_tags nt ON nt.tenant_id=ct.tenant_id AND nt.id=ct.tag_id WHERE ct.tenant_id=client.tenant_id AND ct.client_id=client.id AND lower(nt.name)={marker})")
    async with get_connection() as connection:
        rows = await connection.fetch(
            f"""SELECT client.*, tenant.slug AS tenant_slug, NULL::varchar AS merged_into_client_id, NULL::timestamptz AS merged_at
                  FROM nexus_clients client JOIN tenants tenant ON tenant.id=client.tenant_id
                  LEFT JOIN nexus_client_merges merge ON merge.tenant_id=client.tenant_id AND merge.merged_client_id=client.id
                 WHERE {' AND '.join(filters)} ORDER BY client.updated_at DESC, client.name""", *args,
        )
        return [await serialize_client(connection, row) for row in rows]


async def get_client(slug: str, client_id: str) -> dict[str, Any] | None:
    async with get_connection() as connection:
        return await fetch_client(connection, slug, client_id)


async def list_contact_points(slug: str, client_id: str) -> list[dict[str, Any]]:
    async with get_connection() as connection:
        tenant = await tenant_id(connection, slug)
        rows = await connection.fetch(
            """SELECT id, channel, value, metadata, created_at, updated_at FROM nexus_contact_points
                 WHERE tenant_id=$1 AND client_id=$2 ORDER BY channel, value""", tenant, client_id,
        )
    return [{"id": str(row["id"]), "channel": str(row["channel"]), "external_id": str(row["value"]), "label": clean(dict(row["metadata"] or {}).get("label")), "created_at": iso(row["created_at"]), "updated_at": iso(row["updated_at"])} for row in rows]


async def write_tags(connection: Any, tenant: str, client_id: str, names: list[str]) -> None:
    await connection.execute("DELETE FROM nexus_client_tags WHERE tenant_id=$1 AND client_id=$2", tenant, client_id)
    for name in names:
        tag_id = row_id("tag", tenant, name)
        await connection.execute("INSERT INTO nexus_tags (id, tenant_id, name) VALUES ($1,$2,$3) ON CONFLICT (tenant_id, name) DO NOTHING", tag_id, tenant, name)
        actual_id = await connection.fetchval("SELECT id FROM nexus_tags WHERE tenant_id=$1 AND name=$2", tenant, name)
        await connection.execute("INSERT INTO nexus_client_tags (tenant_id, client_id, tag_id) VALUES ($1,$2,$3) ON CONFLICT DO NOTHING", tenant, client_id, actual_id)


async def upsert_client(slug: str, payload: dict[str, Any]) -> dict[str, Any]:
    name, phone = clean(payload.get("name")), normalized_phone(payload.get("phone"))
    if not name:
        raise ValueError("Nome do cliente e obrigatorio.")
    if not phone:
        raise ValueError("Numero do cliente e obrigatorio.")
    registration_status = clean(payload.get("registration_status")) or "cadastro-completo"
    completed_at = clean(payload.get("registration_completed_at")) or (iso(now()) if registration_status == "cadastro-completo" else "")
    final_tags = registration_tags(payload.get("tags"), registration_status)
    timestamp = now()
    async with transaction() as connection:
        tenant = await tenant_id(connection, slug)
        existing_id = await connection.fetchval("SELECT client_id FROM nexus_contact_points WHERE tenant_id=$1 AND channel='whatsapp' AND normalized_value=$2", tenant, phone)
        client_id = str(existing_id or clean(payload.get("id")) or row_id("client", slug, phone))
        previous = await connection.fetchrow("SELECT custom_fields, created_at FROM nexus_clients WHERE tenant_id=$1 AND id=$2", tenant, client_id)
        custom = dict(previous["custom_fields"] or {}) if previous else {}
        if "registration_answers" in payload:
            custom["registration_answers"] = {**(custom.get("registration_answers") or {}), **(payload.get("registration_answers") or {})}
        custom.update({"registration_token": clean(payload.get("registration_token")) or clean(custom.get("registration_token")) or secrets.token_urlsafe(24), "registration_completed_at": completed_at, "whatsapp_lid": clean(payload.get("whatsapp_lid")) or clean(custom.get("whatsapp_lid")), "whatsapp_jid": clean(payload.get("whatsapp_jid")) or clean(custom.get("whatsapp_jid")), "assigned_seller_id": clean(payload.get("assigned_seller_id"))})
        address = {"zip_code": clean(payload.get("cep")), "street": clean(payload.get("address_street")), "number": clean(payload.get("address_number")), "complement": clean(payload.get("address_complement")), "neighborhood": clean(payload.get("address_neighborhood")), "city": clean(payload.get("address_city")), "state": clean(payload.get("address_state"))}
        await connection.execute(
            """INSERT INTO nexus_clients (id, tenant_id, name, company_name, fiscal_document, email, notes, address, source, registration_status, assigned_member_id, assigned_seller_name, conversation_status, order_status, art_status, art_briefing, art_link, art_notes, custom_fields, created_at, updated_at)
               VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20,$20)
               ON CONFLICT (id) DO UPDATE SET name=EXCLUDED.name, company_name=EXCLUDED.company_name, fiscal_document=EXCLUDED.fiscal_document, email=EXCLUDED.email, notes=EXCLUDED.notes, address=EXCLUDED.address, source=EXCLUDED.source, registration_status=EXCLUDED.registration_status, assigned_member_id=EXCLUDED.assigned_member_id, assigned_seller_name=EXCLUDED.assigned_seller_name, conversation_status=EXCLUDED.conversation_status, order_status=EXCLUDED.order_status, art_status=EXCLUDED.art_status, art_briefing=EXCLUDED.art_briefing, art_link=EXCLUDED.art_link, art_notes=EXCLUDED.art_notes, custom_fields=EXCLUDED.custom_fields, updated_at=EXCLUDED.updated_at""",
            client_id, tenant, name, clean(payload.get("company_name")), clean(payload.get("fiscal_document")), clean(payload.get("email")), clean(payload.get("notes")), address, clean(payload.get("source")) or "manual", registration_status, clean(payload.get("assigned_seller_id")) or None, clean(payload.get("assigned_seller_name")), validate(payload.get("conversation_status"), CONVERSATION_STATUSES, "novo"), validate(payload.get("order_status"), ORDER_STATUSES, "sem_pedido"), validate(payload.get("art_status"), ART_STATUSES, "sem_arte"), clean(payload.get("art_briefing")), clean(payload.get("art_link")), clean(payload.get("art_notes")), custom, timestamp,
        )
        point_id = row_id("contact", slug, "whatsapp", phone)
        await connection.execute("""INSERT INTO nexus_contact_points (id, tenant_id, client_id, channel, value, normalized_value, is_primary, metadata, created_at, updated_at) VALUES ($1,$2,$3,'whatsapp',$4,$5,TRUE,$6,$7,$7) ON CONFLICT (tenant_id, channel, normalized_value) DO UPDATE SET client_id=EXCLUDED.client_id, value=EXCLUDED.value, is_primary=TRUE, metadata=EXCLUDED.metadata, updated_at=EXCLUDED.updated_at""", point_id, tenant, client_id, phone, phone, {"label": name}, timestamp)
        for value in (clean(payload.get("whatsapp_jid")), f"lid:{clean(payload.get('whatsapp_lid'))}" if clean(payload.get("whatsapp_lid")) else ""):
            if value:
                normal = value.lower()
                await connection.execute("""INSERT INTO nexus_contact_points (id, tenant_id, client_id, channel, value, normalized_value, metadata, created_at, updated_at) VALUES ($1,$2,$3,'whatsapp',$4,$5,$6,$7,$7) ON CONFLICT (tenant_id, channel, normalized_value) DO UPDATE SET client_id=EXCLUDED.client_id, metadata=EXCLUDED.metadata, updated_at=EXCLUDED.updated_at""", row_id("contact", slug, "whatsapp", normal), tenant, client_id, value, normal, {"label": name}, timestamp)
        await write_tags(connection, tenant, client_id, final_tags)
        await connection.execute("INSERT INTO nexus_client_events (id, tenant_id, client_id, event_type, payload, created_at) VALUES ($1,$2,$3,'client.upsert',$4,$5) ON CONFLICT DO NOTHING", row_id("event", slug, client_id, iso(timestamp)), tenant, client_id, {"source": clean(payload.get("source")) or "manual", "tags": final_tags}, timestamp)
        return (await fetch_client(connection, slug, client_id)) or {}


async def pre_register_client(slug: str, payload: dict[str, Any]) -> dict[str, Any]:
    remote = clean(payload.get("remote_jid")); lid = remote.split("@", 1)[0] if "@lid" in remote else ""
    phone = normalized_phone(clean(payload.get("phone")) or (f"lid:{lid}" if lid else ""))
    if not phone:
        raise ValueError("Numero do cliente e obrigatorio.")
    existing = await list_clients(slug, search=phone)
    current = next((item for item in existing if normalized_phone(item.get("phone")) == phone), None)
    data = {**(current or {}), **payload, "name": clean((current or {}).get("name")) if current and clean((current or {}).get("name")) not in {phone, ""} else clean(payload.get("display_name")) or clean(payload.get("name")) or phone, "phone": phone, "whatsapp_lid": lid or clean((current or {}).get("whatsapp_lid")), "whatsapp_jid": remote or clean((current or {}).get("whatsapp_jid")), "registration_status": clean((current or {}).get("registration_status")) or "pre-cadastro", "tags": registration_tags((current or {}).get("tags"), clean((current or {}).get("registration_status")) or "pre-cadastro"), "source": clean(payload.get("source")) or "zap"}
    return await upsert_client(slug, data)


async def get_client_by_registration_token(token: str) -> dict[str, Any] | None:
    if not clean(token):
        return None
    async with get_connection() as connection:
        row = await connection.fetchrow("""SELECT client.*, tenant.slug AS tenant_slug, merge.primary_client_id AS merged_into_client_id, merge.created_at AS merged_at FROM nexus_clients client JOIN tenants tenant ON tenant.id=client.tenant_id LEFT JOIN nexus_client_merges merge ON merge.tenant_id=client.tenant_id AND merge.merged_client_id=client.id WHERE client.custom_fields->>'registration_token'=$1""", clean(token))
        return await serialize_client(connection, row) if row else None


async def complete_registration(token: str, payload: dict[str, Any]) -> dict[str, Any]:
    client = await get_client_by_registration_token(token)
    if not client:
        raise ValueError("Link de cadastro invalido.")
    return await upsert_client(client["empresa_id"], {**client, **payload, "id": client["id"], "phone": client["phone"], "registration_token": token, "registration_status": "cadastro-completo", "tags": registration_tags([*client.get("tags", []), *tags(payload.get("tags"))], "cadastro-completo")})


async def delete_client(slug: str, client_id: str) -> bool:
    async with transaction() as connection:
        tenant = await tenant_id(connection, slug)
        result = await connection.execute("DELETE FROM nexus_clients WHERE tenant_id=$1 AND id=$2", tenant, client_id)
    return result.endswith("1")


async def merge_clients(slug: str, primary_client_id: str, duplicate_client_id: str) -> dict[str, Any]:
    if primary_client_id == duplicate_client_id:
        raise ValueError("Escolha dois clientes diferentes para mesclar.")
    async with transaction() as connection:
        tenant = await tenant_id(connection, slug)
        primary = await fetch_client(connection, slug, primary_client_id, include_merged=False)
        duplicate = await fetch_client(connection, slug, duplicate_client_id, include_merged=False)
        if not primary or not duplicate:
            raise ValueError("Um dos clientes nao esta disponivel para mesclagem.")
        merged_tags = registration_tags([*primary.get("tags", []), *duplicate.get("tags", [])], "cadastro-completo" if "cadastro-completo" in {primary.get("registration_status"), duplicate.get("registration_status")} else primary.get("registration_status") or "pre-cadastro")
        await write_tags(connection, tenant, primary_client_id, merged_tags)
        primary_points = {(item["channel"], item["normalized_value"]) for item in await connection.fetch("SELECT channel, normalized_value FROM nexus_contact_points WHERE tenant_id=$1 AND client_id=$2", tenant, primary_client_id)}
        for point in await connection.fetch("SELECT * FROM nexus_contact_points WHERE tenant_id=$1 AND client_id=$2", tenant, duplicate_client_id):
            if (point["channel"], point["normalized_value"]) not in primary_points:
                await connection.execute("UPDATE nexus_contact_points SET client_id=$1, updated_at=$2 WHERE id=$3", primary_client_id, now(), point["id"])
        timestamp = now()
        await connection.execute("INSERT INTO nexus_client_merges (id, tenant_id, primary_client_id, merged_client_id, details, created_at) VALUES ($1,$2,$3,$4,$5,$6) ON CONFLICT (id) DO UPDATE SET primary_client_id=EXCLUDED.primary_client_id, details=EXCLUDED.details, created_at=EXCLUDED.created_at", row_id("merge", tenant, duplicate_client_id), tenant, primary_client_id, duplicate_client_id, {"duplicate_name": duplicate["name"]}, timestamp)
        await connection.execute("INSERT INTO nexus_client_events (id, tenant_id, client_id, event_type, payload, created_at) VALUES ($1,$2,$3,'client.merge_received',$4,$5),($6,$2,$7,'client.merged',$8,$5)", row_id("event", slug, primary_client_id, "merge", duplicate_client_id, iso(timestamp)), tenant, primary_client_id, {"duplicate_client_id": duplicate_client_id}, timestamp, row_id("event", slug, duplicate_client_id, "merged", primary_client_id, iso(timestamp)), duplicate_client_id, {"primary_client_id": primary_client_id})
        client = await fetch_client(connection, slug, primary_client_id)
    return {"client": client, "merged_client": {"id": duplicate_client_id, "name": duplicate["name"]}}


async def list_tags(slug: str) -> list[str]:
    async with get_connection() as connection:
        return [str(row["name"]) for row in await connection.fetch("SELECT tag.name FROM nexus_tags tag JOIN tenants tenant ON tenant.id=tag.tenant_id WHERE tenant.slug=$1 ORDER BY tag.name", slug)]
