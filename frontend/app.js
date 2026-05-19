const API_BASE = "http://127.0.0.1:8001";
const CHECKIN_API_BASE = "http://127.0.0.1:8000";

const calendarView = document.getElementById("calendarView");
const customerListView = document.getElementById("customerListView");
const technicianView = document.getElementById("technicianView");
const appointmentView = document.getElementById("appointmentView");
const inventoryView = document.getElementById("inventoryView");
const checkoutView = document.getElementById("checkoutView");
const techIncomeView = document.getElementById("techIncomeView");
const salonIncomeView = document.getElementById("salonIncomeView");


const navCustomerList = document.getElementById("navCustomerList");
const navTechnician = document.getElementById("navTechnician");
const navAppointment = document.getElementById("navAppointment");
const navInventory = document.getElementById("navInventory");
const navCheckout = document.getElementById("navCheckout");
const navTechIncome = document.getElementById("navTechIncome");
const navSalonIncome = document.getElementById("navSalonIncome");

const preferredTechModal = document.getElementById("preferredTechModal");
const preferredTechSelect = document.getElementById("preferredTechSelect");
const preferredTechCustomerText = document.getElementById("preferredTechCustomerText");
const preferredTechCancelBtn = document.getElementById("preferredTechCancelBtn");
const preferredTechConfirmBtn = document.getElementById("preferredTechConfirmBtn");

const todayBtn = document.getElementById("todayBtn");
const prevDayBtn = document.getElementById("prevDayBtn");
const nextDayBtn = document.getElementById("nextDayBtn");
const dateLabel = document.getElementById("dateLabel");
const calendarWrapper = document.getElementById("calendarWrapper");

const cuteNotification = document.getElementById("cuteNotification");
const cuteNotificationTitle = document.getElementById("cuteNotificationTitle");
const cuteNotificationMessage = document.getElementById("cuteNotificationMessage");
const cuteNotificationBtn = document.getElementById("cuteNotificationBtn");

const cuteConfirm = document.getElementById("cuteConfirm");
const cuteConfirmTitle = document.getElementById("cuteConfirmTitle");
const cuteConfirmMessage = document.getElementById("cuteConfirmMessage");
const cuteConfirmOk = document.getElementById("cuteConfirmOk");
const cuteConfirmCancel = document.getElementById("cuteConfirmCancel");

const inventoryForm = document.getElementById("inventoryForm");
const inventoryFormTitle = document.getElementById("inventoryFormTitle");
const cancelInventoryEditBtn = document.getElementById("cancelInventoryEditBtn");
const saveInventoryBtn = document.getElementById("saveInventoryBtn");

const inventoryIdInput = document.getElementById("inventory_id");
const inventoryItemName = document.getElementById("inventory_item_name");
const inventoryCategory = document.getElementById("inventory_category");
const inventorySupplier = document.getElementById("inventory_supplier");
const inventoryQuantity = document.getElementById("inventory_quantity");
const inventoryUnitPrice = document.getElementById("inventory_unit_price");
const inventoryPurchaseDate = document.getElementById("inventory_purchase_date");

const inventorySearch = document.getElementById("inventorySearch");
const inventoryCategoryFilter = document.getElementById("inventoryCategoryFilter");
const inventoryStockFilter = document.getElementById("inventoryStockFilter");

const inventoryTableBody = document.getElementById("inventoryTableBody");

const inventoryTotalValue = document.getElementById("inventoryTotalValue");
const inventoryWeeklyExpense = document.getElementById("inventoryWeeklyExpense");
const inventoryMonthlyExpense = document.getElementById("inventoryMonthlyExpense");
const inventoryYearlyExpense = document.getElementById("inventoryYearlyExpense");
const inventoryLowStockCount = document.getElementById("inventoryLowStockCount");

const checkoutForm = document.getElementById("checkoutForm");
const checkoutFormTitle = document.getElementById("checkoutFormTitle");
const cancelCheckoutEditBtn = document.getElementById("cancelCheckoutEditBtn");
const saveCheckoutBtn = document.getElementById("saveCheckoutBtn");

const checkoutIdInput = document.getElementById("checkout_id");
const checkoutCustomerName = document.getElementById("checkout_customer_name");
const checkoutCustomerPhone = document.getElementById("checkout_customer_phone");
const checkoutTurnId = document.getElementById("checkout_turn_id");
const checkoutAppointmentId = document.getElementById("checkout_appointment_id");
const checkoutPaymentMethod = document.getElementById("checkout_payment_method");
const checkoutTechnicianId = document.getElementById("checkout_technician_id");
const checkoutTechnicianName = document.getElementById("checkout_technician_name");

const checkoutServiceName = document.getElementById("checkout_service_name");
const checkoutSubtotal = document.getElementById("checkout_subtotal");
const checkoutDiscountType = document.getElementById("checkout_discount_type");
const checkoutDiscountValue = document.getElementById("checkout_discount_value");
const checkoutDiscountPaidBy = document.getElementById("checkout_discount_paid_by");
const checkoutTip = document.getElementById("checkout_tip");

const checkoutGross = document.getElementById("checkoutGross");
const checkoutDiscount = document.getElementById("checkoutDiscount");
const checkoutNet = document.getElementById("checkoutNet");
const checkoutTechShare = document.getElementById("checkoutTechShare");
const checkoutSalonShare = document.getElementById("checkoutSalonShare");
const checkoutSalonActual = document.getElementById("checkoutSalonActual");
const checkoutTechTotal = document.getElementById("checkoutTechTotal");
const checkoutCustomerPays = document.getElementById("checkoutCustomerPays");
const checkoutTipSummary = document.getElementById("checkoutTipSummary");
const checkoutDiscountDisplay = document.getElementById("checkoutDiscountDisplay");
const checkoutReadyList = document.getElementById("checkoutReadyList");

const techIncomeDate = document.getElementById("techIncomeDate");
const techIncomeTechnician = document.getElementById("techIncomeTechnician");
const loadTechIncomeBtn = document.getElementById("loadTechIncomeBtn");
const techIncomeContent = document.getElementById("techIncomeContent");
const techIncomeRangeType = document.getElementById("techIncomeRangeType");
const techIncomeRangeStart = document.getElementById("techIncomeRangeStart");
const techIncomeRangeEnd = document.getElementById("techIncomeRangeEnd");
const loadTechIncomeRangeBtn = document.getElementById("loadTechIncomeRangeBtn");
const techIncomeRangeContent = document.getElementById("techIncomeRangeContent");

const salonIncomeDate = document.getElementById("salonIncomeDate");
const loadSalonIncomeBtn = document.getElementById("loadSalonIncomeBtn");
const salonIncomeContent = document.getElementById("salonIncomeContent");
const salonDayBeforeDiscount = document.getElementById("salonDayBeforeDiscount");
const salonDayDiscount = document.getElementById("salonDayDiscount");
const salonDayAfterTech = document.getElementById("salonDayAfterTech");
const salonWeekAfterTech = document.getElementById("salonWeekAfterTech");
const salonYearAfterTech = document.getElementById("salonYearAfterTech");

const appointmentModal = document.getElementById("appointmentModal");
const appointmentModalContent = document.getElementById("appointmentModalContent");
const appointmentEditBtn = document.getElementById("appointmentEditBtn");
const appointmentDeleteBtn = document.getElementById("appointmentDeleteBtn");
const appointmentCloseBtn = document.getElementById("appointmentCloseBtn");

const apiDot = document.getElementById("api-dot");
const apiText = document.getElementById("api-text");

const technicianForm = document.getElementById("technicianForm");
const appointmentForm = document.getElementById("appointmentForm");
const technicianCards = document.getElementById("technicianCards");
const liveCheckinQueue = document.getElementById("liveCheckinQueue");
const checkoutHistoryList = document.getElementById("checkoutHistoryList");
const saleHistoryRangeType = document.getElementById("saleHistoryRangeType");
const saleHistoryRangeStart = document.getElementById("saleHistoryRangeStart");
const saleHistoryRangeEnd = document.getElementById("saleHistoryRangeEnd");
const loadSaleHistoryRangeBtn = document.getElementById("loadSaleHistoryRangeBtn");
const checkoutHistoryAllBtn = document.getElementById("checkoutHistoryAllBtn");
const queueAutoAssignBtn = document.getElementById("queueAutoAssignBtn");

const techIdInput = document.getElementById("tech_id");
const techName = document.getElementById("tech_name");
const techPhone = document.getElementById("tech_phone");
const techSkills = document.getElementById("tech_skills");
const techStartDate = document.getElementById("tech_start_date");
const techStatus = document.getElementById("tech_status");
const techAvailability = document.getElementById("tech_availability");
const techDateOffStart = document.getElementById("tech_date_off_start");
const techDateOffEnd = document.getElementById("tech_date_off_end");
const techSchedule = document.getElementById("tech_schedule"); // hidden input for storing schedule
const techSpecialties = document.getElementById("tech_specialties");

// ── Weekly Schedule Board ──────────────────────────────────────────────────────
const SCHEDULE_DAYS = [
    { key: "monday", label: "Monday", short: "Mon" },
    { key: "tuesday", label: "Tuesday", short: "Tue" },
    { key: "wednesday", label: "Wednesday", short: "Wed" },
    { key: "thursday", label: "Thursday", short: "Thu" },
    { key: "friday", label: "Friday", short: "Fri" },
    { key: "saturday", label: "Saturday", short: "Sat" },
    { key: "sunday", label: "Sunday", short: "Sun" },
];

const LEGACY_SCHEDULE_SLOT_TIMES = {
    "9am": "09:00",
    "10am": "10:00",
    "11am": "11:00",
    "12pm": "12:00",
    "1pm": "13:00",
    "2pm": "14:00",
    "3pm": "15:00",
    "4pm": "16:00",
    "5pm": "17:00",
    "6pm": "18:00",
    "7pm": "19:00",
    "8pm": "20:00",
};

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

