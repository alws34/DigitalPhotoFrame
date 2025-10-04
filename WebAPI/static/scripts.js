// ==========================================================
// scripts.js (drop-in replacement)
// - Single DOMContentLoaded block
// - <dialog> modals use showModal()/close() with Escape handling
// - Hamburger menu uses [hidden] consistently with ARIA
// - Robust SSE with exponential backoff
// - Drag-and-drop previews with object URLs (revoked to avoid leaks)
// - Drawer stays for image editing (not a modal); grid guarantees >=2 cols on desktop
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
function trapEscape(closeFn) {
  return (e) => { if (e.key === "Escape") closeFn(); };
}
function safeShowDialog(d) {
  try { d.showModal(); }
  catch (_) { d.removeAttribute("hidden"); d.style.display = "block"; }
}
function safeCloseDialog(d) {
  try { d.close(); }
  catch (_) { d.setAttribute("hidden", ""); d.style.display = "none"; }
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

// Keep for direct-link use in templates
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
    menu.hidden = false;
    hamburger.setAttribute("aria-expanded", "true");
    const first = menu.querySelector("button, a, [tabindex]");
    if (first) first.focus();
  }
  function hideMenu() {
    menu.hidden = true;
    hamburger.setAttribute("aria-expanded", "false");
  }

  hamburger.addEventListener("click", () => {
    const isOpen = hamburger.getAttribute("aria-expanded") === "true";
    isOpen ? hideMenu() : showMenu();
  });

  document.addEventListener("click", (e) => {
    if (!menu.hidden) {
      const isClickInsideMenu = menu.contains(e.target);
      const isClickOnHamburger = hamburger.contains(e.target);
      if (!isClickInsideMenu && !isClickOnHamburger) hideMenu();
    }
  });

  document.addEventListener("keydown", (e) => { if (e.key === "Escape") hideMenu(); });
}

// ---------- Drawer (Edit Images panel - NOT a modal) ----------
// ---------- Drawer (Edit Images panel - NOT a modal) ----------
function showDrawer(panel) {
  // remove [hidden] and any stale inline display:none
  panel.removeAttribute("hidden");
  panel.style.display = "";
  // optional: focus the first actionable control
  const first = panel.querySelector("button, input, [tabindex]");
  if (first) first.focus({ preventScroll: true });
  // if the dropdown menu is open, close it so the drawer is visible
  const menu = document.getElementById("dropdown-menu");
  const hamburger = document.getElementById("hamburger");
  if (menu && hamburger && hamburger.getAttribute("aria-expanded") === "true") {
    menu.hidden = true;
    hamburger.setAttribute("aria-expanded", "false");
  }
}
function hideDrawer(panel) {
  panel.setAttribute("hidden", "");
  // also clear any stale inline styles
  panel.style.display = "";
}
function toggleSettingsDrawer() {
  const panel = document.getElementById("bottom-scrollable");
  if (!panel) return;
  const isHidden = panel.hasAttribute("hidden") || panel.style.display === "none";
  isHidden ? showDrawer(panel) : hideDrawer(panel);
}
function initDrawer() {
  onClick("#btn-edit-images", () => toggleSettingsDrawer());
  onClick("#btn-close-settings", () => toggleSettingsDrawer());
}


// ---------- Logs modal (<dialog>) ----------
function initLogsModal() {
  const dlg = $("#logsModal");
  if (!dlg) return;

  function open() {
    fetchLogs();
    safeShowDialog(dlg);
  }
  function close() {
    safeCloseDialog(dlg);
  }

  onClick("#btn-logs", open);
  onClick("#logs-close", close);
  onClick("#btn-download-logs", () => window.location.href = "/download_logs");
  onClick("#btn-clear-logs", () => {
    csrfFetch("/clear_logs", { method: "POST" })
      .then(async (r) => {
        const data = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(data.error || "Failed to clear logs");
        alert(data.message || "Logs cleared");
        const t = $("#logText"); if (t) t.value = "";
      })
      .catch((e) => alert(e.message));
  });
  document.addEventListener("keydown", trapEscape(close));
}

function fetchLogs() {
  const t = document.getElementById("logText");
  if (t) t.value = "Loading...";
  fetch("/logs", { headers: { "X-Requested-With": "XMLHttpRequest" } })
    .then(async (res) => {
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.error || data.details || "Failed to load logs");
      const lines = data.logs || [];
      if (t) t.value = lines.length ? lines.join("\n") : "(no log lines found)";
    })
    .catch((err) => { if (t) t.value = `Error: ${err.message}`; });
}


