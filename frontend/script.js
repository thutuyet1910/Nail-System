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

const carouselSlides = [
  {
    image: "https://images.unsplash.com/photo-1604654894610-df63bc536371?auto=format&fit=crop&w=1400&q=80",
    badge: "Referral Reward",
    title: "Get 10% Off With Referral",
    text: "Use a valid referral code and enjoy 10% off your salon services."
  },
  {
    image: "https://images.unsplash.com/photo-1522337660859-02fbefca4702?auto=format&fit=crop&w=1400&q=80",
    badge: "Birthday Special",
    title: "Birthday Reward",
    text: "Celebrate your birthday with a special $10 off on your birthday."
  },
  {
    image: "https://images.unsplash.com/photo-1519014816548-bf5fe059798b?auto=format&fit=crop&w=1400&q=80",
    badge: "Salon Rewards",
    title: "Enjoy Exclusive Benefits",
    text: "Visit more often and unlock special salon rewards and referral benefits."
  },
  {
    image: "https://images.unsplash.com/photo-1610992015732-2449b76344bc?auto=format&fit=crop&w=1400&q=80",
    badge: "Relax & Enjoy",
    title: "Check In and Relax",
    text: "Check in quickly, take a seat, and enjoy a relaxing salon experience."
  }
];

let carouselIndex = 0;

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
  return value && String(value).trim() ? value : "Not provided";
}

