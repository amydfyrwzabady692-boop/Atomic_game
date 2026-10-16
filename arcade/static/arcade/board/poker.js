/* میز پوکر مینی‌اپ. همه‌ی قوانین و کارت‌ها در سرور است؛ سرور فقط کارت‌های خود بازیکن را می‌فرستد
   و این فایل میز را می‌کشد و حرکت (فولد/چک/کال/رِیز/آل‌این) را می‌فرستد. */
(function () {
  "use strict";

  var BOOT = window.BOARD_BOOT;
  var tg = window.Telegram && window.Telegram.WebApp ? window.Telegram.WebApp : null;
  var query = new URLSearchParams(location.search);
  var initData = tg && tg.initData ? tg.initData : "";
  if (!initData && BOOT.devAuth && query.get("dev_user")) initData = "dev:" + query.get("dev_user");

  var POLL_MS = 1100;
  var SUITS = { s: "♠", h: "♥", d: "♦", c: "♣" };
  var STREETS = { preflop: "قبل از فلاپ", flop: "فلاپ", turn: "ترن", river: "ریور" };
  var ACTIONS = { fold: "فولد", check: "چک", call: "کال", raise: "رِیز", allin: "آل‌این", leave: "ترک میز" };
  var ERRORS = {
    not_your_turn: "نوبت تو نیست.",
    illegal_move: "این حرکت الان مجاز نیست.",
    game_over: "بازی تمام شده است.",
    timeout: "وقت این نوبت تمام شده بود.",
    not_a_player: "تو بازیکن این میز نیستی؛ فقط تماشا می‌کنی.",
    match_not_found: "این مسابقه پیدا نشد.",
    match_not_running: "این مسابقه در جریان نیست.",
    bad_action: "این کار ممکن نیست.",
    rate_limited: "کمی آهسته‌تر! چند ثانیه صبر کن.",
    banned: "حساب تو مسدود شده است.",
    network: "اتصال به سرور برقرار نشد.",
  };
  var REASONS = { chips: "یک نفر همه‌ی ژتون‌ها را برد", limit: "دست‌ها تمام شد", left: "بقیه میز را ترک کردند" };

  var state = null;
  var busy = false;
  var receivedAt = 0;
  var resultShown = false;

  function $(id) { return document.getElementById(id); }
  function fa(value) {
    return String(value).replace(/\d/g, function (d) { return "۰۱۲۳۴۵۶۷۸۹"[d]; });
  }
  function money(value) { return fa(Number(value || 0).toLocaleString("en-US")).replace(/,/g, "٬"); }
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

  // ------------------------------------------------------------------ کارت
  function cardEl(code, extra) {
    var el = document.createElement("span");
    el.className = "card-face" + (extra ? " " + extra : "");
    if (code === null) { el.classList.add("slot"); return el; }
    if (!code) { el.classList.add("back"); return el; }
    var rank = code[0] === "T" ? "10" : code[0];
    el.textContent = rank + SUITS[code[1]];
    if (code[1] === "h" || code[1] === "d") el.classList.add("red");
    return el;
  }
  function winningCards() {
    var set = {};
    var result = state.result;
    if (!result) return set;
    result.winners.forEach(function (w) { (w.cards || []).forEach(function (c) { set[c] = true; }); });
    return set;
  }

  // ------------------------------------------------------------------ رسم
  function name(seat) { return state.players["s" + seat] || ""; }
  function drawSeats() {
    var box = $("seats");
    box.textContent = "";
    var win = winningCards();
    state.seats.forEach(function (s) {
      var el = document.createElement("div");
      el.className = "seat";
      if (state.to_act === s.seat && !state.over) el.classList.add("turn");
      if (state.you === s.seat) el.classList.add("me");
      if (s.folded && s.in_hand) el.classList.add("folded");
      if (s.left) el.classList.add("left");
      if (!s.in_hand && !state.over) el.classList.add("out");
      if (s.bet) {
        var bet = document.createElement("span");
        bet.className = "bet";
        bet.textContent = money(s.bet);
        el.appendChild(bet);
      }
      var info = document.createElement("div");
      info.className = "info";
      var b = document.createElement("b");
      b.textContent = name(s.seat) + (state.you === s.seat ? " (تو)" : "");
      if (s.dealer) {
        var d = document.createElement("span");
        d.className = "dealer";
        d.textContent = "D";
        b.appendChild(d);
      }
      info.appendChild(b);
      var small = document.createElement("small");
      var chips = document.createElement("span");
      chips.className = "chips";
      chips.textContent = money(s.chips) + " ژتون";
      small.appendChild(chips);
      var tag = s.left ? "ترک کرد" : s.allin ? "آل‌این" : s.folded && s.in_hand ? "فولد" : "";
      if (tag) {
        var t = document.createElement("span");
        t.className = "tag";
        t.textContent = "  · " + tag;
        small.appendChild(t);
      }
      info.appendChild(small);
      el.appendChild(info);
      if (s.cards.length && state.you !== s.seat) {
        var mini = document.createElement("div");
        mini.className = "mini";
        s.cards.forEach(function (c) { mini.appendChild(cardEl(c, c && win[c] ? "win" : "")); });
        el.appendChild(mini);
      }
      box.appendChild(el);
    });
  }
  function drawBoard(previous) {
    var box = $("board-cards");
    var known = previous ? previous.board.length : 0;
    box.textContent = "";
    var win = winningCards();
    for (var i = 0; i < 5; i++) {
      var code = state.board[i];
      var extra = (code && win[code] ? "win " : "") + (i >= known && code ? "deal" : "");
      box.appendChild(cardEl(code === undefined ? null : code, extra.trim()));
    }
    $("pot-amount").textContent = money(state.pot);
    $("street").textContent = STREETS[state.street] || "";
    $("hand-info").textContent =
      "دست " + fa(state.hand) + " از " + fa(state.hand_limit) + " · بلایند " + money(state.sb) + "/" + money(state.bb);
  }
  function drawMe() {
    var mine = state.you !== null && state.you !== undefined ? state.seats[state.you] : null;
    $("me").classList.toggle("hidden", !mine || !mine.cards.length);
    if (!mine) return;
    var box = $("my-cards");
    box.textContent = "";
    var win = winningCards();
    mine.cards.forEach(function (c) { box.appendChild(cardEl(c, c && win[c] ? "win" : "")); });
    $("my-hand").textContent = "";
  }
  function secondsLeft() {
    if (!state || state.over) return 0;
    return Math.max(0, state.seconds_left - Math.floor((Date.now() - receivedAt) / 1000));
  }
  function status() {
    var el = $("status");
    el.className = "";
    if (state.cancelled) { el.textContent = "این مسابقه لغو شده است."; el.className = "alert"; return; }
    if (state.over) { el.textContent = resultTitle(); return; }
    var text = "";
    if (state.phase === "pause" && state.result) {
      text = state.result.winners.map(function (w) {
        return "🏆 " + name(w.seat) + " " + money(w.amount) + " ژتون برد" + (w.hand ? " — " + w.hand : "");
      }).join("  ·  ");
      text += "  ·  دست بعد " + fa(secondsLeft()) + " ثانیه‌ی دیگر";
    } else if (state.to_act !== null) {
      var last = state.last_action;
      var prefix = last ? name(last.seat) + ": " + (ACTIONS[last.kind] || "") + (last.amount ? " " + money(last.amount) : "") + "  ·  " : "";
      var mine = state.you === state.to_act;
      text = prefix + (mine ? "نوبت توست" : "نوبت " + name(state.to_act)) + " (" + fa(secondsLeft()) + ")";
      if (mine) el.className = "mine";
    }
    el.textContent = text;
  }
  function controls() {
    var legal = state.legal || {};
    var mine = !state.over && !state.cancelled && state.you === state.to_act && state.phase === "betting";
    $("controls").classList.toggle("hidden", !mine);
    if (!mine) return;
    $("check-btn").classList.toggle("hidden", !legal.check);
    $("call-btn").classList.toggle("hidden", !legal.call);
    $("call-btn").textContent = "کال " + money(legal.call);
    var canRaise = !!legal.raise_min;
    $("raise-row").classList.toggle("hidden", !canRaise);
    if (canRaise) {
      var range = $("raise-range");
      range.min = legal.raise_min;
      range.max = legal.raise_max;
      range.step = Math.max(1, state.bb / 2);
      if (Number(range.value) < legal.raise_min || Number(range.value) > legal.raise_max) range.value = legal.raise_min;
      $("raise-btn").textContent = "رِیز تا " + money(range.value);
    }
    $("allin-btn").classList.toggle("hidden", !legal.allin);
    $("allin-btn").textContent = "آل‌این " + money(legal.allin);
  }
  function resultTitle() {
    var best = -1, top = null;
    state.seats.forEach(function (s) {
      var chips = s.left ? 0 : s.chips;
      if (chips > best) { best = chips; top = s.seat; }
    });
    if (top === null || best <= 0) return "بازی تمام شد";
    if (state.you === top) return "🏆 بیشترین ژتون مال توست!";
    return "🏆 " + name(top) + " بیشترین ژتون را دارد";
  }
  function showResult() {
    if (resultShown) return;
    resultShown = true;
    $("result-title").textContent = resultTitle();
    $("result-reason").textContent = (REASONS[state.over.reason] || "") + " — جایزه‌ی سکه بر اساس رتبه‌ی ژتون در گروه اعلام می‌شود.";
    setTimeout(function () { $("result").classList.remove("hidden"); }, 1200);
    haptic("success");
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
      status();
      return true;
    }
    var previous = state;
    state = response.state;
    receivedAt = Date.now();
    drawSeats();
    drawBoard(previous && previous.hand === state.hand ? previous : null);
    drawMe();
    status();
    controls();
    $("actions").classList.toggle("hidden", state.you === null || state.you === undefined);
    var mine = state.you !== null && state.you !== undefined ? state.seats[state.you] : null;
    $("resign-btn").disabled = !mine || mine.left || !!state.over || !!state.cancelled;
    if (previous && previous.version !== state.version && state.you === state.to_act && state.phase === "betting") haptic("medium");
    if (state.over) showResult();
    return true;
  }
  function refresh() {
    if (busy || document.hidden || !state) return;
    api("board/state", { version: state.version }).then(function (response) {
      if (!busy && response.ok) apply(response);
    });
  }
  function send(kind, amount) {
    if (!state || busy) return;
    busy = true;
    haptic("light");
    api("board/action", { action: kind, amount: amount || 0 }).then(function (response) {
      busy = false;
      apply(response);
      if (!response.ok) refresh();
    });
  }
  function fail(text) {
    $("loading-text").textContent = text;
    document.querySelector("#loading .spinner").classList.add("hidden");
  }

  $("fold-btn").addEventListener("click", function () { send("fold"); });
  $("check-btn").addEventListener("click", function () { send("check"); });
  $("call-btn").addEventListener("click", function () { send("call"); });
  $("allin-btn").addEventListener("click", function () { send("allin"); });
  $("raise-range").addEventListener("input", function () { $("raise-btn").textContent = "رِیز تا " + money(this.value); });
  $("raise-btn").addEventListener("click", function () { send("raise", Number($("raise-range").value)); });
  $("resign-btn").addEventListener("click", function () {
    var run = function () { send("resign"); };
    var question = "مطمئنی می‌خواهی میز را ترک کنی؟ ژتون‌هایت از بازی خارج می‌شود.";
    if (tg && tg.showConfirm) {
      try { tg.showConfirm(question, function (ok) { if (ok) run(); }); return; } catch (e) { /* قدیمی */ }
    }
    if (window.confirm(question)) run();
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
      if (tg.setHeaderColor) tg.setHeaderColor("#0b3d2e");
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
    setInterval(function () { if (state) status(); }, 500);
    document.addEventListener("visibilitychange", function () { if (!document.hidden) refresh(); });
  });
})();
