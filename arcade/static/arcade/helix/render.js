/* «مارپیچ سقوط» — رندر سه‌بعدی و افکت‌ها: سکوهای ضخامت‌دار، ستون استوانه‌ای، توپ براق با سایه
   و رد رنگ روی سکوها.

   هر طبقه یک بار از بالا (به‌صورت حلقه) در یک اسپرایت کشیده می‌شود و در هر فریم فقط با چرخش و
   فشرده‌سازی عمودی روی صفحه می‌آید؛ ضخامت سکو با چند نسخه‌ی تیره‌ی همان حلقه زیر آن ساخته می‌شود. */
(function () {
  "use strict";
  Arcade.registerRenderer("helix", function (env) {
    var core = Arcade.cores.helix, art = env.art;
    var RAD = Math.PI / 180000;
    var TWO_PI = Math.PI * 2;
    var R_OUT = 128, R_IN = 40, TILT = 0.34, SY = 0.085, THICK = 15;
    var R_MID = (R_OUT + R_IN) / 2;
    var WALL_SCALE = 2; // اسپرایت دیواره با نصف وضوح ساخته می‌شود
    var THEMES = [
      { sky: ["#2f6fd0", "#7fd3ff"], plat: "#ffd166", ball: "#ff4d6d" },
      { sky: ["#51377a", "#6f86c9"], plat: "#7bdff2", ball: "#ffb703" },
      { sky: ["#10505c", "#6fb98f"], plat: "#f6ae2d", ball: "#f72585" },
      { sky: ["#3d2356", "#8a5a83"], plat: "#b8f2e6", ball: "#ff9f1c" },
      { sky: ["#1d4a3c", "#8fe3bf"], plat: "#ff9f1c", ball: "#4361ee" },
      { sky: ["#2d3340", "#4f8ff0"], plat: "#f7d6e0", ball: "#06d6a0" },
    ];
    var RED = "#e63946", BASE = "#ffd257";
    var camera = 0, pendingDx = 0, squash = 0;
    var splats = []; // رد رنگ توپ روی سکوها: { floor, local }
    var made = {}; // کلید اسپرایت طبقه‌هایی که ساخته شده‌اند → شماره‌ی طبقه
    var floorsRef = null; // برج فعلی؛ با ساخته شدن مرحله‌ی بعد عوض می‌شود
    var shownLevel = 0;

    function theme() {
      return THEMES[shownLevel % THEMES.length];
    }
    function floorScreenY(index) {
      return env.safeTop + 120 + (index * core.FLOOR_H - camera) * SY;
    }

    // ---------------------------------------------------------------- اسپرایت‌ها
    function sector(c, m, r0, r1, a0, a1) {
      c.beginPath();
      c.arc(m, m, r1, a0, a1);
      c.arc(m, m, r0, a1, a0, true);
      c.closePath();
      c.fill();
    }
    /* حلقه‌ی یک طبقه از نمای بالا. wall=true نسخه‌ی تیره برای ضخامت است. scale برای وضوح کمتر */
    function paintFloor(floor, plat, wall, scale) {
      return function (c, w) {
        var m = w / 2, r1 = R_OUT / scale, r0 = R_IN / scale;
        var platColor = wall ? art.shade(plat, -0.42) : plat;
        var redColor = wall ? art.shade(RED, -0.45) : RED;
        if (!floor) {
          c.fillStyle = wall ? art.shade(BASE, -0.42) : BASE;
          sector(c, m, r0, r1, 0, TWO_PI - 0.0001);
        } else {
          var gapEnd = (floor.gapStart + floor.gapSize) * RAD;
          c.fillStyle = platColor;
          sector(c, m, r0, r1, gapEnd, floor.gapStart * RAD + TWO_PI);
          for (var i = 0; i < floor.reds.length; i++) {
            // بخش قرمزی که روی شکاف افتاده دیده نمی‌شود (شکاف اولویت دارد)
            var start = floor.reds[i][0], size = floor.reds[i][1];
            var intoGap = ((start - floor.gapStart) % core.CIRCLE + core.CIRCLE) % core.CIRCLE;
            if (intoGap < floor.gapSize) {
              var cut = floor.gapSize - intoGap;
              start += cut;
              size -= cut;
            }
            var toGap = ((floor.gapStart - start) % core.CIRCLE + core.CIRCLE) % core.CIRCLE;
            if (toGap < size) size = toGap;
            if (size > 0) {
              c.fillStyle = redColor;
              sector(c, m, r0, r1, start * RAD, (start + size) * RAD);
            }
          }
        }
        if (wall) return;
        // سایه‌ی ملایم کنار ستون و برق لبه‌ی بیرونی (فقط روی خود سکو)
        c.globalCompositeOperation = "source-atop";
        var g = c.createRadialGradient(m, m, r0, m, m, r1);
        g.addColorStop(0, "rgba(0,0,0,.3)");
        g.addColorStop(0.25, "rgba(0,0,0,0)");
        g.addColorStop(0.9, "rgba(255,255,255,0)");
        g.addColorStop(1, "rgba(255,255,255,.35)");
        c.fillStyle = g;
        c.fillRect(0, 0, w, w);
        c.globalCompositeOperation = "source-over";
      };
    }
    function floorSprite(state, k, wall) {
      var key = "helix:floor:" + k + (wall ? ":w" : "");
      made[key] = k;
      var floor = k <= state.count ? state.floors[k - 1] : null;
      var scale = wall ? WALL_SCALE : 1;
      var size = (R_OUT * 2) / scale;
      return env.sprite(key, size, size, paintFloor(floor, theme().plat, wall, scale), 1);
    }
    function forgetFloors(keep) {
      for (var key in made) {
        if (keep === undefined || made[key] < keep) {
          env.forget(key);
          delete made[key];
        }
      }
    }
    function paintSky(colors) {
      return function (c, w, h) {
        var g = c.createLinearGradient(0, 0, 0, h);
        g.addColorStop(0, colors[0]);
        g.addColorStop(1, colors[1]);
        c.fillStyle = g;
        c.fillRect(-1, -1, w + 2, h + 2);
      };
    }
    function paintPillar(c, w, h) {
      var g = c.createLinearGradient(0, 0, w, 0);
      g.addColorStop(0, "#9aa6bd");
      g.addColorStop(0.22, "#ffffff");
      g.addColorStop(0.5, "#dfe6f2");
      g.addColorStop(1, "#77839c");
      c.fillStyle = g;
      c.fillRect(0, -1, w, h + 2);
    }
    function paintBall(color, fire) {
      return function (c) {
        env.dropShadow(c, 2, 1.5, 0.35);
        art.sphere(c, 12, 12, 11.5, fire ? "#ffb703" : color);
      };
    }

    /* یک حلقه با چرخش برج و فشرده‌سازی عمودی (نمای مایل) */
    function ring(c, sp, cx, y, rotRad, scale) {
      c.save();
      c.translate(cx, y);
      c.scale(scale, scale * TILT);
      c.rotate(rotRad);
      c.drawImage(sp.canvas, -sp.fw / 2, -sp.fh / 2, sp.fw, sp.fh);
      c.restore();
    }

    return {
      controls: "drag",
      ownBackground: true,
      reset: function (state) {
        camera = state.y - 1400;
        pendingDx = 0;
        splats = [];
        forgetFloors();
        floorsRef = null;
      },
      input: function (kind, data) {
        if (kind === "drag") pendingDx += data.dx;
        return null; // ورودی در sample و یک بار در هر تیک ثبت می‌شود
      },
      sample: function (state) {
        if (state.pause > 0) { pendingDx = 0; return null; }
        // کشیدن به راست، سطح جلوی برج را به راست می‌برد
        var turn = Math.round(-pendingDx * 600);
        pendingDx = 0;
        if (!turn) return null;
        return [Math.max(-core.MAX_TURN, Math.min(core.MAX_TURN, turn))];
      },
      hud: function (state) {
        if (!state) return "";
        var fire = state.streak >= core.FIRE_STREAK ? " · 🔥 آتشین" : "";
        return "مرحله " + env.fa(state.level + 1) + fire;
      },
      event: function (name, state) {
        var cx = env.W / 2, y = floorScreenY(state.floorIdx) + R_MID * TILT;
        var th = theme();
        if (name === "bounce") {
          squash = 1;
          splats.push({ floor: state.floorIdx, local: (core.BALL_ANGLE - state.rot) * RAD });
          if (splats.length > 14) splats.shift();
          env.fx.burst(cx, y - 6, th.ball, 6, 2);
          env.sound("tick");
        } else if (name === "pass") {
          env.fx.text(cx + 60, y - 70, "+" + env.fa(state.streak), env.colors.gold);
          env.haptic("light");
          env.sound("good");
        } else if (name === "smash") {
          env.fx.debris(cx, y - 150, th.plat, 18, 6, 7);
          env.fx.burst(cx, y - 150, "#ffb703", 22, 5);
          env.fx.shake(7);
          env.haptic("heavy");
          env.sound("bonus");
        } else if (name === "clear") {
          env.fx.burst(cx, y, env.colors.good, 34, 7);
          env.fx.ring(cx, y, "#ffffff", 20, 140);
          env.fx.flash("#ffffff", 0.3);
          env.haptic("success");
          env.sound("clear");
        } else if (name === "fail") {
          env.fx.debris(cx, y, th.ball, 14, 6, 4);
          env.fx.flash(env.colors.danger, 0.5);
          env.fx.shake(10);
          env.haptic("error");
          env.sound("bad");
        }
      },
      draw: function (c, state, alpha) {
        var cx = env.W / 2, W = env.W, H = env.H;
        var ballY = state.y + (state.over || state.pause > 0 ? 0 : state.vy * alpha);
        camera += (ballY - 1400 - camera) * 0.14;
        // برج تازه (مرحله‌ی بعد): اسپرایت طبقه‌های قبلی و رد رنگ‌ها دور ریخته می‌شوند
        if (state.floors !== floorsRef) {
          forgetFloors();
          floorsRef = state.floors;
          shownLevel = state.level;
          splats = [];
        }
        var th = theme();
        var total = state.count + 1; // آخرین حلقه کف برج است
        var first = Math.max(1, Math.floor(camera / core.FLOOR_H));
        var last = Math.min(total, first + Math.ceil(H / (core.FLOOR_H * SY)) + 2);
        var ballDrawn = false;
        var fire = state.streak >= core.FIRE_STREAK;
        var themeIndex = shownLevel % THEMES.length;
        var gap = core.FLOOR_H * SY;
        var rotRad = state.rot * RAD;

        forgetFloors(first - 1); // طبقه‌های رد‌شده دیگر لازم نیستند

        c.drawImage(env.sprite("helix:sky:" + themeIndex, 4, H, paintSky(th.sky)).canvas, -12, -12, W + 24, H + 24);
        art.glow(c, cx, H * 0.45, W * 0.9, "#ffffff", 0.22);
        var pillar = env.sprite("helix:pillar", R_IN * 2, 8, paintPillar);
        c.drawImage(pillar.canvas, cx - R_IN, -12, R_IN * 2, H + 24);

        function drawBall() {
          squash *= 0.8;
          var floorY = env.safeTop + 120 + (state.floorIdx * core.FLOOR_H - camera) * SY + R_MID * TILT;
          var by = env.safeTop + 120 + (ballY - camera) * SY + R_MID * TILT - 11;
          // سایه روی سکوی زیر توپ (هرچه بالاتر، کم‌رنگ‌تر)
          var height = floorY - 11 - by;
          var under = state.floorIdx <= state.count ? state.floors[state.floorIdx - 1] : null;
          var solid = !under || (!under.broken && core.sector(under, ((core.BALL_ANGLE - state.rot) % core.CIRCLE + core.CIRCLE) % core.CIRCLE) !== 0);
          if (solid && state.floorIdx <= total && height < 110) art.shadow(c, cx, floorY, 12 - height * 0.04, (12 - height * 0.04) * 0.42, 0.45 - height * 0.003);
          if (fire) {
            art.glow(c, cx, by, 34 + Math.sin(env.now() / 50) * 4, "#ff7b00", 0.8);
            art.glow(c, cx, by - 16, 20, "#ffd257", 0.6);
          }
          env.blitC(c, env.sprite(fire ? "helix:fire" : "helix:ball:" + themeIndex, 24, 24, paintBall(th.ball, fire), 5), cx, by + squash * 3, 0, 1 + squash * 0.25, 1 - squash * 0.25);
        }

        // از پایین به بالا: ضخامت و سطح سکو، تکه‌ی ستون بالای آن (روی نیمه‌ی پشتی)، توپ
        for (var k = last; k >= first; k--) {
          var floor = k <= state.count ? state.floors[k - 1] : null;
          var y = floorScreenY(k);
          if (y > H + 70 || y < -70) continue;
          if (!(floor && floor.broken)) {
            var wall = floorSprite(state, k, true);
            for (var d = THICK; d > 0; d -= 2.5) ring(c, wall, cx, y + d, rotRad, WALL_SCALE);
            ring(c, floorSprite(state, k, false), cx, y, rotRad, 1);
            // رد رنگ توپ روی این سکو
            for (var s = 0; s < splats.length; s++) {
              var splat = splats[s];
              if (splat.floor !== k) continue;
              var a = splat.local + rotRad;
              c.globalAlpha = 0.5;
              c.fillStyle = th.ball;
              c.beginPath();
              c.ellipse(cx + Math.cos(a) * R_MID, y + Math.sin(a) * R_MID * TILT, 12, 5, 0, 0, TWO_PI);
              c.fill();
              c.globalAlpha = 1;
            }
          }
          c.drawImage(pillar.canvas, cx - R_IN, y - gap, R_IN * 2, gap);
          if (k === state.floorIdx - 1 && !ballDrawn) {
            // توپ زیر طبقه‌هایی است که از آن‌ها رد شده
            drawBall();
            ballDrawn = true;
          }
        }
        if (!ballDrawn) drawBall();
      },
    };
  });
})();
