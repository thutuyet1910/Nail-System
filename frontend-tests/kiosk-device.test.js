// Kiosk device pairing: logic tests that run in plain Node (no browser, no dependencies).
//   node frontend-tests/kiosk-device.test.js
//
// kiosk-device.js is loaded into a vm context with a tiny fake DOM, a fake localStorage and a scripted fetch,
// so every claim below is about the real file. A few static checks also read the other browser files.

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const FRONTEND = path.join(__dirname, "..", "frontend");
const read = (name) => fs.readFileSync(path.join(FRONTEND, name), "utf8");

// ── fake browser ─────────────────────────────────────────────────────────────

function makeElement(id, startsHidden) {
  const classes = new Set(startsHidden ? ["hidden"] : []);
  const listeners = {};
  return {
    id,
    value: "",
    textContent: "",
    className: "",
    disabled: false,
    focused: false,
    classList: {
      add: (name) => classes.add(name),
      remove: (name) => classes.delete(name),
      contains: (name) => classes.has(name),
    },
    addEventListener: (type, handler) => (listeners[type] ||= []).push(handler),
    focus() {
      this.focused = true;
    },
    async fire(type, event = { preventDefault() {} }) {
      for (const handler of listeners[type] || []) await handler(event);
    },
  };
}

function makeEnvironment({ token = null, storageBroken = false } = {}) {
  const store = new Map(token ? [["nailKioskDeviceToken", token]] : []);
  const elements = {
    "pairing-screen": makeElement("pairing-screen", true),
    "pairing-form": makeElement("pairing-form"),
    "pairing-code": makeElement("pairing-code"),
    "pairing-submit": makeElement("pairing-submit"),
    "pairing-message": makeElement("pairing-message"),
  };
  const events = [];
  const requests = [];
  const logs = [];
  const queue = [];

  const localStorage = {
    getItem(key) {
      if (storageBroken) throw new Error("storage blocked");
      return store.has(key) ? store.get(key) : null;
    },
    setItem(key, value) {
      if (storageBroken) throw new Error("storage blocked");
      store.set(key, String(value));
    },
    removeItem(key) {
      if (storageBroken) throw new Error("storage blocked");
      store.delete(key);
    },
  };

  const context = {
    API_BASE: "/api/checkin",
    document: {
      getElementById: (id) => elements[id] || null,
      dispatchEvent: (event) => events.push(event.type),
    },
    CustomEvent: class CustomEvent {
      constructor(type) {
        this.type = type;
      }
    },
    localStorage,
    console: {
      log: (...a) => logs.push(a.join(" ")),
      warn: (...a) => logs.push(a.join(" ")),
      error: (...a) => logs.push(a.join(" ")),
    },
    fetch: async (url, options = {}) => {
      requests.push({ url, options });
      const next = queue.shift();
      if (!next) throw new Error("unexpected request " + url);
      if (next instanceof Error) throw next;
      return {
        status: next.status,
        ok: next.status >= 200 && next.status < 300,
        json: async () => next.body,
      };
    },
  };
  vm.createContext(context);
  vm.runInContext(read("config.js"), context);
  vm.runInContext(read("kiosk-device.js"), context);

  return {
    elements,
    events,
    requests,
    logs,
    store,
    reply: (status, body) => queue.push({ status, body }),
    fail: (error) => queue.push(error),
    run: (code) => vm.runInContext(code, context),
    pairingVisible: () => !elements["pairing-screen"].classList.contains("hidden"),
    message: () => elements["pairing-message"].textContent,
  };
}

// ── tiny runner ──────────────────────────────────────────────────────────────

const tests = [];
const test = (name, fn) => tests.push([name, fn]);

// ── unpaired state ───────────────────────────────────────────────────────────

test("a tablet with no token shows the pairing screen at start-up", () => {
  const env = makeEnvironment();
  assert.equal(env.run("isKioskPaired()"), false);
  assert.equal(env.run("initKioskDevice()"), false);
  assert.equal(env.pairingVisible(), true);
  assert.equal(env.elements["pairing-code"].focused, true);
});

test("a tablet that already holds a token starts paired and hides the pairing screen", () => {
  const env = makeEnvironment({ token: "7.abcdefghijklmnopqrstuvwxyz0123456789ABCD" });
  assert.equal(env.run("initKioskDevice()"), true);
  assert.equal(env.pairingVisible(), false);
});

test("a kiosk call without a token never reaches the network and asks for pairing instead", async () => {
  const env = makeEnvironment();
  await assert.rejects(() => env.run('kioskFetch("/services")'));
  assert.equal(env.requests.length, 0);
  assert.equal(env.pairingVisible(), true);
});

// ── pairing flow ─────────────────────────────────────────────────────────────

