const $ = (id) => document.getElementById(id);
const escapeHtml = (value) => String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));

async function refreshStats() {
  try {
    const r = await fetch("/api/stats");
    const s = await r.json();
    if ($("stat-total")) $("stat-total").textContent = s.total ?? 0;
    if ($("stat-unique")) $("stat-unique").textContent = s.unique ?? 0;
    if ($("stat-today")) $("stat-today").textContent = s.today ?? 0;
  } catch (_) {}
}

function renderResults(container, results) {
  if (!container) return;
  if (!results || !results.length) {
    container.innerHTML = '<div class="empty-state">No confident plate candidates found. Try a clearer, closer image.</div>';
    return;
  }
  container.innerHTML = results.map(r => `
    <div class="result-card">
      <div><div class="plate-text">${escapeHtml(r.plate_number)}</div>
      <div class="result-meta">${escapeHtml(r.state_name || "Unknown")} · ${escapeHtml(r.rto_name || "RTO unknown")}</div></div>
      <span class="confidence">${Number(r.confidence || 0).toFixed(1)}% OCR</span>
    </div>`).join("");
}

const fileInput = $("media-file");
if (fileInput) {
  fileInput.addEventListener("change", () => {
    $("selected-file").textContent = fileInput.files[0]?.name || "No file selected";
  });
}
const uploadForm = $("upload-form");
if (uploadForm) {
  uploadForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const file = fileInput.files[0];
    if (!file) { $("upload-status").textContent = "Please choose an image or video first."; return; }
    const btn = $("analyze-button");
    btn.disabled = true; btn.textContent = "Analyzing… please wait";
    $("upload-status").textContent = "Processing media. First OCR use may take longer while the model initializes.";
    $("upload-results").innerHTML = '<div class="empty-state">Working…</div>';
    const form = new FormData(); form.append("file", file);
    try {
      const response = await fetch("/api/detect", {method:"POST", body:form});
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "Detection failed.");
      renderResults($("upload-results"), data.results);
      $("upload-status").textContent = data.message + (data.frames_processed ? ` Frames processed: ${data.frames_processed}.` : "");
      await refreshStats();
    } catch (err) {
      $("upload-status").textContent = err.message || "An error occurred.";
      $("upload-results").innerHTML = '<div class="empty-state">No results available.</div>';
    } finally { btn.disabled = false; btn.textContent = "Analyze media →"; }
  });
}

