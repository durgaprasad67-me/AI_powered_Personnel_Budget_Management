"use strict";

/**
 * FinSight AI — Import Data Page
 * Two-phase import workflow (validate -> commit) with client-side pre-checks,
 * live stepper progress, accessible modals, focus trapping, and formula injection protection.
 */

const import$ = (id) => document.getElementById(id);

const ALLOWED_EXTENSIONS = [".csv", ".xlsx", ".xls", ".pdf", ".docx", ".txt"];
const MAX_FILE_SIZE = 5 * 1024 * 1024; // 5 MB

let uploadInProgress = false;
let currentUploadedFile = null;
let currentImportSession = null; // { token, filename, total, valid, duplicates, newCount }
let lastActiveElement = null;
let currentFocusTrapCleanup = null;
let currentReportIssues = [];

/* ==========================================================================
   Utilities & Security
   ========================================================================== */

function escapeHTML(value) {
  if (value == null) return "";
  return String(value).replace(/[&<>"']/g, (character) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#039;",
  }[character]));
}

function sanitizeForCsv(value) {
  const str = String(value == null ? "" : value).trim();
  // Prevent CSV / Excel formula injection (CSV Injection / CWE-1236)
  if (/^[=+\-@\t\r]/.test(str)) {
    return `'${str}`;
  }
  return str;
}

