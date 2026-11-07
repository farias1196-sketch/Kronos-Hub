"""PostgreSQL adapter for Chronos Core's existing synchronous API contract."""

from __future__ import annotations

import hashlib
import secrets
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Callable

import bcrypt

from .postgres import get_connection, transaction


def clean(value: object) -> str:
    return "" if value is None else str(value).strip()


def iso(value: datetime | None) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z") if value else ""


def numeric(value: Any) -> float:
    return float(value) if isinstance(value, Decimal) else float(value or 0)


def row_id(prefix: str, *parts: object) -> str:
    raw = "-".join(clean(part).lower() for part in parts if clean(part))
    safe = "".join(char for char in raw.replace(" ", "-") if char.isalnum() or char in "-_.")
    return f"{prefix}_{safe or 'sem-id'}"


def now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


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
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), int(iterations)).hex()
        return secrets.compare_digest(digest, expected)
    except (ValueError, TypeError):
        return False


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 120_000).hex()
    return f"pbkdf2_sha256$120000${salt}${digest}"


def tenant_dict(row: Any) -> dict[str, Any]:
    data = dict(row)
    fiscal = dict(data.pop("fiscal_data", {}) or {})
    settings = dict(data.pop("settings", {}) or {})
    data["chronos_facil"] = settings.get("chronos_facil") is True
    data["implementation_stage"] = settings.get("implementation_stage", 1 if data["chronos_facil"] else 4)
    data.update({f"fiscal_{key}": value for key, value in fiscal.items()})
    data.update({key: value for key, value in settings.items() if key in {"owner_name", "owner_email", "recovery_phone"}})
    data["created_at"], data["updated_at"] = iso(data.get("created_at")), iso(data.get("updated_at"))
    return data


async def audit(connection: Any, tenant_id: str, action: str, entity: str, entity_id: str = "", metadata: dict | None = None) -> None:
    stamp = now()
    await connection.execute("INSERT INTO audit_logs (id, tenant_id, module_slug, action, entity_type, entity_id, metadata, created_at) VALUES ($1,$2,'core',$3,$4,$5,$6,$7) ON CONFLICT (id) DO NOTHING", row_id("audit", tenant_id, action, entity_id, iso(stamp)), tenant_id, action, entity, entity_id, metadata or {}, stamp)


async def tenant_row(connection: Any, slug: str) -> Any:
    return await connection.fetchrow("SELECT * FROM tenants WHERE slug=$1", slug)


async def get_summary() -> dict[str, Any]:
    async with get_connection() as connection:
        row = await connection.fetchrow("SELECT (SELECT count(*) FROM tenants) tenants, (SELECT count(*) FROM tenants WHERE status='ACTIVE') active_tenants, (SELECT count(*) FROM users) users, (SELECT count(*) FROM tenant_members WHERE active) active_members, (SELECT count(*) FROM app_modules WHERE status='ACTIVE') active_modules")
    return {"tenants": int(row["tenants"]), "activeTenants": int(row["active_tenants"]), "users": int(row["users"]), "activeMembers": int(row["active_members"]), "activeModules": int(row["active_modules"]), "database": "PostgreSQL"}


async def list_tenants(search: str = "") -> list[dict[str, Any]]:
    filters, args = [], []
    if clean(search):
        args.append(f"%{clean(search).lower()}%")
        filters.append("(lower(t.name) LIKE $1 OR lower(coalesce(t.trade_name,'')) LIKE $1 OR lower(t.slug) LIKE $1 OR lower(coalesce(t.email,'')) LIKE $1)")
    where = f"WHERE {' AND '.join(filters)}" if filters else ""
    async with get_connection() as connection:
        rows = await connection.fetch(f"""SELECT t.*, s.plan_slug AS package_slug, p.name AS package_name, p.monthly_price, p.ai_weekly_credits, count(DISTINCT tm.user_id) FILTER (WHERE tm.active) AS members_count, count(DISTINCT mt.module_slug) FILTER (WHERE mt.status='ACTIVE') AS modules_count FROM tenants t LEFT JOIN tenant_subscriptions s ON s.tenant_id=t.id LEFT JOIN billing_plans p ON p.slug=s.plan_slug LEFT JOIN tenant_members tm ON tm.tenant_id=t.id LEFT JOIN tenant_modules mt ON mt.tenant_id=t.id {where} GROUP BY t.id,s.plan_slug,p.name,p.monthly_price,p.ai_weekly_credits ORDER BY t.name""", *args)
    result = []
    for row in rows:
        item = tenant_dict(row); item["monthly_price"] = numeric(item.get("monthly_price")); item["members_count"] = int(item.get("members_count") or 0); item["modules_count"] = int(item.get("modules_count") or 0); result.append(item)
    return result


