/* صفحه‌ی شطرنج مینی‌اپ. وضعیت بازی همیشه از سرور می‌آید و حرکت‌ها همان‌جا اعتبارسنجی می‌شوند؛
   این فایل تخته را می‌کشد (کشیدن یا دو لمس، با حرکت نرم مهره)، ساعت شطرنج را تیک‌تاک‌کنان نشان می‌دهد،
   فهرست حرکت‌ها را می‌نویسد و صدای حرکت، زدن مهره و کیش را پخش می‌کند. */
(function () {
  "use strict";

  var BOOT = window.BOARD_BOOT;
  var tg = window.Telegram && window.Telegram.WebApp ? window.Telegram.WebApp : null;
  var query = new URLSearchParams(location.search);
  var initData = tg && tg.initData ? tg.initData : "";
  if (!initData && BOOT.devAuth && query.get("dev_user")) initData = "dev:" + query.get("dev_user");

  var START_COUNT = { p: 8, n: 2, b: 2, r: 2, q: 1 };
  var VALUE = { p: 1, n: 3, b: 3, r: 5, q: 9 };
  var FIGURINES = { K: "♔", Q: "♕", R: "♖", B: "♗", N: "♘" };
  var THEMES = ["wood", "green", "blue", "violet"];
  var THEME_NAMES = { wood: "چوبی", green: "سبز مسابقه", blue: "آبی", violet: "بنفش" };
  var LEVEL_NAMES = { easy: "آسان", medium: "متوسط", hard: "سخت" };
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
    timeout_draw: "پایان وقت، ولی حریف فقط شاه داشت و نمی‌توانست مات کند",
    stalemate: "پات (حرکت مجاز نمانده)",
    insufficient: "مهره‌ی کافی برای مات نمانده",
    fifty: "قانون ۵۰ حرکت",
    repetition: "تکرار سه‌باره‌ی وضعیت",
    agreed: "با توافق دو بازیکن",
    limit: "سقف تعداد حرکت‌ها",
  };

  var state = null; // آخرین وضعیت سرور (یا تصویر خوش‌بینانه‌ی حرکت خودمان تا جواب سرور برسد)
  var selected = null; // خانه‌ی مهره‌ی انتخاب‌شده
  var busy = false; // در حال فرستادن حرکت
  var flipped = false; // تخته از سمت سیاه دیده می‌شود
  var userFlipped = false; // بازیکن خودش تخته را چرخانده
  var receivedAt = 0; // لحظه‌ی رسیدن ساعت‌ها (performance.now)
  var clockBase = null; // میلی‌ثانیه‌ی باقی‌مانده‌ی هر طرف در receivedAt
  var leftBase = 0; // میلی‌ثانیه تا پایان مهلت نوبت فعلی در receivedAt
  var optimistic = null; // حرکت خودمان که پیش از جواب سرور نشان داده شده
  var resultShown = false;
  var lowWarned = false;
  var squares = [];
  var drag = null;
  var pollTimer = null;

  function $(id) { return document.getElementById(id); }
  function fa(value) {
    return String(value).replace(/\d/g, function (d) { return "۰۱۲۳۴۵۶۷۸۹"[d]; });
  }
  function other(side) { return side === "w" ? "b" : "w"; }
  function now() { return window.performance && performance.now ? performance.now() : Date.now(); }
  function load(key) { try { return window.localStorage.getItem(key); } catch (e) { return null; } }
  function save(key, value) { try { window.localStorage.setItem(key, value); } catch (e) { /* حالت خصوصی */ } }
  function haptic(kind) {
    try {
      if (!tg || !tg.HapticFeedback) return;
      if (kind === "error" || kind === "success" || kind === "warning") tg.HapticFeedback.notificationOccurred(kind);
      else tg.HapticFeedback.impactOccurred(kind || "light");
    } catch (e) { /* نسخه‌های قدیمی */ }
  }
  function errorText(code) {
    if (code && code.indexOf("auth_") === 0) return "این صفحه باید از داخل تلگرام باز شود.";
    return ERRORS[code] || "مشکلی پیش آمد. دوباره امتحان کن.";
  }
  var toastTimer = null;
  function toast(text, info) {
    var el = $("toast");
    el.textContent = text;
    el.classList.toggle("info", !!info);
    el.classList.remove("hidden");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { el.classList.add("hidden"); }, 2600);
  }

  var PRACTICE = !!BOOT.practice;
  var PATHS = PRACTICE
    ? { "board/state": "practice/chess/state", "board/move": "practice/chess/move", "board/action": "practice/chess/action" }
    : {};
  function api(path, body) {
    body = body || {};
    body.initData = initData;
    if (PRACTICE) {
      path = PATHS[path] || path;
      if (state && state.game_id) body.game_id = state.game_id;
    } else {
      body.match_token = BOOT.token;
    }
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
    if (!piece || piece === ".") return null;
    return piece === piece.toUpperCase() ? "w" : "b";
  }
  function figurine(san) {
    return san.replace(/[KQRBN]/g, function (letter) { return FIGURINES[letter]; });
  }
  // نام کنترل زمانی با همان مرزهای سایت‌های شطرنج: زمان تخمینی = پایه + ۴۰ × افزایش
  function controlLabel(base, inc) {
    var estimate = base + 40 * inc;
    var kind = estimate < 180 ? "🚀 بولت" : estimate < 480 ? "⚡️ برق‌آسا" : estimate < 1500 ? "⏱ سریع" : "🏛 کلاسیک";
    return kind + " \u200e" + fa(Math.round(base / 60)) + "+" + fa(inc); // بدون نشانه‌ی چپ‌به‌راست «۳+۲» برعکس می‌شود
  }

  // ------------------------------------------------------------------ صدا (common/sfx.js)
  function sound(kind) { if (window.SFX) window.SFX.play(kind); }
  function unlockAudio() { if (window.SFX) window.SFX.unlock(); }
  function soundButton() { $("sound-btn").textContent = window.SFX && window.SFX.isMuted() ? "🔇" : "🔊"; }

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

  function paint() {
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
      cell.classList.remove("arrived");
    }
  }
  function isEnPassant(src, dst) {
    if (src === null) return false;
    return state.board[src].toLowerCase() === "p" && src % 8 !== dst % 8 && state.board[dst] === ".";
  }

  // مهره‌ی رسیده به مقصد از خانه‌ی مبدأ سُر می‌خورد (قلعه: رخ هم)
  function slide(src, dst) {
    var from = squares[src], to = squares[dst];
    var img = to && to.querySelector("img");
    if (!from || !img) return;
    var a = from.getBoundingClientRect(), b = to.getBoundingClientRect();
    img.style.transition = "none";
    img.style.transform = "translate(" + (a.left - b.left) + "px," + (a.top - b.top) + "px)";
    img.getBoundingClientRect();
    img.style.transition = "";
    img.classList.add("sliding");
    img.style.transform = "";
    setTimeout(function () { img.classList.remove("sliding"); }, 260);
  }
  function slideMove(board, src, dst) {
    slide(src, dst);
    var piece = board[dst];
    if (piece && piece.toLowerCase() === "k" && Math.abs(dst - src) === 2) {
      slide(dst > src ? src + 3 : src - 4, dst > src ? src + 1 : src - 1);
    }
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
    var taken = takenBy(side);
    var key = taken.list.join("") + ":" + lead;
    if (box.dataset.key !== key) {
      box.dataset.key = key;
      box.textContent = "";
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
    }
    $("bar-" + prefix).classList.toggle("active", !state.over && state.turn === side);
  }
  function bars() {
    var bottom = flipped ? "b" : "w";
    var top = other(bottom);
    var diff = takenBy(bottom).points - takenBy(top).points;
    fillBar("bottom", bottom, diff);
    fillBar("top", top, -diff);
  }

  // ------------------------------------------------------------------ ساعت شطرنج
  function pad(n) { return n < 10 ? "0" + n : String(n); }
  function clockText(ms) {
    ms = Math.max(0, ms);
    if (ms <= 0) return fa("0:00");
    // زیر ۱۰ ثانیه دهم ثانیه هم نشان داده می‌شود (با ممیز فارسی «٫»)
    if (ms < 10000) return fa("0:0" + Math.floor(ms / 1000)) + "٫" + fa(Math.floor((ms % 1000) / 100));
    var total = Math.floor(ms / 1000);
    var hours = Math.floor(total / 3600), minutes = Math.floor((total % 3600) / 60), seconds = total % 60;
    return fa(hours ? hours + ":" + pad(minutes) + ":" + pad(seconds) : minutes + ":" + pad(seconds));
  }
  function currentClocks() {
    if (!state || !clockBase) return null;
    var result = { w: clockBase.w, b: clockBase.b };
    if (state.running && !state.over) result[state.running] = Math.max(0, clockBase[state.running] - (now() - receivedAt));
    return result;
  }
  function windowLeft() { return Math.max(0, leftBase - (now() - receivedAt)); }
  function lowLimit() { return Math.min(30000, (state.base || 0) * 100); } // ۱۰٪ وقت اولیه، حداکثر ۳۰ ثانیه
  function clockBar(el) {
    var bar = el.querySelector(".clock-bar");
    if (!bar) {
      bar = document.createElement("i");
      bar.className = "clock-bar";
      el.appendChild(bar);
    }
    return bar;
  }
  function renderClocks() {
    if (!state) return;
    var clocks = currentClocks();
    var bottom = flipped ? "b" : "w";
    [["bottom", bottom], ["top", other(bottom)]].forEach(function (pair) {
      var el = $(pair[0] + "-clock");
      if (!clocks) { el.classList.add("hidden"); return; }
      el.classList.remove("hidden");
      var ms = clocks[pair[1]];
      var label = el.querySelector(".clock-text") || el;
      var text = clockText(ms);
      if (label.textContent !== text) label.textContent = text;
      var running = state.running === pair[1] && !state.over;
      el.classList.toggle("low", running && ms < lowLimit());
      el.classList.toggle("paused", !!state.first_move && !state.over && state.turn === pair[1]);
      var timeUp = state.over && ms <= 0 && /^timeout/.test(state.over.reason);
      el.classList.toggle("flagged", !!timeUp);
      if (state.base) clockBar(el).style.transform = "scaleX(" + Math.min(1, ms / (state.base * 1000)).toFixed(3) + ")";
    });
    if (clocks && state.you && state.running === state.you && clocks[state.you] < 10000 && !lowWarned) {
      lowWarned = true;
      sound("low");
      haptic("warning");
    }
    if (state.first_move && !state.over) status();
  }

  function status() {
    var el = $("status");
    el.className = "";
    if (state.cancelled) { el.textContent = "این مسابقه لغو شده است."; el.className = "alert"; return; }
    if (state.over) { el.textContent = resultTitle(); return; }
    var mine = state.you === state.turn;
    var name = state.players[state.turn] || "";
    var text = state.you ? (mine ? "نوبت توست" : "نوبت حریف است") : "نوبت " + name;
    if (PRACTICE && !mine) text = "کامپیوتر در حال فکر کردن…";
    if (state.first_move && state.clock) {
      var seconds = Math.ceil(windowLeft() / 1000);
      text = (mine ? "اولین حرکتت را بزن" : "منتظر اولین حرکت " + (state.you ? "حریف" : name)) + " (" + fa(seconds) + " ثانیه)";
      el.className = seconds <= 15 ? "warn" : mine ? "mine" : "";
    } else if (mine) {
      el.className = "mine";
    }
    if (state.check !== null) { text = "کیش! " + text; el.className = "alert"; }
    if (state.draw_offer === "opponent") text += " · حریف پیشنهاد مساوی داده است";
    if (state.draw_offer === "you") text += " · پیشنهاد مساوی فرستاده شد";
    if (el.textContent !== text) el.textContent = text;
  }

  function buttons() {
    var playing = !!state.you && !state.over && !state.cancelled;
    $("actions").classList.toggle("hidden", !state.you);
    $("draw-btn").disabled = !playing || state.draw_offer === "you";
    $("resign-btn").disabled = !playing;
    $("draw-btn").textContent = state.draw_offer === "opponent" ? "🤝 قبول مساوی" : "🤝 پیشنهاد مساوی";
    $("draw-btn").classList.toggle("offer", playing && state.draw_offer === "opponent");
  }

  // ------------------------------------------------------------------ فهرست حرکت‌ها و عنوان
  function renderMoves() {
    var box = $("moves");
    var san = state.san || [];
    if (box.dataset.count === String(san.length)) return;
    box.dataset.count = String(san.length);
    box.textContent = "";
    if (!san.length) {
      var empty = document.createElement("span");
      empty.className = "empty";
      empty.textContent = "حرکت‌ها این‌جا نوشته می‌شوند";
      box.appendChild(empty);
      return;
    }
    for (var i = 0; i < san.length; i++) {
      if (i % 2 === 0) {
        var number = document.createElement("span");
        number.className = "num";
        number.textContent = fa(i / 2 + 1) + ".";
        box.appendChild(number);
      }
      var move = document.createElement("span");
      move.className = "mv" + (i === san.length - 1 ? " cur" : "");
      move.textContent = figurine(san[i]);
      box.appendChild(move);
    }
    box.scrollLeft = box.scrollWidth;
  }
  function heading() {
    var chip = $("control-chip");
    if (PRACTICE) {
      $("title").textContent = "شطرنج با کامپیوتر";
      chip.textContent = "سطح " + (LEVEL_NAMES[state.level] || "");
    } else {
      $("title").textContent = state.you ? "شطرنج" : "شطرنج · تماشا";
      chip.textContent = state.base ? controlLabel(state.base, state.inc) : "";
    }
    chip.classList.toggle("hidden", !chip.textContent);
  }

  // ------------------------------------------------------------------ نتیجه
  function resultTitle() {
    var over = state.over;
    if (!over.side) return "🤝 مساوی";
    if (!state.you) return "🏆 " + (state.players[over.side] || "") + " برد";
    return state.you === over.side ? "🏆 بردی!" : "باختی";
  }
  function confetti() {
    var box = $("confetti");
    var colors = ["#ffc857", "#6ee7ff", "#a78bfa", "#34d399", "#ff5c7a", "#ffffff"];
    box.textContent = "";
    for (var i = 0; i < 46; i++) {
      var bit = document.createElement("i");
      bit.style.left = Math.random() * 100 + "%";
      bit.style.background = colors[i % colors.length];
      bit.style.animationDuration = (1.8 + Math.random() * 1.6).toFixed(2) + "s";
      bit.style.animationDelay = (Math.random() * 0.5).toFixed(2) + "s";
      bit.style.transform = "rotate(" + Math.floor(Math.random() * 360) + "deg)";
      box.appendChild(bit);
    }
    setTimeout(function () { box.textContent = ""; }, 4200);
  }
  function showResult() {
    if (resultShown) return;
    resultShown = true;
    var over = state.over;
    var won = !!state.you && state.you === over.side;
    var lost = !!state.you && !!over.side && state.you !== over.side;
    var icon = $("result-icon");
    icon.textContent = "";
    icon.className = "result-icon" + (won ? " won" : "");
    var kings = over.side ? [over.side === "w" ? "K" : "k"] : ["K", "k"];
    var holder = icon;
    if (kings.length > 1) {
      holder = document.createElement("span");
      holder.className = "pair";
      icon.appendChild(holder);
    }
    kings.forEach(function (piece) {
      var img = document.createElement("img");
      img.src = pieceUrl(piece);
      img.alt = "";
      holder.appendChild(img);
    });
    $("result-title").textContent = resultTitle();
    $("result-reason").textContent = REASONS[over.reason] || "";
    var clocks = currentClocks();
    $("result-clocks").classList.toggle("hidden", !clocks);
    if (clocks) $("result-clocks").textContent = "⚪️ " + clockText(clocks.w) + "     ⚫️ " + clockText(clocks.b);
    sound(won ? "win" : lost ? "lose" : over.side ? "move" : "draw");
    haptic(won || !over.side ? "success" : "error");
    // آخرین حرکت اول دیده شود
    setTimeout(function () {
      $("result").classList.remove("hidden");
      if (won) confetti();
    }, 700);
  }

  // ------------------------------------------------------------------ دریافت وضعیت
  function moveSound(previous, next) {
    if (next.check !== null) { sound("check"); return; }
    var before = previous.board.replace(/\./g, "").length;
    var after = next.board.replace(/\./g, "").length;
    sound(after < before ? "capture" : "move");
  }
  function apply(response) {
    if (!response.ok) {
      toast(errorText(response.error));
      haptic("error");
      return false;
    }
    if (response.changed === false) {
      // فقط هم‌گام کردن ساعت طرفی که نوبت دارد با سرور
      receivedAt = now();
      leftBase = response.left_ms !== undefined ? response.left_ms : response.seconds_left * 1000;
      if (clockBase && state.running) {
        clockBase[other(state.running)] = currentClocksAt(other(state.running));
        clockBase[state.running] = leftBase;
      }
      renderClocks();
      return true;
    }
    var previous = state;
    state = response.state;
    receivedAt = now();
    clockBase = state.clock ? { w: state.clock.w, b: state.clock.b } : null;
    leftBase = state.left_ms !== undefined ? state.left_ms : state.seconds_left * 1000;
    if (state.running !== state.you) lowWarned = false;
    var shouldFlip = (state.you === "b") !== userFlipped;
    if (!squares.length || shouldFlip !== flipped) {
      flipped = shouldFlip;
      buildBoard();
    }
    // جواب سرور به حرکت خود ما: همان حرکتی است که از قبل نشان داده شده؛ دوباره سُر نمی‌خورد
    var echo = !!optimistic && !!state.last && state.plies === optimistic.plies &&
      state.last[0] === optimistic.src && state.last[1] === optimistic.dst;
    optimistic = null;
    var moved = !!previous && !!state.last && state.plies !== previous.plies;
    selected = null;
    paint();
    if (moved && !echo) {
      slideMove(state.board, state.last[0], state.last[1]);
      moveSound(previous, state);
    } else if (echo && state.check !== null) {
      sound("check");
    }
    heading();
    bars();
    renderMoves();
    renderClocks();
    status();
    buttons();
    if (previous && previous.plies !== state.plies && state.you === state.turn && !state.over) haptic("medium");
    if (state.over) showResult();
    return true;
  }
  function currentClocksAt(side) {
    var clocks = currentClocks();
    return clocks ? clocks[side] : 0;
  }

  // هر چند وقت یک بار وضعیت تازه: وقتی منتظر حرکت حریفیم زودتر
  function pollDelay() {
    if (!state || state.over || state.cancelled) return 5000;
    if (state.you && state.turn !== state.you) return 800;
    return state.you ? 1500 : 1200;
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
  function refreshNow() {
    if (busy || !state || PRACTICE) return;
    api("board/state", { version: state.version }).then(function (response) {
      if (!busy && response.ok) apply(response);
    });
  }

  // ------------------------------------------------------------------ حرکت
  function localMove(board, src, dst, promo) {
    var cells = board.split("");
    var piece = cells[src];
    var kind = piece.toLowerCase();
    var white = piece === "P" || piece === piece.toUpperCase();
    if (kind === "p" && src % 8 !== dst % 8 && cells[dst] === ".") cells[dst + (white ? -8 : 8)] = "."; // آن‌پاسان
    if (kind === "k" && Math.abs(dst - src) === 2) {
      var rookFrom = dst > src ? src + 3 : src - 4, rookTo = dst > src ? src + 1 : src - 1;
      cells[rookTo] = cells[rookFrom];
      cells[rookFrom] = ".";
    }
    var lastRank = Math.floor(dst / 8) === 7 || Math.floor(dst / 8) === 0;
    if (kind === "p" && lastRank) piece = white ? (promo || "q").toUpperCase() : (promo || "q").toLowerCase();
    cells[dst] = piece;
    cells[src] = ".";
    return cells.join("");
  }
  function send(src, dst, promo, dragged) {
    busy = true;
    unlockAudio();
    var before = state;
    var board = localMove(before.board, src, dst, promo);
    var captured = board.replace(/\./g, "").length < before.board.replace(/\./g, "").length;
    // حرکت همان لحظه روی تخته دیده می‌شود؛ وضعیت قطعی (و جواب کامپیوتر در تمرین) با پاسخ سرور می‌آید
    state = Object.assign({}, before, {
      board: board, last: [src, dst], turn: other(before.turn), legal: {}, check: null, running: null,
      first_move: false, plies: before.plies + 1,
    });
    clockBase = currentClocks();
    receivedAt = now();
    optimistic = { plies: before.plies + 1, src: src, dst: dst };
    selected = null;
    paint();
    if (!dragged) slideMove(board, src, dst);
    sound(captured ? "capture" : "move");
    bars();
    status();
    var sentAt = now();
    api("board/move", { src: src, dst: dst, promo: promo || "" }).then(function (response) {
      var finish = function () {
        busy = false;
        if (!response.ok) {
          optimistic = null;
          state = before;
          clockBase = before.clock ? currentClocks() : null;
          paint();
          bars();
          status();
          toast(errorText(response.error));
          haptic("error");
          refreshNow();
          return;
        }
        apply(response);
      };
      // در تمرین جواب کامپیوتر هم‌زمان می‌رسد؛ کمی مکث تا حرکت خود بازیکن دیده شود
      var wait = PRACTICE ? Math.max(0, 420 - (now() - sentAt)) : 0;
      if (wait) setTimeout(finish, wait);
      else finish();
    });
  }
  function askPromotion(src, dst, dragged) {
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
        send(src, dst, kind, dragged);
      });
      box.appendChild(button);
    });
    box.classList.remove("hidden");
  }
  function canMove() {
    return !!state && !busy && !state.over && !state.cancelled && !!state.you && state.you === state.turn;
  }
  function tryMove(src, dst, dragged) {
    var piece = state.board[src];
    var lastRank = Math.floor(dst / 8) === (state.you === "w" ? 7 : 0);
    haptic("light");
    if (piece.toLowerCase() === "p" && lastRank) askPromotion(src, dst, dragged);
    else send(src, dst, "", dragged);
  }

  // ------------------------------------------------------------------ لمس و کشیدن مهره
  function squareAt(x, y) {
    var rect = $("board").getBoundingClientRect();
    var col = Math.floor(((x - rect.left) / rect.width) * 8);
    var row = Math.floor(((y - rect.top) / rect.height) * 8);
    if (col < 0 || col > 7 || row < 0 || row > 7) return null;
    var rank = flipped ? row : 7 - row;
    var file = flipped ? 7 - col : col;
    return rank * 8 + file;
  }
  function moveGhost(x, y) {
    var ghost = $("ghost");
    ghost.style.transform = "translate(" + (x - drag.size / 2) + "px," + (y - drag.size * 0.72) + "px) scale(1.12)";
    var over = squareAt(x, y);
    if (over !== drag.hover) {
      if (drag.hover !== null && squares[drag.hover]) squares[drag.hover].classList.remove("hover");
      drag.hover = targetsOf(drag.src).indexOf(over) !== -1 ? over : null;
      if (drag.hover !== null) squares[drag.hover].classList.add("hover");
    }
  }
  function endDrag() {
    if (!drag) return;
    $("ghost").classList.add("hidden");
    if (drag.hover !== null && squares[drag.hover]) squares[drag.hover].classList.remove("hover");
    if (squares[drag.src]) squares[drag.src].classList.remove("dragging");
    drag = null;
  }
  $("board").addEventListener("pointerdown", function (event) {
    unlockAudio();
    var cell = event.target.closest(".sq");
    if (!cell || !canMove() || event.button > 0) return;
    var index = Number(cell.dataset.i);
    if (selected !== null && targetsOf(selected).indexOf(index) !== -1) {
      tryMove(selected, index, false);
      return;
    }
    if (colorOf(state.board[index]) === state.you && targetsOf(index).length) {
      var again = selected === index;
      selected = index;
      paint();
      var rect = cell.getBoundingClientRect();
      drag = { src: index, x: event.clientX, y: event.clientY, moved: false, again: again, id: event.pointerId, size: rect.width, hover: null };
      try { $("board").setPointerCapture(event.pointerId); } catch (e) { /* مرورگر قدیمی */ }
      event.preventDefault();
      haptic("light");
    } else if (selected !== null) {
      selected = null;
      paint();
    }
  });
  $("board").addEventListener("pointermove", function (event) {
    if (!drag || event.pointerId !== drag.id) return;
    if (!drag.moved) {
      if (Math.abs(event.clientX - drag.x) + Math.abs(event.clientY - drag.y) < 7) return;
      drag.moved = true;
      var ghost = $("ghost");
      ghost.src = pieceUrl(state.board[drag.src]);
      ghost.style.width = ghost.style.height = drag.size + "px";
      ghost.classList.remove("hidden");
      squares[drag.src].classList.add("dragging");
    }
    moveGhost(event.clientX, event.clientY);
  });
  $("board").addEventListener("pointerup", function (event) {
    if (!drag || event.pointerId !== drag.id) return;
    var finished = drag;
    var target = finished.moved ? squareAt(event.clientX, event.clientY) : null;
    endDrag();
    if (finished.moved) {
      if (target !== null && canMove() && targetsOf(finished.src).indexOf(target) !== -1) tryMove(finished.src, target, true);
      else paint(); // مهره سر جایش برمی‌گردد و انتخاب‌شده می‌ماند
      return;
    }
    if (finished.again) { selected = null; paint(); } // لمس دوباره‌ی همان مهره یعنی لغو انتخاب
  });
  $("board").addEventListener("pointercancel", function () { endDrag(); if (state) paint(); });
  $("board").addEventListener("contextmenu", function (event) { event.preventDefault(); });

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

  // ------------------------------------------------------------------ دکمه‌ها
  $("resign-btn").addEventListener("click", function () {
    confirmThen("مطمئنی می‌خواهی تسلیم شوی؟", function () { act("resign"); });
  });
  $("draw-btn").addEventListener("click", function () { act("draw"); });
  $("flip-btn").addEventListener("click", function () {
    if (!state) return;
    userFlipped = !userFlipped;
    flipped = !flipped;
    buildBoard();
    paint();
    bars();
    renderClocks();
    haptic("light");
  });
  function applyTheme(name) {
    document.body.dataset.theme = THEMES.indexOf(name) === -1 ? "wood" : name;
  }
  $("theme-btn").addEventListener("click", function () {
    var next = THEMES[(THEMES.indexOf(document.body.dataset.theme) + 1) % THEMES.length];
    applyTheme(next);
    save("chess.theme", next);
    toast("رنگ صفحه: " + THEME_NAMES[next], true);
    haptic("light");
  });
  $("sound-btn").addEventListener("click", function () {
    if (!window.SFX) return;
    window.SFX.setMuted(!window.SFX.isMuted());
    soundButton();
    if (!window.SFX.isMuted()) setTimeout(function () { sound("move"); }, 60);
  });
  $("result-close").addEventListener("click", function () {
    if (PRACTICE) { $("result").classList.add("hidden"); chooseLevel(); return; }
    if (tg && tg.close) { try { tg.close(); return; } catch (e) { /* قدیمی */ } }
    $("result").classList.add("hidden");
  });
  function chooseLevel() {
    $("loading").classList.add("hidden");
    $("levels").classList.remove("hidden");
  }
  Array.prototype.forEach.call(document.querySelectorAll("#levels [data-level]"), function (button) {
    button.addEventListener("click", function () {
      if (busy) return;
      unlockAudio();
      busy = true;
      state = null;
      resultShown = false;
      api("practice/chess/new", { level: button.dataset.level }).then(function (response) {
        busy = false;
        if (!response.ok) { toast(errorText(response.error)); return; }
        $("levels").classList.add("hidden");
        $("game").classList.remove("hidden");
        squares = [];
        apply(response);
        sound("start");
      });
    });
  });
  $("result-view").addEventListener("click", function () { $("result").classList.add("hidden"); });

  // ------------------------------------------------------------------ شروع
  applyTheme(load("chess.theme") || "wood");
  soundButton();
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
  setInterval(renderClocks, 100);
  if (PRACTICE) {
    document.body.classList.add("practice");
    $("result-close").textContent = "بازی دوباره";
    api("board/state", {}).then(function (response) {
      if (!response.ok) { fail(errorText(response.error)); return; }
      if (response.none) { chooseLevel(); return; } // بازی نیمه‌کاره‌ای نیست
      apply(response);
      $("loading").classList.add("hidden");
      $("game").classList.remove("hidden");
    });
    return;
  }
  api("board/state", {}).then(function (response) {
    if (!response.ok) { fail(errorText(response.error)); return; }
    apply(response);
    $("loading").classList.add("hidden");
    $("game").classList.remove("hidden");
    loop();
    document.addEventListener("visibilitychange", function () { if (!document.hidden) refreshNow(); });
  });
})();
