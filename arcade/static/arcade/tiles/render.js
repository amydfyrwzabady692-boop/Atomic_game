/* «کاشی‌های سیاه» — رندر و افکت‌ها: کلیدهای عاجی پیانو و کاشی‌های مشکی براق (لاک پیانو). */
(function () {
  "use strict";
  Arcade.registerRenderer("tiles", function (env) {
    var core = Arcade.cores.tiles, art = env.art;
    var shown = 0; // اسکرول نمایشی (در حالت ۵۰ کاشی نرم دنبال منطق می‌رود)
    var hitFlash = [];
    var INSET = 4;

    function rowH() { return env.H / core.VISIBLE_ROWS; }
    function colW() { return env.W / 4; }

    // ---------------------------------------------------------------- اسپرایت‌ها
    function paintScene(c, w, h, b) {
      var cw = w / 4;
      for (var k = 0; k < 4; k++) {
        var x = k * cw - (k === 0 ? b : 0), kw = cw + (k === 0 || k === 3 ? b : 0);
        var g = c.createLinearGradient(x, 0, x + kw, 0);
        g.addColorStop(0, "#e9e4d8");
        g.addColorStop(0.08, "#fbf8f0");
        g.addColorStop(0.9, "#f1ecdf");
        g.addColorStop(1, "#d6cfbf");
        c.fillStyle = g;
        c.fillRect(x, -b, kw, h + b * 2);
        // شکاف بین کلیدها
        if (k > 0) {
          c.fillStyle = "rgba(40,30,20,.55)";
          c.fillRect(k * cw - 0.8, -b, 1.6, h + b * 2);
          c.fillStyle = "rgba(255,255,255,.7)";
          c.fillRect(k * cw + 0.8, -b, 1, h + b * 2);
        }
      }
      var depth = c.createLinearGradient(0, 0, 0, h);
      depth.addColorStop(0, "rgba(60,40,20,.12)");
      depth.addColorStop(0.5, "rgba(60,40,20,0)");
      depth.addColorStop(1, "rgba(60,40,20,.2)");
      c.fillStyle = depth;
      c.fillRect(-b, -b, w + b * 2, h + b * 2);
      art.grain(c, -b, -b, w + b * 2, h + b * 2, 0.12);
    }

    /* kind: black | next | wrong */
    function paintTile(kind, w, h) {
      return function (c) {
        var base = kind === "wrong" ? "#c2283c" : "#17171b";
        env.dropShadow(c, 5, 4, 0.5);
        var g = c.createLinearGradient(0, 0, w, 0);
        g.addColorStop(0, art.shade(base, 0.14));
        g.addColorStop(0.5, base);
        g.addColorStop(1, art.shade(base, -0.5));
        c.fillStyle = g;
        art.rr(c, 0, 0, w, h, 11);
        c.fill();
        env.dropShadow(c);
        c.save();
        art.rr(c, 0, 0, w, h, 11);
        c.clip();
        // برق لاک: نوار روشن سمت چپ و بازتاب بالا
        var streak = c.createLinearGradient(0, 0, w * 0.5, 0);
        streak.addColorStop(0, "rgba(255,255,255,0)");
        streak.addColorStop(0.3, "rgba(255,255,255,.22)");
        streak.addColorStop(0.42, "rgba(255,255,255,.04)");
        streak.addColorStop(1, "rgba(255,255,255,0)");
        c.fillStyle = streak;
        c.fillRect(0, 0, w, h);
        var top = c.createLinearGradient(0, 0, 0, h * 0.3);
        top.addColorStop(0, "rgba(255,255,255,.26)");
        top.addColorStop(1, "rgba(255,255,255,0)");
        c.fillStyle = top;
        c.fillRect(0, 0, w, h * 0.3);
        var foot = c.createLinearGradient(0, h * 0.82, 0, h);
        foot.addColorStop(0, "rgba(0,0,0,0)");
        foot.addColorStop(1, "rgba(0,0,0,.5)");
        c.fillStyle = foot;
        c.fillRect(0, h * 0.82, w, h * 0.18);
        c.restore();
        if (kind === "next") {
          c.strokeStyle = "#ffd257";
          c.lineWidth = 2.5;
          art.rr(c, 1.5, 1.5, w - 3, h - 3, 10);
          c.stroke();
          c.strokeStyle = "rgba(255,210,87,.3)";
          c.lineWidth = 6;
          c.stroke();
        }
      };
    }

    function paintTopShade(c, w, h) {
      var g = c.createLinearGradient(0, 0, 0, h);
      g.addColorStop(0, "rgba(14,12,10,.82)");
      g.addColorStop(0.55, "rgba(14,12,10,.3)");
      g.addColorStop(1, "rgba(14,12,10,0)");
      c.fillStyle = g;
      c.fillRect(-1, -1, w + 2, h + 2);
    }

    return {
      controls: "tap",
      ownBackground: true,
      reset: function (state) {
        shown = state.offset;
        hitFlash = [];
      },
      input: function (kind, data) {
        if (kind !== "tap") return null;
        return [Math.max(0, Math.min(3, Math.floor(data.x / colW())))];
      },
      hud: function (state) {
        if (!state) return "";
        if (state.mode === "fifty") {
          var secs = state.started ? ((state.tick - state.startTick) * core.TICK_MS) / 1000 : 0;
          return env.fa(state.hits) + " از " + env.fa(core.TARGET) + " · " + env.fa(secs.toFixed(1)) + " ثانیه";
        }
        return state.started ? "" : "پایین‌ترین کاشی تیره را بزن";
      },
      event: function (name, state) {
        if (name === "hit") {
          hitFlash.push({ row: state.hits - 1, life: 1 });
          var col = state.cols[state.hits - 1];
          env.fx.text((col + 0.5) * colW(), env.H * 0.62, ["♪", "♫", "♩"][state.hits % 3], ["#ffd257", "#6ee7ff", "#ff9ecb"][state.hits % 3]);
          env.haptic("light");
          env.sound("tap");
        } else if (name === "win") {
          env.fx.flash(env.colors.good, 0.4);
          env.fx.burst(env.W / 2, env.H / 2, env.colors.gold, 40, 7);
          env.haptic("success");
          env.sound("clear");
        } else if (name === "fail") {
          env.fx.flash(env.colors.danger, 0.5);
          env.fx.shake(10);
          env.haptic("error");
          env.sound("bad");
        }
      },
      draw: function (c, state, alpha) {
        var rh = rowH(), cw = colW(), unit = rh / core.ROW_H;
        var tw = cw - INSET * 2, th = rh - INSET * 2;
        // در حالت ۵۰ کاشی، کاشی بعدی یک ردیف پایین‌تر نمایش داده می‌شود (نزدیک انگشت)
        var base = state.mode === "fifty" ? core.ROW_H : 2 * core.ROW_H;
        var target = state.offset;
        if (state.mode === "endless" && state.started && !state.over) target += core.speedFor(state.hits) * alpha;
        shown = state.mode === "fifty" ? shown + (target - shown) * 0.35 : target;

        env.scene(c, "tiles", paintScene);
        var black = env.sprite("tiles:black", tw, th, paintTile("black", tw, th), 10);
        var next = env.sprite("tiles:next", tw, th, paintTile("next", tw, th), 10);

        var first = Math.max(0, Math.floor((shown - base) / core.ROW_H) - 1);
        for (var row = first; row < first + 7 && row < state.cols.length; row++) {
          var bottom = (base + row * core.ROW_H - shown) * unit;
          var y = env.H - bottom - rh;
          if (y > env.H || y + rh < 0) continue;
          var tx = state.cols[row] * cw + INSET;
          if (row < state.hits) {
            // کاشی زده‌شده: رد کم‌رنگ
            c.fillStyle = "rgba(40,30,20,.13)";
            art.rr(c, tx, y + INSET, tw, th, 11);
            c.fill();
            continue;
          }
          var isNext = row === state.hits;
          env.blit(c, isNext ? next : black, tx, y + INSET);
          if (isNext && !state.started) {
            c.fillStyle = "#ffd257";
            c.textAlign = "center";
            c.font = env.font(19, 800);
            c.fillText("شروع", state.cols[row] * cw + cw / 2, y + rh / 2 + 7);
          }
        }

        for (var f = hitFlash.length - 1; f >= 0; f--) {
          var hit = hitFlash[f];
          hit.life -= 0.07;
          if (hit.life <= 0) { hitFlash.splice(f, 1); continue; }
          var hy = env.H - (base + hit.row * core.ROW_H - shown) * unit - rh;
          var hx = state.cols[hit.row] * cw;
          var grow = (1 - hit.life) * 10;
          c.globalAlpha = hit.life * 0.55;
          c.fillStyle = "#3fdc94";
          art.rr(c, hx + INSET - grow, hy + INSET - grow, tw + grow * 2, th + grow * 2, 11 + grow);
          c.fill();
          c.globalAlpha = 1;
        }

        if (state.over && state.wrongCol >= 0) {
          var wy = env.H - (base + state.hits * core.ROW_H - shown) * unit - rh;
          env.blit(c, env.sprite("tiles:wrong", tw, th, paintTile("wrong", tw, th), 10), state.wrongCol * cw + INSET, wy + INSET);
        }
        // سایه‌ی بالای صفحه تا امتیاز خوانا بماند
        var shade = env.sprite("tiles:top", 4, env.safeTop + 40, paintTopShade);
        c.drawImage(shade.canvas, -12, -12, env.W + 24, env.safeTop + 52);
      },
    };
  });
})();
