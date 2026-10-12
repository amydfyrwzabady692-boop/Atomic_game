/* جعبه‌ابزار گرافیکی مشترک بازی‌ها: رنگ، نور و سایه و متریال‌ها (چوب، فلز، سنگ، چمن).
   همه‌ی تابع‌ها روی هر context دوبعدی کار می‌کنند؛ کارهای سنگین (بافت‌ها) فقط یک بار داخل
   اسپرایت‌های کش‌شده‌ی env.sprite کشیده می‌شوند تا هر فریم فقط drawImage بماند. */
(function (root) {
  "use strict";
  var TAU = Math.PI * 2;

  // ------------------------------------------------------------------ رنگ
  var parsed = {};
  function parse(color) {
    var hit = parsed[color];
    if (hit) return hit;
    var hex = color.charAt(0) === "#" ? color.slice(1) : "888888";
    if (hex.length === 3) hex = hex[0] + hex[0] + hex[1] + hex[1] + hex[2] + hex[2];
    var n = parseInt(hex, 16);
    hit = parsed[color] = [(n >> 16) & 255, (n >> 8) & 255, n & 255];
    return hit;
  }
  function rgb(r, g, b) { return "rgb(" + Math.round(r) + "," + Math.round(g) + "," + Math.round(b) + ")"; }
  /* amount مثبت: روشن‌تر (به سمت سفید)، منفی: تیره‌تر (به سمت سیاه) */
  function shade(color, amount) {
    var p = parse(color), t = amount < 0 ? 0 : 255, k = Math.abs(amount);
    return rgb(p[0] + (t - p[0]) * k, p[1] + (t - p[1]) * k, p[2] + (t - p[2]) * k);
  }
  function mix(a, b, t) {
    var p = parse(a), q = parse(b);
    return rgb(p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t, p[2] + (q[2] - p[2]) * t);
  }
  function alpha(color, a) {
    var p = parse(color);
    return "rgba(" + p[0] + "," + p[1] + "," + p[2] + "," + a + ")";
  }
  /* عدد تصادفی قطعی: بافت‌ها در هر بار اجرا یک شکل‌اند */
  function rand(seed) {
    var s = seed >>> 0;
    return function () {
      s = (s + 0x6d2b79f5) >>> 0;
      var t = Math.imul(s ^ (s >>> 15), 1 | s);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }

  root.ArcadeArt = function (env) {
    var art = { TAU: TAU, shade: shade, mix: mix, alpha: alpha, rand: rand };

    function rr(c, x, y, w, h, r) { env.roundRect(c, x, y, w, h, r); }
    art.rr = rr;

    // ---------------------------------------------------------------- نور و سایه
    /* سایه‌ی نرم زیر اجسام: یک اسپرایت شعاعی که کشیده و فشرده می‌شود (بدون shadowBlur) */
    art.shadow = function (c, x, y, rx, ry, a) {
      var sp = env.sprite("art:shadow", 64, 64, function (s) {
        var g = s.createRadialGradient(32, 32, 0, 32, 32, 32);
        g.addColorStop(0, "rgba(0,0,0,.85)");
        g.addColorStop(0.55, "rgba(0,0,0,.4)");
        g.addColorStop(1, "rgba(0,0,0,0)");
        s.fillStyle = g;
        s.fillRect(0, 0, 64, 64);
      });
      var old = c.globalAlpha;
      c.globalAlpha = old * (a === undefined ? 0.4 : a);
      c.drawImage(sp.canvas, x - rx, y - ry, rx * 2, ry * 2);
      c.globalAlpha = old;
    };

    /* هاله‌ی نور افزودنی */
    art.glow = function (c, x, y, r, color, a) {
      var sp = env.sprite("art:glow:" + color, 64, 64, function (s) {
        var g = s.createRadialGradient(32, 32, 0, 32, 32, 32);
        g.addColorStop(0, alpha(color, 0.9));
        g.addColorStop(0.35, alpha(color, 0.35));
        g.addColorStop(1, alpha(color, 0));
        s.fillStyle = g;
        s.fillRect(0, 0, 64, 64);
      });
      var old = c.globalAlpha, op = c.globalCompositeOperation;
      c.globalAlpha = old * (a === undefined ? 1 : a);
      c.globalCompositeOperation = "lighter";
      c.drawImage(sp.canvas, x - r, y - r, r * 2, r * 2);
      c.globalCompositeOperation = op;
      c.globalAlpha = old;
    };

    /* کره‌ی سایه‌خورده با برق نور */
    art.sphere = function (c, x, y, r, color, gloss) {
      var g = c.createRadialGradient(x - r * 0.35, y - r * 0.42, r * 0.05, x, y, r);
      g.addColorStop(0, shade(color, 0.7));
      g.addColorStop(0.3, shade(color, 0.18));
      g.addColorStop(0.72, color);
      g.addColorStop(1, shade(color, -0.5));
      c.fillStyle = g;
      c.beginPath();
      c.arc(x, y, r, 0, TAU);
      c.fill();
      if (gloss !== false) {
        c.fillStyle = "rgba(255,255,255,.55)";
        c.beginPath();
        c.ellipse(x - r * 0.34, y - r * 0.46, r * 0.26, r * 0.15, -0.6, 0, TAU);
        c.fill();
      }
    };

    /* بلوک برجسته (پلاستیک/سرامیک): نور از بالا، سایه در پایین و خط دور */
    art.bevel = function (c, x, y, w, h, r, color, depth) {
      depth = depth === undefined ? 1 : depth;
      var g = c.createLinearGradient(0, y, 0, y + h);
      g.addColorStop(0, shade(color, 0.28 * depth));
      g.addColorStop(0.45, color);
      g.addColorStop(1, shade(color, -0.3 * depth));
      c.fillStyle = g;
      rr(c, x, y, w, h, r);
      c.fill();
      var old = c.globalAlpha;
      c.strokeStyle = shade(color, -0.5);
      c.globalAlpha = old * 0.55;
      c.lineWidth = 1;
      c.stroke();
      c.globalAlpha = old;
      // برق لبه‌ی بالا
      var hl = c.createLinearGradient(0, y, 0, y + Math.min(h * 0.5, 14));
      hl.addColorStop(0, "rgba(255,255,255," + 0.5 * depth + ")");
      hl.addColorStop(1, "rgba(255,255,255,0)");
      c.fillStyle = hl;
      rr(c, x + 1.5, y + 1.5, w - 3, Math.min(h * 0.5, 14), Math.max(1, r - 1.5));
      c.fill();
    };

    /* دانه‌ی ریز برای حس متریال: یک کاشی نویز که به‌صورت pattern پر می‌شود */
    var grainTile = null;
    art.grain = function (c, x, y, w, h, a) {
      if (!grainTile) {
        grainTile = document.createElement("canvas");
        grainTile.width = grainTile.height = 96;
        var gc = grainTile.getContext("2d");
        var img = gc.createImageData(96, 96), rnd = rand(7);
        for (var i = 0; i < img.data.length; i += 4) {
          var v = rnd() < 0.5 ? 0 : 255;
          img.data[i] = img.data[i + 1] = img.data[i + 2] = v;
          img.data[i + 3] = Math.floor(rnd() * 70);
        }
        gc.putImageData(img, 0, 0);
      }
      c.save();
      c.globalAlpha *= a === undefined ? 0.25 : a;
      c.beginPath();
      c.rect(x, y, w, h);
      c.clip();
      // pattern با مقیاس ثابت روی پیکسل واقعی (مستقل از بزرگ‌نمایی اسپرایت)
      var res = env.res || 1;
      c.scale(1 / res, 1 / res);
      c.fillStyle = c.createPattern(grainTile, "repeat");
      c.fillRect(x * res, y * res, w * res, h * res);
      c.restore();
    };

    // ---------------------------------------------------------------- متریال‌ها
    /* چوب با رگه‌های طولی. opts: base, seed, horizontal, round (سایه‌ی استوانه‌ای), knots */
    art.wood = function (c, x, y, w, h, opts) {
      opts = opts || {};
      var base = opts.base || "#9a6234";
      var rnd = rand(opts.seed || 1);
      var horizontal = !!opts.horizontal;
      c.save();
      c.beginPath();
      c.rect(x, y, w, h);
      c.clip();
      var g = horizontal ? c.createLinearGradient(0, y, 0, y + h) : c.createLinearGradient(x, 0, x + w, 0);
      if (opts.round) {
        g.addColorStop(0, shade(base, -0.38));
        g.addColorStop(0.28, shade(base, 0.12));
        g.addColorStop(0.55, base);
        g.addColorStop(1, shade(base, -0.5));
      } else {
        g.addColorStop(0, shade(base, 0.06));
        g.addColorStop(1, shade(base, -0.12));
      }
      c.fillStyle = g;
      c.fillRect(x, y, w, h);
      var across = horizontal ? h : w, along = horizontal ? w : h;
      var lines = Math.max(6, Math.round(across / 3.2));
      c.lineCap = "round";
      for (var i = 0; i < lines; i++) {
        var p = (i + rnd() * 0.8) / lines * across;
        var dark = rnd() < 0.7;
        c.strokeStyle = dark ? alpha("#2a1608", 0.08 + rnd() * 0.2) : "rgba(255,230,190," + (0.05 + rnd() * 0.1) + ")";
        c.lineWidth = 0.5 + rnd() * 1.4;
        c.beginPath();
        var wob = (rnd() - 0.5) * 5, steps = 6;
        for (var s = 0; s <= steps; s++) {
          var q = (s / steps) * along;
          var off = Math.sin(s * 1.3 + i) * wob * 0.4 + (rnd() - 0.5) * 1.2;
          if (horizontal) { if (s) c.lineTo(x + q, y + p + off); else c.moveTo(x + q, y + p + off); }
          else if (s) c.lineTo(x + p + off, y + q);
          else c.moveTo(x + p + off, y + q);
        }
        c.stroke();
      }
      var knots = opts.knots === undefined ? Math.round((w * h) / 9000) : opts.knots;
      for (var k = 0; k < knots; k++) {
        var kx = x + w * (0.15 + rnd() * 0.7), ky = y + h * (0.15 + rnd() * 0.7), kr = 2.5 + rnd() * 4;
        for (var ring = 3; ring >= 1; ring--) {
          c.strokeStyle = alpha("#2a1608", 0.16 + 0.1 * (3 - ring));
          c.lineWidth = 1;
          c.beginPath();
          c.ellipse(kx, ky, horizontal ? kr * ring * 1.5 : kr * ring * 0.7, horizontal ? kr * ring * 0.7 : kr * ring * 1.5, 0, 0, TAU);
          c.stroke();
        }
        c.fillStyle = alpha("#24120a", 0.55);
        c.beginPath();
        c.ellipse(kx, ky, kr * 0.7, kr * 0.7, 0, 0, TAU);
        c.fill();
      }
      c.restore();
    };

    /* برش عرضی تنه‌ی درخت: حلقه‌های سالیانه، ترک‌ها و پوست دور آن */
    art.logSlice = function (c, cx, cy, r, opts) {
      opts = opts || {};
      var base = opts.base || "#c8935a", bark = opts.bark || "#4a2c17";
      var rnd = rand(opts.seed || 3);
      // پوست
      c.fillStyle = bark;
      c.beginPath();
      for (var a = 0; a <= 48; a++) {
        var ang = (a / 48) * TAU, rr2 = r * (1 + (rnd() - 0.5) * 0.035);
        if (a) c.lineTo(cx + Math.cos(ang) * rr2, cy + Math.sin(ang) * rr2);
        else c.moveTo(cx + Math.cos(ang) * rr2, cy + Math.sin(ang) * rr2);
      }
      c.closePath();
      c.fill();
      // چوب
      var inner = r * 0.9;
      var g = c.createRadialGradient(cx - r * 0.25, cy - r * 0.3, r * 0.05, cx, cy, inner);
      g.addColorStop(0, shade(base, 0.3));
      g.addColorStop(0.6, base);
      g.addColorStop(1, shade(base, -0.28));
      c.fillStyle = g;
      c.beginPath();
      c.arc(cx, cy, inner, 0, TAU);
      c.fill();
      // حلقه‌ها
      var rings = Math.max(5, Math.round(inner / 5.5));
      for (var i = 1; i <= rings; i++) {
        var rad = (i / (rings + 0.6)) * inner;
        c.strokeStyle = alpha("#5a3414", 0.16 + rnd() * 0.22);
        c.lineWidth = 0.6 + rnd() * 1.1;
        c.beginPath();
        var wob = rnd() * 0.05, ph = rnd() * TAU;
        for (var t = 0; t <= 40; t++) {
          var th = (t / 40) * TAU, rw = rad * (1 + Math.sin(th * 3 + ph) * wob);
          if (t) c.lineTo(cx + Math.cos(th) * rw, cy + Math.sin(th) * rw);
          else c.moveTo(cx + Math.cos(th) * rw, cy + Math.sin(th) * rw);
        }
        c.closePath();
        c.stroke();
      }
      // ترک‌های شعاعی
      c.strokeStyle = alpha("#3a2110", 0.5);
      c.lineCap = "round";
      for (var k = 0; k < 5; k++) {
        var ca = rnd() * TAU, c0 = inner * (0.1 + rnd() * 0.25), c1 = inner * (0.55 + rnd() * 0.4);
        c.lineWidth = 0.8 + rnd();
        c.beginPath();
        c.moveTo(cx + Math.cos(ca) * c0, cy + Math.sin(ca) * c0);
        c.lineTo(cx + Math.cos(ca + 0.04) * c1, cy + Math.sin(ca + 0.04) * c1);
        c.stroke();
      }
      // مغز چوب
      c.fillStyle = alpha("#6b3f1c", 0.75);
      c.beginPath();
      c.arc(cx, cy, Math.max(1.5, r * 0.035), 0, TAU);
      c.fill();
      // لبه‌ی داخلی پوست و برق بالا
      c.strokeStyle = alpha("#2b170b", 0.6);
      c.lineWidth = 1.2;
      c.beginPath();
      c.arc(cx, cy, inner, 0, TAU);
      c.stroke();
      c.strokeStyle = "rgba(255,255,255,.18)";
      c.lineWidth = 1.5;
      c.beginPath();
      c.arc(cx, cy, r * 0.97, Math.PI * 1.1, Math.PI * 1.75);
      c.stroke();
    };

    /* فلز برس‌خورده. opts: base, vertical, bands */
    art.metal = function (c, x, y, w, h, opts) {
      opts = opts || {};
      var base = opts.base || "#a9b4c6";
      var g = opts.vertical ? c.createLinearGradient(x, 0, x + w, 0) : c.createLinearGradient(0, y, 0, y + h);
      g.addColorStop(0, shade(base, 0.55));
      g.addColorStop(0.22, shade(base, 0.12));
      g.addColorStop(0.5, shade(base, -0.22));
      g.addColorStop(0.7, shade(base, 0.2));
      g.addColorStop(1, shade(base, -0.45));
      c.fillStyle = g;
      c.fillRect(x, y, w, h);
    };

    /* چمن: دو تُن سبز با لکه‌های نور و تیغه‌های ریز */
    art.grass = function (c, x, y, w, h, opts) {
      opts = opts || {};
      var base = opts.base || "#4c9a3f";
      var rnd = rand(opts.seed || 11);
      var g = c.createLinearGradient(0, y, 0, y + h);
      g.addColorStop(0, shade(base, 0.1));
      g.addColorStop(1, shade(base, -0.18));
      c.fillStyle = g;
      c.fillRect(x, y, w, h);
      var blades = Math.round((w * h) / (opts.density || 46));
      c.lineCap = "round";
      for (var i = 0; i < blades; i++) {
        var bx = x + rnd() * w, by = y + rnd() * h, len = 2 + rnd() * 4;
        c.strokeStyle = rnd() < 0.5 ? alpha("#1f5a23", 0.25 + rnd() * 0.25) : "rgba(190,240,140," + (0.12 + rnd() * 0.2) + ")";
        c.lineWidth = 0.7 + rnd() * 0.6;
        c.beginPath();
        c.moveTo(bx, by);
        c.lineTo(bx + (rnd() - 0.5) * 2.4, by - len);
        c.stroke();
      }
    };

    /* خاک/سنگ دانه‌دار */
    art.speckle = function (c, x, y, w, h, color, count, seed) {
      var rnd = rand(seed || 5);
      for (var i = 0; i < count; i++) {
        c.fillStyle = alpha(color, 0.08 + rnd() * 0.25);
        var s = 0.6 + rnd() * 2.2;
        c.fillRect(x + rnd() * w, y + rnd() * h, s, s * (0.6 + rnd() * 0.6));
      }
    };

    /* تاریکی ملایم گوشه‌ها برای عمق صحنه */
    art.vignette = function (c, w, h, strength) {
      var g = c.createRadialGradient(w / 2, h * 0.45, Math.min(w, h) * 0.3, w / 2, h * 0.5, Math.max(w, h) * 0.78);
      g.addColorStop(0, "rgba(0,0,0,0)");
      g.addColorStop(1, "rgba(0,0,0," + (strength === undefined ? 0.5 : strength) + ")");
      c.fillStyle = g;
      c.fillRect(-20, -20, w + 40, h + 40);
    };

    /* ابر پف‌دار از چند کره‌ی سایه‌خورده */
    /* ابر حجیم: توده‌ای از پف‌های نرم با لبه‌ی محو، کف صاف‌تر و سایه‌ی آبی-خاکستری در پایین.
       ارتفاع ابر ‎0.5×w‎ است. seed شکل پف‌ها را عوض می‌کند. */
    art.cloud = function (c, x, y, w, top, bottom, seed) {
      top = top || "#ffffff";
      bottom = bottom || "#aab9d8";
      var h = w * 0.5;
      var rnd = rand(seed || 1);
      var lw = Math.ceil(w), lh = Math.ceil(h);
      // ابر در لایه‌ی جدا ساخته می‌شود تا سایه فقط روی خود ابر بنشیند
      var layer = document.createElement("canvas");
      var res = env.res || 1;
      layer.width = Math.ceil(lw * res);
      layer.height = Math.ceil(lh * res);
      var l = layer.getContext("2d");
      l.scale(res, res);
      var puffs = [];
      var count = 7 + Math.floor(rnd() * 3);
      for (var i = 0; i < count; i++) {
        var t = (i + 0.5) / count;
        // وسط بلندتر، کناره‌ها کوتاه‌تر
        var arch = Math.sin(t * Math.PI);
        var r = w * (0.1 + arch * 0.085 + rnd() * 0.02);
        puffs.push([w * (0.13 + t * 0.74), Math.max(r + 1, h * (0.76 - arch * 0.3 - rnd() * 0.05)), r]);
      }
      puffs.push([w * 0.3, h * 0.74, w * 0.15], [w * 0.52, h * 0.76, w * 0.17], [w * 0.72, h * 0.74, w * 0.14]);
      for (i = 0; i < puffs.length; i++) {
        var px = puffs[i][0], py = puffs[i][1], pr = puffs[i][2];
        var g = l.createRadialGradient(px, py, pr * 0.55, px, py, pr);
        g.addColorStop(0, top);
        g.addColorStop(1, alpha(top.charAt(0) === "#" ? top : "#ffffff", 0));
        l.fillStyle = g;
        l.beginPath();
        l.arc(px, py, pr, 0, TAU);
        l.fill();
      }
      // کف ابر صاف‌تر است
      l.globalCompositeOperation = "destination-out";
      var cut = l.createLinearGradient(0, h * 0.84, 0, h);
      cut.addColorStop(0, "rgba(0,0,0,0)");
      cut.addColorStop(1, "rgba(0,0,0,1)");
      l.fillStyle = cut;
      l.fillRect(0, h * 0.84, w, h * 0.2);
      // سایه‌ی پایین و نور بالا فقط روی خود ابر
      l.globalCompositeOperation = "source-atop";
      var shade = l.createLinearGradient(0, h * 0.3, 0, h * 0.92);
      shade.addColorStop(0, alpha(bottom.charAt(0) === "#" ? bottom : "#aab9d8", 0));
      shade.addColorStop(1, alpha(bottom.charAt(0) === "#" ? bottom : "#aab9d8", 0.85));
      l.fillStyle = shade;
      l.fillRect(0, 0, w, h);
      for (i = 0; i < puffs.length - 3; i++) {
        var hx = puffs[i][0] - puffs[i][2] * 0.25, hy = puffs[i][1] - puffs[i][2] * 0.35, hr = puffs[i][2] * 0.7;
        var hg = l.createRadialGradient(hx, hy, 0, hx, hy, hr);
        hg.addColorStop(0, "rgba(255,255,255,.75)");
        hg.addColorStop(1, "rgba(255,255,255,0)");
        l.fillStyle = hg;
        l.fillRect(hx - hr, hy - hr, hr * 2, hr * 2);
      }
      c.drawImage(layer, x, y, lw, lh);
    };

    /* درخت پهن‌برگ: تنه و تاجی از چند توده‌ی برگ */
    art.tree = function (c, x, base, h, tone, seed) {
      tone = tone || "#3f9a4c";
      var rnd = rand(seed || 2);
      var trunkW = h * 0.09;
      var tg = c.createLinearGradient(x - trunkW, 0, x + trunkW, 0);
      tg.addColorStop(0, "#7a4e2a");
      tg.addColorStop(1, "#3f2613");
      c.fillStyle = tg;
      c.beginPath();
      c.moveTo(x - trunkW * 0.6, base - h * 0.5);
      c.lineTo(x + trunkW * 0.6, base - h * 0.5);
      c.lineTo(x + trunkW, base);
      c.lineTo(x - trunkW, base);
      c.closePath();
      c.fill();
      var crown = [[0, -0.48, 0.22], [-0.21, -0.56, 0.24], [0.21, -0.58, 0.24], [0, -0.66, 0.3], [-0.1, -0.8, 0.22], [0.12, -0.8, 0.2]];
      for (var i = 0; i < crown.length; i++) {
        var jitter = (rnd() - 0.5) * 0.04;
        art.leaves(c, x + (crown[i][0] + jitter) * h, base + crown[i][1] * h, crown[i][2] * h, shade(tone, (rnd() - 0.5) * 0.2));
      }
    };

    /* توده‌ی برگ: سایه‌روشن مات (بدون برق) با لکه‌های ریز نور */
    art.leaves = function (c, x, y, r, tone) {
      var g = c.createRadialGradient(x - r * 0.35, y - r * 0.4, r * 0.1, x, y, r);
      g.addColorStop(0, shade(tone, 0.3));
      g.addColorStop(0.55, tone);
      g.addColorStop(1, shade(tone, -0.42));
      c.fillStyle = g;
      c.beginPath();
      c.arc(x, y, r, 0, TAU);
      c.fill();
      var rnd = rand(Math.round(x * 7 + y * 13 + r));
      c.fillStyle = shade(tone, 0.45);
      for (var i = 0; i < 7; i++) {
        var a = rnd() * TAU, d = rnd() * r * 0.75;
        c.globalAlpha = 0.35;
        c.beginPath();
        c.ellipse(x + Math.cos(a) * d - r * 0.15, y + Math.sin(a) * d - r * 0.15, r * 0.13, r * 0.07, a, 0, TAU);
        c.fill();
      }
      c.globalAlpha = 1;
    };

    /* بوته‌ی کوچک */
    art.bush = function (c, x, base, w, tone) {
      tone = tone || "#2f8f46";
      art.leaves(c, x - w * 0.25, base - w * 0.2, w * 0.28, shade(tone, -0.1));
      art.leaves(c, x + w * 0.25, base - w * 0.2, w * 0.26, shade(tone, 0.06));
      art.leaves(c, x, base - w * 0.32, w * 0.34, tone);
    };

    /* پرنده‌ی دوردست: دو کمان که با phase بال می‌زنند (ارزان؛ هر فریم کشیده می‌شود) */
    art.bird = function (c, x, y, size, phase, color) {
      var flap = Math.sin(phase) * size * 0.45;
      c.strokeStyle = color || "rgba(30,36,60,.7)";
      c.lineWidth = Math.max(1, size * 0.16);
      c.lineCap = "round";
      c.beginPath();
      c.moveTo(x - size, y - flap);
      c.quadraticCurveTo(x - size * 0.45, y - size * 0.35 - flap * 0.3, x, y);
      c.quadraticCurveTo(x + size * 0.45, y - size * 0.35 - flap * 0.3, x + size, y - flap);
      c.stroke();
    };

    /* خودرو از پشت سر (برای جاده): کف خودرو روی y=h و وسط آن x=w/2 است.
       kind: sedan | van | taxi */
    art.carRear = function (c, w, h, color, kind) {
      var m = w / 2;
      var van = kind === "van";
      var roofY = van ? h * 0.06 : h * 0.2, beltY = h * 0.5, bumperY = h * 0.8;
      var roofHalf = w * (van ? 0.4 : 0.33), bodyHalf = w * 0.46;
      // چرخ‌ها
      c.fillStyle = "#14161c";
      rr(c, m - bodyHalf + 2, h * 0.78, w * 0.15, h * 0.22, 3);
      c.fill();
      rr(c, m + bodyHalf - 2 - w * 0.15, h * 0.78, w * 0.15, h * 0.22, 3);
      c.fill();
      // بدنه
      var paint = c.createLinearGradient(0, roofY, 0, h * 0.92);
      paint.addColorStop(0, shade(color, 0.35));
      paint.addColorStop(0.3, color);
      paint.addColorStop(1, shade(color, -0.45));
      c.fillStyle = paint;
      c.beginPath();
      c.moveTo(m - roofHalf + 5, roofY);
      c.lineTo(m + roofHalf - 5, roofY);
      c.quadraticCurveTo(m + roofHalf, roofY, m + roofHalf + 2, roofY + 6);
      c.lineTo(m + bodyHalf - 3, beltY);
      c.quadraticCurveTo(m + bodyHalf + 1, beltY + 4, m + bodyHalf, beltY + 10);
      c.lineTo(m + bodyHalf - 2, h * 0.9);
      c.lineTo(m - bodyHalf + 2, h * 0.9);
      c.lineTo(m - bodyHalf, beltY + 10);
      c.quadraticCurveTo(m - bodyHalf - 1, beltY + 4, m - bodyHalf + 3, beltY);
      c.lineTo(m - roofHalf - 2, roofY + 6);
      c.quadraticCurveTo(m - roofHalf, roofY, m - roofHalf + 5, roofY);
      c.closePath();
      c.fill();
      c.strokeStyle = shade(color, -0.6);
      c.lineWidth = 1;
      c.stroke();
      // شیشه‌ی عقب با بازتاب آسمان
      var glass = c.createLinearGradient(0, roofY + 5, 0, beltY - 2);
      glass.addColorStop(0, "#9fd0f0");
      glass.addColorStop(0.5, "#3f6c93");
      glass.addColorStop(1, "#16263a");
      c.fillStyle = glass;
      c.beginPath();
      c.moveTo(m - roofHalf + 6, roofY + 6);
      c.lineTo(m + roofHalf - 6, roofY + 6);
      c.lineTo(m + bodyHalf - 9, beltY - 3);
      c.lineTo(m - bodyHalf + 9, beltY - 3);
      c.closePath();
      c.fill();
      c.fillStyle = "rgba(255,255,255,.28)";
      c.beginPath();
      c.moveTo(m - roofHalf + 10, roofY + 8);
      c.lineTo(m - roofHalf + 22, roofY + 8);
      c.lineTo(m - bodyHalf + 20, beltY - 5);
      c.lineTo(m - bodyHalf + 12, beltY - 5);
      c.closePath();
      c.fill();
      // صندوق، خط در و سپر
      c.strokeStyle = "rgba(0,0,0,.3)";
      c.beginPath();
      c.moveTo(m - bodyHalf + 6, beltY + 14);
      c.lineTo(m + bodyHalf - 6, beltY + 14);
      c.stroke();
      c.fillStyle = "#2a2e38";
      rr(c, m - bodyHalf + 1, bumperY, bodyHalf * 2 - 2, h * 0.11, 3);
      c.fill();
      c.fillStyle = "rgba(255,255,255,.2)";
      c.fillRect(m - bodyHalf + 5, bumperY + 1.5, bodyHalf * 2 - 10, 1.2);
      // چراغ‌های عقب با هاله‌ی قرمز
      for (var side = -1; side <= 1; side += 2) {
        var lx = m + side * (bodyHalf - w * 0.13), ly = beltY + 18;
        var halo = c.createRadialGradient(lx, ly, 0, lx, ly, w * 0.16);
        halo.addColorStop(0, "rgba(255,60,60,.55)");
        halo.addColorStop(1, "rgba(255,60,60,0)");
        c.fillStyle = halo;
        c.fillRect(lx - w * 0.16, ly - w * 0.16, w * 0.32, w * 0.32);
        var lamp = c.createLinearGradient(0, ly - 4, 0, ly + 4);
        lamp.addColorStop(0, "#ff8f8f");
        lamp.addColorStop(1, "#c81e2e");
        c.fillStyle = lamp;
        rr(c, lx - w * 0.085, ly - 4, w * 0.17, 8, 3);
        c.fill();
      }
      // پلاک (بدون نوشته) و تابلوی تاکسی
      c.fillStyle = "#f4f1e4";
      rr(c, m - w * 0.11, bumperY - h * 0.1, w * 0.22, h * 0.075, 1.5);
      c.fill();
      c.fillStyle = "#3a5fb0";
      c.fillRect(m - w * 0.11, bumperY - h * 0.1, w * 0.035, h * 0.075);
      if (kind === "taxi") {
        c.fillStyle = "#1c1f28";
        rr(c, m - w * 0.09, roofY - h * 0.07, w * 0.18, h * 0.08, 2);
        c.fill();
        c.fillStyle = "#ffe36b";
        rr(c, m - w * 0.07, roofY - h * 0.055, w * 0.14, h * 0.05, 1.5);
        c.fill();
      }
      // برق سقف
      c.fillStyle = "rgba(255,255,255,.35)";
      c.fillRect(m - roofHalf + 8, roofY + 1.5, roofHalf * 2 - 16, 1.4);
    };

    art.starPath = function (c, x, y, r, points, inner) {
      points = points || 5;
      inner = inner === undefined ? 0.46 : inner;
      c.beginPath();
      for (var i = 0; i < points * 2; i++) {
        var rad = i % 2 ? r * inner : r, a = (i / (points * 2)) * TAU - Math.PI / 2;
        if (i) c.lineTo(x + Math.cos(a) * rad, y + Math.sin(a) * rad);
        else c.moveTo(x + Math.cos(a) * rad, y + Math.sin(a) * rad);
      }
      c.closePath();
    };

    /* سکه‌ی طلایی با لبه و ستاره‌ی برجسته (فقط تزئینی؛ ارز واقعی نیست) */
    art.coin = function (c, x, y, r) {
      var g = c.createLinearGradient(x - r, y - r, x + r, y + r);
      g.addColorStop(0, "#fff3b0");
      g.addColorStop(0.45, "#f5b82e");
      g.addColorStop(1, "#b9770e");
      c.fillStyle = g;
      c.beginPath();
      c.arc(x, y, r, 0, TAU);
      c.fill();
      c.strokeStyle = "#8a5a0a";
      c.lineWidth = Math.max(1, r * 0.1);
      c.stroke();
      c.strokeStyle = "rgba(255,255,255,.55)";
      c.lineWidth = Math.max(0.8, r * 0.08);
      c.beginPath();
      c.arc(x, y, r * 0.74, 0, TAU);
      c.stroke();
      c.fillStyle = "#a66a08";
      art.starPath(c, x + r * 0.04, y + r * 0.06, r * 0.46);
      c.fill();
      c.fillStyle = "#ffe58a";
      art.starPath(c, x, y, r * 0.46);
      c.fill();
    };

    /* متن با خط دور تیره تا روی هر پس‌زمینه‌ای خوانا باشد */
    art.label = function (c, text, x, y, size, color, weight) {
      c.font = env.font(size, weight || 800);
      c.textAlign = "center";
      c.lineJoin = "round";
      c.lineWidth = Math.max(2.5, size * 0.2);
      c.strokeStyle = "rgba(8,10,24,.75)";
      c.strokeText(text, x, y);
      c.fillStyle = color || "#fff";
      c.fillText(text, x, y);
    };

    return art;
  };
})(typeof self !== "undefined" ? self : this);
