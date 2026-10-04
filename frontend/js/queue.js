// Same customer? A usable phone is authoritative; name is only a fallback when neither side has one.
function isSameCustomer(nameA, phoneA, nameB, phoneB) {
    const normalizedNameA = (nameA || "").trim().toLowerCase();
    const normalizedNameB = (nameB || "").trim().toLowerCase();
    const normalizePhone = (value) => {
        const digits = (value || "").replace(/\D/g, "");
        return digits.length === 11 && digits.startsWith("1") ? digits.slice(1) : digits;
    };
    const digitsA = normalizePhone(phoneA);
    const digitsB = normalizePhone(phoneB);

    if (digitsA || digitsB) return Boolean(digitsA && digitsB && digitsA === digitsB);
    return Boolean(normalizedNameA && normalizedNameB && normalizedNameA === normalizedNameB);
}

// When the customer checked in, in milliseconds (null if the check-in app sent no usable time).
function getCheckinTimeMs(item) {
    if (!item?.checked_in_at) return null;
    const ms = new Date(item.checked_in_at).getTime();
    return Number.isNaN(ms) ? null : ms;
}

// Working today: marked active and available today (the same test the backend uses).
function isAvailableToday(tech) {
    const status = String(tech.status || "").trim().toLowerCase();
    const availability = String(tech.availability || "").trim().toLowerCase();
    return status === "active" && availability === "available today";
}

// True when the technician already has a waiting, assigned, or in-service customer today
// (the same meaning as "free" in the backend). excludeTurnId lets a customer's own turn be ignored.
function isTechnicianBusyToday(technicianId, excludeTurnId = null) {
    return todayTurns.some((turn) =>
        Number(turn.technician_id) === Number(technicianId) &&
        (excludeTurnId === null || Number(turn.id) !== Number(excludeTurnId)) &&
        ["waiting", "assigned", "in_service"].includes(turn.status)
    );
}

// Fills the technician dropdown with technicians who are available today and qualified for
// the service. For a reassign it also leaves out the customer's current technician and anyone
// who is busy, because the backend refuses both. (The backend makes the final decision.)
function populatePreferredTechSelect(serviceName = "", { excludeTechnicianId = null, onlyFree = false } = {}) {
    if (!preferredTechSelect) return;

    preferredTechSelect.innerHTML = `<option value="">Select technician</option>`;

    const availableTechs = techniciansRaw.filter((tech) => {
        const isAvailable = isAvailableToday(tech);
        const isExcluded = excludeTechnicianId !== null && Number(tech.id) === Number(excludeTechnicianId);
        const canDoService = !serviceName || serviceMatchesTechSpecialties(serviceName, tech.specialties);
        const isFree = !onlyFree || !isTechnicianBusyToday(tech.id);

        return isAvailable && !isExcluded && canDoService && isFree;
    });

    if (!availableTechs.length) {
        const option = document.createElement("option");
        option.value = "";
        option.textContent = onlyFree
            ? "No free technician matches this service"
            : serviceName ? "No available technician matches this service" : "No available technicians today";
        preferredTechSelect.appendChild(option);
        return;
    }

    availableTechs.forEach((tech) => {
        const option = document.createElement("option");
        option.value = tech.id;
        option.textContent = tech.full_name;
        preferredTechSelect.appendChild(option);
    });
}

function formatLiveCheckinTime(dateString) {
    const date = new Date(dateString);
    return date.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
}

function getTurnForCustomer(checkinItem) {
    const matchingTurns = todayTurns.filter((turn) =>
        isSameCustomer(checkinItem.full_name, checkinItem.phone_number, turn.customer_name, turn.customer_phone)
    );

    if (!matchingTurns.length) return null;

    matchingTurns.sort((a, b) => {
        const aTime = new Date(a.created_at || 0).getTime();
        const bTime = new Date(b.created_at || 0).getTime();
        return bTime - aTime;
    });

    return matchingTurns[0];
}

async function loadTodayTurns() {
    try {
        todayTurns = await fetchJson(`${API_BASE}/turns/today`);
    } catch (error) {
        console.error("Failed to load today turns:", error);
        todayTurns = [];
    }
}

