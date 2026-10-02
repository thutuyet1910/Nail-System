// income.js: Technician income and salon income reports
function setupIncomeDateDefaults() {
    const today = isoToDisplayDate(new Date());
    if (techIncomeDate && !techIncomeDate.value) techIncomeDate.value = today;
    if (salonIncomeDate && !salonIncomeDate.value) salonIncomeDate.value = today;
    if (techIncomeRangeStart && !techIncomeRangeStart.value) techIncomeRangeStart.value = today;
    if (techIncomeRangeEnd && !techIncomeRangeEnd.value) techIncomeRangeEnd.value = today;
    if (saleHistoryRangeStart && !saleHistoryRangeStart.value) saleHistoryRangeStart.value = today;
    if (saleHistoryRangeEnd && !saleHistoryRangeEnd.value) saleHistoryRangeEnd.value = today;
    setupRangeInputs(techIncomeRangeType, techIncomeRangeStart, techIncomeRangeEnd);
    setupRangeInputs(saleHistoryRangeType, saleHistoryRangeStart, saleHistoryRangeEnd);
}

function setupRangeInputs(typeInput, startInput, endInput) {
    if (!typeInput || !startInput || !endInput) return;
    const isYearRange = typeInput.value === "year";
    [startInput, endInput].forEach((input) => {
        const currentISO = displayDateToISO(input.value);
        input.dataset.dateMask = isYearRange ? "false" : "true";
        input.dataset.yearMask = isYearRange ? "true" : "false";
        input.placeholder = isYearRange ? "YYYY" : "MM-DD-YYYY";
        input.maxLength = isYearRange ? 4 : 10;
        input.pattern = isYearRange ? "\\d{4}" : "\\d{2}-\\d{2}-\\d{4}";
        if (isYearRange) {
            input.value = currentISO ? currentISO.slice(0, 4) : formatMaskedYear(input.value);
        } else if (/^\d{4}$/.test(input.value)) {
            input.value = input.id.toLowerCase().includes("end") ? `12-31-${input.value}` : `01-01-${input.value}`;
        } else {
            input.value = formatMaskedDate(input.value || isoToDisplayDate(new Date()));
        }
    });
}

function getWeekBounds(dateText) {
    const date = new Date(`${dateText}T00:00:00`);
    if (Number.isNaN(date.getTime())) return null;
    const day = date.getDay();
    const mondayOffset = day === 0 ? -6 : 1 - day;
    const sundayOffset = mondayOffset + 6;
    const start = new Date(date);
    const end = new Date(date);
    start.setDate(date.getDate() + mondayOffset);
    end.setDate(date.getDate() + sundayOffset);
    return {
        start: getLocalDateKey(start),
        end: getLocalDateKey(end),
    };
}

function getRangeBounds(rangeTypeInput, startInput, endInput) {
    const type = rangeTypeInput?.value || "date";
    const startValue = startInput?.value || "";
    const endValue = endInput?.value || "";

    if (type === "year") {
        if (!/^\d{4}$/.test(startValue) || !/^\d{4}$/.test(endValue)) return null;
        const startYear = Number(startValue);
        const endYear = Number(endValue);
        if (startYear > endYear) return null;
        return {
            type,
            start: `${startValue}-01-01`,
            end: `${endValue}-12-31`,
            label: `${startValue} to ${endValue}`,
        };
    }

    if (!isValidDateText(startValue) || !isValidDateText(endValue)) return null;

    const startISO = displayDateToISO(startValue);
    const endISO = displayDateToISO(endValue);
    const startBound = type === "week" ? getWeekBounds(startISO)?.start : startISO;
    const endBound = type === "week" ? getWeekBounds(endISO)?.end : endISO;
    if (!startBound || !endBound || startBound > endBound) return null;

    return {
        type,
        start: startBound,
        end: endBound,
        label: `${isoToDisplayDate(startBound)} to ${isoToDisplayDate(endBound)}`,
    };
}

function populateTechIncomeTechnicianDropdown() {
    if (!techIncomeTechnician) return;
    const selected = techIncomeTechnician.value;
    techIncomeTechnician.innerHTML = `<option value="">All technicians</option>`;

    techniciansRaw.forEach((tech) => {
        const option = document.createElement("option");
        option.value = tech.id;
        option.textContent = tech.full_name;
        techIncomeTechnician.appendChild(option);
    });

    techIncomeTechnician.value = selected;
}

