const LOCALE_MAP = { en: "en-US", vi: "vi-VN", es: "es-ES" };
const LANGUAGE_LABELS = { en: "🌐 EN", vi: "🌐 VI", es: "🌐 ES" };
const CREATE_CUSTOMER_PATH = "/customers/new";
const CAROUSEL_INTERVAL_MS = 4000;
const QUEUE_REFRESH_MS = 10000;

const CAROUSEL_SLIDES = [
  { key: "slide1", image: "https://images.unsplash.com/photo-1604654894610-df63bc536371?auto=format&fit=crop&w=1400&q=80" },
  { key: "slide2", image: "https://images.unsplash.com/photo-1522337660859-02fbefca4702?auto=format&fit=crop&w=1400&q=80" },
  { key: "slide3", image: "https://images.unsplash.com/photo-1519014816548-bf5fe059798b?auto=format&fit=crop&w=1400&q=80" },
  { key: "slide4", image: "https://images.unsplash.com/photo-1610992015732-2449b76344bc?auto=format&fit=crop&w=1400&q=80" }
];

// ── DOM references ────────────────────────────────────────────

const $ = (id) => document.getElementById(id);

const forms = {
  phone: $("phone-form"),
  newCustomer: $("new-customer-form"),
  existingCustomer: $("existing-customer-form"),
  updateProfile: $("update-profile-form"),
  verifyProfile: $("verify-profile-form")
};

const screens = {
  phone: $("phone-screen"),
  newForm: $("form-screen"),
  newServices: $("new-customer-service-screen"),
  newReview: $("new-customer-review-screen"),
  existing: $("existing-screen"),
  existingServices: $("existing-customer-service-screen"),
  existingReview: $("existing-customer-review-screen"),
  updateProfile: $("update-profile-screen"),
  verifyProfile: $("verify-profile-screen"),
  thankYou: $("thank-you-screen")
};

const messageBox = $("message");
const checkinOrderList = $("checkin-order-list");
const thankYouMessage = $("thank-you-message");
const existingCustomerName = $("existing-customer-name");
const existingCustomerProfile = $("existing-customer-profile");

const phoneInput = $("phone_number");
const dobInput = $("date_of_birth");
const updateFullNameInput = $("update_full_name");
const verifyDobInput = $("verify_dob");
const updatePhoneInput = $("update_phone");
const updateEmailInput = $("update_email");

const birthdayModal = $("birthday-modal");
const birthdayModalText = $("birthday-modal-text");
const successModal = $("success-modal");
const successModalText = $("success-modal-text");

const carousel = {
  image: $("carousel-image"),
  badge: $("ad-badge"),
  title: $("ad-title"),
  text: $("ad-text")
};

const review = {
  newCustomer: {
    name: $("review-full-name"),
    dob: $("review-dob"),
    email: $("review-email"),
    referral: $("review-referral-code"),
    services: $("review-services")
  },
  existing: {
    name: $("existing-review-full-name"),
    phone: $("existing-review-phone"),
    email: $("existing-review-email"),
    referral: $("existing-review-referral-code"),
    services: $("existing-review-services")
  }
};

const selectedNewServiceIds = [];
const selectedExistingServiceIds = [];

const newPicker = {
  list: $("new-service-list"),
  search: $("new-service-search"),
  selected: selectedNewServiceIds
};
const existingPicker = {
  list: $("existing-service-list"),
  search: $("existing-service-search"),
  selected: selectedExistingServiceIds
};

// ── State ─────────────────────────────────────────────────────

let currentLanguage = localStorage.getItem("nailSalonLanguage") || "en";
let phoneNumber = "";
let existingCustomer = null;
let profileEditToken = ""; // short-lived proof that the birth date on file was just entered; never shown or stored
let pendingNewCustomerPayload = null;
let pendingExistingReferralCode = "";
let availableServices = [];
let lastThankYou = null;
let carouselIndex = 0;

// ── Translation helpers ───────────────────────────────────────

function t(key) {
  return translations[currentLanguage]?.[key] || translations.en[key] || key;
}

function tf(key, vars = {}) {
  return t(key).replace(/\{(\w+)\}/g, (_, k) => vars[k] ?? "");
}

