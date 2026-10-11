/* «موش‌زن» — رندر و افکت‌ها: چمن باغچه با چاله‌های خاکی، چکش چوبی که روی چاله فرود می‌آید و
   شخصیت‌های اورجینال: موجود صورتی (عادی)، موجود طلایی تاج‌دار (جایزه‌ی بیشتر) و بمب فتیله‌دار (نزن!). */
(function () {
  "use strict";
  Arcade.registerRenderer("whack", function (env) {
    var core = Arcade.cores.whack, art = env.art;
    var TAU = Math.PI * 2;
    var KINDS = ["", "creature", "bomb", "gold"];
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

    // ---------------------------------------------------------------- اسپرایت‌ها
    function eye(c, x, y, r) {
      c.fillStyle = "#fff";
      c.beginPath();
      c.arc(x, y, r, 0, TAU);
      c.fill();
      c.fillStyle = "#1b1f3a";
      c.beginPath();
      c.arc(x, y + r * 0.1, r * 0.55, 0, TAU);
      c.fill();
      c.fillStyle = "#fff";
      c.beginPath();
      c.arc(x - r * 0.2, y - r * 0.2, r * 0.2, 0, TAU);
      c.fill();
    }

    function drawCreature(c, x, baseY, r, gold) {
      var top = baseY - r * 1.9;
      var body = c.createLinearGradient(x - r * 0.7, 0, x + r * 0.7, 0);
      if (gold) {
        body.addColorStop(0, "#ffe89a");
        body.addColorStop(0.45, "#ffc233");
        body.addColorStop(1, "#c67a10");
      } else {
        body.addColorStop(0, "#ffb3e0");
        body.addColorStop(0.45, "#f472b6");
        body.addColorStop(1, "#b83280");
      }
      // گوش‌ها
      art.sphere(c, x - r * 0.52, top + r * 0.12, r * 0.24, gold ? "#ffc233" : "#f472b6", false);
      art.sphere(c, x + r * 0.52, top + r * 0.12, r * 0.24, gold ? "#ffc233" : "#f472b6", false);
      // بدن کپسولی
      c.fillStyle = body;
      c.beginPath();
      c.moveTo(x - r * 0.72, baseY);
      c.lineTo(x - r * 0.72, top + r * 0.72);
      c.arc(x, top + r * 0.72, r * 0.72, Math.PI, 0);
      c.lineTo(x + r * 0.72, baseY);
      c.closePath();
      c.fill();
      c.strokeStyle = gold ? "rgba(120,70,0,.5)" : "rgba(120,20,80,.45)";
      c.lineWidth = 1;
      c.stroke();
      // برق روی سر
      c.fillStyle = "rgba(255,255,255,.4)";
      c.beginPath();
      c.ellipse(x - r * 0.3, top + r * 0.38, r * 0.2, r * 0.3, -0.5, 0, TAU);
      c.fill();
      // شکم
      c.fillStyle = "rgba(255,255,255,.3)";
      c.beginPath();
      c.ellipse(x, baseY - r * 0.42, r * 0.42, r * 0.5, 0, 0, TAU);
      c.fill();
      // صورت
      eye(c, x - r * 0.27, top + r * 0.66, r * 0.19);
      eye(c, x + r * 0.27, top + r * 0.66, r * 0.19);
      c.fillStyle = "rgba(255,120,160,.55)";
      c.beginPath();
      c.arc(x - r * 0.5, top + r * 0.95, r * 0.1, 0, TAU);
      c.arc(x + r * 0.5, top + r * 0.95, r * 0.1, 0, TAU);
      c.fill();
      c.strokeStyle = "#1b1f3a";
      c.lineWidth = Math.max(1.5, r * 0.06);
      c.lineCap = "round";
      c.beginPath();
      c.arc(x, top + r * 0.9, r * 0.14, 0.15 * Math.PI, 0.85 * Math.PI);
      c.stroke();
      if (gold) {
        // تاج
        var crown = c.createLinearGradient(0, top - r * 0.36, 0, top + r * 0.1);
        crown.addColorStop(0, "#fffbe0");
        crown.addColorStop(1, "#f5b82e");
        c.fillStyle = crown;
        c.beginPath();
        c.moveTo(x - r * 0.34, top + r * 0.1);
        c.lineTo(x - r * 0.4, top - r * 0.26);
        c.lineTo(x - r * 0.16, top - r * 0.06);
        c.lineTo(x, top - r * 0.36);
        c.lineTo(x + r * 0.16, top - r * 0.06);
        c.lineTo(x + r * 0.4, top - r * 0.26);
        c.lineTo(x + r * 0.34, top + r * 0.1);
        c.closePath();
        c.fill();
        c.strokeStyle = "rgba(120,70,0,.6)";
        c.lineWidth = 1;
        c.stroke();
      }
    }

    function drawBomb(c, x, baseY, r) {
      var cy = baseY - r * 0.95;
      art.sphere(c, x, cy, r * 0.8, "#3a4062");
      // کلاهک و فتیله
      c.fillStyle = "#565d85";
      art.rr(c, x - r * 0.2, cy - r * 0.98, r * 0.4, r * 0.26, 4);
      c.fill();
      c.strokeStyle = "#c9a27a";
      c.lineWidth = 3;
      c.lineCap = "round";
      c.beginPath();
      c.moveTo(x, cy - r * 0.98);
      c.quadraticCurveTo(x + r * 0.3, cy - r * 1.28, x + r * 0.16, cy - r * 1.45);
      c.stroke();
      // چهره‌ی اخمو
      c.strokeStyle = "#ff5c7a";
      c.lineWidth = Math.max(2, r * 0.08);
      c.beginPath();
      c.moveTo(x - r * 0.42, cy - r * 0.24);
      c.lineTo(x - r * 0.14, cy - r * 0.1);
      c.moveTo(x + r * 0.42, cy - r * 0.24);
      c.lineTo(x + r * 0.14, cy - r * 0.1);
      c.stroke();
      c.fillStyle = "#ff5c7a";
      c.beginPath();
      c.arc(x - r * 0.26, cy + r * 0.04, r * 0.09, 0, TAU);
      c.arc(x + r * 0.26, cy + r * 0.04, r * 0.09, 0, TAU);
      c.fill();
      c.beginPath();
      c.arc(x, cy + r * 0.46, r * 0.16, Math.PI * 1.1, Math.PI * 1.9);
      c.stroke();
    }

    /* هر شخصیت در اسپرایتی به عرض ۲٫۲r و ارتفاع ۲٫۶r؛ پایین اسپرایت = کف بدن */
    function paintKind(kind, r) {
      return function (c, w, h) {
        if (kind === "bomb") drawBomb(c, w / 2, h, r);
        else drawCreature(c, w / 2, h, r, kind === "gold");
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

    function paintScene(c, w, h, b) {
      art.grass(c, -b, -b, w + b * 2, h + b * 2, { base: "#4f9e3e", seed: 21, density: 30 });
      // نوارهای چمن‌زنی
      c.fillStyle = "rgba(255,255,255,.045)";
      for (var sx = -b; sx < w + b; sx += 72) c.fillRect(sx, -b, 36, h + b * 2);
      var g = grid(), rnd = art.rand(33);
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
      }
      art.vignette(c, w, h, 0.42);
    }

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
      };
    }

    /* چکش: دسته افقی، سر در سمت چپ؛ لولا در (۷۸، ۲۰) */
    function paintMallet(c) {
      env.dropShadow(c, 3, 3, 0.4);
      art.wood(c, 22, 16, 58, 8, { base: "#c79a63", seed: 3, horizontal: true, knots: 0 });
      c.save();
      art.rr(c, 0, 1, 28, 38, 6);
      c.clip();
      art.wood(c, 0, 1, 28, 38, { base: "#8a5a32", seed: 8, round: true, knots: 0 });
      c.fillStyle = "rgba(40,20,8,.55)";
      c.fillRect(0, 1, 28, 5);
      c.fillRect(0, 34, 28, 5);
      c.restore();
      env.dropShadow(c);
      c.strokeStyle = "rgba(40,20,8,.7)";
      c.lineWidth = 1;
      art.rr(c, 0, 1, 28, 38, 6);
      c.stroke();
    }

    function drawKind(c, kind, x, baseY, r, cutY, squash) {
      // فقط بخشی از شخصیت که بالاتر از لبه‌ی چاله است کشیده می‌شود (برش از خود اسپرایت، بدون clip)
      var w = r * 2.2, h = r * 2.6;
      var sp = env.sprite("whack:" + kind, w, h, paintKind(kind, r));
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
          env.fx.burst(p.x, p.y, gold ? env.colors.gold : "#ff9ecb", gold ? 26 : 12, gold ? 5 : 3.5);
          env.fx.ring(p.x, p.y, "#ffffff", 10, p.cell * 0.5);
          env.fx.text(p.x, p.y - 38, gold ? "+۳۰" : "+۱۰", gold ? env.colors.gold : "#ffffff");
          env.fx.shake(gold ? 5 : 3);
          env.haptic(gold ? "medium" : "light");
          env.sound(gold ? "bonus" : "good");
        } else if (name === "bomb") {
          env.fx.burst(p.x, p.y, "#ff7b00", 30, 6.5);
          env.fx.burst(p.x, p.y, "#ffd257", 16, 4);
          env.fx.debris(p.x, p.y, "#3a4062", 12, 6, 4);
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
          var drawn = false;
          if (slot.type !== 0) {
            var age = tickNow - slot.born, left = slot.until - tickNow;
            var rise = env.clamp(Math.min(age / 6, left / 6), 0, 1);
            var bounce = rise >= 1 ? Math.sin(age / 5) * 1.5 : 0;
            var baseY = holeY + r * 0.25 + (1 - rise) * r * 2.1 + bounce;
            var kind = KINDS[slot.type];
            drawKind(c, kind, p.x, baseY, r, cut, 1);
            if (slot.type === 2 && baseY - r * 2.42 < cut) {
              // جرقه‌ی فتیله
              var spark = 0.5 + 0.5 * Math.sin(now / 55 + i);
              art.glow(c, p.x + r * 0.16, baseY - r * 2.42, r * (0.3 + spark * 0.2), spark > 0.5 ? "#ffd257" : "#ff7b00", 0.9);
            }
            drawn = true;
          } else if (struck[i]) {
            // موجود ضربه‌خورده له می‌شود و پایین می‌رود
            var t = (now - struck[i].at) / 220;
            if (t >= 1) struck[i] = null;
            else {
              drawKind(c, KINDS[struck[i].type], p.x, holeY + r * 0.25 + t * r * 1.6, r, cut, 0.62 - t * 0.2);
              drawn = true;
            }
          }
          if (drawn) env.blit(c, env.sprite("whack:rim", r * 2.6, r * 0.56, paintRim(r)), p.x - r * 1.3, holeY);
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
