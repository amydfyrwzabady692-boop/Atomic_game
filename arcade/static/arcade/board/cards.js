/* روی کارت‌ها مثل کارت واقعی: کارت‌های عددی همان تعداد نقش خال را با چیدمان استاندارد دارند (هفت خشت واقعاً هفت
   خشت دارد) و شاه، بی‌بی و سرباز تصویر دوسرِ خودشان را (شاه با تاج و ریش و شمشیر، بی‌بی با تاج کوچک و موی بلند و گل،
   سرباز با کلاه پردار و نیزه). نقش خال‌ها مسیر SVG است (نه نویسه) تا روی همه‌ی گوشی‌ها یکسان و بدون ایموجی کشیده شود.
   هر کارت یک بار به SVG تبدیل و به صورت data URI نگه داشته می‌شود؛ صفحه‌ها آن را پس‌زمینه‌ی کارت می‌کنند.
   استفاده: CardFaces.face("Td") یا CardFaces.apply(element, "Kh"). */
(function () {
  "use strict";

  var RED = "#d3163c";
  var BLACK = "#16181f";
  var GOLD = "#e2b23a";
  var GOLD_DARK = "#9a7413";
  var SKIN = "#f6d3b3";
  var SKIN_LINE = "#9b6a48";
  // نقش هر خال در جعبه‌ی ۱۰۰×۱۰۰ با مرکز (۵۰، ۵۰)
  var SUIT_PATHS = {
    h: "M50 92C50 92 4 61 4 31C4 15 16 5 30 5C39 5 46 10 50 18C54 10 61 5 70 5C84 5 96 15 96 31C96 61 50 92 50 92Z",
    d: "M50 2C61 21 74 36 90 50C74 64 61 79 50 98C39 79 26 64 10 50C26 36 39 21 50 2Z",
    s: "M50 3C50 3 7 36 7 60C7 74 18 84 31 84C39 84 45 80 48 74C47 84 42 92 33 97L67 97C58 92 53 84 52 74C55 80 61 84 69 84C82 84 93 74 93 60C93 36 50 3 50 3Z",
    c: "M50 6A20 20 0 0 0 33 37A20 20 0 1 0 47 64C46 79 41 89 33 97L67 97C59 89 54 79 53 64A20 20 0 1 0 67 37A20 20 0 0 0 50 6Z",
  };
  var NAMES = { s: "پیک", h: "دل", d: "خشت", c: "گشنیز" };
  var RANK_NAMES = { A: "آس", K: "شاه", Q: "بی‌بی", J: "سرباز", T: "۱۰" };
  // رنگ لباس شاه و بی‌بی و سرباز در هر خال (مثل کارت‌های کلاسیک، هر خال رنگ‌بندی خودش را دارد)
  var ROBES = {
    h: { robe: "#c8102e", accent: "#2c56a8", hair: "#b07a2a" },
    d: { robe: "#2c56a8", accent: "#c8102e", hair: "#8a5a22" },
    s: { robe: "#20283f", accent: "#e2b23a", hair: "#5b3a1e" },
    c: { robe: "#1e6b4a", accent: "#c8102e", hair: "#a0672a" },
  };
  // جای نقش‌ها در کارت‌های عددی (x، y) در کادر ۱۰۰×۱۴۰؛ نقش‌های نیمه‌ی پایین برعکس کشیده می‌شوند
  var L = 32;
  var C = 50;
  var R = 68;
  var TOP = 26;
  var BOT = 114;
  var MID = 70;
  var LAYOUT = {
    A: [[C, MID]],
    2: [[C, TOP], [C, BOT]],
    3: [[C, TOP], [C, MID], [C, BOT]],
    4: [[L, TOP], [R, TOP], [L, BOT], [R, BOT]],
    5: [[L, TOP], [R, TOP], [C, MID], [L, BOT], [R, BOT]],
    6: [[L, TOP], [R, TOP], [L, MID], [R, MID], [L, BOT], [R, BOT]],
    7: [[L, TOP], [R, TOP], [C, 48], [L, MID], [R, MID], [L, BOT], [R, BOT]],
    8: [[L, TOP], [R, TOP], [C, 48], [L, MID], [R, MID], [C, 92], [L, BOT], [R, BOT]],
    9: [[L, TOP], [R, TOP], [L, 55.3], [R, 55.3], [C, MID], [L, 84.7], [R, 84.7], [L, BOT], [R, BOT]],
    T: [[L, TOP], [R, TOP], [C, 40.7], [L, 55.3], [R, 55.3], [L, 84.7], [R, 84.7], [C, 99.3], [L, BOT], [R, BOT]],
  };
  var cache = {};

  function color(suit) { return suit === "h" || suit === "d" ? RED : BLACK; }
  function pip(suit, x, y, size, flip, fill) {
    var s = size / 100;
    var transform = "translate(" + (x - size / 2).toFixed(2) + " " + (y - size / 2).toFixed(2) + ") scale(" + s.toFixed(4) + ")";
    if (flip) transform = "rotate(180 " + x + " " + y + ") " + transform;
    return '<path d="' + SUIT_PATHS[suit] + '" transform="' + transform + '" fill="' + (fill || color(suit)) + '"/>';
  }
  function corner(rank, suit) {
    var label = rank === "T" ? "10" : rank;
    var size = rank === "T" ? 19 : 23;
    var spacing = rank === "T" ? ' letter-spacing="-1.5"' : "";
    var index = '<text x="12.5" y="25" text-anchor="middle" font-family="Georgia, \'Times New Roman\', Times, serif" font-weight="700" font-size="' +
      size + '"' + spacing + ' fill="' + color(suit) + '">' + label + "</text>" + pip(suit, 12.5, 36, 13);
    return index + '<g transform="rotate(180 50 70)">' + index + "</g>";
  }

  // ------------------------------------------------------------------ تصویر شاه، بی‌بی و سرباز (نیمه‌ی بالا)
  function face(skinX, skinY) {
    return '<ellipse cx="' + skinX + '" cy="' + skinY + '" rx="7.6" ry="9" fill="' + SKIN + '" stroke="' + SKIN_LINE + '" stroke-width=".6"/>' +
      '<circle cx="' + (skinX - 3) + '" cy="' + (skinY - 1) + '" r=".95" fill="#2b1a10"/>' +
      '<circle cx="' + (skinX + 3) + '" cy="' + (skinY - 1) + '" r=".95" fill="#2b1a10"/>' +
      '<path d="M' + (skinX - 4.4) + " " + (skinY - 3) + " q1.4 -1 2.8 0 M" + (skinX + 1.6) + " " + (skinY - 3) + ' q1.4 -1 2.8 0" stroke="#5a3a22" stroke-width=".55" fill="none"/>' +
      '<path d="M' + skinX + " " + (skinY - .5) + " l-1 3 h2" + '" stroke="' + SKIN_LINE + '" stroke-width=".55" fill="none"/>';
  }
  function robe(colors) {
    return '<path d="M24 70V59Q26 49 38 46H62Q74 49 76 59V70Z" fill="' + colors.robe + '" stroke="' + GOLD_DARK + '" stroke-width=".6"/>' +
      '<rect x="46" y="51" width="8" height="19" fill="' + colors.accent + '"/>' +
      '<circle cx="50" cy="56" r="1.3" fill="#fff"/><circle cx="50" cy="62" r="1.3" fill="#fff"/><circle cx="50" cy="68" r="1.3" fill="#fff"/>' +
      '<path d="M26 58Q50 66 74 58V61.5Q50 69 26 61.5Z" fill="#fff" stroke="' + GOLD_DARK + '" stroke-width=".4"/>' +
      '<path d="M33 60.5l1 1.6M41 62.4l1 1.6M57 62.4l1 1.6M65 60.5l1 1.6" stroke="#16181f" stroke-width="1"/>' +
      '<path d="M38 46Q50 55 62 46L60 50Q50 59 40 50Z" fill="' + GOLD + '" stroke="' + GOLD_DARK + '" stroke-width=".4"/>' +
      '<rect x="46" y="40" width="8" height="7" fill="' + SKIN + '"/>';
  }
  function king(suit) {
    var c = ROBES[suit];
    return robe(c) +
      // شمشیر
      '<path d="M69.5 19V60" stroke="#c7ced9" stroke-width="2.4"/><path d="M69.5 19V60" stroke="#fff" stroke-width=".6" opacity=".7"/>' +
      '<rect x="65.6" y="24" width="7.8" height="2" rx=".8" fill="' + GOLD + '" stroke="' + GOLD_DARK + '" stroke-width=".4"/>' +
      '<path d="M69.5 17.5V24" stroke="#7a4a20" stroke-width="2"/><circle cx="69.5" cy="16.6" r="1.6" fill="' + GOLD + '"/>' +
      // مو، صورت، ریش و سبیل
      '<path d="M41.6 31Q40 41 43.5 46L46 41Q43.8 36 44.6 30Z M58.4 31Q60 41 56.5 46L54 41Q56.2 36 55.4 30Z" fill="' + c.hair + '"/>' +
      face(50, 33) +
      '<path d="M42.5 35.5Q42.5 47 50 49.5Q57.5 47 57.5 35.5Q55 42 50 42Q45 42 42.5 35.5Z" fill="' + c.hair + '" stroke="#5a3a1a" stroke-width=".4"/>' +
      '<path d="M45 38.6Q50 36.4 55 38.6Q50 40.2 45 38.6Z" fill="#6b4420"/>' +
      // تاج
      '<path d="M41 24V15.5L45.2 19.6L50 13L54.8 19.6L59 15.5V24Z" fill="' + GOLD + '" stroke="' + GOLD_DARK + '" stroke-width=".6"/>' +
      '<rect x="40.6" y="22.6" width="18.8" height="4" rx=".8" fill="' + GOLD + '" stroke="' + GOLD_DARK + '" stroke-width=".6"/>' +
      '<circle cx="50" cy="24.6" r="1.4" fill="#c8102e"/><circle cx="44.8" cy="24.6" r="1" fill="#2c56a8"/><circle cx="55.2" cy="24.6" r="1" fill="#2c56a8"/>' +
      '<circle cx="41" cy="15.3" r="1.1" fill="' + GOLD + '"/><circle cx="50" cy="12.8" r="1.3" fill="' + GOLD + '"/><circle cx="59" cy="15.3" r="1.1" fill="' + GOLD + '"/>';
  }
  function queen(suit) {
    var c = ROBES[suit];
    return robe(c) +
      // موی بلند پشت سر
      '<path d="M42 27Q36.5 42 38 52L44.5 49Q42.5 40 44.5 29Z M58 27Q63.5 42 62 52L55.5 49Q57.5 40 55.5 29Z" fill="#6b3a1c"/>' +
      '<path d="M42.4 29Q50 21.5 57.6 29Q50 25.5 42.4 29Z" fill="#6b3a1c"/>' +
      face(50, 33.5) +
      // لب و گونه
      '<path d="M48 38.9Q50 40.2 52 38.9Q50 39.4 48 38.9Z" fill="#c8102e"/>' +
      '<circle cx="45.4" cy="36.6" r="1.6" fill="#f08aa0" opacity=".5"/><circle cx="54.6" cy="36.6" r="1.6" fill="#f08aa0" opacity=".5"/>' +
      // گردنبند
      '<path d="M44 46.6Q50 51 56 46.6" stroke="' + GOLD + '" stroke-width="1" fill="none" stroke-dasharray="1.2 1"/>' +
      // تاج کوچک
      '<path d="M43 25V19.6L46.4 22.2L50 16.6L53.6 22.2L57 19.6V25Z" fill="' + GOLD + '" stroke="' + GOLD_DARK + '" stroke-width=".55"/>' +
      '<rect x="42.6" y="23.8" width="14.8" height="3" rx=".7" fill="' + GOLD + '" stroke="' + GOLD_DARK + '" stroke-width=".5"/>' +
      '<circle cx="50" cy="21.6" r="1.3" fill="#c8102e"/><circle cx="50" cy="16.4" r="1" fill="' + GOLD + '"/>' +
      // گل در دست
      '<path d="M66 60Q64.5 50 64.8 41" stroke="#2f7d32" stroke-width="1.1" fill="none"/>' +
      '<path d="M65 49q-4 -1 -5 -4q4 0 5 4Z" fill="#2f7d32"/>' +
      '<g fill="#e8486a"><circle cx="64.8" cy="35.6" r="2.3"/><circle cx="62" cy="38.4" r="2.3"/><circle cx="67.6" cy="38.4" r="2.3"/><circle cx="63" cy="41.6" r="2.3"/><circle cx="66.6" cy="41.6" r="2.3"/></g>' +
      '<circle cx="64.8" cy="39" r="1.6" fill="' + GOLD + '"/>';
  }
  function jack(suit) {
    var c = ROBES[suit];
    return robe(c) +
      // نیزه (هالبرد)
      '<path d="M30.5 14V62" stroke="#8a5a2b" stroke-width="2"/>' +
      '<path d="M30.5 9L32.4 15H28.6Z" fill="#c7ced9" stroke="#7d8696" stroke-width=".4"/>' +
      '<path d="M30.5 17Q23.4 18.6 22.6 25.4Q27 23 30.5 24.6Z" fill="#c7ced9" stroke="#7d8696" stroke-width=".4"/>' +
      // موی کوتاه
      '<path d="M42.4 30Q41.2 38.4 44 42L45.6 37Q44.2 33 45 29Z M57.6 30Q58.8 38.4 56 42L54.4 37Q55.8 33 55 29Z" fill="' + c.hair + '"/>' +
      face(50, 34) +
      '<path d="M48.2 39.4Q50 40.4 51.8 39.4" stroke="#8a4b2a" stroke-width=".6" fill="none"/>' +
      // کلاه پردار
      '<path d="M40.4 28Q41.6 18.6 51.4 18.4Q61.2 18.8 61 26.6Q50.6 23.8 40.4 28Z" fill="' + c.robe + '" stroke="' + GOLD_DARK + '" stroke-width=".5"/>' +
      '<path d="M40.4 28Q50.6 23.8 61 26.6L61 29Q50.6 26.2 40.6 30.4Z" fill="' + GOLD + '" stroke="' + GOLD_DARK + '" stroke-width=".4"/>' +
      '<path d="M57.6 21Q65 13.6 73 12.4Q67.4 17.6 60.6 23.8Z" fill="#f7f7f7" stroke="#b9bec9" stroke-width=".5"/>' +
      '<path d="M59 22.4Q65 16 71.4 13.4" stroke="#b9bec9" stroke-width=".4" fill="none"/>';
  }
  function court(rank, suit) {
    var draw = rank === "K" ? king : rank === "Q" ? queen : jack;
    // تصویر کمی پایین‌تر تا تاج و کلاه داخل قاب بمانند؛ نقش کوچک خال کنار سر (سرباز جایش نیزه دارد)
    var half = '<g transform="translate(0 3.5)">' + draw(suit) + "</g>" + (rank === "J" ? "" : pip(suit, 26, 23, 9));
    return '<rect x="19" y="15" width="62" height="110" rx="2.5" fill="#fbf3dc" stroke="' + GOLD_DARK + '" stroke-width="1"/>' +
      '<clipPath id="half"><rect x="19.5" y="15.5" width="61" height="54.5"/></clipPath>' +
      '<g clip-path="url(#half)">' + half + "</g>" +
      '<g transform="rotate(180 50 70)"><g clip-path="url(#half)">' + half + "</g></g>" +
      '<path d="M19.5 70H80.5" stroke="' + GOLD_DARK + '" stroke-width=".9"/>' +
      '<rect x="21" y="17" width="58" height="106" rx="1.6" fill="none" stroke="' + GOLD + '" stroke-width=".7"/>';
  }

  function svg(code) {
    var rank = code[0];
    var suit = code[1];
    var body;
    if (rank === "K" || rank === "Q" || rank === "J") body = court(rank, suit);
    else if (rank === "A") {
      // آس: یک نقش بزرگ وسط کارت (آس پیک با حلقه‌ی تزئینی، مثل کارت‌های واقعی)
      body = (suit === "s" ? '<circle cx="50" cy="70" r="31" fill="none" stroke="' + GOLD + '" stroke-width="1.4"/>' : "") +
        pip(suit, 50, 70, suit === "s" ? 50 : 42);
    } else {
      var size = rank === "9" || rank === "T" ? 17 : 19;
      body = (LAYOUT[rank] || []).map(function (p) { return pip(suit, p[0], p[1], size, p[1] > MID + 0.1); }).join("");
    }
    return '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 140">' + body + corner(rank, suit) + "</svg>";
  }
  function faceUrl(code) {
    if (!cache[code]) cache[code] = "data:image/svg+xml;charset=utf-8," + encodeURIComponent(svg(code));
    return cache[code];
  }
  function label(code) {
    return (RANK_NAMES[code[0]] || code[0]) + " " + NAMES[code[1]];
  }
  // کارت را با تصویر کامل همان کارت می‌پوشاند (برچسب متنی برای خواندن صفحه می‌ماند)
  function apply(node, code) {
    node.classList.add("face");
    node.style.backgroundImage = 'url("' + faceUrl(code) + '")';
    node.setAttribute("role", "img");
    node.setAttribute("aria-label", label(code));
    return node;
  }

  window.CardFaces = { face: faceUrl, svg: svg, apply: apply, label: label, layout: LAYOUT };
})();
