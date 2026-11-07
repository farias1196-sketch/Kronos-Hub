from __future__ import annotations

import hashlib
import json
import secrets
import sqlite3
from datetime import datetime
from pathlib import Path

import bcrypt

from chronos_storage.runtime_sync import postgres_mode, run as run_postgres
from chronos_storage import core_runtime




LOCAL_DIR = Path(__file__).resolve().parents[3] / ".local"
DATABASE_PATH = LOCAL_DIR / "core.sqlite3"
ASSETS_DIR = LOCAL_DIR / "assets"


class ClosingConnection(sqlite3.Connection):
    """SQLite's base context manager commits but does not close the file handle."""

    def __exit__(self, exc_type, exc_value, traceback):
        try:
            return super().__exit__(exc_type, exc_value, traceback)
        finally:
            self.close()


DEFAULT_MODULES = [
    ("core", "Core", "Chronos Core", "Identidade, empresas, equipe e permissoes.", "geral", "#0ea5e9", "users"),
    ("nexus", "Nexus", "Chronos Nexus", "Formularios de cadastro de clientes.", "cadastro", "#22c55e", "users-round"),
    ("zap", "Zap", "Chronos Zap", "Atendimento e mensagens pelo WhatsApp.", "atendimento", "#25d366", "message-circle"),
    ("hera", "Hera", "Chronos Hera AI", "Inteligencia artificial do Chronos.", "ia", "#a855f7", "bot"),
    ("stock", "Stock", "Chronos Stock", "Produtos, itens e estoque.", "operacao", "#f97316", "package"),
    ("pay", "Pay", "Chronos Pay", "Pagamentos e Stripe.", "financeiro", "#2563eb", "credit-card"),
    ("log", "Log", "Chronos Log", "Cotacao, etiquetas e rastreio de fretes.", "operacao", "#0284c7", "truck"),
    ("agenda", "Agenda", "Chronos Agenda", "Agendamentos de servicos.", "operacao", "#14b8a6", "calendar"),
    ("loja", "Loja", "Chronos Loja", "Site, visual e template da empresa.", "vendas", "#ec4899", "store"),
    ("promocoes", "Promo", "Chronos Promocoes", "Promocoes, encartes e disparos.", "marketing", "#eab308", "file-text"),
    ("flow", "Flow", "Chronos Flow", "Pipeline de atendimento e producao.", "operacao", "#64748b", "git-branch"),
    ("checkout", "Checkout", "Chronos Checkout", "Checkout e pedidos.", "vendas", "#10b981", "shopping-cart"),
    ("design", "Design", "Chronos Design", "Criativos e composicoes.", "marketing", "#f43f5e", "palette"),
]

DEFAULT_PERMISSIONS = [
    ("core.admin", "Administrar Core", "core"),
    ("core.company.view", "Ver empresa", "core"),
    ("core.company.manage", "Editar empresa", "core"),
    ("core.members.view", "Ver equipe", "core"),
    ("core.members.manage", "Gerenciar equipe", "core"),
    ("core.modules.view", "Ver modulos", "core"),
    ("core.modules.manage", "Gerenciar modulos", "core"),
    ("core.packages.view", "Ver pacotes", "core"),
    ("core.packages.manage", "Alterar pacote", "core"),
    ("core.audit.view", "Ver auditoria", "core"),
    ("nexus.clients.manage", "Gerenciar clientes", "nexus"),
    ("zap.chat.view", "Ver conversas do WhatsApp", "zap"),
    ("log.shipping.manage", "Gerenciar fretes", "log"),
    ("zap.chat.reply", "Responder WhatsApp", "zap"),
    ("zap.templates.manage", "Gerenciar templates do WhatsApp", "zap"),
    ("zap.campaigns.manage", "Gerenciar campanhas do WhatsApp", "zap"),
    ("zap.connections.manage", "Gerenciar conexoes do WhatsApp", "zap"),
    ("hera.settings.view", "Ver configuracoes da Hera", "hera"),
    ("hera.settings.manage", "Gerenciar Hera", "hera"),
    ("hera.transcription.use", "Usar transcricao da Hera", "hera"),
    ("hera.logs.view", "Ver logs da Hera", "hera"),
    ("promo.editor.manage", "Gerenciar Promo", "promocoes"),
    ("checkout.sales.manage", "Gerenciar vendas", "checkout"),
    ("stock.products.manage", "Gerenciar produtos", "stock"),
    ("pay.charges.manage", "Gerenciar cobrancas", "pay"),
    ("loja.store.manage", "Gerenciar loja", "loja"),
    ("agenda.events.manage", "Gerenciar agenda", "agenda"),
    ("flow.board.manage", "Gerenciar quadros Flow", "flow"),
    ("media.files.manage", "Gerenciar arquivos", "media"),
]

