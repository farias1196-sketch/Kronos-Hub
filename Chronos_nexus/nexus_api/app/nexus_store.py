from __future__ import annotations

import json
import secrets
import sqlite3
from datetime import datetime
from pathlib import Path

from chronos_storage.runtime_sync import postgres_mode, run as run_postgres
from chronos_storage import nexus_runtime




LOCAL_DIR = Path(__file__).resolve().parents[3] / ".local"
DATABASE_PATH = LOCAL_DIR / "nexus.sqlite3"
ASSETS_DIR = LOCAL_DIR / "assets"


class ClosingConnection(sqlite3.Connection):
    """Close SQLite handles after each transaction, including on Windows."""

    def __exit__(self, exc_type, exc_value, traceback):
        try:
            return super().__exit__(exc_type, exc_value, traceback)
        finally:
            self.close()

CONVERSATION_STATUSES = ["novo", "em_atendimento", "aguardando_cliente", "pausado", "finalizado"]
ORDER_STATUSES = ["sem_pedido", "orcamento", "aguardando_pagamento", "em_arte", "em_producao", "pronto_para_entrega", "entregue", "cancelado"]
ART_STATUSES = ["sem_arte", "aguardando_briefing", "criando", "aguardando_aprovacao", "aprovada", "reprovada"]


def connect() -> sqlite3.Connection:
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DATABASE_PATH, timeout=5, factory=ClosingConnection)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode = WAL")
    connection.execute("PRAGMA synchronous = NORMAL")
    connection.execute("PRAGMA busy_timeout = 5000")
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def init_db() -> None:
    with connect() as db:
        db.executescript(
            """
            PRAGMA foreign_keys = ON;

            CREATE TABLE IF NOT EXISTS clients (
              id TEXT PRIMARY KEY,
              empresa_id TEXT NOT NULL,
              name TEXT NOT NULL,
              phone TEXT NOT NULL,
              fiscal_document TEXT,
              company_name TEXT,
              email TEXT,
              cep TEXT,
              address_street TEXT,
              address_number TEXT,
              address_complement TEXT,
              address_neighborhood TEXT,
              address_city TEXT,
              address_state TEXT,
              notes TEXT,
              whatsapp_lid TEXT,
              whatsapp_jid TEXT,
              registration_status TEXT NOT NULL DEFAULT 'pre-cadastro',
              registration_token TEXT,
              registration_completed_at TEXT,
              assigned_seller_id TEXT,
              assigned_seller_name TEXT,
              conversation_status TEXT NOT NULL DEFAULT 'novo',
              order_status TEXT NOT NULL DEFAULT 'sem_pedido',
              art_status TEXT NOT NULL DEFAULT 'sem_arte',
              art_briefing TEXT,
              art_link TEXT,
              art_notes TEXT,
              merged_into_client_id TEXT REFERENCES clients(id),
              merged_at TEXT,
              tags TEXT NOT NULL DEFAULT '[]',
              source TEXT NOT NULL DEFAULT 'manual',
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL,
              UNIQUE(empresa_id, phone)
            );

            CREATE TABLE IF NOT EXISTS client_events (
              id TEXT PRIMARY KEY,
              empresa_id TEXT NOT NULL,
              client_id TEXT NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
              event_type TEXT NOT NULL,
              payload TEXT NOT NULL DEFAULT '{}',
              created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS client_contact_points (
              id TEXT PRIMARY KEY,
              empresa_id TEXT NOT NULL,
              client_id TEXT NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
              channel TEXT NOT NULL,
              external_id TEXT NOT NULL,
              label TEXT,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL,
              UNIQUE(empresa_id, channel, external_id)
            );
            """
        )
        ensure_column(db, "clients", "registration_status", "TEXT NOT NULL DEFAULT 'pre-cadastro'")
        ensure_column(db, "clients", "registration_token", "TEXT")
        ensure_column(db, "clients", "registration_answers", "TEXT")
        ensure_column(db, "clients", "registration_completed_at", "TEXT")
        ensure_column(db, "clients", "assigned_seller_id", "TEXT")
        ensure_column(db, "clients", "assigned_seller_name", "TEXT")
        ensure_column(db, "clients", "whatsapp_lid", "TEXT")
        ensure_column(db, "clients", "whatsapp_jid", "TEXT")
        ensure_column(db, "clients", "art_briefing", "TEXT")
        ensure_column(db, "clients", "art_link", "TEXT")
        ensure_column(db, "clients", "art_notes", "TEXT")
        ensure_column(db, "clients", "merged_into_client_id", "TEXT")
        ensure_column(db, "clients", "merged_at", "TEXT")
        db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_clients_registration_token ON clients (registration_token)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_clients_merge_target ON clients (empresa_id, merged_into_client_id)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_contact_points_client ON client_contact_points (empresa_id, client_id)")


