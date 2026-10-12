// salon-settings.js: the owner-only Salon Settings page. Every value comes from, and is saved to, the
// backend (the single source of truth): the booking hours here are the same ones the calendar, manual
// booking and the AI receptionist use, so saving updates them all at once. No secret is ever shown.

const SETTINGS_DAY_LABELS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];

const settingsEl = (id) => document.getElementById(id);

function showSettingsError(id, message) {
    const box = settingsEl(id);
    if (!box) return;
    box.textContent = message || "";
    box.classList.toggle("hidden", !message);
}

function applySalonName(name) {
    if (!name) return;
    if (salonNameHeading) salonNameHeading.textContent = name;
    document.title = `${name} Calendar`;
}

// Public endpoint (staff can read it): keeps the sidebar and tab title in step with the saved name.
async function loadSalonName() {
    const profile = await fetchJson(`${API_BASE}/salon`);
    applySalonName(profile.salon_name);
}

function timeInputValue(value) {
    return value ? String(value).slice(0, 5) : "";
}

function renderBusinessHoursForm(hours) {
    const byDay = new Map((hours || []).map((day) => [day.day_of_week, day]));
    settingsEl("businessHoursBody").innerHTML = SETTINGS_DAY_LABELS.map((label, index) => {
        const day = byDay.get(index) || { is_closed: true };
        const open = !day.is_closed;
        return `
      <tr data-day="${index}">
        <td><strong>${label}</strong></td>
        <td><label class="hours-open-label"><input type="checkbox" class="hours-open" ${open ? "checked" : ""} aria-label="${label} open" /><span class="hours-state">${open ? "Open" : "Closed"}</span></label></td>
        <td><input type="time" step="900" class="hours-opens" value="${open ? timeInputValue(day.opens_at) : ""}" ${open ? "" : "disabled"} aria-label="${label} opens" /></td>
        <td><input type="time" step="900" class="hours-closes" value="${open ? timeInputValue(day.closes_at) : ""}" ${open ? "" : "disabled"} aria-label="${label} closes" /></td>
      </tr>`;
    }).join("");
}

function statusPill(ok, yes, no) {
    return `<span class="settings-pill ${ok ? "ok" : "off"}">${ok ? yes : no}</span>`;
}

// The saved public salon phone is shown from the SAME profile record as the Salon Information box, so the
// two sections can never disagree. It is a separate value from the Twilio number below.
function renderSalonPhoneSaved(profile) {
    settingsEl("salonPhoneSaved").textContent = profile.business_phone_display
        ? `Saved: ${profile.business_phone_display}`
        : "No salon phone saved yet.";
}

function renderAiStatus(status, profile) {
    settingsEl("aiStatusList").innerHTML = `
      <dt>Public salon phone</dt><dd>${escapeHtml(profile.business_phone_display || "Not set (add it under Salon Information)")}</dd>
      <dt>AI Receptionist</dt><dd>${statusPill(status.configured, "Configured", "Not configured")}${status.missing.length ? ` <small>Missing: ${escapeHtml(status.missing.join(", "))}</small>` : ""}</dd>
      <dt>Twilio number</dt><dd>${escapeHtml(status.twilio_number_display || "Not configured")}</dd>
      <dt>Voice status</dt><dd>${statusPill(status.ready_for_calls, "Enabled", "Disabled")}</dd>`;
    settingsEl("aiStatusNote").textContent = status.note;
}

async function renderSettingsPage() {
    const [profile, hours, ai] = await Promise.all([
        fetchJson(`${API_BASE}/settings/salon`),
        fetchJson(`${API_BASE}/business-hours`),
        fetchJson(`${API_BASE}/settings/ai-receptionist`),
    ]);
    settingsEl("settings_salon_name").value = profile.salon_name;
    settingsEl("settings_salon_phone").value = profile.business_phone_display || "";
    settingsEl("settings_timezone").value = profile.timezone;
    renderSalonPhoneSaved(profile);
    settingsEl("settingsTimezoneNote").textContent = profile.timezone_note;
    ["salonProfileError", "businessHoursError", "passwordError"].forEach((id) => showSettingsError(id, ""));
    renderBusinessHoursForm(hours);
    renderAiStatus(ai, profile);
}

