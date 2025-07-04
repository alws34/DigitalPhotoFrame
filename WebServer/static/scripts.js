function logout() {
  window.location.href = "/logout";
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
  fetch("/clear_logs", { method: "POST" })
    .then((res) => res.json())
    .then((data) => {
      alert(data.message || "Logs cleared");
      document.getElementById("logText").value = "";
    });
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
  // Get the values from the modal fields
  const caption = document.getElementById("editCaption").value;
  const uploader = document.getElementById("editUploader").value;
  const hash = document.getElementById("editHash").value;

  // Send the hash, caption, and uploader in the payload
  fetch("/update_metadata", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      hash: hash,
      caption: caption,
      uploader: uploader,
    }),
  })
    .then((res) => res.json())
    .then((data) => {
      alert(data.message || "Metadata updated.");
      closeEditModal();
    })
    .catch((err) => alert("Failed to update metadata"));
}

function downloadImage(imageName) {
  window.location.href = `/download/${encodeURIComponent(imageName)}`;
}

function deleteImage(imageName) {
  if (confirm(`Are you sure you want to delete ${imageName}?`)) {
    const form = document.createElement("form");
    form.method = "POST";
    form.action = `/delete/${encodeURIComponent(imageName)}`;
    document.body.appendChild(form);
    form.submit();
  }
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
          <tr><td>Uploader:</td><td><input name="uploader_${i}"></td></tr>
          <tr><td>Caption:</td><td><input name="caption_${i}"></td></tr>
        </table>
      `;
      container.appendChild(div);
    };
    reader.readAsDataURL(files[i]);
  }
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
    console.log("✅ Intercepted form submission");

    const files = document.getElementById("fileInput").files;
    const previews = document.querySelectorAll("#previewContainer .image-preview");

    if (!files.length) {
      alert("No files selected.");
      return;
    }

    const formData = new FormData();
    for (let i = 0; i < previews.length; i++) {
      const file = files[i];
      const preview = previews[i];

      const uploader = preview.querySelector(`input[name="uploader_${i}"]`);
      const caption  = preview.querySelector(`input[name="caption_${i}"]`);

      // allow both fields to be blank
      const uploaderVal = uploader  ? uploader.value.trim() : "";
      const captionVal  = caption   ? caption.value.trim()  : "";

      formData.append("file[]", file);
      formData.append(`uploader_${i}`, uploaderVal);
      formData.append(`caption_${i}`, captionVal);
    }

    fetch("/upload_with_metadata", {
      method: "POST",
      body: formData,
    })
      .then((res) => res.json())
      .then((data) => {
        console.log(data);
        alert("Upload successful!");
        closeUploadModal();
        location.reload();
      })
      .catch((err) => {
        alert("Upload failed.");
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
      uploader.required = true;

      const caption = document.createElement("input");
      caption.type = "text";
      caption.placeholder = "Caption";
      caption.name = `caption_${index}`;
      caption.required = true;

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
  if (selected.length === 0) return alert("No images selected.");
  const form = document.createElement("form");
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
  if (selected.length === 0) return alert("No images selected.");
  if (!confirm(`Are you sure you want to delete ${selected.length} image(s)?`)) return;
  const form = document.createElement("form");
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
