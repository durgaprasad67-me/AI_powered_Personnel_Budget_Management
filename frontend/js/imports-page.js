"use strict";
const import$ = (id) => document.getElementById(id);
let pendingPartialImport = null;
let uploadInProgress = false;

function escapeHTML(value) {
  return String(value).replace(/[&<>"']/g, (character) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#039;",
  }[character]));
}

function renderResult(result) {
  const resultCard = import$("importResult");
  if (!resultCard) return;

  if (Number.isFinite(result.total_records) && Number.isFinite(result.imported_records)) {
    const transactionIds = Array.isArray(result.transactions) ? result.transactions : [];
    const filename = result.filename ? escapeHTML(result.filename) : "Uploaded file";
    const message = result.message || "Transactions imported successfully.";
    const recordsLabel = result.imported_records === 1 ? "transaction" : "transactions";
    const idsMarkup = transactionIds.length
      ? `<details class="import-details"><summary>View imported transaction IDs</summary><p>${transactionIds.map(escapeHTML).join(", ")}</p></details>`
      : "";

    resultCard.className = "card result-card result-success";
    resultCard.innerHTML = `
      <div class="result-heading">
        <span class="result-icon" aria-hidden="true">✓</span>
        <div>
          <h2>${escapeHTML(message)}</h2>
          <p>${filename}</p>
        </div>
      </div>
      <div class="import-stats">
        <div><strong>${result.imported_records}</strong><span>${recordsLabel} imported</span></div>
        <div><strong>${result.total_records}</strong><span>records processed</span></div>
      </div>
      ${idsMarkup}`;
    return;
  }

  const message = result.message || "Operation completed successfully.";
  resultCard.className = "card result-card result-success";
  resultCard.innerHTML = `
    <div class="result-heading">
      <span class="result-icon" aria-hidden="true">✓</span>
      <div><h2>${escapeHTML(message)}</h2><p>Your file is ready to use.</p></div>
    </div>`;
}

function getSelectedFile(inputId) {
  const input = import$(inputId);
  return input?.files[0] || null;
}

function formatImportIssues(details) {
  const issues = [];
  if (details.message) issues.push(details.message);
  (details.missing_required || []).forEach((item) => {
    issues.push(`Record ${item.row}: missing ${item.columns.join(", ")}.`);
  });
  (details.invalid_rows || []).forEach((item) => {
    const messages = (item.errors || []).map((error) =>
      error.loc ? `${error.loc.join(".")}: ${error.msg || error.message}` : (error.message || "Invalid value"),
    );
    issues.push(`Record ${item.row}: ${messages.join("; ")}.`);
  });
  const unsupported = details.unsupported_columns || [];
  if (unsupported.length) {
    issues.push(`Unused columns: ${unsupported.join(", ")}. These columns are not used by FinSight AI.`);
  }
  return issues;
}

function showImportIssues(file, label, details) {
  pendingPartialImport = { file, label, validRecords: Number(details.valid_records || 0) };
  const issues = formatImportIssues(details);
  const valid = Number(details.valid_records || 0);
  const total = Number(details.total_records || 0);
  const canImportValidRows = valid > 0;
  import$("importIssuesContent").innerHTML = `
    <p>${valid} of ${total} records are valid. ${canImportValidRows ? "You can import the valid records and skip the rows listed below." : "There are no valid records to import."}</p>
    ${issues.length ? `<ul>${issues.map(escapeHTML).map((issue) => `<li>${issue}</li>`).join("")}</ul>` : ""}
    <div class="issue-note">Unsupported columns are ignored and are not imported.</div>`;
  import$("confirmPartialImport").disabled = !canImportValidRows;
  import$("importIssuesModal").classList.add("show");
  if (canImportValidRows) import$("confirmPartialImport").focus();
}

function closeImportIssues() {
  import$("importIssuesModal").classList.remove("show");
  pendingPartialImport = null;
}

