"use strict";

const API_BASE_URL =
  window.FINSIGHT_API_URL || "http://127.0.0.1:8000/api/v1";

const getElement = (id) => document.getElementById(id);
const amountFormatter = new Intl.NumberFormat("en-IN", {
  style: "currency",
  currency: "INR",
  maximumFractionDigits: 2,
});

let transactions = [];

function formatAmount(value) {
  return amountFormatter.format(Number(value || 0));
}

function showToast(message) {
  const toast = getElement("toast");
  if (!toast) {
    return;
  }
  toast.textContent = message;
  toast.classList.add("show");
  window.setTimeout(() => toast.classList.remove("show"), 3000);
}

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
    ...options,
  });

  if (!response.ok) {
    let detail = `Request failed (${response.status}).`;
    try {
      const body = await response.json();
      if (typeof body.detail === "string") {
        detail = body.detail;
      }
    } catch {
      // Keep the status-based message when the server does not return JSON.
    }
    throw new Error(detail);
  }

  return response.status === 204 ? null : response.json();
}

function renderSummary(items) {
  const income = items
    .filter((item) => item.transaction_type === "income")
    .reduce((total, item) => total + Number(item.amount || 0), 0);
  const expenses = items
    .filter((item) => item.transaction_type === "expense")
    .reduce((total, item) => total + Number(item.amount || 0), 0);

  getElement("totalTransactions").textContent = String(items.length);
  getElement("totalIncome").textContent = formatAmount(income);
  getElement("totalExpenses").textContent = formatAmount(expenses);
  getElement("netBalance").textContent = formatAmount(income - expenses);
}

function renderTable(items) {
  const table = getElement("transactionsTable");
  table.replaceChildren();

  if (!items.length) {
    const row = document.createElement("tr");
    const cell = document.createElement("td");
    cell.colSpan = 6;
    cell.textContent = "No transactions found.";
    row.appendChild(cell);
    table.appendChild(row);
    return;
  }

  items.forEach((transaction) => {
    const row = document.createElement("tr");
    const values = [
      transaction.date,
      transaction.description,
      transaction.category,
      transaction.transaction_type,
      formatAmount(transaction.amount),
    ];

    values.forEach((value) => {
      const cell = document.createElement("td");
      cell.textContent = value || "";
      row.appendChild(cell);
    });

    const actions = document.createElement("td");
    actions.className = "actions";
    const editButton = document.createElement("button");
    editButton.className = "text-btn";
    editButton.type = "button";
    editButton.textContent = "Edit";
    editButton.addEventListener("click", () => openModal(transaction));
    const deleteButton = document.createElement("button");
    deleteButton.className = "text-btn danger";
    deleteButton.type = "button";
    deleteButton.textContent = "Delete";
    deleteButton.addEventListener("click", () => deleteTransaction(transaction.id));
    actions.append(editButton, deleteButton);
    row.appendChild(actions);
    table.appendChild(row);
  });
}

async function loadTransactions() {
  const search = getElement("searchInput").value.trim().toLowerCase();
  const type = getElement("typeFilter").value;
  const query = new URLSearchParams({ limit: "100" });
  if (type) {
    query.set("transaction_type", type);
  }

  const response = await request(`/transactions?${query}`);
  transactions = response.items || [];
  const filtered = search
    ? transactions.filter((item) =>
        [item.description, item.category, item.transaction_type]
          .filter(Boolean)
          .some((value) => String(value).toLowerCase().includes(search)),
      )
    : transactions;
  renderSummary(filtered);
  renderTable(filtered);
}

function openModal(transaction = null) {
  getElement("transactionModal").classList.add("show");
  getElement("modalTitle").textContent = transaction
    ? "Edit Transaction"
    : "Add Transaction";
  getElement("transactionId").value = transaction?.id || "";
  getElement("date").value =
    transaction?.date || new Date().toISOString().slice(0, 10);
  getElement("description").value = transaction?.description || "";
  getElement("category").value = transaction?.category || "";
  getElement("transactionType").value =
    transaction?.transaction_type || "expense";
  getElement("amount").value = transaction?.amount || "";
}

function closeModal() {
  getElement("transactionModal").classList.remove("show");
  getElement("transactionForm").reset();
  getElement("transactionId").value = "";
}

async function saveTransaction(event) {
  event.preventDefault();
  const id = getElement("transactionId").value;
  const payload = {
    date: getElement("date").value,
    description: getElement("description").value.trim(),
    category: getElement("category").value.trim(),
    transaction_type: getElement("transactionType").value,
    amount: Number(getElement("amount").value),
  };

  try {
    await request(id ? `/transactions/${id}` : "/transactions", {
      method: id ? "PATCH" : "POST",
      body: JSON.stringify(payload),
    });
    closeModal();
    await loadTransactions();
    showToast(id ? "Transaction updated." : "Transaction added.");
  } catch (error) {
    console.error("Transaction save failed:", error);
    showToast(error.message);
  }
}

async function deleteTransaction(id) {
  if (!window.confirm("Delete this transaction?")) {
    return;
  }
  try {
    await request(`/transactions/${id}`, { method: "DELETE" });
    await loadTransactions();
    showToast("Transaction deleted.");
  } catch (error) {
    console.error("Transaction deletion failed:", error);
    showToast(error.message);
  }
}

document.addEventListener("DOMContentLoaded", () => {
  getElement("addTransactionBtn").addEventListener("click", () => openModal());
  getElement("closeModalBtn").addEventListener("click", closeModal);
  getElement("cancelBtn").addEventListener("click", closeModal);
  getElement("transactionForm").addEventListener("submit", saveTransaction);
  getElement("filterBtn").addEventListener("click", () => void loadTransactions());
  getElement("resetBtn").addEventListener("click", () => {
    getElement("searchInput").value = "";
    getElement("typeFilter").value = "";
    void loadTransactions();
  });
  getElement("searchInput").addEventListener("input", () => void loadTransactions());
  void loadTransactions().catch((error) => {
    console.error("Transaction loading failed:", error);
    getElement("transactionsTable").innerHTML =
      '<tr><td colspan="6">Unable to load transactions. Check the backend.</td></tr>';
    showToast(error.message);
  });
});
