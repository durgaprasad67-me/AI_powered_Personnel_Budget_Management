"use strict";
const import$ = (id) => document.getElementById(id);
async function upload(path, file, label) { const form = new FormData(); form.append("file", file); import$("importResult").textContent = `${label}...`; try { const result = await FinSight.api(path, { method: "POST", body: form }); import$("importResult").textContent = JSON.stringify(result, null, 2); FinSight.toast("Operation completed."); } catch (error) { import$("importResult").textContent = error.message; FinSight.toast(error.message); } }
import$("importForm").addEventListener("submit", (event) => { event.preventDefault(); const file = import$("importFile").files[0]; if (file) void upload("/imports", file, "Importing transactions"); });
import$("documentForm").addEventListener("submit", (event) => { event.preventDefault(); const file = import$("documentFile").files[0]; if (file) void upload("/ai/rag/documents", file, "Indexing document"); });
