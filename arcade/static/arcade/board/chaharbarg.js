/* میز چهاربرگ (پاسور) مینی‌اپ. همه‌ی قوانین و کارت‌ها در سرور است؛ سرور فقط کارت‌های خود بازیکن را می‌فرستد و در نوبت
   تو برای هر کارت همه‌ی راه‌های برداشتن را هم می‌دهد (``options``).
   صندلی‌ها نسبت به بیننده: خودت پایین؛ در دونفره حریف بالا، در سه‌نفره راست و چپ و در چهارنفره راست، بالا و چپ.
   کارت‌های زمین وسط میزند. کارت دستت را لمس کن تا بالا بیاید؛ زیر میز راه‌های برداشتن (کارت‌هایی که با آن جمع ۱۱
   می‌شوند، یا شاه با شاه، بی‌بی با بی‌بی، سرباز همه‌ی زمین جز شاه و بی‌بی) و «زمین بگذار» می‌آید. کارت‌هایی که با
   برداشتن جمع می‌شوند به سمت برداشت‌کننده پرواز می‌کنند و «سور» (جارو کردن کل زمین) جشن کوچکی دارد.
   کارت‌های دستت از راست به چپ بر اساس بزرگی چیده می‌شوند (بزرگ‌ترین سمت راست). */
