/* میز پوکر مینی‌اپ. همه‌ی قوانین و کارت‌ها در سرور است؛ سرور فقط کارت‌های خود بازیکن را می‌فرستد.
   این فایل میز را مثل اپ‌های پوکر موبایل می‌کشد: صندلی‌ها با جای ثابت دور میز (بسته به تعداد نفرات)، ستون
   ژتون شرط جلوی هر نفر، دکمه‌ی دیلر، حلقه‌ی زمان نوبت، کارت‌هایی که پخش می‌شوند و برمی‌گردند، پات‌های جانبی و
   در آل‌این باز شدن کارت‌های وسط یکی‌یکی.

   میز نقدی است: هر ژتون سهم ثابتی از سکه‌های میز است، پس کنار ژتون‌ها ارزش سکه‌ای‌شان هم نشان داده می‌شود و
   «بلند شدن از میز» ژتون‌ها را (بعد از فولد دست جاری) نگه می‌دارد. مبلغ شرط را می‌شود دقیق تایپ کرد، با + و −
   یا نوار لغزنده تنظیم کرد یا از انتخاب‌های آماده (½ پات، پات، …) برداشت؛ شرط با یک «تأیید» فرستاده می‌شود.
   گفت‌وگوی میز همراه همان پرسش «چیزی عوض شده؟» می‌آید و پیام هر نفر بالای صندلی‌اش هم دیده می‌شود. */
