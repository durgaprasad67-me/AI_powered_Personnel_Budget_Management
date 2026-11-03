"use strict";

let transactionItems = [];
let currentPage = 1;
const pageSize = 5;
const tx$ = (id) => document.getElementById(id);

function today() {
  return new Date().toISOString().slice(0, 10);
}

function selectedTransactions() {
  const search = tx$("search").value.trim().toLowerCase();
  const type = tx$("type").value;
  const category = tx$("category").value;
  const month = tx$("month").value;

  return transactionItems.filter((item) => {
    const searchable = `${item.description || ""} ${item.category || ""}`.toLowerCase();
    return (!search || searchable.includes(search))
      && (!type || item.transaction_type === type)
      && (!category || item.category === category)
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
  const stats = [
    ["Total transactions", items.length],
    ["Total income", FinSight.money(income)],
    ["Total expenses", FinSight.money(expenses)],
    ["Net balance", FinSight.money(income - expenses)],
  ];
  tx$("transactionStats").innerHTML = stats
    .map(([label, value]) => `<article class="card stat-card"><div class="stat-label">${label}</div><div class="stat-value">${value}</div></article>`)
    .join("");
}

function renderCategoryOptions() {
  const category = tx$("category");
  const selected = category.value;
  const values = [...new Set(transactionItems.map((item) => item.category).filter(Boolean))]
    .sort((left, right) => left.localeCompare(right));
  category.innerHTML = '<option value="">All categories</option>';
  values.forEach((value) => {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = value;
    category.appendChild(option);
  });
  category.value = values.includes(selected) ? selected : "";
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
    row.innerHTML = `<td>${item.date}</td><td>${item.description}</td><td><span class="badge">${item.category}</span></td><td><span class="badge">${item.transaction_type}</span></td><td>${FinSight.money(item.amount)}</td><td><div class="row-actions"><button class="secondary edit" type="button">Edit</button><button class="danger delete" type="button">Delete</button></div></td>`;
    row.querySelector(".edit").addEventListener("click", () => openTransaction(item));
    row.querySelector(".delete").addEventListener("click", () => removeTransaction(item.id));
    rows.appendChild(row);
  });
}

function openTransaction(item = null) {
  tx$("transactionModal").classList.add("show");
  tx$("transactionTitle").textContent = item ? "Edit transaction" : "Add transaction";
  tx$("saveTransaction").textContent = item ? "Update transaction" : "Save transaction";
  tx$("transactionId").value = item?.id || "";
  tx$("transactionDate").value = item?.date || today();
  tx$("transactionType").value = item?.transaction_type || "expense";
  tx$("transactionAmount").value = item?.amount || "";
  tx$("transactionCategory").value = item?.category || "";
  tx$("transactionDescription").value = item?.description || "";
}

function closeTransaction() {
  tx$("transactionModal").classList.remove("show");
  tx$("transactionForm").reset();
  tx$("transactionId").value = "";
  tx$("saveTransaction").textContent = "Save transaction";
}

async function loadTransactions() {
  tx$("transactionRows").innerHTML = '<tr><td class="loading" colspan="6">Loading transactions...</td></tr>';
  try {
    const data = await FinSight.api("/transactions?limit=100");
    transactionItems = data.items || [];
    renderCategoryOptions();
    renderTransactions();
  } catch (error) {
    tx$("transactionRows").innerHTML = `<tr><td class="empty" colspan="6">${error.message}</td></tr>`;
    FinSight.toast(error.message);
  }
}

async function removeTransaction(id) {
  if (!window.confirm("Delete this transaction?")) return;
  try {
    await FinSight.api(`/transactions/${id}`, { method: "DELETE" });
    await loadTransactions();
    FinSight.toast("Transaction deleted.");
  } catch (error) {
    FinSight.toast(error.message);
  }
}

tx$("addTransaction").addEventListener("click", () => openTransaction());
tx$("closeTransaction").addEventListener("click", closeTransaction);
tx$("search").addEventListener("input", () => { currentPage = 1; renderTransactions(); });
tx$("type").addEventListener("change", () => { currentPage = 1; renderTransactions(); });
tx$("category").addEventListener("change", () => { currentPage = 1; renderTransactions(); });
tx$("month").addEventListener("change", () => { currentPage = 1; renderTransactions(); });
tx$("clearFilters").addEventListener("click", () => {
  tx$("search").value = "";
  tx$("type").value = "";
  tx$("category").value = "";
  tx$("month").value = "";
  currentPage = 1;
  renderTransactions();
});
tx$("previousPage").addEventListener("click", () => { currentPage -= 1; renderTransactions(); });
tx$("nextPage").addEventListener("click", () => { currentPage += 1; renderTransactions(); });

tx$("transactionForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const id = tx$("transactionId").value;
  const payload = {
    date: tx$("transactionDate").value,
    transaction_type: tx$("transactionType").value,
    amount: Number(tx$("transactionAmount").value),
    category: tx$("transactionCategory").value.trim(),
    description: tx$("transactionDescription").value.trim(),
  };
  try {
    await FinSight.api(id ? `/transactions/${id}` : "/transactions", {
      method: id ? "PATCH" : "POST",
      body: JSON.stringify(payload),
    });
    closeTransaction();
    await loadTransactions();
    FinSight.toast(id ? "Transaction updated." : "Transaction added.");
  } catch (error) {
    FinSight.toast(error.message);
  }
});

void loadTransactions();
