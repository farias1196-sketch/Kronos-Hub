from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any
from urllib.parse import quote
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from chronos_auth import AuthUser, get_current_user

from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer
import jwt
from passlib.context import CryptContext
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .database import AdmCompany, AdmModule, AdmSetting, AiPlan, GlobalNotice, SuperAdmin, get_db


from preview_config import require_secret

SECRET_KEY = require_secret("PREVIEW_ADM_SECRET")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 12
DEFAULT_AI_PLAN = "trial"

pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

app = FastAPI(title="Chronos ADM API", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:18800", "http://localhost:18800"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class SetupRequest(BaseModel):
    username: str = Field(min_length=3, max_length=80)
    display_name: str = Field(min_length=2, max_length=120)
    password: str = Field(min_length=6, max_length=120)


class LoginRequest(BaseModel):
    username: str
    password: str


class CompanyUpdatePayload(BaseModel):
    tenant_name: str | None = None
    owner_name: str | None = None
    owner_email: str | None = None
    status: str | None = None
    plan_slug: str | None = None
    ai_weekly_limit: int | None = Field(default=None, ge=0)
    ai_monthly_limit: int | None = Field(default=None, ge=0)
    notes: str | None = None


class CompanyCreatePayload(BaseModel):
    tenant_slug: str = Field(min_length=2, max_length=80)
    tenant_name: str = Field(min_length=2, max_length=160)
    owner_name: str = ""
    owner_email: str = ""
    status: str = "TRIAL"
    plan_slug: str = DEFAULT_AI_PLAN
    ai_weekly_limit: int = Field(default=0, ge=0)
    ai_monthly_limit: int = Field(default=0, ge=0)
    notes: str = ""


class ModuleUpdatePayload(BaseModel):
    name: str | None = None
    description: str | None = None
    port: int | None = None
    status: str | None = None
    visible: bool | None = None


class AiPlanPayload(BaseModel):
    slug: str = Field(min_length=2, max_length=60)
    name: str = Field(min_length=2, max_length=120)
    monthly_price: float = Field(default=0, ge=0)
    weekly_credits: int = Field(default=0, ge=0)
    monthly_credits: int = Field(default=0, ge=0)
    active: bool = True
    description: str = ""


class NoticePayload(BaseModel):
    title: str = "Aviso global"
    message: str = Field(min_length=1)
    tone: str = "info"
    active: bool = True
    dismissible: bool = True


class AssistedSyncPayload(BaseModel):
    active: bool = False
    tenant_slug: str = ""
    tenant_name: str = ""
    empresa_id: str = "demo"
    note: str = ""


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def create_access_token(subject: str) -> str:
    expire = now_utc() + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
    return jwt.encode({"sub": subject, "exp": expire}, SECRET_KEY, algorithm=ALGORITHM)


def get_current_admin(token: Annotated[str, Depends(oauth2_scheme)], db: Session = Depends(get_db)) -> SuperAdmin:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Sessao ADM invalida.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM], options={"require": ["exp", "sub"]})
        username = payload.get("sub")
        if not username:
            raise credentials_exception
    except jwt.InvalidTokenError as exc:
        raise credentials_exception from exc

    admin = db.query(SuperAdmin).filter(SuperAdmin.username == username).first()
    if not admin or not admin.is_active:
        raise credentials_exception
    return admin


def module_registry() -> list[dict[str, Any]]:
    return [
        {'slug': 'core', 'name': 'Chronos Core', 'status': 'local', 'port': 18802, 'description': 'Empresa e equipe.'},
        {'slug': 'nexus', 'name': 'Chronos Nexus', 'status': 'local', 'port': 18803, 'description': 'Cadastro de clientes.'},
        {'slug': 'stock', 'name': 'Chronos Stock', 'status': 'local', 'port': 18815, 'description': 'Cadastro e movimentação de estoque.'},
        {'slug': 'loja', 'name': 'Chronos Loja', 'status': 'local', 'port': 18806, 'description': 'Catálogo e pedidos.'},
        {'slug': 'agenda', 'name': 'Chronos Agenda', 'status': 'local', 'port': 18807, 'description': 'Serviços e agendamentos.'},
    ]




