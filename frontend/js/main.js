document.querySelectorAll("[data-icon]").forEach((el) => {
    el.innerHTML = UI_ICONS[el.dataset.icon] || "";
});

navInventory?.addEventListener("click", async () => {
    if (!(await requireOwner())) return;
    await renderInventory();
    showView("inventory");
});

navCheckout?.addEventListener("click", async () => {
    await loadTechniciansRaw();
    await loadAppointments();
    await loadTodayTurns();
    resetCheckoutForm();
    updateCheckoutSummary();
    renderCheckoutReadyList();
    showView("checkout");
});

navCustomerList?.addEventListener("click", async () => {
    // The screen always opens. If loading its data fails (for example an outdated file), the error is
    // shown on screen instead of the button silently doing nothing.
    try {
        setupIncomeDateDefaults();
        resetHistoryView();
        await loadTechniciansRaw();
        await loadTodayTurns();
        await loadCheckoutHistory();
        await loadLiveCheckinQueue();
        renderCheckoutHistoryList();
    } catch (error) {
        console.error("Could not load the Customer List:", error);
        showCuteNotification(error.message || "Could not load the Customer List.", "Oops");
    }

    showView("customerList");
});

navTechnician?.addEventListener("click", async () => {
    if (!(await requireOwner())) return;
    await loadTechnicians();
    renderScheduleBoard();
    showView("technician");
});

navAppointment?.addEventListener("click", async () => {
    await loadTechniciansRaw();
    populateAppointmentTechnicianDropdown();
    resetAppointmentForm();
    showView("appointment");
});

navTechIncome?.addEventListener("click", async () => {
    if (!(await requireOwner())) return;
    setupIncomeDateDefaults();
    await loadTechniciansRaw();
    populateTechIncomeTechnicianDropdown();
    await loadTechIncome();
    showView("techIncome");
});

navSalonIncome?.addEventListener("click", async () => {
    if (!(await requireOwner())) return;
    setupIncomeDateDefaults();
    await loadSalonIncome();
    showView("salonIncome");
});

loadTechIncomeBtn?.addEventListener("click", loadTechIncome);

loadTechIncomeRangeBtn?.addEventListener("click", loadTechIncomeRange);

loadSalonIncomeBtn?.addEventListener("click", loadSalonIncome);

loadSaleHistoryRangeBtn?.addEventListener("click", loadSaleHistoryRange);

checkoutHistoryAllBtn?.addEventListener("click", loadAllCheckoutHistory);

techIncomeRangeType?.addEventListener("change", () => setupRangeInputs(techIncomeRangeType, techIncomeRangeStart, techIncomeRangeEnd));

saleHistoryRangeType?.addEventListener("change", () => setupRangeInputs(saleHistoryRangeType, saleHistoryRangeStart, saleHistoryRangeEnd));

const OWNER_VIEWS = ["technicianView", "inventoryView", "techIncomeView", "salonIncomeView"];

let lastActivity = Date.now();

["click", "keydown", "mousemove", "touchstart"].forEach((evt) => {
    document.addEventListener(evt, () => {
        lastActivity = Date.now();
    });
});

setInterval(() => {
    const onOwnerPage = OWNER_VIEWS.some((id) =>
        document.getElementById(id)?.classList.contains("active-view")
    );
    if (onOwnerPage && Date.now() - lastActivity > 2 * 60 * 1000) {
        showView("calendar");
    }
}, 10000);

document.querySelectorAll(".back-btn").forEach((btn) => {
    btn.addEventListener("click", async () => {
        await loadAll();
        showView("calendar");
    });
});

inventoryForm?.addEventListener("submit", async (e) => {
    e.preventDefault();

    // low_stock_level is not sent: the backend uses its default (3) for new items and
    // leaves an existing item's level unchanged when editing.
    const itemData = {
        item_name: inventoryItemName.value.trim(),
        category: inventoryCategory.value,
        supplier: inventorySupplier.value.trim() || null,
        quantity: Number(inventoryQuantity.value || 0),
        unit_price: Number(inventoryUnitPrice.value || 0),
        purchase_date: displayDateToISO(inventoryPurchaseDate.value) || null
    };

    if (!itemData.item_name || !itemData.category) {
        showCuteNotification("Please fill in item name and category.", "Oops");
        return;
    }

    if (itemData.purchase_date && !isValidDateText(itemData.purchase_date)) {
        showCuteNotification("Enter a valid purchase date with a 4-number year.", "Notice");
        return;
    }

    try {
        if (inventoryIdInput.value) {
            await fetchJson(`${API_BASE}/inventory/${inventoryIdInput.value}`, {
                method: "PUT",
                body: JSON.stringify(itemData)
            });
            showCuteNotification("Inventory item updated successfully.");
        } else {
            await fetchJson(`${API_BASE}/inventory`, {
                method: "POST",
                body: JSON.stringify(itemData)
            });
            showCuteNotification("Inventory item added successfully.");
        }

        resetInventoryForm();
        await renderInventory();
    } catch (error) {
        showCuteNotification(error.message || "Failed to save inventory item.", "Oops");
    }
});

