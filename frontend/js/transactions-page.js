"use strict";

let transactionItems = [];
let currentPage = 1;
const pageSize = 5;
const tx$ = (id) => document.getElementById(id);
const CATEGORY_OPTIONS = [
  "food", "groceries", "transport", "bills", "rent", "shopping",
  "entertainment", "health", "education", "home", "utilities", "salary",
  "freelance", "interest", "refund", "investment", "loan",
];
const CUSTOM_CATEGORY_VALUE = "__custom__";
const TRANSACTION_TYPE_LABELS = {
  investment_return: "Investment return",
  loan_taken: "Loan taken",
  loan_repaid: "Loan repaid",
  loan_given: "Loan given",
  loan_collected: "Loan collected",
};
const CATEGORIES_BY_TYPE = {
  income: ["salary", "freelance", "interest", "refund"],
  expense: ["food", "groceries", "transport", "bills", "rent", "shopping", "entertainment", "health", "education", "home", "utilities"],
  investment: ["investment"],
  investment_return: ["investment return", "investment"],
  loan_taken: ["loan"],
  loan_repaid: ["loan"],
  loan_given: ["loan"],
  loan_collected: ["loan return", "loan"],
};
let transactionToDelete = null;
let deleteModalPreviousFocus = null;
let currentLimitData = null;

function clearFieldErrors() {
  ["transactionDate", "transactionType", "transactionAmount", "transactionCategory", "transactionDescription"].forEach((field) => {
    const errorEl = tx$(`${field}Error`);
    if (errorEl) errorEl.textContent = "";
    const inputEl = tx$(field);
    if (inputEl) inputEl.classList.remove("has-error");
  });
  const customInput = tx$("transactionOtherCategory");
  if (customInput) customInput.classList.remove("has-error");
}

function setFieldError(field, message) {
  let errorEl = null;
  let inputEl = null;

  if (field === "date") {
    errorEl = tx$("transactionDateError");
    inputEl = tx$("transactionDate");
  } else if (field === "transaction_type" || field === "type") {
    errorEl = tx$("transactionTypeError");
    inputEl = tx$("transactionType");
  } else if (field === "amount") {
    errorEl = tx$("transactionAmountError");
    inputEl = tx$("transactionAmount");
  } else if (field === "category") {
    errorEl = tx$("transactionCategoryError");
    inputEl = tx$("transactionCategory").value === CUSTOM_CATEGORY_VALUE ? tx$("transactionOtherCategory") : tx$("transactionCategory");
  } else if (field === "description") {
    errorEl = tx$("transactionDescriptionError");
    inputEl = tx$("transactionDescription");
  } else {
    FinSight.showTopPopup({
      title: "Transaction Issue",
      message: message,
      type: "error",
    });
    return;
  }

  if (errorEl) errorEl.textContent = message;
  if (inputEl) inputEl.classList.add("has-error");
}