// Goes back to "today" (used when the Customer List screen is opened again).
function resetHistoryView() {
    historyView = { mode: "today", bounds: null, label: "today" };
}

// Fetches the checkouts ONCE and updates both lists. Throws if the backend cannot be reached.
//   todayCheckouts  -> used by the waiting queue (always today, whatever the history card shows)
//   checkoutHistory -> what the history card shows, following the view the user chose
async function refreshCheckoutLists() {
    const checkouts = await fetchJson(`${API_BASE}/checkouts`);
    const todayBounds = { start: getLocalDateKey(), end: getLocalDateKey() };
    todayCheckouts = filterCheckoutsByRange(checkouts, todayBounds);

    if (historyView.mode === "all") {
        checkoutHistory = checkouts;
    } else if (historyView.mode === "range" && historyView.bounds) {
        checkoutHistory = filterCheckoutsByRange(checkouts, historyView.bounds);
    } else {
        checkoutHistory = todayCheckouts;
    }
}

async function loadCheckoutHistory() {
    try {
        await refreshCheckoutLists();
    } catch (error) {
        console.error("Failed to load checkout history:", error);
        todayCheckouts = [];
        checkoutHistory = [];
    }
}

async function loadSaleHistoryRange() {
    setupIncomeDateDefaults();
    const bounds = getRangeBounds(saleHistoryRangeType, saleHistoryRangeStart, saleHistoryRangeEnd);
    if (!bounds) {
        showCuteNotification("Enter a valid sale history range. Years must be exactly 4 numbers.", "Notice");
        return;
    }

    historyView = { mode: "range", bounds, label: bounds.label };
    await loadCheckoutHistory();
    renderCheckoutHistoryList();
}

async function loadAllCheckoutHistory() {
    historyView = { mode: "all", bounds: null, label: "all history" };

    try {
        await refreshCheckoutLists();
        renderCheckoutHistoryList();
    } catch (error) {
        todayCheckouts = [];
        checkoutHistory = [];
        renderCheckoutHistoryList();
        showCuteNotification(error.message || "Failed to load checkout history.", "Oops");
    }
}

// A customer who has already paid today is not shown in the waiting queue again.
// Uses todayCheckouts, so it is not affected by what the history card is showing.
function getCheckoutForCustomer(checkinItem) {
    return todayCheckouts.find((checkout) =>
        isSameCustomer(checkinItem.full_name, checkinItem.phone_number, checkout.customer_name, checkout.customer_phone)
    ) || null;
}

function renderCheckoutHistoryList() {
    if (!checkoutHistoryList) return;
    const rangeLabel = historyView.label || "today";

    if (!checkoutHistory.length) {
        checkoutHistoryList.innerHTML = `
      <div class="tech-card">
        <div class="tech-card-top">
          <div class="tech-main-info">
            <div class="tech-title-row"><h4>No completed checkouts for ${escapeHtml(rangeLabel)}</h4></div>
            <p class="tech-subtext">Checked-out customers will appear here.</p>
          </div>
        </div>
      </div>`;
        return;
    }

    checkoutHistoryList.innerHTML = checkoutHistory.map((checkout) => `
      <div class="tech-card history-card">
        <div class="person-row">
          <div class="person-avatar">${escapeHtml(getInitials(checkout.customer_name))}</div>
          <div class="person-info">
            <div class="person-title">
              <h4>${escapeHtml(checkout.customer_name)}</h4>
              <span class="status-chip chip-checked-out">${UI_ICONS.check}Checked Out</span>
            </div>
            <p class="person-line">${UI_ICONS.phone}<span>${escapeHtml(checkout.customer_phone || "-")}</span></p>
            <p class="person-line">${UI_ICONS.calendar}<span>Completed: ${formatDateTime(checkout.created_at)}</span></p>
          </div>
        </div>
        <div class="person-divider"></div>
        <p class="person-detail"><strong>Technician:</strong><span>${escapeHtml(getTechnicianNameById(checkout.technician_id))}</span></p>
        <p class="person-detail"><strong>Service:</strong><span>${escapeHtml(checkout.service_name || "-")}</span></p>
        <p class="person-detail-inline"><strong>Paid:</strong> ${formatMoney(checkout.customer_pays)}<span class="person-sep">|</span><strong>Technician Tip:</strong> ${formatMoney(checkout.tip_amount)}</p>
      </div>`).join("");
}

