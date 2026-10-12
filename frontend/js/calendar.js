// calendar.js: Calendar grid

function formatDateHeader(date) {
    return date.toLocaleDateString([], {
        weekday: "long",
        month: "short",
        day: "2-digit",
        year: "numeric",
    });
}

function setDateLabel() {
    dateLabel.textContent = formatDateHeader(selectedDate);
}

function formatHourLabel(hour24) {
    const suffix = hour24 >= 12 ? "pm" : "am";
    const display = hour24 % 12 === 0 ? 12 : hour24 % 12;
    return `${display}:00<br><span>${suffix}</span>`;
}

function getAvatarClass(index) {
    const classes = ["coral", "gold", "teal", "blue", "pink", "plum", "mint", "amber", "indigo", "rose"];
    return classes[index % classes.length];
}

// The salon's wall clock, independent of the browser's timezone.
function getSalonNowParts(now = new Date()) {
    const parts = {};
    new Intl.DateTimeFormat("en-US", {
        timeZone: SALON_TIMEZONE, hourCycle: "h23",
        year: "numeric", month: "numeric", day: "numeric", hour: "numeric", minute: "numeric",
    }).formatToParts(now).forEach((part) => { if (part.type !== "literal") parts[part.type] = Number(part.value); });
    return parts;
}

// "Today" for the calendar: the salon's calendar date, as a local-midnight Date like selectedDate.
function getSalonToday(now = new Date()) {
    const parts = getSalonNowParts(now);
    return new Date(parts.year, parts.month - 1, parts.day);
}

// null when the line must be hidden (another day, or outside the displayed hours).
// fraction is the position inside the whole displayed grid, so it is minute-accurate: within an
// hour it advances by minute / 60 (12:30 sits halfway between the 12:00 and 1:00 rows).
function computeCurrentTimeLine(selected, now, startHour, totalHours) {
    const parts = getSalonNowParts(now);
    if (selected.getFullYear() !== parts.year || selected.getMonth() + 1 !== parts.month || selected.getDate() !== parts.day) return null;
    const minutesFromStart = parts.hour * 60 + parts.minute - startHour * 60;
    const totalMinutes = totalHours * 60;
    if (minutesFromStart < 0 || minutesFromStart >= totalMinutes) return null;
    const hour12 = parts.hour % 12 === 0 ? 12 : parts.hour % 12;
    return {
        fraction: minutesFromStart / totalMinutes,
        percentWithinHour: (parts.minute / 60) * 100,
        label: `${hour12}:${String(parts.minute).padStart(2, "0")} ${parts.hour >= 12 ? "PM" : "AM"}`,
    };
}

// The calendar shows the span between the earliest opening and the latest closing of the week
// (whole hours), so the grid height does not change from day to day. Without hours (not loaded yet)
// it falls back to the old 9:00-21:00.
function timeToMinutes(value) {
    const [hours, minutes] = String(value).split(":");
    return Number(hours) * 60 + Number(minutes || 0);
}

function getCalendarWindow() {
    const open = (businessHours || []).filter((day) => !day.is_closed && day.opens_at && day.closes_at);
    if (!open.length) return { startHour: 9, totalHours: 12 };
    const startHour = Math.floor(Math.min(...open.map((day) => timeToMinutes(day.opens_at))) / 60);
    const endHour = Math.ceil(Math.max(...open.map((day) => timeToMinutes(day.closes_at))) / 60);
    return { startHour, totalHours: Math.max(1, endHour - startHour) };
}

// Hours for one date (backend weekday numbering: Monday = 0), or null when unknown.
function getBookableHours(date) {
    const day = (businessHours || []).find((item) => item.day_of_week === (date.getDay() + 6) % 7);
    if (!day) return null;
    if (day.is_closed || !day.opens_at || !day.closes_at) return { closed: true };
    return { closed: false, opensMinutes: timeToMinutes(day.opens_at), closesMinutes: timeToMinutes(day.closes_at) };
}

