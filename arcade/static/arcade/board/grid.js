/* صفحه‌ی دوز و دوز چهارتایی مینی‌اپ. وضعیت از سرور می‌آید و حرکت‌ها همان‌جا اعتبارسنجی می‌شوند؛
   این فایل صفحه را می‌کشد، حرکت بازیکن را همان لحظه نشان می‌دهد (مهره از بالای ستون می‌افتد) و
   انتخاب او (خانه یا ستون) را می‌فرستد. */
(function () {
  "use strict";

  var BOOT = window.BOARD_BOOT;
  var tg = window.Telegram && window.Telegram.WebApp ? window.Telegram.WebApp : null;
  var query = new URLSearchParams(location.search);
  var initData = tg && tg.initData ? tg.initData : "";
  if (!initData && BOOT.devAuth && query.get("dev_user")) initData = "dev:" + query.get("dev_user");

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
  var leftBase = 0;
  var resultShown = false;
  var cells = [];
  var pollTimer = null;

  function $(id) { return document.getElementById(id); }
  function fa(value) {
    return String(value).replace(/\d/g, function (d) { return "۰۱۲۳۴۵۶۷۸۹"[d]; });
  }
  function now() { return window.performance && performance.now ? performance.now() : Date.now(); }
  function sound(kind) { if (window.SFX) window.SFX.play(kind); }
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
        // در دوز چهارتایی مهره از بالای ستون تا همین ردیف می‌افتد
        if (state.gravity) disc.style.setProperty("--fall", state.rows - Math.floor(i / state.cols));
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
    return Math.max(0, Math.ceil((leftBase - (now() - receivedAt)) / 1000));
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
    if (mine) el.className = secondsLeft() <= 5 ? "warn" : "mine";
    var text = state.you ? (mine ? "نوبت توست" : "نوبت حریف است") : "نوبت " + (state.players[state.turn] || "");
    text += " (" + fa(secondsLeft()) + " ثانیه)";
    if (el.textContent !== text) el.textContent = text;
  }
  function confetti() {
    var box = $("confetti");
    var colors = ["#ffc857", "#6ee7ff", "#a78bfa", "#34d399", "#ff5c7a", "#ffffff"];
    box.textContent = "";
    for (var i = 0; i < 40; i++) {
      var bit = document.createElement("i");
      bit.style.left = Math.random() * 100 + "%";
      bit.style.background = colors[i % colors.length];
      bit.style.animationDuration = (1.8 + Math.random() * 1.6).toFixed(2) + "s";
      bit.style.animationDelay = (Math.random() * 0.5).toFixed(2) + "s";
      box.appendChild(bit);
    }
    setTimeout(function () { box.textContent = ""; }, 4200);
  }
  function showResult() {
    if (resultShown) return;
    resultShown = true;
    var over = state.over;
    var won = !!state.you && state.you === over.side;
    $("result-icon").textContent = !over.side ? "🤝" : (!state.you || won ? "🏆" : "😔");
    $("result-title").textContent = resultTitle();
    $("result-reason").textContent = REASONS[over.reason] || "";
    var lost = !!state.you && !!over.side && !won;
    setTimeout(function () {
      $("result").classList.remove("hidden"); // خط برنده اول دیده شود
      if (won) confetti();
    }, 900);
    sound(won ? "win" : lost ? "lose" : "draw");
    haptic(won || !over.side ? "success" : "error");
  }

  function apply(response) {
    if (!response.ok) {
      toast(errorText(response.error));
      haptic("error");
      return false;
    }
    receivedAt = now();
    if (response.changed === false) {
      leftBase = response.left_ms !== undefined ? response.left_ms : response.seconds_left * 1000;
      clocks();
      status();
      return true;
    }
    var first = !state;
    var previous = state;
    state = response.state;
    leftBase = state.left_ms !== undefined ? state.left_ms : state.seconds_left * 1000;
    if (first) build();
    var placed = previous && previous.cells.join() !== state.cells.join() && !optimistic;
    optimistic = false;
    paint();
    if (placed) sound(state.gravity ? "drop" : "move");
    bars();
    clocks();
    status();
    $("actions").classList.toggle("hidden", !state.you);
    $("resign-btn").disabled = !state.you || !!state.over || !!state.cancelled;
    if (previous && previous.version !== state.version && state.you === state.turn && !state.over) {
      haptic("medium");
      sound("turn");
    }
    if (state.over) showResult();
    return true;
  }
  function pollDelay() {
    if (!state || state.over || state.cancelled) return 5000;
    return state.you && state.turn !== state.you ? 800 : 1300;
  }
  function loop() {
    clearTimeout(pollTimer);
    pollTimer = setTimeout(function () {
      if (document.hidden || busy || !state) { loop(); return; }
      api("board/state", { version: state.version }).then(function (response) {
        if (!busy && response.ok) apply(response);
        loop();
      });
    }, pollDelay());
  }
  function refresh() {
    if (busy || document.hidden || !state) return;
    api("board/state", { version: state.version }).then(function (response) {
      if (!busy && response.ok) apply(response);
    });
  }
  var optimistic = false;
  function onCell(cell) {
    if (!state || busy || state.over || state.cancelled || !state.you || state.you !== state.turn) return;
    var move = state.gravity ? Number(cell.dataset.c) : Number(cell.dataset.i);
    if (state.legal.indexOf(move) === -1) return;
    busy = true;
    haptic("light");
    clearPreview();
    // مهره همان لحظه روی صفحه می‌نشیند؛ نتیجه‌ی قطعی با جواب سرور می‌آید
    var before = state;
    var index = state.gravity ? landing(move) : move;
    var board = state.cells.slice();
    board[index] = state.you;
    state = Object.assign({}, state, { cells: board, last: index, legal: [], turn: state.you === state.sides[0] ? state.sides[1] : state.sides[0] });
    paint();
    bars();
    sound(state.gravity ? "drop" : "move");
    optimistic = true;
    api("board/move", { src: move }).then(function (response) {
      busy = false;
      if (!response.ok) {
        optimistic = false;
        state = before;
        paint();
        bars();
      }
      apply(response);
    });
  }
  // دوز چهارتایی: خانه‌ای که مهره در آن می‌افتد کم‌رنگ نشان داده می‌شود
  function clearPreview() {
    Array.prototype.forEach.call(document.querySelectorAll(".cell.preview"), function (cell) { cell.classList.remove("preview"); });
  }
  function preview(cell) {
    clearPreview();
    if (!cell || !state || !state.gravity || busy || state.over || !state.you || state.you !== state.turn) return;
    var column = Number(cell.dataset.c);
    if (state.legal.indexOf(column) === -1) return;
    var target = cells[landing(column)];
    if (!target) return;
    target.dataset.preview = state.you;
    target.classList.add("preview");
  }
  function fail(text) {
    $("loading-text").textContent = text;
    document.querySelector("#loading .spinner").classList.add("hidden");
  }

  $("grid").addEventListener("click", function (event) {
    var cell = event.target.closest(".cell");
    if (cell) onCell(cell);
  });
  $("grid").addEventListener("pointermove", function (event) { preview(event.target.closest(".cell")); });
  $("grid").addEventListener("pointerleave", clearPreview);
  function soundButton() { $("sound-btn").textContent = window.SFX && window.SFX.isMuted() ? "🔇" : "🔊"; }
  $("sound-btn").addEventListener("click", function () {
    if (!window.SFX) return;
    window.SFX.setMuted(!window.SFX.isMuted());
    soundButton();
    if (!window.SFX.isMuted()) setTimeout(function () { sound("move"); }, 60);
  });
  soundButton();
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
    loop();
    setInterval(function () { if (state) { clocks(); if (!state.over) status(); } }, 250);
    document.addEventListener("visibilitychange", function () { if (!document.hidden) refresh(); });
  });
})();