async def get_tenant(slug: str, role_permissions: Callable[[str], list[str]]) -> dict[str, Any] | None:
    async with get_connection() as connection:
        row = await tenant_row(connection, slug)
        if not row:
            return None
        data = tenant_dict(row); tenant = str(row["id"])
        members = await connection.fetch("""SELECT tm.id,tm.role,tm.title,tm.department,tm.active,tm.password_hash,tm.permissions,tm.must_change_password,tm.invited_at,tm.invite_accepted_at,u.name,u.email,u.status,u.recovery_phone,u.recovery_phone_verified FROM tenant_members tm JOIN users u ON u.id=tm.user_id WHERE tm.tenant_id=$1 ORDER BY CASE tm.role WHEN 'OWNER' THEN 0 WHEN 'ADMIN' THEN 1 WHEN 'MANAGER' THEN 2 ELSE 3 END,u.name""", tenant)
        data["members"] = []
        for member in members:
            item = dict(member); explicit = list(item.pop("permissions") or []); item["password_configured"] = bool(item.pop("password_hash") or ""); item["explicit_permissions"] = explicit; item["effective_permissions"] = sorted(set(role_permissions(str(item["role"])) + explicit)); item["invited_at"] = iso(item["invited_at"]); item["invite_accepted_at"] = iso(item["invite_accepted_at"]); data["members"].append(item)
        modules = await connection.fetch("""SELECT m.slug,m.name,m.full_name,m.settings,tm.status,tm.show_in_menu FROM tenant_modules tm JOIN app_modules m ON m.slug=tm.module_slug WHERE tm.tenant_id=$1 ORDER BY m.name""", tenant)
        data["modules"] = [{"slug": str(module["slug"]), "name": str(module["name"]), "full_name": str(module["full_name"]), "color": clean(dict(module["settings"] or {}).get("color")), "icon": clean(dict(module["settings"] or {}).get("icon")), "status": str(module["status"]), "show_in_menu": bool(module["show_in_menu"])} for module in modules]
        subscription = await connection.fetchrow("""SELECT s.*,p.name AS package_name,p.monthly_price,p.ai_weekly_credits FROM tenant_subscriptions s LEFT JOIN billing_plans p ON p.slug=s.plan_slug WHERE s.tenant_id=$1""", tenant)
        data["subscription"] = dict(subscription or {})
        if subscription:
            data["subscription"]["package_slug"] = data["subscription"].pop("plan_slug", None); data["subscription"]["monthly_price"] = numeric(data["subscription"].get("monthly_price")); data["subscription"]["starts_at"] = iso(data["subscription"].get("starts_at")); data["subscription"]["ends_at"] = iso(data["subscription"].get("ends_at"))
        invoices = await connection.fetch("SELECT * FROM billing_invoices WHERE tenant_id=$1 ORDER BY due_date DESC,created_at DESC", tenant)
        data["billing"] = {"invoices": [{**dict(invoice), "amount": numeric(invoice["amount"]), "due_date": str(invoice["due_date"] or ""), "paid_at": iso(invoice["paid_at"]), "created_at": iso(invoice["created_at"]), "updated_at": iso(invoice["updated_at"])} for invoice in invoices]}
    return data


async def update_logo(slug: str, logo_url: str, role_permissions: Callable[[str], list[str]]) -> dict[str, Any] | None:
    async with transaction() as connection:
        row = await tenant_row(connection, slug)
        if not row: return None
        await connection.execute("UPDATE tenants SET logo_url=$1,updated_at=$2 WHERE id=$3", logo_url, now(), row["id"]); await audit(connection, str(row["id"]), "core.company.logo_update", "Tenant", str(row["id"]))
    return await get_tenant(slug, role_permissions)


