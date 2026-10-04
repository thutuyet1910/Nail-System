// ui.js: Icons, notifications, confirm box, PIN, switching views

const TECH_ICONS = {
    calendar: `<svg class="tech-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="18" rx="3"/><path d="M16 2v4M8 2v4M3 10h18"/></svg>`,
    clock: `<svg class="tech-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></svg>`,
    edit: `<svg class="btn-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 013 3L7 19l-4 1 1-4z"/></svg>`,
    trash: `<svg class="btn-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18M8 6V4h8v2M6 6l1 14h10l1-14M10 10v6M14 10v6"/></svg>`,
    ban: `<svg class="btn-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M5.6 5.6l12.8 12.8"/></svg>`,
};

const uiIcon = (paths) =>
    `<svg class="ui-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${paths}</svg>`;

const UI_ICONS = {
    phone: uiIcon(`<path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72c.127.96.361 1.903.7 2.81a2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45c.907.339 1.85.573 2.81.7A2 2 0 0 1 22 16.92z"/>`),
    clock: uiIcon(`<circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>`),
    calendar: uiIcon(`<rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/>`),
    user: uiIcon(`<path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>`),
    check: uiIcon(`<polyline points="20 6 9 17 4 12"/>`),
    search: uiIcon(`<circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>`),
    arrowLeft: uiIcon(`<line x1="19" y1="12" x2="5" y2="12"/><polyline points="12 19 5 12 12 5"/>`),
    wand: uiIcon(`<path d="m21.64 3.64-1.28-1.28a1.21 1.21 0 0 0-1.72 0L2.36 18.64a1.21 1.21 0 0 0 0 1.72l1.28 1.28a1.2 1.2 0 0 0 1.72 0L21.64 5.36a1.2 1.2 0 0 0 0-1.72"/><path d="m14 7 3 3"/><path d="M5 6v4"/><path d="M19 14v4"/><path d="M10 2v2"/><path d="M7 8H3"/><path d="M21 16h-4"/><path d="M11 3H9"/>`),
};

function showView(view) {
    const views = {
        calendar: [calendarView, null],
        customerList: [customerListView, navCustomerList],
        technician: [technicianView, navTechnician],
        appointment: [appointmentView, navAppointment],
        inventory: [inventoryView, navInventory],
        checkout: [checkoutView, navCheckout],
        techIncome: [techIncomeView, navTechIncome],
        salonIncome: [salonIncomeView, navSalonIncome],
    };

    Object.values(views).forEach(([section, nav]) => {
        section.classList.remove("active-view");
        nav?.classList.remove("active");
    });

    const [section, nav] = views[view] || views.calendar;
    section.classList.add("active-view");
    nav?.classList.add("active");
}

function askPin() {
    return new Promise((resolve) => {
        const modal = document.getElementById("pinModal");
        const input = document.getElementById("pinInput");
        const okBtn = document.getElementById("pinOkBtn");
        const cancelBtn = document.getElementById("pinCancelBtn");

        const finish = (value) => {
            modal.classList.add("hidden");
            input.value = "";
            resolve(value);
        };

        input.value = "";
        modal.classList.remove("hidden");
        input.focus();

        okBtn.onclick = () => finish(input.value);
        cancelBtn.onclick = () => finish(null);
        input.onkeydown = (e) => {
            if (e.key === "Enter") finish(input.value);
            if (e.key === "Escape") finish(null);
        };
    });
}

async function requireOwner() {
    try {
        const session = await fetchJson(`${API_BASE}/auth/session`);
        if (session.authenticated) {
            ownerAuthenticated = true;
            ownerSessionExpiresAt = session.expires_at;
            return true;
        }
    } catch {
        ownerAuthenticated = false;
    }
    const entered = await askPin();
    if (entered === null) return false;

    try {
        const session = await fetchJson(`${API_BASE}/auth/login`, {
            method: "POST",
            body: JSON.stringify({ password: entered }),
        });
        ownerAuthenticated = true;
        ownerSessionExpiresAt = session.expires_at;
        return true;
    } catch (error) {
        ownerAuthenticated = false;
        showCuteNotification(error.message || "Incorrect owner password/PIN.", "Oops");
        return false;
    }
}

function showCuteNotification(message, title = "Success") {
    cuteNotificationTitle.textContent = title;
    cuteNotificationMessage.textContent = message;
    cuteNotification.classList.remove("hidden");
}

function hideCuteNotification() {
    cuteNotification.classList.add("hidden");
}

function showCuteConfirm(message, title = "Please Confirm") {
    return new Promise((resolve) => {
        confirmResolve = resolve;
        cuteConfirmTitle.textContent = title;
        cuteConfirmMessage.textContent = message;
        cuteConfirm.classList.remove("hidden");
    });
}

function closeCuteConfirm(result) {
    cuteConfirm.classList.add("hidden");
    if (confirmResolve) {
        confirmResolve(result);
        confirmResolve = null;
    }
}
