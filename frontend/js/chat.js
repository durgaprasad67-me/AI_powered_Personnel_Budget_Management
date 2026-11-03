"use strict";

const API_BASE_URL =
  window.FINSIGHT_API_URL || "http://127.0.0.1:8000/api/v1";

const conversation = document.getElementById("conversation");
const questionForm = document.getElementById("questionForm");
const questionInput = document.getElementById("question");
const recommendations = document.getElementById("recommendations");
const sendButton = document.getElementById("sendButton");
const formStatus = document.getElementById("formStatus");
const selectedMonth = new URLSearchParams(window.location.search).get("month");
const monthNames = [
  "january",
  "february",
  "march",
  "april",
  "may",
  "june",
  "july",
  "august",
  "september",
  "october",
  "november",
  "december",
];

function formatLocalDate(date) {
  return [
    date.getFullYear(),
    String(date.getMonth() + 1).padStart(2, "0"),
    String(date.getDate()).padStart(2, "0"),
  ].join("-");
}

function addMessage(text, role) {
  const message = document.createElement("div");
  const avatar = document.createElement("span");
  const bubble = document.createElement("div");

  message.className = `message ${role}`;
  avatar.className = "message-avatar";
  avatar.textContent = role === "assistant" ? "✦" : "You";
  bubble.className = "bubble";
  bubble.textContent = text;
  message.append(avatar, bubble);
  conversation.appendChild(message);
  conversation.scrollTop = conversation.scrollHeight;
}

function formatInsight(result) {
  const sections = [result.summary];

  if (result.key_findings?.length) {
    sections.push(`Key findings:\n${result.key_findings.map((item) => `• ${item}`).join("\n")}`);
  }

  if (result.recommendations?.length) {
    sections.push(
      `Recommendations:\n${result.recommendations
        .map((item) => `• ${item.title}: ${item.explanation}`)
        .join("\n")}`,
    );
  }

  if (result.limitations?.length) {
    sections.push(`Notes:\n${result.limitations.map((item) => `• ${item}`).join("\n")}`);
  }

  return sections.join("\n\n");
}

function getErrorMessage(error) {
  if (typeof error === "string") return error;

  if (error && typeof error === "object") {
    if (typeof error.detail === "string") return error.detail;
    if (error.detail && typeof error.detail === "object") {
      if (Array.isArray(error.detail)) {
        return error.detail
          .map((item) => item.msg || "Please check your question.")
          .join(" ");
      }

      return "Please check your question and try again.";
    }
    if (typeof error.message === "string") return error.message;
  }

  return "The AI request could not be completed.";
}

function isGreeting(question) {
  return /^(hi|hello|hey|good morning|good afternoon|good evening)[!. ]*$/i.test(
    question,
  );
}

function getQuestionMonth(question, now) {
  const monthIndex = monthNames.findIndex((month) =>
    new RegExp(`\\b${month}\\b`, "i").test(question),
  );

  if (monthIndex < 0) return null;

  const yearMatch = question.match(/\b20\d{2}\b/);
  const year = yearMatch ? Number(yearMatch[0]) : now.getFullYear();

  return `${year}-${String(monthIndex + 1).padStart(2, "0")}`;
}

async function askChat(question) {
  const response = await fetch(`${API_BASE_URL}/ai/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      message: question,
      month: selectedMonth || null,
      include_recommendations: recommendations.checked,
    }),
  });

  if (!response.ok) {
    let detail = `AI request failed (${response.status}).`;

    try {
      const error = await response.json();
      detail = getErrorMessage(error) || detail;
    } catch {
      // Keep the status-based message when the server does not return JSON.
    }

    throw new Error(detail);
  }

  return response.json();
}

questionForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const question = questionInput.value.trim();

  if (!question) return;

  addMessage(question, "user");
  questionInput.value = "";

  if (isGreeting(question)) {
    addMessage(
      "Hi! I’m FinSight AI. Ask me about your spending, budgets, or financial goals.",
      "assistant",
    );
    formStatus.className = "";
    formStatus.textContent = "Ready to help";
    questionInput.focus();
    return;
  }

  if (question.length < 3) {
    addMessage(
      "Please enter at least 3 characters. For example: “Where am I spending most?”",
      "assistant",
    );
    formStatus.className = "error";
    formStatus.textContent = "Question is too short";
    questionInput.focus();
    return;
  }

  sendButton.disabled = true;
  formStatus.className = "";
  formStatus.textContent = "Analyzing your data...";

  try {
    const result = await askChat(question);
    addMessage(result.message, "assistant");
    formStatus.textContent = "Analysis complete";
  } catch (error) {
    console.error("AI insight request failed:", error);
    addMessage(
      `${getErrorMessage(error)} Check that the backend is running and Gemini is configured.`,
      "assistant",
    );
    formStatus.className = "error";
    formStatus.textContent = "Unable to complete analysis";
  } finally {
    sendButton.disabled = false;
    questionInput.focus();
  }
});

document.querySelectorAll("[data-question]").forEach((button) => {
  button.addEventListener("click", () => {
    questionInput.value = button.dataset.question;
    questionInput.focus();
  });
});