// Turns a /checkouts record into one line of the income detail table.
// (/checkouts has no turn number, so Range Review shows "-" in the Turn column.)
function checkoutToIncomeDetail(checkout) {
    return {
        created_at: checkout.created_at,
        customer_name: checkout.customer_name || "",
        technician_name: getTechnicianNameById(checkout.technician_id),
        service_name: checkout.service_name || "",
        gross_before_discount: Number(checkout.subtotal || 0),
        discount_amount: Number(checkout.discount_amount || 0),
        net_after_discount: Number(checkout.net_service || 0),
        tech_60_percent: Number(checkout.technician_share || 0),
        tip_amount: Number(checkout.tip_amount || 0),
        tech_total: Number(checkout.technician_total || 0),
    };
}

function getCheckoutDateKey(checkout) {
    return checkout?.created_at ? getLocalDateKey(checkout.created_at) : "";
}

function filterCheckoutsByRange(checkouts, bounds) {
    return (checkouts || []).filter((checkout) => {
        const dateKey = getCheckoutDateKey(checkout);
        return dateKey && dateKey >= bounds.start && dateKey <= bounds.end;
    });
}

function renderIncomeDetailTable(details) {
    if (!details || !details.length) {
        return `<div class="empty-state">No turn details for this date.</div>`;
    }

    return `
    <div class="inventory-table-wrap income-table-wrap">
      <table class="inventory-table income-table">
        <thead>
          <tr>
            <th>Time</th>
            <th>Turn</th>
            <th>Customer</th>
            <th>Tech</th>
            <th>Service</th>
            <th>Gross</th>
            <th>Discount</th>
            <th>Net</th>
            <th>60%</th>
            <th>Tip</th>
            <th>Tech Total</th>
          </tr>
        </thead>
        <tbody>
          ${details.map((detail) => `
            <tr>
              <td>${formatDateTime(detail.created_at)}</td>
              <td>${detail.turn_number ? `#${detail.turn_number}` : "-"}</td>
              <td>${escapeHtml(detail.customer_name)}</td>
              <td>${escapeHtml(detail.technician_name || "-")}</td>
              <td>${escapeHtml(detail.service_name)}</td>
              <td>${formatMoney(detail.gross_before_discount)}</td>
              <td>${formatMoney(detail.discount_amount)}</td>
              <td>${formatMoney(detail.net_after_discount)}</td>
              <td>${formatMoney(detail.tech_60_percent)}</td>
              <td>${formatMoney(detail.tip_amount)}</td>
              <td>${formatMoney(detail.tech_total)}</td>
            </tr>
          `).join("")}
        </tbody>
      </table>
    </div>`;
}

function renderTechIncome(report) {
    techIncomeDateSummaries = report?.technicians || [];
    techIncomeDateLabel = report?.date ? isoToDisplayDate(report.date) : "";
    renderCombinedTechIncome();
}

function renderSalonIncome(report) {
    if (!report) return;

    if (salonDayBeforeDiscount) salonDayBeforeDiscount.textContent = formatMoney(report.day.income_before_discount);
    if (salonDayDiscount) salonDayDiscount.textContent = formatMoney(report.day.total_discount);
    if (salonDayAfterTech) salonDayAfterTech.textContent = formatMoney(report.day.salon_income_after_techs);
    if (salonWeekAfterTech) salonWeekAfterTech.textContent = formatMoney(report.week.salon_income_after_techs);
    if (salonYearAfterTech) salonYearAfterTech.textContent = formatMoney(report.year.salon_income_after_techs);

    if (!salonIncomeContent) return;
    const periods = [report.day, report.week, report.year];
    salonIncomeContent.innerHTML = `
    <div class="form-card income-report-card">
      <div class="income-period-grid">
        ${periods.map((period) => `
          <div class="income-period-panel">
            <h3>${period.period}</h3>
            <p class="subtitle">${formatIncomePeriodDates(period)}</p>
            <div class="income-period-lines">
              <p><span>Before Discount</span><strong>${formatMoney(period.income_before_discount)}</strong></p>
              <p><span>Discount</span><strong>${formatMoney(period.total_discount)}</strong></p>
              <p><span>After Discount</span><strong>${formatMoney(period.income_after_discount)}</strong></p>
              <p><span>Tech 60%</span><strong>${formatMoney(period.tech_60_percent_total)}</strong></p>
              <p><span>Tips Paid to Techs</span><strong>${formatMoney(period.tech_tip_total)}</strong></p>
              <p><span>Total Paid to Techs</span><strong>${formatMoney(period.total_paid_to_techs)}</strong></p>
              <p><span>Salon After Tech Pay</span><strong>${formatMoney(period.salon_income_after_techs)}</strong></p>
              <p><span>Turns</span><strong>${period.turns}</strong></p>
            </div>
          </div>
        `).join("")}
      </div>
    </div>
    <div class="form-card income-report-card">
      <div class="section-header">
        <div>
          <h3>Date Turn Details</h3>
          <p class="subtitle">${isoToDisplayDate(report.date)}</p>
        </div>
      </div>
      ${renderIncomeDetailTable(report.details)}
    </div>`;
}