// ---------- App settings modal (<dialog>) ----------
// ---------- Settings dynamic form renderer ----------
function toName(pathParts) {
  // ["backend_configs","server_port"] -> backend_configs[server_port]
  if (!pathParts.length) return "";
  const [head, ...rest] = pathParts;
  return head + rest.map(p => `[${p}]`).join("");
}
function coerceType(val) {
  if (typeof val === "boolean") return "boolean";
  if (typeof val === "number") return Number.isInteger(val) ? "integer" : "number";
  if (Array.isArray(val)) return "array";
  if (val === null) return "string";
  if (typeof val === "object") return "object";
  return "string";
}
function createLabeled(control, labelText, id) {
  const wrap = document.createElement("div");
  wrap.className = "form-group";
  if (labelText) {
    const label = document.createElement("label");
    label.setAttribute("for", id);
    label.textContent = labelText;
    wrap.appendChild(label);
  }
  wrap.appendChild(control);
  return wrap;
}
function createInputForPrimitive(path, key, value) {
  const id = `set_${path.concat(key).join("_")}`;
  const fullName = toName(path.concat(key));
  const t = coerceType(value);

  if (t === "boolean") {
    // Hidden false + checkbox true pattern so unchecked posts "false"
    const hidden = document.createElement("input");
    hidden.type = "hidden";
    hidden.name = fullName;
    hidden.value = "false";

    const cb = document.createElement("input");
    cb.type = "checkbox";
    cb.id = id;
    cb.name = fullName;
    cb.checked = !!value;
    cb.value = "true";

    const label = document.createElement("label");
    label.setAttribute("for", id);
    label.textContent = key;

    const div = document.createElement("div");
    div.className = "form-group";
    div.appendChild(hidden);
    div.appendChild(cb);
    div.appendChild(label);
    return div;
  }

  const input = document.createElement("input");
  input.id = id;
  input.name = fullName;

  if (t === "integer" || t === "number") {
    input.type = "number";
    input.step = t === "integer" ? "1" : "any";
    input.value = value ?? "";
  } else {
    input.type = "text";
    input.value = value ?? "";
  }
  return createLabeled(input, key, id);
}
function createArrayEditor(path, key, arr) {
  const fieldset = document.createElement("fieldset");
  const legend = document.createElement("legend");
  legend.textContent = key;
  fieldset.appendChild(legend);

  const list = document.createElement("div");
  list.className = "form-group";
  fieldset.appendChild(list);

  function addRow(idx, initialVal) {
    const row = document.createElement("div");
    row.style.display = "grid";
    row.style.gridTemplateColumns = "1fr auto";
    row.style.gap = "8px";
    const name = toName(path.concat([key, String(idx)]));

    const input = document.createElement("input");
    input.type = typeof initialVal === "number" ? "number" : "text";
    input.name = name;
    input.value = initialVal ?? "";

    const del = document.createElement("button");
    del.type = "button";
    del.textContent = "Remove";
    del.addEventListener("click", () => {
      row.remove();
      // Reindex remaining rows so server receives 0..N-1
      Array.from(list.children).forEach((r, i) => {
        const inp = r.querySelector("input");
        if (inp) {
          const parts = nameToParts(inp.name);
          // replace last part with new index
          parts[parts.length - 1] = String(i);
          inp.name = toName(parts);
        }
      });
    });

    row.appendChild(input);
    row.appendChild(del);
    list.appendChild(row);
  }

  (arr || []).forEach((v, i) => addRow(i, v));

  const addBtn = document.createElement("button");
  addBtn.type = "button";
  addBtn.textContent = "Add item";
  addBtn.addEventListener("click", () => {
    const idx = list.children.length;
    addRow(idx, "");
  });
  fieldset.appendChild(addBtn);
  return fieldset;
}
function nameToParts(name) {
  // backend_configs[foo][bar] -> ["backend_configs","foo","bar"]
  const parts = [];
  let i = 0;
  while (i < name.length) {
    const j = name.indexOf("[", i);
    if (j === -1) {
      parts.push(name.slice(i));
      break;
    }
    parts.push(name.slice(i, j));
    const k = name.indexOf("]", j);
    parts.push(name.slice(j + 1, k));
    i = k + 1;
  }
  return parts.filter(Boolean);
}
function renderSettingsObject(container, obj, path = []) {
  // For top-level, create fieldsets for objects. For primitives, just inputs.
  Object.keys(obj).forEach((key) => {
    const val = obj[key];
    const kind = coerceType(val);

    if (kind === "object") {
      const fieldset = document.createElement("fieldset");
      const legend = document.createElement("legend");
      legend.textContent = key;
      fieldset.appendChild(legend);
      renderSettingsObject(fieldset, val, path.concat(key));
      container.appendChild(fieldset);
    } else if (kind === "array") {
      container.appendChild(createArrayEditor(path, key, val));
    } else {
      container.appendChild(createInputForPrimitive(path, key, val));
    }
  });
}
async function populateSettingsForm() {
  const container = document.getElementById("settingsDynamicContainer");
  const form = document.getElementById("appSettingsForm");
  if (!container || !form) return;

  // Clear previous contents
  container.innerHTML = "";

  // Load current settings
  let data = {};
  try {
    const res = await fetch("/settings", { headers: { "X-Requested-With": "XMLHttpRequest" } });
    data = await res.json();
    if (!res.ok || !data || typeof data !== "object") throw new Error("Failed to load settings");
  } catch (e) {
    // Fallback to a minimal shape so user can recover
    data = {
      image_dir: "Images",
      image_quality_encoding: 80,
      backend_configs: { stream_width: 1920, stream_height: 1080, idle_fps: 5, server_port: 5001, host: "0.0.0.0" },
      weather_api_key: "",
      location_key: ""
    };
  }

  renderSettingsObject(container, data);
}
function initAppSettingsModal() {
  const dlg = $("#appSettingsModal");
  const form = $("#appSettingsForm");
  if (!dlg) return;

  async function open() {
    await populateSettingsForm();
    safeShowDialog(dlg);
  }
  function close() { safeCloseDialog(dlg); }

  onClick("#btn-app-settings", open);
  onClick("#app-settings-cancel", close);
  onClick("#app-settings-close", close);
  document.addEventListener("keydown", trapEscape(close));

  if (form) {
    // Disable Save during submit; allow server redirect to flash index
    form.addEventListener("submit", function () {
      const saveBtn = $("#app-settings-save");
      if (saveBtn) { saveBtn.disabled = true; saveBtn.textContent = "Saving..."; }
    });
  }
}


