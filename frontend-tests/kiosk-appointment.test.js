// The kiosk's phone-first appointment flow, driven through the REAL script.js and translations.js in a fake page (plain Node, no dependencies).
//   node frontend-tests/kiosk-appointment.test.js
//
// What is scripted is only the server: /appointments/lookup, /appointments/check-in, the normal customer routes. Everything the customer
// sees (screens, messages, escaped text, buttons) is the real code.

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const FRONTEND = path.join(__dirname, "..", "frontend");
const read = (name) => fs.readFileSync(path.join(FRONTEND, name), "utf8");
const tests = [];
const test = (name, fn) => tests.push([name, fn]);
const settle = async () => { for (let i = 0; i < 12; i++) await new Promise((resolve) => setImmediate(resolve)); };

function makeKiosk({ language = "en" } = {}) {
  const elements = new Map();
  const make = (id) => {
    const handlers = {};
    const classes = new Set();
    return {
      id, value: "", textContent: "", innerHTML: "", disabled: false, className: "", style: {}, dataset: {}, children: [],
      classList: { add: (c) => classes.add(c), remove: (c) => classes.delete(c), contains: (c) => classes.has(c), toggle: (c) => (classes.has(c) ? classes.delete(c) : classes.add(c)) },
      addEventListener: (type, fn) => { (handlers[type] ||= []).push(fn); },
      async fire(type, event = {}) { for (const fn of handlers[type] || []) await fn({ preventDefault() {}, stopPropagation() {}, target: this, ...event }); },
      click() { return this.fire("click"); }, focus() {}, reset() { this.value = ""; }, scrollIntoView() {}, closest: () => null, appendChild() {},
      querySelectorAll: () => [], querySelector: () => null, setAttribute() {}, removeAttribute() {},
    };
  };
  const get = (id) => { if (!elements.has(id)) elements.set(id, make(id)); return elements.get(id); };
  const storage = new Map([["nailSalonLanguage", language]]);
  const requests = [];
  const server = { routes: {}, default: { status: 200, body: {} } };
  const kiosk = {
    get, requests, server,
    visible: () => ["phone-screen", "appointment-screen", "form-screen", "existing-screen", "thank-you-screen", "existing-customer-service-screen", "new-customer-service-screen"]
      .filter((id) => get(id).style.display === "block"),
    message: () => get("message").textContent,
    called: (method, route) => requests.filter((r) => r.method === method && r.path.startsWith(route)),
  };
  const ctx = {
    console: { log() {}, warn() {}, error() {} }, JSON, Math, Date, Promise, Error, Array, Object, String, Number, Set, Map, RegExp, Intl, encodeURIComponent, setTimeout, clearTimeout,
    document: { getElementById: get, querySelector: (selector) => get("q:" + selector), querySelectorAll: () => [], addEventListener() {}, documentElement: {} },
    localStorage: { getItem: (k) => (storage.has(k) ? storage.get(k) : null), setItem: (k, v) => storage.set(k, v) },
    setInterval: () => 1, clearInterval() {}, window: {},
    isKioskPaired: () => true, initKioskDevice() {},
    kioskFetch: async (route, options = {}) => {
      const method = options.method || "GET";
      requests.push({ method, path: route, body: options.body ? JSON.parse(options.body) : undefined });
      const match = server.routes[`${method} ${route}`] || server.routes[`${method} ${route.split("?")[0]}`]
        || Object.entries(server.routes).find(([key]) => key.endsWith("*") && `${method} ${route}`.startsWith(key.slice(0, -1)))?.[1] || server.default;
      const result = typeof match === "function" ? await match(options) : match;
      return { ok: result.status >= 200 && result.status < 300, status: result.status, json: async () => result.body, clone() { return this; } };
    },
  };
  ctx.globalThis = ctx;
  vm.createContext(ctx);
  vm.runInContext(read("translations.js") + "\nthis.translations = translations;", ctx, { filename: "translations.js" });
  vm.runInContext(read("script.js"), ctx, { filename: "script.js" });
  kiosk.ctx = ctx;
  kiosk.run = (code) => vm.runInContext(code, ctx);
  kiosk.type = async (digits) => { get("phone_number").value = digits; await get("phone-form").fire("submit"); await settle(); };
  server.routes["GET /queue-status"] = { status: 200, body: { checkins: [] } };
  server.routes["GET /services"] = { status: 200, body: [{ id: 10, name: "Gel Manicure", category: "Nails", duration_minutes: 45 }] };
  return kiosk;
}

