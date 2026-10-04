function resetCheckoutForm() {
    checkoutForm?.reset();
    if (saveCheckoutBtn) saveCheckoutBtn.textContent = "Complete Checkout";
    if (checkoutTechnicianId) checkoutTechnicianId.value = "";
    if (checkoutTechnicianName) checkoutTechnicianName.value = "";

    if (checkoutSubtotal) checkoutSubtotal.value = 0;
    if (checkoutDiscountValue) checkoutDiscountValue.value = 0;
    if (checkoutTip) checkoutTip.value = 0;
    if (checkoutDiscountType) checkoutDiscountType.value = "none";
    if (checkoutPaymentMethod) checkoutPaymentMethod.value = "cash";
    if (checkoutDiscountDisplay) {
        checkoutDiscountDisplay.dataset.discountLabel = "";
        checkoutDiscountDisplay.textContent = "No discount applied";
    }

    updateCheckoutSummary();
}

// ---------------------------------------------------------------------------------------
// Checkout preview math. DISPLAY ONLY.
//
// The backend recalculates every money figure when the checkout is saved
// (_calculate_checkout in backend/crud.py), and the form sends it only the four inputs:
// subtotal, discount type, discount value, and tip. Keep these rules identical to the backend:
//
//   discount          none = 0 | fixed = the value | percent = subtotal x value / 100
//                     (never more than the subtotal)
//   net service       subtotal - discount
//   technician 60%    60% of the SUBTOTAL (a discount never lowers technician pay)
//   salon share       subtotal - technician share
//   salon actual      salon share - discount        (the owner pays the discount)
//   technician total  technician share + tip
//   customer pays     net service + tip
//
// Amounts are worked out in whole cents and rounded half-up, like the server does.
// ---------------------------------------------------------------------------------------
const TECHNICIAN_RATE_PERCENT = 60;

function toCents(value) {
    return Math.round((Number(value) || 0) * 100 + 1e-7);
}

function calculateCheckoutAmounts({ gross, discountType, discountValue, tip }) {
    const grossCents = toCents(gross);
    const tipCents = toCents(tip);

    let discountCents = 0;
    if (discountType === "fixed") {
        discountCents = toCents(discountValue);
    } else if (discountType === "percent") {
        discountCents = Math.round((grossCents * (Number(discountValue) || 0)) / 100 + 1e-7);
    }
    discountCents = Math.min(discountCents, grossCents);

    const netCents = grossCents - discountCents;
    const techShareCents = Math.round((grossCents * TECHNICIAN_RATE_PERCENT) / 100 + 1e-7);
    const salonShareCents = grossCents - techShareCents;
    const salonActualCents = salonShareCents - discountCents;

    return {
        discountAmount: discountCents / 100,
        netService: netCents / 100,
        techShare: techShareCents / 100,
        salonActual: salonActualCents / 100,
        techTotal: (techShareCents + tipCents) / 100,
        customerPays: (netCents + tipCents) / 100,
    };
}

function getCheckoutCalculation() {
    const gross = Number(checkoutSubtotal?.value || 0);
    const discountType = checkoutDiscountType?.value || "none";
    const discountValue = Number(checkoutDiscountValue?.value || 0);
    const tip = Number(checkoutTip?.value || 0);

    return {
        gross,
        tip,
        discountType,
        discountValue,
        ...calculateCheckoutAmounts({ gross, discountType, discountValue, tip }),
    };
}

function updateCheckoutSummary() {
    const calc = getCheckoutCalculation();

    if (checkoutGross) checkoutGross.textContent = formatMoney(calc.gross);
    if (checkoutDiscount) checkoutDiscount.textContent = formatMoney(calc.discountAmount);
    if (checkoutNet) checkoutNet.textContent = formatMoney(calc.netService);
    if (checkoutTechShare) checkoutTechShare.textContent = formatMoney(calc.techShare);
    if (checkoutSalonActual) checkoutSalonActual.textContent = formatMoney(calc.salonActual);
    if (checkoutTechTotal) checkoutTechTotal.textContent = formatMoney(calc.techTotal);
    if (checkoutCustomerPays) checkoutCustomerPays.textContent = formatMoney(calc.customerPays);
    if (checkoutTipSummary) checkoutTipSummary.textContent = formatMoney(calc.tip);
    if (checkoutDiscountDisplay) {
        checkoutDiscountDisplay.textContent = formatDiscountText(
            checkoutDiscountDisplay.dataset.discountLabel || "",
            calc.discountType,
            calc.discountValue
        );
    }
}

