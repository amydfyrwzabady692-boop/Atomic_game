/* «کاشی‌های سیاه» — رندر و افکت‌ها */
(function () {
  "use strict";
  Arcade.registerRenderer("tiles", function (env) {
    var core = Arcade.cores.tiles;
    var shown = 0; // اسکرول نمایشی (در حالت ۵۰ کاشی نرم دنبال منطق می‌رود)
    var hitFlash = [];

    function rowH() { return env.H / core.VISIBLE_ROWS; }
    function colW() { return env.W / 4; }

    return {
      controls: "tap",
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
          env.haptic("light");
          env.sound("tap");
        } else if (name === "win") {
          env.fx.flash(env.colors.good, 0.4);
          env.fx.burst(env.W / 2, env.H / 2, env.colors.gold, 40, 7);
          env.haptic("success");
          env.sound("clear");
        } else if (name === "fail") {
          env.fx.flash(env.colors.danger, 0.5);
          env.fx.shake(12);
          env.haptic("error");
          env.sound("bad");
        }
      },
      draw: function (c, state, alpha) {
        var rh = rowH(), cw = colW(), unit = rh / core.ROW_H;
        // در حالت ۵۰ کاشی، کاشی بعدی یک ردیف پایین‌تر نمایش داده می‌شود (نزدیک انگشت)
        var base = state.mode === "fifty" ? core.ROW_H : 2 * core.ROW_H;
        var target = state.offset;
        if (state.mode === "endless" && state.started && !state.over) target += core.speedFor(state.hits) * alpha;
        shown = state.mode === "fifty" ? shown + (target - shown) * 0.35 : target;

        c.fillStyle = "rgba(8,10,28,.45)";
        c.fillRect(0, 0, env.W, env.H);
        c.strokeStyle = "rgba(255,255,255,.08)";
        c.lineWidth = 1;
        for (var k = 1; k < 4; k++) {
          c.beginPath();
          c.moveTo(k * cw, 0);
          c.lineTo(k * cw, env.H);
          c.stroke();
        }

        var first = Math.max(0, Math.floor((shown - base) / core.ROW_H) - 1);
        for (var row = first; row < first + 7 && row < state.cols.length; row++) {
          var bottom = (base + row * core.ROW_H - shown) * unit;
          var y = env.H - bottom - rh;
          if (y > env.H || y + rh < 0) continue;
          var done = row < state.hits;
          var isNext = row === state.hits;
          var tx = state.cols[row] * cw + 4;
          if (done) {
            c.fillStyle = "rgba(255,255,255,.06)";
          } else {
            var tgrad = c.createLinearGradient(0, y, 0, y + rh);
            tgrad.addColorStop(0, isNext ? "#6ee7ff" : "#8b9cff");
            tgrad.addColorStop(1, isNext ? "#7aa2ff" : "#a78bfa");
            c.fillStyle = tgrad;
            env.glow(c, isNext ? "#6ee7ff" : "#a78bfa", isNext ? 22 : 10);
          }
          env.roundRect(c, tx, y + 4, cw - 8, rh - 8, 14);
          c.fill();
          env.glow(c);
          if (!done) {
            c.fillStyle = "rgba(255,255,255,.28)";
            env.roundRect(c, tx + 6, y + 10, cw - 20, 6, 3);
            c.fill();
          }
          if (isNext && !state.started) {
            c.fillStyle = "#0d1324";
            c.textAlign = "center";
            c.font = env.font(18, 800);
            c.fillText("شروع", state.cols[row] * cw + cw / 2, y + rh / 2 + 6);
          }
          c.strokeStyle = "rgba(255,255,255,.05)";
          c.beginPath();
          c.moveTo(0, y);
          c.lineTo(env.W, y);
          c.stroke();
        }

        for (var f = hitFlash.length - 1; f >= 0; f--) {
          var hit = hitFlash[f];
          hit.life -= 0.08;
          if (hit.life <= 0) { hitFlash.splice(f, 1); continue; }
          var hy = env.H - (base + hit.row * core.ROW_H - shown) * unit - rh;
          c.globalAlpha = hit.life * 0.6;
          c.fillStyle = env.colors.good;
          env.roundRect(c, state.cols[hit.row] * cw + 3, hy + 3, cw - 6, rh - 6, 10);
          c.fill();
          c.globalAlpha = 1;
        }

        if (state.over && state.wrongCol >= 0) {
          var wy = env.H - (base + state.hits * core.ROW_H - shown) * unit - rh;
          c.fillStyle = env.colors.danger;
          env.roundRect(c, state.wrongCol * cw + 3, wy + 3, cw - 6, rh - 6, 10);
          c.fill();
        }
        // سایه‌ی بالای صفحه تا امتیاز خوانا بماند
        var shade = c.createLinearGradient(0, 0, 0, env.safeTop + 30);
        shade.addColorStop(0, "rgba(9,11,28,.9)");
        shade.addColorStop(1, "rgba(9,11,28,0)");
        c.fillStyle = shade;
        c.fillRect(0, 0, env.W, env.safeTop + 30);
      },
    };
  });
})();
