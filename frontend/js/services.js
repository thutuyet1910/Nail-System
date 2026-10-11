// services.js: Owner service catalog (the backend database is the only source of truth)

let catalogServices = [];
let catalogTechnicians = [];

const svcEl = (id) => document.getElementById(id);

function showServiceFormError(message) {
    const box = svcEl("serviceFormError");
    box.textContent = message || "";
    box.classList.toggle("hidden", !message);
}

function formatServicePrice(price) {
    return price === null || price === undefined ? "Not set" : formatMoney(price);
}

async function loadServiceCatalog() {
    const [services, technicians] = await Promise.all([
        fetchJson(`${API_BASE}/booking-services`),
        fetchJson(`${API_BASE}/technicians`),
    ]);
    catalogServices = services;
    catalogTechnicians = technicians;
}

function renderServiceTechnicianChoices(selectedIds = []) {
    const selected = new Set(selectedIds);
    const box = svcEl("serviceTechnicians");
    if (!catalogTechnicians.length) {
        box.innerHTML = `<span class="tech-empty-value">No active technicians.</span>`;
        return;
    }
    box.innerHTML = catalogTechnicians.map((tech) => `
      <label class="service-tech-option">
        <input type="checkbox" value="${tech.id}" ${selected.has(tech.id) ? "checked" : ""} />
        <span>${escapeHtml(tech.full_name)}</span>
      </label>`).join("");
}

function renderServiceCategoryOptions() {
    const categories = [...new Set(catalogServices.map((s) => s.category).filter(Boolean))].sort();
    const filter = svcEl("serviceCategoryFilter");
    const current = filter.value;
    filter.innerHTML = `<option value="">All Categories</option>` +
        categories.map((c) => `<option value="${escapeHtml(c)}">${escapeHtml(c)}</option>`).join("");
    filter.value = categories.includes(current) ? current : "";
    svcEl("serviceCategoryList").innerHTML = categories.map((c) => `<option value="${escapeHtml(c)}"></option>`).join("");
}

function renderServiceTable() {
    const search = svcEl("serviceSearch").value.trim().toLowerCase();
    const category = svcEl("serviceCategoryFilter").value;
    const status = svcEl("serviceStatusFilter").value;
    const techNames = new Map(catalogTechnicians.map((t) => [t.id, t.full_name]));

    const rows = catalogServices.filter((s) =>
        (!search || s.name.toLowerCase().includes(search)) &&
        (!category || s.category === category) &&
        (!status || (status === "active") === s.is_active));

    const body = svcEl("serviceTableBody");
    if (!rows.length) {
        body.innerHTML = `<tr><td colspan="9" class="notification-empty">No services found.</td></tr>`;
        return;
    }
    body.innerHTML = rows.map((s) => {
        const names = s.eligible_technician_ids.map((id) => techNames.get(id)).filter(Boolean);
        return `
      <tr class="${s.is_active ? "" : "service-inactive"}">
        <td><strong>${escapeHtml(s.name)}</strong></td>
        <td>${escapeHtml(s.category || "—")}</td>
        <td>${s.duration_minutes} min</td>
        <td>${escapeHtml(formatServicePrice(s.price))}</td>
        <td>${s.buffer_before_minutes} min</td>
        <td>${s.buffer_after_minutes} min</td>
        <td title="${escapeHtml(names.join(", "))}">${s.eligible_technician_ids.length} tech${s.eligible_technician_ids.length === 1 ? "" : "s"}</td>
        <td><span class="inventory-status ${s.is_active ? "inventory-status-ok" : "inventory-status-low"}">${s.is_active ? "Active" : "Inactive"}</span></td>
        <td><div class="inventory-actions">
          <button type="button" class="ghost-btn" data-service-edit="${s.id}">Edit</button>
          <button type="button" class="ghost-btn" data-service-toggle="${s.id}">${s.is_active ? "Deactivate" : "Activate"}</button>
        </div></td>
      </tr>`;
    }).join("");
}

function resetServiceForm() {
    svcEl("serviceForm").reset();
    svcEl("service_id").value = "";
    svcEl("serviceFormTitle").textContent = "Add Service";
    svcEl("saveServiceBtn").textContent = "Save Service";
    svcEl("cancelServiceEditBtn").classList.add("hidden");
    svcEl("service_duration").value = 60;
    svcEl("service_buffer_before").value = 0;
    svcEl("service_buffer_after").value = 0;
    svcEl("service_active").checked = true;
    renderServiceTechnicianChoices([]);
    showServiceFormError("");
}

