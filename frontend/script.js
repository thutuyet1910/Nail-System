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

const carouselImage = document.getElementById("carousel-image");
const adBadge = document.getElementById("ad-badge");
const adTitle = document.getElementById("ad-title");
const adText = document.getElementById("ad-text");
const phoneInput = document.getElementById("phone_number");

const API_BASE = "http://127.0.0.1:8000";
const CREATE_CUSTOMER_URL = `${API_BASE}/customers/new`;

let phoneNumber = "";
let existingCustomer = null;

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

// ── Phone formatting helpers ──────────────────────────────────

function formatPhone(value) {
  const digits = value.replace(/\D/g, "").slice(0, 10);
  if (digits.length < 4) return digits;
  if (digits.length < 7) return `(${digits.slice(0, 3)}) ${digits.slice(3)}`;
  return `(${digits.slice(0, 3)}) ${digits.slice(3, 6)}-${digits.slice(6)}`;
}

function rawDigits(value) {
  return value.replace(/\D/g, "");
}

// ── Discount message builder ──────────────────────────────────

function buildDiscountMessage(discounts) {
  if (!discounts || discounts.length === 0) return "";
  return discounts.map(d => d.description).join(" · ");
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
  birthdayModalText.textContent = `Happy Birthday ${fullName}! You have $${amount} off today.`;
  birthdayModal.classList.remove("hidden");
}

function hideBirthdayModal() {
  birthdayModal.classList.add("hidden");
}

function showThankYouScreen(text) {
  phoneScreen.style.display = "none";
  formScreen.style.display = "none";
  existingScreen.style.display = "none";
  if (updatePhoneScreen) updatePhoneScreen.style.display = "none";
  thankYouScreen.style.display = "block";
  thankYouMessage.textContent = text;
}

function formatCheckInTime(dateString) {
  const date = new Date(dateString);
  return date.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
}

// ── Today's check-in list ─────────────────────────────────────

async function loadTodayCheckInOrder() {
  try {
    const response = await fetch(`${API_BASE}/today-checkins`);
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "Failed to load today's check-in order.");
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

// ── Reset to main screen ──────────────────────────────────────

function resetToMainScreen() {
  customerForm.reset();
  existingCustomerForm.reset();
  phoneForm.reset();
  phoneInput.value = "";

  formScreen.style.display = "none";
  existingScreen.style.display = "none";
  thankYouScreen.style.display = "none";
  if (updatePhoneScreen) updatePhoneScreen.style.display = "none";
  phoneScreen.style.display = "block";

  messageBox.textContent = "";
  messageBox.className = "message";

  phoneNumber = "";
  existingCustomer = null;
}

closeBirthdayModalBtn.addEventListener("click", hideBirthdayModal);
backHomeBtn.addEventListener("click", resetToMainScreen);

// ── Phone input — format as (***) ***-**** ────────────────────

phoneInput.addEventListener("input", () => {
  const digits = rawDigits(phoneInput.value);
  phoneInput.value = formatPhone(digits);
});

// ── Phone form — look up customer ────────────────────────────

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

      if (!statusResponse.ok) throw new Error(statusData.detail || "Failed to check today's status.");

      if (statusData.already_checked_in_today) {
        messageBox.textContent = `${statusData.full_name} has already checked in today.`;
        messageBox.className = "message error";
        phoneScreen.style.display = "block";
        formScreen.style.display = "none";
        existingScreen.style.display = "none";
        thankYouScreen.style.display = "none";
        return;
      }

      existingCustomerName.textContent = `Welcome back, ${existingCustomer.full_name}`;
      messageBox.textContent = "";
      phoneScreen.style.display = "none";
      formScreen.style.display = "none";
      existingScreen.style.display = "block";
      thankYouScreen.style.display = "none";
      return;
    }

    if (response.status === 404) {
      existingCustomer = null;
      messageBox.textContent = "";
      phoneScreen.style.display = "none";
      existingScreen.style.display = "none";
      thankYouScreen.style.display = "none";
      formScreen.style.display = "block";
      return;
    }

    const data = await response.json();
    throw new Error(data.detail || "Something went wrong while checking phone number.");
  } catch (error) {
    messageBox.textContent = error.message || "Failed to check phone number.";
    messageBox.className = "message error";
  }
});

