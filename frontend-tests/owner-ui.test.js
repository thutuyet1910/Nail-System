// Run: node frontend-tests/owner-ui.test.js   (no dependencies; the real dashboard scripts in a fake DOM)
process.env.TZ = "Pacific/Auckland";  // the dashboard must follow the SALON clock, not this computer's
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const assert = require("assert");

const root = path.join(__dirname, "..", "frontend");
const read = (rel) => fs.readFileSync(path.join(root, rel), "utf8");
const results = [];
const test = (name, fn) => results.push([name, fn]);
const tick = () => new Promise((r) => setImmediate(r));

function makeEnv({ realFetchJson = false } = {}) {
  let clock = 1_000_000;
  const env = {};
  const elements = new Map();
  const writes = { storage: [], cookies: [] };
  const docHandlers = {};
  const intervals = [];
  const mkClassList = () => {
    const set = new Set();
    return { add: (...c) => c.forEach((x) => set.add(x)), remove: (...c) => c.forEach((x) => set.delete(x)),
      contains: (c) => set.has(c), toggle(c, on) { (on === undefined ? !set.has(c) : on) ? set.add(c) : set.delete(c); }, _set: set };
  };
  const stub = (id) => ({ id, innerHTML: "", textContent: "", value: "", dataset: {}, attrs: {}, classList: mkClassList(), clicks: 0, resets: 0, handlers: {},
    setAttribute(k, v) { this.attrs[k] = String(v); }, addEventListener(t, f) { this.handlers[t] = f; },
    click() { this.clicks++; if (this.handlers.click) this.handlers.click({ isTrusted: false, target: this }); },
    focus() {}, contains() { return false; }, querySelectorAll() { return []; }, reset() { this.resets++; }, scrollIntoView() {} });
  const getEl = (id) => { if (!elements.has(id)) elements.set(id, stub(id)); return elements.get(id); };
  const forms = [stub("form1"), stub("form2")];
  const ownerForms = [stub("ownerForm")];
  const document = {
    getElementById: getEl,
    querySelectorAll: (sel) => (sel === ".owner-view form" ? ownerForms : sel === "form" ? forms.concat(ownerForms) : []),
    addEventListener: (t, f) => { (docHandlers[t] = docHandlers[t] || []).push(f); },
    body: { classList: mkClassList() },
    hidden: false,
    get cookie() { return env.cookie; }, set cookie(v) { writes.cookies.push(v); },
  };
  document.body.classList.add("owner-locked");  // as shipped in index.html
  class FakeDate extends Date {
    constructor(...args) { if (args.length) super(...args); else super(clock); }
    static now() { return clock; }
  }
  const calls = { fetch: [], messages: [], pinAsked: 0, renders: 0 };
  const ctx = {
    console: { log() {}, info() {}, warn() {}, error() {} }, document, Date: FakeDate, Intl, JSON, Math, Promise, Error, Array, Object, String, Number, Set, Map, RegExp,
    localStorage: { setItem: (k, v) => writes.storage.push(["local", k, v]), getItem: () => null },
    sessionStorage: { setItem: (k, v) => writes.storage.push(["session", k, v]), getItem: () => null },
    setInterval: (fn, ms) => { intervals.push([fn, ms]); return intervals.length; },
    setTimeout: (fn, ms) => { intervals.push([fn, ms, "once"]); return intervals.length; },
    clearTimeout() {}, window: { scrollTo() {} },
  };
  vm.createContext(ctx);
  const load = (rel) => vm.runInContext(read(rel), ctx, { filename: rel });
  const run = (code) => vm.runInContext(code, ctx);
  ["js/config.js", "js/dom.js", "js/state.js", "js/utils.js", "js/calendar.js", "js/ui.js", "js/calendar-refresh.js", "js/dashboard-load.js", "js/ownerlock.js", "js/salon-settings.js"].forEach(load);
  run(`
    var resetCalls = 0, notificationLoads = 0, panelClosed = 0, confirmClosed = 0;
    async function resetTemporaryUnavailableTechs() { resetCalls++; }
    async function loadNotifications() { notificationLoads++; }
    function setNotificationsPanelOpen(open) { if (!open) panelClosed++; }
    function closeCuteConfirm() { confirmClosed++; }
    // The loaders dashboard-load.js orchestrates: same URLs and the same fail/swallow behaviour as the real ones.
    function installFourDigitYearGuard() {}
    function checkApi() { return Promise.resolve(); }
    function syncDefaultSpecialtiesToFilter() {}
    function populateAppointmentTechnicianDropdown() {}
    async function loadBookingServices() { bookingServices = await fetchJson(API_BASE + "/services"); }
    async function loadBusinessHours() { try { businessHours = await fetchJson(API_BASE + "/business-hours"); } catch (e) { /* keeps last hours */ } }
    async function loadTechniciansRaw() { techniciansAll = await fetchJson(API_BASE + "/technicians?include_inactive=true"); techniciansRaw = techniciansAll.filter((t) => t.is_active !== false); }
    async function loadTechnicians() { technicians = await fetchJson(API_BASE + "/technicians/cards"); await loadTechniciansRaw(); }
    async function loadAppointments() { appointments = await fetchJson(API_BASE + "/appointments"); }
    async function loadTodayTurns() { try { todayTurns = await fetchJson(API_BASE + "/turns/today"); } catch (e) { todayTurns = []; } }
    async function loadCheckoutHistory() { try { await fetchJson(API_BASE + "/checkouts"); } catch (e) { /* logged by the real one */ } }
    async function loadLiveCheckinQueue() { try { await fetchJson(API_BASE + "/checkins/today"); } catch (e) { /* shows its own message elsewhere */ } }
  `);
  Object.assign(env, {
    ctx, run, getEl, document, writes, intervals, calls, docHandlers, cookie: "", forms, ownerForms,
    advance(ms) { clock += ms; }, now: () => clock, setNow(iso) { clock = Date.parse(iso); },
    fire(type, init = {}) { (docHandlers[type] || []).forEach((f) => f({ isTrusted: true, ...init })); },
    password: "correct horse", ownerSession: false, staffSession: false, staffFails: false, loginFails: false,
    logoutFails: false, logouts: 0, staffSessions: 0, nextPassword: undefined, appointmentsOnServer: [], appointmentFetchFails: false,
    expireStaffOnce: false, rawRequests: [],
    failures: {}, failureMessage: null, expireStaff: 0, gate: null, techniciansOnServer: [], hoursOnServer: [],
  });
  const handler = async (url, options = {}) => {
    calls.fetch.push([url, options.method || "GET"]);
    if (url.endsWith("/auth/staff-session")) {
      if (env.staffFails) throw new Error("backend down");
      env.staffSession = true; env.staffSessions++;
      return { role: "staff" };
    }
    if (url.endsWith("/auth/logout")) {
      env.logouts++;
      if (env.logoutFails) throw new Error("Could not connect to backend");
      env.ownerSession = false;
      return { message: "Logged out" };
    }
    if (url.endsWith("/auth/session")) return { authenticated: env.ownerSession, expires_at: "2099-01-01T00:00:00" };
    const failing = Object.keys(env.failures).find((key) => url.includes(key) && env.failures[key] !== 0);
    if (failing) {
      if (env.failures[failing] > 0) env.failures[failing]--;
      throw new Error(env.failureMessage || `Could not connect to backend: ${url}`);
    }
    if (env.expireStaff > 0 && !url.includes("/auth/")) {  // the staff session lapsed under several requests at once
      env.expireStaff--;
      const lapsed = new Error("Staff session required"); lapsed.status = 401; throw lapsed;
    }
    if (env.gate && url.endsWith("/appointments")) await env.gate;
    if (url.endsWith("/auth/login")) {
      const body = JSON.parse(options.body);
      if (env.loginFails || body.password !== env.password) throw new Error("Invalid owner credentials");
      env.ownerSession = true;
      return { authenticated: true, expires_at: "2099-01-01T00:00:00" };
    }
    if (url.endsWith("/appointments")) {
      if (env.expireStaffOnce) { env.expireStaffOnce = false; env.staffSession = false; const e = new Error("Staff session required"); e.status = 401; throw e; }
      if (env.appointmentFetchFails) throw new Error("backend down");
      return JSON.parse(JSON.stringify(env.appointmentsOnServer));
    }
    if (url.includes("/technicians")) return JSON.parse(JSON.stringify(env.techniciansOnServer));
    if (url.endsWith("/business-hours")) return JSON.parse(JSON.stringify(env.hoursOnServer));
    return [];
  };
  ctx.fetch = async (url, options = {}) => {  // raw fetch: the staff-session bootstrap (and, in realFetchJson mode, everything)
    if (!url.endsWith("/auth/staff-session") && !realFetchJson) throw new Error("raw fetch must not be used for " + url);
    env.rawRequests.push({ url, method: options.method || "GET", headers: options.headers || {}, credentials: options.credentials });
    try {
      const data = await handler(url, options);
      return { ok: true, status: 200, json: async () => data };
    } catch (error) {
      const status = error.status || 503;
      return { ok: false, status, clone() { return this; }, json: async () => ({ detail: error.message }), text: async () => error.message };
    }
  };
  if (!realFetchJson) ctx.fetchJson = handler;
  ctx.showCuteNotification = (message, title) => calls.messages.push([title, message]);
  ctx.askPin = async () => { calls.pinAsked++; return env.nextPassword === undefined ? env.password : env.nextPassword; };
  ctx.renderCalendar = () => { calls.renders++; };
  return env;
}

const state = (env, name) => env.run(name);
const unlock = async (env) => { assert.strictEqual(await env.run("requireOwner()"), true); };
const openView = (env, id) => env.getEl(id).classList.add("active-view");
const staffUp = async (env) => { assert.strictEqual(await env.run("ensureStaffSession()"), true); };
const ownerUp = async (env) => { await staffUp(env); await unlock(env); openView(env, "technicianView"); };

const OWNER_CONTAINERS = ["technicianCards", "techIncomeContent", "techIncomeRangeContent", "salonIncomeContent", "inventoryTableBody", "serviceTableBody", "serviceTechnicians", "notificationsList"];
const STAFF_CONTAINERS = ["calendarWrapper", "liveCheckinQueue", "checkoutReadyList", "checkoutHistoryList", "appointmentModalContent"];

// ------------------------------------------------------------------ navigation / static structure
test("the sidebar is split into Daily Operations (staff) and Management (owner); Log Out is gone", () => {
  const html = read("index.html");
  assert(!/logoutBtn|navLogout/.test(html) && !/>\s*Log Out\s*</.test(html));
  assert(!/ownerLockScreen|ownerUnlockBtn/.test(html), "no full-screen lock overlay any more");
  const nav = /<nav class="menu">([\s\S]*?)<\/nav>/.exec(html)[1];
  const staffPart = nav.slice(0, nav.indexOf('id="navOwner"'));
  for (const id of ["navCustomerList", "navAppointment", "navCheckout"]) assert(staffPart.includes(`id="${id}"`), id + " is a daily-operations item");
  const group = /<div id="ownerNavGroup"[^>]*class="[^"]*owner-only[^"]*">([\s\S]*?)<\/div>/.exec(nav)[1];
  for (const id of ["navTechnician", "navServices", "navInventory", "navTechIncome", "navSalonIncome"]) assert(group.includes(`id="${id}"`), id + " is owner-only");
  for (const id of ["navCustomerList", "navAppointment", "navCheckout"]) assert(!group.includes(id));
  assert(/Daily Operations/.test(nav) && /Management/.test(nav) && /Owner Management/.test(nav));
  for (const view of ["technicianView", "servicesView", "inventoryView", "techIncomeView", "salonIncomeView"]) assert(new RegExp(`id="${view}" class="view owner-view"`).test(html), view);
  assert(/history-all-btn owner-only/.test(html) && /history-range-card owner-only/.test(html), "history beyond today is owner-only");
  assert(/<body class="owner-locked">/.test(html), "page starts in staff mode");
  assert(/body\.owner-locked \.owner-only,\s*body\.owner-locked \.owner-view \{ display: none !important; \}/.test(read("styles.css")));
  for (const file of fs.readdirSync(path.join(root, "js"))) assert(!/logoutBtn|ownerLockScreen/.test(read("js/" + file)), file);
});

