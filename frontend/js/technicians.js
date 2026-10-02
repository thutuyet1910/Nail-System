// technicians.js: Technician form, directory cards, specialties, schedule, availability
function getDefaultScheduleState() {
    return {
        days: [],
        start_time: "09:00",
        end_time: "18:00",
    };
}

function normalizeScheduleDay(value) {
    const normalized = String(value || "").trim().toLowerCase();
    const match = SCHEDULE_DAYS.find((day) =>
        day.key === normalized ||
        day.label.toLowerCase() === normalized ||
        day.short.toLowerCase() === normalized
    );
    return match ? match.key : "";
}

function addOneHourToTime(value) {
    const [hourText, minuteText = "00"] = String(value || "").split(":");
    const hour = Number(hourText);
    if (Number.isNaN(hour)) return value;
    return `${String(Math.min(hour + 1, 23)).padStart(2, "0")}:${minuteText}`;
}

function parseScheduleState(workSchedule) {
    const state = getDefaultScheduleState();
    if (!workSchedule) return state;

    try {
        const parsed = JSON.parse(workSchedule);

        if (Array.isArray(parsed.days)) {
            state.days = parsed.days.map(normalizeScheduleDay).filter(Boolean);
            state.start_time = parsed.start_time || state.start_time;
            state.end_time = parsed.end_time || state.end_time;
            return state;
        }

        if (parsed && typeof parsed === "object") {
            const legacyDays = [];
            const legacyTimes = [];

            Object.entries(parsed).forEach(([dayName, slots]) => {
                if (Array.isArray(slots) && slots.length) {
                    const dayKey = normalizeScheduleDay(dayName);
                    if (dayKey) legacyDays.push(dayKey);
                    slots.forEach((slot) => {
                        const timeValue = LEGACY_SCHEDULE_SLOT_TIMES[String(slot).toLowerCase()];
                        if (timeValue) legacyTimes.push(timeValue);
                    });
                }
            });

            if (legacyDays.length) {
                state.days = Array.from(new Set(legacyDays));
            }

            if (legacyTimes.length) {
                const sortedTimes = legacyTimes.sort();
                state.start_time = sortedTimes[0];
                state.end_time = addOneHourToTime(sortedTimes[sortedTimes.length - 1]);
            }

            return state;
        }
    } catch {
        return state;
    }

    return state;
}

function getScheduleState() {
    return parseScheduleState(techSchedule?.value?.trim());
}

function updateScheduleFromControls() {
    const boardEl = document.getElementById("techScheduleBoard");
    if (!boardEl || !techSchedule) return;

    const days = Array.from(boardEl.querySelectorAll(".sched-day-checkbox:checked"))
        .map((checkbox) => checkbox.value);

    if (!days.length) {
        techSchedule.value = "";
        return;
    }

    techSchedule.value = JSON.stringify({
        days,
        start_time: "09:00",
        end_time: "18:00",
    });
}

function renderScheduleBoard() {
    const boardEl = document.getElementById("techScheduleBoard");
    if (!boardEl) return;

    const current = getScheduleState();
    const selectedDays = new Set(current.days);

    boardEl.innerHTML = `
    <div class="schedule-editor schedule-editor-days-only">
      <div class="schedule-day-grid">
        ${SCHEDULE_DAYS.map((day) => `
          <label class="schedule-day-box">
            <input type="checkbox" class="sched-day-checkbox" value="${day.key}" ${selectedDays.has(day.key) ? "checked" : ""} />
            <span>${day.label}</span>
          </label>
        `).join("")}
      </div>
    </div>
  `;

    boardEl.querySelectorAll("input").forEach((input) => {
        input.addEventListener("change", updateScheduleFromControls);
        input.addEventListener("input", updateScheduleFromControls);
    });
}