TENANT_ADMIN_PERMISSIONS = [permission[0] for permission in DEFAULT_PERMISSIONS]
ROLE_PERMISSION_MAP = {
    "OWNER": TENANT_ADMIN_PERMISSIONS,
    "ADMIN": [permission for permission in TENANT_ADMIN_PERMISSIONS if permission != "core.admin"],
    "MANAGER": [
        "core.company.view",
        "core.company.manage",
        "core.members.view",
        "core.modules.view",
        "core.packages.view",
        "core.audit.view",
        "nexus.clients.manage",
        "zap.chat.view",
        "zap.chat.reply",
        "zap.templates.manage",
        "zap.campaigns.manage",
        "hera.settings.view",
        "hera.settings.manage",
        "hera.transcription.use",
        "hera.logs.view",
        "promo.editor.manage",
        "stock.products.manage",
        "log.shipping.manage",
        "loja.store.manage",
        "flow.board.manage",
    ],
    "OPERATOR": [
        "core.company.view",
        "core.modules.view",
        "core.packages.view",
        "nexus.clients.manage",
        "zap.chat.view",
        "zap.chat.reply",
        "hera.transcription.use",
        "promo.editor.manage",
        "log.shipping.manage",
    ],
    "VIEWER": ["core.company.view", "core.members.view", "core.modules.view", "core.packages.view", "zap.chat.view"],
}


