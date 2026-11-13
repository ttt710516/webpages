(() => {
  const ORDERS_KEY = "jianpu.orders";
  const $ = (id) => document.getElementById(id);

  const store = {
    getOrders() {
      try { return JSON.parse(localStorage.getItem(ORDERS_KEY)) || []; } catch { return []; }
    },
    addOrder(o) {
      try {
        const list = [o, ...this.getOrders()].slice(0, 20);
        localStorage.setItem(ORDERS_KEY, JSON.stringify(list));
      } catch { /* ignore */ }
    },
  };

  function showMsg(el, text, ok = false) {
    el.textContent = text;
    el.classList.toggle("ok", ok);
    el.hidden = false;
  }

  function option(name, value, title, sub, checked) {
    const label = document.createElement("label");
    label.className = "option";
    const input = document.createElement("input");
    input.type = "radio";
    input.name = name;
    input.value = value;
    input.checked = checked;
    input.required = true;
    const t = document.createElement("span");
    t.className = "opt-title";
    t.textContent = title;
    label.append(input, t);
    if (sub) {
      const s = document.createElement("span");
      s.className = "opt-sub";
      s.textContent = sub;
      label.append(s);
    }
    return label;
  }

  async function load() {
    const res = await fetch("/api/packages");
    const data = await res.json();
    $("test-banner").hidden = !data.testMode;

    const pk = $("packages");
    data.packages.forEach((p, i) => {
      const per = (p.price / p.credits).toFixed(1).replace(/\.0$/, "");
      pk.append(option("package", p.id, `NT$ ${p.price}`, `${p.name}・每次約 ${per} 元`, i === 0));
    });
    const pm = $("payments");
    data.payments.forEach((p, i) => pm.append(option("payment", p.id, p.name, "", i === 0)));

    renderOrders();
  }

  function renderOrders() {
    const orders = store.getOrders();
    if (!orders.length) return;
    $("my-orders").hidden = false;
    const ul = $("order-list");
    ul.innerHTML = "";
    orders.forEach((o) => {
      const li = document.createElement("li");
      const a = document.createElement("a");
      a.href = o.orderUrl;
      a.textContent = `${o.packageName}・NT$ ${o.price}`;
      const t = document.createElement("span");
      t.className = "muted small";
      t.textContent = new Date(o.createdAt).toLocaleString("zh-TW");
      li.append(a, t);
      ul.append(li);
    });
  }

  async function submit(e) {
    e.preventDefault();
    const form = e.target;
    const btn = $("buy-btn");
    const msg = $("buy-msg");
    msg.hidden = true;
    btn.disabled = true;
    try {
      const pkgInput = form.querySelector("input[name=package]:checked");
      const res = await fetch("/api/orders", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          package: pkgInput.value,
          payment: form.querySelector("input[name=payment]:checked").value,
          email: $("email").value.trim(),
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "建立訂單失敗");

      const label = pkgInput.closest("label");
      store.addOrder({
        orderUrl: data.orderUrl,
        packageName: label.querySelector(".opt-sub").textContent.split("・")[0],
        price: label.querySelector(".opt-title").textContent.replace("NT$ ", ""),
        createdAt: Date.now(),
      });

      // 組一個表單送到綠界
      const f = document.createElement("form");
      f.method = "POST";
      f.action = data.checkout.action;
      f.acceptCharset = "UTF-8";
      for (const [k, v] of Object.entries(data.checkout.fields)) {
        const input = document.createElement("input");
        input.type = "hidden";
        input.name = k;
        input.value = v;
        f.append(input);
      }
      document.body.append(f);
      f.submit();
    } catch (err) {
      showMsg(msg, err instanceof TypeError ? "無法連線到伺服器" : err.message);
      btn.disabled = false;
    }
  }

  async function checkBalance(e) {
    e.preventDefault();
    const msg = $("balance-msg");
    try {
      const res = await fetch("/api/code", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ code: $("balance-code").value }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error);
      showMsg(msg, `${data.code} 剩餘 ${data.creditsLeft} / ${data.creditsTotal} 點`, true);
    } catch (err) {
      showMsg(msg, err instanceof TypeError ? "無法連線到伺服器" : err.message);
    }
  }

  // 從綠界按「上一頁」回來時，讓按鈕恢復可按
  window.addEventListener("pageshow", () => { $("buy-btn").disabled = false; });

  $("buy-form").addEventListener("submit", submit);
  $("balance-form").addEventListener("submit", checkBalance);
  load().catch(() => showMsg($("buy-msg"), "無法載入方案，請重新整理"));
})();
