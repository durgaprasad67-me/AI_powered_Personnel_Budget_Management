"use strict";

/* ==========================================================================
   FinSight AI - Analytics Page Controller
   Faithfully using the Overview Page (Dashboard) Color Palette & Design Tokens
   ========================================================================== */

const analytics$ = (id) => document.getElementById(id);

// All 8 supported transaction types mapped to the Overview Page color palette
const TYPE_CONFIG = {
  income: {
    label: "Income",
    stream: "inflow",
    color: "#8fc8b5", // Sage green (Overview Total Income)
    bg: "#eaf5f1",
    icon: "arrow-down-left",
    description: "Salary, wages, business revenue, freelance",
  },
  investment_return: {
    label: "Investment Return",
    stream: "inflow",
    color: "#bfd6f2", // Soft pastel blue (Overview Brand & Balance)
    bg: "#edf4fc",
    icon: "trending-up",
    description: "Dividends, capital gains, interest returns",
  },
  loan_taken: {
    label: "Loan Taken (Borrowed)",
    stream: "inflow",
    color: "#b8a6f4", // Lavender (Overview Allocated/Loan)
    bg: "#f3f0fd",
    icon: "landmark",
    description: "Loans received from banks, lenders, or peers",
  },
  loan_collected: {
    label: "Loan Collected (Repaid to You)",
    stream: "inflow",
    color: "#9eafab", // Muted Sage (Overview Sage)
    bg: "#eef3f2",
    icon: "hand-coins",
    description: "Repayments received from money previously lent",
  },
  expense: {
    label: "Expense",
    stream: "outflow",
    color: "#ffb5ae", // Soft Coral (Overview Total Expenses)
    bg: "#fff0ee",
    icon: "arrow-up-right",
    description: "Living costs, bills, dining, leisure, groceries",
  },
  investment: {
    label: "Investment",
    stream: "outflow",
    color: "#b8a6f4", // Lavender (Overview Investments)
    bg: "#f3f0fd",
    icon: "piggy-bank",
    description: "SIPs, equity, mutual funds, gold, fixed deposits",
  },
  loan_repaid: {
    label: "Loan Repayment (EMI)",
    stream: "outflow",
    color: "#f4d59c", // Warm Peach / Gold (Overview Loan & Goal)
    bg: "#fdf8ee",
    icon: "receipt",
    description: "EMIs, loan installments, debt settlements",
  },
  loan_given: {
    label: "Loan Given (Lent)",
    stream: "outflow",
    color: "#e5b5d1", // Soft Orchid (Overview Doughnut 7th color)
    bg: "#faf0f5",
    icon: "badge-percent",
    description: "Money lent to friends, relatives, or partners",
  },
};

// Exact Category Doughnut Palette from Overview Page (dashboard.js lines 440-447)
const CATEGORY_PALETTE = [
  "#8fc8b5", // sage green
  "#ffb5ae", // soft coral
  "#b8a6f4", // lavender
  "#bfd6f2", // soft blue
  "#f4d59c", // warm gold
  "#9eafab", // muted sage
  "#e5b5d1", // soft orchid
  "#a3d6c5", // light sage
  "#f7c5ba", // light coral
  "#cbbeef", // light lavender
  "#d2e4f7", // pale blue
  "#fae3ba", // pale gold
];

// Active Chart.js instances
let outflowChartInstance = null;
let inflowChartInstance = null;
let cashflowChartInstance = null;
let allTypesChartInstance = null;

let currentAnalyticsData = null;
let currentFilter = "all";

