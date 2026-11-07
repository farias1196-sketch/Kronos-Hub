from __future__ import annotations

import sys
import time
from pathlib import Path

# Torna o pacote chronos_auth importável de qualquer API
_HUB_ROOT = Path(__file__).resolve().parents[3]
if str(_HUB_ROOT) not in sys.path:
    sys.path.insert(0, str(_HUB_ROOT))

from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, StrictBool, Field
from typing import Literal

from chronos_auth import AuthUser, create_token, get_current_user
from chronos_auth.integration import install_sso
from chronos_storage.runtime_sync import postgres_mode

from .core_store import (
    authenticated_member,
    ASSETS_DIR,
    change_first_login_password,
    enable_all_modules_for_all_tenants,
    ensure_current_invoice,
    find_tenant_for_login,
    search_tenants_for_login,
    get_tenant_context,
    get_summary,
    get_tenant,
    list_audit_logs,
    list_modules,
    list_tenants,
    create_or_update_member,
    update_member_password,
    update_member_status,
    update_tenant_fiscal_data,
    update_tenant_logo,
    verify_company_login,
)


app = FastAPI(title="Chronos Core API", version="0.1.0")
install_sso(app, "core")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:18800", "http://localhost:18800"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

ASSETS_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/core/assets", StaticFiles(directory=ASSETS_DIR), name="core-assets")


class TenantFiscalUpdate(BaseModel):
    chronos_facil: StrictBool = False
    name: str | None = None
    trade_name: str | None = None
    document: str | None = None
    email: str | None = None
    phone: str | None = None
    theme_slug: Literal["rosa-branco", "verde-branco", "azul-branco", "laranja-cinza", "rosa-preto", "prata-cinza"] | None = None
    fiscal_cnpj: str | None = None
    fiscal_state_registration: str | None = None
    fiscal_municipal_registration: str | None = None
    fiscal_tax_regime: str | None = None
    fiscal_cnae: str | None = None
    fiscal_email: str | None = None
    fiscal_phone: str | None = None
    fiscal_responsible_name: str | None = None
    fiscal_zip_code: str | None = None
    fiscal_street: str | None = None
    fiscal_number: str | None = None
    fiscal_complement: str | None = None
    fiscal_neighborhood: str | None = None
    fiscal_city: str | None = None
    fiscal_state: str | None = None
    fiscal_country: str | None = None
    fiscal_notes: str | None = None


class MemberCreate(BaseModel):
    name: str
    email: str
    role: str = "OPERATOR"
    title: str | None = None
    department: str | None = None
    temporary_password: str | None = None


class MemberPasswordUpdate(BaseModel):
    password: str


class MemberStatusUpdate(BaseModel):
    active: bool


class CompanyLoginPayload(BaseModel):
    tenant_slug: str
    email: str
    password: str


class TenantSelectPayload(BaseModel):
    tenant: str


class FirstPasswordChangePayload(BaseModel):
    tenant_slug: str
    email: str
    current_password: str
    new_password: str


@app.get("/health")
def health() -> dict:
    mode = postgres_mode("core")
    return {"ok": True, "service": "Chronos Core API", "storage_mode": mode, "storage": "PostgreSQL" if mode == "primary" else "SQLite"}


@app.get("/core/summary")
def core_summary() -> dict:
    return get_summary()




@app.post("/core/modules/enable-all")
def enable_all_modules() -> dict:
    enable_all_modules_for_all_tenants()
    return get_summary()


@app.get("/core/tenants")
def tenants(current_slug: str = Query(default=""), user: AuthUser = Depends(get_current_user)) -> dict:
    """Return the current company, or the official directory for Chronos ADM.

    A regular user must never enumerate companies outside their session. The
    local ADM service has a short-lived, signed service credential and is the
    only caller allowed to refresh the global company directory.
    """
    is_adm_directory_sync = user.kind == "service" and user.user_id == "adm" and user.tenant_slug == "*"
    if is_adm_directory_sync:
        active_statuses = {"ACTIVE", "TRIAL"}
        return {"tenants": [tenant for tenant in list_tenants() if tenant.get("status") in active_statuses]}

    slug = user.tenant_slug
    tenant = get_tenant(slug)
    return {"tenants": [tenant] if tenant else []}


from chronos_storage.quote_validity import QuoteValidityPayload, settings as quote_validity_settings


