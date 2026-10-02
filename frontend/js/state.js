// state.js: Data kept in memory while the page is open
let technicians = [];

// Active technicians only: used for dropdowns, calendar columns, and assignment.
let techniciansRaw = [];

// Every technician including deactivated ones: used only to look up names on past
// checkouts and income lines (the backend deactivates, rather than deletes, anyone with history).
let techniciansAll = [];

let appointments = [];

let selectedDate = new Date();

let confirmResolve = null;

let activeAppointment = null;

// The "Select Technician" popup is shared by two actions:
//   "assign"   = pick a preferred technician for a customer in the check-in queue
//   "reassign" = move a customer who is already assigned to a different technician
let preferredTechModalMode = "assign";

let pendingPreferredCheckinItem = null;

let pendingReassignTurn = null;

let liveCheckins = [];

let todayTurns = [];

// What the history card on the Customer List is currently SHOWING (today, all, or a date range).
let checkoutHistory = [];

// Today's checkouts only. The waiting queue uses this to hide customers who already paid, so it
// is never affected by what the history card is showing.
let todayCheckouts = [];

// Which view of the history card the user chose. It is only changed by the user (or by leaving and
// re-opening the screen), never by the automatic refresh.
let historyView = { mode: "today", bounds: null, label: "today" };

let techIncomeDateSummaries = [];

let techIncomeDateLabel = "";

let techIncomeRangeSummaries = [];

let techIncomeRangeLabel = "";

let inventoryItems = [];