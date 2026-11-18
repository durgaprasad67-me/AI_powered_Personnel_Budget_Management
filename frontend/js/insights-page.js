"use strict";

const insight$ = (id) => document.getElementById(id);

function renderInsight(result) {
  const root = insight$("insightResult");
  root.innerHTML = `
    <h2>${result.summary}</h2>
    ${result.key_findings?.length ? `
      <div class="result-section">
        <h3>Key findings</h3>
        <ul>${result.key_findings.map((x) => `<li>${x}</li>`).join("")}</ul>
      </div>
    ` : ""}
    ${result.recommendations?.length ? `
      <div class="result-section">
        <h3>Recommendations</h3>
        <ul>${result.recommendations.map((x) => `<li><strong>${x.title}:</strong> ${x.explanation}</li>`).join("")}</ul>
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
    const now = new Date();
    const start = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-01`;
    const end = new Date(now.getFullYear(), now.getMonth() + 1, 0).toISOString().slice(0, 10);
    const result = await FinSight.api("/ai/spending-insights", {
      method: "POST",
      body: JSON.stringify({
        question: insight$("question").value.trim(),
        start_date: start,
        end_date: end,
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
