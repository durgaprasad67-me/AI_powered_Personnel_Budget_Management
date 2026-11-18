"use strict";

let goals = [];
let goalToDelete = null;
let deleteGoalPreviousFocus = null;

const goal$ = (id) => document.getElementById(id);

function escapeHTML(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  })[char]);
}

function formatStatusLabel(status) {
  if (!status) return "Active";
  return status.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function openGoal(item) {
  goal$("goalModal").classList.add("show");
  goal$("goalId").value = item?.id || "";
  goal$("goalName").value = item?.name || "";
  goal$("goalTarget").value = item?.target_amount || "";
  goal$("goalCurrent").value = item?.current_amount || 0;
  goal$("goalDate").value = item?.target_date || "";
  goal$("goalDescription").value = item?.description || "";
}

function closeGoal() {
  goal$("goalModal").classList.remove("show");
  goal$("goalForm").reset();
}

function requestDeleteGoal(item) {
  goalToDelete = item;
  deleteGoalPreviousFocus = document.activeElement;

  const target = Number(item.target_amount || 0);
  const current = Number(item.current_amount || 0);
  const percent = target ? Math.min(100, (current / target) * 100) : 0;
  const statusLabel = formatStatusLabel(item.status);
  const deadlineText = item.target_date || "No deadline set";

  goal$("deleteGoalTitle").textContent = `Delete "${item.name}"?`;
  goal$("deleteGoalMessage").textContent = `Are you sure you want to delete this financial goal? All tracked progress and savings targets for this goal will be permanently removed.`;
  goal$("deleteGoalDetails").innerHTML = `
    <div class="confirm-goal-row">
      <span>Goal:</span>
      <strong>${escapeHTML(item.name)}</strong>
    </div>
    <div class="confirm-goal-row">
      <span>Target Amount:</span>
      <strong>${FinSight.money(target)}</strong>
    </div>
    <div class="confirm-goal-row">
      <span>Current Savings:</span>
      <strong>${FinSight.money(current)} (${Math.round(percent)}%)</strong>
    </div>
    <div class="confirm-goal-row">
      <span>Status:</span>
      <strong>${escapeHTML(statusLabel)}</strong>
    </div>
    <div class="confirm-goal-row">
      <span>Target Date:</span>
      <strong>${escapeHTML(deadlineText)}</strong>
    </div>
  `;

  const modal = goal$("deleteGoalModal");
  modal.classList.add("show");
  goal$("confirmDeleteGoal").disabled = false;
  goal$("confirmDeleteGoal").textContent = "Yes, delete goal";
  goal$("confirmDeleteGoal").focus();
}

function closeDeleteGoalModal() {
  const modal = goal$("deleteGoalModal");
  if (modal) modal.classList.remove("show");
  goalToDelete = null;
  if (deleteGoalPreviousFocus && typeof deleteGoalPreviousFocus.focus === "function") {
    deleteGoalPreviousFocus.focus();
  }
  deleteGoalPreviousFocus = null;
}

async function confirmDeleteGoalAction() {
  if (!goalToDelete) return;
  const target = goalToDelete;
  const confirmBtn = goal$("confirmDeleteGoal");
  confirmBtn.disabled = true;
  confirmBtn.textContent = "Deleting…";

  try {
    await FinSight.api(`/financial-goals/${target.id}`, { method: "DELETE" });
    closeDeleteGoalModal();
    await loadGoals();

    const targetAmount = Number(target.target_amount || 0);
    const currentAmount = Number(target.current_amount || 0);
    const percent = targetAmount ? Math.min(100, (currentAmount / targetAmount) * 100) : 0;

    FinSight.showTopPopup({
      title: "Goal Deleted",
      message: `The financial goal "${target.name}" (${FinSight.money(targetAmount)}) was deleted successfully.`,
      type: "success",
      meta: [
        { label: "Goal", value: target.name },
        { label: "Target", value: FinSight.money(targetAmount) },
        { label: "Saved", value: FinSight.money(currentAmount) },
        { label: "Progress", value: `${Math.round(percent)}%` },
      ],
      duration: 6000,
    });
  } catch (error) {
    confirmBtn.disabled = false;
    confirmBtn.textContent = "Yes, delete goal";
    FinSight.showTopPopup({
      title: "Delete Failed",
      message: error.message,
      type: "error",
    });
  }
}

function renderGoals() {
  const root = goal$("goalCards");
  root.replaceChildren();

  if (!goals.length) {
    root.innerHTML = '<div class="card empty">No financial goals yet. Add a goal to start tracking progress.</div>';
    return;
  }

  goals.forEach((item) => {
    const target = Number(item.target_amount || 0);
    const current = Number(item.current_amount || 0);
    const percent = target ? Math.min(100, (current / target) * 100) : 0;

    const card = document.createElement("article");
    card.className = "card goal-card";
    card.innerHTML = `
      <div class="goal-row">
        <h2>${escapeHTML(item.name)}</h2>
        <span class="badge">${escapeHTML(item.status || "active")}</span>
      </div>
      <p class="subtitle">${escapeHTML(item.description || "Keep moving toward this goal.")}</p>
      <div class="goal-meta">
        <span>${FinSight.money(current)} saved</span>
        <strong>${FinSight.money(target)}</strong>
      </div>
      <div class="progress"><span style="width:${percent}%"></span></div>
      <div class="goal-meta">
        <span>${Math.round(percent)}% complete</span>
        <span>${escapeHTML(item.target_date || "No target date")}</span>
      </div>
      <div class="goal-actions">
        <button class="secondary edit" type="button">Edit</button>
        <button class="danger delete" type="button">Delete</button>
      </div>
    `;

    card.querySelector(".edit").addEventListener("click", () => openGoal(item));
    card.querySelector(".delete").addEventListener("click", () => requestDeleteGoal(item));
    root.appendChild(card);
  });
}

async function loadGoals() {
  goal$("goalCards").innerHTML = '<div class="loading">Loading goals…</div>';
  try {
    const data = await FinSight.api("/financial-goals?limit=100");
    goals = data.items || [];
    renderGoals();
  } catch (error) {
    goal$("goalCards").innerHTML = `<div class="card empty">${escapeHTML(error.message)}</div>`;
  }
}

goal$("addGoal").addEventListener("click", () => openGoal());
goal$("closeGoal").addEventListener("click", closeGoal);

goal$("cancelDeleteGoal").addEventListener("click", closeDeleteGoalModal);
goal$("confirmDeleteGoal").addEventListener("click", () => void confirmDeleteGoalAction());
goal$("deleteGoalModal").addEventListener("click", (event) => {
  if (event.target === goal$("deleteGoalModal")) closeDeleteGoalModal();
});

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    if (goal$("deleteGoalModal") && goal$("deleteGoalModal").classList.contains("show")) {
      closeDeleteGoalModal();
    } else if (goal$("goalModal") && goal$("goalModal").classList.contains("show")) {
      closeGoal();
    }
  }
});

goal$("goalForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const id = goal$("goalId").value;
  const targetAmount = Number(goal$("goalTarget").value);
  const currentAmount = Number(goal$("goalCurrent").value || 0);

  if (!Number.isFinite(targetAmount) || targetAmount <= 0) {
    FinSight.toast("Enter a target amount greater than ₹0.");
    return;
  }
  if (!Number.isFinite(currentAmount) || currentAmount < 0) {
    FinSight.toast("Current amount cannot be negative.");
    return;
  }
  if (targetAmount > FinSight.MAX_AMOUNT) {
    FinSight.toast("Target amount exceeds the maximum limit.");
    return;
  }

  const payload = {
    name: goal$("goalName").value.trim(),
    target_amount: targetAmount,
    current_amount: currentAmount,
    target_date: goal$("goalDate").value || null,
    description: goal$("goalDescription").value.trim() || null,
  };

  try {
    await FinSight.api(id ? `/financial-goals/${id}` : "/financial-goals", {
      method: id ? "PATCH" : "POST",
      body: JSON.stringify(payload),
    });
    closeGoal();
    await loadGoals();
    FinSight.toast("Goal saved.", "success");
  } catch (error) {
    FinSight.toast(error.message);
  }
});

void loadGoals();