// The whole week, checked in the browser for a quick message; the backend validates it again and is the authority.
function readBusinessHoursForm() {
    const days = [...settingsEl("businessHoursBody").querySelectorAll("tr")].map((row) => {
        const index = Number(row.dataset.day);
        const open = row.querySelector(".hours-open").checked;
        const opens = row.querySelector(".hours-opens").value;
        const closes = row.querySelector(".hours-closes").value;
        if (open) {
            if (!opens || !closes) throw new Error(`${SETTINGS_DAY_LABELS[index]}: enter both an opening and a closing time.`);
            if (closes <= opens) throw new Error(`${SETTINGS_DAY_LABELS[index]}: closing time must be after opening time.`);
        }
        return { day_of_week: index, is_closed: !open, opens_at: open ? opens : null, closes_at: open ? closes : null };
    });
    return { days };
}

settingsEl("businessHoursBody")?.addEventListener("change", (event) => {
    if (!event.target.classList.contains("hours-open")) return;
    const row = event.target.closest("tr");
    const state = row.querySelector(".hours-state");
    if (state) state.textContent = event.target.checked ? "Open" : "Closed";
    row.querySelectorAll(".hours-opens, .hours-closes").forEach((input) => {
        input.disabled = !event.target.checked;
        if (event.target.checked && !input.value) input.value = input.classList.contains("hours-opens") ? "09:00" : "18:00";
    });
});

settingsEl("businessHoursForm")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    showSettingsError("businessHoursError", "");
    let payload;
    try {
        payload = readBusinessHoursForm();
    } catch (error) {
        showSettingsError("businessHoursError", error.message);
        return;
    }
    try {
        const saved = await fetchJson(`${API_BASE}/business-hours`, { method: "PUT", body: JSON.stringify(payload) });
        businessHours = saved;  // the calendar's hours: window, shading, red line follow at once
        renderBusinessHoursForm(saved);
        if (calendarHasLoaded) renderCalendar();
        showCuteNotification("Booking hours saved. The calendar and the AI receptionist use them right away.");
    } catch (error) {
        showSettingsError("businessHoursError", error.message || "Could not save the booking hours.");
    }
});

settingsEl("salonProfileForm")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    showSettingsError("salonProfileError", "");
    const name = settingsEl("settings_salon_name").value.trim();
    if (!name) return showSettingsError("salonProfileError", "Salon name is required.");
    try {
        const saved = await fetchJson(`${API_BASE}/settings/salon`, {
            method: "PUT",
            body: JSON.stringify({ salon_name: name, business_phone: settingsEl("settings_salon_phone").value.trim() || null }),
        });
        settingsEl("settings_salon_name").value = saved.salon_name;
        settingsEl("settings_salon_phone").value = saved.business_phone_display || "";
        applySalonName(saved.salon_name);
        renderSalonPhoneSaved(saved);
        renderAiStatus(await fetchJson(`${API_BASE}/settings/ai-receptionist`), saved);
        showCuteNotification("Salon information saved.");
    } catch (error) {
        showSettingsError("salonProfileError", error.message || "Could not save the salon information.");
    }
});

settingsEl("passwordForm")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    showSettingsError("passwordError", "");
    const current = settingsEl("settings_current_password").value;
    const next = settingsEl("settings_new_password").value;
    const confirm = settingsEl("settings_confirm_password").value;
    const clearPasswords = () => ["settings_current_password", "settings_new_password", "settings_confirm_password"].forEach((id) => { settingsEl(id).value = ""; });
    if (!current || !next || !confirm) return showSettingsError("passwordError", "Fill in all three password boxes.");
    if (next !== confirm) return showSettingsError("passwordError", "The new password and its confirmation do not match.");
    try {
        await fetchJson(`${API_BASE}/settings/security/password`, {
            method: "POST",
            body: JSON.stringify({ current_password: current, new_password: next, confirm_password: confirm }),
        });
    } catch (error) {
        clearPasswords();
        showSettingsError("passwordError", error.message || "Could not change the password.");
        return;
    }
    clearPasswords();
    // The server signed every owner session out (this one too). Drop to staff mode without another request.
    lockOwner({ serverSignedOut: true });
    showCuteNotification("Your password was changed. Please sign in again to open Owner Management.", "Password changed");
});