function validateScheduleSelection() {
    updateScheduleFromControls();

    if (!techSchedule?.value) return true;

    return true;
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

function formatScheduleTime(value) {
    if (!value) return "";
    const [hourText, minuteText = "00"] = value.split(":");
    const hour = Number(hourText);
    if (Number.isNaN(hour)) return value;

    const suffix = hour >= 12 ? "PM" : "AM";
    const displayHour = hour % 12 || 12;
    return `${displayHour}:${minuteText} ${suffix}`;
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


const techSearch = document.getElementById("techSearch");
const techFilterSpecialty = document.getElementById("techFilterSpecialty");
const techFilterStatus = document.getElementById("techFilterStatus");
const cancelEditBtn = document.getElementById("cancelEditBtn");
const techFormTitle = document.getElementById("techFormTitle");
const saveTechBtn = document.getElementById("saveTechBtn");

const addSpecialtyBtn = document.getElementById("addSpecialtyBtn");
const deleteSpecialtyBtn = document.getElementById("deleteSpecialtyBtn");
const newSpecialtyInput = document.getElementById("new_specialty_input");

const appointmentIdInput = document.getElementById("appointment_id");
const appointmentFormTitle = document.getElementById("appointmentFormTitle");
const cancelAppointmentEditBtn = document.getElementById("cancelAppointmentEditBtn");
const saveAppointmentBtn = document.getElementById("saveAppointmentBtn");

const preferredTechnician = document.getElementById("preferred_technician_id");

const customerNameInput = document.getElementById("customer_name");
const customerPhoneInput = document.getElementById("customer_phone");
const appointmentTimeInput = document.getElementById("appointment_time");
const specialRequests = document.getElementById("special_requests");
const allergies = document.getElementById("allergies");
const appointmentServicesBox = document.getElementById("appointment_services");
const appointmentPeopleCount = document.getElementById("appointment_people_count");

let technicians = [];
let techniciansRaw = [];
let appointments = [];
let selectedDate = new Date();
let confirmResolve = null;
let activeAppointment = null;
let pendingPreferredCheckinItem = null;
let preferredTechModalMode = "assign";
let pendingReassignTurnId = null;
let currentReassignTechnicianId = null;
let liveCheckins = [];
let todayTurns = [];
let checkoutHistory = [];
let techIncomeDateSummaries = [];
let techIncomeDateLabel = "";
let techIncomeRangeSummaries = [];
let techIncomeRangeLabel = "";

let inventoryItems = [];

const DEFAULT_SPECIALTIES = [
    "Manicure / Pedicure",
    "Acrylic",
    "Gel",
    "Dip Powder",
    "Builder / Hard Gel",
    "Nail Art",
    "Nail Repair / Removal",
    "Waxing",
];
const DEFAULT_APPOINTMENT_SERVICES = [
    "Acrylic Full Set",
    "Acrylic Fill",
    "Gel Full Set",
    "Gel Fill",
    "Dip Powder",
    "Pink and White",
    "Ombre Nails",
    "Builder Gel",
    "Classic Manicure",
    "Gel Manicure",
    "Deluxe Manicure",
    "Classic Pedicure",
    "Deluxe Pedicure",
    "Spa Pedicure",
    "Jelly Pedicure",
    "Polish Change - Hands",
    "Polish Change - Feet",
    "Nail Repair",
    "Nail Removal",
    "French Tip",
    "Nail Art",
    "Chrome / Cat Eye",
    "Paraffin Treatment",
    "Waxing - Eyebrows",
    "Waxing - Lip",
    "Waxing - Chin",
];
const REMOVED_SPECIALTIES_STORAGE_KEY = "ownerRemovedSpecialties";
const TECH_UNAVAILABLE_TODAY_STORAGE_KEY = "ownerTechUnavailableToday";

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

function showView(view) {
    calendarView.classList.remove("active-view");
    customerListView.classList.remove("active-view");
    technicianView.classList.remove("active-view");
    appointmentView.classList.remove("active-view");
    inventoryView.classList.remove("active-view");
    checkoutView.classList.remove("active-view");
    techIncomeView.classList.remove("active-view");
    salonIncomeView.classList.remove("active-view");

    navCustomerList.classList.remove("active");
    navTechnician.classList.remove("active");
    navAppointment.classList.remove("active");
    navInventory.classList.remove("active");
    navCheckout.classList.remove("active");
    navTechIncome.classList.remove("active");
    navSalonIncome.classList.remove("active");

    if (view === "calendar") {
        calendarView.classList.add("active-view");
    } else if (view === "customerList") {
        customerListView.classList.add("active-view");
        navCustomerList.classList.add("active");
    } else if (view === "technician") {
        technicianView.classList.add("active-view");
        navTechnician.classList.add("active");
    } else if (view === "appointment") {
        appointmentView.classList.add("active-view");
        navAppointment.classList.add("active");
    } else if (view === "inventory") {
        inventoryView.classList.add("active-view");
        navInventory.classList.add("active");
    } else if (view === "checkout") {
        checkoutView.classList.add("active-view");
        navCheckout.classList.add("active");
    } else if (view === "techIncome") {
        techIncomeView.classList.add("active-view");
        navTechIncome.classList.add("active");
    } else if (view === "salonIncome") {
        salonIncomeView.classList.add("active-view");
        navSalonIncome.classList.add("active");
    }
}

navInventory?.addEventListener("click", async () => {
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
    setupIncomeDateDefaults();
    await loadTechniciansRaw();
    await loadTodayTurns();
    await loadCheckoutHistory();
    await loadLiveCheckinQueue();
    renderCheckoutHistoryList();
    showView("customerList");
});
navTechnician?.addEventListener("click", async () => {
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
    setupIncomeDateDefaults();
    await loadTechniciansRaw();
    populateTechIncomeTechnicianDropdown();
    await loadTechIncome();
    showView("techIncome");
});

navSalonIncome?.addEventListener("click", async () => {
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

document.querySelectorAll(".back-btn").forEach((btn) => {
    btn.addEventListener("click", async () => {
        await loadAll();
        showView("calendar");
    });
});


function formatMoney(value) {
    return `$${Number(value || 0).toFixed(2)}`;
}

function getLocalDateKey(value = new Date()) {
    return formatDateInputValue(value);
}

function limitDateYearValue(input) {
    if (!input?.value) return;
    const match = input.value.match(/^(\d{5,})(-\d{2}-\d{2}(?:T\d{2}:\d{2})?)$/);
    if (match) {
        input.value = `${match[1].slice(0, 4)}${match[2]}`;
    }
}

function formatMaskedDate(value) {
    const digits = String(value || "").replace(/\D/g, "").slice(0, 8);
    if (digits.length <= 2) return digits;
    if (digits.length <= 4) return `${digits.slice(0, 2)}-${digits.slice(2)}`;
    return `${digits.slice(0, 2)}-${digits.slice(2, 4)}-${digits.slice(4)}`;
}

function formatMaskedDateTime(value) {
    const digits = String(value || "").replace(/\D/g, "").slice(0, 12);
    const datePart = formatMaskedDate(digits.slice(0, 8));
    if (digits.length <= 8) return datePart;
    if (digits.length <= 10) return `${datePart} ${digits.slice(8)}`;
    return `${datePart} ${digits.slice(8, 10)}:${digits.slice(10)}`;
}

function formatMaskedYear(value) {
    return String(value || "").replace(/\D/g, "").slice(0, 4);
}

function hasFourDigitYear(value) {
    return /^\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2})?$/.test(value || "");
}

function displayDateToISO(value) {
    if (/^\d{4}-\d{2}-\d{2}$/.test(value || "")) return value;
    if (!/^\d{2}-\d{2}-\d{4}$/.test(value || "")) return "";
    const [monthText, dayText, yearText] = value.split("-");
    return `${yearText}-${monthText}-${dayText}`;
}

function isoToDisplayDate(value) {
    const isoValue = formatDateInputValue(value);
    if (!/^\d{4}-\d{2}-\d{2}$/.test(isoValue)) return "";
    const [year, month, day] = isoValue.split("-");
    return `${month}-${day}-${year}`;
}

function isValidISODate(value) {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(value || "")) return false;
    const [yearText, monthText, dayText] = value.split("-");
    const year = Number(yearText);
    const month = Number(monthText);
    const day = Number(dayText);
    const date = new Date(year, month - 1, day);
    return (
        date.getFullYear() === year &&
        date.getMonth() + 1 === month &&
        date.getDate() === day
    );
}

function isValidDateText(value) {
    return isValidISODate(displayDateToISO(value));
}

function displayDateTimeToApi(value) {
    const match = String(value || "").match(/^(\d{2}-\d{2}-\d{4})\s+(\d{2}):(\d{2})$/);
    if (!match) return "";
    const isoDate = displayDateToISO(match[1]);
    const hours = Number(match[2]);
    const minutes = Number(match[3]);
    if (!isValidISODate(isoDate) || hours > 23 || minutes > 59) return "";
    return `${isoDate}T${match[2]}:${match[3]}`;
}

function getDateOffAvailability(startDisplay, endDisplay) {
    const startISO = displayDateToISO(startDisplay);
    const endISO = displayDateToISO(endDisplay);
    if (!startISO || !endISO) return "";
    return `date off: ${startISO} to ${endISO}`;
}

function parseDateOffAvailability(value) {
    const match = String(value || "").match(/^date off:\s*(\d{4}-\d{2}-\d{2})\s+to\s+(\d{4}-\d{2}-\d{2})$/i);
    if (!match) {
        return { start: "", end: "" };
    }
    return {
        start: isoToDisplayDate(match[1]),
        end: isoToDisplayDate(match[2]),
    };
}

function applyDateOffStatus() {
    if (!techStatus || !techDateOffStart || !techDateOffEnd) return;
    if (isValidDateText(techDateOffStart.value) && isValidDateText(techDateOffEnd.value)) {
        techStatus.value = "unavailable";
    }
}

function isoDateTimeToDisplay(value) {
    if (!value) return "";
    const d = new Date(value);
    if (Number.isNaN(d.getTime())) return "";
    const dateText = isoToDisplayDate(d);
    const hours = String(d.getHours()).padStart(2, "0");
    const mins = String(d.getMinutes()).padStart(2, "0");
    return `${dateText} ${hours}:${mins}`;
}

function installFourDigitYearGuard() {
    document.querySelectorAll('input[data-date-mask="true"], input[data-year-mask="true"], input[data-datetime-mask="true"], input[type="date"], input[type="datetime-local"]').forEach((input) => {
        if (input.dataset.yearGuardInstalled === "true") return;
        input.dataset.yearGuardInstalled = "true";

        if (input.dataset.yearMask === "true" || input.dataset.dateMask === "true" || input.dataset.datetimeMask === "true") {
            input.type = "text";
            input.setAttribute("inputmode", "numeric");
            const applyMask = () => {
                const yearOnly = input.dataset.yearMask === "true";
                const dateTime = input.dataset.datetimeMask === "true";
                input.setAttribute("maxlength", yearOnly ? "4" : dateTime ? "16" : "10");
                input.value = yearOnly ? formatMaskedYear(input.value) : dateTime ? formatMaskedDateTime(input.value) : formatMaskedDate(input.value);
            };
            input.addEventListener("input", applyMask);
            input.addEventListener("change", applyMask);
            return;
        }

        input.setAttribute("maxlength", input.type === "datetime-local" ? "16" : "10");
        if (!input.min) input.min = "1900-01-01";
        if (!input.max) input.max = input.type === "datetime-local" ? "2100-12-31T23:59" : "2100-12-31";

        input.addEventListener("input", () => limitDateYearValue(input));
        input.addEventListener("change", () => limitDateYearValue(input));
    });
}

function escapeHtml(value) {
    return String(value ?? "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

function formatDateTime(value) {
    if (!value) return "-";
    const d = new Date(value);
    if (Number.isNaN(d.getTime())) return "-";
    return d.toLocaleString([], {
        year: "numeric",
        month: "short",
        day: "numeric",
        hour: "numeric",
        minute: "2-digit"
    });
}

function setupIncomeDateDefaults() {
    const today = isoToDisplayDate(new Date());
    if (techIncomeDate && !techIncomeDate.value) techIncomeDate.value = today;
    if (salonIncomeDate && !salonIncomeDate.value) salonIncomeDate.value = today;
    if (techIncomeRangeStart && !techIncomeRangeStart.value) techIncomeRangeStart.value = today;
    if (techIncomeRangeEnd && !techIncomeRangeEnd.value) techIncomeRangeEnd.value = today;
    if (saleHistoryRangeStart && !saleHistoryRangeStart.value) saleHistoryRangeStart.value = today;
    if (saleHistoryRangeEnd && !saleHistoryRangeEnd.value) saleHistoryRangeEnd.value = today;
    setupRangeInputs(techIncomeRangeType, techIncomeRangeStart, techIncomeRangeEnd);
    setupRangeInputs(saleHistoryRangeType, saleHistoryRangeStart, saleHistoryRangeEnd);
}

function setupRangeInputs(typeInput, startInput, endInput) {
    if (!typeInput || !startInput || !endInput) return;
    const isYearRange = typeInput.value === "year";
    [startInput, endInput].forEach((input) => {
        const currentISO = displayDateToISO(input.value);
        input.dataset.dateMask = isYearRange ? "false" : "true";
        input.dataset.yearMask = isYearRange ? "true" : "false";
        input.placeholder = isYearRange ? "YYYY" : "MM-DD-YYYY";
        input.maxLength = isYearRange ? 4 : 10;
        input.pattern = isYearRange ? "\\d{4}" : "\\d{2}-\\d{2}-\\d{4}";
        if (isYearRange) {
            input.value = currentISO ? currentISO.slice(0, 4) : formatMaskedYear(input.value);
        } else if (/^\d{4}$/.test(input.value)) {
            input.value = input.id.toLowerCase().includes("end") ? `12-31-${input.value}` : `01-01-${input.value}`;
        } else {
            input.value = formatMaskedDate(input.value || isoToDisplayDate(new Date()));
        }
    });
}

function getWeekBounds(dateText) {
    const date = new Date(`${dateText}T00:00:00`);
    if (Number.isNaN(date.getTime())) return null;
    const day = date.getDay();
    const mondayOffset = day === 0 ? -6 : 1 - day;
    const sundayOffset = mondayOffset + 6;
    const start = new Date(date);
    const end = new Date(date);
    start.setDate(date.getDate() + mondayOffset);
    end.setDate(date.getDate() + sundayOffset);
    return {
        start: getLocalDateKey(start),
        end: getLocalDateKey(end),
    };
}

function getRangeBounds(rangeTypeInput, startInput, endInput) {
    const type = rangeTypeInput?.value || "date";
    const startValue = startInput?.value || "";
    const endValue = endInput?.value || "";

    if (type === "year") {
        if (!/^\d{4}$/.test(startValue) || !/^\d{4}$/.test(endValue)) return null;
        const startYear = Number(startValue);
        const endYear = Number(endValue);
        if (startYear > endYear) return null;
        return {
            type,
            start: `${startValue}-01-01`,
            end: `${endValue}-12-31`,
            label: `${startValue} to ${endValue}`,
        };
    }

    if (!isValidDateText(startValue) || !isValidDateText(endValue)) return null;

    const startISO = displayDateToISO(startValue);
    const endISO = displayDateToISO(endValue);
    const startBound = type === "week" ? getWeekBounds(startISO)?.start : startISO;
    const endBound = type === "week" ? getWeekBounds(endISO)?.end : endISO;
    if (!startBound || !endBound || startBound > endBound) return null;

    return {
        type,
        start: startBound,
        end: endBound,
        label: `${isoToDisplayDate(startBound)} to ${isoToDisplayDate(endBound)}`,
    };
}

function populateTechIncomeTechnicianDropdown() {
    if (!techIncomeTechnician) return;
    const selected = techIncomeTechnician.value;
    techIncomeTechnician.innerHTML = `<option value="">All technicians</option>`;

    techniciansRaw.forEach((tech) => {
        const option = document.createElement("option");
        option.value = tech.id;
        option.textContent = tech.full_name;
        techIncomeTechnician.appendChild(option);
    });

    techIncomeTechnician.value = selected;
}

function checkoutToIncomeDetail(checkout) {
    return {
        created_at: checkout.created_at,
        turn_number: checkout.turn_number,
        customer_name: checkout.customer_name || "",
        technician_name: getTechnicianNameById(checkout.technician_id),
        service_name: checkout.service_name || "",
        gross_before_discount: Number(checkout.subtotal || 0),
        discount_amount: Number(checkout.discount_amount || 0),
        net_after_discount: Number(checkout.net_service || 0),
        tech_60_percent: Number(checkout.technician_share || 0),
        tip_amount: Number(checkout.tip_amount || 0),
        tech_total: Number(checkout.technician_total || 0),
    };
}

function getCheckoutDateKey(checkout) {
    return checkout?.created_at ? getLocalDateKey(checkout.created_at) : "";
}

function filterCheckoutsByRange(checkouts, bounds) {
    return (checkouts || []).filter((checkout) => {
        const dateKey = getCheckoutDateKey(checkout);
        return dateKey && dateKey >= bounds.start && dateKey <= bounds.end;
    });
}

function renderIncomeDetailTable(details) {
    if (!details || !details.length) {
        return `<div class="empty-state">No turn details for this date.</div>`;
    }

    return `
    <div class="inventory-table-wrap income-table-wrap">
      <table class="inventory-table income-table">
        <thead>
          <tr>
            <th>Time</th>
            <th>Turn</th>
            <th>Customer</th>
            <th>Tech</th>
            <th>Service</th>
            <th>Gross</th>
            <th>Discount</th>
            <th>Net</th>
            <th>60%</th>
            <th>Tip</th>
            <th>Tech Total</th>
          </tr>
        </thead>
        <tbody>
          ${details.map((detail) => `
            <tr>
              <td>${formatDateTime(detail.created_at)}</td>
              <td>${detail.turn_number ? `#${detail.turn_number}` : "-"}</td>
              <td>${escapeHtml(detail.customer_name)}</td>
              <td>${escapeHtml(detail.technician_name || "-")}</td>
              <td>${escapeHtml(detail.service_name)}</td>
              <td>${formatMoney(detail.gross_before_discount)}</td>
              <td>${formatMoney(detail.discount_amount)}</td>
              <td>${formatMoney(detail.net_after_discount)}</td>
              <td>${formatMoney(detail.tech_60_percent)}</td>
              <td>${formatMoney(detail.tip_amount)}</td>
              <td>${formatMoney(detail.tech_total)}</td>
            </tr>
          `).join("")}
        </tbody>
      </table>
    </div>`;
}

function renderTechIncome(report) {
    techIncomeDateSummaries = report?.technicians || [];
    techIncomeDateLabel = report?.date ? isoToDisplayDate(report.date) : "";
    renderCombinedTechIncome();
}

function renderSalonIncome(report) {
    if (!report) return;

    if (salonDayBeforeDiscount) salonDayBeforeDiscount.textContent = formatMoney(report.day.income_before_discount);
    if (salonDayDiscount) salonDayDiscount.textContent = formatMoney(report.day.total_discount);
    if (salonDayAfterTech) salonDayAfterTech.textContent = formatMoney(report.day.salon_income_after_techs);
    if (salonWeekAfterTech) salonWeekAfterTech.textContent = formatMoney(report.week.salon_income_after_techs);
    if (salonYearAfterTech) salonYearAfterTech.textContent = formatMoney(report.year.salon_income_after_techs);

    if (!salonIncomeContent) return;
    const periods = [report.day, report.week, report.year];
    salonIncomeContent.innerHTML = `
    <div class="form-card income-report-card">
      <div class="income-period-grid">
        ${periods.map((period) => `
          <div class="income-period-panel">
            <h3>${period.period}</h3>
            <p class="subtitle">${formatIncomePeriodDates(period)}</p>
            <div class="income-period-lines">
              <p><span>Before Discount</span><strong>${formatMoney(period.income_before_discount)}</strong></p>
              <p><span>Discount</span><strong>${formatMoney(period.total_discount)}</strong></p>
              <p><span>After Discount</span><strong>${formatMoney(period.income_after_discount)}</strong></p>
              <p><span>Tech 60%</span><strong>${formatMoney(period.tech_60_percent_total)}</strong></p>
              <p><span>Tips Paid to Techs</span><strong>${formatMoney(period.tech_tip_total)}</strong></p>
              <p><span>Total Paid to Techs</span><strong>${formatMoney(period.total_paid_to_techs)}</strong></p>
              <p><span>Salon After Tech Pay</span><strong>${formatMoney(period.salon_income_after_techs)}</strong></p>
              <p><span>Turns</span><strong>${period.turns}</strong></p>
            </div>
          </div>
        `).join("")}
      </div>
    </div>
    <div class="form-card income-report-card">
      <div class="section-header">
        <div>
          <h3>Date Turn Details</h3>
          <p class="subtitle">${isoToDisplayDate(report.date)}</p>
        </div>
      </div>
      ${renderIncomeDetailTable(report.details)}
    </div>`;
}

async function loadTechIncome() {
    setupIncomeDateDefaults();
    if (!techIncomeDate?.value) return;
    if (!isValidDateText(techIncomeDate.value)) {
        showCuteNotification("Enter a valid income report date with a 4-number year.", "Notice");
        return;
    }

    const url = new URL(`${API_BASE}/income/tech`);
    url.searchParams.set("date", displayDateToISO(techIncomeDate.value));
    if (techIncomeTechnician?.value) {
        url.searchParams.set("technician_id", techIncomeTechnician.value);
    }

    try {
        const report = await fetchJson(url.toString());
        renderTechIncome(report);
    } catch (error) {
        if (techIncomeContent) {
            techIncomeContent.innerHTML = `<div class="form-card"><div class="empty-state">Could not load tech income.</div></div>`;
        }
        showCuteNotification(error.message || "Failed to load tech income.", "Oops");
    }
}

async function loadTechIncomeRange() {
    setupIncomeDateDefaults();
    const bounds = getRangeBounds(techIncomeRangeType, techIncomeRangeStart, techIncomeRangeEnd);
    if (!bounds) {
        showCuteNotification("Enter a valid range. Years must be exactly 4 numbers.", "Notice");
        return;
    }

    try {
        const checkouts = await fetchJson(`${API_BASE}/checkouts`);
        const technicianFilter = techIncomeTechnician?.value ? Number(techIncomeTechnician.value) : null;
        const matching = filterCheckoutsByRange(checkouts, bounds).filter((checkout) => {
            return !technicianFilter || Number(checkout.technician_id) === technicianFilter;
        });

        const grouped = new Map();
        matching.forEach((checkout) => {
            const techId = Number(checkout.technician_id || 0);
            const key = techId || `unknown-${checkout.technician_name || "unknown"}`;
            if (!grouped.has(key)) {
                grouped.set(key, {
                    technician_id: techId || null,
                    technician_name: getTechnicianNameById(techId),
                    date: bounds.label,
                    gross_before_60: 0,
                    tech_after_60: 0,
                    tip_total: 0,
                    tech_total: 0,
                    turns: 0,
                    details: [],
                });
            }
            const summary = grouped.get(key);
            summary.gross_before_60 += Number(checkout.subtotal || 0);
            summary.tech_after_60 += Number(checkout.technician_share || 0);
            summary.tip_total += Number(checkout.tip_amount || 0);
            summary.tech_total += Number(checkout.technician_total || 0);
            summary.turns += 1;
            summary.details.push(checkoutToIncomeDetail(checkout));
        });

        renderTechIncomeRange(Array.from(grouped.values()), bounds);
    } catch (error) {
        if (techIncomeRangeContent) {
            techIncomeRangeContent.innerHTML = `<div class="form-card"><div class="empty-state">Could not load tech income range.</div></div>`;
        }
        showCuteNotification(error.message || "Failed to load tech income range.", "Oops");
    }
}

function renderTechIncomeRange(summaries, bounds) {
    techIncomeRangeSummaries = summaries || [];
    techIncomeRangeLabel = bounds?.label || "";
    renderCombinedTechIncome();
}

function getTechIncomeKey(summary) {
    return summary?.technician_id ? `id-${summary.technician_id}` : `name-${summary?.technician_name || "Unknown"}`;
}

function renderTechIncomeSummarySection(title, label, summary) {
    if (!summary) {
        return `
      <div class="income-period-panel">
        <h3>${escapeHtml(title)}</h3>
        <p class="subtitle">${escapeHtml(label || "-")}</p>
        <div class="empty-state">No income found.</div>
      </div>`;
    }

    return `
      <div class="income-period-panel">
        <h3>${escapeHtml(title)}</h3>
        <p class="subtitle">${escapeHtml(label || "-")}</p>
        <div class="inventory-summary-grid income-summary-grid">
          <div class="summary-card">
            <span class="summary-label">Nail Gross Before 60%</span>
            <strong>${formatMoney(summary.gross_before_60)}</strong>
          </div>
          <div class="summary-card">
            <span class="summary-label">Tech 60%</span>
            <strong>${formatMoney(summary.tech_after_60)}</strong>
          </div>
          <div class="summary-card">
            <span class="summary-label">Tip</span>
            <strong>${formatMoney(summary.tip_total)}</strong>
          </div>
          <div class="summary-card">
            <span class="summary-label">Tech Total</span>
            <strong>${formatMoney(summary.tech_total)}</strong>
          </div>
          <div class="summary-card">
            <span class="summary-label">Turns</span>
            <strong>${summary.turns}</strong>
          </div>
        </div>
        ${renderIncomeDetailTable(summary.details)}
      </div>`;
}

function renderCombinedTechIncome() {
    if (techIncomeRangeContent) techIncomeRangeContent.innerHTML = "";
    if (!techIncomeContent) return;

    const grouped = new Map();
    techIncomeDateSummaries.forEach((summary) => {
        const key = getTechIncomeKey(summary);
        grouped.set(key, {
            technician_name: summary.technician_name,
            dateSummary: summary,
            rangeSummary: null,
        });
    });

    techIncomeRangeSummaries.forEach((summary) => {
        const key = getTechIncomeKey(summary);
        const existing = grouped.get(key) || {
            technician_name: summary.technician_name,
            dateSummary: null,
            rangeSummary: null,
        };
        existing.technician_name = existing.technician_name || summary.technician_name;
        existing.rangeSummary = summary;
        grouped.set(key, existing);
    });

    if (!grouped.size) {
        techIncomeContent.innerHTML = `
      <div class="form-card">
        <div class="empty-state">No tech income found.</div>
      </div>`;
        return;
    }

    techIncomeContent.innerHTML = Array.from(grouped.values()).map((group) => `
    <div class="form-card income-report-card">
      <div class="section-header">
        <div>
          <h3>${escapeHtml(group.technician_name || "Unknown Technician")}</h3>
          <p class="subtitle">Date and range results grouped together</p>
        </div>
      </div>
      <div class="income-period-grid tech-income-combined-grid">
        ${renderTechIncomeSummarySection("Date Review", techIncomeDateLabel, group.dateSummary)}
        ${renderTechIncomeSummarySection("Range Review", techIncomeRangeLabel, group.rangeSummary)}
      </div>
    </div>
  `).join("");
}

function formatIncomePeriodDates(period) {
    const start = isoToDisplayDate(period.start_date);
    const end = isoToDisplayDate(period.end_date);
    return start === end ? start : `${start} to ${end}`;
}

async function loadSalonIncome() {
    setupIncomeDateDefaults();
    if (!salonIncomeDate?.value) return;
    if (!isValidDateText(salonIncomeDate.value)) {
        showCuteNotification("Enter a valid salon income date with a 4-number year.", "Notice");
        return;
    }

    const url = new URL(`${API_BASE}/income/salon`);
    url.searchParams.set("date", displayDateToISO(salonIncomeDate.value));

    try {
        const report = await fetchJson(url.toString());
        renderSalonIncome(report);
    } catch (error) {
        if (salonIncomeContent) {
            salonIncomeContent.innerHTML = `<div class="form-card"><div class="empty-state">Could not load salon income.</div></div>`;
        }
        showCuteNotification(error.message || "Failed to load salon income.", "Oops");
    }
}

function isLowStock(item) {
    return Number(item.quantity) <= Number(item.low_stock_level || 0);
}

async function loadInventoryItems() {
    inventoryItems = await fetchJson(`${API_BASE}/inventory`);
}

async function loadInventorySummary() {
    const summary = await fetchJson(`${API_BASE}/inventory/summary`);

    inventoryTotalValue.textContent = formatMoney(summary.total_inventory_value);
    inventoryWeeklyExpense.textContent = formatMoney(summary.weekly_expense);
    inventoryMonthlyExpense.textContent = formatMoney(summary.monthly_expense);
    inventoryYearlyExpense.textContent = formatMoney(summary.yearly_expense);
    inventoryLowStockCount.textContent = String(summary.low_stock_items);
}

function resetInventoryForm() {
    inventoryForm.reset();
    inventoryIdInput.value = "";
    inventoryFormTitle.textContent = "Add Inventory Item";
    saveInventoryBtn.textContent = "Save Item";
    cancelInventoryEditBtn.classList.add("hidden");
    inventoryQuantity.value = 1;
    inventoryUnitPrice.value = 0;
}

function fillInventoryForm(item) {
    inventoryIdInput.value = item.id;
    inventoryItemName.value = item.item_name || "";
    inventoryCategory.value = item.category || "";
    inventorySupplier.value = item.supplier || "";
    inventoryQuantity.value = item.quantity ?? 1;
    inventoryUnitPrice.value = item.unit_price ?? 0;
    inventoryPurchaseDate.value = isoToDisplayDate(item.purchase_date);

    inventoryFormTitle.textContent = "Edit Inventory Item";
    saveInventoryBtn.textContent = "Update Item";
    cancelInventoryEditBtn.classList.remove("hidden");
}

function getFilteredInventoryItems() {
    let items = [...inventoryItems];

    const searchValue = inventorySearch?.value.trim().toLowerCase() || "";
    const categoryValue = inventoryCategoryFilter?.value || "";
    const stockValue = inventoryStockFilter?.value || "";

    if (searchValue) {
        items = items.filter((item) =>
            (item.item_name || "").toLowerCase().includes(searchValue)
        );
    }

    if (categoryValue) {
        items = items.filter((item) => item.category === categoryValue);
    }

    if (stockValue === "low") {
        items = items.filter((item) => isLowStock(item));
    } else if (stockValue === "ok") {
        items = items.filter((item) => !isLowStock(item));
    }

    return items;
}

function getDateRangeStart(type) {
    const now = new Date();

    if (type === "week") {
        const day = now.getDay();
        const diff = day === 0 ? 6 : day - 1;
        const start = new Date(now);
        start.setDate(now.getDate() - diff);
        start.setHours(0, 0, 0, 0);
        return start;
    }

    if (type === "month") {
        return new Date(now.getFullYear(), now.getMonth(), 1);
    }

    if (type === "year") {
        return new Date(now.getFullYear(), 0, 1);
    }

    return new Date(0);
}

function calculateExpenseTotal(type) {
    const startDate = getDateRangeStart(type);

    return inventoryItems.reduce((sum, item) => {
        if (!item.purchase_date) return sum;

        const purchaseDate = new Date(item.purchase_date);
        purchaseDate.setHours(0, 0, 0, 0);

        if (purchaseDate >= startDate) {
            return sum + Number(item.quantity || 0) * Number(item.unit_price || 0);
        }

        return sum;
    }, 0);
}

function updateInventorySummary() {
    const totalValue = inventoryItems.reduce((sum, item) => {
        return sum + Number(item.quantity || 0) * Number(item.unit_price || 0);
    }, 0);

    const lowStockItems = inventoryItems.filter((item) => isLowStock(item)).length;

    inventoryTotalValue.textContent = formatMoney(totalValue);
    inventoryWeeklyExpense.textContent = formatMoney(calculateExpenseTotal("week"));
    inventoryMonthlyExpense.textContent = formatMoney(calculateExpenseTotal("month"));
    inventoryYearlyExpense.textContent = formatMoney(calculateExpenseTotal("year"));
    inventoryLowStockCount.textContent = String(lowStockItems);
}

function renderInventoryTable() {
    const items = getFilteredInventoryItems();

    inventoryTableBody.innerHTML = "";

    if (!items.length) {
        inventoryTableBody.innerHTML = `
      <tr>
        <td colspan="9" class="inventory-empty">No inventory items found.</td>
      </tr>
    `;
        return;
    }

    items.forEach((item) => {
        const tr = document.createElement("tr");
        const totalValue = Number(item.quantity || 0) * Number(item.unit_price || 0);
        const lowStock = isLowStock(item);

        tr.innerHTML = `
      <td>${item.category || "-"}</td>
      <td>${item.item_name || "-"}</td>
      <td>${item.quantity || 0}</td>
      <td>${formatMoney(item.unit_price || 0)}</td>
      <td>${formatMoney(totalValue)}</td>
      <td>${item.supplier || "-"}</td>
      <td>${item.purchase_date ? isoToDisplayDate(item.purchase_date) : "-"}</td>
      <td>
        <span class="inventory-status ${lowStock ? "inventory-status-low" : "inventory-status-ok"}">
          ${lowStock ? "Low Stock" : "In Stock"}
        </span>
      </td>
      <td>
        <div class="inventory-actions">
          <button class="ghost-btn inventory-edit-btn" data-id="${item.id}">Edit</button>
          <button class="ghost-btn inventory-delete-btn" data-id="${item.id}">Delete</button>
        </div>
      </td>
    `;

        inventoryTableBody.appendChild(tr);
    });

    document.querySelectorAll(".inventory-edit-btn").forEach((btn) => {
        btn.addEventListener("click", () => {
            const item = inventoryItems.find((entry) => entry.id === Number(btn.dataset.id));
            if (!item) return;
            fillInventoryForm(item);
            window.scrollTo({ top: 0, behavior: "smooth" });
        });
    });

    document.querySelectorAll(".inventory-delete-btn").forEach((btn) => {
        btn.addEventListener("click", async () => {
            const confirmed = await showCuteConfirm("Delete this inventory item?", "Please Confirm");
            if (!confirmed) return;

            try {
                await fetchJson(`${API_BASE}/inventory/${btn.dataset.id}`, {
                    method: "DELETE"
                });
                await renderInventory();
                showCuteNotification("Inventory item deleted successfully.");
            } catch (error) {
                showCuteNotification(error.message || "Failed to delete inventory item.", "Oops");
            }
        });
    });
}

async function renderInventory() {
    await loadInventoryItems();
    await loadInventorySummary();
    renderInventoryTable();
}

inventoryForm?.addEventListener("submit", async (e) => {
    e.preventDefault();

    const itemData = {
        item_name: inventoryItemName.value.trim(),
        category: inventoryCategory.value,
        supplier: inventorySupplier.value.trim() || null,
        quantity: Number(inventoryQuantity.value || 0),
        unit_price: Number(inventoryUnitPrice.value || 0),
        purchase_date: displayDateToISO(inventoryPurchaseDate.value) || null,
        low_stock_level: 3
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


function populatePreferredTechSelect(excludeTechnicianId = null, serviceName = "") {
    if (!preferredTechSelect) return;

    preferredTechSelect.innerHTML = `<option value="">Select technician</option>`;

    const availableTechs = techniciansRaw.filter((tech) => {
        const status = String(tech.status || "").trim().toLowerCase();
        const availability = String(tech.availability || "").trim().toLowerCase();

        const isAvailable = status === "active" && availability === "available today";
        const isExcluded = excludeTechnicianId && Number(tech.id) === Number(excludeTechnicianId);
        const canDoService = !serviceName || serviceMatchesTechSpecialties(serviceName, tech.specialties);

        return isAvailable && !isExcluded && canDoService;
    });

    if (!availableTechs.length) {
        const option = document.createElement("option");
        option.value = "";
        option.textContent = serviceName ? "No available technician matches this service" : "No available technicians today";
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

function resetCheckoutForm() {
    checkoutForm?.reset();
    if (checkoutIdInput) checkoutIdInput.value = "";
    if (checkoutFormTitle) checkoutFormTitle.textContent = "Final Checkout";
    if (saveCheckoutBtn) saveCheckoutBtn.textContent = "Complete Checkout";
    cancelCheckoutEditBtn?.classList.add("hidden");
    if (checkoutTechnicianId) checkoutTechnicianId.value = "";
    if (checkoutTechnicianName) checkoutTechnicianName.value = "";

    if (checkoutSubtotal) checkoutSubtotal.value = 0;
    if (checkoutDiscountValue) checkoutDiscountValue.value = 0;
    if (checkoutTip) checkoutTip.value = 0;
    if (checkoutDiscountType) checkoutDiscountType.value = "none";
    if (checkoutDiscountPaidBy) checkoutDiscountPaidBy.value = "owner";
    if (checkoutPaymentMethod) checkoutPaymentMethod.value = "cash";
    if (checkoutDiscountDisplay) {
        checkoutDiscountDisplay.dataset.discountLabel = "";
        checkoutDiscountDisplay.textContent = "No discount applied";
    }

    updateCheckoutSummary();
}

function getCheckoutCalculation() {
    const gross = Number(checkoutSubtotal?.value || 0);
    const discountType = checkoutDiscountType?.value || "none";
    const discountValue = Number(checkoutDiscountValue?.value || 0);
    const discountPaidBy = "owner";
    const tip = Number(checkoutTip?.value || 0);

    let discountAmount = 0;

    if (discountType === "fixed") {
        discountAmount = discountValue;
    } else if (discountType === "percent") {
        discountAmount = gross * (discountValue / 100);
    }

    if (discountAmount > gross) {
        discountAmount = gross;
    }

    const netService = gross - discountAmount;

    const techShare = gross * 0.6;
    const salonShare = gross * 0.4;
    let salonActual = salonShare - discountAmount;

    if (salonActual < 0) salonActual = 0;

    const techTotal = techShare + tip;
    const customerPays = netService + tip;

    return {
        gross,
        discountAmount,
        netService,
        techShare,
        salonShare,
        salonActual,
        techTotal,
        customerPays,
        tip,
        discountPaidBy,
        discountType,
        discountValue
    };
}

function updateCheckoutSummary() {
    const calc = getCheckoutCalculation();

    if (checkoutGross) checkoutGross.textContent = formatMoney(calc.gross);
    if (checkoutDiscount) checkoutDiscount.textContent = formatMoney(calc.discountAmount);
    if (checkoutNet) checkoutNet.textContent = formatMoney(calc.netService);
    if (checkoutTechShare) checkoutTechShare.textContent = formatMoney(calc.techShare);
    if (checkoutSalonShare) checkoutSalonShare.textContent = formatMoney(calc.salonShare);
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

[
    checkoutSubtotal,
    checkoutDiscountType,
    checkoutDiscountValue,
    checkoutDiscountPaidBy,
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
        discount_amount: calc.discountAmount,
        discount_paid_by: calc.discountPaidBy,
        tip_amount: calc.tip,
        net_service: calc.netService,
        technician_share: calc.techShare,
        salon_share: calc.salonShare,
        salon_actual_revenue: calc.salonActual,
        technician_total: calc.techTotal,
        customer_pays: calc.customerPays,
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

cancelCheckoutEditBtn?.addEventListener("click", () => {
    resetCheckoutForm();
});

checkoutCustomerPhone?.addEventListener("input", (e) => {
    e.target.value = formatPhoneInput(e.target.value);
});

function showCuteNotification(message, title = "Success") {
    cuteNotificationTitle.textContent = title;
    cuteNotificationMessage.textContent = message;
    cuteNotification.classList.remove("hidden");
}

function hideCuteNotification() {
    cuteNotification.classList.add("hidden");
}

cuteNotificationBtn?.addEventListener("click", hideCuteNotification);
cuteNotification?.addEventListener("click", (e) => {
    if (e.target === cuteNotification) hideCuteNotification();
});

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

cuteConfirmOk?.addEventListener("click", () => closeCuteConfirm(true));
cuteConfirmCancel?.addEventListener("click", () => closeCuteConfirm(false));
cuteConfirm?.addEventListener("click", (e) => {
    if (e.target === cuteConfirm) closeCuteConfirm(false);
});

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
    <p><strong>Customer:</strong> ${appt.customer_name || "-"}</p>
    <p><strong>Phone:</strong> ${appt.customer_phone || "-"}</p>
    <p><strong>Service Category:</strong> ${appt.service_category || appt.service_name || "-"}</p>
    <p><strong>Number of People:</strong> ${appt.people_count || 1}</p>
    <p><strong>Date & Time:</strong> ${prettyDate}</p>
    <p><strong>Preferred Technician:</strong> ${preferredTech?.full_name || "-"}</p>
    <p><strong>Special Requests:</strong> ${appt.special_requests || "-"}</p>
    <p><strong>Allergies:</strong> ${appt.allergies || "-"}</p>
  `;

    appointmentModal.classList.remove("hidden");
}

function closeAppointmentModal() {
    appointmentModal.classList.add("hidden");
}

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

function formatDateHeader(date) {
    return date.toLocaleDateString([], {
        weekday: "long",
        month: "short",
        day: "2-digit",
        year: "numeric",
    });
}

function setDateLabel() {
    dateLabel.textContent = formatDateHeader(selectedDate);
}

function sameDay(a, b) {
    return (
        a.getFullYear() === b.getFullYear() &&
        a.getMonth() === b.getMonth() &&
        a.getDate() === b.getDate()
    );
}

function formatHourLabel(hour24) {
    const suffix = hour24 >= 12 ? "pm" : "am";
    const display = hour24 % 12 === 0 ? 12 : hour24 % 12;
    return `${display}:00<br><span>${suffix}</span>`;
}

function getAvatarClass(index) {
    const classes = ["coral", "gold", "teal", "blue", "pink", "plum", "mint", "amber", "indigo", "rose"];
    return classes[index % classes.length];
}

function getInitials(name) {
    return (name || "")
        .split(" ")
        .filter(Boolean)
        .map((word) => word[0])
        .join("")
        .slice(0, 2)
        .toUpperCase();
}

function formatPhoneInput(value) {
    const digits = value.replace(/\D/g, "").slice(0, 10);
    if (digits.length <= 3) return digits;
    if (digits.length <= 6) return `(${digits.slice(0, 3)}) ${digits.slice(3)}`;
    return `(${digits.slice(0, 3)}) ${digits.slice(3, 6)}-${digits.slice(6)}`;
}

function toDatetimeLocalValue(value) {
    return isoDateTimeToDisplay(value);
}

function formatLiveCheckinTime(dateString) {
    const date = new Date(dateString);
    return date.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
}

function normalizeServiceForMatch(serviceName) {
    return (serviceName || "").trim().toLowerCase();
}

const SERVICE_SPECIALTY_KEYWORDS = [
    { keywords: ["classic manicure", "gel manicure", "deluxe manicure", "classic pedicure", "deluxe pedicure", "spa pedicure", "jelly pedicure", "polish change", "paraffin", "manicure", "pedicure"], specialties: ["manicure / pedicure"] },
    { keywords: ["acrylic full set", "acrylic fill", "pink and white", "acrylic"], specialties: ["acrylic"] },
    { keywords: ["dip powder", "dipping"], specialties: ["dip powder"] },
    { keywords: ["gel full set", "gel fill", "gel x"], specialties: ["gel"] },
    { keywords: ["hard gel", "builder gel"], specialties: ["builder / hard gel", "gel"] },
    { keywords: ["nail art", "chrome", "cat eye", "french tip", "ombre"], specialties: ["nail art", "acrylic", "gel", "builder / hard gel"] },
    { keywords: ["nail repair", "nail removal", "removal"], specialties: ["nail repair / removal", "acrylic", "gel", "dip powder", "builder / hard gel"] },
    { keywords: ["waxing", "eyebrows", "eyebrow", "lip", "chin"], specialties: ["waxing"] }
];

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
        SERVICE_SPECIALTY_KEYWORDS.forEach((mapping) => {
            if (mapping.keywords.some((keyword) => serviceItem.includes(keyword))) {
                mapping.specialties.forEach((specialty) => required.add(specialty));
            }
        });
    });

    if (!required.size) return false;
    return techSpecialties.some((specialty) => required.has(specialty));
}

function getTurnForCustomer(checkinItem) {
    const customerName = (checkinItem.full_name || "").trim().toLowerCase();
    const customerPhone = (checkinItem.phone_number || "").replace(/\D/g, "");

    const matchingTurns = todayTurns.filter((turn) => {
        const turnName = (turn.customer_name || "").trim().toLowerCase();
        const turnPhone = (turn.customer_phone || "").replace(/\D/g, "");

        const sameCustomer =
            (customerPhone && turnPhone && customerPhone === turnPhone) ||
            (customerName && turnName && customerName === turnName);

        return sameCustomer;
    });

    if (!matchingTurns.length) return null;

    matchingTurns.sort((a, b) => {
        const aTime = new Date(a.created_at || 0).getTime();
        const bTime = new Date(b.created_at || 0).getTime();
        return bTime - aTime;
    });

    return matchingTurns[0];
}

function getTechnicianNameById(technicianId) {
    const normalizedId = Number(technicianId);
    const tech = techniciansRaw.find((item) => Number(item.id) === normalizedId);
    return tech ? tech.full_name : "Not assigned";
}

function getAppointmentForTurn(turn) {
    if (!turn) return null;

    const turnName = (turn.customer_name || "").trim().toLowerCase();
    const turnPhone = (turn.customer_phone || "").replace(/\D/g, "");
    const turnService = normalizeServiceForMatch(turn.service_name);

    return appointments.find((appt) => {
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

function formatDiscountText(label, discountType, discountValue) {
    if (discountType === "percent" && discountValue > 0) {
        return `${label || "Automatic discount"}: ${discountValue}% off`;
    }

    if (discountType === "fixed" && discountValue > 0) {
        return `${label || "Automatic discount"}: ${formatMoney(discountValue)} off`;
    }

    return label || "No discount applied";
}

function formatCheckoutDiscountText(turn) {
    if (!turn) return "No discount applied";
    const discount = getDiscountForTurn(turn);
    return formatDiscountText(discount.label, discount.type, discount.value);
}

function getCheckinDiscountForTurn(turn) {
    if (!turn) return null;

    const turnName = (turn.customer_name || "").trim().toLowerCase();
    const turnPhone = (turn.customer_phone || "").replace(/\D/g, "");

    const checkin = liveCheckins.find((item) => {
        const itemName = (item.full_name || "").trim().toLowerCase();
        const itemPhone = (item.phone_number || "").replace(/\D/g, "");
        return (
            (turnPhone && itemPhone && turnPhone === itemPhone) ||
            (turnName && itemName && turnName === itemName)
        );
    });

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

    const linkedAppointment = getAppointmentForTurn(turn);
    const discount = getDiscountForTurn(turn);

    if (checkoutIdInput) checkoutIdInput.value = "";
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
    if (checkoutDiscountPaidBy) checkoutDiscountPaidBy.value = "owner";
    if (checkoutTip) checkoutTip.value = 0;
    if (checkoutSubtotal) checkoutSubtotal.value = 0;
    if (checkoutDiscountDisplay) checkoutDiscountDisplay.dataset.discountLabel = discount.label || "";

    updateCheckoutSummary();
    showView("checkout");
    checkoutForm?.scrollIntoView({ behavior: "smooth", block: "start" });
}

async function loadTodayTurns() {
    try {
        todayTurns = await fetchJson(`${API_BASE}/turns/today`);
        console.log("todayTurns loaded", todayTurns);
    } catch (error) {
        console.error("Failed to load today turns:", error);
        todayTurns = [];
    }
}

async function loadCheckoutHistory(bounds = null) {
    try {
        const checkouts = await fetchJson(`${API_BASE}/checkouts`);
        const activeBounds = bounds || {
            start: getLocalDateKey(),
            end: getLocalDateKey(),
        };
        checkoutHistory = filterCheckoutsByRange(checkouts, activeBounds);
    } catch (error) {
        console.error("Failed to load checkout history:", error);
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

    await loadCheckoutHistory(bounds);
    renderCheckoutHistoryList(bounds);
}

async function loadAllCheckoutHistory() {
    try {
        checkoutHistory = await fetchJson(`${API_BASE}/checkouts`);
        renderCheckoutHistoryList({ label: "all history" });
    } catch (error) {
        checkoutHistory = [];
        renderCheckoutHistoryList({ label: "all history" });
        showCuteNotification(error.message || "Failed to load checkout history.", "Oops");
    }
}

function getCheckoutForCustomer(checkinItem) {
    const customerName = (checkinItem.full_name || "").trim().toLowerCase();
    const customerPhone = (checkinItem.phone_number || "").replace(/\D/g, "");

    return checkoutHistory.find((checkout) => {
        const checkoutName = (checkout.customer_name || "").trim().toLowerCase();
        const checkoutPhone = (checkout.customer_phone || "").replace(/\D/g, "");

        return (
            (customerPhone && checkoutPhone && customerPhone === checkoutPhone) ||
            (customerName && checkoutName && customerName === checkoutName)
        );
    }) || null;
}

function renderCheckoutHistoryList(bounds = null) {
    if (!checkoutHistoryList) return;
    const rangeLabel = bounds?.label || "today";

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
      <div class="tech-card dispatch-card checkout-history-card">
        <div class="tech-card-top">
          <div class="tech-avatar-wrap">
            <div class="tech-avatar-fallback">${getInitials(checkout.customer_name)}</div>
          </div>
          <div class="tech-main-info">
            <div class="tech-title-row">
              <h4>${escapeHtml(checkout.customer_name)}</h4>
              <span class="status-chip dispatch-status-done">checked out</span>
            </div>
            <p class="tech-subtext">Phone: ${escapeHtml(checkout.customer_phone || "-")}</p>
            <p class="tech-subtext">Completed: ${formatDateTime(checkout.created_at)}</p>
          </div>
        </div>
        <div class="tech-meta">
          <p><strong>Technician:</strong> ${escapeHtml(getTechnicianNameById(checkout.technician_id))}</p>
          <p><strong>Service:</strong> ${escapeHtml(checkout.service_name || "-")}</p>
          <p><strong>Paid:</strong> ${formatMoney(checkout.customer_pays)} | <strong>Technician Tip:</strong> ${formatMoney(checkout.tip_amount)}</p>
        </div>
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

async function autoAssignCheckin(item, silent = false) {
    const serviceName = getCombinedServiceName(item);
    if (!serviceName) {
        if (!silent) {
            showCuteNotification("No service found for this customer.", "Oops");
        }
        return null;
    }

    try {
        const turn = await fetchJson(`${API_BASE}/turns/assign-auto`, {
            method: "POST",
            body: JSON.stringify({
                customer_name: item.full_name,
                customer_phone: item.phone_number,
                service_name: serviceName,
                source: "checkin",
                discount_type: item.discount_type || null,
                discount_value: Number(item.discount_value || 0),
                discount_label: item.discount_label || null
            })
        });

        mergeTodayTurn(turn);

        if (!silent) {
            showCuteNotification("Customer auto-assigned successfully.");
        }
        return turn;
    } catch (error) {
        if (!silent) {
            showCuteNotification(error.message || "Failed to auto assign customer.", "Oops");
        }
        return null;
    }
}

async function autoAssignAllWaitingCheckins() {
    await loadTodayTurns();
    await loadCheckoutHistory();
    await loadLiveCheckinQueue();

    const unassignedItems = liveCheckins.filter((item) => {
        const linkedTurn = getTurnForCustomer(item);
        const completedCheckout = getCheckoutForCustomer(item);
        return !completedCheckout && (!linkedTurn || linkedTurn.status === "waiting");
    });

    if (!unassignedItems.length) {
        showCuteNotification("No waiting customers to auto assign.", "Notice");
        return;
    }

    let assignedCount = 0;
    let failedCount = 0;

    for (const item of unassignedItems) {
        const assignedTurn = await autoAssignCheckin(item, true);
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

    if (assignedCount > 0 && failedCount === 0) {
        showCuteNotification(
            `${assignedCount} customer${assignedCount > 1 ? "s have" : " has"} been assigned successfully.`
        );
    } else if (assignedCount > 0 && failedCount > 0) {
        showCuteNotification(
            `${assignedCount} customer${assignedCount > 1 ? "s have" : " has"} been assigned. ${failedCount} ${failedCount > 1 ? "customers are" : "customer is"} still waiting because no technician is available right now.`,
            "Notice"
        );
    } else {
        showCuteNotification(
            "No customers were assigned because no technician is available right now.",
            "Notice"
        );
    }
}

async function openPreferredTechModal(item) {
    await loadTechniciansRaw();
    const serviceName = getCombinedServiceName(item);

    preferredTechModalMode = "assign";
    pendingPreferredCheckinItem = item;
    pendingReassignTurnId = null;
    currentReassignTechnicianId = null;

    populatePreferredTechSelect(null, serviceName);

    preferredTechSelect.value = "";
    preferredTechConfirmBtn.textContent = "Assign";

    const modalTitle = preferredTechModal?.querySelector("h2");
    if (modalTitle) modalTitle.textContent = "Select Preferred Technician";

    if (preferredTechCustomerText) {
        preferredTechCustomerText.textContent = `Choose a technician for ${item.full_name}.`;
    }

    preferredTechModal?.classList.remove("hidden");
}

function closePreferredTechModal() {
    preferredTechModal?.classList.add("hidden");
    preferredTechModalMode = "assign";
    pendingPreferredCheckinItem = null;
    pendingReassignTurnId = null;
    currentReassignTechnicianId = null;

    if (preferredTechSelect) {
        preferredTechSelect.value = "";
    }

    if (preferredTechConfirmBtn) {
        preferredTechConfirmBtn.textContent = "Assign";
    }

    const modalTitle = preferredTechModal?.querySelector("h2");
    if (modalTitle) modalTitle.textContent = "Select Preferred Technician";

    if (preferredTechCustomerText) {
        preferredTechCustomerText.textContent = "";
    }
}

async function openReassignModal(turnId) {
    await loadTechniciansRaw();

    const turn = todayTurns.find((item) => Number(item.id) === Number(turnId));
    if (!turn) {
        showCuteNotification("Turn not found.", "Oops");
        return;
    }

    preferredTechModalMode = "reassign";
    pendingPreferredCheckinItem = null;
    pendingReassignTurnId = turnId;
    currentReassignTechnicianId = turn.technician_id || null;

    populatePreferredTechSelect(currentReassignTechnicianId, turn.service_name || "");

    preferredTechSelect.value = "";
    preferredTechConfirmBtn.textContent = "Reassign";

    const modalTitle = preferredTechModal?.querySelector("h2");
    if (modalTitle) modalTitle.textContent = "Reassign Technician";

    if (preferredTechCustomerText) {
        preferredTechCustomerText.textContent = `Choose a new technician for ${turn.customer_name}.`;
    }

    preferredTechModal?.classList.remove("hidden");
}

async function assignPreferredCheckin(item) {
    const serviceName = getCombinedServiceName(item);
    if (!serviceName) {
        showCuteNotification("No service found for this customer.", "Oops");
        return;
    }

    await openPreferredTechModal(item);
}

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

    try {
        if (preferredTechModalMode === "assign") {
            if (!pendingPreferredCheckinItem) return;

            const serviceName = getCombinedServiceName(pendingPreferredCheckinItem);

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
                    discount_label: pendingPreferredCheckinItem.discount_label || null
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
            return;
        }

        if (preferredTechModalMode === "reassign") {
            if (!pendingReassignTurnId) return;

            await fetchJson(`${API_BASE}/turns/${pendingReassignTurnId}/reassign`, {
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
            renderCheckoutReadyList();
            renderCalendar();
            showView("customerList");
            showCuteNotification("Technician reassigned successfully.");
            return;
        }
    } catch (error) {
        closePreferredTechModal();
        showCuteNotification(error.message || "Failed to save technician assignment.", "Oops");
    }
});

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
            <div class="tech-avatar-fallback">${getInitials(turn.customer_name)}</div>
          </div>
          <div class="tech-main-info">
            <div class="tech-title-row">
              <h4>${turn.customer_name}</h4>
              <span class="status-chip ${isAssigned ? "dispatch-status-assigned" : "dispatch-status-in_service"}">${isAssigned ? "assigned" : "in service"}</span>
            </div>
            <p class="tech-subtext">Phone: ${turn.customer_phone || "-"}</p>
          </div>
        </div>
        <div class="tech-meta">
          <p><strong>Technician:</strong> ${techName}</p>
          <p><strong>Service:</strong> ${turn.service_name || "-"}</p>
        </div>
        <div class="dispatch-card-center">
          <button class="mini-btn checkout-select-btn" type="button" data-turn-id="${turn.id}">
            💅 Select for Checkout
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
      <div class="tech-card dispatch-card">
        <div class="tech-card-top">
          <div class="tech-avatar-wrap">
            <div class="tech-avatar-fallback">${getInitials(item.full_name)}</div>
          </div>
          <div class="tech-main-info">
            <div class="tech-title-row">
              <h4>#${item.position} ${item.full_name}</h4>
              <span class="status-chip dispatch-status-waiting">waiting</span>
            </div>
            <p class="tech-subtext">Phone: ${item.phone_number || "-"}</p>
            <p class="tech-subtext">Checked in: ${formatLiveCheckinTime(item.checked_in_at)}</p>
          </div>
        </div>
        <div class="tech-meta">
          <p><strong>Services:</strong> ${(item.services || []).join(", ") || "-"}</p>
        </div>
        <div class="dispatch-card-center">
          <button class="mini-btn queue-preferred-btn" data-name="${item.full_name}" data-phone="${item.phone_number}">
            Assign Preferred
          </button>
        </div>
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
        const response = await fetch(`${CHECKIN_API_BASE}/today-checkins`);
        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.detail || "Failed to load live check-in queue.");
        }

        liveCheckins = data.checkins || [];
        renderLiveCheckinQueue(liveCheckins);
    } catch (error) {
        liveCheckinQueue.innerHTML = `
      <div class="tech-card">
        <div class="tech-card-header">
          <h4>Unable to load queue</h4>
        </div>
        <p class="tech-subtext">${error.message || "Connection error."}</p>
      </div>
    `;
        renderCheckoutReadyList();
    }
}

function checkApi() {
    return fetch(`${API_BASE}/`)
        .then((res) => {
            if (!res.ok) throw new Error();
            apiDot.className = "dot online";
            apiText.textContent = "Backend connected";
        })
        .catch(() => {
            apiDot.className = "dot offline";
            apiText.textContent = "Backend offline";
        });
}

async function fetchJson(url, options = {}) {
    let response;

    try {
        response = await fetch(url, {
            headers: { "Content-Type": "application/json" },
            ...options,
        });
    } catch (error) {
        throw new Error(`Could not connect to backend: ${url}`);
    }

    if (!response.ok) {
        let message = "Request failed";
        try {
            const err = await response.json();
            message = err.detail || message;
        } catch {
            const text = await response.text();
            message = text || message;
        }
        throw new Error(message);
    }

    if (response.status === 204) return null;
    return response.json();
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
        return `<img src="${tech.profile_photo}" alt="${tech.full_name}" class="tech-avatar-img" />`;
    }
    return `<div class="tech-avatar-fallback">${getInitials(tech.full_name)}</div>`;
}

function getSpecialtyItems(specialties) {
    return String(specialties || "")
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean);
}

function renderSpecialtyButton(tech) {
    const items = getSpecialtyItems(tech.specialties);
    const count = items.length;

    if (!count) return `<span class="tech-empty-value">No specialties</span>`;

    return `
      <button type="button" class="specialty-toggle-btn" data-id="${tech.id}">
        View Specialties (${count})
      </button>
    `;
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
    if (techAvailability) techAvailability.value = "off today";
    if (techDateOffStart) techDateOffStart.value = "";
    if (techDateOffEnd) techDateOffEnd.value = "";
    if (techSchedule) techSchedule.value = "";
    renderScheduleBoard();
}

function formatDateInputValue(value) {
    if (!value) return "";
    if (typeof value === "string" && /^\d{4}-\d{2}-\d{2}$/.test(value)) {
        return value;
    }

    const d = new Date(value);
    if (Number.isNaN(d.getTime())) return "";

    const year = d.getFullYear();
    const month = String(d.getMonth() + 1).padStart(2, "0");
    const day = String(d.getDate()).padStart(2, "0");

    return `${year}-${month}-${day}`;
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

techStartDate?.addEventListener("input", () => validateTechStartDate(false));
techStartDate?.addEventListener("change", () => validateTechStartDate(false));
techDateOffStart?.addEventListener("input", applyDateOffStatus);
techDateOffStart?.addEventListener("change", applyDateOffStatus);
techDateOffEnd?.addEventListener("input", applyDateOffStatus);
techDateOffEnd?.addEventListener("change", applyDateOffStatus);

function fillTechnicianForm(tech) {
    techIdInput.value = tech.id;
    techName.value = tech.full_name || "";
    techPhone.value = tech.phone || "";
    if (techSkills) techSkills.value = tech.skills || "";
    techStartDate.value = isoToDisplayDate(tech.start_date);
    techStatus.value = tech.status || "off";
    if (techAvailability) techAvailability.value = tech.availability || "off today";
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

async function loadTechniciansRaw() {
    techniciansRaw = await fetchJson(`${API_BASE}/technicians`);
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

async function loadAppointments() {
    appointments = await fetchJson(`${API_BASE}/appointments`);
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
            <h4>${tech.full_name}</h4>
            <span class="status-chip">${tech.status || "-"}</span>
          </div>
          <p class="tech-subtext">Phone: ${tech.phone || "-"}</p>
        </div>
      </div>

      <div class="tech-meta">
        <div class="tech-meta-row tech-meta-wide">
          <strong>Specialties</strong>
          ${renderSpecialtyButton(tech)}
        </div>
        <div class="tech-meta-row">
          <strong>Start Date</strong>
          <span>${tech.start_date ? isoToDisplayDate(tech.start_date) : "-"}</span>
        </div>
        <div class="tech-meta-row tech-meta-wide">
          <strong>Schedule</strong>
          ${renderTechnicianScheduleSummary(tech.work_schedule)}
        </div>
      </div>

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

      <div class="tech-badges">
        <span class="availability-badge ${getBadgeClass(tech.availability)}">
          ${getAvailabilityDisplayText(tech.availability)}
        </span>
      </div>

      <div class="tech-actions">
        <button class="ghost-btn tech-edit-btn" data-id="${tech.id}">Edit</button>
        <button class="ghost-btn tech-delete-btn" data-id="${tech.id}">Delete</button>
        <button class="ghost-btn tech-schedule-btn" data-id="${tech.id}">Schedule</button>
        <button class="ghost-btn tech-unavailable-btn" data-id="${tech.id}">Unavailable</button>
      </div>
    `;

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
                await fetchJson(`${API_BASE}/technicians/${techId}`, {
                    method: "DELETE",
                });
                showCuteNotification("Technician deleted successfully.");
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

    document.querySelectorAll(".specialty-toggle-btn").forEach((btn) => {
        btn.addEventListener("click", () => {
            const techId = Number(btn.dataset.id);
            const tech = technicians.find((item) => Number(item.id) === techId);
            const items = getSpecialtyItems(tech?.specialties);
            showCuteNotification(items.map((item) => `- ${item}`).join("\n"), `${tech?.full_name || "Technician"} Specialties`);
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

function getCombinedServiceName(item) {
    if (!item) return "";
    if (Array.isArray(item.services) && item.services.length > 0) {
        return item.services.join(", ");
    }
    return item.services || "";
}

function renderCalendar() {
    setDateLabel();

    const startHour = 9;
    const totalHours = 12;
    const rowHeight = 90;
    const totalHeight = totalHours * rowHeight;
    const staffCount = techniciansRaw.length > 0 ? techniciansRaw.length : 5;

    const staffRow =
        techniciansRaw.length > 0
            ? `
        <div class="staff-row" style="--staff-count:${staffCount}">
          <div class="time-spacer"></div>
          ${techniciansRaw
                .map(
                    (tech, index) => `
                <div class="staff-col">
                  <div class="staff-avatar ${getAvatarClass(index)}">${getInitials(tech.full_name)}</div>
                  <span>${tech.full_name}</span>
                </div>
              `
                )
                .join("")}
        </div>
      `
            : "";

    const times = Array.from({ length: totalHours }, (_, i) => {
        return `<div>${formatHourLabel(startHour + i)}</div>`;
    }).join("");

    const dailyAppointments = appointments.filter((appt) => {
        const dt = new Date(appt.appointment_time);
        return sameDay(dt, selectedDate);
    });

    const appointmentBlocks = dailyAppointments
        .map((appt, index) => {
            const dt = new Date(appt.appointment_time);
            const minutes = dt.getHours() * 60 + dt.getMinutes();
            const baseMinutes = startHour * 60;
            let top = ((minutes - baseMinutes) / 60) * rowHeight;

            if (top < 0) top = 0;
            if (top > totalHeight - 86) top = totalHeight - 86;

            let columnIndex = index % staffCount;
            const calendarTechnicianId = appt.technician_id || appt.preferred_technician_id;
            if (calendarTechnicianId && techniciansRaw.length) {
                const foundIndex = techniciansRaw.findIndex(
                    (t) => Number(t.id) === Number(calendarTechnicianId)
                );
                if (foundIndex >= 0) columnIndex = foundIndex;
            }

            const leftPercent = (100 / staffCount) * columnIndex;

            const timeText = dt.toLocaleTimeString([], {
                hour: "numeric",
                minute: "2-digit",
            });

            const categoryText = appt.service_category || appt.service_name || "Appointment";

            return `
        <div class="appointment color-${columnIndex % 5}" data-id="${appt.id}" style="left:${leftPercent}%; top:${top}px; height:86px;">
          <strong>${timeText}</strong>
          <span>${appt.customer_name}</span>
          <small>${categoryText}</small>
        </div>
      `;
        })
        .join("");

    const activeTurns = sameDay(selectedDate, new Date())
        ? todayTurns.filter((turn) => ["assigned", "in_service"].includes(turn.status))
        : [];

    const turnBlocks = activeTurns
        .map((turn) => {
            if (!turn.technician_id || !techniciansRaw.length) return "";

            const foundIndex = techniciansRaw.findIndex(
                (t) => Number(t.id) === Number(turn.technician_id)
            );
            if (foundIndex < 0) return "";

            const leftPercent = (100 / staffCount) * foundIndex;
            const created = new Date(turn.created_at);
            const minutes = created.getHours() * 60 + created.getMinutes();
            const baseMinutes = startHour * 60;
            let top = ((minutes - baseMinutes) / 60) * rowHeight;

            if (top < 0) top = 0;
            if (top > totalHeight - 74) top = totalHeight - 74;

            return `
        <div class="appointment color-${foundIndex % 5} live-turn-block ${turn.status === "in_service" ? "live-turn-in-service" : "live-turn-assigned"}"
             style="left:${leftPercent}%; top:${top}px; height:74px;">
          <strong>${turn.status === "in_service" ? "In Service" : "Assigned"}</strong>
          <span>${turn.customer_name}</span>
          <small>${turn.service_name}</small>
        </div>
      `;
        })
        .join("");

    let currentTimeLine = "";
    const now = new Date();

    if (sameDay(selectedDate, now)) {
        const nowMinutes = now.getHours() * 60 + now.getMinutes();
        const baseMinutes = startHour * 60;
        const minutesFromStart = nowMinutes - baseMinutes;

        if (minutesFromStart >= 0 && minutesFromStart <= totalHours * 60) {
            const top = (minutesFromStart / 60) * rowHeight;
            currentTimeLine = `
        <div class="current-time-line" style="top:${top}px;">
          <span class="current-time-dot"></span>
        </div>
      `;
        }
    }

    calendarWrapper.innerHTML = `
    <div class="calendar-board">
      ${staffRow}
      <div class="calendar-grid" style="grid-template-columns: 90px 1fr;">
        <div class="times">${times}</div>
        <div class="grid" style="height:${totalHeight}px; --staff-count:${staffCount};">
          <div class="grid-lines" style="background-size: calc(100% / ${staffCount}) 100%, 100% 90px;"></div>
          ${currentTimeLine}
          ${appointmentBlocks}
          ${turnBlocks}
        </div>
      </div>
    </div>
  `;

    calendarWrapper.querySelectorAll(".appointment[data-id]").forEach((block) => {
        block.addEventListener("click", () => {
            const apptId = Number(block.dataset.id);
            const appt = appointments.find((item) => item.id === apptId);
            if (appt) openAppointmentModal(appt);
        });
    });
}

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

    if (!validateScheduleSelection()) {
        return;
    }

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
        skills: techSkills?.value?.trim() || null,
        specialties: selectedSpecialties,
        start_date: displayDateToISO(techStartDate.value) || null,
        status: techStatus.value,
        availability: dateOffAvailability || techAvailability?.value || (techStatus.value === "active" ? "available today" : "off today"),
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

    const payload = {
        customer_name: customerName,
        customer_phone: customerPhone,
        service_name: selectedServices,
        service_category: selectedServices,
        people_count: Number(appointmentPeopleCount?.value || 1),
        appointment_time: appointmentTimeApiValue,
        customer_type: "new",
        note: null,
        special_requests: specialRequests.value.trim() || null,
        allergies: allergies.value.trim() || null,
        technician_id: null,
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
