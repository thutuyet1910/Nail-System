// utils.js: Small helpers: money, dates, phone, escaping, fetchJson

function formatMoney(value) {
    return `$${Number(value || 0).toFixed(2)}`;
}

function getLocalDateKey(value = new Date()) {
    return formatDateInputValue(value);
}

function limitDateYearValue(input) {
    if (!input?.value) return;
    const match = input.value.match(/^(\d{5,})(-\d{2}-\d{2}(?:T\d{2}:\d{2})?)$/);
    if (match) {
        input.value = `${match[1].slice(0, 4)}${match[2]}`;
    }
}

function formatMaskedDate(value) {
    const digits = String(value || "").replace(/\D/g, "").slice(0, 8);
    if (digits.length <= 2) return digits;
    if (digits.length <= 4) return `${digits.slice(0, 2)}-${digits.slice(2)}`;
    return `${digits.slice(0, 2)}-${digits.slice(2, 4)}-${digits.slice(4)}`;
}

function formatMaskedDateTime(value) {
    const digits = String(value || "").replace(/\D/g, "").slice(0, 12);
    const datePart = formatMaskedDate(digits.slice(0, 8));
    if (digits.length <= 8) return datePart;
    if (digits.length <= 10) return `${datePart} ${digits.slice(8)}`;
    return `${datePart} ${digits.slice(8, 10)}:${digits.slice(10)}`;
}

function formatMaskedYear(value) {
    return String(value || "").replace(/\D/g, "").slice(0, 4);
}

function displayDateToISO(value) {
    if (/^\d{4}-\d{2}-\d{2}$/.test(value || "")) return value;
    if (!/^\d{2}-\d{2}-\d{4}$/.test(value || "")) return "";
    const [monthText, dayText, yearText] = value.split("-");
    return `${yearText}-${monthText}-${dayText}`;
}

function isoToDisplayDate(value) {
    const isoValue = formatDateInputValue(value);
    if (!/^\d{4}-\d{2}-\d{2}$/.test(isoValue)) return "";
    const [year, month, day] = isoValue.split("-");
    return `${month}-${day}-${year}`;
}

function isValidISODate(value) {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(value || "")) return false;
    const [yearText, monthText, dayText] = value.split("-");
    const year = Number(yearText);
    const month = Number(monthText);
    const day = Number(dayText);
    const date = new Date(year, month - 1, day);
    return (
        date.getFullYear() === year &&
        date.getMonth() + 1 === month &&
        date.getDate() === day
    );
}

function isValidDateText(value) {
    return isValidISODate(displayDateToISO(value));
}

function displayDateTimeToApi(value) {
    const match = String(value || "").match(/^(\d{2}-\d{2}-\d{4})\s+(\d{2}):(\d{2})$/);
    if (!match) return "";
    const isoDate = displayDateToISO(match[1]);
    const hours = Number(match[2]);
    const minutes = Number(match[3]);
    if (!isValidISODate(isoDate) || hours > 23 || minutes > 59) return "";
    return `${isoDate}T${match[2]}:${match[3]}`;
}

function getDateOffAvailability(startDisplay, endDisplay) {
    const startISO = displayDateToISO(startDisplay);
    const endISO = displayDateToISO(endDisplay);
    if (!startISO || !endISO) return "";
    return `date off: ${startISO} to ${endISO}`;
}

function parseDateOffAvailability(value) {
    const match = String(value || "").match(/^date off:\s*(\d{4}-\d{2}-\d{2})\s+to\s+(\d{4}-\d{2}-\d{2})$/i);
    if (!match) {
        return { start: "", end: "" };
    }
    return {
        start: isoToDisplayDate(match[1]),
        end: isoToDisplayDate(match[2]),
    };
}

function isoDateTimeToDisplay(value) {
    if (!value) return "";
    const d = new Date(value);
    if (Number.isNaN(d.getTime())) return "";
    const dateText = isoToDisplayDate(d);
    const hours = String(d.getHours()).padStart(2, "0");
    const mins = String(d.getMinutes()).padStart(2, "0");
    return `${dateText} ${hours}:${mins}`;
}

