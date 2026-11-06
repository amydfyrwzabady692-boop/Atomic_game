/* انفجار (Crash) مینی‌اپ. سرور زمان شروع هر دور را می‌دهد و صفحه ضریب را خودش روی نمودار بالا می‌برد؛ نقطه‌ی انفجار
   تا لحظه‌ی انفجار هرگز به صفحه نمی‌رسد و «برداشت» به ساعت سرور حساب می‌شود. هر کس زودتر از انفجار برداشت کند ضریب همان
   لحظه امتیازش می‌شود؛ جمع ضریب‌ها برنده را معلوم می‌کند. */
(function () {
  "use strict";

  var BOOT = window.BOARD_BOOT;
  var tg = window.Telegram && window.Telegram.WebApp ? window.Telegram.WebApp : null;
  var query = new URLSearchParams(location.search);
  var initData = tg && tg.initData ? tg.initData : "";
  if (!initData && BOOT.devAuth && query.get("dev_user")) initData = "dev:" + query.get("dev_user");

  var ERRORS = {
    not_your_turn: "نوبت تو نیست.",
    illegal_move: "این کار ممکن نیست.",
    crashed: "دیر شد؛ منفجر شده بود 💥",
    not_flying: "هنوز پرواز شروع نشده.",
    already_cashed: "این دور برداشته‌ای.",
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
  var TABLE_QUICK = ["🚀 بریم بالا!", "😱 چه زود ترکید", "💰 به‌موقع برداشتم", "🍀 موفق باشی", "🤝 بازی خوبی بود"];
  var COLORS = ["#4f8cff", "#ff9f43", "#c084fc", "#34d399", "#f472b6", "#facc15", "#22d3ee", "#a3e635", "#fb7185", "#93c5fd"];

  var real = null;
  var state = null;
  var busy = false;
  var receivedAt = 0;
  var leftBase = 0;
  var resultShown = false;
  var pollTimer = null;
  var prizeTries = 0;
  var prizeTimer = null;
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
  function name(seat) { return state.players["s" + seat] || ""; }
  function who(seat) { return seated() && seat === state.you ? "تو" : name(seat); }
  function badge(seat) {
    var profile = (state.profiles || {})["s" + seat];
    return profile && profile.emoji ? profile.emoji + " " : "";
  }
  function initial(seat) { return (name(seat).trim()[0] || "؟").toUpperCase(); }

  function x(hundredths) {
    var v = Math.max(0, Math.round(hundredths));
    // جداسازی چپ‌به‌راست تا «×» در متن فارسی جابه‌جا نشود
    return "\u2066" + fa(Math.floor(v / 100) + "." + String(v % 100).padStart(2, "0")).replace(".", "٫") + "×\u2069";
  }
  function houseNote() {
    var pct = state.house_percent || 0;
    return pct ? " — " + fa(pct) + "٪ از کل سکه‌ها سهم سرویس است." : "";
  }

  // ------------------------------------------------------------------ ساعت و ضریب
  // زمان‌ها از سرور نسبت به همان پاسخ می‌آید (نه ساعت گوشی): لحظه‌ی شروع پرواز روی ساعت همین صفحه
  var clock = { startAt: 0, rate: Math.log(2) / 6, crashed: null, crashAt: 0 };
  function syncClock() {
    clock.rate = state.rate || clock.rate;
    if (state.phase === "fly" && state.elapsed_ms !== null && state.elapsed_ms !== undefined) clock.startAt = receivedAt - state.elapsed_ms;
    else if (state.phase === "wait" && state.start_in_ms !== null && state.start_in_ms !== undefined) clock.startAt = receivedAt + state.start_in_ms;
    if (state.phase === "fly" || state.phase === "wait") clock.crashed = null;
    else if (state.point && clock.crashed === null) { clock.crashed = state.point; clock.crashAt = now(); }
  }
  function liveMult() {
    var t = (now() - clock.startAt) / 1000;
    return t <= 0 ? 1 : Math.floor(Math.exp(clock.rate * t) * 100) / 100;
  }
  function mine() { return seated() ? state.seats[state.you] : null; }
  function canCash() {
    var me = mine();
    return !!(me && !me.left && state.phase === "fly" && me.cashed === null && !busy && !state.over && now() >= clock.startAt);
  }

  // ------------------------------------------------------------------ نمودار
  var canvas = null;
  var ctx2d = null;
  var dpr = 1;
  function sizeCanvas() {
    canvas = $("graph");
    var box = $("stage");
    dpr = Math.min(2, window.devicePixelRatio || 1);
    canvas.width = Math.round(box.clientWidth * dpr);
    canvas.height = Math.round(box.clientHeight * dpr);
    ctx2d = canvas.getContext("2d");
    stars = [];
  }
  function color(m) {
    if (m < 1.5) return "#6ee7ff";
    if (m < 2) return "#34d399";
    if (m < 5) return "#ffc857";
    return "#ff5c7a";
  }
  // ذره‌ها: شعله‌ی پشت موشک و ترکش‌های انفجار (روی همان canvas)
  var sparks = [];
  var stars = [];
  var lastFrameAt = 0;
  function makeStars(w, h) {
    stars = [];
    for (var i = 0; i < 46; i++) stars.push({ x: Math.random() * w, y: Math.random() * h, r: (Math.random() * 1.3 + 0.3) * dpr, s: Math.random() * 0.6 + 0.2, t: Math.random() * 6 });
  }
  function spawnTrail(p, c) {
    for (var i = 0; i < 3; i++) {
      sparks.push({ x: p[0], y: p[1], vx: (-1.4 - Math.random() * 1.6) * dpr, vy: (0.6 + Math.random() * 1.4) * dpr, life: 1, decay: 0.03 + Math.random() * 0.03, r: (2 + Math.random() * 3) * dpr, c: c });
    }
  }
  function spawnBoom(p) {
    for (var i = 0; i < 70; i++) {
      var a = Math.random() * Math.PI * 2, v = (1.5 + Math.random() * 5) * dpr;
      sparks.push({ x: p[0], y: p[1], vx: Math.cos(a) * v, vy: Math.sin(a) * v, life: 1, decay: 0.012 + Math.random() * 0.02, r: (1.5 + Math.random() * 3.5) * dpr, c: i % 3 ? "#ff5c7a" : "#ffc857", g: 0.06 * dpr });
    }
  }
  function drawSparks() {
    ctx2d.globalCompositeOperation = "lighter";
    for (var i = sparks.length - 1; i >= 0; i--) {
      var p = sparks[i];
      p.x += p.vx; p.y += p.vy; p.vy += p.g || 0; p.life -= p.decay;
      if (p.life <= 0) { sparks.splice(i, 1); continue; }
      ctx2d.globalAlpha = Math.max(0, p.life);
      ctx2d.fillStyle = p.c;
      ctx2d.beginPath(); ctx2d.arc(p.x, p.y, p.r * (0.4 + p.life * 0.6), 0, Math.PI * 2); ctx2d.fill();
    }
    ctx2d.globalAlpha = 1;
    ctx2d.globalCompositeOperation = "source-over";
  }
  function drawStars(w, h, speed) {
    if (!stars.length) makeStars(w, h);
    var t = now() / 1000;
    stars.forEach(function (st) {
      st.x -= st.s * speed * dpr;
      st.y += st.s * speed * 0.35 * dpr;
      if (st.x < 0) st.x += w;
      if (st.y > h) st.y -= h;
      ctx2d.globalAlpha = 0.35 + 0.35 * Math.sin(t * 2 + st.t);
      ctx2d.fillStyle = "#fff";
      ctx2d.beginPath(); ctx2d.arc(st.x, st.y, st.r, 0, Math.PI * 2); ctx2d.fill();
    });
    ctx2d.globalAlpha = 1;
  }
  var boomAt = null;
  function drawGraph(m, flying, crashed) {
    if (!ctx2d) sizeCanvas();
    var w = canvas.width, h = canvas.height;
    ctx2d.clearRect(0, 0, w, h);
    drawStars(w, h, flying ? Math.min(6, 0.6 + Math.log(m) * 2) : 0.15);
    var pad = 18 * dpr;
    var top = Math.max(2, m * 1.15);
    var span = Math.log(top) / clock.rate; // ثانیه‌های تا سقف نمودار
    // خطوط راهنما
    ctx2d.strokeStyle = "rgba(255,255,255,.07)";
    ctx2d.lineWidth = 1 * dpr;
    ctx2d.font = (10 * dpr) + "px sans-serif";
    ctx2d.fillStyle = "rgba(255,255,255,.35)";
    [1.5, 2, 3, 5, 10, 20].forEach(function (g) {
      if (g >= top) return;
      var y = h - pad - ((g - 1) / (top - 1)) * (h - pad * 2);
      ctx2d.beginPath(); ctx2d.moveTo(pad, y); ctx2d.lineTo(w - pad, y); ctx2d.stroke();
      ctx2d.fillText(g + "×", pad + 2 * dpr, y - 3 * dpr);
    });
    if (m <= 1 && !crashed) { placeRocket(null); drawSparks(); return; }
    var steps = 60;
    var tEnd = Math.log(m) / clock.rate;
    var pts = [];
    for (var i = 0; i <= steps; i++) {
      var t = (tEnd * i) / steps;
      var v = Math.exp(clock.rate * t);
      pts.push([pad + (t / span) * (w - pad * 2), h - pad - ((v - 1) / (top - 1)) * (h - pad * 2)]);
    }
    var c = crashed ? "#ff5c7a" : color(m);
    var grad = ctx2d.createLinearGradient(0, h, 0, 0);
    grad.addColorStop(0, "rgba(0,0,0,0)");
    grad.addColorStop(1, crashed ? "rgba(255,92,122,.35)" : "rgba(255,200,87,.28)");
    ctx2d.beginPath();
    ctx2d.moveTo(pts[0][0], h - pad);
    pts.forEach(function (p) { ctx2d.lineTo(p[0], p[1]); });
    ctx2d.lineTo(pts[pts.length - 1][0], h - pad);
    ctx2d.closePath();
    ctx2d.fillStyle = grad;
    ctx2d.fill();
    ctx2d.beginPath();
    pts.forEach(function (p, k) { if (k) ctx2d.lineTo(p[0], p[1]); else ctx2d.moveTo(p[0], p[1]); });
    ctx2d.strokeStyle = c;
    ctx2d.lineWidth = 4 * dpr;
    ctx2d.lineCap = "round";
    ctx2d.shadowColor = c;
    ctx2d.shadowBlur = 14 * dpr;
    ctx2d.stroke();
    ctx2d.shadowBlur = 0;
    var tip = pts[pts.length - 1];
    if (flying) spawnTrail(tip, Math.random() < 0.5 ? "#ffc857" : "#ff8a3d");
    if (crashed && boomAt !== clock.crashAt) { boomAt = clock.crashAt; spawnBoom(tip); }
    // هاله‌ی نور سر منحنی
    var glow = ctx2d.createRadialGradient(tip[0], tip[1], 0, tip[0], tip[1], 40 * dpr);
    glow.addColorStop(0, crashed ? "rgba(255,92,122,.55)" : "rgba(255,220,140,.5)");
    glow.addColorStop(1, "rgba(0,0,0,0)");
    ctx2d.fillStyle = glow;
    ctx2d.fillRect(tip[0] - 40 * dpr, tip[1] - 40 * dpr, 80 * dpr, 80 * dpr);
    drawSparks();
    placeRocket(flying || crashed ? tip : null, crashed);
  }
  function placeRocket(p, crashed) {
    var node = $("rocket");
    node.classList.toggle("hidden", !p);
    if (!p) return;
    node.textContent = crashed ? "💥" : "🚀";
    node.classList.toggle("boom", !!crashed);
    node.style.transform = "translate(" + (p[0] / dpr) + "px," + (p[1] / dpr) + "px) translate(-50%,-50%)" + (crashed ? "" : " rotate(-35deg)");
  }

  // ------------------------------------------------------------------ قاب هر لحظه
  var lastMultText = "";
  function frame() {
    requestAnimationFrame(frame);
    if (!state) return;
    var big = $("mult");
    var note = $("phase-note");
    var text;
    var stage = $("stage");
    if (clock.crashed !== null && state.phase !== "wait" && state.phase !== "fly") {
      text = x(Math.round(clock.crashed * 100));
      note.textContent = state.over ? "بازی تمام شد" : "💥 منفجر شد! دور بعد چند ثانیه‌ی دیگر";
      stage.className = "crashed";
      drawGraph(clock.crashed, false, true);
    } else if (state.phase === "wait" && now() < clock.startAt) {
      var left = Math.ceil((clock.startAt - now()) / 1000);
      text = "۱٫۰۰×";
      note.textContent = "🚀 پرواز تا " + fa(left) + " ثانیه‌ی دیگر";
      stage.className = "waiting";
      drawGraph(1, false, false);
    } else {
      var m = liveMult();
      text = x(Math.round(m * 100));
      note.textContent = state.phase === "fly" ? "در حال اوج گرفتن…" : "شروع…";
      stage.className = "flying";
      stage.style.setProperty("--glow", color(m));
      drawGraph(m, true, false);
    }
    if (text !== lastMultText) { big.textContent = text; lastMultText = text; }
    drawButton();
    status();
  }
  function boom(point) {
    var flash = $("cash-flash");
    flash.textContent = "💥 " + x(Math.round(point * 100));
    flash.className = "boom";
    setTimeout(function () { flash.className = "hidden"; }, 1400);
    $("stage").classList.add("shake");
    setTimeout(function () { $("stage").classList.remove("shake"); }, 500);
    var me = mine();
    var lost = me && !me.left && state.results.length && state.results[state.results.length - 1].cashed[state.you] === null;
    sound(lost ? "lose" : "draw");
    haptic(lost ? "error" : "warning");
  }
  var lastButton = "";
  function drawButton() {
    var button = $("cash-btn");
    var me = mine();
    var text, cls = "btn", off = true;
    if (!me) { text = "👀 تماشا می‌کنی"; }
    else if (me.left) { text = "بازی را ترک کرده‌ای"; }
    else if (state.over) { text = "🏁 بازی تمام شد"; }
    else if (me.cashed !== null && (state.phase === "fly" || state.phase === "wait")) {
      text = "✅ برداشتی در " + x(Math.round(me.cashed * 100)); cls += " done";
    } else if (state.phase === "fly" && now() >= clock.startAt) {
      text = "💰 برداشت در " + x(Math.round(liveMult() * 100)); cls += " go hot"; off = busy;
    } else if (state.phase === "wait" || (state.phase === "fly" && now() < clock.startAt)) {
      text = "⏳ آماده باش…"; cls += " violet";
    } else {
      var last = state.results.length ? state.results[state.results.length - 1].cashed[state.you] : null;
      text = last ? "✅ این دور " + x(Math.round(last * 100)) + " گرفتی" : "💥 این دور منفجر شد"; cls += last ? " done" : " lost";
    }
    var key = text + cls + off;
    if (key === lastButton) return;
    lastButton = key;
    button.textContent = text;
    button.className = cls;
    button.disabled = off;
  }
  function status() {
    var box = $("status");
    var text = "";
    if (state.cancelled) text = "این مسابقه لغو شده است.";
    else if (state.over) text = resultTitle();
    else {
      var me = mine();
      text = me ? "امتیاز تو: " + x(me.score) : "";
    }
    if (box.textContent !== text) box.textContent = text;
  }
  function drawPast() {
    var box = $("past");
    box.textContent = "";
    var list = state.history || [];
    if (!list.length) { box.appendChild(el("span", "empty", "اولین دور — هنوز انفجاری نبوده")); return; }
    list.slice().reverse().forEach(function (p) {
      var chip = el("span", "chip " + (p < 1.5 ? "low" : p < 2 ? "mid" : p < 5 ? "good" : "high"), x(Math.round(p * 100)));
      box.appendChild(chip);
    });
  }
  function drawPlayers() {
    var box = $("players");
    box.textContent = "";
    var order = state.seats.map(function (s) { return s.seat; }).sort(function (a, b) { return state.seats[b].score - state.seats[a].score; });
    order.forEach(function (seat, i) {
      var s = state.seats[seat];
      var row = el("div", "prow" + (seated() && seat === state.you ? " me" : "") + (s.left ? " gone" : ""));
      row.style.setProperty("--c", COLORS[seat % COLORS.length]);
      var ava = el("span", "pava", (name(seat).trim()[0] || "؟").toUpperCase());
      row.appendChild(el("i", "rank", fa(i + 1)));
      row.appendChild(ava);
      row.appendChild(el("b", "", badge(seat) + who(seat)));
      var now_ = "";
      var cls = "now";
      if (s.left) now_ = "رفت";
      else if (s.cashed !== null && (state.phase === "fly" || state.phase === "wait")) { now_ = "✅ " + x(Math.round(s.cashed * 100)); cls += " ok"; }
      else if (state.phase === "fly") now_ = "🚀 در پرواز";
      else if (state.results.length && state.phase !== "wait") {
        var c = state.results[state.results.length - 1].cashed[seat];
        now_ = c ? "✅ " + x(Math.round(c * 100)) : "💥";
        cls += c ? " ok" : " bad";
      }
      row.appendChild(el("span", cls, now_));
      row.appendChild(el("em", "", x(s.score)));
      box.appendChild(row);
    });
  }
  function drawHistory() {
    var body = $("history-body");
    body.textContent = "";
    var rounds = el("section", "hist");
    rounds.appendChild(el("h3", "", "دورها"));
    var list = state.results || [];
    if (!list.length) rounds.appendChild(el("p", "", "هنوز دوری تمام نشده است."));
    list.forEach(function (r) {
      var got = r.cashed.map(function (c, seat) { return who(seat) + " " + (c ? x(Math.round(c * 100)) : "💥"); }).join("، ");
      rounds.appendChild(el("p", "", "دور " + fa(r.round) + ": منفجر در " + x(Math.round(r.point * 100)) + " — " + got));
    });
    body.appendChild(rounds);
    var rules = el("section", "hist");
    rules.appendChild(el("h3", "", "قانون‌ها"));
    [
      "هر دور ضریب از ۱٫۰۰× شروع می‌شود و هر ۶ ثانیه دو برابر می‌شود تا ناگهان منفجر شود.",
      "نقطه‌ی انفجار از قبل با دانه‌ی مسابقه معلوم است و تا انفجار به هیچ‌کس (حتی ربات) نشان داده نمی‌شود.",
      "قبل از انفجار «برداشت» بزن تا ضریب همان لحظه (به ساعت سرور) امتیازت شود؛ دیر کنی آن دور صفر می‌گیری.",
      "جمع ضریب‌های همه‌ی دورها رتبه را معلوم می‌کند و جایزه طبق تقسیم لابی پرداخت می‌شود" + (state.house_percent ? " (پس از کسر " + fa(state.house_percent) + "٪ سهم سرویس)." : "."),
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
  function bubble(message) {
    if (message.mine) return;
    var node = el("div", "bubble", (message.name ? message.name + ": " : "") + message.text);
    $("stage").appendChild(node);
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
    var order = state.seats.map(function (s) { return s.seat; }).sort(function (a, b) { return state.seats[b].score - state.seats[a].score; });
    order.forEach(function (seat) {
      var item = el("li", seated() && seat === state.you ? "me" : "");
      item.style.background = "color-mix(in srgb, " + COLORS[seat % COLORS.length] + " 14%, transparent)";
      item.appendChild(el("span", "", (seat === state.winner_seat ? "🏆 " : "") + name(seat) + (state.seats[seat].left ? " (رفت)" : "")));
      var prizes = state.prizes || null;
      var coins = prizes && prizes["s" + seat] !== undefined ? prizes["s" + seat] : null;
      item.appendChild(el("small", "", coins !== null ? (coins ? "+" + money(coins) + " سکه" : x(state.seats[seat].score)) : x(state.seats[seat].score)));
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
    $("result-icon").textContent = won ? "🏆" : "💥";
    $("result-title").textContent = resultTitle().replace(/^🏆 /, "");
    $("result-reason").textContent = state.over.reason === "left"
      ? name(state.over.left_seat) + " بازی را ترک کرد."
      : "جمع ضریب‌ها: " + state.seats.map(function (s) { return who(s.seat) + " " + x(s.score); }).join(" · ") + houseNote();
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
    var action = state.last_action;
    var fresh = action && JSON.stringify(previous.last_action) !== JSON.stringify(action);
    if (previous.round !== state.round && state.phase === "wait") sound("deal");
    if (fresh && action.kind === "cash") {
      sound(action.seat === state.you ? "chips" : "chip");
      if (action.seat !== state.you) toast("💰 " + name(action.seat) + " در " + x(Math.round(action.mult * 100)) + " برداشت", true);
    }
    if (fresh && action.kind === "crash") boom(action.point);
    if (previous.phase === "wait" && state.phase === "fly") { sound("turn"); haptic("medium"); }
  }
  function render(previous) {
    syncClock();
    drawPast();
    drawPlayers();
    drawButton();
    react(previous);
    $("target-chip").textContent = "دور " + fa(Math.max(1, state.round)) + " از " + fa(state.rounds);
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
    if (response.changed === false) return true;
    var previous = state;
    real = response.state;
    state = real;
    render(previous);
    return true;
  }
  function pollDelay() {
    if (!state || state.over || state.cancelled) return 5000;
    if (state.phase === "fly") return 350; // انفجار باید زود دیده شود
    if (state.phase === "wait" && clock.startAt - now() < 900) return 300;
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
  $("cash-btn").addEventListener("click", function () {
    if (!canCash()) return;
    haptic("heavy");
    send("crash_cash");
  });
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
      if (tg.setHeaderColor) tg.setHeaderColor("#160818");
      if (tg.setBackgroundColor) tg.setBackgroundColor("#0a0410");
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
    requestAnimationFrame(frame);
    var resizeTimer = null;
    window.addEventListener("resize", function () {
      clearTimeout(resizeTimer);
      resizeTimer = setTimeout(sizeCanvas, 150);
    });
    document.addEventListener("visibilitychange", function () {
      if (document.hidden || busy || !state) return;
      api("board/state", { version: real.version, chat_after: talk.last }).then(function (response) { if (!busy && response.ok) apply(response); });
    });
  });
})();

