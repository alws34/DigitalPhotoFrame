function logout() {
  const form = addCsrfToForm(document.createElement("form"));
  form.method = "POST";
  form.action = "/logout";
  document.body.appendChild(form);
  form.submit();
}


function openLogsModal() {
  document.getElementById("logsModal").style.display = "block";
  fetchLogs();
}

function closeLogsModal() {
  document.getElementById("logsModal").style.display = "none";
}

function fetchLogs() {
  fetch("/logs")
    .then((res) => res.json())
    .then((data) => {
      document.getElementById("logText").value = (data.logs || []).join("\n");
    });
}

function downloadLogs() {
  window.location.href = "/download_logs";
}

function clearLogs() {
  csrfFetch("/clear_logs", { method: "POST" })
    .then(res => res.json())
    .then(data => {
      alert(data.message || "Logs cleared");
      document.getElementById("logText").value = "";
    })
    .catch(() => alert("Failed to clear logs"));
}


function toggleSettings() {
  const panel = document.getElementById("bottom-scrollable");
  const isHidden = panel.style.display === "none" || panel.style.display === "";
  panel.style.display = isHidden ? "flex" : "none";
}



function openAppSettingsModal() {
  document.getElementById("appSettingsModal").style.display = "block";
}

function closeAppSettingsModal() {
  document.getElementById("appSettingsModal").style.display = "none";
}

function formatDate(isoDateStr) {
  if (!isoDateStr) return "";
  const date = new Date(isoDateStr);
  return date.toLocaleDateString("en-GB"); // dd/MM/yyyy
}

function openEditModal(imageName) {
  fetch(`/image_metadata?filename=${encodeURIComponent(imageName)}`)
    .then((res) => res.json())
    .then((data) => {
      if (!data || data.error) {
        alert("Failed to load metadata");
        return;
      }
      document.getElementById("editImageName").value = imageName;
      document.getElementById("editCaption").value = data.caption || "";
      document.getElementById("editUploader").value = data.uploader || "";
      document.getElementById("editDateAdded").value = formatDate(
        data.date_added
      );
      document.getElementById("editHash").value = data.hash || "";
      document.getElementById("editModal").style.display = "block";
    })
    .catch((err) => {
      alert("Could not open edit modal");
      console.error(err);
    });
}

function closeEditModal() {
  document.getElementById("editModal").style.display = "none";
}

function submitEditForm(event) {
  event.preventDefault();
  const payload = {
    hash: document.getElementById("editHash").value,
    caption: document.getElementById("editCaption").value,
    uploader: document.getElementById("editUploader").value
  };
  csrfFetch("/update_metadata", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  })
    .then(res => res.json())
    .then(data => {
      alert(data.message || "Metadata updated.");
      closeEditModal();
    })
    .catch(() => alert("Failed to update metadata"));
}


function downloadImage(imageName) {
  window.location.href = `/download/${encodeURIComponent(imageName)}`;
}

// ===== Utilities already defined above (logout, toggleSettings, etc.) =====
// Keep your existing function implementations. We only add listeners below.

// --- Event delegation helpers ---
function onClick(sel, handler) {
  document.addEventListener("click", (e) => {
    const el = e.target.closest(sel);
    if (el) {
      e.preventDefault();
      handler(el, e);
    }
  });
}

