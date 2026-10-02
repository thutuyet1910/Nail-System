// inventory.js: Inventory form and table

function isLowStock(item) {
    return Number(item.quantity) <= Number(item.low_stock_level || 0);
}

async function loadInventoryItems() {
    inventoryItems = await fetchJson(`${API_BASE}/inventory`);
}

async function loadInventorySummary() {
    const summary = await fetchJson(`${API_BASE}/inventory/summary`);

    inventoryTotalValue.textContent = formatMoney(summary.total_inventory_value);
    inventoryWeeklyExpense.textContent = formatMoney(summary.weekly_expense);
    inventoryMonthlyExpense.textContent = formatMoney(summary.monthly_expense);
    inventoryYearlyExpense.textContent = formatMoney(summary.yearly_expense);
    inventoryLowStockCount.textContent = String(summary.low_stock_items);
}

function resetInventoryForm() {
    inventoryForm.reset();
    inventoryIdInput.value = "";
    inventoryFormTitle.textContent = "Add Inventory Item";
    saveInventoryBtn.textContent = "Save Item";
    cancelInventoryEditBtn.classList.add("hidden");
    inventoryQuantity.value = 1;
    inventoryUnitPrice.value = 0;
}

function fillInventoryForm(item) {
    inventoryIdInput.value = item.id;
    inventoryItemName.value = item.item_name || "";
    inventoryCategory.value = item.category || "";
    inventorySupplier.value = item.supplier || "";
    inventoryQuantity.value = item.quantity ?? 1;
    inventoryUnitPrice.value = item.unit_price ?? 0;
    inventoryPurchaseDate.value = isoToDisplayDate(item.purchase_date);

    inventoryFormTitle.textContent = "Edit Inventory Item";
    saveInventoryBtn.textContent = "Update Item";
    cancelInventoryEditBtn.classList.remove("hidden");
}

function getFilteredInventoryItems() {
    let items = [...inventoryItems];

    const searchValue = inventorySearch?.value.trim().toLowerCase() || "";
    const categoryValue = inventoryCategoryFilter?.value || "";
    const stockValue = inventoryStockFilter?.value || "";

    if (searchValue) {
        items = items.filter((item) =>
            (item.item_name || "").toLowerCase().includes(searchValue)
        );
    }

    if (categoryValue) {
        items = items.filter((item) => item.category === categoryValue);
    }

    if (stockValue === "low") {
        items = items.filter((item) => isLowStock(item));
    } else if (stockValue === "ok") {
        items = items.filter((item) => !isLowStock(item));
    }

    return items;
}

function renderInventoryTable() {
    const items = getFilteredInventoryItems();

    inventoryTableBody.innerHTML = "";

    if (!items.length) {
        inventoryTableBody.innerHTML = `
      <tr>
        <td colspan="9" class="inventory-empty">No inventory items found.</td>
      </tr>
    `;
        return;
    }

    items.forEach((item) => {
        const tr = document.createElement("tr");
        const totalValue = Number(item.quantity || 0) * Number(item.unit_price || 0);
        const lowStock = isLowStock(item);

        tr.innerHTML = `
      <td>${escapeHtml(item.category || "-")}</td>
      <td>${escapeHtml(item.item_name || "-")}</td>
      <td>${item.quantity || 0}</td>
      <td>${formatMoney(item.unit_price || 0)}</td>
      <td>${formatMoney(totalValue)}</td>
      <td>${escapeHtml(item.supplier || "-")}</td>
      <td>${item.purchase_date ? isoToDisplayDate(item.purchase_date) : "-"}</td>
      <td>
        <span class="inventory-status ${lowStock ? "inventory-status-low" : "inventory-status-ok"}">
          ${lowStock ? "Low Stock" : "In Stock"}
        </span>
      </td>
      <td>
        <div class="inventory-actions">
          <button class="ghost-btn inventory-edit-btn" data-id="${item.id}">Edit</button>
          <button class="ghost-btn inventory-delete-btn" data-id="${item.id}">Delete</button>
        </div>
      </td>
    `;

        inventoryTableBody.appendChild(tr);
    });

    document.querySelectorAll(".inventory-edit-btn").forEach((btn) => {
        btn.addEventListener("click", () => {
            const item = inventoryItems.find((entry) => entry.id === Number(btn.dataset.id));
            if (!item) return;
            fillInventoryForm(item);
            window.scrollTo({ top: 0, behavior: "smooth" });
        });
    });

    document.querySelectorAll(".inventory-delete-btn").forEach((btn) => {
        btn.addEventListener("click", async () => {
            const confirmed = await showCuteConfirm("Delete this inventory item?", "Please Confirm");
            if (!confirmed) return;

            try {
                await fetchJson(`${API_BASE}/inventory/${btn.dataset.id}`, {
                    method: "DELETE"
                });
                await renderInventory();
                showCuteNotification("Inventory item deleted successfully.");
            } catch (error) {
                showCuteNotification(error.message || "Failed to delete inventory item.", "Oops");
            }
        });
    });
}

async function renderInventory() {
    await loadInventoryItems();
    await loadInventorySummary();
    renderInventoryTable();
}
