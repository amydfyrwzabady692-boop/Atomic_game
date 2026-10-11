/* «زمان‌سنج» — رندر و افکت‌ها: یک عقربه‌ی آنالوگ با قاب فلزی روی پنل برس‌خورده. عقربه رفت‌وبرگشت
   می‌کند و باید داخل ناحیه‌ی سبز (و بهتر، نوار طلایی وسط آن) متوقف شود. */
(function () {
  "use strict";
  Arcade.registerRenderer("timing", function (env) {
    var core = Arcade.cores.timing, art = env.art;
    var TAU = Math.PI * 2;
    var A0 = (200 * Math.PI) / 180, SWEEP = (140 * Math.PI) / 180; // ۲۷۰ درجه = بالا
    var G = 140, RIM = 14;
    var pulse = 0, jolt = 0;

    function center() {
      return { x: env.W / 2, y: Math.max(env.safeTop + G + RIM + 14, env.H * 0.5 - 10) };
    }
    function angleOf(pos) {
      return A0 + (pos / core.BAR) * SWEEP;
    }

    // ---------------------------------------------------------------- اسپرایت‌ها
    function screw(c, x, y, r) {
      art.sphere(c, x, y, r, "#8f99aa", false);
      c.strokeStyle = "rgba(0,0,0,.55)";
      c.lineWidth = Math.max(1, r * 0.3);
      c.beginPath();
      c.moveTo(x - r * 0.6, y - r * 0.25);
      c.lineTo(x + r * 0.6, y + r * 0.25);
      c.stroke();
    }

    function paintScene(c, w, h, b) {
      var g = c.createLinearGradient(0, -b, 0, h + b);
      g.addColorStop(0, "#2c3442");
      g.addColorStop(0.5, "#1c222d");
      g.addColorStop(1, "#11151c");
      c.fillStyle = g;
      c.fillRect(-b, -b, w + b * 2, h + b * 2);
      // خط‌های برس‌خوردگی
      var rnd = art.rand(17);
      for (var i = 0; i < 520; i++) {
        var y = -b + rnd() * (h + b * 2);
        c.fillStyle = rnd() < 0.5 ? "rgba(255,255,255," + (0.012 + rnd() * 0.035) + ")" : "rgba(0,0,0," + (0.03 + rnd() * 0.07) + ")";
        c.fillRect(-b + rnd() * w * 0.6, y, w * (0.3 + rnd() * 0.9), 0.6 + rnd() * 0.8);
      }
      art.grain(c, -b, -b, w + b * 2, h + b * 2, 0.16);
      screw(c, 18, env.safeTop + 6, 5);
      screw(c, w - 18, env.safeTop + 6, 5);
      screw(c, 18, h - 22, 5);
      screw(c, w - 18, h - 22, 5);
      var p = center();
      // فرورفتگی دور قاب
      art.shadow(c, p.x + 4, p.y + 10, (G + RIM) * 1.22, (G + RIM) * 1.22, 0.6);
      art.vignette(c, w, h, 0.55);
    }

    function paintDial(c) {
      var m = G + RIM; // مرکز
      // قاب فلزی
      env.dropShadow(c, 8, 5, 0.55);
      var rim = c.createLinearGradient(0, 0, m * 2, m * 2);
      rim.addColorStop(0, "#f2f5fa");
      rim.addColorStop(0.3, "#8d98aa");
      rim.addColorStop(0.55, "#dfe5ee");
      rim.addColorStop(0.8, "#5b6576");
      rim.addColorStop(1, "#aab4c4");
      c.fillStyle = rim;
      c.beginPath();
      c.arc(m, m, m, 0, TAU);
      c.fill();
      env.dropShadow(c);
      c.strokeStyle = "rgba(0,0,0,.5)";
      c.lineWidth = 1.5;
      c.beginPath();
      c.arc(m, m, G + 1.5, 0, TAU);
      c.stroke();
      // صفحه
      var face = c.createRadialGradient(m - G * 0.3, m - G * 0.4, G * 0.1, m, m, G);
      face.addColorStop(0, "#2b3246");
      face.addColorStop(0.7, "#151a28");
      face.addColorStop(1, "#0a0d16");
      c.fillStyle = face;
      c.beginPath();
      c.arc(m, m, G, 0, TAU);
      c.fill();
      // سایه‌ی داخلی لبه
      var inner = c.createRadialGradient(m, m, G * 0.82, m, m, G);
      inner.addColorStop(0, "rgba(0,0,0,0)");
      inner.addColorStop(1, "rgba(0,0,0,.6)");
      c.fillStyle = inner;
      c.beginPath();
      c.arc(m, m, G, 0, TAU);
      c.fill();
      // مسیر ناحیه‌ی هدف
      c.strokeStyle = "rgba(255,255,255,.06)";
      c.lineWidth = 24;
      c.beginPath();
      c.arc(m, m, G - 38, A0, A0 + SWEEP);
      c.stroke();
      // درجه‌بندی
      c.lineCap = "round";
      for (var i = 0; i <= 40; i++) {
        var a = A0 + (i / 40) * SWEEP, major = i % 4 === 0;
        var r0 = G - (major ? 20 : 14), r1 = G - 7;
        c.strokeStyle = major ? "rgba(255,255,255,.92)" : "rgba(255,255,255,.4)";
        c.lineWidth = major ? 2.2 : 1.1;
        c.beginPath();
        c.moveTo(m + Math.cos(a) * r0, m + Math.sin(a) * r0);
        c.lineTo(m + Math.cos(a) * r1, m + Math.sin(a) * r1);
        c.stroke();
      }
      // قاب نمایشگر پایین
      art.rr(c, m - 54, m + 36, 108, 40, 9);
      c.fillStyle = "#05070c";
      c.fill();
      c.strokeStyle = "rgba(255,255,255,.14)";
      c.lineWidth = 1;
      c.stroke();
      var lcd = c.createLinearGradient(0, m + 38, 0, m + 74);
      lcd.addColorStop(0, "#10261c");
      lcd.addColorStop(1, "#0a1711");
      c.fillStyle = lcd;
      art.rr(c, m - 50, m + 40, 100, 32, 6);
      c.fill();
      // پیچ‌های قاب
      for (var k = 0; k < 4; k++) {
        var sa = Math.PI / 4 + (k * Math.PI) / 2;
        screw(c, m + Math.cos(sa) * (G + RIM / 2), m + Math.sin(sa) * (G + RIM / 2), 3.4);
      }
    }

    /* بازتاب شیشه روی صفحه */
    function paintGlass(c) {
      var m = G;
      c.beginPath();
      c.arc(m, m, G - 2, 0, TAU);
      c.clip();
      var g = c.createLinearGradient(0, 0, m * 1.4, m * 1.5);
      g.addColorStop(0, "rgba(255,255,255,.22)");
      g.addColorStop(0.45, "rgba(255,255,255,.04)");
      g.addColorStop(0.5, "rgba(255,255,255,0)");
      c.fillStyle = g;
      c.beginPath();
      c.ellipse(m * 0.7, m * 0.42, G * 0.95, G * 0.6, -0.5, 0, TAU);
      c.fill();
    }

    function paintHub(c) {
      env.dropShadow(c, 3, 2, 0.6);
      art.sphere(c, 15, 15, 14, "#2a3142", false);
      env.dropShadow(c);
      art.sphere(c, 15, 15, 7, "#c9d2e0");
    }

    function needle(c, x, y, theta, color, a) {
      c.save();
      c.translate(x, y);
      c.rotate(theta);
      c.globalAlpha = a;
      c.fillStyle = color;
      c.beginPath();
      c.moveTo(-26, -4.5);
      c.lineTo(G - 26, -1.4);
      c.lineTo(G - 14, 0);
      c.lineTo(G - 26, 1.4);
      c.lineTo(-26, 4.5);
      c.closePath();
      c.fill();
      c.restore();
    }

    return {
      controls: "tap",
      ownBackground: true,
      reset: function () {
        pulse = jolt = 0;
      },
      input: function (kind) {
        return kind === "tap" ? [] : null;
      },
      hud: function (state) {
        if (!state) return "";
        var left = Math.max(0, Math.ceil(((core.LIMIT_TICKS - state.tick) * core.TICK_MS) / 1000));
        return "⏱ " + env.fa(left) + " ثانیه";
      },
      event: function (name, state) {
        var p = center();
        var a = angleOf(state.pos);
        var x = p.x + Math.cos(a) * (G - 38), y = p.y + Math.sin(a) * (G - 38);
        if (name === "perfect") {
          pulse = 1;
          env.fx.burst(x, y, env.colors.gold, 22, 4);
          env.fx.ring(x, y, "#ffe9b0", 8, 54);
          env.fx.text(x, y - 26, "عالی! +۲۰", env.colors.gold);
          env.haptic("medium");
          env.sound("bonus");
        } else if (name === "hit") {
          pulse = 0.6;
          env.fx.burst(x, y, env.colors.good, 10, 3);
          env.fx.text(x, y - 26, "+۱۰", env.colors.good);
          env.haptic("light");
          env.sound("good");
        } else if (name === "miss") {
          jolt = 1;
          env.fx.flash(env.colors.danger, 0.3);
          env.fx.shake(7);
          env.haptic("error");
          env.sound("bad");
        } else if (name === "timeup") {
          env.fx.flash(env.colors.accent, 0.3);
          env.haptic("success");
        }
      },
      draw: function (c, state, alpha) {
        var p = center();
        var z = state.zone;
        pulse *= 0.9;
        jolt *= 0.86;
        env.scene(c, "timing", paintScene);
        env.blit(c, env.sprite("timing:dial", (G + RIM) * 2, (G + RIM) * 2, paintDial, 18), p.x - G - RIM, p.y - G - RIM);

        // ناحیه‌ی هدف و نوار طلایی وسط آن (۴۰٪ میانی = امتیاز دوبرابر)
        var a0 = angleOf(z.s), a1 = angleOf(z.s + z.w);
        var mid = (a0 + a1) / 2, gold = (a1 - a0) * 0.2;
        if (pulse > 0.02) art.glow(c, p.x + Math.cos(mid) * (G - 38), p.y + Math.sin(mid) * (G - 38), 60, "#5ee6a8", pulse * 0.8);
        c.lineCap = "butt";
        c.lineWidth = 24;
        c.strokeStyle = "#1f9d68";
        c.beginPath();
        c.arc(p.x, p.y, G - 38, a0, a1);
        c.stroke();
        c.lineWidth = 16;
        c.strokeStyle = "#48d597";
        c.beginPath();
        c.arc(p.x, p.y, G - 36, a0 + 0.012, a1 - 0.012);
        c.stroke();
        c.lineWidth = 24;
        c.strokeStyle = "#c98a12";
        c.beginPath();
        c.arc(p.x, p.y, G - 38, mid - gold, mid + gold);
        c.stroke();
        c.lineWidth = 16;
        c.strokeStyle = "#ffd257";
        c.beginPath();
        c.arc(p.x, p.y, G - 36, mid - gold + 0.01, mid + gold - 0.01);
        c.stroke();

        // نمایشگر: مرحله و چراغ‌های جان
        c.fillStyle = "#6dffb4";
        c.textAlign = "center";
        c.font = env.font(15, 800);
        c.fillText("مرحله " + env.fa(state.level + 1), p.x, p.y + 61);
        for (var i = 0; i < 3; i++) {
          var lx = p.x + (i - 1) * 24, ly = p.y + 96 - Math.abs(i - 1) * 4;
          var on = i < state.lives;
          if (on) art.glow(c, lx, ly, 13, "#ff5c7a", 0.7);
          art.sphere(c, lx, ly, 5.5, on ? "#ff4d6d" : "#3a3f4d", on);
        }

        // عقربه
        var pos = state.pos;
        if (!state.over) pos = env.clamp(pos + state.dir * state.speed * alpha, 0, core.BAR);
        var theta = angleOf(pos) + Math.sin(env.now() / 18) * jolt * 0.05;
        needle(c, p.x + 3, p.y + 5, theta, "#000000", 0.35);
        needle(c, p.x, p.y, theta, "#ff3b4e", 1);
        c.save();
        c.translate(p.x, p.y);
        c.rotate(theta);
        c.fillStyle = "rgba(255,255,255,.55)";
        c.fillRect(-24, -3.6, G - 4, 1.3);
        c.fillStyle = "#ffffff";
        c.fillRect(G - 40, -1.2, 22, 2.4);
        c.restore();
        env.blitC(c, env.sprite("timing:hub", 30, 30, paintHub, 6), p.x, p.y);
        env.blit(c, env.sprite("timing:glass", G * 2, G * 2, paintGlass), p.x - G, p.y - G);

        // نوار زمان زیر عقربه‌نما
        var remain = env.clamp(1 - state.tick / core.LIMIT_TICKS, 0, 1);
        var bw = 220, bx = p.x - bw / 2, by = Math.min(env.H - 46, p.y + G + RIM + 26);
        c.fillStyle = "rgba(0,0,0,.5)";
        art.rr(c, bx - 2, by - 2, bw + 4, 12, 6);
        c.fill();
        c.fillStyle = remain < 0.2 ? "#ff5c7a" : "#6ee7ff";
        art.rr(c, bx, by, Math.max(8, bw * remain), 8, 4);
        c.fill();
        c.fillStyle = "rgba(255,255,255,.4)";
        c.fillRect(bx + 3, by + 1.2, Math.max(2, bw * remain - 6), 1.6);
        c.fillStyle = "rgba(255,255,255,.6)";
        c.font = env.font(13, 600);
        c.fillText("نوار طلایی وسط = امتیاز دوبرابر", p.x, by + 32);
      },
    };
  });
})();