// ── Generic helpers ───────────────────────────────────────────

function formatPhone(value) {
  const d = value.replace(/\D/g, "").slice(0, 10);
  if (d.length === 0) return "";
  if (d.length <= 3) return `(${d}`;
  if (d.length <= 6) return `(${d.slice(0, 3)}) ${d.slice(3)}`;
  return `(${d.slice(0, 3)}) ${d.slice(3, 6)}-${d.slice(6)}`;
}

const rawDigits = (value) => value.replace(/\D/g, "");

function safeText(value) {
  return value && String(value).trim() ? value : t("notProvided");
}

function setMessage(text = "", type = "") {
  messageBox.textContent = text;
  messageBox.className = type ? `message ${type}` : "message";
}

function getErrorMessage(data, fallback = "Something went wrong.") {
  if (!data) return fallback;
  if (typeof data === "string") return data;

  const { detail } = data;

  if (Array.isArray(detail)) {
    return detail
      .map((item) => (typeof item === "string" ? item : item?.msg || JSON.stringify(item)))
      .join(", ");
  }
  if (typeof detail === "string") return detail;
  if (detail && typeof detail === "object") return detail.msg || JSON.stringify(detail);

  return fallback;
}

// Calls the API (with this tablet's device token), returns parsed JSON, throws Error(message) on failure.
// The thrown error carries the HTTP status so callers can show a translated message.
async function api(path, { method = "GET", body, fallback, headers = {} } = {}) {
  const options = { method, headers: { ...headers } };
  if (body !== undefined) {
    options.headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(body);
  }

  const response = await kioskFetch(path, options);
  if (response.status === 429) throw httpError(t("tooManyRequests"), response.status);
  if (response.status === 401) throw httpError(t("pairRevoked"), response.status);

  const data = await response.json();

  if (!response.ok) throw httpError(getErrorMessage(data, fallback), response.status);
  return data;
}

function httpError(message, status) {
  const error = new Error(message);
  error.status = status;
  return error;
}

// ── Date helpers ──────────────────────────────────────────────

function getTodayISODate() {
  const today = new Date();
  const month = String(today.getMonth() + 1).padStart(2, "0");
  const day = String(today.getDate()).padStart(2, "0");
  return `${today.getFullYear()}-${month}-${day}`;
}

function formatDateForDisplay(dateValue) {
  if (!dateValue) return t("notProvided");

  const parts = String(dateValue).split("-");
  if (parts.length !== 3) return t("notProvided");

  const [year, month, day] = parts.map(Number);
  const date = new Date(year, month - 1, day);
  if (Number.isNaN(date.getTime())) return t("notProvided");

  return date.toLocaleDateString(LOCALE_MAP[currentLanguage] || "en-US", {
    year: "numeric",
    month: "long",
    day: "numeric"
  });
}

function isValidDOB(dateString) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(dateString || "")) return false;

  const [year, month, day] = dateString.split("-").map(Number);
  if (year < 1900 || year > new Date().getFullYear()) return false;
  if (month < 1 || month > 12 || day < 1 || day > 31) return false;

  const date = new Date(year, month - 1, day);
  if (date.getFullYear() !== year || date.getMonth() + 1 !== month || date.getDate() !== day) {
    return false;
  }

  const today = new Date();
  today.setHours(0, 0, 0, 0);
  return date <= today;
}

function formatMaskedDate(value) {
  const d = String(value || "").replace(/\D/g, "").slice(0, 8);
  if (d.length <= 2) return d;
  if (d.length <= 4) return `${d.slice(0, 2)}-${d.slice(2)}`;
  return `${d.slice(0, 2)}-${d.slice(2, 4)}-${d.slice(4)}`;
}

// MM-DD-YYYY -> YYYY-MM-DD (passes ISO through, returns "" if invalid format)
function displayDateToISO(value) {
  if (/^\d{4}-\d{2}-\d{2}$/.test(value || "")) return value;
  if (!/^\d{2}-\d{2}-\d{4}$/.test(value || "")) return "";
  const [month, day, year] = value.split("-");
  return `${year}-${month}-${day}`;
}

