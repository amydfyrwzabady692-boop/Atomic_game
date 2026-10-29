/* میز پوکر مینی‌اپ. همه‌ی قوانین و کارت‌ها در سرور است؛ سرور فقط کارت‌های خود بازیکن را می‌فرستد.
   این فایل میز را مثل اپ‌های پوکر موبایل می‌کشد: صندلی‌ها دور میز بیضی، ستون ژتون شرط جلوی هر نفر، دکمه‌ی
   دیلر، حلقه‌ی زمان نوبت، کارت‌هایی که پخش می‌شوند و برمی‌گردند، پات‌های جانبی، و در آل‌این باز شدن
   کارت‌های وسط یکی‌یکی. وقتی نوبت حریف است می‌شود حرکت از پیش (چک/فولد، کال، کال هر مبلغ) انتخاب کرد که
   به محض رسیدن نوبت انجام می‌شود. تاریخچه‌ی دست و جدول رتبه‌ی دست‌ها هم از دکمه‌های بالا باز می‌شود. */
(function () {
  "use strict";

  var BOOT = window.BOARD_BOOT;
  var tg = window.Telegram && window.Telegram.WebApp ? window.Telegram.WebApp : null;
  var query = new URLSearchParams(location.search);
  var initData = tg && tg.initData ? tg.initData : "";
  if (!initData && BOOT.devAuth && query.get("dev_user")) initData = "dev:" + query.get("dev_user");

  var SUITS = { s: "♠", h: "♥", d: "♦", c: "♣" };
  var STREETS = { preflop: "قبل از فلاپ", flop: "فلاپ", turn: "ترن", river: "ریور" };
  var ACTIONS = { fold: "فولد", check: "چک", call: "کال", raise: "رِیز", allin: "آل‌این", leave: "ترک میز", sb: "بلایند کوچک", bb: "بلایند بزرگ" };
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
  var AVATARS = [["#5662e0", "#262b78"], ["#f0617f", "#8f1d3a"], ["#2fbf8f", "#0f5c45"], ["#f5a524", "#8a5200"],
    ["#a78bfa", "#4c2a99"], ["#38bdf8", "#0b5d8a"], ["#f472b6", "#86205a"], ["#94a3b8", "#334155"]];
  // جدول رتبه‌ی دست‌ها: نام (همان نام‌های سرور)، نمونه، توضیح
  var RANKINGS = [
    ["رویال فلاش", ["As", "Ks", "Qs", "Js", "Ts"], "۱۰ تا آس، پشت سر هم و هم‌خال"],
    ["استریت فلاش", ["9h", "8h", "7h", "6h", "5h"], "پنج کارت پشت سر هم و هم‌خال"],
    ["چهارتایی", ["Qc", "Qd", "Qh", "Qs", "5d"], "چهار کارت هم‌ارزش"],
    ["فول هاوس", ["Ks", "Kh", "Kd", "8c", "8s"], "یک سه‌تایی و یک جفت"],
    ["فلاش", ["Ad", "Jd", "8d", "6d", "2d"], "پنج کارت هم‌خال"],
    ["استریت", ["Tc", "9d", "8s", "7h", "6c"], "پنج کارت پشت سر هم"],
    ["سه‌تایی", ["7s", "7h", "7d", "Kc", "3s"], "سه کارت هم‌ارزش"],
    ["دو جفت", ["Jh", "Jc", "4s", "4d", "Ac"], "دو جفت جدا"],
    ["یک جفت", ["Ts", "Th", "Kd", "7c", "2h"], "دو کارت هم‌ارزش"],
    ["کارت بالا", ["Ac", "Qd", "9s", "6h", "3c"], "هیچ‌کدام؛ کارت بالاتر می‌برد"],
  ];
  var RANK_PREFIXES = ["رویال فلاش", "استریت فلاش", "چهارتایی", "فول هاوس", "فلاش", "استریت", "سه‌تایی", "دو جفت", "جفت", "کارت بالا"];
  var RUNOUT_MS = 1100; // فاصله‌ی باز شدن هر خیابان در آل‌این (سرور وقفه را به همین اندازه بلند می‌کند)

  var real = null; // آخرین وضعیت سرور
  var state = null; // آنچه کشیده شده: همان وضعیت سرور، یا در آل‌این تصویری که هنوز همه‌ی کارت‌ها را نشان نمی‌دهد
  var stage = null; // باز شدن مرحله‌ای کارت‌ها در آل‌این: {hand, shown, steps, timer}
  var pre = null; // حرکت از پیش: {kind, amount, hand, street}
  var busy = false;
  var receivedAt = 0;
  var leftBase = 0;
  var resultShown = false;
  var raiseTo = 0;
  var pollTimer = null;
  var lastSaid = "";
  var lowWarned = false;
  var historyOpen = false;

  function $(id) { return document.getElementById(id); }
  function el(tag, cls, text) {
    var node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined) node.textContent = text;
    return node;
  }
  function fa(value) {
    return String(value).replace(/\d/g, function (d) { return "۰۱۲۳۴۵۶۷۸۹"[d]; });
  }
  function money(value) { return fa(Number(value || 0).toLocaleString("en-US")).replace(/,/g, "٬"); }
  function plus(value) { return "\u200e+" + money(value); }
  function now() { return window.performance && performance.now ? performance.now() : Date.now(); }
  function sound(kind) { if (window.SFX) window.SFX.play(kind); }
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
  function toast(text) {
    var box = $("toast");
    box.textContent = text;
    box.classList.remove("hidden");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { box.classList.add("hidden"); }, 2600);
  }
  function confirmThen(text, run) {
    if (tg && tg.showConfirm) {
      try { tg.showConfirm(text, function (ok) { if (ok) run(); }); return; } catch (e) { /* قدیمی */ }
    }
    if (window.confirm(text)) run();
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
  function isMe(seat) { return state.you !== null && state.you !== undefined && state.you === seat; }
  function mine() { return state.you !== null && state.you !== undefined ? state.seats[state.you] : null; }
  function name(seat) { return state.players["s" + seat] || ""; }
  function badge(seat) {
    var profile = (state.profiles || {})["s" + seat];
    return profile && profile.emoji ? profile.emoji + " " : "";
  }
  function initial(seat) { return (name(seat).trim()[0] || "؟").toUpperCase(); }
  function myTurn() {
    var me = mine();
    return !!me && !stage && !state.over && !state.cancelled && state.phase === "betting" && state.to_act === me.seat;
  }

  // ------------------------------------------------------------------ کارت و ژتون
  function cardEl(code, extra) {
    var card = el("span", "pcard" + (extra ? " " + extra : "")); // «card» نام پنجره‌های chess.css است
    if (code === null) { card.classList.add("slot"); return card; }
    if (!code) { card.classList.add("back"); return card; }
    var suit = SUITS[code[1]];
    if (code[1] === "h" || code[1] === "d") card.classList.add("red");
    var index = el("span", "idx");
    index.appendChild(el("b", "", code[0] === "T" ? "10" : code[0]));
    index.appendChild(el("i", "", suit));
    card.appendChild(index);
    card.appendChild(el("span", "pip", suit));
    return card;
  }
  function miniCards(codes) {
    var box = el("span", "minis");
    codes.forEach(function (code) { box.appendChild(cardEl(code, "mini")); });
    return box;
  }
  function winning() {
    var set = {};
    if (!state.result || state.phase !== "pause") return set;
    state.result.winners.forEach(function (w) { (w.cards || []).forEach(function (c) { set[c] = true; }); });
    return set;
  }
  function cardClass(code, win, fresh) {
    var showdown = state.phase === "pause" && state.result && state.result.winners.some(function (w) { return w.cards; });
    var classes = [];
    if (code && win[code]) classes.push("win");
    else if (code && showdown) classes.push("dim");
    if (fresh) classes.push("deal");
    return classes.join(" ");
  }
  function chipColor(amount) { return amount >= state.bb * 25 ? "gold" : amount >= state.bb * 10 ? "black" : amount >= state.bb * 3 ? "blue" : ""; }
  // ستونی از ژتون‌ها: هرچه شرط بزرگ‌تر، ستون بلندتر و ژتون‌های گران‌تر
  function chipStack(amount) {
    var count = amount >= state.bb * 25 ? 4 : amount >= state.bb * 8 ? 3 : amount >= state.bb * 3 ? 2 : 1;
    var colors = ["", "blue", "black", "gold"];
    var top = Math.max(0, colors.indexOf(chipColor(amount)));
    var stack = el("span", "stack");
    stack.style.setProperty("--n", count);
    for (var i = 0; i < count; i++) {
      var chip = el("i", "chip-ico " + colors[Math.max(0, top - (count - 1 - i))]);
      chip.style.setProperty("--i", i);
      stack.appendChild(chip);
    }
    return stack;
  }

  // ------------------------------------------------------------------ هندسه‌ی میز
  // صندلی‌ها روی بیضی، ساعت‌گرد از پایین (جای خود بیننده)؛ زاویه با محور x و y رو به پایین
  function relative(seat) {
    var n = state.seats.length;
    var base = mine() ? state.you : 0;
    return (seat - base + n) % n;
  }
  function angle(seat) { return Math.PI / 2 + (relative(seat) * 2 * Math.PI) / state.seats.length; }
  function point(seat, rx, ry, shift) {
    var a = angle(seat) + (shift || 0);
    return { x: 50 + rx * Math.cos(a), y: 50 + ry * Math.sin(a) };
  }
  function place(node, p) {
    node.style.left = p.x.toFixed(2) + "%";
    node.style.top = p.y.toFixed(2) + "%";
  }
  function betPoint(seat) { return isMe(seat) ? { x: 50, y: 74 } : point(seat, 24, 24); }

  // ------------------------------------------------------------------ رسم
  function drawLayer(previous) {
    var layer = $("layer");
    layer.textContent = "";
    var win = winning();
    var fresh = !previous || previous.hand !== state.hand;
    var winners = {};
    if (state.phase === "pause" && state.result) state.result.winners.forEach(function (w) { winners[w.seat] = w.amount; });
    var hands = (state.phase === "pause" && state.result && state.result.hands) || {};
    var said = state.last_action;
    var saidKey = said ? state.hand + ":" + state.version + ":" + said.seat + ":" + said.kind : "";
    var newSaid = said && saidKey !== lastSaid && said.kind !== "sb" && said.kind !== "bb";
    state.seats.forEach(function (s, index) {
      if (s.bet) {
        var bet = el("div", "bet");
        bet.appendChild(chipStack(s.bet));
        bet.appendChild(el("span", "", money(s.bet)));
        place(bet, betPoint(s.seat));
        layer.appendChild(bet);
      }
      if (s.dealer) {
        var button = el("div", "dealer-btn", "D");
        place(button, isMe(s.seat) ? { x: 26, y: 74 } : point(s.seat, 33, 33, 0.42));
        layer.appendChild(button);
      }
      if (isMe(s.seat)) return; // خود بیننده پایین میز جدا کشیده می‌شود
      var seat = el("div", "seat");
      if (state.to_act === s.seat && !state.over && state.phase === "betting") seat.classList.add("turn");
      if (s.folded && s.in_hand) seat.classList.add("folded");
      if (s.left) seat.classList.add("left");
      if (!s.in_hand && !state.over && !s.left) seat.classList.add("out");
      if (winners[s.seat]) seat.classList.add("winner");
      var revealed = s.cards.length && s.cards[0];
      if (revealed) seat.classList.add("revealed");
      // کارت‌هایی که همین الان رو شدند برمی‌گردند (نمایش دست‌ها در شودان یا آل‌این)
      var before = previous && previous.hand === state.hand ? previous.seats[s.seat] : null;
      var flipping = !!revealed && !!before && before.cards.length > 0 && !before.cards[0];
      var avatar = el("div", "ava");
      var colors = AVATARS[index % AVATARS.length];
      avatar.style.setProperty("--ava1", colors[0]);
      avatar.style.setProperty("--ava2", colors[1]);
      avatar.appendChild(el("span", "", initial(s.seat)));
      seat.appendChild(avatar);
      if (s.cards.length) {
        var hole = el("div", "hole");
        s.cards.forEach(function (code, i) {
          var card = cardEl(code, cardClass(code, win, fresh && !code) + (flipping ? " flip" : ""));
          if (fresh && !code) card.style.animationDelay = (0.08 * (relative(s.seat) + i * state.seats.length)).toFixed(2) + "s";
          if (flipping) card.style.animationDelay = (0.12 * i).toFixed(2) + "s";
          hole.appendChild(card);
        });
        seat.appendChild(hole);
      }
      var plate = el("div", "plate");
      plate.appendChild(el("b", "", badge(s.seat) + name(s.seat)));
      plate.appendChild(el("small", "", money(s.chips)));
      seat.appendChild(plate);
      var hand = hands[String(s.seat)];
      var tag = s.left ? ["ترک کرد", ""] : hand ? [hand, winners[s.seat] ? "hand best" : "hand"]
        : s.allin ? ["آل‌این", "allin"] : s.folded && s.in_hand ? ["فولد", "fold"] : null;
      if (tag) seat.appendChild(el("span", "tag " + tag[1], tag[0]));
      if (winners[s.seat]) seat.appendChild(el("span", "win-badge", plus(winners[s.seat])));
      else if (newSaid && said.seat === s.seat) seat.appendChild(el("span", "said " + said.kind, sayText(said)));
      var spot = point(s.seat, 40, 41);
      if (spot.y < 30) seat.classList.add("top");
      place(seat, spot);
      layer.appendChild(seat);
    });
    if (newSaid) lastSaid = saidKey;
    return newSaid ? said : null;
  }
  function sayText(action) {
    var text = ACTIONS[action.kind] || "";
    if (action.kind === "raise" || action.kind === "allin") return text + (action.to ? " " + money(action.to) : "");
    var paid = action.kind === "call" || action.kind === "sb" || action.kind === "bb";
    return text + (action.amount && paid ? " " + money(action.amount) : "");
  }

  function drawBoard(previous) {
    var box = $("board-cards");
    var known = previous && previous.hand === state.hand ? previous.board.length : 0;
    box.textContent = "";
    var win = winning();
    for (var i = 0; i < 5; i++) {
      var code = state.board[i];
      var card = cardEl(code === undefined ? null : code, cardClass(code, win, i >= known && !!code));
      if (i >= known && code) card.style.animationDelay = (0.12 * (i - known)).toFixed(2) + "s";
      box.appendChild(card);
    }
    var pot = $("pot");
    var total = state.pot;
    if (state.phase === "pause" && state.result) {
      // بعد از پایان دست پات به برنده‌ها رسیده؛ همان مبلغ نشان داده می‌شود
      total = state.result.staging ? state.result.total
        : state.result.winners.reduce(function (sum, w) { return sum + w.amount; }, 0);
    }
    var text = money(total);
    if ($("pot-amount").textContent !== text) {
      $("pot-amount").textContent = text;
      if (previous) {
        pot.classList.remove("bump");
        void pot.offsetWidth;
        pot.classList.add("bump");
      }
    }
    var side = $("side-pots");
    var pots = state.pots || [];
    side.classList.toggle("hidden", pots.length < 2);
    side.textContent = "";
    pots.forEach(function (amount, i) {
      var label = i === 0 ? "اصلی" : "جانبی" + (pots.length > 2 ? " " + fa(i) : "");
      side.appendChild(el("span", "", label + " " + money(amount)));
    });
    $("street").textContent = state.over ? "" : STREETS[state.street] || "";
    $("hand-chip").textContent = "دست " + fa(state.hand) + " از " + fa(state.hand_limit);
    $("blind-chip").textContent = "بلایند " + money(state.sb) + "/" + money(state.bb);
    return box.querySelectorAll(".deal").length;
  }

  function myHandText() {
    var me = mine();
    if (!me) return "";
    if (state.phase === "pause" && state.result && state.result.hands && state.result.hands[String(me.seat)]) {
      return state.result.hands[String(me.seat)];
    }
    return state.my_hand || "";
  }
  function drawMe(previous, said) {
    var me = mine();
    $("me").classList.toggle("hidden", !me);
    if (!me) return;
    var box = $("my-cards");
    var fresh = !previous || previous.hand !== state.hand;
    var win = winning();
    box.textContent = "";
    me.cards.forEach(function (code, i) {
      var card = cardEl(code, cardClass(code, win, fresh));
      if (fresh) card.style.animationDelay = (0.1 + i * 0.12).toFixed(2) + "s";
      box.appendChild(card);
    });
    $("me").classList.toggle("folded", !!(me.folded && me.in_hand));
    var hero = document.querySelector("#me .hero");
    hero.classList.toggle("turn", myTurn());
    var wonAmount = 0;
    if (state.phase === "pause" && state.result) {
      state.result.winners.forEach(function (w) { if (w.seat === me.seat) wonAmount = w.amount; });
    }
    hero.classList.toggle("winner", wonAmount > 0);
    var colors = AVATARS[me.seat % AVATARS.length];
    $("my-ava").style.setProperty("--ava1", colors[0]);
    $("my-ava").style.setProperty("--ava2", colors[1]);
    $("my-initial").textContent = initial(me.seat);
    $("my-name").textContent = badge(me.seat) + name(me.seat) + " (تو)";
    $("my-chips").textContent = money(me.chips) + " ژتون";
    var bet = $("my-bet");
    bet.classList.toggle("hidden", !me.bet);
    bet.textContent = "";
    if (me.bet) {
      bet.appendChild(chipStack(me.bet));
      bet.appendChild(el("span", "", money(me.bet)));
    }
    Array.prototype.forEach.call(hero.querySelectorAll(".said, .win-badge"), function (n) { n.remove(); });
    if (wonAmount) hero.appendChild(el("span", "win-badge", plus(wonAmount)));
    else if (said && said.seat === me.seat) hero.appendChild(el("span", "said " + said.kind, sayText(said)));
    var hand = myHandText();
    $("my-hand").textContent = hand ? "دست تو: " + hand : "";
  }

  function drawLog() {
    var box = $("log");
    box.textContent = "";
    var entries = (state.log || []).filter(function (e) { return e.kind !== "sb" && e.kind !== "bb"; }).slice(-3);
    entries.forEach(function (entry, i) {
      var span = el("span", i === entries.length - 1 ? "fresh" : "");
      span.appendChild(el("b", "", name(entry.seat)));
      span.appendChild(document.createTextNode(": " + sayText(entry) + (entry.timeout ? " (وقت تمام شد)" : "")));
      box.appendChild(span);
    });
  }

  // ژتون‌های شرط در پایان هر دور به وسط میز می‌روند و در پایان دست به برنده
  function flyBets(previous) {
    var layer = $("layer");
    var streetDone = previous.hand === state.hand && (previous.street !== state.street || (previous.phase === "betting" && state.phase !== "betting"));
    if (!streetDone) return;
    previous.seats.forEach(function (s) {
      if (!s.bet) return;
      var chip = el("div", "fly bet");
      chip.appendChild(el("i", "chip-ico " + chipColor(s.bet)));
      place(chip, betPoint(s.seat));
      layer.appendChild(chip);
      animateTo(chip, { x: 50, y: 40 });
    });
  }
  // نتیجه‌ی دست همین الان دیده می‌شود (در آل‌این بعد از باز شدن همه‌ی کارت‌ها)
  function resultAppears(previous) {
    if (!previous || state.phase !== "pause" || !state.result || state.result.staging) return false;
    return previous.hand !== state.hand || previous.phase !== "pause" || !!(previous.result && previous.result.staging);
  }
  function flyWinnings() {
    var layer = $("layer");
    state.result.winners.forEach(function (w) {
      for (var i = 0; i < 4; i++) {
        var chip = el("div", "fly");
        chip.appendChild(el("i", "chip-ico " + (i % 2 ? "blue" : "")));
        place(chip, { x: 50 + (i - 1.5) * 3, y: 40 });
        layer.appendChild(chip);
        animateTo(chip, isMe(w.seat) ? { x: 50, y: 98 } : point(w.seat, 40, 41), 120 + i * 80);
      }
    });
  }
  function animateTo(node, p, delay) {
    setTimeout(function () {
      void node.offsetWidth;
      place(node, p);
      node.style.opacity = "0.2";
      setTimeout(function () { node.remove(); }, 520);
    }, (delay || 0) + 30);
  }

  // ------------------------------------------------------------------ آل‌این: کارت‌های وسط یکی‌یکی
  function shouldStage(before, after) {
    return !!before && before.hand === after.hand && before.phase === "betting" && after.phase === "pause" &&
      !!after.result && after.result.runout !== null && after.result.runout !== undefined &&
      after.board.length > before.board.length;
  }
  function startStage(before) {
    var from = before.board.length;
    stage = { hand: real.hand, shown: from, steps: [3, 4, 5].filter(function (n) { return n > from; }), timer: null };
    nextStage(900); // اول دست‌ها رو می‌شوند
  }
  function stagedView() {
    var copy = Object.assign({}, real);
    var won = {};
    var total = 0;
    real.result.winners.forEach(function (w) {
      won[w.seat] = (won[w.seat] || 0) + w.amount;
      total += w.amount;
    });
    copy.board = real.board.slice(0, stage.shown);
    copy.street = ["preflop", "preflop", "preflop", "flop", "turn", "river"][stage.shown];
    copy.seats = real.seats.map(function (s) { return Object.assign({}, s, { chips: s.chips - (won[s.seat] || 0) }); });
    copy.result = { reveal: real.result.reveal, hands: {}, winners: [], runout: real.result.runout, staging: true, total: total };
    copy.my_hand = "";
    return copy;
  }
  function nextStage(delay) {
    stage.timer = setTimeout(function () {
      if (!stage) return;
      var previous = state;
      if (stage.steps.length) {
        stage.shown = stage.steps.shift();
        state = stagedView();
        render(previous);
        nextStage(stage.steps.length ? RUNOUT_MS : 900);
      } else {
        stage = null;
        state = real;
        render(previous);
      }
    }, delay);
  }
  function stopStage() {
    if (stage) clearTimeout(stage.timer);
    stage = null;
  }

  // ------------------------------------------------------------------ زمان و وضعیت
  function msLeft() { return Math.max(0, leftBase - (now() - receivedAt)); }
  function tick() {
    if (!state) return;
    var turn = document.querySelector(".seat.turn > .ava") || document.querySelector(".hero.turn .ava");
    if (turn && state.phase === "betting") {
      var fraction = Math.min(1, msLeft() / (state.move_seconds * 1000));
      turn.style.setProperty("--deg", (fraction * 360).toFixed(1) + "deg");
      var ring = fraction > 0.5 ? "#34d399" : fraction > 0.2 ? "#ffc857" : "#ff5c7a";
      turn.style.setProperty("--ring", ring);
    }
    if (myTurn()) {
      if (msLeft() < 8000 && !lowWarned) {
        lowWarned = true;
        sound("low");
        haptic("warning");
      }
    } else lowWarned = false;
    status();
  }
  function status() {
    var box = $("status");
    var text = "";
    var cls = "";
    var seconds = Math.ceil(msLeft() / 1000);
    if (state.cancelled) { text = "این مسابقه لغو شده است."; cls = "alert"; }
    else if (state.over) text = resultTitle();
    else if (state.result && state.result.staging) { text = "🔥 آل‌این! کارت‌ها یکی‌یکی باز می‌شوند…"; cls = "warn"; }
    else if (state.phase === "pause" && state.result) {
      text = state.result.winners.map(function (w) {
        return "🏆 " + name(w.seat) + " " + money(w.amount) + " ژتون برد" + (w.hand ? " (" + w.hand + ")" : "");
      }).join("  ") + "  ⏳ دست بعد " + fa(seconds) + " ثانیه دیگر";
    } else if (state.to_act !== null && state.to_act !== undefined) {
      var my = isMe(state.to_act);
      text = (my ? "نوبت توست" : "نوبت " + name(state.to_act)) + " (" + fa(seconds) + " ثانیه)";
      cls = my ? (seconds <= 8 ? "warn" : "mine") : "";
      if (!my && pre) text += " · " + preLabel(pre) + " آماده است";
    }
    if (box.textContent !== text) box.textContent = text;
    box.className = cls;
  }

  // ------------------------------------------------------------------ حرکت از پیش
  function toCall(me) { return Math.max(0, Math.min(state.current_bet - me.bet, me.chips)); }
  function preAllowed() {
    var me = mine();
    return !!me && !stage && !state.over && !state.cancelled && state.phase === "betting" && me.in_hand &&
      !me.folded && !me.allin && !me.left && state.to_act !== me.seat;
  }
  function preLabel(choice) {
    if (choice.kind === "checkfold") return "چک/فولد";
    if (choice.kind === "check") return "چک";
    if (choice.kind === "call") return "کال " + money(choice.amount);
    return "کال هر مبلغ";
  }
  function preBar() {
    var box = $("pre");
    var show = preAllowed();
    box.classList.toggle("hidden", !show);
    if (!show) {
      if (!myTurn()) pre = null;
      return;
    }
    var me = mine();
    var amount = toCall(me);
    if (pre && (pre.hand !== state.hand || pre.street !== state.street)) pre = null;
    if (pre && ((pre.kind === "check" && amount > 0) || (pre.kind === "call" && amount !== pre.amount))) {
      pre = null;
      toast("شرط عوض شد؛ حرکت از پیش لغو شد.");
      haptic("warning");
    }
    Array.prototype.forEach.call(box.querySelectorAll(".pre-btn"), function (button) {
      var kind = button.dataset.pre;
      var label = button.querySelector("span");
      if (kind === "checkfold") label.textContent = amount > 0 ? "فولد" : "چک/فولد";
      if (kind === "call") label.textContent = "کال " + money(amount);
      button.classList.toggle("hidden", (kind === "check" && amount > 0) || (kind === "call" && amount === 0));
      button.classList.toggle("on", !!pre && pre.kind === kind);
    });
  }
  function runPre(choice) {
    if (busy || !myTurn()) return;
    var legal = state.legal || {};
    var kind = null;
    if (choice.kind === "checkfold") kind = legal.check ? "check" : "fold";
    else if (choice.kind === "check") kind = legal.check ? "check" : null;
    else if (choice.kind === "call") kind = legal.call === choice.amount ? "call" : null;
    else if (choice.kind === "callany") kind = legal.check ? "check" : legal.call ? "call" : null;
    if (kind) send(kind);
    else toast("شرط عوض شد؛ خودت تصمیم بگیر.");
  }

  // ------------------------------------------------------------------ دکمه‌ها و اندازه‌ی شرط
  function clamp(value, low, high) { return Math.max(low, Math.min(high, value)); }
  function presets(legal) {
    var me = mine();
    var after = state.pot + toCall(me); // پات بعد از کال
    var options = [["حداقل", legal.raise_min]];
    [["½ پات", 0.5], ["¾ پات", 0.75], ["پات", 1]].forEach(function (pair) {
      options.push([pair[0], clamp(state.current_bet + Math.round(after * pair[1]), legal.raise_min, legal.raise_max)]);
    });
    if (state.street === "preflop" && state.current_bet === state.bb) {
      options.splice(1, 0, ["۳ بلایند", clamp(state.bb * 3, legal.raise_min, legal.raise_max)]);
    }
    var seen = {};
    return options.filter(function (pair) {
      if (seen[pair[1]]) return false;
      seen[pair[1]] = true;
      return true;
    }).slice(0, 4);
  }
  function raiseLabel() { return "رِیز تا " + money(raiseTo); }
  function controls() {
    var legal = state.legal || {};
    var playing = myTurn();
    $("controls").classList.toggle("hidden", !playing);
    if (!playing) return;
    $("check-btn").classList.toggle("hidden", !legal.check);
    $("call-btn").classList.toggle("hidden", !legal.call);
    $("call-btn").textContent = "کال " + money(legal.call);
    var canRaise = !!legal.raise_min;
    $("sizing").classList.toggle("hidden", !canRaise);
    $("raise-btn").classList.toggle("hidden", !canRaise);
    var allinIsCall = legal.allin && legal.allin === legal.call;
    $("allin-btn").classList.toggle("hidden", !legal.allin || allinIsCall);
    $("allin-btn").textContent = "آل‌این " + money(legal.allin);
    if (canRaise) {
      var range = $("raise-range");
      range.min = legal.raise_min;
      range.max = legal.raise_max;
      range.step = Math.max(1, state.sb);
      if (raiseTo < legal.raise_min || raiseTo > legal.raise_max) raiseTo = legal.raise_min;
      range.value = raiseTo;
      var box = $("presets");
      box.textContent = "";
      presets(legal).forEach(function (pair) {
        var button = el("button", pair[1] === raiseTo ? "on" : "", pair[0]);
        button.type = "button";
        button.addEventListener("click", function () {
          setRaise(pair[1]);
          button.classList.add("on");
          haptic("light");
        });
        box.appendChild(button);
      });
      $("raise-btn").textContent = raiseLabel();
    }
  }
  function setRaise(value) {
    var legal = state.legal || {};
    raiseTo = clamp(Math.round(value), legal.raise_min, legal.raise_max);
    $("raise-range").value = raiseTo;
    $("raise-btn").textContent = raiseLabel();
    Array.prototype.forEach.call($("presets").children, function (button) { button.classList.remove("on"); });
  }

  // ------------------------------------------------------------------ تاریخچه و رتبه‌ی دست‌ها
  function drawHistory() {
    var body = $("history-body");
    body.textContent = "";
    var board = state.board;
    var current = el("section", "hist");
    current.appendChild(el("h3", "", "دست " + fa(state.hand) + " — همین دست"));
    var byStreet = {};
    (real.log || []).forEach(function (entry) { (byStreet[entry.street] = byStreet[entry.street] || []).push(entry); });
    ["preflop", "flop", "turn", "river"].forEach(function (street) {
      var cards = street === "flop" ? board.slice(0, 3) : street === "turn" ? board.slice(3, 4) : street === "river" ? board.slice(4, 5) : [];
      var entries = byStreet[street] || [];
      if (!entries.length && !cards.length) return;
      var head = el("div", "street-head");
      head.appendChild(el("b", "", STREETS[street]));
      if (cards.length) head.appendChild(miniCards(cards));
      current.appendChild(head);
      entries.forEach(function (entry) {
        var line = el("p", "act " + entry.kind);
        line.appendChild(el("b", "", name(entry.seat)));
        line.appendChild(document.createTextNode(" " + sayText(entry) + (entry.timeout ? " (وقت تمام شد)" : "")));
        current.appendChild(line);
      });
    });
    if (state.phase === "pause" && state.result && !state.result.staging) current.appendChild(resultLines(state.result));
    body.appendChild(current);
    var last = real.last_hand;
    if (last && last.hand !== state.hand) {
      var previous = el("section", "hist");
      previous.appendChild(el("h3", "", "دست " + fa(last.hand) + " — دست قبل"));
      if (last.board && last.board.length) {
        var row = el("div", "street-head");
        row.appendChild(el("b", "", "کارت‌های وسط"));
        row.appendChild(miniCards(last.board));
        previous.appendChild(row);
      }
      previous.appendChild(resultLines(last));
      body.appendChild(previous);
    }
  }
  function resultLines(result) {
    var box = el("div", "hist-result");
    (result.winners || []).forEach(function (w) {
      var line = el("p", "won");
      line.appendChild(el("b", "", "🏆 " + name(w.seat)));
      line.appendChild(document.createTextNode(" " + plus(w.amount) + (w.hand ? " — " + w.hand : " (بقیه فولد کردند)")));
      box.appendChild(line);
    });
    Object.keys(result.reveal || {}).forEach(function (seat) {
      var line = el("p", "shown");
      line.appendChild(el("b", "", name(Number(seat))));
      line.appendChild(miniCards(result.reveal[seat]));
      if (result.hands && result.hands[seat]) line.appendChild(el("small", "", result.hands[seat]));
      box.appendChild(line);
    });
    return box;
  }
  function rankOf(text) {
    if (!text) return -1;
    for (var i = 0; i < RANK_PREFIXES.length; i++) if (text.indexOf(RANK_PREFIXES[i]) === 0) return i;
    return RANK_PREFIXES.length - 1; // قبل از فلاپ مثل «آس و شاه»: کارت بالا
  }
  function drawRanks() {
    var list = $("ranks-list");
    var mineRank = rankOf(myHandText());
    list.textContent = "";
    RANKINGS.forEach(function (row, i) {
      var item = el("li", i === mineRank ? "mine" : "");
      var text = el("div", "rank-text");
      text.appendChild(el("b", "", fa(i + 1) + ". " + row[0] + (i === mineRank ? " ← دست تو" : "")));
      text.appendChild(el("small", "", row[2]));
      item.appendChild(text);
      item.appendChild(miniCards(row[1]));
      list.appendChild(item);
    });
  }
  function openSheet(id) {
    if (id === "history") { historyOpen = true; drawHistory(); }
    if (id === "ranks") drawRanks();
    $(id).classList.remove("hidden");
    haptic("light");
  }
  function closeSheet(sheet) {
    sheet.classList.add("hidden");
    if (sheet.id === "history") historyOpen = false;
  }

  // ------------------------------------------------------------------ نتیجه
  function ranking() {
    return state.seats.map(function (s) { return { seat: s.seat, chips: s.left ? 0 : s.chips }; })
      .sort(function (a, b) { return b.chips - a.chips; });
  }
  function resultTitle() {
    var top = ranking()[0];
    if (!top || top.chips <= 0) return "بازی تمام شد";
    if (isMe(top.seat)) return "🏆 بیشترین ژتون مال توست!";
    return "🏆 " + name(top.seat) + " بیشترین ژتون را دارد";
  }
  function confetti() {
    var box = $("confetti");
    var colors = ["#ffc857", "#6ee7ff", "#a78bfa", "#34d399", "#ff5c7a", "#ffffff"];
    box.textContent = "";
    for (var i = 0; i < 40; i++) {
      var bit = el("i");
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
    var list = $("result-list");
    list.textContent = "";
    var medals = ["🥇", "🥈", "🥉"];
    ranking().forEach(function (row, i) {
      var item = el("li", isMe(row.seat) ? "me" : "");
      item.appendChild(el("span", "", (medals[i] || fa(i + 1) + ".") + " " + name(row.seat)));
      item.appendChild(el("small", "", money(row.chips) + " ژتون"));
      list.appendChild(item);
    });
    var top = ranking()[0];
    var won = !!top && isMe(top.seat) && top.chips > 0;
    $("result-icon").textContent = won ? "🏆" : "🃏";
    $("result-title").textContent = resultTitle();
    $("result-reason").textContent = (REASONS[state.over.reason] || "") + " — جایزه‌ی سکه بر اساس رتبه‌ی ژتون در گروه اعلام می‌شود.";
    setTimeout(function () {
      $("result").classList.remove("hidden");
      if (won) confetti();
    }, 1400);
    sound(won ? "win" : "draw");
    haptic("success");
  }

  // ------------------------------------------------------------------ دریافت وضعیت
  function react(previous, said, dealt) {
    if (!previous) return;
    if (said) {
      var kind = said.kind;
      sound(kind === "fold" || kind === "leave" ? "fold" : kind === "check" ? "move" : kind === "allin" ? "chips" : "chip");
    }
    if (dealt) sound("deal");
    if (resultAppears(previous)) {
      var meWon = state.result.winners.some(function (w) { return isMe(w.seat); });
      setTimeout(function () { sound(meWon ? "win" : "chips"); }, 250);
      if (meWon) haptic("success");
    }
    var wasMyTurn = previous.to_act === previous.you && previous.phase === "betting" && previous.hand === state.hand && previous.street === state.street;
    if (myTurn() && !wasMyTurn) { sound("turn"); haptic("medium"); }
  }
  function render(previous) {
    var said = drawLayer(previous);
    var dealt = drawBoard(previous);
    drawMe(previous, said);
    drawLog();
    if (previous) flyBets(previous);
    if (resultAppears(previous)) flyWinnings();
    controls();
    preBar();
    tick();
    react(previous, said, dealt || (previous && previous.hand !== state.hand));
    var me = mine();
    $("resign-btn").classList.toggle("hidden", !me);
    $("resign-btn").disabled = !me || me.left || !!state.over || !!state.cancelled;
    if (historyOpen) drawHistory();
    if (state.over) showResult();
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
      tick();
      return true;
    }
    var previous = state;
    var before = real;
    real = response.state;
    leftBase = real.left_ms !== undefined ? real.left_ms : real.seconds_left * 1000;
    if (stage && (stage.hand !== real.hand || real.phase !== "pause")) stopStage();
    if (!stage && shouldStage(before, real)) startStage(before);
    state = stage ? stagedView() : real;
    if (!previous || previous.to_act !== state.to_act || previous.street !== state.street || previous.hand !== state.hand) raiseTo = 0;
    // نوبت رسید و حرکت از پیش انتخاب شده بود: کمی بعد انجام می‌شود تا بازیکن ببیند
    if (pre && (pre.hand !== state.hand || pre.street !== state.street)) pre = null;
    var queued = pre && myTurn() ? pre : null;
    if (queued) pre = null;
    render(previous);
    if (queued) setTimeout(function () { runPre(queued); }, 260);
    return true;
  }
  function pollDelay() {
    if (!state || state.over || state.cancelled) return 5000;
    if (myTurn()) return 1600;
    return 900;
  }
  function loop() {
    clearTimeout(pollTimer);
    pollTimer = setTimeout(function () {
      if (document.hidden || busy || !state) { loop(); return; }
      api("board/state", { version: real.version }).then(function (response) {
        if (!busy && response.ok) apply(response);
        loop();
      });
    }, pollDelay());
  }
  function send(kind, amount) {
    if (!state || busy) return;
    busy = true;
    pre = null;
    haptic("light");
    api("board/action", { action: kind, amount: amount || 0 }).then(function (response) {
      busy = false;
      if (!apply(response)) loop();
    });
  }
  function fail(text) {
    $("loading-text").textContent = text;
    document.querySelector("#loading .spinner").classList.add("hidden");
  }

  $("fold-btn").addEventListener("click", function () {
    // مثل اپ‌های پوکر: وقتی چک مجانی است فولد با یک سؤال انجام می‌شود
    if (state && state.legal && state.legal.check) confirmThen("می‌توانی مجانی چک کنی. باز هم فولد می‌کنی؟", function () { send("fold"); });
    else send("fold");
  });
  $("check-btn").addEventListener("click", function () { send("check"); });
  $("call-btn").addEventListener("click", function () { send("call"); });
  $("allin-btn").addEventListener("click", function () { send("allin"); });
  $("raise-btn").addEventListener("click", function () { send("raise", raiseTo); });
  $("raise-range").addEventListener("input", function () { setRaise(Number(this.value)); });
  $("minus-btn").addEventListener("click", function () { setRaise(raiseTo - state.bb); haptic("light"); });
  $("plus-btn").addEventListener("click", function () { setRaise(raiseTo + state.bb); haptic("light"); });
  Array.prototype.forEach.call(document.querySelectorAll(".pre-btn"), function (button) {
    button.addEventListener("click", function () {
      if (!state || !preAllowed()) return;
      var kind = button.dataset.pre;
      pre = pre && pre.kind === kind ? null : { kind: kind, amount: kind === "call" ? toCall(mine()) : 0, hand: state.hand, street: state.street };
      preBar();
      status();
      haptic("light");
    });
  });
  $("history-btn").addEventListener("click", function () { if (state) openSheet("history"); });
  $("ranks-btn").addEventListener("click", function () { if (state) openSheet("ranks"); });
  Array.prototype.forEach.call(document.querySelectorAll(".sheet"), function (sheet) {
    sheet.addEventListener("click", function (event) {
      if (event.target === sheet || event.target.classList.contains("sheet-close")) closeSheet(sheet);
    });
  });
  function soundButton() { $("sound-btn").textContent = window.SFX && window.SFX.isMuted() ? "🔇" : "🔊"; }
  $("sound-btn").addEventListener("click", function () {
    if (!window.SFX) return;
    window.SFX.setMuted(!window.SFX.isMuted());
    soundButton();
    if (!window.SFX.isMuted()) setTimeout(function () { sound("chip"); }, 60);
  });
  $("resign-btn").addEventListener("click", function () {
    confirmThen("مطمئنی می‌خواهی میز را ترک کنی؟ ژتون‌هایت از بازی خارج می‌شود.", function () { send("resign"); });
  });
  $("result-close").addEventListener("click", function () {
    if (tg && tg.close) { try { tg.close(); return; } catch (e) { /* قدیمی */ } }
    $("result").classList.add("hidden");
  });
  $("result-view").addEventListener("click", function () { $("result").classList.add("hidden"); });
  document.addEventListener("pointerdown", function () { if (window.SFX) window.SFX.unlock(); }, { once: true });

  soundButton();
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
    loop();
    setInterval(tick, 200);
    document.addEventListener("visibilitychange", function () {
      if (document.hidden || busy || !state) return;
      api("board/state", { version: real.version }).then(function (response) { if (!busy && response.ok) apply(response); });
    });
  });
})();
