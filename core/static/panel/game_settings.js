/* صفحه‌ی «تنظیمات بازی‌ها» در پنل ادمین: دکمه‌های − و + و کلید فعال/غیرفعال بدون بارگذاری
   دوباره‌ی صفحه ذخیره می‌شوند. سرور مقدار را در بازه‌ی مجاز هر بازی نگه می‌دارد. */
(function () {
  "use strict";
  var FA = "۰۱۲۳۴۵۶۷۸۹";
  function fa(n) { return String(n).replace(/\d/g, function (d) { return FA[d]; }); }

  function csrf() {
    var m = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
    if (m) return decodeURIComponent(m[1]);
    var input = document.querySelector("input[name=csrfmiddlewaretoken]");
    return input ? input.value : "";
  }

  function post(url, data) {
    var body = new URLSearchParams(data);
    return fetch(url, {
      method: "POST",
      credentials: "same-origin",
      headers: { "X-CSRFToken": csrf(), "X-Requested-With": "XMLHttpRequest" },
      body: body,
    }).then(function (r) { return r.json(); });
  }

  var toastTimer = null;
  function toast(text, bad) {
    var el = document.getElementById("gs-toast");
    if (!el) {
      el = document.createElement("div");
      el.id = "gs-toast";
      document.body.appendChild(el);
    }
    el.textContent = text;
    el.className = "show" + (bad ? " bad" : "");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { el.className = ""; }, 1600);
  }

  /* بعد از هر تغییر، هر دو شمارنده‌ی همان ردیف با مقدار و محدوده‌ی تازه هماهنگ می‌شوند */
  function paintRow(row, res) {
    row.querySelectorAll(".gs-stepper").forEach(function (stepper) {
      var isMin = stepper.dataset.field === "min";
      var value = isMin ? res.min : res.max;
      var lo = isMin ? res.floor : res.min;
      var hi = isMin ? res.max : res.ceiling;
      stepper.querySelector("output").textContent = fa(value);
      stepper.querySelector('[data-delta="-1"]').disabled = value <= lo;
      stepper.querySelector('[data-delta="1"]').disabled = value >= hi;
    });
    var sw = row.querySelector(".gs-switch");
    if (sw) {
      sw.classList.toggle("on", res.enabled);
      sw.querySelector("span").textContent = res.enabled ? "فعال" : "غیرفعال";
    }
    row.classList.toggle("gs-off", !res.enabled);
    var changed = row.querySelector(".field-updated_at");
    if (changed) changed.textContent = "همین حالا";
  }

  document.addEventListener("click", function (event) {
    var button = event.target.closest(".gs-stepper button, .gs-switch");
    if (!button || button.disabled) return;
    event.preventDefault();
    var row = button.closest("tr");
    var stepper = button.closest(".gs-stepper");
    var url = stepper ? stepper.dataset.url : button.dataset.url;
    var data = stepper ? { field: stepper.dataset.field, delta: button.dataset.delta } : { field: "enabled" };
    row.classList.add("gs-busy");
    post(url, data).then(function (res) {
      row.classList.remove("gs-busy");
      if (!res.ok) { toast("ذخیره نشد", true); return; }
      paintRow(row, res);
      if (stepper) {
        var out = stepper.querySelector("output");
        out.classList.remove("bump");
        void out.offsetWidth;
        out.classList.add("bump");
      }
      toast("ذخیره شد ✓");
    }).catch(function () {
      row.classList.remove("gs-busy");
      toast("اتصال به سرور برقرار نشد", true);
    });
  });

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll(".gs-switch:not(.on)").forEach(function (sw) {
      sw.closest("tr").classList.add("gs-off");
    });
  });
})();