cancelInventoryEditBtn?.addEventListener("click", () => {
    resetInventoryForm();
});

inventorySearch?.addEventListener("input", renderInventoryTable);

inventoryCategoryFilter?.addEventListener("change", renderInventoryTable);

inventoryStockFilter?.addEventListener("change", renderInventoryTable);

[
    checkoutSubtotal,
    checkoutDiscountType,
    checkoutDiscountValue,
    checkoutTip
].forEach((element) => {
    element?.addEventListener("input", updateCheckoutSummary);
    element?.addEventListener("change", updateCheckoutSummary);
});

checkoutForm?.addEventListener("submit", async (e) => {
    e.preventDefault();

    const customerName = checkoutCustomerName?.value.trim();
    const customerPhone = checkoutCustomerPhone?.value.trim();
    const serviceName = checkoutServiceName?.value.trim();
    const subtotal = Number(checkoutSubtotal?.value || 0);

    if (!customerName) {
        showCuteNotification("Customer name is required.", "Notice");
        return;
    }

    if (!serviceName) {
        showCuteNotification("Service name is required.", "Notice");
        return;
    }

    if (subtotal <= 0) {
        showCuteNotification("Please enter a subtotal greater than 0.", "Notice");
        return;
    }

    const calc = getCheckoutCalculation();

    // Same discount rules the backend enforces (it would answer with an error anyway).
    if (calc.discountType === "percent" && calc.discountValue > 100) {
        showCuteNotification("A percent discount cannot be more than 100.", "Notice");
        return;
    }

    if (calc.discountType === "fixed" && calc.discountValue > calc.gross) {
        showCuteNotification("The discount cannot be more than the subtotal.", "Notice");
        return;
    }

    // Only the inputs are sent. The backend calculates the 60% split, discount amount,
    // salon revenue, and totals itself.
    const payload = {
        customer_name: customerName,
        customer_phone: customerPhone || null,
        technician_id: checkoutTechnicianId?.value ? Number(checkoutTechnicianId.value) : null,
        turn_id: checkoutTurnId?.value ? Number(checkoutTurnId.value) : null,
        appointment_id: checkoutAppointmentId?.value ? Number(checkoutAppointmentId.value) : null,
        payment_method: checkoutPaymentMethod?.value || "cash",
        service_name: serviceName,
        subtotal: calc.gross,
        discount_type: calc.discountType,
        discount_value: calc.discountValue,
        tip_amount: calc.tip,
        note: null
    };

    try {
        await fetchJson(`${API_BASE}/checkouts`, {
            method: "POST",
            body: JSON.stringify(payload)
        });

        showCuteNotification("Checkout completed successfully.");

        resetCheckoutForm();
        await refreshCheckoutRelatedViews();
    } catch (error) {
        showCuteNotification(error.message || "Failed to complete checkout.", "Oops");
    }
});

checkoutCustomerPhone?.addEventListener("input", (e) => {
    e.target.value = formatPhoneInput(e.target.value);
});

cuteNotificationBtn?.addEventListener("click", hideCuteNotification);

cuteNotification?.addEventListener("click", (e) => {
    if (e.target === cuteNotification) hideCuteNotification();
});

cuteConfirmOk?.addEventListener("click", () => closeCuteConfirm(true));

cuteConfirmCancel?.addEventListener("click", () => closeCuteConfirm(false));

cuteConfirm?.addEventListener("click", (e) => {
    if (e.target === cuteConfirm) closeCuteConfirm(false);
});

appointmentCloseBtn?.addEventListener("click", closeAppointmentModal);

appointmentModal?.addEventListener("click", (e) => {
    if (e.target === appointmentModal) closeAppointmentModal();
});

appointmentEditBtn?.addEventListener("click", () => {
    if (!activeAppointment) {
        showCuteNotification("Could not load appointment for editing.", "Oops");
        return;
    }

    const apptToEdit = { ...activeAppointment };

    closeAppointmentModal();
    fillAppointmentForm(apptToEdit);
    showView("appointment");
    window.scrollTo({ top: 0, behavior: "smooth" });
});

appointmentDeleteBtn?.addEventListener("click", async () => {
    if (!activeAppointment) {
        showCuteNotification("Could not find appointment to delete.", "Oops");
        return;
    }

    const apptId = activeAppointment.id;

    closeAppointmentModal();

    const confirmed = await showCuteConfirm(
        "Delete this appointment?",
        "Please Confirm"
    );

    if (!confirmed) return;

    try {
        await fetchJson(`${API_BASE}/appointments/${apptId}`, {
            method: "DELETE",
        });

        activeAppointment = null;
        showCuteNotification("Appointment deleted successfully.");
        await loadAll();
        showView("calendar");
    } catch (error) {
        showCuteNotification(error.message || "Failed to delete appointment.", "Oops");
    }
});