function validateDOBInput() {
  if (!dobInput) return true;

  if (dobInput.value) dobInput.value = formatMaskedDate(dobInput.value);

  if (!dobInput.value) {
    dobInput.setCustomValidity(t("dobRequired"));
    return false;
  }
  if (!isValidDOB(displayDateToISO(dobInput.value))) {
    dobInput.setCustomValidity(t("dobInvalid"));
    return false;
  }

  dobInput.setCustomValidity("");
  return true;
}

// ── Screens & modals ──────────────────────────────────────────

function showScreen(screen) {
  Object.values(screens).forEach((s) => (s.style.display = "none"));
  screen.style.display = "block";
}

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

function showThankYouScreen(key, serviceIds) {
  lastThankYou = { key, ids: [...serviceIds] };
  showScreen(screens.thankYou);
  thankYouMessage.textContent = tf(key, { services: formatServiceNamesFromIds(serviceIds) });
}

function resetToMainScreen() {
  Object.values(forms).forEach((form) => form.reset());

  phoneInput.value = "";
  if (dobInput) dobInput.value = "";
  newPicker.search.value = "";
  existingPicker.search.value = "";
  newPicker.selected.length = 0;
  existingPicker.selected.length = 0;

  showScreen(screens.phone);
  setMessage();

  phoneNumber = "";
  existingCustomer = null;
  profileEditToken = "";
  pendingNewCustomerPayload = null;
  pendingExistingReferralCode = "";
  lastThankYou = null;
}

// ── Services ──────────────────────────────────────────────────

function getServiceNameById(id) {
  return availableServices.find((s) => s.id === id)?.name ?? `Service ${id}`;
}

function formatServiceNamesFromIds(ids) {
  if (!ids || ids.length === 0) return t("noServicesSelected");
  return ids.map(getServiceNameById).join(", ");
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (c) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
  ));
}

function renderServiceList(picker) {
  const { list, search, selected } = picker;
  if (!list) return;

  const term = (search?.value || "").trim().toLowerCase();
  const matches = availableServices.filter((s) => s.name.toLowerCase().includes(term));

  if (matches.length === 0) {
    list.innerHTML = `<p class="queue-empty">${t("noMatchingServices")}</p>`;
    return;
  }

  list.innerHTML = matches
    .map((service) => {
      const inputId = `${list.id}_service_${service.id}`;
      const checked = selected.includes(service.id) ? "checked" : "";
      return `
        <label class="service-option" for="${inputId}">
          <input type="checkbox" id="${inputId}" value="${service.id}" ${checked} />
          <span>${escapeHtml(service.name)}</span>
        </label>`;
    })
    .join("");
}

function bindServicePicker(picker) {
  picker.search?.addEventListener("input", () => renderServiceList(picker));

  picker.list?.addEventListener("change", (event) => {
    const target = event.target;
    if (!(target instanceof HTMLInputElement) || target.type !== "checkbox") return;

    const serviceId = Number(target.value);
    if (!Number.isInteger(serviceId) || serviceId <= 0) return;

    const index = picker.selected.indexOf(serviceId);
    if (index >= 0) picker.selected.splice(index, 1);
    else picker.selected.push(serviceId);

    renderServiceList(picker);
  });
}

async function loadServices() {
  try {
    const data = await api("/services", { fallback: "Failed to load services." });
    availableServices = Array.isArray(data) ? data : [];

    // The catalog comes from the Owner (via the Check-In backend) and can change at any time:
    // drop selections that are no longer offered so they are never submitted.
    const activeIds = new Set(availableServices.map((s) => s.id));
    [selectedNewServiceIds, selectedExistingServiceIds].forEach((selected) => {
      for (let i = selected.length - 1; i >= 0; i--) {
        if (!activeIds.has(selected[i])) selected.splice(i, 1);
      }
    });

    renderServiceList(newPicker);
    renderServiceList(existingPicker);
  } catch (error) {
    console.error("Failed to load services:", error);
    const html = `<p class="queue-empty">${t("unableServices")}</p>`;
    [newPicker, existingPicker].forEach((p) => p.list && (p.list.innerHTML = html));
  }
}