function getScheduleDisplayText(workSchedule) {
    if (!workSchedule) return "-";

    try {
        const obj = JSON.parse(workSchedule);

        if (Array.isArray(obj.days)) {
            const dayText = obj.days
                .map((dayKey) => SCHEDULE_DAYS.find((day) => day.key === normalizeScheduleDay(dayKey))?.label)
                .filter(Boolean)
                .join(", ");
            return dayText || "-";
        }

        return Object.entries(obj)
            .filter(([, slots]) => slots && slots.length)
            .map(([day]) => day)
            .join(", ") || "-";
    } catch {
        return workSchedule || "-";
    }
}

function getRemovedSpecialties() {
    try {
        return new Set(JSON.parse(localStorage.getItem(REMOVED_SPECIALTIES_STORAGE_KEY) || "[]"));
    } catch {
        return new Set();
    }
}

function saveRemovedSpecialties(removed) {
    localStorage.setItem(REMOVED_SPECIALTIES_STORAGE_KEY, JSON.stringify(Array.from(removed)));
}

function getActiveDefaultSpecialties() {
    const removed = getRemovedSpecialties();
    return DEFAULT_SPECIALTIES.filter((specialty) => !removed.has(specialty.toLowerCase()));
}

function applyDateOffStatus() {
    if (!techStatus || !techDateOffStart || !techDateOffEnd) return;
    if (isValidDateText(techDateOffStart.value) && isValidDateText(techDateOffEnd.value)) {
        techStatus.value = "unavailable";
    }
}

function normalizeServiceForMatch(serviceName) {
    return (serviceName || "").trim().toLowerCase();
}

// Same rule as _specialty_matches in backend/crud.py (the map itself is SERVICE_TO_SPECIALTIES
// in config.js). The backend makes the final decision; this only lets the "Assign Preferred"
// and "Reassign" dropdown hide technicians the backend would refuse.
function serviceMatchesTechSpecialties(serviceName, specialties) {
    const techSpecialties = String(specialties || "")
        .split(",")
        .map((item) => item.trim().toLowerCase())
        .filter(Boolean);
    if (!serviceName || !techSpecialties.length) return false;

    const serviceItems = normalizeServiceForMatch(serviceName)
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean);

    if (serviceItems.some((serviceItem) => techSpecialties.includes(serviceItem))) {
        return true;
    }

    const required = new Set();
    serviceItems.forEach((serviceItem) => {
        Object.entries(SERVICE_TO_SPECIALTIES).forEach(([keyword, mapped]) => {
            if (serviceItem.includes(keyword)) mapped.forEach((specialty) => required.add(specialty));
        });
    });

    if (!required.size) return false;
    return techSpecialties.some((specialty) => required.has(specialty));
}

// Looks in techniciansAll so past checkouts and income lines still show the name of a
// technician who has since been deactivated (the backend deactivates anyone with history).
function getTechnicianNameById(technicianId) {
    const normalizedId = Number(technicianId);
    const tech = techniciansAll.find((item) => Number(item.id) === normalizedId);
    return tech ? tech.full_name : "Not assigned";
}

function syncDefaultSpecialtiesToFilter() {
    const selectedFilter = techFilterSpecialty?.value || "";
    const activeDefaultSpecialties = getActiveDefaultSpecialties();

    if (techSpecialties && techSpecialties.dataset.syncedDefaultServices !== "true") {
        techSpecialties.innerHTML = "";
        activeDefaultSpecialties.forEach((specialty) => {
            techSpecialties.appendChild(createSpecialtyCheckbox(specialty));
        });
        techSpecialties.dataset.syncedDefaultServices = "true";
    }

    if (appointmentServicesBox && appointmentServicesBox.dataset.syncedDefaultServices !== "true") {
        appointmentServicesBox.innerHTML = "";
        DEFAULT_APPOINTMENT_SERVICES.forEach((service) => {
            appointmentServicesBox.appendChild(createSpecialtyCheckbox(service));
        });
        appointmentServicesBox.dataset.syncedDefaultServices = "true";
    }

    if (techFilterSpecialty) {
        techFilterSpecialty.innerHTML = `<option value="">All Specialties</option>`;
    }

    activeDefaultSpecialties.forEach((specialty) => {
        const exists = Array.from(techFilterSpecialty.options).some(
            (option) => option.value.toLowerCase() === specialty.toLowerCase()
        );
        if (!exists) {
            const option = document.createElement("option");
            option.value = specialty;
            option.textContent = specialty;
            techFilterSpecialty.appendChild(option);
        }
    });

    if (selectedFilter && Array.from(techFilterSpecialty.options).some((option) => option.value === selectedFilter)) {
        techFilterSpecialty.value = selectedFilter;
    }
}

