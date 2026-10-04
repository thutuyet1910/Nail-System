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

function renderCalendar() {
    setDateLabel();

    const startHour = 9;
    const totalHours = 12;
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

    const times = Array.from({ length: totalHours }, (_, i) => {
        return `<div>${formatHourLabel(startHour + i)}</div>`;
    }).join("");

    const dailyAppointments = appointments.filter((appt) => {
        const dt = new Date(appt.appointment_time);
        return appt.status !== "cancelled" && sameDay(dt, selectedDate);
    });

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

    const activeTurns = sameDay(selectedDate, new Date())
        ? todayTurns.filter((turn) => ["assigned", "in_service"].includes(turn.status))
        : [];

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

    let currentTimeLine = "";
    const now = new Date();

    if (sameDay(selectedDate, now)) {
        const nowMinutes = now.getHours() * 60 + now.getMinutes();
        const baseMinutes = startHour * 60;
        const minutesFromStart = nowMinutes - baseMinutes;

        if (minutesFromStart >= 0 && minutesFromStart <= totalHours * 60) {
            const top = (minutesFromStart / 60) * rowHeight;
            currentTimeLine = `
        <div class="current-time-line" style="top:${top}px;">
          <span class="current-time-dot"></span>
        </div>
      `;
        }
    }

    calendarWrapper.innerHTML = `
    <div class="calendar-board">
      ${staffRow}
      <div class="calendar-grid" style="grid-template-columns: 90px 1fr;">
        <div class="times">${times}</div>
        <div class="grid" style="height:${totalHeight}px; --staff-count:${staffCount};">
          <div class="grid-lines" style="background-size: calc(100% / ${staffCount}) 100%, 100% 90px;"></div>
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
