// ==========================================================
// scripts.js (drop-in replacement)
// - Keeps your routes and behaviors
// - Single DOMContentLoaded block (no duplication)
// - Adds ARIA + Escape close for menus/modals
// - Robust SSE with exponential backoff
// - Drag-and-drop previews with object URLs (cheaper than FileReader)
// ==========================================================

// ---------- CSRF helpers ----------
function getCsrf() {
  return (
    document.querySelector('meta[name="csrf-token"]')?.content ||
    document.querySelector('input[name="csrf_token"]')?.value ||
    ""
  );
}

function addCsrfToForm(form) {
  const hidden = document.createElement("input");
  hidden.type = "hidden";
  hidden.name = "csrf_token";
  hidden.value = getCsrf();
  form.appendChild(hidden);
  return form;
}

function csrfFetch(url, options = {}) {
  const headers = new Headers(options.headers || {});
  headers.set("X-CSRF-Token", getCsrf());
  headers.set("X-Requested-With", "XMLHttpRequest");
  return fetch(url, { ...options, headers });
}

// ---------- Generic utils ----------
function $(sel, root = document) { return root.querySelector(sel); }
function $all(sel, root = document) { return Array.from(root.querySelectorAll(sel)); }
function onClick(sel, handler) {
  document.addEventListener("click", (e) => {
    const el = e.target.closest(sel);
    if (el) {
      e.preventDefault();
      handler(el, e);
    }
  });
}

function formatDate(isoDateStr) {
  if (!isoDateStr) return "";
  const date = new Date(isoDateStr);
  return date.toLocaleDateString("en-GB"); // dd/MM/yyyy
}

// ---------- Auth / simple actions ----------
function logout() {
  const form = addCsrfToForm(document.createElement("form"));
  form.method = "POST";
  form.action = "/logout";
  document.body.appendChild(form);
  form.submit();
}

function downloadImage(imageName) {
  window.location.href = `/download/${encodeURIComponent(imageName)}`;
}

function deleteImage(imageName) {
  if (!confirm(`Are you sure you want to delete ${imageName}?`)) return;
  const form = addCsrfToForm(document.createElement("form"));
  form.method = "POST";
  form.action = `/delete/${encodeURIComponent(imageName)}`;
  document.body.appendChild(form);
  form.submit();
}

// ---------- Top menu (hamburger) ----------
function initMenu() {
  const menu = $("#dropdown-menu");
  const hamburger = $("#hamburger");
  if (!menu || !hamburger) return;

  function showMenu() {
    menu.style.display = "flex";
    hamburger.setAttribute("aria-expanded", "true");
    const first = menu.querySelector("button, a, [tabindex]");
    if (first) first.focus();
  }

  function hideMenu() {
    menu.style.display = "none";
    hamburger.setAttribute("aria-expanded", "false");
  }

  hamburger.addEventListener("click", () => {
    const isOpen = menu.style.display === "flex";
    isOpen ? hideMenu() : showMenu();
  });

  document.addEventListener("click", (e) => {
    const isClickInsideMenu = menu.contains(e.target);
    const isClickOnHamburger = hamburger.contains(e.target);
    if (!isClickInsideMenu && !isClickOnHamburger) {
      hideMenu();
    }
  });

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") hideMenu();
  });
}

// ---------- Bottom drawer (Edit Images panel) ----------
function toggleSettings() {
  const panel = document.getElementById("bottom-scrollable");
  if (!panel) return;
  const isHidden = panel.style.display === "none" || panel.style.display === "";
  panel.style.display = isHidden ? "flex" : "none";
}

function initDrawer() {
  onClick("#btn-edit-images", () => toggleSettings());
  onClick("#btn-close-settings", () => toggleSettings());
}

// ---------- Logs modal (div-based) ----------
function openLogsModal() {
  const m = document.getElementById("logsModal");
  if (m) {
    m.style.display = "block";
    fetchLogs();
  }
}

function closeLogsModal() {
  const m = document.getElementById("logsModal");
  if (m) m.style.display = "none";
}

function fetchLogs() {
  fetch("/logs")
    .then((res) => res.json())
    .then((data) => {
      const t = document.getElementById("logText");
      if (t) t.value = (data.logs || []).join("\n");
    });
}

function downloadLogs() {
  window.location.href = "/download_logs";
}

function clearLogs() {
  csrfFetch("/clear_logs", { method: "POST" })
    .then((res) => res.json())
    .then((data) => {
      alert(data.message || "Logs cleared");
      const t = document.getElementById("logText");
      if (t) t.value = "";
    })
    .catch(() => alert("Failed to clear logs"));
}

