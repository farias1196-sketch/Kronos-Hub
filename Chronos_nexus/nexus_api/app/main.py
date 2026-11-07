from __future__ import annotations

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from chronos_auth.integration import install_sso
from chronos_auth.scope import scoped_tenant
from chronos_storage.client_display import ClientDisplayPayload, settings as client_display_settings, display_name
from chronos_auth.services import service_headers, forwarding_headers
from chronos_storage.runtime_sync import postgres_mode
from pydantic import BaseModel, Field
from typing import Literal
from .registration_profile import profile, validate_answers

from .nexus_store import (
    complete_registration,
    delete_client,
    get_client,
    get_client_by_registration_token,
    get_status_options,
    list_clients,
    list_contact_points,
    list_tags,
    merge_clients,
    pre_register_client,
    upsert_client,
)


app = FastAPI(title="Chronos Nexus API", version="0.1.0")

install_sso(app, "nexus")
app.add_middleware(
    # CORS wraps SSO, including its 401/403 responses.
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:18800", "http://localhost:18800"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ClientPayload(BaseModel):
    registration_answers: dict[str, str] = Field(default_factory=dict)
    id: str | None = None
    name: str
    phone: str
    fiscal_document: str | None = None
    company_name: str | None = None
    email: str | None = None
    cep: str | None = None
    address_street: str | None = None
    address_number: str | None = None
    address_complement: str | None = None
    address_neighborhood: str | None = None
    address_city: str | None = None
    address_state: str | None = None
    notes: str | None = None
    whatsapp_lid: str | None = None
    whatsapp_jid: str | None = None
    conversation_status: str = "novo"
    order_status: str = "sem_pedido"
    art_status: str = "sem_arte"
    art_briefing: str | None = None
    art_link: str | None = None
    art_notes: str | None = None
    tags: list[str] = []
    source: str = "manual"
    registration_status: str | None = None
    registration_token: str | None = None
    assigned_seller_id: str | None = None
    assigned_seller_name: str | None = None


class PreRegisterPayload(BaseModel):
    phone: str | None = None
    name: str | None = None
    display_name: str | None = None
    contact_id: str | None = None
    remote_jid: str | None = None
    whatsapp_lid: str | None = None
    whatsapp_jid: str | None = None
    conversation_id: str | None = None
    source: str = "zap"


class MergeClientsPayload(BaseModel):
    duplicate_client_id: str


class PublicRegistrationPayload(BaseModel):
    registration_answers: dict[str, str] = Field(default_factory=dict)
    name: str
    fiscal_document: str | None = None
    company_name: str | None = None
    email: str | None = None
    cep: str | None = None
    address_street: str | None = None
    address_number: str | None = None
    address_complement: str | None = None
    address_neighborhood: str | None = None
    address_city: str | None = None
    address_state: str | None = None
    notes: str | None = None
    tags: list[str] = []


@app.get("/health")
def health() -> dict:
    mode = postgres_mode("nexus")
    return {"ok": True, "service": "Chronos Nexus API", "storage_mode": mode, "storage": "PostgreSQL" if mode == "primary" else "SQLite"}


class RegistrationField(BaseModel):
    id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,64}$")
    label: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=300)
    type: Literal["text", "textarea", "email", "tel"] = "text"
    required: bool = False

class RegistrationProfile(BaseModel):
    fields: list[RegistrationField] = Field(default_factory=list, max_length=30)

@app.get("/nexus/registration-profile")
def get_registration_profile(empresa_id: str = Query(...)) -> dict:
    return {"fields": profile(scoped_tenant(empresa_id, "nexus"))}

@app.put("/nexus/registration-profile")
def save_registration_profile(payload: RegistrationProfile, empresa_id: str = Query(...)) -> dict:
    if len({field.id for field in payload.fields}) != len(payload.fields) or any(not field.label.strip() for field in payload.fields):
        raise HTTPException(422,"Revise os nomes dos campos de cadastro.")
    return {"fields": profile(scoped_tenant(empresa_id,"nexus"), [field.model_dump() for field in payload.fields])}

@app.get("/nexus/status-options")
def status_options() -> dict:
    return get_status_options()


@app.get("/nexus/clients")
def clients(empresa_id: str = Query(...), search: str = "", tag: str = "") -> dict:
    preference = client_display_settings(empresa_id, module="nexus")["mode"]
    return {"display_preference": preference, "clients": [{**client, "display_name": display_name(client, preference)} for client in list_clients(empresa_id, search, tag)]}


