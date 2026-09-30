const phoneForm = document.getElementById("phone-form");
const customerForm = document.getElementById("new-customer-form");
const existingCustomerForm = document.getElementById("existing-customer-form");
const messageBox = document.getElementById("message");

const checkinOrderList = document.getElementById("checkin-order-list");
const phoneScreen = document.getElementById("phone-screen");
const formScreen = document.getElementById("form-screen");
const existingScreen = document.getElementById("existing-screen");
const thankYouScreen = document.getElementById("thank-you-screen");
const thankYouMessage = document.getElementById("thank-you-message");
const existingCustomerName = document.getElementById("existing-customer-name");

const birthdayModal = document.getElementById("birthday-modal");
const birthdayModalText = document.getElementById("birthday-modal-text");
const closeBirthdayModalBtn = document.getElementById("close-birthday-modal");
const backHomeBtn = document.getElementById("back-home-btn");

const successModal = document.getElementById("success-modal");
const successModalText = document.getElementById("success-modal-text");
const closeSuccessModalBtn = document.getElementById("close-success-modal");

const carouselImage = document.getElementById("carousel-image");
const adBadge = document.getElementById("ad-badge");
const adTitle = document.getElementById("ad-title");
const adText = document.getElementById("ad-text");
const phoneInput = document.getElementById("phone_number");

const existingCustomerProfile = document.getElementById("existing-customer-profile");

const newCustomerServiceScreen = document.getElementById("new-customer-service-screen");
const newServiceSearchInput = document.getElementById("new-service-search");
const newServiceList = document.getElementById("new-service-list");
const backToNewCustomerFormBtn = document.getElementById("back-to-new-customer-form-btn");
const continueToNewReviewBtn = document.getElementById("continue-to-new-review-btn");

const newCustomerReviewScreen = document.getElementById("new-customer-review-screen");
const reviewFullName = document.getElementById("review-full-name");
const reviewDob = document.getElementById("review-dob");
const reviewEmail = document.getElementById("review-email");
const reviewReferralCode = document.getElementById("review-referral-code");
const reviewServices = document.getElementById("review-services");
const editNewCustomerBtn = document.getElementById("edit-new-customer-btn");
const confirmNewCustomerBtn = document.getElementById("confirm-new-customer-btn");

const existingCustomerServiceScreen = document.getElementById("existing-customer-service-screen");
const existingServiceSearchInput = document.getElementById("existing-service-search");
const existingServiceList = document.getElementById("existing-service-list");
const backToExistingCustomerBtn = document.getElementById("back-to-existing-customer-btn");
const continueToExistingReviewBtn = document.getElementById("continue-to-existing-review-btn");

const existingCustomerReviewScreen = document.getElementById("existing-customer-review-screen");
const existingReviewFullName = document.getElementById("existing-review-full-name");
const existingReviewPhone = document.getElementById("existing-review-phone");
const existingReviewEmail = document.getElementById("existing-review-email");
const existingReviewReferralCode = document.getElementById("existing-review-referral-code");
const existingReviewServices = document.getElementById("existing-review-services");
const editExistingCustomerBtn = document.getElementById("edit-existing-customer-btn");
const confirmExistingCustomerBtn = document.getElementById("confirm-existing-customer-btn");

const updateProfileScreen = document.getElementById("update-profile-screen");
const updateProfileForm = document.getElementById("update-profile-form");
const updateProfileBtn = document.getElementById("update-profile-btn");
const cancelUpdateProfileBtn = document.getElementById("cancel-update-profile-btn");
const updateFullNameInput = document.getElementById("update_full_name");
const updatePhoneInput = document.getElementById("update_phone");
const updateEmailInput = document.getElementById("update_email");

const dobInput = document.getElementById("date_of_birth");

const API_BASE = "http://127.0.0.1:8000";
const CREATE_CUSTOMER_URL = `${API_BASE}/customers/new`;

let phoneNumber = "";
let existingCustomer = null;
let pendingNewCustomerPayload = null;
let pendingExistingReferralCode = "";

let availableServices = [];
let selectedNewServiceIds = [];
let selectedExistingServiceIds = [];

// Remembers the last thank-you message so it can be re-translated
let lastThankYou = null;

const carouselSlides = [
  { image: "https://images.unsplash.com/photo-1604654894610-df63bc536371?auto=format&fit=crop&w=1400&q=80", key: "slide1" },
  { image: "https://images.unsplash.com/photo-1522337660859-02fbefca4702?auto=format&fit=crop&w=1400&q=80", key: "slide2" },
  { image: "https://images.unsplash.com/photo-1519014816548-bf5fe059798b?auto=format&fit=crop&w=1400&q=80", key: "slide3" },
  { image: "https://images.unsplash.com/photo-1610992015732-2449b76344bc?auto=format&fit=crop&w=1400&q=80", key: "slide4" }
];

let carouselIndex = 0;

const localeMap = { en: "en-US", vi: "vi-VN", es: "es-ES" };

// Template helper: tf("welcomeBack", { name: "Anna" })
function tf(key, vars = {}) {
  return t(key).replace(/\{(\w+)\}/g, (_, k) => vars[k] ?? "");
}

// ── Helpers ───────────────────────────────────────────────────

function formatPhone(value) {
  const digits = value.replace(/\D/g, "").slice(0, 10);

  if (digits.length === 0) return "";
  if (digits.length <= 3) return `(${digits}`;
  if (digits.length <= 6) return `(${digits.slice(0, 3)}) ${digits.slice(3)}`;
  return `(${digits.slice(0, 3)}) ${digits.slice(3, 6)}-${digits.slice(6)}`;
}

function rawDigits(value) {
  return value.replace(/\D/g, "");
}

function safeText(value) {
  return value && String(value).trim()
    ? value
    : t("notProvided");
}

