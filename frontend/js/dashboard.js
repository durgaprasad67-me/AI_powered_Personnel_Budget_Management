
"use strict";

/* =========================================
   FinSight AI - Dashboard JavaScript
   Functional buttons, charts, navigation
========================================= */

const API_BASE_URL =
  window.FINSIGHT_API_URL || "http://127.0.0.1:8000/api/v1";

const currency = new Intl.NumberFormat("en-IN", {
  style: "currency",
  currency: "INR",
  maximumFractionDigits: 2,
});

const currentMonth = () => {
  const date = new Date();

  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}`;
};

let selectedMonth = currentMonth();
let selectedChartPeriod = 6;

let cashflowChartInstance = null;
let spendingChartInstance = null;
let dashboardData = null;
let toastTimeout = null;
const NOTIFICATION_STORAGE_KEY = "finsight.dashboard.notifications";
let notifications = [];

let selectedCashflowView = "all_types";
let selectedPieView = "all_types";
let cashflowHistoryCache = [];

const OVERVIEW_TRANSACTION_TYPES = [
  { key: "income", label: "Income", color: "#8fc8b5" },
  { key: "expense", label: "Expenses", color: "#ffb5ae" },
  { key: "investment", label: "Investments", color: "#b8a6f4" },
  { key: "investment_return", label: "Investment Returns", color: "#bfd6f2" },
  { key: "loan_taken", label: "Loans Borrowed", color: "#f4d59c" },
  { key: "loan_repaid", label: "Loans Repaid", color: "#e5b5d1" },
  { key: "loan_given", label: "Loans Lent", color: "#fae2b8" },
  { key: "loan_collected", label: "Loans Collected", color: "#9eafab" },
];

const OVERVIEW_CHART_COLORS = [
  "#8fc8b5",
  "#ffb5ae",
  "#b8a6f4",
  "#bfd6f2",
  "#f4d59c",
  "#9eafab",
  "#e5b5d1",
  "#a3d6c5",
  "#f7c5ba",
  "#cbbeef",
];

/* =========================================
   DOM Utilities
========================================= */

const getElement = (id) => document.getElementById(id);

const setText = (id, value) => {
  const element = getElement(id);

  if (element) {
    element.textContent = value;
  }
};

function readNotifications() {
  try {
    const stored = JSON.parse(localStorage.getItem(NOTIFICATION_STORAGE_KEY) || "[]");
    return Array.isArray(stored) ? stored : [];
  } catch (error) {
    console.warn("Unable to read stored notifications:", error);
    return [];
  }
}

function saveNotifications() {
  localStorage.setItem(NOTIFICATION_STORAGE_KEY, JSON.stringify(notifications));
}

function updateNotificationCount() {
  const badge = getElement("notificationCount");
  if (!badge) return;
  const unread = notifications.filter((item) => !item.seen).length;
  badge.textContent = String(unread);
  badge.hidden = unread === 0;
  getElement("notifyBtn")?.classList.toggle("has-notifications", unread > 0);
}

function renderNotifications() {
  const list = getElement("notificationList");
  if (!list) return;
  list.replaceChildren();
  if (!notifications.length) {
    list.innerHTML = '<div class="notification-empty"><i data-lucide="bell-off"></i><strong>No alerts</strong><span>You have no budget alerts right now.</span></div>';
  } else {
    notifications.slice().reverse().forEach((notification) => {
      const item = document.createElement("article");
      item.className = `notification-item${notification.seen ? " seen" : ""}`;
      item.innerHTML = `<label class="notification-check"><input type="checkbox" data-notification-id="${notification.id}" aria-label="Select notification"></label><div class="notification-icon"><i data-lucide="${notification.severity === "danger" ? "triangle-alert" : "bell-ring"}"></i></div><div class="notification-copy"><strong>${notification.title}</strong><p>${notification.message}</p><small>${notification.seen ? "Seen" : "New"} · ${notification.createdAt}</small></div><button class="notification-delete" type="button" aria-label="Delete notification"><i data-lucide="trash-2"></i></button>`;
      item.querySelector(".notification-delete").addEventListener("click", () => {
        notifications = notifications.filter((entry) => entry.id !== notification.id);
        saveNotifications();
        renderNotifications();
        updateNotificationCount();
      });
      list.appendChild(item);
    });
  }
  if (window.lucide) window.lucide.createIcons();
}

async function addBudgetNotifications(data) {
  const thresholds = [50, 75, 100];
  const existing = new Set(notifications.map((item) => item.id));
  await Promise.all((data.budgets || []).map(async (budget) => {
    try {
      const response = await fetch(`${API_BASE_URL}/budgets/${encodeURIComponent(budget.id)}/progress`);
      if (!response.ok) return;
      const usage = await response.json();
      thresholds.forEach((threshold) => {
        const id = `${budget.id}:${data.month}:${threshold}`;
        if (Number(usage.percentage_used) >= threshold && !existing.has(id)) {
          notifications.push({
            id,
            seen: false,
            severity: threshold === 100 ? "danger" : "warning",
            title: `${budget.category || "Budget"} reached ${threshold}%`,
            message: `${amount(usage.spent_amount)} used of ${amount(usage.budget_amount)}. ${threshold === 100 ? "The budget limit has been reached." : "Review your spending to stay within the limit."}`,
            createdAt: new Date().toLocaleString("en-IN"),
          });
          existing.add(id);
        }
      });
    } catch (error) {
      console.warn("Unable to load budget alert:", error);
    }
  }));
  saveNotifications();
  updateNotificationCount();
}

const amount = (value) => currency.format(Number(value || 0));

/* =========================================
   Toast Notifications
========================================= */

function showToast(message) {
  const toast = getElement("toast");

  if (!toast) {
    alert(message);
    return;
  }

  if (!toast._hasDismissListener) {
    toast._hasDismissListener = true;
    toast.style.cursor = "pointer";
    toast.addEventListener("click", () => {
      toast.classList.remove("show", "error");
      clearTimeout(toastTimeout);
    });
  }

  toast.textContent = message;
  toast.classList.add("error");
  toast.setAttribute("role", "alert");
  toast.classList.add("show");

  clearTimeout(toastTimeout);

  toastTimeout = setTimeout(() => {
    toast.classList.remove("show", "error");
  }, 6500);
}

/* =========================================
   Dynamic Greeting
========================================= */

function updateGreeting() {
  const hour = new Date().getHours();

  let greeting = "Good evening";

  if (hour < 12) {
    greeting = "Good morning";
  } else if (hour < 17) {
    greeting = "Good afternoon";
  }

  const nameElement = document.querySelector("[data-user-name]");
  const userName = nameElement?.textContent.trim() || "Personal account";
  setText(
    "greetingTitle",
    userName && userName !== "Personal account"
      ? `${greeting}, ${userName}`
      : `${greeting} — here's your financial snapshot`,
  );

  document.querySelectorAll("[data-user-initial]").forEach((element) => {
    element.textContent = userName.charAt(0).toUpperCase();
  });
}