function mergeTodayTurn(turn) {
    if (!turn?.id) return;

    const existingIndex = todayTurns.findIndex((item) => Number(item.id) === Number(turn.id));
    if (existingIndex >= 0) {
        todayTurns[existingIndex] = turn;
    } else {
        todayTurns.push(turn);
    }
}

// Decides what Auto Assign does for ONE waiting customer who may have booked a technician.
// The booked technician is the one named on the customer's appointment today.
//   mode "preferred" = the booked technician can take the customer right now: give them the customer
//   mode "wait"      = the booked technician is working and qualified but busy: the customer waits for them
//   mode "auto"      = no booking, or the booked technician cannot take this customer today (not
//                      working, not qualified): use the normal fair assignment
// ownTurnId is the customer's own waiting turn (if any), so it does not make the technician look busy.
function getBookedTechnicianPlan(item, ownTurnId = null) {
    if (item?.appointment_match?.outcome === "ambiguous") {
        return { mode: "review" };
    }
    const appointment = getAppointmentForCheckin(item);
    const bookedTechId = appointment ? (appointment.technician_id || appointment.preferred_technician_id) : null;
    if (!bookedTechId) return { mode: "auto" };

    const tech = techniciansRaw.find((entry) => Number(entry.id) === Number(bookedTechId));
    if (!tech) return { mode: "auto" };

    const serviceName = getCombinedServiceName(item);
    if (!isAvailableToday(tech) || !serviceMatchesTechSpecialties(serviceName, tech.specialties)) {
        return { mode: "auto" };
    }

    if (isTechnicianBusyToday(tech.id, ownTurnId)) {
        return WAIT_FOR_BOOKED_TECHNICIAN ? { mode: "wait", tech } : { mode: "auto" };
    }

    return { mode: "preferred", tech };
}

// Assigns one waiting customer through the backend. Quiet on purpose: autoAssignAllWaitingCheckins
// counts the successes and failures and shows one summary message.
//   bookedTechId given -> the customer goes to that technician (assign-preferred)
//   otherwise          -> the backend picks fairly, fewest turns first (assign-auto)
// Returns the turn, or null if the customer could not be assigned.
async function autoAssignCheckin(item, bookedTechId = null) {
    const serviceName = getCombinedServiceName(item);
    if (!serviceName) return null;

    const body = {
        customer_name: item.full_name,
        customer_phone: item.phone_number,
        service_name: serviceName,
        source: "checkin",
        discount_type: item.discount_type || null,
        discount_value: Number(item.discount_value || 0),
        discount_label: item.discount_label || null
    };
    if (item.visit_id) body.checkin_visit_id = item.visit_id;
    if (item.customer_id) body.checkin_customer_id = item.customer_id;
    if (item.appointment_match?.outcome === "exact_match") {
        body.appointment_id = item.appointment_match.appointment.id;
    }
    if (bookedTechId) body.preferred_technician_id = bookedTechId;

    try {
        const turn = await fetchJson(`${API_BASE}/turns/${bookedTechId ? "assign-preferred" : "assign-auto"}`, {
            method: "POST",
            body: JSON.stringify(body)
        });

        mergeTodayTurn(turn);
        return turn;
    } catch {
        return null;
    }
}