function getTodayISODate() {
  const today = new Date();
  const year = today.getFullYear();
  const month = String(today.getMonth() + 1).padStart(2, "0");
  const day = String(today.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function formatDateForDisplay(dateValue) {
  if (!dateValue) return "Not provided";

  const parts = String(dateValue).split("-");
  if (parts.length !== 3) return "Not provided";

  const [year, month, day] = parts.map(Number);
  const date = new Date(year, month - 1, day);

  if (Number.isNaN(date.getTime())) return "Not provided";

  return date.toLocaleDateString([], {
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
  dobInput.setAttribute("inputmode", "numeric");
}

function validateDOBInput() {
  if (!dobInput) return true;

  const value = dobInput.value;

  if (!value) {
    dobInput.setCustomValidity("Please select your date of birth.");
    return false;
  }

  if (!isValidDOB(value)) {
    dobInput.setCustomValidity("Please enter a valid date of birth with a 4-digit year.");
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

function getServiceNameById(id) {
  const service = availableServices.find(item => item.id === id);
  return service ? service.name : `Service ${id}`;
}

function formatServiceNamesFromIds(ids) {
  if (!ids || ids.length === 0) return "No services selected";
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
      newServiceList.innerHTML = `<p class="queue-empty">Unable to load services.</p>`;
    }
    if (existingServiceList) {
      existingServiceList.innerHTML = `<p class="queue-empty">Unable to load services.</p>`;
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
    container.innerHTML = `<p class="queue-empty">No matching services found.</p>`;
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

  if (adBadge) adBadge.textContent = slide.badge;
  if (adTitle) adTitle.textContent = slide.title;
  if (adText) adText.textContent = slide.text;
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

function showThankYouScreen(text) {
  hideAllMainScreens();
  thankYouScreen.style.display = "block";
  thankYouMessage.textContent = text;
}

function formatCheckInTime(dateString) {
  const date = new Date(dateString);
  return date.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
}

function renderExistingCustomerProfile(customer) {
  if (!existingCustomerProfile || !customer) return;

  existingCustomerProfile.innerHTML = `
    <div class="profile-row">
      <span class="profile-label">Name</span>
      <span class="profile-value">${safeText(customer.full_name)}</span>
    </div>
    <div class="profile-row">
      <span class="profile-label">Phone</span>
      <span class="profile-value">${safeText(customer.phone_number_formatted || formatPhone(customer.phone_number || ""))}</span>
    </div>
    <div class="profile-row">
      <span class="profile-label">Email</span>
      <span class="profile-value">${safeText(customer.email)}</span>
    </div>
    <div class="profile-row">
      <span class="profile-label">Birthday</span>
      <span class="profile-value">${formatDateForDisplay(customer.date_of_birth)}</span>
    </div>
  `;
}

function openExistingCustomerScreen() {
  if (!existingCustomer) return;

  existingCustomerName.textContent = `Welcome back, ${existingCustomer.full_name}`;
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
      checkinOrderList.innerHTML = `<p class="queue-empty">No customers checked in yet.</p>`;
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
  } catch (error) {
    checkinOrderList.innerHTML = `<p class="queue-empty">Unable to load check-in order.</p>`;
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
    messageBox.textContent = "Please enter a valid 10-digit phone number.";
    messageBox.className = "message error";
    return;
  }

  messageBox.textContent = "Checking phone number...";
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
        messageBox.textContent = `${statusData.full_name} has already checked in today.`;
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
    date_of_birth: formData.get("date_of_birth"),
    referral_code: referralCode || null
  };
}

customerForm.addEventListener("submit", async (event) => {
  event.preventDefault();

  const payload = buildNewCustomerPayload();

  if (!validateDOBInput() || !isValidDOB(payload.date_of_birth)) {
    messageBox.textContent = "Please enter a valid date of birth with a 4-digit year.";
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
      messageBox.textContent = "Please select at least one service.";
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
      messageBox.textContent = "Please select at least one service.";
      messageBox.className = "message error";
      return;
    }

    confirmNewCustomerBtn.disabled = true;
    messageBox.textContent = "Saving customer...";
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

        referralAppliedMessage = `You’ve received ${applyData.discount_percent}% off today as a referral reward from ${applyData.referral_from_customer_name}.`;
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
        successText = `Happy Birthday, ${checkInData.full_name}! ✨
Enjoy a complimentary $${birthdayDiscount.amount} birthday reward today.
Sit back, relax, and let us take care of you.`;
      } else if (referralAppliedMessage) {
        successText = `Welcome, ${checkInData.full_name}! ✨
${referralAppliedMessage}
Enjoy your visit with us.`;
      } else if (referralRewardDiscount) {
        successText = `Congratulations, ${checkInData.full_name}! ✨
Your ${referralRewardDiscount.percent}% referral reward has been unlocked and applied today.
Thank you for sharing the love with others.`;
      } else if (earnedReferralCode) {
        successText = `You’ve unlocked a special reward, ${checkInData.full_name}! ✨
Your personal referral code is ${checkInData.referral_code}.
Share it with friends and give them 10% off their visit.`;
      }

      messageBox.textContent = "";
      messageBox.className = "message";

      await loadTodayCheckInOrder();

      if (birthdayDiscount || referralAppliedMessage || referralRewardDiscount || earnedReferralCode) {
        showSuccessModal(successText);
      }

      const selectedServicesText = formatServiceNamesFromIds(selectedNewServiceIds);

      pendingNewCustomerPayload = null;
      selectedNewServiceIds.length = 0;

      showThankYouScreen(
        `You are checked in for: ${selectedServicesText}. Please take a seat and relax. A technician will be with you shortly.`
      );
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
      messageBox.textContent = "Please select at least one service.";
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
      messageBox.textContent = "Please select at least one service.";
      messageBox.className = "message error";
      return;
    }

    confirmExistingCustomerBtn.disabled = true;
    messageBox.textContent = "Processing check-in...";
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

        referralAppliedMessage = `You’ve received ${applyData.discount_percent}% off today as a referral reward from ${applyData.referral_from_customer_name}.`;
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
        successText = `Happy Birthday, ${checkInData.full_name}! ✨
Enjoy a complimentary $${birthdayDiscount.amount} birthday reward today.
Sit back, relax, and let us take care of you.`;
      } else if (referralAppliedMessage) {
        successText = `Welcome back, ${checkInData.full_name}! ✨
${referralAppliedMessage}
Enjoy your salon experience.`;
      } else if (referralRewardDiscount) {
        successText = `Congratulations, ${checkInData.full_name}! ✨
Your ${referralRewardDiscount.percent}% referral reward has been unlocked and applied today.
Thank you for sharing the love with others.`;
      } else if (earnedReferralCode) {
        successText = `You’ve unlocked a special reward, ${checkInData.full_name}! ✨
Your personal referral code is ${checkInData.referral_code}.
Share it with friends and give them 10% off their visit.`;
      }

      messageBox.textContent = "";
      messageBox.className = "message";

      await loadTodayCheckInOrder();

      if (birthdayDiscount || referralAppliedMessage || referralRewardDiscount || earnedReferralCode) {
        showSuccessModal(successText);
      }

      const selectedServicesText = formatServiceNamesFromIds(selectedExistingServiceIds);

      selectedExistingServiceIds.length = 0;
      pendingExistingReferralCode = "";

      showThankYouScreen(
        `Thank you for checking in for: ${selectedServicesText}. Please take a seat and enjoy your salon experience.`
      );
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
      messageBox.textContent = "Name is required.";
      messageBox.className = "message error";
      return;
    }

    if (updatedPhone.length !== 10) {
      messageBox.textContent = "Phone number must be exactly 10 digits.";
      messageBox.className = "message error";
      return;
    }

    messageBox.textContent = "Updating profile...";
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

      showSuccessModal(
        `Profile updated successfully, ${data.full_name}. Your rewards, referral code, birthday benefits, and visit history all stay on the same account.`
      );

      updateProfileForm.reset();
      openExistingCustomerScreen();
    } catch (error) {
      messageBox.textContent = error.message || "Failed to update profile.";
      messageBox.className = "message error";
    }
  });
}

// ── Init ──────────────────────────────────────────────────────

startCarousel();
loadTodayCheckInOrder();
loadServices();
setInterval(loadTodayCheckInOrder, 10000);