function requireServiceSelection(picker) {
  if (picker.selected.length > 0) return true;
  setMessage(t("selectOneService"), "error");
  return false;
}

// ── Carousel ──────────────────────────────────────────────────

function renderSlide(index) {
  if (!carousel.image) return;

  const slide = CAROUSEL_SLIDES[index];
  carousel.image.style.backgroundImage = `url("${slide.image}")`;

  if (carousel.badge) carousel.badge.textContent = t(`${slide.key}Badge`);
  if (carousel.title) carousel.title.textContent = t(`${slide.key}Title`);
  if (carousel.text) carousel.text.textContent = t(`${slide.key}Text`);
}

function startCarousel() {
  if (!carousel.image) return;

  renderSlide(carouselIndex);
  setInterval(() => {
    carouselIndex = (carouselIndex + 1) % CAROUSEL_SLIDES.length;
    renderSlide(carouselIndex);
  }, CAROUSEL_INTERVAL_MS);
}

// ── Today's check-in list ─────────────────────────────────────

function formatCheckInTime(dateString) {
  return new Date(dateString).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
}

async function loadTodayCheckInOrder() {
  if (!isKioskPaired()) return; // nothing to show until this tablet is paired
  try {
    const data = await api("/queue-status", { fallback: "Failed to load today's check-in order." });

    if (!data.checkins || data.checkins.length === 0) {
      checkinOrderList.innerHTML = `<p class="queue-empty">${t("noCustomers")}</p>`;
      return;
    }

    checkinOrderList.innerHTML = data.checkins
      .map((item) => `
        <div class="queue-item">
          <div class="queue-item-left">
            <div class="queue-position">${item.position}</div>
            <div class="queue-name">${item.display_name || `Customer #${item.position}`}</div>
          </div>
          <div class="queue-time">${formatCheckInTime(item.checked_in_at)}</div>
        </div>`)
      .join("");

    checkinOrderList
      .querySelector(".queue-item:last-child")
      ?.scrollIntoView({ behavior: "smooth", block: "end" });
  } catch (error) {
    checkinOrderList.innerHTML = `<p class="queue-empty">${t("unableQueue")}</p>`;
  }
}

// ── Returning customer screens ────────────────────────────────

const customerPhoneDisplay = (c) =>
  safeText(c.phone_number_formatted || formatPhone(c.phone_number || ""));

function renderExistingCustomerProfile(customer) {
  if (!existingCustomerProfile || !customer) return;

  const row = (label, value) => `
    <div class="profile-row">
      <span class="profile-label">${label}</span>
      <span class="profile-value">${value}</span>
    </div>`;

  // Only what the tablet is allowed to know (first name, the phone number just typed, a masked email), and
  // always escaped: a name is user-entered text and must never be able to inject markup.
  existingCustomerProfile.innerHTML =
    row(t("name"), escapeHtml(safeText(customer.first_name))) +
    row(t("phone"), escapeHtml(customerPhoneDisplay(customer))) +
    row(t("email"), escapeHtml(safeText(customer.email_hint)));
}

function openExistingCustomerScreen() {
  if (!existingCustomer) return;

  existingCustomerName.textContent = tf("welcomeBack", { name: existingCustomer.first_name });
  renderExistingCustomerProfile(existingCustomer);
  showScreen(screens.existing);
  setMessage();
}

function showExistingCustomerServiceScreen() {
  renderServiceList(existingPicker);
  loadServices(); // re-fetch so renamed/deactivated services show up without a page reload
  showScreen(screens.existingServices);
  setMessage();
}

function showExistingCustomerReview() {
  if (!existingCustomer) return;

  const r = review.existing;
  r.name.textContent = safeText(existingCustomer.first_name);
  r.phone.textContent = customerPhoneDisplay(existingCustomer);
  r.email.textContent = safeText(existingCustomer.email_hint);
  r.referral.textContent = safeText(pendingExistingReferralCode);
  r.services.textContent = formatServiceNamesFromIds(existingPicker.selected);

  showScreen(screens.existingReview);
  setMessage();
}

function populateUpdateProfileForm(customer) {
  if (!customer) return;
  updateFullNameInput.value = customer.full_name || "";
  updatePhoneInput.value = formatPhone(customer.phone_number || "");
  updateEmailInput.value = customer.email || "";
}

// ── New customer screens ──────────────────────────────────────

function buildNewCustomerPayload() {
  const formData = new FormData(forms.newCustomer);
  const referralCode = formData.get("referral_code")?.trim().toUpperCase() || "";

  return {
    phone_number: phoneNumber,
    full_name: formData.get("full_name")?.trim(),
    email: formData.get("email")?.trim() || null,
    date_of_birth: displayDateToISO(formData.get("date_of_birth")),
    referral_code: referralCode || null
  };
}

function showNewCustomerServiceScreen() {
  renderServiceList(newPicker);
  loadServices(); // re-fetch so renamed/deactivated services show up without a page reload
  showScreen(screens.newServices);
  setMessage();
}

function showNewCustomerReview(payload) {
  pendingNewCustomerPayload = payload;

  const r = review.newCustomer;
  r.name.textContent = safeText(payload.full_name);
  r.dob.textContent = formatDateForDisplay(payload.date_of_birth);
  r.email.textContent = safeText(payload.email);
  r.referral.textContent = safeText(payload.referral_code);
  r.services.textContent = formatServiceNamesFromIds(newPicker.selected);

  showScreen(screens.newReview);
  setMessage();
}

// ── Event wiring ──────────────────────────────────────────────

const confirmNewCustomerBtn = $("confirm-new-customer-btn");
const confirmExistingCustomerBtn = $("confirm-existing-customer-btn");

function on(id, handler) {
  $(id)?.addEventListener("click", handler);
}

// Modals & home
if ($("close-birthday-modal")) {
  $("close-birthday-modal").addEventListener("click", hideBirthdayModal);
}

if ($("close-success-modal")) {
  $("close-success-modal").addEventListener("click", hideSuccessModal);
}

on("back-home-btn", resetToMainScreen);

// Input formatting
phoneInput.addEventListener("input", (e) => (e.target.value = formatPhone(e.target.value)));
updatePhoneInput.addEventListener("input", () => (updatePhoneInput.value = formatPhone(updatePhoneInput.value)));

if (dobInput) {
  dobInput.max = getTodayISODate();
  dobInput.min = "1900-01-01";
  dobInput.setAttribute("maxlength", "10");
  dobInput.setAttribute("inputmode", "numeric");
  dobInput.addEventListener("input", validateDOBInput);
  dobInput.addEventListener("change", validateDOBInput);
}

bindServicePicker(newPicker);
bindServicePicker(existingPicker);

// Phone lookup
forms.phone.addEventListener("submit", async (event) => {
  event.preventDefault();

  phoneNumber = rawDigits(phoneInput.value);

  if (phoneNumber.length !== 10) {
    setMessage(t("invalidPhone"), "error");
    return;
  }

  setMessage(t("checkingPhone"));

  try {
    const response = await kioskFetch(`/customers/by-phone/${encodeURIComponent(phoneNumber)}`);

    if (response.ok) {
      existingCustomer = await response.json();

      const status = await api(
        `/customers/check-in-status/${encodeURIComponent(phoneNumber)}`,
        { fallback: "Failed to check today's status." }
      );

      if (status.already_checked_in_today) {
        setMessage(tf("alreadyCheckedIn", { name: status.first_name }), "error");
        showScreen(screens.phone);
        return;
      }

      openExistingCustomerScreen();
      return;
    }

    if (response.status === 404) {
      existingCustomer = null;
      pendingNewCustomerPayload = null;
      newPicker.selected.length = 0;
      newPicker.search.value = "";
      setMessage();
      showScreen(screens.newForm);
      return;
    }

    const data = await response.json();
    throw new Error(getErrorMessage(data, "Something went wrong while checking phone number."));
  } catch (error) {
    setMessage(error.message || "Failed to check phone number.", "error");
  }
});

// New customer flow
forms.newCustomer.addEventListener("submit", (event) => {
  event.preventDefault();

  const payload = buildNewCustomerPayload();

  if (!validateDOBInput() || !isValidDOB(payload.date_of_birth)) {
    setMessage(t("dobInvalid"), "error");
    dobInput?.reportValidity();
    return;
  }

  pendingNewCustomerPayload = payload;
  showNewCustomerServiceScreen();
});

on("back-to-new-customer-form-btn", () => {
  showScreen(screens.newForm);
  setMessage();
});

on("continue-to-new-review-btn", () => {
  if (!pendingNewCustomerPayload) pendingNewCustomerPayload = buildNewCustomerPayload();
  if (!requireServiceSelection(newPicker)) return;
  showNewCustomerReview(pendingNewCustomerPayload);
});

on("edit-new-customer-btn", showNewCustomerServiceScreen);

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
        const validateResponse = await kioskFetch(`/referrals/validate`, {
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
      const createResponse = await kioskFetch(CREATE_CUSTOMER_PATH, {
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
        const applyResponse = await kioskFetch(`/referrals/apply`, {
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

      const checkInResponse = await kioskFetch(
        `/customers/check-in/${encodeURIComponent(phoneNumber)}`,
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
      loadServices(); // the chosen service may have been removed by the Owner; refresh the list
      messageBox.textContent = error.message || "Failed to save customer.";
      messageBox.className = "message error";
      messageBox.scrollIntoView({ behavior: "smooth", block: "center" });
    } finally {
      confirmNewCustomerBtn.disabled = false;
    }
  });
}

// Returning customer flow
forms.existingCustomer.addEventListener("submit", async (event) => {
  event.preventDefault();

  const referralCodeInput = document.getElementById("existing_referral_code");
  pendingExistingReferralCode = referralCodeInput.value.trim().toUpperCase();

  showExistingCustomerServiceScreen();
});

on("back-to-existing-customer-btn", openExistingCustomerScreen);

on("continue-to-existing-review-btn", () => {
  if (!requireServiceSelection(existingPicker)) return;
  showExistingCustomerReview();
});

on("edit-existing-customer-btn", showExistingCustomerServiceScreen);

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
        const applyResponse = await kioskFetch(`/referrals/apply`, {
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

      const checkInResponse = await kioskFetch(
        `/customers/check-in/${encodeURIComponent(phoneNumber)}`,
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
      const earnedReferralCode = !existingCustomer?.has_referral_code && !!checkInData.referral_code;

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
      loadServices(); // the chosen service may have been removed by the Owner; refresh the list
      messageBox.textContent = error.message || "Failed to process returning customer.";
      messageBox.className = "message error";
      messageBox.scrollIntoView({ behavior: "smooth", block: "center" });
    } finally {
      confirmExistingCustomerBtn.disabled = false;
    }
  });
}

// Update profile. A phone number alone is not enough: the birth date on file unlocks the details and returns a
// short-lived edit token, which the save then needs. Nothing about the customer is shown before that.
on("update-profile-btn", () => {
  profileEditToken = "";
  forms.verifyProfile.reset();
  showScreen(screens.verifyProfile);
  setMessage();
  verifyDobInput?.focus();
});

verifyDobInput?.addEventListener("input", () => {
  verifyDobInput.value = formatMaskedDate(verifyDobInput.value);
});

on("cancel-verify-profile-btn", () => {
  forms.verifyProfile.reset();
  profileEditToken = "";
  openExistingCustomerScreen();
});

forms.verifyProfile.addEventListener("submit", async (event) => {
  event.preventDefault();

  const dateOfBirth = displayDateToISO(verifyDobInput.value);
  if (!isValidDOB(dateOfBirth)) return setMessage(t("dobInvalid"), "error");

  try {
    const data = await api(`/customers/${encodeURIComponent(phoneNumber)}/profile-access`, {
      method: "POST",
      body: { date_of_birth: dateOfBirth },
      fallback: t("verifyFailed")
    });

    profileEditToken = data.edit_token;
    forms.verifyProfile.reset(); // the birth date is not kept on screen
    populateUpdateProfileForm(data.profile);
    showScreen(screens.updateProfile);
    setMessage();
  } catch (error) {
    forms.verifyProfile.reset();
    if (error.status === 403) setMessage(t("verifyFailed"), "error");
    else if (error.status === 429) setMessage(t("verifyLocked"), "error");
    else setMessage(error.message || t("verifyFailed"), "error");
  }
});

on("cancel-update-profile-btn", () => {
  forms.updateProfile.reset();
  profileEditToken = "";
  openExistingCustomerScreen();
});

forms.updateProfile.addEventListener("submit", async (event) => {
  event.preventDefault();

  const full_name = updateFullNameInput.value.trim();
  const phone_number = rawDigits(updatePhoneInput.value);
  const email = updateEmailInput.value.trim();

  if (!full_name) return setMessage(t("nameRequired"), "error");
  if (phone_number.length !== 10) return setMessage(t("phoneTenDigits"), "error");

  setMessage(t("updatingProfile"));

  try {
    const data = await api(`/customers/${encodeURIComponent(phoneNumber)}/profile`, {
      method: "PATCH",
      body: { full_name, phone_number, email: email || null },
      headers: { [KIOSK_PROFILE_EDIT_HEADER]: profileEditToken },
      fallback: "Failed to update profile."
    });

    profileEditToken = ""; // one confirmation, one edit
    existingCustomer = data;
    phoneNumber = data.phone_number;

    setMessage();
    showSuccessModal(tf("profileUpdated", { name: data.first_name }));

    forms.updateProfile.reset();
    openExistingCustomerScreen();
  } catch (error) {
    if (error.status === 403) {
      profileEditToken = ""; // expired or used: ask for the birth date again
      forms.updateProfile.reset();
      showScreen(screens.verifyProfile);
      setMessage(t("verifyNeeded"), "error");
      return;
    }
    setMessage(error.message || "Failed to update profile.", "error");
  }
});

// ── Language ──────────────────────────────────────────────────

const TEXT_BINDINGS = [
  [".brand", "salon"],
  [".hero h1", "welcome"],
  [".hero-subtitle", "heroSubtitle"],
  [".promo-disclaimer", "promoDisclaimer"],

  [".queue-card h2", "todayOrder"],
  [".queue-card .subtitle", "todayOrderSubtitle"],

  ["#phone-screen h2", "checkIn"],
  ["#phone-screen .subtitle", "enterPhone"],
  ['#phone-form button[type="submit"]', "continue"],

  ["#form-screen h2", "newCustomer"],
  ["#form-screen .subtitle", "completeInfo"],
  ['#new-customer-form button[type="submit"]', "continue"],

  ["#new-customer-service-screen h2", "selectServices"],
  ["#new-customer-service-screen .subtitle", "chooseServices"],
  ["#existing-customer-service-screen h2", "selectServices"],
  ["#existing-customer-service-screen .subtitle", "chooseServices"],
  ["#back-to-new-customer-form-btn", "back"],
  ["#continue-to-new-review-btn", "reviewInformation"],
  ["#back-to-existing-customer-btn", "back"],
  ["#continue-to-existing-review-btn", "reviewInformation"],

  ["#new-customer-review-screen h2", "reviewTitle"],
  ["#new-customer-review-screen .subtitle", "checkInformation"],
  ["#new-customer-review-screen .reminder-box", "checkInformation"],
  ["#existing-customer-review-screen h2", "reviewTitle"],
  ["#existing-customer-review-screen .subtitle", "checkInformation"],
  ["#existing-customer-review-screen .reminder-box", "checkInformation"],
  ["#edit-new-customer-btn", "edit"],
  ["#confirm-new-customer-btn", "continue"],
  ["#edit-existing-customer-btn", "edit"],
  ["#confirm-existing-customer-btn", "checkIn"],

  ["#existing-screen h2", "returningCustomer"],
  ['#existing-customer-form button[type="submit"]', "continue"],
  ["#update-profile-btn", "updateProfile"],

  ["#update-profile-screen h2", "updateProfile"],
  ["#update-profile-screen .subtitle", "editInformation"],
  ['#update-profile-form button[type="submit"]', "save"],
  ["#cancel-update-profile-btn", "cancel"],

  ["#verify-profile-screen h2", "verifyTitle"],
  ["#verify-profile-screen .subtitle", "verifyText"],
  ['#verify-profile-form button[type="submit"]', "continue"],
  ["#cancel-verify-profile-btn", "cancel"],

  ["#pairing-title", "pairTitle"],
  ["#pairing-text", "pairText"],
  ["#pairing-submit", "pairSubmit"],

  ["#thank-you-screen h2", "thankYou"],
  ["#back-home-btn", "backHome"],
  ["#birthday-modal h2", "happyBirthday"],
  ["#close-birthday-modal", "awesome"],
  ["#success-modal h2", "checkedIn"],
  ["#close-success-modal", "lovely"]
];

const PLACEHOLDER_BINDINGS = [
  ['#new-customer-form input[name="full_name"]', "fullName"],
  ['#new-customer-form input[name="email"]', "emailOptional"],
  ['#new-customer-form input[name="referral_code"]', "referralOptional"],
  ["#new-service-search", "searchServices"],
  ["#existing-service-search", "searchServices"],
  ["#existing_referral_code", "existingReferralOptional"],
  ["#update_full_name", "fullName"],
  ["#update_phone", "phoneNumber"],
  ["#update_email", "emailOptional"]
];

function applyBindings(bindings, property) {
  bindings.forEach(([selector, key]) => {
    const element = document.querySelector(selector);
    if (element) element[property] = t(key);
  });
}

function setLabels(screen, keys) {
  const labels = screen?.querySelectorAll(".profile-label");
  if (labels?.length >= keys.length) {
    keys.forEach((key, i) => (labels[i].textContent = t(key)));
  }
}

// Re-translates whatever dynamic content is currently on screen
function refreshDynamicScreens() {
  if (existingCustomer) {
    existingCustomerName.textContent = tf("welcomeBack", { name: existingCustomer.first_name });
    renderExistingCustomerProfile(existingCustomer);
  }

  if (screens.newReview.style.display === "block" && pendingNewCustomerPayload) {
    showNewCustomerReview(pendingNewCustomerPayload);
  }

  if (screens.existingReview.style.display === "block") {
    showExistingCustomerReview();
  }

  if (screens.thankYou.style.display === "block" && lastThankYou) {
    thankYouMessage.textContent = tf(lastThankYou.key, {
      services: formatServiceNamesFromIds(lastThankYou.ids)
    });
  }
}

function applyLanguage(lang) {
  if (!translations[lang]) lang = "en";

  currentLanguage = lang;
  localStorage.setItem("nailSalonLanguage", lang);
  document.documentElement.lang = lang;

  applyBindings(TEXT_BINDINGS, "textContent");
  applyBindings(PLACEHOLDER_BINDINGS, "placeholder");

  setLabels(screens.newReview, ["name", "birthday", "email", "referral", "services"]);
  setLabels(screens.existingReview, ["name", "phone", "email", "referral", "services"]);

  renderServiceList(newPicker);
  renderServiceList(existingPicker);
  renderSlide(carouselIndex);
  refreshDynamicScreens();
  loadTodayCheckInOrder();
}

const languageToggle = $("language-toggle");
const languageDropdown = $("language-dropdown");

if (languageToggle && languageDropdown) {
  languageToggle.addEventListener("click", (event) => {
    event.stopPropagation();
    languageDropdown.classList.toggle("hidden");
  });

  document.querySelectorAll(".language-option").forEach((button) => {
    button.addEventListener("click", () => {
      const lang = button.dataset.lang;
      applyLanguage(lang);
      languageToggle.textContent = LANGUAGE_LABELS[lang];
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
  languageToggle.textContent = LANGUAGE_LABELS[currentLanguage] || "🌐 EN";
}

// ── Init ──────────────────────────────────────────────────────

applyLanguage(currentLanguage);
startCarousel();
initKioskDevice(); // no device token yet -> the pairing screen
document.addEventListener("kiosk:paired", () => {
  loadServices();
  loadTodayCheckInOrder();
});
if (isKioskPaired()) {
  loadTodayCheckInOrder();
  loadServices();
}
setInterval(() => {
  if (isKioskPaired()) loadTodayCheckInOrder();
}, QUEUE_REFRESH_MS);
