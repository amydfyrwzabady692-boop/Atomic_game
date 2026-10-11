/* «موش‌زن» — رندر و افکت‌ها: باغچه‌ی چمنی با نرده و چاله‌های خاکی، چکش چوبی که روی چاله فرود می‌آید
   و سه شخصیت: موش کور قهوه‌ای (عادی)، موش کور طلایی تاج‌دار (جایزه‌ی بیشتر) و بمب فتیله‌دار (نزن!).
   موش‌ها پلک می‌زنند و بعد از ضربه گیج می‌شوند. */
(function () {
  "use strict";
  Arcade.registerRenderer("whack", function (env) {
    var core = Arcade.cores.whack, art = env.art;
    var TAU = Math.PI * 2;
    var KINDS = ["", "mole", "bomb", "gold"];
    var mallet = { hole: -1, at: 0 };
    var struck = []; // موجودی که همین حالا ضربه خورده: { type, at }
    for (var i = 0; i < 9; i++) struck.push(null);

    function grid() {
      var size = Math.min(env.W - 20, env.H - env.safeTop - 120);
      var top = env.safeTop + 44 + Math.max(0, (env.H - env.safeTop - 130 - size) / 2);
      return { x: (env.W - size) / 2, y: top, cell: size / 3 };
    }
    function center(index, g) {
      g = g || grid();
      return { x: g.x + (index % 3 + 0.5) * g.cell, y: g.y + (Math.floor(index / 3) + 0.5) * g.cell, cell: g.cell };
    }

    // ---------------------------------------------------------------- شخصیت‌ها
    /* موش کور. face: open | blink | dizzy */
    function drawMole(c, x, baseY, r, gold, face) {
      var top = baseY - r * 1.9;
      var fur = gold ? "#f0b429" : "#8a5a33";
      var furLight = gold ? "#ffe38a" : "#c08a52";
      var furDark = gold ? "#a8690c" : "#4f3018";
      // گوش‌ها
      for (var side = -1; side <= 1; side += 2) {
        art.sphere(c, x + side * r * 0.56, top + r * 0.2, r * 0.2, fur, false);
        c.fillStyle = "#f2a7b4";
        c.beginPath();
        c.arc(x + side * r * 0.56, top + r * 0.22, r * 0.1, 0, TAU);
        c.fill();
      }
      // بدن کپسولی با نور از چپ
      var body = c.createLinearGradient(x - r * 0.75, 0, x + r * 0.75, 0);
      body.addColorStop(0, furLight);
      body.addColorStop(0.4, fur);
      body.addColorStop(1, furDark);
      c.fillStyle = body;
      c.beginPath();
      c.moveTo(x - r * 0.74, baseY);
      c.lineTo(x - r * 0.74, top + r * 0.74);
      c.arc(x, top + r * 0.74, r * 0.74, Math.PI, 0);
      c.lineTo(x + r * 0.74, baseY);
      c.closePath();
      c.fill();
      // بافت مو (فقط روی بدن)
      c.save();
      c.clip();
      var rnd = art.rand(gold ? 17 : 5);
      c.lineCap = "round";
      for (var i = 0; i < 90; i++) {
        var fx = x - r * 0.72 + rnd() * r * 1.44, fy = top + rnd() * r * 1.9;
        c.strokeStyle = rnd() < 0.5 ? art.alpha(furDark, 0.35) : art.alpha(furLight, 0.4);
        c.lineWidth = Math.max(0.6, r * 0.022);
        c.beginPath();
        c.moveTo(fx, fy);
        c.lineTo(fx + (rnd() - 0.5) * r * 0.05, fy + r * 0.09);
        c.stroke();
      }
      // سایه‌ی پایین بدن (داخل چاله تاریک‌تر است)
      var deep = c.createLinearGradient(0, baseY - r * 0.7, 0, baseY);
      deep.addColorStop(0, "rgba(0,0,0,0)");
      deep.addColorStop(1, "rgba(0,0,0,.45)");
      c.fillStyle = deep;
      c.fillRect(x - r, baseY - r * 0.7, r * 2, r * 0.7);
      c.restore();
      c.strokeStyle = art.alpha(furDark, 0.8);
      c.lineWidth = 1;
      c.stroke();
      // شکم روشن
      var belly = c.createRadialGradient(x, baseY - r * 0.5, r * 0.05, x, baseY - r * 0.45, r * 0.55);
      belly.addColorStop(0, gold ? "#fff6d0" : "#f0d8b4");
      belly.addColorStop(1, gold ? "rgba(255,240,190,0)" : "rgba(226,195,154,0)");
      c.fillStyle = belly;
      c.beginPath();
      c.ellipse(x, baseY - r * 0.45, r * 0.46, r * 0.55, 0, 0, TAU);
      c.fill();
      // پوزه
      var muzzleY = top + r * 0.98;
      c.fillStyle = gold ? "#fff0bf" : "#e9cfa6";
      c.beginPath();
      c.ellipse(x, muzzleY, r * 0.36, r * 0.27, 0, 0, TAU);
      c.fill();
      // دندان‌ها
      c.fillStyle = "#ffffff";
      art.rr(c, x - r * 0.1, muzzleY + r * 0.06, r * 0.09, r * 0.17, r * 0.02);
      c.fill();
      art.rr(c, x + r * 0.01, muzzleY + r * 0.06, r * 0.09, r * 0.17, r * 0.02);
      c.fill();
      c.strokeStyle = "rgba(60,30,10,.55)";
      c.lineWidth = Math.max(0.8, r * 0.025);
      c.beginPath();
      c.arc(x - r * 0.09, muzzleY + r * 0.04, r * 0.1, 0.1 * Math.PI, 0.9 * Math.PI);
      c.arc(x + r * 0.09, muzzleY + r * 0.04, r * 0.1, 0.1 * Math.PI, 0.9 * Math.PI);
      c.stroke();
      // بینی براق
      art.sphere(c, x, muzzleY - r * 0.12, r * 0.13, "#e2687c");
      // سبیل
      c.strokeStyle = "rgba(40,22,10,.6)";
      c.lineWidth = Math.max(0.7, r * 0.02);
      for (side = -1; side <= 1; side += 2) {
        for (var w = -1; w <= 1; w++) {
          c.beginPath();
          c.moveTo(x + side * r * 0.24, muzzleY + w * r * 0.05);
          c.lineTo(x + side * r * 0.62, muzzleY + w * r * 0.14 - r * 0.03);
          c.stroke();
        }
      }
      // چشم‌ها
      var eyeY = top + r * 0.62;
      for (side = -1; side <= 1; side += 2) {
        var ex = x + side * r * 0.3;
        if (face === "blink") {
          c.strokeStyle = "#1c120a";
          c.lineWidth = Math.max(1.4, r * 0.05);
          c.beginPath();
          c.arc(ex, eyeY - r * 0.03, r * 0.11, 0.15 * Math.PI, 0.85 * Math.PI);
          c.stroke();
        } else if (face === "dizzy") {
          c.strokeStyle = "#1c120a";
          c.lineWidth = Math.max(1.4, r * 0.05);
          c.beginPath();
          c.moveTo(ex - r * 0.1, eyeY - r * 0.1);
          c.lineTo(ex + r * 0.1, eyeY + r * 0.1);
          c.moveTo(ex + r * 0.1, eyeY - r * 0.1);
          c.lineTo(ex - r * 0.1, eyeY + r * 0.1);
          c.stroke();
        } else {
          c.fillStyle = "#ffffff";
          c.beginPath();
          c.arc(ex, eyeY, r * 0.16, 0, TAU);
          c.fill();
          c.fillStyle = "#1c120a";
          c.beginPath();
          c.arc(ex, eyeY + r * 0.02, r * 0.1, 0, TAU);
          c.fill();
          c.fillStyle = "#ffffff";
          c.beginPath();
          c.arc(ex - r * 0.035, eyeY - r * 0.03, r * 0.038, 0, TAU);
          c.fill();
        }
      }
      if (gold) {
        // تاج
        var crown = c.createLinearGradient(0, top - r * 0.4, 0, top + r * 0.1);
        crown.addColorStop(0, "#fffbe0");
        crown.addColorStop(1, "#f5a623");
        c.fillStyle = crown;
        c.beginPath();
        c.moveTo(x - r * 0.36, top + r * 0.12);
        c.lineTo(x - r * 0.42, top - r * 0.26);
        c.lineTo(x - r * 0.17, top - r * 0.06);
        c.lineTo(x, top - r * 0.38);
        c.lineTo(x + r * 0.17, top - r * 0.06);
        c.lineTo(x + r * 0.42, top - r * 0.26);
        c.lineTo(x + r * 0.36, top + r * 0.12);
        c.closePath();
        c.fill();
        c.strokeStyle = "rgba(120,70,0,.7)";
        c.lineWidth = 1;
        c.stroke();
        art.sphere(c, x, top - r * 0.02, r * 0.07, "#e5383b");
        art.sphere(c, x - r * 0.24, top + r * 0.02, r * 0.05, "#38d9ff");
        art.sphere(c, x + r * 0.24, top + r * 0.02, r * 0.05, "#38d9ff");
      }
    }

    function drawBomb(c, x, baseY, r) {
      var cy = baseY - r * 0.95;
      art.sphere(c, x, cy, r * 0.82, "#2f3448");
      // نوار برجسته‌ی دور بمب
      c.strokeStyle = "rgba(255,255,255,.14)";
      c.lineWidth = Math.max(1.5, r * 0.06);
      c.beginPath();
      c.ellipse(x, cy, r * 0.8, r * 0.26, 0, 0.08 * Math.PI, 0.92 * Math.PI);
      c.stroke();
      // کلاهک فلزی و فتیله
      art.metal(c, x - r * 0.22, cy - r * 1.02, r * 0.44, r * 0.26, { base: "#8b93a6" });
      c.strokeStyle = "rgba(0,0,0,.5)";
      c.lineWidth = 1;
      c.strokeRect(x - r * 0.22, cy - r * 1.02, r * 0.44, r * 0.26);
      c.strokeStyle = "#d1b28a";
      c.lineWidth = Math.max(2, r * 0.07);
      c.lineCap = "round";
      c.beginPath();
      c.moveTo(x, cy - r * 1.02);
      c.quadraticCurveTo(x + r * 0.3, cy - r * 1.3, x + r * 0.16, cy - r * 1.45);
      c.stroke();
      // علامت خطر
      c.fillStyle = "#ffd257";
      c.beginPath();
      c.moveTo(x, cy - r * 0.42);
      c.lineTo(x + r * 0.42, cy + r * 0.3);
      c.lineTo(x - r * 0.42, cy + r * 0.3);
      c.closePath();
      c.fill();
      c.strokeStyle = "#1c1f28";
      c.lineWidth = Math.max(1.5, r * 0.05);
      c.lineJoin = "round";
      c.stroke();
      c.fillStyle = "#1c1f28";
      art.rr(c, x - r * 0.04, cy - r * 0.2, r * 0.08, r * 0.28, r * 0.03);
      c.fill();
      c.beginPath();
      c.arc(x, cy + r * 0.18, r * 0.05, 0, TAU);
      c.fill();
    }

    /* هر شخصیت در اسپرایتی به عرض ۲٫۲r و ارتفاع ۲٫۶r؛ پایین اسپرایت = کف بدن */
    function paintKind(kind, face, r) {
      return function (c, w, h) {
        if (kind === "bomb") drawBomb(c, w / 2, h, r);
        else drawMole(c, w / 2, h, r, kind === "gold", face);
      };
    }

    function dirtRing(c, x, y, r, front) {
      // تپه‌ی خاک دور چاله؛ front فقط نیمه‌ی جلویی را می‌کشد
      var g = c.createLinearGradient(0, y - r * 0.5, 0, y + r * 0.55);
      g.addColorStop(0, "#9a6a3c");
      g.addColorStop(0.5, "#7a4e28");
      g.addColorStop(1, "#4d2f16");
      c.fillStyle = g;
      c.beginPath();
      if (front) {
        c.ellipse(x, y, r * 1.28, r * 0.52, 0, 0, Math.PI);
        c.ellipse(x, y, r * 0.94, r * 0.33, 0, Math.PI, 0, true);
      } else {
        c.ellipse(x, y, r * 1.28, r * 0.52, 0, 0, TAU);
      }
      c.closePath();
      c.fill();
    }

    /* چند تیغه‌ی چمن جلوی تپه‌ی خاک */
    function tufts(c, x, y, r, seed) {
      var rnd = art.rand(seed);
      c.lineCap = "round";
      for (var i = 0; i < 16; i++) {
        var a = 0.12 * Math.PI + rnd() * 0.76 * Math.PI;
        var bx = x + Math.cos(a) * r * 1.26, by = y + Math.sin(a) * r * 0.5;
        c.strokeStyle = rnd() < 0.5 ? "#2f7a2a" : "#6cc04a";
        c.lineWidth = Math.max(1, r * 0.035);
        c.beginPath();
        c.moveTo(bx, by + r * 0.06);
        c.quadraticCurveTo(bx + (rnd() - 0.5) * r * 0.1, by - r * 0.08, bx + (rnd() - 0.5) * r * 0.16, by - r * (0.12 + rnd() * 0.12));
        c.stroke();
      }
    }

    function paintScene(c, w, h, b) {
      art.grass(c, -b, -b, w + b * 2, h + b * 2, { base: "#4f9e3e", seed: 21, density: 30 });
      // نوارهای چمن‌زنی
      c.fillStyle = "rgba(255,255,255,.045)";
      for (var sx = -b; sx < w + b; sx += 72) c.fillRect(sx, -b, 36, h + b * 2);
      var g = grid(), rnd = art.rand(33);

      // نرده‌ی چوبی و بوته‌ها پشت باغچه (اگر جا باشد)
      var fenceBottom = g.y - 38;
      if (fenceBottom - env.safeTop > 70) {
        var fenceTop = fenceBottom - 52;
        art.shadow(c, w / 2, fenceBottom + 3, w * 0.62, 7, 0.4);
        c.save();
        c.beginPath();
        c.rect(-b, fenceTop + 14, w + b * 2, 7);
        c.rect(-b, fenceTop + 36, w + b * 2, 7);
        c.clip();
        art.wood(c, -b, fenceTop + 10, w + b * 2, 40, { base: "#a67748", seed: 44, horizontal: true, knots: 0 });
        c.restore();
        for (var px = -b + 4; px < w + b; px += 26) {
          c.save();
          c.beginPath();
          c.moveTo(px, fenceBottom);
          c.lineTo(px, fenceTop + 9);
          c.lineTo(px + 9, fenceTop);
          c.lineTo(px + 18, fenceTop + 9);
          c.lineTo(px + 18, fenceBottom);
          c.closePath();
          c.clip();
          art.wood(c, px, fenceTop, 18, 54, { base: px % 52 < 26 ? "#c79a63" : "#b98a55", seed: 50 + px, knots: 0 });
          c.fillStyle = "rgba(255,240,210,.25)";
          c.fillRect(px, fenceTop, 2, 54);
          c.fillStyle = "rgba(60,30,10,.3)";
          c.fillRect(px + 16, fenceTop, 2, 54);
          c.restore();
        }
        for (var bx = 20; bx < w; bx += 78 + rnd() * 30) art.bush(c, bx, fenceBottom + 7, 46 + rnd() * 16, rnd() < 0.5 ? "#2f8f46" : "#3aa04e");
      }

      // گل‌های ریز
      for (var f = 0; f < 46; f++) {
        var fx = rnd() * w, fy = rnd() * h;
        c.fillStyle = ["#ffffff", "#ffe066", "#ff9ecb", "#c9b6ff"][f % 4];
        for (var petal = 0; petal < 5; petal++) {
          var pa = (petal / 5) * TAU;
          c.beginPath();
          c.arc(fx + Math.cos(pa) * 2, fy + Math.sin(pa) * 2, 1.5, 0, TAU);
          c.fill();
        }
        c.fillStyle = "#f59e0b";
        c.beginPath();
        c.arc(fx, fy, 1.2, 0, TAU);
        c.fill();
      }
      for (var i = 0; i < 9; i++) {
        var p = center(i, g), r = p.cell * 0.36, holeY = p.y + p.cell * 0.2;
        art.shadow(c, p.x + 2, holeY + r * 0.2, r * 1.5, r * 0.62, 0.45);
        dirtRing(c, p.x, holeY, r, false);
        c.save();
        c.beginPath();
        c.ellipse(p.x, holeY, r * 1.28, r * 0.52, 0, 0, TAU);
        c.clip();
        art.speckle(c, p.x - r * 1.3, holeY - r * 0.55, r * 2.6, r * 1.1, "#2a1608", 60, 50 + i);
        art.speckle(c, p.x - r * 1.3, holeY - r * 0.55, r * 2.6, r * 1.1, "#e2b57e", 40, 70 + i);
        c.restore();
        var hole = c.createRadialGradient(p.x, holeY + r * 0.12, 2, p.x, holeY, r);
        hole.addColorStop(0, "#050302");
        hole.addColorStop(1, "#24140a");
        c.fillStyle = hole;
        c.beginPath();
        c.ellipse(p.x, holeY, r * 0.94, r * 0.33, 0, 0, TAU);
        c.fill();
        tufts(c, p.x, holeY, r, 90);
      }
      art.vignette(c, w, h, 0.42);
    }

    /* نیمه‌ی جلویی تپه‌ی خاک (روی پایین شخصیت کشیده می‌شود) با چمن جلوی آن */
    function paintRim(r) {
      return function (c, w, h) {
        dirtRing(c, w / 2, 0, r, true);
        c.save();
        c.beginPath();
        c.ellipse(w / 2, 0, r * 1.28, r * 0.52, 0, 0, Math.PI);
        c.ellipse(w / 2, 0, r * 0.94, r * 0.33, 0, Math.PI, 0, true);
        c.closePath();
        c.clip();
        art.speckle(c, 0, 0, w, h, "#2a1608", 26, 91);
        art.speckle(c, 0, 0, w, h, "#e2b57e", 18, 92);
        c.restore();
        tufts(c, w / 2, 0, r, 90);
      };
    }

    /* پنجه‌ای که لبه‌ی چاله را گرفته */
    function paintPaw(gold, r) {
      return function (c, w, h) {
        var color = gold ? "#f0b429" : "#8a5a33";
        art.sphere(c, w / 2, h * 0.55, w * 0.42, color, false);
        c.strokeStyle = "rgba(40,20,8,.6)";
        c.lineWidth = Math.max(0.8, r * 0.025);
        c.beginPath();
        c.moveTo(w * 0.36, h * 0.5);
        c.lineTo(w * 0.36, h * 0.9);
        c.moveTo(w * 0.62, h * 0.5);
        c.lineTo(w * 0.62, h * 0.9);
        c.stroke();
      };
    }

    function paintStar(c, w) {
      c.fillStyle = "#ffd257";
      art.starPath(c, w / 2, w / 2, w / 2 - 1);
      c.fill();
      c.strokeStyle = "rgba(120,70,0,.7)";
      c.lineWidth = 0.8;
      c.stroke();
    }

    /* چکش: دسته افقی، سر در سمت چپ؛ لولا در (۷۸، ۲۰) */
    function paintMallet(c) {
      env.dropShadow(c, 3, 3, 0.4);
      art.wood(c, 22, 16, 58, 8, { base: "#c79a63", seed: 3, horizontal: true, knots: 0 });
      c.save();
      art.rr(c, 0, 1, 28, 38, 6);
      c.clip();
      art.wood(c, 0, 1, 28, 38, { base: "#8a5a32", seed: 8, round: true, knots: 0 });
      art.metal(c, 0, 1, 28, 5, { base: "#9aa4b8" });
      art.metal(c, 0, 34, 28, 5, { base: "#9aa4b8" });
      c.restore();
      env.dropShadow(c);
      c.strokeStyle = "rgba(40,20,8,.7)";
      c.lineWidth = 1;
      art.rr(c, 0, 1, 28, 38, 6);
      c.stroke();
    }

    function drawKind(c, kind, face, x, baseY, r, cutY, squash) {
      // فقط بخشی از شخصیت که بالاتر از لبه‌ی چاله است کشیده می‌شود (برش از خود اسپرایت، بدون clip)
      var w = r * 2.2, h = r * 2.6;
      var sp = env.sprite("whack:" + kind + ":" + face, w, h, paintKind(kind, face, r));
      var dh = h * squash, top = baseY - dh;
      var visible = env.clamp(cutY - top, 0, dh);
      if (visible <= 0) return;
      var sh = (visible / dh) * sp.canvas.height;
      c.drawImage(sp.canvas, 0, 0, sp.canvas.width, sh, x - w / 2, top, w, visible);
    }

    return {
      controls: "tap",
      ownBackground: true,
      reset: function () {
        mallet.hole = -1;
        for (var i = 0; i < 9; i++) struck[i] = null;
      },
      input: function (kind, data) {
        if (kind !== "tap") return null;
        var g = grid();
        var col = Math.floor((data.x - g.x) / g.cell), row = Math.floor((data.y - g.y) / g.cell);
        if (col < 0 || col > 2 || row < 0 || row > 2) return null;
        return [row * 3 + col];
      },
      hud: function (state) {
        if (!state) return "";
        var left = Math.max(0, Math.ceil(((core.LIMIT_TICKS - state.tick) * core.TICK_MS) / 1000));
        return "⏱ " + env.fa(left) + " ثانیه";
      },
      event: function (name, state) {
        var p = state.lastHole >= 0 ? center(state.lastHole) : { x: env.W / 2, y: env.H / 2, cell: 100 };
        var now = env.now();
        if (state.lastHole >= 0 && name !== "timeup") {
          mallet.hole = state.lastHole;
          mallet.at = now;
        }
        if (name === "hit" || name === "gold") {
          var gold = name === "gold";
          struck[state.lastHole] = { type: gold ? 3 : 1, at: now };
          env.fx.burst(p.x, p.y, gold ? env.colors.gold : "#ffffff", gold ? 26 : 12, gold ? 5 : 3.5);
          env.fx.ring(p.x, p.y, "#ffffff", 10, p.cell * 0.5);
          env.fx.text(p.x, p.y - 38, gold ? "+۳۰" : "+۱۰", gold ? env.colors.gold : "#ffffff");
          env.fx.shake(gold ? 5 : 3);
          env.haptic(gold ? "medium" : "light");
          env.sound(gold ? "bonus" : "good");
        } else if (name === "bomb") {
          env.fx.burst(p.x, p.y, "#ff7b00", 30, 6.5);
          env.fx.burst(p.x, p.y, "#ffd257", 16, 4);
          env.fx.debris(p.x, p.y, "#2f3448", 12, 6, 4);
          env.fx.ring(p.x, p.y, "#ff7b00", 14, p.cell * 0.9);
          env.fx.flash("#ff7b00", 0.4);
          env.fx.shake(10);
          env.fx.text(p.x, p.y - 38, "−۱۵", env.colors.danger);
          env.haptic("error");
          env.sound("bad");
        } else if (name === "empty") {
          env.fx.debris(p.x, p.y + p.cell * 0.2, "#7a4e28", 5, 2.4, 2.5);
          env.sound("tick");
        } else if (name === "timeup") {
          env.fx.flash(env.colors.accent, 0.3);
          env.haptic("success");
        }
      },
      draw: function (c, state, alpha) {
        var tickNow = state.tick + alpha, now = env.now();
        var g = grid();
        env.scene(c, "whack", paintScene);

        // نوار زمان
        var ratio = env.clamp(1 - state.tick / core.LIMIT_TICKS, 0, 1);
        var bw = g.cell * 3 - 12, bx = g.x + 6, by = g.y - 24;
        c.fillStyle = "rgba(20,40,16,.6)";
        art.rr(c, bx - 2, by - 2, bw + 4, 13, 6.5);
        c.fill();
        c.fillStyle = ratio < 0.2 ? "#ff5c7a" : "#ffe066";
        art.rr(c, bx, by, Math.max(9, bw * ratio), 9, 4.5);
        c.fill();
        c.fillStyle = "rgba(255,255,255,.5)";
        c.fillRect(bx + 4, by + 1.5, Math.max(2, bw * ratio - 8), 1.6);

        for (var i = 0; i < 9; i++) {
          var p = center(i, g), r = p.cell * 0.36;
          var holeY = p.y + p.cell * 0.2;
          var cut = holeY + r * 0.34; // لبه‌ی جلویی دهانه‌ی چاله؛ تپه‌ی خاک جلو روی آن کشیده می‌شود
          var slot = state.holes[i];
          var drawn = false, paws = 0, gold = false;
          if (slot.type !== 0) {
            var age = tickNow - slot.born, left = slot.until - tickNow;
            var rise = env.clamp(Math.min(age / 6, left / 6), 0, 1);
            var bounce = rise >= 1 ? Math.sin(age / 5) * 1.5 : 0;
            var baseY = holeY + r * 0.25 + (1 - rise) * r * 2.1 + bounce;
            var kind = KINDS[slot.type];
            // هر موش با ضرب‌آهنگ خودش پلک می‌زند
            var blink = slot.type !== 2 && (now + i * 613) % 2300 < 130;
            drawKind(c, kind, blink ? "blink" : "open", p.x, baseY, r, cut, 1);
            if (slot.type === 2 && baseY - r * 2.42 < cut) {
              // جرقه‌ی فتیله
              var spark = 0.5 + 0.5 * Math.sin(now / 55 + i);
              art.glow(c, p.x + r * 0.16, baseY - r * 2.42, r * (0.3 + spark * 0.2), spark > 0.5 ? "#ffd257" : "#ff7b00", 0.9);
            }
            if (slot.type === 3 && rise >= 1) {
              // برق طلا
              var tw = (now / 300 + i) % 1;
              art.glow(c, p.x + Math.cos(tw * TAU) * r * 0.7, baseY - r * 1.5 + Math.sin(tw * TAU) * r * 0.5, r * 0.3, "#fff6c9", 1 - tw);
            }
            drawn = true;
            paws = slot.type === 2 ? 0 : rise;
            gold = slot.type === 3;
          } else if (struck[i]) {
            // موش ضربه‌خورده گیج می‌شود، له می‌شود و پایین می‌رود؛ ستاره‌ها دور سرش می‌چرخند
            var t = (now - struck[i].at) / 320;
            if (t >= 1) struck[i] = null;
            else {
              var sink = holeY + r * 0.25 + t * t * r * 1.7;
              drawKind(c, KINDS[struck[i].type], "dizzy", p.x, sink, r, cut, 0.66 - t * 0.2);
              var star = env.sprite("whack:star", 12, 12, paintStar);
              for (var k = 0; k < 3; k++) {
                var a = now / 110 + (k * TAU) / 3;
                c.globalAlpha = 1 - t;
                env.blitC(c, star, p.x + Math.cos(a) * r * 0.62, sink - r * 1.36 + Math.sin(a) * r * 0.16, a);
              }
              c.globalAlpha = 1;
              drawn = true;
            }
          }
          if (drawn) {
            env.blit(c, env.sprite("whack:rim", r * 2.6, r * 0.7, paintRim(r), 12), p.x - r * 1.3, holeY);
            if (paws > 0.75) {
              var paw = env.sprite(gold ? "whack:pawGold" : "whack:paw", r * 0.34, r * 0.3, paintPaw(gold, r));
              env.blit(c, paw, p.x - r * 0.78, holeY + r * 0.2);
              env.blit(c, paw, p.x + r * 0.44, holeY + r * 0.2);
            }
          }
        }

        // چکش
        if (mallet.hole >= 0) {
          var mt = (now - mallet.at) / 260;
          if (mt >= 1) mallet.hole = -1;
          else {
            var mp = center(mallet.hole, g), mr = mp.cell * 0.36;
            var swing = mt < 0.35 ? 1 - mt / 0.35 : Math.sin(((mt - 0.35) / 0.65) * Math.PI) * 0.18;
            var sp = env.sprite("whack:mallet", 80, 40, paintMallet, 6);
            c.save();
            c.globalAlpha = mt > 0.75 ? (1 - mt) / 0.25 : 1;
            c.translate(mp.x + 64, mp.y + mp.cell * 0.2 - mr * 0.75);
            c.rotate(swing * 1.05);
            c.drawImage(sp.canvas, -78 - sp.pad, -20 - sp.pad, sp.fw, sp.fh);
            c.restore();
          }
        }
      },
    };
  });
})();