preferredTechCancelBtn?.addEventListener("click", closePreferredTechModal);

preferredTechModal?.addEventListener("click", (e) => {
    if (e.target === preferredTechModal) closePreferredTechModal();
});

preferredTechConfirmBtn?.addEventListener("click", async () => {
    const selectedTechId = Number(preferredTechSelect?.value || 0);

    if (!selectedTechId) {
        showCuteNotification("Please select a technician.", "Notice");
        return;
    }

    if (preferredTechModalMode === "reassign") {
        await submitReassignment(selectedTechId);
    } else {
        await submitPreferredAssignment(selectedTechId);
    }
});

techStartDate?.addEventListener("input", () => validateTechStartDate(false));

techStartDate?.addEventListener("change", () => validateTechStartDate(false));

techDateOffStart?.addEventListener("input", applyDateOffStatus);

techDateOffStart?.addEventListener("change", applyDateOffStatus);

techDateOffEnd?.addEventListener("input", applyDateOffStatus);

techDateOffEnd?.addEventListener("change", applyDateOffStatus);

async function loadAll() {
    installFourDigitYearGuard();
    await checkApi();

    try {
        await resetTemporaryUnavailableTechs();
        syncDefaultSpecialtiesToFilter();
        await loadTechnicians();
        await loadAppointments();
        await loadTodayTurns();
        await loadCheckoutHistory();
        await loadLiveCheckinQueue();
        renderCalendar();
    } catch (error) {
        calendarWrapper.innerHTML = `<div class="empty-state">Could not load backend data. Make sure FastAPI is running.</div>`;
    }
}

technicianForm?.addEventListener("submit", async (e) => {
    e.preventDefault();

    if (!validateTechStartDate(true)) {
        return;
    }

    updateScheduleFromControls();

    const fullName = techName.value.trim();
    const phoneRaw = techPhone.value.trim();
    const selectedSpecialties = getSelectedSpecialties().trim();

    if (!fullName) {
        showCuteNotification("Technician name is required.", "Notice");
        return;
    }

    if (!selectedSpecialties) {
        showCuteNotification("Please select at least one specialty.", "Notice");
        return;
    }

    const digits = phoneRaw.replace(/\D/g, "");
    if (phoneRaw && digits.length !== 10) {
        showCuteNotification("Phone number must contain 10 digits.", "Notice");
        return;
    }

    const hasDateOffStart = Boolean(techDateOffStart?.value);
    const hasDateOffEnd = Boolean(techDateOffEnd?.value);
    if (hasDateOffStart !== hasDateOffEnd) {
        showCuteNotification("Please enter both Date Off start and end.", "Notice");
        return;
    }

    if (hasDateOffStart && (!isValidDateText(techDateOffStart.value) || !isValidDateText(techDateOffEnd.value))) {
        showCuteNotification("Date Off must use MM-DD-YYYY.", "Notice");
        return;
    }

    const dateOffAvailability = getDateOffAvailability(techDateOffStart?.value, techDateOffEnd?.value);
    if (dateOffAvailability && displayDateToISO(techDateOffStart.value) > displayDateToISO(techDateOffEnd.value)) {
        showCuteNotification("Date Off end must be after the start date.", "Notice");
        return;
    }

    if (dateOffAvailability) {
        techStatus.value = "unavailable";
    }

    const payload = {
        full_name: fullName,
        phone: phoneRaw || null,
        specialties: selectedSpecialties,
        start_date: displayDateToISO(techStartDate.value) || null,
        status: techStatus.value,
        availability: dateOffAvailability || (techStatus.value === "active" ? "available today" : "off today"),
        work_schedule: techSchedule.value.trim() || null
    };

    const techId = techIdInput.value;

    try {
        if (techId) {
            await fetchJson(`${API_BASE}/technicians/${techId}`, {
                method: "PUT",
                body: JSON.stringify(payload),
            });
            showCuteNotification("Technician updated successfully.");
        } else {
            await fetchJson(`${API_BASE}/technicians`, {
                method: "POST",
                body: JSON.stringify(payload),
            });
            showCuteNotification("Technician saved successfully.");
        }

        resetTechnicianForm();
        await loadAll();
    } catch (error) {
        showCuteNotification(error.message || "Failed to save technician.", "Oops");
    }
});

