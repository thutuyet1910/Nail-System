// appointments.js: Appointment form and appointment details popup
// appointments.js: Appointment form and appointment details popup

function getSelectedAppointmentServices() {
    if (!appointmentServicesBox) return "";
    return Array.from(
        appointmentServicesBox.querySelectorAll('input[type="checkbox"]:checked')
    )
        .map((checkbox) => checkbox.value)
        .join(", ");
}

function setSelectedAppointmentServices(value) {
    if (!appointmentServicesBox) return;

    appointmentServicesBox
        .querySelectorAll('input[type="checkbox"]')
        .forEach((checkbox) => {
            checkbox.checked = false;
        });

    const selectedValues = (value || "")
        .split(",")
        .map((v) => v.trim().toLowerCase())
        .filter(Boolean);

    appointmentServicesBox
        .querySelectorAll('input[type="checkbox"]')
        .forEach((checkbox) => {
            if (selectedValues.includes(checkbox.value.trim().toLowerCase())) {
                checkbox.checked = true;
            }
        });
}

function openAppointmentModal(appt) {
    activeAppointment = appt;

    const preferredTech = techniciansRaw.find((t) => t.id === appt.preferred_technician_id);

    const dt = new Date(appt.appointment_time);
    const prettyDate = dt.toLocaleString([], {
        weekday: "short",
        month: "short",
        day: "2-digit",
        year: "numeric",
        hour: "numeric",
        minute: "2-digit",
    });

    appointmentModalContent.innerHTML = `
    <p><strong>Customer:</strong> ${escapeHtml(appt.customer_name || "-")}</p>
    <p><strong>Phone:</strong> ${escapeHtml(appt.customer_phone || "-")}</p>
    <p><strong>Service Category:</strong> ${escapeHtml(appt.service_category || appt.service_name || "-")}</p>
    <p><strong>Number of People:</strong> ${appt.people_count || 1}</p>
    <p><strong>Date & Time:</strong> ${prettyDate}</p>
    <p><strong>Preferred Technician:</strong> ${escapeHtml(preferredTech?.full_name || "-")}</p>
    <p><strong>Special Requests:</strong> ${escapeHtml(appt.special_requests || "-")}</p>
    <p><strong>Allergies:</strong> ${escapeHtml(appt.allergies || "-")}</p>
  `;

    appointmentModal.classList.remove("hidden");
}

function closeAppointmentModal() {
    appointmentModal.classList.add("hidden");
}

// Finds TODAY's appointment for a customer's turn so the checkout can be linked to it.
// Only today's appointments are linked: the backend will not let an appointment that
// has a checkout be deleted, so linking an old or future appointment would lock it.
function getAppointmentForTurn(turn) {
    if (!turn) return null;

    const turnName = (turn.customer_name || "").trim().toLowerCase();
    const turnPhone = (turn.customer_phone || "").replace(/\D/g, "");
    const turnService = normalizeServiceForMatch(turn.service_name);
    const today = new Date();

    return appointments.find((appt) => {
        if (!sameDay(new Date(appt.appointment_time), today)) return false;

        const apptName = (appt.customer_name || "").trim().toLowerCase();
        const apptPhone = (appt.customer_phone || "").replace(/\D/g, "");
        const apptService = normalizeServiceForMatch(appt.service_category || appt.service_name || "");

        const sameCustomer =
            (turnPhone && apptPhone && turnPhone === apptPhone) ||
            (turnName && apptName && turnName === apptName);

        const sameService = !turnService || !apptService || turnService === apptService;

        return sameCustomer && sameService;
    }) || null;
}

// Finds today's appointment for a customer who has just checked in (null if they have none).
// If they have several today, the one closest to the time they checked in wins.
// Used by Auto Assign to give the customer the technician they booked.
function getAppointmentForCheckin(item) {
    if (!item) return null;

    const today = new Date();
    const matches = appointments.filter((appt) =>
        sameDay(new Date(appt.appointment_time), today) &&
        isSameCustomer(item.full_name, item.phone_number, appt.customer_name, appt.customer_phone)
    );
    if (!matches.length) return null;

    const checkinMs = getCheckinTimeMs(item);
    const distance = (appt) =>
        checkinMs === null
            ? new Date(appt.appointment_time).getTime()
            : Math.abs(new Date(appt.appointment_time).getTime() - checkinMs);

    return matches.sort((a, b) => distance(a) - distance(b))[0];
}

function resetAppointmentForm() {
    appointmentForm.reset();
    appointmentIdInput.value = "";
    appointmentFormTitle.textContent = "Appointment Form";
    saveAppointmentBtn.textContent = "Save Appointment";
    cancelAppointmentEditBtn.classList.add("hidden");
    setSelectedAppointmentServices("");
    if (appointmentPeopleCount) appointmentPeopleCount.value = 1;
    activeAppointment = null;
}

function fillAppointmentForm(appt) {
    appointmentIdInput.value = appt.id || "";
    customerNameInput.value = appt.customer_name || "";
    customerPhoneInput.value = appt.customer_phone || "";
    setSelectedAppointmentServices(appt.service_category || appt.service_name || "");
    appointmentTimeInput.value = toDatetimeLocalValue(appt.appointment_time);
    preferredTechnician.value = appt.preferred_technician_id || "";
    if (appointmentPeopleCount) appointmentPeopleCount.value = appt.people_count || 1;
    specialRequests.value = appt.special_requests || "";
    allergies.value = appt.allergies || "";

    appointmentFormTitle.textContent = "Edit Appointment";
    saveAppointmentBtn.textContent = "Update Appointment";
    cancelAppointmentEditBtn.classList.remove("hidden");
}

function populateAppointmentTechnicianDropdown() {
    preferredTechnician.innerHTML = `<option value="">Select preferred technician</option>`;

    techniciansRaw.forEach((tech) => {
        const option2 = document.createElement("option");
        option2.value = tech.id;
        option2.textContent = tech.full_name;
        preferredTechnician.appendChild(option2);
    });
}

async function loadAppointments() {
    appointments = await fetchJson(`${API_BASE}/appointments`);
}