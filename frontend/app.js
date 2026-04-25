const API_BASE = "http://127.0.0.1:8001";
const CHECKIN_API_BASE = "http://127.0.0.1:8000";

const calendarView = document.getElementById("calendarView");
const customerListView = document.getElementById("customerListView");
const technicianView = document.getElementById("technicianView");
const appointmentView = document.getElementById("appointmentView");
const inventoryView = document.getElementById("inventoryView");
const checkoutView = document.getElementById("checkoutView");


const navCustomerList = document.getElementById("navCustomerList");
const navTechnician = document.getElementById("navTechnician");
const navAppointment = document.getElementById("navAppointment");
const navInventory = document.getElementById("navInventory");
const navCheckout = document.getElementById("navCheckout");

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
const checkoutNote = document.getElementById("checkout_note");

const checkoutGross = document.getElementById("checkoutGross");
const checkoutDiscount = document.getElementById("checkoutDiscount");
const checkoutNet = document.getElementById("checkoutNet");
const checkoutTechShare = document.getElementById("checkoutTechShare");
const checkoutSalonShare = document.getElementById("checkoutSalonShare");
const checkoutSalonActual = document.getElementById("checkoutSalonActual");
const checkoutTechTotal = document.getElementById("checkoutTechTotal");
const checkoutCustomerPays = document.getElementById("checkoutCustomerPays");
const checkoutReadyList = document.getElementById("checkoutReadyList");

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
const queueAutoAssignBtn = document.getElementById("queueAutoAssignBtn");

const techIdInput = document.getElementById("tech_id");
const techName = document.getElementById("tech_name");
const techPhone = document.getElementById("tech_phone");
const techSkills = document.getElementById("tech_skills");
const techStartDate = document.getElementById("tech_start_date");
const techStatus = document.getElementById("tech_status");
const techAvailability = document.getElementById("tech_availability");
const techSchedule = document.getElementById("tech_schedule");
const techSpecialties = document.getElementById("tech_specialties");

const techSearch = document.getElementById("techSearch");
const techFilterSpecialty = document.getElementById("techFilterSpecialty");
const techFilterStatus = document.getElementById("techFilterStatus");
const cancelEditBtn = document.getElementById("cancelEditBtn");
const techFormTitle = document.getElementById("techFormTitle");
const saveTechBtn = document.getElementById("saveTechBtn");

const addSpecialtyBtn = document.getElementById("addSpecialtyBtn");
const newSpecialtyInput = document.getElementById("new_specialty_input");

const appointmentIdInput = document.getElementById("appointment_id");
const appointmentFormTitle = document.getElementById("appointmentFormTitle");
const cancelAppointmentEditBtn = document.getElementById("cancelAppointmentEditBtn");
const saveAppointmentBtn = document.getElementById("saveAppointmentBtn");

const appointmentTechnician = document.getElementById("appointment_technician");
const preferredTechnician = document.getElementById("preferred_technician_id");

const customerNameInput = document.getElementById("customer_name");
const customerPhoneInput = document.getElementById("customer_phone");
const appointmentTimeInput = document.getElementById("appointment_time");
const customerType = document.getElementById("customer_type");
const specialRequests = document.getElementById("special_requests");
const allergies = document.getElementById("allergies");
const appointmentNote = document.getElementById("appointment_note");
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

let inventoryItems = [];

const DEFAULT_SPECIALTIES = [
  "manicure / pedicure (gel)",
  "acrylic",
  "dipping",
  "acrylic (nail art)",
  "hard gel",
  "builder gel",
  "gel x",
  "waxing",
  "facial",
];

function showView(view) {
  calendarView.classList.remove("active-view");
  customerListView.classList.remove("active-view");
  technicianView.classList.remove("active-view");
  appointmentView.classList.remove("active-view");
  inventoryView.classList.remove("active-view");
  checkoutView.classList.remove("active-view");

  navCustomerList.classList.remove("active");
  navTechnician.classList.remove("active");
  navAppointment.classList.remove("active");
  navInventory.classList.remove("active");
  navCheckout.classList.remove("active");

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
  await loadTechniciansRaw();
  await loadTodayTurns();
  await loadLiveCheckinQueue();
  showView("customerList");
});
navTechnician?.addEventListener("click", async () => {
  await loadTechnicians();
  showView("technician");
});