def seed_defaults(db: Session) -> None:
    for item in module_registry():
        module = db.query(AdmModule).filter(AdmModule.slug == item["slug"]).first()
        if not module:
            db.add(AdmModule(**item, visible=True))
        else:
            module.name = item["name"]
            module.description = item["description"]
            module.port = item["port"]
            if not module.status or module.status == "pending":
                module.status = item["status"]
    if db.query(GlobalNotice).count() == 0:
        db.add(
            GlobalNotice(
                title="Aviso global",
                message="Placeholder de notificacao global do Chronos. Depois o ADM controla este texto.",
                tone="info",
                active=True,
                dismissible=True,
            )
        )
    db.commit()




def module_health(module: AdmModule) -> str:
    return "offline"




def sync_companies_from_core(db: Session) -> bool:
    return False


def company_to_dict(company: AdmCompany) -> dict[str, Any]:
    return {
        "id": company.id,
        "tenant_slug": company.tenant_slug,
        "tenant_name": company.tenant_name,
        "owner_name": company.owner_name,
        "owner_email": company.owner_email,
        "status": company.status,
        "plan_slug": company.plan_slug,
        "ai_weekly_limit": company.ai_weekly_limit,
        "ai_monthly_limit": company.ai_monthly_limit,
        "notes": company.notes,
        "updated_at": company.updated_at.isoformat() if company.updated_at else "",
    }


def module_to_dict(module: AdmModule, include_health: bool = False) -> dict[str, Any]:
    data = {
        "id": module.id,
        "slug": module.slug,
        "name": module.name,
        "description": module.description,
        "port": module.port,
        "status": module.status,
        "visible": module.visible,
    }
    if include_health:
        data["runtime_status"] = module_health(module)
    return data


def plan_to_dict(plan: AiPlan) -> dict[str, Any]:
    return {
        "id": plan.id,
        "slug": plan.slug,
        "name": plan.name,
        "monthly_price": plan.monthly_price,
        "weekly_credits": plan.weekly_credits,
        "monthly_credits": plan.monthly_credits,
        "active": plan.active,
        "description": plan.description,
    }


def notice_to_dict(notice: GlobalNotice) -> dict[str, Any]:
    return {
        "id": notice.id,
        "title": notice.title,
        "message": notice.message,
        "tone": notice.tone,
        "active": notice.active,
        "dismissible": notice.dismissible,
        "created_at": notice.created_at.isoformat() if notice.created_at else "",
    }


def get_setting(db: Session, key: str) -> str:
    setting = db.query(AdmSetting).filter(AdmSetting.key == key).first()
    return setting.value if setting else ""


def set_setting(db: Session, key: str, value: str) -> None:
    setting = db.query(AdmSetting).filter(AdmSetting.key == key).first()
    if not setting:
        db.add(AdmSetting(key=key, value=value))
    else:
        setting.value = value
    db.commit()


def get_assisted_sync_config(db: Session) -> dict[str, Any]:
    raw = get_setting(db, "zap_assisted_sync")
    if not raw:
        return {"active": False, "tenant_slug": "", "tenant_name": "", "empresa_id": "demo", "note": ""}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        data = {}
    return {
        "active": bool(data.get("active")),
        "tenant_slug": data.get("tenant_slug") or "",
        "tenant_name": data.get("tenant_name") or "",
        "empresa_id": data.get("empresa_id") or "demo",
        "note": data.get("note") or "",
        "updated_at": data.get("updated_at") or "",
    }


@app.on_event("startup")
def startup() -> None:
    db = next(get_db())
    try:
        seed_defaults(db)
    finally:
        db.close()


@app.get("/health")
def health_check():
    return {"ok": True, "status": "online", "module": "Chronos_ADM"}


@app.get("/auth/setup-status")
def setup_status(db: Session = Depends(get_db)):
    return {"configured": db.query(SuperAdmin).first() is not None}