// ---------- Edit metadata modal (<dialog>) ----------
function initEditModal() {
  const dlg = $("#editModal");
  const editForm = $("#editForm");
  if (!dlg || !editForm) return;

  function openWith(imageName) {
    fetch(`/image_metadata?filename=${encodeURIComponent(imageName)}`)
      .then((res) => res.json())
      .then((data) => {
        if (!data || data.error) { alert("Failed to load metadata"); return; }
        $("#editImageName").value = imageName;
        $("#editCaption").value = data.caption || "";
        $("#editUploader").value = data.uploader || "";
        $("#editDateAdded").value = formatDate(data.date_added);
        $("#editHash").value = data.hash || "";
        safeShowDialog(dlg);
      })
      .catch((err) => { alert("Could not open edit modal"); console.error(err); });
  }

  onClick(".image-card .btn-edit", (btn) => {
    const name = btn.dataset.image || btn.closest(".image-card")?.dataset.image;
    if (name) openWith(name);
  });


  onClick("#edit-cancel", () => safeCloseDialog(dlg));
  document.addEventListener("keydown", trapEscape(() => safeCloseDialog(dlg)));

  editForm.addEventListener("submit", function (event) {
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
        safeCloseDialog(dlg);
      })
      .catch(() => alert("Failed to update metadata"));
  });
}