/* =========================================
   Month Formatting
========================================= */

function getMonthLabel(month) {
  return new Date(`${month}-01T00:00:00`).toLocaleDateString(
    "en-IN",
    {
      month: "long",
      year: "numeric",
    },
  );
}

/* =========================================
   Render Financial Summary
========================================= */

function renderSummary(summary) {
  const income = Number(summary.total_income || 0);
  const expenses = Number(summary.total_expenses || 0);

  const invested = Number(
    summary.investments?.net_invested || 0,
  );

  const balance = Number(summary.balance || 0);
  const availableCash = Number(summary.net_cash_flow ?? balance);
  const cashIn = income
    + Number(summary.investments?.returned || 0)
    + Number(summary.loans?.borrowed || 0)
    + Number(summary.loans?.collected || 0);
  const cashOut = expenses
    + Number(summary.investments?.invested || 0)
    + Number(summary.loans?.repaid || 0)
    + Number(summary.loans?.lent || 0);
  const loanCashOut = Number(summary.loans?.repaid || 0)
    + Number(summary.loans?.lent || 0);
  const investmentCashOut = Number(summary.investments?.invested || 0);

  const netLoanCashFlow = Number(summary.loans?.borrowed || 0)
    + Number(summary.loans?.collected || 0)
    - Number(summary.loans?.repaid || 0)
    - Number(summary.loans?.lent || 0);

  const denominator = income || 1;

  setText("availableValue", amount(availableCash));
  setText("incomeValue", amount(income));
  setText("expenseValue", amount(expenses));
  setText("investmentValue", amount(invested));
  setText("loanValue", amount(netLoanCashFlow));
  setText("allocatedValue", amount(summary.allocated_budget || 0));
  setText("availableAllocatedValue", amount(summary.available_allocated_budget || 0));

  setText(
    "savingRate",
    `${Math.max(0, (balance / denominator) * 100).toFixed(1)}%`,
  );

  setText(
    "spentPercent",
    `${cashIn > 0 ? Math.round(((expenses + loanCashOut) / cashIn) * 100) : 0}%`,
  );

  setText(
    "investedPercent",
    `${cashIn > 0 ? Math.round((investmentCashOut / cashIn) * 100) : 0}%`,
  );

  setText(
    "availablePercent",
    `${cashIn > 0 ? Math.max(0, Math.round((availableCash / cashIn) * 100)) : 0}%`,
  );

  const monthLabel = getMonthLabel(summary.month || selectedMonth);

  setText("periodText", monthLabel);
  setText("dateLabel", monthLabel);

  renderHeroProgress(expenses, Number(summary.investments?.invested || 0), availableCash, cashIn, cashOut);
}