def connect() -> sqlite3.Connection:
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DATABASE_PATH, timeout=5, factory=ClosingConnection)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode = WAL")
    connection.execute("PRAGMA synchronous = NORMAL")
    connection.execute("PRAGMA busy_timeout = 5000")
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def init_db() -> None:
    with connect() as db:
        db.executescript(
            """
            PRAGMA foreign_keys = ON;

            CREATE TABLE IF NOT EXISTS tenants (
              id TEXT PRIMARY KEY,
              name TEXT NOT NULL,
              trade_name TEXT,
              slug TEXT NOT NULL UNIQUE,
              document TEXT,
              email TEXT,
              phone TEXT,
              status TEXT NOT NULL DEFAULT 'TRIAL',
              owner_name TEXT,
              owner_email TEXT,
              recovery_phone TEXT,
              recovery_phone_verified INTEGER NOT NULL DEFAULT 0,
              theme_slug TEXT NOT NULL DEFAULT 'rosa-branco',
              logo_url TEXT,
              fiscal_cnpj TEXT,
              fiscal_state_registration TEXT,
              fiscal_municipal_registration TEXT,
              fiscal_tax_regime TEXT,
              fiscal_cnae TEXT,
              fiscal_email TEXT,
              fiscal_phone TEXT,
              fiscal_responsible_name TEXT,
              fiscal_zip_code TEXT,
              fiscal_street TEXT,
              fiscal_number TEXT,
              fiscal_complement TEXT,
              fiscal_neighborhood TEXT,
              fiscal_city TEXT,
              fiscal_state TEXT,
              fiscal_country TEXT,
              fiscal_notes TEXT,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS users (
              id TEXT PRIMARY KEY,
              name TEXT NOT NULL,
              email TEXT NOT NULL UNIQUE,
              status TEXT NOT NULL DEFAULT 'ACTIVE',
              recovery_phone TEXT,
              recovery_phone_verified INTEGER NOT NULL DEFAULT 0,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS tenant_members (
              id TEXT PRIMARY KEY,
              tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
              user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
              role TEXT NOT NULL DEFAULT 'OPERATOR',
              title TEXT,
              department TEXT,
              active INTEGER NOT NULL DEFAULT 1,
              password_hash TEXT,
              must_change_password INTEGER NOT NULL DEFAULT 0,
              invited_at TEXT,
              invite_accepted_at TEXT,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL,
              UNIQUE(tenant_id, user_id)
            );

            CREATE TABLE IF NOT EXISTS app_modules (
              slug TEXT PRIMARY KEY,
              name TEXT NOT NULL,
              full_name TEXT NOT NULL,
              description TEXT NOT NULL,
              category TEXT NOT NULL,
              color TEXT NOT NULL,
              icon TEXT NOT NULL,
              active INTEGER NOT NULL DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS tenant_modules (
              tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
              module_slug TEXT NOT NULL REFERENCES app_modules(slug) ON DELETE CASCADE,
              status TEXT NOT NULL DEFAULT 'ACTIVE',
              show_in_menu INTEGER NOT NULL DEFAULT 1,
              PRIMARY KEY (tenant_id, module_slug)
            );

            CREATE TABLE IF NOT EXISTS packages (
              slug TEXT PRIMARY KEY,
              name TEXT NOT NULL,
              monthly_price REAL NOT NULL DEFAULT 0,
              ai_weekly_credits INTEGER,
              active INTEGER NOT NULL DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS subscriptions (
              id TEXT PRIMARY KEY,
              tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
              package_slug TEXT REFERENCES packages(slug),
              status TEXT NOT NULL,
              starts_at TEXT,
              ends_at TEXT,
              updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS permissions (
              key TEXT PRIMARY KEY,
              label TEXT NOT NULL,
              module_slug TEXT NOT NULL,
              description TEXT,
              created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS member_permissions (
              member_id TEXT NOT NULL REFERENCES tenant_members(id) ON DELETE CASCADE,
              permission_key TEXT NOT NULL REFERENCES permissions(key) ON DELETE CASCADE,
              created_at TEXT NOT NULL,
              PRIMARY KEY (member_id, permission_key)
            );

            CREATE TABLE IF NOT EXISTS billing_invoices (
              id TEXT PRIMARY KEY,
              tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
              subscription_id TEXT,
              billing_month TEXT NOT NULL,
              title TEXT NOT NULL,
              description TEXT,
              amount REAL NOT NULL DEFAULT 0,
              due_date TEXT,
              status TEXT NOT NULL DEFAULT 'OPEN',
              provider TEXT NOT NULL DEFAULT 'MANUAL',
              checkout_url TEXT,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS audit_logs (
              id TEXT PRIMARY KEY,
              tenant_id TEXT REFERENCES tenants(id) ON DELETE CASCADE,
              actor_member_id TEXT,
              action TEXT NOT NULL,
              entity TEXT NOT NULL,
              entity_id TEXT,
              metadata TEXT,
              created_at TEXT NOT NULL
            );
            """
        )
        existing_columns = {
            row["name"] for row in db.execute("PRAGMA table_info(tenants)").fetchall()
        }
        fiscal_columns = {
            "chronos_facil": "INTEGER NOT NULL DEFAULT 0",
            "fiscal_cnpj": "TEXT",
            "fiscal_state_registration": "TEXT",
            "fiscal_municipal_registration": "TEXT",
            "fiscal_tax_regime": "TEXT",
            "fiscal_cnae": "TEXT",
            "fiscal_email": "TEXT",
            "fiscal_phone": "TEXT",
            "fiscal_responsible_name": "TEXT",
            "fiscal_zip_code": "TEXT",
            "fiscal_street": "TEXT",
            "fiscal_number": "TEXT",
            "fiscal_complement": "TEXT",
            "fiscal_neighborhood": "TEXT",
            "fiscal_city": "TEXT",
            "fiscal_state": "TEXT",
            "fiscal_country": "TEXT",
            "fiscal_notes": "TEXT",
        }
        for column, column_type in fiscal_columns.items():
            if column not in existing_columns:
                db.execute(f"ALTER TABLE tenants ADD COLUMN {column} {column_type}")
        member_columns = {
            row["name"] for row in db.execute("PRAGMA table_info(tenant_members)").fetchall()
        }
        member_extra_columns = {
            "password_hash": "TEXT",
            "must_change_password": "INTEGER NOT NULL DEFAULT 0",
            "invited_at": "TEXT",
            "invite_accepted_at": "TEXT",
        }
        for column, column_type in member_extra_columns.items():
            if column not in member_columns:
                db.execute(f"ALTER TABLE tenant_members ADD COLUMN {column} {column_type}")
        db.executemany(
            """
            INSERT INTO app_modules (slug, name, full_name, description, category, color, icon, active)
            VALUES (?, ?, ?, ?, ?, ?, ?, 1)
            ON CONFLICT(slug) DO UPDATE SET
              name = excluded.name,
              full_name = excluded.full_name,
              description = excluded.description,
              category = excluded.category,
              color = excluded.color,
              icon = excluded.icon,
              active = 1
            """,
            DEFAULT_MODULES,
        )
        db.executemany(
            """
            INSERT INTO permissions (key, label, module_slug, description, created_at)
            VALUES (?, ?, ?, '', CURRENT_TIMESTAMP)
            ON CONFLICT(key) DO UPDATE SET
              label = excluded.label,
              module_slug = excluded.module_slug
            """,
            DEFAULT_PERMISSIONS,
        )


def now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def audit_log(tenant_id: str | None, action: str, entity: str, entity_id: str = "", metadata: dict | None = None) -> None:
    with connect() as db:
        db.execute(
            """
            INSERT INTO audit_logs (id, tenant_id, actor_member_id, action, entity, entity_id, metadata, created_at)
            VALUES (?, ?, '', ?, ?, ?, ?, ?)
            """,
            (
                row_id("audit", f"{action}-{entity_id}-{secrets.token_hex(6)}"),
                tenant_id,
                action,
                entity,
                entity_id,
                json.dumps(metadata or {}, ensure_ascii=False),
                now_iso(),
            ),
        )


def role_permissions(role: str) -> list[str]:
    return ROLE_PERMISSION_MAP.get(clean_text(role).upper(), ROLE_PERMISSION_MAP["VIEWER"])


