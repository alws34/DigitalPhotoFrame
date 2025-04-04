<script>
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
      document.getElementById("logText").value = (data.logs || []).join(
        "\n"
      );
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
  panel.style.display =
    panel.style.display === "none" || panel.style.display === ""
      ? "flex"
      : "none";
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

let buffer = "";
fetch("/live_feed").then((response) => {
  const reader = response.body.getReader();
  const decoder = new TextDecoder();

  function readChunk() {
    reader.read().then(({ done, value }) => {
      if (done) return;
      buffer += decoder.decode(value, { stream: true });

      const lines = buffer.split("\n");
      buffer = lines.pop(); // preserve incomplete JSON

      for (const line of lines) {
        try {
          const data = JSON.parse(line);
          document.getElementById("liveImage").src =
            "data:image/jpeg;base64," + data.image;
          document.getElementById("captionField").textContent =
            data.metadata.caption || "No Caption";
          document.getElementById("uploaderField").textContent =
            data.metadata.uploader || "Unknown";
          document.getElementById("dateField").textContent = data.metadata
            .date_added
            ? formatDate(data.metadata.date_added)
            : "Unknown";
        } catch (e) {
          console.error("Invalid JSON stream:", e);
        }
      }

      readChunk();
    });
  }

  readChunk();
});
</script>