// ── New customer form ─────────────────────────────────────────

customerForm.addEventListener("submit", async (event) => {
  event.preventDefault();

  const formData = new FormData(customerForm);
  const referralCode = formData.get("referral_code")?.trim().toUpperCase() || "";

  const payload = {
    phone_number: phoneNumber,
    full_name: formData.get("full_name")?.trim(),
    email: formData.get("email")?.trim() || null,
    date_of_birth: formData.get("date_of_birth"),
    referral_code: referralCode || null,
  };

  messageBox.textContent = "Saving customer...";
  messageBox.className = "message";

  try {
    const createResponse = await fetch(CREATE_CUSTOMER_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    const createData = await createResponse.json();
    if (!createResponse.ok) throw new Error(createData.detail || "Failed to create customer.");

    let message = "";

    if (referralCode) {
      const applyResponse = await fetch(`${API_BASE}/referrals/apply`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ phone_number: phoneNumber, referral_code: referralCode }),
      });
      const applyData = await applyResponse.json();
      if (!applyResponse.ok) throw new Error(applyData.detail || "Failed to apply referral code.");
      message += `${applyData.message} `;
    }

    const checkInResponse = await fetch(
      `${API_BASE}/customers/check-in/${encodeURIComponent(phoneNumber)}`,
      { method: "POST" }
    );
    const checkInData = await checkInResponse.json();
    if (!checkInResponse.ok) throw new Error(checkInData.detail || "Failed to check in customer.");

    message += message
      ? `Checked in: ${checkInData.full_name}.`
      : `Customer saved and checked in: ${checkInData.full_name}.`;

    const discountMsg = buildDiscountMessage(checkInData.discounts_applied);
    if (discountMsg) message += ` ${discountMsg}`;

    if (checkInData.referral_code) {
      message += ` Your referral code: ${checkInData.referral_code} (share for 10% off).`;
    }

    const birthdayDiscount = checkInData.discounts_applied?.find(d => d.type === "birthday");
    if (birthdayDiscount) showBirthdayModal(checkInData.full_name, birthdayDiscount.amount);

    messageBox.textContent = message;
    messageBox.className = "message success";

    await loadTodayCheckInOrder();
    showThankYouScreen("You are checked in. Please take a seat and relax. A technician will be with you shortly.");
  } catch (error) {
    messageBox.textContent = error.message || "Failed to save customer.";
    messageBox.className = "message error";
  }
});

// ── Returning customer form ───────────────────────────────────

existingCustomerForm.addEventListener("submit", async (event) => {
  event.preventDefault();

  const referralCodeInput = document.getElementById("existing_referral_code");
  const referralCode = referralCodeInput.value.trim().toUpperCase();

  try {
    let message = "";

    if (referralCode) {
      const applyResponse = await fetch(`${API_BASE}/referrals/apply`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ phone_number: phoneNumber, referral_code: referralCode }),
      });
      const applyData = await applyResponse.json();
      if (!applyResponse.ok) throw new Error(applyData.detail || "Failed to apply referral code.");
      message += `${applyData.message} `;
    }

    const checkInResponse = await fetch(
      `${API_BASE}/customers/check-in/${encodeURIComponent(phoneNumber)}`,
      { method: "POST" }
    );
    const checkInData = await checkInResponse.json();
    if (!checkInResponse.ok) throw new Error(checkInData.detail || "Failed to check in customer.");

    message += `Welcome back, ${checkInData.full_name}!`;

    const discountMsg = buildDiscountMessage(checkInData.discounts_applied);
    if (discountMsg) message += ` ${discountMsg}`;

    if (checkInData.referral_code) {
      message += ` Your referral code: ${checkInData.referral_code} (share for 10% off).`;
    }

    const birthdayDiscount = checkInData.discounts_applied?.find(d => d.type === "birthday");
    if (birthdayDiscount) showBirthdayModal(checkInData.full_name, birthdayDiscount.amount);

    messageBox.textContent = message;
    messageBox.className = "message success";

    await loadTodayCheckInOrder();
    showThankYouScreen("Thank you for checking in. Please take a seat and enjoy your salon experience.");
  } catch (error) {
    messageBox.textContent = error.message || "Failed to process returning customer.";
    messageBox.className = "message error";
  }
});