// ---------- Upload modal (<dialog>) ----------
function initUploadModal() {
  const dlg = $("#uploadModal");
  const previews = $("#previewContainer");

  const fileFromLibrary = $("#fileFromLibrary");
  const fileFromCamera = $("#fileFromCamera");

  // Defensive: make sure the library input has no capture attr
  if (fileFromLibrary) fileFromLibrary.removeAttribute("capture");

  function heicStatusBadge() {
    const el = document.createElement("div");
    el.id = "heicStatus";
    el.style.fontSize = "12px";
    el.style.opacity = "0.8";
    el.style.margin = "8px 0";
    const ok = (typeof window.heic2any === "function");
    el.textContent = ok
      ? "HEIC conversion: available (will preview & upload as JPEG)"
      : "HEIC conversion: unavailable (no preview; original HEIC will upload)";
    return el;
  }
  function open() {
    // Insert/update the status line at the top of the upload form
    const formEl = $("#uploadForm");
    if (formEl) {
      const existing = $("#heicStatus");
      if (existing) {
        existing.textContent =
          (typeof window.heic2any === "function")
            ? "HEIC conversion: available (will preview & upload as JPEG)"
            : "HEIC conversion: unavailable (no preview; original HEIC will upload)";
      } else {
        formEl.prepend(heicStatusBadge());
      }
    }
    safeShowDialog(dlg);
  }

  function close() {
    $all("#previewContainer .image-preview img[data-objurl]").forEach((img) => {
      try { URL.revokeObjectURL(img.getAttribute("data-objurl")); } catch (_) { }
    });
    if (previews) previews.innerHTML = "";
    if (fileFromLibrary) fileFromLibrary.value = "";
    if (fileFromCamera) fileFromCamera.value = "";
    safeCloseDialog(dlg);
  }

  onClick("#btn-upload", open);
  onClick("#upload-cancel", close);
  onClick("#upload-close", close);
  document.addEventListener("keydown", trapEscape(close));

  // Buttons → specific inputs
  onClick("#btn-choose-library", () => {
    // normalize accept just in case
    if (fileFromLibrary) {
      fileFromLibrary.setAttribute(
        "accept",
        "image/*,.heic,.heif,.jpg,.jpeg,.png,.gif,.webp"
      );
      fileFromLibrary.removeAttribute("capture");
      fileFromLibrary.click();
    }
  });

  onClick("#btn-take-photo", () => {
    if (fileFromCamera) {
      fileFromCamera.setAttribute("accept", "image/*");
      fileFromCamera.setAttribute("capture", "environment");
      fileFromCamera.click();
    }
  });

  // Preview handler (same function you already have)
  if (fileFromLibrary) fileFromLibrary.addEventListener("change", previewFiles);
  if (fileFromCamera) fileFromCamera.addEventListener("change", previewFiles);

  // Also allow clicking the drop zone to open the *chooser*
  const dropZone = $("#dropZone");
  if (dropZone) {
    dropZone.addEventListener("dragover", (e) => e.preventDefault(), { passive: false });
    dropZone.addEventListener("drop", (e) => {
      e.preventDefault();
      // Feed dropped files into the library input path
      if (fileFromLibrary && e.dataTransfer?.files?.length) {
        // NOTE: assigning FileList is not supported everywhere; we just call preview on DataTransfer
        previewFiles(e.dataTransfer.files);
      }
    });
    dropZone.addEventListener("click", () => fileFromLibrary && fileFromLibrary.click());
    dropZone.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); fileFromLibrary && fileFromLibrary.click(); }
    });
  }

  const form = $("#uploadForm");
  if (form) {
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      if (!stagedFiles.length) return alert("No files selected.");

      const blocks = $all("#previewContainer .image-preview");
      const fd = new FormData();
      fd.append("csrf_token", getCsrf());

      // keep indices aligned with preview blocks
      for (let i = 0; i < blocks.length; i++) {
        const f = stagedFiles[i];
        if (!f) continue;
        const block = blocks[i];
        fd.append("file[]", f, f.name);
        fd.append(`uploader_${i}`, (block.querySelector(`input[name="uploader_${i}"]`)?.value || "").trim());
        fd.append(`caption_${i}`, (block.querySelector(`input[name="caption_${i}"]`)?.value || "").trim());
      }

      csrfFetch("/upload_with_metadata", { method: "POST", body: fd })
        .then(async (res) => {
          const data = await res.json().catch(() => ({}));
          if (!res.ok) throw new Error(data.error || data.message || `Upload failed (${res.status})`);
          return data;
        })
        .then((data) => {
          alert(data.message || "Upload successful!");
          // reset and close
          stagedFiles = [];
          $all("#previewContainer .image-preview img[data-objurl]").forEach((img) => {
            try { URL.revokeObjectURL(img.getAttribute("data-objurl")); } catch (_) { }
          });
          $("#previewContainer").innerHTML = "";
          $("#fileFromLibrary") && ($("#fileFromLibrary").value = "");
          $("#fileFromCamera") && ($("#fileFromCamera").value = "");
          safeCloseDialog(dlg);
          location.reload();
        })
        .catch((err) => {
          alert(err.message || "Upload failed.");
          console.error(err);
        });
    });
  }
}

