"use strict";
const report$ = (id) => document.getElementById(id);
const reportMonth = () => { const date = new Date(); return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}`; };
const reportYear = () => String(new Date().getFullYear());
function reportValue() { return report$("reportPeriod").value === "year" ? report$("reportYear").value : report$("reportMonth").value; }
function reportDateRange() {
  const value = reportValue();
  if (report$("reportPeriod").value === "year") return [`${value}-01-01`, `${value}-12-31`];
  const [year, month] = value.split("-").map(Number);
  const lastDay = new Date(year, month, 0).getDate();
  return [`${value}-01`, `${value}-${String(lastDay).padStart(2, "0")}`];
}
function apiBase() { return window.FINSIGHT_API_URL || "http://127.0.0.1:8000/api/v1"; }
async function reportData() { return FinSight.api(`/dashboard?month=${report$("reportMonth").value}`); }
let reportItems = [];
let downloadFocus = null;
let pendingReportAction = null;
async function loadReportPreview() {
  const rows = report$("reportPreviewRows");
  rows.innerHTML = '<tr><td class="loading" colspan="5">Loading report data...</td></tr>';
  try {
    const [startDate, endDate] = reportDateRange();
    const items = [];
    let skip = 0;
    let total = Infinity;
    while (items.length < total) {
      const query = new URLSearchParams({ start_date: startDate, end_date: endDate, limit: "100", skip: String(skip) });
      const data = await FinSight.api(`/transactions?${query}`);
      const page = Array.isArray(data.items) ? data.items : [];
      items.push(...page);
      total = Number.isFinite(Number(data.total)) ? Number(data.total) : items.length;
      if (!page.length) break;
      skip += page.length;
    }
    reportItems = items;
    report$("reportPreviewLabel").textContent = `${report$("reportPeriod").value === "year" ? "Year" : "Month"}: ${reportValue()}`;
    report$("reportPreviewCount").textContent = `${items.length} transaction${items.length === 1 ? "" : "s"}`;
    rows.replaceChildren();
    if (!items.length) {
      rows.innerHTML = '<tr><td class="empty" colspan="5">No data found for the selected period.</td></tr>';
      return;
    }
    items.forEach((item) => {
      const row = document.createElement("tr");
      [item.date, item.description, item.category, item.transaction_type, FinSight.money(item.amount)]
        .forEach((value) => { const cell = document.createElement("td"); cell.textContent = value || ""; row.appendChild(cell); });
      rows.appendChild(row);
    });
  } catch (error) {
    reportItems = [];
    rows.innerHTML = `<tr><td class="empty" colspan="5">${error.message}</td></tr>`;
    FinSight.toast(error.message);
  }
}
report$("reportMonth").value = reportMonth();
report$("reportYear").value = reportYear();
function updatePeriodInput() {
  const yearly = report$("reportPeriod").value === "year";
  report$("reportMonth").hidden = yearly;
  report$("reportYear").hidden = !yearly;
  report$("reportMonth").setAttribute("aria-hidden", String(yearly));
  report$("reportYear").setAttribute("aria-hidden", String(!yearly));
}
report$("reportPeriod").addEventListener("change", () => { updatePeriodInput(); void loadReportPreview(); });
report$("reportMonth").addEventListener("change", () => void loadReportPreview());
report$("reportYear").addEventListener("change", () => void loadReportPreview());
updatePeriodInput();
report$("downloadReport").addEventListener("click", async () => {
  try {
    openReportConfirmation("download");
  } catch (error) { FinSight.toast(error.message); }
});
function openReportConfirmation(action) {
  const period = report$("reportPeriod").value;
  const value = reportValue();
  const periodLabel = period === "year" ? "year" : "month";
  const format = report$("reportFormat").value;
  pendingReportAction = action;
  downloadFocus = document.activeElement;
  report$("downloadConfirmTitle").textContent = reportItems.length
    ? action === "print" ? "Print report?" : "Download report?"
    : "No data found";
  report$("downloadConfirmMessage").textContent = reportItems.length
    ? `${reportItems.length} transaction${reportItems.length === 1 ? "" : "s"} found for ${periodLabel} ${value}. Do you want to ${action === "print" ? "print" : `download the ${format.toUpperCase()}`} report?`
    : `No transactions were found for ${periodLabel} ${value}. Do you still want to ${action === "print" ? "print" : `download an empty ${format.toUpperCase()}`} report?`;
  report$("confirmDownload").textContent = action === "print" ? "Yes, print" : "Yes, download";
  report$("downloadConfirmModal").classList.add("show");
  report$("confirmDownload").focus();
}
async function downloadReport() {
  const period = report$("reportPeriod").value;
  const value = reportValue();
  const format = report$("reportFormat").value;
  closeDownloadConfirmation();
  try {
    const response = await fetch(`${window.FinSight.API_BASE_URL || window.FINSIGHT_API_URL || "http://127.0.0.1:8000/api/v1"}/reports/transactions?period=${period}&value=${encodeURIComponent(value)}&format=${format}`);
    if (!response.ok) throw new Error(`Report download failed (${response.status}).`);
    const link = document.createElement("a");
    link.href = URL.createObjectURL(await response.blob());
    link.download = `FinSight_Transactions_${value}.${format}`;
    link.click();
    URL.revokeObjectURL(link.href);
  } catch (error) { FinSight.toast(error.message); }
}
function printReport() {
  const period = report$("reportPeriod").value;
  const value = reportValue();
  closeDownloadConfirmation();
  const totalIncome = reportItems
    .filter((item) => item.transaction_type === "income")
    .reduce((total, item) => total + Number(item.amount || 0), 0);
  const totalExpenses = reportItems
    .filter((item) => item.transaction_type === "expense")
    .reduce((total, item) => total + Number(item.amount || 0), 0);
  const printWindow = window.open("", "_blank");
  if (!printWindow) {
    FinSight.toast("Please allow pop-ups to print the report.");
    return;
  }
  printWindow.document.write(
    `<title>FinSight AI report</title><h1>FinSight AI report - ${period === "year" ? "Year" : "Month"} ${value}</h1><p>Total income: ${FinSight.money(totalIncome)}</p><p>Total expenses: ${FinSight.money(totalExpenses)}</p><p>Balance: ${FinSight.money(totalIncome - totalExpenses)}</p><p>Transactions: ${reportItems.length}</p>`,
  );
  printWindow.document.close();
  printWindow.print();
}
function closeDownloadConfirmation() {
  report$("downloadConfirmModal").classList.remove("show");
  pendingReportAction = null;
  if (downloadFocus && typeof downloadFocus.focus === "function") downloadFocus.focus();
  downloadFocus = null;
}
report$("cancelDownload").addEventListener("click", closeDownloadConfirmation);
report$("confirmDownload").addEventListener("click", () => {
  if (pendingReportAction === "print") printReport();
  else void downloadReport();
});
report$("downloadConfirmModal").addEventListener("click", (event) => {
  if (event.target === report$("downloadConfirmModal")) closeDownloadConfirmation();
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && report$("downloadConfirmModal").classList.contains("show")) closeDownloadConfirmation();
});
report$("printReport").addEventListener("click", () => openReportConfirmation("print"));
void loadReportPreview();