/* =========================================
   Category Legend
========================================= */

function renderCategoryLegend(entries, colors = []) {
  const legend = getElement("categoryLegend");

  if (!legend) return;

  legend.replaceChildren();

  const list = Array.isArray(entries) ? entries : Object.entries(entries || {});

  if (!list.length) {
    legend.textContent = "No data recorded for this view.";
    return;
  }

  list.forEach(([category, total], index) => {
    const item = document.createElement("div");
    const marker = document.createElement("i");
    const label = document.createElement("span");
    const value = document.createElement("b");

    item.className = "legend-row";
    const color = colors[index % colors.length] || "#8fc8b5";
    marker.style.backgroundColor = color;
    marker.style.boxShadow = `0 0 0 2px ${color}33`;
    label.textContent = category;
    value.textContent = amount(total);

    item.append(marker, label, value);

    legend.appendChild(item);
  });
}

/* =========================================
   Hero Progress Bar
========================================= */

function renderHeroProgress(expenses, invested, balance, cashIn, cashOut) {
  const progress = document.querySelector(".hero-progress");

  if (!progress) return;

  const totalCashIn = cashIn || 1;
  const loanCashOut = Math.max(0, cashOut - expenses - invested);

  const spentPercentage = Math.max(
    0,
    Math.min(100, ((expenses + loanCashOut) / totalCashIn) * 100),
  );

  const investedPercentage = Math.max(
    0,
    Math.min(100 - spentPercentage, (invested / totalCashIn) * 100),
  );

  const availablePercentage = Math.max(
    0,
    Math.min(100 - spentPercentage - investedPercentage, Math.max(0, (balance / totalCashIn) * 100)),
  );

  const spans = progress.querySelectorAll("span");

  if (spans.length >= 3) {
    spans[0].style.width = `${spentPercentage}%`;
    spans[1].style.width = `${investedPercentage}%`;
    spans[2].style.width = `${availablePercentage}%`;
  }
}

/* =========================================
   Chart Rendering
========================================= */

function renderCashflowChart(labels, historyData) {
  const canvas = getElement("cashflowChart");

  if (!canvas || !window.Chart) return;

  if (cashflowChartInstance) {
    cashflowChartInstance.destroy();
    cashflowChartInstance = null;
  }

  let datasets = [];

  if (selectedCashflowView === "all_types") {
    // Generate datasets for all 8 transaction types using Overview palette
    datasets = OVERVIEW_TRANSACTION_TYPES.map((typeObj) => ({
      label: typeObj.label,
      data: historyData.map((item) => {
        if (!item || typeof item !== "object") return 0;
        if (item.type_breakdown && item.type_breakdown[typeObj.key] !== undefined) {
          return Number(item.type_breakdown[typeObj.key] || 0);
        }
        if (typeObj.key === "income") return Number(item.total_income || 0);
        if (typeObj.key === "expense") return Number(item.total_expenses || 0);
        if (typeObj.key === "investment") return Number(item.investments?.invested || 0);
        if (typeObj.key === "investment_return") return Number(item.investments?.returned || 0);
        if (typeObj.key === "loan_taken") return Number(item.loans?.borrowed || 0);
        if (typeObj.key === "loan_repaid") return Number(item.loans?.repaid || 0);
        if (typeObj.key === "loan_given") return Number(item.loans?.lent || 0);
        if (typeObj.key === "loan_collected") return Number(item.loans?.collected || 0);
        return 0;
      }),
      backgroundColor: typeObj.color,
      borderRadius: 4,
    }));

    // Keep active datasets that have values, or fallback to first two
    const active = datasets.filter((ds) => ds.data.some((val) => val > 0));
    datasets = active.length > 0 ? active : datasets.slice(0, 2);

  } else if (selectedCashflowView === "cash_flow") {
    datasets = [
      {
        label: "Cash Inflow",
        data: historyData.map((item) => Number(item?.total_cash_inflow ?? item?.total_income ?? 0)),
        backgroundColor: "#8fc8b5",
        borderRadius: 4,
      },
      {
        label: "Cash Outflow",
        data: historyData.map((item) => Number(item?.total_cash_outflow ?? item?.total_expenses ?? 0)),
        backgroundColor: "#ffb5ae",
        borderRadius: 4,
      },
      {
        label: "Net Cash Flow",
        data: historyData.map((item) => Number(item?.net_cash_flow ?? (Number(item?.total_income || 0) - Number(item?.total_expenses || 0)))),
        backgroundColor: "#bfd6f2",
        borderRadius: 4,
      },
    ];
  } else {
    // income_expense
    datasets = [
      {
        label: "Income",
        data: historyData.map((item) => Number(item?.total_income ?? 0)),
        backgroundColor: "#8fc8b5",
        borderRadius: 4,
      },
      {
        label: "Expenses",
        data: historyData.map((item) => Number(item?.total_expenses ?? 0)),
        backgroundColor: "#ffb5ae",
        borderRadius: 4,
      },
    ];
  }

  cashflowChartInstance = new Chart(canvas, {
    type: "bar",

    data: {
      labels,
      datasets,
    },

    options: {
      responsive: true,
      maintainAspectRatio: false,

      interaction: {
        intersect: false,
        mode: "index",
      },

      plugins: {
        legend: {
          position: "bottom",
          labels: {
            font: { family: "DM Sans", size: 11 },
            color: "#56636d",
            usePointStyle: true,
            boxWidth: 8,
          },
        },

        tooltip: {
          backgroundColor: "#111c2a",
          padding: 10,
          cornerRadius: 8,
          titleFont: { family: "Manrope", size: 12, weight: "700" },
          bodyFont: { family: "DM Sans", size: 11 },
          callbacks: {
            label(context) {
              return `${context.dataset.label}: ${amount(context.raw)}`;
            },
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
            callback(value) {
              return currency.format(value);
            },
          },
        },
        x: {
          grid: {
            display: false,
          },
          ticks: {
            font: { family: "Manrope", size: 11, weight: "600" },
            color: "#17202d",
          },
        },
      },
    },
  });
}

