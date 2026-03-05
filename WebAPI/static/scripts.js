// ==========================================================
// scripts.js (drop-in replacement)
// - Theme toggle (dark/light) with Material-style chips
// - Deeply nested JSON settings form (Cards/Accordions)
// - Arrays of objects support (for schedules, etc.)
// ==========================================================

// ---------- Theme helpers ----------

const THEME_STORAGE_KEY = "ui_theme";

function applyTheme(theme) {
  const root = document.documentElement;
  const value = theme === "light" ? "light" : "dark";

  root.setAttribute("data-theme", value);
  try {
    window.localStorage.setItem(THEME_STORAGE_KEY, value);
  } catch (_) {
    // ignore
  }

  const chips = document.querySelectorAll(".theme-chip");
  chips.forEach((chip) => {
    const target = chip.dataset.theme;
    const isActive = target === value;
    chip.classList.toggle("is-active", isActive);
    chip.setAttribute("aria-pressed", isActive ? "true" : "false");
  });
}

// Set initial theme as early as possible (before DOMContentLoaded)
(function bootTheme() {
  let initial = "dark";
  try {
    const stored = window.localStorage.getItem(THEME_STORAGE_KEY);
    if (stored === "light" || stored === "dark") {
      initial = stored;
    }
  } catch (_) {
    // ignore
  }
  document.documentElement.setAttribute("data-theme", initial);
})();

function initThemeToggle() {
  const container = document.querySelector(".theme-toggle");
  if (!container) return; // No toggle on this page

  // Sync toggle UI to current theme
  const current =
    document.documentElement.getAttribute("data-theme") || "dark";
  applyTheme(current);

  container.addEventListener("click", (e) => {
    const btn = e.target.closest(".theme-chip");
    if (!btn) return;
    const next = btn.dataset.theme === "light" ? "light" : "dark";
    applyTheme(next);
  });
}

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

function $(sel, root = document) {
  return root.querySelector(sel);
}
function $all(sel, root = document) {
  return Array.from(root.querySelectorAll(sel));
}
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
  return (e) => {
    if (e.key === "Escape") closeFn();
  };
}
function safeShowDialog(d) {
  if (!d) return;
  try {
    d.showModal();
  } catch (_) {
    d.removeAttribute("hidden");
    d.style.display = "block";
  }
}
function safeCloseDialog(d) {
  if (!d) return;
  try {
    d.close();
  } catch (_) {
    d.setAttribute("hidden", "");
    d.style.display = "none";
  }
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

// ---------- Top menu (hamburger) ----------

function initMenu() {
  const menu = $("#dropdown-menu");
  const hamburger = $("#hamburger");
  if (!menu || !hamburger) return;

  function showMenu() {
    menu.hidden = false;
    hamburger.setAttribute("aria-expanded", "true");
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

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") hideMenu();
  });
}

// ---------- Drawer (Edit Images panel) ----------

function showDrawer(panel) {
  panel.removeAttribute("hidden");
  panel.style.display = "";
  const menu = document.getElementById("dropdown-menu");
  const hamburger = document.getElementById("hamburger");
  if (menu && hamburger && hamburger.getAttribute("aria-expanded") === "true") {
    menu.hidden = true;
    hamburger.setAttribute("aria-expanded", "false");
  }
}
function hideDrawer(panel) {
  panel.setAttribute("hidden", "");
  panel.style.display = "";
}
function toggleSettingsDrawer() {
  const panel = document.getElementById("bottom-scrollable");
  if (!panel) return;
  const isHidden =
    panel.hasAttribute("hidden") || panel.style.display === "none";
  isHidden ? showDrawer(panel) : hideDrawer(panel);
}
function initDrawer() {
  onClick("#btn-edit-images", () => toggleSettingsDrawer());
  onClick("#btn-close-settings", () => toggleSettingsDrawer());
}

