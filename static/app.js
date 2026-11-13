(() => {
  const MAX_BYTES = 20 * 1024 * 1024;
  const ALLOWED = [".pdf", ".png", ".jpg", ".jpeg", ".musicxml", ".xml", ".mxl"];
  const CODE_KEY = "jianpu.code";

  const $ = (id) => document.getElementById(id);
  const dropzone = $("dropzone");
  const fileInput = $("file-input");
  const statusEl = $("status");
  const uploadSection = $("upload-section");
  const resultSection = $("result-section");
  const preview = $("preview");
  const codeInput = $("code-input");
  const unlockMsg = $("unlock-msg");

  let busy = false;
  let currentJob = null;

  // localStorage 只用來記住上次用的兌換碼，讀不到也不影響功能
  const store = {
    get(k) { try { return localStorage.getItem(k); } catch { return null; } },
    set(k, v) { try { localStorage.setItem(k, v); } catch { /* ignore */ } },
  };

  function showStatus(message, { loading = false, error = false } = {}) {
    statusEl.hidden = false;
    statusEl.className = "status" + (error ? " error" : "");
    statusEl.innerHTML = "";
    if (loading) {
      const s = document.createElement("span");
      s.className = "spinner";
      statusEl.appendChild(s);
    }
    statusEl.appendChild(document.createTextNode(message));
  }

  function hideStatus() { statusEl.hidden = true; }

  function setBusy(v) {
    busy = v;
    dropzone.classList.toggle("disabled", v);
  }

  function extOf(name) {
    const i = name.lastIndexOf(".");
    return i >= 0 ? name.slice(i).toLowerCase() : "";
  }

  async function postJSON(url, body) {
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    let data = {};
    try { data = await res.json(); } catch { /* 非 JSON */ }
    if (!res.ok) throw new Error(data.error || `伺服器錯誤（${res.status}）`);
    return data;
  }

  // ---------- 上傳與轉換 ----------
  async function handleFile(file) {
    if (!file || busy) return;

    if (!ALLOWED.includes(extOf(file.name))) {
      showStatus(`不支援的檔案格式。請上傳 ${ALLOWED.join("、")}`, { error: true });
      return;
    }
    if (file.size > MAX_BYTES) {
      showStatus("檔案太大，上限為 20 MB", { error: true });
      return;
    }

    setBusy(true);
    showStatus(`正在轉換「${file.name}」…`, { loading: true });

    try {
      const res = await fetch("/api/convert", {
        method: "POST",
        headers: {
          "Content-Type": "application/octet-stream",
          "X-Filename": encodeURIComponent(file.name),
        },
        body: file,
      });
      let data = {};
      try { data = await res.json(); } catch { /* 非 JSON */ }
      if (!res.ok) throw new Error(data.error || `伺服器錯誤（${res.status}）`);
      showResult(file.name, data);
    } catch (err) {
      const msg = err instanceof TypeError ? "無法連線到伺服器" : err.message;
      showStatus(`轉換失敗：${msg}`, { error: true });
    } finally {
      setBusy(false);
      fileInput.value = "";
    }
  }

  function showResult(sourceName, data) {
    hideStatus();
    currentJob = data;
    $("source-name").textContent = sourceName;
    $("result-name").textContent = data.filename;

    preview.innerHTML = "";
    const img = document.createElement("img");
    img.src = data.previewUrl;
    img.alt = "簡譜預覽（含浮水印）";
    preview.appendChild(img);

    $("unlock-form-wrap").hidden = false;
    $("unlocked-wrap").hidden = true;
    unlockMsg.hidden = true;
    codeInput.value = store.get(CODE_KEY) || "";

    uploadSection.hidden = true;
    resultSection.hidden = false;
  }

  function reset() {
    currentJob = null;
    resultSection.hidden = true;
    uploadSection.hidden = false;
    preview.innerHTML = "";
    hideStatus();
  }

  // ---------- 兌換碼解鎖 ----------
  async function unlock(e) {
    e.preventDefault();
    if (!currentJob) return;
    const btn = $("unlock-btn");
    btn.disabled = true;
    unlockMsg.hidden = true;
    try {
      const data = await postJSON("/api/unlock", { jobId: currentJob.id, code: codeInput.value });
      store.set(CODE_KEY, data.code);
      $("used-code").textContent = data.code;
      $("credits-left").textContent = data.creditsLeft;
      const dl = $("download-btn");
      dl.href = data.downloadUrl;
      dl.setAttribute("download", currentJob.filename);
      $("unlock-form-wrap").hidden = true;
      $("unlocked-wrap").hidden = false;
      dl.click(); // 解鎖後直接開始下載
    } catch (err) {
      unlockMsg.textContent = err instanceof TypeError ? "無法連線到伺服器" : err.message;
      unlockMsg.hidden = false;
    } finally {
      btn.disabled = false;
    }
  }

  // ---------- 事件 ----------
  fileInput.addEventListener("change", () => handleFile(fileInput.files[0]));

  dropzone.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      fileInput.click();
    }
  });

  ["dragenter", "dragover"].forEach((type) =>
    dropzone.addEventListener(type, (e) => {
      e.preventDefault();
      dropzone.classList.add("dragover");
    })
  );
  ["dragleave", "drop"].forEach((type) =>
    dropzone.addEventListener(type, (e) => {
      e.preventDefault();
      dropzone.classList.remove("dragover");
    })
  );
  dropzone.addEventListener("drop", (e) => handleFile(e.dataTransfer.files[0]));

  window.addEventListener("dragover", (e) => e.preventDefault());
  window.addEventListener("drop", (e) => e.preventDefault());

  $("reset-btn").addEventListener("click", reset);
  $("unlock-form").addEventListener("submit", unlock);
})();