test("entering a valid code stores the device token, hides the screen and announces it", async () => {
  const env = makeEnvironment();
  env.run("initKioskDevice()");
  env.reply(200, { device_id: 3, display_name: "Front desk", device_token: "3.SECRETSECRETSECRETSECRETSECRETSECRETSECRET1" });
  env.elements["pairing-code"].value = "abcd-efgh";
  await env.elements["pairing-form"].fire("submit");

  assert.equal(env.store.get("nailKioskDeviceToken"), "3.SECRETSECRETSECRETSECRETSECRETSECRETSECRET1");
  assert.equal(env.run("isKioskPaired()"), true);
  assert.equal(env.pairingVisible(), false);
  assert.deepEqual(env.events, ["kiosk:paired"]);
});

test("the pairing request is a POST with the code in the body, no device header and nothing in the URL", async () => {
  const env = makeEnvironment();
  env.reply(200, { device_token: "1.tokentokentokentokentokentokentokentoken00" });
  env.elements["pairing-code"].value = "ABCD-EFGH";
  await env.elements["pairing-form"].fire("submit");

  const { url, options } = env.requests[0];
  assert.equal(url, "/api/checkin/kiosk/pair");
  assert.equal(options.method, "POST");
  assert.deepEqual(JSON.parse(options.body), { code: "ABCD-EFGH" });
  assert.equal(Object.keys(options.headers).some((h) => /device|token/i.test(h)), false);
  assert.equal(options.credentials, "omit");
  assert.ok(!/[?#]/.test(url) && !/ABCD/.test(url));
});

test("a wrong or expired code stores nothing and says so", async () => {
  const env = makeEnvironment();
  env.run("initKioskDevice()");
  env.reply(400, { detail: "That pairing code is not valid or has expired." });
  env.elements["pairing-code"].value = "ZZZZ-ZZZZ";
  await env.elements["pairing-form"].fire("submit");
  assert.equal(env.run("isKioskPaired()"), false);
  assert.equal(env.store.size, 0);
  assert.match(env.message(), /not valid or has expired/);
  assert.equal(env.pairingVisible(), true); // the overlay stays up
});

test("too many attempts is reported without pretending the code was wrong", async () => {
  const env = makeEnvironment();
  env.reply(429, { detail: "Too many attempts." });
  env.elements["pairing-code"].value = "ZZZZ-ZZZZ";
  await env.elements["pairing-form"].fire("submit");
  assert.match(env.message(), /Too many attempts/);
  assert.equal(env.store.size, 0);
});

test("a network failure is reported and nothing is stored", async () => {
  const env = makeEnvironment();
  env.fail(new TypeError("Failed to fetch"));
  env.elements["pairing-code"].value = "ABCD-EFGH";
  await env.elements["pairing-form"].fire("submit");
  assert.match(env.message(), /Cannot reach the salon computer/);
  assert.equal(env.store.size, 0);
});

test("an empty code makes no request", async () => {
  const env = makeEnvironment();
  env.elements["pairing-code"].value = "   ";
  await env.elements["pairing-form"].fire("submit");
  assert.equal(env.requests.length, 0);
  assert.match(env.message(), /enter the pairing code/i);
});

test("the typed code is cleared and the button re-enabled whether pairing worked or not", async () => {
  const env = makeEnvironment();
  env.reply(400, { detail: "no" });
  env.elements["pairing-code"].value = "ZZZZ-ZZZZ";
  await env.elements["pairing-form"].fire("submit");
  assert.equal(env.elements["pairing-code"].value, "");
  assert.equal(env.elements["pairing-submit"].disabled, false);
});

test("a response without a device token is not treated as success", async () => {
  const env = makeEnvironment();
  env.reply(200, { device_id: 1 });
  env.elements["pairing-code"].value = "ABCD-EFGH";
  await env.elements["pairing-form"].fire("submit");
  assert.equal(env.run("isKioskPaired()"), false);
});

// ── authenticated requests ───────────────────────────────────────────────────

const TOKEN = "5.PAIREDTOKENPAIREDTOKENPAIREDTOKENPAIREDTOKEN12";

test("every kiosk request carries the device token header, same-origin, uncached, without cookies", async () => {
  const env = makeEnvironment({ token: TOKEN });
  env.reply(200, []);
  await env.run('kioskFetch("/services")');
  const { url, options } = env.requests[0];
  assert.equal(url, "/api/checkin/services");
  assert.equal(options.headers["X-Kiosk-Device-Token"], TOKEN);
  assert.equal(options.credentials, "omit");
  assert.equal(options.cache, "no-store");
});

test("caller headers and the profile-edit header are kept alongside the device token", async () => {
  const env = makeEnvironment({ token: TOKEN });
  env.reply(200, {});
  await env.run(
    'kioskFetch("/customers/5550000001/profile", { method: "PATCH", body: "{}", headers: { "Content-Type": "application/json", [KIOSK_PROFILE_EDIT_HEADER]: "edit-token" } })'
  );
  const { options } = env.requests[0];
  assert.equal(options.method, "PATCH");
  assert.equal(options.headers["Content-Type"], "application/json");
  assert.equal(options.headers["X-Profile-Edit-Token"], "edit-token");
  assert.equal(options.headers["X-Kiosk-Device-Token"], TOKEN);
});

test("a caller cannot replace the device header with another value", async () => {
  const env = makeEnvironment({ token: TOKEN });
  env.reply(200, {});
  await env.run('kioskFetch("/services", { headers: { "X-Kiosk-Device-Token": "attacker-value" } })');
  assert.equal(env.requests[0].options.headers["X-Kiosk-Device-Token"], TOKEN);
});

test("the token never appears in a URL, a query string or the console", async () => {
  const env = makeEnvironment({ token: TOKEN });
  env.reply(200, []);
  env.reply(200, []);
  await env.run('kioskFetch("/services")');
  await env.run('kioskFetch("/customers/by-phone/5550000001")');
  for (const { url } of env.requests) assert.ok(!url.includes(TOKEN) && !url.includes("PAIREDTOKEN") && !/[?#]/.test(url));
  assert.ok(env.logs.every((line) => !line.includes("PAIREDTOKEN")));
  env.reply(200, { device_token: "9.NEWTOKENNEWTOKENNEWTOKENNEWTOKENNEWTOKEN001" });
  env.elements["pairing-code"].value = "ABCD-EFGH";
  await env.elements["pairing-form"].fire("submit");
  assert.ok(env.logs.every((line) => !line.includes("NEWTOKEN")));
  assert.ok(env.requests.every(({ url }) => !url.includes("NEWTOKEN")));
});

test("the token is never copied into the page", async () => {
  const env = makeEnvironment({ token: TOKEN });
  env.run("initKioskDevice()");
  assert.ok(Object.values(env.elements).every((el) => !String(el.textContent).includes("PAIREDTOKEN") && !String(el.value).includes("PAIREDTOKEN")));
});

// ── revoked / lost token ─────────────────────────────────────────────────────

test("a 401 (revoked tablet) clears the token and returns to the pairing screen with an explanation", async () => {
  const env = makeEnvironment({ token: TOKEN });
  env.run("initKioskDevice()");
  assert.equal(env.pairingVisible(), false);
  env.reply(401, { detail: "This tablet is not paired." });
  const response = await env.run('kioskFetch("/queue-status")');
  assert.equal(response.status, 401);
  assert.equal(env.store.has("nailKioskDeviceToken"), false);
  assert.equal(env.run("isKioskPaired()"), false);
  assert.equal(env.pairingVisible(), true);
  assert.match(env.message(), /no longer paired/);
});

test("after revocation no further request is sent until the tablet is paired again", async () => {
  const env = makeEnvironment({ token: TOKEN });
  env.reply(401, {});
  await env.run('kioskFetch("/services")');
  await assert.rejects(() => env.run('kioskFetch("/services")'));
  assert.equal(env.requests.length, 1);
});

test("pairing again after a revocation works and the new token is used", async () => {
  const env = makeEnvironment({ token: TOKEN });
  env.reply(401, {});
  await env.run('kioskFetch("/services")');
  env.reply(200, { device_token: "6.FRESHTOKENFRESHTOKENFRESHTOKENFRESHTOKEN001" });
  env.elements["pairing-code"].value = "ABCD-EFGH";
  await env.elements["pairing-form"].fire("submit");
  env.reply(200, []);
  await env.run('kioskFetch("/services")');
  assert.equal(env.requests.at(-1).options.headers["X-Kiosk-Device-Token"], "6.FRESHTOKENFRESHTOKENFRESHTOKENFRESHTOKEN001");
});

test("a request that fails for another reason (500, 429) does not unpair the tablet", async () => {
  const env = makeEnvironment({ token: TOKEN });
  env.reply(500, {});
  env.reply(429, {});
  env.reply(503, {});
  for (let i = 0; i < 3; i++) await env.run('kioskFetch("/services")');
  assert.equal(env.run("isKioskPaired()"), true);
  assert.equal(env.pairingVisible(), false);
});

test("a background request does not wipe a pairing code that is being typed", () => {
  const env = makeEnvironment();
  env.run("initKioskDevice()");
  env.elements["pairing-code"].value = "ABCD-E";
  env.run("showPairingScreen()");
  assert.equal(env.elements["pairing-code"].value, "ABCD-E");
});

// ── storage ──────────────────────────────────────────────────────────────────

test("when browser storage is blocked the token still works for the session (memory only)", async () => {
  const env = makeEnvironment({ storageBroken: true });
  env.reply(200, { device_token: "2.MEMORYTOKENMEMORYTOKENMEMORYTOKENMEMORY0001" });
  env.elements["pairing-code"].value = "ABCD-EFGH";
  await env.elements["pairing-form"].fire("submit");
  assert.equal(env.run("isKioskPaired()"), true);
  env.reply(200, []);
  await env.run('kioskFetch("/services")');
  assert.equal(env.requests.at(-1).options.headers["X-Kiosk-Device-Token"], "2.MEMORYTOKENMEMORYTOKENMEMORYTOKENMEMORY0001");
});

test("only one storage key is used, and it is not a Cookie or the URL", () => {
  const source = read("kiosk-device.js");
  assert.deepEqual([...new Set(source.match(/nailKioskDeviceToken/g))], ["nailKioskDeviceToken"]);
  assert.ok(!/document\.cookie|location\.(search|hash|href)|history\.(push|replace)State|sessionStorage/.test(source));
});

// ── the other browser files ──────────────────────────────────────────────────

test("script.js makes every API call through kioskFetch (never a bare fetch)", () => {
  const script = read("script.js");
  assert.equal((script.match(/(?<![A-Za-z.])fetch\(/g) || []).length, 0);
  assert.ok((script.match(/kioskFetch\(/g) || []).length >= 6);
  assert.ok(!/localStorage\.(get|set)Item\([^)]*[Tt]oken/.test(script));
  assert.ok(!/getKioskToken\(\)/.test(script), "script.js must not read the token");
});

test("customer text is escaped before it is rendered as HTML", () => {
  const script = read("script.js");
  assert.match(script, /escapeHtml\(safeText\(customer\.first_name\)\)/);
  assert.match(script, /escapeHtml\(safeText\(customer\.email_hint\)\)/);
  assert.ok(!/safeText\(customer\.(full_name|email)\)/.test(script));
  assert.ok(!/date_of_birth/.test(script.slice(script.indexOf("function renderExistingCustomerProfile"), script.indexOf("function openExistingCustomerScreen"))));
});

test("the returning-customer screens only use the reduced fields", () => {
  const script = read("script.js");
  assert.ok(!/existingCustomer\??\.(full_name|email|date_of_birth|referral_code)\b/.test(script));
  assert.ok(!/status\.full_name/.test(script));
});

test("profile editing asks for the birth date first and sends the edit token", () => {
  const script = read("script.js");
  assert.match(script, /profile-access/);
  assert.match(script, /KIOSK_PROFILE_EDIT_HEADER\]: profileEditToken/);
  assert.match(read("index.html"), /id="verify-profile-screen"/);
});

test("no browser file contains the internal service token, its name, or an owner/internal address", () => {
  const joined = fs.readdirSync(FRONTEND).filter((f) => /\.(js|html|css)$/.test(f)).map(read).join("\n");
  for (const forbidden of ["X-Internal-Service-Token", "CHECKIN_INTERNAL_SERVICE_TOKEN", "OWNER_API_BASE", "/internal/", "/api/owner", ":8001", ":8000", "127.0.0.1", "localhost"]) {
    assert.ok(!joined.includes(forbidden), `found ${forbidden}`);
  }
});

test("the page loads config.js and kiosk-device.js before script.js and uses no inline script", () => {
  const html = read("index.html");
  const order = [...html.matchAll(/<script src="([^"]+)"/g)].map((m) => m[1]);
  assert.ok(order.indexOf("config.js") < order.indexOf("kiosk-device.js") && order.indexOf("kiosk-device.js") < order.indexOf("script.js"));
  assert.ok(!/<script(?![^>]*\bsrc=)[^>]*>/.test(html), "inline <script> would be blocked by the CSP");
  assert.ok(!/\son[a-z]+\s*=/.test(html), "inline event handlers would be blocked by the CSP");
});

test("all new screens have translations in every language", () => {
  const context = { };
  vm.createContext(context);
  vm.runInContext(read("translations.js") + "\nthis.translations = translations;", context);
  const keys = ["pairTitle", "pairText", "pairSubmit", "pairInvalid", "pairTooMany", "pairNetwork", "pairRevoked", "pairEnterCode",
    "verifyTitle", "verifyText", "verifyFailed", "verifyLocked", "verifyNeeded", "tooManyRequests"];
  for (const lang of ["en", "vi", "es"]) for (const key of keys) assert.ok(context.translations[lang][key], `${lang}.${key}`);
});

// ── run ──────────────────────────────────────────────────────────────────────

(async () => {
  let failed = 0;
  for (const [name, fn] of tests) {
    try {
      await fn();
      console.log("PASS", name);
    } catch (error) {
      failed++;
      console.log("FAIL", name, "\n   ", error.message.split("\n").slice(0, 4).join("\n    "));
    }
  }
  console.log(`\n${tests.length - failed}/${tests.length} passed`);
  process.exit(failed ? 1 : 0);
})();
