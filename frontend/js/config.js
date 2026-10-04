// config.js: Settings and constant lists
const API_BASE = "http://127.0.0.1:8001";

const CHECKIN_API_BASE = "http://127.0.0.1:8000";

const SCHEDULE_DAYS = [
    { key: "monday", label: "Monday", short: "Mon" },
    { key: "tuesday", label: "Tuesday", short: "Tue" },
    { key: "wednesday", label: "Wednesday", short: "Wed" },
    { key: "thursday", label: "Thursday", short: "Thu" },
    { key: "friday", label: "Friday", short: "Fri" },
    { key: "saturday", label: "Saturday", short: "Sat" },
    { key: "sunday", label: "Sunday", short: "Sun" },
];

const DEFAULT_SPECIALTIES = [
    "Manicure / Pedicure",
    "Acrylic",
    "Gel",
    "Dip Powder",
    "Builder / Hard Gel",
    "Nail Art",
    "Nail Repair / Removal",
    "Waxing",
    "Facial",
];

const DEFAULT_APPOINTMENT_SERVICES = [
    "Acrylic Full Set",
    "Acrylic Fill",
    "Gel Full Set",
    "Gel Fill",
    "Dip Powder",
    "Pink and White",
    "Ombre Nails",
    "Builder Gel",
    "Classic Manicure",
    "Gel Manicure",
    "Deluxe Manicure",
    "Classic Pedicure",
    "Deluxe Pedicure",
    "Spa Pedicure",
    "Jelly Pedicure",
    "Polish Change - Hands",
    "Polish Change - Feet",
    "Nail Repair",
    "Nail Removal",
    "French Tip",
    "Nail Art",
    "Chrome / Cat Eye",
    "Paraffin Treatment",
    "Waxing - Eyebrows",
    "Waxing - Lip",
    "Waxing - Chin",
    "Facial",
];

const REMOVED_SPECIALTIES_STORAGE_KEY = "ownerRemovedSpecialties";

const TECH_UNAVAILABLE_TODAY_STORAGE_KEY = "ownerTechUnavailableToday";

// MUST stay identical to SERVICE_TO_SPECIALTIES in backend/crud.py.
// The backend is the one that finally accepts or rejects an assignment; this copy only
// lets the "Assign Preferred" / "Reassign" dropdown hide technicians the backend would refuse.
// If you edit one list, edit the other. (A service matches when its text CONTAINS the key.)
const SERVICE_TO_SPECIALTIES = {
    "manicure": ["manicure / pedicure"],
    "pedicure": ["manicure / pedicure"],
    "classic manicure": ["manicure / pedicure"],
    "deluxe manicure": ["manicure / pedicure"],
    "classic pedicure": ["manicure / pedicure"],
    "deluxe pedicure": ["manicure / pedicure"],
    "spa pedicure": ["manicure / pedicure"],
    "jelly pedicure": ["manicure / pedicure"],
    "gel manicure": ["manicure / pedicure", "gel"],
    "gel pedicure": ["manicure / pedicure", "gel"],
    "paraffin treatment": ["manicure / pedicure"],
    "polish change": ["manicure / pedicure"],
    "acrylic": ["acrylic"],
    "acrylic full set": ["acrylic"],
    "acrylic fill": ["acrylic"],
    "pink and white": ["acrylic", "nail art"],
    "nail repair": ["nail repair / removal", "acrylic", "gel", "builder / hard gel"],
    "dipping": ["dip powder"],
    "dip powder": ["dip powder"],
    "gel full set": ["gel"],
    "gel fill": ["gel"],
    "hard gel": ["builder / hard gel", "gel"],
    "builder gel": ["builder / hard gel"],
    "gel x": ["gel"],
    "nail art": ["nail art"],
    "french tip": ["nail art"],
    "ombre": ["nail art"],
    "chrome": ["nail art"],
    "cat eye": ["nail art"],
    "waxing": ["waxing"],
    "eyebrows": ["waxing"],
    "chin": ["waxing"],
    "lip": ["waxing"],
    "facial": ["facial"],
    "removal": ["nail repair / removal", "acrylic", "dip powder", "gel", "builder / hard gel"],
};

// ---- Booked technicians ----------------------------------------------------------------------
// Auto Assign and customers who booked a technician (named on today's appointment):
//   true  = if that technician is working and qualified but busy right now, the customer waits for them
//   false = give the customer to someone else straight away
const WAIT_FOR_BOOKED_TECHNICIAN = true;
