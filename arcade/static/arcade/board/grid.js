/* صفحه‌ی دوز و دوز چهارتایی مینی‌اپ. وضعیت از سرور می‌آید و حرکت‌ها همان‌جا اعتبارسنجی می‌شوند؛
   این فایل فقط صفحه را می‌کشد و انتخاب بازیکن (خانه یا ستون) را می‌فرستد. */
(function () {
  "use strict";

  var BOOT = window.BOARD_BOOT;
  var tg = window.Telegram && window.Telegram.WebApp ? window.Telegram.WebApp : null;
  var query = new URLSearchParams(location.search);
  var initData = tg && tg.initData ? tg.initData : "";
  if (!initData && BOOT.devAuth && query.get("dev_user")) initData = "dev:" + query.get("dev_user");

  var POLL_MS = 1200;
  var TITLES = { tictactoe: "❌⭕️ دوز", connect4: "🔴🟡 دوز چهارتایی" };
  var MARKS = { X: "✕", O: "◯", R: "", Y: "" };
  var ERRORS = {
    not_your_turn: "نوبت تو نیست.",
    illegal_move: "این حرکت مجاز نیست.",
    game_over: "بازی تمام شده است.",
    not_a_player: "تو بازیکن این مسابقه نیستی؛ فقط تماشا می‌کنی.",
    match_not_found: "این مسابقه پیدا نشد.",
    match_not_running: "این مسابقه در جریان نیست.",
    rate_limited: "کمی آهسته‌تر! چند ثانیه صبر کن.",
    banned: "حساب تو مسدود شده است.",
    network: "اتصال به سرور برقرار نشد.",
  };
  var REASONS = { line: "خط کامل شد", full: "صفحه پر شد", timeout: "پایان وقت", resign: "تسلیم" };

  var state = null;
  var busy = false;
  var receivedAt = 0;
  var resultShown = false;
  var cells = [];

  function $(id) { return document.getElementById(id); }
  function fa(value) {
    return String(value).replace(/\d/g, function (d) { return "۰۱۲۳۴۵۶۷۸۹"[d]; });
  }
  function haptic(kind) {
    try {
      if (!tg || !tg.HapticFeedback) return;
      if (kind === "error" || kind === "success") tg.HapticFeedback.notificationOccurred(kind);
      else tg.HapticFeedback.impactOccurred(kind || "light");
    } catch (e) { /* نسخه‌های قدیمی */ }
  }
  function errorText(code) {
    if (code && code.indexOf("auth_") === 0) return "این صفحه باید از داخل تلگرام باز شود.";
    return ERRORS[code] || "مشکلی پیش آمد. دوباره امتحان کن.";
  }
  var toastTimer = null;
  function toast(text) {
    var el = $("toast");
    el.textContent = text;
    el.classList.remove("hidden");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { el.classList.add("hidden"); }, 2600);
  }
  function api(path, body) {
    body = body || {};
    body.initData = initData;
    body.match_token = BOOT.token;
    return fetch(BOOT.apiBase + path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }).then(function (response) { return response.json(); })
      .catch(function () { return { ok: false, error: "network" }; });
  }

  // ------------------------------------------------------------------ صفحه
  function build() {
    var grid = $("grid");
    grid.textContent = "";
    grid.style.gridTemplateColumns = "repeat(" + state.cols + ", 1fr)";
    $("grid-wrap").classList.toggle("xo", !state.gravity);
    $("title").textContent = TITLES[state.game] || "";
    document.title = (TITLES[state.game] || "بازی").replace(/^[^ ]+ /, "");
    cells = [];
    for (var r = 0; r < state.rows; r++) {
      var row = state.gravity ? state.rows - 1 - r : r; // در دوز چهارتایی ردیف ۰ پایین است
      for (var column = 0; column < state.cols; column++) {
        var index = row * state.cols + column;
        var cell = document.createElement("button");
        cell.type = "button";
        cell.className = "cell";
        cell.dataset.i = index;
        cell.dataset.c = column;
        grid.appendChild(cell);
        cells[index] = cell;
      }
    }
  }
  function landing(column) {
    for (var row = 0; row < state.rows; row++) {
      if (!state.cells[row * state.cols + column]) return row * state.cols + column;
    }
    return -1;
  }
  function paint() {
    var open = {};
    state.legal.forEach(function (move) { open[state.gravity ? landing(move) : move] = true; });
    for (var i = 0; i < cells.length; i++) {
      var cell = cells[i];
      var mark = state.cells[i];
      var disc = cell.querySelector("i");
      if (mark && !disc) {
        disc = document.createElement("i");
        disc.className = mark;
        disc.textContent = MARKS[mark];
        cell.appendChild(disc);
      } else if (!mark && disc) {
        cell.removeChild(disc);
      }
      cell.classList.toggle("last", state.last === i);
      cell.classList.toggle("win", state.win.indexOf(i) !== -1);
      cell.classList.toggle("hint", !!open[i]);
      cell.classList.toggle("open", state.legal.length > 0 && !mark);
    }
  }

  function bars() {
    var mine = state.you || state.sides[0];
    var theirs = state.sides[0] === mine ? state.sides[1] : state.sides[0];
    [["bottom", mine], ["top", theirs]].forEach(function (pair) {
      var disc = $(pair[0] + "-disc");
      disc.className = "disc " + pair[1];
      disc.textContent = MARKS[pair[1]];
      $(pair[0] + "-name").textContent = (state.players[pair[1]] || "") + (state.you === pair[1] ? " (تو)" : "");
      $("bar-" + pair[0]).classList.toggle("active", !state.over && state.turn === pair[1]);
      $("bar-" + pair[0]).dataset.side = pair[1];
    });
  }
  function secondsLeft() {
    if (!state || state.over) return 0;
    return Math.max(0, state.seconds_left - Math.floor((Date.now() - receivedAt) / 1000));
  }
  function clocks() {
    if (!state) return;
    var left = secondsLeft();
    ["bottom", "top"].forEach(function (prefix) {
      var el = $(prefix + "-clock");
      var running = !state.over && state.turn === $("bar-" + prefix).dataset.side;
      el.textContent = fa(running ? left : state.move_seconds);
      el.classList.toggle("low", running && left <= 5);
    });
  }
  function resultTitle() {
    var over = state.over;
    if (!over.side) return "🤝 مساوی";
    if (!state.you) return "🏆 " + (state.players[over.side] || "") + " برد";
    return state.you === over.side ? "🏆 بردی!" : "باختی";
  }
  function status() {
    var el = $("status");
    el.className = "";
    if (state.cancelled) { el.textContent = "این مسابقه لغو شده است."; el.className = "alert"; return; }
    if (state.over) { el.textContent = resultTitle(); return; }
    var mine = state.you === state.turn;
    if (mine) el.className = "mine";
    el.textContent = state.you ? (mine ? "نوبت توست" : "نوبت حریف است") : "نوبت " + (state.players[state.turn] || "");
  }
  function showResult() {
    if (resultShown) return;
    resultShown = true;
    var over = state.over;
    var won = !!state.you && state.you === over.side;
    $("result-icon").textContent = !over.side ? "🤝" : (!state.you || won ? "🏆" : "😔");
    $("result-title").textContent = resultTitle();
    $("result-reason").textContent = REASONS[over.reason] || "";
    setTimeout(function () { $("result").classList.remove("hidden"); }, 900); // خط برنده اول دیده شود
    haptic(won || !over.side ? "success" : "error");
  }

  function apply(response) {
    if (!response.ok) {
      toast(errorText(response.error));
      haptic("error");
      return false;
    }
    if (response.changed === false) {
      state.seconds_left = response.seconds_left;
      receivedAt = Date.now();
      clocks();
      return true;
    }
    var first = !state;
    var previous = state;
    state = response.state;
    receivedAt = Date.now();
    if (first) build();
    paint();
    bars();
    clocks();
    status();
    $("actions").classList.toggle("hidden", !state.you);
    $("resign-btn").disabled = !state.you || !!state.over || !!state.cancelled;
    if (previous && previous.version !== state.version && state.you === state.turn) haptic("medium");
    if (state.over) showResult();
    return true;
  }
  function refresh() {
    if (busy || document.hidden || !state) return;
    api("board/state", { version: state.version }).then(function (response) {
      if (!busy && response.ok) apply(response);
    });
  }
  function onCell(cell) {
    if (!state || busy || state.over || state.cancelled || !state.you || state.you !== state.turn) return;
    var move = state.gravity ? Number(cell.dataset.c) : Number(cell.dataset.i);
    if (state.legal.indexOf(move) === -1) return;
    busy = true;
    haptic("light");
    api("board/move", { src: move }).then(function (response) {
      busy = false;
      apply(response);
    });
  }
  function fail(text) {
    $("loading-text").textContent = text;
    document.querySelector("#loading .spinner").classList.add("hidden");
  }

  $("grid").addEventListener("click", function (event) {
    var cell = event.target.closest(".cell");
    if (cell) onCell(cell);
  });
  $("resign-btn").addEventListener("click", function () {
    var run = function () {
      busy = true;
      api("board/action", { action: "resign" }).then(function (response) { busy = false; apply(response); });
    };
    if (tg && tg.showConfirm) {
      try { tg.showConfirm("مطمئنی می‌خواهی تسلیم شوی؟", function (ok) { if (ok) run(); }); return; } catch (e) { /* قدیمی */ }
    }
    if (window.confirm("مطمئنی می‌خواهی تسلیم شوی؟")) run();
  });
  $("result-close").addEventListener("click", function () {
    if (tg && tg.close) { try { tg.close(); return; } catch (e) { /* قدیمی */ } }
    $("result").classList.add("hidden");
  });
  $("result-view").addEventListener("click", function () { $("result").classList.add("hidden"); });

  if (tg) {
    try {
      tg.ready();
      tg.expand();
      if (tg.setHeaderColor) tg.setHeaderColor("#141a2e");
      if (tg.setBackgroundColor) tg.setBackgroundColor("#0d1024");
      if (tg.disableVerticalSwipes) tg.disableVerticalSwipes();
    } catch (e) { /* نسخه‌های قدیمی */ }
  }
  if (!initData) { fail(errorText("auth_missing")); return; }
  api("board/state", {}).then(function (response) {
    if (!response.ok) { fail(errorText(response.error)); return; }
    apply(response);
    $("loading").classList.add("hidden");
    $("game").classList.remove("hidden");
    setInterval(refresh, POLL_MS);
    setInterval(clocks, 500);
    document.addEventListener("visibilitychange", function () { if (!document.hidden) refresh(); });
  });
})();
