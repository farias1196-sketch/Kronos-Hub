import AuthenticatedImage from "../../AuthenticatedImage";
import MobileDialog from "../../components/ui/MobileDialog";
import "./agendaMobile.css";
import { useEffect, useState } from "react";
import {
  CalendarDays, CheckCircle2, Clock3, Loader2, MapPin, Pencil, Plus, Search,
  Trash2, UserRound, UsersRound, X,
} from "lucide-react";
import { authFetch, isPublicPage } from "../../auth";
import {
  AGENDA_API_URL, AGENDA_PATH, CORE_API_URL, DEFAULT_CORE_TENANT_SLUG,
  HERA_API_URL, NEXUS_API_URL, SHOP_API_URL, STOCK_API_URL,
} from "../../shared/chronosConfig";
import { formatMoney } from "../core/coreUtils";

export default function AgendaPage({ path, currentTenantSlug, currentTenant, mobile = false }) {
  const [serviceOpen, setServiceOpen] = useState(false);
  const [services, setServices] = useState([]);
  const [appointments, setAppointments] = useState([]);
  const [agendaResources, setAgendaResources] = useState([]);
  const [storeSlug, setStoreSlug] = useState("");
  const [agendaSettings, setAgendaSettings] = useState(null);
  const [status, setStatus] = useState("Carregando agenda...");
  const [isSaving, setIsSaving] = useState(false);
  const [editingServiceId, setEditingServiceId] = useState(null);
  const [selectedDay, setSelectedDay] = useState(new Date().toISOString().slice(0, 10));
  const [isAppointmentOpen, setIsAppointmentOpen] = useState(false);
  const [isDatePickerOpen, setIsDatePickerOpen] = useState(false);
  const [datePickerAnchor, setDatePickerAnchor] = useState(new Date().toISOString().slice(0, 10));
  const [serviceForm, setServiceForm] = useState({
    name: "",
    description: "",
    image_url: "",
    duration_minutes: "60",
    buffer_minutes: "0",
    price: "0",
    payment_timing: "after",
    resource_ids: [],
    color: "",
    active: true,
  });
  const [appointmentForm, setAppointmentForm] = useState({
    service_id: "",
    client_name: "",
    client_phone: "",
    employee_id: "",
    day: new Date().toISOString().slice(0, 10),
    time: "09:00",
    notes: "",
  });
  const [quickResourceForm, setQuickResourceForm] = useState({ name: "", kind: "equipment", quantity: "1" });

  const tenantId = currentTenantSlug || DEFAULT_CORE_TENANT_SLUG;
  const normalizedAgendaPath = path.toLowerCase();
  const activeSection = normalizedAgendaPath.includes("/servicos")
    ? "services"
    : normalizedAgendaPath.includes("/horarios")
      ? "hours"
      : "chores";
  const selectedDateForWeek = new Date(`${selectedDay}T12:00:00`);
  const weekStartDate = new Date(selectedDateForWeek);
  weekStartDate.setDate(selectedDateForWeek.getDate() - selectedDateForWeek.getDay());
  const visibleDays = Array.from({ length: 7 }, (_, index) => {
    const day = new Date(weekStartDate);
    day.setDate(weekStartDate.getDate() + index);
    return day.toISOString().slice(0, 10);
  });
  const monthAnchor = new Date(`${datePickerAnchor}T12:00:00`);
  const monthStart = new Date(monthAnchor.getFullYear(), monthAnchor.getMonth(), 1);
  const calendarStart = new Date(monthStart);
  calendarStart.setDate(monthStart.getDate() - monthStart.getDay());
  const monthDays = Array.from({ length: 42 }, (_, index) => {
    const day = new Date(calendarStart);
    day.setDate(calendarStart.getDate() + index);
    return day.toISOString().slice(0, 10);
  });
  const weekDayLabels = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sab", "Dom"];
  const calendarWeekLabels = ["Dom", "Seg", "Ter", "Qua", "Qui", "Sex", "Sab"];
  const agendaMembers = (currentTenant?.members || []).filter((member) => member.active !== false);

  async function loadAgenda() {
    setStatus("Carregando agenda...");
    try {
      const todayIso = new Date().toISOString().slice(0, 10);
      const start = visibleDays[0] < todayIso ? visibleDays[0] : todayIso;
      const endDate = new Date(`${visibleDays[visibleDays.length - 1]}T12:00:00`);
      endDate.setDate(endDate.getDate() + 180);
      const end = endDate.toISOString().slice(0, 10);
      const [servicesResponse, appointmentsResponse] = await Promise.all([
        authFetch(`${AGENDA_API_URL}/agenda/services?tenant_id=${encodeURIComponent(tenantId)}&include_inactive=true`),
        authFetch(`${AGENDA_API_URL}/agenda/appointments?tenant_id=${encodeURIComponent(tenantId)}&start=${start}&end=${end}`),
      ]);
      const servicesData = await servicesResponse.json();
      const appointmentsData = await appointmentsResponse.json();
      if (!servicesResponse.ok) throw new Error(servicesData.detail || "Nao foi possivel carregar servicos.");
      if (!appointmentsResponse.ok) throw new Error(appointmentsData.detail || "Nao foi possivel carregar calendario.");
      setServices(servicesData.services || []);
      setAppointments(appointmentsData.appointments || []);
      setStatus("Agenda carregada.");
      if (!appointmentForm.service_id && (servicesData.services || []).some((service) => service.active)) {
        setAppointmentForm((current) => ({ ...current, service_id: servicesData.services.find((service) => service.active)?.id || "" }));
      }
    } catch (error) {
      setStatus(error.message || "Agenda API indisponivel.");
      setServices([]);
      setAppointments([]);
    }
  }

  async function loadStoreSlug() {
    try {
      const response = await authFetch(`${SHOP_API_URL}/shop/config?tenant_id=${encodeURIComponent(tenantId)}`);
      const data = await response.json();
      setStoreSlug(data.config?.chronos_slug || tenantId);
    } catch {
      setStoreSlug(tenantId);
    }
  }

  async function loadAgendaSettings() {
    try {
      const response = await authFetch(`${AGENDA_API_URL}/agenda/settings?tenant_id=${encodeURIComponent(tenantId)}`);
      const data = await response.json();
      if (!response.ok || !data.ok) throw new Error(data.detail || "Nao foi possivel carregar horarios.");
      setAgendaSettings(data.settings);
    } catch {
      setAgendaSettings(null);
    }
  }

  async function loadAgendaResources() {
    try {
      const response = await authFetch(`${STOCK_API_URL}/stock/service-resources?tenant_id=${encodeURIComponent(tenantId)}&include_disabled=false`);
      const data = await response.json();
      if (!response.ok || !data.ok) throw new Error(data.detail || "Nao foi possivel carregar recursos.");
      setAgendaResources(data.resources || []);
    } catch {
      setAgendaResources([]);
    }
  }

  useEffect(() => {
    loadAgenda().catch(() => undefined);
    loadStoreSlug().catch(() => undefined);
    loadAgendaSettings().catch(() => undefined);
    loadAgendaResources().catch(() => undefined);
  }, [tenantId, selectedDay]);

  function updateWeeklyHour(dayKey, field, value) {
    setAgendaSettings((current) => ({
      ...(current || {}),
      weekly_hours: {
        ...((current && current.weekly_hours) || {}),
        [dayKey]: {
          ...(((current && current.weekly_hours) || {})[dayKey] || { enabled: true, start: "08:00", end: "18:00" }),
          [field]: value,
        },
      },
    }));
  }

  async function saveAgendaSettings() {
    if (!agendaSettings?.weekly_hours) return;
    setIsSaving(true);
    setStatus("Salvando horarios de atendimento...");
    try {
      const response = await authFetch(`${AGENDA_API_URL}/agenda/settings`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tenant_id: tenantId, weekly_hours: agendaSettings.weekly_hours }),
      });
      const data = await response.json();
      if (!response.ok || !data.ok) throw new Error(data.detail || "Nao foi possivel salvar horarios.");
      setAgendaSettings(data.settings);
      setStatus("Horarios de atendimento salvos.");
    } catch (error) {
      setStatus(error.message || "Nao foi possivel salvar horarios.");
    } finally {
      setIsSaving(false);
    }
  }

  function resetServiceForm() {
    setEditingServiceId(null);
    setServiceForm({
      name: "",
      description: "",
      image_url: "",
      duration_minutes: "60",
      buffer_minutes: "0",
      price: "0",
      payment_timing: "after",
      resource_ids: [],
      color: "",
      active: true,
    });
  }

  function editService(service) {
    setServiceOpen(true);
    setEditingServiceId(service.id);
    setServiceForm({
      name: service.name || "",
      description: service.description || "",
      image_url: service.image_url || "",
      duration_minutes: String(service.duration_minutes || 60),
      buffer_minutes: String(service.buffer_minutes || 0),
      price: String(service.price || 0),
      payment_timing: service.payment_timing || "after",
      resource_ids: service.resource_ids || [],
      color: service.color || "",
      active: service.active ?? true,
    });
  }

  function toggleServiceResource(resourceId) {
    setServiceForm((current) => {
      const currentIds = current.resource_ids || [];
      return {
        ...current,
        resource_ids: currentIds.includes(resourceId) ? currentIds.filter((id) => id !== resourceId) : [...currentIds, resourceId],
      };
    });
  }

  async function createQuickAgendaResource() {
    if (!quickResourceForm.name.trim()) {
      setStatus("Informe o nome do recurso.");
      return;
    }
    setIsSaving(true);
    setStatus("Criando recurso...");
    try {
      const response = await authFetch(`${STOCK_API_URL}/stock/service-resources`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          tenant_id: tenantId,
          name: quickResourceForm.name,
          kind: quickResourceForm.kind,
          quantity: Number(quickResourceForm.quantity) || 1,
          status: "active",
        }),
      });
      const data = await response.json();
      if (!response.ok || !data.ok) throw new Error(data.detail || "Nao foi possivel criar recurso.");
      setAgendaResources((current) => [...current, data.resource]);
      setServiceForm((current) => ({ ...current, resource_ids: [...(current.resource_ids || []), data.resource.id] }));
      setQuickResourceForm({ name: "", kind: "equipment", quantity: "1" });
      setStatus(`Recurso criado: ${data.resource.name}.`);
    } catch (error) {
      setStatus(error.message || "Nao foi possivel criar recurso.");
    } finally {
      setIsSaving(false);
    }
  }

  async function submitService(event) {
    event.preventDefault();
    if (!serviceForm.name.trim()) {
      setStatus("Informe o nome do servico.");
      return;
    }
    setIsSaving(true);
    setStatus(editingServiceId ? "Salvando servico..." : "Criando servico...");
    try {
      const payload = {
        tenant_id: tenantId,
        ...serviceForm,
        duration_minutes: Number(serviceForm.duration_minutes) || 60,
        buffer_minutes: Number(serviceForm.buffer_minutes) || 0,
          price: Number(serviceForm.price) || 0,
          resource_ids: serviceForm.resource_ids || [],
        };
      const response = await authFetch(
        editingServiceId ? `${AGENDA_API_URL}/agenda/services/${editingServiceId}` : `${AGENDA_API_URL}/agenda/services`,
        {
          method: editingServiceId ? "PATCH" : "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        }
      );
      const data = await response.json();
      if (!response.ok || !data.ok) throw new Error(data.detail || "Nao foi possivel salvar servico.");
      setStatus(`Servico salvo: ${data.service.name}.`);
      resetServiceForm();
      setServiceOpen(false);
      await loadAgenda();
    } catch (error) {
      setStatus(error.message || "Nao foi possivel salvar servico.");
    } finally {
      setIsSaving(false);
    }
  }

  async function deleteService(service) {
    const confirmed = window.confirm(`Desativar o servico "${service.name}"?`);
    if (!confirmed) return;
    setIsSaving(true);
    try {
      const response = await authFetch(`${AGENDA_API_URL}/agenda/services/${service.id}?tenant_id=${encodeURIComponent(tenantId)}`, { method: "DELETE" });
      const data = await response.json();
      if (!response.ok || !data.ok) throw new Error(data.detail || "Nao foi possivel desativar servico.");
      setStatus(`Servico desativado: ${service.name}.`);
      await loadAgenda();
    } catch (error) {
      setStatus(error.message || "Nao foi possivel desativar servico.");
    } finally {
      setIsSaving(false);
    }
  }

  async function submitAppointment(event) {
    event.preventDefault();
    if (!appointmentForm.service_id || !appointmentForm.client_name.trim()) {
      setStatus("Informe servico e cliente.");
      return;
    }
    setIsSaving(true);
    setStatus("Criando agendamento...");
    try {
      const response = await authFetch(`${AGENDA_API_URL}/agenda/appointments`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          tenant_id: tenantId,
          service_id: appointmentForm.service_id,
          client_name: appointmentForm.client_name,
          client_phone: appointmentForm.client_phone,
          employee_id: appointmentForm.employee_id,
          employee_name: agendaMembers.find((member) => member.id === appointmentForm.employee_id)?.name || "",
          starts_at: `${appointmentForm.day}T${appointmentForm.time}:00`,
          notes: appointmentForm.notes,
        }),
      });
      const data = await response.json();
      if (!response.ok || !data.ok) throw new Error(data.detail || "Nao foi possivel criar agendamento.");
      setAppointmentForm((current) => ({ ...current, client_name: "", client_phone: "", notes: "" }));
      setIsAppointmentOpen(false);
      setStatus(`Agendamento criado para ${data.appointment.client_name}.`);
      await loadAgenda();
    } catch (error) {
      setStatus(error.message || "Nao foi possivel criar agendamento.");
    } finally {
      setIsSaving(false);
    }
  }

  async function updateAppointmentStatus(appointment, nextStatus) {
    setIsSaving(true);
    try {
      const response = await authFetch(`${AGENDA_API_URL}/agenda/appointments/${appointment.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tenant_id: tenantId, status: nextStatus }),
      });
      const data = await response.json();
      if (!response.ok || !data.ok) throw new Error(data.detail || "Nao foi possivel atualizar agendamento.");
      setStatus(`Agendamento atualizado: ${data.appointment.client_name}.`);
      await loadAgenda();
    } catch (error) {
      setStatus(error.message || "Nao foi possivel atualizar agendamento.");
    } finally {
      setIsSaving(false);
    }
  }

  const activeServices = services.filter((service) => service.active);
  const appointmentsByDay = visibleDays.reduce((groups, day) => {
    groups[day] = appointments.filter((appointment) => appointment.day === day && appointment.status !== "canceled");
    return groups;
  }, {});
  const selectedDayAppointments = appointmentsByDay[selectedDay] || [];
  const selectedAppointmentsByTime = selectedDayAppointments.reduce((groups, appointment) => {
    groups[appointment.start_time] = appointment;
    return groups;
  }, {});
  const selectedService = activeServices.find((service) => service.id === appointmentForm.service_id) || activeServices[0] || null;
  const selectedServiceDuration = selectedService ? Number(selectedService.duration_minutes || 60) + Number(selectedService.buffer_minutes || 0) : 60;
  const busyTimes = new Set(selectedDayAppointments.map((appointment) => appointment.start_time));
  const now = new Date();
  const upcomingAppointments = appointments
    .filter((appointment) => appointment.status !== "canceled" && new Date(appointment.starts_at) >= now)
    .sort((a, b) => new Date(a.starts_at) - new Date(b.starts_at))
    .slice(0, 10);
  const selectedDate = new Date(`${selectedDay}T12:00:00`);
  const selectedDayConfig = agendaSettings?.weekly_hours?.[String((selectedDate.getDay() + 6) % 7)] || { enabled: true, start: "08:00", end: "18:00" };
  const daySlots = [];
  const [slotStartHour, slotStartMinute] = String(selectedDayConfig.start || "08:00").split(":").map(Number);
  const [slotEndHour, slotEndMinute] = String(selectedDayConfig.end || "18:00").split(":").map(Number);
  let slotCursor = slotStartHour * 60 + slotStartMinute;
  const slotEnd = slotEndHour * 60 + slotEndMinute;
  while (selectedDayConfig.enabled && slotCursor < slotEnd) {
    const wholeHour = Math.floor(slotCursor / 60);
    const minutes = slotCursor % 60;
    const label = `${String(wholeHour).padStart(2, "0")}:${String(minutes).padStart(2, "0")}`;
    daySlots.push({ time: label, available: !busyTimes.has(label) });
    slotCursor += selectedServiceDuration;
  }

  function openAppointmentModal(day = selectedDay, time = appointmentForm.time) {
    setSelectedDay(day);
    setAppointmentForm((current) => ({
      ...current,
      day,
      time,
      service_id: current.service_id || activeServices[0]?.id || "",
    }));
    setIsAppointmentOpen(true);
  }

  function changeSelectedWeek(direction) {
    const nextDate = new Date(`${selectedDay}T12:00:00`);
    nextDate.setDate(nextDate.getDate() + direction * 7);
    setSelectedDay(nextDate.toISOString().slice(0, 10));
  }

  function changeCalendarMonth(direction) {
    const nextDate = new Date(`${datePickerAnchor}T12:00:00`);
    nextDate.setMonth(nextDate.getMonth() + direction);
    setDatePickerAnchor(nextDate.toISOString().slice(0, 10));
  }

  const serviceEditor = <form className="agenda-panel agenda-service-form" onSubmit={submitService}>
            <header>
              <div>
                <span>{editingServiceId ? "Editar servico" : "Novo servico"}</span>
                <h2>{editingServiceId ? serviceForm.name || "Servico" : "Cadastrar servico"}</h2>
              </div>
              {editingServiceId && (
                <button type="button" onClick={resetServiceForm}>
                  <X size={16} />
                </button>
              )}
            </header>
            <div className="agenda-form-grid">
              <label>
                Nome do servico
                <input value={serviceForm.name} onChange={(event) => setServiceForm((current) => ({ ...current, name: event.target.value }))} />
              </label>
              <label>
                Imagem URL
                <input value={serviceForm.image_url} onChange={(event) => setServiceForm((current) => ({ ...current, image_url: event.target.value }))} placeholder="Caminho da imagem local" />
              </label>
              <label>
                Tempo em minutos
                <input type="number" min="5" step="5" value={serviceForm.duration_minutes} onChange={(event) => setServiceForm((current) => ({ ...current, duration_minutes: event.target.value }))} />
              </label>
              <label>
                Intervalo pos-servico
                <input type="number" min="0" step="5" value={serviceForm.buffer_minutes} onChange={(event) => setServiceForm((current) => ({ ...current, buffer_minutes: event.target.value }))} />
              </label>
              <label>
                Preco base
                <input type="number" min="0" step="0.01" value={serviceForm.price} onChange={(event) => setServiceForm((current) => ({ ...current, price: event.target.value }))} />
              </label>
              <label>
                Pagamento
                <select value={serviceForm.payment_timing} onChange={(event) => setServiceForm((current) => ({ ...current, payment_timing: event.target.value }))}>
                  <option value="before">Antes</option>
                  <option value="half_half">50 / 50</option>
                  <option value="after">Depois</option>
                </select>
              </label>
              <label>
                Cor
                <input value={serviceForm.color} onChange={(event) => setServiceForm((current) => ({ ...current, color: event.target.value }))} placeholder="#25d366" />
              </label>
              <label className="agenda-check-label">
                <input type="checkbox" checked={serviceForm.active} onChange={(event) => setServiceForm((current) => ({ ...current, active: event.target.checked }))} />
                Servico ativo
              </label>
              <label className="wide">
                Descricao do servico
                <textarea value={serviceForm.description} onChange={(event) => setServiceForm((current) => ({ ...current, description: event.target.value }))} />
              </label>
            </div>
            <section className="agenda-resource-picker">
              <header>
                <div>
                  <strong>Recursos utilizados</strong>
                  <span>Selecione salas, cadeiras, macas ou equipamentos que bloqueiam horarios.</span>
                </div>
              </header>
              <div className="agenda-resource-options">
                {agendaResources.map((resource) => (
                  <label className={serviceForm.resource_ids.includes(resource.id) ? "selected" : ""} key={resource.id}>
                    <input
                      type="checkbox"
                      checked={serviceForm.resource_ids.includes(resource.id)}
                      onChange={() => toggleServiceResource(resource.id)}
                    />
                    <span>
                      <strong>{resource.name}</strong>
                      <small>{resource.quantity} disponivel(is) · {resource.status}</small>
                    </span>
                  </label>
                ))}
                {agendaResources.length === 0 && <small>Nenhum recurso cadastrado no Estoque.</small>}
              </div>
              <div className="agenda-quick-resource">
                <input value={quickResourceForm.name} onChange={(event) => setQuickResourceForm((current) => ({ ...current, name: event.target.value }))} placeholder="Novo recurso rapido" />
                <select value={quickResourceForm.kind} onChange={(event) => setQuickResourceForm((current) => ({ ...current, kind: event.target.value }))}>
                  <option value="equipment">Equipamento</option>
                  <option value="space">Espaco</option>
                  <option value="room">Sala</option>
                  <option value="chair">Cadeira</option>
                  <option value="machine">Maquina</option>
                  <option value="other">Outro</option>
                </select>
                <input type="number" min="1" step="1" value={quickResourceForm.quantity} onChange={(event) => setQuickResourceForm((current) => ({ ...current, quantity: event.target.value }))} />
                <button type="button" onClick={createQuickAgendaResource} disabled={isSaving || !quickResourceForm.name.trim()} title="Criar recurso">
                  <Plus size={15} />
                </button>
              </div>
            </section>
            <footer>
              <button type="submit" disabled={isSaving}>
                {isSaving ? "Salvando..." : editingServiceId ? "Salvar servico" : "Criar servico"}
              </button>
            </footer>
          </form>;

  return (
    <section className={`agenda-page ${mobile ? "agenda-mobile" : ""}`}>
      {activeSection !== "chores" && (
        <>
          <header className="agenda-header">
            <div>
              <span>Chronos Agenda</span>
              <h1>{activeSection === "services" ? "Servicos" : "Horarios"}</h1>
              <p>Servicos, duracao e horarios da empresa.</p>
            </div>
            <div className="agenda-header-card">
              <small>{currentTenant?.name || tenantId}</small>
              <strong>{activeServices.length} servico(s)</strong>
              <span>{appointments.filter((item) => item.status !== "canceled").length} agenda(s) nos proximos dias</span>
            </div>
          </header>
          <small className="agenda-status">{status}</small>
        </>
      )}

      {activeSection === "services" ? (
        <section className="agenda-services-layout">
          {mobile ? <><button className="agenda-mobile-new" onClick={() => { resetServiceForm(); setServiceOpen(true); }}><Plus size={18} />Novo serviço</button>{serviceOpen && <MobileDialog title={editingServiceId ? "Editar serviço" : "Novo serviço"} onClose={() => { if (!isSaving) setServiceOpen(false); }}><p role="status">{status}</p>{serviceEditor}</MobileDialog>}</> : serviceEditor}

          <section className="agenda-service-list">
            {services.map((service) => (
              <article className={`agenda-service-card ${service.active ? "" : "inactive"}`} key={service.id}>
                <div className="agenda-service-image">{service.image_url ? <AuthenticatedImage src={service.image_url} alt="" /> : <CalendarDays size={26} />}</div>
                <div>
                  <span>{service.payment_label}</span>
                  <strong>{service.name}</strong>
                  <p>{service.description || "Sem descricao."}</p>
                  <small>{service.duration_minutes} min · {formatMoney(service.price)} · intervalo {service.buffer_minutes || 0} min</small>
                  {(service.resource_ids || []).length > 0 && (
                    <small>
                      Recursos: {(service.resource_ids || [])
                        .map((resourceId) => agendaResources.find((resource) => resource.id === resourceId)?.name || resourceId)
                        .join(", ")}
                    </small>
                  )}
                </div>
                <div className="agenda-card-actions">
                  <button type="button" onClick={() => editService(service)} title="Editar servico">
                    <Pencil size={15} />
                  </button>
                  <button type="button" onClick={() => deleteService(service)} title="Desativar servico">
                    <Trash2 size={15} />
                  </button>
                </div>
              </article>
            ))}
            {services.length === 0 && <p className="agenda-empty">Nenhum servico cadastrado ainda.</p>}
          </section>
        </section>
      ) : activeSection === "hours" ? (
        <section className="agenda-calendar-layout">
          <section className="agenda-hours-panel agenda-hours-page">
            <header>
              <div>
                <span>Horarios de atendimento</span>
                <strong>Agenda disponivel para agendamento</strong>
              </div>
              <button type="button" onClick={saveAgendaSettings} disabled={isSaving || !agendaSettings?.weekly_hours}>
                Salvar horarios
              </button>
            </header>
            <div className="agenda-hours-grid">
              {weekDayLabels.map((label, index) => {
                const dayKey = String(index);
                const currentDay = agendaSettings?.weekly_hours?.[dayKey] || { enabled: true, start: "08:00", end: "18:00" };
                return (
                  <div className={`agenda-hours-row ${currentDay.enabled ? "" : "closed"}`} key={dayKey}>
                    <label>
                      <input
                        type="checkbox"
                        checked={currentDay.enabled}
                        onChange={(event) => updateWeeklyHour(dayKey, "enabled", event.target.checked)}
                      />
                      {label}
                    </label>
                    <input type="time" aria-label={`Abertura ${label}`} value={currentDay.start} onChange={(event) => updateWeeklyHour(dayKey, "start", event.target.value)} disabled={!currentDay.enabled} />
                    <input type="time" aria-label={`Fechamento ${label}`} value={currentDay.end} onChange={(event) => updateWeeklyHour(dayKey, "end", event.target.value)} disabled={!currentDay.enabled} />
                  </div>
                );
              })}
            </div>
          </section>
        </section>
      ) : (
        <section className="agenda-today-shell">
          <section className="agenda-today-card">
            <header className="agenda-today-header">
              <div>
                <h2>Agenda conectada</h2>
                <small>{currentTenant?.name || tenantId}</small>
              </div>
              <div className="agenda-today-actions">
                <button type="button" onClick={loadAgenda}>
                  <Loader2 size={14} />
                  Sincronizar
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setDatePickerAnchor(selectedDay);
                    setIsDatePickerOpen(true);
                  }}
                >
                  <CalendarDays size={15} />
                  Escolher data
                </button>
              </div>
            </header>

            <div className="agenda-week-selector">
              <button type="button" onClick={() => changeSelectedWeek(-1)} aria-label="Semana anterior">
                ‹
              </button>
              <div>
                {visibleDays.map((day) => {
                  const date = new Date(`${day}T12:00:00`);
                  const isSelected = selectedDay === day;
                  return (
                    <button type="button" className={isSelected ? "active" : ""} key={day} onClick={() => setSelectedDay(day)}>
                      <span>{date.toLocaleDateString("pt-BR", { weekday: "short" })}</span>
                      <strong>{date.toLocaleDateString("pt-BR", { day: "2-digit" })}</strong>
                      {(appointmentsByDay[day]?.length || 0) > 0 && <small>{appointmentsByDay[day].length}</small>}
                    </button>
                  );
                })}
              </div>
              <button type="button" onClick={() => changeSelectedWeek(1)} aria-label="Proxima semana">
                ›
              </button>
            </div>

            <div className="agenda-quick-create">
              <strong>{new Date(`${selectedDay}T12:00:00`).toLocaleDateString("pt-BR", { weekday: "long", day: "2-digit", month: "long" })}</strong>
              <button type="button" onClick={() => openAppointmentModal(selectedDay)}>
                <Plus size={17} />
                Agendar
              </button>
            </div>

            <section className="agenda-today-list">
              {selectedDayAppointments.map((appointment) => (
                <article className={`agenda-today-item ${appointment.status}`} key={appointment.id}>
                  <div className="agenda-today-check">
                    <CheckCircle2 size={22} />
                  </div>
                  <div>
                    <strong>{appointment.client_name}</strong>
                    <span>{appointment.service_name}</span>
                    {appointment.employee_name && <small>{appointment.employee_name}</small>}
                    {appointment.notes && <p>{appointment.notes}</p>}
                  </div>
                  <time>{appointment.start_time}</time>
                  <div className="agenda-today-item-actions">
                    <button type="button" onClick={() => updateAppointmentStatus(appointment, "confirmed")} title="Confirmar">
                      <CheckCircle2 size={16} />
                    </button>
                    <button type="button" onClick={() => updateAppointmentStatus(appointment, "canceled")} title="Cancelar">
                      <Trash2 size={16} />
                    </button>
                  </div>
                </article>
              ))}
              {selectedDayAppointments.length === 0 && (
                <div className="agenda-today-empty">
                  <CalendarDays size={42} />
                  <strong>Nada agendado neste dia.</strong>
                  <span>Escolha outro dia ou crie um agendamento.</span>
                </div>
              )}
            </section>
            <section className="agenda-upcoming">
              <header>
                <span>Proximos agendamentos</span>
                <strong>{upcomingAppointments.length}</strong>
              </header>
              <div>
                {upcomingAppointments.map((appointment) => (
                  <article key={appointment.id}>
                    <time>
                      {new Date(appointment.starts_at).toLocaleDateString("pt-BR", { day: "2-digit", month: "short" })}
                      <strong>{appointment.start_time}</strong>
                    </time>
                    <div>
                      <strong>{appointment.client_name}</strong>
                      <span>{appointment.service_name}</span>
                      {appointment.employee_name && <small>{appointment.employee_name}</small>}
                    </div>
                  </article>
                ))}
                {upcomingAppointments.length === 0 && <small>Nenhum agendamento futuro encontrado.</small>}
              </div>
            </section>
          </section>
        </section>
      )}
      {isDatePickerOpen && (
        <MobileDialog title="Escolher data" onClose={() => setIsDatePickerOpen(false)}>
          <section className="agenda-date-modal" onMouseDown={(event) => event.stopPropagation()}>
            <header>
              <div>
                <span>Escolher data</span>
                <strong>{monthAnchor.toLocaleDateString("pt-BR", { month: "long", year: "numeric" })}</strong>
              </div>
              <nav>
                <button type="button" onClick={() => changeCalendarMonth(-1)} aria-label="Mes anterior">
                  ‹
                </button>
                <button type="button" onClick={() => changeCalendarMonth(1)} aria-label="Proximo mes">
                  ›
                </button>
              </nav>
              <button type="button" onClick={() => setIsDatePickerOpen(false)} aria-label="Fechar">
                <X size={16} />
              </button>
            </header>
            <div className="agenda-date-modal-weekdays">
              {calendarWeekLabels.map((label) => (
                <span key={label}>{label}</span>
              ))}
            </div>
            <div className="agenda-date-modal-days">
              {monthDays.map((day) => {
                const date = new Date(`${day}T12:00:00`);
                const isCurrentMonth = date.getMonth() === monthAnchor.getMonth();
                const isSelected = day === selectedDay;
                return (
                  <button
                    type="button"
                    className={`${isSelected ? "active" : ""} ${isCurrentMonth ? "" : "muted"}`}
                    key={day}
                    onClick={() => {
                      setSelectedDay(day);
                      setIsDatePickerOpen(false);
                    }}
                  >
                    {date.getDate()}
                  </button>
                );
              })}
            </div>
          </section>
        </MobileDialog>
      )}
      {isAppointmentOpen && (
        <MobileDialog title="Agendar" onClose={() => { if (!isSaving) setIsAppointmentOpen(false); }}><p role="status">{status}</p>
          <form className="agenda-panel agenda-appointment-form agenda-modal" onSubmit={submitAppointment} onMouseDown={(event) => event.stopPropagation()}>
            <header>
              <h2>Agendar</h2>
              <button type="button" onClick={() => setIsAppointmentOpen(false)} aria-label="Fechar">
                <X size={16} />
              </button>
            </header>
            <label>
              Servico
              <select value={appointmentForm.service_id} onChange={(event) => setAppointmentForm((current) => ({ ...current, service_id: event.target.value }))}>
                <option value="">{activeServices.length === 0 ? "Cadastre um servico primeiro" : "Selecionar servico"}</option>
                {activeServices.map((service) => (
                  <option key={service.id} value={service.id}>
                    {service.name} · {service.duration_minutes} min
                  </option>
                ))}
              </select>
            </label>
            <label>
              Cliente
              <input value={appointmentForm.client_name} onChange={(event) => setAppointmentForm((current) => ({ ...current, client_name: event.target.value }))} autoFocus />
            </label>
            <label>
              Telefone
              <input value={appointmentForm.client_phone} onChange={(event) => setAppointmentForm((current) => ({ ...current, client_phone: event.target.value }))} />
            </label>
            <label>
              Funcionario
              <select value={appointmentForm.employee_id} onChange={(event) => setAppointmentForm((current) => ({ ...current, employee_id: event.target.value }))}>
                <option value="">Sem funcionario definido</option>
                {agendaMembers.map((member) => (
                  <option key={member.id} value={member.id}>
                    {member.name}
                  </option>
                ))}
              </select>
            </label>
            <div className="agenda-inline-fields">
              <label>
                Data
                <input type="date" value={appointmentForm.day} onChange={(event) => setAppointmentForm((current) => ({ ...current, day: event.target.value }))} />
              </label>
              <label>
                Hora
                <input type="time" value={appointmentForm.time} onChange={(event) => setAppointmentForm((current) => ({ ...current, time: event.target.value }))} />
              </label>
            </div>
            <label>
              Observacoes
              <textarea value={appointmentForm.notes} onChange={(event) => setAppointmentForm((current) => ({ ...current, notes: event.target.value }))} />
            </label>
            <button type="submit" disabled={isSaving || activeServices.length === 0}>
              <Plus size={16} />
              Agendar
            </button>
          </form>
        </MobileDialog>
      )}
    </section>
  );
}

export function AgendaPublicPage({ storeSlug }) {
  const [services, setServices] = useState([]);
  const [selectedServiceId, setSelectedServiceId] = useState("");
  const [selectedDay, setSelectedDay] = useState(new Date().toISOString().slice(0, 10));
  const [slots, setSlots] = useState([]);
  const [form, setForm] = useState({ client_name: "", client_phone: "", notes: "", time: "" });
  const [status, setStatus] = useState("Carregando agenda...");
  const [isSaving, setIsSaving] = useState(false);
  const today = new Date();
  const visibleDays = Array.from({ length: 10 }, (_, index) => {
    const day = new Date(today);
    day.setDate(today.getDate() + index);
    return day.toISOString().slice(0, 10);
  });
  const selectedService = services.find((service) => service.id === selectedServiceId) || null;

  async function loadPublicAgenda() {
    try {
      const response = await authFetch(`${AGENDA_API_URL}/public/${encodeURIComponent(storeSlug)}/agenda`);
      const data = await response.json();
      if (!response.ok || !data.ok) throw new Error(data.detail || "Nao foi possivel carregar servicos.");
      setServices(data.services || []);
      if (!selectedServiceId && (data.services || []).length > 0) {
        setSelectedServiceId(data.services[0].id);
      }
      setStatus("Escolha um servico e horario.");
    } catch (error) {
      setServices([]);
      setStatus(error.message || "Agenda indisponivel.");
    }
  }

  async function loadSlots(serviceId = selectedServiceId, day = selectedDay) {
    if (!serviceId) {
      setSlots([]);
      return;
    }
    setStatus("Carregando horarios...");
    try {
      const response = await authFetch(`${AGENDA_API_URL}/public/${encodeURIComponent(storeSlug)}/agenda/availability?service_id=${encodeURIComponent(serviceId)}&day=${day}`);
      const data = await response.json();
      if (!response.ok || !data.ok) throw new Error(data.detail || "Nao foi possivel carregar horarios.");
      setSlots(data.slots || []);
      setStatus((data.slots || []).length ? "Horarios disponiveis." : "Nenhum horario disponivel neste dia.");
    } catch (error) {
      setSlots([]);
      setStatus(error.message || "Nao foi possivel carregar horarios.");
    }
  }

  useEffect(() => {
    loadPublicAgenda().catch(() => undefined);
  }, [storeSlug]);

  useEffect(() => {
    loadSlots().catch(() => undefined);
  }, [selectedServiceId, selectedDay]);

  async function submitPublicAppointment(event) {
    event.preventDefault();
    if (!selectedServiceId || !form.time || !form.client_name.trim()) {
      setStatus("Escolha horario e informe seu nome.");
      return;
    }
    setIsSaving(true);
    setStatus("Confirmando agendamento...");
    try {
      const response = await authFetch(`${AGENDA_API_URL}/public/${encodeURIComponent(storeSlug)}/agenda/book`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          service_id: selectedServiceId,
          client_name: form.client_name,
          client_phone: form.client_phone,
          day: selectedDay,
          time: form.time,
          notes: form.notes,
        }),
      });
      const data = await response.json();
      if (!response.ok || !data.ok) throw new Error(data.detail || "Nao foi possivel agendar.");
      setForm({ client_name: "", client_phone: "", notes: "", time: "" });
      setStatus("Agendamento solicitado com sucesso.");
      await loadSlots(selectedServiceId, selectedDay);
    } catch (error) {
      setStatus(error.message || "Nao foi possivel agendar.");
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <section className="agenda-public-page">
      <main className="agenda-public-shell">
        <header>
          <span>Chronos Agenda</span>
          <h1>Agendar horario</h1>
          <p>Escolha um servico, veja os horarios disponiveis e confirme seu atendimento.</p>
        </header>
        <form className="agenda-public-card" onSubmit={submitPublicAppointment}>
          <label>
            Servico
            <select value={selectedServiceId} onChange={(event) => setSelectedServiceId(event.target.value)}>
              <option value="">Selecionar servico</option>
              {services.map((service) => (
                <option key={service.id} value={service.id}>
                  {service.name} · {service.duration_minutes} min
                </option>
              ))}
            </select>
          </label>
          {selectedService && (
            <div className="agenda-public-service">
              <div>{selectedService.image_url ? <AuthenticatedImage src={selectedService.image_url} alt="" /> : <CalendarDays size={24} />}</div>
              <section>
                <strong>{selectedService.name}</strong>
                <p>{selectedService.description || "Servico disponivel para agendamento."}</p>
                <small>{formatMoney(selectedService.price)} · {selectedService.payment_label}</small>
              </section>
            </div>
          )}
          <div className="agenda-public-days">
            {visibleDays.map((day) => (
              <button type="button" className={selectedDay === day ? "active" : ""} key={day} onClick={() => setSelectedDay(day)}>
                <span>{new Date(`${day}T12:00:00`).toLocaleDateString("pt-BR", { weekday: "short" })}</span>
                <strong>{new Date(`${day}T12:00:00`).toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" })}</strong>
              </button>
            ))}
          </div>
          <div className="agenda-public-slots">
            {slots.map((slot) => (
              <button type="button" className={form.time === slot.time ? "active" : ""} key={slot.time} onClick={() => setForm((current) => ({ ...current, time: slot.time }))}>
                {slot.time}
              </button>
            ))}
            {slots.length === 0 && <small>{status}</small>}
          </div>
          <div className="agenda-public-fields">
            <label>
              Nome
              <input value={form.client_name} onChange={(event) => setForm((current) => ({ ...current, client_name: event.target.value }))} />
            </label>
            <label>
              WhatsApp
              <input value={form.client_phone} onChange={(event) => setForm((current) => ({ ...current, client_phone: event.target.value }))} />
            </label>
            <label className="wide">
              Observacao
              <textarea value={form.notes} onChange={(event) => setForm((current) => ({ ...current, notes: event.target.value }))} />
            </label>
          </div>
          <small>{status}</small>
          <button type="submit" disabled={isSaving || !form.time}>
            {isSaving ? "Agendando..." : "Confirmar agendamento"}
          </button>
        </form>
      </main>
    </section>
  );
}