test("staff navigation never asks for the owner password; every owner navigation does", () => {
  const main = read("js/main.js");
  const handler = (id) => new RegExp(`${id}\\?\\.addEventListener\\("click", async \\(\\) => \\{([\\s\\S]*?)\\n\\}\\);`).exec(main)[1];
  for (const id of ["navCustomerList", "navAppointment", "navCheckout"]) assert(!/requireOwner/.test(handler(id)), id);
  for (const id of ["navOwner", "navTechnician", "navServices", "navInventory", "navTechIncome", "navSalonIncome"]) assert(/requireOwner/.test(handler(id)), id);
});

test("staff screens only use staff-safe endpoints", () => {
  const forbidden = /\/income\/|\/inventory|\/booking-services|\/notifications|\/technicians\/cards|\/callbacks|method:\s*"DELETE"/;
  for (const file of ["js/queue.js", "js/checkout.js", "js/appointments.js", "js/calendar.js", "js/calendar-refresh.js"]) assert(!forbidden.test(read(file)), file);
  const main = read("js/main.js");
  const loader = read("js/dashboard-load.js");
  assert(/if \(!ownerLocked\) \{\s*await loadTechnicians\(\);/.test(loader) && /await loadTechniciansRaw\(\);[^\n]*\s*populateAppointmentTechnicianDropdown\(\);/.test(loader), "loadAll uses owner-only cards only in owner mode");
  assert(!/initializeOwnerDashboard\(\)[\s\S]{0,80}requireOwner/.test(main), "start-up never prompts for the owner password");
});

// ------------------------------------------------------------------ staff mode
test("a fresh page opens in staff mode: staff session, no password prompt, owner privilege off", async () => {
  const env = makeEnv();
  assert.strictEqual(state(env, "ownerLocked"), true);
  assert.strictEqual(state(env, "staffReady"), false);
  await staffUp(env);
  assert.strictEqual(env.calls.pinAsked, 0);
  assert.strictEqual(env.rawRequests.filter((r) => r.url.endsWith("/auth/staff-session") && r.method === "POST").length, 1);
  assert.strictEqual(env.rawRequests[0].credentials, "include");
  assert.strictEqual(state(env, "appSessionReady()"), true);
  assert.strictEqual(state(env, "ownerAuthenticated"), false);
  assert(env.document.body.classList.contains("owner-locked"));
});

test("if the staff session cannot be created the dashboard is not ready and does not poll", async () => {
  const env = makeEnv();
  env.staffFails = true;
  assert.strictEqual(await env.run("ensureStaffSession()"), false);
  assert.strictEqual(state(env, "appSessionReady()"), false);
  env.calls.fetch.length = 0;
  assert.strictEqual(await env.run("refreshAppointmentsIfChanged()"), false);
  assert.strictEqual(env.calls.fetch.length, 0, "no polling without a session");
});

test("a lapsed staff session (server restart) is re-created once, transparently, by the real fetchJson", async () => {
  const env = makeEnv({ realFetchJson: true });
  await staffUp(env);
  env.expireStaffOnce = true;
  env.appointmentsOnServer = [{ id: 1 }];
  const rows = await env.run('fetchJson(`${API_BASE}/appointments`)');
  assert.strictEqual(JSON.stringify(rows), '[{"id":1}]');
  assert.strictEqual(env.staffSessions, 2, "one new staff session, one retry");
});

test("the real fetchJson sends the staff CSRF header, and the owner one only when an owner session exists", async () => {
  const env = makeEnv({ realFetchJson: true });
  env.cookie = "staff_session=s; staff_csrf=staff%2Ftok";
  env.rawRequests.length = 0;
  await env.run('fetchJson(`${API_BASE}/checkouts`, { method: "POST", body: "{}" })');
  let sent = env.rawRequests[0].headers;
  assert.strictEqual(sent["X-Staff-CSRF-Token"], "staff/tok");
  assert(!("X-CSRF-Token" in sent));
  env.cookie = "owner_session=o; owner_csrf=own%2Ftok; staff_session=s; staff_csrf=staff%2Ftok";
  env.rawRequests.length = 0;
  await env.run('fetchJson(`${API_BASE}/checkouts`, { method: "POST", body: "{}" })');
  sent = env.rawRequests[0].headers;
  assert.strictEqual(sent["X-CSRF-Token"], "own/tok");
  assert.strictEqual(sent["X-Staff-CSRF-Token"], "staff/tok");
  env.rawRequests.length = 0;
  await env.run('fetchJson(`${API_BASE}/appointments`)');
  assert(!("X-CSRF-Token" in env.rawRequests[0].headers) && !("X-Staff-CSRF-Token" in env.rawRequests[0].headers), "GET sends no CSRF header");
});

// ------------------------------------------------------------------ owner unlock
test("Owner Management asks for the password; a correct one unlocks owner mode", async () => {
  const env = makeEnv();
  await staffUp(env);
  await unlock(env);
  assert.strictEqual(env.calls.pinAsked, 1);
  assert.strictEqual(state(env, "ownerLocked"), false);
  assert.strictEqual(state(env, "ownerAuthenticated"), true);
  assert(!env.document.body.classList.contains("owner-locked"), "owner-only navigation is revealed");
  assert.strictEqual(env.run("notificationLoads"), 1);
  assert(env.calls.fetch.some(([u]) => u.endsWith("/auth/login")), "verified by the backend, not the browser");
});

test("a valid backend session alone never unlocks: a fresh page still asks for the password", async () => {
  const env = makeEnv();
  env.ownerSession = true;
  await staffUp(env);
  assert.strictEqual(state(env, "ownerLocked"), true);
  await unlock(env);
  assert.strictEqual(env.calls.pinAsked, 1);
});

test("a wrong password does not unlock and shows only a generic message", async () => {
  const env = makeEnv();
  await staffUp(env);
  env.nextPassword = "wrong";
  assert.strictEqual(await env.run("requireOwner()"), false);
  assert.strictEqual(state(env, "ownerLocked"), true);
  assert(env.document.body.classList.contains("owner-locked"));
  assert.deepStrictEqual(env.calls.messages.at(-1), ["Oops", "Incorrect password."]);
  assert(!JSON.stringify(env.calls.messages).includes("Invalid owner credentials"));
});

test("concurrent owner-unlock requests share ONE prompt", async () => {
  const env = makeEnv();
  await staffUp(env);
  const [a, b] = await Promise.all([env.run("requireOwner()"), env.run("requireOwner()")]);
  assert(a === true && b === true && env.calls.pinAsked === 1);
});

test("the password is never persisted anywhere", async () => {
  const env = makeEnv();
  env.password = "S3cret-Owner-Pass!";
  await staffUp(env);
  await unlock(env);
  env.run("lockOwner()"); await tick();
  await unlock(env);
  assert.deepStrictEqual(env.writes.storage, []);
  assert.deepStrictEqual(env.writes.cookies, []);
  for (const id of ["pinInput", "calendarWrapper", "cuteNotificationMessage", "navOwner"]) {
    const el = env.getEl(id);
    assert(!JSON.stringify([el.value, el.innerHTML, el.textContent, el.attrs, el.dataset]).includes("S3cret"));
  }
  assert(!JSON.stringify(env.calls.messages).includes("S3cret"));
  assert.strictEqual(env.calls.fetch.filter(([u]) => u.endsWith("/auth/login")).length, 2);
  for (const name of ["ownerLocked", "ownerAuthenticated", "ownerSessionExpiresAt", "staffReady"]) assert(!String(env.run(name)).includes("S3cret"));
});

// ------------------------------------------------------------------ owner inactivity (180 s)
test("owner mode expires after 180 s of owner inactivity: 179 s keeps it, 181 s revokes it", async () => {
  const env = makeEnv();
  await ownerUp(env);
  env.advance(179_000); env.run("ownerIdleCheck(Date.now())");
  assert.strictEqual(state(env, "ownerLocked"), false);
  env.advance(2_000); env.run("ownerIdleCheck(Date.now())");
  assert.strictEqual(state(env, "ownerLocked"), true);
  assert.strictEqual(state(env, "ownerAuthenticated"), false);
});

for (const type of ["pointerdown", "keydown", "click", "touchstart", "wheel"]) {
  test(`${type} inside an owner screen resets the owner timer`, async () => {
    const env = makeEnv();
    await ownerUp(env);
    env.advance(170_000); env.fire(type);
    env.advance(170_000); env.run("ownerIdleCheck(Date.now())");
    assert.strictEqual(state(env, "ownerLocked"), false, "340 s total but only 170 s since the last owner input");
    env.advance(11_000); env.run("ownerIdleCheck(Date.now())");
    assert.strictEqual(state(env, "ownerLocked"), true);
  });
}

test("staff working in the daily-operations screens does NOT keep owner access alive", async () => {
  const env = makeEnv();
  await ownerUp(env);
  env.getEl("technicianView").classList.remove("active-view");
  openView(env, "checkoutView");  // a nail tech checking customers out all day
  for (let i = 0; i < 9; i++) {  // 270 s of constant clicks, typing, scrolling
    env.advance(30_000);
    for (const type of ["pointerdown", "click", "keydown", "touchstart", "wheel"]) env.fire(type, { target: { closest: () => null } });
    env.run("ownerIdleCheck(Date.now())");
    if (i < 5) assert.strictEqual(state(env, "ownerLocked"), false, `${(i + 1) * 30} s`);
  }
  assert.strictEqual(state(env, "ownerLocked"), true, "locked at 180 s despite constant staff activity");
});

test("using an owner-only control (e.g. the notification bell) counts even from a staff screen", async () => {
  const env = makeEnv();
  await ownerUp(env);
  env.getEl("technicianView").classList.remove("active-view");
  openView(env, "calendarView");
  env.advance(170_000); env.fire("click", { target: { closest: (sel) => (sel.includes(".owner-only") ? {} : null) } });
  env.advance(170_000); env.run("ownerIdleCheck(Date.now())");
  assert.strictEqual(state(env, "ownerLocked"), false);
});

test("mouse movement, synthetic events and background polling do NOT reset the owner timer", async () => {
  const env = makeEnv();
  await ownerUp(env);
  openView(env, "calendarView");
  env.getEl("technicianView").classList.remove("active-view");
  env.appointmentsOnServer = [{ id: 1, appointment_time: "2030-01-01T10:00:00", status: "scheduled", customer_name: "A" }];
  for (let i = 0; i < 30; i++) {  // 150 s of polling, programmatic clicks and synthetic input
    env.advance(5_000);
    await env.run("refreshAppointmentsIfChanged()");
    env.fire("click", { isTrusted: false }); env.fire("keydown", { isTrusted: false });
    env.fire("mousemove"); env.getEl("anyButton").click();
    env.run("ownerIdleCheck(Date.now())");
  }
  assert.strictEqual(state(env, "ownerLocked"), false);
  env.advance(31_000); env.run("ownerIdleCheck(Date.now())");
  assert.strictEqual(state(env, "ownerLocked"), true);
});

// ------------------------------------------------------------------ what the timeout does
test("timeout: owner session revoked once (POST /auth/logout), owner data wiped, staff data and screens untouched", async () => {
  const env = makeEnv();
  await ownerUp(env);
  env.run(`appointments = [{id:1, customer_name:'Walk Up'}]; liveCheckins = [{id:1}]; todayTurns = [{id:1}]; techniciansRaw = [{id:1, full_name:'Zed'}];
           technicians = [{id:1}]; inventoryItems = [{id:1}]; ownerNotifications = [{id:1}]; techIncomeDateSummaries = [{id:1}];`);
  OWNER_CONTAINERS.forEach((id) => { env.getEl(id).innerHTML = "<b>Owner secret $1,234</b>"; });
  STAFF_CONTAINERS.forEach((id) => { env.getEl(id).innerHTML = "<b>Walk Up</b>"; });
  env.getEl("appointmentModal").classList.remove("hidden");
  env.calls.fetch.length = 0;
  env.advance(181_000); env.run("ownerIdleCheck(Date.now())"); await tick();
  assert.deepStrictEqual(env.calls.fetch.filter(([u]) => u.includes("/auth/")), [[`${env.run("API_BASE")}/auth/logout`, "POST"]]);
  assert.strictEqual(env.ownerSession, false, "backend owner session revoked");
  OWNER_CONTAINERS.forEach((id) => assert.strictEqual(env.getEl(id).innerHTML, "", id));
  STAFF_CONTAINERS.forEach((id) => assert.strictEqual(env.getEl(id).innerHTML, "<b>Walk Up</b>", id + " must keep working"));
  assert.strictEqual(env.run("JSON.stringify([technicians.length, inventoryItems.length, ownerNotifications.length, techIncomeDateSummaries.length])"), "[0,0,0,0]");
  assert.strictEqual(env.run("JSON.stringify([appointments.length, liveCheckins.length, todayTurns.length, techniciansRaw.length])"), "[1,1,1,1]");
  assert.strictEqual(env.getEl("appointmentModal").classList.contains("hidden"), false, "a staff dialog is not closed by the owner timeout");
  assert(env.run("panelClosed") >= 1, "notifications close");
  assert.strictEqual(env.ownerForms[0].resets, 1, "owner forms cleared");
  assert.strictEqual(env.forms[0].resets, 0, "staff forms (appointment, checkout) are left alone");
  assert(env.document.body.classList.contains("owner-locked"), "owner navigation and views hidden");
  env.advance(60_000); env.run("ownerIdleCheck(Date.now())"); await tick();
  assert.strictEqual(env.logouts, 1, "revoked once");
});

test("an owner screen that is open at timeout is replaced by the staff home screen", async () => {
  const env = makeEnv();
  await ownerUp(env);
  openView(env, "technicianView");
  env.run("lockOwner()");
  assert(!env.getEl("technicianView").classList.contains("active-view"));
  assert(env.getEl("calendarView").classList.contains("active-view"));
});

test("staff keep working after the owner timeout: staff session intact, polling and checkout paths continue", async () => {
  const env = makeEnv();
  await ownerUp(env);
  openView(env, "calendarView");
  env.getEl("technicianView").classList.remove("active-view");
  env.run("lockOwner()"); await tick();
  assert.strictEqual(state(env, "staffReady"), true);
  assert.strictEqual(state(env, "appSessionReady()"), true);
  assert.strictEqual(env.calls.pinAsked, 1, "no further password prompt for staff");
  env.appointmentsOnServer = [{ id: 7, appointment_time: "2030-01-01T10:00:00", status: "scheduled", customer_name: "Phone Booking" }];
  env.ctx.renderCalendar = undefined; vm.runInContext(read("js/calendar.js"), env.ctx);
  env.run("techniciansRaw = [{id:1, full_name:'Zed'}]; selectedDate = new Date(2030, 0, 1);");
  assert.strictEqual(await env.run("refreshAppointmentsIfChanged()"), true, "phone-booked appointment appears");
  assert(env.getEl("calendarWrapper").innerHTML.includes("Phone Booking"));
  const posted = await env.run('fetchJson(`${API_BASE}/checkouts`, { method: "POST", body: "{}" })').then(() => true, () => false);
  assert.strictEqual(posted, true, "staff mutations (checkout) still go through");
  assert.strictEqual(env.staffSessions, 1, "the staff session was never recreated");
});

test("owner access is restored only by entering the password again, and the 180 s timer restarts", async () => {
  const env = makeEnv();
  await ownerUp(env);
  env.run("lockOwner()"); await tick();
  env.nextPassword = "wrong";
  assert.strictEqual(await env.run("requireOwner()"), false);
  assert.strictEqual(state(env, "ownerLocked"), true);
  assert(env.document.body.classList.contains("owner-locked"));
  env.nextPassword = undefined;
  env.ownerSession = true;  // even a still-valid backend session must not skip the password
  const before = env.calls.pinAsked;
  await unlock(env);
  assert.strictEqual(env.calls.pinAsked, before + 1, "asked for the password again");
  assert.strictEqual(state(env, "ownerLocked"), false);
  assert(!env.document.body.classList.contains("owner-locked"));
  openView(env, "technicianView");
  env.advance(179_000); env.run("ownerIdleCheck(Date.now())");
  assert.strictEqual(state(env, "ownerLocked"), false);
  env.advance(2_000); env.run("ownerIdleCheck(Date.now())");
  assert.strictEqual(state(env, "ownerLocked"), true);
});

test("a failed logout request still removes owner data and privilege, retries quietly, never restores", async () => {
  const env = makeEnv();
  await ownerUp(env);
  env.getEl("technicianCards").innerHTML = "<b>owner</b>";
  env.logoutFails = true;
  env.run("lockOwner()"); await tick();
  assert.strictEqual(env.getEl("technicianCards").innerHTML, "");
  assert.strictEqual(state(env, "ownerLocked"), true);
  assert.strictEqual(state(env, "ownerAuthenticated"), false);
  for (let attempt = 2; attempt <= 3; attempt++) {
    env.intervals.filter(([, ms, kind]) => kind === "once" && ms === 5000).at(-1)[0]();
    await tick();
    assert.strictEqual(env.logouts, attempt);
  }
  assert.strictEqual(env.intervals.filter(([, ms, kind]) => kind === "once" && ms === 5000).length, 2, "no fourth attempt");
  assert.strictEqual(state(env, "ownerLocked"), true);
});

test("a pending logout retry never fires after the owner signed in again", async () => {
  const env = makeEnv();
  await ownerUp(env);
  env.logoutFails = true;
  env.run("lockOwner()"); await tick();
  env.logoutFails = false;
  await unlock(env);
  const before = env.logouts;
  env.intervals.filter(([, ms, kind]) => kind === "once" && ms === 5000).forEach(([fn]) => fn());
  await tick();
  assert.strictEqual(env.logouts, before, "must not revoke the new owner session");
});

test("the manual lock button revokes owner access exactly like the timeout", async () => {
  const env = makeEnv();
  await ownerUp(env);
  env.getEl("lockNowBtn").handlers.click({ isTrusted: true });
  await tick();
  assert.strictEqual(state(env, "ownerLocked"), true);
  assert.strictEqual(env.logouts, 1);
});

test("an in-flight owner request that finishes after the lock is cleared again", async () => {
  const env = makeEnv();
  await ownerUp(env);
  env.run("lockOwner()");
  env.getEl("inventoryTableBody").innerHTML = "late owner data";
  env.intervals.find(([, ms, kind]) => kind === "once" && ms === 3000)[0]();
  assert.strictEqual(env.getEl("inventoryTableBody").innerHTML, "");
});

test("owner polling stops with the lock while staff polling does not; the 5s/60s timers are the only ones", () => {
  const main = read("js/main.js");
  assert.strictEqual((main.match(/setInterval\(/g) || []).length, 2);
  assert(/setInterval\(async \(\) => \{\s*if \(!appSessionReady\(\)\) return;[\s\S]*?refreshNotificationCount\(\);\s*await refreshAppointmentsIfChanged\(\);/.test(main));
  assert(!/resetTemporaryUnavailableTechs/.test(main), "the technician availability rollover is server-side now");
  assert(/async function refreshNotificationCount\(\) \{\s*if \(!ownerAuthenticated\) return;/.test(read("js/notifications.js")), "notification polling is owner-only");
});

// ------------------------------------------------------------------ calendar (staff feature)
const appt = (id, time = "2030-01-01T10:00:00", extra = {}) => ({ id, appointment_time: time, status: "scheduled", customer_name: "Cust " + id, service_category: "Gel Manicure", technician_id: 1, ...extra });

async function openCalendar(env) {
  await staffUp(env);  // staff mode only: no owner password involved
  openView(env, "calendarView");
  env.run("techniciansRaw = [{id:1, full_name:'Zed Tech'}]; selectedDate = new Date(2030, 0, 1);");
  vm.runInContext(read("js/calendar.js"), env.ctx);  // the real renderCalendar (the harness stubs it by default)
}

test("calendar auto-refresh works for staff: an external or phone-booked appointment appears, no duplicates", async () => {
  const env = makeEnv();
  await openCalendar(env);
  env.run("calendarHasLoaded = true");  // the calendar has loaded once; this checks the polling after that
  env.appointmentsOnServer = [];
  assert.strictEqual(await env.run("refreshAppointmentsIfChanged()"), false);
  env.appointmentsOnServer = [appt(7)];
  assert.strictEqual(await env.run("refreshAppointmentsIfChanged()"), true);
  for (let i = 0; i < 5; i++) assert.strictEqual(await env.run("refreshAppointmentsIfChanged()"), false);
  assert.strictEqual((env.getEl("calendarWrapper").innerHTML.match(/class="appointment color/g) || []).length, 1);
  const selected = env.run("selectedDate.getTime()");
  env.appointmentsOnServer = [appt(7, "2030-01-01T13:30:00", { status: "cancelled" })];
  await env.run("refreshAppointmentsIfChanged()");
  assert(!env.getEl("calendarWrapper").innerHTML.includes("Cust 7"));
  assert.strictEqual(env.run("selectedDate.getTime()"), selected);
});

test("a failing poll is silent and recovers; nothing is fetched while another screen is open", async () => {
  const env = makeEnv();
  await openCalendar(env);
  env.appointmentsOnServer = [appt(1)];
  await env.run("refreshAppointmentsIfChanged()");
  const shown = env.getEl("calendarWrapper").innerHTML;
  env.appointmentFetchFails = true;
  assert.strictEqual(await env.run("refreshAppointmentsIfChanged()"), false);
  assert.strictEqual(env.getEl("calendarWrapper").innerHTML, shown);
  env.appointmentFetchFails = false;
  env.appointmentsOnServer = [appt(1), appt(2, "2030-01-01T12:00:00")];
  assert.strictEqual(await env.run("refreshAppointmentsIfChanged()"), true);
  env.getEl("calendarView").classList.remove("active-view");
  env.calls.fetch.length = 0;
  assert.strictEqual(await env.run("refreshAppointmentsIfChanged()"), false);
  assert.strictEqual(env.calls.fetch.length, 0);
});

// ------------------------------------------------------------------ current-time line (Phoenix clock)
const phoenix = (day, hh, mm) => {
  const [y, m, d] = day.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d, hh + 7, mm)).toISOString();  // Phoenix = UTC-7, no daylight saving
};
const lines = (env) => (env.getEl("calendarWrapper").innerHTML.match(/class="current-time-line"/g) || []).length;
const topPercent = (env) => Number(/class="current-time-line"[^>]*style="top:([\d.]+)%/.exec(env.getEl("calendarWrapper").innerHTML)[1]);

async function calendarAt(env, iso, selected = new Date(2030, 0, 1)) {
  env.setNow(iso);
  await openCalendar(env);
  env.run("techniciansRaw = [{id:1, full_name:'Zed Tech'}, {id:2, full_name:'Amy Tech'}];");
  env.ctx.__selected = selected;
  env.run("selectedDate = __selected; renderCalendar()");
}

test("the line shows for today, hides for a past day and a future day", async () => {
  const env = makeEnv();
  await calendarAt(env, phoenix("2030-01-01", 12, 37));
  assert.strictEqual(lines(env), 1);
  env.ctx.__selected = new Date(2029, 11, 31); env.run("selectedDate = __selected; renderCalendar()");
  assert.strictEqual(lines(env), 0);
  env.ctx.__selected = new Date(2030, 0, 2); env.run("selectedDate = __selected; renderCalendar()");
  assert.strictEqual(lines(env), 0);
  env.ctx.__selected = new Date(2030, 0, 1); env.run("selectedDate = __selected; renderCalendar()");
  assert.strictEqual(lines(env), 1);
});

for (const [minute, within] of [[0, 0], [15, 25], [30, 50], [37, 61.6667], [45, 75], [59, 98.3333]]) {
  test(`12:${String(minute).padStart(2, "0")} sits ${within.toFixed(1)}% into the 12 o'clock hour`, async () => {
    const env = makeEnv();
    await calendarAt(env, phoenix("2030-01-01", 12, minute));
    const info = env.run("computeCurrentTimeLine(selectedDate, new Date(), 9, 12)");
    assert(Math.abs(info.percentWithinHour - within) < 0.001);
    assert(Math.abs((topPercent(env) / 100) * 1080 - (3 * 90 + (minute / 60) * 90)) < 0.1);
  });
}

test("hidden before 9:00 and from 21:00; the salon clock wins over the browser clock", async () => {
  const env = makeEnv();
  assert.strictEqual(new Date(2030, 0, 1, 12).getTimezoneOffset(), -780, "harness runs in another timezone");
  await calendarAt(env, phoenix("2030-01-01", 8, 59));
  assert.strictEqual(lines(env), 0);
  for (const [hh, mm, expected] of [[9, 0, 1], [20, 59, 1], [21, 0, 0], [22, 0, 0]]) {
    env.setNow(phoenix("2030-01-01", hh, mm)); env.run("renderCalendar()");
    assert.strictEqual(lines(env), expected, `${hh}:${mm}`);
  }
  env.setNow(phoenix("2030-01-01", 23, 59));
  assert.strictEqual(env.run("getSalonToday().getDate()"), 1, "still Jan 1 in Phoenix while it is Jan 2 in Auckland");
});

test("no duplicate lines or timers across renders/refreshes; the owner timeout leaves the line and calendar alone", async () => {
  const env = makeEnv();
  await calendarAt(env, phoenix("2030-01-01", 12, 37));
  await unlock(env);
  const timers = env.intervals.length;
  for (let i = 0; i < 5; i++) env.run("renderCalendar()");
  env.appointmentsOnServer = [appt(1), appt(2, "2030-01-01T11:00:00")];
  await env.run("refreshAppointmentsIfChanged()");
  assert.strictEqual(env.intervals.length, timers, "rendering and refreshing never create a timer");
  env.run("lockOwner()"); await tick();
  assert.strictEqual(lines(env), 1, "calendar and red line survive the owner timeout");
  for (const file of ["js/calendar.js", "js/calendar-refresh.js"]) assert(!/setInterval\(|setTimeout\(/.test(read(file)), file);
  const css = read("styles.css");
  for (const selector of [".current-time-line", ".current-time-dot", ".current-time-label"]) {
    assert(/pointer-events:\s*none;/.test(new RegExp(selector.replace(".", "\\.") + " \\{([^}]*)\\}").exec(css)[1]), selector);
  }
});


// ------------------------------------------------------------------ calendar follows the configured salon hours
const weekHours = (overrides = {}) => Array.from({ length: 7 }, (_, day) => ({ day_of_week: day, is_closed: day === 6, opens_at: day === 6 ? null : "09:00:00", closes_at: day === 6 ? null : "18:00:00", ...(overrides[day] || {}) }));
const setHours = (env, hours) => { env.ctx.__hours = hours; env.run("businessHours = __hours"); };
const timesRows = (env) => /class="times" style="grid-template-rows: repeat\((\d+), 90px\)/.exec(env.getEl("calendarWrapper").innerHTML);
const bands = (env) => [...env.getEl("calendarWrapper").innerHTML.matchAll(/class="closed-band" title="([^"]+)" style="top:([\d.]+)%; height:([\d.]+)%/g)].map((m) => [m[1], Number(m[2]), Number(m[3])]);

test("16:00 typed in the form is sent as 16:00 whatever timezone the browser is in", async () => {
  const env = makeEnv();
  assert.strictEqual(new Date(2026, 9, 12, 12).getTimezoneOffset(), -780, "harness runs in Auckland");
  assert.strictEqual(env.run('displayDateTimeToApi("10-12-2026 16:00")'), "2026-10-12T16:00");
  assert.strictEqual(env.run('displayDateTimeToApi("10-12-2026 00:15")'), "2026-10-12T00:15");
  const main = read("js/main.js");
  const at = main.indexOf("appointmentTimeApiValue");
  assert(!/toISOString|getTimezoneOffset/.test(main.slice(at, at + 1500)), "no UTC conversion in the booking path");
});

test("the calendar's visible hours come from the configured business hours (9:00-18:00 -> 9 rows)", async () => {
  const env = makeEnv();
  await openCalendar(env);
  setHours(env, weekHours());
  env.run("renderCalendar()");
  assert.deepStrictEqual(env.run("JSON.stringify(getCalendarWindow())"), '{"startHour":9,"totalHours":9}');
  assert.strictEqual(timesRows(env)[1], "9");
  const html = env.getEl("calendarWrapper").innerHTML;
  assert.strictEqual((html.match(/<div>\d+:00<br>/g) || []).length, 9);
  assert(html.includes("height:810px"), "9 rows x 90px");
  assert(html.includes('class="times-end">6:00<br><span>pm') && !html.includes(">9:00<br><span>pm"), "the 6 pm closing label follows the last (5 pm) row; nothing beyond it");
});

test("the window spans the earliest opening to the latest closing across the week", async () => {
  const env = makeEnv();
  await openCalendar(env);
  setHours(env, weekHours({ 0: { opens_at: "10:30:00", closes_at: "17:00:00" }, 4: { opens_at: "08:15:00", closes_at: "20:30:00" } }));
  assert.deepStrictEqual(env.run("JSON.stringify(getCalendarWindow())"), '{"startHour":8,"totalHours":13}');
});

test("time that cannot be booked that day is shaded, and a closed day is shaded entirely", async () => {
  const env = makeEnv();
  await openCalendar(env);
  setHours(env, weekHours({ 0: { opens_at: "10:00:00", closes_at: "17:00:00" } }));  // Monday 10-17, rest of week 9-18
  env.ctx.__d = new Date(2026, 9, 12); env.run("selectedDate = __d; renderCalendar()");  // Monday
  const found = bands(env);
  assert.deepStrictEqual(found.map((b) => b[0]), ["Before opening", "After closing"]);
  assert(Math.abs(found[0][1] - 0) < 0.01 && Math.abs(found[0][2] - (60 / 540) * 100) < 0.01, "9:00-10:00");
  assert(Math.abs(found[1][1] - (480 / 540) * 100) < 0.01 && Math.abs(found[1][2] - (60 / 540) * 100) < 0.01, "17:00-18:00");
  env.ctx.__d = new Date(2026, 9, 11); env.run("selectedDate = __d; renderCalendar()");  // Sunday: closed
  assert.deepStrictEqual(JSON.stringify(bands(env)), JSON.stringify([["Salon closed", 0, 100]]));
  env.ctx.__d = new Date(2026, 9, 13); env.run("selectedDate = __d; renderCalendar()");  // Tuesday: full 9-18
  assert.deepStrictEqual(bands(env), []);
  assert(/\.closed-band \{[^}]*pointer-events:\s*none;/.test(read("styles.css")), "shading never blocks clicks");
});

test("the calendar and the booking rules read the same hours: 18:00 closing, Sunday closed", async () => {
  const env = makeEnv();
  await openCalendar(env);
  setHours(env, weekHours());
  env.ctx.__d = new Date(2026, 9, 12); env.run("selectedDate = __d; renderCalendar()");
  assert.strictEqual(env.run("getBookableHours(selectedDate).closesMinutes"), 18 * 60);
  assert.strictEqual(env.run("getBookableHours(new Date(2026, 9, 11)).closed"), true, "Sunday");
  assert.strictEqual(env.getEl("calendarWrapper").innerHTML.includes(">9:00<br><span>pm"), false, "no 9 pm row implying later bookings");
});

test("without loaded hours the calendar keeps the old 9:00-21:00 span and shows no shading", async () => {
  const env = makeEnv();
  await openCalendar(env);
  env.run("businessHours = []; renderCalendar()");
  assert.deepStrictEqual(env.run("JSON.stringify(getCalendarWindow())"), '{"startHour":9,"totalHours":12}');
  assert.strictEqual(timesRows(env)[1], "12");
  assert.deepStrictEqual(bands(env), []);
});

test("the red time line uses the same window as the grid (16:00 in a 9-18 calendar)", async () => {
  const env = makeEnv();
  await calendarAt(env, phoenix("2026-10-12", 16, 0), new Date(2026, 9, 12));
  setHours(env, weekHours());
  env.run("renderCalendar()");
  assert(Math.abs(topPercent(env) - (7 / 9) * 100) < 0.001, "7 of 9 hours down");
  env.setNow(phoenix("2026-10-12", 18, 0)); env.run("renderCalendar()");
  assert.strictEqual(lines(env), 0, "closing time is outside the displayed span");
});

test("business hours are loaded through the staff-safe public endpoint when the dashboard loads", () => {
  assert(/\/business-hours/.test(read("js/appointments.js")));
  assert(/attempt\(loadBusinessHours\)/.test(read("js/dashboard-load.js")));
  assert(!/\/business-hours/.test(read("js/ownerlock.js")), "no owner session needed");
});


// ------------------------------------------------------------------ calendar keeps its last good data
const hours9to18 = Array.from({ length: 7 }, (_, day) => ({ day_of_week: day, is_closed: day === 6, opens_at: day === 6 ? null : "09:00:00", closes_at: day === 6 ? null : "18:00:00" }));
const tech = (id, name) => ({ id, full_name: name, is_active: true });
const cardCount = (env) => (env.getEl("calendarWrapper").innerHTML.match(/class="appointment color/g) || []).length;
const showsError = (env) => /Could not load|FastAPI|session needs/i.test(env.getEl("calendarWrapper").innerHTML);
const apptRequests = (env) => env.calls.fetch.filter(([u]) => u.endsWith("/appointments")).length;

async function loadedCalendar(env, { at = phoenix("2026-10-12", 16, 0), options } = {}) {
  env.setNow(at);
  env.techniciansOnServer = [tech(1, "Zed Tech"), tech(2, "Amy Tech")];
  env.hoursOnServer = hours9to18;
  env.appointmentsOnServer = [appt(1, "2026-10-12T10:00:00"), appt(2, "2026-10-12T11:00:00", { technician_id: 2 })];
  await staffUp(env);
  vm.runInContext(read("js/calendar.js"), env.ctx);  // real renderCalendar
  openView(env, "calendarView");
  env.ctx.__d = new Date(2026, 9, 12); env.run("selectedDate = __d");
  await env.run("loadAll()");
}

test("the first load shows a neutral loading state, then the calendar", async () => {
  const env = makeEnv();
  env.setNow(phoenix("2026-10-12", 16, 0));
  env.techniciansOnServer = [tech(1, "Zed Tech")]; env.hoursOnServer = hours9to18; env.appointmentsOnServer = [appt(1, "2026-10-12T10:00:00")];
  await staffUp(env);
  vm.runInContext(read("js/calendar.js"), env.ctx);
  env.ctx.__d = new Date(2026, 9, 12); env.run("selectedDate = __d");
  env.gate = new Promise((resolve) => { env.release = resolve; });
  const loading = env.run("loadAll()");
  await tick();
  assert(/Loading calendar/.test(env.getEl("calendarWrapper").innerHTML) && !showsError(env), "neutral, not an error");
  env.release(); await loading;
  assert.strictEqual(cardCount(env), 1);
  assert.strictEqual(state(env, "calendarHasLoaded"), true);
});

test("navigating away and back shows the last good calendar immediately, with no error flash", async () => {
  const env = makeEnv();
  await loadedCalendar(env);
  const before = env.getEl("calendarWrapper").innerHTML;
  const selected = env.run("selectedDate.getTime()");
  env.getEl("calendarView").classList.remove("active-view"); openView(env, "customerListView");  // away
  env.gate = new Promise((resolve) => { env.release = resolve; });  // the refresh is slow
  env.calls.fetch.length = 0;
  env.run("returnToCalendar()");  // back: synchronous part only
  assert(env.getEl("calendarView").classList.contains("active-view"), "calendar is shown at once");
  assert(!env.getEl("customerListView").classList.contains("active-view"));
  const now = env.getEl("calendarWrapper").innerHTML;
  assert.strictEqual(cardCount(env), 2, "appointments visible immediately");
  assert(now.includes("Zed Tech") && now.includes("Amy Tech"), "technicians visible immediately");
  assert(/closed-band[^>]*title="After closing"|height:810px/.test(now), "business-hour window still applied");
  assert(now.includes('class="current-time-line"'), "current-time line still drawn");
  assert(!showsError(env) && !/Loading calendar/.test(now), "no error and no loading flash");
  assert.strictEqual(env.run("selectedDate.getTime()"), selected);
  await tick();
  assert.strictEqual(apptRequests(env), 1, "the background refresh has started (one request)");
  assert(!showsError(env) && cardCount(env) === 2, "a delayed refresh does not blank anything");
  env.release(); await env.run("backgroundRefreshInFlight");
  assert.strictEqual(cardCount(env), 2, "no duplicate cards after the refresh");
  assert(before.length > 0 && !showsError(env));
});

test("fresh data from the background refresh replaces the old data (a phone booking appears)", async () => {
  const env = makeEnv();
  await loadedCalendar(env);
  env.appointmentsOnServer = [...env.appointmentsOnServer, appt(3, "2026-10-12T14:00:00", { customer_name: "Phone Booking" })];
  env.run("returnToCalendar()");
  await env.run("backgroundRefreshInFlight");
  assert.strictEqual(cardCount(env), 3);
  assert(env.getEl("calendarWrapper").innerHTML.includes("Phone Booking"));
});

test("a failed background refresh keeps the last good calendar; the next refresh recovers", async () => {
  const env = makeEnv();
  await loadedCalendar(env);
  for (const message of [null, "Internal Server Error", "Staff session required"]) {
    env.failures = { "/appointments": -1, "/technicians": -1 };
    env.failureMessage = message;
    env.run("returnToCalendar()");
    await env.run("backgroundRefreshInFlight");
    assert.strictEqual(cardCount(env), 2, `still shows the last good appointments (${message})`);
    assert(env.getEl("calendarWrapper").innerHTML.includes("Zed Tech"), "still shows technicians");
    assert(!showsError(env), `no error text (${message})`);
    assert.strictEqual(state(env, "calendarHasLoaded"), true);
  }
  env.failures = {}; env.failureMessage = null;
  env.appointmentsOnServer = [appt(1, "2026-10-12T10:00:00"), appt(2, "2026-10-12T11:00:00", { technician_id: 2 }), appt(9, "2026-10-12T13:00:00")];
  env.run("returnToCalendar()");
  await env.run("backgroundRefreshInFlight");
  assert.strictEqual(cardCount(env), 3, "recovered on the next refresh");
});

test("the 5-second poll keeps working after a failed refresh and never blanks the calendar", async () => {
  const env = makeEnv();
  await loadedCalendar(env);
  env.failures = { "/appointments": -1 };
  assert.strictEqual(await env.run("refreshAppointmentsIfChanged()"), false);
  assert.strictEqual(cardCount(env), 2); assert(!showsError(env));
  env.failures = {};
  env.appointmentsOnServer = [appt(5, "2026-10-12T12:00:00")];
  assert.strictEqual(await env.run("refreshAppointmentsIfChanged()"), true);
  assert.strictEqual(cardCount(env), 1);
});

test("repeated returns while a refresh is running share ONE refresh; no timers are created", async () => {
  const env = makeEnv();
  await loadedCalendar(env);
  const timers = env.intervals.length;
  env.gate = new Promise((resolve) => { env.release = resolve; });
  env.calls.fetch.length = 0;
  for (let i = 0; i < 4; i++) env.run("returnToCalendar()");
  await tick();
  assert.strictEqual(apptRequests(env), 1, "one in-flight refresh, not four");
  env.release(); await env.run("backgroundRefreshInFlight");
  assert.strictEqual(cardCount(env), 2);
  assert.strictEqual(env.intervals.length, timers, "no new timers");
  assert(!/setInterval\(|setTimeout\(/.test(read("js/dashboard-load.js")));
  assert.strictEqual((read("js/main.js").match(/setInterval\(/g) || []).length, 2);
});

test("a true first-load failure shows an accurate message (never the old FastAPI text) and can recover", async () => {
  const env = makeEnv();
  env.techniciansOnServer = [tech(1, "Zed Tech")]; env.hoursOnServer = hours9to18; env.appointmentsOnServer = [];
  await staffUp(env);
  vm.runInContext(read("js/calendar.js"), env.ctx);
  env.ctx.__d = new Date(2026, 9, 12); env.run("selectedDate = __d");
  env.failures = { "/appointments": -1 };
  await env.run("loadAll()");
  assert.strictEqual(state(env, "calendarHasLoaded"), false);
  assert(/Could not load calendar data\. The server could not be reached; please try again\./.test(env.getEl("calendarWrapper").innerHTML));
  assert(env.getEl("calendarWrapper").innerHTML.includes("calendarRetryBtn") && !/FastAPI/.test(env.getEl("calendarWrapper").innerHTML));
  env.failureMessage = "Internal Server Error"; await env.run("loadAll()");
  assert(/Could not load calendar data\. Please try again\./.test(env.getEl("calendarWrapper").innerHTML));
  env.failureMessage = "Staff session required"; await env.run("loadAll()");
  assert(/session needs to be renewed/.test(env.getEl("calendarWrapper").innerHTML));
  env.failures = {}; env.failureMessage = null;  // the poll recovers an empty calendar too (nothing changed vs the empty list)
  openView(env, "calendarView");
  assert.strictEqual(await env.run("refreshAppointmentsIfChanged()"), true);
  assert.strictEqual(state(env, "calendarHasLoaded"), true);
  assert(!showsError(env) && env.getEl("calendarWrapper").innerHTML.includes('class="calendar-board"'));
});

test("a lapsed staff session is renewed invisibly (one new session for concurrent requests), with no error shown", async () => {
  const env = makeEnv({ realFetchJson: true });
  env.techniciansOnServer = [tech(1, "Zed Tech")]; env.hoursOnServer = hours9to18; env.appointmentsOnServer = [appt(1, "2026-10-12T10:00:00")];
  env.setNow(phoenix("2026-10-12", 16, 0));
  await staffUp(env);
  vm.runInContext(read("js/calendar.js"), env.ctx);
  openView(env, "calendarView");
  env.ctx.__d = new Date(2026, 9, 12); env.run("selectedDate = __d");
  env.expireStaff = 2;  // the first two requests both hit the expired session
  const [a, b] = await Promise.all([env.run("loadAppointments()").then(() => "ok"), env.run("loadTechniciansRaw()").then(() => "ok")]);
  assert.deepStrictEqual([a, b], ["ok", "ok"]);
  assert.strictEqual(env.staffSessions, 2, "the initial session plus exactly ONE renewal");
  env.expireStaff = 1;
  await env.run("loadAll()");
  assert(!showsError(env) && cardCount(env) === 1, "a temporary 401 that retries successfully stays invisible");
  assert.strictEqual(env.staffSessions, 3);
});

test("owner sign-out wipes only owner data: the loaded calendar, technicians, hours and date survive", async () => {
  const env = makeEnv();
  await loadedCalendar(env);
  await unlock(env);
  env.getEl("inventoryTableBody").innerHTML = "owner data";
  const selected = env.run("selectedDate.getTime()");
  env.run("lockOwner()"); await tick();
  assert.strictEqual(env.getEl("inventoryTableBody").innerHTML, "");
  assert.strictEqual(cardCount(env), 2);
  assert.strictEqual(state(env, "calendarHasLoaded"), true);
  assert.strictEqual(env.run("techniciansRaw.length + businessHours.length"), 2 + 7);
  assert.strictEqual(env.run("selectedDate.getTime()"), selected);
  env.run("returnToCalendar()"); await env.run("backgroundRefreshInFlight");
  assert.strictEqual(cardCount(env), 2); assert(!showsError(env));
});

test("the old catch-all message is gone and the back button no longer waits for a full reload", () => {
  for (const file of fs.readdirSync(path.join(root, "js"))) assert(!/Make sure FastAPI is running/.test(read("js/" + file)), file);
  const main = read("js/main.js");
  assert(/btn\.addEventListener\("click", returnToCalendar\)/.test(main) && !/async function loadAll/.test(main));
  assert(/<script src="js\/dashboard-load\.js"/.test(read("index.html")));
});


// ------------------------------------------------------------------ booking hours schedule appointments; they never hide customers
test("changing Monday from 9-6 to 10-7 moves the calendar window and the shading with no code change", async () => {
  const env = makeEnv();
  await openCalendar(env);
  env.ctx.__d = new Date(2026, 9, 12); env.run("selectedDate = __d");  // a Monday
  setHours(env, weekHours());
  env.run("renderCalendar()");
  assert.deepStrictEqual(env.run("JSON.stringify(getCalendarWindow())"), '{"startHour":9,"totalHours":9}');
  setHours(env, weekHours({ 0: { opens_at: "10:00:00", closes_at: "19:00:00" } }));  // the owner reconfigures Monday
  env.run("renderCalendar()");
  assert.deepStrictEqual(env.run("JSON.stringify(getCalendarWindow())"), '{"startHour":9,"totalHours":10}');  // Tue-Sat still open 9-18
  assert.deepStrictEqual(bands(env).map((b) => b[0]), ["Before opening"], "Monday opens at 10, closes at the edge of the window");
  setHours(env, weekHours({ 0: { opens_at: "10:00:00", closes_at: "19:00:00" }, 1: { opens_at: "10:00:00", closes_at: "19:00:00" }, 2: { opens_at: "10:00:00", closes_at: "19:00:00" },
    3: { opens_at: "10:00:00", closes_at: "19:00:00" }, 4: { opens_at: "10:00:00", closes_at: "19:00:00" }, 5: { opens_at: "10:00:00", closes_at: "19:00:00" } }));
  env.run("renderCalendar()");
  assert.deepStrictEqual(env.run("JSON.stringify(getCalendarWindow())"), '{"startHour":10,"totalHours":9}');
  assert.deepStrictEqual(bands(env), [], "the whole 10-19 span is bookable");
});

test("after closing, customers still being served stay on the calendar at their TRUE time (nothing is hidden or pinned to the edge)", async () => {
  const env = makeEnv();
  await openCalendar(env);
  env.setNow(phoenix("2026-10-12", 19, 30));  // 7:30 pm in Phoenix; the browser is in Auckland
  setHours(env, weekHours());  // Monday 9:00-18:00
  env.ctx.__d = new Date(2026, 9, 12); env.run("selectedDate = __d");
  env.run(`appointments = [
    { id: 1, appointment_time: "2026-10-12T10:00:00", status: "scheduled", customer_name: "Morning", service_category: "Gel", technician_id: 1 },
    { id: 2, appointment_time: "2026-10-12T18:30:00", status: "in_service", customer_name: "Ran Late", service_category: "Acrylic", technician_id: 1 }];
    todayTurns = [{ id: 9, status: "in_service", technician_id: 2, customer_name: "Late Walk In", service_name: "Gel", created_at: "2026-10-12T19:10:00" }];`);
  env.run("techniciansRaw = [{id:1, full_name:'Zed'}, {id:2, full_name:'Amy'}]; renderCalendar()");
  const html = env.getEl("calendarWrapper").innerHTML;
  assert(html.includes('data-id="2"') && html.includes("Ran Late"), "the appointment that ran past closing is shown");
  assert(html.includes("Late Walk In") && html.includes("live-turn-in-service"), "the active turn after closing is shown (salon date, not browser date)");
  assert(html.includes("top:855px"), "18:30 sits at its real position: (18:30 - 9:00) x 90px/hr = 855px, not clamped");
  assert.deepStrictEqual(env.run("JSON.stringify(extendWindowForItems(getCalendarWindow(), appointments, todayTurns))"), '{"startHour":9,"totalHours":12}');
  assert.deepStrictEqual(bands(env).map((b) => b[0]), ["After closing"], "the extra hours are shaded as not bookable, not removed");
  assert.strictEqual(lines(env), 1, "the current-time line shows (19:30 is inside the extended span)");
  assert(Math.abs(topPercent(env) - ((19 * 60 + 30 - 9 * 60) / 720) * 100) < 0.001);
});

test("a day with nothing outside booking hours keeps exactly the booking-hours window", async () => {
  const env = makeEnv();
  await openCalendar(env);
  setHours(env, weekHours());
  env.ctx.__d = new Date(2026, 9, 12); env.run("selectedDate = __d");
  env.run(`appointments = [{ id: 1, appointment_time: "2026-10-12T17:00:00", status: "scheduled", customer_name: "Last Slot", technician_id: 1 }]; techniciansRaw = [{id:1, full_name:'Zed'}]; renderCalendar()`);
  assert.strictEqual(timesRows(env)[1], "9");  // a 17:00 appointment still fits in the 9-18 span: no growth
  env.run(`appointments = [{ id: 1, appointment_time: "2026-10-12T07:15:00", status: "scheduled", customer_name: "Early", technician_id: 1 }]; renderCalendar()`);
  assert.strictEqual(timesRows(env)[1], "11", "an early customer extends the top (7:00-18:00) instead of being hidden");
  assert(env.getEl("calendarWrapper").innerHTML.includes("Early"));
});

test("the weekly hours are read ONLY by the calendar's display code: nothing operational is gated on them", () => {
  const users = fs.readdirSync(path.join(root, "js")).filter((file) => /businessHours|getBookableHours|getCalendarWindow/.test(read("js/" + file)));
  assert.deepStrictEqual(users.sort(), ["appointments.js", "calendar.js", "ownerlock.js", "salon-settings.js", "state.js"], "the loader, the calendar renderer, the state variable, the settings page that EDITS them and one container id the lock clears");
  for (const file of ["queue.js", "checkout.js", "ui.js", "main.js", "utils.js", "notifications.js"]) {
    assert(!/businessHours|closes_at|opens_at|getBookableHours/.test(read("js/" + file)), file + " must not depend on booking hours");
  }
  assert(!/is_closed|closing|after hours/i.test(read("js/checkout.js") + read("js/queue.js")), "checkout and the queue never refuse service after closing");
});


// ------------------------------------------------------------------ Salon Settings page (owner only)
const settingsFixtures = () => ({
  profile: { salon_name: "Nail Salon", business_phone: "+12245492806", business_phone_display: "(224) 549-2806", timezone: "America/Phoenix", timezone_editable: false, timezone_note: "The time zone is set when the salon is installed." },
  ai: { configured: true, missing: [], voice_enabled: true, real_calls_allowed: true, ready_for_calls: true, twilio_number: "+16025559999", twilio_number_display: "(602) 555-9999", public_salon_phone_display: "(224) 549-2806", note: "The public salon phone is NOT the Twilio number." },
  security: { has_recovery_phone: true, recovery_phone_masked: "(***) ***-0142", sms_recovery_available: false, sms_recovery_note: "Text-message recovery is not available yet." },
});

function settingsEnv() {
  const env = makeEnv();
  const fixtures = settingsFixtures();
  env.fixtures = fixtures;
  env.bodies = [];
  const base = env.ctx.fetchJson;
  env.ctx.fetchJson = async (url, options = {}) => {
    env.bodies.push({ url, method: options.method || "GET", body: options.body ? JSON.parse(options.body) : null });
    if (url.endsWith("/settings/salon")) {
      if (options.method === "PUT") { const body = JSON.parse(options.body); env.fixtures.profile = { ...env.fixtures.profile, salon_name: body.salon_name, business_phone_display: body.business_phone || null }; }
      return env.fixtures.profile;
    }
    if (url.endsWith("/salon")) return { salon_name: env.fixtures.profile.salon_name };
    if (url.endsWith("/settings/ai-receptionist")) return env.fixtures.ai;
    if (url.endsWith("/settings/security")) return env.fixtures.security;
    if (url.endsWith("/settings/security/recovery-phone")) { if (env.settingsFail) throw new Error("Current password is incorrect"); return env.fixtures.security; }
    if (url.endsWith("/settings/security/password")) { if (env.settingsFail) throw new Error("Current password is incorrect"); return { changed: true }; }
    if (url.endsWith("/business-hours") && options.method === "PUT") { if (env.settingsFail) throw new Error("Closing time must be after opening time"); return JSON.parse(options.body).days.map((d) => ({ ...d, opens_at: d.opens_at && d.opens_at + ":00", closes_at: d.closes_at && d.closes_at + ":00" })); }
    if (url.endsWith("/business-hours")) return weekHours();
    return base(url, options);
  };
  return env;
}

const mkInput = (extra = {}) => ({ checked: false, value: "", disabled: false, classList: { contains: () => false }, ...extra });
function hoursRows(env, rows) {  // the table rows the form reads (the fake DOM has no real table)
  env.getEl("businessHoursBody").querySelectorAll = () => rows.map((r, index) => ({
    dataset: { day: String(index) },
    querySelector: (sel) => ({ ".hours-open": mkInput({ checked: r.open }), ".hours-opens": mkInput({ value: r.opens || "" }), ".hours-closes": mkInput({ value: r.closes || "" }) }[sel]),
  }));
}
const weekRows = (overrides = {}) => Array.from({ length: 7 }, (_, d) => ({ open: d !== 6, opens: d === 6 ? "" : "09:00", closes: d === 6 ? "" : "18:00", ...(overrides[d] || {}) }));
const submit = (env, id) => env.getEl(id).handlers.submit({ preventDefault() {} });

test("Salon Settings sits in the owner-only navigation and loads all four areas from the backend", async () => {
  const html = read("index.html");
  const group = /<div id="ownerNavGroup"[^>]*>([\s\S]*?)<\/div>/.exec(html)[1];
  assert(/id="navSettings"[^>]*>Salon Settings</.test(group));
  assert(!/id="navSettings"/.test(html.slice(0, html.indexOf('id="navOwner"'))), "not in the staff part of the sidebar");
  assert(/<section id="settingsView" class="view owner-view">/.test(html) && /salon-settings\.js/.test(html));
  assert(/\/settings\/salon/.test(read("js/salon-settings.js")) && /requireOwner/.exec(/navSettings\?\.addEventListener\("click", async \(\) => \{([\s\S]*?)\n\}\);/.exec(read("js/main.js"))[1]));
  const env = settingsEnv();
  await ownerUp(env);
  await env.run("renderSettingsPage()");
  assert.strictEqual(env.getEl("settings_salon_name").value, "Nail Salon");
  assert.strictEqual(env.getEl("settings_salon_phone").value, "(224) 549-2806");
  assert.strictEqual(env.getEl("settings_timezone").value, "America/Phoenix");
  assert(env.getEl("settingsTimezoneNote").textContent.includes("set when the salon is installed"));
  const rows = env.getEl("businessHoursBody").innerHTML;
  for (const day of ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]) assert(rows.includes(`<strong>${day}</strong>`), day);
  assert(/data-day="6"[\s\S]*?disabled/.test(rows) && /data-day="0"[\s\S]*?value="09:00"/.test(rows), "Sunday closed (times disabled), Monday 09:00");
  const status = env.getEl("aiStatusList").innerHTML;
  assert(/Configured/.test(status) && status.includes("(602) 555-9999") && status.includes("Enabled") && status.includes("(224) 549-2806"));
  assert(env.getEl("settings_timezone").value && !env.getEl("settings_timezone").handlers.input, "time zone is read-only text");
  assert(/readonly/.test(html.slice(html.indexOf('id="settings_timezone"') - 10, html.indexOf('id="settings_timezone"') + 80)));
});

test("saving new booking hours calls the owner endpoint with the whole week and the calendar follows at once", async () => {
  const env = settingsEnv();
  await ownerUp(env);
  await openCalendar(env);
  env.ctx.__d = new Date(2026, 9, 12); env.run("selectedDate = __d; calendarHasLoaded = true; businessHours = []");  // a Monday
  hoursRows(env, weekRows({ 0: { opens: "10:00", closes: "19:00" }, 6: { open: false } }));
  await submit(env, "businessHoursForm");
  const put = env.bodies.find((b) => b.url.endsWith("/business-hours") && b.method === "PUT");
  assert.strictEqual(put.body.days.length, 7);
  assert.deepStrictEqual(put.body.days[0], { day_of_week: 0, is_closed: false, opens_at: "10:00", closes_at: "19:00" });
  assert.deepStrictEqual(put.body.days[6], { day_of_week: 6, is_closed: true, opens_at: null, closes_at: null });
  assert.strictEqual(env.run("getBookableHours(new Date(2026, 9, 12)).opensMinutes"), 10 * 60, "the calendar's hours were replaced from the save response");
  assert.strictEqual(env.run("getBookableHours(new Date(2026, 9, 12)).closesMinutes"), 19 * 60);
  const grid = env.getEl("calendarWrapper").innerHTML;
  assert(grid.includes('title="Before opening"') && !grid.includes("After closing"), "the open calendar was redrawn at once: Monday now opens at 10:00 and closes at the end of the span");
  assert.deepStrictEqual(env.run("JSON.stringify(getCalendarWindow())"), '{"startHour":9,"totalHours":10}');
  assert(env.calls.messages.at(-1)[1].includes("Booking hours saved"));
});

test("invalid hours are caught before any request and a rejected save shows the server's reason", async () => {
  const env = settingsEnv();
  await ownerUp(env);
  hoursRows(env, weekRows({ 1: { opens: "18:00", closes: "09:00" } }));
  env.bodies.length = 0;
  await submit(env, "businessHoursForm");
  assert(env.getEl("businessHoursError").textContent.includes("Tuesday: closing time must be after opening time"));
  assert.strictEqual(env.bodies.length, 0, "nothing was sent");
  hoursRows(env, weekRows({ 2: { opens: "", closes: "" } }));
  await submit(env, "businessHoursForm");
  assert(env.getEl("businessHoursError").textContent.includes("Wednesday: enter both"));
  hoursRows(env, weekRows());
  env.settingsFail = true;
  const before = env.run("JSON.stringify(businessHours)");
  await submit(env, "businessHoursForm");
  assert(env.getEl("businessHoursError").textContent.includes("Closing time must be after opening time"));
  assert.strictEqual(env.run("JSON.stringify(businessHours)"), before, "the calendar's hours are not changed by a failed save");
});

test("saving the salon name updates the sidebar and tab title; the public phone note says it does not touch Twilio", async () => {
  const env = settingsEnv();
  await ownerUp(env);
  await env.run("renderSettingsPage()");
  env.getEl("settings_salon_name").value = "  Lotus Nails ";
  env.getEl("settings_salon_phone").value = "(224) 549-2806";
  await submit(env, "salonProfileForm");
  const put = env.bodies.find((b) => b.url.endsWith("/settings/salon") && b.method === "PUT");
  assert.deepStrictEqual(put.body, { salon_name: "Lotus Nails", business_phone: "(224) 549-2806" });
  assert.strictEqual(env.getEl("salonNameHeading").textContent, "Lotus Nails");
  assert.strictEqual(env.document.title, "Lotus Nails Calendar");
  assert(!env.bodies.some((b) => /twilio/i.test(b.url)), "no Twilio request exists");
  assert(/NOT the Twilio number/.test(env.getEl("aiStatusNote").textContent));
  env.getEl("settings_salon_name").value = "   ";
  env.bodies.length = 0;
  await submit(env, "salonProfileForm");
  assert(env.getEl("salonProfileError").textContent.includes("required") && env.bodies.length === 0);
});

test("every dashboard load takes the salon name from the public endpoint (staff see it too)", async () => {
  const env = settingsEnv();
  await staffUp(env);
  env.fixtures.profile.salon_name = "Lotus Nails";
  await env.run("loadSalonName()");
  assert.strictEqual(env.getEl("salonNameHeading").textContent, "Lotus Nails");
  assert(/attempt\(loadSalonName\)/.test(read("js/dashboard-load.js")));
});

test("Salon Settings has no Recovery Phone section and no Forgot Password / SMS recovery UI (backend support is kept for later)", () => {
  const html = read("index.html");
  const page = html.slice(html.indexOf('<section id="settingsView"'), html.indexOf("<!-- ============ CHECKOUT"));
  for (const gone of ["recoveryPhoneForm", "settings_recovery_phone", "settings_recovery_password", "recoveryPhoneStatus", "recoveryPhoneError", "forgotPasswordNote", "Recovery Phone", "Forgot Password", "SMS", "text message", "Text-message"]) {
    assert(!page.includes(gone), gone + " must not be on the page");
  }
  assert(!/recovery/i.test(page), "nothing on the settings page mentions a recovery phone");
  const help = /id="ownerPasswordHelp">([^<]*)</.exec(page)[1];
  assert.strictEqual(help, "If the owner password is forgotten, it can be reset locally on the salon computer by an administrator.");
  assert(!/reset_owner_password|\.py\b|python|command/i.test(page), "no script names or commands shown to the salon");
  assert(page.includes('id="passwordForm"') && page.includes("Change Password"), "changing the password is still there");
  const code = read("js/salon-settings.js");
  assert(!/recovery|forgot/i.test(code), "the page code no longer touches the recovery phone");
  assert(!code.includes("/settings/security`"), "the page no longer even loads the security status");
  for (const file of fs.readdirSync(path.join(root, "js"))) assert(!/recovery-phone|recoveryPhone/i.test(read("js/" + file)), file);
  assert(!/recoveryPhone/i.test(read("styles.css")));
});

test("the Owner Login prompt says 'owner password' (no PIN) and its field is labelled Owner password", () => {
  const html = read("index.html");
  const at = html.indexOf('<div id="pinModal"');
  const modal = html.slice(at, at + 900);
  assert(modal.includes("<h4>Owner Login</h4>"));
  assert(modal.includes("<p>Enter the owner password to continue.</p>"));
  assert(/id="pinInput"[^>]*placeholder="Owner password"/.test(modal));
  assert(!/password or PIN|owner PIN/i.test(html), "no 'password or PIN' anywhere");
  const allJs = fs.readdirSync(path.join(root, "js")).map((f) => read("js/" + f)).join("\n");
  assert(!/\bPIN\b/.test(html) && !/\bPIN\b/.test(allJs), "no PIN wording left in the frontend");
  assert(/type="password"/.test(modal) && /autocomplete="current-password"/.test(modal), "still a hidden password field");
});

test("change password: client checks, success signs the owner out locally (staff untouched), failure keeps owner mode", async () => {
  const env = settingsEnv();
  await ownerUp(env);
  const fill = (current, next, confirm) => { env.getEl("settings_current_password").value = current; env.getEl("settings_new_password").value = next; env.getEl("settings_confirm_password").value = confirm; };
  env.bodies.length = 0;
  fill("", "", ""); await submit(env, "passwordForm");
  assert(env.getEl("passwordError").textContent.includes("all three"));
  fill("old-pass-1234", "new-pass-5678", "different-5678"); await submit(env, "passwordForm");
  assert(env.getEl("passwordError").textContent.includes("do not match") && env.bodies.length === 0);
  env.settingsFail = true;
  fill("wrong-old-pass", "new-pass-5678", "new-pass-5678"); await submit(env, "passwordForm");
  assert(env.getEl("passwordError").textContent.includes("incorrect"));
  for (const id of ["settings_current_password", "settings_new_password", "settings_confirm_password"]) assert.strictEqual(env.getEl(id).value, "", id + " cleared");
  assert.strictEqual(state(env, "ownerLocked"), false, "a failed attempt keeps owner mode");
  env.settingsFail = false;
  fill("old-pass-1234", "new-pass-5678", "new-pass-5678");
  env.calls.fetch.length = 0;
  await submit(env, "passwordForm");
  await tick();
  const post = env.bodies.filter((b) => b.url.endsWith("/settings/security/password") && b.method === "POST").at(-1);
  assert.deepStrictEqual(post.body, { current_password: "old-pass-1234", new_password: "new-pass-5678", confirm_password: "new-pass-5678" });
  for (const id of ["settings_current_password", "settings_new_password", "settings_confirm_password"]) assert.strictEqual(env.getEl(id).value, "", id + " cleared");
  assert.strictEqual(state(env, "ownerLocked"), true, "back in staff mode");
  assert.strictEqual(state(env, "staffReady"), true);
  assert(!env.calls.fetch.some(([u]) => u.endsWith("/auth/logout")), "the server already signed the owner out: no second logout request");
  assert(env.calls.messages.at(-1)[1].includes("sign in again"));
  assert.deepStrictEqual(env.writes.storage, []);
});

test("the owner timeout and manual lock clear the settings page (including typed passwords) and leave the settings screen", async () => {
  const env = settingsEnv();
  await ownerUp(env);
  await env.run("renderSettingsPage()");
  env.getEl("technicianView").classList.remove("active-view"); openView(env, "settingsView");
  env.getEl("businessHoursBody").innerHTML = "<tr>hours</tr>"; env.getEl("aiStatusList").innerHTML = "<dt>x</dt>";
  env.advance(170_000); env.fire("click");  // working inside the settings screen keeps owner mode alive
  env.advance(170_000); env.run("ownerIdleCheck(Date.now())");
  assert.strictEqual(state(env, "ownerLocked"), false);
  env.advance(11_000); env.run("ownerIdleCheck(Date.now())"); await tick();
  assert.strictEqual(state(env, "ownerLocked"), true);
  for (const id of ["businessHoursBody", "aiStatusList"]) assert.strictEqual(env.getEl(id).innerHTML, "", id);
  assert.strictEqual(env.ownerForms[0].resets, 1, "forms (typed passwords) are reset");
  assert(env.getEl("calendarView").classList.contains("active-view") && !env.getEl("settingsView").classList.contains("active-view"));
  assert.strictEqual(env.logouts, 1);
});

test("nothing secret is in the settings page code and the server rollover replaces the browser-side one", () => {
  const code = read("js/salon-settings.js") + read("index.html");
  for (const secret of ["TWILIO_AUTH_TOKEN", "TWILIO_ACCOUNT_SID", "OPENAI_API_KEY", "CHECKIN_INTERNAL_SERVICE_TOKEN", "sk-proj"]) assert(!code.includes(secret), secret);
  for (const file of fs.readdirSync(path.join(root, "js"))) assert(!/resetTemporaryUnavailableTechs|TemporaryUnavailableMap|ownerTechUnavailableToday/.test(read("js/" + file)), file);
});


// ------------------------------------------------------------------ UI polish: settings table, lock control, closing boundary, phone
const cssRule = (selector) => {
  const css = read("styles.css");
  const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const matches = [...css.matchAll(new RegExp(escaped + " \\{([^}]*)\\}", "g"))];
  assert(matches.length, "no CSS rule for " + selector);
  return matches.map((m) => m[1]).join(" ");
};
const px = (rule, property) => Number(new RegExp("(?:^|[\\s;])" + property + ":\\s*(-?[\\d.]+)px").exec(rule)[1]);
const hourLabels = (env) => [...env.getEl("calendarWrapper").innerHTML.matchAll(/<div(?: class="times-end")?>(\d+):00<br><span>(am|pm)<\/span>/g)].map((m) => m[1] + m[2]);
const uniformHours = (opens, closes) => weekHours(Object.fromEntries([0, 1, 2, 3, 4, 5].map((d) => [d, { opens_at: opens, closes_at: closes }])));

test("booking-hours checkbox: compact, centred, with a comfortable click target (page-wide input rules are overridden)", () => {
  const box = cssRule('.settings-hours-table input[type="checkbox"]');
  assert(px(box, "width") <= 20 && px(box, "height") <= 20 && px(box, "width") >= 16, "slightly smaller than the 100% x 46px default, still tappable");
  assert(/min-height:\s*0/.test(box) && /margin:\s*0/.test(box) && /padding:\s*0/.test(box), "the global min-height/padding no longer apply");
  const label = cssRule(".hours-open-label");
  assert(/display:\s*inline-flex/.test(label) && /align-items:\s*center/.test(label) && /margin:\s*0/.test(label), "checkbox and Open/Closed text centred on one line");
  assert(px(label, "min-height") >= 40, "the whole label is the click target (44px tall)");
  assert(/vertical-align:\s*middle/.test(cssRule(".settings-hours-table td")), "every cell centred in its row");
  assert(/table-layout:\s*fixed/.test(cssRule(".settings-hours-table")), "columns line up the same in every row");
  assert(/max-width:\s*150px/.test(cssRule('.settings-hours-table input[type="time"]')) && px(cssRule('.settings-hours-table input[type="time"]'), "min-height") >= 40);
  assert(!/accent-color/.test(read("styles.css").slice(read("styles.css").indexOf(".settings-hours-table"))), "the existing blue is kept");
});

test("every weekday row has identical structure; closed rows read Closed and their time boxes are disabled", () => {
  const env = settingsEnv();
  env.run('renderBusinessHoursForm(' + JSON.stringify(weekHours()) + ")");
  const rows = env.getEl("businessHoursBody").innerHTML.split("<tr ").slice(1);
  assert.strictEqual(rows.length, 7);
  const skeleton = (row) => row.replace(/data-day="\d"/, "").replace(/<strong>\w+<\/strong>/, "").replace(/aria-label="\w+ (open|opens|closes)"/g, "").replace(/ (checked|disabled)/g, "").replace(/value="[\d:]*"/g, "").replace(/(Open|Closed)<\/span>/, "</span>").replace(/\s+/g, " ").trim();
  assert.strictEqual(new Set(rows.map(skeleton)).size, 1, "all seven rows share one layout");
  assert(rows.every((row) => row.includes('class="hours-open-label"') && row.includes('class="hours-state"')));
  assert(/Closed<\/span>/.test(rows[6]) && !/checked/.test(rows[6]) && (rows[6].match(/disabled/g) || []).length === 2, "Sunday: Closed, both time boxes disabled");
  assert(/Open<\/span>/.test(rows[0]) && /checked/.test(rows[0]) && !/disabled/.test(rows[0]));
});

test("ticking or clearing Open flips the Open/Closed text and enables or disables the time boxes", () => {
  const env = settingsEnv();
  const state = { textContent: "Closed" };
  const inputs = [{ classList: { contains: (c) => c === "hours-opens" }, disabled: true, value: "" }, { classList: { contains: (c) => c === "hours-opens" ? false : true }, disabled: true, value: "" }];
  const row = { querySelector: (sel) => (sel === ".hours-state" ? state : null), querySelectorAll: () => inputs };
  const target = { checked: true, classList: { contains: (c) => c === "hours-open" }, closest: () => row };
  env.getEl("businessHoursBody").handlers.change({ target });
  assert.strictEqual(state.textContent, "Open");
  assert(inputs.every((input) => input.disabled === false) && inputs[0].value === "09:00" && inputs[1].value === "18:00", "sensible defaults when a closed day is opened");
  target.checked = false;
  env.getEl("businessHoursBody").handlers.change({ target });
  assert.strictEqual(state.textContent, "Closed");
  assert(inputs.every((input) => input.disabled === true));
});

test("the lock control is larger, centred under the bell, and its whole 48px circle is clickable", () => {
  const lock = cssRule(".lock-now-btn");
  const bell = cssRule(".floating-notification-btn");
  assert(px(lock, "width") >= 44 && px(lock, "height") >= 44, "at least a 44px touch target (was 36px)");
  assert.strictEqual(px(lock, "width"), px(lock, "height"));
  assert(px(lock, "width") < px(bell, "width"), "compact next to the 64px bell");
  assert(/font-size:\s*1\.[3-9]\d*rem/.test(lock), "bigger icon glyph (was 1rem)");
  assert.strictEqual(px(lock, "right") + px(lock, "width") / 2, px(bell, "right") + px(bell, "width") / 2, "horizontally centred on the bell");
  assert(px(lock, "top") >= px(bell, "top") + px(bell, "height"), "sits just below the bell, not overlapping it");
  assert(/border-radius:\s*999px/.test(lock) && /cursor:\s*pointer/.test(lock) && /padding:\s*0/.test(lock), "the whole circle is the button");
  const mobile = /@media \(max-width: 640px\) \{ \.lock-now-btn \{([^}]*)\}/.exec(read("styles.css"))[1];
  assert(px(mobile, "width") >= 44 && px(mobile, "height") >= 44);
  assert(/id="lockNowBtn"[^>]*aria-label="Lock owner access"/.test(read("index.html")) && /lockNowBtn\?\.addEventListener\("click", lockOwner\)/.test(read("js/ownerlock.js")), "behaviour unchanged");
});

for (const [opens, closes, closingLabel, rows] of [["09:00:00", "18:00:00", "6pm", 9], ["10:00:00", "19:00:00", "7pm", 9], ["09:00:00", "17:00:00", "5pm", 8]]) {
  test(`booking hours ${opens.slice(0, 5)}-${closes.slice(0, 5)}: the calendar visibly includes the ${closingLabel} closing boundary and no shading follows it`, async () => {
    const env = makeEnv();
    await openCalendar(env);
    env.ctx.__d = new Date(2026, 9, 12); env.run("selectedDate = __d");  // a Monday
    setHours(env, uniformHours(opens, closes));
    env.run("renderCalendar()");
    const labels = hourLabels(env);
    assert.strictEqual(labels.length, rows + 1, "one label per hour row plus the closing boundary");
    assert.strictEqual(labels.at(-1), closingLabel, "the last label is the closing time");
    assert.strictEqual(labels[0], `${Number(opens.slice(0, 2)) % 12 || 12}${Number(opens.slice(0, 2)) >= 12 ? "pm" : "am"}`);
    assert(env.getEl("calendarWrapper").innerHTML.includes('class="times-end"'));
    assert.strictEqual(timesRows(env)[1], String(rows));
    assert(new RegExp(`repeat\\(${rows}, 90px\\) 56px`).test(env.getEl("calendarWrapper").innerHTML), "extra room for the closing label so it is not clipped");
    assert.strictEqual((env.getEl("calendarWrapper").innerHTML.match(/class="grid-end-line"/g) || []).length, 1, "the closing line is drawn once");
    assert.deepStrictEqual(bands(env), [], "the span ends exactly at closing: nothing is shaded after it");
    assert(env.getEl("calendarWrapper").innerHTML.includes(`height:${rows * 90}px`), "grid height unchanged: minute maths intact");
  });
}

test("labels run hour by hour and the closing label follows the 5 pm row (9-6 example in full)", async () => {
  const env = makeEnv();
  await openCalendar(env);
  setHours(env, uniformHours("09:00:00", "18:00:00"));
  env.ctx.__d = new Date(2026, 9, 12); env.run("selectedDate = __d; renderCalendar()");
  assert.deepStrictEqual(hourLabels(env), ["9am", "10am", "11am", "12pm", "1pm", "2pm", "3pm", "4pm", "5pm", "6pm"]);
});

test("a closed day still shows the labelled hours with the whole span shaded", async () => {
  const env = makeEnv();
  await openCalendar(env);
  setHours(env, weekHours());
  env.ctx.__d = new Date(2026, 9, 11); env.run("selectedDate = __d; renderCalendar()");  // Sunday
  assert.strictEqual(hourLabels(env).at(-1), "6pm");
  assert.deepStrictEqual(JSON.stringify(bands(env)), JSON.stringify([["Salon closed", 0, 100]]));
});

test("late appointments and active turns stay visible; the 'After closing' shading starts exactly at the closing line", async () => {
  const env = makeEnv();
  await openCalendar(env);
  env.setNow(phoenix("2026-10-12", 19, 30));
  setHours(env, uniformHours("09:00:00", "18:00:00"));
  env.ctx.__d = new Date(2026, 9, 12); env.run("selectedDate = __d");
  env.run(`appointments = [{ id: 1, appointment_time: "2026-10-12T10:00:00", status: "scheduled", customer_name: "Morning", technician_id: 1 },
    { id: 2, appointment_time: "2026-10-12T18:30:00", status: "in_service", customer_name: "Ran Late", technician_id: 1 }];
    todayTurns = [{ id: 9, status: "in_service", technician_id: 2, customer_name: "Late Walk In", service_name: "Gel", created_at: "2026-10-12T19:10:00" }];
    techniciansRaw = [{id:1, full_name:'Zed'}, {id:2, full_name:'Amy'}]; renderCalendar()`);
  const html = env.getEl("calendarWrapper").innerHTML;
  assert(html.includes("Ran Late") && html.includes("Late Walk In") && html.includes("top:855px"), "true positions, nothing hidden");
  const [after] = bands(env);
  assert.strictEqual(after[0], "After closing");
  assert(Math.abs(after[1] - ((18 - 9) / 12) * 100) < 0.001, "the shading begins at the 6 pm line (75%), not at 5 pm");
  assert.strictEqual(hourLabels(env).at(-1), "9pm", "the span grew to include the 7:10 pm turn");
  assert(hourLabels(env).includes("6pm"), "the closing hour is still labelled");
  assert(Math.abs(topPercent(env) - ((19 * 60 + 30 - 9 * 60) / 720) * 100) < 0.001, "the red line sits at 7:30 pm inside the grown span");
});

test("the current-time line before opening, during booking hours and after closing", async () => {
  const env = makeEnv();
  await openCalendar(env);
  setHours(env, uniformHours("09:00:00", "18:00:00"));
  env.ctx.__d = new Date(2026, 9, 12); env.run("selectedDate = __d; appointments = []; todayTurns = []");
  for (const [hh, mm, expected] of [[8, 30, "hidden"], [9, 0, 0], [16, 0, (7 / 9) * 100], [17, 59, (539 / 540) * 100], [18, 0, "hidden"], [19, 30, "hidden"]]) {
    env.setNow(phoenix("2026-10-12", hh, mm)); env.run("renderCalendar()");
    if (expected === "hidden") assert.strictEqual(lines(env), 0, `${hh}:${mm}`);
    else { assert.strictEqual(lines(env), 1, `${hh}:${mm}`); assert(Math.abs(topPercent(env) - expected) < 0.01, `${hh}:${mm}`); }
  }
  setHours(env, uniformHours("10:00:00", "19:00:00"));  // 10-7: the same 16:00 is now 6 of 9 hours down
  env.setNow(phoenix("2026-10-12", 16, 0)); env.run("renderCalendar()");
  assert(Math.abs(topPercent(env) - (6 / 9) * 100) < 0.01);
});

test("the Phone / AI Receptionist section shows the same saved public phone as Salon Information", async () => {
  const env = settingsEnv();
  await ownerUp(env);
  await env.run("renderSettingsPage()");
  assert.strictEqual(env.getEl("settings_salon_phone").value, "(224) 549-2806");
  assert.strictEqual(env.getEl("salonPhoneSaved").textContent, "Saved: (224) 549-2806");
  assert(env.getEl("aiStatusList").innerHTML.includes("<dt>Public salon phone</dt><dd>(224) 549-2806</dd>"));
  env.fixtures.profile.business_phone = null; env.fixtures.profile.business_phone_display = null;
  await env.run("renderSettingsPage()");
  assert.strictEqual(env.getEl("settings_salon_phone").value, "");
  assert.strictEqual(env.getEl("salonPhoneSaved").textContent, "No salon phone saved yet.");
  assert(env.getEl("aiStatusList").innerHTML.includes("Not set (add it under Salon Information)"), "both sections agree that nothing is saved");
});

test("the empty phone box no longer shows a number-looking placeholder that could be mistaken for a saved value", () => {
  const html = read("index.html");
  assert(/id="settings_salon_phone"[^>]*placeholder="Salon phone number"/.test(html));
  const settingsPage = html.slice(html.indexOf('<section id="settingsView"'), html.indexOf("<!-- ============ CHECKOUT"));
  assert(!/placeholder="[^"]*\d{3}[^"]*\d{4}"/.test(settingsPage), "no real-looking phone number as placeholder text on the settings page");
});

test("the Twilio number stays a separate value: saving or changing the public phone never alters it", async () => {
  const env = settingsEnv();
  await ownerUp(env);
  await env.run("renderSettingsPage()");
  const twilioLine = () => /<dt>Twilio number<\/dt><dd>([^<]*)<\/dd>/.exec(env.getEl("aiStatusList").innerHTML)[1];
  assert.strictEqual(twilioLine(), "(602) 555-9999");
  env.getEl("settings_salon_name").value = "Nail Salon";
  env.getEl("settings_salon_phone").value = "(480) 555-0100";
  env.bodies.length = 0;
  await submit(env, "salonProfileForm");
  const put = env.bodies.find((b) => b.url.endsWith("/settings/salon") && b.method === "PUT");
  assert.deepStrictEqual(put.body, { salon_name: "Nail Salon", business_phone: "(480) 555-0100" });
  assert(!JSON.stringify(put.body).toLowerCase().includes("twilio"), "the save request carries no Twilio field");
  assert(env.getEl("aiStatusList").innerHTML.includes("<dt>Public salon phone</dt><dd>(480) 555-0100</dd>"), "public phone updated in the AI section");
  assert.strictEqual(twilioLine(), "(602) 555-9999", "Twilio number untouched");
  assert.strictEqual(env.fixtures.ai.twilio_number, "+16025559999");
  assert(!env.bodies.some((b) => /twilio|ai-receptionist/.test(b.url) && b.method !== "GET"), "no write ever targets Twilio");
});

(async () => {
  let failed = 0;
  for (const [name, fn] of results) {
    try { await fn(); console.log("PASS", name); } catch (error) { failed++; console.log("FAIL", name, "\n   ", error.message); }
  }
  console.log(`\n${results.length - failed}/${results.length} passed`);
  process.exit(failed ? 1 : 0);
})();