// ── Update phone number (old customers) ──────────────────────

const updatePhoneScreen = document.getElementById("update-phone-screen");
const updatePhoneForm = document.getElementById("update-phone-form");
const updatePhoneBtn = document.getElementById("update-phone-btn");
const cancelUpdatePhoneBtn = document.getElementById("cancel-update-phone-btn");
const currentPhoneInput = document.getElementById("current_phone");
const newPhoneInput = document.getElementById("new_phone");

if (updatePhoneBtn) {
  updatePhoneBtn.addEventListener("click", () => {
    existingScreen.style.display = "none";
    updatePhoneScreen.style.display = "block";
    messageBox.textContent = "";
    messageBox.className = "message";
    if (currentPhoneInput) {
      currentPhoneInput.value = formatPhone(phoneNumber);
    }
  });
}

if (cancelUpdatePhoneBtn) {
  cancelUpdatePhoneBtn.addEventListener("click", () => {
    updatePhoneScreen.style.display = "none";
    existingScreen.style.display = "block";
    if (updatePhoneForm) updatePhoneForm.reset();
    messageBox.textContent = "";
    messageBox.className = "message";
  });
}

// Format current_phone and new_phone inputs as (***) ***-****
[currentPhoneInput, newPhoneInput].forEach(input => {
  if (!input) return;
  input.addEventListener("input", () => {
    input.value = formatPhone(rawDigits(input.value));
  });
});

if (updatePhoneForm) {
  updatePhoneForm.addEventListener("submit", async (event) => {
    event.preventDefault();

    const currentPhone = rawDigits(currentPhoneInput.value);
    const newPhone = rawDigits(newPhoneInput.value);

    if (currentPhone.length !== 10) {
      messageBox.textContent = "Current phone number must be exactly 10 digits.";
      messageBox.className = "message error";
      return;
    }
    if (newPhone.length !== 10) {
      messageBox.textContent = "New phone number must be exactly 10 digits.";
      messageBox.className = "message error";
      return;
    }
    if (currentPhone === newPhone) {
      messageBox.textContent = "New phone number must be different from the current one.";
      messageBox.className = "message error";
      return;
    }

    messageBox.textContent = "Updating phone number...";
    messageBox.className = "message";

    try {
      const response = await fetch(
        `${API_BASE}/customers/${currentPhone}/update-phone`,
        {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ new_phone_number: newPhone }),
        }
      );

      const data = await response.json();

      if (!response.ok) {
        messageBox.textContent = data.detail || "Failed to update phone number.";
        messageBox.className = "message error";
        return;
      }

      // Update the stored phone number so further actions use the new one
      phoneNumber = newPhone;

      messageBox.textContent = `Phone number updated successfully, ${data.full_name}! All your rewards are kept.`;
      messageBox.className = "message success";

      updatePhoneScreen.style.display = "none";
      updatePhoneForm.reset();

      showThankYouScreen("Your phone number has been updated. All rewards, visit history, and discounts are preserved.");
    } catch (error) {
      messageBox.textContent = error.message || "Failed to update phone number.";
      messageBox.className = "message error";
    }
  });
}

// ── Init ──────────────────────────────────────────────────────

startCarousel();
loadTodayCheckInOrder();
setInterval(loadTodayCheckInOrder, 10000);