def enable_all_modules_for_all_tenants() -> None:
    if postgres_mode("core") == "primary":
        run_postgres(core_runtime.enable_all_modules())
        return
    init_db()
    with connect() as db:
        tenants = db.execute("SELECT id FROM tenants").fetchall()
        modules = db.execute("SELECT slug FROM app_modules WHERE active = 1").fetchall()
        for tenant in tenants:
            for module in modules:
                db.execute(
                    """
                    INSERT OR IGNORE INTO tenant_modules (tenant_id, module_slug, status, show_in_menu)
                    VALUES (?, ?, 'ACTIVE', 1)
                    """,
                    (tenant["id"], module["slug"]),
                )


def clean_text(value: object) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if not text or text == "-":
        return ""
    try:
        fixed = text.encode("latin1").decode("utf-8")
        if "Ã" in text or "Â" in text:
            return fixed
    except UnicodeError:
        pass
    replacements = {
        "Ã§": "ç",
        "Ã£": "ã",
        "Ã¡": "á",
        "Ã©": "é",
        "Ã­": "í",
        "Ã³": "ó",
        "Ãº": "ú",
        "Ãª": "ê",
        "Ã´": "ô",
        "Ã‡": "Ç",
        "Ãƒ": "Ã",
        "Â": "",
    }
    for wrong, right in replacements.items():
        text = text.replace(wrong, right)
    return text


def row_id(prefix: str, value: str) -> str:
    safe = clean_text(value).lower().replace(" ", "-")
    safe = "".join(char for char in safe if char.isalnum() or char in "-_.")
    return f"{prefix}_{safe or 'sem-id'}"


def truthy(value: object) -> int:
    return 1 if str(value).strip().lower() in {"1", "t", "true", "sim", "yes"} else 0


def parse_money(value: object) -> float:
    text = clean_text(value).replace("R$", "").strip()
    if not text:
        return 0.0
    if "," in text:
        text = text.replace(".", "").replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return 0.0




def rows_to_dicts(rows: list[sqlite3.Row]) -> list[dict]:
    return [dict(row) for row in rows]


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 120_000)
    return f"pbkdf2_sha256$120000${salt}${digest.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    if not stored_hash:
        return False
    if stored_hash.startswith(("$2a$", "$2b$", "$2y$")):
        try:
            return bcrypt.checkpw(password.encode("utf-8"), stored_hash.encode("utf-8"))
        except (ValueError, TypeError):
            return False
    try:
        algorithm, iterations, salt, expected = stored_hash.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt.encode("utf-8"),
            int(iterations),
        ).hex()
        return secrets.compare_digest(digest, expected)
    except (ValueError, TypeError):
        return False


def normalize_role(role: str) -> str:
    role = clean_text(role).upper()
    return role if role in {"ADMIN", "MANAGER", "OPERATOR", "VIEWER"} else "OPERATOR"


def get_summary() -> dict:
    if postgres_mode("core") == "primary":
        return run_postgres(core_runtime.get_summary())
    init_db()
    with connect() as db:
        tenants = db.execute("SELECT COUNT(*) AS total FROM tenants").fetchone()["total"]
        active_tenants = db.execute("SELECT COUNT(*) AS total FROM tenants WHERE status = 'ACTIVE'").fetchone()["total"]
        users = db.execute("SELECT COUNT(*) AS total FROM users").fetchone()["total"]
        active_members = db.execute("SELECT COUNT(*) AS total FROM tenant_members WHERE active = 1").fetchone()["total"]
        modules = db.execute("SELECT COUNT(*) AS total FROM app_modules WHERE active = 1").fetchone()["total"]
    return {
        "tenants": tenants,
        "activeTenants": active_tenants,
        "users": users,
        "activeMembers": active_members,
        "activeModules": modules,
        "database": str(DATABASE_PATH),
    }


def list_tenants(search: str = "") -> list[dict]:
    if postgres_mode("core") == "primary":
        return run_postgres(core_runtime.list_tenants(search))
    init_db()
    query = """
      SELECT
        t.*,
        s.package_slug,
        p.name AS package_name,
        p.monthly_price,
        p.ai_weekly_credits,
        COUNT(DISTINCT tm.user_id) AS members_count,
        COUNT(DISTINCT tmod.module_slug) AS modules_count
      FROM tenants t
      LEFT JOIN subscriptions s ON s.tenant_id = t.id
      LEFT JOIN packages p ON p.slug = s.package_slug
      LEFT JOIN tenant_members tm ON tm.tenant_id = t.id AND tm.active = 1
      LEFT JOIN tenant_modules tmod ON tmod.tenant_id = t.id AND tmod.status = 'ACTIVE'
    """
    params: list[str] = []
    if search:
        query += " WHERE lower(t.name) LIKE ? OR lower(t.trade_name) LIKE ? OR lower(t.slug) LIKE ? OR lower(t.email) LIKE ?"
        value = f"%{search.lower()}%"
        params.extend([value, value, value, value])
    query += " GROUP BY t.id ORDER BY t.name COLLATE NOCASE"
    with connect() as db:
        return rows_to_dicts(db.execute(query, params).fetchall())