function fillServiceForm(service) {
    svcEl("service_id").value = service.id;
    svcEl("service_name").value = service.name;
    svcEl("service_category").value = service.category || "";
    svcEl("service_duration").value = service.duration_minutes;
    svcEl("service_price").value = service.price === null ? "" : service.price;
    svcEl("service_buffer_before").value = service.buffer_before_minutes;
    svcEl("service_buffer_after").value = service.buffer_after_minutes;
    svcEl("service_active").checked = service.is_active;
    svcEl("serviceFormTitle").textContent = `Edit Service: ${service.name}`;
    svcEl("saveServiceBtn").textContent = "Update Service";
    svcEl("cancelServiceEditBtn").classList.remove("hidden");
    renderServiceTechnicianChoices(service.eligible_technician_ids);
    showServiceFormError("");
}

function readServiceForm() {
    const name = svcEl("service_name").value.trim();
    const duration = Number(svcEl("service_duration").value);
    const before = Number(svcEl("service_buffer_before").value);
    const after = Number(svcEl("service_buffer_after").value);
    const priceText = svcEl("service_price").value.trim();
    if (!name) throw new Error("Service name is required.");
    if (!Number.isInteger(duration) || duration < 5 || duration > 600) throw new Error("Duration must be a whole number of minutes between 5 and 600.");
    if (!Number.isInteger(before) || before < 0 || before > 120) throw new Error("Buffer before must be a whole number between 0 and 120 minutes.");
    if (!Number.isInteger(after) || after < 0 || after > 120) throw new Error("Buffer after must be a whole number between 0 and 120 minutes.");
    let price = null;
    if (priceText !== "") {
        price = Number(priceText);
        if (!Number.isFinite(price) || price < 0 || price > 100000) throw new Error("Price must be a number from 0 to 100000, or left blank if not set.");
        price = Math.round(price * 100) / 100;
    }
    return {
        name,
        category: svcEl("service_category").value.trim() || null,
        duration_minutes: duration,
        price,
        buffer_before_minutes: before,
        buffer_after_minutes: after,
        is_active: svcEl("service_active").checked,
    };
}

async function refreshServices() {
    await loadServiceCatalog();
    renderServiceCategoryOptions();
    renderServiceTable();
}

async function renderServicesPage() {
    await refreshServices();
    if (!svcEl("service_id").value) renderServiceTechnicianChoices([]);
}

svcEl("serviceForm")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    showServiceFormError("");
    let payload;
    try {
        payload = readServiceForm();
    } catch (error) {
        showServiceFormError(error.message);
        return;
    }
    const technicianIds = [...svcEl("serviceTechnicians").querySelectorAll("input:checked")].map((box) => Number(box.value));
    const editingId = svcEl("service_id").value;
    let saved = null;
    try {
        saved = await fetchJson(
            editingId ? `${API_BASE}/booking-services/${editingId}` : `${API_BASE}/booking-services`,
            { method: editingId ? "PATCH" : "POST", body: JSON.stringify(payload) },
        );
        await fetchJson(`${API_BASE}/booking-services/${saved.id}/technicians`, {
            method: "PUT", body: JSON.stringify({ technician_ids: technicianIds }),
        });
        resetServiceForm();
        await refreshServices();
        showCuteNotification(editingId ? "Service updated successfully." : "Service added successfully.");
    } catch (error) {
        showServiceFormError(error.message || "Failed to save service.");
        if (saved) await refreshServices().catch(() => {});  // service saved but technicians did not: show real state
    }
});

svcEl("cancelServiceEditBtn")?.addEventListener("click", resetServiceForm);
["serviceSearch", "serviceCategoryFilter", "serviceStatusFilter"].forEach((id) => {
    svcEl(id)?.addEventListener("input", renderServiceTable);
    svcEl(id)?.addEventListener("change", renderServiceTable);
});
svcEl("addServiceBtn")?.addEventListener("click", () => {
    resetServiceForm();
    svcEl("service_name").focus();
    svcEl("serviceFormCard").scrollIntoView({ behavior: "smooth", block: "start" });
});

svcEl("serviceTableBody")?.addEventListener("click", async (event) => {
    const editBtn = event.target.closest("[data-service-edit]");
    const toggleBtn = event.target.closest("[data-service-toggle]");
    if (editBtn) {
        const service = catalogServices.find((s) => s.id === Number(editBtn.dataset.serviceEdit));
        if (!service) return;
        fillServiceForm(service);
        svcEl("serviceFormCard").scrollIntoView({ behavior: "smooth", block: "start" });
    } else if (toggleBtn) {
        const service = catalogServices.find((s) => s.id === Number(toggleBtn.dataset.serviceToggle));
        if (!service) return;
        if (service.is_active && !(await showCuteConfirm(`Deactivate "${service.name}"? It will no longer be bookable or offered to callers. Existing appointments are not changed.`))) return;
        try {
            await fetchJson(`${API_BASE}/booking-services/${service.id}`, { method: "PATCH", body: JSON.stringify({ is_active: !service.is_active }) });
            await refreshServices();
        } catch (error) {
            showCuteNotification(error.message || "Failed to update service.", "Oops");
        }
    }
});