/* =========================================
   Spending & Distribution Doughnut Chart
========================================= */

function renderSpendingChart(summary = dashboardData) {
  const canvas = getElement("spendingChart");

  if (!canvas || !window.Chart || !summary) return;

  if (spendingChartInstance) {
    spendingChartInstance.destroy();
    spendingChartInstance = null;
  }

  const titleEl = getElement("pieChartTitle");
  const subEl = getElement("pieChartSubtitle");
  const centerTotalEl = getElement("categoryTotal");
  const centerLabelEl = getElement("categoryLabel");

  let entries = [];
  let colors = [];
  let totalAmount = 0;
  let centerLabelText = "All transaction types";

  if (selectedPieView === "all_types") {
    if (titleEl) titleEl.textContent = "Distribution breakdown";
    if (subEl) subEl.textContent = "All financial activity types for this month";
    centerLabelText = "All transaction types";

    const typeConfig = [
      ["Income", Number(summary.type_breakdown?.income ?? summary.total_income ?? 0), "#8fc8b5"],
      ["Expenses", Number(summary.type_breakdown?.expense ?? summary.total_expenses ?? 0), "#ffb5ae"],
      ["Investments", Number(summary.type_breakdown?.investment ?? summary.investments?.invested ?? 0), "#b8a6f4"],
      ["Investment Returns", Number(summary.type_breakdown?.investment_return ?? summary.investments?.returned ?? 0), "#bfd6f2"],
      ["Loans Borrowed", Number(summary.type_breakdown?.loan_taken ?? summary.loans?.borrowed ?? 0), "#f4d59c"],
      ["Loans Repaid", Number(summary.type_breakdown?.loan_repaid ?? summary.loans?.repaid ?? 0), "#e5b5d1"],
      ["Loans Lent", Number(summary.type_breakdown?.loan_given ?? summary.loans?.lent ?? 0), "#fae2b8"],
      ["Loans Collected", Number(summary.type_breakdown?.loan_collected ?? summary.loans?.collected ?? 0), "#9eafab"],
    ];

    const activeTypes = typeConfig.filter(([, val]) => val > 0);
    entries = activeTypes.map(([name, val]) => [name, val]);
    colors = activeTypes.map(([, , col]) => col);
    totalAmount = entries.reduce((acc, [, val]) => acc + val, 0);

  } else if (selectedPieView === "inflow_categories") {
    if (titleEl) titleEl.textContent = "Cash inflows by category";
    if (subEl) subEl.textContent = "Income, returns, borrowings & collections";
    centerLabelText = "Total inflows";

    const rawCats = summary.inflow_categories || (summary.total_income ? { Income: summary.total_income } : {});
    entries = Object.entries(rawCats).filter(([, val]) => Number(val) > 0);
    totalAmount = Number(summary.total_cash_inflow || summary.total_income || 0);
    colors = entries.map((_, i) => OVERVIEW_CHART_COLORS[i % OVERVIEW_CHART_COLORS.length]);

  } else {
    // outflow_categories (covers expenses, investments, repayments & lent amounts)
    if (titleEl) titleEl.textContent = "Cash outflows by category";
    if (subEl) subEl.textContent = "Expenses, investments, repayments & lent amounts";
    centerLabelText = "Total outflows";

    const rawCats = summary.outflow_categories || summary.category_breakdown || {};
    entries = Object.entries(rawCats).filter(([, val]) => Number(val) > 0);
    totalAmount = Number(summary.total_cash_outflow || summary.total_expenses || 0);
    colors = entries.map((_, i) => OVERVIEW_CHART_COLORS[i % OVERVIEW_CHART_COLORS.length]);
  }

  if (centerTotalEl) {
    centerTotalEl.textContent = amount(totalAmount);
  }
  if (centerLabelEl) {
    centerLabelEl.textContent = centerLabelText;
  }

  renderCategoryLegend(entries, colors);

  if (!entries.length) {
    return;
  }

  spendingChartInstance = new Chart(canvas, {
    type: "doughnut",

    data: {
      labels: entries.map(([category]) => category),

      datasets: [
        {
          data: entries.map(([, total]) => Number(total || 0)),
          backgroundColor: colors,
          borderWidth: 2,
          borderColor: "#ffffff",
          borderRadius: 4,
          spacing: 2,
        },
      ],
    },

    options: {
      responsive: true,
      maintainAspectRatio: false,
      cutout: "72%",

      plugins: {
        legend: {
          display: false,
        },

        tooltip: {
          backgroundColor: "#111c2a",
          padding: 10,
          cornerRadius: 8,
          titleFont: { family: "Manrope", size: 12, weight: "700" },
          bodyFont: { family: "DM Sans", size: 11 },
          callbacks: {
            label(context) {
              const val = context.raw || 0;
              const pct = totalAmount > 0 ? ((val / totalAmount) * 100).toFixed(1) : 0;
              return `${context.label}: ${amount(val)} (${pct}%)`;
            },
          },
        },
      },
    },
  });
}