function getTodayISODate() {
  const today = new Date();
  const year = today.getFullYear();
  const month = String(today.getMonth() + 1).padStart(2, "0");
  const day = String(today.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function formatDateForDisplay(dateValue) {
  if (!dateValue) return t("notProvided");

  const parts = String(dateValue).split("-");
  if (parts.length !== 3) return t("notProvided");

  const [year, month, day] = parts.map(Number);
  const date = new Date(year, month - 1, day);

  if (Number.isNaN(date.getTime())) return t("notProvided");

  return date.toLocaleDateString(localeMap[currentLanguage] || "en-US", {
    year: "numeric",
    month: "long",
    day: "numeric"
  });
}

function isValidDOB(dateString) {
  if (!dateString || typeof dateString !== "string") return false;

  if (!/^\d{4}-\d{2}-\d{2}$/.test(dateString)) return false;

  const [yearStr, monthStr, dayStr] = dateString.split("-");
  const year = Number(yearStr);
  const month = Number(monthStr);
  const day = Number(dayStr);

  if (yearStr.length !== 4) return false;
  if (year < 1900 || year > new Date().getFullYear()) return false;
  if (month < 1 || month > 12) return false;
  if (day < 1 || day > 31) return false;

  const date = new Date(year, month - 1, day);

  if (
    date.getFullYear() !== year ||
    date.getMonth() + 1 !== month ||
    date.getDate() !== day
  ) {
    return false;
  }

  const today = new Date();
  today.setHours(0, 0, 0, 0);
  date.setHours(0, 0, 0, 0);

  if (date > today) return false;

  return true;
}

function setDOBLimits() {
  if (!dobInput) return;

  dobInput.max = getTodayISODate();
  dobInput.min = "1900-01-01";
  dobInput.setAttribute("maxlength", "10");
  dobInput.setAttribute("inputmode", "numeric");
}

function formatMaskedDate(value) {
  const digits = String(value || "").replace(/\D/g, "").slice(0, 8);
  if (digits.length <= 2) return digits;
  if (digits.length <= 4) return `${digits.slice(0, 2)}-${digits.slice(2)}`;
  return `${digits.slice(0, 2)}-${digits.slice(2, 4)}-${digits.slice(4)}`;
}

function displayDateToISO(value) {
  if (/^\d{4}-\d{2}-\d{2}$/.test(value || "")) return value;
  if (!/^\d{2}-\d{2}-\d{4}$/.test(value || "")) return "";
  const [month, day, year] = value.split("-");
  return `${year}-${month}-${day}`;
}

function limitDOBYearValue() {
  if (!dobInput?.value) return;
  dobInput.value = formatMaskedDate(dobInput.value);
}

function validateDOBInput() {
  if (!dobInput) return true;

  limitDOBYearValue();
  const value = displayDateToISO(dobInput.value);

  if (!dobInput.value) {
    dobInput.setCustomValidity(t("dobRequired"));
    return false;
  }

  if (!isValidDOB(value)) {
    dobInput.setCustomValidity(t("dobInvalid"));
    return false;
  }

  dobInput.setCustomValidity("");
  return true;
}

function getErrorMessage(data, fallback = "Something went wrong.") {
  if (!data) return fallback;

  if (typeof data === "string") return data;

  if (Array.isArray(data.detail)) {
    return data.detail
      .map(item => {
        if (typeof item === "string") return item;
        if (item?.msg) return item.msg;
        return JSON.stringify(item);
      })
      .join(", ");
  }

  if (typeof data.detail === "string") return data.detail;

  if (data.detail && typeof data.detail === "object") {
    if (data.detail.msg) return data.detail.msg;
    return JSON.stringify(data.detail);
  }

  return fallback;
}

// Service names are intentionally kept exactly as returned by the API
function getServiceNameById(id) {
  const service = availableServices.find(item => item.id === id);
  return service ? service.name : `Service ${id}`;
}

function formatServiceNamesFromIds(ids) {
  if (!ids || ids.length === 0) {
    return t("noServicesSelected");
  }
  return ids.map(getServiceNameById).join(", ");
}

// ── Services ──────────────────────────────────────────────────

async function loadServices() {
  try {
    const response = await fetch(`${API_BASE}/services`);
    const data = await response.json();

    if (!response.ok) {
      throw new Error(getErrorMessage(data, "Failed to load services."));
    }

    availableServices = Array.isArray(data) ? data : [];

    renderServiceList(newServiceList, selectedNewServiceIds, newServiceSearchInput?.value || "");
    renderServiceList(existingServiceList, selectedExistingServiceIds, existingServiceSearchInput?.value || "");
  } catch (error) {
    console.error("Failed to load services:", error);
    if (newServiceList) {
      newServiceList.innerHTML = `<p class="queue-empty">${t("unableServices")}</p>`;
    }
    if (existingServiceList) {
      existingServiceList.innerHTML = `<p class="queue-empty">${t("unableServices")}</p>`;
    }
  }
}

function renderServiceList(container, selectedServiceIds, searchTerm = "") {
  if (!container) return;

  const normalizedSearch = searchTerm.trim().toLowerCase();

  const filteredServices = availableServices.filter(service =>
    service.name.toLowerCase().includes(normalizedSearch)
  );

  if (filteredServices.length === 0) {
    container.innerHTML =
      `<p class="queue-empty">${t("noMatchingServices")}</p>`;
    return;
  }

  container.innerHTML = filteredServices
    .map(service => {
      const checked = selectedServiceIds.includes(service.id) ? "checked" : "";
      const safeId = `service_${service.id}`;
      return `
        <label class="service-option" for="${container.id}_${safeId}">
          <input
            type="checkbox"
            id="${container.id}_${safeId}"
            value="${service.id}"
            ${checked}
          />
          <span>${service.name}</span>
        </label>
      `;
    })
    .join("");
}

function toggleServiceSelection(serviceId, selectedServiceIdsRef) {
  const index = selectedServiceIdsRef.indexOf(serviceId);

  if (index >= 0) {
    selectedServiceIdsRef.splice(index, 1);
  } else {
    selectedServiceIdsRef.push(serviceId);
  }
}

function bindServiceListSelection(container, getSelectedServiceIds, searchInput) {
  if (!container) return;

  container.addEventListener("change", (event) => {
    const target = event.target;
    if (!(target instanceof HTMLInputElement)) return;
    if (target.type !== "checkbox") return;

    const selectedServiceIdsRef = getSelectedServiceIds();
    const serviceId = Number(target.value);

    if (!Number.isInteger(serviceId) || serviceId <= 0) return;

    toggleServiceSelection(serviceId, selectedServiceIdsRef);

    renderServiceList(
      container,
      selectedServiceIdsRef,
      searchInput ? searchInput.value : ""
    );
  });
}

function showNewCustomerServiceScreen() {
  renderServiceList(newServiceList, selectedNewServiceIds, newServiceSearchInput?.value || "");
  hideAllMainScreens();
  newCustomerServiceScreen.style.display = "block";
  messageBox.textContent = "";
  messageBox.className = "message";
}

function showExistingCustomerServiceScreen() {
  renderServiceList(existingServiceList, selectedExistingServiceIds, existingServiceSearchInput?.value || "");
  hideAllMainScreens();
  existingCustomerServiceScreen.style.display = "block";
  messageBox.textContent = "";
  messageBox.className = "message";
}

function showNewCustomerReview(payload) {
  pendingNewCustomerPayload = payload;

  reviewFullName.textContent = safeText(payload.full_name);
  reviewDob.textContent = formatDateForDisplay(payload.date_of_birth);
  reviewEmail.textContent = safeText(payload.email);
  reviewReferralCode.textContent = safeText(payload.referral_code);
  reviewServices.textContent = formatServiceNamesFromIds(selectedNewServiceIds);

  hideAllMainScreens();
  newCustomerReviewScreen.style.display = "block";

  messageBox.textContent = "";
  messageBox.className = "message";
}

function showExistingCustomerReview() {
  if (!existingCustomer) return;

  existingReviewFullName.textContent = safeText(existingCustomer.full_name);
  existingReviewPhone.textContent = safeText(
    existingCustomer.phone_number_formatted || formatPhone(existingCustomer.phone_number || "")
  );
  existingReviewEmail.textContent = safeText(existingCustomer.email);
  existingReviewReferralCode.textContent = safeText(pendingExistingReferralCode);
  existingReviewServices.textContent = formatServiceNamesFromIds(selectedExistingServiceIds);

  hideAllMainScreens();
  existingCustomerReviewScreen.style.display = "block";

  messageBox.textContent = "";
  messageBox.className = "message";
}

// ── Carousel ──────────────────────────────────────────────────

function renderSlide(index) {
  if (!carouselImage) return;

  const slide = carouselSlides[index];
  carouselImage.style.backgroundImage = `url("${slide.image}")`;

  if (adBadge) adBadge.textContent = t(`${slide.key}Badge`);
  if (adTitle) adTitle.textContent = t(`${slide.key}Title`);
  if (adText) adText.textContent = t(`${slide.key}Text`);
}

function startCarousel() {
  if (!carouselImage) return;

  renderSlide(carouselIndex);

  setInterval(() => {
    carouselIndex = (carouselIndex + 1) % carouselSlides.length;
    renderSlide(carouselIndex);
  }, 4000);
}

// ── Modals & screens ──────────────────────────────────────────

function showBirthdayModal(fullName, amount) {
  if (!birthdayModal || !birthdayModalText) return;
  birthdayModalText.textContent = `Happy Birthday ${fullName}! You have $${amount} off today.`;
  birthdayModal.classList.remove("hidden");
}

function hideBirthdayModal() {
  if (!birthdayModal) return;
  birthdayModal.classList.add("hidden");
}

function showSuccessModal(text) {
  if (!successModal || !successModalText) return;
  successModalText.textContent = text;
  successModal.classList.remove("hidden");
}

function hideSuccessModal() {
  if (!successModal) return;
  successModal.classList.add("hidden");
}

function hideAllMainScreens() {
  phoneScreen.style.display = "none";
  formScreen.style.display = "none";
  newCustomerServiceScreen.style.display = "none";
  newCustomerReviewScreen.style.display = "none";
  existingScreen.style.display = "none";
  existingCustomerServiceScreen.style.display = "none";
  existingCustomerReviewScreen.style.display = "none";
  updateProfileScreen.style.display = "none";
  thankYouScreen.style.display = "none";
}

function showThankYouScreen(key, serviceIds) {
  lastThankYou = { key, ids: [...serviceIds] };
  hideAllMainScreens();
  thankYouScreen.style.display = "block";
  thankYouMessage.textContent = tf(key, {
    services: formatServiceNamesFromIds(lastThankYou.ids)
  });
}

function formatCheckInTime(dateString) {
  const date = new Date(dateString);
  return date.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
}

function renderExistingCustomerProfile(customer) {
  if (!existingCustomerProfile || !customer) return;

  existingCustomerProfile.innerHTML = `
    <div class="profile-row">
      <span class="profile-label">${t("name")}</span>
      <span class="profile-value">${safeText(customer.full_name)}</span>
    </div>
    <div class="profile-row">
      <span class="profile-label">${t("phone")}</span>
      <span class="profile-value">${safeText(customer.phone_number_formatted || formatPhone(customer.phone_number || ""))}</span>
    </div>
    <div class="profile-row">
      <span class="profile-label">${t("email")}</span>
      <span class="profile-value">${safeText(customer.email)}</span>
    </div>
    <div class="profile-row">
      <span class="profile-label">${t("birthday")}</span>
      <span class="profile-value">${formatDateForDisplay(customer.date_of_birth)}</span>
    </div>
  `;
}

function openExistingCustomerScreen() {
  if (!existingCustomer) return;

  existingCustomerName.textContent = tf("welcomeBack", { name: existingCustomer.full_name });
  renderExistingCustomerProfile(existingCustomer);

  hideAllMainScreens();
  existingScreen.style.display = "block";

  messageBox.textContent = "";
  messageBox.className = "message";
}

function populateUpdateProfileForm(customer) {
  if (!customer) return;
  updateFullNameInput.value = customer.full_name || "";
  updatePhoneInput.value = formatPhone(customer.phone_number || "");
  updateEmailInput.value = customer.email || "";
}

// ── Today's check-in list ─────────────────────────────────────

async function loadTodayCheckInOrder() {
  try {
    const response = await fetch(`${API_BASE}/today-checkins`);
    const data = await response.json();

    if (!response.ok) {
      throw new Error(getErrorMessage(data, "Failed to load today's check-in order."));
    }

    if (!data.checkins || data.checkins.length === 0) {
      checkinOrderList.innerHTML =
        `<p class="queue-empty">${t("noCustomers")}</p>`;
      return;
    }

    checkinOrderList.innerHTML = data.checkins
      .map(item => `
        <div class="queue-item">
          <div class="queue-item-left">
            <div class="queue-position">${item.position}</div>
            <div class="queue-name">${item.full_name}</div>
          </div>
          <div class="queue-time">${formatCheckInTime(item.checked_in_at)}</div>
        </div>
      `)
      .join("");

    checkinOrderList.querySelector(".queue-item:last-child")?.scrollIntoView({
      behavior: "smooth",
      block: "end"
    });
  } catch (error) {
    checkinOrderList.innerHTML = `<p class="queue-empty">${t("unableQueue")}</p>`;
  }
}

// ── Reset ─────────────────────────────────────────────────────

function resetToMainScreen() {
  customerForm.reset();
  existingCustomerForm.reset();
  phoneForm.reset();
  updateProfileForm.reset();

  if (phoneInput) phoneInput.value = "";
  if (dobInput) dobInput.value = "";
  if (newServiceSearchInput) newServiceSearchInput.value = "";
  if (existingServiceSearchInput) existingServiceSearchInput.value = "";

  selectedNewServiceIds.length = 0;
  selectedExistingServiceIds.length = 0;
  pendingExistingReferralCode = "";

  hideAllMainScreens();
  phoneScreen.style.display = "block";

  messageBox.textContent = "";
  messageBox.className = "message";

  phoneNumber = "";
  existingCustomer = null;
  pendingNewCustomerPayload = null;
  lastThankYou = null;
}

if (closeBirthdayModalBtn) {
  closeBirthdayModalBtn.addEventListener("click", hideBirthdayModal);
}

if (backHomeBtn) {
  backHomeBtn.addEventListener("click", resetToMainScreen);
}

if (closeSuccessModalBtn) {
  closeSuccessModalBtn.addEventListener("click", hideSuccessModal);
}

// ── Phone input formatting ────────────────────────────────────

if (phoneInput) {
  phoneInput.addEventListener("input", (e) => {
    e.target.value = formatPhone(e.target.value);
  });
}

if (updatePhoneInput) {
  updatePhoneInput.addEventListener("input", () => {
    updatePhoneInput.value = formatPhone(updatePhoneInput.value);
  });
}

// ── DOB input rules ───────────────────────────────────────────

setDOBLimits();

if (dobInput) {
  dobInput.addEventListener("input", validateDOBInput);
  dobInput.addEventListener("change", validateDOBInput);
}

// ── Service search + checkbox binding ────────────────────────

if (newServiceSearchInput) {
  newServiceSearchInput.addEventListener("input", () => {
    renderServiceList(newServiceList, selectedNewServiceIds, newServiceSearchInput.value);
  });
}

if (existingServiceSearchInput) {
  existingServiceSearchInput.addEventListener("input", () => {
    renderServiceList(existingServiceList, selectedExistingServiceIds, existingServiceSearchInput.value);
  });
}

bindServiceListSelection(newServiceList, () => selectedNewServiceIds, newServiceSearchInput);
bindServiceListSelection(existingServiceList, () => selectedExistingServiceIds, existingServiceSearchInput);

// ── Phone form ────────────────────────────────────────────────

phoneForm.addEventListener("submit", async (event) => {
  event.preventDefault();

  phoneNumber = rawDigits(phoneInput.value);

  if (phoneNumber.length !== 10) {
    messageBox.textContent = t("invalidPhone");
    messageBox.className = "message error";
    return;
  }

  messageBox.textContent = t("checkingPhone");
  messageBox.className = "message";

  try {
    const response = await fetch(
      `${API_BASE}/customers/by-phone/${encodeURIComponent(phoneNumber)}`
    );

    if (response.ok) {
      existingCustomer = await response.json();

      const statusResponse = await fetch(
        `${API_BASE}/customers/check-in-status/${encodeURIComponent(phoneNumber)}`
      );
      const statusData = await statusResponse.json();

      if (!statusResponse.ok) {
        throw new Error(getErrorMessage(statusData, "Failed to check today's status."));
      }

      if (statusData.already_checked_in_today) {
        messageBox.textContent = tf("alreadyCheckedIn", { name: statusData.full_name });
        messageBox.className = "message error";
        hideAllMainScreens();
        phoneScreen.style.display = "block";
        return;
      }

      openExistingCustomerScreen();
      return;
    }

    if (response.status === 404) {
      existingCustomer = null;
      pendingNewCustomerPayload = null;
      selectedNewServiceIds.length = 0;
      if (newServiceSearchInput) newServiceSearchInput.value = "";
      messageBox.textContent = "";
      hideAllMainScreens();
      formScreen.style.display = "block";
      return;
    }

    const data = await response.json();
    throw new Error(getErrorMessage(data, "Something went wrong while checking phone number."));
  } catch (error) {
    messageBox.textContent = error.message || "Failed to check phone number.";
    messageBox.className = "message error";
  }
});

// ── New customer flow ─────────────────────────────────────────

function buildNewCustomerPayload() {
  const formData = new FormData(customerForm);
  const referralCode = formData.get("referral_code")?.trim().toUpperCase() || "";

  return {
    phone_number: phoneNumber,
    full_name: formData.get("full_name")?.trim(),
    email: formData.get("email")?.trim() || null,
    date_of_birth: displayDateToISO(formData.get("date_of_birth")),
    referral_code: referralCode || null
  };
}

customerForm.addEventListener("submit", async (event) => {
  event.preventDefault();

  const payload = buildNewCustomerPayload();

  if (!validateDOBInput() || !isValidDOB(payload.date_of_birth)) {
    messageBox.textContent = t("dobInvalid");
    messageBox.className = "message error";
    if (dobInput) dobInput.reportValidity();
    return;
  }

  pendingNewCustomerPayload = payload;
  showNewCustomerServiceScreen();
});

if (backToNewCustomerFormBtn) {
  backToNewCustomerFormBtn.addEventListener("click", () => {
    hideAllMainScreens();
    formScreen.style.display = "block";
    messageBox.textContent = "";
    messageBox.className = "message";
  });
}

if (continueToNewReviewBtn) {
  continueToNewReviewBtn.addEventListener("click", () => {
    if (!pendingNewCustomerPayload) {
      pendingNewCustomerPayload = buildNewCustomerPayload();
    }

    if (selectedNewServiceIds.length === 0) {
      messageBox.textContent = t("selectOneService");
      messageBox.className = "message error";
      return;
    }

    showNewCustomerReview(pendingNewCustomerPayload);
  });
}

if (editNewCustomerBtn) {
  editNewCustomerBtn.addEventListener("click", () => {
    showNewCustomerServiceScreen();
  });
}

if (confirmNewCustomerBtn) {
  confirmNewCustomerBtn.addEventListener("click", async (event) => {
    event.preventDefault();
    event.stopPropagation();

    if (!pendingNewCustomerPayload) return;

    if (selectedNewServiceIds.length === 0) {
      messageBox.textContent = t("selectOneService");
      messageBox.className = "message error";
      return;
    }

    confirmNewCustomerBtn.disabled = true;
    messageBox.textContent = t("savingCustomer");
    messageBox.className = "message";

    try {
      let referralAppliedMessage = "";
      const referralCode = pendingNewCustomerPayload.referral_code || "";

      // 1. Validate referral first
      if (referralCode) {
        const validateResponse = await fetch(`${API_BASE}/referrals/validate`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            phone_number: phoneNumber,
            referral_code: referralCode
          })
        });

        const validateData = await validateResponse.json();
        if (!validateResponse.ok) {
          throw new Error(getErrorMessage(validateData, "Referral code not found or invalid."));
        }
      }

      // 2. Create customer only after referral is valid
      const createResponse = await fetch(CREATE_CUSTOMER_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(pendingNewCustomerPayload)
      });

      const createData = await createResponse.json();
      if (!createResponse.ok) {
        throw new Error(getErrorMessage(createData, "Failed to create customer."));
      }

      // 3. Apply referral after customer exists
      if (referralCode) {
        const applyResponse = await fetch(`${API_BASE}/referrals/apply`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            phone_number: phoneNumber,
            referral_code: referralCode
          })
        });

        const applyData = await applyResponse.json();
        if (!applyResponse.ok) {
          throw new Error(getErrorMessage(applyData, "Referral code not found or invalid."));
        }

        referralAppliedMessage = tf("referralApplied", {
          percent: applyData.discount_percent,
          from: applyData.referral_from_customer_name
        });
      }

      const checkInResponse = await fetch(
        `${API_BASE}/customers/check-in/${encodeURIComponent(phoneNumber)}`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            selected_service_ids: selectedNewServiceIds
          })
        }
      );

      const checkInData = await checkInResponse.json();
      if (!checkInResponse.ok) {
        throw new Error(getErrorMessage(checkInData, "Failed to check in customer."));
      }

      const birthdayDiscount = checkInData.discounts_applied?.find(d => d.type === "birthday");
      const referralRewardDiscount = checkInData.discounts_applied?.find(d => d.type === "referral");
      const earnedReferralCode = !!checkInData.referral_code;

      let successText = "";

      if (birthdayDiscount) {
        successText = tf("successBirthday", {
          name: checkInData.full_name,
          amount: birthdayDiscount.amount
        });
      } else if (referralAppliedMessage) {
        successText = tf("successWelcomeReferral", {
          name: checkInData.full_name,
          referral: referralAppliedMessage
        });
      } else if (referralRewardDiscount) {
        successText = tf("successRewardUnlocked", {
          name: checkInData.full_name,
          percent: referralRewardDiscount.percent
        });
      } else if (earnedReferralCode) {
        successText = tf("successCode", {
          name: checkInData.full_name,
          code: checkInData.referral_code
        });
      }

      messageBox.textContent = "";
      messageBox.className = "message";

      await loadTodayCheckInOrder();

      if (birthdayDiscount || referralAppliedMessage || referralRewardDiscount || earnedReferralCode) {
        showSuccessModal(successText);
      }

      const servicesForThanks = [...selectedNewServiceIds];

      pendingNewCustomerPayload = null;
      selectedNewServiceIds.length = 0;

      showThankYouScreen("thankYouNew", servicesForThanks);
    } catch (error) {
      console.error("New customer confirm error:", error);
      messageBox.textContent = error.message || "Failed to save customer.";
      messageBox.className = "message error";
      messageBox.scrollIntoView({ behavior: "smooth", block: "center" });
    } finally {
      confirmNewCustomerBtn.disabled = false;
    }
  });
}