async function autoAssignAllWaitingCheckins() {
    await loadTodayTurns();
    await loadCheckoutHistory();
    await loadLiveCheckinQueue();
    await loadTechniciansRaw();
    await loadAppointments();

    const unassignedItems = liveCheckins.filter((item) => {
        const linkedTurn = getTurnForCustomer(item);
        const completedCheckout = getCheckoutForCustomer(item);
        return !completedCheckout && (!linkedTurn || linkedTurn.status === "waiting");
    });

    if (!unassignedItems.length) {
        showCuteNotification("No waiting customers to auto assign.", "Notice");
        return;
    }

    // Customers who booked a technician go FIRST, so nobody else is given that technician before them.
    // (The sort is stable: everyone keeps their place in the queue within each group.)
    const hasBooking = (item) => getBookedTechnicianPlan(item).mode !== "auto";
    const orderedItems = [...unassignedItems].sort((a, b) => Number(hasBooking(b)) - Number(hasBooking(a)));

    let assignedCount = 0;
    let failedCount = 0;
    let waitingForBookedCount = 0;
    let ambiguousCount = 0;

    for (const item of orderedItems) {
        // Work this out again for each customer: every assignment above changes who is busy.
        const ownTurn = getTurnForCustomer(item);
        const plan = getBookedTechnicianPlan(item, ownTurn ? ownTurn.id : null);

        if (plan.mode === "wait") {
            waitingForBookedCount += 1;
            continue;
        }
        if (plan.mode === "review") {
            ambiguousCount += 1;
            continue;
        }

        const assignedTurn = await autoAssignCheckin(item, plan.mode === "preferred" ? plan.tech.id : null);
        if (assignedTurn) {
            assignedCount += 1;
        } else {
            failedCount += 1;
        }
    }

    await loadTechniciansRaw();
    await loadTodayTurns();
    await loadCheckoutHistory();
    await loadLiveCheckinQueue();
    renderCheckoutReadyList();

    if (calendarView.classList.contains("active-view")) {
        renderCalendar();
    }

    if (assignedCount > 0) {
        showView("checkout");
    }

    const waitingNotes = [];
    if (failedCount > 0) {
        waitingNotes.push(
            `${failedCount} ${failedCount > 1 ? "customers are" : "customer is"} still waiting because no technician is available right now.`
        );
    }
    if (waitingForBookedCount > 0) {
        waitingNotes.push(
            `${waitingForBookedCount} ${waitingForBookedCount > 1 ? "customers are" : "customer is"} waiting for the technician they booked.`
        );
    }
    if (ambiguousCount > 0) {
        waitingNotes.push(
            `${ambiguousCount} ${ambiguousCount > 1 ? "customers need" : "customer needs"} an appointment match reviewed before assignment.`
        );
    }

    if (assignedCount > 0 && waitingNotes.length === 0) {
        showCuteNotification(
            `${assignedCount} customer${assignedCount > 1 ? "s have" : " has"} been assigned successfully.`
        );
    } else if (assignedCount > 0) {
        showCuteNotification(
            `${assignedCount} customer${assignedCount > 1 ? "s have" : " has"} been assigned. ${waitingNotes.join(" ")}`,
            "Notice"
        );
    } else if (waitingForBookedCount === 0 && ambiguousCount === 0) {
        showCuteNotification(
            "No customers were assigned because no technician is available right now.",
            "Notice"
        );
    } else {
        showCuteNotification(`No customers were assigned. ${waitingNotes.join(" ")}`, "Notice");
    }
}

function setPreferredTechModalText(title, confirmLabel) {
    const modalTitle = document.getElementById("preferredTechTitle");
    if (modalTitle) modalTitle.textContent = title;
    if (preferredTechConfirmBtn) preferredTechConfirmBtn.textContent = confirmLabel;
}

async function openPreferredTechModal(item) {
    await loadTechniciansRaw();
    const serviceName = getCombinedServiceName(item);

    preferredTechModalMode = "assign";
    pendingPreferredCheckinItem = item;
    pendingReassignTurn = null;

    populatePreferredTechSelect(serviceName);

    preferredTechSelect.value = "";
    setPreferredTechModalText("Select Preferred Technician", "Assign");

    if (preferredTechCustomerText) {
        preferredTechCustomerText.textContent = `Choose a technician for ${item.full_name}.`;
    }

    preferredTechModal?.classList.remove("hidden");
}

