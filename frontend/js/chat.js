"use strict";

const API_BASE_URL =
  window.FINSIGHT_API_URL || "http://127.0.0.1:8000/api/v1";
const conversation = document.getElementById("conversation");
const questionForm = document.getElementById("questionForm");
const questionInput = document.getElementById("question");
const sendButton = document.getElementById("sendButton");
const formStatus = document.getElementById("formStatus");
const uploadForm = document.getElementById("documentUploadForm");
const uploadInput = document.getElementById("documentFile");
const uploadButton = document.getElementById("uploadButton");
const uploadStatus = document.getElementById("uploadStatus");
const history = [];

function getErrorMessage(body, status) {
  if (status === 401 || status === 403) {
    return "Your session may have expired or access was denied. Refresh and sign in again.";
  }
  const detail = body?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail.map((item) => item.msg || "Please check the submitted values.").join(" ");
  }
  if (detail && typeof detail === "object") {
    return detail.message || "Please check the uploaded file or question.";
  }
  return `The request could not be completed (${status}).`;
}

async function requestJson(path, options = {}) {
  const response = await fetch(`${API_BASE_URL}${path}`, options);
  let body = null;
  try {
    body = await response.json();
  } catch {
    // Some errors may not include a JSON body.
  }
  if (!response.ok) {
    const error = new Error(getErrorMessage(body, response.status));
    error.status = response.status;
    error.retryAfter = response.headers.get("Retry-After");
    throw error;
  }
  return body;
}

function formatRequestError(error) {
  if (error.status === 429 || error.status === 503) {
    const seconds = Number(error.retryAfter);
    const retry = Number.isFinite(seconds) && seconds > 0
      ? ` Try again in about ${Math.ceil(seconds)} seconds.`
      : " Please try again shortly.";
    return `${error.message}${retry}`;
  }
  return error.message || "The request could not be completed.";
}

function addMessage(text, role, sourceChunks = null) {
  const message = document.createElement("div");
  const avatar = document.createElement("span");
  const bubble = document.createElement("div");
  message.className = `message ${role}`;
  avatar.className = "message-avatar";
  avatar.textContent = role === "assistant" ? "✦" : "You";
  bubble.className = "bubble";
  bubble.textContent = text;
  message.append(avatar, bubble);

  if (role === "assistant" && sourceChunks) {
    const details = document.createElement("details");
    details.className = "source-details";
    const summary = document.createElement("summary");
    summary.textContent = `Sources (${sourceChunks.length})`;
    details.appendChild(summary);
    if (!sourceChunks.length) {
      const empty = document.createElement("p");
      empty.textContent = "No supporting sources were retrieved.";
      details.appendChild(empty);
    } else {
      const list = document.createElement("ul");
      sourceChunks.forEach((source) => {
        const item = document.createElement("li");
        const label = source.page
          ? `${source.source}, page ${source.page}`
          : `${source.source}, chunk ${source.chunk_index}`;
        const score = Number(source.score).toFixed(2);
        item.textContent = `${label} · relevance ${score} · ${source.snippet}`;
        list.appendChild(item);
      });
      details.appendChild(list);
    }
    bubble.appendChild(details);
  }

  conversation.appendChild(message);
  conversation.scrollTop = conversation.scrollHeight;
}

async function askRag(question) {
  return requestJson("/ai/rag/ask", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, k: 4, history: history.slice(-8) }),
  });
}

questionForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (sendButton.disabled) return;
  const question = questionInput.value.trim();
  if (!question) {
    formStatus.className = "error";
    formStatus.textContent = "Enter a question first.";
    questionInput.focus();
    return;
  }
  if (question.length < 3) {
    formStatus.className = "error";
    formStatus.textContent = "Enter at least 3 characters.";
    questionInput.focus();
    return;
  }

  addMessage(question, "user");
  sendButton.disabled = true;
  formStatus.className = "";
  formStatus.textContent = "Searching your data...";
  try {
    const result = await askRag(question);
    addMessage(result.answer, "assistant", result.source_chunks || []);
    history.push(
      { role: "user", content: question },
      { role: "assistant", content: result.answer },
    );
    history.splice(0, Math.max(0, history.length - 8));
    questionInput.value = "";
    formStatus.textContent = "Answer ready";
  } catch (error) {
    const message = formatRequestError(error);
    addMessage(message, "assistant", []);
    formStatus.className = "error";
    formStatus.textContent = error.status === 422 ? "Check your question" : "Unable to answer";
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

uploadForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (uploadButton.disabled) return;
  const file = uploadInput.files?.[0];
  if (!file) {
    uploadStatus.className = "error";
    uploadStatus.textContent = "Choose a PDF, DOCX, TXT, CSV, or XLSX file.";
    return;
  }
  const form = new FormData();
  form.append("file", file);
  uploadButton.disabled = true;
  uploadStatus.className = "";
  uploadStatus.textContent = "Indexing document...";
  try {
    const result = await requestJson("/ai/rag/documents", {
      method: "POST",
      body: form,
    });
    uploadStatus.className = "success";
    uploadStatus.textContent = `${result.filename}: indexed ${result.chunks_created} chunks.`;
    uploadForm.reset();
  } catch (error) {
    uploadStatus.className = "error";
    uploadStatus.textContent = formatRequestError(error);
  } finally {
    uploadButton.disabled = false;
  }
});
