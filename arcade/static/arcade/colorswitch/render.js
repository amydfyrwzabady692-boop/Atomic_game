/* «تعویض رنگ» — رندر و افکت‌ها: حلقه‌های لوله‌ای براق، توپ شیشه‌ای و پس‌زمینه‌ی تیره با نورهای محو. */
(function () {
  "use strict";
  Arcade.registerRenderer("colorswitch", function (env) {
    var core = Arcade.cores.colorswitch, art = env.art;
    var COLORS = ["#2bc8f5", "#ffc233", "#ff4f93", "#3fdc94"];
    var RAD = Math.PI / 180000;
    var TAU = Math.PI * 2;
    var S = 0.1; // واحد core → پیکسل
    var THICK = core.HALF_T * 2 * S;
    var camera = 0;
    var squash = 0;
    var trail = [];

    function screenY(worldY) {
      return env.H * 0.68 - (worldY - camera) * S;
    }

    // ---------------------------------------------------------------- اسپرایت‌ها
    function paintScene(c, w, h, b) {
      var g = c.createLinearGradient(0, -b, 0, h + b);
      g.addColorStop(0, "#1a1c2c");
      g.addColorStop(0.55, "#111320");
      g.addColorStop(1, "#08090f");
      c.fillStyle = g;
      c.fillRect(-b, -b, w + b * 2, h + b * 2);
      // نورهای محو دوردست
      var rnd = art.rand(23);
      for (var i = 0; i < 16; i++) {
        var x = rnd() * w, y = rnd() * h, r = 26 + rnd() * 70;
        var color = COLORS[i % 4];
        var bg = c.createRadialGradient(x, y, 0, x, y, r);
        bg.addColorStop(0, art.alpha(color, 0.1 + rnd() * 0.07));
        bg.addColorStop(0.7, art.alpha(color, 0.035));
        bg.addColorStop(1, art.alpha(color, 0));
        c.fillStyle = bg;
        c.fillRect(x - r, y - r, r * 2, r * 2);
      }
      art.grain(c, -b, -b, w + b * 2, h + b * 2, 0.14);
      art.vignette(c, w, h, 0.6);
    }

    /* حلقه‌ی چهاررنگ با حجم لوله‌ای؛ رنگ i ربع [i×۹۰°، (i+۱)×۹۰°) را می‌گیرد */
    function paintRing(radius) {
      return function (c, w) {
        var m = w / 2, r = radius * S, i;
        c.lineCap = "butt";
        env.dropShadow(c, 5, 4, 0.5);
        for (i = 0; i < 4; i++) {
          c.strokeStyle = art.shade(COLORS[i], -0.38);
          c.lineWidth = THICK;
          c.beginPath();
          c.arc(m, m, r, (i * Math.PI) / 2, ((i + 1) * Math.PI) / 2);
          c.stroke();
        }
        env.dropShadow(c);
        for (i = 0; i < 4; i++) {
          var a0 = (i * Math.PI) / 2 + 0.012, a1 = ((i + 1) * Math.PI) / 2 - 0.012;
          c.strokeStyle = COLORS[i];
          c.lineWidth = THICK * 0.74;
          c.beginPath();
          c.arc(m, m, r, a0, a1);
          c.stroke();
          c.strokeStyle = art.shade(COLORS[i], 0.5);
          c.lineWidth = THICK * 0.2;
          c.beginPath();
          c.arc(m, m, r - THICK * 0.16, a0, a1);
          c.stroke();
        }
      };
    }

    /* نوار چهاررنگ متحرک: هر رنگ یک‌چهارم عرض صفحه */
    function paintBar(c, w, h) {
      var seg = core.SEG_W * S;
      for (var i = 0; i < 4; i++) {
        var g = c.createLinearGradient(0, 0, 0, h);
        g.addColorStop(0, art.shade(COLORS[i], 0.45));
        g.addColorStop(0.3, COLORS[i]);
        g.addColorStop(1, art.shade(COLORS[i], -0.42));
        c.fillStyle = g;
        c.fillRect(i * seg, 0, seg + 0.5, h);
        c.fillStyle = "rgba(0,0,0,.35)";
        c.fillRect(i * seg, 0, 1, h);
      }
    }

    function paintBall(color, r) {
      return function (c) {
        env.dropShadow(c, 3, 2, 0.45);
        art.sphere(c, r, r, r, color);
      };
    }

    function paintStar(c, w) {
      var m = w / 2;
      env.dropShadow(c, 3, 1.5, 0.5);
      var g = c.createLinearGradient(0, 0, w, w);
      g.addColorStop(0, "#fff6c9");
      g.addColorStop(0.5, "#ffd257");
      g.addColorStop(1, "#d98b12");
      c.fillStyle = g;
      art.starPath(c, m, m + 1, m - 1);
      c.fill();
      env.dropShadow(c);
      c.fillStyle = "rgba(255,255,255,.55)";
      art.starPath(c, m - 1.5, m - 1, (m - 1) * 0.42);
      c.fill();
    }

    /* گوی تعویض رنگ */
    function paintSwitch(c, w) {
      var m = w / 2, r = m - 1;
      env.dropShadow(c, 3, 2, 0.5);
      c.fillStyle = "#10121c";
      c.beginPath();
      c.arc(m, m, r, 0, TAU);
      c.fill();
      env.dropShadow(c);
      for (var q = 0; q < 4; q++) {
        c.fillStyle = COLORS[q];
        c.beginPath();
        c.moveTo(m, m);
        c.arc(m, m, r, (q * Math.PI) / 2, ((q + 1) * Math.PI) / 2);
        c.closePath();
        c.fill();
      }
      var g = c.createRadialGradient(m - r * 0.35, m - r * 0.4, 1, m, m, r);
      g.addColorStop(0, "rgba(255,255,255,.65)");
      g.addColorStop(0.4, "rgba(255,255,255,.08)");
      g.addColorStop(1, "rgba(0,0,0,.4)");
      c.fillStyle = g;
      c.beginPath();
      c.arc(m, m, r, 0, TAU);
      c.fill();
    }

    function paintBase(c, w, h) {
      env.dropShadow(c, 4, 3, 0.5);
      art.bevel(c, 0, 0, w, h, 6, "#566078");
      env.dropShadow(c);
      c.fillStyle = "rgba(255,255,255,.25)";
      c.fillRect(8, 3, w - 16, 1.4);
    }

    return {
      controls: "tap",
      ownBackground: true,
      reset: function () {
        camera = 0;
        trail = [];
      },
      input: function (kind) {
        return kind === "tap" ? [] : null;
      },
      hud: function (state) {
        if (!state) return "";
        return state.started ? "مرحله " + env.fa(state.level + 1) : "برای شروع تپ کن";
      },
      event: function (name, state) {
        var x = env.W / 2, y = screenY(state.y);
        if (name === "jump") {
          squash = 1;
          env.sound("tick");
        } else if (name === "pass") {
          env.fx.text(x, y - 34, "+۱", env.colors.gold);
          env.fx.burst(x, y, "#fff2b8", 12, 3.2);
          env.fx.ring(x, y, "#ffe9b0", 8, 40);
          env.haptic("light");
          env.sound("good");
        } else if (name === "switch") {
          env.fx.burst(x, y, COLORS[state.color], 18, 4);
          env.fx.ring(x, y, COLORS[state.color], 10, 50);
          env.haptic("medium");
          env.sound("bonus");
        } else if (name === "fail") {
          for (var i = 0; i < 4; i++) env.fx.debris(x, y, COLORS[i], 6, 5.5, 4);
          env.fx.flash(env.colors.danger, 0.45);
          env.fx.shake(10);
          env.haptic("error");
          env.sound("bad");
        }
      },
      draw: function (c, state, alpha) {
        var y = state.y + (state.started && !state.over ? state.vy * alpha : 0);
        var target = Math.max(0, state.maxY - 900);
        camera += (target - camera) * 0.12;
        var tick = state.tick + (state.over ? 0 : alpha);
        var cx = env.W / 2;
        var now = env.now();
        env.scene(c, "colorswitch", paintScene);

        var first = Math.max(0, Math.floor((camera - 2600) / core.SPACING) - 1);
        for (var k = first; k < first + 4; k++) {
          var spec = core.specOf(state, k);
          var sy = screenY(spec.y);
          if (sy > -160 && sy < env.H + 160) {
            if (spec.type === 2) {
              var bar = env.sprite("cs:bar", env.W, THICK, paintBar);
              var off = core.barOffset(spec, tick) * S;
              art.shadow(c, cx, sy + THICK * 0.9, env.W * 0.6, 7, 0.45);
              env.blit(c, bar, off - env.W, sy - THICK / 2);
              env.blit(c, bar, off, sy - THICK / 2);
            } else {
              var size = (core.RING_R * S + THICK) * 2;
              env.blitC(c, env.sprite("cs:ring", size, size, paintRing(core.RING_R), 12), cx, sy, core.ringRot(spec, tick) * RAD);
              if (spec.type === 1) {
                var outer = (core.OUTER_R * S + THICK) * 2;
                env.blitC(c, env.sprite("cs:outer", outer, outer, paintRing(core.OUTER_R), 12), cx, sy, core.outerRot(spec, tick) * RAD);
              }
            }
            if (k >= state.passed && spec.type !== 2) {
              var beat = 1 + Math.sin(now / 260 + k) * 0.08;
              art.glow(c, cx, sy, 26, "#ffd257", 0.35);
              env.blitC(c, env.sprite("cs:star", 28, 28, paintStar, 5), cx, sy, 0, beat);
            }
          }
          // گوی تعویض رنگ بین این مانع و بعدی
          if (k >= state.switched) {
            var iy = screenY(spec.y + core.SPACING / 2);
            if (iy > -30 && iy < env.H + 30) {
              env.blitC(c, env.sprite("cs:switch", 30, 30, paintSwitch, 5), cx, iy, now / 420);
            }
          }
        }

        // سکوی شروع
        var gy = screenY(0) + core.BALL_R * S;
        if (gy < env.H + 20) env.blit(c, env.sprite("cs:base", 124, 12, paintBase, 8), cx - 62, gy);

        // رد حرکت و توپ
        squash *= 0.8;
        var by = screenY(y), r = core.BALL_R * S;
        var color = COLORS[state.color];
        if (state.started && !state.over) trail.push(by);
        if (trail.length > 7) trail.shift();
        for (var t = 0; t < trail.length; t++) {
          c.globalAlpha = (t / trail.length) * 0.22;
          c.fillStyle = color;
          c.beginPath();
          c.arc(cx, trail[t], r * (0.45 + (t / trail.length) * 0.45), 0, TAU);
          c.fill();
        }
        c.globalAlpha = 1;
        if (!state.over) {
          art.glow(c, cx, by, r * 2.6, color, 0.45);
          env.blitC(c, env.sprite("cs:ball:" + state.color, r * 2, r * 2, paintBall(color, r), 6), cx, by, 0, 1 - squash * 0.15, 1 + squash * 0.2);
        }
      },
    };
  });
})();