(function () {
  "use strict";

  var BOOT = window.BOARD_BOOT;
  var tg = window.Telegram && window.Telegram.WebApp ? window.Telegram.WebApp : null;
  var query = new URLSearchParams(location.search);
  var initData = tg && tg.initData ? tg.initData : "";
  if (!initData && BOOT.devAuth && query.get("dev_user")) initData = "dev:" + query.get("dev_user");

  var SUITS = { s: "♠", h: "♥", d: "♦", c: "♣" };
  var STREETS = { preflop: "قبل از فلاپ", flop: "فلاپ", turn: "ترن", river: "ریور" };
  var ACTIONS = {
    fold: "فولد", check: "چک", call: "کال", raise: "رِیز", bet: "شرط", allin: "آل‌این", leave: "بلند شد",
    sb: "بلایند کوچک", bb: "بلایند بزرگ",
  };
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
    chat_empty: "پیام خالی است.",
    chat_no_links: "فرستادن لینک و آیدی در گفت‌وگو ممنوع است.",
    chat_too_fast: "کمی آهسته‌تر بنویس 🙂",
    chat_locked: "گفت‌وگوی این میز بسته شده است.",
  };
  var REASONS = { chips: "یک نفر همه‌ی ژتون‌ها را برد", limit: "دست‌ها تمام شد", left: "بقیه از میز بلند شدند" };
  var AVATARS = [["#5662e0", "#262b78"], ["#f0617f", "#8f1d3a"], ["#2fbf8f", "#0f5c45"], ["#f5a524", "#8a5200"],
    ["#a78bfa", "#4c2a99"], ["#38bdf8", "#0b5d8a"], ["#f472b6", "#86205a"], ["#94a3b8", "#334155"]];
  // جای صندلی‌ها روی میز (درصد از چپ و بالا) به ترتیب نوبت از خود بیننده (پایین) در جهت عقربه‌های ساعت
  var LAYOUTS = {
    2: [[50, 100], [50, 9]],
    3: [[50, 100], [12, 30], [88, 30]],
    4: [[50, 100], [11, 50], [50, 9], [89, 50]],
    5: [[50, 100], [11, 66], [19, 16], [81, 16], [89, 66]],
    6: [[50, 100], [11, 73], [11, 29], [50, 9], [89, 29], [89, 73]],
    7: [[50, 100], [11, 77], [10, 44], [27, 11], [73, 11], [90, 44], [89, 77]],
    8: [[50, 100], [11, 79], [10, 50], [18, 18], [50, 8], [82, 18], [90, 50], [89, 79]],
  };
  var TABLE_QUICK = ["👏 دست خوبی بود", "🤔 بلوف بود؟", "😅 شانس آوردی", "🙏 دست بعد"];
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
  var sizingOpen = false;
  var pollTimer = null;
  var lastSaid = "";
  var lowWarned = false;
  var historyOpen = false;
  var ring = { node: null, end: 0 };
  var prizeTries = 0;
  var talk = { last: 0, open: false, unread: 0, can: false, quick: [], loaded: false, sending: false, locked: false, voted: false };

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
  function plus(value) { return "‎+" + money(value); }
  function digits(text) {
    var latin = String(text || "").replace(/[۰-۹]/g, function (d) { return "۰۱۲۳۴۵۶۷۸۹".indexOf(d); })
      .replace(/[٠-٩]/g, function (d) { return "٠١٢٣٤٥٦٧٨٩".indexOf(d); }).replace(/\D/g, "");
    return latin ? Number(latin) : 0;
  }
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
  // ارزش سکه‌ای ژتون در میز نقدی: کل سکه‌های میز تقسیم بر همه‌ی ژتون‌ها (میز رایگان و مسابقه‌ی قدیمی: صفر)
  function rate() {
    if (!state || !state.cash || state.payout !== "chips" || !state.pot_coins) return 0;
    return state.pot_coins / (state.seats.length * state.start_chips);
  }
  function worth(chips) { return Math.floor(chips * rate() + 1e-9); }
  function coinsText(chips) { return rate() ? "≈ " + money(worth(chips)) + " سکه" : ""; }
  function opening() { return state.current_bet === 0; } // بعد از فلاپ، کسی هنوز شرط نبسته

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
    // روی کارت مثل کارت واقعی (تعداد نقش درست، تصویر شاه و بی‌بی و سرباز)؛ کارت‌های ریز فهرست‌ها همان برچسب ساده را دارند
    if (window.CardFaces && !card.classList.contains("mini")) window.CardFaces.apply(card, code);
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
    for (var i = 0; i < count; i++) {
      var chip = el("i", "chip-ico " + colors[Math.max(0, top - (count - 1 - i))]);
      chip.style.setProperty("--i", i);
      stack.appendChild(chip);
    }
    return stack;
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

  // ------------------------------------------------------------------ هندسه‌ی میز
  function relative(seat) {
    var n = state.seats.length;
    var base = mine() ? state.you : 0;
    return (seat - base + n) % n;
  }
  var tableHeight = 0;
  function spot(seat) {
    var layout = LAYOUTS[state.seats.length] || LAYOUTS[8];
    var p = layout[relative(seat)] || [50, 50];
    // تماشاچی: صندلی پایین هم روی میز کشیده می‌شود
    if (relative(seat) === 0 && !mine()) return { x: 50, y: 88 };
    // صندلی بالای میز در صفحه‌های کوتاه پایین‌تر می‌نشیند تا زیر سربرگ نرود (نیمه‌ی بالای صندلی حدود ۳۶ پیکسل است)
    var top = tableHeight ? (36 / tableHeight) * 100 : 0;
    return { x: p[0], y: Math.max(p[1], top) };
  }
  function place(node, p) {
    node.style.left = p.x.toFixed(2) + "%";
    node.style.top = p.y.toFixed(2) + "%";
  }
  // ژتون شرط و دکمه‌ی دیلر جایی می‌نشینند که روی کارت‌ها، پات، صندلی‌ها و کارت‌های خودت نیفتند: چند جای
  // پیشنهادی (از صندلی رو به وسط میز) به ترتیب امتحان می‌شود و اولین جای خالی انتخاب می‌شود.
  var betSpots = {};
  function toward(p, f) { return { x: p.x + (50 - p.x) * f, y: p.y + (50 - p.y) * f }; }
  function betPoint(seat) { return betSpots[seat] || (isMe(seat) ? { x: 50, y: 77 } : toward(spot(seat), 0.45)); }
  function relRect(node, origin, pad) {
    var r = node.getBoundingClientRect();
    pad = pad || 0;
    return { l: r.left - origin.left - pad, t: r.top - origin.top - pad, r: r.right - origin.left + pad, b: r.bottom - origin.top + pad };
  }
  function covered(box, list) {
    var area = 0;
    for (var i = 0; i < list.length; i++) {
      var o = list[i];
      var w = Math.min(box.r, o.r) - Math.max(box.l, o.l);
      var h = Math.min(box.b, o.b) - Math.max(box.t, o.t);
      if (w > 0 && h > 0) area += w * h;
    }
    return area;
  }
  function outside(box, W, H) {
    var w = box.r - box.l;
    var h = box.b - box.t;
    var inW = Math.max(0, Math.min(box.r, W * 0.95) - Math.max(box.l, W * 0.05));
    var inH = Math.max(0, Math.min(box.b, H * 0.95) - Math.max(box.t, H * 0.05));
    return w * h - inW * inH;
  }
  function candidates(seat, W, H, near) {
    var cx = W / 2;
    var cy = H / 2;
    if (isMe(seat)) {
      return near ? [[W * 0.27, H * 0.8], [W * 0.73, H * 0.8], [W * 0.3, H * 0.74]]
        : [[cx, H * 0.77], [cx, H * 0.73], [cx - 64, H * 0.79], [cx + 64, H * 0.79]];
    }
    var p = spot(seat);
    var sx = (p.x / 100) * W;
    var sy = (p.y / 100) * H;
    var dx = cx - sx;
    var dy = cy - sy;
    var len = Math.sqrt(dx * dx + dy * dy) || 1;
    var side = sx < cx ? 1 : sx > cx ? -1 : 0;
    var out = [];
    (near ? [46, 56, 66] : [62, 74, 86, 98, 112, 126]).forEach(function (d) { out.push([sx + (dx / len) * d, sy - 8 + (dy / len) * d]); });
    if (side) (near ? [62, 74] : [76, 90]).forEach(function (d) { out.push([sx + side * d, sy - (near ? 26 : 14)]); });
    else (near ? [58, 70] : []).forEach(function (d) { out.push([sx + d, sy + 10]); });
    return out;
  }
  function settle(items, blocked, W, H) {
    items.forEach(function (item) {
      var w = item.node.offsetWidth || 56;
      var h = item.node.offsetHeight || 22;
      item.w = w;
      item.h = h;
    });
    items.forEach(function (item) {
      var list = candidates(item.seat, W, H, item.near);
      // اولین جای کاملاً خالی؛ اگر نبود (میز شلوغ و صفحه‌ی کوچک)، جایی که کمترین هم‌پوشانی را دارد
      var pick = list[0];
      var best = Infinity;
      for (var i = 0; i < list.length; i++) {
        var c = list[i];
        var box = { l: c[0] - item.w / 2, t: c[1] - item.h / 2, r: c[0] + item.w / 2, b: c[1] + item.h / 2 };
        var cost = covered(box, blocked) + outside(box, W, H) * 4;
        if (cost < best) { best = cost; pick = c; }
        if (cost === 0) break;
      }
      blocked.push({ l: pick[0] - item.w / 2 - 3, t: pick[1] - item.h / 2 - 3, r: pick[0] + item.w / 2 + 3, b: pick[1] + item.h / 2 + 3 });
      var p = { x: (pick[0] / W) * 100, y: (pick[1] / H) * 100 };
      if (!item.near) betSpots[item.seat] = p;
      place(item.node, p);
      item.node.style.visibility = "";
    });
  }

  // ------------------------------------------------------------------ رسم
  function drawLayer(previous) {
    var layer = $("layer");
    layer.textContent = "";
    var table = $("table");
    tableHeight = table.offsetHeight;
    // میز شلوغ یا صفحه‌ی کوتاه: صندلی‌ها جمع‌وجورتر
    table.classList.toggle("dense", state.seats.length >= 7 || tableHeight < 360);
    var win = winning();
    var fresh = !previous || previous.hand !== state.hand;
    var winners = {};
    if (state.phase === "pause" && state.result) state.result.winners.forEach(function (w) { winners[w.seat] = w.amount; });
    var hands = (state.phase === "pause" && state.result && state.result.hands) || {};
    var said = state.last_action;
    var saidKey = said ? state.hand + ":" + state.version + ":" + said.seat + ":" + said.kind : "";
    var newSaid = said && saidKey !== lastSaid && said.kind !== "sb" && said.kind !== "bb";
    var seatNodes = [];
    var items = [];
    state.seats.forEach(function (s, index) {
      if (s.bet) {
        var bet = el("div", "bet");
        bet.appendChild(chipStack(s.bet));
        bet.appendChild(el("span", "", money(s.bet)));
        bet.style.visibility = "hidden";
        layer.appendChild(bet);
        items.push({ seat: s.seat, node: bet, near: false });
      }
      if (s.dealer) {
        var button = el("div", "dealer-btn", "D");
        button.style.visibility = "hidden";
        layer.appendChild(button);
        items.push({ seat: s.seat, node: button, near: true });
      }
      if (isMe(s.seat)) return; // خود بیننده پایین میز جدا کشیده می‌شود
      var p = spot(s.seat);
      var seat = el("div", "seat");
      if (state.to_act === s.seat && !state.over && state.phase === "betting") seat.classList.add("turn");
      if (s.folded && s.in_hand) seat.classList.add("folded");
      if (s.left) seat.classList.add("left");
      if (!s.in_hand && !state.over && !s.left) seat.classList.add("out");
      if (winners[s.seat]) seat.classList.add("winner");
      if (p.x > 50) seat.classList.add("in-right");
      if (p.x < 30) seat.classList.add("side-l");
      if (p.x > 70) seat.classList.add("side-r");
      if (p.y < 30) seat.classList.add("top");
      var revealed = s.cards.length && s.cards[0];
      if (revealed) seat.classList.add("revealed");
      // کارت‌هایی که همین الان رو شدند برمی‌گردند (نمایش دست‌ها در شودان یا آل‌این)
      var before = previous && previous.hand === state.hand ? previous.seats[s.seat] : null;
      var flipping = !!revealed && !!before && before.cards.length > 0 && !before.cards[0];
      var avatar = el("div", "ava");
      var colors = AVATARS[index % AVATARS.length];
      avatar.style.setProperty("--ava1", colors[0]);
      avatar.style.setProperty("--ava2", colors[1]);
      avatar.appendChild(ringSvg());
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
      var chips = el("small");
      chips.appendChild(el("i", "chip-ico"));
      chips.appendChild(el("span", "", money(s.chips)));
      plate.appendChild(chips);
      seat.appendChild(plate);
      var hand = hands[String(s.seat)];
      var tag = s.left ? ["بلند شد", "away"] : hand ? [hand, winners[s.seat] ? "hand best" : "hand"]
        : s.allin ? ["آل‌این", "allin"] : s.folded && s.in_hand ? ["فولد", "fold"]
        : !s.in_hand && !state.over ? ["بدون ژتون", "fold"] : null;
      if (tag) seat.appendChild(el("span", "tag " + tag[1], tag[0]));
      if (winners[s.seat]) seat.appendChild(el("span", "win-badge", plus(winners[s.seat])));
      else if (newSaid && said.seat === s.seat && !(tag && /fold|leave|allin/.test(said.kind))) {
        // حرکت تازه چند ثانیه روی پلاک خود صندلی (جای نام) نشان داده می‌شود، مثل اپ‌های پوکر؛ روی صندلی
        // دیگری نمی‌افتد. فولد، بلند شدن و آل‌این همین حالا با برچسب زیر صندلی دیده می‌شوند.
        plate.appendChild(el("span", "said k-" + saidKind(said), sayText(said)));
      }
      place(seat, p);
      layer.appendChild(seat);
      seatNodes.push(seat);
    });
    // یک بار اندازه‌ها خوانده می‌شود (صندلی‌ها، وسط میز، کارت‌های خودت) و بعد ژتون‌ها و دکمه‌ی دیلر جا می‌گیرند
    var origin = $("table").getBoundingClientRect();
    if (items.length && origin.width) {
      var blocked = [];
      ["pot", "board-cards", "street", "side-pots"].forEach(function (id) {
        var node = $(id);
        if (node.offsetWidth && node.textContent !== "") blocked.push(relRect(node, origin, 3));
      });
      blocked.push(relRect($("board-cards"), origin, 4));
      blocked.push(relRect(document.querySelector(".table-info"), origin, 2));
      seatNodes.forEach(function (node) {
        blocked.push(relRect(node, origin, 2));
        var hole = node.querySelector(".hole");
        if (hole) blocked.push(relRect(hole, origin, 2));
      });
      if (mine()) blocked.push(relRect($("my-cards"), origin, 4));
      settle(items, blocked, origin.width, origin.height);
    } else items.forEach(function (item) { item.node.style.visibility = ""; });
    if (newSaid) lastSaid = saidKey;
    return newSaid ? said : null;
  }
  function saidKind(action) { return action.kind === "raise" && action.open ? "bet" : action.kind; }
  function sayText(action) {
    if (action.kind === "raise" && action.open) return "شرط " + money(action.to);
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
    $("pot-coins").textContent = total && rate() ? "(" + coinsText(total) + ")" : "";
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
    $("kind-chip").textContent = state.cash ? "میز نقدی" : "مسابقه";
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
    $("me").classList.toggle("folded", !!(me.folded && me.in_hand) || me.left);
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
    $("my-name").textContent = badge(me.seat) + name(me.seat) + (me.left ? " (بلند شدی)" : " (تو)");
    $("my-chips").textContent = money(me.chips);
    $("my-coins").textContent = coinsText(me.chips);
    var bet = $("my-bet");
    bet.classList.toggle("hidden", !me.bet);
    bet.textContent = "";
    if (me.bet) {
      bet.appendChild(chipStack(me.bet));
      bet.appendChild(el("span", "", money(me.bet)));
    }
    Array.prototype.forEach.call(hero.querySelectorAll(".said, .win-badge"), function (n) { n.remove(); });
    if (wonAmount) hero.appendChild(el("span", "win-badge", plus(wonAmount)));
    else if (said && said.seat === me.seat) hero.appendChild(el("span", "said k-" + saidKind(said), sayText(said)));
    var hand = myHandText();
    $("my-hand").textContent = hand ? "دست تو: " + hand : "";
  }

  function drawLog() {
    var box = $("log");
    box.textContent = "";
    var entries = (state.log || []).filter(function (e) { return e.kind !== "sb" && e.kind !== "bb"; }).slice(-2);
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
        animateTo(chip, isMe(w.seat) ? { x: 50, y: 98 } : spot(w.seat), 120 + i * 80);
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
  // حلقه‌ی زمان با یک transition خطی خالی می‌شود (نه با رنگ کردن هر فریم)؛ فقط اگر زمان سرور فرق کرد دوباره تنظیم می‌شود
  function armRing() {
    var circle = document.querySelector(".seat.turn .ring circle, .hero.turn .ring circle");
    if (!circle || state.phase !== "betting" || state.over) { ring.node = null; return; }
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
    var me = mine();
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
      if (!my && pre) text += " — " + preLabel(pre) + " آماده است";
      else if (!my && me && !me.left && me.folded && me.in_hand) text += " — منتظر دست بعد";
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
    seen[legal.raise_max] = true; // آل‌این همیشه جدا و آخر می‌آید
    options = options.filter(function (pair) {
      if (seen[pair[1]]) return false;
      seen[pair[1]] = true;
      return true;
    }).slice(0, 4);
    options.push(["آل‌این", legal.raise_max, "max"]);
    return options;
  }
  // متن دکمه فقط وقتی عوض شده دوباره ساخته می‌شود؛ وگرنه لمسی که همان لحظه روی دکمه است گم می‌شود
  function setBtn(node, label, sub) {
    var key = label + "|" + (sub || "");
    if (node.dataset.key === key) return;
    node.dataset.key = key;
    node.textContent = "";
    node.appendChild(el("span", "", label));
    if (sub) node.appendChild(el("small", "", sub));
  }
  function confirmLabel(legal) {
    if (raiseTo >= legal.raise_max) return "آل‌این " + money(legal.raise_max);
    return (opening() ? "شرط " : "رِیز تا ") + money(raiseTo);
  }
  function controls() {
    var legal = state.legal || {};
    var playing = myTurn();
    $("controls").classList.toggle("hidden", !playing);
    if (!playing) { sizingOpen = false; return; }
    var me = mine();
    var canRaise = !!legal.raise_min;
    if (!canRaise) sizingOpen = false;
    $("sizing").classList.toggle("hidden", !sizingOpen);
    $("confirm-row").classList.toggle("hidden", !sizingOpen);
    document.querySelector("#controls .row.main").classList.toggle("hidden", sizingOpen);
    $("check-btn").classList.toggle("hidden", !legal.check);
    $("call-btn").classList.toggle("hidden", !legal.call);
    setBtn($("call-btn"), "کال", money(legal.call) + (legal.call && legal.call >= me.chips ? " (آل‌این)" : ""));
    $("raise-btn").classList.toggle("hidden", !canRaise);
    setBtn($("raise-btn"), opening() ? "شرط…" : "رِیز…", "از " + money(legal.raise_min));
    var allinOnly = !canRaise && legal.allin && legal.allin > legal.call;
    $("allin-btn").classList.toggle("hidden", !allinOnly);
    setBtn($("allin-btn"), "آل‌این", money(legal.allin));
    if (sizingOpen) drawSizing(legal);
  }
  function drawSizing(legal) {
    var range = $("raise-range");
    range.min = legal.raise_min;
    range.max = legal.raise_max;
    range.step = 1;
    if (raiseTo < legal.raise_min || raiseTo > legal.raise_max) raiseTo = legal.raise_min;
    range.value = raiseTo;
    $("range-min").textContent = money(legal.raise_min);
    $("range-max").textContent = money(legal.raise_max);
    $("amount-label").textContent = opening() ? "شرط" : "رِیز تا";
    var box = $("presets");
    box.textContent = "";
    presets(legal).forEach(function (pair) {
      var button = el("button", pair[2] || "", pair[0]);
      button.type = "button";
      button.dataset.value = pair[1];
      button.addEventListener("click", function () {
        setRaise(pair[1]);
        haptic("light");
      });
      box.appendChild(button);
    });
    showAmount(false);
  }
  function showAmount(writeInput) {
    var legal = state.legal || {};
    if (writeInput || document.activeElement !== $("raise-input")) $("raise-input").value = money(raiseTo);
    $("raise-range").value = raiseTo;
    $("amount-coins").textContent = coinsText(raiseTo);
    setBtn($("sizing-ok"), confirmLabel(legal), "");
    Array.prototype.forEach.call($("presets").children, function (button) {
      button.classList.toggle("on", Number(button.dataset.value) === raiseTo);
    });
  }
  function setRaise(value) {
    var legal = state.legal || {};
    if (!legal.raise_min) return;
    raiseTo = clamp(Math.round(value), legal.raise_min, legal.raise_max);
    showAmount(true);
  }
  function openSizing() {
    var legal = state.legal || {};
    if (!myTurn() || !legal.raise_min) return;
    sizingOpen = true;
    if (raiseTo < legal.raise_min || raiseTo > legal.raise_max) raiseTo = legal.raise_min;
    controls();
    haptic("light");
  }
  function closeSizing() {
    sizingOpen = false;
    if (state) controls();
  }
  function confirmSizing() {
    var legal = state.legal || {};
    if (!myTurn() || !legal.raise_min) return;
    var typed = digits($("raise-input").value);
    if (typed !== raiseTo) {
      // مبلغ تایپ‌شده بیرون از محدوده بی‌صدا فرستاده نمی‌شود: درستش می‌کنیم و یک بار دیگر تأیید می‌خواهیم
      if (typed < legal.raise_min) {
        setRaise(legal.raise_min);
        toast("کمترین مبلغ " + money(legal.raise_min) + " است.");
        return;
      }
      if (typed > legal.raise_max) {
        setRaise(legal.raise_max);
        toast("بیشترین مبلغ " + money(legal.raise_max) + " (آل‌این) است.");
        return;
      }
      raiseTo = typed;
    }
    $("raise-input").blur();
    sizingOpen = false;
    if (raiseTo >= legal.raise_max) send("allin");
    else send("raise", raiseTo);
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
  function showTab(id) {
    Array.prototype.forEach.call(document.querySelectorAll("#history .tab"), function (tab) {
      tab.classList.toggle("on", tab.dataset.tab === id);
      $(tab.dataset.tab).classList.toggle("hidden", tab.dataset.tab !== id);
    });
    if (id === "ranks-body") drawRanks();
  }
  function openSheet(id) {
    if (id === "history") { historyOpen = true; drawHistory(); drawRanks(); }
    if (id === "chat") openChat();
    if (id === "leave") drawLeave();
    $(id).classList.remove("hidden");
    haptic("light");
  }
  function closeSheet(sheet) {
    sheet.classList.add("hidden");
    if (sheet.id === "history") historyOpen = false;
    if (sheet.id === "chat") { talk.open = false; $("chat-input").blur(); }
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
    var badgeNode = $("chat-badge");
    badgeNode.textContent = talk.unread > 9 ? "۹+" : fa(talk.unread);
    badgeNode.classList.toggle("hidden", !talk.unread);
  }
  function bubble(message) {
    var seat = chatSeat(message);
    if (seat === null || !state || seat >= state.seats.length) return;
    var node = el("div", "bubble" + (message.mine ? " mine" : ""), message.text);
    var p = isMe(seat) ? { x: 50, y: 92 } : spot(seat);
    if (!isMe(seat) && p.y < 30) node.classList.add("below");
    var box = $("bubbles");
    Array.prototype.forEach.call(box.querySelectorAll('[data-seat="' + seat + '"]'), function (old) { old.remove(); });
    node.dataset.seat = seat;
    place(node, p);
    box.appendChild(node);
    // حباب صندلی‌های کنار میز از صفحه بیرون نزند
    var width = box.offsetWidth || 1;
    var half = (node.offsetWidth / 2 / width) * 100 + 1;
    place(node, { x: clamp(p.x, half, 100 - half), y: p.y });
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
  }
  // بستن گفت‌وگو وقتی کسی با پیام‌ها تقلب (علامت دادن) می‌کند: با رأی اکثر بازیکن‌های میز تا آخر همین بازی بسته می‌شود
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
  function openChat() {
    talk.open = true;
    talk.unread = 0;
    drawBadge();
    drawChatAccess();
    var box = $("chat-list");
    setTimeout(function () { box.scrollTop = box.scrollHeight; }, 30);
  }
  function say(text) {
    text = String(text || "").trim();
    if (!text || talk.sending) return;
    talk.sending = true;
    $("chat-send").disabled = true;
    api("board/chat", { text: text, chat_after: talk.last }).then(function (response) {
      talk.sending = false;
      $("chat-send").disabled = false;
      if (!response.ok) {
        if (response.error === "chat_locked") setLocked(true);
        toast(errorText(response.error));
        haptic("error");
        return;
      }
      $("chat-input").value = "";
      addChat(response.chat);
    });
  }

  // ------------------------------------------------------------------ بلند شدن از میز
  function drawLeave() {
    var me = mine();
    if (!me) return;
    $("leave-chips").textContent = money(me.chips) + " ژتون";
    var value = rate() ? money(worth(me.chips)) + " سکه" : "";
    $("leave-coins").textContent = value;
    $("leave-coins").classList.toggle("hidden", !value);
    $("leave-coins-label").classList.toggle("hidden", !value);
    var inHand = state.phase === "betting" && me.in_hand && !me.folded;
    var note = inHand ? "دستی که الان در آن هستی فولد می‌شود و ژتون‌هایی که وسط گذاشته‌ای برنمی‌گردد. " : "";
    if (!state.cash) note += "در این میز ترک کردن یعنی از دست دادن همه‌ی ژتون‌ها.";
    else if (!rate()) note += "این میز رایگان است؛ ژتون‌هایت سر جایش می‌ماند.";
    else note += "ژتون‌هایت سر جایش می‌ماند و آخر میز به همین اندازه سکه به کیف پولت واریز می‌شود.";
    $("leave-note").textContent = note;
  }
  function drawLeft() {
    var me = mine();
    var gone = !!me && me.left && !state.over;
    $("left-box").classList.toggle("hidden", !gone);
    if (!gone) return;
    var box = $("left-text");
    box.textContent = "";
    box.appendChild(document.createTextNode("ژتون‌هایت: "));
    box.appendChild(el("b", "", money(me.chips)));
    if (state.cash && rate()) {
      box.appendChild(document.createTextNode(" — سهمت: "));
      box.appendChild(el("b", "", money(worth(me.chips)) + " سکه"));
      box.appendChild(document.createTextNode(" که آخر میز به کیف پولت واریز می‌شود."));
    }
    box.appendChild(document.createTextNode(" می‌توانی میز را تماشا کنی و در گفت‌وگو بنویسی."));
  }

  // ------------------------------------------------------------------ نتیجه
  function ranking() {
    return state.seats.map(function (s) { return { seat: s.seat, chips: s.left && !state.cash ? 0 : s.chips }; })
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
  function prizeOf(seat) {
    var prizes = state.prizes || null;
    if (prizes && prizes["s" + seat] !== undefined) return { coins: prizes["s" + seat], exact: true };
    if (!rate()) return null;
    var s = state.seats[seat];
    return { coins: worth(s.left && !state.cash ? 0 : s.chips), exact: false };
  }
  function drawResultList() {
    var list = $("result-list");
    list.textContent = "";
    var medals = ["🥇", "🥈", "🥉"];
    ranking().forEach(function (row, i) {
      var item = el("li", isMe(row.seat) ? "me" : "");
      item.appendChild(el("span", "", (medals[i] || fa(i + 1) + ".") + " " + name(row.seat)));
      var side = el("small");
      var prize = prizeOf(row.seat);
      if (prize && (prize.coins || state.payout === "chips")) side.appendChild(el("b", "", (prize.exact ? "" : "≈ ") + money(prize.coins) + " سکه"));
      side.appendChild(document.createTextNode(money(row.chips) + " ژتون"));
      item.appendChild(side);
      list.appendChild(item);
    });
    var me = mine();
    var mineBox = $("result-mine");
    var own = me ? prizeOf(me.seat) : null;
    mineBox.classList.toggle("hidden", !own || !own.coins);
    if (own && own.coins) {
      mineBox.textContent = own.exact ? "💰 " + money(own.coins) + " سکه به کیف پولت واریز شد" : "💰 سهم تو: حدود " + money(own.coins) + " سکه (در حال واریز…)";
    }
  }
  function showResult() {
    if (resultShown) { drawResultList(); return; }
    resultShown = true;
    drawResultList();
    var top = ranking()[0];
    var won = !!top && isMe(top.seat) && top.chips > 0;
    $("result-icon").textContent = won ? "🏆" : "🃏";
    $("result-title").textContent = resultTitle().replace(/^🏆 /, ""); // جام بزرگ بالای همین عنوان است
    $("result-reason").textContent = (REASONS[state.over.reason] || "") +
      (state.payout === "chips" ? " — هر کس به اندازه‌ی ژتون‌هایش سکه می‌برد." : " — جایزه‌ی سکه بر اساس رتبه‌ی ژتون در گروه اعلام می‌شود.");
    setTimeout(function () {
      $("result").classList.remove("hidden");
      if (won) confetti();
    }, 1400);
    sound(won ? "win" : "draw");
    haptic("success");
  }
  // بعد از پایان بازی، ربات چند ثانیه بعد سکه‌ها را پرداخت می‌کند؛ آن موقع مبلغ دقیق را می‌گیریم
  var prizeTimer = null;
  function fetchPrizes() {
    if (!state || !state.over || state.prizes || state.payout !== "chips" || prizeTries >= 8 || prizeTimer) return;
    prizeTries += 1;
    prizeTimer = setTimeout(function () {
      api("board/state", { chat_after: talk.last }).then(function (response) {
        prizeTimer = null;
        if (response.ok) apply(response);
      });
    }, 2500);
  }

  // ------------------------------------------------------------------ دریافت وضعیت
  function react(previous, said, dealt) {
    if (!previous) return;
    if (said) {
      var kind = said.kind;
      sound(kind === "fold" || kind === "leave" ? "fold" : kind === "check" ? "check" : kind === "allin" ? "chips" : "chip");
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
    var dealt = drawBoard(previous); // اول وسط میز، تا جای خالی‌اش برای ژتون‌ها درست اندازه گرفته شود
    var said = drawLayer(previous);
    drawMe(previous, said);
    drawLog();
    if (previous) flyBets(previous);
    if (resultAppears(previous)) flyWinnings();
    controls();
    preBar();
    drawLeft();
    tick();
    armRing();
    react(previous, said, dealt || (previous && previous.hand !== state.hand));
    var me = mine();
    $("resign-btn").classList.toggle("hidden", !me);
    $("resign-btn").disabled = !me || me.left || !!state.over || !!state.cancelled;
    if (historyOpen) drawHistory();
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
      addChat(response.chat, !talk.loaded); // پیام‌های قبل از باز شدن صفحه حباب و شمارنده ندارند
      talk.loaded = true;
    } else if (response.changed !== false) talk.loaded = true;
    if (response.changed === false) {
      leftBase = response.left_ms !== undefined ? response.left_ms : response.seconds_left * 1000;
      tick();
      armRing();
      return true;
    }
    var previous = state;
    var before = real;
    real = response.state;
    leftBase = real.left_ms !== undefined ? real.left_ms : real.seconds_left * 1000;
    if (stage && (stage.hand !== real.hand || real.phase !== "pause")) stopStage();
    if (!stage && shouldStage(before, real)) startStage(before);
    state = stage ? stagedView() : real;
    if (!previous || previous.to_act !== state.to_act || previous.street !== state.street || previous.hand !== state.hand) {
      raiseTo = 0;
      sizingOpen = false;
    }
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
    if (myTurn()) return talk.open ? 1200 : 1600;
    return 900;
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
  function send(kind, amount) {
    if (!state || busy) return;
    busy = true;
    pre = null;
    haptic("light");
    api("board/action", { action: kind, amount: amount || 0, chat_after: talk.last }).then(function (response) {
      busy = false;
      if (!apply(response)) loop();
    });
  }
  function fail(text) {
    $("loading-text").textContent = text;
    document.querySelector("#loading .spinner").classList.add("hidden");
  }

  // ------------------------------------------------------------------ دکمه‌ها
  $("fold-btn").addEventListener("click", function () {
    // مثل اپ‌های پوکر: وقتی چک مجانی است فولد با یک سؤال انجام می‌شود
    if (state && state.legal && state.legal.check) confirmThen("می‌توانی مجانی چک کنی. باز هم فولد می‌کنی؟", function () { send("fold"); });
    else send("fold");
  });
  $("check-btn").addEventListener("click", function () { send("check"); });
  $("call-btn").addEventListener("click", function () { send("call"); });
  $("allin-btn").addEventListener("click", function () {
    var legal = (state && state.legal) || {};
    confirmThen("همه‌ی " + money(legal.allin) + " ژتونت وسط برود؟", function () { send("allin"); });
  });
  // دکمه‌های پنل شرط فوکوس فیلد مبلغ را نمی‌گیرند تا صفحه‌کلید گوشی بی‌دلیل بسته و باز نشود
  Array.prototype.forEach.call(document.querySelectorAll("#sizing button, #confirm-row button"), function (button) {
    button.addEventListener("mousedown", function (event) { event.preventDefault(); });
  });
  $("presets").addEventListener("mousedown", function (event) { event.preventDefault(); });
  $("raise-btn").addEventListener("click", openSizing);
  $("sizing-cancel").addEventListener("click", function () { closeSizing(); haptic("light"); });
  $("sizing-ok").addEventListener("click", confirmSizing);
  $("raise-range").addEventListener("input", function () { setRaise(Number(this.value)); });
  $("minus-btn").addEventListener("click", function () { setRaise(raiseTo - state.bb); haptic("light"); });
  $("plus-btn").addEventListener("click", function () { setRaise(raiseTo + state.bb); haptic("light"); });
  $("raise-input").addEventListener("focus", function () { this.select(); });
  $("raise-input").addEventListener("input", function () {
    // هنگام تایپ فقط رقم‌ها نگه داشته می‌شود؛ محدوده موقع تأیید یا ترک فیلد اعمال می‌شود
    var legal = (state && state.legal) || {};
    var typed = digits(this.value);
    this.value = typed ? money(typed) : "";
    if (typed >= (legal.raise_min || 0) && typed <= (legal.raise_max || 0)) { raiseTo = typed; showAmount(false); }
  });
  $("raise-input").addEventListener("change", function () { setRaise(digits(this.value) || raiseTo); });
  $("raise-input").addEventListener("keydown", function (event) { if (event.key === "Enter") { event.preventDefault(); confirmSizing(); } });
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
  $("chat-btn").addEventListener("click", function () { if (state) openSheet("chat"); });
  Array.prototype.forEach.call(document.querySelectorAll("#history .tab"), function (tab) {
    tab.addEventListener("click", function () { showTab(tab.dataset.tab); haptic("light"); });
  });
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
  $("resign-btn").addEventListener("click", function () {
    var me = state && mine();
    if (!me || me.left || state.over) return;
    openSheet("leave");
  });
  $("leave-yes").addEventListener("click", function () {
    closeSheet($("leave"));
    sizingOpen = false;
    send("resign");
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
      if (tg.setHeaderColor) tg.setHeaderColor("#07130f");
      if (tg.setBackgroundColor) tg.setBackgroundColor("#050a09");
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
      resizeTimer = setTimeout(function () { if (state) render(state); }, 150);
    });
    document.addEventListener("visibilitychange", function () {
      if (document.hidden || busy || !state) return;
      api("board/state", { version: real.version, chat_after: talk.last }).then(function (response) { if (!busy && response.ok) apply(response); });
    });
  });
})();