// ── Returning customer flow ───────────────────────────────────

existingCustomerForm.addEventListener("submit", async (event) => {
  event.preventDefault();

  const referralCodeInput = document.getElementById("existing_referral_code");
  pendingExistingReferralCode = referralCodeInput.value.trim().toUpperCase();

  showExistingCustomerServiceScreen();
});

if (backToExistingCustomerBtn) {
  backToExistingCustomerBtn.addEventListener("click", () => {
    openExistingCustomerScreen();
  });
}

if (continueToExistingReviewBtn) {
  continueToExistingReviewBtn.addEventListener("click", () => {
    if (selectedExistingServiceIds.length === 0) {
      messageBox.textContent = t("selectOneService");
      messageBox.className = "message error";
      return;
    }

    showExistingCustomerReview();
  });
}

if (editExistingCustomerBtn) {
  editExistingCustomerBtn.addEventListener("click", () => {
    showExistingCustomerServiceScreen();
  });
}

if (confirmExistingCustomerBtn) {
  confirmExistingCustomerBtn.addEventListener("click", async (event) => {
    event.preventDefault();
    event.stopPropagation();

    if (selectedExistingServiceIds.length === 0) {
      messageBox.textContent = t("selectOneService");
      messageBox.className = "message error";
      return;
    }

    confirmExistingCustomerBtn.disabled = true;
    messageBox.textContent = t("processingCheckIn");
    messageBox.className = "message";

    try {
      let referralAppliedMessage = "";

      if (pendingExistingReferralCode) {
        const applyResponse = await fetch(`${API_BASE}/referrals/apply`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            phone_number: phoneNumber,
            referral_code: pendingExistingReferralCode
          })
        });

        const applyData = await applyResponse.json();
        if (!applyResponse.ok) {
          throw new Error(getErrorMessage(applyData, "Failed to apply referral code."));
        }

        referralAppliedMessage = tf("referralApplied", {
          percent: applyData.discount_percent,
          from: applyData.referral_from_customer_name
        });
      }

      const checkInResponse = await fetch(
        `${API_BASE}/customers/check-in/${encodeURIComponent(phoneNumber)}`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            selected_service_ids: selectedExistingServiceIds
          })
        }
      );

      const checkInData = await checkInResponse.json();
      if (!checkInResponse.ok) {
        throw new Error(getErrorMessage(checkInData, "Failed to check in customer."));
      }

      const birthdayDiscount = checkInData.discounts_applied?.find(d => d.type === "birthday");
      const referralRewardDiscount = checkInData.discounts_applied?.find(d => d.type === "referral");
      const earnedReferralCode = !existingCustomer?.referral_code && !!checkInData.referral_code;

      let successText = "";

      if (birthdayDiscount) {
        successText = tf("successBirthday", {
          name: checkInData.full_name,
          amount: birthdayDiscount.amount
        });
      } else if (referralAppliedMessage) {
        successText = tf("successWelcomeBackReferral", {
          name: checkInData.full_name,
          referral: referralAppliedMessage
        });
      } else if (referralRewardDiscount) {
        successText = tf("successRewardUnlocked", {
          name: checkInData.full_name,
          percent: referralRewardDiscount.percent
        });
      } else if (earnedReferralCode) {
        successText = tf("successCode", {
          name: checkInData.full_name,
          code: checkInData.referral_code
        });
      }

      messageBox.textContent = "";
      messageBox.className = "message";

      await loadTodayCheckInOrder();

      if (birthdayDiscount || referralAppliedMessage || referralRewardDiscount || earnedReferralCode) {
        showSuccessModal(successText);
      }

      const servicesForThanks = [...selectedExistingServiceIds];

      selectedExistingServiceIds.length = 0;
      pendingExistingReferralCode = "";

      showThankYouScreen("thankYouExisting", servicesForThanks);
    } catch (error) {
      console.error("Returning customer confirm error:", error);
      messageBox.textContent = error.message || "Failed to process returning customer.";
      messageBox.className = "message error";
      messageBox.scrollIntoView({ behavior: "smooth", block: "center" });
    } finally {
      confirmExistingCustomerBtn.disabled = false;
    }
  });
}

