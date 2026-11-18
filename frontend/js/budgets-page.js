"use strict";
let budgets = [];
let budgetToDelete = null;
let deleteBudgetPreviousFocus = null;
const $ = (id) => document.getElementById(id);
const BUDGET_CATEGORIES = [
  "food", "groceries", "transport", "bills", "rent", "shopping",
  "entertainment", "health", "education", "home", "utilities", "salary",
  "freelance", "interest", "refund", "investment", "investment return",
  "loan return", "loan",
];
const BUDGET_CATEGORIES_BY_TYPE = {
  income: ["salary", "freelance", "interest", "refund"],
  expense: ["food", "groceries", "transport", "bills", "rent", "shopping", "entertainment", "health", "education", "home", "utilities"],
  investment: ["investment"],
  investment_return: ["investment"],
  loan_taken: ["loan"],
  loan_repaid: ["loan"],
  loan_given: ["loan"],
  loan_collected: ["loan"],
  all: BUDGET_CATEGORIES,
};
const today = () => new Date().toISOString().slice(0, 10);
function showBudgetWarning(message) {
  const modal = $("budgetWarningModal");
  $("budgetWarningMessage").textContent = message;
  modal.hidden = false;
  $("closeBudgetWarning").focus();
}
function closeBudgetWarning() {
  $("budgetWarningModal").hidden = true;
}
function initializeCategoryOptions(type = "expense", selected = "") {
  const categories = BUDGET_CATEGORIES_BY_TYPE[type] || BUDGET_CATEGORIES;
  $("budgetCategory").innerHTML = '<option value="">All categories</option>'
    + categories.map((category) => `<option value="${category}">${category.replace(/\b\w/g, (letter) => letter.toUpperCase())}</option>`).join("");
  $("budgetCategory").value = categories.includes(selected) ? selected : "";
}
function openBudget(item) { $("budgetModal").classList.add("show"); $("modalTitle").textContent = item ? "Edit budget" : "Create budget"; $("budgetId").value = item?.id || ""; $("budgetType").value = item?.transaction_type || "expense"; initializeCategoryOptions($("budgetType").value, item?.category || ""); $("budgetAmount").value = item?.amount || ""; $("budgetStart").value = item?.start_date || today(); $("budgetEnd").value = item?.end_date || ""; }
function closeBudget() { $("budgetModal").classList.remove("show"); $("budgetForm").reset(); }
function escapeHTML(value) { return String(value ?? "").replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char]); }
async function renderBudgets() {
  const root = $("budgetCards");
  root.replaceChildren();
  if (!budgets.length) { root.innerHTML = '<div class="card empty">No budgets yet. Create your first budget to start tracking spending.</div>'; return; }
  const cards = budgets.map((item) => {
    const card = document.createElement("article");
    card.className = "card budget-card";
    card.innerHTML = `<div class="card-header"><h2>${escapeHTML(item.category || "All categories")}</h2></div><div class="budget-meta"><span>${escapeHTML(item.transaction_type || "expense")}</span><strong>${FinSight.money(item.amount)}</strong></div><div class="progress" aria-label="Budget usage loading"><span></span></div><div class="budget-meta progress-copy"><span>Loading actual spending…</span><span>${escapeHTML(item.start_date)}</span></div><div class="budget-actions"><button class="secondary edit" type="button">Edit</button><button class="danger delete" type="button">Delete</button></div>`;
    card.querySelector(".edit").addEventListener("click", () => openBudget(item));
    card.querySelector(".delete").addEventListener("click", () => requestDeleteBudget(item));
    root.appendChild(card);
    return { item, card };
  });
  await Promise.all(cards.map(async ({ item, card }) => {
    const progress = card.querySelector(".progress");
    const copy = card.querySelector(".progress-copy");
    try {
      const data = await FinSight.api(`/budgets/${encodeURIComponent(item.id)}/progress`);
      const percent = Math.max(0, Number(data.percentage_used || 0));
      const fill = progress.querySelector("span");
      fill.style.width = `${Math.min(100, percent)}%`;
      fill.classList.toggle("over-budget", data.is_over_budget);
      progress.setAttribute("aria-label", `${percent.toFixed(0)} percent of budget used`);
      copy.firstElementChild.textContent = `${FinSight.money(data.spent_amount)} spent · ${FinSight.money(data.remaining_amount)} remaining`;
      copy.lastElementChild.textContent = `${percent.toFixed(0)}% used`;
      copy.lastElementChild.classList.toggle("over-budget-text", data.is_over_budget);
    } catch (error) {
      copy.firstElementChild.textContent = "Spending progress unavailable";
      progress.setAttribute("aria-label", "Budget usage unavailable");
    }
  }));
}
async function loadBudgets() { $("budgetCards").innerHTML = '<div class="loading">Loading budgets…</div>'; try { const data = await FinSight.api("/budgets?limit=100"); budgets = data.items || []; await renderBudgets(); } catch (error) { $("budgetCards").innerHTML = `<div class="card empty">${escapeHTML(error.message)}</div>`; } }
function formatTypeLabel(type) {
  const labels = {
    expense: "Expenses",
    income: "Income",
    investment: "Investments",
    investment_return: "Investment returns",
    loan_taken: "Loan returns received",
    loan_repaid: "Loan repayments",
    loan_given: "Loans given",
    loan_collected: "Loan returns collected",
    all: "All transaction types",
  };
  return labels[type] || (type ? type.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()) : "All transaction types");
}