@app.post("/auth/login")
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    admin = db.query(SuperAdmin).filter(SuperAdmin.username == payload.username.strip().lower()).first()
    if not admin or not admin.is_active or not verify_password(payload.password, admin.hashed_password):
        raise HTTPException(status_code=401, detail="Login ou senha invalidos.")
    return {
        "access_token": create_access_token(admin.username),
        "token_type": "bearer",
        "admin": {"username": admin.username, "display_name": admin.display_name},
    }


@app.get("/system/status")
def system_status(_: SuperAdmin = Depends(get_current_admin), db: Session = Depends(get_db)):
    seed_defaults(db)
    core_online = sync_companies_from_core(db)
    modules = [module_to_dict(module, include_health=True) for module in db.query(AdmModule).order_by(AdmModule.name).all()]
    modules_online = len([item for item in modules if item["runtime_status"] in {"online", "ready", "testing"}])
    alerts = []
    if not core_online:
        alerts.append({"level": "warning", "title": "Core offline", "description": "Empresas exibidas podem estar usando apenas cache ADM."})
    return {
        "adm": "online",
        "core_online": core_online,
        "modules_total": len(modules),
        "modules_online": modules_online,
        "companies_total": db.query(AdmCompany).count(),
        "active_notices": db.query(GlobalNotice).filter(GlobalNotice.active == True).count(),
        "alerts": alerts,
        "updated_at": now_utc().isoformat(timespec="seconds"),
    }


@app.post("/system/sync-core")
def sync_core(_: SuperAdmin = Depends(get_current_admin), db: Session = Depends(get_db)):
    return {"ok": True, "core_online": sync_companies_from_core(db)}


@app.get("/companies")
def companies(_: SuperAdmin = Depends(get_current_admin), db: Session = Depends(get_db), q: str = Query(default="")):
    sync_companies_from_core(db)
    query = db.query(AdmCompany)
    if q:
        like = f"%{q.lower()}%"
        query = query.filter(
            AdmCompany.tenant_name.ilike(like)
            | AdmCompany.tenant_slug.ilike(like)
            | AdmCompany.owner_name.ilike(like)
            | AdmCompany.owner_email.ilike(like)
        )
    return [company_to_dict(company) for company in query.order_by(AdmCompany.tenant_name).all()]


@app.post("/companies")
def create_company(payload: CompanyCreatePayload, _: SuperAdmin = Depends(get_current_admin), db: Session = Depends(get_db)):
    tenant_slug = payload.tenant_slug.strip().lower().replace(" ", "-")
    if db.query(AdmCompany).filter(AdmCompany.tenant_slug == tenant_slug).first():
        raise HTTPException(status_code=409, detail="Empresa ja existe no ADM.")
    company = AdmCompany(**{**payload.model_dump(), "tenant_slug": tenant_slug})
    db.add(company)
    db.commit()
    db.refresh(company)
    return {"ok": True, "company": company_to_dict(company)}


@app.patch("/companies/{tenant_slug}")
def update_company(tenant_slug: str, payload: CompanyUpdatePayload, _: SuperAdmin = Depends(get_current_admin), db: Session = Depends(get_db)):
    company = db.query(AdmCompany).filter(AdmCompany.tenant_slug == tenant_slug).first()
    if not company:
        raise HTTPException(status_code=404, detail="Empresa nao encontrada no ADM.")
    for key, value in payload.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(company, key, value)
    db.commit()
    db.refresh(company)
    return {"ok": True, "company": company_to_dict(company)}


@app.get("/modules")
def modules(_: SuperAdmin = Depends(get_current_admin), db: Session = Depends(get_db)):
    seed_defaults(db)
    return [module_to_dict(module, include_health=True) for module in db.query(AdmModule).order_by(AdmModule.name).all()]


@app.patch("/modules/{module_slug}")
def update_module(module_slug: str, payload: ModuleUpdatePayload, _: SuperAdmin = Depends(get_current_admin), db: Session = Depends(get_db)):
    module = db.query(AdmModule).filter(AdmModule.slug == module_slug).first()
    if not module:
        raise HTTPException(status_code=404, detail="Modulo nao encontrado.")
    for key, value in payload.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(module, key, value)
    db.commit()
    db.refresh(module)
    return {"ok": True, "module": module_to_dict(module, include_health=True)}


