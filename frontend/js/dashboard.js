
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

  toast.textContent = message;
  toast.classList.add("show");

  clearTimeout(toastTimeout);

  toastTimeout = setTimeout(() => {
    toast.classList.remove("show");
  }, 3000);
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
  const userName = nameElement?.textContent.trim() || "User";

  setText("greetingTitle", `${greeting}, ${userName} 👋`);

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

  const loanPayments = Number(
    summary.loans?.repaid || 0,
  );

  const denominator = income || 1;

  setText("availableValue", amount(balance));
  setText("incomeValue", amount(income));
  setText("expenseValue", amount(expenses));
  setText("investmentValue", amount(invested));
  setText("loanValue", amount(loanPayments));

  setText("categoryTotal", amount(expenses));

  setText(
    "savingRate",
    `${Math.max(0, (balance / denominator) * 100).toFixed(1)}%`,
  );

  setText(
    "spentPercent",
    `${Math.round((expenses / denominator) * 100)}%`,
  );

  setText(
    "investedPercent",
    `${Math.round((invested / denominator) * 100)}%`,
  );

  setText(
    "availablePercent",
    `${Math.max(0, Math.round((balance / denominator) * 100))}%`,
  );

  const monthLabel = getMonthLabel(summary.month || selectedMonth);

  setText("periodText", monthLabel);
  setText("dateLabel", monthLabel);

  renderCategoryLegend(summary.category_breakdown || {});
  renderHeroProgress(expenses, invested, balance, income);
}

/* =========================================
   Category Legend
========================================= */

function renderCategoryLegend(categoryBreakdown) {
  const legend = getElement("categoryLegend");

  if (!legend) return;

  legend.replaceChildren();

  const entries = Object.entries(categoryBreakdown);

  if (!entries.length) {
    legend.textContent = "No expense categories for this month.";
    return;
  }

  entries.forEach(([category, total]) => {
    const item = document.createElement("div");
    const marker = document.createElement("i");
    const label = document.createElement("span");
    const value = document.createElement("b");

    item.className = "legend-row";
    marker.style.backgroundColor = "#8eb3a4";
    label.textContent = category;
    value.textContent = amount(total);

    item.append(marker, label, value);

    legend.appendChild(item);
  });
}

/* =========================================
   Hero Progress Bar
========================================= */

function renderHeroProgress(expenses, invested, balance, income) {
  const progress = document.querySelector(".hero-progress");

  if (!progress) return;

  const totalIncome = income || 1;

  const spentPercentage = Math.max(
    0,
    Math.min(100, (expenses / totalIncome) * 100),
  );

  const investedPercentage = Math.max(
    0,
    Math.min(100 - spentPercentage, (invested / totalIncome) * 100),
  );

  const availablePercentage = Math.max(
    0,
    100 - spentPercentage - investedPercentage,
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

function renderCashflowChart(labels, incomes, expenses) {
  const canvas = getElement("cashflowChart");

  if (!canvas || !window.Chart) return;

  if (cashflowChartInstance) {
    cashflowChartInstance.destroy();
  }

  cashflowChartInstance = new Chart(canvas, {
    type: "bar",

    data: {
      labels,

      datasets: [
        {
          label: "Income",
          data: incomes,
          backgroundColor: "#8fc8b5",
          borderRadius: 6,
        },

        {
          label: "Expenses",
          data: expenses,
          backgroundColor: "#ffb5ae",
          borderRadius: 6,
        },
      ],
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
        },

        tooltip: {
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

          ticks: {
            callback(value) {
              return currency.format(value);
            },
          },
        },
      },
    },
  });
}

/* =========================================
   Spending Doughnut Chart
========================================= */

function renderSpendingChart(categoryBreakdown) {
  const canvas = getElement("spendingChart");

  if (!canvas || !window.Chart) return;

  if (spendingChartInstance) {
    spendingChartInstance.destroy();
  }

  const entries = Object.entries(categoryBreakdown || {});

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

          backgroundColor: [
            "#8fc8b5",
            "#ffb5ae",
            "#b8a6f4",
            "#bfd6f2",
            "#f4d59c",
            "#9eafab",
            "#e5b5d1",
          ],

          borderWidth: 2,
          borderColor: "#ffffff",
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
          callbacks: {
            label(context) {
              return `${context.label}: ${amount(context.raw)}`;
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
  renderBudgets(data.budgets || [], data.category_breakdown || {});
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

function renderBudgets(budgets, categoryBreakdown) {
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
    const spent = Number(
      categoryBreakdown[String(budget.category || "").toLowerCase()] || 0,
    );
    const limit = Number(budget.amount || 0);
    const percentageUsed = limit > 0
      ? Math.min(100, (spent / limit) * 100)
      : 0;

    item.className = "budget-item";
    top.className = "budget-top";
    name.className = "budget-name";
    name.textContent = budget.name || "Budget";
    budgetAmount.className = "budget-amount";
    budgetAmount.textContent =
      `${amount(spent)} spent of ${amount(limit)} · ${budget.period || "monthly"}`;
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

    renderSpendingChart(data.category_breakdown || {});

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

async function loadCashflowHistory(period = 6) {
  selectedChartPeriod = Number(period);

  const months = [];

  for (let i = selectedChartPeriod - 1; i >= 0; i--) {
    months.push(shiftMonth(selectedMonth, -i));
  }

  try {
    const history = await Promise.all(
      months.map((month) => fetchDashboard(month)),
    );

    const labels = history.map((data) =>
      new Date(`${data.month}-01T00:00:00`).toLocaleDateString(
        "en-IN",
        {
          month: "short",
          year: "2-digit",
        },
      ),
    );

    const incomes = history.map((data) =>
      Number(data.total_income || 0),
    );

    const expenses = history.map((data) =>
      Number(data.total_expenses || 0),
    );

    renderCashflowChart(labels, incomes, expenses);

  } catch (error) {
    console.error("Cashflow history error:", error);

    if (dashboardData) {
      renderCashflowChart(
        [getMonthLabel(dashboardData.month || selectedMonth)],
        [Number(dashboardData.total_income || 0)],
        [Number(dashboardData.total_expenses || 0)],
      );
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
    "Financial Goals": "goals.html",
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

  notifyButton.addEventListener("click", () => {
    showToast("You are all caught up! No new notifications.");
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
   Chart Period Dropdown
========================================= */

function initializeChartPeriod() {
  const periodSelect = getElement("chartPeriod");

  if (!periodSelect) return;

  periodSelect.value = String(selectedChartPeriod);

  periodSelect.addEventListener("change", () => {
    const period = Number(periodSelect.value);

    if (![6, 12].includes(period)) {
      return;
    }

    void loadCashflowHistory(period);
  });
}

/* =========================================
   Ask FinSight AI
========================================= */

function initializeAskAI() {
  const askButton = getElement("askAI");

  if (!askButton) return;

  askButton.addEventListener("click", () => {
    window.location.href = `chat.html?month=${encodeURIComponent(selectedMonth)}`;
  });
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
  rows.push(["Name", "Amount", "Period"]);

  (dashboardData.budgets || []).forEach((budget) => {
    rows.push([
      budget.name || "",
      budget.amount || 0,
      budget.period || "",
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
  initializeChartPeriod();
  initializeAskAI();

  void loadDashboard(selectedMonth);
});