// ---------- Logs modal ----------

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
  onClick("#btn-download-logs", () => (window.location.href = "/download_logs"));
  onClick("#btn-clear-logs", () => {
    csrfFetch("/clear_logs", { method: "POST" })
      .then(async (r) => {
        const data = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(data.error || "Failed to clear logs");
        alert(data.message || "Logs cleared");
        const t = $("#logText");
        if (t) t.value = "";
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
      if (!res.ok) throw new Error(data.error || "Failed to load logs");
      const lines = data.logs || [];
      if (t) t.value = lines.length ? lines.join("\n") : "(no log lines found)";
    })
    .catch((err) => {
      if (t) t.value = `Error: ${err.message}`;
    });
}

// ==========================================================
// NEW: Settings dynamic form renderer (Deep nesting support)
// ==========================================================

// Helper: Convert "image_quality_encoding" -> "Image Quality Encoding"
function formatLabel(key) {
  return key
    .replace(/_/g, " ")
    .replace(/\b\w/g, (l) => l.toUpperCase());
}

// Helper: Flatten path keys for form naming: ["ui", "margins", "left"] -> "ui[margins][left]"
function toFormName(pathParts) {
  if (!pathParts.length) return "";
  const [head, ...rest] = pathParts;
  return head + rest.map((p) => `[${p}]`).join("");
}

// Helper: Flatten path keys for IDs: ["ui", "margins", "left"] -> "set_ui_margins_left"
function toId(pathParts) {
  return "set_" + pathParts.join("_");
}

function getType(val, keyName) {
  if (typeof val === "boolean") return "boolean";
  if (typeof val === "number") return Number.isInteger(val) ? "integer" : "number";
  if (Array.isArray(val)) return "array";
  if (val === null) return "string";
  if (typeof val === "object") return "object";

  // Heuristics for inputs
  const k = keyName.toLowerCase();
  if (k.includes("password") || k.includes("secret") || k.includes("token")) return "password";
  if (k.includes("color")) return "color";

  return "string";
}

// 1. Render a single Primitive Input (String, Number, Bool)
function createInputForPrimitive(path, key, value) {
  const formName = toFormName(path.concat(key));
  const elId = toId(path.concat(key));
  const type = getType(value, key);
  const prettyKey = formatLabel(key);

  const container = document.createElement("div");
  container.className = "settings-row";

  // Boolean: Checkbox
  if (type === "boolean") {
    container.classList.add("checkbox-row");

    // Hidden input for false state
    const hidden = document.createElement("input");
    hidden.type = "hidden";
    hidden.name = formName;
    hidden.value = "false";

    const label = document.createElement("label");
    label.setAttribute("for", elId);
    label.className = "settings-label";
    label.textContent = prettyKey;

    const cb = document.createElement("input");
    cb.type = "checkbox";
    cb.id = elId;
    cb.name = formName;
    cb.checked = !!value;
    cb.value = "true";

    container.appendChild(label);
    container.appendChild(hidden);
    container.appendChild(cb);
    return container;
  }

  // Standard inputs
  const label = document.createElement("label");
  label.setAttribute("for", elId);
  label.className = "settings-label";
  label.textContent = prettyKey;
  container.appendChild(label);

  const input = document.createElement("input");
  input.id = elId;
  input.name = formName;
  input.value = value ?? "";

  if (type === "integer" || type === "number") {
    input.type = "number";
    input.step = type === "integer" ? "1" : "any";
  } else if (type === "password") {
    input.type = "password";
    input.autocomplete = "new-password";
  } else if (type === "color") {
    // Basic heuristic: if it's not a valid hex, show text, otherwise color picker?
    // For safety, let's keep it text unless we are sure, or use type="text" 
    // but maybe class could trigger a picker library if present.
    // We'll stick to text for max compatibility unless it matches #RRGGBB
    input.type = /^#[0-9A-F]{6}$/i.test(value) ? "color" : "text";
  } else {
    input.type = "text";
  }

  container.appendChild(input);
  return container;
}

// 2. Render an Array Editor (Primitive list or Object list)
function createArrayEditor(path, key, arr) {
  const container = document.createElement("div");
  container.className = "settings-fieldset";

  const legend = document.createElement("div");
  legend.className = "settings-legend";
  legend.textContent = formatLabel(key);
  container.appendChild(legend);

  const listContainer = document.createElement("div");
  container.appendChild(listContainer);

  // Determine if this is an array of objects or primitives based on first item
  const isObjectArray = arr.length > 0 && typeof arr[0] === "object" && arr[0] !== null;

  // Function to render one row/block
  function renderItem(index, itemVal) {
    const itemPath = path.concat([key, String(index)]);
    const wrap = document.createElement("div");
    wrap.className = "settings-array-item";

    if (isObjectArray || (typeof itemVal === 'object' && itemVal !== null)) {
      // Recursive render for object inside array
      renderSettingsRecursively(wrap, itemVal, itemPath, false); // false = not root
    } else {
      // Simple primitive input
      const input = document.createElement("input");
      input.type = typeof itemVal === "number" ? "number" : "text";
      input.name = toFormName(itemPath);
      input.value = itemVal ?? "";
      input.style.width = "100%";
      input.style.padding = "8px";
      input.style.marginBottom = "4px";
      input.style.background = "rgba(0,0,0,0.2)";
      input.style.border = "1px solid rgba(148,163,184,0.4)";
      input.style.color = "var(--text)";
      input.style.borderRadius = "4px";
      wrap.appendChild(input);
    }

    const actions = document.createElement("div");
    actions.className = "settings-array-actions";

    const removeBtn = document.createElement("button");
    removeBtn.type = "button";
    removeBtn.className = "btn-remove";
    removeBtn.textContent = "Remove";
    removeBtn.onclick = () => {
      wrap.remove();
      // We rely on form order or we might need to re-index names.
      // Simple approach: re-index inputs in this listContainer
      reIndexInputs(listContainer, key, path);
    };

    actions.appendChild(removeBtn);
    wrap.appendChild(actions);
    listContainer.appendChild(wrap);
  }

  // Initial population
  arr.forEach((val, idx) => renderItem(idx, val));

  // "Add" button
  const addBtn = document.createElement("button");
  addBtn.type = "button";
  addBtn.className = "btn-add";
  addBtn.textContent = "+ Add Item";
  addBtn.onclick = () => {
    const newIdx = listContainer.children.length;
    let template = "";
    // If we have an existing item, copy its structure (deep clone simple obj)
    if (arr.length > 0) {
      template = JSON.parse(JSON.stringify(arr[0]));
      // clear values in template
      if (typeof template === 'object') {
        clearValues(template);
      } else {
        template = "";
      }
    } else {
      // No template, assume empty object if key suggests complex, else string
      // This is a guess. If the user deleted all items, we might lose schema.
      // For this specific app, 'schedules' is the main array of objects.
      if (key === 'schedules') {
        template = { enabled: false, off_hour: 0, on_hour: 8, days: [] };
      } else {
        template = "";
      }
    }
    renderItem(newIdx, template);
  };

  container.appendChild(addBtn);
  return container;
}

// Helper to clear values for new array items
function clearValues(obj) {
  for (const k in obj) {
    if (typeof obj[k] === 'object' && obj[k] !== null) clearValues(obj[k]);
    else if (typeof obj[k] === 'boolean') obj[k] = false;
    else if (typeof obj[k] === 'number') obj[k] = 0;
    else obj[k] = "";
  }
}

// Helper to re-calculate index in name="path[key][INDEX][sub]"
function reIndexInputs(container, arrayKey, parentPath) {
  // complex regex replacement or DOM reconstruction?
  // Easier: iterate children, find inputs, update names.
  Array.from(container.children).forEach((wrap, newIndex) => {
    const inputs = wrap.querySelectorAll("input, select");
    inputs.forEach(input => {
      const name = input.name;
      // name is something like ...[arrayKey][OLD_INDEX]...
      // We need to replace [arrayKey][OLD_INDEX] with [arrayKey][newIndex]
      // Construct prefix
      const prefix = toFormName(parentPath.concat(arrayKey)); // e.g. screen[schedules]
      const regex = new RegExp(`^(${escapeRegExp(prefix)})\\[\\d+\\]`);
      input.name = name.replace(regex, `$1[${newIndex}]`);
    });
  });
}
function escapeRegExp(string) {
  return string.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

// 3. Main Recursive Renderer
function renderSettingsRecursively(container, obj, path = [], isRoot = true) {
  Object.keys(obj).forEach((key) => {
    const val = obj[key];
    const type = getType(val, key);
    const currentPath = path.concat(key);

    // Case A: Nested Object (not null)
    if (type === "object" && val !== null) {
      if (isRoot) {
        // Root level: Create a Collapsible Card (Details/Summary)
        const details = document.createElement("details");
        details.className = "settings-section";
        details.open = true; // Default open for better discoverability

        const summary = document.createElement("summary");
        summary.className = "settings-summary";
        summary.textContent = formatLabel(key);

        const content = document.createElement("div");
        content.className = "settings-content";

        details.appendChild(summary);
        details.appendChild(content);
        container.appendChild(details);

        renderSettingsRecursively(content, val, currentPath, false);
      } else {
        // Nested level: Create a Fieldset
        const fieldset = document.createElement("div");
        fieldset.className = "settings-fieldset";

        const legend = document.createElement("div");
        legend.className = "settings-legend";
        legend.textContent = formatLabel(key);

        fieldset.appendChild(legend);
        container.appendChild(fieldset);

        renderSettingsRecursively(fieldset, val, currentPath, false);
      }
    }
    // Case B: Array
    else if (type === "array") {
      container.appendChild(createArrayEditor(path, key, val));
    }
    // Case C: Primitive
    else {
      container.appendChild(createInputForPrimitive(path, key, val));
    }
  });
}

// 4. Load & Populate Form
async function populateSettingsForm() {
  const container = document.getElementById("settingsDynamicContainer");
  const form = document.getElementById("appSettingsForm");
  if (!container || !form) return;

  container.innerHTML = "<div style='text-align:center; padding:20px;'>Loading settings...</div>";

  let data = {};
  try {
    const res = await fetch("/api/settings/", {
      headers: { "X-Requested-With": "XMLHttpRequest" },
    });
    data = await res.json();
    if (!res.ok || !data || typeof data !== "object") {
      throw new Error("Failed to load settings");
    }
  } catch (e) {
    console.error(e);
    container.innerHTML = `<div class="flash error">Error loading settings: ${e.message}</div>`;
    return;
  }

  // Inject UI Theme if missing (so it persists)
  if (!data.ui) data.ui = {}; // Ensure 'ui' exists if strictly following schema
  // Actually, ui_theme is often stored in localStorage, but let's see if it's in the JSON.
  // The user prompt JSON has "ui" object but no "ui_theme" key.
  // We can add a "local_settings" block or just append to root if the backend accepts dynamic keys.
  // For safety, let's respect the JSON structure provided.
  // If we want to save the theme preference to the server, we should put it somewhere.
  // We'll stick to the "ui_theme" handling as a hidden field or separate logic 
  // if the backend doesn't explicitly support it in the JSON file. 
  // *Reverting to original logic*: original script added ui_theme to data. 
  // We will add it to the 'system' block or root if 'ui_theme' key is allowed.
  // Let's just create a hidden input for ui_theme separately so it doesn't break JSON structure validation.

  container.innerHTML = "";

  // Render the JSON
  renderSettingsRecursively(container, data);

  // Handle Theme Persistence manually (outside the recursive JSON)
  // This ensures we don't accidentally push "ui_theme" into a strict JSON struct if not expected.
  const currentTheme = document.documentElement.getAttribute("data-theme") || "dark";
  const hiddenTheme = document.createElement("input");
  hiddenTheme.type = "hidden";
  hiddenTheme.name = "ui_theme";
  hiddenTheme.value = currentTheme;
  container.appendChild(hiddenTheme);
}

function initAppSettingsModal() {
  const dlg = $("#appSettingsModal");
  if (!dlg) return;

  async function open() {
    await populateSettingsForm();
    safeShowDialog(dlg);
  }
  function close() {
    safeCloseDialog(dlg);
  }

  onClick("#btn-app-settings", open);
  onClick("#app-settings-cancel", close);
  onClick("#app-settings-close", close);
  document.addEventListener("keydown", trapEscape(close));

  const form = $("#appSettingsForm");
  if (form) {
    form.addEventListener("submit", function () {
      const saveBtn = $("#app-settings-save");
      if (saveBtn) {
        saveBtn.disabled = true;
        saveBtn.textContent = "Saving...";
      }
      // Update the hidden theme input right before submit
      const currentTheme = document.documentElement.getAttribute("data-theme") || "dark";
      const hiddenTheme = form.querySelector('input[name="ui_theme"]');
      if (hiddenTheme) hiddenTheme.value = currentTheme;
    });
  }
}

// ---------- Edit metadata modal ----------

function initEditModal() {
  const dlg = $("#editModal");
  const editForm = $("#editForm");
  const preview = $("#editImagePreview");
  if (!dlg || !editForm || !preview) return;

  let previewObjUrl = null;

  function showPreviewPlaceholder(imageName) {
    const wrapper = preview.parentElement || dlg;

    preview.style.display = "none";
    preview.removeAttribute("src");

    let placeholder = wrapper.querySelector(".edit-preview-fallback");
    if (!placeholder) {
      placeholder = document.createElement("div");
      placeholder.className = "edit-preview-fallback";
      placeholder.style.width = "100%";
      placeholder.style.minHeight = "160px";
      placeholder.style.border = "1px dashed #666";
      placeholder.style.display = "grid";
      placeholder.style.placeItems = "center";
      placeholder.style.textAlign = "center";
      placeholder.style.fontSize = "14px";
      placeholder.style.color = "#aaa";
      placeholder.style.marginTop = "4px";
      wrapper.appendChild(placeholder);
    }

    placeholder.innerHTML =
      `<div><strong>${imageName || "Selected image"}</strong><br>` +
      `Preview not available (HEIC not supported by browser / decoder).</div>`;
  }

  function showPreviewImage(url, alt) {
    const wrapper = preview.parentElement || dlg;
    const placeholder = wrapper.querySelector(".edit-preview-fallback");
    if (placeholder) {
      placeholder.remove();
    }

    preview.style.display = "block";
    preview.src = url;
    preview.alt = alt || "";

    preview.onerror = function () {
      showPreviewPlaceholder(alt);
    };
  }

  async function openWith(imageName, fullUrl) {
    if (previewObjUrl) {
      try {
        URL.revokeObjectURL(previewObjUrl);
      } catch (_) { }
      previewObjUrl = null;
    }

    let finalUrl = fullUrl || "";
    finalUrl = await createPreviewUrlForExistingImage(imageName, finalUrl);

    if (finalUrl) {
      if (finalUrl.startsWith("blob:")) {
        previewObjUrl = finalUrl;
      }
      showPreviewImage(finalUrl, imageName);
    } else {
      showPreviewPlaceholder(imageName);
    }

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
        $("#editDateAdded").value = data.date_added
          ? formatDate(data.date_added)
          : "";
        $("#editHash").value = data.hash || "";

        safeShowDialog(dlg);
      })
      .catch((err) => {
        alert("Could not open edit modal");
        console.error(err);
      });
  }

  onClick(".image-card .btn-edit", (btn) => {
    const card = btn.closest(".image-card");
    const name = btn.dataset.image || card?.dataset.image;
    if (!name) return;

    let fullUrl = "";
    if (card) {
      const imgEl = card.querySelector("img[data-full]") || card.querySelector("img");
      if (imgEl) {
        fullUrl = imgEl.dataset.full || imgEl.src || "";
      }
    }

    if (!fullUrl) {
      fullUrl = `/images/${encodeURIComponent(name)}`;
    }

    openWith(name, fullUrl);
  });

  function closeDialog() {
    if (previewObjUrl) {
      try {
        URL.revokeObjectURL(previewObjUrl);
      } catch (_) { }
      previewObjUrl = null;
    }
    const wrapper = preview.parentElement || dlg;
    const placeholder = wrapper.querySelector(".edit-preview-fallback");
    if (placeholder) {
      placeholder.remove();
    }
    preview.style.display = "block";
    preview.removeAttribute("src");
    safeCloseDialog(dlg);
  }

  onClick("#edit-cancel", () => closeDialog());
  document.addEventListener("keydown", trapEscape(closeDialog));

  editForm.addEventListener("submit", function (event) {
    event.preventDefault();

    const payload = {
      hash: $("#editHash").value,
      caption: $("#editCaption").value,
      uploader: $("#editUploader").value,
    };

    csrfFetch("/update_metadata", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    })
      .then((res) => res.json())
      .then((data) => {
        alert(data.message || "Metadata updated.");
        closeDialog();
      })
      .catch(() => alert("Failed to update metadata"));
  });
}