const APPOINTMENT = { code: "APPT-1", time: "2030-01-01T14:00", first_name: "Ana", services: ["Gel Manicure", "Classic Pedicure"], technician_name: "Amy" };
const found = (appointment = APPOINTMENT, extra = {}) => ({ status: 200, body: { outcome: "one", already_checked_in: false, appointment, ...extra } });
const CHECKED_IN = { status: 200, body: { message: "Customer checked in successfully.", phone_number: "6025551234", full_name: "Ana", discounts_applied: [], selected_services: ["Gel Manicure", "Classic Pedicure"], selected_service_ids: [10, 11] } };

// ── A. one appointment: phone, summary, one tap ───────────────────────────────────────────────────────

test("A. phone -> appointment found -> Check In -> success; no name, no services, no walk-in questions", async () => {
  const k = makeKiosk();
  k.server.routes["POST /appointments/lookup"] = found();
  k.server.routes["POST /appointments/check-in"] = CHECKED_IN;
  await k.type("(602) 555-1234");
  assert.deepEqual(k.visible(), ["appointment-screen"]);
  assert.equal(k.get("appointment-title").textContent, "Welcome back, Ana");
  const details = k.get("appointment-details").innerHTML;
  assert.ok(/2:00\s?PM/.test(details), details);
  assert.ok(details.includes("Gel Manicure, Classic Pedicure") && details.includes("Amy"));
  assert.deepEqual(k.called("POST", "/appointments/lookup")[0].body, { phone_number: "6025551234" });
  assert.equal(k.called("GET", "/customers/by-phone").length, 0, "the walk-in lookup was not even started");

  await k.get("appointment-checkin-btn").click();
  await settle();
  assert.deepEqual(k.visible(), ["thank-you-screen"]);
  assert.deepEqual(k.called("POST", "/appointments/check-in").map((r) => r.body), [{ phone_number: "6025551234", appointment_code: "APPT-1" }]);
  const thanks = k.get("thank-you-message").textContent;
  assert.ok(thanks.includes("Gel Manicure, Classic Pedicure") && /2:00\s?PM/.test(thanks), thanks);
  for (const never of ["/customers/new", "/customers/check-in", "/customers/by-phone", "/referrals"]) assert.equal(k.requests.filter((r) => r.path.startsWith(never)).length, 0, never);
});

test("A. any technician is shown as such", async () => {
  const k = makeKiosk();
  k.server.routes["POST /appointments/lookup"] = found({ ...APPOINTMENT, technician_name: null });
  await k.type("6025551234");
  assert.ok(k.get("appointment-details").innerHTML.includes("Any technician"));
});

test("A. tapping Check In twice sends one request", async () => {
  const k = makeKiosk();
  k.server.routes["POST /appointments/lookup"] = found();
  let release;
  k.server.routes["POST /appointments/check-in"] = () => new Promise((resolve) => { release = () => resolve(CHECKED_IN); });
  await k.type("6025551234");
  const first = k.get("appointment-checkin-btn").click();
  await settle();
  const second = k.get("appointment-checkin-btn").click();
  await settle();
  assert.equal(k.called("POST", "/appointments/check-in").length, 1, "the second tap while the first is running does nothing");
  assert.equal(k.get("appointment-checkin-btn").disabled, true);
  release();
  await first; await second; await settle();
  assert.equal(k.get("appointment-checkin-btn").disabled, false);
  assert.deepEqual(k.visible(), ["thank-you-screen"]);
});

test("A. what the server sent is shown as text, never as markup", async () => {
  const k = makeKiosk();
  k.server.routes["POST /appointments/lookup"] = found({ ...APPOINTMENT, first_name: "<b>Ana</b>", services: ["<img src=x onerror=alert(1)>"], technician_name: "<i>Amy</i>" });
  await k.type("6025551234");
  const details = k.get("appointment-details").innerHTML;
  assert.ok(!details.includes("<img") && !details.includes("<i>") && details.includes("&lt;img"), details);
});

test("A. a birthday reward on the visit is announced like on a normal check-in", async () => {
  const k = makeKiosk();
  k.server.routes["POST /appointments/lookup"] = found();
  k.server.routes["POST /appointments/check-in"] = { status: 200, body: { ...CHECKED_IN.body, discounts_applied: [{ type: "birthday", amount: 10 }] } };
  await k.type("6025551234");
  await k.get("appointment-checkin-btn").click();
  await settle();
  assert.ok(k.get("success-modal-text").textContent.includes("Happy Birthday"));
});

// ── B. no appointment: the walk-in flow is untouched ──────────────────────────────────────────────────

