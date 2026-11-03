"use strict";

window.FINSIGHT_API_URL =
  window.FINSIGHT_API_URL || "http://127.0.0.1:8000/api/v1";

const pageLinks = [
  ["Overview", "dashboard.html", "layout-dashboard"],
  ["Transactions", "transactions.html", "arrow-left-right"],
  ["Budgets", "budgets.html", "wallet"],
  ["Financial goals", "goals.html", "target"],
  ["AI insights", "insights.html", "sparkles"],
  ["Analytics", "analytics.html", "chart-column-increasing"],
  ["Reports", "reports.html", "file-chart-column"],
  ["Import data", "imports.html", "upload"],
];

window.FinSight = {
  api: async (path, options = {}) => {
    const response = await fetch(`${window.FINSIGHT_API_URL}${path}`, {
      ...options,
      headers: {
        ...(options.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
        ...(options.headers || {}),
      },
    });
    if (!response.ok) {
      let detail = `Request failed (${response.status}).`;
      try {
        const body = await response.json();
        if (typeof body.detail === "string") detail = body.detail;
      } catch {
        // Keep the HTTP status when the server does not return JSON.
      }
      throw new Error(detail);
    }
    return response.status === 204 ? null : response.json();
  },
  money: (value) => new Intl.NumberFormat("en-IN", {
    style: "currency", currency: "INR", maximumFractionDigits: 2,
  }).format(Number(value || 0)),
  toast: (message) => {
    const toast = document.getElementById("toast");
    if (!toast) return;
    toast.textContent = message;
    toast.classList.add("show");
    window.clearTimeout(window.FinSight.toastTimer);
    window.FinSight.toastTimer = window.setTimeout(() => toast.classList.remove("show"), 3200);
  },
};

function renderShell() {
  const sidebar = document.getElementById("sidebar");
  if (!sidebar) return;
  const current = document.body.dataset.page || "Overview";
  sidebar.innerHTML = `
    <a class="brand" href="dashboard.html">
      <span class="brand-icon"><i data-lucide="chart-no-axes-combined"></i></span>
      <span><div class="brand-name">FinSight AI</div><div class="brand-tag">Smarter Finance. Brighter Future.</div></span>
    </a>
    <div class="section-label">Your workspace</div>
    <nav class="nav">${pageLinks.map(([label, href, icon]) =>
      `<a class="${label === current ? "active" : ""}" href="${href}"><i data-lucide="${icon}"></i>${label}</a>`).join("")}</nav>
    <div class="side-bottom">
      <div class="side-tip"><div class="side-tip-title"><i data-lucide="lightbulb"></i>A little money wisdom</div><p>Small, consistent reviews make your spending easier to understand.</p></div>
      <div class="account"><span class="avatar">D</span><div><div class="account-name">Durga Prasad</div><div class="account-sub">Personal account</div></div></div>
    </div>`;
  const menu = document.getElementById("menuBtn");
  menu?.addEventListener("click", () => sidebar.classList.toggle("open"));
  if (window.lucide) window.lucide.createIcons();
}

document.addEventListener("DOMContentLoaded", () => {
  renderShell();
  const year = document.getElementById("year");
  if (year) year.textContent = String(new Date().getFullYear());
});