// Shaded bands for the part of the displayed span that cannot be booked that day.
function buildClosedBands(date, startHour, totalHours) {
    const hours = getBookableHours(date);
    if (!hours) return "";
    const spanStart = startHour * 60;
    const spanMinutes = totalHours * 60;
    const band = (fromMinutes, toMinutes, label) => {
        if (toMinutes <= fromMinutes) return "";
        const top = ((fromMinutes - spanStart) / spanMinutes) * 100;
        const height = ((toMinutes - fromMinutes) / spanMinutes) * 100;
        return `<div class="closed-band" title="${label}" style="top:${top.toFixed(4)}%; height:${height.toFixed(4)}%;"><span>${label}</span></div>`;
    };
    if (hours.closed) return band(spanStart, spanStart + spanMinutes, "Salon closed");
    return band(spanStart, hours.opensMinutes, "Before opening") + band(hours.closesMinutes, spanStart + spanMinutes, "After closing");
}

function showCalendarLoading() {
    calendarWrapper.innerHTML = `<div class="empty-state">Loading calendar&hellip;</div>`;
}

// Only reachable when the calendar has never loaded. Says only what is known: a session problem, a
// server that could not be reached, or an ordinary failure.
function describeCalendarLoadError(error) {
    const text = String((error && error.message) || "");
    if (/session|authenticat|owner access/i.test(text)) return "Your session needs to be renewed. Please reload the page.";
    if (/could not connect/i.test(text)) return "Could not load calendar data. The server could not be reached; please try again.";
    return "Could not load calendar data. Please try again.";
}

function showCalendarError(error) {
    calendarWrapper.innerHTML = `<div class="empty-state">${escapeHtml(describeCalendarLoadError(error))}
      <div><button type="button" class="ghost-btn" id="calendarRetryBtn">Try again</button></div></div>`;
    document.getElementById("calendarRetryBtn")?.addEventListener("click", () => refreshDashboardInBackground());
}

// Grows the displayed span (whole hours) so every appointment/turn shown that day sits at its true
// time. An item is drawn one row tall, so it counts for the hour after its start as well.
function extendWindowForItems(window, appointmentsToday, turnsToday) {
    let startMinutes = window.startHour * 60;
    let endMinutes = (window.startHour + window.totalHours) * 60;
    const include = (value) => {
        const when = new Date(value);
        if (Number.isNaN(when.getTime())) return;
        const minutes = when.getHours() * 60 + when.getMinutes();
        startMinutes = Math.min(startMinutes, Math.floor(minutes / 60) * 60);
        endMinutes = Math.max(endMinutes, Math.ceil((minutes + 60) / 60) * 60);
    };
    appointmentsToday.forEach((appt) => include(appt.appointment_time));
    turnsToday.forEach((turn) => include(turn.created_at));
    endMinutes = Math.min(endMinutes, 24 * 60);
    return { startHour: startMinutes / 60, totalHours: Math.max(1, (endMinutes - startMinutes) / 60) };
}