function createSpecialtyCheckbox(value, checked = false, isCustom = false) {
    const label = document.createElement("label");
    label.className = "checkbox-item";
    label.dataset.value = value.toLowerCase();

    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.value = value;
    checkbox.checked = checked;

    const span = document.createElement("span");
    span.textContent = value;

    label.appendChild(checkbox);
    label.appendChild(span);

    if (isCustom) {
        const deleteBtn = document.createElement("button");
        deleteBtn.type = "button";
        deleteBtn.className = "checkbox-delete-btn";
        deleteBtn.textContent = "Delete";
        deleteBtn.addEventListener("click", (e) => {
            e.preventDefault();
            e.stopPropagation();
            label.remove();
        });
        label.appendChild(deleteBtn);
    }

    return label;
}

function ensureSpecialtyExists(value, checked = false) {
    const normalized = value.trim().toLowerCase();
    if (!normalized) return;

    const removed = getRemovedSpecialties();
    if (removed.delete(normalized)) {
        saveRemovedSpecialties(removed);
    }

    const existing = Array.from(
        techSpecialties.querySelectorAll(".checkbox-item")
    ).find((item) => item.dataset.value === normalized);

    if (existing) {
        const checkbox = existing.querySelector('input[type="checkbox"]');
        if (checkbox) checkbox.checked = checked;
        return;
    }

    const isDefault = DEFAULT_SPECIALTIES.some((specialty) => specialty.toLowerCase() === normalized);
    const newItem = createSpecialtyCheckbox(value, checked, !isDefault);
    techSpecialties.appendChild(newItem);

    const optionExists = Array.from(techFilterSpecialty.options).some(
        (option) => option.value.toLowerCase() === normalized
    );

    if (!optionExists) {
        const option = document.createElement("option");
        option.value = value;
        option.textContent = value;
        techFilterSpecialty.appendChild(option);
    }
}

function deleteSpecialtyByName(value) {
    const normalized = String(value || "").trim().toLowerCase();
    if (!normalized) return false;

    let removedAny = false;
    [techSpecialties, appointmentServicesBox].forEach((container) => {
        const item = Array.from(container?.querySelectorAll(".checkbox-item") || [])
            .find((entry) => entry.dataset.value === normalized);
        if (item) {
            item.remove();
            removedAny = true;
        }
    });

    Array.from(techFilterSpecialty?.options || []).forEach((option) => {
        if (option.value.toLowerCase() === normalized) {
            option.remove();
            removedAny = true;
        }
    });

    if (DEFAULT_SPECIALTIES.some((specialty) => specialty.toLowerCase() === normalized)) {
        const removed = getRemovedSpecialties();
        removed.add(normalized);
        saveRemovedSpecialties(removed);
        removedAny = true;
    }

    return removedAny;
}

function getSelectedSpecialties() {
    return Array.from(
        techSpecialties.querySelectorAll('input[type="checkbox"]:checked')
    )
        .map((checkbox) => checkbox.value)
        .join(", ");
}

function setSelectedSpecialties(value) {
    techSpecialties
        .querySelectorAll('input[type="checkbox"]')
        .forEach((checkbox) => {
            checkbox.checked = false;
        });

    const selectedValues = (value || "")
        .split(",")
        .map((v) => v.trim())
        .filter(Boolean);

    selectedValues.forEach((item) => {
        ensureSpecialtyExists(item, true);
    });
}

function getBadgeClass(availability) {
    if (String(availability || "").toLowerCase().startsWith("date off:")) return "badge-off";
    const map = {
        "available today": "badge-available",
        "on break": "badge-break",
        "busy": "badge-busy",
        "off today": "badge-off",
    };
    return map[availability] || "badge-default";
}