function currentMonthValue() {
  const date = new Date();
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}`;
}

/* =========================================
   Render Executive Financial KPI Stat Cards
========================================= */
function renderStats(data) {
  const container = analytics$("analyticsStats");
  if (!container) return;

  const netCash = Number(data.net_cash_flow || 0);
  const netSurplusClass = netCash >= 0 ? "net-positive" : "net-negative";
  const netSurplusBadge = netCash >= 0 ? "inflow" : "outflow";
  const netSurplusLabel = netCash >= 0 ? "Net Cash Surplus" : "Net Cash Deficit";

  const cardsHtml = [
    `
    <article class="analytics-stat-card inflow">
      <div class="stat-header">
        <div class="stat-label-wrap">
          <span class="stat-label-eyebrow">Cash Inflows</span>
        </div>
        <div class="stat-icon-wrap inflow">
          <i data-lucide="arrow-down-left"></i>
        </div>
      </div>
      <div class="stat-value">${FinSight.money(data.total_cash_inflow)}</div>
      <div class="stat-footer">
        <span class="stat-badge-tag pill-amount-badge inflow">Total Inflow</span>
        <span class="stat-subtext" title="Income, returns, borrowings and collections">Income, Returns &amp; Borrowings</span>
      </div>
    </article>
    `,
    `
    <article class="analytics-stat-card outflow">
      <div class="stat-header">
        <div class="stat-label-wrap">
          <span class="stat-label-eyebrow">Cash Outflows</span>
        </div>
        <div class="stat-icon-wrap outflow">
          <i data-lucide="arrow-up-right"></i>
        </div>
      </div>
      <div class="stat-value">${FinSight.money(data.total_cash_outflow)}</div>
      <div class="stat-footer">
        <span class="stat-badge-tag pill-amount-badge outflow">Total Outflow</span>
        <span class="stat-subtext" title="Expenses, investments, repayments and loans given">Expenses, Investments &amp; EMIs</span>
      </div>
    </article>
    `,
    `
    <article class="analytics-stat-card ${netSurplusClass}">
      <div class="stat-header">
        <div class="stat-label-wrap">
          <span class="stat-label-eyebrow">Net Position</span>
        </div>
        <div class="stat-icon-wrap ${netSurplusClass}">
          <i data-lucide="scale"></i>
        </div>
      </div>
      <div class="stat-value">${FinSight.money(netCash)}</div>
      <div class="stat-footer">
        <span class="stat-badge-tag pill-amount-badge ${netSurplusBadge}">${netSurplusLabel}</span>
        <span class="stat-subtext">Total Inflow minus Outflow</span>
      </div>
    </article>
    `,
    `
    <article class="analytics-stat-card balance">
      <div class="stat-header">
        <div class="stat-label-wrap">
          <span class="stat-label-eyebrow">Operating Balance</span>
        </div>
        <div class="stat-icon-wrap balance">
          <i data-lucide="wallet"></i>
        </div>
      </div>
      <div class="stat-value">${FinSight.money(data.balance)}</div>
      <div class="stat-footer">
        <span class="stat-badge-tag" style="background:#edf4fc;color:#4872a4;border:1px solid #d5e5f7;">Income vs Expense</span>
        <span class="stat-subtext">Inc: ${FinSight.money(data.total_income)} | Exp: ${FinSight.money(data.total_expenses)}</span>
      </div>
    </article>
    `,
    `
    <article class="analytics-stat-card invest">
      <div class="stat-header">
        <div class="stat-label-wrap">
          <span class="stat-label-eyebrow">Investments</span>
        </div>
        <div class="stat-icon-wrap invest">
          <i data-lucide="trending-up"></i>
        </div>
      </div>
      <div class="stat-value">${FinSight.money(data.investments?.net_invested || 0)}</div>
      <div class="stat-footer">
        <span class="stat-badge-tag" style="background:#f3f0fd;color:#6b57b5;border:1px solid #ded7fa;">Net Invested</span>
        <span class="stat-subtext">Put: ${FinSight.money(data.investments?.invested || 0)} | Got: ${FinSight.money(data.investments?.returned || 0)}</span>
      </div>
    </article>
    `,
    `
    <article class="analytics-stat-card loan">
      <div class="stat-header">
        <div class="stat-label-wrap">
          <span class="stat-label-eyebrow">Debt Activity</span>
        </div>
        <div class="stat-icon-wrap loan">
          <i data-lucide="landmark"></i>
        </div>
      </div>
      <div class="stat-value">${FinSight.money((data.loans?.borrowed || 0) - (data.loans?.repaid || 0))}</div>
      <div class="stat-footer">
        <span class="stat-badge-tag" style="background:#fdf8ee;color:#96702e;border:1px solid #f8e5c2;">Net Borrowing</span>
        <span class="stat-subtext">Borrowed: ${FinSight.money(data.loans?.borrowed || 0)} | Repaid: ${FinSight.money(data.loans?.repaid || 0)}</span>
      </div>
    </article>
    `
  ].join("");

  container.innerHTML = cardsHtml;
}

/* =========================================
   Render Category Doughnut & Dynamic List
========================================= */
function renderCategorySection(canvasId, listId, badgeId, categoriesDict, totalAmount, emptyMessage, isOutflow) {
  const badge = analytics$(badgeId);
  const list = analytics$(listId);
  const canvas = analytics$(canvasId);

  if (badge) {
    badge.textContent = FinSight.money(totalAmount);
  }

  const entries = Object.entries(categoriesDict || {}).filter(([, val]) => Number(val) > 0);

  if (isOutflow && outflowChartInstance) {
    outflowChartInstance.destroy();
    outflowChartInstance = null;
  } else if (!isOutflow && inflowChartInstance) {
    inflowChartInstance.destroy();
    inflowChartInstance = null;
  }

  if (entries.length === 0 || Number(totalAmount) <= 0) {
    if (list) {
      list.innerHTML = `
        <div class="empty-state">
          <div class="empty-icon-wrap"><i data-lucide="inbox"></i></div>
          <div>${emptyMessage}</div>
          <p>No activity recorded in this stream for ${analytics$("analyticsMonth").value}</p>
        </div>
      `;
    }
    return;
  }

  // Generate chart data using Overview Palette
  const labels = entries.map(([name]) => name);
  const data = entries.map(([, val]) => Number(val));
  const colors = entries.map((_, i) => CATEGORY_PALETTE[i % CATEGORY_PALETTE.length]);

  const newChart = new Chart(canvas, {
    type: "doughnut",
    data: {
      labels,
      datasets: [
        {
          data,
          backgroundColor: colors,
          borderColor: "#ffffff",
          borderWidth: 2,
          borderRadius: 4,
          spacing: 2,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          display: false,
        },
        tooltip: {
          backgroundColor: "#111c2a",
          padding: 12,
          cornerRadius: 10,
          titleFont: { family: "Manrope", size: 13, weight: "700" },
          bodyFont: { family: "DM Sans", size: 12 },
          callbacks: {
            label: (context) => {
              const val = context.raw || 0;
              const pct = totalAmount > 0 ? ((val / totalAmount) * 100).toFixed(1) : 0;
              return ` ${context.label}: ${FinSight.money(val)} (${pct}%)`;
            },
          },
        },
      },
      cutout: "74%",
    },
  });

  if (isOutflow) {
    outflowChartInstance = newChart;
  } else {
    inflowChartInstance = newChart;
  }

  // Render dynamic list rows with horizontal progress bars
  if (list) {
    list.innerHTML = entries
      .map(([name, val], index) => {
        const amount = Number(val);
        const pct = totalAmount > 0 ? ((amount / totalAmount) * 100).toFixed(1) : "0.0";
        const color = colors[index];
        return `
          <div class="category-row">
            <div class="category-main">
              <div class="category-name-wrap">
                <span class="category-color-dot" style="background: ${color}"></span>
                <span class="category-name" title="${name}">${name}</span>
              </div>
              <div class="category-bar-track">
                <div class="category-bar-fill" style="width: ${pct}%; background: ${color}"></div>
              </div>
            </div>
            <div class="category-meta">
              <span class="category-amount">${FinSight.money(amount)}</span>
              <span class="category-pct">${pct}%</span>
            </div>
          </div>
        `;
      })
      .join("");
  }
}

/* =========================================
   Render Cash Flow Streams Comparison Chart
========================================= */
function renderCashflowComparison(data) {
  const canvas = analytics$("cashflowChart");
  if (!canvas) return;

  if (cashflowChartInstance) {
    cashflowChartInstance.destroy();
    cashflowChartInstance = null;
  }

  const inflow = Number(data.total_cash_inflow || 0);
  const outflow = Number(data.total_cash_outflow || 0);
  const net = Number(data.net_cash_flow || 0);

  cashflowChartInstance = new Chart(canvas, {
    type: "bar",
    data: {
      labels: ["Cash Inflow", "Cash Outflow", "Net Cash Flow"],
      datasets: [
        {
          label: "Volume",
          data: [inflow, outflow, net],
          backgroundColor: [
            "#8fc8b5", // Overview Income green
            "#ffb5ae", // Overview Expense coral
            net >= 0 ? "#8fc8b5" : "#ffb5ae",
          ],
          borderRadius: 6,
          barPercentage: 0.55,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          display: false,
        },
        tooltip: {
          backgroundColor: "#111c2a",
          padding: 12,
          cornerRadius: 10,
          titleFont: { family: "Manrope", size: 13, weight: "700" },
          bodyFont: { family: "DM Sans", size: 12 },
          callbacks: {
            label: (ctx) => ` Amount: ${FinSight.money(ctx.raw)}`,
          },
        },
      },
      scales: {
        y: {
          beginAtZero: true,
          grid: {
            color: "rgba(224, 231, 230, 0.7)",
          },
          ticks: {
            font: { family: "DM Sans", size: 11 },
            color: "#7f8b96",
            callback: (val) => FinSight.money(val),
          },
        },
        x: {
          grid: {
            display: false,
          },
          ticks: {
            font: { family: "Manrope", size: 12, weight: "700" },
            color: "#17202d",
          },
        },
      },
    },
  });
}

/* =========================================
   Render All 8 Transaction Types Distribution Chart
========================================= */
function renderAllTypesChart(data) {
  const canvas = analytics$("allTypesChart");
  if (!canvas) return;

  if (allTypesChartInstance) {
    allTypesChartInstance.destroy();
    allTypesChartInstance = null;
  }

  const typeBreakdown = data.type_breakdown || {};
  const types = Object.keys(TYPE_CONFIG);

  const labels = types.map((type) => TYPE_CONFIG[type].label);
  const values = types.map((type) => Number(typeBreakdown[type] || 0));
  const colors = types.map((type) => TYPE_CONFIG[type].color);

  allTypesChartInstance = new Chart(canvas, {
    type: "bar",
    data: {
      labels,
      datasets: [
        {
          label: "Volume",
          data: values,
          backgroundColor: colors,
          borderRadius: 6,
          barPercentage: 0.65,
        },
      ],
    },
    options: {
      indexAxis: "y",
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          display: false,
        },
        tooltip: {
          backgroundColor: "#111c2a",
          padding: 12,
          cornerRadius: 10,
          titleFont: { family: "Manrope", size: 13, weight: "700" },
          bodyFont: { family: "DM Sans", size: 12 },
          callbacks: {
            label: (ctx) => ` Total Volume: ${FinSight.money(ctx.raw)}`,
          },
        },
      },
      scales: {
        x: {
          beginAtZero: true,
          grid: {
            color: "rgba(224, 231, 230, 0.7)",
          },
          ticks: {
            font: { family: "DM Sans", size: 11 },
            color: "#7f8b96",
            callback: (val) => FinSight.money(val),
          },
        },
        y: {
          grid: {
            display: false,
          },
          ticks: {
            font: { family: "DM Sans", size: 11.5, weight: "600" },
            color: "#17202d",
          },
        },
      },
    },
  });
}

/* =========================================
   Render Types & Dynamic Categories Explorer Table
========================================= */
function renderTypesTable(data, filter = "all") {
  const tbody = analytics$("typeBreakdownTableBody");
  if (!tbody) return;

  let items = data.type_details || [];

  // Fallback if type_details was not returned directly
  if (items.length === 0) {
    const typeBreakdown = data.type_breakdown || {};
    items = Object.keys(TYPE_CONFIG).map((type) => {
      const cfg = TYPE_CONFIG[type];
      const cats = type === "expense" ? (data.category_breakdown || {}) : {};
      return {
        type,
        stream: cfg.stream,
        total: Number(typeBreakdown[type] || 0),
        count: 0,
        categories: cats,
      };
    });
  }

  const filteredItems = items.filter((item) => {
    if (filter === "inflow") return item.stream === "inflow";
    if (filter === "outflow") return item.stream === "outflow";
    return true;
  });

  const totalInflow = Number(data.total_cash_inflow || 0);
  const totalOutflow = Number(data.total_cash_outflow || 0);

  if (filteredItems.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="6" class="empty">
          <div class="empty-state">
            <div class="empty-icon-wrap"><i data-lucide="layers"></i></div>
            <div>No matching transaction types</div>
            <p>No transactions found for the selected filter.</p>
          </div>
        </td>
      </tr>
    `;
    if (window.lucide && typeof window.lucide.createIcons === "function") {
      window.lucide.createIcons();
    }
    return;
  }

  tbody.innerHTML = filteredItems
    .map((item) => {
      const cfg = TYPE_CONFIG[item.type] || {
        label: item.type,
        stream: item.stream,
        color: "#9eafab",
        bg: "#f1f5f4",
        icon: "circle",
        description: "",
      };
      const streamBadge =
        item.stream === "inflow"
          ? '<span class="stream-pill inflow"><span class="dot"></span>Cash Inflow</span>'
          : '<span class="stream-pill outflow"><span class="dot"></span>Cash Outflow</span>';

      const baseTotal = item.stream === "inflow" ? totalInflow : totalOutflow;
      const sharePct =
        baseTotal > 0 ? ((item.total / baseTotal) * 100).toFixed(1) + "%" : "0.0%";

      const categoryEntries = Object.entries(item.categories || {}).filter(
        ([, amt]) => Number(amt) > 0
      );

      const categoryTagsHtml =
        categoryEntries.length > 0
          ? categoryEntries
              .map(
                ([cat, amt]) =>
                  `<span class="category-tag">${cat}: <strong>${FinSight.money(amt)}</strong></span>`
              )
              .join("")
          : '<span class="category-tag" style="color:var(--muted);background:transparent;border:0;">None recorded</span>';

      return `
        <tr>
          <td>${streamBadge}</td>
          <td>
            <div class="type-cell">
              <div class="type-icon-box" style="background:${cfg.bg};color:${cfg.color}">
                <i data-lucide="${cfg.icon}"></i>
              </div>
              <div class="type-details-wrap">
                <span class="type-title">${cfg.label}</span>
                <span class="type-desc">${cfg.description}</span>
              </div>
            </div>
          </td>
          <td><span class="amount-cell">${FinSight.money(item.total)}</span></td>
          <td><span class="count-badge">${item.count || 0} txn${item.count === 1 ? '' : 's'}</span></td>
          <td>
            <div class="share-cell">
              <div class="share-bar-track">
                <div class="share-bar-fill" style="width: ${sharePct}; background: ${cfg.color}"></div>
              </div>
              <span class="share-text">${sharePct}</span>
            </div>
          </td>
          <td>
            <div class="category-tags">
              ${categoryTagsHtml}
            </div>
          </td>
        </tr>
      `;
    })
    .join("");

  if (window.lucide && typeof window.lucide.createIcons === "function") {
    window.lucide.createIcons();
  }
}