appointmentForm?.addEventListener("submit", async (e) => {
    e.preventDefault();

    const customerName = customerNameInput.value.trim();
    const customerPhone = customerPhoneInput.value.trim();
    const appointmentTime = appointmentTimeInput.value;
    const appointmentTimeApiValue = displayDateTimeToApi(appointmentTime);
    const phoneDigits = customerPhone.replace(/\D/g, "");
    const selectedServices = getSelectedAppointmentServices();

    if (!customerName) {
        showCuteNotification("Customer name is required.", "Notice");
        return;
    }

    if (phoneDigits.length !== 10) {
        showCuteNotification("Customer phone number must contain 10 digits.", "Notice");
        return;
    }

    if (!selectedServices) {
        showCuteNotification("Please select at least one service.", "Notice");
        return;
    }

    if (!appointmentTime) {
        showCuteNotification("Appointment date and time is required.", "Notice");
        return;
    }

    if (!appointmentTimeApiValue) {
        showCuteNotification("Appointment date and time must use MM-DD-YYYY HH:MM.", "Notice");
        return;
    }

    // service_name is not sent: the backend copies it from service_category.
    const payload = {
        customer_name: customerName,
        customer_phone: customerPhone,
        service_category: selectedServices,
        people_count: Number(appointmentPeopleCount?.value || 1),
        appointment_time: appointmentTimeApiValue,
        special_requests: specialRequests.value.trim() || null,
        allergies: allergies.value.trim() || null,
        preferred_technician_id: preferredTechnician.value ? Number(preferredTechnician.value) : null,
    };

    const appointmentId = appointmentIdInput.value;

    try {
        if (appointmentId) {
            await fetchJson(`${API_BASE}/appointments/${appointmentId}`, {
                method: "PUT",
                body: JSON.stringify(payload),
            });
            showCuteNotification("Appointment updated successfully.");
        } else {
            await fetchJson(`${API_BASE}/appointments`, {
                method: "POST",
                body: JSON.stringify(payload),
            });
            showCuteNotification("Appointment created successfully.");
        }

        activeAppointment = null;
        resetAppointmentForm();
        await loadAll();
        showView("calendar");
    } catch (error) {
        showCuteNotification(error.message || "Failed to save appointment.", "Oops");
    }
});

todayBtn?.addEventListener("click", () => {
    selectedDate = new Date();
    renderCalendar();
});

prevDayBtn?.addEventListener("click", () => {
    const d = new Date(selectedDate);
    d.setDate(d.getDate() - 1);
    selectedDate = d;
    renderCalendar();
});

nextDayBtn?.addEventListener("click", () => {
    const d = new Date(selectedDate);
    d.setDate(d.getDate() + 1);
    selectedDate = d;
    renderCalendar();
});

cancelEditBtn?.addEventListener("click", () => {
    resetTechnicianForm();
});

cancelAppointmentEditBtn?.addEventListener("click", () => {
    resetAppointmentForm();
});

techPhone?.addEventListener("input", (e) => {
    e.target.value = formatPhoneInput(e.target.value);
});

customerPhoneInput?.addEventListener("input", (e) => {
    e.target.value = formatPhoneInput(e.target.value);
});

addSpecialtyBtn?.addEventListener("click", () => {
    const value = newSpecialtyInput.value.trim();
    if (!value) return;
    ensureSpecialtyExists(value, true);
    newSpecialtyInput.value = "";
});

deleteSpecialtyBtn?.addEventListener("click", () => {
    const checkedValues = Array.from(
        techSpecialties?.querySelectorAll('input[type="checkbox"]:checked') || []
    ).map((checkbox) => checkbox.value);

    if (!checkedValues.length) {
        showCuteNotification("Check the service groups you want to delete.", "Notice");
        return;
    }

    const deletedCount = checkedValues.reduce((count, value) => {
        return deleteSpecialtyByName(value) ? count + 1 : count;
    }, 0);

    if (newSpecialtyInput) newSpecialtyInput.value = "";
    syncDefaultSpecialtiesToFilter();
    showCuteNotification(`${deletedCount} service group${deletedCount === 1 ? "" : "s"} deleted.`);
});

newSpecialtyInput?.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
        e.preventDefault();
        addSpecialtyBtn.click();
    }
});

queueAutoAssignBtn?.addEventListener("click", async () => {
    await autoAssignAllWaitingCheckins();
});

[techSearch, techFilterSpecialty, techFilterStatus].forEach((element) => {
    element?.addEventListener("input", loadTechnicians);
    element?.addEventListener("change", loadTechnicians);
});

loadAll();

setInterval(async () => {
    if (customerListView.classList.contains("active-view")) {
        await loadTodayTurns();
        await loadCheckoutHistory();
    }
    await loadLiveCheckinQueue();
}, 5000);

setInterval(async () => {
    await resetTemporaryUnavailableTechs();
    await loadTodayTurns();
    await loadCheckoutHistory();
    await loadLiveCheckinQueue();
    if (calendarView.classList.contains("active-view")) {
        renderCalendar();
    }
}, 60000);

showView("calendar");