navAppointment?.addEventListener("click", async () => {
  await loadTechniciansRaw();
  populateAppointmentTechnicianDropdown();
  resetAppointmentForm();
  showView("appointment");
});

document.querySelectorAll(".back-btn").forEach((btn) => {
  btn.addEventListener("click", async () => {
    await loadAll();
    showView("calendar");
  });
});


function formatMoney(value) {
  return `$${Number(value || 0).toFixed(2)}`;
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
  inventoryPurchaseDate.value = item.purchase_date || "";

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
      <td>${item.purchase_date || "-"}</td>
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
    purchase_date: inventoryPurchaseDate.value || null,
    low_stock_level: 3
  };

  if (!itemData.item_name || !itemData.category) {
    showCuteNotification("Please fill in item name and category.", "Oops");
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


function populatePreferredTechSelect(excludeTechnicianId = null) {
  if (!preferredTechSelect) return;

  preferredTechSelect.innerHTML = `<option value="">Select technician</option>`;

  const availableTechs = techniciansRaw.filter((tech) => {
    const status = String(tech.status || "").trim().toLowerCase();
    const availability = String(tech.availability || "").trim().toLowerCase();

    const isAvailable = status === "active" && availability === "available today";
    const isExcluded = excludeTechnicianId && Number(tech.id) === Number(excludeTechnicianId);

    return isAvailable && !isExcluded;
  });

  if (!availableTechs.length) {
    const option = document.createElement("option");
    option.value = "";
    option.textContent = "No available technicians today";
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

  updateCheckoutSummary();
}

function getCheckoutCalculation() {
  const gross = Number(checkoutSubtotal?.value || 0);
  const discountType = checkoutDiscountType?.value || "none";
  const discountValue = Number(checkoutDiscountValue?.value || 0);
  const discountPaidBy = checkoutDiscountPaidBy?.value || "owner";
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

  let techShare = 0;
  let salonShare = 0;
  let salonActual = 0;

  if (discountPaidBy === "owner") {
    techShare = gross * 0.6;
    salonShare = gross * 0.4;
    salonActual = salonShare - discountAmount;
  } else {
    techShare = netService * 0.6;
    salonShare = netService * 0.4;
    salonActual = salonShare;
  }

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
    note: checkoutNote?.value.trim() || null
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
  await loadLiveCheckinQueue();
  renderCheckoutReadyList();

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

  const assignedTech = techniciansRaw.find((t) => t.id === appt.technician_id);
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
    <p><strong>Assigned Technician:</strong> ${assignedTech?.full_name || "-"}</p>
    <p><strong>Preferred Technician:</strong> ${preferredTech?.full_name || "-"}</p>
    <p><strong>Customer Type:</strong> ${appt.customer_type || "-"}</p>
    <p><strong>Special Requests:</strong> ${appt.special_requests || "-"}</p>
    <p><strong>Allergies:</strong> ${appt.allergies || "-"}</p>
    <p><strong>Note:</strong> ${appt.note || "-"}</p>
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
  const classes = ["coral", "gold", "teal", "blue", "pink"];
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
  if (!value) return "";
  const d = new Date(value);
  const year = d.getFullYear();
  const month = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  const hours = String(d.getHours()).padStart(2, "0");
  const mins = String(d.getMinutes()).padStart(2, "0");
  return `${year}-${month}-${day}T${hours}:${mins}`;
}

function formatLiveCheckinTime(dateString) {
  const date = new Date(dateString);
  return date.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
}

function normalizeServiceForMatch(serviceName) {
  return (serviceName || "").trim().toLowerCase();
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

    return sameCustomer && ["waiting", "assigned", "in_service"].includes(turn.status);
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

function fillCheckoutFormFromTurn(turn) {
  if (!turn) return;

  const linkedAppointment = getAppointmentForTurn(turn);

  if (checkoutIdInput) checkoutIdInput.value = "";
  if (checkoutCustomerName) checkoutCustomerName.value = turn.customer_name || "";
  if (checkoutCustomerPhone) checkoutCustomerPhone.value = turn.customer_phone || "";
  if (checkoutTechnicianId) checkoutTechnicianId.value = turn.technician_id ? String(turn.technician_id) : "";
  if (checkoutTechnicianName) checkoutTechnicianName.value = getTechnicianNameById(turn.technician_id);
  if (checkoutTurnId) checkoutTurnId.value = turn.id || "";
  if (checkoutAppointmentId) checkoutAppointmentId.value = linkedAppointment?.id || "";
  if (checkoutServiceName) checkoutServiceName.value = turn.service_name || "";
  if (checkoutPaymentMethod) checkoutPaymentMethod.value = "cash";
if (checkoutDiscountType) checkoutDiscountType.value = turn.discount_type || "none";
if (checkoutDiscountValue) checkoutDiscountValue.value = Number(turn.discount_value || 0);
if (checkoutDiscountPaidBy) checkoutDiscountPaidBy.value = "owner";
if (checkoutTip) checkoutTip.value = 0;
if (checkoutSubtotal) checkoutSubtotal.value = 0;
if (checkoutNote) checkoutNote.value = turn.discount_label || "";

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

async function autoAssignCheckin(item, silent = false) {
  const serviceName = getCombinedServiceName(item);
  if (!serviceName) {
    if (!silent) {
      showCuteNotification("No service found for this customer.", "Oops");
    }
    return false;
  }

  try {
    await fetchJson(`${API_BASE}/turns/assign-auto`, {
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

    if (!silent) {
      showCuteNotification("Customer auto-assigned successfully.");
    }
    return true;
  } catch (error) {
    if (!silent) {
      showCuteNotification(error.message || "Failed to auto assign customer.", "Oops");
    }
    return false;
  }
}

async function autoAssignAllWaitingCheckins() {
  const unassignedItems = liveCheckins.filter((item) => !getTurnForCustomer(item));

  if (!unassignedItems.length) {
    showCuteNotification("No waiting customers to auto assign.", "Notice");
    return;
  }

  let assignedCount = 0;
  let failedCount = 0;

  for (const item of unassignedItems) {
    const success = await autoAssignCheckin(item, true);
    if (success) {
      assignedCount += 1;
    } else {
      failedCount += 1;
    }
  }

  await loadAll();

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

  preferredTechModalMode = "assign";
  pendingPreferredCheckinItem = item;
  pendingReassignTurnId = null;
  currentReassignTechnicianId = null;

  populatePreferredTechSelect();

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

  populatePreferredTechSelect(currentReassignTechnicianId);

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
renderCalendar();
showView("customerList");
showCuteNotification("Preferred technician assigned successfully.");
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

function renderCheckoutReadyList() {
  if (!checkoutReadyList) return;

  const readyTurns = todayTurns.filter((turn) =>
    ["assigned", "in_service"].includes(turn.status)
  );

  if (!readyTurns.length) {
    checkoutReadyList.innerHTML = `
      <div class="tech-card">
        <div class="tech-card-top">
          <div class="tech-main-info">
            <div class="tech-title-row">
              <h4>No customers ready</h4>
            </div>
            <p class="tech-subtext">No assigned or in-service customers right now.</p>
          </div>
        </div>
      </div>
    `;
    return;
  }

  checkoutReadyList.innerHTML = readyTurns
    .map((turn) => {
      const techName = getTechnicianNameById(turn.technician_id);
      const statusText = String(turn.status || "").replace("_", " ");
      const linkedAppointment = getAppointmentForTurn(turn);

      return `
        <div class="tech-card dispatch-card">
          <div class="tech-card-top">
            <div class="tech-avatar-wrap">
              <div class="tech-avatar-fallback">${getInitials(turn.customer_name)}</div>
            </div>

            <div class="tech-main-info">
              <div class="tech-title-row">
                <h4>${turn.customer_name}</h4>
                <span class="status-chip dispatch-status-${turn.status}">${statusText}</span>
              </div>
              <p class="tech-subtext">Phone: ${turn.customer_phone || "-"}</p>
            </div>
          </div>

          <div class="tech-meta">
            <p><strong>Technician:</strong> ${techName}</p>
            <p><strong>Service:</strong> ${turn.service_name || "-"}</p>
          </div>

          <div class="dispatch-card-center">
            <button
              class="mini-btn checkout-select-btn"
              type="button"
              data-turn-id="${turn.id}"
            >
              Select for Checkout
            </button>
          </div>
        </div>
      `;
    })
    .join("");

  document.querySelectorAll(".checkout-select-btn").forEach((btn) => {
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

  liveCheckinQueue.innerHTML = checkins
    .map((item) => {
      const linkedTurn = getTurnForCustomer(item);
      const status = linkedTurn?.status || "waiting";
      const assignedTechName = linkedTurn?.technician_id
        ? getTechnicianNameById(linkedTurn.technician_id)
        : "Not assigned";

      const actionArea = !linkedTurn
        ? `
          <div class="dispatch-card-center">
            <button class="mini-btn queue-preferred-btn" data-name="${item.full_name}" data-phone="${item.phone_number}">
              Assign Preferred
            </button>
          </div>
        `
        : `
          <div class="dispatch-actions">
            ${status !== "done" ? `<button class="mini-btn queue-reassign-btn" data-turn-id="${linkedTurn.id}">Reassign</button>` : ""}
          </div>
        `;

      return `
        <div class="tech-card dispatch-card">
          <div class="tech-card-top">
            <div class="tech-avatar-wrap">
              <div class="tech-avatar-fallback">${getInitials(item.full_name)}</div>
            </div>

            <div class="tech-main-info">
              <div class="tech-title-row">
                <h4>#${item.position} ${item.full_name}</h4>
                <span class="status-chip dispatch-status-${status}">${status.replace("_", " ")}</span>
              </div>
              <p class="tech-subtext">Phone: ${item.phone_number || "-"}</p>
              <p class="tech-subtext">Checked in: ${formatLiveCheckinTime(item.checked_in_at)}</p>
            </div>
          </div>

          <div class="tech-meta">
            <p><strong>Services:</strong> ${(item.services || []).join(", ") || "-"}</p>
            <p><strong>Assigned Tech:</strong> ${assignedTechName}</p>
          </div>

          ${actionArea}
        </div>
      `;
    })
    .join("");

  document.querySelectorAll(".queue-preferred-btn").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const item = checkins.find(
        (entry) =>
          entry.full_name === btn.dataset.name &&
          String(entry.phone_number || "") === String(btn.dataset.phone || "")
      );
      if (item) await assignPreferredCheckin(item);
    });
  });

  document.querySelectorAll(".queue-reassign-btn").forEach((btn) => {
  btn.addEventListener("click", async () => {
    await openReassignModal(Number(btn.dataset.turnId));
  });
});
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
  DEFAULT_SPECIALTIES.forEach((specialty) => {
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

  const existing = Array.from(
    techSpecialties.querySelectorAll(".checkbox-item")
  ).find((item) => item.dataset.value === normalized);

  if (existing) {
    const checkbox = existing.querySelector('input[type="checkbox"]');
    if (checkbox) checkbox.checked = checked;
    return;
  }

  const isDefault = DEFAULT_SPECIALTIES.includes(normalized);
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
  const map = {
    "available today": "badge-available",
    "on break": "badge-break",
    "busy": "badge-busy",
    "off today": "badge-off",
  };
  return map[availability] || "badge-default";
}

function getTechnicianAvatar(tech) {
  if (tech.profile_photo) {
    return `<img src="${tech.profile_photo}" alt="${tech.full_name}" class="tech-avatar-img" />`;
  }
  return `<div class="tech-avatar-fallback">${getInitials(tech.full_name)}</div>`;
}

function resetTechnicianForm() {
  technicianForm.reset();
  techIdInput.value = "";
  techFormTitle.textContent = "Add Technician";
  saveTechBtn.textContent = "Save Technician";
  cancelEditBtn.classList.add("hidden");
  setSelectedSpecialties("");
  techStatus.value = "off";
  techAvailability.value = "off today";
}

function formatDateInputValue(value) {
  if (!value) return "";

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

  if (value < minDate || value > maxDate) {
    techStartDate.setCustomValidity("Please enter a valid year between 2000 and 2100.");
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

function fillTechnicianForm(tech) {
  techIdInput.value = tech.id;
  techName.value = tech.full_name || "";
  techPhone.value = tech.phone || "";
  techSkills.value = tech.skills || "";
  techStartDate.value = formatDateInputValue(tech.start_date);
  techStatus.value = tech.status || "off";
  techAvailability.value = tech.availability || "off today";
  techSchedule.value = tech.work_schedule || "";
  setSelectedSpecialties(tech.specialties || "");

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
  appointmentTechnician.value = appt.technician_id || "";
  preferredTechnician.value = appt.preferred_technician_id || "";
  customerType.value = appt.customer_type || "new";
  if (appointmentPeopleCount) appointmentPeopleCount.value = appt.people_count || 1;
  specialRequests.value = appt.special_requests || "";
  allergies.value = appt.allergies || "";
  appointmentNote.value = appt.note || "";

  appointmentFormTitle.textContent = "Edit Appointment";
  saveAppointmentBtn.textContent = "Update Appointment";
  cancelAppointmentEditBtn.classList.remove("hidden");
}

async function loadTechniciansRaw() {
  techniciansRaw = await fetchJson(`${API_BASE}/technicians`);
}

function populateAppointmentTechnicianDropdown() {
  appointmentTechnician.innerHTML = `<option value="">Select technician</option>`;
  preferredTechnician.innerHTML = `<option value="">Select preferred technician</option>`;

  techniciansRaw.forEach((tech) => {
    const option1 = document.createElement("option");
    option1.value = tech.id;
    option1.textContent = tech.full_name;
    appointmentTechnician.appendChild(option1);

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
    card.className = "tech-card";

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
        <p><strong>Specialties:</strong> ${tech.specialties || "-"}</p>
        <p><strong>Start date:</strong> ${tech.start_date || "-"}</p>
        <p><strong>Schedule:</strong> ${tech.work_schedule || "-"}</p>
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
          ${tech.availability || "unknown"}
        </span>
      </div>

      <div class="tech-actions">
        <button class="ghost-btn tech-edit-btn" data-id="${tech.id}">Edit</button>
        <button class="ghost-btn tech-delete-btn" data-id="${tech.id}">Delete</button>
        <button class="ghost-btn tech-schedule-btn" data-id="${tech.id}">Schedule</button>
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
      const today = new Date().toISOString().split("T")[0];

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
      if (appt.technician_id && techniciansRaw.length) {
        const foundIndex = techniciansRaw.findIndex(
        (t) => Number(t.id) === Number(appt.technician_id)
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

  const activeTurns = todayTurns.filter((turn) => ["assigned", "in_service"].includes(turn.status));

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
        <div class="appointment live-turn-block ${turn.status === "in_service" ? "live-turn-in-service" : "live-turn-assigned"}"
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
  await checkApi();

  try {
    syncDefaultSpecialtiesToFilter();
    await loadTechnicians();
    await loadAppointments();
    await loadTodayTurns();
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

  const payload = {
    full_name: fullName,
    phone: phoneRaw || null,
    skills: techSkills.value.trim() || null,
    specialties: selectedSpecialties,
    start_date: techStartDate.value || null,
    status: techStatus.value,
    availability: techAvailability.value,
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
  const note = appointmentNote.value.trim();
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

  const payload = {
    customer_name: customerName,
    customer_phone: customerPhone,
    service_name: selectedServices,
    service_category: selectedServices,
    people_count: Number(appointmentPeopleCount?.value || 1),
    appointment_time: appointmentTime,
    customer_type: customerType.value || "new",
    note: note || null,
    special_requests: specialRequests.value.trim() || null,
    allergies: allergies.value.trim() || null,
    technician_id: appointmentTechnician.value ? Number(appointmentTechnician.value) : null,
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
setInterval(loadLiveCheckinQueue, 5000);
setInterval(async () => {
  await loadTodayTurns();
  await loadLiveCheckinQueue();
  if (calendarView.classList.contains("active-view")) {
    renderCalendar();
  }
}, 60000);
showView("calendar");