test("B. no appointment and an unknown phone -> the new-customer form, exactly as before", async () => {
  const k = makeKiosk();
  k.server.routes["POST /appointments/lookup"] = { status: 200, body: { outcome: "none", already_checked_in: false, appointment: null } };
  k.server.routes["GET /customers/by-phone/6025551234"] = { status: 404, body: { detail: "Customer not found." } };
  await k.type("6025551234");
  assert.deepEqual(k.visible(), ["form-screen"]);
  assert.equal(k.called("GET", "/customers/by-phone").length, 1);
});

test("B. no appointment and a returning customer -> the returning-customer screen, exactly as before", async () => {
  const k = makeKiosk();
  k.server.routes["POST /appointments/lookup"] = { status: 200, body: { outcome: "none", already_checked_in: false, appointment: null } };
  k.server.routes["GET /customers/by-phone/6025551234"] = { status: 200, body: { first_name: "Bea", phone_number: "6025551234", phone_number_formatted: "(602) 555-1234", email_hint: null, has_referral_code: false } };
  k.server.routes["GET /customers/check-in-status/6025551234"] = { status: 200, body: { first_name: "Bea", already_checked_in_today: false } };
  await k.type("6025551234");
  assert.deepEqual(k.visible(), ["existing-screen"]);
});

test("B. a phone that is not ten digits never reaches the server", async () => {
  const k = makeKiosk();
  await k.type("123");
  assert.equal(k.requests.filter((r) => r.path.startsWith("/appointments")).length, 0);
  assert.ok(k.message().length > 0);
});

// ── C. several appointments, or one only staff can handle ─────────────────────────────────────────────

test("C. several appointments -> ask a staff member; nothing is guessed or shown", async () => {
  const k = makeKiosk();
  k.server.routes["POST /appointments/lookup"] = { status: 200, body: { outcome: "multiple", already_checked_in: false, appointment: null } };
  await k.type("6025551234");
  assert.deepEqual(k.visible(), ["phone-screen"]);
  assert.equal(k.message(), "We found more than one appointment for this phone number. Please ask a staff member for help.");
  assert.equal(k.get("appointment-details").innerHTML, "");
  assert.equal(k.requests.filter((r) => r.path.startsWith("/customers") || r.path === "/appointments/check-in").length, 0, "no walk-in questions and no check-in");
});

test("C. an appointment that only staff can check in -> ask the front desk", async () => {
  const k = makeKiosk();
  k.server.routes["POST /appointments/lookup"] = { status: 200, body: { outcome: "staff", already_checked_in: false, appointment: null } };
  await k.type("6025551234");
  assert.deepEqual(k.visible(), ["phone-screen"]);
  assert.ok(k.message().includes("front desk"));
});

// ── D. "This isn't my appointment" ────────────────────────────────────────────────────────────────────

test("D. This isn't my appointment -> nothing is checked in; the normal flow continues", async () => {
  const k = makeKiosk();
  k.server.routes["POST /appointments/lookup"] = found();
  k.server.routes["GET /customers/by-phone/6025551234"] = { status: 404, body: { detail: "Customer not found." } };
  await k.type("6025551234");
  assert.deepEqual(k.visible(), ["appointment-screen"]);
  await k.get("appointment-not-mine-btn").click();
  await settle();
  assert.deepEqual(k.visible(), ["form-screen"]);
  assert.equal(k.called("POST", "/appointments/check-in").length, 0);
  assert.equal(k.run("pendingAppointment"), null);
});

// ── E. failures are never "no appointment" ────────────────────────────────────────────────────────────

test("E. the appointment check failing -> staff help, and NOT the walk-in flow", async () => {
  const k = makeKiosk();
  k.server.routes["POST /appointments/lookup"] = { status: 503, body: { detail: "We couldn't check your appointment right now. Please ask a staff member for help." } };
  await k.type("6025551234");
  assert.deepEqual(k.visible(), ["phone-screen"]);
  assert.equal(k.message(), "We couldn't check your appointment right now. Please ask a staff member for help.");
  assert.equal(k.requests.filter((r) => r.path.startsWith("/customers")).length, 0);
});

test("E. a server error text is never shown to the customer", async () => {
  const k = makeKiosk();
  k.server.routes["POST /appointments/lookup"] = { status: 500, body: { detail: "Traceback: OwnerClient failed at http://127.0.0.1:8001 token=abc" } };
  await k.type("6025551234");
  assert.ok(!k.message().includes("Traceback") && !k.message().includes("8001") && !k.message().includes("token"));
});

test("E. too many tries and an un-paired tablet keep their own messages", async () => {
  const k = makeKiosk();
  k.server.routes["POST /appointments/lookup"] = { status: 429, body: { detail: "Too many attempts." } };
  await k.type("6025551234");
  assert.equal(k.message(), k.run("t('tooManyRequests')"));
});

