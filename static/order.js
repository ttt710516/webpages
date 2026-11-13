(() => {
  const $ = (id) => document.getElementById(id);
  const token = new URLSearchParams(location.search).get("t");
  const STATUS = {
    pending: "尚未取得繳費資訊",
    awaiting_payment: "等待付款",
    paid: "已付款",
  };
  let timer = null;

  function showError(msg) {
    $("error").textContent = msg;
    $("error").hidden = false;
  }

  function row(label, value) {
    const p = document.createElement("p");
    const b = document.createElement("span");
    b.className = "muted";
    b.textContent = label + "：";
    const v = document.createElement("strong");
    v.textContent = value;
    p.append(b, v);
    return p;
  }

  function renderPayInfo(info) {
    const box = $("pay-info");
    box.innerHTML = "";
    if (!info) { box.hidden = true; return; }
    if (info.vAccount) {
      box.append(row("銀行代碼", info.BankCode), row("轉帳帳號", info.vAccount));
    }
    if (info.PaymentNo) box.append(row("超商繳費代碼", info.PaymentNo));
    if (info.Barcode1) box.append(row("條碼", [info.Barcode1, info.Barcode2, info.Barcode3].join(" / ")));
    if (info.ExpireDate) box.append(row("繳費期限", info.ExpireDate));
    box.hidden = false;
  }

  async function refresh() {
    try {
      const res = await fetch(`/api/orders/${encodeURIComponent(token)}`);
      const o = await res.json();
      if (!res.ok) throw new Error(o.error || "讀取訂單失敗");

      $("trade-no").textContent = o.tradeNo;
      $("package").textContent = o.packageName;
      $("amount").textContent = `NT$ ${o.amount}`;
      $("payment").textContent = o.paymentName;
      const badge = $("status-badge");
      badge.textContent = STATUS[o.status] || o.status;
      badge.className = "badge " + o.status;

      const paid = o.status === "paid";
      renderPayInfo(paid ? null : o.paymentInfo);
      $("waiting").hidden = paid;
      $("paid").hidden = !paid;
      $("dev").hidden = paid || !o.testMode;
      if (paid) {
        $("code").textContent = o.code;
        $("credits-left").textContent = o.creditsLeft;
        try { localStorage.setItem("jianpu.code", o.code); } catch { /* ignore */ }
        clearInterval(timer);
      }
      $("order").hidden = false;
    } catch (err) {
      showError(err instanceof TypeError ? "無法連線到伺服器" : err.message);
      clearInterval(timer);
    }
  }

  async function simulate() {
    const btn = $("simulate-btn");
    btn.disabled = true;
    try {
      const res = await fetch(`/api/dev/simulate-pay/${encodeURIComponent(token)}`, { method: "POST" });
      if (!res.ok) throw new Error((await res.json()).error);
      await refresh();
    } catch (err) {
      showError(err.message);
    } finally {
      btn.disabled = false;
    }
  }

  async function copy() {
    try {
      await navigator.clipboard.writeText($("code").textContent);
      $("copy-btn").textContent = "已複製";
    } catch {
      $("copy-btn").textContent = "請手動複製";
    }
  }

  if (!token) {
    showError("網址缺少訂單資訊");
    return;
  }
  $("simulate-btn").addEventListener("click", simulate);
  $("copy-btn").addEventListener("click", copy);
  refresh();
  timer = setInterval(refresh, 5000);
})();