def get_tenant(slug: str) -> dict | None:
    if postgres_mode("core") == "primary":
        return run_postgres(core_runtime.get_tenant(slug, role_permissions))
    init_db()
    with connect() as db:
        tenant = db.execute("SELECT * FROM tenants WHERE slug = ?", (slug,)).fetchone()
        if not tenant:
            return None
        data = dict(tenant)
        data["chronos_facil"] = bool(data.get("chronos_facil", False))
        data["members"] = rows_to_dicts(
            db.execute(
                """
                SELECT tm.id, tm.role, tm.title, tm.department, tm.active, u.name, u.email, u.status,
                       u.recovery_phone, u.recovery_phone_verified,
                       CASE WHEN tm.password_hash IS NOT NULL AND tm.password_hash != '' THEN 1 ELSE 0 END AS password_configured,
                       tm.must_change_password,
                       tm.invited_at, tm.invite_accepted_at
                FROM tenant_members tm
                JOIN users u ON u.id = tm.user_id
                WHERE tm.tenant_id = ?
                ORDER BY
                  CASE tm.role WHEN 'OWNER' THEN 0 WHEN 'ADMIN' THEN 1 WHEN 'MANAGER' THEN 2 ELSE 3 END,
                  u.name COLLATE NOCASE
                """,
                (data["id"],),
            ).fetchall()
        )
        for member in data["members"]:
            explicit = db.execute(
                "SELECT permission_key FROM member_permissions WHERE member_id = ?",
                (member["id"],),
            ).fetchall()
            explicit_permissions = [row["permission_key"] for row in explicit]
            member["explicit_permissions"] = explicit_permissions
            member["effective_permissions"] = sorted(set(role_permissions(member["role"]) + explicit_permissions))
        data["modules"] = rows_to_dicts(
            db.execute(
                """
                SELECT m.slug, m.name, m.full_name, m.color, m.icon, tm.status, tm.show_in_menu
                FROM tenant_modules tm
                JOIN app_modules m ON m.slug = tm.module_slug
                WHERE tm.tenant_id = ?
                ORDER BY m.name COLLATE NOCASE
                """,
                (data["id"],),
            ).fetchall()
        )
        data["subscription"] = (
            dict(
                db.execute(
                    """
                    SELECT s.*, p.name AS package_name, p.monthly_price, p.ai_weekly_credits
                    FROM subscriptions s
                    LEFT JOIN packages p ON p.slug = s.package_slug
                    WHERE s.tenant_id = ?
                    """,
                    (data["id"],),
                ).fetchone()
                or {}
            )
        )
        data["billing"] = {"invoices": list_billing_invoices_by_tenant_id(data["id"])}
        return data


def update_tenant_logo(slug: str, logo_url: str) -> dict | None:
    if postgres_mode("core") == "primary":
        return run_postgres(core_runtime.update_logo(slug, logo_url, role_permissions))
    init_db()
    tenant = get_tenant(slug)
    with connect() as db:
        db.execute(
            "UPDATE tenants SET logo_url = ?, updated_at = ? WHERE slug = ?",
            (logo_url, now_iso(), slug),
        )
    if tenant:
        audit_log(tenant["id"], "core.company.logo_update", "Tenant", tenant["id"])
    return get_tenant(slug)


FISCAL_FIELDS = [
    "chronos_facil",
    "name",
    "trade_name",
    "document",
    "email",
    "phone",
    "theme_slug",
    "fiscal_cnpj",
    "fiscal_state_registration",
    "fiscal_municipal_registration",
    "fiscal_tax_regime",
    "fiscal_cnae",
    "fiscal_email",
    "fiscal_phone",
    "fiscal_responsible_name",
    "fiscal_zip_code",
    "fiscal_street",
    "fiscal_number",
    "fiscal_complement",
    "fiscal_neighborhood",
    "fiscal_city",
    "fiscal_state",
    "fiscal_country",
    "fiscal_notes",
]


def update_tenant_fiscal_data(slug: str, data: dict) -> dict | None:
    if postgres_mode("core") == "primary":
        return run_postgres(core_runtime.update_fiscal(slug, data, role_permissions))
    init_db()
    tenant = get_tenant(slug)
    fields = [field for field in FISCAL_FIELDS if field in data]
    if not fields:
        return get_tenant(slug)

    assignments = ", ".join(f"{field} = ?" for field in fields)
    values = [int(data[field]) if field == "chronos_facil" else clean_text(data.get(field)) for field in fields]
    values.extend([now_iso(), slug])

    with connect() as db:
        db.execute(
            f"UPDATE tenants SET {assignments}, updated_at = ? WHERE slug = ?",
            values,
        )
    if tenant:
        audit_log(tenant["id"], "core.company.fiscal_update", "Tenant", tenant["id"], {"fields": fields})
    return get_tenant(slug)