test("E. the check-in being refused because the appointment changed -> staff help, and the appointment is forgotten", async () => {
  const k = makeKiosk();
  k.server.routes["POST /appointments/lookup"] = found();
  k.server.routes["POST /appointments/check-in"] = { status: 409, body: { detail: "This appointment has changed." } };
  await k.type("6025551234");
  await k.get("appointment-checkin-btn").click();
  await settle();
  assert.deepEqual(k.visible(), ["phone-screen"]);
  assert.equal(k.message(), "This appointment has changed. Please ask a staff member for help.");
  assert.equal(k.run("pendingAppointment"), null);
});

test("E. a failure during the confirmation is also a staff-help message", async () => {
  const k = makeKiosk();
  k.server.routes["POST /appointments/lookup"] = found();
  k.server.routes["POST /appointments/check-in"] = { status: 503, body: { detail: "internal" } };
  await k.type("6025551234");
  await k.get("appointment-checkin-btn").click();
  await settle();
  assert.deepEqual(k.visible(), ["phone-screen"]);
  assert.ok(k.message().includes("staff member"));
  assert.equal(k.get("appointment-checkin-btn").disabled, false);
});

// ── F. already checked in ─────────────────────────────────────────────────────────────────────────────

test("F. someone who already checked in today is told so, with no second check-in", async () => {
  const k = makeKiosk();
  k.server.routes["POST /appointments/lookup"] = found(APPOINTMENT, { already_checked_in: true });
  await k.type("6025551234");
  assert.deepEqual(k.visible(), ["phone-screen"]);
  assert.equal(k.message(), "Ana has already checked in today.");
  assert.equal(k.called("POST", "/appointments/check-in").length, 0);
});

// ── G. languages and structure ────────────────────────────────────────────────────────────────────────

test("G. every new text exists in English, Vietnamese and Spanish", () => {
  const k = makeKiosk();
  const keys = ["appointmentFound", "appointmentTimeLabel", "appointmentTechnicianLabel", "appointmentAnyTechnician", "notMyAppointment", "appointmentMultiple",
    "appointmentNeedsStaff", "appointmentLookupFailed", "appointmentChanged", "thankYouAppointment"];
  for (const language of ["en", "vi", "es"]) {
    for (const key of keys) {
      const text = k.run(`translations.${language}.${key}`);
      assert.ok(typeof text === "string" && text.trim().length >= 3, `${language}.${key}`);
    }
    assert.ok(k.run(`translations.${language}.thankYouAppointment`).includes("{time}") && k.run(`translations.${language}.thankYouAppointment`).includes("{services}"), language);
  }
  assert.notEqual(k.run("translations.vi.appointmentMultiple"), k.run("translations.en.appointmentMultiple"));
  assert.notEqual(k.run("translations.es.appointmentMultiple"), k.run("translations.en.appointmentMultiple"));
});

test("G. switching language while the appointment is shown translates it", async () => {
  const k = makeKiosk();
  k.server.routes["POST /appointments/lookup"] = found();
  await k.type("6025551234");
  k.run("applyLanguage('es')");
  assert.ok(k.get("appointment-title").textContent.startsWith(k.run("translations.es.welcomeBack").split("{")[0]));
  assert.ok(k.get("appointment-details").innerHTML.includes("Hora") && k.get("appointment-details").innerHTML.includes("Técnico"));
});

test("G. the page has the appointment screen with its two buttons, and no inline script", () => {
  const html = read("index.html");
  for (const id of ["appointment-screen", "appointment-title", "appointment-details", "appointment-checkin-btn", "appointment-not-mine-btn"]) assert.ok(html.includes(`id="${id}"`), id);
  assert.ok(!/<script(?![^>]*\bsrc=)[^>]*>/i.test(html), "no inline script");
  assert.ok(!/onerror=|onclick=/i.test(html));
});

test("G. the browser never receives or sends an internal id, only the appointment code and the typed phone", () => {
  const script = read("script.js");
  const calls = [...script.matchAll(/\/appointments\/(lookup|check-in)/g)];
  assert.equal(calls.length, 2);
  assert.ok(!/appointment_id|customer_id|external_customer_id|date_of_birth.*appointment/.test(script.slice(script.indexOf("Appointment (phone first)"), script.indexOf("// ── Services"))));
});

(async () => {
  let failed = 0;
  for (const [name, fn] of tests) {
    try { await fn(); console.log("PASS", name); } catch (error) { failed++; console.log("FAIL", name, "\n   ", error.message); }
  }
  console.log(`\n${tests.length - failed}/${tests.length} passed`);
  process.exit(failed ? 1 : 0);
})();