(function () {
  "use strict";

  var BOOT = window.BOARD_BOOT;
  var tg = window.Telegram && window.Telegram.WebApp ? window.Telegram.WebApp : null;
  var query = new URLSearchParams(location.search);
  var initData = tg && tg.initData ? tg.initData : "";
  if (!initData && BOOT.devAuth && query.get("dev_user")) initData = "dev:" + query.get("dev_user");

  var SUITS = { s: "♠", h: "♥", d: "♦", c: "♣" };
  var RANKS = "A23456789TJQK";
  var RANK_NAMES = { A: "آس", J: "سرباز", Q: "بی‌بی", K: "شاه", T: "۱۰" };
  var ERRORS = {
    not_your_turn: "نوبت تو نیست.",
    illegal_move: "این برداشت مجاز نیست.",
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
  var COLORS = ["#4f8cff", "#ff9f43", "#c084fc", "#34d399"];
  // چهار جای ممکن روی میز (درصد): خودت، راست، بالا، چپ؛ و جای صندلی‌ها بسته به تعداد بازیکن
  var SPOTS = [{ x: 50, y: 90 }, { x: 87, y: 45 }, { x: 50, y: 12 }, { x: 13, y: 45 }];
  var SLOTS = { 2: [0, 2], 3: [0, 1, 3], 4: [0, 1, 2, 3] };
  var TABLE_QUICK = ["👏 برداشت خوبی بود", "🧹 سور!", "😅 ببخشید", "🍀 موفق باشی", "🤝 بازی خوبی بود"];

  var real = null;
  var state = null;
  var busy = false;
  var receivedAt = 0;
  var leftBase = 0;
  var picked = null;
  var resultShown = false;
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
  function count() { return state.seats.length; }
  function seated() { return state.you !== null && state.you !== undefined; }
  function base() { return seated() ? state.you : 0; }
  function rel(seat) { return (seat - base() + count()) % count(); }
  function slot(seat) { return (SLOTS[count()] || SLOTS[4])[rel(seat)]; }
  function name(seat) { return state.players["s" + seat] || ""; }
  function who(seat) { return seated() && seat === state.you ? "تو" : name(seat); }
  function badge(seat) {
    var profile = (state.profiles || {})["s" + seat];
    return profile && profile.emoji ? profile.emoji + " " : "";
  }
  function initial(seat) { return (name(seat).trim()[0] || "؟").toUpperCase(); }
  function myTurn() { return seated() && !state.over && state.phase === "play" && state.turn === state.you; }
  function rank(code) { return RANKS.indexOf(code[0]); }
  function label(code) { return (code[0] === "T" ? "10" : code[0]) + SUITS[code[1]]; }
  function longLabel(code) { return (RANK_NAMES[code[0]] || code[0]) + " " + SUITS[code[1]]; }

  // ------------------------------------------------------------------ کارت
  function cardEl(code, extra) {
    var card = el("span", "pcard" + (extra ? " " + extra : ""));
    if (!code) { card.classList.add("back"); return card; }
    var suit = SUITS[code[1]];
    if (code[1] === "h" || code[1] === "d") card.classList.add("red");
    var index = el("span", "idx");
    index.appendChild(el("b", "", code[0] === "T" ? "10" : code[0]));
    index.appendChild(el("i", "", suit));
    card.appendChild(index);
    card.appendChild(el("span", "pip", suit));
    if (code === "Td" || code === "2c") card.classList.add("gem"); // ۱۰ خشت و ۲ گشنیز امتیاز دارند
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
    if (state.seats[seat] && state.seats[seat].dealer) node.appendChild(el("i", "crown dealer", "🎴"));
    return node;
  }

  // ------------------------------------------------------------------ امتیازها
  function drawScores() {
    var box = $("scores");
    box.textContent = "";
    box.classList.toggle("n4", count() > 3);
    var best = Math.max.apply(null, state.points);
    var order = state.seats.map(function (s) { return s.seat; }).sort(function (a, b) { return rel(a) - rel(b); });
    order.forEach(function (seat) {
      var s = state.seats[seat];
      var pill = el("div", "team" + (seated() && seat === state.you ? " me" : ""));
      pill.style.setProperty("--c", COLORS[seat % COLORS.length]);
      if (state.points[seat] === best && best > 0) pill.classList.add("lead");
      if (s.left) pill.classList.add("gone");
      pill.appendChild(el("b", "name", who(seat)));
      var pts = el("span", "pts", fa(state.points[seat]));
      pill.appendChild(pts);
      var info = "🃏" + fa(s.captured) + "  ♣" + fa(s.clubs) + (s.surs ? "  🧹" + fa(s.surs) : "");
      pill.appendChild(el("small", "tricks", info));
      box.appendChild(pill);
    });
    $("target-chip").textContent = state.target ? "تا " + fa(state.target) + " امتیاز" : "یک دست";
    $("deck-count").textContent = fa(state.deck);
    $("deck-chip").classList.toggle("empty", !state.deck);
  }

  // ------------------------------------------------------------------ صندلی‌ها
  function drawSeats() {
    var box = $("seats");
    box.textContent = "";
    state.seats.forEach(function (s) {
      var r = slot(s.seat);
      var turn = !state.over && state.phase === "play" && state.turn === s.seat;
      var color = COLORS[s.seat % COLORS.length];
      if (seated() && s.seat === state.you) {
        var me = el("div", "");
        me.id = "me-plate";
        me.style.setProperty("--c", color);
        if (turn) me.classList.add("turn");
        me.appendChild(avatar(s.seat));
        me.appendChild(el("b", "", badge(s.seat) + name(s.seat) + " (تو)"));
        box.appendChild(me);
        return;
      }
      var seat = el("div", "seat" + (r === 1 ? " at-right" : r === 3 ? " at-left" : r === 2 ? " at-top" : ""));
      seat.style.setProperty("--c", color);
      if (turn) seat.classList.add("turn");
      if (s.left) seat.classList.add("left");
      seat.appendChild(avatar(s.seat));
      if (s.count && state.phase !== "over") {
        var backs = el("div", "backs");
        for (var i = 0; i < Math.min(4, s.count); i++) backs.appendChild(cardEl("", ""));
        seat.appendChild(backs);
      }
      var plate = el("div", "plate");
      plate.appendChild(el("b", "", badge(s.seat) + name(s.seat)));
      plate.appendChild(el("small", "", fa(s.count) + " کارت · " + fa(state.points[s.seat]) + " امتیاز"));
      seat.appendChild(plate);
      if (s.left) seat.appendChild(el("span", "tag left", "رفت"));
      else if (s.away) seat.appendChild(el("span", "tag away", "غایب؛ خودکار"));
      place(seat, SPOTS[r]);
      box.appendChild(seat);
    });
  }

  // ------------------------------------------------------------------ کارت‌های زمین
  function pickedOptions() {
    if (!picked || !state.options) return [];
    return state.options[picked] || [];
  }
  function drawPile(previous) {
    var box = $("pile");
    var table = state.table || [];
    var before = {};
    if (previous) (previous.table || []).forEach(function (c) { before[c] = true; });
    var hot = {};
    pickedOptions().forEach(function (option) { option.forEach(function (c) { hot[c] = true; }); });
    box.textContent = "";
    box.style.setProperty("--pw", table.length > 10 ? "calc(var(--cw) * .66)" : table.length > 6 ? "calc(var(--cw) * .8)" : "var(--cw)");
    if (!table.length && state.phase === "play") box.appendChild(el("p", "empty", "زمین خالی است"));
    table.forEach(function (code, i) {
      var card = cardEl(code, (previous && !before[code] ? "in" : "") + (hot[code] ? " hot" : "") + (picked && !hot[code] ? " cold" : ""));
      card.style.setProperty("--r", (((i * 37) % 9) - 4) + "deg");
      box.appendChild(card);
    });
  }
  // برداشتن: کارت بازی‌شده و کارت‌های برداشته‌شده وسط میز جمع می‌شوند و به سمت برداشت‌کننده پرواز می‌کنند
  function flyCapture(action) {
    var box = $("fly");
    var cards = [action.card].concat(action.take || []);
    var target = SPOTS[slot(action.seat)];
    var nodes = [];
    var width = 7 * Math.min(cards.length, 6);
    cards.forEach(function (code, i) {
      var card = cardEl(code, "in" + (i === 0 ? " lead" : ""));
      card.style.setProperty("--r", ((i - (cards.length - 1) / 2) * 6).toFixed(1) + "deg");
      place(card, { x: 50 - width / 2 + (cards.length > 1 ? (width * i) / (cards.length - 1) : width / 2), y: 47 });
      box.appendChild(card);
      nodes.push(card);
    });
    setTimeout(function () {
      nodes.forEach(function (card) { place(card, target); card.classList.add("gone"); });
      setTimeout(function () { nodes.forEach(function (card) { card.remove(); }); }, 420);
    }, 720);
    if (action.sur) burst(action.seat);
  }
  function burst(seat) {
    var box = $("center-note");
    box.className = "sur";
    box.textContent = "";
    box.appendChild(el("b", "", "🧹 سور!"));
    box.appendChild(el("p", "", who(seat) + " همه‌ی زمین را جارو کرد — +۵ امتیاز"));
    box.classList.remove("hidden");
    sound("win");
    haptic("success");
    clearTimeout(noteTimer);
    noteTimer = setTimeout(function () { noteTimer = null; if (state) drawNote(); }, 1800);
  }

  // ------------------------------------------------------------------ کارت‌های خودت
  function sortedHand() {
    // کوچک به بزرگ از چپ؛ یعنی از راست به چپ از بزرگ به کوچک (بزرگ‌ترین کارت سمت راست)
    return (state.hand || []).slice().sort(function (a, b) { return rank(a) - rank(b) || "cdhs".indexOf(a[1]) - "cdhs".indexOf(b[1]); });
  }
  function drawHand(previous) {
    var box = $("hand");
    var hand = sortedHand();
    var playing = myTurn() && !busy;
    if (picked && (!playing || hand.indexOf(picked) < 0)) picked = null;
    var fresh = !previous || (previous.hand || []).length < hand.length;
    box.textContent = "";
    box.classList.toggle("myturn", playing);
    var width = box.clientWidth || 360;
    var cardW = parseFloat(getComputedStyle(box).getPropertyValue("--hw")) || Math.min(width * 0.18, 72);
    var n = hand.length;
    var step = n > 1 ? Math.min(cardW * 0.92, (width - cardW - 24) / (n - 1)) : 0;
    var start = (width - (cardW + step * (n - 1))) / 2;
    var mid = (n - 1) / 2;
    hand.forEach(function (code, i) {
      var can = playing && (state.options[code] || []).length > 0;
      var card = cardEl(code, (code === picked ? "pick" : "") + (fresh ? " deal" : "") + (can ? " can" : ""));
      card.style.setProperty("--x", (start + i * step).toFixed(1) + "px");
      card.style.setProperty("--r", ((i - mid) * 3).toFixed(2) + "deg");
      card.style.setProperty("--y", (Math.pow(i - mid, 2) * 1.6).toFixed(1) + "px");
      if (fresh) card.style.animationDelay = (i * 0.05).toFixed(2) + "s";
      card.addEventListener("click", function () { tapCard(code); });
      box.appendChild(card);
    });
    var hint = "";
    if (playing) hint = picked ? "برداشت را از زیر میز انتخاب کن یا کارت دیگری بزن" : "یک کارت را لمس کن؛ کارت‌های سبز چیزی از زمین برمی‌دارند";
    else if (seated() && !state.over && state.phase === "play") hint = "منتظر نوبت " + name(state.turn) + "…";
    $("hand-hint").textContent = hint;
  }
  function tapCard(code) {
    if (!state || state.over) return;
    if (!myTurn()) { toast("نوبت تو نیست.", true); return; }
    if (busy) return;
    picked = picked === code ? null : code;
    haptic("light");
    drawHand(state);
    drawPile(null);
    drawChoices();
  }
  // راه‌های برداشتن کارت انتخاب‌شده؛ و «زمین بگذار» (سرباز اگر بتواند برداشتن را جا نمی‌گذارد)
  function drawChoices() {
    var box = $("choices");
    box.textContent = "";
    if (!picked || !myTurn() || busy) { box.classList.add("hidden"); return; }
    var options = pickedOptions();
    var lastCard = !state.deck && state.seats.every(function (s) { return s.count === (s.seat === state.you ? 1 : 0); });
    box.appendChild(el("b", "head", "با " + longLabel(picked) + ":"));
    options.forEach(function (option) {
      var button = el("button", "take");
      button.type = "button";
      var row = el("span", "cards");
      option.forEach(function (c) { row.appendChild(cardEl(c, "mini")); });
      button.appendChild(el("em", "", "بردار"));
      button.appendChild(row);
      var bonus = option.concat([picked]).filter(function (c) { return c === "Td" || c === "2c" || c[0] === "A" || c[0] === "J"; }).length;
      if (option.length === (state.table || []).length && picked[0] !== "J" && !lastCard) button.appendChild(el("i", "sur-tag", "سور +۵"));
      else if (bonus) button.appendChild(el("i", "", "⭐ " + fa(bonus)));
      button.addEventListener("click", function () { play(picked, option); });
      box.appendChild(button);
    });
    if (!(picked[0] === "J" && options.length)) {
      var lay = el("button", "lay", options.length ? "نه، زمین بگذار" : "🂠 زمین بگذار");
      lay.type = "button";
      lay.addEventListener("click", function () { play(picked, []); });
      box.appendChild(lay);
    }
    box.classList.remove("hidden");
  }
  function play(card, take) {
    if (!card) return;
    send("cb_play", { card: card, take: take });
  }

  // ------------------------------------------------------------------ وسط میز و وضعیت
  function note(text, extra, cls) {
    var box = $("center-note");
    box.textContent = "";
    box.className = cls || "";
    box.appendChild(el("b", "", text));
    if (extra) {
      if (typeof extra === "string") box.appendChild(el("p", "", extra));
      else box.appendChild(extra);
    }
    box.classList.remove("hidden");
  }
  function hideNote() { $("center-note").classList.add("hidden"); }
  function roundTable(rows) {
    var table = el("div", "round-rows");
    rows.forEach(function (row, seat) {
      var line = el("div", "rr" + (seated() && seat === state.you ? " me" : ""));
      line.style.setProperty("--c", COLORS[seat % COLORS.length]);
      line.appendChild(el("b", "", who(seat)));
      var bits = [];
      if (row.clubs_bonus) bits.push("♣۷");
      if (row.ten_diamonds) bits.push("۱۰♦");
      if (row.two_clubs) bits.push("۲♣");
      if (row.aces) bits.push("آس " + fa(row.aces));
      if (row.jacks) bits.push("سرباز " + fa(row.jacks));
      if (row.surs) bits.push("سور " + fa(row.surs));
      line.appendChild(el("small", "", bits.join(" · ") || "—"));
      line.appendChild(el("i", "", "+" + fa(row.total)));
      table.appendChild(line);
    });
    return table;
  }
  function drawNote() {
    if (noteTimer) return;
    if (state.over) { hideNote(); return; }
    if (state.phase === "pause" && state.result) {
      note("🃏 دست " + fa(state.result.round) + " تمام شد", roundTable(state.result.rows), "round");
      return;
    }
    hideNote();
  }
  function msLeft() { return Math.max(0, leftBase - (now() - receivedAt)); }
  function armRing() {
    var circle = document.querySelector(".seat.turn .ring circle, #me-plate.turn .ring circle");
    if (!circle || state.over || state.phase !== "play") { ring.node = null; return; }
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
    else if (state.phase === "pause") text = "⏳ دست بعد " + fa(seconds) + " ثانیه‌ی دیگر پخش می‌شود";
    else if (state.turn !== null && state.turn !== undefined) {
      var mine = myTurn();
      text = (mine ? "نوبت توست" : "نوبت " + name(state.turn)) + " (" + fa(seconds) + " ثانیه)";
      cls = mine ? (seconds <= 7 ? "warn" : "mine") : "";
    }
    if (box.textContent !== text) box.textContent = text;
    box.className = cls;
  }

  // ------------------------------------------------------------------ امتیازها و قانون‌ها
  function drawHistory() {
    var body = $("history-body");
    body.textContent = "";
    if (state.result) {
      var last = el("section", "hist");
      last.appendChild(el("h3", "", "دست " + fa(state.result.round)));
      last.appendChild(roundTable(state.result.rows));
      body.appendChild(last);
    }
    var rounds = el("section", "hist");
    rounds.appendChild(el("h3", "", "دست‌ها"));
    var list = state.history || [];
    if (!list.length) rounds.appendChild(el("p", "", "هنوز دستی تمام نشده است."));
    list.forEach(function (r) {
      rounds.appendChild(el("p", "", "دست " + fa(r.round) + ": " + r.totals.map(function (t, seat) { return who(seat) + " +" + fa(t); }).join("، ")));
    });
    body.appendChild(rounds);
    var rules = el("section", "hist");
    rules.appendChild(el("h3", "", "قانون‌ها"));
    [
      "هر کارت عددی کارت‌هایی از زمین را برمی‌دارد که جمعشان با آن ۱۱ شود (آس = ۱).",
      "شاه فقط شاه و بی‌بی فقط بی‌بی برمی‌دارد؛ سرباز همه‌ی زمین را جز شاه و بی‌بی جمع می‌کند.",
      "اگر کل زمین را جارو کنی «سور» است: ۵ امتیاز (با سرباز و کارت آخر سور حساب نمی‌شود).",
      "امتیاز: بیشترین گشنیز ۷، ده خشت ۳، دو گشنیز ۲، هر آس ۱ و هر سرباز ۱.",
      "کارت‌های آخر زمین به آخرین کسی می‌رسد که چیزی برداشته است.",
    ].forEach(function (line) { rules.appendChild(el("p", "", "• " + line)); });
    body.appendChild(rules);
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
    talk.quick.concat(TABLE_QUICK).forEach(function (text) {
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
  // بستن گفت‌وگو وقتی کسی با پیام‌ها تقلب (علامت دادن) می‌کند: با رأی اکثر بازیکن‌ها تا آخر همین بازی بسته می‌شود
  function lockChat() {
    if (!talk.can || talk.locked || talk.voted) return;
    talk.voted = true;
    drawChatAccess();
    api("board/chat_lock", {}).then(function (response) {
      if (!response.ok) { talk.voted = false; drawChatAccess(); toast(errorText(response.error)); return; }
      if (response.chat_locked) setLocked(true);
      else {
        $("chat-lock-note").textContent = "رأی تو ثبت شد (" + fa(response.votes) + " از " + fa(response.need) + ")؛ اگر بقیه هم بزنند گفت‌وگو بسته می‌شود.";
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
    if (!state.over) return "";
    var win = state.winner_seat;
    if (win === null || win === undefined) return "🤝 مساوی شد";
    if (seated() && win === state.you) return "🏆 تو بردی!";
    return (seated() ? "😔 " : "🏆 ") + name(win) + " برد";
  }
  function confetti() {
    var box = $("confetti");
    var colors = ["#ffc857", "#6ee7ff", "#c084fc", "#34d399", "#ff9f43", "#ffffff"];
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
    var order = state.seats.map(function (s) { return s.seat; }).sort(function (a, b) { return state.points[b] - state.points[a]; });
    order.forEach(function (seat) {
      var item = el("li", seated() && seat === state.you ? "me" : "");
      item.style.background = "color-mix(in srgb, " + COLORS[seat % COLORS.length] + " 14%, transparent)";
      item.appendChild(el("span", "", (seat === state.winner_seat ? "🏆 " : "") + name(seat) + (state.seats[seat].left ? " (رفت)" : "")));
      var prizes = state.prizes || null;
      var coins = prizes && prizes["s" + seat] !== undefined ? prizes["s" + seat] : null;
      item.appendChild(el("small", "", coins !== null ? (coins ? "+" + money(coins) + " سکه" : fa(state.points[seat]) + " امتیاز") : fa(state.points[seat]) + " امتیاز"));
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
    var won = seated() && state.winner_seat === state.you;
    $("result-icon").textContent = won ? "🏆" : "🀄";
    $("result-title").textContent = resultTitle().replace(/^🏆 /, "");
    $("result-reason").textContent = state.over.reason === "left"
      ? name(state.over.left_seat) + " بازی را ترک کرد."
      : "امتیازها: " + state.seats.map(function (s) { return who(s.seat) + " " + fa(state.points[s.seat]); }).join(" · ");
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
    var action = state.last_action;
    var fresh = action && JSON.stringify(previous.last_action) !== JSON.stringify(action);
    if (fresh && action.kind === "play") {
      if (action.take && action.take.length) { flyCapture(action); sound("chips"); }
      else sound("move");
    }
    var wasMine = previous.turn === previous.you && previous.you !== null && previous.phase === "play";
    if (myTurn() && !wasMine) { sound("turn"); haptic("medium"); }
  }
  function render(previous) {
    drawScores();
    drawSeats();
    drawPile(previous);
    drawHand(previous);
    drawChoices();
    drawNote();
    tick();
    armRing();
    react(previous);
    $("resign-btn").classList.toggle("hidden", !seated());
    $("resign-btn").disabled = !seated() || !!state.over || !!state.cancelled || state.seats[state.you].left;
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
    $("choices").classList.add("hidden");
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
      if (tg.setHeaderColor) tg.setHeaderColor("#1a0d24");
      if (tg.setBackgroundColor) tg.setBackgroundColor("#0d0614");
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