async def update_fiscal(slug: str, data: dict[str, Any], role_permissions: Callable[[str], list[str]]) -> dict[str, Any] | None:
    fields = {key: clean(value) for key, value in data.items() if key.startswith("fiscal_")}
    direct = {key: clean(value) for key, value in data.items() if key in {"name", "trade_name", "document", "email", "phone", "theme_slug"}}
    async with transaction() as connection:
        row = await tenant_row(connection, slug)
        if not row: return None
        fiscal = dict(row["fiscal_data"] or {}); fiscal.update({key.removeprefix("fiscal_"): value for key, value in fields.items()})
        assignments, values = ["fiscal_data"], [fiscal]
        for key, value in direct.items(): assignments.append(key); values.append(value)
        if "chronos_facil" in data:
            assignments.append("settings"); values.append({"chronos_facil": data["chronos_facil"]})
        values.extend([now(), row["id"]]); sets = ", ".join(f"settings=coalesce(settings, '{{}}'::jsonb) || ${index + 1}::jsonb" if key == "settings" else f"{key}=${index + 1}" for index, key in enumerate(assignments))
        await connection.execute(f"UPDATE tenants SET {sets},updated_at=${len(values)-1} WHERE id=${len(values)}", *values); await audit(connection, str(row["id"]), "core.company.fiscal_update", "Tenant", str(row["id"]), {"fields": list(fields | direct) + (["chronos_facil"] if "chronos_facil" in data else [])})
    return await get_tenant(slug, role_permissions)


async def verify_login(slug: str, email: str, password: str, role_permissions: Callable[[str], list[str]]) -> dict[str, Any]:
    async with get_connection() as connection:
        row = await connection.fetchrow("""SELECT tm.id member_id,tm.role,tm.active,tm.password_hash,tm.permissions,tm.must_change_password,t.id tenant_id,t.slug tenant_slug,t.name tenant_name,t.trade_name,t.status tenant_status,u.id user_id,u.name user_name,u.email,u.status user_status FROM tenant_members tm JOIN tenants t ON t.id=tm.tenant_id JOIN users u ON u.id=tm.user_id WHERE t.slug=$1 AND lower(u.email)=lower($2)""", slug, clean(email))
    if not row or not row["active"] or row["tenant_status"] not in {"ACTIVE", "TRIAL"} or row["user_status"] == "DISABLED": return {"ok": False, "reason": "invalid_credentials" if not row else "inactive_access"}
    if not verify_password(clean(password), clean(row["password_hash"])): return {"ok": False, "reason": "invalid_credentials"}
    async with transaction() as connection: await audit(connection, str(row["tenant_id"]), "core.auth.login", "User", str(row["user_id"]), {"email": str(row["email"])})
    permissions = sorted(set(role_permissions(str(row["role"])) + list(row["permissions"] or [])))
    return {"ok": True, "mustChangePassword": bool(row["must_change_password"]), "permissions": permissions, "user": {"id": str(row["user_id"]), "member_id": str(row["member_id"]), "name": str(row["user_name"]), "email": str(row["email"]), "role": str(row["role"])}, "tenant": {"id": str(row["tenant_id"]), "slug": str(row["tenant_slug"]), "name": str(row["trade_name"] or row["tenant_name"]), "status": str(row["tenant_status"])}}


async def authenticated_member(user_id: str, slug: str, member_id: str | None, role_permissions: Callable[[str], list[str]]) -> dict[str, Any] | None:
    async with get_connection() as connection:
        row = await connection.fetchrow("""SELECT tm.id member_id,tm.role,tm.active,tm.permissions,tm.must_change_password,u.id user_id,u.name,u.email,u.status user_status,t.id tenant_id,t.slug,t.name tenant_name,t.status FROM tenant_members tm JOIN users u ON u.id=tm.user_id JOIN tenants t ON t.id=tm.tenant_id WHERE u.id=$1 AND t.slug=$2""", user_id, slug)
    if not row or not row["active"] or row["user_status"] == "DISABLED" or row["status"] not in {"ACTIVE", "TRIAL"} or row["must_change_password"] or (member_id is not None and str(row["member_id"]) != member_id): return None
    return {"ok": True, "user": {"id": str(row["user_id"]), "member_id": str(row["member_id"]), "name": str(row["name"]), "email": str(row["email"]), "role": str(row["role"])}, "tenant": {"id": str(row["tenant_id"]), "slug": str(row["slug"]), "name": str(row["tenant_name"]), "status": str(row["status"])}, "permissions": sorted(set(role_permissions(str(row["role"])) + list(row["permissions"] or [])))}


async def find_tenant(identifier: str) -> dict[str, Any] | None:
    value = clean(identifier).lower()
    if not value: return None
    async with get_connection() as connection:
        row = await connection.fetchrow("SELECT id,slug,name,trade_name,status,logo_url FROM tenants WHERE status IN ('ACTIVE','TRIAL') AND (lower(slug)=$1 OR lower(name)=$1 OR lower(coalesce(trade_name,''))=$1)", value)
    return dict(row) if row else None


