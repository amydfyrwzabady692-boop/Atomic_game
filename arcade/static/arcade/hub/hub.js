/* صفحه‌ی اصلی مینی‌اپ: تب‌های بازی‌ها، حریف تصادفی، رتبه‌ها، فروشگاه و پروفایل.
   همه‌ی داده‌ها از API سرور می‌آید و همه‌ی کارها (خرید، دوئل، جایزه‌ی روزانه) در سرور انجام می‌شود. */
(function () {
  "use strict";

  var BOOT = window.HUB_BOOT;
  var tg = window.Telegram && window.Telegram.WebApp ? window.Telegram.WebApp : null;
  var query = new URLSearchParams(location.search);
  var initData = tg && tg.initData ? tg.initData : "";
  if (!initData && BOOT.devAuth) initData = "dev:" + (query.get("dev_user") || "1");

  var ERRORS = {
    bad_game: "این بازی برای حریف تصادفی در دسترس نیست.",
    bad_stake: "مقدار سکه معتبر نیست.",
    banned: "حساب تو مسدود شده است.",
    need_start: "اول یک بار ربات را در پیوی /start کن.",
    not_enough_coins: "سکه‌ات کافی نیست.",
    no_coins: "سکه‌ات کافی نیست.",
    already_in_duel: "یک دوئل در جریان داری.",
    already_searching: "در حال جستجو هستی.",
    not_your_duel: "این دوئل مال تو نیست.",
    duel_closed: "این دوئل دیگر باز نیست.",
    no_offer: "حریف هنوز پیشنهادی نداده است.",
    already_owned: "این آیتم را داری.",
    not_found: "پیدا نشد.",
    not_owned: "این آیتم را نداری.",
    daily_disabled: "جایزه‌ی روزانه فعلاً فعال نیست.",
    rate_limited: "کمی آهسته‌تر! چند ثانیه صبر کن.",
    network: "اتصال به سرور برقرار نشد.",
    chat_empty: "پیام خالی است.",
    chat_no_links: "فرستادن لینک و یوزرنیم در گفت‌وگو مجاز نیست.",
    chat_too_fast: "کمی آهسته‌تر پیام بده.",
  };
  var CANCEL_REASONS = {
    timeout: "زمان توافق تمام شد.",
    me: "انصراف دادی.",
    them: "حریف انصراف داد.",
    coins: "یکی از دو طرف سکه‌ی کافی نداشت؛ از کسی سکه‌ای کم نشد.",
    admin: "توسط مدیر لغو شد و ورودی‌ها برگشت.",
  };

  var current = "games";
  var duel = { state: null, games: [], stakes: [], quick: [], maxStake: 1000000, game: null, stake: null, receivedAt: 0, seen: null, chatSeen: 0 };
  var timers = { duel: null };

  function $(id) { return document.getElementById(id); }
  function fa(value) { return String(value).replace(/\d/g, function (d) { return "۰۱۲۳۴۵۶۷۸۹"[d]; }); }
  function money(value) { return fa(Number(value || 0).toLocaleString("en-US")).replace(/,/g, "٬"); }
  function el(tag, cls, text) {
    var node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined && text !== null) node.textContent = text;
    return node;
  }
  function haptic(kind) {
    try {
      if (!tg || !tg.HapticFeedback) return;
      if (kind === "error" || kind === "success") tg.HapticFeedback.notificationOccurred(kind);
      else tg.HapticFeedback.impactOccurred(kind || "light");
    } catch (e) { /* نسخه‌های قدیمی */ }
  }
  var toastTimer = null;
  function toast(text) {
    var box = $("toast");
    box.textContent = text;
    box.classList.remove("hidden");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { box.classList.add("hidden"); }, 2800);
  }
  function errorText(code) {
    if (code && code.indexOf("auth_") === 0) return "این صفحه باید از داخل تلگرام باز شود.";
    return ERRORS[code] || "مشکلی پیش آمد. دوباره امتحان کن.";
  }
  function api(path, body) {
    body = body || {};
    body.initData = initData;
    return fetch(BOOT.apiBase + path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }).then(function (r) { return r.json(); })
      .catch(function () { return { ok: false, error: "network" }; })
      .then(function (data) {
        if (data.error === "join_required") { showJoinGate(data.channels); haptic("warning"); return data; }
        if (!data.ok) { toast(errorText(data.error)); haptic("error"); }
        return data;
      });
  }

  // ------------------------------------------------------------------ جوین اجباری
  /* تا کاربر عضو کانال‌های ربات نشود سرور «join_required» با فهرست کانال‌ها می‌دهد؛ این صفحه دکمه‌ی هر کانال
     و «✅ عضو شدم» (بررسی دوباره بدون کش) را نشان می‌دهد. */
  function openChannel(url) {
    haptic("light");
    if (tg && tg.openTelegramLink && url.indexOf("https://t.me/") === 0) {
      try { tg.openTelegramLink(url); return; } catch (e) { /* قدیمی */ }
    }
    window.open(url, "_blank");
  }
  function showJoinGate(channels) {
    var list = $("join-list");
    list.textContent = "";
    (channels || []).forEach(function (channel) {
      if (!channel.link) return;
      var button = el("button", "btn", "📢 " + channel.title);
      button.type = "button";
      button.addEventListener("click", function () { openChannel(channel.link); });
      list.appendChild(button);
    });
    $("join-gate").classList.remove("hidden");
  }
  function stakeLabel(stake) {
    if (stake === null || stake === undefined) return "🤝 فرقی نمی‌کند";
    if (stake === 0) return "🆓 بدون سکه";
    return money(stake) + " 🪙";
  }
  function setCoins(coins) {
    if (coins === undefined || coins === null) return;
    $("me-coins").textContent = "🪙 " + money(coins);
    $("wallet-coins").textContent = money(coins) + " سکه";
  }

  // ------------------------------------------------------------------ کیف پول: میان‌بر به پیوی ربات
  /* شارژ، فروش و انتقال سکه در پیوی ربات انجام می‌شود (رسید، شماره کارت و تأیید ادمین)؛ این دکمه‌ها
     همان بخش را مستقیم در ربات باز می‌کنند. */
  function openBot(payload) {
    if (!BOOT.botUsername) return;
    var url = "https://t.me/" + BOOT.botUsername + "?start=" + payload;
    haptic("light");
    if (tg && tg.openTelegramLink) { try { tg.openTelegramLink(url); return; } catch (e) { /* قدیمی */ } }
    window.open(url, "_blank");
  }
  $("wallet-card").classList.toggle("hidden", !BOOT.botUsername);
  document.querySelectorAll("#wallet-card [data-start]").forEach(function (b) {
    b.addEventListener("click", function () { openBot(b.dataset.start); });
  });

  // ------------------------------------------------------------------ نماد تصویری بازی‌ها (همان نمادهای صفحه‌ی بازی)
  var icons = (function () {
    if (!window.ArcadeArt || !window.ArcadeIcons) return null;
    try {
      var sprites = {};
      var env = {
        res: Math.min(window.devicePixelRatio || 1, 2),
        font: function (size, weight) { return (weight || 700) + " " + size + "px Vazirmatn, Tahoma, sans-serif"; },
        roundRect: function (c, x, y, w, h, r) {
          r = Math.min(r, w / 2, h / 2);
          c.beginPath();
          c.moveTo(x + r, y);
          c.arcTo(x + w, y, x + w, y + h, r);
          c.arcTo(x + w, y + h, x, y + h, r);
          c.arcTo(x, y + h, x, y, r);
          c.arcTo(x, y, x + w, y, r);
          c.closePath();
        },
        sprite: function (key, w, h, paint, pad) {
          if (sprites[key]) return sprites[key];
          pad = pad || 0;
          var cv = document.createElement("canvas");
          cv.width = Math.max(1, Math.ceil((w + pad * 2) * env.res));
          cv.height = Math.max(1, Math.ceil((h + pad * 2) * env.res));
          var sc = cv.getContext("2d");
          sc.scale(env.res, env.res);
          sc.translate(pad, pad);
          paint(sc, w, h);
          sprites[key] = { canvas: cv, w: w, h: h, pad: pad, fw: w + pad * 2, fh: h + pad * 2 };
          return sprites[key];
        },
        glow: function () {},
        dropShadow: function () {},
      };
      env.art = window.ArcadeArt(env);
      return window.ArcadeIcons(env);
    } catch (e) { return null; }
  })();
  function iconFor(key, emoji) {
    var holder = el("span", "icon");
    var canvas = null;
    try { canvas = icons && icons.has(key) ? icons.element(key, 58) : null; } catch (e) { canvas = null; }
    if (canvas) holder.appendChild(canvas);
    else holder.textContent = emoji;
    return holder;
  }

  // ------------------------------------------------------------------ تب‌ها
  function show(tab) {
    current = tab;
    ["games", "duel", "top", "shop", "me"].forEach(function (name) {
      $("tab-" + name).classList.toggle("hidden", name !== tab);
    });
    document.querySelectorAll("#tabs button").forEach(function (b) { b.classList.toggle("on", b.dataset.tab === tab); });
    window.scrollTo(0, 0);
    if (tab === "duel") loadDuel();
    if (tab === "top") loadTop("week");
    if (tab === "shop") loadShop();
    if (tab === "me") loadMe(true);
  }
  document.querySelectorAll("#tabs button").forEach(function (b) {
    b.addEventListener("click", function () { haptic("light"); show(b.dataset.tab); });
  });

  // ------------------------------------------------------------------ پروفایل
  var profile = null;
  function loadMe(full) {
    return api("hub/me").then(function (data) {
      if (!data.ok) return;
      profile = data;
      $("me-name").textContent = data.name + (data.decor && data.decor.emoji ? " " + data.decor.emoji : "");
      $("avatar").textContent = (data.decor && data.decor.frame) || (data.name || "🙂").slice(0, 1);
      setCoins(data.coins);
      $("me-level").textContent = "سطح " + fa(data.level);
      var span = Math.max(1, data.next_xp - data.level_xp);
      $("me-xp-bar").style.width = Math.min(100, Math.round((data.xp - data.level_xp) * 100 / span)) + "%";
      $("daily-card").classList.toggle("hidden", !data.daily_enabled);
      if (full) drawMe(data);
    });
  }
  function drawMe(data) {
    var stats = $("me-stats");
    stats.textContent = "";
    var rate = data.games ? Math.round(data.wins * 100 / data.games) : 0;
    [[data.games, "بازی"], [data.wins, "برد"], [rate + "٪", "درصد برد"]].forEach(function (pair) {
      var box = el("div");
      box.appendChild(el("b", "", fa(pair[0])));
      box.appendChild(el("small", "", pair[1]));
      stats.appendChild(box);
    });
    var badges = $("me-badges");
    badges.textContent = "";
    badges.appendChild(el("b", "", "🏅 نشان‌ها"));
    badges.appendChild(el("p", "small", data.badges.length ? data.badges.join(" ") : "هنوز نشانی نگرفته‌ای"));
    if (data.best_game) badges.appendChild(el("p", "small muted", "بهترین بازی: " + data.best_game));
    var records = $("me-records");
    records.textContent = "";
    records.appendChild(el("b", "", "👾 رکوردهای آرکید"));
    records.appendChild(el("p", "small", data.records.length
      ? data.records.map(function (r) { return r.emoji + " " + fa(r.score); }).join("   ")
      : "هنوز رکوردی نداری؛ از تب بازی‌ها تمرین کن."));
    var invite = data.invite;
    if (invite.reward > 0) {
      $("invite-text").textContent = "به ازای هر " + fa(invite.every) + " دوستی که با لینک تو ربات را استارت کنند، " +
        fa(invite.reward) + " سکه می‌گیری. دعوت‌شده‌ها: " + fa(invite.count) + " · تا جایزه‌ی بعدی: " + fa(invite.progress) + " از " + fa(invite.every);
      $("invite-bar").style.width = Math.round(invite.progress * 100 / invite.every) + "%";
    } else {
      $("invite-text").textContent = "جایزه‌ی دعوت فعلاً فعال نیست. دعوت‌شده‌ها: " + fa(invite.count);
      $("invite-bar").style.width = "0";
    }
    $("invite-card").classList.toggle("hidden", !invite.link);
    loadHistory();
  }
  function loadHistory() {
    api("hub/history").then(function (data) {
      if (!data.ok) return;
      var list = $("history-list");
      list.textContent = "";
      if (!data.rows.length) list.appendChild(el("li", "", "هنوز تراکنشی نداری."));
      data.rows.forEach(function (row) {
        var li = el("li");
        var name = el("div", "name", row.type);
        name.appendChild(el("small", "", fa(row.at)));
        li.appendChild(name);
        li.appendChild(el("span", "val " + (row.amount < 0 ? "minus" : "plus"), (row.amount < 0 ? "−" : "+") + money(Math.abs(row.amount))));
        list.appendChild(li);
      });
    });
  }
  $("invite-share").addEventListener("click", function () {
    if (!profile || !profile.invite.link) return;
    var url = "https://t.me/share/url?url=" + encodeURIComponent(profile.invite.link) + "&text=" + encodeURIComponent("بیا با هم بازی کنیم 🎮");
    if (tg && tg.openTelegramLink) { try { tg.openTelegramLink(url); return; } catch (e) { /* قدیمی */ } }
    window.open(url, "_blank");
  });
  $("invite-copy").addEventListener("click", function () {
    if (!profile || !profile.invite.link) return;
    var done = function () { toast("لینک کپی شد"); haptic("success"); };
    if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(profile.invite.link).then(done, function () { toast(profile.invite.link); });
    else toast(profile.invite.link);
  });
  $("daily-btn").addEventListener("click", function () {
    api("hub/daily").then(function (data) {
      if (!data.ok) return;
      setCoins(data.coins);
      if (data.claimed) { toast("🎁 +" + money(data.amount) + " سکه · روز " + fa(data.streak)); haptic("success"); }
      else if (data.rescue) { toast("🛟 +" + money(data.rescue) + " سکه‌ی کمکی"); haptic("success"); }
      else {
        var h = Math.floor(data.next_in / 3600), m = Math.floor((data.next_in % 3600) / 60);
        toast("جایزه‌ی امروز را گرفته‌ای · بعدی " + fa(h) + " ساعت و " + fa(m) + " دقیقه‌ی دیگر");
      }
    });
  });

  // ------------------------------------------------------------------ بازی‌ها
  function drawGames() {
    var grid = $("game-grid");
    grid.textContent = "";
    var chess = el("a", "tile");
    chess.href = BOOT.chessPractice + location.search;
    var knight = el("span", "icon chess");
    var img = document.createElement("img");
    img.src = BOOT.pieceBase + "wn.png";
    img.alt = "";
    knight.appendChild(img);
    chess.appendChild(knight);
    chess.appendChild(el("b", "", "شطرنج با کامپیوتر"));
    grid.appendChild(chess);
    BOOT.games.forEach(function (game) {
      var a = el("a", "tile");
      a.href = BOOT.playBase + game.key + "/" + location.search;
      a.appendChild(iconFor(game.key, game.emoji));
      a.appendChild(el("b", "", game.title));
      grid.appendChild(a);
    });
  }
  $("duel-banner").addEventListener("click", function () { haptic("light"); show("duel"); });
  // میان‌بُر بازی‌های محبوب: همان بازی در تب «حریف» انتخاب‌شده باز می‌شود
  Array.prototype.forEach.call(document.querySelectorAll("#featured button"), function (button) {
    button.addEventListener("click", function () {
      haptic("light");
      duel.game = button.dataset.game;
      show("duel");
      if (duel.state) drawDuel();
    });
  });

  // ------------------------------------------------------------------ حریف تصادفی
  function duelSecondsLeft() {
    var s = duel.state;
    if (!s || s.seconds_left === undefined) return 0;
    return Math.max(0, s.seconds_left - Math.floor((Date.now() - duel.receivedAt) / 1000));
  }
  function loadDuel() {
    return api("duel/state").then(applyDuel);
  }
  function applyDuel(data) {
    if (!data.ok) return;
    var previous = duel.state;
    duel.state = data.state;
    duel.games = data.games;
    duel.stakes = data.stakes;
    duel.quick = data.quick || [];
    duel.maxStake = data.max_stake || duel.maxStake;
    duel.coins = data.coins;
    duel.receivedAt = Date.now();
    setCoins(data.coins);
    if (previous && previous.mode !== data.state.mode) {
      haptic(data.state.mode === "negotiating" || data.state.mode === "playing" ? "success" : "medium");
    }
    drawDuel();
    schedule();
  }
  function schedule() {
    clearTimeout(timers.duel);
    var mode = duel.state ? duel.state.mode : "idle";
    var active = mode === "searching" || mode === "negotiating" || mode === "playing";
    if (!active && current !== "duel") return;
    timers.duel = setTimeout(function () {
      if (document.hidden) { schedule(); return; }
      loadDuel();
    }, active ? 1500 : 6000);
  }
  function chip(label, on, onClick) {
    var b = el("button", "chip" + (on ? " on" : ""), label);
    b.type = "button";
    b.addEventListener("click", function () { haptic("light"); onClick(); });
    return b;
  }
  function drawDuel() {
    var s = duel.state;
    ["idle", "searching", "negotiating", "playing"].forEach(function (mode) {
      $("duel-" + mode).classList.toggle("hidden", s.mode !== mode && !(mode === "idle" && (s.mode === "finished" || s.mode === "cancelled")));
    });
    var last = s.mode === "idle" ? s.last : (s.mode === "finished" || s.mode === "cancelled" ? s : null);
    var lastBox = $("duel-last");
    lastBox.classList.toggle("hidden", !last || duel.seen === last.duel_id);
    if (last) {
      lastBox.textContent = "";
      var title;
      if (last.mode === "finished") {
        title = last.outcome === "win" ? "🏆 بردی!" : last.outcome === "draw" ? "🤝 مساوی شد" : "😔 باختی";
        if (last.prize) title += "  +" + money(last.prize) + " 🪙";
      } else {
        title = "❌ دوئل لغو شد — " + (CANCEL_REASONS[last.reason] || "");
      }
      lastBox.appendChild(el("b", "", title));
      lastBox.appendChild(el("p", "small muted", last.game.emoji + " " + last.game.title + " مقابل " + last.opponent.name));
      var hide = el("button", "btn ghost", "باشه");
      hide.type = "button";
      hide.addEventListener("click", function () { duel.seen = last.duel_id; drawDuel(); });
      lastBox.appendChild(hide);
    }
    if (s.mode === "idle" || s.mode === "finished" || s.mode === "cancelled") {
      if (!duel.game && duel.games.length) duel.game = duel.games[0].key;
      drawDuelGames();
      var stakes = $("duel-stakes");
      stakes.textContent = "";
      var custom = duel.stake !== null && duel.stakes.indexOf(duel.stake) === -1;
      duel.stakes.concat([null]).forEach(function (value) {
        stakes.appendChild(chip(stakeLabel(value), duel.stake === value, function () { duel.stake = value; drawDuel(); }));
      });
      if (custom) stakes.appendChild(chip("✍️ " + stakeLabel(duel.stake), true, function () {}));
    } else if (s.mode === "searching") {
      $("duel-search-info").textContent = s.game.emoji + " " + s.game.title + " — " + stakeLabel(s.stake) +
        " — " + fa(Math.ceil(duelSecondsLeft() / 60)) + " دقیقه";
    } else if (s.mode === "negotiating") {
      $("duel-opponent").textContent = s.opponent.name;
      $("duel-opponent-level").textContent = "سطح " + fa(s.opponent.level) + " — " + s.game.emoji + " " + s.game.title;
      $("duel-mine").textContent = s.mine === null ? "هنوز پیشنهاد نداده‌ای" : stakeLabel(s.mine);
      $("duel-theirs").textContent = s.theirs === null ? "هنوز پیشنهاد نداده" : stakeLabel(s.theirs);
      $("duel-timer").textContent = fa(duelSecondsLeft()) + " ثانیه";
      var accept = $("duel-accept");
      var canAccept = s.theirs !== null && s.theirs !== s.mine;
      accept.classList.toggle("hidden", !canAccept);
      if (canAccept) accept.textContent = "✅ قبول " + stakeLabel(s.theirs);
      var offers = $("duel-offers");
      offers.textContent = "";
      duel.stakes.forEach(function (value) {
        offers.appendChild(chip(stakeLabel(value), s.mine === value, function () {
          api("duel/offer", { duel_id: s.duel_id, amount: value }).then(applyDuel);
        }));
      });
      drawChat($("duel-chat-negotiating"), s);
    } else if (s.mode === "playing") {
      // پوکر میز نقدی است: هر کس به اندازه‌ی ژتونش از کل سکه‌ها می‌برد، نه برنده‌ی همه
      var seats = s.players || 2;
      var pot = s.game.key === "poker" ? "هر کس به اندازه‌ی ژتونش از " + money(s.stake * seats) + " 🪙" : "جایزه " + money(s.stake * seats) + " 🪙";
      $("duel-playing-info").textContent = s.game.emoji + " " + s.game.title + " مقابل " + s.opponent.name + " — " +
        (s.stake ? "ورودی " + money(s.stake) + " — " + pot : "بدون سکه") +
        (s.game.kind === "arcade" ? " — " + s.game.note + "؛ امتیاز بیشتر برنده" : "");
      // میز چندنفره گفت‌وگوی خودش را داخل صفحه‌ی میز دارد
      $("duel-chat-playing").classList.toggle("hidden", !!s.table);
      if (!s.table) drawChat($("duel-chat-playing"), s);
    }
  }

  /* انتخاب بازی: چهار بازی نوبتی با دکمه‌ی بزرگ و بازی‌های آرکید در یک شبکه‌ی جمع‌وجور نمادها */
  function drawDuelGames() {
    var board = $("duel-board-games"), arcade = $("duel-arcade-games");
    board.textContent = "";
    arcade.textContent = "";
    var picked = null;
    duel.games.forEach(function (g) {
      var on = duel.game === g.key;
      if (on) picked = g;
      var pick = function () { haptic("light"); duel.game = g.key; drawDuel(); };
      var b;
      if (g.kind === "arcade") {
        b = el("button", "duel-tile" + (on ? " on" : ""));
        b.appendChild(iconFor(g.icon || g.key, g.emoji));
        b.appendChild(el("b", "", g.title));
        arcade.appendChild(b);
      } else {
        b = el("button", "duel-game" + (on ? " on" : ""));
        b.appendChild(el("span", "duel-emoji", g.emoji));
        b.appendChild(el("b", "", g.title));
        if (g.note) b.appendChild(el("small", "", g.note));
        board.appendChild(b);
      }
      b.type = "button";
      b.addEventListener("click", pick);
    });
    $("duel-pick").textContent = picked
      ? "انتخاب تو: " + picked.emoji + " " + picked.title + (picked.kind === "arcade"
        ? " — هر دو همان بازی را در " + picked.note + " بازی می‌کنید؛ بهترین امتیاز برنده است."
        : picked.table ? " — میز " + fa(picked.table) + " نفره: جستجو تا پر شدن میز ادامه دارد و بازی بدون توافق، با همان سکه‌ای که انتخاب کردی شروع می‌شود."
        : picked.key === "chess" && picked.note ? " · ساعت " + picked.note : picked.note ? " · " + picked.note : "")
      : "";
  }

  // ------------------------------------------------------------------ مبلغ دلخواه
  function readAmount(input) {
    var raw = String(input.value || "").replace(/[۰-۹]/g, function (d) { return "۰۱۲۳۴۵۶۷۸۹".indexOf(d); }).trim();
    var value = Number(raw);
    if (!raw || !isFinite(value) || value < 0 || Math.floor(value) !== value) { toast("مبلغ را با عدد درست بنویس."); return null; }
    if (value > duel.maxStake) { toast("حداکثر " + money(duel.maxStake) + " سکه"); return null; }
    if (value > 0 && duel.coins !== undefined && duel.coins !== null && value > duel.coins) {
      toast("سکه‌ات کافی نیست (" + money(duel.coins) + " 🪙)");
      return null;
    }
    return value;
  }
  $("duel-custom-set").addEventListener("click", function () {
    var value = readAmount($("duel-custom"));
    if (value === null) return;
    duel.stake = value;
    $("duel-custom").value = "";
    haptic("light");
    drawDuel();
  });
  $("duel-offer-send").addEventListener("click", function () {
    var value = readAmount($("duel-offer-custom"));
    if (value === null || !duel.state) return;
    $("duel-offer-custom").value = "";
    api("duel/offer", { duel_id: duel.state.duel_id, amount: value }).then(applyDuel);
  });

  // ------------------------------------------------------------------ گفت‌وگو با حریف
  /* پیام‌ها با textContent نشان داده می‌شوند (HTML اجرا نمی‌شود)؛ پیام تازه‌ی حریف با لرزش کوتاه اعلام می‌شود */
  function drawChat(box, s) {
    if (!box.firstChild) {
      box.appendChild(el("b", "chat-title", "💬 گفت‌وگو با حریف"));
      box.appendChild(el("div", "chat-log"));
      var quick = el("div", "chat-quick");
      box.appendChild(quick);
      var row = el("div", "chat-input");
      var input = el("input");
      input.maxLength = 120;
      input.placeholder = "پیام به حریف…";
      var send = el("button", "btn go", "ارسال");
      send.type = "button";
      row.appendChild(input);
      row.appendChild(send);
      box.appendChild(row);
      var post = function (text) {
        text = String(text || "").trim();
        if (!text) { input.focus(); return; } // «ارسال» با کادر خالی: مکان‌نما به کادر پیام می‌رود
        if (!duel.state) return;
        api("duel/chat", { duel_id: duel.state.duel_id, text: text }).then(function (res) {
          if (res.ok) { input.value = ""; applyDuel(res); }
        });
      };
      send.addEventListener("click", function () { post(input.value); });
      input.addEventListener("keydown", function (e) { if (e.key === "Enter") post(input.value); });
      box._post = post;
    }
    var quickBox = box.querySelector(".chat-quick");
    if (!quickBox.firstChild) {
      duel.quick.forEach(function (text) {
        var b = el("button", "chip small", text);
        b.type = "button";
        b.addEventListener("click", function () { haptic("light"); box._post(text); });
        quickBox.appendChild(b);
      });
    }
    var log = box.querySelector(".chat-log");
    var messages = s.chat || [];
    var lastId = messages.length ? messages[messages.length - 1].id : 0;
    if (log.dataset.last === String(lastId)) return;
    log.dataset.last = String(lastId);
    log.textContent = "";
    if (!messages.length) log.appendChild(el("p", "muted small chat-empty", "هنوز پیامی نیست؛ با یک سلام شروع کن 🙂"));
    messages.forEach(function (m) {
      var row = el("div", "chat-msg" + (m.mine ? " mine" : ""));
      if (!m.mine) row.appendChild(el("small", "", m.name));
      row.appendChild(el("span", "", m.text));
      log.appendChild(row);
    });
    log.scrollTop = log.scrollHeight;
    var fresh = messages.filter(function (m) { return !m.mine && m.id > duel.chatSeen; });
    if (fresh.length && duel.chatSeen) haptic("light");
    duel.chatSeen = Math.max(duel.chatSeen, lastId);
  }
  $("duel-search").addEventListener("click", function () {
    if (!duel.game) return;
    api("duel/search", { game: duel.game, stake: duel.stake }).then(applyDuel);
  });
  $("duel-cancel-search").addEventListener("click", function () { api("duel/cancel_search").then(applyDuel); });
  $("duel-accept").addEventListener("click", function () {
    api("duel/accept", { duel_id: duel.state.duel_id }).then(applyDuel);
  });
  $("duel-leave").addEventListener("click", function () {
    api("duel/cancel", { duel_id: duel.state.duel_id }).then(applyDuel);
  });
  $("duel-open").addEventListener("click", function () {
    if (duel.state && duel.state.url) location.href = duel.state.url;
  });
  setInterval(function () {
    if (current === "duel" && duel.state && (duel.state.mode === "negotiating" || duel.state.mode === "searching")) drawDuel();
  }, 1000);

  // ------------------------------------------------------------------ رتبه‌ها
  function loadTop(period) {
    document.querySelectorAll("#top-periods button").forEach(function (b) { b.classList.toggle("on", b.dataset.period === period); });
    api("hub/top", { period: period }).then(function (data) {
      if (!data.ok) return;
      var list = $("top-list");
      list.textContent = "";
      if (!data.rows.length) list.appendChild(el("li", "", "هنوز کسی در این بازه بازی سکه‌ای نکرده است."));
      var medals = { 1: "🥇", 2: "🥈", 3: "🥉" };
      data.rows.forEach(function (row) {
        var li = el("li", row.me ? "me" : "");
        li.appendChild(el("span", "rank", medals[row.rank] || fa(row.rank)));
        var name = el("div", "name", (row.badge ? row.badge + " " : "") + row.name + (row.title ? " «" + row.title + "»" : ""));
        name.appendChild(el("small", "", fa(row.wins) + " برد · " + fa(row.games) + " بازی"));
        li.appendChild(name);
        li.appendChild(el("span", "val", money(row.coins) + " 🪙"));
        list.appendChild(li);
      });
    });
  }
  document.querySelectorAll("#top-periods button").forEach(function (b) {
    b.addEventListener("click", function () { loadTop(b.dataset.period); });
  });

  // ------------------------------------------------------------------ فروشگاه
  function loadShop() { api("hub/shop").then(drawShop); }
  /* خرید سکه: بسته‌ها و قیمت‌ها از سرور (همان منوی شارژ ربات). زدن هر بسته پیوی ربات را با همان بسته باز
     می‌کند: شماره کارت، مبلغ دقیق، ارسال رسید و تأیید مدیر همان‌جا انجام می‌شود. */
  function drawCoinShop(shop, coins) {
    var box = $("coin-shop");
    if (!shop || !BOOT.botUsername) { box.classList.add("hidden"); return; }
    box.classList.remove("hidden");
    $("coin-shop-balance").textContent = "موجودی: " + money(coins) + " 🪙";
    $("coin-shop-note").textContent = shop.ready
      ? "هر سکه " + money(shop.price) + " تومان" + (shop.fee_percent ? " + " + fa(shop.fee_percent) + "٪ کارمزد" : "")
      : "خرید سکه به‌زودی فعال می‌شود.";
    var packs = $("coin-packs");
    packs.textContent = "";
    shop.packs.forEach(function (pack) {
      var card = el("button", "pack");
      card.type = "button";
      card.disabled = !shop.ready;
      card.appendChild(el("b", "", money(pack.coins)));
      card.appendChild(el("small", "unit", "سکه"));
      card.appendChild(el("span", "price", money(pack.total) + " تومان"));
      card.addEventListener("click", function () { openBot(pack.start); });
      packs.appendChild(card);
    });
    $("coin-custom").disabled = !shop.ready;
    $("coin-sell-note").textContent = "💰 فروش: حداقل " + money(shop.min_sell) + " سکه، هر سکه " + money(shop.sell_price) +
      " تومان؛ واریز به کارت خودت بعد از بررسی مدیر.";
  }
  $("coin-custom").addEventListener("click", function () { openBot("topup_custom"); });
  $("coin-sell").addEventListener("click", function () { openBot("sell"); });

  function drawShop(data) {
    if (!data.ok) return;
    setCoins(data.coins);
    drawCoinShop(data.coin_shop, data.coins);
    var box = $("shop-kinds");
    box.textContent = "";
    var any = data.kinds.some(function (kind) { return kind.items.length; });
    if (!any) box.appendChild(el("p", "small muted soon", "🎨 آیتم‌های ظاهری به‌زودی اضافه می‌شوند."));
    data.kinds.forEach(function (kind) {
      if (!kind.items.length) return; // دسته‌ی خالی نشان داده نمی‌شود
      box.appendChild(el("h2", "", kind.title));
      var items = el("div", "items");
      kind.items.forEach(function (item) {
        var card = el("div", "item" + (item.equipped ? " equipped" : ""));
        card.appendChild(el("b", "", item.value));
        card.appendChild(el("small", "muted", item.name));
        var btn = el("button", "btn " + (item.owned ? (item.equipped ? "ghost" : "violet") : "go"));
        btn.type = "button";
        if (item.owned) {
          btn.textContent = item.equipped ? "✅ فعال (برداشتن)" : "فعال کن";
          btn.addEventListener("click", function () { api("hub/shop/equip", { item_id: item.id }).then(drawShop); });
        } else {
          btn.textContent = "خرید " + money(item.price) + " 🪙";
          btn.disabled = data.coins < item.price;
          btn.addEventListener("click", function () {
            var run = function () {
              api("hub/shop/buy", { item_id: item.id }).then(function (res) {
                if (res.ok) { haptic("success"); toast("خرید انجام شد"); loadMe(false); }
                drawShop(res);
              });
            };
            var question = "خرید «" + item.name + "» به قیمت " + money(item.price) + " سکه؟ قابل برگشت نیست.";
            if (tg && tg.showConfirm) { try { tg.showConfirm(question, function (ok) { if (ok) run(); }); return; } catch (e) { /* قدیمی */ } }
            if (window.confirm(question)) run();
          });
        }
        card.appendChild(btn);
        items.appendChild(card);
      });
      box.appendChild(items);
    });
  }

  // ------------------------------------------------------------------ شروع
  if (tg) {
    try {
      tg.ready();
      tg.expand();
      if (tg.setHeaderColor) tg.setHeaderColor("#141a2e");
      if (tg.setBackgroundColor) tg.setBackgroundColor("#0d1024");
      if (tg.disableVerticalSwipes) tg.disableVerticalSwipes();
    } catch (e) { /* نسخه‌های قدیمی */ }
  }
  $("join-check").addEventListener("click", function () {
    var button = this;
    button.disabled = true;
    api("hub/me", { fresh: true }).then(function (data) {
      button.disabled = false;
      if (!data.ok) return;
      $("join-gate").classList.add("hidden");
      haptic("success");
      toast("✅ عضویتت تأیید شد");
      loadMe(current === "me");
    });
  });
  drawGames();
  if (!initData) {
    $("me-name").textContent = "این صفحه باید از داخل تلگرام باز شود.";
    return;
  }
  loadMe(false);
  // اگر دوئلی در جریان است، مستقیم تب حریف باز می‌شود
  api("duel/state").then(function (data) {
    if (!data.ok) return;
    applyDuel(data);
    var mode = data.state.mode;
    if (BOOT.tab === "duel" || mode === "searching" || mode === "negotiating" || mode === "playing") show("duel");
  });
  document.addEventListener("visibilitychange", function () {
    if (!document.hidden && (current === "duel" || (duel.state && duel.state.mode !== "idle"))) loadDuel();
  });
})();
