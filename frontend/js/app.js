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
    let response;
    try {
      response = await fetch(`${window.FINSIGHT_API_URL}${path}`, {
        ...options,
        headers: {
          ...(options.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
          ...(options.headers || {}),
        },
      });
    } catch (cause) {
      if (cause?.name === "AbortError") throw cause;
      const error = new Error("Unable to reach FinSight. Check that the backend is running and try again.");
      error.cause = cause;
      throw error;
    }
    if (!response.ok) {
      let detail = `Request failed (${response.status}).`;
      let errorDetails = null;
      let fieldErrors = {};
      try {
        const body = await response.json();
        if (body.errors && typeof body.errors === "object") {
          fieldErrors = body.errors;
        }
        if (typeof body.detail === "string") {
          detail = body.detail;
        } else if (Array.isArray(body.detail)) {
          errorDetails = body.detail;
          detail = body.detail.map((item) => {
            const field = Array.isArray(item.loc) ? item.loc[item.loc.length - 1] : "";
            if (field && !fieldErrors[field]) {
              fieldErrors[field] = item.msg || "Invalid value";
            }
            return field ? `${field}: ${item.msg || "Invalid value"}` : (item.msg || "Invalid value");
          }).join(" ");
        } else if (body.detail && typeof body.detail === "object") {
          errorDetails = body.detail;
          if (typeof body.detail.message === "string") detail = body.detail.message;
        } else if (typeof body.message === "string") {
          detail = body.message;
        }
      } catch {
        // Keep the HTTP status when the server does not return JSON.
      }
      const error = new Error(detail);
      error.status = response.status;
      error.retryAfter = response.headers.get("Retry-After");
      if (errorDetails) error.details = errorDetails;
      error.errors = fieldErrors;
      throw error;
    }
    return response.status === 204 ? null : response.json();
  },
  money: (value) => new Intl.NumberFormat("en-IN", {
    style: "currency", currency: "INR", maximumFractionDigits: 2,
  }).format(Number(value || 0)),
  toast: (message, type = "error") => {
    const toast = document.getElementById("toast");
    if (!toast) return;
    toast.textContent = message;
    toast.classList.toggle("error", type === "error");
    toast.classList.toggle("success", type === "success");
    toast.setAttribute("role", type === "error" ? "alert" : "status");
    toast.classList.add("show");
    window.clearTimeout(window.FinSight.toastTimer);
    window.FinSight.toastTimer = window.setTimeout(() => {
      toast.classList.remove("show", "error", "success");
    }, 6500);
  },
  showTopPopup: ({ title, message, meta = [], type = "warning", duration = null }) => {
    let popup = document.getElementById("topPopup");
    if (!popup) {
      popup = document.createElement("div");
      popup.id = "topPopup";
      popup.className = "top-popup";
      popup.setAttribute("role", "alert");
      popup.setAttribute("aria-live", "assertive");
      popup.innerHTML = `
        <div class="top-popup-content">
          <div class="top-popup-icon" id="topPopupIcon"></div>
          <div class="top-popup-body">
            <div class="top-popup-title" id="topPopupTitle"></div>
            <div class="top-popup-message" id="topPopupMessage"></div>
            <div class="top-popup-meta" id="topPopupMeta"></div>
          </div>
          <button class="top-popup-close" id="topPopupClose" type="button" aria-label="Dismiss">×</button>
        </div>
        <div class="top-popup-progress"><div class="top-popup-progress-bar" id="topPopupProgressBar"></div></div>
      `;
      document.body.appendChild(popup);

      const closeBtn = popup.querySelector("#topPopupClose");
      if (closeBtn) {
        closeBtn.addEventListener("click", () => FinSight.hideTopPopup());
      }

      popup.addEventListener("mouseenter", () => FinSight.pauseTopPopup());
      popup.addEventListener("mouseleave", () => FinSight.resumeTopPopup());
    }

    popup.className = `top-popup ${type} show`;
    popup.hidden = false;

    const iconEl = popup.querySelector("#topPopupIcon");
    const icons = {
      warning: "⚠️",
      error: "🚫",
      info: "ℹ️",
      success: "✅"
    };
    if (iconEl) iconEl.textContent = icons[type] || "ℹ️";

    const titleEl = popup.querySelector("#topPopupTitle");
    if (titleEl) {
      titleEl.textContent = title || "";
      titleEl.style.display = title ? "block" : "none";
    }

    const msgEl = popup.querySelector("#topPopupMessage");
    if (msgEl) msgEl.textContent = message || "";

    const metaEl = popup.querySelector("#topPopupMeta");
    if (metaEl) {
      if (Array.isArray(meta) && meta.length > 0) {
        metaEl.innerHTML = meta.map(item => `
          <span class="top-popup-chip ${item.highlight ? 'chip-highlight' : ''}">
            <span class="chip-label">${item.label}:</span>
            <strong class="chip-val">${item.value}</strong>
          </span>
        `).join("");
        metaEl.style.display = "flex";
      } else {
        metaEl.innerHTML = "";
        metaEl.style.display = "none";
      }
    }

    // Dynamic duration: reading speed calculation (approx 75ms per character) -> min 7s, max 18s
    const textLen = (title || "").length + (message || "").length;
    const readDuration = duration || Math.max(7000, Math.min(18000, textLen * 75));

    FinSight.startTopPopupTimer(readDuration);
  },
  hideTopPopup: () => {
    const popup = document.getElementById("topPopup");
    if (!popup) return;
    popup.classList.remove("show");
    window.clearTimeout(window.FinSight._topPopupTimer);
    window.cancelAnimationFrame(window.FinSight._topPopupAnimFrame);
  },
  pauseTopPopup: () => {
    window.FinSight._topPopupPaused = true;
  },
  resumeTopPopup: () => {
    window.FinSight._topPopupPaused = false;
  },
  startTopPopupTimer: (duration) => {
    window.clearTimeout(window.FinSight._topPopupTimer);
    window.cancelAnimationFrame(window.FinSight._topPopupAnimFrame);
    window.FinSight._topPopupPaused = false;

    const progressBar = document.getElementById("topPopupProgressBar");
    if (progressBar) {
      progressBar.style.transition = "none";
      progressBar.style.width = "100%";
    }

    let startTime = performance.now();
    let remainingTime = duration;

    function step(now) {
      if (!window.FinSight._topPopupPaused) {
        const elapsed = now - startTime;
        startTime = now;
        remainingTime -= elapsed;

        if (progressBar) {
          const pct = Math.max(0, (remainingTime / duration) * 100);
          progressBar.style.width = `${pct}%`;
        }

        if (remainingTime <= 0) {
          FinSight.hideTopPopup();
          return;
        }
      } else {
        startTime = now;
      }
      window.FinSight._topPopupAnimFrame = requestAnimationFrame(step);
    }

    window.FinSight._topPopupAnimFrame = requestAnimationFrame(step);
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
      <div class="account"><span class="avatar">P</span><div><div class="account-name">Personal account</div><div class="account-sub">Connected workspace</div></div></div>
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