def create_or_update_member(slug: str, data: dict) -> dict | None:
    if postgres_mode("core") == "primary":
        return run_postgres(core_runtime.create_or_update_member(slug, data, role_permissions))
    init_db()
    tenant = get_tenant(slug)
    if not tenant:
        return None

    name = clean_text(data.get("name"))
    email = clean_text(data.get("email")).lower()
    role = normalize_role(data.get("role", "OPERATOR"))
    password = clean_text(data.get("temporary_password"))
    title = clean_text(data.get("title"))
    department = clean_text(data.get("department"))
    created_at = now_iso()

    if not name or not email:
        raise ValueError("Nome e e-mail sao obrigatorios.")
    if password and len(password) < 8:
        raise ValueError("A senha provisoria precisa ter pelo menos 8 caracteres.")

    user_id = row_id("user", email)
    member_id = row_id("member", f"{slug}-{email}")
    password_hash = hash_password(password) if password else None
    user_status = "ACTIVE" if password_hash else "INVITED"

    with connect() as db:
        db.execute(
            """
            INSERT INTO users (id, name, email, status, recovery_phone, recovery_phone_verified, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(email) DO UPDATE SET
              name = excluded.name,
              status = CASE WHEN excluded.status = 'ACTIVE' THEN 'ACTIVE' ELSE users.status END,
              recovery_phone = COALESCE(NULLIF(excluded.recovery_phone, ''), users.recovery_phone),
              recovery_phone_verified = CASE
                WHEN excluded.recovery_phone_verified = 1 THEN 1
                ELSE users.recovery_phone_verified
              END,
              updated_at = excluded.updated_at
            """,
            (user_id, name, email, user_status, "", 0, created_at, created_at),
        )
        user = db.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
        real_user_id = user["id"] if user else user_id
        db.execute(
            """
            INSERT INTO tenant_members (
              id, tenant_id, user_id, role, title, department, active, password_hash,
              must_change_password, invited_at, invite_accepted_at, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(tenant_id, user_id) DO UPDATE SET
              role = excluded.role,
              title = excluded.title,
              department = excluded.department,
              active = 1,
              password_hash = COALESCE(excluded.password_hash, tenant_members.password_hash),
              must_change_password = CASE
                WHEN excluded.password_hash IS NOT NULL THEN 1
                ELSE tenant_members.must_change_password
              END,
              invited_at = COALESCE(tenant_members.invited_at, excluded.invited_at),
              updated_at = excluded.updated_at
            """,
            (
                member_id,
                tenant["id"],
                real_user_id,
                role,
                title,
                department,
                password_hash,
                1 if password_hash else 0,
                created_at,
                created_at if password_hash else "",
                created_at,
                created_at,
            ),
        )

    audit_log(
        tenant["id"],
        "core.member.upsert",
        "TenantMember",
        member_id,
        {"email": email, "role": role, "temporaryPassword": bool(password_hash)},
    )
    return get_tenant(slug)


def update_member_password(slug: str, member_id: str, password: str) -> dict | None:
    if postgres_mode("core") == "primary":
        return run_postgres(core_runtime.update_member_password(slug, member_id, password, role_permissions))
    init_db()
    password = clean_text(password)
    if len(password) < 8:
        raise ValueError("A senha precisa ter pelo menos 8 caracteres.")
    tenant = get_tenant(slug)
    if not tenant:
        return None
    password_hash = hash_password(password)
    updated_at = now_iso()
    with connect() as db:
        member = db.execute(
            "SELECT user_id FROM tenant_members WHERE id = ? AND tenant_id = ?",
            (member_id, tenant["id"]),
        ).fetchone()
        if not member:
            return None
        db.execute(
            """
            UPDATE tenant_members
            SET password_hash = ?, must_change_password = 1, invite_accepted_at = ?, updated_at = ?
            WHERE id = ? AND tenant_id = ?
            """,
            (password_hash, updated_at, updated_at, member_id, tenant["id"]),
        )
        db.execute(
            "UPDATE users SET status = 'ACTIVE', updated_at = ? WHERE id = ?",
            (updated_at, member["user_id"]),
        )
    audit_log(tenant["id"], "core.member.password_update", "TenantMember", member_id)
    return get_tenant(slug)


def update_member_status(slug: str, member_id: str, active: bool) -> dict | None:
    if postgres_mode("core") == "primary":
        return run_postgres(core_runtime.update_member_status(slug, member_id, active, role_permissions))
    init_db()
    tenant = get_tenant(slug)
    if not tenant:
        return None
    with connect() as db:
        db.execute(
            "UPDATE tenant_members SET active = ?, updated_at = ? WHERE id = ? AND tenant_id = ?",
            (1 if active else 0, now_iso(), member_id, tenant["id"]),
        )
    audit_log(tenant["id"], "core.member.status_update", "TenantMember", member_id, {"active": active})
    return get_tenant(slug)