function installFourDigitYearGuard() {
    document.querySelectorAll('input[data-date-mask="true"], input[data-year-mask="true"], input[data-datetime-mask="true"], input[type="date"], input[type="datetime-local"]').forEach((input) => {
        if (input.dataset.yearGuardInstalled === "true") return;
        input.dataset.yearGuardInstalled = "true";

        if (input.dataset.yearMask === "true" || input.dataset.dateMask === "true" || input.dataset.datetimeMask === "true") {
            input.type = "text";
            input.setAttribute("inputmode", "numeric");
            const applyMask = () => {
                const yearOnly = input.dataset.yearMask === "true";
                const dateTime = input.dataset.datetimeMask === "true";
                input.setAttribute("maxlength", yearOnly ? "4" : dateTime ? "16" : "10");
                input.value = yearOnly ? formatMaskedYear(input.value) : dateTime ? formatMaskedDateTime(input.value) : formatMaskedDate(input.value);
            };
            input.addEventListener("input", applyMask);
            input.addEventListener("change", applyMask);
            return;
        }

        input.setAttribute("maxlength", input.type === "datetime-local" ? "16" : "10");
        if (!input.min) input.min = "1900-01-01";
        if (!input.max) input.max = input.type === "datetime-local" ? "2100-12-31T23:59" : "2100-12-31";

        input.addEventListener("input", () => limitDateYearValue(input));
        input.addEventListener("change", () => limitDateYearValue(input));
    });
}

function escapeHtml(value) {
    return String(value ?? "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

function formatDateTime(value) {
    if (!value) return "-";
    const d = new Date(value);
    if (Number.isNaN(d.getTime())) return "-";
    return d.toLocaleString([], {
        year: "numeric",
        month: "short",
        day: "numeric",
        hour: "numeric",
        minute: "2-digit"
    });
}

function sameDay(a, b) {
    return (
        a.getFullYear() === b.getFullYear() &&
        a.getMonth() === b.getMonth() &&
        a.getDate() === b.getDate()
    );
}

function getInitials(name) {
    return (name || "")
        .split(" ")
        .filter(Boolean)
        .map((word) => word[0])
        .join("")
        .slice(0, 2)
        .toUpperCase();
}

function formatPhoneInput(value) {
    const digits = value.replace(/\D/g, "").slice(0, 10);
    if (digits.length <= 3) return digits;
    if (digits.length <= 6) return `(${digits.slice(0, 3)}) ${digits.slice(3)}`;
    return `(${digits.slice(0, 3)}) ${digits.slice(3, 6)}-${digits.slice(6)}`;
}

function toDatetimeLocalValue(value) {
    return isoDateTimeToDisplay(value);
}

function checkApi() {
    return fetch(`${API_BASE}/`)
        .then((res) => {
            if (!res.ok) throw new Error();
            apiDot.className = "dot online";
            apiText.textContent = "Backend connected";
        })
        .catch(() => {
            apiDot.className = "dot offline";
            apiText.textContent = "Backend offline";
        });
}

async function fetchJson(url, options = {}) {
    let response;

    try {
        response = await fetch(url, {
            headers: { "Content-Type": "application/json" },
            ...options,
        });
    } catch (error) {
        throw new Error(`Could not connect to backend: ${url}`);
    }

    if (!response.ok) {
        let message = "Request failed";
        try {
            const err = await response.clone().json();
            message = Array.isArray(err.detail)
                ? err.detail.map((e) => String(e.msg).replace(/^Value error, /, "")).join("\n")
                : err.detail || message;
        } catch {
            message = (await response.text()) || message;
        }
        throw new Error(message);
    }

    if (response.status === 204) return null;
    return response.json();
}

function formatDateInputValue(value) {
    if (!value) return "";
    if (typeof value === "string" && /^\d{4}-\d{2}-\d{2}$/.test(value)) {
        return value;
    }

    const d = new Date(value);
    if (Number.isNaN(d.getTime())) return "";

    const year = d.getFullYear();
    const month = String(d.getMonth() + 1).padStart(2, "0");
    const day = String(d.getDate()).padStart(2, "0");

    return `${year}-${month}-${day}`;
}