async function loadTechIncome() {
    setupIncomeDateDefaults();
    if (!techIncomeDate?.value) return;
    if (!isValidDateText(techIncomeDate.value)) {
        showCuteNotification("Enter a valid income report date with a 4-number year.", "Notice");
        return;
    }

    const url = new URL(`${API_BASE}/income/tech`);
    url.searchParams.set("date", displayDateToISO(techIncomeDate.value));
    if (techIncomeTechnician?.value) {
        url.searchParams.set("technician_id", techIncomeTechnician.value);
    }

    try {
        const report = await fetchJson(url.toString());
        renderTechIncome(report);
    } catch (error) {
        if (techIncomeContent) {
            techIncomeContent.innerHTML = `<div class="form-card"><div class="empty-state">Could not load tech income.</div></div>`;
        }
        showCuteNotification(error.message || "Failed to load tech income.", "Oops");
    }
}

async function loadTechIncomeRange() {
    setupIncomeDateDefaults();
    const bounds = getRangeBounds(techIncomeRangeType, techIncomeRangeStart, techIncomeRangeEnd);
    if (!bounds) {
        showCuteNotification("Enter a valid range. Years must be exactly 4 numbers.", "Notice");
        return;
    }

    try {
        const checkouts = await fetchJson(`${API_BASE}/checkouts`);
        const technicianFilter = techIncomeTechnician?.value ? Number(techIncomeTechnician.value) : null;
        const matching = filterCheckoutsByRange(checkouts, bounds).filter((checkout) => {
            return !technicianFilter || Number(checkout.technician_id) === technicianFilter;
        });

        const grouped = new Map();
        matching.forEach((checkout) => {
            const techId = Number(checkout.technician_id || 0);
            const key = techId || "unassigned";
            if (!grouped.has(key)) {
                grouped.set(key, {
                    technician_id: techId || null,
                    // Same wording the backend uses, so Date Review and Range Review merge into one card.
                    technician_name: techId ? getTechnicianNameById(techId) : "Unassigned Technician",
                    date: bounds.label,
                    gross_before_60: 0,
                    tech_after_60: 0,
                    tip_total: 0,
                    tech_total: 0,
                    turns: 0,
                    details: [],
                });
            }
            const summary = grouped.get(key);
            summary.gross_before_60 += Number(checkout.subtotal || 0);
            summary.tech_after_60 += Number(checkout.technician_share || 0);
            summary.tip_total += Number(checkout.tip_amount || 0);
            summary.tech_total += Number(checkout.technician_total || 0);
            summary.turns += 1;
            summary.details.push(checkoutToIncomeDetail(checkout));
        });

        renderTechIncomeRange(Array.from(grouped.values()), bounds);
    } catch (error) {
        if (techIncomeRangeContent) {
            techIncomeRangeContent.innerHTML = `<div class="form-card"><div class="empty-state">Could not load tech income range.</div></div>`;
        }
        showCuteNotification(error.message || "Failed to load tech income range.", "Oops");
    }
}

function renderTechIncomeRange(summaries, bounds) {
    techIncomeRangeSummaries = summaries || [];
    techIncomeRangeLabel = bounds?.label || "";
    renderCombinedTechIncome();
}

