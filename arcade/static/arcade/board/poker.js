/* میز پوکر مینی‌اپ. همه‌ی قوانین و کارت‌ها در سرور است؛ سرور فقط کارت‌های خود بازیکن را می‌فرستد.
   این فایل میز را مثل سالن‌های پوکر آنلاین می‌کشد (صندلی‌ها دور میز بیضی، ژتون شرط جلوی هر نفر، دکمه‌ی
   دیلر، حلقه‌ی زمان نوبت)، کارت‌ها را با پخش و برگشتن نشان می‌دهد و حرکت (فولد/چک/کال/رِیز/آل‌این) را
   با دکمه‌های اندازه‌ی شرط (نصف پات، سه‌چهارم پات، پات) می‌فرستد. */
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

  var state = null;
  var busy = false;
  var receivedAt = 0;
  var leftBase = 0;
  var resultShown = false;
  var raiseTo = 0;
  var pollTimer = null;
  var lastSaid = "";

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
  function initial(seat) { return (name(seat).trim()[0] || "؟").toUpperCase(); }

  // ------------------------------------------------------------------ کارت
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
  function chipColor(amount) { return amount >= state.bb * 10 ? "black" : amount >= state.bb * 3 ? "blue" : ""; }

  // ------------------------------------------------------------------ رسم
  function drawLayer(previous) {
    var layer = $("layer");
    layer.textContent = "";
    var win = winning();
    var fresh = !previous || previous.hand !== state.hand;
    var winners = {};
    if (state.phase === "pause" && state.result) state.result.winners.forEach(function (w) { winners[w.seat] = w.amount; });
    var said = state.last_action;
    var saidKey = said ? state.hand + ":" + state.version + ":" + said.seat + ":" + said.kind : "";
    var newSaid = said && saidKey !== lastSaid && said.kind !== "sb" && said.kind !== "bb";
    state.seats.forEach(function (s, index) {
      if (s.bet) {
        var bet = el("div", "bet");
        bet.appendChild(el("i", "chip-ico " + chipColor(s.bet)));
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
      var avatar = el("div", "ava");
      var colors = AVATARS[index % AVATARS.length];
      avatar.style.setProperty("--ava1", colors[0]);
      avatar.style.setProperty("--ava2", colors[1]);
      avatar.appendChild(el("span", "", initial(s.seat)));
      seat.appendChild(avatar);
      if (s.cards.length) {
        var hole = el("div", "hole");
        s.cards.forEach(function (code, i) {
          var card = cardEl(code, cardClass(code, win, fresh && !code));
          if (fresh && !code) card.style.animationDelay = (0.08 * (relative(s.seat) + i * state.seats.length)).toFixed(2) + "s";
          hole.appendChild(card);
        });
        seat.appendChild(hole);
      }
      var plate = el("div", "plate");
      plate.appendChild(el("b", "", name(s.seat)));
      plate.appendChild(el("small", "", money(s.chips)));
      seat.appendChild(plate);
      var tag = s.left ? ["ترک کرد", ""] : s.allin ? ["آل‌این", "allin"] : s.folded && s.in_hand ? ["فولد", "fold"] : null;
      if (tag) seat.appendChild(el("span", "tag " + tag[1], tag[0]));
      if (winners[s.seat]) seat.appendChild(el("span", "win-badge", "+" + money(winners[s.seat])));
      else if (newSaid && said.seat === s.seat) seat.appendChild(el("span", "said", sayText(said)));
      place(seat, point(s.seat, 40, 41));
      layer.appendChild(seat);
    });
    if (newSaid) lastSaid = saidKey;
    return newSaid ? said : null;
  }
  function sayText(action) {
    var text = ACTIONS[action.kind] || "";
    if (action.kind === "raise" || action.kind === "allin") return text + (action.to ? " " + money(action.to) : "");
    return text + (action.amount && action.kind === "call" ? " " + money(action.amount) : "");
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
      total = state.result.winners.reduce(function (sum, w) { return sum + w.amount; }, 0);
    }
    $("pot-amount").textContent = money(total);
    if (previous && previous.pot !== state.pot) {
      pot.classList.remove("bump");
      void pot.offsetWidth;
      pot.classList.add("bump");
    }
    $("street").textContent = state.over ? "" : STREETS[state.street] || "";
    $("hand-chip").textContent = "دست " + fa(state.hand) + " از " + fa(state.hand_limit);
    $("blind-chip").textContent = "بلایند " + money(state.sb) + "/" + money(state.bb);
    return box.querySelectorAll(".deal").length;
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
    hero.classList.toggle("turn", state.to_act === me.seat && state.phase === "betting" && !state.over);
    var wonAmount = 0;
    if (state.phase === "pause" && state.result) {
      state.result.winners.forEach(function (w) { if (w.seat === me.seat) wonAmount = w.amount; });
    }
    hero.classList.toggle("winner", wonAmount > 0);
    var colors = AVATARS[me.seat % AVATARS.length];
    $("my-ava").style.setProperty("--ava1", colors[0]);
    $("my-ava").style.setProperty("--ava2", colors[1]);
    $("my-initial").textContent = initial(me.seat);
    $("my-name").textContent = name(me.seat) + " (تو)";
    $("my-chips").textContent = money(me.chips) + " ژتون";
    var bet = $("my-bet");
    bet.classList.toggle("hidden", !me.bet);
    bet.textContent = "";
    if (me.bet) {
      bet.appendChild(el("i", "chip-ico " + chipColor(me.bet)));
      bet.appendChild(el("span", "", money(me.bet)));
    }
    Array.prototype.forEach.call(hero.querySelectorAll(".said, .win-badge"), function (n) { n.remove(); });
    if (wonAmount) hero.appendChild(el("span", "win-badge", "+" + money(wonAmount)));
    else if (said && said.seat === me.seat) hero.appendChild(el("span", "said", sayText(said)));
    var hand = state.my_hand || "";
    if (state.phase === "pause" && state.result && state.result.hands && state.result.hands[String(me.seat)]) {
      hand = state.result.hands[String(me.seat)];
    }
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
  function flyChips(previous) {
    var layer = $("layer");
    var streetDone = previous.hand === state.hand && (previous.street !== state.street || (previous.phase === "betting" && state.phase !== "betting"));
    if (streetDone) {
      previous.seats.forEach(function (s) {
        if (!s.bet) return;
        var chip = el("div", "fly bet");
        chip.appendChild(el("i", "chip-ico " + chipColor(s.bet)));
        place(chip, betPoint(s.seat));
        layer.appendChild(chip);
        animateTo(chip, { x: 50, y: 40 });
      });
    }
    if (state.phase === "pause" && previous.phase !== "pause" && state.result) {
      state.result.winners.forEach(function (w) {
        for (var i = 0; i < 3; i++) {
          var chip = el("div", "fly");
          chip.appendChild(el("i", "chip-ico"));
          place(chip, { x: 50 + (i - 1) * 3, y: 40 });
          layer.appendChild(chip);
          animateTo(chip, isMe(w.seat) ? { x: 50, y: 98 } : point(w.seat, 40, 41), 120 + i * 90);
        }
      });
    }
  }
  function animateTo(node, p, delay) {
    setTimeout(function () {
      void node.offsetWidth;
      place(node, p);
      node.style.opacity = "0.2";
      setTimeout(function () { node.remove(); }, 520);
    }, (delay || 0) + 30);
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
    status();
  }
  function status() {
    var box = $("status");
    var text = "";
    var cls = "";
    var seconds = Math.ceil(msLeft() / 1000);
    if (state.cancelled) { text = "این مسابقه لغو شده است."; cls = "alert"; }
    else if (state.over) text = resultTitle();
    else if (state.phase === "pause" && state.result) {
      text = state.result.winners.map(function (w) {
        return "🏆 " + name(w.seat) + " " + money(w.amount) + " ژتون برد" + (w.hand ? " (" + w.hand + ")" : "");
      }).join("  ") + "  ⏳ دست بعد " + fa(seconds) + " ثانیه دیگر";
    } else if (state.to_act !== null && state.to_act !== undefined) {
      var my = isMe(state.to_act);
      text = (my ? "نوبت توست" : "نوبت " + name(state.to_act)) + " (" + fa(seconds) + " ثانیه)";
      cls = my ? (seconds <= 8 ? "warn" : "mine") : "";
    }
    if (box.textContent !== text) box.textContent = text;
    box.className = cls;
  }

  // ------------------------------------------------------------------ دکمه‌ها و اندازه‌ی شرط
  function clamp(value, low, high) { return Math.max(low, Math.min(high, value)); }
  function presets(legal) {
    var me = mine();
    var toCall = Math.max(0, state.current_bet - me.bet);
    var after = state.pot + toCall; // پات بعد از کال
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
    var me = mine();
    var playing = !!me && !state.over && !state.cancelled && state.to_act === me.seat && state.phase === "betting";
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
    if (state.phase === "pause" && previous.phase !== "pause") {
      var meWon = state.result && state.result.winners.some(function (w) { return isMe(w.seat); });
      setTimeout(function () { sound(meWon ? "win" : "chips"); }, 250);
    }
    var myTurn = mine() && state.to_act === state.you && state.phase === "betting";
    var wasMyTurn = previous.to_act === previous.you && previous.phase === "betting" && previous.hand === state.hand && previous.street === state.street;
    if (myTurn && !wasMyTurn && !state.over) { sound("turn"); haptic("medium"); }
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
    state = response.state;
    leftBase = state.left_ms !== undefined ? state.left_ms : state.seconds_left * 1000;
    if (!previous || previous.to_act !== state.to_act || previous.street !== state.street || previous.hand !== state.hand) raiseTo = 0;
    var said = drawLayer(previous);
    var dealt = drawBoard(previous);
    drawMe(previous, said);
    drawLog();
    if (previous) flyChips(previous);
    controls();
    tick();
    react(previous, said, dealt || (previous && previous.hand !== state.hand));
    var me = mine();
    $("resign-btn").classList.toggle("hidden", !me);
    $("resign-btn").disabled = !me || me.left || !!state.over || !!state.cancelled;
    if (state.over) showResult();
    return true;
  }
  function pollDelay() {
    if (!state || state.over || state.cancelled) return 5000;
    if (mine() && state.to_act === state.you && state.phase === "betting") return 1600;
    return 900;
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
  function send(kind, amount) {
    if (!state || busy) return;
    busy = true;
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

  $("fold-btn").addEventListener("click", function () { send("fold"); });
  $("check-btn").addEventListener("click", function () { send("check"); });
  $("call-btn").addEventListener("click", function () { send("call"); });
  $("allin-btn").addEventListener("click", function () { send("allin"); });
  $("raise-btn").addEventListener("click", function () { send("raise", raiseTo); });
  $("raise-range").addEventListener("input", function () { setRaise(Number(this.value)); });
  $("minus-btn").addEventListener("click", function () { setRaise(raiseTo - state.bb); haptic("light"); });
  $("plus-btn").addEventListener("click", function () { setRaise(raiseTo + state.bb); haptic("light"); });
  function soundButton() { $("sound-btn").textContent = window.SFX && window.SFX.isMuted() ? "🔇" : "🔊"; }
  $("sound-btn").addEventListener("click", function () {
    if (!window.SFX) return;
    window.SFX.setMuted(!window.SFX.isMuted());
    soundButton();
    if (!window.SFX.isMuted()) setTimeout(function () { sound("chip"); }, 60);
  });
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
      api("board/state", { version: state.version }).then(function (response) { if (!busy && response.ok) apply(response); });
    });
  });
})();