function initLogsModal() {
  onClick("#btn-logs", () => openLogsModal());
  onClick("#logs-close", () => closeLogsModal());
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closeLogsModal();
  });
  onClick("#btn-download-logs", () => downloadLogs());
  onClick("#btn-clear-logs", () => clearLogs());
}

// ---------- App settings modal (div-based) ----------
function openAppSettingsModal() {
  const m = document.getElementById("appSettingsModal");
  if (m) m.style.display = "block";
}

function closeAppSettingsModal() {
  const m = document.getElementById("appSettingsModal");
  if (m) m.style.display = "none";
}

function initAppSettingsModal() {
  onClick("#btn-app-settings", () => openAppSettingsModal());
  onClick("#app-settings-close", () => closeAppSettingsModal());
  onClick("#app-settings-cancel", () => closeAppSettingsModal());
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closeAppSettingsModal();
  });
}

// ---------- Edit metadata modal (div-based) ----------
function openEditModal(imageName) {
  fetch(`/image_metadata?filename=${encodeURIComponent(imageName)}`)
    .then((res) => res.json())
    .then((data) => {
      if (!data || data.error) {
        alert("Failed to load metadata");
        return;
      }
      $("#editImageName").value = imageName;
      $("#editCaption").value = data.caption || "";
      $("#editUploader").value = data.uploader || "";
      $("#editDateAdded").value = formatDate(data.date_added);
      $("#editHash").value = data.hash || "";
      $("#editModal").style.display = "block";
    })
    .catch((err) => {
      alert("Could not open edit modal");
      console.error(err);
    });
}

function closeEditModal() {
  const m = document.getElementById("editModal");
  if (m) m.style.display = "none";
}

function submitEditForm(event) {
  event.preventDefault();
  const payload = {
    hash: $("#editHash").value,
    caption: $("#editCaption").value,
    uploader: $("#editUploader").value
  };
  csrfFetch("/update_metadata", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  })
    .then((res) => res.json())
    .then((data) => {
      alert(data.message || "Metadata updated.");
      closeEditModal();
      // optional: refresh the visible metadata without reload
      // location.reload();
    })
    .catch(() => alert("Failed to update metadata"));
}

function initEditModal() {
  onClick(".image-card .btn-edit", (btn) => {
    const name = btn.dataset.image || btn.closest(".image-card")?.dataset.image;
    if (name) openEditModal(name);
  });
  onClick("#edit-close", () => closeEditModal());
  onClick("#edit-cancel", () => closeEditModal());
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closeEditModal();
  });
  const editForm = $("#editForm");
  if (editForm) editForm.addEventListener("submit", submitEditForm);
}

// ---------- Upload modal (div-based) ----------
function openUploadModal() {
  const m = document.getElementById("uploadModal");
  if (m) m.style.display = "block";
}

function closeUploadModal() {
  const m = document.getElementById("uploadModal");
  if (m) m.style.display = "none";
}

function handleDrop(event) {
  event.preventDefault();
  const files = event.dataTransfer.files;
  const input = document.getElementById("fileInput");
  if (input) {
    // Safari fallback: DataTransfer may be restricted; try assignment first
    try { input.files = files; } catch (_) { /* ignore */ }
  }
  previewFiles();
}

function previewFiles() {
  const container = document.getElementById("previewContainer");
  const input = document.getElementById("fileInput");
  if (!container || !input || !input.files) return;

  // Revoke any old object URLs to avoid leaks
  $all(".image-preview [data-objurl]").forEach((img) => {
    try { URL.revokeObjectURL(img.getAttribute("data-objurl")); } catch (_) {}
  });

  container.innerHTML = "";
  const files = input.files;

  for (let i = 0; i < files.length; i++) {
    const objUrl = URL.createObjectURL(files[i]); // cheaper than FileReader for previews

    const div = document.createElement("div");
    div.classList.add("image-preview");
    div.innerHTML = `
      <img src="${objUrl}" data-objurl="${objUrl}" style="max-width: 300px; max-height: 300px; object-fit: cover;" />
      <table>
        <tr><td>Uploader:</td><td><input name="uploader_${i}" placeholder="(optional)" /></td></tr>
        <tr><td>Caption:</td><td><input name="caption_${i}" placeholder="(optional)" /></td></tr>
      </table>
    `;
    container.appendChild(div);
  }
}