// ── Update profile ────────────────────────────────────────────

if (updateProfileBtn) {
  updateProfileBtn.addEventListener("click", () => {
    populateUpdateProfileForm(existingCustomer);
    hideAllMainScreens();
    updateProfileScreen.style.display = "block";
    messageBox.textContent = "";
    messageBox.className = "message";
  });
}

if (cancelUpdateProfileBtn) {
  cancelUpdateProfileBtn.addEventListener("click", () => {
    updateProfileForm.reset();
    openExistingCustomerScreen();
  });
}

if (updateProfileForm) {
  updateProfileForm.addEventListener("submit", async (event) => {
    event.preventDefault();

    const updatedFullName = updateFullNameInput.value.trim();
    const updatedPhone = rawDigits(updatePhoneInput.value);
    const updatedEmail = updateEmailInput.value.trim();

    if (!updatedFullName) {
      messageBox.textContent = t("nameRequired");
      messageBox.className = "message error";
      return;
    }

    if (updatedPhone.length !== 10) {
      messageBox.textContent = t("phoneTenDigits");
      messageBox.className = "message error";
      return;
    }

    messageBox.textContent = t("updatingProfile");
    messageBox.className = "message";

    try {
      const response = await fetch(
        `${API_BASE}/customers/${encodeURIComponent(phoneNumber)}/profile`,
        {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            full_name: updatedFullName,
            phone_number: updatedPhone,
            email: updatedEmail || null
          })
        }
      );

      const data = await response.json();

      if (!response.ok) {
        throw new Error(getErrorMessage(data, "Failed to update profile."));
      }

      existingCustomer = data;
      phoneNumber = data.phone_number;

      messageBox.textContent = "";
      messageBox.className = "message";

      showSuccessModal(tf("profileUpdated", { name: data.full_name }));

      updateProfileForm.reset();
      openExistingCustomerScreen();
    } catch (error) {
      messageBox.textContent = error.message || "Failed to update profile.";
      messageBox.className = "message error";
    }
  });
}