def verify_company_login(slug: str, email: str, password: str) -> dict:
    if postgres_mode("core") == "primary":
        return run_postgres(core_runtime.verify_login(slug, email, password, role_permissions))
    init_db()
    email = clean_text(email).lower()
    password = clean_text(password)
    with connect() as db:
        member = db.execute(
            """
            SELECT tm.id, tm.role, tm.active, tm.password_hash, tm.must_change_password,
                   t.id AS tenant_id, t.slug AS tenant_slug, t.name AS tenant_name, t.trade_name,
                   t.status AS tenant_status, u.id AS user_id, u.name AS user_name, u.email,
                   u.status AS user_status
            FROM tenant_members tm
            JOIN tenants t ON t.id = tm.tenant_id
            JOIN users u ON u.id = tm.user_id
            WHERE t.slug = ? AND lower(u.email) = ?
            """,
            (slug, email),
        ).fetchone()

    if not member:
        return {"ok": False, "reason": "invalid_credentials"}
    data = dict(member)
    if not data["active"] or data["tenant_status"] not in {"ACTIVE", "TRIAL"} or data["user_status"] == "DISABLED":
        return {"ok": False, "reason": "inactive_access"}
    if not verify_password(password, data["password_hash"] or ""):
        return {"ok": False, "reason": "invalid_credentials"}
    audit_log(data["tenant_id"], "core.auth.login", "User", data["user_id"], {"email": data["email"]})
    return {
        "ok": True,
        "mustChangePassword": bool(data["must_change_password"]),
        "permissions": member_effective_permissions(data["id"], data["role"]),
        "user": {
            "id": data["user_id"],
            "member_id": data["id"],
            "name": data["user_name"],
            "email": data["email"],
            "role": data["role"],
        },
        "tenant": {
            "id": data["tenant_id"],
            "slug": data["tenant_slug"],
            "name": data["trade_name"] or data["tenant_name"],
            "status": data["tenant_status"],
        },
    }


def member_effective_permissions(member_id: str, role: str) -> list[str]:
    with connect() as db:
        explicit = db.execute("SELECT permission_key FROM member_permissions WHERE member_id = ?", (member_id,)).fetchall()
    return sorted(set(role_permissions(role)) | {row["permission_key"] for row in explicit})


def authenticated_member(user_id: str, slug: str, member_id: str | None = None) -> dict | None:
    if postgres_mode("core") == "primary":
        return run_postgres(core_runtime.authenticated_member(user_id, slug, member_id, role_permissions))
    init_db()
    with connect() as db:
        row = db.execute(
            """SELECT tm.id AS member_id, tm.role, tm.active, tm.must_change_password,
                      u.id AS user_id, u.name, u.email, u.status AS user_status,
                      t.id AS tenant_id, t.slug, t.name AS tenant_name, t.status
               FROM tenant_members tm JOIN users u ON u.id = tm.user_id
               JOIN tenants t ON t.id = tm.tenant_id
               WHERE u.id = ? AND t.slug = ?""", (user_id, slug),
        ).fetchone()
    if not row or not row["active"] or row["user_status"] == "DISABLED" or row["status"] not in {"ACTIVE", "TRIAL"} or row["must_change_password"]:
        return None
    if member_id is not None and row["member_id"] != member_id:
        return None
    return {
        "ok": True,
        "user": {"id": row["user_id"], "member_id": row["member_id"], "name": row["name"], "email": row["email"], "role": row["role"]},
        "tenant": {"id": row["tenant_id"], "slug": row["slug"], "name": row["tenant_name"], "status": row["status"]},
        "permissions": member_effective_permissions(row["member_id"], row["role"]),
    }


def find_tenant_for_login(identifier: str) -> dict | None:
    if postgres_mode("core") == "primary":
        return run_postgres(core_runtime.find_tenant(identifier))
    init_db()
    value = clean_text(identifier).lower()
    if not value:
        return None
    with connect() as db:
        tenant = db.execute(
            """
            SELECT id, slug, name, trade_name, status, logo_url
            FROM tenants
            WHERE status IN ('ACTIVE', 'TRIAL')
              AND (lower(slug) = ? OR lower(name) = ? OR lower(trade_name) = ?)
            """,
            (value, value, value),
        ).fetchone()
    return dict(tenant) if tenant else None


def search_tenants_for_login(prefix: str, limit: int = 8) -> list[dict]:
    if postgres_mode("core") == "primary":
        return run_postgres(core_runtime.search_tenants(prefix, limit))
    """Return a deliberately small public login chooser after three typed characters."""
    init_db()
    value = clean_text(prefix).lower()
    if len(value) < 3:
        return []
    safe_limit = max(1, min(int(limit), 8))
    like = f"{value}%"
    with connect() as db:
        rows = db.execute(
            """
            SELECT id, slug, name, trade_name, logo_url
            FROM tenants
            WHERE status IN ('ACTIVE', 'TRIAL')
              AND (
                lower(slug) LIKE ?
                OR lower(name) LIKE ?
                OR lower(coalesce(trade_name, '')) LIKE ?
              )
            ORDER BY
              CASE
                WHEN lower(slug) = ? OR lower(name) = ? OR lower(coalesce(trade_name, '')) = ? THEN 0
                ELSE 1
              END,
              name COLLATE NOCASE
            LIMIT ?
            """,
            (like, like, like, value, value, value, safe_limit),
        ).fetchall()
    return [dict(row) for row in rows]