function renderCalendar() {
    setDateLabel();

    // Booking hours decide the default span (and what is shaded as not bookable). Appointments and
    // active turns outside them (a customer running late, a service that overran closing) still show
    // at their true time: the span grows to include them instead of pinning them to the grid edge.
    const dailyAppointments = appointments.filter((appt) => {
        const dt = new Date(appt.appointment_time);
        return appt.status !== "cancelled" && sameDay(dt, selectedDate);
    });
    const activeTurns = sameDay(selectedDate, getSalonToday())
        ? todayTurns.filter((turn) => ["assigned", "in_service"].includes(turn.status))
        : [];
    const { startHour, totalHours } = extendWindowForItems(getCalendarWindow(), dailyAppointments, activeTurns);
    const rowHeight = 90;
    const totalHeight = totalHours * rowHeight;
    const staffCount = techniciansRaw.length > 0 ? techniciansRaw.length : 5;

    const staffRow =
        techniciansRaw.length > 0
            ? `
        <div class="staff-row" style="--staff-count:${staffCount}">
          <div class="time-spacer"></div>
          ${techniciansRaw
                .map(
                    (tech, index) => `
                <div class="staff-col">
                  <div class="staff-avatar ${getAvatarClass(index)}">${escapeHtml(getInitials(tech.full_name))}</div>
                  <span>${escapeHtml(tech.full_name)}</span>
                </div>
              `
                )
                .join("")}
        </div>
      `
            : "";

    // One label per hour row, plus one for the boundary under the last row (the closing hour): a 9-6 day
    // reads 9 am ... 5 pm, 6 pm, so the calendar visibly ends where booking ends.
    const times = Array.from({ length: totalHours }, (_, i) => {
        return `<div>${formatHourLabel(startHour + i)}</div>`;
    }).join("") + `<div class="times-end">${formatHourLabel(startHour + totalHours)}</div>`;

    const appointmentBlocks = dailyAppointments
        .map((appt, index) => {
            const dt = new Date(appt.appointment_time);
            const minutes = dt.getHours() * 60 + dt.getMinutes();
            const baseMinutes = startHour * 60;
            let top = ((minutes - baseMinutes) / 60) * rowHeight;

            if (top < 0) top = 0;
            if (top > totalHeight - 86) top = totalHeight - 86;

            let columnIndex = index % staffCount;
            const calendarTechnicianId = appt.technician_id || appt.preferred_technician_id;
            if (calendarTechnicianId && techniciansRaw.length) {
                const foundIndex = techniciansRaw.findIndex(
                    (t) => Number(t.id) === Number(calendarTechnicianId)
                );
                if (foundIndex >= 0) columnIndex = foundIndex;
            }

            const leftPercent = (100 / staffCount) * columnIndex;

            const timeText = dt.toLocaleTimeString([], {
                hour: "numeric",
                minute: "2-digit",
            });

            const categoryText = appt.service_category || appt.service_name || "Appointment";

            return `
        <div class="appointment color-${columnIndex % 5}" data-id="${appt.id}" style="left:${leftPercent}%; top:${top}px; height:86px;">
          <strong>${timeText}</strong>
          <span>${escapeHtml(appt.customer_name)}</span>
          <small>${escapeHtml(categoryText)}</small>
        </div>
      `;
        })
        .join("");

    const turnBlocks = activeTurns
        .map((turn) => {
            if (!turn.technician_id || !techniciansRaw.length) return "";

            const foundIndex = techniciansRaw.findIndex(
                (t) => Number(t.id) === Number(turn.technician_id)
            );
            if (foundIndex < 0) return "";

            const leftPercent = (100 / staffCount) * foundIndex;
            const created = new Date(turn.created_at);
            const minutes = created.getHours() * 60 + created.getMinutes();
            const baseMinutes = startHour * 60;
            let top = ((minutes - baseMinutes) / 60) * rowHeight;

            if (top < 0) top = 0;
            if (top > totalHeight - 74) top = totalHeight - 74;

            return `
        <div class="appointment color-${foundIndex % 5} live-turn-block ${turn.status === "in_service" ? "live-turn-in-service" : "live-turn-assigned"}"
             style="left:${leftPercent}%; top:${top}px; height:74px;">
          <strong>${turn.status === "in_service" ? "In Service" : "Assigned"}</strong>
          <span>${escapeHtml(turn.customer_name)}</span>
          <small>${escapeHtml(turn.service_name)}</small>
        </div>
      `;
        })
        .join("");

    // Rebuilt with the grid on every render, so there is never more than one. Positioned as a share of
    // the grid height (not pixels), so it stays right if row height, column count or width change.
    const timeLine = computeCurrentTimeLine(selectedDate, new Date(), startHour, totalHours);
    const currentTimeLine = timeLine
        ? `
        <div class="current-time-line" data-time-label="${timeLine.label}" style="top:${(timeLine.fraction * 100).toFixed(4)}%;">
          <span class="current-time-dot"></span>
          <span class="current-time-label">${timeLine.label}</span>
        </div>
      `
        : "";

    calendarWrapper.innerHTML = `
    <div class="calendar-board">
      ${staffRow}
      <div class="calendar-grid" style="grid-template-columns: 90px 1fr;">
        <div class="times" style="grid-template-rows: repeat(${totalHours}, ${rowHeight}px) 56px;">${times}</div>
        <div class="grid" style="height:${totalHeight}px; --staff-count:${staffCount};">
          <div class="grid-lines" style="background-size: calc(100% / ${staffCount}) 100%, 100% 90px;"></div>
          <div class="grid-end-line"></div>
          ${buildClosedBands(selectedDate, startHour, totalHours)}
          ${currentTimeLine}
          ${appointmentBlocks}
          ${turnBlocks}
        </div>
      </div>
    </div>
  `;

    calendarWrapper.querySelectorAll(".appointment[data-id]").forEach((block) => {
        block.addEventListener("click", () => {
            const apptId = Number(block.dataset.id);
            const appt = appointments.find((item) => item.id === apptId);
            if (appt) openAppointmentModal(appt);
        });
    });
}
