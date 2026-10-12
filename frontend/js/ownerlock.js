// ownerlock.js: owner privilege with a 3-minute inactivity timeout.
//
// The dashboard always runs in STAFF mode (customers, appointments, checkout; no password). Owner
// Management is an elevation on top of it: a password login creates the backend owner session. After
// 180 seconds WITHOUT OWNER ACTIVITY the owner session is revoked on the server (POST /auth/logout,
// normal CSRF), all owner-only data is wiped from the page, and the app drops back to staff mode,
// which keeps working. Staff clicking around in the daily-operations screens never keeps the owner
// session alive: only trusted input while an owner screen (or an owner-only control) is in use counts.
//
// Nothing here stores the password or the unlock state: both live only in page variables.

const OWNER_LOCK_AFTER_MS = 3 * 60 * 1000;
const OWNER_ACTIVITY_EVENTS = ["pointerdown", "click", "keydown", "touchstart", "wheel"];

const OWNER_VIEW_NAV = {
    technicianView: "navTechnician", servicesView: "navServices", inventoryView: "navInventory",
    techIncomeView: "navTechIncome", salonIncomeView: "navSalonIncome", settingsView: "navSettings",
};
const OWNER_VIEW_IDS = Object.keys(OWNER_VIEW_NAV);

// Rendered from owner-only data. Emptied on lock, so the data is gone from the page, not merely hidden.
const OWNER_DATA_CONTAINER_IDS = [
    "technicianCards", "techIncomeContent", "techIncomeRangeContent", "salonIncomeContent",
    "inventoryTableBody", "serviceTableBody", "serviceTechnicians", "notificationsList",
    "businessHoursBody", "aiStatusList",
];

function ownerViewIsOpen() {
    return OWNER_VIEW_IDS.some((id) => document.getElementById(id)?.classList.contains("active-view"));
}

// Is this input part of OWNER work? Staff screens do not count.
function isOwnerContext(target) {
    if (ownerViewIsOpen()) return true;
    return Boolean(target && typeof target.closest === "function" && target.closest(".owner-only, #notificationsPanel"));
}

function noteOwnerActivity(event) {
    if (event && event.isTrusted === false) return;  // synthetic events (element.click(), dispatchEvent) never count
    if (ownerLocked) return;
    if (isOwnerContext(event && event.target)) ownerLastActivity = Date.now();
}

function ownerIdleCheck(now = Date.now()) {
    if (!ownerLocked && now - ownerLastActivity >= OWNER_LOCK_AFTER_MS) lockOwner();
}

function wipeOwnerData() {
    technicians = [];
    inventoryItems = [];
    ownerNotifications = [];
    techIncomeDateSummaries = [];
    techIncomeRangeSummaries = [];
    OWNER_DATA_CONTAINER_IDS.forEach((id) => {
        const element = document.getElementById(id);
        if (element) element.innerHTML = "";
    });
    document.querySelectorAll(".owner-view form").forEach((form) => form.reset());
    document.querySelectorAll(".owner-view .summary-card strong").forEach((element) => { element.textContent = ""; });
}

// Revokes the backend OWNER session (the staff session is separate and stays). Never blocks or reverses
// the lock: the page is already wiped, and a failed request is retried a few times in the background.
const OWNER_LOGOUT_RETRIES = 3;
async function logoutOwnerSession(attempt = 1) {
    try {
        await fetchJson(`${API_BASE}/auth/logout`, { method: "POST" });
        return true;
    } catch (error) {
        if (attempt < OWNER_LOGOUT_RETRIES) setTimeout(() => { if (ownerLocked) logoutOwnerSession(attempt + 1); }, 5000);
        return false;
    }
}

function lockOwner(options = {}) {
    if (ownerLocked) return;
    const wasInOwnerView = ownerViewIsOpen();
    ownerLocked = true;
    ownerAuthenticated = false;  // owner-only pollers stop; staff pollers run on staffReady
    ownerSessionExpiresAt = null;
    if (typeof setNotificationsPanelOpen === "function") setNotificationsPanelOpen(false);
    if (wasInOwnerView && typeof closeCuteConfirm === "function") closeCuteConfirm(false);
    wipeOwnerData();
    document.body.classList.add("owner-locked");  // hides every .owner-only / .owner-view element
    if (wasInOwnerView) showView("calendar");  // back to the staff home screen; nothing else changes
    // A request already in flight when the lock fired may still render: clear it again shortly after.
    setTimeout(() => { if (ownerLocked) wipeOwnerData(); }, 3000);
    if (!(options && options.serverSignedOut === true)) logoutOwnerSession();  // real revocation; deliberately not awaited
}

// Called after the backend has verified the owner password.
async function markOwnerUnlocked() {
    ownerLocked = false;
    ownerLastActivity = Date.now();
    document.body.classList.remove("owner-locked");
    try {
        await loadNotifications();
    } catch (error) {
        console.error("Owner data failed to load after unlock:", error);
    }
}

OWNER_ACTIVITY_EVENTS.forEach((name) => document.addEventListener(name, noteOwnerActivity, { passive: true, capture: true }));
document.addEventListener("visibilitychange", () => { if (!document.hidden) ownerIdleCheck(); });
setInterval(() => ownerIdleCheck(), 1000);

lockNowBtn?.addEventListener("click", lockOwner);