/* =========================================
   Dashboard Lists
========================================= */

function renderDashboardLists(data) {
  renderTransactions(data.transactions || []);
  renderBudgets(data.budgets || [], data.category_breakdown || {}, data.transactions || []);
  renderGoals(data.goals || []);

  if (window.lucide) {
    window.lucide.createIcons();
  }
}

function renderTransactions(transactions) {
  const list = getElement("transactionList");

  if (!list) return;

  list.replaceChildren();

  if (!transactions.length) {
    list.textContent = "No transactions for this month.";
    return;
  }

  transactions.forEach((transaction) => {
    const item = document.createElement("div");
    const icon = document.createElement("div");
    const iconElement = document.createElement("i");
    const details = document.createElement("div");
    const name = document.createElement("div");
    const meta = document.createElement("div");
    const transactionAmount = document.createElement("div");
    const isIncome = transaction.transaction_type === "income";

    item.className = "transaction";
    icon.className = `tx-icon ${isIncome ? "blue" : "coral"}`;
    iconElement.setAttribute(
      "data-lucide",
      isIncome ? "arrow-down-left" : "arrow-up-right",
    );
    name.className = "tx-name";
    name.textContent = transaction.category || "Uncategorized";
    meta.className = "tx-meta";
    meta.textContent = `${transaction.description || "Transaction"} · ${
      transaction.date || ""
    }`;
    transactionAmount.className =
      `tx-amount ${isIncome ? "income" : "expense"}`;
    transactionAmount.textContent =
      `${isIncome ? "+" : "-"}${amount(transaction.amount)}`;

    icon.appendChild(iconElement);
    details.append(name, meta);
    item.append(icon, details, transactionAmount);

    list.appendChild(item);
  });
}

const DASHBOARD_CASH_OUTFLOW_TYPES = new Set(["expense", "investment", "loan_repaid", "loan_given"]);