function downloadCsv(filename, rows) {
  const csvContent = rows
    .map((row) =>
      row
        .map((cell) => `"${sanitizeForCsv(cell).replace(/"/g, '""')}"`)
        .join(",")
    )
    .join("\r\n");

  const blob = new Blob(["\uFEFF" + csvContent], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.setAttribute("href", url);
  link.setAttribute("download", filename);
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

function formatFileSize(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

function formatTypeLabel(type) {
  const labels = {
    income: "Income",
    expense: "Expense",
    investment: "Investment",
    investment_return: "Investment return",
    loan_taken: "Loan taken",
    loan_repaid: "Loan repaid",
    loan_given: "Loan given",
    loan_collected: "Loan collected",
  };
  return labels[type] || (type ? type.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()) : "Expense");
}

/* ==========================================================================
   Accessibility & Focus Trap
   ========================================================================== */

function trapFocus(modalEl) {
  if (!modalEl) return () => {};
  const focusableSelector = 'button:not([disabled]), [tabindex]:not([tabindex="-1"]), a[href], input:not([disabled])';
  const focusableElements = Array.from(modalEl.querySelectorAll(focusableSelector));

  if (focusableElements.length) {
    focusableElements[0].focus();
  }

  function handleKeyDown(event) {
    if (event.key !== "Tab") return;
    const currentElements = Array.from(modalEl.querySelectorAll(focusableSelector));
    if (!currentElements.length) return;

    const first = currentElements[0];
    const last = currentElements[currentElements.length - 1];

    if (event.shiftKey) {
      if (document.activeElement === first || document.activeElement === modalEl) {
        event.preventDefault();
        last.focus();
      }
    } else {
      if (document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }
  }

  modalEl.addEventListener("keydown", handleKeyDown);
  return () => modalEl.removeEventListener("keydown", handleKeyDown);
}

function openModal(modalEl) {
  if (!modalEl) return;
  lastActiveElement = document.activeElement;
  modalEl.classList.add("show");
  modalEl.setAttribute("aria-hidden", "false");
  if (currentFocusTrapCleanup) currentFocusTrapCleanup();
  currentFocusTrapCleanup = trapFocus(modalEl);
}

function closeModal(modalEl) {
  if (!modalEl) return;
  modalEl.classList.remove("show");
  modalEl.setAttribute("aria-hidden", "true");
  if (currentFocusTrapCleanup) {
    currentFocusTrapCleanup();
    currentFocusTrapCleanup = null;
  }
  if (lastActiveElement && typeof lastActiveElement.focus === "function") {
    lastActiveElement.focus();
    lastActiveElement = null;
  }
}

/* ==========================================================================
   Client-Side Pre-Checks
   ========================================================================== */

function validateFileClientSide(file) {
  if (!file) {
    return { valid: false, message: "" };
  }

  const name = file.name || "";
  const lastDot = name.lastIndexOf(".");
  const ext = lastDot !== -1 ? name.substring(lastDot).toLowerCase() : "";

  if (!ALLOWED_EXTENSIONS.includes(ext)) {
    return {
      valid: false,
      message: `Unsupported file format "${escapeHTML(ext || "unknown")}". Supported formats: CSV, Excel (.xlsx, .xls), PDF, Word (.docx), TXT.`,
    };
  }

  if (file.size === 0) {
    return {
      valid: false,
      message: `The selected file "${escapeHTML(name)}" is empty (0 bytes). Please choose a file containing transactions.`,
    };
  }

  if (file.size > MAX_FILE_SIZE) {
    return {
      valid: false,
      message: `File size (${formatFileSize(file.size)}) exceeds the 5 MB limit. Please select a smaller file or split the records.`,
    };
  }

  return { valid: true, message: "" };
}

function handleFileSelection() {
  const fileInput = import$("importFile");
  const selectedLabel = import$("selectedFile");
  const submitBtn = import$("submitImportBtn");

  const file = fileInput?.files?.[0] || null;
  currentUploadedFile = file;

  if (!file) {
    if (selectedLabel) selectedLabel.textContent = "No file selected";
    if (submitBtn) submitBtn.disabled = true;
    return;
  }

  const precheck = validateFileClientSide(file);
  if (!precheck.valid) {
    if (selectedLabel) selectedLabel.textContent = `${file.name} (${formatFileSize(file.size)})`;
    if (submitBtn) submitBtn.disabled = true;
    resetStepper();
    FinSight.toast(precheck.message, "error");
    return;
  }

  // Valid file
  if (selectedLabel) {
    selectedLabel.textContent = `${file.name} (${formatFileSize(file.size)})`;
  }
  if (submitBtn) submitBtn.disabled = false;
}

function clearFileInput(resetResults = true) {
  currentUploadedFile = null;
  const fileInput = import$("importFile");
  if (fileInput) fileInput.value = "";
  const selectedLabel = import$("selectedFile");
  if (selectedLabel) selectedLabel.textContent = "No file selected";
  const submitBtn = import$("submitImportBtn");
  if (submitBtn) submitBtn.disabled = true;
  if (resetResults) {
    resetStepper();
  }
}

/* ==========================================================================
   Stepper Component
   ========================================================================== */

function updateStepper(stepNum, statusMsg, isError = false) {
  const stepperWrap = import$("importStepperWrap");
  const emptyHint = import$("emptyStateHint");
  const statusEl = import$("stepperStatusMsg");

  if (stepperWrap) stepperWrap.hidden = false;
  if (emptyHint) emptyHint.hidden = true;
  if (statusEl) {
    statusEl.textContent = statusMsg || "";
    statusEl.className = isError ? "stepper-status-msg error" : "stepper-status-msg";
  }

  const stepIds = ["stepValidate", "stepDedupe", "stepImport", "stepEmbed", "stepDone"];
  stepIds.forEach((id, index) => {
    const el = import$(id);
    if (!el) return;
    const stepIndex = index + 1;
    el.classList.remove("active", "completed", "error");

    if (stepIndex < stepNum) {
      el.classList.add("completed");
    } else if (stepIndex === stepNum) {
      if (isError) {
        el.classList.add("error");
      } else {
        el.classList.add("active");
      }
    }
  });
}

function resetStepper() {
  const stepperWrap = import$("importStepperWrap");
  const emptyHint = import$("emptyStateHint");
  const resultDetails = import$("importResultDetails");
  if (stepperWrap) stepperWrap.hidden = true;
  if (emptyHint) emptyHint.hidden = false;
  if (resultDetails) resultDetails.innerHTML = "";
}

/* ==========================================================================
   Validation Error Modal
   ========================================================================== */

function showValidationErrorModal(data) {
  const modal = import$("validationErrorModal");
  if (!modal) return;

  const titleEl = import$("validationErrorTitle");
  const subtitleEl = import$("validationErrorSubtitle");
  const chipsEl = import$("errorSummaryChips");
  const groupedListEl = import$("errorGroupedList");
  const tableBodyEl = import$("errorTableBody");
  const overflowEl = import$("errorOverflowNote");

  const title = data.title || "Validation Failed";
  if (titleEl) titleEl.textContent = title;

  const rawErrors = Array.isArray(data.errors) ? data.errors : [];
  const hasRowErrors = rawErrors.some((e) => e.row != null);

  // If there are row issues, show a clean instruction instead of a single row's error in the header
  if (subtitleEl) {
    if (hasRowErrors) {
      subtitleEl.textContent = "Please review the row-by-row issues below, correct them in your file, and upload again.";
    } else {
      subtitleEl.textContent = data.message || "Fix the issues below and upload the file again.";
    }
  }

  const summary = data.summary || {};
  const total = summary.total_rows || 0;
  const valid = summary.valid || 0;
  const invalid = summary.invalid != null ? summary.invalid : rawErrors.length;

  // Render chips
  if (chipsEl) {
    chipsEl.innerHTML = `
      <span class="error-chip chip-total"><strong>${total}</strong> total rows</span>
      <span class="error-chip chip-valid"><strong>${valid}</strong> valid</span>
      <span class="error-chip chip-invalid"><strong>${invalid}</strong> invalid</span>
      ${data.code ? `<span class="error-chip chip-category">Code: ${escapeHTML(data.code)}</span>` : ""}
    `;
  }

  // Render grouped issues
  const grouped = Array.isArray(data.grouped_errors) ? data.grouped_errors : [];
  if (groupedListEl) {
    if (grouped.length) {
      groupedListEl.innerHTML = grouped
        .map((grp) => {
          const rowsList = Array.isArray(grp.rows) ? grp.rows.join(", ") : "";
          return `
            <div class="error-group-card">
              <div class="error-group-title">${escapeHTML(grp.message || grp.code)}</div>
              <div class="error-group-meta">
                ${grp.count} occurrence${grp.count === 1 ? "" : "s"}${grp.column ? ` in column <strong>${escapeHTML(grp.column)}</strong>` : ""}
              </div>
              ${rowsList ? `<div class="error-group-rows">Affected rows: ${escapeHTML(rowsList)}</div>` : ""}
            </div>
          `;
        })
        .join("");
      import$("errorGroupedSection").hidden = false;
    } else {
      groupedListEl.innerHTML = "";
      import$("errorGroupedSection").hidden = true;
    }
  }

  // Deduplicate exact duplicate error objects if any
  const seenErrors = new Set();
  const uniqueErrors = [];
  for (const err of rawErrors) {
    const key = `${err.row}_${err.column}_${err.code}_${err.message}`;
    if (!seenErrors.has(key)) {
      seenErrors.add(key);
      uniqueErrors.push(err);
    }
  }
  currentReportIssues = uniqueErrors;

  // Render detailed issues table
  if (tableBodyEl) {
    if (uniqueErrors.length) {
      const displayErrors = uniqueErrors.slice(0, 50);
      tableBodyEl.innerHTML = displayErrors
        .map((err) => {
          const rowDisplay = err.row != null ? `Row ${err.row}` : "File";
          const colDisplay = err.column ? escapeHTML(err.column) : "—";
          const codeDisplay = err.code ? escapeHTML(err.code) : "VALIDATION_ERROR";
          const msgDisplay = err.message || "Invalid value";

          return `
            <tr>
              <td><span class="error-row-badge">${escapeHTML(rowDisplay)}</span></td>
              <td><span class="error-col-badge">${colDisplay}</span></td>
              <td><span class="error-code-badge">${codeDisplay}</span></td>
              <td>${escapeHTML(msgDisplay)}</td>
            </tr>
          `;
        })
        .join("");
      import$("errorTableSection").hidden = false;

      if (uniqueErrors.length > 50) {
        if (overflowEl) {
          overflowEl.textContent = `Showing first 50 of ${uniqueErrors.length} issues. Download the CSV report below for the full list.`;
          overflowEl.hidden = false;
        }
      } else {
        if (overflowEl) overflowEl.hidden = true;
      }
    } else {
      tableBodyEl.innerHTML = `<tr><td colspan="4" style="text-align: center; color: #64748b;">${escapeHTML(data.message || "No specific row issues reported.")}</td></tr>`;
    }
  }

  // Configure 'Import valid rows only' button
  const validBtn = import$("importValidRowsBtn");
  const validCount = summary.valid != null ? summary.valid : 0;
  const activeFile = currentUploadedFile || import$("importFile")?.files?.[0];

  if (validBtn) {
    if (validCount > 0 && activeFile) {
      const rowWord = validCount === 1 ? "row" : "rows";
      const recordWord = validCount === 1 ? "record" : "records";
      validBtn.textContent = `Import valid ${rowWord} only (${validCount} ${recordWord})`;
      validBtn.hidden = false;
    } else {
      validBtn.hidden = true;
    }
  }

  openModal(modal);
}

function handleDownloadErrorReport() {
  if (!currentReportIssues.length) {
    FinSight.toast("No row issues to export.", "info");
    return;
  }
  const rows = [
    ["Row", "Column", "Code", "Message", "Sample Value"],
    ...currentReportIssues.map((iss) => [
      iss.row != null ? iss.row : "",
      iss.column || "",
      iss.code || "",
      iss.message || "",
      iss.sample_value != null ? iss.sample_value : (iss.value != null ? iss.value : ""),
    ]),
  ];
  downloadCsv("finsight_import_error_report.csv", rows);
}

function handleDownloadSampleTemplate() {
  const rows = [
    ["Date", "Description", "Amount", "Type", "Category"],
    ["2026-01-05", "Monthly salary", "52000", "income", "salary"],
    ["2026-01-11", "Apartment rent", "14500", "expense", "housing"],
    ["2026-02-03", "Freelance website work", "8200", "income", "freelance"],
    ["2026-02-17", "Vegetable market", "1350", "expense", "food"],
    ["2026-03-08", "Annual insurance premium", "9600", "expense", "insurance"],
    ["2026-03-22", "Interest earned", "740", "income", "interest"],
    ["2026-04-04", "Bus pass", "1200", "expense", "transport"],
    ["2026-04-19", "Laptop repair", "3400", "expense", "electronics"],
  ];
  downloadCsv("sample_transactions_template.csv", rows);
}

/* ==========================================================================
   Duplicate Confirmation Modal
   ========================================================================== */

function showDuplicateConfirmModal(data) {
  const modal = import$("duplicateConfirmModal");
  if (!modal) return;

  currentImportSession = {
    token: data.import_token,
    filename: data.filename || "Uploaded file",
  };

  const titleEl = import$("duplicateModalTitle");
  const subtitleEl = import$("duplicateModalSubtitle");
  if (titleEl) titleEl.textContent = data.title || "Duplicates Detected";
  if (subtitleEl) subtitleEl.textContent = data.message || "Some records in this file already exist in your database.";

  const summary = data.summary || {};
  const dup = data.duplicates || {};

  import$("dupTotalCount").textContent = summary.total_rows || 0;
  import$("dupDuplicateCount").textContent = dup.count || summary.duplicates || 0;
  import$("dupNewCount").textContent = summary.new || 0;
  import$("dupRatio").textContent = `${Math.round((dup.ratio || 0) * 100)}%`;

  const confirmNewBtn = import$("confirmImportNewOnlyBtn");
  const confirmAllBtn = import$("confirmImportAllBtn");
  const newCount = summary.new != null ? summary.new : 0;
  const totalCount = summary.total_rows || 0;
  const newRecordLabel = newCount === 1 ? "record" : "records";
  const totalRecordLabel = totalCount === 1 ? "record" : "records";

  if (confirmNewBtn) {
    confirmNewBtn.textContent = newCount > 0
      ? `Import new records only (${newCount} ${newRecordLabel})`
      : "Import new records only (Recommended)";
  }
  if (confirmAllBtn) {
    confirmAllBtn.textContent = totalCount > 0
      ? `Import all including duplicates (${totalCount} ${totalRecordLabel})`
      : "Import all (including duplicates)";
  }

  const sampleBody = import$("duplicateSampleBody");
  const sample = Array.isArray(dup.sample) ? dup.sample : [];
  if (sampleBody) {
    if (sample.length) {
      sampleBody.innerHTML = sample
        .map(
          (row) => `
        <tr>
          <td>${escapeHTML(row.date || "—")}</td>
          <td><strong>${escapeHTML(row.description || "—")}</strong></td>
          <td>₹${Number(row.amount || 0).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</td>
          <td><span class="badge type-badge ${escapeHTML(row.transaction_type || "expense")}">${escapeHTML(formatTypeLabel(row.transaction_type))}</span></td>
          <td><span class="badge category-badge">${escapeHTML(row.category || "General")}</span></td>
        </tr>
      `
        )
        .join("");
    } else {
      sampleBody.innerHTML = `<tr><td colspan="5" style="text-align: center; color: #64748b;">No sample preview available.</td></tr>`;
    }
  }

  openModal(modal);
}

/* ==========================================================================
   Two-Phase Upload & Commit Orchestration
   ========================================================================== */

async function startImportFlow(file, allowPartial = false) {
  if (uploadInProgress) return;
  uploadInProgress = true;
  currentUploadedFile = file;

  const submitBtn = import$("submitImportBtn");
  const clearBtn = import$("clearImportFile");

  if (submitBtn) {
    submitBtn.disabled = true;
    submitBtn.setAttribute("aria-busy", "true");
    submitBtn.textContent = allowPartial ? "Importing valid..." : "Validating...";
  }
  if (clearBtn) clearBtn.disabled = true;

  updateStepper(1, allowPartial ? "Validating and staging valid rows..." : "Validating file and table structure...");

  const form = new FormData();
  form.append("file", file);
  if (allowPartial) {
    form.append("allow_partial", "true");
  }

  try {
    const response = await FinSight.api("/imports/validate", {
      method: "POST",
      body: form,
    });

    handleValidateSuccess(response, file.name);
  } catch (error) {
    handleValidateError(error);
  } finally {
    uploadInProgress = false;
    if (submitBtn) {
      submitBtn.disabled = false;
      submitBtn.removeAttribute("aria-busy");
      submitBtn.textContent = "Upload and import";
    }
    if (clearBtn) clearBtn.disabled = false;
  }
}

function handleValidateSuccess(data, filename) {
  if (data.status === "needs_confirmation" || (data.duplicates && data.duplicates.count > 0)) {
    updateStepper(2, "Duplicates detected — awaiting confirmation.");
    showDuplicateConfirmModal({ ...data, filename });
  } else if (data.status === "ready") {
    updateStepper(2, "Checking duplicates... No duplicates found.");
    // Auto-proceed to commit only when zero duplicates exist
    void executeCommit(data.import_token, "import_new_only", filename);
  } else {
    updateStepper(1, data.message || "File validated successfully.");
  }
}

function handleValidateError(error) {
  const details = error.details || error.data || {};
  const status = details.status || error.status;
  const code = details.code || error.code || "VALIDATION_FAILED";

  if (status === "needs_confirmation" || details.status === "needs_confirmation" || (details.duplicates && details.duplicates.count > 0)) {
    updateStepper(2, "Duplicates detected — awaiting confirmation.");
    showDuplicateConfirmModal(details);
    return;
  }

  if (code === "ALL_DUPLICATES" || code === "FILE_ALREADY_IMPORTED") {
    updateStepper(2, details.message || "Duplicate file detected", true);
    showValidationErrorModal(details);
    return;
  }

  // Row or file validation failure (HTTP 422, 415, 413)
  updateStepper(1, details.message || error.message || "Validation failed", true);

  // Normalize issues / errors list
  let errorList = [];
  if (Array.isArray(details.errors) && details.errors.length) {
    errorList = details.errors;
  } else if (Array.isArray(details.invalid_rows) && details.invalid_rows.length) {
    errorList = details.invalid_rows.map((r) => {
      if (r && (r.code || r.column || r.message)) {
        return {
          row: r.row != null ? r.row : null,
          column: r.column || "",
          code: r.code || "ROW_INVALID",
          message: r.message || r.msg || "Invalid value",
          sample_value: r.sample_value != null ? r.sample_value : null,
        };
      }
      return {
        row: r.row != null ? r.row : null,
        column: r.column || (r.field || ""),
        code: r.code || "ROW_INVALID",
        message: (r.errors || []).map((e) => e.msg || e.message).join("; ") || r.message || "Invalid value",
        sample_value: r.sample_value != null ? r.sample_value : null,
      };
    });
  }

  // Summary object
  const summary = details.summary || {
    total_rows: details.total_records != null ? details.total_records : (details.total_rows || 0),
    valid: details.valid_records != null ? details.valid_records : (details.valid || 0),
    invalid: details.invalid_records != null ? details.invalid_records : (details.invalid != null ? details.invalid : (errorList.length || 0)),
  };

  showValidationErrorModal({
    ...details,
    title: details.title || "Validation Failed",
    message: details.message || error.message || "The file could not be parsed or validated.",
    code: code,
    summary: summary,
    errors: errorList,
    grouped_errors: details.grouped_errors || [],
  });
}

async function executeCommit(importToken, duplicateStrategy, filename) {
  if (!importToken) {
    FinSight.toast("Invalid import session. Please re-upload.", "error");
    return;
  }

  updateStepper(3, "Saving transactions to database...");
  const submitBtn = import$("submitImportBtn");
  if (submitBtn) {
    submitBtn.disabled = true;
    submitBtn.textContent = "Saving...";
  }

  try {
    // Show step 4 transition
    setTimeout(() => {
      updateStepper(4, "Creating search and AI embeddings...");
    }, 400);

    const result = await FinSight.api("/imports/commit", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        import_token: importToken,
        duplicate_strategy: duplicateStrategy,
      }),
    });

    updateStepper(5, "Complete! All records processed successfully.");
    renderResult({ ...result, filename });
    clearFileInput(false);
    FinSight.toast(result.message || "Import completed successfully.", "success");
  } catch (err) {
    updateStepper(3, err.message || "Failed to commit import records.", true);
    FinSight.toast(err.message || "Failed to save transactions.", "error");
  } finally {
    if (submitBtn) {
      submitBtn.disabled = false;
      submitBtn.textContent = "Upload and import";
    }
  }
}