const video = $("camera-video"), canvas = $("camera-canvas");
let cameraStream = null, cameraTimer = null, cameraBusy = false;
async function sendCameraFrame() {
  if (!video || !cameraStream || cameraBusy || video.readyState < 2) return;
  cameraBusy = true;
  try {
    const ctx = canvas.getContext("2d", {willReadFrequently:false});
    const scale = Math.min(1, 800 / video.videoWidth);
    canvas.width = Math.max(1, Math.round(video.videoWidth * scale));
    canvas.height = Math.max(1, Math.round(video.videoHeight * scale));
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
    const image = canvas.toDataURL("image/jpeg", 0.68);
    const response = await fetch("/api/detect-frame", {
      method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({image})
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Camera detection failed.");
    if (data.results?.length) {
      renderResults($("camera-results"), data.results);
      refreshStats();
    }
  } catch (err) {
    if ($("camera-status")) $("camera-status").textContent = "CHECK CAMERA";
  } finally { cameraBusy = false; }
}
if ($("start-camera")) {
  $("start-camera").addEventListener("click", async () => {
    try {
      cameraStream = await navigator.mediaDevices.getUserMedia({
        video:{facingMode:"environment", width:{ideal:1280}, height:{ideal:720}}, audio:false
      });
      video.srcObject = cameraStream; video.classList.add("visible");
      $("camera-placeholder").style.display = "none";
      $("camera-status").textContent = "LIVE"; $("camera-status").classList.add("on");
      $("start-camera").disabled = true; $("stop-camera").disabled = false;
      // OCR is computationally expensive; sample one frame every ~1.2 seconds to keep UI responsive.
      cameraTimer = setInterval(sendCameraFrame, 2000);
    } catch (err) {
      $("camera-status").textContent = "CAMERA ERROR";
      alert("Camera access failed. Allow camera permission in your browser and use http://127.0.0.1:5000.");
    }
  });
}
if ($("stop-camera")) {
  $("stop-camera").addEventListener("click", stopCamera);
}
function stopCamera() {
  if (cameraTimer) clearInterval(cameraTimer);
  cameraTimer = null;
  if (cameraStream) cameraStream.getTracks().forEach(t => t.stop());
  cameraStream = null;
  if (video) { video.srcObject = null; video.classList.remove("visible"); }
  if ($("camera-placeholder")) $("camera-placeholder").style.display = "flex";
  if ($("camera-status")) { $("camera-status").textContent = "OFFLINE"; $("camera-status").classList.remove("on"); }
  if ($("start-camera")) $("start-camera").disabled = false;
  if ($("stop-camera")) $("stop-camera").disabled = true;
}
window.addEventListener("beforeunload", stopCamera);

const rtoButton = $("rto-search");
if (rtoButton) {
  rtoButton.addEventListener("click", async () => {
    const raw = $("rto-query").value.toUpperCase().replace(/[^A-Z0-9]/g, "");
    if (!/^[A-Z]{2}\\d{1,2}/.test(raw)) { $("rto-result").textContent = "Enter a valid prefix such as UP62, UP32 or MH12."; return; }
    try {
      const resp = await fetch("/api/rto?q=" + encodeURIComponent(raw));
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.error || "Lookup failed.");
      $("rto-result").innerHTML = `<b>${escapeHtml(data.rto_code)}</b><br>State: ${escapeHtml(data.state_name)}<br>RTO: ${escapeHtml(data.rto_name)}`;
    } catch (err) { $("rto-result").textContent = err.message || "Could not query local RTO data."; }
  });
}

async function loadHistory() {
  const body = $("history-body");
  if (!body) return [];
  const q = $("history-search")?.value || "";
  try {
    const response = await fetch("/api/history?q=" + encodeURIComponent(q));
    const rows = await response.json();
    body.innerHTML = rows.length ? rows.map(r => `
      <tr data-id="${r.id}">
        <td><input class="edit-input" value="${escapeHtml(r.plate_number)}" aria-label="Plate number"></td>
        <td>${escapeHtml(r.state_name || "Unknown")}</td>
        <td>${escapeHtml(r.rto_name || "Unknown")}</td>
        <td>${Number(r.confidence || 0).toFixed(1)}%</td>
        <td>${escapeHtml(r.source || "")}</td>
        <td>${escapeHtml(r.created_at || "")}</td>
        <td><button class="small-btn save-plate" data-id="${r.id}">Save correction</button></td>
      </tr>`).join("") : '<tr><td colspan="7" class="empty-state">No history records found.</td></tr>';
    return rows;
  } catch (_) {
    body.innerHTML = '<tr><td colspan="7" class="empty-state">Could not load history.</td></tr>';
    return [];
  }
}
if ($("history-search-btn")) $("history-search-btn").addEventListener("click", loadHistory);
if ($("history-search")) $("history-search").addEventListener("keydown", e => { if (e.key === "Enter") loadHistory(); });
if ($("history-body")) {
  $("history-body").addEventListener("click", async e => {
    const btn = e.target.closest(".save-plate");
    if (!btn) return;
    const row = btn.closest("tr"), input = row.querySelector("input");
    try {
      const response = await fetch("/api/update-plate", {
        method:"POST", headers:{"Content-Type":"application/json"},
        body:JSON.stringify({id:Number(btn.dataset.id), plate:input.value})
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "Update failed");
      await loadHistory(); await refreshStats();
    } catch (err) { alert(err.message); }
  });
}
if ($("export-csv")) {
  $("export-csv").addEventListener("click", async () => {
    const rows = await loadHistory();
    const columns = ["id","plate_number","state_name","rto_name","confidence","source","created_at","reviewed"];
    const csvCell = v => `"${String(v ?? "").replace(/"/g,'""')}"`;
    const csv = [columns.join(","), ...rows.map(r => columns.map(c => csvCell(r[c])).join(","))].join("\r\n");
    const url = URL.createObjectURL(new Blob([csv], {type:"text/csv;charset=utf-8;"}));
    const a = document.createElement("a"); a.href = url; a.download = "anpr-history.csv"; a.click(); URL.revokeObjectURL(url);
  });
}
refreshStats();
loadHistory();
