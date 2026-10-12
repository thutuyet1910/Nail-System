// dashboard-load.js: loading the dashboard data without ever blanking a calendar that already worked.
//
//   INITIAL LOAD   nothing has loaded yet: a neutral "Loading calendar..." state, then either the
//                  calendar or an accurate error (only here can an error replace the calendar)
//   LAST GOOD DATA once appointments have loaded, they stay in memory (navigation never clears them)
//   REFRESH        runs in the background; a failure keeps the last good calendar on screen and the
//                  next poll or navigation retries; no error text, no flicker
//
// Calendar-critical data (technicians, appointments, business hours) is fetched first and drawn as
// soon as it arrives; the rest of the dashboard (services, queue, history) fills in afterwards.

let backgroundRefreshInFlight = null;

async function loadAll() {
    installFourDigitYearGuard();
    if (!calendarHasLoaded) showCalendarLoading();
    checkApi();  // only updates the status dot: never awaited, never able to blank the calendar

    let firstFailure = null;
    const attempt = async (step) => {
        try {
            await step();
            return true;
        } catch (error) {
            firstFailure = firstFailure || error;
            console.warn("Dashboard refresh step failed:", error);
            return false;
        }
    };

    await attempt(async () => {
        if (!ownerLocked) {
            await loadTechnicians();  // management cards: owner only
        } else {
            await loadTechniciansRaw();  // staff: names and availability only
            populateAppointmentTechnicianDropdown();
        }
    });
    const appointmentsLoaded = await attempt(loadAppointments);
    await attempt(loadBusinessHours);
    if (appointmentsLoaded) calendarHasLoaded = true;
    if (calendarHasLoaded) {
        renderCalendar();  // from fresh data, or from the last good data if this refresh failed
    } else {
        showCalendarError(firstFailure);
    }

    await attempt(loadBookingServices);
    await attempt(loadSalonName);
    syncDefaultSpecialtiesToFilter();
    await attempt(loadTodayTurns);
    await attempt(loadCheckoutHistory);
    await attempt(loadLiveCheckinQueue);
    if (calendarHasLoaded) renderCalendar();  // today's live turns have arrived
}

// Opening the calendar again is instant: the screen switches first and draws what is already in
// memory; the refresh then runs in the background (one at a time).
function refreshDashboardInBackground() {
    if (!backgroundRefreshInFlight) {
        backgroundRefreshInFlight = loadAll().catch(() => {}).finally(() => { backgroundRefreshInFlight = null; });
    }
    return backgroundRefreshInFlight;
}

function returnToCalendar() {
    showView("calendar");
    if (calendarHasLoaded) renderCalendar();
    refreshDashboardInBackground();
}