async function refreshCheckoutRelatedViews() {
    await loadAppointments();
    await loadTodayTurns();
    await loadCheckoutHistory();
    await loadLiveCheckinQueue();
    renderCheckoutReadyList();
    renderCheckoutHistoryList();

    if (calendarView.classList.contains("active-view")) {
        renderCalendar();
    }
}

function formatDiscountText(label, discountType, discountValue) {
    if (discountType === "percent" && discountValue > 0) {
        return `${label || "Automatic discount"}: ${discountValue}% off`;
    }

    if (discountType === "fixed" && discountValue > 0) {
        return `${label || "Automatic discount"}: ${formatMoney(discountValue)} off`;
    }

    return label || "No discount applied";
}

function getCheckinDiscountForTurn(turn) {
    if (!turn) return null;

    const checkin = liveCheckins.find((item) =>
        isSameCustomer(item.full_name, item.phone_number, turn.customer_name, turn.customer_phone)
    );

    if (!checkin?.discount_type) return null;

    return {
        type: checkin.discount_type,
        value: Number(checkin.discount_value || 0),
        label: checkin.discount_label || "",
    };
}

function getDiscountForTurn(turn) {
    if (turn?.discount_type && turn.discount_type !== "none") {
        return {
            type: turn.discount_type,
            value: Number(turn.discount_value || 0),
            label: turn.discount_label || "",
        };
    }

    return getCheckinDiscountForTurn(turn) || {
        type: "none",
        value: 0,
        label: "",
    };
}

function fillCheckoutFormFromTurn(turn) {
    if (!turn) return;

    const linkedAppointment = turn.appointment_id
        ? appointments.find((appt) => Number(appt.id) === Number(turn.appointment_id))
        : getAppointmentForTurn(turn);
    const discount = getDiscountForTurn(turn);

    if (checkoutCustomerName) checkoutCustomerName.value = turn.customer_name || "";
    if (checkoutCustomerPhone) checkoutCustomerPhone.value = turn.customer_phone || "";
    if (checkoutTechnicianId) checkoutTechnicianId.value = turn.technician_id ? String(turn.technician_id) : "";
    if (checkoutTechnicianName) checkoutTechnicianName.value = getTechnicianNameById(turn.technician_id);
    if (checkoutTurnId) checkoutTurnId.value = turn.id || "";
    if (checkoutAppointmentId) checkoutAppointmentId.value = linkedAppointment?.id || "";
    if (checkoutServiceName) checkoutServiceName.value = turn.service_name || "";
    if (checkoutPaymentMethod) checkoutPaymentMethod.value = "cash";
    if (checkoutDiscountType) checkoutDiscountType.value = discount.type || "none";
    if (checkoutDiscountValue) checkoutDiscountValue.value = Number(discount.value || 0);
    if (checkoutTip) checkoutTip.value = 0;
    if (checkoutSubtotal) checkoutSubtotal.value = 0;
    if (checkoutDiscountDisplay) checkoutDiscountDisplay.dataset.discountLabel = discount.label || "";

    updateCheckoutSummary();
    showView("checkout");
    checkoutForm?.scrollIntoView({ behavior: "smooth", block: "start" });
}