@app.get("/core/tenants/{slug}/quote-validity")
def get_quote_validity(slug: str):
    return quote_validity_settings(slug, module="core")


@app.put("/core/tenants/{slug}/quote-validity")
def put_quote_validity(slug: str, payload: QuoteValidityPayload):
    return quote_validity_settings(slug, payload.model_dump(), module="core")


@app.get("/core/tenants/{slug}")
def tenant_detail(slug: str) -> dict:
    tenant = get_tenant(slug)
    if not tenant:
        raise HTTPException(status_code=404, detail="Empresa nao encontrada.")
    return {"tenant": tenant}


@app.get("/core/tenants/{slug}/context")
def tenant_context(slug: str) -> dict:
    context = get_tenant_context(slug)
    if not context:
        raise HTTPException(status_code=404, detail="Empresa nao encontrada.")
    return {"context": context}


@app.put("/core/tenants/{slug}/fiscal")
def update_fiscal_data(slug: str, payload: TenantFiscalUpdate) -> dict:
    tenant = get_tenant(slug)
    if not tenant:
        raise HTTPException(status_code=404, detail="Empresa nao encontrada.")

    if "chronos_facil" in payload.model_fields_set and payload.chronos_facil != tenant.get("chronos_facil", False):
        user = __import__('chronos_auth.scope', fromlist=['current_user']).current_user.get()
        if not user or user.kind != "service" or user.user_id != "adm":
            raise HTTPException(403, "A etapa da empresa é administrada pelo ADM geral.")

    updated = update_tenant_fiscal_data(slug, payload.model_dump(exclude_unset=True))
    return {"tenant": updated}


@app.post("/core/tenants/{slug}/members")
def create_member(slug: str, payload: MemberCreate) -> dict:
    try:
      updated = create_or_update_member(slug, payload.model_dump())
    except ValueError as exc:
      raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not updated:
        raise HTTPException(status_code=404, detail="Empresa nao encontrada.")
    return {"tenant": updated}


@app.put("/core/tenants/{slug}/members/{member_id}/password")
def change_member_password(slug: str, member_id: str, payload: MemberPasswordUpdate) -> dict:
    try:
      updated = update_member_password(slug, member_id, payload.password)
    except ValueError as exc:
      raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not updated:
        raise HTTPException(status_code=404, detail="Membro nao encontrado.")
    return {"tenant": updated}


@app.put("/core/tenants/{slug}/members/{member_id}/status")
def change_member_status(slug: str, member_id: str, payload: MemberStatusUpdate) -> dict:
    updated = update_member_status(slug, member_id, payload.active)
    if not updated:
        raise HTTPException(status_code=404, detail="Membro nao encontrado.")
    return {"tenant": updated}


@app.post("/core/tenants/{slug}/billing/prepare-current")
def prepare_current_invoice(slug: str) -> dict:
    updated = ensure_current_invoice(slug)
    if not updated:
        raise HTTPException(status_code=404, detail="Empresa nao encontrada.")
    return {"tenant": updated}


@app.get("/core/tenants/{slug}/audit")
def tenant_audit(slug: str, limit: int = Query(default=50)) -> dict:
    logs = list_audit_logs(slug, limit)
    if logs is None:
        raise HTTPException(status_code=404, detail="Empresa nao encontrada.")
    return {"logs": logs}


@app.post("/core/tenants/{slug}/logo")
async def upload_tenant_logo(slug: str, file: UploadFile = File(...)) -> dict:
    tenant = get_tenant(slug)
    if not tenant:
        raise HTTPException(status_code=404, detail="Empresa nao encontrada.")

    content_type = (file.content_type or "").lower()
    filename = (file.filename or "").lower()
    if content_type != "image/png" and not filename.endswith(".png"):
        raise HTTPException(status_code=400, detail="Envie uma logo em PNG.")

    content = await file.read(2 * 1024 * 1024 + 1)
    if not content:
        raise HTTPException(status_code=400, detail="Arquivo vazio.")
    if len(content) > 2 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Logo muito grande. Limite: 2 MB.")
    if not content.startswith(b"\x89PNG\r\n\x1a\n"):
        raise HTTPException(status_code=400, detail="O arquivo nao parece ser um PNG valido.")

    tenant_dir = ASSETS_DIR / slug
    tenant_dir.mkdir(parents=True, exist_ok=True)
    logo_path = tenant_dir / "logo.png"
    logo_path.write_bytes(content)
    logo_url = f"/core/assets/{slug}/logo.png?v={int(time.time())}"
    updated = update_tenant_logo(slug, logo_url)
    return {"tenant": updated}