// ── Language ──────────────────────────────────────────────────

let currentLanguage = localStorage.getItem("nailSalonLanguage") || "en";

const translations = {
  en: {
    salon: "NAIL SALON",
    welcome: "Welcome to Nail Salon",
    heroSubtitle:
      "Check in, enjoy rewards, and relax while we take care of the rest.",

    todayOrder: "Today's Check-In Order",
    todayOrderSubtitle:
      "Customers are listed in the order they checked in.",
    noCustomers: "No customers checked in yet.",

    checkIn: "Check In",
    enterPhone: "Enter your phone number to continue",
    continue: "Continue",

    newCustomer: "New Customer",
    completeInfo: "Please complete your information",

    fullName: "Full Name",
    emailOptional: "Email (optional)",
    referralOptional: "Referral Code (optional)",
    existingReferralOptional: "Enter referral code (optional)",

    selectServices: "Select Services",
    chooseServices: "Choose your services below.",
    searchServices: "Search services",
    back: "Back",
    reviewInformation: "Review Information",

    reviewTitle: "Review Your Information",
    checkInformation:
      "Please check your information before continuing.",

    name: "Name",
    phone: "Phone",
    email: "Email",
    birthday: "Birthday",
    referral: "Referral",
    services: "Services",

    edit: "Edit",

    returningCustomer: "Returning Customer",
    updateProfile: "Update Profile",

    editInformation: "Edit your information below.",
    phoneNumber: "Phone Number",
    save: "Save",
    cancel: "Cancel",

    thankYou: "Thank You!",
    checkedInRelax:
      "You are checked in. Please take a seat and relax.",
    backHome: "Back to Home",

    happyBirthday: "Happy Birthday!",
    birthdayTen: "You have $10 off today.",
    awesome: "Awesome",

    checkedIn: "You're Checked In",
    welcomeRelax:
      "Welcome! Please relax and enjoy your visit.",
    lovely: "Lovely",

    specialOffer: "Special Offer",
    salonRewards: "Salon Rewards",
    salonRewardsText:
      "Visit more often and enjoy exclusive salon benefits.",

    promoDisclaimer:
      "Promotion images and offers are for advertising only.",

    notProvided: "Not provided",
    noServicesSelected: "No services selected",
    noMatchingServices: "No matching services found.",
    unableServices: "Unable to load services.",
    unableQueue: "Unable to load check-in order.",

    invalidPhone: "Please enter a valid 10-digit phone number.",
    checkingPhone: "Checking phone number...",
    selectOneService: "Please select at least one service.",
    savingCustomer: "Saving customer...",
    processingCheckIn: "Processing check-in...",
    nameRequired: "Name is required.",
    phoneTenDigits: "Phone number must be exactly 10 digits.",
    updatingProfile: "Updating profile...",

    dobRequired: "Please enter your date of birth.",
    dobInvalid: "Please enter a valid date of birth with a 4-digit year.",
    welcomeBack: "Welcome back, {name}",
    alreadyCheckedIn: "{name} has already checked in today.",
    referralApplied: "You've received {percent}% off today as a referral reward from {from}.",
    successBirthday: "Happy Birthday, {name}! ✨\nEnjoy a complimentary ${amount} birthday reward today.\nSit back, relax, and let us take care of you.",
    successWelcomeReferral: "Welcome, {name}! ✨\n{referral}\nEnjoy your visit with us.",
    successWelcomeBackReferral: "Welcome back, {name}! ✨\n{referral}\nEnjoy your salon experience.",
    successRewardUnlocked: "Congratulations, {name}! ✨\nYour {percent}% referral reward has been unlocked and applied today.\nThank you for sharing the love with others.",
    successCode: "You've unlocked a special reward, {name}! ✨\nYour personal referral code is {code}.\nShare it with friends and give them 10% off their visit.",
    thankYouNew: "You are checked in for: {services}. Please take a seat and relax. A technician will be with you shortly.",
    thankYouExisting: "Thank you for checking in for: {services}. Please take a seat and enjoy your salon experience.",
    profileUpdated: "Profile updated successfully, {name}. Your rewards, referral code, birthday benefits, and visit history all stay on the same account.",
    slide1Badge: "Referral Reward", slide1Title: "Get 10% Off With Referral", slide1Text: "Use a valid referral code and enjoy 10% off your salon services.",
    slide2Badge: "Birthday Special", slide2Title: "Birthday Reward", slide2Text: "Celebrate your birthday with a special $10 off on your birthday.",
    slide3Badge: "Salon Rewards", slide3Title: "Enjoy Exclusive Benefits", slide3Text: "Visit more often and unlock special salon rewards and referral benefits.",
    slide4Badge: "Relax & Enjoy", slide4Title: "Check In and Relax", slide4Text: "Check in quickly, take a seat, and enjoy a relaxing salon experience."
  },


  vi: {
    salon: "TIỆM NAIL",
    welcome: "Chào Mừng Đến Tiệm Nail",
    heroSubtitle:
      "Chào mừng bạn đến với tiệm! Vui lòng check-in bên dưới để chúng tôi có thể phục vụ bạn nhanh chóng và chu đáo hơn.",

    todayOrder: "Thứ Tự Check-In Hôm Nay",
    todayOrderSubtitle:
      "Khách hàng được hiển thị theo thứ tự check-in.",
    noCustomers: "Chưa có khách hàng nào check-in.",

    checkIn: "Check-In",
    enterPhone: "Nhập số điện thoại để tiếp tục",
    continue: "Tiếp Tục",

    newCustomer: "Khách Hàng Mới",
    completeInfo: "Vui lòng điền thông tin của bạn",

    fullName: "Họ và Tên",
    emailOptional: "Email (không bắt buộc)",
    referralOptional: "Mã giới thiệu (không bắt buộc)",
    existingReferralOptional: "Nhập mã giới thiệu (không bắt buộc)",

    selectServices: "Chọn Dịch Vụ",
    chooseServices: "Chọn dịch vụ bên dưới.",
    searchServices: "Tìm dịch vụ",
    back: "Quay Lại",
    reviewInformation: "Kiểm Tra Thông Tin",

    reviewTitle: "Kiểm Tra Thông Tin Của Bạn",
    checkInformation:
      "Vui lòng kiểm tra thông tin trước khi tiếp tục.",

    name: "Họ Tên",
    phone: "Điện Thoại",
    email: "Email",
    birthday: "Ngày Sinh",
    referral: "Giới Thiệu",
    services: "Dịch Vụ",

    edit: "Chỉnh Sửa",

    returningCustomer: "Khách Hàng Cũ",
    updateProfile: "Cập Nhật Thông Tin",

    editInformation: "Chỉnh sửa thông tin của bạn bên dưới.",
    phoneNumber: "Số Điện Thoại",
    save: "Lưu",
    cancel: "Hủy",

    thankYou: "Cảm Ơn!",
    checkedInRelax:
      "Bạn đã check-in. Vui lòng ngồi chờ và thư giãn.",
    backHome: "Về Trang Chính",

    happyBirthday: "Chúc Mừng Sinh Nhật!",
    birthdayTen: "Hôm nay bạn được giảm $10.",
    awesome: "Tuyệt Vời",

    checkedIn: "Bạn Đã Check-In",
    welcomeRelax:
      "Chào mừng! Hãy thư giãn và tận hưởng dịch vụ.",
    lovely: "Tuyệt Vời",

    specialOffer: "Ưu Đãi Đặc Biệt",
    salonRewards: "Ưu Đãi Khách Hàng",
    salonRewardsText:
      "Ghé tiệm thường xuyên để nhận thêm nhiều ưu đãi.",

    promoDisclaimer:
      "Hình ảnh và ưu đãi chỉ dùng cho mục đích quảng cáo.",

    notProvided: "Chưa cung cấp",
    noServicesSelected: "Chưa chọn dịch vụ",
    noMatchingServices: "Không tìm thấy dịch vụ phù hợp.",
    unableServices: "Không thể tải danh sách dịch vụ.",
    unableQueue: "Không thể tải danh sách check-in.",

    invalidPhone: "Vui lòng nhập số điện thoại hợp lệ gồm 10 số.",
    checkingPhone: "Đang kiểm tra số điện thoại...",
    selectOneService: "Vui lòng chọn ít nhất một dịch vụ.",
    savingCustomer: "Đang lưu thông tin khách hàng...",
    processingCheckIn: "Đang xử lý check-in...",
    nameRequired: "Vui lòng nhập họ tên.",
    phoneTenDigits: "Số điện thoại phải có đúng 10 số.",
    updatingProfile: "Đang cập nhật thông tin...",

    dobRequired: "Vui lòng nhập ngày sinh.",
    dobInvalid: "Vui lòng nhập ngày sinh hợp lệ với năm gồm 4 chữ số.",
    welcomeBack: "Chào mừng trở lại, {name}",
    alreadyCheckedIn: "{name} đã check-in hôm nay.",
    referralApplied: "Bạn được giảm {percent}% hôm nay nhờ mã giới thiệu từ {from}.",
    successBirthday: "Chúc mừng sinh nhật, {name}! ✨\nHôm nay bạn được tặng ${amount} quà sinh nhật.\nHãy thư giãn và để chúng tôi chăm sóc bạn.",
    successWelcomeReferral: "Chào mừng, {name}! ✨\n{referral}\nChúc bạn có một buổi làm đẹp vui vẻ.",
    successWelcomeBackReferral: "Chào mừng trở lại, {name}! ✨\n{referral}\nChúc bạn tận hưởng dịch vụ của tiệm.",
    successRewardUnlocked: "Chúc mừng, {name}! ✨\nBạn đã nhận được ưu đãi giới thiệu {percent}% và đã được áp dụng hôm nay.\nCảm ơn bạn đã chia sẻ với mọi người.",
    successCode: "Bạn vừa mở khóa phần thưởng đặc biệt, {name}! ✨\nMã giới thiệu của bạn là {code}.\nHãy chia sẻ cho bạn bè để họ được giảm 10%.",
    thankYouNew: "Bạn đã check-in cho: {services}. Vui lòng ngồi chờ và thư giãn. Thợ sẽ đến với bạn ngay.",
    thankYouExisting: "Cảm ơn bạn đã check-in cho: {services}. Vui lòng ngồi chờ và tận hưởng dịch vụ.",
    profileUpdated: "Đã cập nhật thông tin thành công, {name}. Ưu đãi, mã giới thiệu, quà sinh nhật và lịch sử đều giữ nguyên trên cùng một tài khoản.",
    slide1Badge: "Thưởng Giới Thiệu", slide1Title: "Giảm 10% Khi Có Mã Giới Thiệu", slide1Text: "Dùng mã giới thiệu hợp lệ để được giảm 10% dịch vụ.",
    slide2Badge: "Đặc Biệt Sinh Nhật", slide2Title: "Quà Sinh Nhật", slide2Text: "Mừng sinh nhật với ưu đãi giảm $10 vào ngày sinh nhật của bạn.",
    slide3Badge: "Ưu Đãi Tiệm", slide3Title: "Tận Hưởng Ưu Đãi Độc Quyền", slide3Text: "Ghé tiệm thường xuyên để mở khóa thêm nhiều ưu đãi và quyền lợi giới thiệu.",
    slide4Badge: "Thư Giãn & Tận Hưởng", slide4Title: "Check-In Và Thư Giãn", slide4Text: "Check-in nhanh chóng, ngồi chờ và tận hưởng trải nghiệm thư giãn."
  },


  es: {
    salon: "SALÓN DE UÑAS",
    welcome: "Bienvenido al Salón de Uñas",
    heroSubtitle:
      "¡Bienvenido! Regístrese a continuación para que podamos atenderle lo antes posible y hacer que disfrute de su visita.",

    todayOrder: "Orden de Registro de Hoy",
    todayOrderSubtitle:
      "Los clientes aparecen en el orden en que se registraron.",
    noCustomers: "Aún no hay clientes registrados.",

    checkIn: "Registrarse",
    enterPhone: "Ingrese su número de teléfono para continuar",
    continue: "Continuar",

    newCustomer: "Cliente Nuevo",
    completeInfo: "Complete su información",

    fullName: "Nombre Completo",
    emailOptional: "Correo electrónico (opcional)",
    referralOptional: "Código de referido (opcional)",
    existingReferralOptional: "Ingrese código de referido (opcional)",

    selectServices: "Seleccionar Servicios",
    chooseServices: "Seleccione sus servicios a continuación.",
    searchServices: "Buscar servicios",
    back: "Atrás",
    reviewInformation: "Revisar Información",

    reviewTitle: "Revise Su Información",
    checkInformation:
      "Revise su información antes de continuar.",

    name: "Nombre",
    phone: "Teléfono",
    email: "Correo Electrónico",
    birthday: "Fecha de Nacimiento",
    referral: "Referido",
    services: "Servicios",

    edit: "Editar",

    returningCustomer: "Cliente Existente",
    updateProfile: "Actualizar Perfil",

    editInformation: "Edite su información a continuación.",
    phoneNumber: "Número de Teléfono",
    save: "Guardar",
    cancel: "Cancelar",

    thankYou: "¡Gracias!",
    checkedInRelax:
      "Ya está registrado. Tome asiento y relájese.",
    backHome: "Volver al Inicio",

    happyBirthday: "¡Feliz Cumpleaños!",
    birthdayTen: "Hoy tiene $10 de descuento.",
    awesome: "Excelente",

    checkedIn: "Ya Está Registrado",
    welcomeRelax:
      "¡Bienvenido! Relájese y disfrute su visita.",
    lovely: "Perfecto",

    specialOffer: "Oferta Especial",
    salonRewards: "Recompensas del Salón",
    salonRewardsText:
      "Visítenos con frecuencia y disfrute beneficios exclusivos.",

    promoDisclaimer:
      "Las imágenes y ofertas promocionales son solo para publicidad.",

    notProvided: "No proporcionado",
    noServicesSelected: "No se seleccionaron servicios",
    noMatchingServices: "No se encontraron servicios.",
    unableServices: "No se pudieron cargar los servicios.",
    unableQueue: "No se pudo cargar la lista de registro.",

    invalidPhone: "Ingrese un número de teléfono válido de 10 dígitos.",
    checkingPhone: "Verificando número de teléfono...",
    selectOneService: "Seleccione al menos un servicio.",
    savingCustomer: "Guardando cliente...",
    processingCheckIn: "Procesando registro...",
    nameRequired: "El nombre es obligatorio.",
    phoneTenDigits: "El número de teléfono debe tener exactamente 10 dígitos.",
    updatingProfile: "Actualizando perfil...",

    dobRequired: "Ingrese su fecha de nacimiento.",
    dobInvalid: "Ingrese una fecha de nacimiento válida con año de 4 dígitos.",
    welcomeBack: "Bienvenido de nuevo, {name}",
    alreadyCheckedIn: "{name} ya se registró hoy.",
    referralApplied: "Recibió {percent}% de descuento hoy como recompensa de referido de {from}.",
    successBirthday: "¡Feliz cumpleaños, {name}! ✨\nDisfrute de ${amount} de regalo de cumpleaños hoy.\nRelájese y permítanos cuidarle.",
    successWelcomeReferral: "¡Bienvenido, {name}! ✨\n{referral}\nDisfrute su visita.",
    successWelcomeBackReferral: "¡Bienvenido de nuevo, {name}! ✨\n{referral}\nDisfrute su experiencia en el salón.",
    successRewardUnlocked: "¡Felicidades, {name}! ✨\nSu recompensa de referido de {percent}% fue desbloqueada y aplicada hoy.\nGracias por compartir con otros.",
    successCode: "¡Ha desbloqueado una recompensa especial, {name}! ✨\nSu código de referido personal es {code}.\nCompártalo con amigos y dales 10% de descuento.",
    thankYouNew: "Está registrado para: {services}. Tome asiento y relájese. Un técnico lo atenderá en breve.",
    thankYouExisting: "Gracias por registrarse para: {services}. Tome asiento y disfrute su experiencia en el salón.",
    profileUpdated: "Perfil actualizado con éxito, {name}. Sus recompensas, código de referido, beneficios de cumpleaños e historial se mantienen en la misma cuenta.",
    slide1Badge: "Recompensa por Referido", slide1Title: "10% de Descuento con Referido", slide1Text: "Use un código de referido válido y disfrute 10% de descuento en sus servicios.",
    slide2Badge: "Especial de Cumpleaños", slide2Title: "Regalo de Cumpleaños", slide2Text: "Celebre su cumpleaños con $10 de descuento especial.",
    slide3Badge: "Recompensas del Salón", slide3Title: "Disfrute Beneficios Exclusivos", slide3Text: "Visítenos con más frecuencia y desbloquee recompensas y beneficios por referidos.",
    slide4Badge: "Relájese y Disfrute", slide4Title: "Regístrese y Relájese", slide4Text: "Regístrese rápido, tome asiento y disfrute una experiencia relajante."
  }
};