async def search_tenants(prefix: str, limit: int = 8) -> list[dict[str, Any]]:
    value = clean(prefix).lower()
    if len(value) < 3: return []
    limit = max(1, min(int(limit), 8)); like = f"{value}%"
    async with get_connection() as connection:
        rows = await connection.fetch("""SELECT id,slug,name,trade_name,logo_url FROM tenants WHERE status IN ('ACTIVE','TRIAL') AND (lower(slug) LIKE $1 OR lower(name) LIKE $1 OR lower(coalesce(trade_name,'')) LIKE $1) ORDER BY CASE WHEN lower(slug)=$2 OR lower(name)=$2 OR lower(coalesce(trade_name,''))=$2 THEN 0 ELSE 1 END,name LIMIT $3""", like, value, limit)
    return [dict(row) for row in rows]


async def list_audit_logs(slug: str, limit: int = 50) -> list[dict[str, Any]] | None:
    async with get_connection() as connection:
        tenant = await tenant_row(connection, slug)
        if not tenant: return None
        rows = await connection.fetch("SELECT * FROM audit_logs WHERE tenant_id=$1 ORDER BY created_at DESC LIMIT $2", tenant["id"], max(1, min(limit, 100)))
    return [{**dict(row), "created_at": iso(row["created_at"])} for row in rows]


async def list_modules() -> list[dict[str, Any]]:
    async with get_connection() as connection:
        rows = await connection.fetch("SELECT * FROM app_modules ORDER BY name")
    return [{"slug": str(row["slug"]), "name": str(row["name"]), "full_name": str(row["full_name"]), "description": clean(row["description"]), "active": str(row["status"]) == "ACTIVE", **dict(row["settings"] or {})} for row in rows]


async def enable_all_modules() -> None:
    async with transaction() as connection:
        await connection.execute("""INSERT INTO tenant_modules (tenant_id,module_slug,status,show_in_menu)
            SELECT tenant.id,module.slug,'ACTIVE',TRUE FROM tenants tenant CROSS JOIN app_modules module
            WHERE module.status='ACTIVE' ON CONFLICT (tenant_id,module_slug) DO NOTHING""")


async def create_or_update_member(slug: str, data: dict[str, Any], role_permissions: Callable[[str], list[str]]) -> dict[str, Any] | None:
    name, email = clean(data.get("name")), clean(data.get("email")).lower()
    password = clean(data.get("temporary_password"))
    role = clean(data.get("role") or "OPERATOR").upper()
    role = role if role in {"OWNER", "ADMIN", "MANAGER", "OPERATOR", "VIEWER"} else "OPERATOR"
    if not name or not email:
        raise ValueError("Nome e e-mail sao obrigatorios.")
    if password and len(password) < 8:
        raise ValueError("A senha provisoria precisa ter pelo menos 8 caracteres.")
    stamp, password_hash = now(), hash_password(password) if password else None
    async with transaction() as connection:
        tenant = await tenant_row(connection, slug)
        if not tenant: return None
        user_id, member_id = row_id("user", email), row_id("member", f"{slug}-{email}")
        await connection.execute("""INSERT INTO users (id,name,email,status,recovery_phone,recovery_phone_verified,created_at,updated_at) VALUES ($1,$2,$3,$4,'',FALSE,$5,$5) ON CONFLICT (email) DO UPDATE SET name=EXCLUDED.name,status=CASE WHEN EXCLUDED.status='ACTIVE' THEN 'ACTIVE' ELSE users.status END,updated_at=EXCLUDED.updated_at""", user_id, name, email, "ACTIVE" if password_hash else "INVITED", stamp)
        real_user = await connection.fetchval("SELECT id FROM users WHERE email=$1", email)
        await connection.execute("""INSERT INTO tenant_members (id,tenant_id,user_id,role,title,department,active,password_hash,must_change_password,invited_at,invite_accepted_at,created_at,updated_at) VALUES ($1,$2,$3,$4,$5,$6,TRUE,$7,$8,$9,$10,$9,$9) ON CONFLICT (tenant_id,user_id) DO UPDATE SET role=EXCLUDED.role,title=EXCLUDED.title,department=EXCLUDED.department,active=TRUE,password_hash=coalesce(EXCLUDED.password_hash,tenant_members.password_hash),must_change_password=CASE WHEN EXCLUDED.password_hash IS NOT NULL THEN TRUE ELSE tenant_members.must_change_password END,updated_at=EXCLUDED.updated_at""", member_id, tenant["id"], real_user, role, clean(data.get("title")), clean(data.get("department")), password_hash, bool(password_hash), stamp, stamp if password_hash else None)
        await audit(connection, str(tenant["id"]), "core.member.upsert", "TenantMember", member_id, {"email": email, "role": role, "temporaryPassword": bool(password_hash)})
    return await get_tenant(slug, role_permissions)