async function fetchDynamicBudgetLimit() {
  const type = tx$("transactionType").value;
  const category = selectedCategory();
  const date = tx$("transactionDate").value || today();
  const id = tx$("transactionId").value;
  const amountInput = tx$("transactionAmount");

  try {
    const query = new URLSearchParams({
      transaction_type: type,
      date,
    });
    if (category) query.set("category", category);
    if (id) query.set("exclude_id", id);

    const data = await FinSight.api(`/transactions/budget-limit?${query}`);
    currentLimitData = data;

    if (data.max_allowed != null) {
      amountInput.max = data.max_allowed;
    } else {
      amountInput.removeAttribute("max");
    }

    const enteredAmount = Number(amountInput.value);
    if (data.has_budget && data.remaining_budget != null) {
      if (enteredAmount > 0 && enteredAmount > data.remaining_budget) {
        const diff = enteredAmount - data.remaining_budget;
        setFieldError("amount", `Exceeds remaining budget by ${FinSight.money(diff)}.`);
        FinSight.showTopPopup({
          title: "Budget Limit Exceeded",
          message: `Remaining budget for ${category || "this category"} in ${data.month} is ${FinSight.money(data.remaining_budget)} (allocated: ${FinSight.money(data.allocated_budget)}, spent: ${FinSight.money(data.spent_amount)}). This transaction of ${FinSight.money(enteredAmount)} exceeds your available budget by ${FinSight.money(diff)}.`,
          meta: [
            { label: "Month", value: data.month },
            { label: "Allocated", value: FinSight.money(data.allocated_budget) },
            { label: "Spent", value: FinSight.money(data.spent_amount) },
            { label: "Remaining", value: FinSight.money(data.remaining_budget) },
            { label: "Exceeded By", value: FinSight.money(diff), highlight: true },
          ],
          type: "warning",
        });
      } else if (data.remaining_budget <= 0) {
        FinSight.showTopPopup({
          title: "Budget Fully Exhausted",
          message: `The budget for ${category || "all categories"} in ${data.month} is fully spent (allocated: ${FinSight.money(data.allocated_budget)}, spent: ${FinSight.money(data.spent_amount)}). There is ₹0.00 remaining, so any new outflow will exceed the budget limit.`,
          meta: [
            { label: "Month", value: data.month },
            { label: "Allocated", value: FinSight.money(data.allocated_budget) },
            { label: "Spent", value: FinSight.money(data.spent_amount) },
            { label: "Remaining", value: "₹0.00", highlight: true },
          ],
          type: "warning",
        });
      }
    } else if (data.warning && !data.has_budget) {
      FinSight.showTopPopup({
        title: "No Budget Set",
        message: `${data.warning} Transactions for this month will be recorded without a spending limit.`,
        meta: [
          { label: "Month", value: data.month },
          { label: "Status", value: "Unrestricted" },
        ],
        type: "info",
        duration: 7000,
      });
    }
  } catch (err) {
    currentLimitData = null;
  }
}

function today() {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Kolkata",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(new Date());
  const dateParts = Object.fromEntries(
    parts.map(({ type, value }) => [type, value]),
  );
  return `${dateParts.year}-${dateParts.month}-${dateParts.day}`;
}

function selectedTransactions() {
  const search = tx$("search").value.trim().toLowerCase();
  const type = tx$("type").value;
  const category = tx$("category").value;
  const month = tx$("month").value;

  return transactionItems.filter((item) => {
    const searchable = `${item.description || ""} ${item.category || ""}`.toLowerCase();
    const categoryMatches = category === "__other__"
      ? (!CATEGORY_OPTIONS.includes(item.category) || item.category === "other")
      : (!category || item.category === category);
    return (!search || searchable.includes(search))
      && (!type || item.transaction_type === type)
      && categoryMatches
      && (!month || String(item.date).startsWith(month));
  });
}

function renderTransactionStats(items) {
  const income = items
    .filter((item) => item.transaction_type === "income")
    .reduce((total, item) => total + Number(item.amount || 0), 0);
  const expenses = items
    .filter((item) => item.transaction_type === "expense")
    .reduce((total, item) => total + Number(item.amount || 0), 0);
  const cashInTypes = new Set(["income", "investment_return", "loan_taken", "loan_collected"]);
  const cashOutTypes = new Set(["expense", "investment", "loan_repaid", "loan_given"]);
  const cashIn = items
    .filter((item) => cashInTypes.has(item.transaction_type))
    .reduce((total, item) => total + Number(item.amount || 0), 0);
  const cashOut = items
    .filter((item) => cashOutTypes.has(item.transaction_type))
    .reduce((total, item) => total + Number(item.amount || 0), 0);
  const stats = [
    ["Total transactions", items.length],
    ["Total income", FinSight.money(income)],
    ["Total expenses", FinSight.money(expenses)],
    ["Net cash flow", FinSight.money(cashIn - cashOut)],
  ];
  tx$("transactionStats").innerHTML = stats
    .map(([label, value]) => `<article class="card stat-card"><div class="stat-label">${label}</div><div class="stat-value">${value}</div></article>`)
    .join("");
}

