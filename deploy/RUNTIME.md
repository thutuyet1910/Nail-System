# Runtime layout, configuration, secrets and backups (Phase 3)

This describes where a **real salon install** keeps its program files, data, settings, secrets, logs and backups,
and how the two backends (Check-In and Owner) find them. It applies to both repositories; the code is one shared file
pair, `nailsystem_runtime.py` and `nailsystem_backup.py`, kept byte-identical in each (a test compares them).
There is no installer or launcher yet: everything below can be exercised by hand, and development is unchanged.

## 1. What lives where

```text
C:\Program Files\NailSystem\            (installer, read-only at run time, replaced on upgrade)
    app code, bundled Python runtime, Caddy, frontends

C:\ProgramData\NailSystem\              (data; survives upgrades and uninstall)
    config\salon.json                   non-secret deployment settings
    secrets\secrets.dat                 DPAPI-protected secrets
    data\owner\owner.db                 Owner database
    data\checkin\checkin.db             Check-In database (customers, visits, kiosk devices)
    backups\owner\   backups\checkin\   verified backups
    logs\owner\  logs\checkin\          rotating logs (logs\launcher\ reserved)
```

| Belongs in Program Files | Belongs in ProgramData |
|---|---|
| Code, bundled runtime, Caddy binary, static frontends, the Caddyfile template | Databases, `salon.json`, `secrets.dat`, backups, logs |
| Replaced wholesale by an upgrade | Never replaced by an upgrade; migrated in place (additive, repeatable) |
| Not writable by the running app | Writable by the runtime account only |

**Production databases never belong in a Git working copy or in the install folder.** Product mode refuses a data
folder inside a Git checkout, and the apps refuse a database outside the data folder.

## 2. Development mode and product mode

The mode is chosen **explicitly** by `NAILSYSTEM_MODE`; it is never guessed from the current directory.

| | development (default) | product |
|---|---|---|
| How | nothing to set | `NAILSYSTEM_MODE=product` (set by the installer/launcher) |
| Data root | none: databases stay where you point `DATABASE_URL` (repo-local by default). Optional opt-in: `NAILSYSTEM_HOME=<absolute folder>` | `%PROGRAMDATA%\NailSystem`, or `NAILSYSTEM_HOME` for testing |
| `.env` (Check-In) | loaded, never overrides the environment | **ignored** (reported by name in the log) |
| `salon.json` | used only if `NAILSYSTEM_HOME` is set | required; a missing or malformed file stops start-up |
| Secrets | plain environment as before (or the store, if `NAILSYSTEM_HOME` has one) | the protected store; required ones must exist |
| Logs | console | rotating files + console, redacted |
| Folders | not created | created (`config`, `data\<app>`, `backups\<app>`, `logs\<app>`) |

Nothing in the test suites ever touches `C:\ProgramData\NailSystem`: tests use temporary folders and plain dictionaries.

## 3. Configuration precedence

**Development** (first wins): 1. process environment, 2. `.env` (Check-In only; fills only what is unset),
3. `salon.json` and the layout (only if `NAILSYSTEM_HOME` is set), 4. built-in defaults.

**Product** (first wins): 1. the protected secrets store (for secrets), 2. `salon.json` and the installed layout (for
everything this layer manages), 3. the process environment **only** when `NAILSYSTEM_ALLOW_ENV_OVERRIDE=true`
(support/debug; logged as a warning, naming what was overridden), 4. built-in safe defaults.

In product mode the managed names are **overwritten (or removed) at start-up** and each ignored value is logged *by
name*, so a stale environment variable or a forgotten `.env` can never silently replace an installed value.