async def update_member_password(slug: str, member_id: str, password: str, role_permissions: Callable[[str], list[str]]) -> dict[str, Any] | None:
    password = clean(password)
    if len(password) < 8:
        raise ValueError("A senha precisa ter pelo menos 8 caracteres.")
    stamp = now()
    async with transaction() as connection:
        tenant = await tenant_row(connection, slug)
        if not tenant: return None
        member = await connection.fetchrow("SELECT user_id FROM tenant_members WHERE id=$1 AND tenant_id=$2", member_id, tenant["id"])
        if not member: return None
        await connection.execute("UPDATE tenant_members SET password_hash=$1,must_change_password=TRUE,invite_accepted_at=$2,updated_at=$2 WHERE id=$3 AND tenant_id=$4", hash_password(password), stamp, member_id, tenant["id"])
        await connection.execute("UPDATE users SET status='ACTIVE',updated_at=$1 WHERE id=$2", stamp, member["user_id"])
        await audit(connection, str(tenant["id"]), "core.member.password_update", "TenantMember", member_id)
    return await get_tenant(slug, role_permissions)


async def update_member_status(slug: str, member_id: str, active: bool, role_permissions: Callable[[str], list[str]]) -> dict[str, Any] | None:
    async with transaction() as connection:
        tenant = await tenant_row(connection, slug)
        if not tenant: return None
        await connection.execute("UPDATE tenant_members SET active=$1,updated_at=$2 WHERE id=$3 AND tenant_id=$4", bool(active), now(), member_id, tenant["id"])
        await audit(connection, str(tenant["id"]), "core.member.status_update", "TenantMember", member_id, {"active": bool(active)})
    return await get_tenant(slug, role_permissions)


async def change_first_login_password(slug: str, email: str, current_password: str, new_password: str, role_permissions: Callable[[str], list[str]]) -> dict[str, Any]:
    login = await verify_login(slug, email, current_password, role_permissions)
    if not login["ok"]: return login
    if len(clean(new_password)) < 8:
        raise ValueError("A nova senha precisa ter pelo menos 8 caracteres.")
    stamp = now()
    async with transaction() as connection:
        row = await connection.fetchrow("""SELECT tm.id,tm.tenant_id FROM tenant_members tm JOIN tenants t ON t.id=tm.tenant_id JOIN users u ON u.id=tm.user_id WHERE t.slug=$1 AND lower(u.email)=lower($2)""", slug, clean(email))
        if not row: return {"ok": False, "reason": "invalid_credentials"}
        await connection.execute("UPDATE tenant_members SET password_hash=$1,must_change_password=FALSE,invite_accepted_at=$2,updated_at=$2 WHERE id=$3", hash_password(new_password), stamp, row["id"])
        await audit(connection, str(row["tenant_id"]), "core.auth.first_password_change", "TenantMember", str(row["id"]))
    return await verify_login(slug, email, new_password, role_permissions)


async def ensure_current_invoice(slug: str, role_permissions: Callable[[str], list[str]]) -> dict[str, Any] | None:
    async with transaction() as connection:
        tenant = await tenant_row(connection, slug)
        if not tenant: return None
        subscription = await connection.fetchrow("""SELECT s.*,p.name package_name,p.monthly_price FROM tenant_subscriptions s LEFT JOIN billing_plans p ON p.slug=s.plan_slug WHERE s.tenant_id=$1""", tenant["id"])
        month = datetime.now(timezone.utc).strftime("%Y-%m"); invoice_id = row_id("invoice", f"{slug}-{month}")
        package_name = clean(subscription["package_name"]) if subscription else "Chronos Hub"; amount = subscription["monthly_price"] if subscription else 0
        await connection.execute("""INSERT INTO billing_invoices (id,tenant_id,subscription_id,status,amount,due_date,provider,metadata,created_at,updated_at) VALUES ($1,$2,$3,'OPEN',$4,$5,'MANUAL',$6,$7,$7) ON CONFLICT (id) DO UPDATE SET amount=EXCLUDED.amount,metadata=EXCLUDED.metadata,updated_at=EXCLUDED.updated_at""", invoice_id, tenant["id"], subscription["id"] if subscription else None, amount, date.fromisoformat(f"{month}-10"), {"title": f"Mensalidade {package_name}", "description": "Plano mensal de limite e uso da Hera AI.", "checkout_url": ""}, now())
        await audit(connection, str(tenant["id"]), "core.billing.invoice_prepare", "BillingInvoice", invoice_id)
    return await get_tenant(slug, role_permissions)