function getAvailabilityDisplayText(availability) {
    const parsed = parseDateOffAvailability(availability);
    if (parsed.start && parsed.end) {
        return `Date Off: ${parsed.start} to ${parsed.end}`;
    }
    return availability || "unknown";
}

function getTemporaryUnavailableMap() {
    try {
        return JSON.parse(localStorage.getItem(TECH_UNAVAILABLE_TODAY_STORAGE_KEY) || "{}") || {};
    } catch {
        return {};
    }
}

function saveTemporaryUnavailableMap(map) {
    localStorage.setItem(TECH_UNAVAILABLE_TODAY_STORAGE_KEY, JSON.stringify(map || {}));
}

async function setTechnicianUnavailableToday(techId) {
    await fetchJson(`${API_BASE}/technicians/${techId}`, {
        method: "PUT",
        body: JSON.stringify({
            status: "unavailable",
            availability: "off today",
        }),
    });

    const map = getTemporaryUnavailableMap();
    map[String(techId)] = getLocalDateKey();
    saveTemporaryUnavailableMap(map);
}

async function resetTemporaryUnavailableTechs() {
    const map = getTemporaryUnavailableMap();
    const today = getLocalDateKey();
    const expiredIds = Object.keys(map).filter((techId) => map[techId] !== today);

    if (!expiredIds.length) return;

    let rawTechs = [];
    try {
        rawTechs = await fetchJson(`${API_BASE}/technicians`);
    } catch {
        return;
    }

    for (const techId of expiredIds) {
        const tech = rawTechs.find((item) => Number(item.id) === Number(techId));
        const availability = String(tech?.availability || "").trim().toLowerCase();

        if (availability.startsWith("date off:")) {
            delete map[techId];
            continue;
        }

        try {
            await fetchJson(`${API_BASE}/technicians/${techId}`, {
                method: "PUT",
                body: JSON.stringify({
                    status: "active",
                    availability: "available today",
                }),
            });
            delete map[techId];
        } catch (error) {
            console.warn("Could not reset technician availability", techId, error);
        }
    }

    saveTemporaryUnavailableMap(map);
}

function getTechnicianAvatar(tech) {
    if (tech.profile_photo) {
        return `<img src="${escapeHtml(tech.profile_photo)}" alt="${escapeHtml(tech.full_name)}" class="tech-avatar-img" />`;
    }
    return `<div class="tech-avatar-fallback">${escapeHtml(getInitials(tech.full_name))}</div>`;
}

function getSpecialtyItems(specialties) {
    return String(specialties || "")
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean);
}

function renderTechnicianScheduleSummary(schedule) {
    return `<span class="tech-schedule-value">${escapeHtml(getScheduleDisplayText(schedule))}</span>`;
}

function resetTechnicianForm() {
    technicianForm.reset();
    techIdInput.value = "";
    techFormTitle.textContent = "Add Technician";
    saveTechBtn.textContent = "Save Technician";
    cancelEditBtn.classList.add("hidden");
    setSelectedSpecialties("");
    techStatus.value = "off";
    if (techDateOffStart) techDateOffStart.value = "";
    if (techDateOffEnd) techDateOffEnd.value = "";
    if (techSchedule) techSchedule.value = "";
    renderScheduleBoard();
}

function validateTechStartDate(showMessage = false) {
    if (!techStartDate) return true;

    const value = techStartDate.value;
    if (!value) {
        techStartDate.setCustomValidity("");
        return true;
    }

    const minDate = "2000-01-01";
    const maxDate = "2100-12-31";
    const isoValue = displayDateToISO(value);

    if (!isValidDateText(value) || isoValue < minDate || isoValue > maxDate) {
        techStartDate.setCustomValidity("Please enter a valid date with a 4-digit year between 2000 and 2100.");
        if (showMessage) {
            techStartDate.reportValidity();
        }
        return false;
    }

    techStartDate.setCustomValidity("");
    return true;
}