function renderBudgets(budgets, categoryBreakdown, transactions = []) {
  const list = getElement("budgetList");

  if (!list) return;

  list.replaceChildren();

  if (!budgets.length) {
    list.textContent = "No budgets available.";
    return;
  }

  budgets.forEach((budget) => {
    const item = document.createElement("div");
    const top = document.createElement("div");
    const details = document.createElement("div");
    const name = document.createElement("div");
    const budgetAmount = document.createElement("div");
    const percentage = document.createElement("div");
    const track = document.createElement("div");
    const fill = document.createElement("span");
    const spent = transactions
      .filter((transaction) => {
        if (!DASHBOARD_CASH_OUTFLOW_TYPES.has(transaction.transaction_type)) {
          return false;
        }
        const category = String(transaction.category || "").toLowerCase();
        const budgetCategory = String(budget.category || "").toLowerCase();
        const categoryMatches = !budgetCategory || category === budgetCategory;
        const typeMatches = !budget.transaction_type
          || budget.transaction_type === "all"
          || transaction.transaction_type === budget.transaction_type;
        return categoryMatches && typeMatches;
      })
      .reduce((total, transaction) => total + Number(transaction.amount || 0), 0);
    const limit = Number(budget.amount || 0);
    const percentageUsed = limit > 0
      ? Math.min(100, (spent / limit) * 100)
      : 0;

    item.className = "budget-item";
    top.className = "budget-top";
    name.className = "budget-name";
    name.textContent = budget.category
      ? String(budget.category).replace(/\b\w/g, (c) => c.toUpperCase())
      : (budget.transaction_type === "all" ? "All cash outflows" : "All categories");
    budgetAmount.className = "budget-amount";
    budgetAmount.textContent =
      `${amount(spent)} spent of ${amount(limit)}`;
    percentage.className = "budget-percent";
    percentage.textContent = `${Math.round(percentageUsed)}%`;
    track.className = "track";
    fill.style.width = `${percentageUsed}%`;

    details.append(name, budgetAmount);
    top.append(details, percentage);
    track.appendChild(fill);
    item.append(top, track);

    list.appendChild(item);
  });
}

function renderGoals(goals) {
  const list = getElement("goalList");

  if (!list) return;

  list.replaceChildren();

  if (!goals.length) {
    list.textContent = "No financial goals available.";
    return;
  }

  goals.forEach((goal) => {
    const item = document.createElement("div");
    const icon = document.createElement("div");
    const iconElement = document.createElement("i");
    const details = document.createElement("div");
    const name = document.createElement("div");
    const money = document.createElement("div");
    const progress = document.createElement("div");
    const track = document.createElement("div");
    const fill = document.createElement("span");
    const percentage = document.createElement("small");
    const target = Number(goal.target_amount || 0);
    const current = Number(goal.current_amount || 0);
    const percentageComplete = target > 0
      ? Math.min(100, (current / target) * 100)
      : 0;

    item.className = "goal-item";
    icon.className = "goal-icon";
    iconElement.setAttribute("data-lucide", "target");
    name.className = "goal-name";
    name.textContent = goal.name || "Financial goal";
    money.className = "goal-money";
    money.textContent = `${amount(current)} / ${amount(target)}`;
    progress.className = "goal-progress";
    track.className = "track";
    fill.style.width = `${percentageComplete}%`;
    percentage.textContent = `${Math.round(percentageComplete)}%`;

    icon.appendChild(iconElement);
    track.appendChild(fill);
    progress.append(track, percentage);
    details.append(name, money, progress);
    item.append(icon, details);

    list.appendChild(item);
  });
}

/* =========================================
   API Request
========================================= */

async function fetchDashboard(month) {
  const response = await fetch(
    `${API_BASE_URL}/dashboard?month=${encodeURIComponent(month)}`,
  );

  if (!response.ok) {
    throw new Error(`Dashboard request failed: ${response.status}`);
  }

  return response.json();
}

/* =========================================
   Load Dashboard
========================================= */

async function loadDashboard(month = selectedMonth) {
  selectedMonth = month;

  setText("insightStatus", "Loading financial data...");

  try {
    const data = await fetchDashboard(month);

    dashboardData = data;

    renderSummary(data);
    renderDashboardLists(data);
    await addBudgetNotifications(data);

    renderSpendingChart(data);

    setText(
      "insightStatus",
      "Your financial dashboard is updated successfully.",
    );

    await loadCashflowHistory(selectedChartPeriod);

  } catch (error) {
    console.error("Dashboard loading error:", error);

    setText(
      "insightStatus",
      "Unable to load dashboard data. Please check the backend.",
    );

    setText("availableValue", "Unavailable");

    showToast("Unable to load dashboard. Check your backend.");
  }
}

/* =========================================
   Cashflow History
   Fetch last 6 or 12 months from API
========================================= */

