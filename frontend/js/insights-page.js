"use strict";

const insight$ = (id) => document.getElementById(id);

function renderInsight(result) {
  const root = insight$("insightResult");
  const isWarning = result.summary && (result.summary.includes("Access Denied") || result.summary.startsWith("⚠️"));

  // Filter out any findings that repeat the summary (preventing duplicate answers)
  const summaryNorm = (result.summary || "").trim().toLowerCase();
  const distinctFindings = (result.key_findings || []).filter((finding) => {
    const fNorm = (finding || "").trim().toLowerCase();
    if (!fNorm || fNorm === summaryNorm) return false;
    if (summaryNorm.length > 20 && (summaryNorm.includes(fNorm) || fNorm.includes(summaryNorm))) return false;
    return true;
  });

  // Omit recommendations for access denied warnings or when empty
  const activeRecs = isWarning ? [] : (result.recommendations || []);

  root.innerHTML = `
    ${isWarning ? `
      <div class="insight-warning-box">
        <div class="warning-badge"><i data-lucide="shield-alert"></i> Privacy Protection</div>
        <h2>${result.summary}</h2>
      </div>
    ` : `
      <h2>${result.summary}</h2>
    `}
    ${distinctFindings.length ? `
      <div class="result-section">
        <h3>Key findings</h3>
        <ul>${distinctFindings.map((x) => `<li>${x}</li>`).join("")}</ul>
      </div>
    ` : ""}
    ${activeRecs.length ? `
      <div class="result-section">
        <h3>Recommendations</h3>
        <ul>${activeRecs.map((x) => {
          const savings = x.estimated_monthly_savings ? ` <span class="savings-tag">(Estimated savings: ₹${Number(x.estimated_monthly_savings).toLocaleString('en-IN')}/mo)</span>` : '';
          const formattedExp = (x.explanation || '').replace(/\n/g, '<br>');
          return `<li><strong>${x.title}:</strong> ${formattedExp}${savings}</li>`;
        }).join("")}</ul>
      </div>
    ` : ""}
    ${result.limitations?.length ? `
      <div class="result-section">
        <h3>Notes</h3>
        <ul>${result.limitations.map((x) => `<li>${x}</li>`).join("")}</ul>
      </div>
    ` : ""}
  `;
  root.scrollTop = 0;
  if (window.lucide && typeof window.lucide.createIcons === "function") {
    window.lucide.createIcons();
  }
}

insight$("insightForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  insight$("insightResult").innerHTML = `
    <div class="loading">
      <div class="empty-icon"><i data-lucide="loader-2" class="spin"></i></div>
      <span>Analyzing your finances...</span>
    </div>
  `;
  if (window.lucide && typeof window.lucide.createIcons === "function") {
    window.lucide.createIcons();
  }

  try {
    const result = await FinSight.api("/ai/spending-insights", {
      method: "POST",
      body: JSON.stringify({
        question: insight$("question").value.trim(),
        include_recommendations: insight$("recommendations").checked,
      }),
    });
    renderInsight(result);
  } catch (error) {
    insight$("insightResult").innerHTML = `
      <div class="empty">
        <div class="empty-icon" style="background:#fff0ee;color:#b85b54;"><i data-lucide="alert-circle"></i></div>
        <span>${error.message}</span>
      </div>
    `;
    if (window.lucide && typeof window.lucide.createIcons === "function") {
      window.lucide.createIcons();
    }
  }
});

// Clear only the Question box (leaves the insight result box untouched)
insight$("clearQuestionBtn")?.addEventListener("click", () => {
  const questionInput = insight$("question");
  if (questionInput) {
    questionInput.value = "";
    questionInput.focus();
  }
});

if (window.lucide && typeof window.lucide.createIcons === "function") {
  window.lucide.createIcons();
}