@app.get("/core/modules")
def modules() -> dict:
    return {"modules": list_modules()}


@app.post("/core/auth/login")
def company_login(payload: CompanyLoginPayload) -> dict:
    result = verify_company_login(payload.tenant_slug, payload.email, payload.password)
    if not result["ok"]:
        raise HTTPException(status_code=401, detail=result["reason"])
    return login_response(result)


def login_response(result: dict) -> dict:
    if result.get("mustChangePassword"):
        return result
    token = create_token(
        member_id=result["user"]["member_id"],
        user_id=result["user"]["id"],
        user_name=result["user"]["name"],
        tenant_id=result["tenant"]["id"],
        tenant_slug=result["tenant"]["slug"],
        role=result["user"]["role"],
        permissions=result["permissions"],
    )
    result["token"] = token
    result["member"] = {**result["user"], "id": result["user"]["member_id"], "tenant_slug": result["tenant"]["slug"]}
    return result


@app.get("/core/auth/me")
def auth_me(user: AuthUser = Depends(get_current_user)) -> dict:
    """Retorna os dados do usuário autenticado a partir do token JWT."""
    result = authenticated_member(user.user_id, user.tenant_slug, user.member_id)
    if not result or result["tenant"]["id"] != user.tenant_id:
        raise HTTPException(401, "Acesso desativado. Faca login novamente.")
    return result


@app.post("/core/auth/switch-tenant")
def switch_tenant(payload: TenantSelectPayload, user: AuthUser = Depends(get_current_user)) -> dict:
    if not authenticated_member(user.user_id, user.tenant_slug, user.member_id):
        raise HTTPException(401, "Sessao invalida")
    result = authenticated_member(user.user_id, payload.tenant)
    if not result:
        raise HTTPException(403, "Sem acesso a esta empresa")
    return login_response(result)


@app.post("/core/auth/select-tenant")
def select_tenant(payload: TenantSelectPayload) -> dict:
    tenant = find_tenant_for_login(payload.tenant)
    if not tenant:
        raise HTTPException(status_code=404, detail="Empresa nao encontrada.")
    return {"tenant": tenant}


@app.get("/core/auth/tenant-options")
def tenant_options(q: str = Query(min_length=3, max_length=120)) -> dict:
    return {"tenants": search_tenants_for_login(q)}


@app.post("/core/auth/change-first-password")
def change_first_password(payload: FirstPasswordChangePayload) -> dict:
    try:
        result = change_first_login_password(
            payload.tenant_slug,
            payload.email,
            payload.current_password,
            payload.new_password,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not result["ok"]:
        raise HTTPException(status_code=401, detail=result["reason"])
    return login_response(result)


from chronos_storage.client_display import ClientDisplayPayload, settings as client_display_settings

@app.get("/core/tenants/{slug}/client-display")
def get_client_display(slug: str):
    return client_display_settings(slug, module="core")

@app.put("/core/tenants/{slug}/client-display")
def put_client_display(slug: str, payload: ClientDisplayPayload):
    return client_display_settings(slug, payload.model_dump(), module="core")


from chronos_storage.pdf_header import PdfHeaderPayload, settings as pdf_header_settings

@app.get("/core/tenants/{slug}/pdf-header")
def get_pdf_header(slug: str):
    return pdf_header_settings(slug, module="core")

@app.put("/core/tenants/{slug}/pdf-header")
def put_pdf_header(slug: str, payload: PdfHeaderPayload):
    return pdf_header_settings(slug, payload.model_dump(), module="core")


class ImplantationPayload(BaseModel):
    stage: int = Field(strict=True, ge=1, le=4)

@app.put("/core/tenants/{slug}/implantation")
def change_implantation(slug: str, payload: ImplantationPayload):
    from chronos_auth.scope import current_user
    from chronos_storage.implantation import set_stage
    from chronos_storage.runtime_sync import run
    user = current_user.get()
    if not user or user.kind != "service" or user.user_id != "adm":
        raise HTTPException(403, "Somente o ADM geral pode alterar a etapa.")
    if postgres_mode("core") != "primary":
        raise HTTPException(503, "A configuração de implantação requer o Core no PostgreSQL.")
    run(set_stage(slug, payload.stage))
    return {"tenant": get_tenant(slug)}