// Opens the popup to move a customer who is already assigned (or in service) to another technician.
async function openReassignModal(turnId) {
    // Fresh data first: the list of free technicians depends on who is busy right now.
    await loadTechniciansRaw();
    await loadTodayTurns();

    const turn = todayTurns.find((item) => Number(item.id) === Number(turnId));
    if (!turn) {
        showCuteNotification("This customer is no longer in today's list.", "Oops");
        renderCheckoutReadyList();
        return;
    }

    if (!["assigned", "in_service"].includes(turn.status)) {
        showCuteNotification("Only assigned or in-service customers can be reassigned.", "Notice");
        renderCheckoutReadyList();
        return;
    }

    preferredTechModalMode = "reassign";
    pendingPreferredCheckinItem = null;
    pendingReassignTurn = turn;

    populatePreferredTechSelect(turn.service_name || "", {
        excludeTechnicianId: turn.technician_id,
        onlyFree: true,
    });

    preferredTechSelect.value = "";
    setPreferredTechModalText("Reassign Technician", "Reassign");

    if (preferredTechCustomerText) {
        preferredTechCustomerText.textContent =
            `Choose a new technician for ${turn.customer_name}. Currently with ${getTechnicianNameById(turn.technician_id)}.`;
    }

    preferredTechModal?.classList.remove("hidden");
}

function closePreferredTechModal() {
    preferredTechModal?.classList.add("hidden");
    preferredTechModalMode = "assign";
    pendingPreferredCheckinItem = null;
    pendingReassignTurn = null;

    if (preferredTechSelect) {
        preferredTechSelect.value = "";
    }

    setPreferredTechModalText("Select Preferred Technician", "Assign");

    if (preferredTechCustomerText) {
        preferredTechCustomerText.textContent = "";
    }
}

// "Assign" button, assign mode: give the checked-in customer to the chosen preferred technician.
async function submitPreferredAssignment(selectedTechId) {
    if (!pendingPreferredCheckinItem) return;

    if (pendingPreferredCheckinItem.appointment_match?.outcome === "ambiguous") {
        showCuteNotification("This customer has multiple possible appointments. Review the appointments before assigning.", "Notice");
        return;
    }

    try {
        const serviceName = getCombinedServiceName(pendingPreferredCheckinItem);
        const matchedAppointment = getAppointmentForCheckin(pendingPreferredCheckinItem);

        await fetchJson(`${API_BASE}/turns/assign-preferred`, {
            method: "POST",
            body: JSON.stringify({
                customer_name: pendingPreferredCheckinItem.full_name,
                customer_phone: pendingPreferredCheckinItem.phone_number,
                service_name: serviceName,
                preferred_technician_id: selectedTechId,
                source: "checkin",
                discount_type: pendingPreferredCheckinItem.discount_type || null,
                discount_value: Number(pendingPreferredCheckinItem.discount_value || 0),
                discount_label: pendingPreferredCheckinItem.discount_label || null,
                appointment_id: matchedAppointment?.id || null,
                checkin_customer_id: pendingPreferredCheckinItem.customer_id || null,
                checkin_visit_id: pendingPreferredCheckinItem.visit_id || null
            })
        });

        closePreferredTechModal();
        await loadTechniciansRaw();
        await loadAppointments();
        await loadTodayTurns();
        await loadLiveCheckinQueue();
        renderCheckoutReadyList();
        renderCalendar();
        showView("customerList");
        showCuteNotification("Preferred technician assigned. Customer moved to Checkout.");
    } catch (error) {
        closePreferredTechModal();
        showCuteNotification(error.message || "Failed to save technician assignment.", "Oops");
    }
}

// "Reassign" button, reassign mode: move the customer's turn to the chosen technician.
// The backend keeps the turn's progress (an in-service customer stays in service).
async function submitReassignment(selectedTechId) {
    const turn = pendingReassignTurn;
    if (!turn) return;

    try {
        await fetchJson(`${API_BASE}/turns/${turn.id}/reassign`, {
            method: "PUT",
            body: JSON.stringify({
                technician_id: selectedTechId,
                assigned_by: "manager"
            })
        });

        closePreferredTechModal();
        await loadTechniciansRaw();
        await loadAppointments();
        await loadTodayTurns();
        await loadLiveCheckinQueue();

        // If this customer is already loaded into the checkout form, point the form at the new
        // technician. Otherwise the checkout would be refused ("technician does not match the turn").
        if (checkoutTurnId?.value && Number(checkoutTurnId.value) === Number(turn.id)) {
            if (checkoutTechnicianId) checkoutTechnicianId.value = String(selectedTechId);
            if (checkoutTechnicianName) checkoutTechnicianName.value = getTechnicianNameById(selectedTechId);
        }

        renderCheckoutReadyList();
        renderCalendar();
        showCuteNotification("Technician reassigned successfully.");
    } catch (error) {
        closePreferredTechModal();
        showCuteNotification(error.message || "Failed to reassign technician.", "Oops");
    }
}