function getTechIncomeKey(summary) {
    return summary?.technician_id ? `id-${summary.technician_id}` : `name-${summary?.technician_name || "Unknown"}`;
}

function renderTechIncomeSummarySection(title, label, summary) {
    if (!summary) {
        return `
      <div class="income-period-panel">
        <h3>${escapeHtml(title)}</h3>
        <p class="subtitle">${escapeHtml(label || "-")}</p>
        <div class="empty-state">No income found.</div>
      </div>`;
    }

    return `
      <div class="income-period-panel">
        <h3>${escapeHtml(title)}</h3>
        <p class="subtitle">${escapeHtml(label || "-")}</p>
        <div class="inventory-summary-grid income-summary-grid">
          <div class="summary-card">
            <span class="summary-label">Nail Gross Before 60%</span>
            <strong>${formatMoney(summary.gross_before_60)}</strong>
          </div>
          <div class="summary-card">
            <span class="summary-label">Tech 60%</span>
            <strong>${formatMoney(summary.tech_after_60)}</strong>
          </div>
          <div class="summary-card">
            <span class="summary-label">Tip</span>
            <strong>${formatMoney(summary.tip_total)}</strong>
          </div>
          <div class="summary-card">
            <span class="summary-label">Tech Total</span>
            <strong>${formatMoney(summary.tech_total)}</strong>
          </div>
          <div class="summary-card">
            <span class="summary-label">Turns</span>
            <strong>${summary.turns}</strong>
          </div>
        </div>
        ${renderIncomeDetailTable(summary.details)}
      </div>`;
}

function renderCombinedTechIncome() {
    if (techIncomeRangeContent) techIncomeRangeContent.innerHTML = "";
    if (!techIncomeContent) return;

    const grouped = new Map();
    techIncomeDateSummaries.forEach((summary) => {
        const key = getTechIncomeKey(summary);
        grouped.set(key, {
            technician_name: summary.technician_name,
            dateSummary: summary,
            rangeSummary: null,
        });
    });

    techIncomeRangeSummaries.forEach((summary) => {
        const key = getTechIncomeKey(summary);
        const existing = grouped.get(key) || {
            technician_name: summary.technician_name,
            dateSummary: null,
            rangeSummary: null,
        };
        existing.technician_name = existing.technician_name || summary.technician_name;
        existing.rangeSummary = summary;
        grouped.set(key, existing);
    });

    if (!grouped.size) {
        techIncomeContent.innerHTML = `
      <div class="form-card">
        <div class="empty-state">No tech income found.</div>
      </div>`;
        return;
    }

    techIncomeContent.innerHTML = Array.from(grouped.values()).map((group) => `
    <div class="form-card income-report-card">
      <div class="section-header">
        <div>
          <h3>${escapeHtml(group.technician_name || "Unknown Technician")}</h3>
          <p class="subtitle">Date and range results grouped together</p>
        </div>
      </div>
      <div class="income-period-grid tech-income-combined-grid">
        ${renderTechIncomeSummarySection("Date Review", techIncomeDateLabel, group.dateSummary)}
        ${renderTechIncomeSummarySection("Range Review", techIncomeRangeLabel, group.rangeSummary)}
      </div>
    </div>
  `).join("");
}

function formatIncomePeriodDates(period) {
    const start = isoToDisplayDate(period.start_date);
    const end = isoToDisplayDate(period.end_date);
    return start === end ? start : `${start} to ${end}`;
}

async function loadSalonIncome() {
    setupIncomeDateDefaults();
    if (!salonIncomeDate?.value) return;
    if (!isValidDateText(salonIncomeDate.value)) {
        showCuteNotification("Enter a valid salon income date with a 4-number year.", "Notice");
        return;
    }

    const url = new URL(`${API_BASE}/income/salon`);
    url.searchParams.set("date", displayDateToISO(salonIncomeDate.value));

    try {
        const report = await fetchJson(url.toString());
        renderSalonIncome(report);
    } catch (error) {
        if (salonIncomeContent) {
            salonIncomeContent.innerHTML = `<div class="form-card"><div class="empty-state">Could not load salon income.</div></div>`;
        }
        showCuteNotification(error.message || "Failed to load salon income.", "Oops");
    }
}