function renderCategoryOptions(type = "") {
  const category = tx$("category");
  const selected = category.value;
  const allowedCategories = type
    ? (CATEGORIES_BY_TYPE[type] || [])
    : CATEGORY_OPTIONS;
  const customValues = [...new Set(transactionItems.map((item) => item.category).filter(
    (value) => value
      && allowedCategories.includes(value) === false
      && (!type || transactionItems.some((item) => item.category === value && item.transaction_type === type)),
  ))]
    .sort((left, right) => left.localeCompare(right));
  category.innerHTML = '<option value="">All categories</option>';
  allowedCategories.forEach((value) => {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = value[0].toUpperCase() + value.slice(1);
    category.appendChild(option);
  });
  customValues.forEach((value) => {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = value;
    category.appendChild(option);
  });
  category.value = [...allowedCategories, ...customValues].includes(selected)
    ? selected
    : "";
}

function updateTransactionCategories(categoryValue = "") {
  const select = tx$("transactionCategory");
  const customInput = tx$("transactionOtherCategory");
  const selected = categoryValue
    || (select.value === CUSTOM_CATEGORY_VALUE ? customInput?.value.trim() : select.value);
  const categories = CATEGORIES_BY_TYPE[tx$("transactionType").value] || [];
  select.innerHTML = '<option value="">Select category</option>';
  categories.forEach((value) => {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = value.replace(/\b\w/g, (letter) => letter.toUpperCase());
    select.appendChild(option);
  });
  const isCustom = selected && !categories.includes(selected);
  const customOption = document.createElement("option");
  customOption.value = CUSTOM_CATEGORY_VALUE;
  customOption.textContent = "Custom";
  select.appendChild(customOption);
  select.value = isCustom ? CUSTOM_CATEGORY_VALUE : selected;
  if (customInput && isCustom) customInput.value = selected;
  updateOtherCategoryInput();
}

function renderTransactions() {
  const filtered = selectedTransactions();
  const pageCount = Math.max(1, Math.ceil(filtered.length / pageSize));
  currentPage = Math.min(currentPage, pageCount);
  const visible = filtered.slice((currentPage - 1) * pageSize, currentPage * pageSize);

  renderTransactionStats(filtered);
  tx$("transactionCount").textContent = `Showing ${visible.length} of ${filtered.length} transactions`;
  tx$("previousPage").disabled = currentPage === 1;
  tx$("nextPage").disabled = currentPage === pageCount;

  const rows = tx$("transactionRows");
  rows.replaceChildren();
  if (!visible.length) {
    rows.innerHTML = '<tr><td class="empty" colspan="6">No transactions found.</td></tr>';
    return;
  }

  visible.forEach((item) => {
    const row = document.createElement("tr");
    const dateCell = document.createElement("td");
    dateCell.textContent = String(item.date || "");
    const descriptionCell = document.createElement("td");
    descriptionCell.textContent = String(item.description || "");
    const categoryCell = document.createElement("td");
    const categoryBadge = document.createElement("span");
    categoryBadge.className = "badge";
    categoryBadge.textContent = String(item.category || "");
    categoryCell.appendChild(categoryBadge);
    const typeCell = document.createElement("td");
    const typeBadge = document.createElement("span");
    typeBadge.className = "badge";
    typeBadge.textContent = TRANSACTION_TYPE_LABELS[item.transaction_type]
      || String(item.transaction_type || "").replaceAll("_", " ");
    typeCell.appendChild(typeBadge);
    const amountCell = document.createElement("td");
    amountCell.textContent = FinSight.money(item.amount);
    const actionsCell = document.createElement("td");
    const actions = document.createElement("div");
    actions.className = "row-actions";
    const editButton = document.createElement("button");
    editButton.className = "secondary edit";
    editButton.type = "button";
    editButton.textContent = "Edit";
    editButton.addEventListener("click", () => openTransaction(item));
    const deleteButton = document.createElement("button");
    deleteButton.className = "danger delete";
    deleteButton.type = "button";
    deleteButton.textContent = "Delete";
    deleteButton.addEventListener("click", () => removeTransaction(item.id));
    actions.append(editButton, deleteButton);
    actionsCell.appendChild(actions);
    row.append(dateCell, descriptionCell, categoryCell, typeCell, amountCell, actionsCell);
    rows.appendChild(row);
  });
}