/* =========================================
   Load Analytics Handler
========================================= */
async function loadAnalytics() {
  const month = analytics$("analyticsMonth").value;
  try {
    const data = await FinSight.api(`/dashboard?month=${month}`);
    currentAnalyticsData = data;

    // 1. Render Top KPI Stat cards
    renderStats(data);

    // 2. Render Outflow categories (expenses, investments, loan repaid, loan given)
    const outflowCats = data.outflow_categories || data.category_breakdown || {};
    renderCategorySection(
      "outflowCategoryChart",
      "outflowCategoriesList",
      "outflowTotalBadge",
      outflowCats,
      data.total_cash_outflow || data.total_expenses,
      "No cash outflows recorded this month.",
      true
    );

    // 3. Render Inflow categories (income, investment returns, loans taken & collected)
    const inflowCats = data.inflow_categories || {};
    renderCategorySection(
      "inflowCategoryChart",
      "inflowCategoriesList",
      "inflowTotalBadge",
      inflowCats,
      data.total_cash_inflow || data.total_income,
      "No cash inflows recorded this month.",
      false
    );

    // 4. Render Cash Flow stream comparison bar chart
    renderCashflowComparison(data);

    // 5. Render All 8 transaction types distribution bar chart
    renderAllTypesChart(data);

    // 6. Render Dynamic Types & Categories Explorer Table
    renderTypesTable(data, currentFilter);

    if (window.lucide && typeof window.lucide.createIcons === "function") {
      window.lucide.createIcons();
    }
  } catch (error) {
    FinSight.toast(error.message);
  }
}

