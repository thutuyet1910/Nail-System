// dom.js: References to elements in index.html

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

const notificationsBtn = document.getElementById("notificationsBtn");
const notificationBadge = document.getElementById("notificationBadge");
const notificationsPanel = document.getElementById("notificationsPanel");
const notificationsList = document.getElementById("notificationsList");
const markAllNotificationsRead = document.getElementById("markAllNotificationsRead");
const closeNotifications = document.getElementById("closeNotifications");
const logoutBtn = document.getElementById("logoutBtn");

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

const saveCheckoutBtn = document.getElementById("saveCheckoutBtn");

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

const checkoutTip = document.getElementById("checkout_tip");

const checkoutGross = document.getElementById("checkoutGross");

const checkoutDiscount = document.getElementById("checkoutDiscount");

const checkoutNet = document.getElementById("checkoutNet");

const checkoutTechShare = document.getElementById("checkoutTechShare");

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

const techStartDate = document.getElementById("tech_start_date");

const techStatus = document.getElementById("tech_status");

const techDateOffStart = document.getElementById("tech_date_off_start");

const techDateOffEnd = document.getElementById("tech_date_off_end");

const techSchedule = document.getElementById("tech_schedule"); // hidden input for storing schedule

const techSpecialties = document.getElementById("tech_specialties");

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