function openTransaction(item = null) {
  clearFieldErrors();
  tx$("transactionModal").classList.add("show");
  tx$("transactionTitle").textContent = item ? "Edit transaction" : "Add transaction";
  tx$("saveTransaction").textContent = item ? "Update transaction" : "Save transaction";
  tx$("transactionId").value = item?.id || "";
  const initialDate = item?.date || today();
  tx$("transactionDate").value = initialDate;
  tx$("transactionDate").max = today();
  tx$("transactionType").value = item?.transaction_type || "expense";
  updateTransactionCategories(item?.category || "");
  tx$("transactionAmount").value = item?.amount || "";
  const category = item?.category || "";
  if (category && !CATEGORIES_BY_TYPE[tx$("transactionType").value]?.includes(category)) {
    tx$("transactionCategory").value = CUSTOM_CATEGORY_VALUE;
    tx$("transactionOtherCategory").value = category;
  }
  updateOtherCategoryInput();
  tx$("transactionDescription").value = item?.description || "";
  void fetchDynamicBudgetLimit();
}

function closeTransaction() {
  clearFieldErrors();
  tx$("transactionModal").classList.remove("show");
  tx$("transactionForm").reset();
  tx$("transactionId").value = "";
  tx$("saveTransaction").textContent = "Save transaction";
  updateOtherCategoryInput();
  currentLimitData = null;
}

function updateOtherCategoryInput() {
  const input = tx$("transactionOtherCategory");
  if (!input) return;
  const isCustom = tx$("transactionCategory").value === CUSTOM_CATEGORY_VALUE;
  input.hidden = !isCustom;
  input.required = isCustom;
  if (!isCustom) input.value = "";
}

function selectedCategory() {
  const selectValue = tx$("transactionCategory").value;
  if (selectValue !== CUSTOM_CATEGORY_VALUE) return selectValue;
  return tx$("transactionOtherCategory").value.trim();
}

async function loadTransactions() {
  tx$("transactionRows").innerHTML = '<tr><td class="loading" colspan="6">Loading transactions...</td></tr>';
  try {
    const limit = 100;
    const items = [];
    let skip = 0;
    let total = Infinity;

    while (items.length < total) {
      const data = await FinSight.api(`/transactions?limit=${limit}&skip=${skip}`);
      const page = Array.isArray(data.items) ? data.items : [];
      items.push(...page);
      total = Number.isFinite(Number(data.total)) ? Number(data.total) : items.length;

      if (page.length === 0) break;
      skip += page.length;
    }

    transactionItems = items;
    renderCategoryOptions();
    renderTransactions();
  } catch (error) {
    tx$("transactionRows").innerHTML = `<tr><td class="empty" colspan="6">${error.message}</td></tr>`;
    FinSight.showTopPopup({
      title: "Failed to Load Transactions",
      message: error.message,
      type: "error",
    });
  }
}

async function removeTransaction(id) {
  transactionToDelete = id;
  deleteModalPreviousFocus = document.activeElement;
  tx$("deleteTransactionModal").classList.add("show");
  tx$("confirmDeleteTransaction").focus();
}