function initGallerySort() {
  const select = $("#sortSelect");
  const container = $("#gallery");
  if (!select || !container) return;

  function parseDate(el) {
    const d = new Date(el.dataset.date || 0);
    const t = d.getTime();
    return Number.isFinite(t) ? t : 0;
  }

  function applySort() {
    const cards = $all(".image-card", container);
    cards.sort((a, b) => {
      const ad = parseDate(a);
      const bd = parseDate(b);
      return select.value === "new" ? bd - ad : ad - bd;
    });
    // re-append in sorted order
    cards.forEach((c) => container.appendChild(c));
  }

  select.addEventListener("change", applySort);

  // Run once on open (drawer toggle) and once on load
  applySort();

  // If you want it to auto-apply whenever the drawer opens:
  document.addEventListener("click", (e) => {
    if (e.target.closest("#btn-edit-images")) {
      // slight delay lets the drawer render before sorting
      setTimeout(applySort, 0);
    }
  });
}

// ---------- HEIC/HEIF detection & conversion ----------
function isHeicLike(file) {
  const name = (file.name || "").toLowerCase();
  const t = (file.type || "").toLowerCase();
  return /\.heic$|\.heif$/.test(name) || /heic|heif/.test(t);
}
function canDisplayInImg(mime, name) {
  const ok = new Set(["image/jpeg", "image/png", "image/gif", "image/webp", "image/bmp"]);
  if (ok.has((mime || "").toLowerCase())) return true;
  const ext = (name || "").toLowerCase();
  return /\.(jpe?g|png|gif|webp|bmp)$/.test(ext);
}
async function convertHeicToJpeg(file, quality = 0.85) {
  // Try client-side lib first
  if (typeof window.heic2any === "function") {
    try {
      const out = await window.heic2any({ blob: file, toType: "image/jpeg", quality });
      const blob = Array.isArray(out) ? out[0] : out;
      const newName = file.name.replace(/\.(heic|heif)$/i, "") + ".jpg";
      return new File([blob], newName, { type: "image/jpeg", lastModified: Date.now() });
    } catch (e) {
      console.warn("Client HEIC convert failed, will try server:", e);
    }
  }
  // Server fallback (works with strict CSP)
  const fd = new FormData();
  fd.append("file", file, file.name);
  const res = await fetch("/heic_preview", {
    method: "POST",
    body: fd,
    headers: { "X-Requested-With": "XMLHttpRequest" },
  });
  if (!res.ok) throw new Error(`Server HEIC preview failed (${res.status})`);
  const blob = await res.blob();
  const newName = file.name.replace(/\.(heic|heif)$/i, "") + ".jpg";
  return new File([blob], newName, { type: "image/jpeg", lastModified: Date.now() });
}

let stagedFiles = [];

async function previewFiles(filesOverride) {
  const container = $("#previewContainer");
  const libInput = $("#fileFromLibrary");
  const camInput = $("#fileFromCamera");
  if (!container) return;

  // revoke old URLs
  $all("#previewContainer .image-preview img[data-objurl]").forEach((img) => {
    try { URL.revokeObjectURL(img.getAttribute("data-objurl")); } catch (_) { }
  });

  container.innerHTML = "";
  stagedFiles = [];

  // Build a clean array of Files
  let files = [];
  if (filesOverride && filesOverride.length) {
    files = Array.from(filesOverride);
  } else if (libInput?.files?.length) {
    files = Array.from(libInput.files);
  } else if (camInput?.files?.length) {
    files = Array.from(camInput.files);
  }

  // Nothing selected
  if (!files.length) return;

  // Process each file sequentially (keeps index alignment simple)
  for (let i = 0; i < files.length; i++) {
    const f = files[i];

    // placeholder card while converting
    const wrap = document.createElement("div");
    wrap.className = "image-preview";
    wrap.innerHTML = `
      <div style="width:300px; height:200px; border:1px dashed #666; display:grid; place-items:center; text-align:center; padding:8px;">
        <div>
          <div style="font-weight:bold;">${f.name}</div>
          <div style="font-size:12px; color:#aaa;">Preparing preview…</div>
        </div>
      </div>
      <table>
        <tr><td>Uploader:</td><td><input name="uploader_${i}" placeholder="(optional)" /></td></tr>
        <tr><td>Caption:</td><td><input name="caption_${i}"  placeholder="(optional)" /></td></tr>
      </table>
    `;
    container.appendChild(wrap);

    let upFile = f;
    let note = "";

    // Convert HEIC/HEIF → JPEG on the client when possible
    if (isHeicLike(f)) {
      try {
        upFile = await convertHeicToJpeg(f, 0.85);
        note = "(converted to JPEG)";
      } catch (e) {
        console.warn("HEIC convert failed; uploading original", e);
        note = "(HEIC conversion unavailable; uploading original)";
      }
    }

    // stage the file we’ll POST
    stagedFiles.push(upFile);

    // Render preview (real <img> if browser can display it)
    if (canDisplayInImg(upFile.type, upFile.name)) {
      const url = URL.createObjectURL(upFile);
      wrap.innerHTML = `
        <img src="${url}" data-objurl="${url}" style="max-width:300px; max-height:300px; object-fit:cover;" />
        <div style="font-size:12px; color:#aaa; margin-top:4px;">${note}</div>
        <table>
          <tr><td>Uploader:</td><td><input name="uploader_${i}" placeholder="(optional)" /></td></tr>
          <tr><td>Caption:</td><td><input name="caption_${i}"  placeholder="(optional)" /></td></tr>
        </table>
      `;
    } else {
      const sizeKB = Math.round(upFile.size / 1024);
      wrap.innerHTML = `
        <div style="width:300px; height:200px; border:1px dashed #666; display:grid; place-items:center; text-align:center; padding:8px;">
          <div>
            <div style="font-weight:bold;">${upFile.name}</div>
            <div style="font-size:12px; color:#aaa;">${sizeKB} KB ${note}</div>
            <div style="font-size:12px; color:#aaa;">Preview not supported.</div>
          </div>
        </div>
        <table>
          <tr><td>Uploader:</td><td><input name="uploader_${i}" placeholder="(optional)" /></td></tr>
          <tr><td>Caption:</td><td><input name="caption_${i}"  placeholder="(optional)" /></td></tr>
        </table>
      `;
    }
  }
}



