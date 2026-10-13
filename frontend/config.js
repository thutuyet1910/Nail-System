// config.js: where the kiosk finds its backend.
// Same-origin on purpose: the page is served by the local reverse proxy, which forwards /api/checkin/*
// to the Check-In backend. No host, IP address or port is hard-coded here, so the tablet works at
// whatever address it opened the page from. (See deploy/lan-poc/README.md.)
const API_BASE = "/api/checkin";
