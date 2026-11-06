/* میز حکم مینی‌اپ. همه‌ی قوانین و کارت‌ها در سرور است؛ سرور فقط کارت‌های خود بازیکن را می‌فرستد.
   صندلی‌ها نسبت به بیننده: خودت پایین، نفر بعدی (نوبت به سمت راست می‌چرخد) راست، یارت بالا و حریف دیگر چپ.
   کارت‌های هر دست از سمت بازیکنش وسط میز می‌آیند؛ وقتی دست کامل شد کارت برنده برجسته می‌شود و کارت‌ها به سمت
   برنده جمع می‌شوند. کارت‌های خودت پایین صفحه به شکل بادبزن است: کارت مجاز را یک بار لمس کن تا بالا بیاید و دوباره
   بزن تا بازی شود (کارت‌هایی که طبق قانون «از خال زمین بده» مجاز نیستند کم‌رنگ‌اند). حاکم حکم را از روی ۵ کارت اول
   انتخاب می‌کند. گفت‌وگوی میز همراه همان پرسش «چیزی عوض شده؟» می‌آید و پیام هر نفر بالای صندلی‌اش هم دیده می‌شود. */
(function () {
  "use strict";

  var BOOT = window.BOARD_BOOT;
  var tg = window.Telegram && window.Telegram.WebApp ? window.Telegram.WebApp : null;
  var query = new URLSearchParams(location.search);
  var initData = tg && tg.initData ? tg.initData : "";
  if (!initData && BOOT.devAuth && query.get("dev_user")) initData = "dev:" + query.get("dev_user");

  var SUITS = { s: "♠", h: "♥", d: "♦", c: "♣" };
  var SUIT_NAMES = { s: "پیک", h: "دل", d: "خشت", c: "گشنیز" };
  var ERRORS = {
    not_your_turn: "نوبت تو نیست.",
    illegal_move: "این کارت الان مجاز نیست.",
    game_over: "بازی تمام شده است.",
    timeout: "وقت این نوبت تمام شده بود.",
    not_a_player: "تو بازیکن این میز نیستی؛ فقط تماشا می‌کنی.",
    match_not_found: "این مسابقه پیدا نشد.",
    match_not_running: "این مسابقه در جریان نیست.",
    bad_action: "این کار ممکن نیست.",
    rate_limited: "کمی آهسته‌تر! چند ثانیه صبر کن.",
    banned: "حساب تو مسدود شده است.",
    network: "اتصال به سرور برقرار نشد.",
    chat_empty: "پیام خالی است.",
    chat_no_links: "فرستادن لینک و آیدی در گفت‌وگو ممنوع است.",
    chat_too_fast: "کمی آهسته‌تر بنویس 🙂",
    chat_locked: "گفت‌وگوی این میز بسته شده است.",
  };
  var AVATARS = [["#5662e0", "#262b78"], ["#f0617f", "#8f1d3a"], ["#2fbf8f", "#0f5c45"], ["#f5a524", "#8a5200"]];
  // جای صندلی‌ها روی میز (درصد) به ترتیب نسبت به بیننده: خودت، نفر بعدی (راست)، یار (بالا)، نفر قبلی (چپ)
  var SPOTS = [{ x: 50, y: 90 }, { x: 87, y: 45 }, { x: 50, y: 13 }, { x: 13, y: 45 }];
  // جای کارت هر نفر وسط میز و چرخش کمش؛ و این‌که کارت از کدام سمت می‌آید (پیکسل)
  var TRICK_SPOTS = [{ x: 50, y: 64, r: -3 }, { x: 67, y: 47, r: 7 }, { x: 50, y: 30, r: 2 }, { x: 33, y: 47, r: -7 }];
  var FROM = [[0, 70], [70, 0], [0, -70], [-70, 0]];
  var TABLE_QUICK = ["👏 آفرین یار", "💪 بریم برای کُت", "🙏 حکم خوبی بود", "😅 ببخشید", "🤝 بازی خوبی بود"];
  var SOLO_QUICK = ["👏 دست خوبی بود", "😎 کُت در راه است", "🙏 حکم خوبی بود", "😅 ببخشید", "🤝 بازی خوبی بود"];
  // در حکم سه‌نفره دو حریف راست و چپ می‌نشینند (جای بالا خالی است)
  var SOLO_SLOTS = [0, 1, 3];
  var DUO_SLOTS = [0, 2]; // حکم دونفره: حریف روبه‌رو

  var real = null; // آخرین وضعیت سرور
  var state = null;
  var busy = false;
  var receivedAt = 0;
  var leftBase = 0;
  var picked = null; // کارتی که برای بازی بالا آمده
  var collecting = null; // دستِ تمام‌شده‌ای که هنوز وسط میز نشان داده می‌شود: {no, timer}
  var shownTrick = 0; // آخرین شماره‌ی دست که جمع شدنش نشان داده شد
  var resultShown = false;
  var introShown = false;
  var noteTimer = null;
  var pollTimer = null;
  var lowWarned = false;
  var prizeTries = 0;
  var prizeTimer = null;
  var ring = { node: null, end: 0 };
  var talk = { last: 0, open: false, unread: 0, can: false, quick: [], loaded: false, sending: false, locked: false, voted: false };

  function $(id) { return document.getElementById(id); }
  function el(tag, cls, text) {
    var node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined) node.textContent = text;
    return node;
  }
  function fa(value) { return String(value).replace(/\d/g, function (d) { return "۰۱۲۳۴۵۶۷۸۹"[d]; }); }
  function money(value) { return fa(Number(value || 0).toLocaleString("en-US")).replace(/,/g, "٬"); }
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
  function toast(text, info) {
    var box = $("toast");
    box.textContent = text;
    box.classList.toggle("info", !!info);
    box.classList.remove("hidden");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { box.classList.add("hidden"); }, 2600);
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
  function seated() { return state.you !== null && state.you !== undefined; }
  function base() { return seated() ? state.you : 0; }
  function count() { return state.seats ? state.seats.length : 4; }
  function solo() { return !!state.solo; }
  function rel(seat) { return (seat - base() + count()) % count(); }
  // جای صندلی روی میز (یکی از چهار جای SPOTS): در سه‌نفره بالا خالی می‌ماند
  function slot(seat) { var r = rel(seat); return count() === 2 ? DUO_SLOTS[r] : solo() ? SOLO_SLOTS[r] : r; }
  function name(seat) { return state.players["s" + seat] || ""; }
  function badge(seat) {
    var profile = (state.profiles || {})["s" + seat];
    return profile && profile.emoji ? profile.emoji + " " : "";
  }
  function initial(seat) { return (name(seat).trim()[0] || "؟").toUpperCase(); }
  function team(seat) { return solo() ? seat : seat % 2; }
  function myTeam() { return seated() ? team(state.you) : 0; }
  function teamLabel(t) {
    if (solo()) return seated() && t === state.you ? "تو" : name(t);
    if (!seated()) return t === 0 ? "تیم آبی" : "تیم نارنجی";
    return t === myTeam() ? "ما" : "حریف";
  }
  function pairNames(t) { return solo() ? name(t) : name(t) + " و " + name(t + 2); }
  // «۷ به ۳» برای دو تیم؛ در سه‌نفره دست‌های هر سه نفر از برنده به بعد
  function tally(list, win) {
    if (!solo()) return fa(list[win]) + " به " + fa(list[1 - win]);
    var order = [win].concat(list.map(function (_, i) { return i; }).filter(function (t) { return t !== win; }));
    return order.map(function (t) { return fa(list[t]); }).join(" – ");
  }
  function others(list, t) { return Math.max.apply(null, list.filter(function (_, i) { return i !== t; })); }
  function myTurn() {
    return seated() && !state.over && state.turn === state.you && (state.phase === "play" || state.phase === "trump" || state.phase === "draw");
  }
  function duo() { return count() === 2; }
  function legalSet() {
    var set = {};
    (state.legal || []).forEach(function (c) { set[c] = true; });
    return set;
  }
  function ledSuit() { return state.trick && state.trick.length ? state.trick[0][1][1] : ""; }

  // ------------------------------------------------------------------ کارت
  function cardEl(code, extra) {
    var card = el("span", "pcard" + (extra ? " " + extra : ""));
    if (!code) { card.classList.add("back"); return card; }
    var suit = SUITS[code[1]];
    if (code[1] === "h" || code[1] === "d") card.classList.add("red");
    if (state && state.trump && code[1] === state.trump) card.classList.add("trump");
    var index = el("span", "idx");
    index.appendChild(el("b", "", code[0] === "T" ? "10" : code[0]));
    index.appendChild(el("i", "", suit));
    card.appendChild(index);
    card.appendChild(el("span", "pip", suit));
    // روی کارت مثل کارت واقعی (تعداد نقش درست، تصویر شاه و بی‌بی و سرباز)؛ کارت‌های ریز فهرست‌ها همان برچسب ساده را دارند
    if (window.CardFaces && !card.classList.contains("mini")) window.CardFaces.apply(card, code);
    return card;
  }
  function place(node, p) {
    node.style.left = p.x.toFixed(2) + "%";
    node.style.top = p.y.toFixed(2) + "%";
  }
  function ringSvg() {
    var svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("class", "ring");
    svg.setAttribute("viewBox", "0 0 40 40");
    svg.setAttribute("aria-hidden", "true");
    var circle = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    circle.setAttribute("cx", "20");
    circle.setAttribute("cy", "20");
    circle.setAttribute("r", "18.5");
    circle.setAttribute("pathLength", "100");
    svg.appendChild(circle);
    return svg;
  }
  function avatar(seat) {
    var node = el("div", "ava");
    var colors = AVATARS[seat % AVATARS.length];
    node.style.setProperty("--ava1", colors[0]);
    node.style.setProperty("--ava2", colors[1]);
    node.appendChild(ringSvg());
    node.appendChild(el("span", "", initial(seat)));
    if (state.hakem === seat) node.appendChild(el("i", "crown", "👑"));
    return node;
  }

  // ------------------------------------------------------------------ امتیاز و حکم
  function drawScores() {
    $("team-2").classList.toggle("hidden", count() !== 3);
    $("scores").classList.toggle("solo", solo());
    state.points.forEach(function (_, t) {
      var box = $("team-" + t);
      box.classList.toggle("me", solo() && seated() && t === state.you);
      box.querySelector(".name").textContent = teamLabel(t);
      box.querySelector(".name").title = pairNames(t);
      var pts = box.querySelector(".pts");
      pts.textContent = fa(state.points[t]);
      pts.appendChild(el("small", "", " امتیاز"));
      box.querySelector(".tricks").textContent = (state.phase === "trump" && !state.trick_no ? "دور " + fa(state.round) : "این دور " + fa(state.tricks[t]) + " دست");
      box.classList.toggle("lead", state.points[t] > others(state.points, t));
      // تیم خودت همیشه سمت راست (اول در راست‌به‌چپ)؛ در سه‌نفره بقیه به ترتیب نوبت بعد از حکم
      box.style.order = t === myTeam() ? 0 : solo() ? 1 + rel(t) : 2;
    });
    $("trump-box").style.order = 1;
    $("target-chip").textContent = "تا " + fa(state.target) + " امتیاز";
  }
  var lastTrump = "";
  function drawTrump() {
    var box = $("trump-box");
    var trump = state.trump;
    box.classList.toggle("empty", !trump);
    box.classList.toggle("red", trump === "h" || trump === "d");
    $("trump-sym").textContent = trump ? SUITS[trump] : "?";
    $("trump-name").textContent = trump ? "حکم: " + SUIT_NAMES[trump] : "حکم";
    if (trump && trump !== lastTrump) {
      box.classList.remove("fresh");
      void box.offsetWidth;
      box.classList.add("fresh");
    }
    lastTrump = trump;
  }

  // ------------------------------------------------------------------ صندلی‌ها
  function drawSeats() {
    var box = $("seats");
    box.textContent = "";
    state.seats.forEach(function (s) {
      var r = slot(s.seat);
      var turn = !state.over && state.turn === s.seat && (state.phase === "play" || state.phase === "trump" || state.phase === "draw");
      if (seated() && s.seat === state.you) {
        var me = el("div", "t" + (solo() ? s.seat : s.team));
        me.id = "me-plate";
        me.style.setProperty("--c", "var(--team" + (solo() ? s.seat : s.team) + ")");
        if (turn) me.classList.add("turn");
        me.appendChild(avatar(s.seat));
        me.appendChild(el("b", "", badge(s.seat) + name(s.seat) + " (تو)"));
        box.appendChild(me);
        return;
      }
      var seat = el("div", "seat t" + (solo() ? s.seat : s.team) + (r === 1 ? " at-right" : r === 3 ? " at-left" : r === 2 ? " at-top" : ""));
      if (turn) seat.classList.add("turn");
      if (s.left) seat.classList.add("left");
      seat.appendChild(avatar(s.seat));
      if (s.count && state.phase !== "over") {
        var backs = el("div", "backs");
        for (var i = 0; i < Math.min(3, s.count); i++) backs.appendChild(cardEl("", ""));
        seat.appendChild(backs);
      }
      var plate = el("div", "plate");
      plate.appendChild(el("b", "", badge(s.seat) + name(s.seat)));
      plate.appendChild(el("small", "", fa(s.count) + " کارت"));
      seat.appendChild(plate);
      if (s.left) seat.appendChild(el("span", "tag left", "رفت"));
      else if (s.away) seat.appendChild(el("span", "tag away", "غایب؛ خودکار"));
      place(seat, SPOTS[r]);
      box.appendChild(seat);
    });
  }

  // ------------------------------------------------------------------ کارت‌های وسط میز
  // جای کارت‌های وسط بسته به ارتفاع میز: کارت بالا زیر پلاک یار و کارت پایین بالای پلاک خودت (صفحه‌های کوتاه)
  function trickSpots() {
    var table = $("table");
    var height = table.offsetHeight || 400;
    var cardH = (parseFloat(getComputedStyle(table).getPropertyValue("--cw")) || 54) * 1.4;
    var top = ((0.13 * height + 38 + cardH / 2 + 4) / height) * 100;
    var bottom = ((0.9 * height - 30 - cardH / 2 - 4) / height) * 100;
    top = Math.max(TRICK_SPOTS[2].y, top);
    bottom = Math.min(TRICK_SPOTS[0].y, bottom);
    var middle = (top + bottom) / 2;
    return [
      { x: 50, y: bottom, r: TRICK_SPOTS[0].r },
      { x: TRICK_SPOTS[1].x, y: middle, r: TRICK_SPOTS[1].r },
      { x: 50, y: top, r: TRICK_SPOTS[2].r },
      { x: TRICK_SPOTS[3].x, y: middle, r: TRICK_SPOTS[3].r },
    ];
  }
  var spots = null;
  function trickCard(seat, code, fresh) {
    var r = slot(seat);
    var spot = (spots || TRICK_SPOTS)[r];
    var card = cardEl(code, fresh ? "in" : "");
    card.style.setProperty("--r", spot.r + "deg");
    card.style.setProperty("--fx", FROM[r][0] + "px");
    card.style.setProperty("--fy", FROM[r][1] + "px");
    card.dataset.seat = seat;
    place(card, spot);
    return card;
  }
  function drawTrick(previous) {
    var box = $("trick");
    if (collecting) return; // دستِ تمام‌شده هنوز نمایش داده می‌شود؛ بعدش همین تابع دوباره صدا زده می‌شود
    spots = trickSpots();
    var finished = state.last_trick && state.last_trick.no > shownTrick && previous &&
      previous.round === state.round && state.trick_no > previous.trick_no;
    if (finished) {
      showCollect(previous);
      return;
    }
    if (state.last_trick) shownTrick = Math.max(shownTrick, state.last_trick.no);
    var before = {};
    if (previous && previous.round === state.round && previous.trick_no === state.trick_no) {
      (previous.trick || []).forEach(function (p) { before[p[0]] = true; });
    }
    box.textContent = "";
    (state.trick || []).forEach(function (p) { box.appendChild(trickCard(p[0], p[1], !before[p[0]])); });
  }
  // دستی که همین الان کامل شد: کارت‌ها یک لحظه می‌مانند، کارت برنده برجسته می‌شود و بعد به سمت برنده جمع می‌شوند
  function showCollect(previous) {
    var box = $("trick");
    var last = state.last_trick;
    var already = {};
    if (previous && previous.round === state.round && previous.trick_no === last.no - 1) {
      (previous.trick || []).forEach(function (p) { already[p[0]] = true; });
    }
    box.textContent = "";
    last.plays.forEach(function (p) {
      var card = trickCard(p[0], p[1], !already[p[0]]);
      if (p[0] === last.winner) card.classList.add("best");
      box.appendChild(card);
    });
    var mine = seated() && team(last.winner) === myTeam();
    setTimeout(function () { sound(mine ? "chips" : "chip"); }, 250);
    collecting = { no: last.no, timer: null };
    collecting.timer = setTimeout(function () {
      var target = SPOTS[slot(last.winner)];
      Array.prototype.forEach.call(box.children, function (card) {
        place(card, target);
        card.classList.add("gone");
      });
      setTimeout(function () {
        shownTrick = Math.max(shownTrick, last.no);
        collecting = null;
        drawTrick(null);
        drawNote();
      }, 380);
    }, 1150);
  }

  // ------------------------------------------------------------------ کارت‌های خودت
  function drawHand(previous) {
    var box = $("hand");
    // سرور هر خال را از بزرگ به کوچک می‌فرستد؛ روی صفحه از راست به چپ چیده می‌شود (بزرگ‌ترین کارت سمت راست)
    var hand = (state.hand || []).slice().reverse();
    var legal = legalSet();
    var playing = myTurn() && state.phase === "play" && !busy;
    if (picked && (!playing || !legal[picked] || hand.indexOf(picked) < 0)) picked = null;
    var fresh = !previous || previous.round !== state.round || (previous.hand || []).length < hand.length;
    box.textContent = "";
    box.classList.toggle("myturn", playing);
    // بادبزن: کارت‌ها روی هم می‌افتند تا ۱۳ کارت هم در عرض صفحه جا شود؛ چرخش کم است و دو طرف حاشیه دارد
    // تا کارت‌های کناری (که با چرخش کمی بیرون می‌روند) از صفحه بیرون نزنند
    var width = box.clientWidth || 360;
    var cardW = parseFloat(getComputedStyle(box).getPropertyValue("--hw")) || Math.min(width * 0.16, 66);
    var n = hand.length;
    var margin = 12;
    var step = n > 1 ? Math.min(cardW * 0.62, (width - cardW - margin * 2) / (n - 1)) : 0;
    var start = (width - (cardW + step * (n - 1))) / 2;
    var mid = (n - 1) / 2;
    var tilt = n > 1 ? Math.min(1.6, 10 / mid) : 0;
    hand.forEach(function (code, i) {
      var off = state.phase === "play" && playing && !legal[code];
      var card = cardEl(code, (off ? "off" : "") + (code === picked ? " pick" : "") + (fresh ? " deal" : ""));
      card.style.setProperty("--x", (start + i * step).toFixed(1) + "px");
      card.style.setProperty("--r", ((i - mid) * tilt).toFixed(2) + "deg");
      card.style.setProperty("--y", (Math.pow(i - mid, 2) * 0.35).toFixed(1) + "px");
      if (fresh) card.style.animationDelay = (i * 0.03).toFixed(2) + "s";
      card.dataset.card = code;
      card.addEventListener("click", function () { tapCard(code); });
      box.appendChild(card);
    });
    var hint = "";
    if (playing) {
      var led = ledSuit();
      var limited = led && hand.some(function (c) { return !legal[c]; });
      hint = picked ? "دوباره بزن تا «" + label(picked) + "» بازی شود" : limited ? "باید از خال زمین (" + SUIT_NAMES[led] + ") بدهی" : "یک کارت را لمس کن تا بالا بیاید، دوباره بزن تا بازی شود";
    } else if (seated() && state.phase === "trump" && state.turn !== state.you) {
      hint = duo() ? "این ۵ کارت اول توست؛ بعد از انتخاب حکم نوبتی کارت می‌کشید." : "این ۵ کارت اول توست؛ بقیه بعد از انتخاب حکم می‌آید.";
    } else if (seated() && state.phase === "draw") {
      hint = fa(hand.length) + " از ۱۳ کارت؛ " + (myTurn() ? "کارت رویی را بردار یا بسوزان" : "نوبت " + name(state.turn) + " است که بکشد");
    }
    $("hand-hint").textContent = hint;
  }
  function label(code) { return (code[0] === "T" ? "10" : code[0]) + SUITS[code[1]]; }
  function tapCard(code) {
    if (!state || state.over) return;
    if (!myTurn() || state.phase !== "play") {
      toast(state.phase === "trump" ? "اول حاکم باید حکم را انتخاب کند." : state.phase === "draw" ? "اول باید کارت‌ها کشیده شود." : "نوبت تو نیست.", true);
      return;
    }
    if (busy) return;
    var legal = legalSet();
    if (!legal[code]) {
      toast("باید از خال زمین (" + SUIT_NAMES[ledSuit()] + ") بدهی.");
      haptic("error");
      return;
    }
    if (picked !== code) {
      picked = code;
      haptic("light");
      drawHand(state);
      return;
    }
    send("hokm_play", { card: code });
  }

  // حکم دونفره: کارت رویی برای نفرِ نوبت؛ «برش دار» (زیری می‌سوزد) یا «بسوزان» (زیری ندیده مال تو)
  var shownDraw = "";
  function drawDrawPick() {
    var box = $("draw-pick");
    var show = myTurn() && state.phase === "draw" && !!state.draw_card;
    box.classList.toggle("hidden", !show);
    if (!show) { shownDraw = ""; return; }
    var key = state.draw_card + ":" + (state.hand || []).length;
    if (key !== shownDraw) {
      shownDraw = key;
      var slotBox = $("draw-card");
      slotBox.textContent = "";
      slotBox.appendChild(cardEl(state.draw_card, "in"));
    }
    var trump = state.draw_card[1] === state.trump;
    $("draw-note").textContent = (trump ? "⭐ این کارت حکم است. " : "") + "مانده در دسته: " + fa(state.deck) + " کارت";
    $("draw-keep").disabled = busy;
    $("draw-pass").disabled = busy;
  }

  // ------------------------------------------------------------------ وسط میز: انتخاب حکم، نتیجه‌ی دور
  function drawTrumpPick() {
    var box = $("trump-pick");
    var show = myTurn() && state.phase === "trump" && !noteTimer; // بعد از نمایش «تعیین حاکم»
    box.classList.toggle("hidden", !show);
    if (!show) return;
    var counts = { s: 0, h: 0, d: 0, c: 0 };
    (state.hand || []).forEach(function (c) { counts[c[1]] += 1; });
    var best = Object.keys(counts).sort(function (a, b) { return counts[b] - counts[a]; })[0];
    Array.prototype.forEach.call(box.querySelectorAll("button"), function (button) {
      var suit = button.dataset.suit;
      button.querySelector("i").textContent = counts[suit] ? fa(counts[suit]) + " کارت" : "—";
      button.classList.toggle("best", suit === best && counts[suit] > 0);
      button.disabled = busy;
    });
  }
  function note(text, extra, cls) {
    var box = $("center-note");
    box.textContent = "";
    box.className = cls || "";
    box.appendChild(el("b", "", text));
    if (extra) box.appendChild(el("p", "", extra));
    box.classList.remove("hidden");
  }
  function hideNote() { $("center-note").classList.add("hidden"); }
  function drawNote() {
    if (collecting || state.over) { hideNote(); return; }
    if (noteTimer) return; // پیام تعیین حاکم هنوز روی میز است
    if (state.phase === "draw" && !myTurn()) {
      note("🃏 " + name(state.turn) + " دارد کارت می‌کشد…", "هر کدام نوبتی کارت رویی را برمی‌دارید یا می‌سوزانید تا ۱۳ کارت.");
      return;
    }
    if (state.phase === "draw") { hideNote(); return; }
    if (state.phase === "trump" && !(myTurn())) {
      note("👑 " + name(state.hakem) + " دارد حکم را انتخاب می‌کند…", "حاکم از روی ۵ کارت اولش خال حکم را می‌گوید.");
      return;
    }
    if (state.phase === "pause" && state.result) {
      var r = state.result;
      var win = r.winner_team;
      var kot = r.kot === "hakem_kot" ? "💥 حاکم‌کُت! " : r.kot === "kot" ? "🔥 کُت! " : "";
      var title = seated() ? (win === myTeam() ? (solo() ? "🎉 این دور را بردی" : "🎉 این دور را بردیم") : (solo() ? "😕 این دور را " + name(win) + " برد" : "😕 این دور را حریف برد")) : "🎉 " + teamLabel(win) + " این دور را برد";
      note(title, kot + tally(r.tricks, win) + " — +" + fa(r.points) + " امتیاز. دور بعد چند ثانیه‌ی دیگر…", seated() && win === myTeam() ? "win" : "");
      return;
    }
    hideNote();
  }
  // دور اول: اولین آسی که رو شد حاکم را معلوم کرد
  function showIntro() {
    if (introShown || !state.draw || !state.draw.length || state.round !== 1 || state.phase !== "trump") return;
    introShown = true;
    var ace = state.draw[state.draw.length - 1];
    var box = $("center-note");
    box.textContent = "";
    box.className = "";
    box.appendChild(el("b", "", "تعیین حاکم"));
    var row = el("div", "");
    row.style.cssText = "display:flex;justify-content:center;gap:6px;margin-top:8px;direction:ltr";
    state.draw.slice(-4).forEach(function (pair) {
      var card = cardEl(pair[1], "");
      card.style.setProperty("--w", "38px");
      if (pair === ace) card.style.boxShadow = "0 0 0 3px #ffd166, 0 0 14px rgba(255,209,102,.8)";
      row.appendChild(card);
    });
    box.appendChild(row);
    box.appendChild(el("p", "", "کارت‌ها رو یکی‌یکی پخش شد تا اولین آس؛ آس به " + name(ace[0]) + " رسید و او حاکم است 👑"));
    box.classList.remove("hidden");
    sound("deal");
    noteTimer = setTimeout(function () { noteTimer = null; if (state) { drawNote(); drawTrumpPick(); } }, 2600);
  }

  // ------------------------------------------------------------------ زمان و وضعیت
  function msLeft() { return Math.max(0, leftBase - (now() - receivedAt)); }
  function armRing() {
    var circle = document.querySelector(".seat.turn .ring circle, #me-plate.turn .ring circle");
    if (!circle || state.over || !(state.phase === "play" || state.phase === "trump" || state.phase === "draw")) { ring.node = null; return; }
    var total = Math.max(1, state.move_seconds * 1000);
    var left = Math.min(total, msLeft());
    var end = now() + left;
    if (ring.node === circle && Math.abs(ring.end - end) < 700) return;
    ring.node = circle;
    ring.end = end;
    circle.style.transition = "none";
    circle.style.strokeDashoffset = (100 * (1 - left / total)).toFixed(2);
    circle.style.animation = "ring-color " + total + "ms linear " + (left - total).toFixed(0) + "ms both";
    void circle.getBoundingClientRect();
    circle.style.transition = "stroke-dashoffset " + left.toFixed(0) + "ms linear";
    circle.style.strokeDashoffset = "100";
  }
  function tick() {
    if (!state) return;
    if (myTurn()) {
      if (msLeft() < 7000 && !lowWarned) { lowWarned = true; sound("low"); haptic("warning"); }
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
    else if (state.phase === "pause") text = "⏳ دور بعد " + fa(seconds) + " ثانیه‌ی دیگر پخش می‌شود";
    else if (state.phase === "trump") {
      text = myTurn() ? "👑 تو حاکمی؛ حکم را انتخاب کن (" + fa(seconds) + " ثانیه)" : "👑 " + name(state.hakem) + " دارد حکم را انتخاب می‌کند (" + fa(seconds) + ")";
      cls = myTurn() ? "mine" : "";
    } else if (state.phase === "draw") {
      text = myTurn() ? "🃏 نوبت توست که بکشی (" + fa(seconds) + " ثانیه)" : "🃏 " + name(state.turn) + " می‌کشد (" + fa(seconds) + ")";
      cls = myTurn() ? "mine" : "";
    } else if (state.turn !== null && state.turn !== undefined) {
      var mine = myTurn();
      text = (mine ? "نوبت توست" : "نوبت " + name(state.turn)) + " (" + fa(seconds) + " ثانیه)";
      if (!mine && seated() && !solo() && state.turn === (state.you + 2) % 4) text += " — یارت";
      cls = mine ? (seconds <= 7 ? "warn" : "mine") : "";
    }
    if (box.textContent !== text) box.textContent = text;
    box.className = cls;
  }

  // ------------------------------------------------------------------ تاریخچه
  function drawHistory() {
    var body = $("history-body");
    body.textContent = "";
    var last = state.last_trick;
    var sec = el("section", "hist");
    sec.appendChild(el("h3", "", last ? "دست " + fa(last.no) + " (دست قبل)" : "هنوز دستی کامل نشده"));
    if (last) {
      last.plays.forEach(function (p) {
        var row = el("div", "row" + (p[0] === last.winner ? " win" : ""));
        row.appendChild(el("b", "", (p[0] === last.winner ? "🏆 " : "") + name(p[0])));
        row.appendChild(cardEl(p[1], "mini"));
        sec.appendChild(row);
      });
    }
    body.appendChild(sec);
    var rounds = el("section", "hist");
    rounds.appendChild(el("h3", "", "دورها"));
    var list = state.history || [];
    if (!list.length) rounds.appendChild(el("p", "", "هنوز دوری تمام نشده است."));
    list.forEach(function (r) {
      var kot = r.kot === "hakem_kot" ? " — حاکم‌کُت" : r.kot === "kot" ? " — کُت" : "";
      rounds.appendChild(el("p", "", "دور " + fa(r.round) + ": " + teamLabel(r.winner_team) + " " + tally(r.tricks, r.winner_team) + kot + " (+" + fa(r.points) + ") — حکم " + SUIT_NAMES[r.trump]));
    });
    body.appendChild(rounds);
  }

  // ------------------------------------------------------------------ گفت‌وگوی میز
  function chatSeat(message) {
    if (message.side && /^s\d+$/.test(message.side)) return Number(message.side.slice(1));
    return null;
  }
  function addChat(list, quiet) {
    if (!list || !list.length) return;
    var box = $("chat-list");
    var fresh = 0;
    list.forEach(function (message) {
      if (!message || message.id <= talk.last) return;
      talk.last = message.id;
      var item = el("div", "msg" + (message.mine ? " mine" : ""));
      item.appendChild(el("b", "", message.name || ""));
      item.appendChild(document.createTextNode(message.text));
      box.appendChild(item);
      if (quiet) return;
      bubble(message);
      if (!message.mine) fresh += 1;
    });
    while (box.children.length > 60) box.removeChild(box.firstChild);
    $("chat-empty").classList.toggle("hidden", box.children.length > 0);
    if (talk.open) box.scrollTop = box.scrollHeight;
    else if (fresh) talk.unread += fresh;
    if (fresh) { sound("move"); haptic("light"); }
    drawBadge();
  }
  function drawBadge() {
    var node = $("chat-badge");
    node.textContent = talk.unread > 9 ? "۹+" : fa(talk.unread);
    node.classList.toggle("hidden", !talk.unread);
  }
  function clamp(value, low, high) { return Math.max(low, Math.min(high, value)); }
  function bubble(message) {
    var seat = chatSeat(message);
    if (seat === null || !state || seat >= count()) return;
    var spot = SPOTS[slot(seat)];
    var node = el("div", "bubble" + (message.mine ? " mine" : ""), message.text);
    if (spot.y < 30) node.classList.add("below");
    var box = $("bubbles");
    Array.prototype.forEach.call(box.querySelectorAll('[data-seat="' + seat + '"]'), function (old) { old.remove(); });
    node.dataset.seat = seat;
    place(node, spot);
    box.appendChild(node);
    var width = box.offsetWidth || 1;
    var half = (node.offsetWidth / 2 / width) * 100 + 1;
    place(node, { x: clamp(spot.x, half, 100 - half), y: spot.y });
    setTimeout(function () { node.remove(); }, 4300);
  }
  function drawQuick() {
    var box = $("chat-quick");
    box.textContent = "";
    talk.quick.concat(state && solo() ? SOLO_QUICK : TABLE_QUICK).forEach(function (text) {
      var button = el("button", "", text);
      button.type = "button";
      button.addEventListener("click", function () { say(text); });
      box.appendChild(button);
    });
  }
  function drawChatAccess() {
    var open = talk.can && !talk.locked;
    $("chat-form").classList.toggle("hidden", !open);
    $("chat-quick").classList.toggle("hidden", !open);
    $("chat-note").classList.toggle("hidden", talk.can || talk.locked);
    $("chat-locked").classList.toggle("hidden", !talk.locked);
    $("chat-lock").classList.toggle("hidden", !talk.can || talk.locked);
    $("chat-lock").disabled = talk.voted;
    $("chat-btn").classList.toggle("locked", talk.locked);
  }
  // بستن گفت‌وگو: اگر حریف با پیام‌ها تقلب (علامت دادن) می‌کند؛ وقتی هر دو نفر یک تیم (در سه‌نفره دو نفر از سه نفر) بزنند
  // گفت‌وگو تا آخر همین بازی برای همه بسته می‌شود
  function lockChat() {
    if (!talk.can || talk.locked || talk.voted) return;
    talk.voted = true;
    drawChatAccess();
    api("board/chat_lock", {}).then(function (response) {
      if (!response.ok) { talk.voted = false; drawChatAccess(); toast(errorText(response.error)); return; }
      if (response.chat_locked) setLocked(true);
      else {
        $("chat-lock-note").textContent = "رأی تو ثبت شد (" + fa(response.votes) + " از " + fa(response.need) + ")؛ " +
          (solo() ? "اگر یک نفر دیگر هم بزند" : "اگر یارت هم بزند") + " گفت‌وگو بسته می‌شود.";
        toast("رأی بستن گفت‌وگو ثبت شد", true);
      }
      drawChatAccess();
    });
  }
  function setLocked(locked) {
    if (!locked || talk.locked) return;
    talk.locked = true;
    $("chat-lock-note").textContent = "";
    toast("🔒 گفت‌وگوی این میز تا پایان بازی بسته شد", true);
    drawChatAccess();
  }
  function say(text) {
    text = String(text || "").trim();
    if (!text) { $("chat-input").focus(); return; }
    if (talk.sending) return;
    talk.sending = true;
    $("chat-send").disabled = true;
    api("board/chat", { text: text, chat_after: talk.last }).then(function (response) {
      talk.sending = false;
      $("chat-send").disabled = false;
      if (!response.ok) {
        if (response.error === "chat_locked") setLocked(true);
        toast(errorText(response.error)); haptic("error"); return;
      }
      $("chat-input").value = "";
      addChat(response.chat);
    });
  }

  // ------------------------------------------------------------------ نتیجه
  function resultTitle() {
    var over = state.over;
    if (!over) return "";
    var win = over.winner_team;
    if (solo()) return seated() && win === state.you ? "🏆 تو بردی!" : (seated() ? "😔 " : "🏆 ") + name(win) + " برد";
    if (!seated()) return "🏆 " + teamLabel(win) + " (" + pairNames(win) + ") برد";
    return win === myTeam() ? "🏆 تیم شما برد!" : "😔 تیم حریف برد";
  }
  function confetti() {
    var box = $("confetti");
    var colors = ["#ffc857", "#6ee7ff", "#4f8cff", "#34d399", "#ff9f43", "#ffffff"];
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
  function drawResultList() {
    var list = $("result-list");
    list.textContent = "";
    var win = state.over.winner_team;
    var order = solo()
      ? [win].concat(state.seats.map(function (s) { return s.seat; }).filter(function (s) { return s !== win; }).sort(function (a, b) { return state.points[b] - state.points[a]; }))
      : [win, win + 2, 1 - win, 3 - win];
    order.forEach(function (seat) {
      var item = el("li", "t" + team(seat) + (seated() && seat === state.you ? " me" : ""));
      item.appendChild(el("span", "", (team(seat) === win ? "🏆 " : "") + name(seat)));
      var prizes = state.prizes || null;
      var coins = prizes && prizes["s" + seat] !== undefined ? prizes["s" + seat] : null;
      var fallback = state.over.reason === "left" && team(seat) === win ? "برنده" : fa(state.points[team(seat)]) + " امتیاز";
      item.appendChild(el("small", "", coins !== null ? (coins ? "+" + money(coins) + " سکه" : "—") : fallback));
      list.appendChild(item);
    });
    var mine = $("result-mine");
    var own = seated() && state.prizes ? state.prizes["s" + state.you] : 0;
    mine.classList.toggle("hidden", !own);
    if (own) mine.textContent = "💰 " + money(own) + " سکه به کیف پولت واریز شد";
  }
  function showResult() {
    if (resultShown) { drawResultList(); return; }
    resultShown = true;
    drawResultList();
    var over = state.over;
    var won = seated() && over.winner_team === myTeam();
    $("result-icon").textContent = won ? "🏆" : "♠️";
    $("result-title").textContent = resultTitle().replace(/^🏆 /, "");
    $("result-reason").textContent = over.reason === "left"
      ? name(over.left_seat) + (solo() ? " بازی را ترک کرد." : " بازی را ترک کرد؛ تیمش باخت.")
      : solo() ? "امتیاز " + tally(state.points, over.winner_team) + " — برنده کل جایزه را می‌برد."
        : "امتیاز " + fa(state.points[0]) + " به " + fa(state.points[1]) + " — تیم برنده جایزه را نصف‌نصف می‌برد.";
    setTimeout(function () {
      $("result").classList.remove("hidden");
      if (won) confetti();
    }, 1500);
    sound(won ? "win" : seated() ? "lose" : "draw");
    haptic("success");
  }
  function fetchPrizes() {
    if (!state || !state.over || state.prizes || prizeTries >= 8 || prizeTimer) return;
    prizeTries += 1;
    prizeTimer = setTimeout(function () {
      api("board/state", { chat_after: talk.last }).then(function (response) {
        prizeTimer = null;
        if (response.ok) apply(response);
      });
    }, 2500);
  }

  // ------------------------------------------------------------------ دریافت وضعیت
  function react(previous) {
    if (!previous) return;
    if (previous.round !== state.round) sound("deal");
    var played = state.last_action && previous.last_action !== state.last_action &&
      JSON.stringify(previous.last_action) !== JSON.stringify(state.last_action);
    if (played && state.last_action.kind === "play") sound("move");
    if (played && state.last_action.kind === "draw") sound(state.last_action.keep ? "deal" : "chip");
    if (played && state.last_action.kind === "trump") { sound("chips"); toast("حکم: " + SUITS[state.trump] + " " + SUIT_NAMES[state.trump], true); }
    var wasMine = previous.turn === previous.you && previous.you !== null && previous.phase === state.phase;
    if (myTurn() && !wasMine) { sound("turn"); haptic("medium"); }
  }
  var dressed = false;
  // یک بار: عنوان و متن‌های مخصوص حکم سه‌نفره
  function dress() {
    if (dressed) return;
    dressed = true;
    document.body.classList.toggle("solo", solo());
    if (!solo()) return;
    document.title = duo() ? "حکم دونفره" : "حکم سه‌نفره";
    $("game-title").textContent = duo() ? "♥️ حکم دونفره" : "👑 حکم سه‌نفره";
    $("chat-empty").textContent = "هنوز پیامی نیست؛ سلام کن 👋";
    $("leave-note").textContent = "اگر بروی، بازی برای تو تمام می‌شود و می‌بازی؛ جایزه به نفری می‌رسد که امتیاز بیشتری دارد.";
    if (talk.quick.length) drawQuick();
  }
  function render(previous) {
    dress();
    drawScores();
    drawTrump();
    drawSeats();
    drawTrick(previous);
    drawHand(previous);
    showIntro(); // قبل از پنجره‌ی انتخاب حکم، تا «تعیین حاکم» زیر آن پنهان نماند
    drawTrumpPick();
    drawDrawPick();
    drawNote();
    tick();
    armRing();
    react(previous);
    $("resign-btn").classList.toggle("hidden", !seated());
    $("resign-btn").disabled = !seated() || !!state.over || !!state.cancelled;
    if (!$("history").classList.contains("hidden")) drawHistory();
    if (state.over) { showResult(); fetchPrizes(); }
  }
  function apply(response) {
    if (!response.ok) {
      toast(errorText(response.error));
      haptic("error");
      return false;
    }
    receivedAt = now();
    if (response.chat_locked) setLocked(true);
    if (response.can_chat !== undefined) {
      talk.can = !!response.can_chat;
      if (response.quick && !talk.quick.length) { talk.quick = response.quick; drawQuick(); }
      drawChatAccess();
    }
    if (response.chat) {
      addChat(response.chat, !talk.loaded);
      talk.loaded = true;
    } else if (response.changed !== false) talk.loaded = true;
    if (response.changed === false) {
      leftBase = response.left_ms !== undefined ? response.left_ms : response.seconds_left * 1000;
      tick();
      armRing();
      return true;
    }
    var previous = state;
    real = response.state;
    state = real;
    leftBase = real.left_ms !== undefined ? real.left_ms : real.seconds_left * 1000;
    if (!previous && state.last_trick) shownTrick = state.last_trick.no; // دست‌های قبل از باز شدن صفحه نمایش داده نمی‌شوند
    if (previous && previous.round !== state.round) shownTrick = 0; // شماره‌ی دست‌ها در هر دور از ۱ شروع می‌شود
    render(previous);
    return true;
  }
  function pollDelay() {
    if (!state || state.over || state.cancelled) return 5000;
    if (myTurn()) return talk.open ? 1200 : 1500;
    return 800;
  }
  function loop() {
    clearTimeout(pollTimer);
    pollTimer = setTimeout(function () {
      if (document.hidden || busy || !state) { loop(); return; }
      api("board/state", { version: real.version, chat_after: talk.last }).then(function (response) {
        if (!busy && response.ok) apply(response);
        loop();
      });
    }, pollDelay());
  }
  function send(kind, extra) {
    if (!state || busy) return;
    busy = true;
    picked = null;
    haptic("light");
    var body = { action: kind, chat_after: talk.last };
    Object.keys(extra || {}).forEach(function (k) { body[k] = extra[k]; });
    api("board/action", body).then(function (response) {
      busy = false;
      if (!apply(response)) { loop(); if (state) render(state); }
    });
  }
  function fail(text) {
    $("loading-text").textContent = text;
    document.querySelector("#loading .spinner").classList.add("hidden");
  }

  // ------------------------------------------------------------------ دکمه‌ها
  Array.prototype.forEach.call(document.querySelectorAll("#trump-pick button"), function (button) {
    button.addEventListener("click", function () {
      if (!myTurn() || state.phase !== "trump") return;
      send("hokm_trump", { suit: button.dataset.suit });
    });
  });
  $("draw-keep").addEventListener("click", function () { if (myTurn() && state.phase === "draw") send("hokm_draw", { keep: true }); });
  $("draw-pass").addEventListener("click", function () { if (myTurn() && state.phase === "draw") send("hokm_draw", { keep: false }); });
  function openSheet(id) {
    if (id === "history") drawHistory();
    if (id === "chat") {
      talk.open = true;
      talk.unread = 0;
      drawBadge();
      drawChatAccess();
      setTimeout(function () { $("chat-list").scrollTop = $("chat-list").scrollHeight; }, 30);
    }
    $(id).classList.remove("hidden");
    haptic("light");
  }
  function closeSheet(sheet) {
    sheet.classList.add("hidden");
    if (sheet.id === "chat") { talk.open = false; $("chat-input").blur(); }
  }
  $("history-btn").addEventListener("click", function () { if (state) openSheet("history"); });
  $("chat-btn").addEventListener("click", function () { if (state) openSheet("chat"); });
  $("resign-btn").addEventListener("click", function () { if (state && seated() && !state.over) openSheet("leave"); });
  $("leave-yes").addEventListener("click", function () { closeSheet($("leave")); send("resign"); });
  Array.prototype.forEach.call(document.querySelectorAll(".sheet"), function (sheet) {
    sheet.addEventListener("click", function (event) {
      if (event.target === sheet || event.target.classList.contains("sheet-close")) closeSheet(sheet);
    });
  });
  $("chat-lock").addEventListener("click", lockChat);
  $("chat-form").addEventListener("submit", function (event) {
    event.preventDefault();
    say($("chat-input").value);
  });
  function soundButton() { $("sound-btn").textContent = window.SFX && window.SFX.isMuted() ? "🔇" : "🔊"; }
  $("sound-btn").addEventListener("click", function () {
    if (!window.SFX) return;
    window.SFX.setMuted(!window.SFX.isMuted());
    soundButton();
    if (!window.SFX.isMuted()) setTimeout(function () { sound("chip"); }, 60);
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
      if (tg.setHeaderColor) tg.setHeaderColor("#06201d");
      if (tg.setBackgroundColor) tg.setBackgroundColor("#04110f");
      if (tg.disableVerticalSwipes) tg.disableVerticalSwipes();
    } catch (e) { /* نسخه‌های قدیمی */ }
  }
  if (!initData) { fail(errorText("auth_missing")); return; }
  api("board/state", { chat_after: 0 }).then(function (response) {
    if (!response.ok) { fail(errorText(response.error)); return; }
    $("loading").classList.add("hidden");
    $("game").classList.remove("hidden");
    apply(response);
    loop();
    setInterval(tick, 250);
    var resizeTimer = null;
    window.addEventListener("resize", function () {
      clearTimeout(resizeTimer);
      resizeTimer = setTimeout(function () { if (state) drawHand(state); }, 150);
    });
    document.addEventListener("visibilitychange", function () {
      if (document.hidden || busy || !state) return;
      api("board/state", { version: real.version, chat_after: talk.last }).then(function (response) { if (!busy && response.ok) apply(response); });
    });
  });
})();