async function upload(path, file, label, allowPartial = false) {
  if (uploadInProgress) return;
  uploadInProgress = true;
  const submitButton = importForm.querySelector('button[type="submit"]');
  const submitLabel = submitButton?.textContent || "Upload and import";
  const clearButton = import$("clearImportFile");
  const partialButton = import$("confirmPartialImport");
  if (submitButton) {
    submitButton.disabled = true;
    submitButton.setAttribute("aria-busy", "true");
    submitButton.textContent = label;
  }
  if (clearButton) clearButton.disabled = true;
  if (partialButton) partialButton.disabled = true;
  importForm.setAttribute("aria-busy", "true");
  const form = new FormData();
  form.append("file", file);
  const resultCard = import$("importResult");
  resultCard.className = "card result-card result-loading";
  resultCard.textContent = `${label}...`;
  try {
    form.append("allow_partial", String(allowPartial));
    const result = await FinSight.api(path, { method: "POST", body: form });
    renderResult(result);
    clearFileInput("importFile");
    FinSight.toast(`${result.imported_records || 0} transaction${result.imported_records === 1 ? "" : "s"} imported.`, "success");
  } catch (error) {
    const details = error.details;
    const hasRowDiagnostics = details
      && Number.isFinite(Number(details.total_records))
      && (Array.isArray(details.invalid_rows)
        || Array.isArray(details.missing_required)
        || Array.isArray(details.unsupported_columns));
    if (path === "/imports" && hasRowDiagnostics && !allowPartial) {
      showImportIssues(file, label, error.details);
      return;
    }
    resultCard.className = "card result-card result-error";
    const message = error.message || "Unable to import this file. Please try again.";
    resultCard.textContent = message;
    FinSight.toast(message);
  } finally {
    uploadInProgress = false;
    if (submitButton) {
      submitButton.disabled = false;
      submitButton.removeAttribute("aria-busy");
      submitButton.textContent = submitLabel;
    }
    if (clearButton) clearButton.disabled = false;
    importForm.removeAttribute("aria-busy");
    if (partialButton) {
      partialButton.disabled = !(pendingPartialImport?.validRecords > 0);
    }
  }
}

function clearFileInput(inputId) {
  const input = import$(inputId);
  if (input) {
    input.value = "";
    const selectedFile = import$("selectedFile");
    if (selectedFile) selectedFile.textContent = "No file selected";
  }
}

const importForm = import$("importForm");
const importFile = import$("importFile");
const dropZone = import$("dropZone");

function updateSelectedFile() {
  const file = importFile.files[0];
  import$("selectedFile").textContent = file ? file.name : "No file selected";
}

function isSupportedFile(file) {
  return /\.(csv|xlsx|xls|pdf|docx|txt)$/i.test(file.name);
}

function setDroppedFile(file) {
  if (!isSupportedFile(file)) {
    FinSight.toast("Choose a CSV, Excel, PDF, DOCX, or TXT file.");
    return;
  }

  const transfer = new DataTransfer();
  transfer.items.add(file);
  importFile.files = transfer.files;
  updateSelectedFile();
}

importFile.addEventListener("change", updateSelectedFile);
["dragenter", "dragover"].forEach((eventName) => {
  dropZone.addEventListener(eventName, (event) => {
    event.preventDefault();
    dropZone.classList.add("is-dragging");
  });
});
["dragleave", "drop"].forEach((eventName) => {
  dropZone.addEventListener(eventName, (event) => {
    event.preventDefault();
    dropZone.classList.remove("is-dragging");
  });
});
dropZone.addEventListener("drop", (event) => {
  const [file] = event.dataTransfer.files;
  if (file) setDroppedFile(file);
});

importForm.addEventListener("submit", (event) => {
  event.preventDefault();
  const file = getSelectedFile("importFile");
  if (file) {
    void upload("/imports", file, "Importing transactions");
  } else {
    FinSight.toast("Choose a transaction file first.");
  }
});
import$("clearImportFile").addEventListener("click", () => clearFileInput("importFile"));
import$("closeImportIssues").addEventListener("click", closeImportIssues);
import$("cancelPartialImport").addEventListener("click", closeImportIssues);
import$("confirmPartialImport").addEventListener("click", () => {
  if (!pendingPartialImport) return;
  const { file, label } = pendingPartialImport;
  closeImportIssues();
  void upload("/imports", file, label, true);
});
import$("importIssuesModal").addEventListener("click", (event) => {
  if (event.target === import$("importIssuesModal")) closeImportIssues();
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && import$("importIssuesModal").classList.contains("show")) closeImportIssues();
});