function initUploadModal() {
  onClick("#btn-upload", () => openUploadModal());
  onClick("#upload-close", () => closeUploadModal());
  onClick("#upload-cancel", () => closeUploadModal());

  onClick("#btn-browse", () => {
    const fileInput = document.getElementById("fileInput");
    if (fileInput) fileInput.click();
  });

  const dropZone = document.getElementById("dropZone");
  if (dropZone) {
    dropZone.addEventListener("dragover", (e) => e.preventDefault(), { passive: false });
    dropZone.addEventListener("drop", handleDrop);
    dropZone.addEventListener("click", () => {
      const fileInput = document.getElementById("fileInput");
      if (fileInput) fileInput.click();
    });
    dropZone.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        const fileInput = document.getElementById("fileInput");
        if (fileInput) fileInput.click();
      }
    });
  }

  const fileInput = document.getElementById("fileInput");
  if (fileInput) {
    fileInput.addEventListener("change", previewFiles);
  }

  const form = document.getElementById("uploadForm");
  if (form) {
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      const input = document.getElementById("fileInput");
      const previews = document.querySelectorAll("#previewContainer .image-preview");
      if (!input || !input.files || !input.files.length) return alert("No files selected.");

      const formData = new FormData();
      formData.append("csrf_token", getCsrf());

      for (let i = 0; i < previews.length; i++) {
        const file = input.files[i];
        const preview = previews[i];
        formData.append("file[]", file);
        formData.append(`uploader_${i}`, (preview.querySelector(`input[name="uploader_${i}"]`)?.value || "").trim());
        formData.append(`caption_${i}`,  (preview.querySelector(`input[name="caption_${i}"]`)?.value  || "").trim());
      }

      csrfFetch("/upload_with_metadata", { method: "POST", body: formData })
        .then(async (res) => {
          const data = await res.json().catch(() => ({}));
          if (!res.ok) throw new Error(data.error || data.message || `Upload failed (${res.status})`);
          return data;
        })
        .then((data) => {
          alert(data.message || "Upload successful!");
          closeUploadModal();
          location.reload();
        })
        .catch((err) => {
          alert(err.message || "Upload failed.");
          console.error(err);
        });
    });
  }
}

// ---------- Bulk actions ----------
function getSelectedFiles() {
  return Array.from(document.querySelectorAll(".select-checkbox:checked")).map((cb) => cb.value);
}

function downloadSelected() {
  const selected = getSelectedFiles();
  if (!selected.length) return alert("No images selected.");

  const form = addCsrfToForm(document.createElement("form"));
  form.method = "POST";
  form.action = "/download_selected";
  selected.forEach((filename) => {
    const input = document.createElement("input");
    input.type = "hidden";
    input.name = "selected_files";
    input.value = filename;
    form.appendChild(input);
  });
  document.body.appendChild(form);
  form.submit();
}

function deleteSelected() {
  const selected = getSelectedFiles();
  if (!selected.length) return alert("No images selected.");
  if (!confirm(`Are you sure you want to delete ${selected.length} image(s)?`)) return;

  const form = addCsrfToForm(document.createElement("form"));
  form.method = "POST";
  form.action = "/delete_selected";
  selected.forEach((filename) => {
    const input = document.createElement("input");
    input.type = "hidden";
    input.name = "selected_files";
    input.value = filename;
    form.appendChild(input);
  });
  document.body.appendChild(form);
  form.submit();
}

function initBulkActions() {
  onClick("#btn-download-selected", () => downloadSelected());
  onClick("#btn-delete-selected", () => deleteSelected());
}

// ---------- Metadata live updates (SSE with backoff) ----------
function initMetadataStream() {
  const url = "/metadata_stream";
  let es = null;
  let attempt = 0;
  const maxDelay = 10000;

  function connect() {
    es = new EventSource(url, { withCredentials: true });

    es.onmessage = (e) => {
      attempt = 0;
      try {
        const data = JSON.parse(e.data || "{}");
        $("#captionField").textContent  = data.caption || "No Caption";
        $("#uploaderField").textContent = data.uploader || "Unknown";
        $("#dateField").textContent     = data.date_added
          ? new Date(data.date_added).toLocaleDateString("en-GB")
          : "Unknown";
      } catch (_) {}
    };

    es.onerror = () => {
      try { es.close(); } catch (_) {}
      attempt = Math.min(attempt + 1, 6);
      const delay = Math.min(500 * attempt, maxDelay);
      setTimeout(connect, delay);
    };
  }

  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible" && (!es || es.readyState === 2)) {
      connect();
    }
  });

  window.addEventListener("beforeunload", () => {
    try { es && es.close(); } catch (_) {}
  });

  connect();
}

// ---------- Wire up everything once ----------
document.addEventListener("DOMContentLoaded", () => {
  console.log("✅ DOM is ready");

  initMenu();
  initDrawer();
  initLogsModal();
  initAppSettingsModal();
  initEditModal();
  initUploadModal();
  initBulkActions();
  initMetadataStream();

  // Also wire existing buttons that call functions directly
  onClick("#btn-upload", () => openUploadModal());
  onClick("#btn-logout", () => logout());
});
