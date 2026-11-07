import json
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Literal
from urllib.parse import quote
from preview_http import open_local as urlopen
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from chronos_auth.integration import install_sso
from chronos_auth.scope import scoped_tenant
from chronos_auth.services import service_headers, forwarding_headers
from chronos_auth.assets import public_image_url
from chronos_storage import atomic_write_json
from pydantic import BaseModel, Field


app = FastAPI(title="Chronos Agenda API", version="0.1.0")

install_sso(app, "agenda")
app.add_middleware(
    # CORS wraps SSO, including its 401/403 responses.
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:18800", "http://localhost:18800"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


DATA_DIR = Path(__file__).resolve().parents[3] / ".local" / "agenda"
AGENDA_DATA_PATH = DATA_DIR / "agenda_data.json"
SHOP_API_URL = "http://127.0.0.1:18806"
STOCK_API_URL = "http://127.0.0.1:18815"
DEFAULT_TENANT_ID = "demo"
PaymentTiming = Literal["before", "half_half", "after"]
AppointmentStatus = Literal["scheduled", "confirmed", "done", "canceled"]


class ServicePayload(BaseModel):
    tenant_id: str = DEFAULT_TENANT_ID
    name: str = Field(min_length=1)
    description: str = ""
    image_url: str = ""
    duration_minutes: int = Field(default=60, ge=5, le=1440)
    buffer_minutes: int = Field(default=0, ge=0, le=240)
    price: float = Field(default=0, ge=0)
    payment_timing: PaymentTiming = "after"
    resource_ids: list[str] = []
    active: bool = True
    color: str = ""


class ServiceUpdatePayload(BaseModel):
    tenant_id: str = DEFAULT_TENANT_ID
    name: str | None = None
    description: str | None = None
    image_url: str | None = None
    duration_minutes: int | None = Field(default=None, ge=5, le=1440)
    buffer_minutes: int | None = Field(default=None, ge=0, le=240)
    price: float | None = Field(default=None, ge=0)
    payment_timing: PaymentTiming | None = None
    resource_ids: list[str] | None = None
    active: bool | None = None
    color: str | None = None


class ScheduleDayPayload(BaseModel):
    enabled: bool = True
    start: str = "08:00"
    end: str = "18:00"


class AgendaSettingsPayload(BaseModel):
    tenant_id: str = DEFAULT_TENANT_ID
    weekly_hours: dict[str, ScheduleDayPayload]


class AppointmentPayload(BaseModel):
    tenant_id: str = DEFAULT_TENANT_ID
    service_id: str
    client_name: str = Field(min_length=1)
    client_phone: str = ""
    employee_id: str = ""
    employee_name: str = ""
    starts_at: datetime
    notes: str = ""
    status: AppointmentStatus = "scheduled"
    payment_status: str = "pending"


class PublicAppointmentPayload(BaseModel):
    service_id: str
    client_name: str = Field(min_length=1)
    client_phone: str = ""
    day: date
    time: str
    notes: str = ""


class AppointmentUpdatePayload(BaseModel):
    tenant_id: str = DEFAULT_TENANT_ID
    service_id: str | None = None
    client_name: str | None = None
    client_phone: str | None = None
    employee_id: str | None = None
    employee_name: str | None = None
    starts_at: datetime | None = None
    notes: str | None = None
    status: AppointmentStatus | None = None
    payment_status: str | None = None


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def empty_data() -> dict[str, Any]:
    return {
        "schema": "chronos_agenda_data_v1",
        "saved_at": now_iso(),
        "services": {},
        "appointments": {},
        "settings": {},
    }


def load_data() -> dict[str, Any]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not AGENDA_DATA_PATH.exists():
        data = empty_data()
        save_data(data)
        return data
    return json.loads(AGENDA_DATA_PATH.read_text(encoding="utf-8"))


def save_data(data: dict[str, Any]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    data["saved_at"] = now_iso()
    atomic_write_json(AGENDA_DATA_PATH, data)


def tenant_bucket(data: dict[str, Any], bucket: str, tenant_id: str) -> dict[str, Any]:
    return data.setdefault(bucket, {}).setdefault(tenant_id, {})


def default_weekly_hours() -> dict[str, dict[str, Any]]:
    return {
        "0": {"enabled": True, "start": "08:00", "end": "18:00"},
        "1": {"enabled": True, "start": "08:00", "end": "18:00"},
        "2": {"enabled": True, "start": "08:00", "end": "18:00"},
        "3": {"enabled": True, "start": "08:00", "end": "18:00"},
        "4": {"enabled": True, "start": "08:00", "end": "18:00"},
        "5": {"enabled": True, "start": "08:00", "end": "12:00"},
        "6": {"enabled": False, "start": "08:00", "end": "12:00"},
    }


def agenda_settings(data: dict[str, Any], tenant_id: str) -> dict[str, Any]:
    settings = data.setdefault("settings", {}).setdefault(tenant_id, {})
    if "weekly_hours" not in settings:
        settings["weekly_hours"] = default_weekly_hours()
    return settings


def parse_clock(value: str) -> time:
    hour, minute = str(value or "00:00").split(":")[:2]
    return time(hour=int(hour), minute=int(minute))


def resolve_tenant_from_store_slug(store_slug: str) -> tuple[str, dict[str, Any] | None]:
    try:
        with urlopen(f"{SHOP_API_URL}/public/{quote(store_slug)}/catalog", timeout=3) as response:
            payload = json.loads(response.read().decode("utf-8"))
        store = payload.get("store") or {}
        return store.get("tenant_id") or store_slug, store
    except Exception:
        return store_slug, None


def fetch_stock_resources(tenant_id: str) -> list[dict[str, Any]]:
    try:
        from urllib.request import Request
        request = Request(f"{STOCK_API_URL}/stock/service-resources?tenant_id={quote(tenant_id)}", headers=service_headers("agenda", tenant_id))
        with urlopen(request, timeout=3) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return payload.get("resources") or []
    except Exception:
        return []


def parse_day(value: str | None, fallback: date) -> date:
    if not value:
        return fallback
    return date.fromisoformat(value)


def service_with_meta(service: dict[str, Any]) -> dict[str, Any]:
    payment_label = {
        "before": "Pagamento antes",
        "half_half": "50% antes / 50% depois",
        "after": "Pagamento depois",
    }.get(service.get("payment_timing"), "Pagamento depois")
    return {**service, "payment_label": payment_label, "resource_ids": service.get("resource_ids") or []}


def appointment_with_service(appointment: dict[str, Any], services: dict[str, Any]) -> dict[str, Any]:
    service = services.get(appointment.get("service_id")) or {}
    duration = int(service.get("duration_minutes") or appointment.get("duration_minutes") or 60)
    starts_at = datetime.fromisoformat(appointment["starts_at"])
    return {
        **appointment,
        "service_name": service.get("name") or "Servico removido",
        "service_color": service.get("color") or "",
        "duration_minutes": duration,
        "resource_ids": appointment.get("resource_ids") or service.get("resource_ids") or [],
        "employee_id": appointment.get("employee_id") or "",
        "employee_name": appointment.get("employee_name") or "",
        "payment_timing": service.get("payment_timing") or "after",
        "price": service.get("price") or 0,
        "day": starts_at.date().isoformat(),
        "start_time": starts_at.time().isoformat(timespec="minutes"),
    }


def appointment_window(appointment: dict[str, Any], services: dict[str, Any]) -> tuple[datetime, datetime]:
    service = services.get(appointment.get("service_id")) or {}
    start_at = datetime.fromisoformat(appointment["starts_at"])
    minutes = int(service.get("duration_minutes") or appointment.get("duration_minutes") or 60)
    minutes += int(service.get("buffer_minutes") or appointment.get("buffer_minutes") or 0)
    return start_at, start_at + timedelta(minutes=minutes)


def windows_overlap(first_start: datetime, first_end: datetime, second_start: datetime, second_end: datetime) -> bool:
    return first_start < second_end and second_start < first_end


def resource_unavailable(resource: dict[str, Any], target_day: date) -> bool:
    status = resource.get("status") or "active"
    if status == "disabled":
        return True
    if status != "maintenance":
        return False
    unavailable_until = resource.get("unavailable_until") or ""
    if not unavailable_until:
        return True
    try:
        return target_day <= date.fromisoformat(unavailable_until)
    except ValueError:
        return True


def validate_appointment_slot(
    data: dict[str, Any],
    tenant_id: str,
    service_id: str,
    starts_at: datetime,
    employee_id: str = "",
    ignore_appointment_id: str = "",
) -> dict[str, Any]:
    services = tenant_bucket(data, "services", tenant_id)
    service = services.get(service_id)
    if not service or not service.get("active", True):
        raise HTTPException(status_code=404, detail="Servico ativo nao encontrado.")

    duration = int(service.get("duration_minutes") or 60) + int(service.get("buffer_minutes") or 0)
    ends_at = starts_at + timedelta(minutes=duration)
    target_day = starts_at.date()
    day_config = agenda_settings(data, tenant_id).get("weekly_hours", {}).get(str(target_day.weekday()), {})
    if not day_config.get("enabled", True):
        raise HTTPException(status_code=409, detail="Empresa fechada neste dia.")

    business_start = datetime.combine(target_day, parse_clock(day_config.get("start") or "08:00"))
    business_end = datetime.combine(target_day, parse_clock(day_config.get("end") or "18:00"))
    if starts_at < business_start or ends_at > business_end:
        raise HTTPException(status_code=409, detail="Horario fora do atendimento configurado.")

    appointments = [
        appointment
        for appointment in data.get("appointments", {}).get(tenant_id, {}).values()
        if appointment.get("status") != "canceled" and appointment.get("id") != ignore_appointment_id
    ]
    overlapping = []
    for appointment in appointments:
        current_start, current_end = appointment_window(appointment, services)
        if windows_overlap(starts_at, ends_at, current_start, current_end):
            overlapping.append(appointment)

    if employee_id and any((appointment.get("employee_id") or "") == employee_id for appointment in overlapping):
        raise HTTPException(status_code=409, detail="Funcionario indisponivel neste horario.")

    resource_ids = service.get("resource_ids") or []
    if resource_ids:
        stock_resources = {resource.get("id"): resource for resource in fetch_stock_resources(tenant_id)}
        for resource_id in resource_ids:
            resource = stock_resources.get(resource_id)
            if not resource:
                raise HTTPException(status_code=409, detail="Recurso do servico nao encontrado no estoque.")
            if resource_unavailable(resource, target_day):
                raise HTTPException(status_code=409, detail=f"Recurso indisponivel: {resource.get('name') or resource_id}.")
            capacity = max(1, int(resource.get("quantity") or 1))
            used = sum(1 for appointment in overlapping if resource_id in (appointment.get("resource_ids") or []))
            if used >= capacity:
                raise HTTPException(status_code=409, detail=f"Recurso ocupado neste horario: {resource.get('name') or resource_id}.")

    return {"service": service, "resource_ids": resource_ids}


def available_slots_for_service(data: dict[str, Any], tenant_id: str, service_id: str, day: str, employee_id: str = "") -> list[dict[str, Any]]:
    services = tenant_bucket(data, "services", tenant_id)
    service = services.get(service_id)
    if not service or not service.get("active", True):
        raise HTTPException(status_code=404, detail="Servico ativo nao encontrado.")
    duration = int(service.get("duration_minutes") or 60) + int(service.get("buffer_minutes") or 0)
    target_day = date.fromisoformat(day)
    day_config = agenda_settings(data, tenant_id).get("weekly_hours", {}).get(str(target_day.weekday()), {})
    if not day_config.get("enabled", True):
        return []
    business_start = parse_clock(day_config.get("start") or "08:00")
    business_end = parse_clock(day_config.get("end") or "18:00")
    slots = []
    cursor = datetime.combine(target_day, business_start)
    end_at = datetime.combine(target_day, business_end)
    while cursor < end_at:
        label = cursor.time().isoformat(timespec="minutes")
        try:
            validate_appointment_slot(data, tenant_id, service_id, cursor, employee_id=employee_id)
            slots.append({"time": label, "available": True})
        except HTTPException as exc:
            slots.append({"time": label, "available": False, "reason": exc.detail})
        cursor += timedelta(minutes=duration)
    return slots


@app.get("/health")
def health() -> dict[str, Any]:
    return {"ok": True, "service": "Chronos Agenda API", "storage": str(AGENDA_DATA_PATH)}


@app.get("/agenda/settings")
def get_settings(tenant_id: str = Query(default=DEFAULT_TENANT_ID)) -> dict[str, Any]:
    data = load_data()
    settings = agenda_settings(data, tenant_id)
    save_data(data)
    return {"ok": True, "settings": settings}


@app.put("/agenda/settings")
def save_settings(payload: AgendaSettingsPayload) -> dict[str, Any]:
    data = load_data()
    settings = agenda_settings(data, payload.tenant_id)
    settings["weekly_hours"] = {key: value.model_dump() for key, value in payload.weekly_hours.items()}
    settings["updated_at"] = now_iso()
    save_data(data)
    return {"ok": True, "settings": settings}


@app.get("/agenda/services")
def list_services(tenant_id: str = Query(default=DEFAULT_TENANT_ID), include_inactive: bool = False) -> dict[str, Any]:
    data = load_data()
    services = list(data.get("services", {}).get(tenant_id, {}).values())
    if not include_inactive:
        services = [service for service in services if service.get("active", True)]
    services = sorted(services, key=lambda item: (not item.get("active", True), item.get("name", "")))
    return {"ok": True, "services": [service_with_meta(service) for service in services]}


@app.post("/agenda/services")
def create_service(payload: ServicePayload) -> dict[str, Any]:
    data = load_data()
    services = tenant_bucket(data, "services", payload.tenant_id)
    service_id = f"svc-{uuid4().hex[:10]}"
    service = {
        "id": service_id,
        **payload.model_dump(),
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    services[service_id] = service
    save_data(data)
    return {"ok": True, "service": service_with_meta(service)}


@app.patch("/agenda/services/{service_id}")
def update_service(service_id: str, payload: ServiceUpdatePayload) -> dict[str, Any]:
    data = load_data()
    services = tenant_bucket(data, "services", payload.tenant_id)
    if service_id not in services:
        raise HTTPException(status_code=404, detail="Servico nao encontrado.")
    updates = payload.model_dump(exclude_unset=True)
    updates.pop("tenant_id", None)
    services[service_id].update(updates)
    services[service_id]["updated_at"] = now_iso()
    save_data(data)
    return {"ok": True, "service": service_with_meta(services[service_id])}


@app.delete("/agenda/services/{service_id}")
def delete_service(service_id: str, tenant_id: str = Query(default=DEFAULT_TENANT_ID)) -> dict[str, Any]:
    data = load_data()
    services = tenant_bucket(data, "services", tenant_id)
    if service_id not in services:
        raise HTTPException(status_code=404, detail="Servico nao encontrado.")
    services[service_id]["active"] = False
    services[service_id]["updated_at"] = now_iso()
    save_data(data)
    return {"ok": True}


@app.get("/agenda/appointments")
def list_appointments(
    tenant_id: str = Query(default=DEFAULT_TENANT_ID),
    start: str | None = None,
    end: str | None = None,
) -> dict[str, Any]:
    data = load_data()
    services = data.get("services", {}).get(tenant_id, {})
    appointments = list(data.get("appointments", {}).get(tenant_id, {}).values())
    start_day = parse_day(start, date.today())
    end_day = parse_day(end, start_day)
    filtered = []
    for appointment in appointments:
        appointment_day = datetime.fromisoformat(appointment["starts_at"]).date()
        if start_day <= appointment_day <= end_day:
            filtered.append(appointment_with_service(appointment, services))
    filtered.sort(key=lambda item: item.get("starts_at", ""))
    return {"ok": True, "appointments": filtered}


@app.post("/agenda/appointments")
def create_appointment(payload: AppointmentPayload) -> dict[str, Any]:
    data = load_data()
    services = tenant_bucket(data, "services", payload.tenant_id)
    validation = validate_appointment_slot(data, payload.tenant_id, payload.service_id, payload.starts_at, payload.employee_id)
    appointments = tenant_bucket(data, "appointments", payload.tenant_id)
    appointment_id = f"apt-{uuid4().hex[:10]}"
    appointment = {
        "id": appointment_id,
        **payload.model_dump(mode="json"),
        "resource_ids": validation["resource_ids"],
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    appointments[appointment_id] = appointment
    save_data(data)
    return {"ok": True, "appointment": appointment_with_service(appointment, services)}


@app.patch("/agenda/appointments/{appointment_id}")
def update_appointment(appointment_id: str, payload: AppointmentUpdatePayload) -> dict[str, Any]:
    data = load_data()
    services = tenant_bucket(data, "services", payload.tenant_id)
    appointments = tenant_bucket(data, "appointments", payload.tenant_id)
    if appointment_id not in appointments:
        raise HTTPException(status_code=404, detail="Agendamento nao encontrado.")
    updates = payload.model_dump(exclude_unset=True, mode="json")
    updates.pop("tenant_id", None)
    if updates.get("service_id") and updates["service_id"] not in services:
        raise HTTPException(status_code=404, detail="Servico nao encontrado.")
    candidate = {**appointments[appointment_id], **updates}
    if candidate.get("status") != "canceled":
        validation = validate_appointment_slot(
            data,
            payload.tenant_id,
            candidate.get("service_id"),
            datetime.fromisoformat(candidate.get("starts_at")),
            candidate.get("employee_id") or "",
            ignore_appointment_id=appointment_id,
        )
        updates["resource_ids"] = validation["resource_ids"]
    appointments[appointment_id].update(updates)
    appointments[appointment_id]["updated_at"] = now_iso()
    save_data(data)
    return {"ok": True, "appointment": appointment_with_service(appointments[appointment_id], services)}


@app.delete("/agenda/appointments/{appointment_id}")
def cancel_appointment(appointment_id: str, tenant_id: str = Query(default=DEFAULT_TENANT_ID)) -> dict[str, Any]:
    data = load_data()
    services = tenant_bucket(data, "services", tenant_id)
    appointments = tenant_bucket(data, "appointments", tenant_id)
    if appointment_id not in appointments:
        raise HTTPException(status_code=404, detail="Agendamento nao encontrado.")
    appointments[appointment_id]["status"] = "canceled"
    appointments[appointment_id]["updated_at"] = now_iso()
    save_data(data)
    return {"ok": True, "appointment": appointment_with_service(appointments[appointment_id], services)}


@app.get("/agenda/availability")
def availability(
    tenant_id: str = Query(default=DEFAULT_TENANT_ID),
    service_id: str = Query(),
    day: str = Query(),
    employee_id: str = "",
) -> dict[str, Any]:
    data = load_data()
    return {"ok": True, "slots": available_slots_for_service(data, tenant_id, service_id, day, employee_id=employee_id)}


@app.get("/public/{store_slug}/agenda")
def public_agenda(store_slug: str) -> dict[str, Any]:
    tenant_id, store = resolve_tenant_from_store_slug(store_slug)
    data = load_data()
    services = [
        service_with_meta(service)
        for service in data.get("services", {}).get(tenant_id, {}).values()
        if service.get("active", True)
    ]
    services.sort(key=lambda item: item.get("name", ""))
    services = [{**service, "image_url": public_image_url(service.get("image_url", ""), tenant_id)} for service in services]
    return {"ok": True, "tenant_id": tenant_id, "store_slug": store_slug, "store": store, "services": services}


@app.get("/public/{store_slug}/agenda/availability")
@app.get("/public/{store_slug}/slots")
def public_availability(store_slug: str, service_id: str = Query(), day: str = Query()) -> dict[str, Any]:
    tenant_id, _store = resolve_tenant_from_store_slug(store_slug)
    data = load_data()
    slots = [slot for slot in available_slots_for_service(data, tenant_id, service_id, day) if slot.get("available")]
    return {"ok": True, "slots": slots}


@app.post("/public/{store_slug}/agenda/book")
def public_book(store_slug: str, payload: PublicAppointmentPayload) -> dict[str, Any]:
    tenant_id, _store = resolve_tenant_from_store_slug(store_slug)
    data = load_data()
    available = {
        slot["time"]
        for slot in available_slots_for_service(data, tenant_id, payload.service_id, payload.day.isoformat())
        if slot.get("available")
    }
    if payload.time not in available:
        raise HTTPException(status_code=409, detail="Horario indisponivel.")
    appointment_payload = AppointmentPayload(
        tenant_id=tenant_id,
        service_id=payload.service_id,
        client_name=payload.client_name,
        client_phone=payload.client_phone,
        starts_at=datetime.fromisoformat(f"{payload.day.isoformat()}T{payload.time}:00"),
        notes=payload.notes,
        status="scheduled",
        payment_status="pending",
    )
    return create_appointment(appointment_payload)