function fillTechnicianForm(tech) {
    techIdInput.value = tech.id;
    techName.value = tech.full_name || "";
    techPhone.value = tech.phone || "";
    techStartDate.value = isoToDisplayDate(tech.start_date);
    techStatus.value = tech.status || "off";
    const dateOff = parseDateOffAvailability(tech.availability);
    if (techDateOffStart) techDateOffStart.value = dateOff.start;
    if (techDateOffEnd) techDateOffEnd.value = dateOff.end;
    if (techSchedule) techSchedule.value = tech.work_schedule || "";
    setSelectedSpecialties(tech.specialties || "");
    renderScheduleBoard();

    techFormTitle.textContent = "Edit Technician";
    saveTechBtn.textContent = "Update Technician";
    cancelEditBtn.classList.remove("hidden");
}

// One request gives both lists:
//   techniciansAll = everyone, including deactivated (for looking up names on history)
//   techniciansRaw = active technicians only (for dropdowns, calendar columns, assignment)
async function loadTechniciansRaw() {
    techniciansAll = await fetchJson(`${API_BASE}/technicians?include_inactive=true`);
    techniciansRaw = techniciansAll.filter((tech) => tech.is_active !== false);
}

async function loadTechnicians() {
    const params = new URLSearchParams();

    if (techSearch?.value.trim()) params.append("search", techSearch.value.trim());
    if (techFilterSpecialty?.value) params.append("specialty", techFilterSpecialty.value);
    if (techFilterStatus?.value) params.append("status", techFilterStatus.value);

    const queryString = params.toString() ? `?${params.toString()}` : "";
    technicians = await fetchJson(`${API_BASE}/technicians/cards${queryString}`);
    await loadTechniciansRaw();
    populateAppointmentTechnicianDropdown();
    renderTechnicianCards();
}