// --- Hamburger / menu ---
document.addEventListener("DOMContentLoaded", () => {
  const menu = document.getElementById("dropdown-menu");
  const hamburger = document.getElementById("hamburger");

  if (hamburger) {
    hamburger.addEventListener("click", () => {
      menu.style.display = menu.style.display === "flex" ? "none" : "flex";
    });
  }

  document.addEventListener("click", (e) => {
    if (!menu || !hamburger) return;
    const isClickInsideMenu = menu.contains(e.target);
    const isClickOnHamburger = hamburger.contains(e.target);
    if (!isClickInsideMenu && !isClickOnHamburger) {
      menu.style.display = "none";
    }
  });

  // Top menu buttons
  onClick("#btn-edit-images", () => toggleSettings());
  onClick("#btn-app-settings", () => openAppSettingsModal());
  onClick("#btn-upload", () => openUploadModal());
  onClick("#btn-logs", () => openLogsModal());
  onClick("#btn-logout", () => logout());

  // Action bar buttons
  onClick("#btn-download-selected", () => downloadSelected());
  onClick("#btn-delete-selected", () => deleteSelected());
  onClick("#btn-close-settings", () => toggleSettings());

  // Logs modal
  onClick("#logs-close", () => closeLogsModal());

  // Edit modal
  onClick("#edit-close", () => closeEditModal());
  onClick("#edit-cancel", () => closeEditModal());

  // App settings modal
  onClick("#app-settings-close", () => closeAppSettingsModal());
  onClick("#app-settings-cancel", () => closeAppSettingsModal());

  // Upload modal
  onClick("#upload-close", () => closeUploadModal());
  onClick("#btn-browse", () => {
    const fileInput = document.getElementById("fileInput");
    if (fileInput) fileInput.click();
  });

  // Drop zone (no inline handlers)
  const dropZone = document.getElementById("dropZone");
  if (dropZone) {
    dropZone.addEventListener("dragover", (e) => e.preventDefault());
    dropZone.addEventListener("drop", (e) => {
      e.preventDefault();
      const files = e.dataTransfer.files;
      const fileInput = document.getElementById("fileInput");
      if (fileInput) {
        // Create a new DataTransfer to set files programmatically in some browsers
        const dt = new DataTransfer();
        for (let i = 0; i < files.length; i++) dt.items.add(files[i]);
        fileInput.files = dt.files;
      }
      previewFiles();
    });
  }

  // Image edit buttons (delegation)
  onClick(".image-card .btn-edit", (btn) => {
    const name = btn.dataset.image || btn.closest(".image-card")?.dataset.image;
    if (name) openEditModal(name);
  });
});

// --- Robust EventSource with auto-retry ---
(function setupMetadataStream() {
  const url = "/metadata_stream";
  let es;
  let retry = 0;
  const maxDelay = 10000;

  function connect() {
    es = new EventSource(url, { withCredentials: true });

    es.onmessage = (e) => {
      retry = 0;
      try {
        const data = JSON.parse(e.data || "{}");
        document.getElementById("captionField").textContent =
          data.caption || "No Caption";
        document.getElementById("uploaderField").textContent =
          data.uploader || "Unknown";
        document.getElementById("dateField").textContent = data.date_added
          ? new Date(data.date_added).toLocaleDateString("en-GB")
          : "Unknown";
      } catch (_) {}
    };

    es.onerror = () => {
      es.close();
      retry = Math.min((retry || 0) + 1, 6);
      const delay = Math.min(500 * retry, maxDelay);
      setTimeout(connect, delay);
    };
  }

  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible" && (!es || es.readyState === 2)) {
      connect();
    }
  });

  window.addEventListener("beforeunload", () => {
    if (es) es.close();
  });

  connect();
})();

function deleteImage(imageName) {
  if (!confirm(`Are you sure you want to delete ${imageName}?`)) return;
  const form = addCsrfToForm(document.createElement("form"));
  form.method = "POST";
  form.action = `/delete/${encodeURIComponent(imageName)}`;
  document.body.appendChild(form);
  form.submit();
}


function openUploadModal() {
  document.getElementById("uploadModal").style.display = "block";
}

function closeUploadModal() {
  document.getElementById("uploadModal").style.display = "none";
}

function handleDrop(event) {
  event.preventDefault();
  const files = event.dataTransfer.files;
  document.getElementById("fileInput").files = files;
  previewFiles();
}

function previewFiles() {
  const container = document.getElementById("previewContainer");
  container.innerHTML = "";
  const files = document.getElementById("fileInput").files;

  for (let i = 0; i < files.length; i++) {
    const reader = new FileReader();
    reader.onload = function (e) {
      const div = document.createElement("div");
      div.classList.add("image-preview");
      div.innerHTML = `
        <img src="${e.target.result}" style="max-width: 300px; max-height: 300px;" />
        <table>
          <tr><td>Uploader:</td><td><input name="uploader_${i}" placeholder="(optional)" /></td></tr>
          <tr><td>Caption:</td><td><input name="caption_${i}" placeholder="(optional)" /></td></tr>
        </table>
      `;
      container.appendChild(div);
    };
    reader.readAsDataURL(files[i]);
  }
}

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
  // Mark as ajax (helps server decide JSON vs redirect on CSRF failure)
  headers.set("X-Requested-With", "XMLHttpRequest");
  return fetch(url, { ...options, headers });
}



