// kiosk-device.js: this tablet's device credential, the pairing screen, and every authenticated kiosk call.
//
// How it works
//   * The salon owner creates a one-time pairing code in the Owner Dashboard (Salon Settings, Check-In Device).
//   * Typing it here (POST /kiosk/pair) returns a random per-device token, which is kept in this browser's
//     localStorage and sent as the X-Kiosk-Device-Token header on every kiosk request.
//   * If the server answers 401 (the owner revoked the tablet, or the token is gone) the token is dropped and the
//     pairing screen comes back. The token is never put in a URL, never logged and never shown on the page.
//
// Storage choice (Phase 2): localStorage is script-readable, so a script injected into this page could read the
// token. That is why the page has a strict Content-Security-Policy (no inline or foreign script, set by the proxy),
// customer data is escaped before it is rendered, and the token only unlocks the kiosk routes; the owner can revoke
// it at any time. An HttpOnly cookie would hide it from scripts and is the planned upgrade (see deploy/lan-poc/).
//
// Depends on: config.js (API_BASE). Uses t() from script.js when it is available, English otherwise.

const KIOSK_TOKEN_STORAGE_KEY = "nailKioskDeviceToken";
const KIOSK_DEVICE_HEADER = "X-Kiosk-Device-Token";
const KIOSK_PROFILE_EDIT_HEADER = "X-Profile-Edit-Token";

const KIOSK_FALLBACK_TEXT = {
  pairInvalid: "That pairing code is not valid or has expired. Please ask the owner for a new one.",
  pairTooMany: "Too many attempts. Please wait a few minutes and try again.",
  pairNetwork: "Cannot reach the salon computer. Please check the Wi-Fi and try again.",
  pairRevoked: "This tablet is no longer paired. Please pair it again.",
  pairEnterCode: "Please enter the pairing code."
};

// If the browser blocks storage (private mode) the token lives only in memory and is lost on reload.
let kioskTokenInMemory = "";

function kioskText(key) {
  if (typeof t === "function") {
    const translated = t(key);
    if (translated && translated !== key) return translated;
  }
  return KIOSK_FALLBACK_TEXT[key] || key;
}

function getKioskToken() {
  try {
    return localStorage.getItem(KIOSK_TOKEN_STORAGE_KEY) || kioskTokenInMemory;
  } catch {
    return kioskTokenInMemory;
  }
}

function storeKioskToken(token) {
  kioskTokenInMemory = token;
  try {
    localStorage.setItem(KIOSK_TOKEN_STORAGE_KEY, token);
  } catch {
    /* storage unavailable: the in-memory copy keeps this session working */
  }
}

function clearKioskToken() {
  kioskTokenInMemory = "";
  try {
    localStorage.removeItem(KIOSK_TOKEN_STORAGE_KEY);
  } catch {
    /* nothing to remove */
  }
}

function isKioskPaired() {
  return Boolean(getKioskToken());
}

// ── Pairing screen ────────────────────────────────────────────

function setPairingMessage(text = "", type = "") {
  const box = document.getElementById("pairing-message");
  if (!box) return;
  box.textContent = text;
  box.className = type ? `message ${type}` : "message";
}

function showPairingScreen(message = "") {
  const screen = document.getElementById("pairing-screen");
  const wasHidden = !screen || screen.classList.contains("hidden");
  if (screen) screen.classList.remove("hidden");
  if (message || wasHidden) setPairingMessage(message, message ? "error" : "");
  const input = document.getElementById("pairing-code");
  if (input && wasHidden) {
    // only when the screen first appears: a background request must not wipe a code being typed
    input.value = "";
    if (typeof input.focus === "function") input.focus();
  }
}

function hidePairingScreen() {
  const screen = document.getElementById("pairing-screen");
  if (screen) screen.classList.add("hidden");
  setPairingMessage();
}

// Called once at start-up: ask for a code when there is no token.
function initKioskDevice() {
  if (isKioskPaired()) hidePairingScreen();
  else showPairingScreen();
  return isKioskPaired();
}

// The server said this tablet is not (or no longer) paired.
function handleKioskUnauthorized() {
  const wasPaired = isKioskPaired();
  clearKioskToken();
  showPairingScreen(wasPaired ? kioskText("pairRevoked") : "");
}

// ── Pairing ───────────────────────────────────────────────────

async function redeemPairingCode(rawCode) {
  const code = String(rawCode || "").trim();
  if (!code) {
    setPairingMessage(kioskText("pairEnterCode"), "error");
    return false;
  }

  let response;
  try {
    // No device header here: the code IS the credential for this one request. The body carries the code, not the URL.
    response = await fetch(`${API_BASE}/kiosk/pair`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code }),
      cache: "no-store",
      credentials: "omit"
    });
  } catch {
    setPairingMessage(kioskText("pairNetwork"), "error");
    return false;
  }

  if (response.status === 429) {
    setPairingMessage(kioskText("pairTooMany"), "error");
    return false;
  }

  let data = null;
  try {
    data = await response.json();
  } catch {
    data = null;
  }

  if (!response.ok || !data || !data.device_token) {
    setPairingMessage(kioskText("pairInvalid"), "error");
    return false;
  }

  storeKioskToken(data.device_token);
  hidePairingScreen();
  document.dispatchEvent(new CustomEvent("kiosk:paired"));
  return true;
}

function bindPairingForm() {
  const form = document.getElementById("pairing-form");
  const input = document.getElementById("pairing-code");
  if (!form) return;
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const submit = document.getElementById("pairing-submit");
    if (submit) submit.disabled = true;
    try {
      await redeemPairingCode(input ? input.value : "");
    } finally {
      if (input) input.value = ""; // the code is single-use; never leave it on screen
      if (submit) submit.disabled = false;
    }
  });
}

// ── Authenticated kiosk requests ──────────────────────────────

// Every call to the Check-In API goes through here. `path` starts with "/" and is relative to API_BASE.
async function kioskFetch(path, options = {}) {
  const token = getKioskToken();
  if (!token) {
    showPairingScreen();
    throw new Error(kioskText("pairInvalid"));
  }

  const headers = { ...(options.headers || {}), [KIOSK_DEVICE_HEADER]: token };
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers,
    cache: "no-store",
    credentials: "omit"
  });

  if (response.status === 401) handleKioskUnauthorized();
  return response;
}

bindPairingForm();