function closeDeleteConfirmation() {
  tx$("deleteTransactionModal").classList.remove("show");
  transactionToDelete = null;
  if (deleteModalPreviousFocus && typeof deleteModalPreviousFocus.focus === "function") {
    deleteModalPreviousFocus.focus();
  }
  deleteModalPreviousFocus = null;
}

async function confirmDeleteTransaction() {
  if (transactionToDelete === null) return;
  const id = transactionToDelete;
  closeDeleteConfirmation();
  try {
    await FinSight.api(`/transactions/${id}`, { method: "DELETE" });
    await loadTransactions();
    FinSight.showTopPopup({
      title: "Transaction Deleted",
      message: "The transaction was permanently deleted from your records.",
      type: "success",
      duration: 5000,
    });
  } catch (error) {
    FinSight.showTopPopup({
      title: "Delete Failed",
      message: error.message,
      type: "error",
    });
  }
}

tx$("addTransaction").addEventListener("click", () => openTransaction());
tx$("closeTransaction").addEventListener("click", closeTransaction);
tx$("transactionType").addEventListener("change", () => {
  updateTransactionCategories();
  void fetchDynamicBudgetLimit();
});
tx$("transactionCategory").addEventListener("change", () => {
  updateOtherCategoryInput();
  void fetchDynamicBudgetLimit();
});
const customCategoryInput = tx$("transactionOtherCategory");
if (customCategoryInput) {
  customCategoryInput.addEventListener("input", () => void fetchDynamicBudgetLimit());
}
tx$("transactionDate").addEventListener("change", () => void fetchDynamicBudgetLimit());
tx$("transactionAmount").addEventListener("input", () => {
  const raw = tx$("transactionAmount").value.trim();
  const val = Number(raw);
  const errorEl = tx$("transactionAmountError");
  const amountInput = tx$("transactionAmount");

  if (!raw) {
    if (errorEl) errorEl.textContent = "";
    amountInput.classList.remove("has-error");
    return;
  }

  if (currentLimitData?.has_budget && currentLimitData.remaining_budget != null && val > currentLimitData.remaining_budget) {
    const diff = val - currentLimitData.remaining_budget;
    const category = selectedCategory();
    setFieldError(
      "amount",
      `Exceeds remaining budget by ${FinSight.money(diff)}.`
    );
    FinSight.showTopPopup({
      title: "Budget Limit Exceeded",
      message: `Remaining budget for ${category || "this category"} in ${currentLimitData.month} is ${FinSight.money(currentLimitData.remaining_budget)} (allocated: ${FinSight.money(currentLimitData.allocated_budget)}, spent: ${FinSight.money(currentLimitData.spent_amount)}). This transaction of ${FinSight.money(val)} exceeds your available budget by ${FinSight.money(diff)}.`,
      meta: [
        { label: "Allocated", value: FinSight.money(currentLimitData.allocated_budget) },
        { label: "Spent", value: FinSight.money(currentLimitData.spent_amount) },
        { label: "Remaining", value: FinSight.money(currentLimitData.remaining_budget) },
        { label: "Exceeded By", value: FinSight.money(diff), highlight: true },
      ],
      type: "warning",
    });
  } else {
    if (errorEl) errorEl.textContent = "";
    amountInput.classList.remove("has-error");
  }
});
tx$("cancelDeleteTransaction").addEventListener("click", closeDeleteConfirmation);
tx$("confirmDeleteTransaction").addEventListener("click", () => void confirmDeleteTransaction());
tx$("deleteTransactionModal").addEventListener("click", (event) => {
  if (event.target === tx$("deleteTransactionModal")) closeDeleteConfirmation();
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && tx$("deleteTransactionModal").classList.contains("show")) {
    closeDeleteConfirmation();
  }
});
tx$("search").addEventListener("input", () => { currentPage = 1; renderTransactions(); });
tx$("type").addEventListener("change", () => {
  renderCategoryOptions(tx$("type").value);
  currentPage = 1;
  renderTransactions();
});
tx$("category").addEventListener("change", () => { currentPage = 1; renderTransactions(); });
tx$("month").addEventListener("change", () => { currentPage = 1; renderTransactions(); });
tx$("clearFilters").addEventListener("click", () => {
  tx$("search").value = "";
  tx$("type").value = "";
  renderCategoryOptions();
  tx$("month").value = "";
  currentPage = 1;
  renderTransactions();
});
tx$("previousPage").addEventListener("click", () => { currentPage -= 1; renderTransactions(); });
tx$("nextPage").addEventListener("click", () => { currentPage += 1; renderTransactions(); });