// Renders assigned/in-service customers ready to checkout.
function renderCheckoutReadyList() {
    if (!checkoutReadyList) return;

    const inServiceTurns = todayTurns.filter((t) => ["assigned", "in_service"].includes(t.status));

    if (!inServiceTurns.length) {
        checkoutReadyList.innerHTML = `
      <div class="tech-card">
        <div class="tech-card-top">
          <div class="tech-main-info">
            <div class="tech-title-row"><h4>No customers ready for checkout</h4></div>
            <p class="tech-subtext">Assigned customers will appear here after auto assign.</p>
          </div>
        </div>
      </div>`;
        return;
    }

    checkoutReadyList.innerHTML = inServiceTurns.map((turn) => {
        const techName = getTechnicianNameById(turn.technician_id);
        const isAssigned = turn.status === "assigned";
        return `
      <div class="tech-card dispatch-card">
        <div class="tech-card-top">
          <div class="tech-avatar-wrap">
            <div class="tech-avatar-fallback">${escapeHtml(getInitials(turn.customer_name))}</div>
          </div>
          <div class="tech-main-info">
            <div class="tech-title-row">
              <h4>${escapeHtml(turn.customer_name)}</h4>
              <span class="status-chip ${isAssigned ? "dispatch-status-assigned" : "dispatch-status-in_service"}">${isAssigned ? "assigned" : "in service"}</span>
            </div>
            <p class="tech-subtext">Phone: ${escapeHtml(turn.customer_phone || "-")}</p>
          </div>
        </div>
        <div class="tech-meta">
          <p><strong>Technician:</strong> ${escapeHtml(techName)}</p>
          <p><strong>Service:</strong> ${escapeHtml(turn.service_name || "-")}</p>
        </div>
        <div class="dispatch-card-center">
          <button class="mini-btn checkout-select-btn" type="button" data-turn-id="${turn.id}">
            💅 Select for Checkout
          </button>
          ${isAssigned ? `<button class="mini-btn checkout-start-btn" type="button" data-turn-id="${turn.id}">
            Start service
          </button>` : ""}
          <button class="mini-btn checkout-reassign-btn" type="button" data-turn-id="${turn.id}">
            ${UI_ICONS.user}Reassign
          </button>
          <button class="mini-btn danger-mini-btn checkout-cancel-btn" type="button" data-turn-id="${turn.id}">
            Cancel
          </button>
        </div>
      </div>`;
    }).join("");

    checkoutReadyList.querySelectorAll(".checkout-select-btn").forEach((btn) => {
        btn.addEventListener("click", () => {
            const turnId = Number(btn.dataset.turnId);
            const turn = todayTurns.find((item) => Number(item.id) === turnId);
            if (!turn) {
                showCuteNotification("Could not load this customer for checkout.", "Oops");
                return;
            }
            fillCheckoutFormFromTurn(turn);
            showCuteNotification("Customer loaded into checkout.");
        });
    });

    checkoutReadyList.querySelectorAll(".checkout-reassign-btn").forEach((btn) => {
        btn.addEventListener("click", () => openReassignModal(Number(btn.dataset.turnId)));
    });

    checkoutReadyList.querySelectorAll(".checkout-start-btn").forEach((btn) => {
        btn.addEventListener("click", () => startCustomerService(Number(btn.dataset.turnId)));
    });

    checkoutReadyList.querySelectorAll(".checkout-cancel-btn").forEach((btn) => {
        btn.addEventListener("click", () => cancelCustomerTurn(Number(btn.dataset.turnId)));
    });
}

// Reloads everything the turn buttons change, so every screen shows the new state.
async function refreshTurnViews() {
    await loadTodayTurns();
    await loadLiveCheckinQueue();
    renderCheckoutReadyList();
    renderCalendar();
}

// "Start service": assigned -> in service (sets the start time; the calendar block turns "In Service").
async function startCustomerService(turnId) {
    try {
        await fetchJson(`${API_BASE}/turns/${turnId}/start`, {
            method: "PUT",
            body: JSON.stringify({})
        });
        await refreshTurnViews();
        showCuteNotification("Service started.");
    } catch (error) {
        await refreshTurnViews();
        showCuteNotification(error.message || "Failed to start service.", "Oops");
    }
}

// "Cancel": the customer leaves the checkout list and the technician is free again.
// A cancelled turn is final, and it closes that visit: the customer does not return to the waiting queue.
async function cancelCustomerTurn(turnId) {
    const turn = todayTurns.find((item) => Number(item.id) === Number(turnId));
    const name = turn ? turn.customer_name : "this customer";

    const confirmed = await showCuteConfirm(
        `Cancel ${name}'s turn? ${name} will leave the checkout list and the technician will be free again.`,
        "Please Confirm"
    );
    if (!confirmed) return;

    try {
        await fetchJson(`${API_BASE}/turns/${turnId}/status`, {
            method: "PUT",
            body: JSON.stringify({ status: "cancelled" })
        });

        // A cancelled turn cannot be checked out, so clear the form if this customer was loaded into it.
        if (checkoutTurnId?.value && Number(checkoutTurnId.value) === Number(turnId)) {
            resetCheckoutForm();
        }

        await refreshTurnViews();
        showCuteNotification("Turn cancelled.");
    } catch (error) {
        await refreshTurnViews();
        showCuteNotification(error.message || "Failed to cancel turn.", "Oops");
    }
}