@app.post("/nexus/clients")
def save_client(payload: ClientPayload, empresa_id: str = Query(...)) -> dict:
    try:
        values = payload.model_dump(exclude_unset=True)
        previous = get_client(empresa_id, payload.id) if payload.id else None
        if payload.id and not previous: raise HTTPException(404, "Cliente não encontrado.")
        if "registration_answers" in values:
            values["registration_answers"] = validate_answers(empresa_id, values["registration_answers"])
        client = upsert_client(empresa_id, {**(previous or {}), **values})
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"client": client}


@app.post("/nexus/pre-register")
def pre_register(payload: PreRegisterPayload, empresa_id: str = Query(...)) -> dict:
    try:
        client = pre_register_client(empresa_id, payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"client": client}


@app.get("/nexus/public-registration/{token}")
@app.get("/nexus/public/register/{token}")
def public_registration(token: str) -> dict:
    client = get_client_by_registration_token(token)
    if not client:
        raise HTTPException(status_code=404, detail="Link de cadastro invalido.")
    return {
        "fields": profile(client["empresa_id"]),
        "client": {
            "registration_answers": client.get("registration_answers") or {},
            "name": client.get("name"),
            "phone": client.get("phone"),
            "fiscal_document": client.get("fiscal_document"),
            "company_name": client.get("company_name"),
            "email": client.get("email"),
            "cep": client.get("cep"),
            "address_street": client.get("address_street"),
            "address_number": client.get("address_number"),
            "address_complement": client.get("address_complement"),
            "address_neighborhood": client.get("address_neighborhood"),
            "address_city": client.get("address_city"),
            "address_state": client.get("address_state"),
            "notes": client.get("notes"),
            "registration_status": client.get("registration_status"),
        }
    }


@app.post("/nexus/public-registration/{token}")
@app.post("/nexus/public/register/{token}")
def complete_public_registration(token: str, payload: PublicRegistrationPayload) -> dict:
    try:
        existing = get_client_by_registration_token(token)
        if not existing: raise HTTPException(404,"Link de cadastro inválido.")
        values = payload.model_dump(exclude_unset=True)
        values["registration_answers"] = validate_answers(existing["empresa_id"], payload.registration_answers, required=True)
        client = complete_registration(token, values)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return public_registration(token)


@app.get("/nexus/clients/{client_id}")
def client_detail(client_id: str, empresa_id: str = Query(...)) -> dict:
    client = get_client(empresa_id, client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Cliente nao encontrado.")
    return {"client": client}


@app.get("/nexus/clients/{client_id}/contact-points")
def client_contact_points(client_id: str, empresa_id: str = Query(...)) -> dict:
    client = get_client(empresa_id, client_id)
    if not client or client.get("merged_into_client_id"):
        raise HTTPException(status_code=404, detail="Cliente nao encontrado.")
    return {"contact_points": list_contact_points(empresa_id, client_id)}


@app.get("/nexus/clients/{client_id}/avatar")
def client_avatar(client_id: str, empresa_id: str = Query(...)):
    from fastapi import Response
    if not get_client(empresa_id, client_id):
        raise HTTPException(404, "Cliente não encontrado.")
    return Response(status_code=204)


@app.post("/nexus/clients/{client_id}/merge")
def merge_client_records(client_id: str, payload: MergeClientsPayload, empresa_id: str = Query(...)) -> dict:
    try:
        return merge_clients(empresa_id, client_id, payload.duplicate_client_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.delete("/nexus/clients/{client_id}")
def remove_client(client_id: str, empresa_id: str = Query(...)) -> dict:
    removed = delete_client(empresa_id, client_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Cliente nao encontrado.")
    return {"removed": True}


@app.get("/nexus/tags")
def tags(empresa_id: str = Query(...)) -> dict:
    return {"tags": list_tags(empresa_id)}


@app.get("/nexus/client-display")
def get_client_display(empresa_id: str = Query(...)):
    return client_display_settings(scoped_tenant(empresa_id, "nexus"), module="nexus")

@app.put("/nexus/client-display")
def put_client_display(payload: ClientDisplayPayload, empresa_id: str = Query(...)):
    return client_display_settings(scoped_tenant(empresa_id, "nexus"), payload.model_dump(), module="nexus")
