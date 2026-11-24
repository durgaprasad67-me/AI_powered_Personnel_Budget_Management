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
  getCurrentUserId: () => {
    return localStorage.getItem("finsight_user_id") || localStorage.getItem("user_id") || "default_dashboard_user";
  },
  api: async (path, options = {}) => {
    const userId = FinSight.getCurrentUserId();
    const token = localStorage.getItem("finsight_token") || localStorage.getItem("token");
    const authHeaders = {};
    if (token) authHeaders["Authorization"] = `Bearer ${token}`;
    if (userId) authHeaders["X-User-Id"] = userId;
    let response;
    try {
      response = await fetch(`${window.FINSIGHT_API_URL}${path}`, {
        ...options,
        headers: {
          ...(options.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
          ...authHeaders,
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
        errorDetails = body;
        if (body.errors && typeof body.errors === "object") {
          fieldErrors = body.errors;
        }
        if (typeof body.detail === "string") {
          detail = body.detail;
        } else if (Array.isArray(body.detail)) {
          errorDetails = { ...body, items: body.detail };
          detail = body.detail.map((item) => {
            const field = Array.isArray(item.loc) ? item.loc[item.loc.length - 1] : "";
            if (field && !fieldErrors[field]) {
              fieldErrors[field] = item.msg || "Invalid value";
            }
            return field ? `${field}: ${item.msg || "Invalid value"}` : (item.msg || "Invalid value");
          }).join(" ");
        } else if (body.detail && typeof body.detail === "object") {
          errorDetails = { ...body, ...body.detail };
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
      error.details = errorDetails || {};
      error.data = errorDetails || {};
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
    if (!toast._hasDismiss) {
      toast._hasDismiss = true;
      toast.style.cursor = "pointer";
      toast.addEventListener("click", () => {
        toast.classList.remove("show", "error", "success");
        window.clearTimeout(window.FinSight.toastTimer);
      });
    }
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
    }

    // Ensure close button handler is ALWAYS wired up regardless of whether popup was in HTML or dynamically created
    const closeBtn = popup.querySelector("#topPopupClose") || popup.querySelector(".top-popup-close");
    if (closeBtn && !closeBtn._hasTopPopupListener) {
      closeBtn._hasTopPopupListener = true;
      closeBtn.addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
        FinSight.hideTopPopup();
      });
    }

    // Ensure hover pause/resume is ALWAYS wired up
    if (!popup._hasHoverListeners) {
      popup._hasHoverListeners = true;
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
    window.FinSight._topPopupPaused = false;
    window.setTimeout(() => {
      if (!popup.classList.contains("show")) {
        popup.hidden = true;
      }
    }, 350);
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

const NOTIFICATION_STORAGE_KEY = "finsight.dashboard.notifications";

FinSight.notifications = {
  read: () => {
    try {
      const stored = JSON.parse(localStorage.getItem(NOTIFICATION_STORAGE_KEY) || "[]");
      return Array.isArray(stored) ? stored : [];
    } catch (error) {
      console.warn("Unable to read stored notifications:", error);
      return [];
    }
  },
  save: (list) => {
    localStorage.setItem(NOTIFICATION_STORAGE_KEY, JSON.stringify(list));
  },
  updateBadge: () => {
    const badge = document.getElementById("notificationCount");
    const notifyBtn = document.getElementById("notifyBtn");
    const list = FinSight.notifications.read();
    const unread = list.filter((item) => !item.seen).length;
    if (badge) {
      badge.textContent = String(unread);
      badge.hidden = unread === 0;
    }
    notifyBtn?.classList.toggle("has-notifications", unread > 0);
  },
  render: () => {
    const listEl = document.getElementById("notificationList");
    if (!listEl) return;
    listEl.replaceChildren();
    const list = FinSight.notifications.read();
    if (!list.length) {
      listEl.innerHTML = '<div class="notification-empty"><i data-lucide="bell-off"></i><strong>No alerts</strong><span>You have no budget alerts right now.</span></div>';
    } else {
      list.slice().reverse().forEach((notification) => {
        const item = document.createElement("article");
        item.className = `notification-item${notification.seen ? " seen" : ""}`;
        item.innerHTML = `
          <label class="notification-check">
            <input type="checkbox" data-notification-id="${notification.id}" aria-label="Select notification">
          </label>
          <div class="notification-icon">
            <i data-lucide="${notification.severity === "danger" ? "triangle-alert" : "bell-ring"}"></i>
          </div>
          <div class="notification-copy">
            <strong>${notification.title}</strong>
            <p>${notification.message}</p>
            <small>${notification.seen ? "Seen" : "New"} · ${notification.createdAt}</small>
          </div>
          <button class="notification-delete" type="button" aria-label="Delete notification">
            <i data-lucide="trash-2"></i>
          </button>
        `;
        item.querySelector(".notification-delete").addEventListener("click", () => {
          const current = FinSight.notifications.read();
          const updated = current.filter((entry) => entry.id !== notification.id);
          FinSight.notifications.save(updated);
          FinSight.notifications.render();
          FinSight.notifications.updateBadge();
        });
        listEl.appendChild(item);
      });
    }
    if (window.lucide) window.lucide.createIcons();
  },
  openModal: () => {
    let modal = document.getElementById("notificationModal");
    if (!modal) {
      FinSight.notifications.ensureModalInDOM();
      modal = document.getElementById("notificationModal");
    }
    const current = FinSight.notifications.read();
    const marked = current.map((item) => ({ ...item, seen: true }));
    FinSight.notifications.save(marked);
    FinSight.notifications.updateBadge();
    FinSight.notifications.render();
    if (modal) modal.hidden = false;
  },
  closeModal: () => {
    const modal = document.getElementById("notificationModal");
    if (modal) modal.hidden = true;
  },
  ensureModalInDOM: () => {
    if (document.getElementById("notificationModal")) return;
    const modalDiv = document.createElement("div");
    modalDiv.className = "notification-modal";
    modalDiv.id = "notificationModal";
    modalDiv.setAttribute("role", "dialog");
    modalDiv.setAttribute("aria-modal", "true");
    modalDiv.setAttribute("aria-labelledby", "notificationTitle");
    modalDiv.hidden = true;
    modalDiv.innerHTML = `
      <div class="notification-card">
        <div class="notification-head">
          <div>
            <div class="eyebrow">Budget alerts</div>
            <h2 id="notificationTitle">Notifications</h2>
          </div>
          <div class="notification-actions">
            <label class="select-all-notifications">
              <input id="selectAllNotifications" type="checkbox"> Select all
            </label>
            <button class="secondary" id="deleteSelectedNotifications" type="button">Delete selected</button>
            <button class="close" id="closeNotifications" type="button" aria-label="Close notifications">×</button>
          </div>
        </div>
        <div class="notification-list" id="notificationList"></div>
      </div>
    `;
    document.body.appendChild(modalDiv);
    FinSight.notifications.attachModalListeners(modalDiv);
  },
  attachModalListeners: (modal) => {
    if (!modal || modal._hasListeners) return;
    modal._hasListeners = true;
    modal.querySelector("#closeNotifications")?.addEventListener("click", () => {
      modal.hidden = true;
    });
    modal.addEventListener("click", (e) => {
      if (e.target === modal) modal.hidden = true;
    });
    modal.querySelector("#selectAllNotifications")?.addEventListener("change", (e) => {
      document.querySelectorAll("#notificationList input[data-notification-id]").forEach((input) => {
        input.checked = e.target.checked;
      });
    });
    modal.querySelector("#deleteSelectedNotifications")?.addEventListener("click", () => {
      const selected = new Set(
        [...document.querySelectorAll("#notificationList input[data-notification-id]:checked")]
          .map((input) => input.dataset.notificationId)
      );
      const current = FinSight.notifications.read();
      const updated = current.filter((item) => !selected.has(item.id));
      FinSight.notifications.save(updated);
      FinSight.notifications.render();
      FinSight.notifications.updateBadge();
      const selectAll = document.getElementById("selectAllNotifications");
      if (selectAll) selectAll.checked = false;
    });
  },
  checkBudgetAlerts: async () => {
    try {
      const res = await FinSight.api("/budgets?limit=100");
      const budgets = res?.items || [];
      if (!budgets.length) return;
      const month = new Date().toISOString().slice(0, 7);
      const thresholds = [50, 75, 100];
      const notifications = FinSight.notifications.read();
      const existing = new Set(notifications.map((item) => item.id));
      let added = false;

      await Promise.all(budgets.map(async (budget) => {
        try {
          const usage = await FinSight.api(`/budgets/${encodeURIComponent(budget.id)}/progress`);
          if (!usage) return;
          const pct = Number(usage.percentage_used || 0);
          thresholds.forEach((threshold) => {
            const id = `${budget.id}:${month}:${threshold}`;
            if (pct >= threshold && !existing.has(id)) {
              notifications.push({
                id,
                seen: false,
                severity: threshold === 100 ? "danger" : "warning",
                title: `${budget.category ? budget.category.replace(/\b\w/g, (c) => c.toUpperCase()) : "Budget"} reached ${threshold}%`,
                message: `${FinSight.money(usage.spent_amount)} used of ${FinSight.money(usage.budget_amount)}. ${threshold === 100 ? "The budget limit has been reached." : "Review your spending to stay within the limit."}`,
                createdAt: new Date().toLocaleString("en-IN"),
              });
              existing.add(id);
              added = true;
            }
          });
        } catch {
          // ignore single budget error
        }
      }));

      if (added) {
        FinSight.notifications.save(notifications);
      }
      FinSight.notifications.updateBadge();
    } catch {
      // ignore
    }
  },
  init: () => {
    const notifyBtn = document.getElementById("notifyBtn");
    if (!notifyBtn) return;
    FinSight.notifications.ensureModalInDOM();
    const modal = document.getElementById("notificationModal");
    if (modal) FinSight.notifications.attachModalListeners(modal);

    if (!notifyBtn._hasNotifyListener) {
      notifyBtn._hasNotifyListener = true;
      notifyBtn.addEventListener("click", () => {
        FinSight.notifications.openModal();
      });
    }

    FinSight.notifications.updateBadge();
    FinSight.notifications.checkBudgetAlerts();
  },
};

function isCurrentPage(linkPage, current) {
  if (!current) return linkPage === "Overview";
  const a = linkPage.toLowerCase();
  const b = current.toLowerCase();
  if (a === b) return true;
  if (a.includes("goal") && b.includes("goal")) return true;
  if (a.includes("insight") && b.includes("insight")) return true;
  return false;
}

function renderShell() {
  const sidebar = document.getElementById("sidebar");
  if (sidebar) {
    const current = document.body.dataset.page || "Overview";
    sidebar.innerHTML = `
      <a class="brand" href="dashboard.html">
        <span class="brand-icon">
          <i data-lucide="chart-no-axes-combined"></i>
        </span>
        <span>
          <div class="brand-name">FinSight AI</div>
          <div class="brand-tag">Smarter Finance. Brighter Future.</div>
        </span>
      </a>

      <div class="section-label">Your workspace</div>

      <nav class="nav">
        ${pageLinks.map(([label, href, icon]) => {
          const activeClass = isCurrentPage(label, current) ? "active" : "";
          return `<a class="${activeClass}" href="${href}" data-page="${label}"><i data-lucide="${icon}"></i> ${label}</a>`;
        }).join("")}
      </nav>

      <div class="side-bottom">
        <div class="side-tip">
          <div class="side-tip-title">
            <i data-lucide="lightbulb"></i> A little money wisdom
          </div>
          <p>Small, consistent reviews can make your spending easier to understand and your goals easier to reach.</p>
        </div>

        <div class="account">
          <span class="avatar" data-user-initial>D</span>
          <div>
            <div class="account-name" data-user-name>Personal account</div>
            <div class="account-sub">Personal account</div>
          </div>
        </div>
      </div>`;

    const menu = document.getElementById("menuBtn");
    menu?.addEventListener("click", () => sidebar.classList.toggle("open"));
  }

  const profileBtn = document.getElementById("profileBtn");
  if (profileBtn && !profileBtn._hasListener) {
    profileBtn._hasListener = true;
    profileBtn.addEventListener("click", () => {
      const name = document.querySelector("[data-user-name]")?.textContent.trim() || "Personal account";
      FinSight.toast(`Signed in as ${name}.`, "success");
    });
  }

  const storedUser = localStorage.getItem("finsight_user_name") || "Personal account";
  document.querySelectorAll("[data-user-name]").forEach((el) => {
    el.textContent = storedUser;
  });
  document.querySelectorAll("[data-user-initial]").forEach((el) => {
    el.textContent = storedUser.charAt(0).toUpperCase();
  });

  if (window.lucide) window.lucide.createIcons();
}

document.addEventListener("DOMContentLoaded", () => {
  renderShell();
  FinSight.notifications.init();
  const year = document.getElementById("year");
  if (year) year.textContent = String(new Date().getFullYear());

  // Attach hover pause and click dismiss immediately if topPopup is already in DOM
  const popup = document.getElementById("topPopup");
  if (popup) {
    const closeBtn = popup.querySelector("#topPopupClose") || popup.querySelector(".top-popup-close");
    if (closeBtn && !closeBtn._hasTopPopupListener) {
      closeBtn._hasTopPopupListener = true;
      closeBtn.addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
        FinSight.hideTopPopup();
      });
    }
    if (!popup._hasHoverListeners) {
      popup._hasHoverListeners = true;
      popup.addEventListener("mouseenter", () => FinSight.pauseTopPopup());
      popup.addEventListener("mouseleave", () => FinSight.resumeTopPopup());
    }
  }
});

// Global delegated dismiss for top popups across all pages
document.addEventListener("click", (event) => {
  const closeBtn = event.target && event.target.closest && event.target.closest("#topPopupClose, .top-popup-close");
  if (closeBtn) {
    event.preventDefault();
    event.stopPropagation();
    FinSight.hideTopPopup();
  }
});

// Allow user to instantly dismiss active top popup or notification modal with Escape key
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    const popup = document.getElementById("topPopup");
    if (popup && popup.classList.contains("show")) {
      FinSight.hideTopPopup();
    }
    const notifModal = document.getElementById("notificationModal");
    if (notifModal && !notifModal.hidden) {
      notifModal.hidden = true;
    }
  }
});