async function createPreviewUrlForExistingImage(fileName, fullUrl) {
  const lower = (fileName || fullUrl || "").toLowerCase();

  if (!/\.heic$|\.heif$/.test(lower)) {
    return fullUrl;
  }

  const tryUrls = [];
  tryUrls.push(fullUrl.replace(/(\.heic|\.heif)(\b|$)/i, ".png"));
  tryUrls.push(fullUrl.replace(/(\.heic|\.heif)(\b|$)/i, ".jpg"));

  for (const u of tryUrls) {
    if (!u || u === fullUrl) continue;
    try {
      const res = await fetch(u, { method: "HEAD" });
      if (res.ok) {
        return u;
      }
    } catch (_) {
      // ignore
    }
  }

  console.warn(
    "HEIC preview: no PNG/JPEG sibling found, using original URL; browser may not show it."
  );
  return fullUrl;
}

// ---------- Upload modal ----------

let stagedFiles = [];

function initUploadModal() {
  const dlg = $("#uploadModal");
  const previews = $("#previewContainer");
  const fileFromLibrary = $("#fileFromLibrary");
  const fileFromCamera = $("#fileFromCamera");

  if (fileFromLibrary) fileFromLibrary.removeAttribute("capture");

  function open() {
    safeShowDialog(dlg);
  }

  function close() {
    if (previews) previews.innerHTML = "";
    if (fileFromLibrary) fileFromLibrary.value = "";
    if (fileFromCamera) fileFromCamera.value = "";
    stagedFiles = [];
    safeCloseDialog(dlg);
  }

  onClick("#btn-upload", open);
  onClick("#upload-cancel", close);
  onClick("#upload-close", close);
  document.addEventListener("keydown", trapEscape(close));

  onClick("#btn-choose-library", () => {
    if (fileFromLibrary) {
      fileFromLibrary.setAttribute("accept", "image/*,video/*,.heic,.heif,.mov,.mp4");
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

  if (fileFromLibrary)
    fileFromLibrary.addEventListener("change", (e) => previewFiles(null));
  if (fileFromCamera)
    fileFromCamera.addEventListener("change", (e) => previewFiles(null));

  const form = $("#uploadForm");
  if (form) {
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      if (!stagedFiles.length) return alert("No files selected.");

      const submitBtn = form.querySelector("button[type='submit']");
      if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.textContent = "Uploading...";
      }

      const fd = new FormData();
      fd.append("csrf_token", getCsrf());

      stagedFiles.forEach((f, i) => {
        fd.append("file[]", f, f.name);
        const uploaderVal = document.querySelector(`input[name="uploader_${i}"]`)?.value || "";
        const captionVal = document.querySelector(`input[name="caption_${i}"]`)?.value || "";
        fd.append(`uploader_${i}`, uploaderVal.trim());
        fd.append(`caption_${i}`, captionVal.trim());
      });

      csrfFetch("/upload_with_metadata", { method: "POST", body: fd })
        .then(async (res) => {
          const data = await res.json().catch(() => ({}));
          if (!res.ok) throw new Error(data.error || data.message || `Upload failed`);
          return data;
        })
        .then((data) => {
          alert(data.message || "Upload successful!");
          close();
          location.reload();
        })
        .catch((err) => {
          alert(err.message || "Upload failed.");
          console.error(err);
          if (submitBtn) {
            submitBtn.disabled = false;
            submitBtn.textContent = "Upload";
          }
        });
    });
  }
}