function renderTechnicianCards() {
    technicianCards.innerHTML = "";

    if (!technicians.length) {
        technicianCards.innerHTML = `<div class="empty-state">No technicians found.</div>`;
        return;
    }

    technicians.forEach((tech) => {
        const card = document.createElement("div");
        card.className = "tech-card technician-card";

        card.innerHTML = `
        <div class="tech-card-top">
            <div class="tech-avatar-wrap">
                ${getTechnicianAvatar(tech)}
            </div>
            <div class="tech-main-info">
                <div class="tech-title-row">
                    <h4>${escapeHtml(tech.full_name)}</h4>
                    <span class="status-chip">${escapeHtml(tech.status || "-")}</span>
                </div>
            </div>
        </div>

        <div class="tech-popup">
            <span class="availability-badge ${getBadgeClass(tech.availability)}">
                ${escapeHtml(getAvailabilityDisplayText(tech.availability))}
            </span>

            <div class="tech-stats">
                <div class="stat-box">
                    <span class="stat-label">Today Appts</span>
                    <strong>${tech.today_appointments_count || 0}</strong>
                </div>
                <div class="stat-box">
                    <span class="stat-label">Today Turns</span>
                    <strong>${tech.today_turns_count || 0}</strong>
                </div>
            </div>

            <div class="tech-details">
                <div class="tech-meta">
                    <div class="tech-meta-row tech-meta-wide">
                        <strong>Phone</strong>
                        <span class="tech-phone">${escapeHtml(tech.phone || "-")}</span>
                    </div>
                    <div class="tech-meta-row tech-meta-wide">
                        <strong>Specialties</strong>
                        <div class="specialty-chips">
                            ${getSpecialtyItems(tech.specialties).map((item) =>
                                `<span class="specialty-chip">${escapeHtml(item)}</span>`
                            ).join("") || `<span class="tech-empty-value">No specialties</span>`}
                        </div>
                    </div>
                    <div class="tech-meta-row">
                        <strong>Start Date</strong>
                        <div class="tech-icon-line">
                            ${TECH_ICONS.calendar}
                            <span>${tech.start_date ? isoToDisplayDate(tech.start_date) : "-"}</span>
                        </div>
                    </div>
                    <div class="tech-meta-row">
                        <strong>Schedule</strong>
                        <div class="tech-icon-line tech-icon-line-top">
                            ${TECH_ICONS.clock}
                            ${renderTechnicianScheduleSummary(tech.work_schedule)}
                        </div>
                    </div>
                </div>
            </div>

            <div class="tech-actions">
                <button class="ghost-btn tech-btn-edit tech-edit-btn" data-id="${tech.id}">${TECH_ICONS.edit}Edit</button>
                <button class="ghost-btn tech-btn-delete tech-delete-btn" data-id="${tech.id}">${TECH_ICONS.trash}Delete</button>
                <button class="ghost-btn tech-btn-schedule tech-schedule-btn" data-id="${tech.id}">${TECH_ICONS.calendar.replace("tech-icon", "btn-icon")}Schedule</button>
                <button class="ghost-btn tech-btn-unavailable tech-unavailable-btn" data-id="${tech.id}">${TECH_ICONS.ban}Unavailable</button>
            </div>
        </div>
        `;

        card.addEventListener("mouseenter", () => {
            const popup = card.querySelector(".tech-popup");
            const rect = card.getBoundingClientRect();
            const appRect = document.querySelector(".app").getBoundingClientRect();

            card.classList.toggle("popup-right", rect.left + 340 > window.innerWidth - 16);
            card.classList.toggle("popup-up", rect.bottom + popup.offsetHeight > appRect.bottom - 8);
        });


        card.addEventListener("click", (e) => {
            if (e.target.closest(".tech-popup")) return;
            card.classList.toggle("expanded");
        });

        technicianCards.appendChild(card);
    });

    document.querySelectorAll(".tech-edit-btn").forEach((btn) => {
        btn.addEventListener("click", async () => {
            const techId = btn.dataset.id;
            const tech = await fetchJson(`${API_BASE}/technicians/${techId}`);
            fillTechnicianForm(tech);
            window.scrollTo({ top: 0, behavior: "smooth" });
        });
    });

    document.querySelectorAll(".tech-delete-btn").forEach((btn) => {
        btn.addEventListener("click", async () => {
            const techId = btn.dataset.id;
            const confirmed = await showCuteConfirm("Delete this technician?", "Please Confirm");
            if (!confirmed) return;

            try {
                const result = await fetchJson(`${API_BASE}/technicians/${techId}`, {
                    method: "DELETE",
                });
                showCuteNotification(result?.message || "Technician deleted successfully.");
                await loadAll();
            } catch (error) {
                showCuteNotification(error.message || "Failed to delete technician.", "Oops");
            }
        });
    });

    document.querySelectorAll(".tech-schedule-btn").forEach((btn) => {
        btn.addEventListener("click", async () => {
            const techId = btn.dataset.id;
            const today = getLocalDateKey();

            try {
                const data = await fetchJson(`${API_BASE}/appointments?date=${today}&technician_id=${techId}`);
                if (!data.length) {
                    showCuteNotification("No appointments for this technician today.", "Today's Schedule");
                    return;
                }

                const summary = data
                    .map((appt) => {
                        const dt = new Date(appt.appointment_time);
                        const time = dt.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
                        const category = appt.service_category || appt.service_name || "-";
                        return `${time} - ${appt.customer_name} (${category})`;
                    })
                    .join(" • ");

                showCuteNotification(summary, "Today's Schedule");
            } catch (error) {
                showCuteNotification("Could not load technician schedule.", "Oops");
            }
        });
    });

    document.querySelectorAll(".tech-unavailable-btn").forEach((btn) => {
        btn.addEventListener("click", async () => {
            const techId = btn.dataset.id;
            const confirmed = await showCuteConfirm(
                "Mark this technician unavailable for the rest of today?",
                "Please Confirm"
            );
            if (!confirmed) return;

            try {
                await setTechnicianUnavailableToday(techId);
                showCuteNotification("Technician will not receive more customers today.");
                await loadAll();
            } catch (error) {
                showCuteNotification(error.message || "Failed to update technician availability.", "Oops");
            }
        });
    });
}