function requestDeleteBudget(item) {
  budgetToDelete = item;
  deleteBudgetPreviousFocus = document.activeElement;

  const categoryName = item.category
    ? item.category.replace(/\b\w/g, (c) => c.toUpperCase())
    : "All Categories";
  const typeLabel = formatTypeLabel(item.transaction_type);
  const dateText = item.end_date
    ? `${item.start_date} to ${item.end_date}`
    : `From ${item.start_date}`;

  $("deleteBudgetTitle").textContent = `Delete ${categoryName} budget?`;
  $("deleteBudgetMessage").textContent = `Are you sure you want to delete this budget? Spending tracking and limits for this allocation will no longer be enforced.`;
  $("deleteBudgetDetails").innerHTML = `
    <div class="confirm-budget-row">
      <span>Category:</span>
      <strong>${escapeHTML(categoryName)}</strong>
    </div>
    <div class="confirm-budget-row">
      <span>Allocated Amount:</span>
      <strong>${FinSight.money(item.amount)}</strong>
    </div>
    <div class="confirm-budget-row">
      <span>Applies To:</span>
      <strong>${escapeHTML(typeLabel)}</strong>
    </div>
    <div class="confirm-budget-row">
      <span>Active Period:</span>
      <strong>${escapeHTML(dateText)}</strong>
    </div>
  `;

  const modal = $("deleteBudgetModal");
  modal.classList.add("show");
  $("confirmDeleteBudget").disabled = false;
  $("confirmDeleteBudget").textContent = "Yes, delete budget";
  $("confirmDeleteBudget").focus();
}

function closeDeleteBudgetModal() {
  const modal = $("deleteBudgetModal");
  if (modal) modal.classList.remove("show");
  budgetToDelete = null;
  if (deleteBudgetPreviousFocus && typeof deleteBudgetPreviousFocus.focus === "function") {
    deleteBudgetPreviousFocus.focus();
  }
  deleteBudgetPreviousFocus = null;
}

async function confirmDeleteBudgetAction() {
  if (!budgetToDelete) return;
  const target = budgetToDelete;
  const confirmBtn = $("confirmDeleteBudget");
  confirmBtn.disabled = true;
  confirmBtn.textContent = "Deleting…";

  try {
    await FinSight.api(`/budgets/${target.id}`, { method: "DELETE" });
    closeDeleteBudgetModal();
    await loadBudgets();

    const categoryName = target.category
      ? target.category.replace(/\b\w/g, (c) => c.toUpperCase())
      : "All Categories";
    const typeLabel = formatTypeLabel(target.transaction_type);

    FinSight.showTopPopup({
      title: "Budget Deleted",
      message: `The ${categoryName} budget (${FinSight.money(target.amount)}) was deleted successfully.`,
      type: "success",
      meta: [
        { label: "Category", value: categoryName },
        { label: "Amount", value: FinSight.money(target.amount) },
        { label: "Applies To", value: typeLabel },
      ],
      duration: 6000,
    });
  } catch (error) {
    confirmBtn.disabled = false;
    confirmBtn.textContent = "Yes, delete budget";
    FinSight.showTopPopup({
      title: "Delete Failed",
      message: error.message,
      type: "error",
    });
  }
}

$("addBudget").addEventListener("click", () => openBudget()); $("closeBudget").addEventListener("click", closeBudget);
$("closeBudgetWarning").addEventListener("click", closeBudgetWarning);
$("budgetWarningModal").addEventListener("click", (event) => {
  if (event.target === $("budgetWarningModal")) closeBudgetWarning();
});
$("cancelDeleteBudget").addEventListener("click", closeDeleteBudgetModal);
$("confirmDeleteBudget").addEventListener("click", () => void confirmDeleteBudgetAction());
$("deleteBudgetModal").addEventListener("click", (event) => {
  if (event.target === $("deleteBudgetModal")) closeDeleteBudgetModal();
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    if ($("deleteBudgetModal") && $("deleteBudgetModal").classList.contains("show")) {
      closeDeleteBudgetModal();
    } else if ($("budgetWarningModal") && !$("budgetWarningModal").hidden) {
      closeBudgetWarning();
    }
  }
});
$("budgetType").addEventListener("change", () => initializeCategoryOptions($("budgetType").value));
$("budgetForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const id = $("budgetId").value;
  const amount = Number($("budgetAmount").value);
  if (!Number.isFinite(amount) || amount <= 0) {
    FinSight.toast("Enter a budget amount greater than ₹0.");
    return;
  }
  if (amount > FinSight.MAX_AMOUNT) {
    FinSight.toast("Budget cannot exceed ₹100,000,000.");
    return;
  }
  const payload = { category: $("budgetCategory").value || null, transaction_type: $("budgetType").value, amount, start_date: $("budgetStart").value, end_date: $("budgetEnd").value || null };
  try {
    await FinSight.api(id ? `/budgets/${id}` : "/budgets", { method: id ? "PATCH" : "POST", body: JSON.stringify(payload) });
    closeBudget();
    await loadBudgets();
    FinSight.toast("Budget saved.", "success");
  } catch (error) {
    if (error.message.startsWith("Budget plan conflict:")) {
      showBudgetWarning(error.message);
    } else {
      FinSight.toast(error.message);
    }
  }
});
initializeCategoryOptions();
void loadBudgets();
