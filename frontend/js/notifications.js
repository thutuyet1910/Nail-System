let lastUnreadCount = null;

function formatUnreadBadge(count) {
    return count > 99 ? "99+" : String(count);
}

function setUnreadBadges(count) {
    const text = formatUnreadBadge(count);
    if (floatingNotificationBadge) {
        floatingNotificationBadge.textContent = text;
        floatingNotificationBadge.classList.toggle("hidden", !count);
    }
    floatingNotificationBtn?.setAttribute("aria-label", count ? `Notifications, ${text} unread` : "Notifications, none unread");
    lastUnreadCount = count;
}

async function loadNotifications() {
    if (!ownerAuthenticated) return;
    try {
        ownerNotifications = await fetchJson(`${API_BASE}/notifications?limit=50`);
        const count = await fetchJson(`${API_BASE}/notifications/unread-count`);
        setUnreadBadges(count.unread_count || 0);
        renderNotifications();
    } catch (error) {
        console.error("Failed to load notifications:", error);
    }
}

// Called from the existing 5s dashboard timer: cheap count check, full reload only when it changed.
async function refreshNotificationCount() {
    if (!ownerAuthenticated) return;
    try {
        const count = (await fetchJson(`${API_BASE}/notifications/unread-count`)).unread_count || 0;
        if (count !== lastUnreadCount) await loadNotifications();
    } catch (error) {
        console.error("Failed to refresh notification count:", error);
    }
}

function setNotificationsPanelOpen(open) {
    notificationsPanel?.classList.toggle("hidden", !open);
    floatingNotificationBtn?.setAttribute("aria-expanded", String(open));
}

async function openNotificationsPanel() {
    if (!(await requireOwner())) return;
    await loadNotifications();
    setNotificationsPanelOpen(true);
}

function notificationPhone(item) {
    const phone = item.metadata_json && item.metadata_json.caller_phone;
    return typeof phone === "string" ? phone : "";
}

function renderNotifications() {
    if (!notificationsList) return;
    if (!ownerNotifications.length) {
        notificationsList.innerHTML = `<p class="notification-empty">No notifications.</p>`;
        return;
    }
    notificationsList.innerHTML = ownerNotifications.map((item) => `
      <button type="button" class="notification-row ${item.read_at ? "read" : "unread"}" data-notification-id="${item.id}">
        <span class="notification-severity ${escapeHtml(item.severity)}">${escapeHtml(item.severity)}</span>
        <strong>${escapeHtml(item.title)}</strong>
        <span>${escapeHtml(item.message)}</span>
        ${notificationPhone(item) ? `<small class="notification-phone">${escapeHtml(notificationPhone(item))}</small>` : ""}
        <small>${formatDateTime(item.created_at)}${item.read_at ? "" : " · Unread"}</small>
      </button>`).join("");
    notificationsList.querySelectorAll("[data-notification-id]").forEach((button) => {
        button.addEventListener("click", async () => {
            await fetchJson(`${API_BASE}/notifications/${button.dataset.notificationId}/read`, { method: "POST" });
            await loadNotifications();
        });
    });
}

floatingNotificationBtn?.addEventListener("click", () => {
    if (notificationsPanel?.classList.contains("hidden")) openNotificationsPanel();
    else setNotificationsPanelOpen(false);
});

closeNotifications?.addEventListener("click", () => setNotificationsPanelOpen(false));

document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && notificationsPanel && !notificationsPanel.classList.contains("hidden")) {
        setNotificationsPanelOpen(false);
        floatingNotificationBtn?.focus();
    }
});

document.addEventListener("click", (event) => {
    if (!notificationsPanel || notificationsPanel.classList.contains("hidden")) return;
    if (notificationsPanel.contains(event.target) || floatingNotificationBtn?.contains(event.target)) return;
    setNotificationsPanelOpen(false);
});

markAllNotificationsRead?.addEventListener("click", async () => {
    await fetchJson(`${API_BASE}/notifications/read-all`, { method: "POST" });
    await loadNotifications();
});

logoutBtn?.addEventListener("click", async () => {
    try {
        await fetchJson(`${API_BASE}/auth/logout`, { method: "POST" });
    } finally {
        ownerAuthenticated = false;
        ownerSessionExpiresAt = null;
        setNotificationsPanelOpen(false);
        ownerNotifications = [];
        setUnreadBadges(0);
        showCuteNotification("You have been logged out.", "Owner session");
    }
});