def ensure_column(db: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    columns = [row["name"] for row in db.execute(f"PRAGMA table_info({table})").fetchall()]
    if column not in columns:
        db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def clean_text(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def normalize_phone(value: object) -> str:
    text = clean_text(value)
    if text.lower().startswith("lid:"):
        return text.lower()
    digits = "".join(char for char in text if char.isdigit())
    return digits or text


def jid_user(value: object) -> str:
    return clean_text(value).split("@", 1)[0]


def is_lid_jid(value: object) -> bool:
    return "@lid" in clean_text(value)


def normalize_tags(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        raw_items = value.split(",")
    else:
        raw_items = list(value)
    tags = []
    for item in raw_items:
        tag = clean_text(item).lower()
        if tag and tag not in tags:
            tags.append(tag)
    return tags


def merge_tags(*tag_groups: object) -> list[str]:
    tags: list[str] = []
    for group in tag_groups:
        for tag in normalize_tags(group):
            if tag not in tags:
                tags.append(tag)
    return tags


def apply_registration_tag(tags: object, registration_status: str) -> list[str]:
    clean_tags = [tag for tag in normalize_tags(tags) if tag not in {"pre-cadastro", "cadastro-completo"}]
    if registration_status:
        clean_tags.append(registration_status)
    return clean_tags


def row_id(prefix: str, *parts: str) -> str:
    raw = "-".join(clean_text(part).lower() for part in parts if clean_text(part))
    safe = "".join(char for char in raw.replace(" ", "-") if char.isalnum() or char in "-_.")
    return f"{prefix}_{safe or 'sem-id'}"


def validate_status(value: str, allowed: list[str], fallback: str) -> str:
    value = clean_text(value)
    if not value:
        return fallback
    if value not in allowed:
        raise ValueError(f"Status invalido: {value}.")
    return value


def row_to_client(row: sqlite3.Row) -> dict:
    data = dict(row)
    data["registration_answers"] = json.loads(data.get("registration_answers") or "{}")
    try:
        data["tags"] = json.loads(data.get("tags") or "[]")
    except json.JSONDecodeError:
        data["tags"] = []
    return data


def save_contact_point(
    db: sqlite3.Connection,
    empresa_id: str,
    client_id: str,
    channel: str,
    external_id: object,
    label: str,
) -> None:
    identifier = clean_text(external_id).lower()
    if not identifier:
        return
    timestamp = now_iso()
    db.execute(
        """
        INSERT INTO client_contact_points (
          id, empresa_id, client_id, channel, external_id, label, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(empresa_id, channel, external_id) DO UPDATE SET
          client_id = excluded.client_id,
          label = coalesce(nullif(excluded.label, ''), client_contact_points.label),
          updated_at = excluded.updated_at
        """,
        (
            row_id("contact", empresa_id, channel, identifier),
            empresa_id,
            client_id,
            channel,
            identifier,
            label,
            timestamp,
            timestamp,
        ),
    )


def sync_whatsapp_contact_points(db: sqlite3.Connection, client: dict) -> None:
    if client.get("merged_into_client_id"):
        return
    empresa_id = client["empresa_id"]
    client_id = client["id"]
    label = clean_text(client.get("name")) or "WhatsApp"
    save_contact_point(db, empresa_id, client_id, "whatsapp", client.get("phone"), label)
    save_contact_point(db, empresa_id, client_id, "whatsapp", client.get("whatsapp_jid"), label)
    if client.get("whatsapp_lid"):
        save_contact_point(db, empresa_id, client_id, "whatsapp", f"lid:{client['whatsapp_lid']}", label)


def list_contact_points(empresa_id: str, client_id: str) -> list[dict]:
    if postgres_mode("nexus") == "primary":
        return run_postgres(nexus_runtime.list_contact_points(empresa_id, client_id))
    init_db()
    with connect() as db:
        client_row = db.execute(
            "SELECT * FROM clients WHERE empresa_id = ? AND id = ? AND merged_into_client_id IS NULL",
            (empresa_id, client_id),
        ).fetchone()
        if client_row:
            sync_whatsapp_contact_points(db, row_to_client(client_row))
        rows = db.execute(
            """
            SELECT id, channel, external_id, label, created_at, updated_at
              FROM client_contact_points
             WHERE empresa_id = ? AND client_id = ?
             ORDER BY channel, label COLLATE NOCASE, external_id
            """,
            (empresa_id, client_id),
        ).fetchall()
    return [dict(row) for row in rows]


def generate_registration_token() -> str:
    return secrets.token_urlsafe(24)


def client_by_phone(db: sqlite3.Connection, empresa_id: str, phone: str) -> sqlite3.Row | None:
    return db.execute("SELECT * FROM clients WHERE empresa_id = ? AND phone = ?", (empresa_id, phone)).fetchone()


def list_clients(empresa_id: str, search: str = "", tag: str = "") -> list[dict]:
    if postgres_mode("nexus") == "primary":
        return run_postgres(nexus_runtime.list_clients(empresa_id, search, tag))
    init_db()
    query = "SELECT * FROM clients WHERE empresa_id = ? AND merged_into_client_id IS NULL"
    params: list[str] = [empresa_id]
    if search:
        value = f"%{search.lower()}%"
        query += """
          AND (
            lower(name) LIKE ? OR lower(phone) LIKE ? OR lower(company_name) LIKE ?
            OR lower(fiscal_document) LIKE ? OR lower(email) LIKE ?
          )
        """
        params.extend([value, value, value, value, value])
    if tag:
        query += " AND lower(tags) LIKE ?"
        params.append(f"%{tag.lower()}%")
    query += " ORDER BY updated_at DESC, name COLLATE NOCASE"
    with connect() as db:
        return [row_to_client(row) for row in db.execute(query, params).fetchall()]


def get_client(empresa_id: str, client_id: str) -> dict | None:
    if postgres_mode("nexus") == "primary":
        return run_postgres(nexus_runtime.get_client(empresa_id, client_id))
    init_db()
    with connect() as db:
        row = db.execute("SELECT * FROM clients WHERE empresa_id = ? AND id = ?", (empresa_id, client_id)).fetchone()
    return row_to_client(row) if row else None


def upsert_client(empresa_id: str, payload: dict) -> dict:
    if postgres_mode("nexus") == "primary":
        return run_postgres(nexus_runtime.upsert_client(empresa_id, payload))
    init_db()
    name = clean_text(payload.get("name"))
    phone = normalize_phone(payload.get("phone"))
    if not name:
        raise ValueError("Nome do cliente e obrigatorio.")
    if not phone:
        raise ValueError("Numero do cliente e obrigatorio.")

    client_id = clean_text(payload.get("id")) or row_id("client", empresa_id, phone)
    updated_at = now_iso()
    registration_status = clean_text(payload.get("registration_status")) or "cadastro-completo"
    completed_at = clean_text(payload.get("registration_completed_at"))
    if registration_status == "cadastro-completo" and not completed_at:
        completed_at = updated_at
    tags = apply_registration_tag(payload.get("tags"), registration_status)
    values = {
        "id": client_id,
        "empresa_id": empresa_id,
        "name": name,
        "phone": phone,
        "fiscal_document": clean_text(payload.get("fiscal_document")),
        "company_name": clean_text(payload.get("company_name")),
        "email": clean_text(payload.get("email")),
        "cep": clean_text(payload.get("cep")),
        "address_street": clean_text(payload.get("address_street")),
        "address_number": clean_text(payload.get("address_number")),
        "address_complement": clean_text(payload.get("address_complement")),
        "address_neighborhood": clean_text(payload.get("address_neighborhood")),
        "address_city": clean_text(payload.get("address_city")),
        "address_state": clean_text(payload.get("address_state")),
        "notes": clean_text(payload.get("notes")),
        "whatsapp_lid": clean_text(payload.get("whatsapp_lid")),
        "whatsapp_jid": clean_text(payload.get("whatsapp_jid")),
        "registration_status": registration_status,
        "registration_token": clean_text(payload.get("registration_token")) or generate_registration_token(),
        "registration_completed_at": completed_at,
        "assigned_seller_id": clean_text(payload.get("assigned_seller_id")),
        "assigned_seller_name": clean_text(payload.get("assigned_seller_name")),
        "conversation_status": validate_status(payload.get("conversation_status"), CONVERSATION_STATUSES, "novo"),
        "order_status": validate_status(payload.get("order_status"), ORDER_STATUSES, "sem_pedido"),
        "art_status": validate_status(payload.get("art_status"), ART_STATUSES, "sem_arte"),
        "art_briefing": clean_text(payload.get("art_briefing")),
        "art_link": clean_text(payload.get("art_link")),
        "art_notes": clean_text(payload.get("art_notes")),
        "tags": json.dumps(tags, ensure_ascii=False),
        "source": clean_text(payload.get("source")) or "manual",
        "created_at": updated_at,
        "updated_at": updated_at,
    }

    with connect() as db:
        db.execute(
            """
            INSERT INTO clients (
              id, empresa_id, name, phone, fiscal_document, company_name, email, cep,
              address_street, address_number, address_complement, address_neighborhood,
              address_city, address_state, notes, whatsapp_lid, whatsapp_jid, conversation_status, order_status,
              registration_status, registration_token, registration_completed_at,
              assigned_seller_id, assigned_seller_name, art_status, art_briefing, art_link, art_notes,
              tags, source, created_at, updated_at
            )
            VALUES (
              :id, :empresa_id, :name, :phone, :fiscal_document, :company_name, :email, :cep,
              :address_street, :address_number, :address_complement, :address_neighborhood,
              :address_city, :address_state, :notes, :whatsapp_lid, :whatsapp_jid, :conversation_status, :order_status,
              :registration_status, :registration_token, :registration_completed_at,
              :assigned_seller_id, :assigned_seller_name, :art_status, :art_briefing, :art_link, :art_notes,
              :tags, :source, :created_at, :updated_at
            )
            ON CONFLICT(empresa_id, phone) DO UPDATE SET
              name = excluded.name,
              fiscal_document = excluded.fiscal_document,
              company_name = excluded.company_name,
              email = excluded.email,
              cep = excluded.cep,
              address_street = excluded.address_street,
              address_number = excluded.address_number,
              address_complement = excluded.address_complement,
              address_neighborhood = excluded.address_neighborhood,
              address_city = excluded.address_city,
              address_state = excluded.address_state,
              notes = excluded.notes,
              whatsapp_lid = coalesce(nullif(excluded.whatsapp_lid, ''), clients.whatsapp_lid),
              whatsapp_jid = coalesce(nullif(excluded.whatsapp_jid, ''), clients.whatsapp_jid),
              registration_status = excluded.registration_status,
              registration_token = coalesce(clients.registration_token, excluded.registration_token),
              registration_completed_at = excluded.registration_completed_at,
              assigned_seller_id = excluded.assigned_seller_id,
              assigned_seller_name = excluded.assigned_seller_name,
              conversation_status = excluded.conversation_status,
              order_status = excluded.order_status,
              art_status = excluded.art_status,
              art_briefing = excluded.art_briefing,
              art_link = excluded.art_link,
              art_notes = excluded.art_notes,
              tags = excluded.tags,
              source = excluded.source,
              updated_at = excluded.updated_at
            """,
            values,
        )
        if "registration_answers" in payload:
            old = db.execute("SELECT registration_answers FROM clients WHERE empresa_id=? AND id=?", (empresa_id,client_id)).fetchone()
            answers = {**json.loads(old[0] or "{}"), **(payload.get("registration_answers") or {})}
            db.execute("UPDATE clients SET registration_answers=? WHERE empresa_id=? AND id=?", (json.dumps(answers,ensure_ascii=False),empresa_id,client_id))
        client = db.execute("SELECT * FROM clients WHERE empresa_id = ? AND phone = ?", (empresa_id, phone)).fetchone()
        client_data = row_to_client(client)
        sync_whatsapp_contact_points(db, client_data)
        db.execute(
            """
            INSERT OR IGNORE INTO client_events (id, empresa_id, client_id, event_type, payload, created_at)
            VALUES (?, ?, ?, 'client.upsert', ?, ?)
            """,
            (
                row_id("event", empresa_id, client_data["id"], updated_at),
                empresa_id,
                client_data["id"],
                json.dumps({"source": values["source"], "tags": tags}, ensure_ascii=False),
                updated_at,
            ),
        )
        return client_data


def pre_register_client(empresa_id: str, payload: dict) -> dict:
    if postgres_mode("nexus") == "primary":
        return run_postgres(nexus_runtime.pre_register_client(empresa_id, payload))
    init_db()
    remote_jid = clean_text(payload.get("remote_jid"))
    raw_phone = clean_text(payload.get("phone"))
    lid = jid_user(remote_jid) if is_lid_jid(remote_jid) else ""
    phone = normalize_phone(raw_phone if raw_phone and not is_lid_jid(remote_jid) else f"lid:{lid}")
    if not phone:
        raise ValueError("Numero do cliente e obrigatorio.")
    fallback_name = clean_text(payload.get("display_name")) or clean_text(payload.get("name")) or phone
    updated_at = now_iso()

    with connect() as db:
        existing = client_by_phone(db, empresa_id, phone)
        if existing:
            existing_data = row_to_client(existing)
            current_status = existing_data.get("registration_status") or "pre-cadastro"
            tags = apply_registration_tag(existing_data.get("tags"), current_status)
            db.execute(
                """
                UPDATE clients
                   SET name = CASE WHEN name = phone OR name = '' THEN ? ELSE name END,
                       tags = ?,
                       whatsapp_lid = coalesce(nullif(?, ''), whatsapp_lid),
                       whatsapp_jid = coalesce(nullif(?, ''), whatsapp_jid),
                       registration_token = coalesce(registration_token, ?),
                       updated_at = ?
                 WHERE empresa_id = ? AND phone = ?
                """,
                (
                    fallback_name,
                    json.dumps(tags, ensure_ascii=False),
                    lid,
                    remote_jid,
                    existing_data.get("registration_token") or generate_registration_token(),
                    updated_at,
                    empresa_id,
                    phone,
                ),
            )
        else:
            client_id = row_id("client", empresa_id, phone)
            db.execute(
                """
                INSERT INTO clients (
                  id, empresa_id, name, phone, whatsapp_lid, whatsapp_jid, tags, source, registration_status,
                  registration_token, conversation_status, order_status, art_status,
                  created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pre-cadastro', ?, 'novo', 'sem_pedido', 'sem_arte', ?, ?)
                """,
                (
                    client_id,
                    empresa_id,
                    fallback_name,
                    phone,
                    lid,
                    remote_jid,
                    json.dumps(["pre-cadastro"], ensure_ascii=False),
                    clean_text(payload.get("source")) or "zap",
                    generate_registration_token(),
                    updated_at,
                    updated_at,
                ),
            )

        client = client_by_phone(db, empresa_id, phone)
        client_data = row_to_client(client)
        sync_whatsapp_contact_points(db, client_data)
        db.execute(
            """
            INSERT OR IGNORE INTO client_events (id, empresa_id, client_id, event_type, payload, created_at)
            VALUES (?, ?, ?, 'client.pre_register', ?, ?)
            """,
            (
                row_id("event", empresa_id, client_data["id"], updated_at),
                empresa_id,
                client_data["id"],
                json.dumps(
                    {
                        "source": clean_text(payload.get("source")) or "zap",
                        "conversation_id": clean_text(payload.get("conversation_id")),
                        "remote_jid": clean_text(payload.get("remote_jid")),
                    },
                    ensure_ascii=False,
                ),
                updated_at,
            ),
        )
        return client_data


def get_client_by_registration_token(token: str) -> dict | None:
    if postgres_mode("nexus") == "primary":
        return run_postgres(nexus_runtime.get_client_by_registration_token(token))
    init_db()
    token = clean_text(token)
    if not token:
        return None
    with connect() as db:
        row = db.execute("SELECT * FROM clients WHERE registration_token = ?", (token,)).fetchone()
    return row_to_client(row) if row else None


def complete_registration(token: str, payload: dict) -> dict:
    if postgres_mode("nexus") == "primary":
        return run_postgres(nexus_runtime.complete_registration(token, payload))
    client = get_client_by_registration_token(token)
    if not client:
        raise ValueError("Link de cadastro invalido.")
    payload = {
        **client,
        **payload,
        "id": client["id"],
        "phone": client["phone"],
        "registration_token": token,
        "registration_status": "cadastro-completo",
        "tags": apply_registration_tag(merge_tags(client.get("tags"), payload.get("tags")), "cadastro-completo"),
        "source": client.get("source") or "link-cadastro",
    }
    return upsert_client(client["empresa_id"], payload)


def delete_client(empresa_id: str, client_id: str) -> bool:
    if postgres_mode("nexus") == "primary":
        return run_postgres(nexus_runtime.delete_client(empresa_id, client_id))
    init_db()
    with connect() as db:
        cursor = db.execute("DELETE FROM clients WHERE empresa_id = ? AND id = ?", (empresa_id, client_id))
        return cursor.rowcount > 0


def merge_clients(empresa_id: str, primary_client_id: str, duplicate_client_id: str) -> dict:
    """Manually consolidate a duplicate while retaining its record and audit trail."""
    if postgres_mode("nexus") == "primary":
        return run_postgres(nexus_runtime.merge_clients(empresa_id, primary_client_id, duplicate_client_id))
    init_db()
    if primary_client_id == duplicate_client_id:
        raise ValueError("Escolha dois clientes diferentes para mesclar.")
    timestamp = now_iso()
    with connect() as db:
        primary_row = db.execute(
            "SELECT * FROM clients WHERE empresa_id = ? AND id = ? AND merged_into_client_id IS NULL",
            (empresa_id, primary_client_id),
        ).fetchone()
        duplicate_row = db.execute(
            "SELECT * FROM clients WHERE empresa_id = ? AND id = ? AND merged_into_client_id IS NULL",
            (empresa_id, duplicate_client_id),
        ).fetchone()
        if not primary_row or not duplicate_row:
            raise ValueError("Um dos clientes nao esta disponivel para mesclagem.")

        primary = row_to_client(primary_row)
        duplicate = row_to_client(duplicate_row)
        fillable_fields = [
            "fiscal_document", "company_name", "email", "cep", "address_street", "address_number",
            "address_complement", "address_neighborhood", "address_city", "address_state", "whatsapp_lid",
            "whatsapp_jid", "assigned_seller_id", "assigned_seller_name",
        ]
        updates = {field: primary.get(field) or duplicate.get(field) or "" for field in fillable_fields}
        notes = clean_text(primary.get("notes"))
        duplicate_note = clean_text(duplicate.get("notes"))
        if duplicate_note and duplicate_note not in notes:
            notes = "\n\n".join(part for part in [notes, f"Historico do cadastro mesclado ({duplicate['name']}): {duplicate_note}"] if part)
        registration_status = "cadastro-completo" if "cadastro-completo" in {
            primary.get("registration_status"), duplicate.get("registration_status")
        } else primary.get("registration_status") or duplicate.get("registration_status") or "pre-cadastro"
        tags = apply_registration_tag(merge_tags(primary.get("tags"), duplicate.get("tags")), registration_status)
        db.execute(
            f"""
            UPDATE clients
               SET {", ".join(f"{field} = ?" for field in fillable_fields)},
                   notes = ?, tags = ?, registration_status = ?, updated_at = ?
             WHERE id = ? AND empresa_id = ?
            """,
            [*updates.values(), notes, json.dumps(tags, ensure_ascii=False), registration_status, timestamp, primary_client_id, empresa_id],
        )
        db.execute(
            """
            DELETE FROM client_contact_points
             WHERE empresa_id = ?
               AND client_id = ?
               AND EXISTS (
                 SELECT 1
                   FROM client_contact_points AS primary_point
                  WHERE primary_point.empresa_id = client_contact_points.empresa_id
                    AND primary_point.client_id = ?
                    AND primary_point.channel = client_contact_points.channel
                    AND primary_point.external_id = client_contact_points.external_id
               )
            """,
            (empresa_id, duplicate_client_id, primary_client_id),
        )
        db.execute(
            """
            UPDATE client_contact_points
               SET client_id = ?, updated_at = ?
             WHERE empresa_id = ? AND client_id = ?
            """,
            (primary_client_id, timestamp, empresa_id, duplicate_client_id),
        )
        db.execute(
            """
            UPDATE clients
               SET merged_into_client_id = ?, merged_at = ?, updated_at = ?
             WHERE id = ? AND empresa_id = ?
            """,
            (primary_client_id, timestamp, timestamp, duplicate_client_id, empresa_id),
        )
        primary_after = row_to_client(
            db.execute("SELECT * FROM clients WHERE empresa_id = ? AND id = ?", (empresa_id, primary_client_id)).fetchone()
        )
        sync_whatsapp_contact_points(db, primary_after)
        db.execute(
            """
            INSERT INTO client_events (id, empresa_id, client_id, event_type, payload, created_at)
            VALUES (?, ?, ?, 'client.merge_received', ?, ?), (?, ?, ?, 'client.merged', ?, ?)
            """,
            (
                row_id("event", empresa_id, primary_client_id, "merge", duplicate_client_id, timestamp),
                empresa_id,
                primary_client_id,
                json.dumps({"duplicate_client_id": duplicate_client_id, "duplicate_name": duplicate["name"]}, ensure_ascii=False),
                timestamp,
                row_id("event", empresa_id, duplicate_client_id, "merged", primary_client_id, timestamp),
                empresa_id,
                duplicate_client_id,
                json.dumps({"primary_client_id": primary_client_id, "primary_name": primary_after["name"]}, ensure_ascii=False),
                timestamp,
            ),
        )
    return {"client": primary_after, "merged_client": {"id": duplicate_client_id, "name": duplicate["name"]}}


def list_tags(empresa_id: str) -> list[str]:
    if postgres_mode("nexus") == "primary":
        return run_postgres(nexus_runtime.list_tags(empresa_id))
    init_db()
    tags = []
    for client in list_clients(empresa_id):
        for tag in client.get("tags", []):
            if tag not in tags:
                tags.append(tag)
    return sorted(tags)


def get_status_options() -> dict:
    return {
        "conversation": CONVERSATION_STATUSES,
        "order": ORDER_STATUSES,
        "art": ART_STATUSES,
    }