def change_first_login_password(slug: str, email: str, current_password: str, new_password: str) -> dict:
    if postgres_mode("core") == "primary":
        return run_postgres(core_runtime.change_first_login_password(slug, email, current_password, new_password, role_permissions))
    login = verify_company_login(slug, email, current_password)
    if not login["ok"]:
        return login
    if len(clean_text(new_password)) < 8:
        raise ValueError("A nova senha precisa ter pelo menos 8 caracteres.")

    with connect() as db:
        member = db.execute(
            """
            SELECT tm.id, tm.tenant_id
            FROM tenant_members tm
            JOIN tenants t ON t.id = tm.tenant_id
            JOIN users u ON u.id = tm.user_id
            WHERE t.slug = ? AND lower(u.email) = ?
            """,
            (slug, clean_text(email).lower()),
        ).fetchone()
        if not member:
            return {"ok": False, "reason": "invalid_credentials"}
        db.execute(
            """
            UPDATE tenant_members
            SET password_hash = ?, must_change_password = 0, invite_accepted_at = ?, updated_at = ?
            WHERE id = ?
            """,
            (hash_password(new_password), now_iso(), now_iso(), member["id"]),
        )
    audit_log(member["tenant_id"], "core.auth.first_password_change", "TenantMember", member["id"])
    return verify_company_login(slug, email, new_password)


def list_billing_invoices_by_tenant_id(tenant_id: str) -> list[dict]:
    with connect() as db:
        return rows_to_dicts(
            db.execute(
                """
                SELECT *
                FROM billing_invoices
                WHERE tenant_id = ?
                ORDER BY billing_month DESC, created_at DESC
                """,
                (tenant_id,),
            ).fetchall()
        )


def ensure_current_invoice(slug: str) -> dict | None:
    if postgres_mode("core") == "primary":
        return run_postgres(core_runtime.ensure_current_invoice(slug, role_permissions))
    init_db()
    tenant = get_tenant(slug)
    if not tenant:
        return None
    subscription = tenant.get("subscription") or {}
    package_name = subscription.get("package_name") or "Chronos Hub"
    amount = float(subscription.get("monthly_price") or 0)
    billing_month = datetime.utcnow().strftime("%Y-%m")
    invoice_id = row_id("invoice", f"{slug}-{billing_month}")
    with connect() as db:
        db.execute(
            """
            INSERT INTO billing_invoices (
              id, tenant_id, subscription_id, billing_month, title, description, amount,
              due_date, status, provider, checkout_url, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'OPEN', 'MANUAL', '', ?, ?)
            ON CONFLICT(id) DO UPDATE SET
              title = excluded.title,
              description = excluded.description,
              amount = excluded.amount,
              updated_at = excluded.updated_at
            """,
            (
                invoice_id,
                tenant["id"],
                subscription.get("id", ""),
                billing_month,
                f"Mensalidade {package_name}",
                "Plano mensal de limite e uso da Hera AI.",
                amount,
                f"{billing_month}-10",
                now_iso(),
                now_iso(),
            ),
        )
    audit_log(tenant["id"], "core.billing.invoice_prepare", "BillingInvoice", invoice_id)
    return get_tenant(slug)


def list_audit_logs(slug: str, limit: int = 50) -> list[dict] | None:
    if postgres_mode("core") == "primary":
        return run_postgres(core_runtime.list_audit_logs(slug, limit))
    init_db()
    tenant = get_tenant(slug)
    if not tenant:
        return None
    with connect() as db:
        return rows_to_dicts(
            db.execute(
                """
                SELECT *
                FROM audit_logs
                WHERE tenant_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (tenant["id"], max(1, min(limit, 100))),
            ).fetchall()
        )


def get_tenant_context(slug: str) -> dict | None:
    tenant = get_tenant(slug)
    if not tenant:
        return None
    return {
        "id": tenant["id"],
        "slug": tenant["slug"],
        "name": tenant["trade_name"] or tenant["name"],
        "status": tenant["status"],
        "logoUrl": tenant.get("logo_url"),
        "themeSlug": tenant.get("theme_slug"),
        "package": tenant.get("subscription"),
        "modules": tenant.get("modules", []),
    }


def list_modules() -> list[dict]:
    if postgres_mode("core") == "primary":
        return run_postgres(core_runtime.list_modules())
    init_db()
    with connect() as db:
        return rows_to_dicts(db.execute("SELECT * FROM app_modules ORDER BY name COLLATE NOCASE").fetchall())
