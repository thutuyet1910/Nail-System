// calendar-refresh.js: pick up appointments created elsewhere (phone receptionist, another session)
// while the calendar is open. Driven by the existing 5-second dashboard timer in main.js; it only
// fetches while the calendar is visible and a staff or owner session is active, and only re-renders
// on a change.

async function refreshAppointmentsIfChanged() {
    if (!appSessionReady() || !calendarView?.classList.contains("active-view")) return false;
    try {
        const fresh = await fetchJson(`${API_BASE}/appointments`);
        if (!Array.isArray(fresh)) return false;
        // unchanged data needs no redraw, unless the calendar is still showing "loading"/an error
        if (calendarHasLoaded && JSON.stringify(fresh) === JSON.stringify(appointments)) return false;
        appointments = fresh;
        calendarHasLoaded = true;
        renderCalendar();  // rebuilds the grid from scratch (no duplicate cards); selectedDate is untouched
        return true;
    } catch (error) {
        return false;  // a failed poll is silent; the next tick retries
    }
}