/* =========================================
   Period Navigation & Month Shift
========================================= */
function shiftMonth(offset) {
  const input = analytics$("analyticsMonth");
  if (!input) return;
  const current = input.value || currentMonthValue();
  const [yearStr, monthStr] = current.split("-");
  const d = new Date(parseInt(yearStr, 10), parseInt(monthStr, 10) - 1 + offset, 1);
  input.value = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
  void loadAnalytics();
}

/* =========================================
   Event Bindings & Initialization
========================================= */
const monthInput = analytics$("analyticsMonth");
monthInput.value = currentMonthValue();
monthInput.addEventListener("change", () => void loadAnalytics());

analytics$("prevMonthBtn")?.addEventListener("click", () => shiftMonth(-1));
analytics$("nextMonthBtn")?.addEventListener("click", () => shiftMonth(1));

// Filter pills binding
const filterContainer = analytics$("typeFilters");
if (filterContainer) {
  filterContainer.addEventListener("click", (event) => {
    const target = event.target.closest(".filter-pill");
    if (!target) return;

    filterContainer.querySelectorAll(".filter-pill").forEach((pill) => {
      pill.classList.remove("active");
    });
    target.classList.add("active");

    currentFilter = target.getAttribute("data-filter") || "all";
    if (currentAnalyticsData) {
      renderTypesTable(currentAnalyticsData, currentFilter);
    }
  });
}

void loadAnalytics();