// ---------- Bulk actions ----------
function getSelectedFiles() {
  return $all(".select-checkbox:checked").map((cb) => cb.value);
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
        $("#captionField").textContent = data.caption || "No Caption";
        $("#uploaderField").textContent = data.uploader || "Unknown";
        $("#dateField").textContent = data.date_added
          ? new Date(data.date_added).toLocaleDateString("en-GB")
          : "Unknown";
      } catch (_) { }
    };

    es.onerror = () => {
      try { es.close(); } catch (_) { }
      attempt = Math.min(attempt + 1, 6);
      const delay = Math.min(500 * attempt, maxDelay);
      setTimeout(connect, delay);
    };
  }

  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible" && (!es || es.readyState === 2)) connect();
  });
  window.addEventListener("beforeunload", () => { try { es && es.close(); } catch (_) { } });

  connect();
}

// ---------- Wire up everything once ----------
document.addEventListener("DOMContentLoaded", () => {
  initMenu();
  initDrawer();
  initLogsModal();
  initAppSettingsModal();
  initEditModal();
  initUploadModal();
  initBulkActions();
  initMetadataStream();
  initGallerySort();

  onClick("#btn-upload", () => safeShowDialog($("#uploadModal")));
  onClick("#btn-logout", () => logout());

  // Signup shake + password policy (unchanged behavior, moved here)
  (function () {
    var box = document.getElementById('signupBox');
    if (box && box.dataset.hadError === 'true') {
      box.classList.remove('shake'); void box.offsetWidth; box.classList.add('shake');
    }
    var pw = document.getElementById('password');
    var btn = document.getElementById('submitBtn');
    var ruleLength = document.getElementById('ruleLength');
    var ruleClasses = document.getElementById('ruleClasses');
    if (!pw || !btn || !ruleLength || !ruleClasses) return;

    function classify(p) {
      var lower = /[a-z]/.test(p);
      var upper = /[A-Z]/.test(p);
      var digit = /[0-9]/.test(p);
      var symbol = /[!@#$%^&*()_+\-=\[\]{};':",.<>\/?\\|]/.test(p);
      var classes = (lower ? 1 : 0) + (upper ? 1 : 0) + (digit ? 1 : 0) + (symbol ? 1 : 0);
      return { lengthOK: p.length >= 10, classesOK: classes >= 3 };
    }
    function update() {
      var v = pw.value || '';
      var res = classify(v);
      ruleLength.classList.toggle('ok', res.lengthOK);
      ruleClasses.classList.toggle('ok', res.classesOK);
      btn.disabled = !(res.lengthOK && res.classesOK);
    }
    pw.addEventListener('input', update);
    update();
    var form = document.getElementById('signupForm');
    if (form) form.addEventListener('submit', function (e) {
      if (btn.disabled) {
        e.preventDefault();
        if (box) { box.classList.remove('shake'); void box.offsetWidth; box.classList.add('shake'); }
      }
    });
  })();
});