@app.get("/ai/plans")
def ai_plans(_: SuperAdmin = Depends(get_current_admin), db: Session = Depends(get_db)):
    seed_defaults(db)
    return [plan_to_dict(plan) for plan in db.query(AiPlan).order_by(AiPlan.monthly_price, AiPlan.name).all()]


@app.post("/ai/plans")
def upsert_ai_plan(payload: AiPlanPayload, _: SuperAdmin = Depends(get_current_admin), db: Session = Depends(get_db)):
    slug = payload.slug.strip().lower().replace(" ", "-")
    plan = db.query(AiPlan).filter(AiPlan.slug == slug).first()
    data = payload.model_dump()
    data["slug"] = slug
    if not plan:
        plan = AiPlan(**data)
        db.add(plan)
    else:
        for key, value in data.items():
            setattr(plan, key, value)
    db.commit()
    db.refresh(plan)
    return {"ok": True, "plan": plan_to_dict(plan)}


@app.get("/notices")
def notices(_: SuperAdmin = Depends(get_current_admin), db: Session = Depends(get_db)):
    return [notice_to_dict(notice) for notice in db.query(GlobalNotice).order_by(GlobalNotice.created_at.desc()).all()]


@app.get("/notices/active")
def active_notices(db: Session = Depends(get_db)):
    return {"notices": [notice_to_dict(notice) for notice in db.query(GlobalNotice).filter(GlobalNotice.active == True).order_by(GlobalNotice.created_at.desc()).all()]}


@app.get("/assisted-sync/active")
def active_assisted_sync(db: Session = Depends(get_db), user: AuthUser = Depends(get_current_user)):
    config = get_assisted_sync_config(db)
    if config.get("tenant_slug") != user.tenant_slug:
        return {"active": False}
    user.require_permission("zap.connections.manage")
    return config


@app.get("/assisted-sync")
def assisted_sync(_: SuperAdmin = Depends(get_current_admin), db: Session = Depends(get_db)):
    return get_assisted_sync_config(db)


@app.put("/assisted-sync")
def update_assisted_sync(payload: AssistedSyncPayload, _: SuperAdmin = Depends(get_current_admin), db: Session = Depends(get_db)):
    data = payload.model_dump()
    data["tenant_slug"] = data["tenant_slug"].strip()
    data["tenant_name"] = data["tenant_name"].strip()
    data["empresa_id"] = data["empresa_id"].strip() or "demo"
    data["updated_at"] = now_utc().isoformat(timespec="seconds")
    if data["active"] and not data["tenant_slug"]:
        raise HTTPException(status_code=400, detail="Selecione uma empresa para liberar a sincronizacao.")
    set_setting(db, "zap_assisted_sync", json.dumps(data, ensure_ascii=True))
    return {"ok": True, "assisted_sync": data}


@app.post("/notices")
def create_notice(payload: NoticePayload, _: SuperAdmin = Depends(get_current_admin), db: Session = Depends(get_db)):
    notice = GlobalNotice(**payload.model_dump())
    db.add(notice)
    db.commit()
    db.refresh(notice)
    return {"ok": True, "notice": notice_to_dict(notice)}


@app.patch("/notices/{notice_id}")
def update_notice(notice_id: int, payload: NoticePayload, _: SuperAdmin = Depends(get_current_admin), db: Session = Depends(get_db)):
    notice = db.query(GlobalNotice).filter(GlobalNotice.id == notice_id).first()
    if not notice:
        raise HTTPException(status_code=404, detail="Aviso nao encontrado.")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(notice, key, value)
    db.commit()
    db.refresh(notice)
    return {"ok": True, "notice": notice_to_dict(notice)}


@app.delete("/notices/{notice_id}")
def delete_notice(notice_id: int, _: SuperAdmin = Depends(get_current_admin), db: Session = Depends(get_db)):
    notice = db.query(GlobalNotice).filter(GlobalNotice.id == notice_id).first()
    if not notice:
        raise HTTPException(status_code=404, detail="Aviso nao encontrado.")
    db.delete(notice)
    db.commit()
    return {"ok": True, "deleted": notice_id}
