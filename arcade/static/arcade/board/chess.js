/* صفحه‌ی شطرنج مینی‌اپ. وضعیت بازی همیشه از سرور می‌آید و حرکت‌ها همان‌جا اعتبارسنجی می‌شوند؛
   این فایل فقط تخته را می‌کشد، حرکت‌های مجازی را که سرور فرستاده نشان می‌دهد و انتخاب بازیکن را می‌فرستد. */
(function () {
  "use strict";

  var BOOT = window.BOARD_BOOT;
  var tg = window.Telegram && window.Telegram.WebApp ? window.Telegram.WebApp : null;
  var query = new URLSearchParams(location.search);
  var initData = tg && tg.initData ? tg.initData : "";
  if (!initData && BOOT.devAuth && query.get("dev_user")) initData = "dev:" + query.get("dev_user");

  var POLL_MS = 1200;
  var START_COUNT = { p: 8, n: 2, b: 2, r: 2, q: 1 };
  var VALUE = { p: 1, n: 3, b: 3, r: 5, q: 9 };
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
  var REASONS = {
    checkmate: "کیش و مات",
    resign: "تسلیم",
    timeout: "پایان وقت",
    stalemate: "پات (حرکت مجاز نمانده)",
    insufficient: "مهره‌ی کافی برای مات نمانده",
    fifty: "قانون ۵۰ حرکت",
    repetition: "تکرار سه‌باره‌ی وضعیت",
    agreed: "با توافق دو بازیکن",
    limit: "سقف تعداد حرکت‌ها",
  };

  var state = null; // آخرین وضعیت سرور
  var selected = null; // خانه‌ی مهره‌ی انتخاب‌شده
  var busy = false; // در حال فرستادن حرکت
  var flipped = false; // بازیکن سیاه تخته را از سمت خودش می‌بیند
  var receivedAt = 0;
  var resultShown = false;
  var squares = [];

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

  function pieceUrl(piece) {
    var color = piece === piece.toUpperCase() ? "w" : "b";
    return BOOT.pieceBase + color + piece.toLowerCase() + ".png?v=" + BOOT.version;
  }
  function colorOf(piece) {
    if (piece === ".") return null;
    return piece === piece.toUpperCase() ? "w" : "b";
  }

  // ------------------------------------------------------------------ ساخت تخته
  function buildBoard() {
    var board = $("board");
    board.textContent = "";
    squares = [];
    for (var row = 0; row < 8; row++) {
      for (var col = 0; col < 8; col++) {
        var rank = flipped ? row : 7 - row;
        var file = flipped ? 7 - col : col;
        var index = rank * 8 + file;
        var cell = document.createElement("button");
        cell.type = "button";
        cell.className = "sq" + ((rank + file) % 2 === 0 ? " dark" : "");
        cell.dataset.i = index;
        if (row === 7) {
          var fileMark = document.createElement("span");
          fileMark.className = "coord file";
          fileMark.textContent = "abcdefgh"[file];
          cell.appendChild(fileMark);
        }
        if (col === 0) {
          var rankMark = document.createElement("span");
          rankMark.className = "coord rank";
          rankMark.textContent = rank + 1;
          cell.appendChild(rankMark);
        }
        board.appendChild(cell);
        squares[index] = cell;
      }
    }
  }

  function setPiece(cell, piece) {
    var img = cell.querySelector("img");
    if (piece === ".") {
      if (img) cell.removeChild(img);
      cell.dataset.p = "";
      return;
    }
    if (cell.dataset.p === piece) return;
    if (!img) {
      img = document.createElement("img");
      img.alt = "";
      img.draggable = false;
      cell.appendChild(img);
    }
    img.src = pieceUrl(piece);
    cell.dataset.p = piece;
  }

  function targetsOf(index) {
    return (state && state.legal && state.legal[String(index)]) || [];
  }

  function paint(arrived) {
    var targets = selected === null ? [] : targetsOf(selected);
    for (var i = 0; i < 64; i++) {
      var cell = squares[i];
      var piece = state.board[i];
      setPiece(cell, piece);
      cell.classList.toggle("last", !!state.last && (state.last[0] === i || state.last[1] === i));
      cell.classList.toggle("check", state.check === i);
      cell.classList.toggle("selected", selected === i);
      var isTarget = targets.indexOf(i) !== -1;
      cell.classList.toggle("target", isTarget);
      cell.classList.toggle("capture", isTarget && (piece !== "." || isEnPassant(selected, i)));
      cell.classList.toggle("arrived", arrived === i);
    }
  }
  function isEnPassant(src, dst) {
    if (src === null) return false;
    return state.board[src].toLowerCase() === "p" && src % 8 !== dst % 8 && state.board[dst] === ".";
  }

  // ------------------------------------------------------------------ نوار بازیکن‌ها
  function takenBy(side) {
    // مهره‌هایی که این طرف از حریف گرفته = کمبود مهره‌های حریف نسبت به شروع بازی
    var counts = { p: 0, n: 0, b: 0, r: 0, q: 0 };
    for (var i = 0; i < 64; i++) {
      var piece = state.board[i];
      if (piece !== "." && colorOf(piece) !== side && counts[piece.toLowerCase()] !== undefined) {
        counts[piece.toLowerCase()]++;
      }
    }
    var list = [];
    var points = 0;
    ["q", "r", "b", "n", "p"].forEach(function (kind) {
      var missing = Math.max(0, START_COUNT[kind] - counts[kind]);
      points += missing * VALUE[kind];
      for (var n = 0; n < missing; n++) list.push(side === "w" ? kind : kind.toUpperCase());
    });
    return { list: list, points: points };
  }
  function fillBar(prefix, side, lead) {
    $(prefix + "-avatar").className = "avatar " + side;
    $(prefix + "-name").textContent = (state.players[side] || "") + (state.you === side ? " (تو)" : "");
    var box = $(prefix + "-taken");
    box.textContent = "";
    var taken = takenBy(side);
    taken.list.forEach(function (piece) {
      var img = document.createElement("img");
      img.src = pieceUrl(piece);
      img.alt = "";
      box.appendChild(img);
    });
    if (lead > 0) {
      var plus = document.createElement("span");
      plus.textContent = "+" + fa(lead);
      box.appendChild(plus);
    }
    var bar = $("bar-" + prefix);
    bar.classList.toggle("active", !state.over && state.turn === side);
  }
  function bars() {
    var bottom = flipped ? "b" : "w";
    var top = flipped ? "w" : "b";
    var diff = takenBy(bottom).points - takenBy(top).points;
    fillBar("bottom", bottom, diff);
    fillBar("top", top, -diff);
  }

  function secondsLeft() {
    if (!state || state.over) return 0;
    return Math.max(0, state.seconds_left - Math.floor((Date.now() - receivedAt) / 1000));
  }
  function clocks() {
    if (!state) return;
    var left = secondsLeft();
    var text = fa(Math.floor(left / 60)) + ":" + fa(String(left % 60).padStart(2, "0"));
    var full = fa(Math.floor(state.move_seconds / 60)) + ":" + fa(String(state.move_seconds % 60).padStart(2, "0"));
    var bottomSide = flipped ? "b" : "w";
    [["bottom", bottomSide], ["top", bottomSide === "w" ? "b" : "w"]].forEach(function (pair) {
      var el = $(pair[0] + "-clock");
      var running = !state.over && state.turn === pair[1];
      el.textContent = running ? text : full;
      el.classList.toggle("low", running && left <= 10);
    });
  }

  function status() {
    var el = $("status");
    el.className = "";
    if (state.cancelled) { el.textContent = "این مسابقه لغو شده است."; el.className = "alert"; return; }
    if (state.over) { el.textContent = resultTitle(); return; }
    var mine = state.you === state.turn;
    var text = state.you ? (mine ? "نوبت توست" : "نوبت حریف است") : "نوبت " + (state.players[state.turn] || "");
    if (state.check !== null) { text = "کیش! " + text; el.className = "alert"; }
    else if (mine) el.className = "mine";
    if (state.draw_offer === "opponent") text += " · حریف پیشنهاد مساوی داده است";
    if (state.draw_offer === "you") text += " · پیشنهاد مساوی فرستاده شد";
    el.textContent = text;
  }

  function buttons() {
    var playing = !!state.you && !state.over && !state.cancelled;
    $("actions").classList.toggle("hidden", !state.you);
    $("draw-btn").disabled = !playing || state.draw_offer === "you";
    $("resign-btn").disabled = !playing;
    $("draw-btn").textContent = state.draw_offer === "opponent" ? "🤝 قبول مساوی" : "🤝 پیشنهاد مساوی";
    $("draw-btn").classList.toggle("offer", playing && state.draw_offer === "opponent");
  }

  // ------------------------------------------------------------------ نتیجه
  function resultTitle() {
    var over = state.over;
    if (!over.side) return "🤝 مساوی";
    if (!state.you) return "🏆 " + (state.players[over.side] || "") + " برد";
    return state.you === over.side ? "🏆 بردی!" : "باختی";
  }
  function showResult() {
    if (resultShown) return;
    resultShown = true;
    var over = state.over;
    var won = !!state.you && state.you === over.side;
    $("result-icon").textContent = !over.side ? "🤝" : (!state.you || won ? "🏆" : "😔");
    $("result-title").textContent = resultTitle();
    $("result-reason").textContent = REASONS[over.reason] || "";
    $("result").classList.remove("hidden");
    haptic(won || !over.side ? "success" : "error");
  }

  // ------------------------------------------------------------------ دریافت وضعیت
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
    var previous = state;
    state = response.state;
    receivedAt = Date.now();
    var shouldFlip = state.you === "b";
    if (!squares.length || shouldFlip !== flipped) {
      flipped = shouldFlip;
      buildBoard();
    }
    selected = null;
    var arrived = state.last && (!previous || previous.version !== state.version) ? state.last[1] : null;
    paint(arrived);
    bars();
    clocks();
    status();
    buttons();
    if (previous && previous.plies !== state.plies && state.you === state.turn) haptic("medium");
    if (state.over) showResult();
    return true;
  }

  function refresh() {
    if (busy || document.hidden) return;
    api("board/state", state ? { version: state.version } : {}).then(function (response) {
      if (busy) return;
      if (!state && !response.ok) { fail(errorText(response.error)); return; }
      if (response.ok) apply(response);
    });
  }

  // ------------------------------------------------------------------ حرکت
  function send(src, dst, promo) {
    busy = true;
    api("board/move", { src: src, dst: dst, promo: promo || "" }).then(function (response) {
      busy = false;
      if (!apply(response)) { selected = null; paint(null); }
    });
  }
  function askPromotion(src, dst) {
    var box = $("promo");
    var white = state.you === "w";
    box.textContent = "";
    ["q", "r", "b", "n"].forEach(function (kind) {
      var button = document.createElement("button");
      button.type = "button";
      var img = document.createElement("img");
      img.src = pieceUrl(white ? kind.toUpperCase() : kind);
      img.alt = kind;
      button.appendChild(img);
      button.addEventListener("click", function () {
        box.classList.add("hidden");
        send(src, dst, kind);
      });
      box.appendChild(button);
    });
    box.classList.remove("hidden");
  }
  function onSquare(index) {
    if (!state || busy || state.over || state.cancelled || !state.you || state.you !== state.turn) return;
    if (selected !== null && targetsOf(selected).indexOf(index) !== -1) {
      var piece = state.board[selected];
      var lastRank = Math.floor(index / 8) === (state.you === "w" ? 7 : 0);
      haptic("light");
      if (piece.toLowerCase() === "p" && lastRank) askPromotion(selected, index);
      else send(selected, index, "");
      return;
    }
    if (colorOf(state.board[index]) === state.you && targetsOf(index).length) {
      selected = selected === index ? null : index;
      haptic("light");
    } else {
      selected = null;
    }
    paint(null);
  }

  function act(kind) {
    if (busy) return;
    busy = true;
    api("board/action", { action: kind }).then(function (response) {
      busy = false;
      apply(response);
    });
  }
  function confirmThen(text, run) {
    if (tg && tg.showConfirm) {
      try { tg.showConfirm(text, function (ok) { if (ok) run(); }); return; } catch (e) { /* قدیمی */ }
    }
    if (window.confirm(text)) run();
  }

  function fail(text) {
    $("loading-text").textContent = text;
    document.querySelector("#loading .spinner").classList.add("hidden");
  }

  // ------------------------------------------------------------------ شروع
  $("board").addEventListener("click", function (event) {
    var cell = event.target.closest(".sq");
    if (cell) onSquare(Number(cell.dataset.i));
  });
  $("resign-btn").addEventListener("click", function () {
    confirmThen("مطمئنی می‌خواهی تسلیم شوی؟", function () { act("resign"); });
  });
  $("draw-btn").addEventListener("click", function () { act("draw"); });
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

  if (!initData) {
    fail(errorText("auth_missing"));
    return;
  }
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
