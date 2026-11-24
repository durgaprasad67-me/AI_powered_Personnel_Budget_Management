"use strict";
let budgets = [];
let knownTransactionCategories = [];
let budgetToDelete = null;
let deleteBudgetPreviousFocus = null;

const $ = (id) => document.getElementById(id);
const CUSTOM_CATEGORY_VALUE = "__custom__";

const BUDGET_CATEGORIES = [
  "food", "groceries", "transport", "bills", "rent", "shopping",
  "entertainment", "health", "education", "home", "utilities",
  "investment", "loan",
];

const BUDGET_CATEGORIES_BY_TYPE = {
  expense: ["food", "groceries", "transport", "bills", "rent", "shopping", "entertainment", "health", "education", "home", "utilities"],
  investment: ["investment"],
  loan_repaid: ["loan"],
  loan_given: ["loan"],
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

function updateOtherBudgetCategoryInput() {
  const input = $("budgetOtherCategory");
  if (!input) return;
  const isCustom = $("budgetCategory").value === CUSTOM_CATEGORY_VALUE;
  input.hidden = !isCustom;
  input.required = isCustom;
  if (!isCustom) {
    input.value = "";
  } else {
    input.focus();
  }
}

function initializeCategoryOptions(type = "expense", selected = "") {
  const baseCategories = BUDGET_CATEGORIES_BY_TYPE[type] || BUDGET_CATEGORIES;
  
  // Collect any custom categories from existing budgets and transactions
  const extraCategories = [...new Set([
    ...budgets.map((b) => b.category?.toLowerCase()),
    ...knownTransactionCategories,
  ].filter((c) => c && !baseCategories.includes(c)))].sort();

  let html = '<option value="">All categories</option>';
  baseCategories.forEach((category) => {
    html += `<option value="${category}">${category.replace(/\b\w/g, (letter) => letter.toUpperCase())}</option>`;
  });
  if (extraCategories.length > 0) {
    extraCategories.forEach((category) => {
      html += `<option value="${category}">${category.replace(/\b\w/g, (letter) => letter.toUpperCase())}</option>`;
    });
  }
  html += `<option value="${CUSTOM_CATEGORY_VALUE}">Custom category…</option>`;
  $("budgetCategory").innerHTML = html;

  const normalizedSelected = (selected || "").trim().toLowerCase();
  const allKnown = [...baseCategories, ...extraCategories];

  if (normalizedSelected && !allKnown.includes(normalizedSelected)) {
    $("budgetCategory").value = CUSTOM_CATEGORY_VALUE;
    if ($("budgetOtherCategory")) {
      $("budgetOtherCategory").value = selected;
    }
  } else if (normalizedSelected) {
    $("budgetCategory").value = normalizedSelected;
    if ($("budgetOtherCategory")) {
      $("budgetOtherCategory").value = "";
    }
  } else {
    $("budgetCategory").value = "";
    if ($("budgetOtherCategory")) {
      $("budgetOtherCategory").value = "";
    }
  }
  updateOtherBudgetCategoryInput();
}

function openBudget(item) {
  $("budgetModal").classList.add("show");
  $("modalTitle").textContent = item ? "Edit budget" : "Create budget";
  $("budgetId").value = item?.id || "";
  $("budgetType").value = item?.transaction_type || "expense";
  initializeCategoryOptions($("budgetType").value, item?.category || "");
  $("budgetAmount").value = item?.amount || "";
  $("budgetStart").value = item?.start_date || today();
  $("budgetEnd").value = item?.end_date || "";
}

function closeBudget() {
  $("budgetModal").classList.remove("show");
  $("budgetForm").reset();
  updateOtherBudgetCategoryInput();
}

function escapeHTML(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  })[char]);
}

async function renderBudgets() {
  const root = $("budgetCards");
  root.replaceChildren();
  if (!budgets.length) {
    root.innerHTML = '<div class="card empty">No budgets yet. Create your first budget to start tracking spending.</div>';
    return;
  }
  const cards = budgets.map((item) => {
    const card = document.createElement("article");
    card.className = "card budget-card";
    const categoryTitle = item.category
      ? item.category.replace(/\b\w/g, (c) => c.toUpperCase())
      : "All categories";
    card.innerHTML = `<div class="card-header"><h2>${escapeHTML(categoryTitle)}</h2></div><div class="budget-meta"><span>${escapeHTML(formatTypeLabel(item.transaction_type || "expense"))}</span><strong>${FinSight.money(item.amount)}</strong></div><div class="progress" aria-label="Budget usage loading"><span></span></div><div class="budget-meta progress-copy"><span>Loading actual spending…</span><span>${escapeHTML(item.start_date)}</span></div><div class="budget-actions"><button class="secondary edit" type="button">Edit</button><button class="danger delete" type="button">Delete</button></div>`;
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

async function loadBudgets() {
  $("budgetCards").innerHTML = '<div class="loading">Loading budgets…</div>';
  try {
    const [budgetData, txData] = await Promise.all([
      FinSight.api("/budgets?limit=100"),
      FinSight.api("/transactions?limit=100").catch(() => ({ items: [] })),
    ]);
    budgets = budgetData.items || [];
    knownTransactionCategories = [
      ...new Set(
        (txData.items || [])
          .map((t) => (t.category || "").trim().toLowerCase())
          .filter(Boolean)
      ),
    ];
    initializeCategoryOptions($("budgetType") ? $("budgetType").value : "expense");
    await renderBudgets();
    FinSight?.notifications?.checkBudgetAlerts?.();
  } catch (error) {
    $("budgetCards").innerHTML = `<div class="card empty">${escapeHTML(error.message)}</div>`;
  }
}

function formatTypeLabel(type) {
  const labels = {
    expense: "Expenses",
    investment: "Investments",
    loan_repaid: "Loan repayments",
    loan_given: "Loans given",
    all: "All cash outflows",
  };
  return labels[type] || (type ? type.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()) : "All cash outflows");
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

$("addBudget").addEventListener("click", () => openBudget());
$("closeBudget").addEventListener("click", closeBudget);
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

$("budgetType").addEventListener("change", () => {
  initializeCategoryOptions($("budgetType").value);
});

$("budgetCategory").addEventListener("change", updateOtherBudgetCategoryInput);

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

  const selectedCat = $("budgetCategory").value;
  let categoryValue = null;
  if (selectedCat === CUSTOM_CATEGORY_VALUE) {
    const customVal = $("budgetOtherCategory")
      ? $("budgetOtherCategory").value.trim().toLowerCase()
      : "";
    if (!customVal || customVal.length < 2 || customVal.length > 30) {
      FinSight.toast("Custom category must be between 2 and 30 characters.");
      $("budgetOtherCategory")?.focus();
      return;
    }
    categoryValue = customVal;
  } else if (selectedCat) {
    categoryValue = selectedCat.trim().toLowerCase();
  }

  const payload = {
    category: categoryValue,
    transaction_type: $("budgetType").value,
    amount,
    start_date: $("budgetStart").value,
    end_date: $("budgetEnd").value || null,
  };

  try {
    await FinSight.api(id ? `/budgets/${id}` : "/budgets", {
      method: id ? "PATCH" : "POST",
      body: JSON.stringify(payload),
    });
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