function t(key) {
  return translations[currentLanguage]?.[key]
    || translations.en[key]
    || key;
}


function setText(selector, key) {
  const element = document.querySelector(selector);

  if (element) {
    element.textContent = t(key);
  }
}


function setPlaceholder(selector, key) {
  const element = document.querySelector(selector);

  if (element) {
    element.placeholder = t(key);
  }
}


// Re-translates whatever dynamic content is currently on screen
function refreshDynamicScreens() {
  if (existingCustomer) {
    existingCustomerName.textContent = tf("welcomeBack", { name: existingCustomer.full_name });
    renderExistingCustomerProfile(existingCustomer);
  }

  if (newCustomerReviewScreen.style.display === "block" && pendingNewCustomerPayload) {
    showNewCustomerReview(pendingNewCustomerPayload);
  }

  if (existingCustomerReviewScreen.style.display === "block") {
    showExistingCustomerReview();
  }

  if (thankYouScreen.style.display === "block" && lastThankYou) {
    thankYouMessage.textContent = tf(lastThankYou.key, {
      services: formatServiceNamesFromIds(lastThankYou.ids)
    });
  }
}


function applyLanguage(lang) {
  if (!translations[lang]) {
    lang = "en";
  }

  currentLanguage = lang;

  localStorage.setItem("nailSalonLanguage", lang);

  document.documentElement.lang = lang;


  // Header

  setText(".brand", "salon");
  setText(".hero h1", "welcome");
  setText(".hero-subtitle", "heroSubtitle");

  setText(".promo-disclaimer", "promoDisclaimer");


  // Queue

  const queueCard = document.querySelector(".queue-card");

  if (queueCard) {
    const heading = queueCard.querySelector("h2");
    const subtitle = queueCard.querySelector(".subtitle");

    if (heading) heading.textContent = t("todayOrder");
    if (subtitle) subtitle.textContent = t("todayOrderSubtitle");
  }


  // Phone screen

  const phoneHeading = phoneScreen?.querySelector("h2");
  const phoneSubtitle = phoneScreen?.querySelector(".subtitle");
  const phoneButton = phoneForm?.querySelector('button[type="submit"]');

  if (phoneHeading) phoneHeading.textContent = t("checkIn");
  if (phoneSubtitle) phoneSubtitle.textContent = t("enterPhone");
  if (phoneButton) phoneButton.textContent = t("continue");


  // New customer

  const newHeading = formScreen?.querySelector("h2");
  const newSubtitle = formScreen?.querySelector(".subtitle");
  const newContinue = customerForm?.querySelector('button[type="submit"]');

  if (newHeading) newHeading.textContent = t("newCustomer");
  if (newSubtitle) newSubtitle.textContent = t("completeInfo");
  if (newContinue) newContinue.textContent = t("continue");

  setPlaceholder('#new-customer-form input[name="full_name"]', "fullName");
  setPlaceholder('#new-customer-form input[name="email"]', "emailOptional");
  setPlaceholder('#new-customer-form input[name="referral_code"]', "referralOptional");


  // Service screens

  [newCustomerServiceScreen, existingCustomerServiceScreen]
    .forEach(screen => {
      if (!screen) return;

      const heading = screen.querySelector("h2");
      const subtitle = screen.querySelector(".subtitle");

      if (heading) heading.textContent = t("selectServices");
      if (subtitle) subtitle.textContent = t("chooseServices");
    });


  setPlaceholder("#new-service-search", "searchServices");
  setPlaceholder("#existing-service-search", "searchServices");


  if (backToNewCustomerFormBtn) {
    backToNewCustomerFormBtn.textContent = t("back");
  }

  if (continueToNewReviewBtn) {
    continueToNewReviewBtn.textContent = t("reviewInformation");
  }

  if (backToExistingCustomerBtn) {
    backToExistingCustomerBtn.textContent = t("back");
  }

  if (continueToExistingReviewBtn) {
    continueToExistingReviewBtn.textContent = t("reviewInformation");
  }


  // Review screens

  [newCustomerReviewScreen, existingCustomerReviewScreen]
    .forEach(screen => {
      if (!screen) return;

      const heading = screen.querySelector("h2");
      const subtitle = screen.querySelector(".subtitle");
      const reminder = screen.querySelector(".reminder-box");

      if (heading) heading.textContent = t("reviewTitle");
      if (subtitle) subtitle.textContent = t("checkInformation");
      if (reminder) reminder.textContent = t("checkInformation");
    });


  const newLabels = newCustomerReviewScreen?.querySelectorAll(".profile-label");

  if (newLabels?.length >= 5) {
    newLabels[0].textContent = t("name");
    newLabels[1].textContent = t("birthday");
    newLabels[2].textContent = t("email");
    newLabels[3].textContent = t("referral");
    newLabels[4].textContent = t("services");
  }


  const existingLabels = existingCustomerReviewScreen?.querySelectorAll(".profile-label");

  if (existingLabels?.length >= 5) {
    existingLabels[0].textContent = t("name");
    existingLabels[1].textContent = t("phone");
    existingLabels[2].textContent = t("email");
    existingLabels[3].textContent = t("referral");
    existingLabels[4].textContent = t("services");
  }


  if (editNewCustomerBtn) {
    editNewCustomerBtn.textContent = t("edit");
  }

  if (confirmNewCustomerBtn) {
    confirmNewCustomerBtn.textContent = t("continue");
  }

  if (editExistingCustomerBtn) {
    editExistingCustomerBtn.textContent = t("edit");
  }

  if (confirmExistingCustomerBtn) {
    confirmExistingCustomerBtn.textContent = t("checkIn");
  }


  // Returning customer

  const existingHeading = existingScreen?.querySelector("h2");

  if (existingHeading) {
    existingHeading.textContent = t("returningCustomer");
  }

  setPlaceholder("#existing_referral_code", "existingReferralOptional");

  const existingContinue = existingCustomerForm?.querySelector('button[type="submit"]');

  if (existingContinue) {
    existingContinue.textContent = t("continue");
  }

  if (updateProfileBtn) {
    updateProfileBtn.textContent = t("updateProfile");
  }


  // Update profile

  const updateHeading = updateProfileScreen?.querySelector("h2");
  const updateSubtitle = updateProfileScreen?.querySelector(".subtitle");

  if (updateHeading) {
    updateHeading.textContent = t("updateProfile");
  }

  if (updateSubtitle) {
    updateSubtitle.textContent = t("editInformation");
  }

  setPlaceholder("#update_full_name", "fullName");
  setPlaceholder("#update_phone", "phoneNumber");
  setPlaceholder("#update_email", "emailOptional");

  const saveButton = updateProfileForm?.querySelector('button[type="submit"]');

  if (saveButton) {
    saveButton.textContent = t("save");
  }

  if (cancelUpdateProfileBtn) {
    cancelUpdateProfileBtn.textContent = t("cancel");
  }


  // Thank you

  const thankHeading = thankYouScreen?.querySelector("h2");

  if (thankHeading) {
    thankHeading.textContent = t("thankYou");
  }

  if (backHomeBtn) {
    backHomeBtn.textContent = t("backHome");
  }


  // Birthday modal

  const birthdayHeading = birthdayModal?.querySelector("h2");

  if (birthdayHeading) {
    birthdayHeading.textContent = t("happyBirthday");
  }

  if (closeBirthdayModalBtn) {
    closeBirthdayModalBtn.textContent = t("awesome");
  }


  // Success modal

  const successHeading = successModal?.querySelector("h2");

  if (successHeading) {
    successHeading.textContent = t("checkedIn");
  }

  if (closeSuccessModalBtn) {
    closeSuccessModalBtn.textContent = t("lovely");
  }

  renderServiceList(
    newServiceList,
    selectedNewServiceIds,
    newServiceSearchInput?.value || ""
  );

  renderServiceList(
    existingServiceList,
    selectedExistingServiceIds,
    existingServiceSearchInput?.value || ""
  );

  renderSlide(carouselIndex);
  refreshDynamicScreens();
  loadTodayCheckInOrder();
}

const languageToggle = document.getElementById("language-toggle");
const languageDropdown = document.getElementById("language-dropdown");

const languageLabels = {
  en: "🌐 EN",
  vi: "🌐 VI",
  es: "🌐 ES"
};

if (languageToggle && languageDropdown) {

  languageToggle.addEventListener("click", (event) => {
    event.stopPropagation();
    languageDropdown.classList.toggle("hidden");
  });

  document.querySelectorAll(".language-option").forEach(button => {

    button.addEventListener("click", () => {

      const lang = button.dataset.lang;

      applyLanguage(lang);

      languageToggle.textContent = languageLabels[lang];

      languageDropdown.classList.add("hidden");
    });

  });

  document.addEventListener("click", (event) => {

    if (!event.target.closest(".language-menu")) {
      languageDropdown.classList.add("hidden");
    }

  });

}

if (languageToggle) {
  languageToggle.textContent =
    languageLabels[currentLanguage] || "🌐 EN";
}

// ── Init ──────────────────────────────────────────────────────

applyLanguage(currentLanguage);

startCarousel();
loadTodayCheckInOrder();
loadServices();

setInterval(loadTodayCheckInOrder, 10000);