function isHeicLike(file) {
  const name = (file.name || "").toLowerCase();
  const t = (file.type || "").toLowerCase();
  return /\.heic$|\.heif$/.test(name) || /heic|heif/.test(t);
}
function canDisplayInImg(mime, name) {
  const ok = new Set([
    "image/jpeg",
    "image/png",
    "image/gif",
    "image/webp",
    "image/bmp",
  ]);
  if (ok.has((mime || "").toLowerCase())) return true;
  const ext = (name || "").toLowerCase();
  return /\.(jpe?g|png|gif|webp|bmp)$/.test(ext);
}

async function convertHeicToJpeg(file, quality = 0.85) {
  if (typeof window.heic2any === "function") {
    try {
      const out = await window.heic2any({
        blob: file,
        toType: "image/jpeg",
        quality,
      });
      const blob = Array.isArray(out) ? out[0] : out;
      const newName = file.name.replace(/\.(heic|heif)$/i, "") + ".jpg";
      return new File([blob], newName, {
        type: "image/jpeg",
        lastModified: Date.now(),
      });
    } catch (e) {
      console.warn(
        "Client HEIC preview conversion failed; uploading original file instead",
        e
      );
    }
  }
  throw new Error("HEIC preview not supported in this browser");
}

async function previewFiles(filesOverride) {
  const container = $("#previewContainer");
  const libInput = $("#fileFromLibrary");
  const camInput = $("#fileFromCamera");
  if (!container) return;

  $all("#previewContainer .image-preview img[data-objurl]").forEach((img) => {
    try {
      URL.revokeObjectURL(img.getAttribute("data-objurl"));
    } catch (_) { }
  });

  container.innerHTML = "";
  stagedFiles = [];

  let files = [];
  if (filesOverride && filesOverride.length) {
    files = Array.from(filesOverride);
  } else if (libInput?.files?.length) {
    files = Array.from(libInput.files);
  } else if (camInput?.files?.length) {
    files = Array.from(camInput.files);
  }
  if (!files.length) return;

  for (let i = 0; i < files.length; i++) {
    const f = files[i];

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

    if (isHeicLike(f)) {
      try {
        upFile = await convertHeicToJpeg(f, 0.85);
        note = "(converted to JPEG)";
      } catch (e) {
        console.warn("HEIC convert failed; uploading original", e);
        note = "(HEIC conversion unavailable; uploading original)";
      }
    }

    stagedFiles.push(upFile);

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
  if (!confirm(`Are you sure you want to delete ${selected.length} image(s)?`))
    return;
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
      try {
        es.close();
      } catch (_) { }
      attempt = Math.min(attempt + 1, 6);
      const delay = Math.min(500 * attempt, maxDelay);
      setTimeout(connect, delay);
    };
  }

  document.addEventListener("visibilitychange", () => {
    if (
      document.visibilityState === "visible" &&
      (!es || es.readyState === 2)
    )
      connect();
  });
  window.addEventListener("beforeunload", () => {
    try {
      es && es.close();
    } catch (_) { }
  });

  connect();
}

// ---------- Gallery sort ----------

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
    cards.forEach((c) => container.appendChild(c));
  }

  select.addEventListener("change", applySort);
  applySort();

  document.addEventListener("click", (e) => {
    if (e.target.closest("#btn-edit-images")) {
      setTimeout(applySort, 0);
    }
  });
}

// ---------- Wire up everything once ----------

document.addEventListener("DOMContentLoaded", () => {
  initThemeToggle();
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
});