window.addEventListener("DOMContentLoaded", () => {
  console.log("✅ DOM is ready");

  const form = document.getElementById("uploadForm");
  if (!form) {
    console.error("❌ uploadForm not found in DOM");
    return;
  }
  form.addEventListener("submit", function (e) {
    e.preventDefault();
    const files = document.getElementById("fileInput").files;
    const previews = document.querySelectorAll("#previewContainer .image-preview");
    if (!files.length) return alert("No files selected.");

    const formData = new FormData();
    formData.append("csrf_token", getCsrf()); // field

    for (let i = 0; i < previews.length; i++) {
      const file = files[i];
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
});

window.addEventListener("DOMContentLoaded", () => {
  const fileInput = document.getElementById("fileInput");
  if (fileInput) {
    fileInput.addEventListener("change", function () {
      document.getElementById("previewContainer").innerHTML = "";
      handleFiles(this.files);
    });
  } else {
    console.error("❌ fileInput element not found in DOM");
  }
});



function handleFiles(fileList) {
  const container = document.getElementById("previewContainer");
  for (let i = 0; i < fileList.length; i++) {
    const file = fileList[i];
    const index = i;
    const reader = new FileReader();

    reader.onload = function (e) {
      const imgCard = document.createElement("div");
      imgCard.classList.add("image-preview"); // Important!
      imgCard.style.margin = "10px";
      imgCard.style.textAlign = "center";

      const img = document.createElement("img");
      img.src = e.target.result;
      img.width = 300;
      img.height = 300;
      img.style.objectFit = "cover";

      const uploader = document.createElement("input");
      uploader.type = "text";
      uploader.placeholder = "Uploader Name";
      uploader.name = `uploader_${index}`;
      uploader.required = false;

      const caption = document.createElement("input");
      caption.type = "text";
      caption.placeholder = "Caption";
      caption.name = `caption_${index}`;
      caption.required = false;

      imgCard.appendChild(img);
      imgCard.appendChild(document.createElement("br"));
      imgCard.appendChild(uploader);
      imgCard.appendChild(document.createElement("br"));
      imgCard.appendChild(caption);

      container.appendChild(imgCard);
    };

    reader.readAsDataURL(file);
  }
}
function getSelectedFiles() {
  return Array.from(document.querySelectorAll('.select-checkbox:checked')).map(cb => cb.value);
}

function downloadSelected() {
  const selected = getSelectedFiles();
  if (!selected.length) return alert("No images selected.");

  const form = addCsrfToForm(document.createElement("form"));
  form.method = "POST";
  form.action = "/download_selected";
  selected.forEach(filename => {
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
  selected.forEach(filename => {
    const input = document.createElement("input");
    input.type = "hidden";
    input.name = "selected_files";
    input.value = filename;
    form.appendChild(input);
  });
  document.body.appendChild(form);
  form.submit();
}


function pollMetadata() {
  fetch("/current_metadata")
    .then(res => res.json())
    .then(data => {
      document.getElementById("captionField").textContent =
        data.caption || "No Caption";
      document.getElementById("uploaderField").textContent =
        data.uploader || "Unknown";
      document.getElementById("dateField").textContent = data.date_added
        ? formatDate(data.date_added)
        : "Unknown";
    })
    .catch((err) => {
      console.error("Failed to fetch metadata:", err);
    });
}


// setInterval(pollMetadata, 2000); // poll every 2 seconds
const evtSrc = new EventSource("/metadata_stream");
evtSrc.onmessage = e => {
  const data = JSON.parse(e.data);
  document.getElementById("captionField").textContent  = data.caption || "No Caption";
  document.getElementById("uploaderField").textContent = data.uploader || "Unknown";
  document.getElementById("dateField").textContent     = data.date_added 
    ? new Date(data.date_added).toLocaleDateString("en-GB")
    : "Unknown";
};

function toggleMenu() {
  const menu = document.getElementById("dropdown-menu");
  menu.style.display = menu.style.display === "flex" ? "none" : "flex";
}
document.addEventListener("click", function (e) {
  const menu = document.getElementById("dropdown-menu");
  const hamburger = document.querySelector(".hamburger");

  if (!menu || !hamburger) return;

  const isClickInsideMenu = menu.contains(e.target);
  const isClickOnHamburger = hamburger.contains(e.target);

  if (!isClickInsideMenu && !isClickOnHamburger) {
    menu.style.display = "none";
  }
});