| Name | Source in product mode | Apps |
|---|---|---|
| `DATABASE_URL` | the installed layout (`data\<app>\<app>.db`) | both |
| `SALON_TIMEZONE` | `salon.json` `timezone` | both |
| `ALLOWED_ORIGINS` | derived from `salon.json` `network.owner_port` (`http://127.0.0.1:<port>`, `http://localhost:<port>`) | Owner |
| `OWNER_API_BASE` / `CHECKIN_API_BASE` | the loopback backend ports (`127.0.0.1:8001` / `:8000`) | Check-In / Owner |
| `CHECKIN_INTERNAL_SERVICE_TOKEN` (required), `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `OPENAI_API_KEY`, `OWNER_BOOTSTRAP_PASSWORD`, `OWNER_PASSWORD_HASH` | secrets store | Owner (the token also Check-In) |
| `EMAIL_PASSWORD` | secrets store | Check-In |
| every other setting (cookies, voice switches, `PUBLIC_BASE_URL`, `TWILIO_PHONE_NUMBER`, `SMTP_*`, `EMAIL_SENDER`, timeouts, ...) | still the process environment | |

Each app also drops, in product mode, secrets that belong to the *other* app (Check-In never holds the voice keys).
`TWILIO_PHONE_NUMBER` is deployment configuration, not a secret (it is public and shown in Salon Settings); it stays an
environment setting until the voice settings move into `salon.json`. The Twilio account SID is treated as a secret.

## 4. `config\salon.json`

Non-secret **deployment** settings only. Business data (salon name, booking hours, services) stays in the database.

```json
{
  "schema_version": 1,
  "salon_id": "salon-1a2b3c4d",
  "timezone": "America/Phoenix",
  "tier": "development",
  "network": { "kiosk_port": 8080, "owner_port": 8081 }
}
```

Validated strictly; any problem stops start-up with a message that names the file and the field:
`schema_version` must be exactly `1` (a newer file says what this build understands); `salon_id` 1-64 letters, digits,
`-` `_`; `timezone` must exist; `tier` lowercase `[a-z0-9_-]` up to 32; ports whole numbers 1024-65535, different from
each other and from the reserved loopback ports 8000/8001; unknown keys are errors (so typos cannot pass silently);
**any key that looks like a secret** (`token`, `password`, `secret`, `api_key`, `credential`, ...) is refused. The file is
read as UTF-8 (a BOM is tolerated) and limited to 64 KB.

The ports are consumed by the proxy/launcher later; the apps only use `owner_port` (allowed origins) today.

## 5. Secrets

`secrets\secrets.dat` is one **Windows DPAPI**-protected blob (JSON inside). It never contains plaintext, secret names
included. Values are written atomically, and a damaged, tampered or foreign file is refused rather than trusted.

* **Interface:** `SecretsProvider` (`get`, `names`, `set`, `delete`). `names()` never returns values; `repr()` never contains
  values. Backends: `EnvironmentSecrets` (read-only, the development path) and `DpapiSecrets` (product).
* **Scope:** machine scope by default, so the account that runs the apps need not be the account that ran the installer.
  Any process on this computer that can **read the file** could decrypt it, so the **folder permission is the
  confidentiality boundary** (section 6). `scope="user"` additionally binds it to one Windows account.
* **Not stored here:** kiosk device tokens and pairing codes (hashes in the Check-In database), owner/staff sessions, the
  owner password hash (Owner database).
* **Never** in `salon.json`, logs, the frontend, or API responses (the AI status endpoint returns yes/no flags only).
* **How the apps receive them:** at start-up `bootstrap()` places the app's own secrets in that process's environment, because
  the existing code reads `os.environ`. That keeps the code unchanged, but the values are then visible to anything that can
  inspect that process. Reading through the provider directly is a later refactor.

```powershell
python nailsystem_runtime.py secrets generate CHECKIN_INTERNAL_SERVICE_TOKEN   # random, stored, never printed
python nailsystem_runtime.py secrets set OPENAI_API_KEY                         # hidden prompt; never on the command line
python nailsystem_runtime.py secrets list                                       # names only
python nailsystem_runtime.py secrets delete OPENAI_API_KEY
python nailsystem_runtime.py check --app owner      # would this app start? prints names, sources and problems; never a value (exit 0 / 2)
```

In the Check-In repository the same tools sit inside the package: run `python app\nailsystem_runtime.py ...` and
`python app\nailsystem_backup.py ...` from `backend\`.

The secrets are shared by both apps through one file: DPAPI cannot give each app its own key on one account, so each app
simply reads only its own names. Run these as an administrator in a real install (the runtime account only has read access).

## 6. Permissions (ACLs)

Implemented as helpers (`restrict_directory`, `apply_acls`, `readable_by_everyone`, `python nailsystem_runtime.py acl-check`) using
`icacls` with well-known SIDs (so they work on any Windows language). The **installer must call `init` (or `apply_acls`) as an
administrator**; the apps themselves never change permissions.

| Folder | SYSTEM | Administrators | Runtime account | Everyone / Users / Authenticated Users |
|---|---|---|---|---|
| `NailSystem\` and below (data, backups, logs, config) | Full | Full | Modify | **none** (inheritance removed) |
| `NailSystem\secrets\` | Full | Full | **Read and execute only** | **none** |

So kiosk/browser users and other Windows accounts cannot read the databases or the secrets, a compromised app cannot rewrite its
own secrets, and nothing grants `Everyone:FullControl`. `init --runtime-sid <SID>` names the account that will run NailSystem
(default: the current one). What is **not** done by code: choosing/creating that account, per-app accounts, and auditing.

## 7. Logs

`logs\<app>\<app>.log`, rotated at 5 MB with 5 old files, plus the console. Every line is passed through a redactor:

* any loaded secret value, anywhere in the line (and tracebacks);
* credential headers and assignments: `X-Internal-Service-Token`, `X-Kiosk-Device-Token`, `X-Profile-Edit-Token`, CSRF headers,
  `Authorization` (scheme *and* credentials), `Cookie`/`Set-Cookie`, `token=`, `password=`, `api_key=`, `Bearer ...`;
* kiosk device tokens and pairing codes by shape;
* phone numbers (all but the last two digits) and e-mail addresses (`j***@example.com`).

No call audio or transcripts are stored anywhere. Application logs use customer **ids**, not names. Run uvicorn with
`--no-access-log`: request lines contain phone numbers. uvicorn's own start-up messages bypass the root logger; the launcher
will capture them under `logs\launcher\`. Development keeps plain console logging.

## 8. SQLite settings (both databases, both modes)

Applied on every connection: `busy_timeout=5000` (wait for a locked database instead of failing), `foreign_keys=ON`,
`journal_mode=WAL` (readers do not block the writer; a crash cannot corrupt the file) and `synchronous=FULL` (a committed
change survives power loss). Check-In previously did **not** enforce foreign keys; it does now, its tests run with the same
settings, and the four existing development databases were checked on copies: zero violations.

WAL adds `<db>-wal` and `<db>-shm` next to the database while it is open: **never copy a database file by hand while the app
runs**; use the backup commands. These files are git-ignored.

## 9. Backups and restore validation

`nailsystem_backup.py` makes a **live** backup with SQLite's online backup API (never a raw file copy), verifies it
(`PRAGMA integrity_check` must be `ok`, core tables present, every table readable), writes a checksum file, and only then keeps it.
A backup that fails verification is deleted. Backups are single, self-contained files (no WAL), separate per app:
`backups\owner\owner-20261013T031500Z.db` (+ `.json`), UTC, optionally `...-pre-upgrade.db`.

```powershell
cd <repo>\backend                       # Owner. Check-In: run  python app\nailsystem_backup.py ...  (same arguments)
$env:NAILSYSTEM_MODE = "product"        # or pass --db / --dir
python nailsystem_backup.py backup  --app owner [--keep 14] [--label pre-upgrade]
python nailsystem_backup.py list    --app owner
python nailsystem_backup.py verify  --app owner --file <backup>
python nailsystem_backup.py prune   --app owner --keep 14
python nailsystem_backup.py preflight --app owner --file <backup>   # restore advice only
```

* **Retention:** newest 14 regular backups and newest 3 `pre-upgrade` backups are kept; nothing else in the folder is touched.
* **Scheduling:** none yet. The launcher will call `create_backup()` nightly and before every upgrade (`label="pre-upgrade"`).
* **Restore validation:** `restore_preflight()` opens the backup, runs the integrity check, requires the core tables, checks the checksum
  file, rejects the wrong app's backup, warns about rows that point at missing records, and reports whether the live database
  looks in use (leftover `-wal`/`-shm`, or locked). It changes nothing. **Restoring is never automatic.**
* **Manual recovery** (until the launcher does this): stop NailSystem; `backup --label before-restore` the current database if it still
  opens; delete `<db>-wal` and `<db>-shm`; copy the verified backup over the database file; start NailSystem (the additive
  migrations bring an older backup up to date).

## 10. Exact commands

**Development (unchanged; nothing installed anywhere):**
see `deploy/lan-poc/README.md` for the three processes. Tests:

```powershell
# Owner (from backend\)                      # Check-In (from backend\)
venv\Scripts\python.exe -m pytest Test-main.py test_nailsystem_runtime.py test_nailsystem_backup.py test_runtime_wiring.py -q
venv\Scripts\python.exe -m pytest app -q
```

**Trying the installed layout without touching ProgramData** (any empty folder outside a repository):

```powershell
$env:NAILSYSTEM_HOME = "C:\Temp\NailSystemTest"
python nailsystem_runtime.py init --no-acl                         # folders + a default salon.json (never overwrites)
python nailsystem_runtime.py secrets generate CHECKIN_INTERNAL_SERVICE_TOKEN
$env:NAILSYSTEM_MODE = "product"                                   # now start the app as usual; it uses that folder
venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8001 --no-access-log
```

Do not also set `DATABASE_URL` or the token: product mode ignores them (and says so in the log).

## 11. Uninstall and upgrades

* **Uninstall removes Program Files only and preserves ProgramData by default** (customers, appointments and backups are the
  salon's records). Deleting data must be a separate, explicit, confirmed choice.
* An upgrade replaces Program Files, takes a `pre-upgrade` backup of both databases, starts the apps (additive, repeatable
  migrations), and rolls back by restoring that backup if start-up fails (launcher/installer phase).

## 11b. Health and the launcher

Both backends answer `GET /health` on loopback with `{"status": "ok", "app": "owner|checkin", "version": ..., "contract_version": 1}`
(or `503 {"status": "unavailable"}` if the database does not answer): no paths, settings, tokens or counts, and the reverse proxy never
forwards it. The Windows launcher (the `Nail-System-installer-git` repository) uses it, runs the `check` command above before it
starts anything, and passes each app only its own settings; in product mode it never holds a secret itself.

## 12. Not done in this phase

Installer, launcher/tray app, auto-start, Windows service, QR pairing, HTTPS, scheduled backups, automatic restore, per-app
accounts, moving the voice/SMTP settings into `salon.json`, reading secrets through the provider instead of `os.environ`,
shared (multi-process) rate limiting, and cloud/multi-salon.