tx$("transactionForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  clearFieldErrors();

  const id = tx$("transactionId").value;
  const type = tx$("transactionType").value;
  const category = selectedCategory();
  const dateStr = tx$("transactionDate").value.trim();
  const amountStr = tx$("transactionAmount").value.trim();
  const description = tx$("transactionDescription").value.trim();

  let hasClientError = false;

  // 1. Validate Type
  if (!type) {
    setFieldError("type", "Transaction type is required.");
    FinSight.showTopPopup({
      title: "Transaction Type Required",
      message: "Please choose a valid transaction type.",
      type: "error",
    });
    hasClientError = true;
  }

  // 2. Validate Amount
  if (!amountStr) {
    setFieldError("amount", "Amount is required.");
    FinSight.showTopPopup({
      title: "Amount Required",
      message: "Please enter the transaction amount in ₹.",
      type: "error",
    });
    hasClientError = true;
  } else if (amountStr.includes("e") || amountStr.includes("E")) {
    setFieldError("amount", "Scientific notation is not permitted.");
    FinSight.showTopPopup({
      title: "Invalid Amount Format",
      message: "Scientific notation (e.g. 1e5) is not allowed. Please enter regular decimal numbers.",
      type: "error",
    });
    hasClientError = true;
  } else if (!/^\d+(\.\d{1,2})?$/.test(amountStr)) {
    setFieldError("amount", "Amount must be a positive number with at most 2 decimal places.");
    FinSight.showTopPopup({
      title: "Invalid Decimals",
      message: "Amount must be a positive number with at most 2 decimal places (e.g., 250.50).",
      type: "error",
    });
    hasClientError = true;
  } else {
    const num = Number(amountStr);
    if (!Number.isFinite(num) || num <= 0) {
      setFieldError("amount", "Amount must be greater than ₹0.");
      FinSight.showTopPopup({
        title: "Invalid Amount",
        message: "Transaction amount must be strictly greater than ₹0.00.",
        type: "error",
      });
      hasClientError = true;
    } else if (currentLimitData?.has_budget && currentLimitData.remaining_budget != null && num > currentLimitData.remaining_budget) {
      const diff = num - currentLimitData.remaining_budget;
      setFieldError(
        "amount",
        `Exceeds remaining budget by ${FinSight.money(diff)}.`
      );
      FinSight.showTopPopup({
        title: "Budget Limit Exceeded",
        message: `Remaining budget for ${category || "this category"} in ${currentLimitData.month} is ${FinSight.money(currentLimitData.remaining_budget)} (allocated: ${FinSight.money(currentLimitData.allocated_budget)}, spent: ${FinSight.money(currentLimitData.spent_amount)}). This transaction of ${FinSight.money(num)} exceeds your available budget by ${FinSight.money(diff)}.`,
        meta: [
          { label: "Allocated", value: FinSight.money(currentLimitData.allocated_budget) },
          { label: "Spent", value: FinSight.money(currentLimitData.spent_amount) },
          { label: "Remaining", value: FinSight.money(currentLimitData.remaining_budget) },
          { label: "Exceeded By", value: FinSight.money(diff), highlight: true },
        ],
        type: "error",
      });
      hasClientError = true;
    }
  }

  // 3. Validate Category
  if (!category) {
    setFieldError("category", "Category is required.");
    FinSight.showTopPopup({
      title: "Category Required",
      message: "Please select or enter a category name for this transaction.",
      type: "error",
    });
    hasClientError = true;
  } else if (category.length < 2 || category.length > 30) {
    setFieldError("category", "Category must be between 2 and 30 characters.");
    FinSight.showTopPopup({
      title: "Invalid Category Length",
      message: `Category "${category}" has ${category.length} characters. Category must be between 2 and 30 characters.`,
      type: "error",
    });
    hasClientError = true;
  }

  // 4. Validate Date
  if (dateStr && dateStr > today()) {
    setFieldError("date", "Transaction date cannot be in the future.");
    FinSight.showTopPopup({
      title: "Future Date Not Permitted",
      message: `The selected date (${dateStr}) is in the future. Financial transactions must be recorded on or before today (${today()}).`,
      meta: [
        { label: "Selected Date", value: dateStr, highlight: true },
        { label: "Today (IST)", value: today() },
      ],
      type: "error",
    });
    hasClientError = true;
  }

  // 5. Validate Description
  if (description.length > 200) {
    setFieldError("description", "Description cannot exceed 200 characters.");
    FinSight.showTopPopup({
      title: "Description Too Long",
      message: `Description has ${description.length} characters, exceeding the 200-character limit.`,
      type: "error",
    });
    hasClientError = true;
  }

  if (hasClientError) return;

  const payload = {
    amount: Number(amountStr),
    transaction_type: type,
    category,
    description,
  };
  if (dateStr) {
    payload.date = dateStr;
  }

  // Double-submit prevention: disable submit button while in flight
  const submitBtn = tx$("saveTransaction");
  const originalText = submitBtn.textContent;
  submitBtn.disabled = true;
  submitBtn.textContent = id ? "Updating..." : "Saving...";

  try {
    const result = await FinSight.api(id ? `/transactions/${id}` : "/transactions", {
      method: id ? "PATCH" : "POST",
      body: JSON.stringify(payload),
    });
    closeTransaction();
    await loadTransactions();
    if (result?.warning) {
      FinSight.showTopPopup({
        title: "Transaction Saved (Notice)",
        message: `Transaction recorded. Warning: ${result.warning}`,
        type: "warning",
        duration: 8000,
      });
    } else {
      FinSight.showTopPopup({
        title: "Transaction Saved",
        message: id ? "Transaction was successfully updated." : "Transaction was successfully recorded.",
        type: "success",
        duration: 5000,
      });
    }
  } catch (error) {
    if (error.errors && typeof error.errors === "object" && Object.keys(error.errors).length > 0) {
      for (const [field, message] of Object.entries(error.errors)) {
        setFieldError(field, message);
      }
    } else {
      setFieldError("non_field_errors", error.message);
    }

    const errStr = String(error.message || "");
    if (errStr.toLowerCase().includes("duplicate")) {
      FinSight.showTopPopup({
        title: "Duplicate Transaction Blocked",
        message: "An identical transaction with the same amount, category, type, and date was submitted within the last 5 seconds. To prevent accidental duplicate entries, please wait 5 seconds before resubmitting.",
        meta: [
          { label: "Amount", value: FinSight.money(payload.amount) },
          { label: "Category", value: payload.category },
          { label: "Type", value: payload.transaction_type },
        ],
        type: "error",
      });
    } else if (errStr.toLowerCase().includes("budget")) {
      FinSight.showTopPopup({
        title: "Transaction Declined: Budget Limit Exceeded",
        message: errStr,
        type: "error",
      });
    } else {
      FinSight.showTopPopup({
        title: "Transaction Declined",
        message: errStr || "Unable to save transaction.",
        type: "error",
      });
    }
  } finally {
    submitBtn.disabled = false;
    submitBtn.textContent = originalText;
  }
});

void loadTransactions();
updateTransactionCategories();