function shiftMonth(month, offset) {
  const [year, monthNumber] = month.split("-").map(Number);

  const date = new Date(year, monthNumber - 1 + offset, 1);

  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}`;
}

function renderCashflowChartFromCache() {
  if (!cashflowHistoryCache || !cashflowHistoryCache.length) return;

  const labels = cashflowHistoryCache.map((data) =>
    new Date(`${data.month}-01T00:00:00`).toLocaleDateString(
      "en-IN",
      {
        month: "short",
        year: "2-digit",
      },
    ),
  );

  renderCashflowChart(labels, cashflowHistoryCache);
}

async function loadCashflowHistory(period = selectedChartPeriod) {
  selectedChartPeriod = Number(period);

  const months = [];

  for (let i = selectedChartPeriod - 1; i >= 0; i--) {
    months.push(shiftMonth(selectedMonth, -i));
  }

  try {
    const history = await Promise.all(
      months.map((month) => fetchDashboard(month)),
    );

    cashflowHistoryCache = history;
    renderCashflowChartFromCache();

  } catch (error) {
    console.error("Cashflow history error:", error);

    if (dashboardData) {
      cashflowHistoryCache = [dashboardData];
      renderCashflowChartFromCache();
    }
  }
}

/* =========================================
   Month Picker
========================================= */

function initializeMonthPicker() {
  const dateButton = getElement("dateBtn");

  if (!dateButton) return;

  const monthPicker = document.createElement("input");

  monthPicker.type = "month";
  monthPicker.value = selectedMonth;
  monthPicker.className = "month-picker";
  monthPicker.setAttribute("aria-label", "Select dashboard month");

  document.body.appendChild(monthPicker);

  dateButton.addEventListener("click", () => {
    monthPicker.classList.add("is-open");
    monthPicker.focus();

    if (typeof monthPicker.showPicker === "function") {
      monthPicker.showPicker();
    }
  });

  monthPicker.addEventListener("change", () => {
    if (!monthPicker.value) return;

    selectedMonth = monthPicker.value;

    monthPicker.classList.remove("is-open");

    void loadDashboard(selectedMonth);
  });

  monthPicker.addEventListener("blur", () => {
    monthPicker.classList.remove("is-open");
  });
}

/* =========================================
   Navigation Buttons
========================================= */

function navigateToPage(page) {
  const routes = {
    Transactions: "transactions.html",
    Budgets: "budgets.html",
    "AI Insights": "insights.html",
    "AI insights": "insights.html",
    "Financial Goals": "goals.html",
    "Financial goals": "goals.html",
    Analytics: "analytics.html",
    Reports: "reports.html",
    "Import data": "imports.html",
    Overview: "#overview",
  };

  const destination = routes[page];

  if (!destination) {
    showToast("Page is not available yet.");
    return;
  }

  if (destination.startsWith("#")) {
    const section = getElement(destination.substring(1));

    if (section) {
      section.scrollIntoView({
        behavior: "smooth",
        block: "start",
      });
    }

    return;
  }

  window.location.href = destination;
}

/* =========================================
   Sidebar Navigation
========================================= */

function initializeNavigation() {
  document.querySelectorAll(".nav a[data-page]").forEach((link) => {
    link.addEventListener("click", (event) => {
      event.preventDefault();

      const page = link.dataset.page;

      navigateToPage(page);

      document.querySelectorAll(".nav a").forEach((navLink) => {
        navLink.classList.remove("active");
      });

      link.classList.add("active");

      setText("crumb", page);

      getElement("sidebar")?.classList.remove("open");
    });
  });

  document.querySelectorAll("[data-go]").forEach((button) => {
    button.addEventListener("click", () => {
      navigateToPage(button.dataset.go);
    });
  });
}

/* =========================================
   Mobile Sidebar Menu
========================================= */

function initializeMobileMenu() {
  const menuButton = getElement("menuBtn");
  const sidebar = getElement("sidebar");

  if (!menuButton || !sidebar) return;

  menuButton.addEventListener("click", () => {
    const isOpen = sidebar.classList.toggle("open");

    menuButton.setAttribute(
      "aria-label",
      isOpen ? "Close navigation" : "Open navigation",
    );
  });
}

/* =========================================
   Notifications Button
========================================= */

function initializeNotifications() {
  const notifyButton = getElement("notifyBtn");

  if (!notifyButton) return;

  notifications = readNotifications();
  updateNotificationCount();
  notifyButton.addEventListener("click", () => {
    notifications = notifications.map((item) => ({ ...item, seen: true }));
    saveNotifications();
    updateNotificationCount();
    renderNotifications();
    getElement("notificationModal").hidden = false;
  });
  getElement("closeNotifications")?.addEventListener("click", () => {
    getElement("notificationModal").hidden = true;
  });
  getElement("notificationModal")?.addEventListener("click", (event) => {
    if (event.target === getElement("notificationModal")) getElement("notificationModal").hidden = true;
  });
  getElement("selectAllNotifications")?.addEventListener("change", (event) => {
    document.querySelectorAll("#notificationList input[data-notification-id]").forEach((input) => {
      input.checked = event.target.checked;
    });
  });
  getElement("deleteSelectedNotifications")?.addEventListener("click", () => {
    const selected = new Set(
      [...document.querySelectorAll("#notificationList input[data-notification-id]:checked")]
        .map((input) => input.dataset.notificationId),
    );
    notifications = notifications.filter((item) => !selected.has(item.id));
    saveNotifications();
    renderNotifications();
    updateNotificationCount();
    const selectAll = getElement("selectAllNotifications");
    if (selectAll) selectAll.checked = false;
  });
}

/* =========================================
   Profile Button
========================================= */

function initializeProfileButton() {
  const profileButton = getElement("profileBtn");

  if (!profileButton) return;

  profileButton.addEventListener("click", () => {
    const nameElement = document.querySelector("[data-user-name]");

    const userName =
      nameElement?.textContent.trim() || "User";

    showToast(`Signed in as ${userName}.`);
  });
}

/* =========================================
   Chart Controls (Period & View Modes)
========================================= */

function initializeChartControls() {
  const periodSelect = getElement("chartPeriod");

  if (periodSelect) {
    periodSelect.value = String(selectedChartPeriod);

    periodSelect.addEventListener("change", () => {
      const period = Number(periodSelect.value);

      if (![6, 12].includes(period)) {
        return;
      }

      void loadCashflowHistory(period);
    });
  }

  const cashflowViewSelect = getElement("cashflowViewMode");

  if (cashflowViewSelect) {
    cashflowViewSelect.value = selectedCashflowView;

    cashflowViewSelect.addEventListener("change", () => {
      selectedCashflowView = cashflowViewSelect.value;
      renderCashflowChartFromCache();
    });
  }

  const pieViewSelect = getElement("pieViewMode");

  if (pieViewSelect) {
    pieViewSelect.value = selectedPieView;

    pieViewSelect.addEventListener("change", () => {
      selectedPieView = pieViewSelect.value;
      if (dashboardData) {
        renderSpendingChart(dashboardData);
      }
    });
  }
}

/* =========================================
   CSV Report Export
========================================= */

function exportDashboardCSV() {
  if (!dashboardData) {
    showToast("Dashboard data is not available yet.");
    return;
  }

  const rows = [
    ["FinSight AI Financial Report"],
    ["Month", dashboardData.month || selectedMonth],
    [],
    ["Financial Summary"],
    ["Total Income", dashboardData.total_income || 0],
    ["Total Expenses", dashboardData.total_expenses || 0],
    ["Balance", dashboardData.balance || 0],
    [
      "Investments",
      dashboardData.investments?.net_invested || 0,
    ],
    ["Loan Payments", dashboardData.loans?.repaid || 0],
    [],
    ["Transactions"],
    ["Category", "Amount", "Date"],
  ];

  (dashboardData.transactions || []).forEach((transaction) => {
    rows.push([
      transaction.category || "Uncategorized",
      transaction.amount || 0,
      transaction.date || "",
    ]);
  });

  rows.push([], ["Budgets"]);
  rows.push(["Category", "Amount"]);

  (dashboardData.budgets || []).forEach((budget) => {
    rows.push([
      budget.category || "All categories",
      budget.amount || 0,
    ]);
  });

  rows.push([]);
  rows.push(["Financial Goals"]);
  rows.push(["Goal", "Current Amount", "Target Amount"]);

  (dashboardData.goals || []).forEach((goal) => {
    rows.push([
      goal.name || "",
      goal.current_amount || 0,
      goal.target_amount || 0,
    ]);
  });

  const csvContent = rows
    .map((row) =>
      row
        .map((value) => {
          const text = String(value ?? "");

          return `"${text.replace(/"/g, '""')}"`;
        })
        .join(","),
    )
    .join("\n");

  const blob = new Blob(
    ["\uFEFF" + csvContent],
    { type: "text/csv;charset=utf-8;" },
  );

  const url = URL.createObjectURL(blob);

  const link = document.createElement("a");

  link.href = url;

  link.download =
    `FinSight_Report_${dashboardData.month || selectedMonth}.csv`;

  document.body.appendChild(link);

  link.click();

  link.remove();

  URL.revokeObjectURL(url);

  showToast("Financial report downloaded successfully.");
}

/* =========================================
   Application Initialization
========================================= */

document.addEventListener("DOMContentLoaded", () => {
  setText("year", new Date().getFullYear());

  updateGreeting();

  if (window.lucide) {
    window.lucide.createIcons();
  }

  initializeMonthPicker();
  initializeNavigation();
  initializeMobileMenu();
  initializeNotifications();
  initializeProfileButton();
  initializeChartControls();

  void loadDashboard(selectedMonth);
});