async function assignPreferredCheckin(item) {
    const serviceName = getCombinedServiceName(item);
    if (!serviceName) {
        showCuteNotification("No service found for this customer.", "Oops");
        return;
    }

    await openPreferredTechModal(item);
}

function renderLiveCheckinQueue(checkins) {
    if (!liveCheckinQueue) return;

    if (!checkins || checkins.length === 0) {
        liveCheckinQueue.innerHTML = `
      <div class="tech-card">
        <div class="tech-card-header">
          <h4>No customers waiting</h4>
        </div>
        <p class="tech-subtext">No one has checked in yet.</p>
      </div>
    `;
        return;
    }

    // Only show unassigned/waiting customers in live queue
    const waitingCheckins = checkins.filter((item) => {
        const linkedTurn = getTurnForCustomer(item);
        const completedCheckout = getCheckoutForCustomer(item);
        return !completedCheckout && (!linkedTurn || linkedTurn.status === "waiting");
    });

    if (!waitingCheckins.length) {
        liveCheckinQueue.innerHTML = `
      <div class="tech-card">
        <div class="tech-card-header">
          <h4>All customers assigned</h4>
        </div>
        <p class="tech-subtext">No one is waiting to be assigned.</p>
      </div>`;
    } else {
        liveCheckinQueue.innerHTML = waitingCheckins.map((item) => `
      <div class="tech-card queue-card">
        <div class="person-row">
          <div class="person-avatar">${escapeHtml((item.full_name || "?").trim().charAt(0).toUpperCase())}</div>
          <div class="person-info">
            <div class="person-title">
              <h4>#${item.position} ${escapeHtml(item.full_name)}</h4>
              <span class="status-chip dispatch-status-waiting">waiting</span>
            </div>
            <p class="person-line">${UI_ICONS.phone}<span>${escapeHtml(item.phone_number || "-")}</span></p>
            <p class="person-line">${UI_ICONS.clock}<span>Checked in: ${formatLiveCheckinTime(item.checked_in_at)}</span></p>
          </div>
        </div>
        <div class="person-divider"></div>
        <p class="person-detail"><strong>Services:</strong><span>${escapeHtml((item.services || []).join(", ") || "-")}</span></p>
        <button class="mini-btn assign-btn queue-preferred-btn" data-name="${escapeHtml(item.full_name)}" data-phone="${escapeHtml(item.phone_number)}">${UI_ICONS.user}Assign Preferred</button>
      </div>`).join("");

        liveCheckinQueue.querySelectorAll(".queue-preferred-btn").forEach((btn) => {
            btn.addEventListener("click", async () => {
                const item = checkins.find(
                    (entry) =>
                        entry.full_name === btn.dataset.name &&
                        String(entry.phone_number || "") === String(btn.dataset.phone || "")
                );
                if (item) await assignPreferredCheckin(item);
            });
        });
    }

    // Always render assigned list below the waiting queue
    renderCheckoutReadyList();
    renderCheckoutHistoryList();
}

async function loadLiveCheckinQueue() {
    if (!liveCheckinQueue) return;

    try {
        const response = await fetch(`${API_BASE}/checkins/today`, { credentials: "include" });
        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.detail || "Failed to load live check-in queue.");
        }

        liveCheckins = data.checkins || [];
        renderLiveCheckinQueue(liveCheckins);
    } catch (error) {
        liveCheckins = [];
        liveCheckinQueue.innerHTML = `
      <div class="tech-card">
        <div class="tech-card-header">
          <h4>Unable to load queue</h4>
        </div>
        <p class="tech-subtext">${escapeHtml(error.message || "Connection error.")}</p>
      </div>
    `;
        renderCheckoutReadyList();
    }
}

function getCombinedServiceName(item) {
    if (!item) return "";
    if (Array.isArray(item.services) && item.services.length > 0) {
        return item.services.join(", ");
    }
    return item.services || "";
}
