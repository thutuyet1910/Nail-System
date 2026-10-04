async function loadNotifications() {
    if (!ownerAuthenticated) return;
    try {
        ownerNotifications = await fetchJson(`${API_BASE}/notifications?limit=50`);
        const count = await fetchJson(`${API_BASE}/notifications/unread-count`);
        notificationBadge.textContent = String(count.unread_count || 0);
        notificationBadge.classList.toggle("hidden", !count.unread_count);
        renderNotifications();
    } catch (error) {
        console.error("Failed to load notifications:", error);
    }
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
        <small>${formatDateTime(item.created_at)}</small>
      </button>`).join("");
    notificationsList.querySelectorAll("[data-notification-id]").forEach((button) => {
        button.addEventListener("click", async () => {
            await fetchJson(`${API_BASE}/notifications/${button.dataset.notificationId}/read`, { method: "POST" });
            await loadNotifications();
        });
    });
}

notificationsBtn?.addEventListener("click", async () => {
    if (!(await requireOwner())) return;
    await loadNotifications();
    notificationsPanel?.classList.remove("hidden");
});

closeNotifications?.addEventListener("click", () => notificationsPanel?.classList.add("hidden"));

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
        notificationsPanel?.classList.add("hidden");
        showCuteNotification("You have been logged out.", "Owner session");
    }
});