/* ==========================================================================
   Render Success Result Table
   ========================================================================== */

function renderResult(result) {
  const resultCard = import$("importResult");
  const detailsEl = import$("importResultDetails");
  const emptyHint = import$("emptyStateHint");
  if (!resultCard || !detailsEl) return;

  if (emptyHint) emptyHint.hidden = true;

  const records = Array.isArray(result.records)
    ? result.records
    : (Array.isArray(result.items) ? result.items : (Array.isArray(result.data) ? result.data : []));
  const filename = result.filename ? escapeHTML(result.filename) : "Uploaded file";
  const message = result.message || "Transactions imported successfully.";
  const count = result.imported_records != null ? result.imported_records : records.length;
  const recordsLabel = count === 1 ? "transaction" : "transactions";

  detailsEl.innerHTML = `
    <div class="result-heading">
      <span class="result-icon" aria-hidden="true">✓</span>
      <div>
        <h2>${escapeHTML(message)}</h2>
        <p>${filename}</p>
      </div>
    </div>
    <div class="import-stats">
      <div><strong>${count}</strong><span>${recordsLabel} imported</span></div>
      <div><strong>${result.total_records != null ? result.total_records : count}</strong><span>records processed</span></div>
      ${result.summary?.duplicates ? `<div><strong>${result.summary.duplicates}</strong><span>duplicates skipped</span></div>` : ""}
    </div>
    ${renderRecordsTable(records, count)}
  `;

  resultCard.hidden = false;
  detailsEl.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

function renderRecordsTable(records, totalCount) {
  const count = totalCount || (records ? records.length : 0);
  if (!count && (!records || !records.length)) return "";

  if (!records || !records.length) {
    return `
      <details class="import-details" open>
        <summary class="import-details-summary" aria-label="Toggle imported transactions table">
          <div class="import-summary-left">
            <span class="dropdown-chevron-icon" aria-hidden="true">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                <polyline points="6 9 12 15 18 9"></polyline>
              </svg>
            </span>
            <span class="import-summary-title">View all imported transactions (${count})</span>
          </div>
          <span class="import-details-tag">Click to collapse / expand ▾</span>
        </summary>
        <div style="padding: 24px; text-align: center; color: #64748b;">
          All ${count} transactions have been saved to your account.
        </div>
        <div class="import-actions-bar">
          <span>All ${count} records processed</span>
          <a class="view-transactions-btn" href="transactions.html">
            View in Transactions page ↗
          </a>
        </div>
      </details>
    `;
  }

  return `
    <details class="import-details" open>
      <summary class="import-details-summary" aria-label="Toggle imported transactions table">
        <div class="import-summary-left">
          <span class="dropdown-chevron-icon" aria-hidden="true">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
              <polyline points="6 9 12 15 18 9"></polyline>
            </svg>
          </span>
          <span class="import-summary-title">View all imported transactions (${count})</span>
        </div>
        <span class="import-details-tag">Click to collapse / expand ▾</span>
      </summary>
      <div class="table-wrap import-table-wrap" tabindex="0" role="region" aria-label="Scrollable imported transactions table">
        <table class="import-table">
          <thead>
            <tr>
              <th style="width: 120px;">Date</th>
              <th>Description</th>
              <th style="width: 140px;">Category</th>
              <th style="width: 140px;">Type</th>
              <th style="width: 130px; text-align: right;">Amount</th>
            </tr>
          </thead>
          <tbody>
            ${records
              .map((row) => {
                const type = row.transaction_type || row.type || "expense";
                const isOutflow = ["expense", "investment", "loan_repaid", "loan_given"].includes(type);
                const amountClass = isOutflow ? "outflow" : "inflow";
                const amountPrefix = isOutflow ? "-" : "+";
                const formattedMoney =
                  window.FinSight && window.FinSight.money
                    ? window.FinSight.money(row.amount)
                    : `₹${Number(row.amount || 0).toLocaleString("en-IN", {
                        minimumFractionDigits: 2,
                        maximumFractionDigits: 2,
                      })}`;
                return `
                <tr>
                  <td><span class="date-cell">${escapeHTML(row.date || "—")}</span></td>
                  <td><strong>${escapeHTML(row.description || "—")}</strong></td>
                  <td><span class="badge category-badge">${escapeHTML(row.category || "General")}</span></td>
                  <td><span class="badge type-badge ${escapeHTML(type)}">${escapeHTML(formatTypeLabel(type))}</span></td>
                  <td class="amount-cell ${amountClass}">${amountPrefix}${escapeHTML(formattedMoney)}</td>
                </tr>
              `;
              })
              .join("")}
          </tbody>
        </table>
      </div>
      <div class="import-actions-bar">
        <span>Showing all ${records.length} imported ${records.length === 1 ? "record" : "records"} · Scroll vertically to view all</span>
        <a class="view-transactions-btn" href="transactions.html">
          View in Transactions page ↗
        </a>
      </div>
    </details>
  `;
}

/* ==========================================================================
   Initialization & Event Listeners
   ========================================================================== */

function initImportPage() {
  const form = import$("importForm");
  const fileInput = import$("importFile");
  const dropZone = import$("dropZone");
  const clearBtn = import$("clearImportFile");

  // File selection
  if (fileInput) {
    fileInput.addEventListener("change", handleFileSelection);
  }

  // Clear button
  if (clearBtn) {
    clearBtn.addEventListener("click", clearFileInput);
  }

  // Drag and Drop
  if (dropZone) {
    ["dragenter", "dragover"].forEach((eventName) => {
      dropZone.addEventListener(eventName, (e) => {
        e.preventDefault();
        dropZone.classList.add("is-dragging");
      });
    });

    ["dragleave", "drop"].forEach((eventName) => {
      dropZone.addEventListener(eventName, (e) => {
        e.preventDefault();
        dropZone.classList.remove("is-dragging");
      });
    });

    dropZone.addEventListener("drop", (e) => {
      const file = e.dataTransfer?.files?.[0];
      if (file && fileInput) {
        const transfer = new DataTransfer();
        transfer.items.add(file);
        fileInput.files = transfer.files;
        handleFileSelection();
      }
    });
  }

  // Form submit
  if (form) {
    form.addEventListener("submit", (e) => {
      e.preventDefault();
      const file = fileInput?.files?.[0];
      if (!file) {
        FinSight.toast("Please choose a transaction file first.", "warning");
        return;
      }
      const precheck = validateFileClientSide(file);
      if (!precheck.valid) {
        FinSight.toast(precheck.message, "error");
        return;
      }
      void startImportFlow(file);
    });
  }

  // Validation Error Modal Buttons
  const closeValidationBtn = import$("closeValidationErrorBtn");
  const dismissValidationBtn = import$("dismissValidationErrorBtn");
  const importValidRowsBtn = import$("importValidRowsBtn");
  const valModal = import$("validationErrorModal");

  if (closeValidationBtn) closeValidationBtn.addEventListener("click", () => closeModal(valModal));
  if (dismissValidationBtn) dismissValidationBtn.addEventListener("click", () => closeModal(valModal));
  if (importValidRowsBtn) {
    importValidRowsBtn.addEventListener("click", () => {
      const file = currentUploadedFile || import$("importFile")?.files?.[0];
      if (!file) {
        FinSight.toast("No file available to import. Please select your file again.", "error");
        return;
      }
      closeModal(valModal);
      void startImportFlow(file, true);
    });
  }
  if (valModal) {
    valModal.addEventListener("click", (e) => {
      if (e.target === valModal) closeModal(valModal);
    });
  }

  const downloadReportBtn = import$("downloadErrorReportBtn");
  if (downloadReportBtn) downloadReportBtn.addEventListener("click", handleDownloadErrorReport);

  const downloadTemplateBtn = import$("downloadSampleTemplateBtn");
  if (downloadTemplateBtn) downloadTemplateBtn.addEventListener("click", handleDownloadSampleTemplate);

  // Duplicate Confirmation Modal Buttons
  const dupModal = import$("duplicateConfirmModal");
  const closeDupBtn = import$("closeDuplicateModalBtn");
  const cancelDupBtn = import$("cancelDuplicateImportBtn");
  const confirmNewOnlyBtn = import$("confirmImportNewOnlyBtn");
  const confirmAllBtn = import$("confirmImportAllBtn");

  if (closeDupBtn) closeDupBtn.addEventListener("click", () => closeModal(dupModal));
  if (cancelDupBtn) {
    cancelDupBtn.addEventListener("click", () => {
      closeModal(dupModal);
      resetStepper();
      currentImportSession = null;
      FinSight.toast("Import cancelled.", "info");
    });
  }
  if (dupModal) {
    dupModal.addEventListener("click", (e) => {
      if (e.target === dupModal) closeModal(dupModal);
    });
  }

  if (confirmNewOnlyBtn) {
    confirmNewOnlyBtn.addEventListener("click", () => {
      if (!currentImportSession) return;
      const { token, filename } = currentImportSession;
      closeModal(dupModal);
      void executeCommit(token, "import_new_only", filename);
    });
  }

  if (confirmAllBtn) {
    confirmAllBtn.addEventListener("click", () => {
      if (!currentImportSession) return;
      const { token, filename } = currentImportSession;
      closeModal(dupModal);
      void executeCommit(token, "import_all", filename);
    });
  }

  // Global ESC key listener for modals
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      if (valModal && valModal.classList.contains("show")) closeModal(valModal);
      if (dupModal && dupModal.classList.contains("show")) closeModal(dupModal);
      const legacyModal = import$("importIssuesModal");
      if (legacyModal && legacyModal.classList.contains("show")) closeModal(legacyModal);
    }
  });
}

// Boot on DOMContentLoaded
if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", initImportPage);
} else {
  initImportPage();
}
