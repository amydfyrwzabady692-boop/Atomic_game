/* «۲۰۴۸ سرعتی» — رندر و افکت‌ها: سینی چوبی روی میز ماهوتی و کاشی‌های سرامیکی برجسته.
   کاشی‌ها واقعاً سر می‌خورند: مسیر هر کاشی از مقایسه‌ی صفحه‌ی قبل و بعد به دست می‌آید. */
(function () {
  "use strict";
  Arcade.registerRenderer("g2048", function (env) {
    var core = Arcade.cores.g2048, art = env.art;
    var DIRS = { up: 0, right: 1, down: 2, left: 3 };
    var FA = "۰۱۲۳۴۵۶۷۸۹";
    var TILES = {
      2: ["#f3e9d8", "#6a5743"], 4: ["#eedbb2", "#6a5743"], 8: ["#f5a95c", "#fffaf2"], 16: ["#f28a48", "#fffaf2"],
      32: ["#ee6c4c", "#fffaf2"], 64: ["#e04a3a", "#fffaf2"], 128: ["#f2d268", "#5c4410"], 256: ["#f0c843", "#5c4410"],
      512: ["#ebb81f", "#4a360a"], 1024: ["#4fb3d9", "#f4fbff"], 2048: ["#7d6cf2", "#ffffff"],
    };
    var BIG = ["#2b2d3e", "#ffd257"];
    var SLIDE_MS = 95, POP_MS = 170, SPAWN_MS = 130;
    var GAP = 8, FRAME = 9;

    var prev = null; // آخرین صفحه‌ای که نمایش داده شده
    var anim = null; // { moves: [{v, from, to}], start }
    var popAt = [], spawnIdx = -1, spawnAt = 0;

    function digits(v) {
      return String(v).replace(/\d/g, function (d) { return FA[d]; });
    }
    function board() {
      var size = Math.min(env.W - 44, env.H - env.safeTop - 130);
      return { x: (env.W - size) / 2, y: env.safeTop + 50 + Math.max(0, (env.H - env.safeTop - 130 - size) / 2), size: size, cell: (size - GAP * 5) / 4 };
    }
    function cellX(b, i) { return b.x + GAP + (i % 4) * (b.cell + GAP); }
    function cellY(b, i) { return b.y + GAP + Math.floor(i / 4) * (b.cell + GAP); }

    /* همان قانون حرکت core، فقط برای پیدا کردن مبدأ و مقصد هر کاشی (نمایشی) */
    function plan(grid, dir) {
      var moves = [], result = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], moved = false;
      for (var line = 0; line < 4; line++) {
        var items = [], k;
        for (k = 0; k < 4; k++) {
          var idx = core.cellIndex(dir, line, k);
          if (grid[idx]) items.push({ v: grid[idx], from: idx });
        }
        var pos = 0;
        for (k = 0; k < items.length; k++) {
          var dest = core.cellIndex(dir, line, pos++);
          moves.push({ v: items[k].v, from: items[k].from, to: dest });
          if (k + 1 < items.length && items[k].v === items[k + 1].v) {
            moves.push({ v: items[k + 1].v, from: items[k + 1].from, to: dest });
            result[dest] = items[k].v * 2;
            k++;
          } else {
            result[dest] = items[k].v;
          }
        }
      }
      for (var i = 0; i < moves.length; i++) if (moves[i].from !== moves[i].to) moved = true;
      return { moves: moves, result: result, moved: moved };
    }
    function findPlan(before, state) {
      for (var dir = 0; dir < 4; dir++) {
        var p = plan(before, dir);
        if (!p.moved) continue;
        var same = true;
        for (var i = 0; i < 16 && same; i++) if (i !== state.spawned && p.result[i] !== state.grid[i]) same = false;
        if (same) return p;
      }
      return null;
    }

    // ---------------------------------------------------------------- اسپرایت‌ها
    function paintScene(c, w, h, b) {
      // میز ماهوتی
      var g = c.createRadialGradient(w / 2, h * 0.45, 30, w / 2, h * 0.5, h * 0.8);
      g.addColorStop(0, "#1f6f5c");
      g.addColorStop(1, "#0c3a31");
      c.fillStyle = g;
      c.fillRect(-b, -b, w + b * 2, h + b * 2);
      art.grain(c, -b, -b, w + b * 2, h + b * 2, 0.5);
      var bd = board();
      art.shadow(c, bd.x + bd.size / 2 + 5, bd.y + bd.size / 2 + 14, bd.size * 0.66, bd.size * 0.64, 0.6);
      art.vignette(c, w, h, 0.6);
    }

    function paintBoard(size, cell) {
      return function (c) {
        // قاب چوبی (کمی بیرون‌تر از خانه‌ها)
        var o = FRAME;
        c.save();
        art.rr(c, -o, -o, size + o * 2, size + o * 2, 24);
        c.clip();
        art.wood(c, -o, -o, size + o * 2, size + o * 2, { base: "#7b4b2a", seed: 31, horizontal: true, knots: 3 });
        var sheen = c.createLinearGradient(0, -o, 0, size + o);
        sheen.addColorStop(0, "rgba(255,235,200,.3)");
        sheen.addColorStop(0.06, "rgba(255,235,200,0)");
        sheen.addColorStop(0.93, "rgba(0,0,0,0)");
        sheen.addColorStop(1, "rgba(0,0,0,.42)");
        c.fillStyle = sheen;
        c.fillRect(-o, -o, size + o * 2, size + o * 2);
        c.restore();
        c.strokeStyle = "rgba(30,14,4,.7)";
        c.lineWidth = 1.5;
        art.rr(c, -o + 0.75, -o + 0.75, size + o * 2 - 1.5, size + o * 2 - 1.5, 24);
        c.stroke();
        // کف سینی
        var floor = c.createLinearGradient(0, 0, 0, size);
        floor.addColorStop(0, "#22140c");
        floor.addColorStop(1, "#3a2618");
        c.fillStyle = floor;
        art.rr(c, 1, 1, size - 2, size - 2, 16);
        c.fill();
        c.strokeStyle = "rgba(0,0,0,.55)";
        c.lineWidth = 2;
        c.stroke();
        // خانه‌های فرورفته
        for (var i = 0; i < 16; i++) {
          var x = GAP + (i % 4) * (cell + GAP), y = GAP + Math.floor(i / 4) * (cell + GAP);
          var slot = c.createLinearGradient(0, y, 0, y + cell);
          slot.addColorStop(0, "rgba(0,0,0,.5)");
          slot.addColorStop(0.18, "rgba(0,0,0,.26)");
          slot.addColorStop(1, "rgba(0,0,0,.2)");
          c.fillStyle = slot;
          art.rr(c, x, y, cell, cell, cell * 0.16);
          c.fill();
          c.strokeStyle = "rgba(255,220,180,.07)";
          c.lineWidth = 1;
          c.stroke();
        }
      };
    }

    function paintTile(v, s) {
      return function (c) {
        var col = TILES[v] || BIG;
        env.dropShadow(c, 3, 2.5, 0.45);
        art.bevel(c, 0, 0, s, s, s * 0.16, col[0], 1);
        env.dropShadow(c);
        // لعاب: برق مورب ملایم
        c.save();
        art.rr(c, 0, 0, s, s, s * 0.16);
        c.clip();
        var gloss = c.createLinearGradient(0, 0, s, s);
        gloss.addColorStop(0, "rgba(255,255,255,.3)");
        gloss.addColorStop(0.4, "rgba(255,255,255,0)");
        c.fillStyle = gloss;
        c.fillRect(0, 0, s, s);
        c.restore();
        var text = digits(v);
        var size = s * (text.length <= 2 ? 0.5 : text.length === 3 ? 0.4 : text.length === 4 ? 0.32 : 0.26);
        c.font = env.font(size, 900);
        c.textAlign = "center";
        c.textBaseline = "middle";
        // عدد برجسته: زیر نوشته‌ی روشن سایه‌ی تیره و زیر نوشته‌ی تیره لبه‌ی روشن
        var lightText = col[1].charAt(1) > "7";
        c.fillStyle = art.shade(col[0], lightText ? -0.45 : 0.6);
        c.fillText(text, s / 2, s / 2 + 2.6);
        c.fillStyle = col[1];
        c.fillText(text, s / 2, s / 2 + 1.4);
      };
    }

    function tile(c, b, v, x, y, scale) {
      var s = Math.round(b.cell * 10) / 10;
      var sp = env.sprite("g2048:tile:" + v, s, s, paintTile(v, s), 7);
      env.blitC(c, sp, x + b.cell / 2, y + b.cell / 2, 0, scale);
    }

    return {
      controls: "swipe",
      ownBackground: true,
      reset: function (state) {
        prev = state.grid.slice();
        anim = null;
        popAt = [];
        spawnIdx = -1;
      },
      input: function (kind, data) {
        if (kind !== "swipe") return null;
        return [DIRS[data.dir]];
      },
      hud: function (state) {
        if (!state) return "";
        var left = Math.max(0, Math.ceil(((core.LIMIT_TICKS - state.tick) * core.TICK_MS) / 1000));
        return "⏱ " + env.fa(Math.floor(left / 60)) + ":" + env.fa(String(left % 60).padStart(2, "0"));
      },
      event: function (name, state) {
        if (name === "move" || name === "merge") {
          var now = env.now();
          var found = prev ? findPlan(prev, state) : null;
          anim = found ? { moves: found.moves, start: now } : null;
          var after = now + (found ? SLIDE_MS : 0);
          popAt = [];
          for (var i = 0; i < state.merged.length; i++) popAt[state.merged[i]] = after;
          spawnIdx = state.spawned;
          spawnAt = after;
          prev = state.grid.slice();
          env.sound("tick");
        }
        if (name === "merge") {
          var b = board();
          for (var m = 0; m < state.merged.length; m++) {
            var idx = state.merged[m], v = state.grid[idx];
            if (v >= 128) {
              env.fx.burst(cellX(b, idx) + b.cell / 2, cellY(b, idx) + b.cell / 2, (TILES[v] || BIG)[0], 14, 3.5);
              env.fx.ring(cellX(b, idx) + b.cell / 2, cellY(b, idx) + b.cell / 2, "#fff6cf", b.cell * 0.4, b.cell * 0.9);
            }
          }
          env.haptic("light");
          env.sound("good");
        } else if (name === "fail") {
          env.fx.flash(env.colors.danger, 0.4);
          env.fx.shake(8);
          env.haptic("error");
          env.sound("bad");
        } else if (name === "timeup") {
          env.fx.flash(env.colors.accent, 0.3);
          env.haptic("success");
        }
      },
      draw: function (c, state) {
        var b = board(), now = env.now(), i;
        env.scene(c, "g2048", paintScene);
        env.blit(c, env.sprite("g2048:board", b.size, b.size, paintBoard(b.size, b.cell), FRAME + 2), b.x, b.y);

        var t = anim ? (now - anim.start) / SLIDE_MS : 1;
        if (t >= 1) anim = null;
        if (anim) {
          var e = 1 - (1 - t) * (1 - t); // حرکت با کند شدن در انتها
          for (i = 0; i < anim.moves.length; i++) {
            var mv = anim.moves[i];
            tile(c, b, mv.v, env.lerp(cellX(b, mv.from), cellX(b, mv.to), e), env.lerp(cellY(b, mv.from), cellY(b, mv.to), e), 1);
          }
        } else {
          for (i = 0; i < 16; i++) {
            var v = state.grid[i];
            if (!v) continue;
            var scale = 1;
            if (i === spawnIdx) {
              var s = (now - spawnAt) / SPAWN_MS;
              if (s < 0) continue;
              if (s < 1) scale = 0.3 + 0.7 * s;
            }
            if (popAt[i] !== undefined) {
              var p = (now - popAt[i]) / POP_MS;
              if (p >= 0 && p < 1) scale = 1 + Math.sin(p * Math.PI) * 0.16;
            }
            tile(c, b, v, cellX(b, i), cellY(b, i), scale);
          }
        }

        // نوار زمان
        var ratio = env.clamp(1 - state.tick / core.LIMIT_TICKS, 0, 1);
        var by = b.y + b.size + 20;
        c.fillStyle = "rgba(0,0,0,.45)";
        art.rr(c, b.x - 2, by - 2, b.size + 4, 14, 7);
        c.fill();
        c.fillStyle = ratio < 0.2 ? "#ff5c7a" : "#ffd257";
        art.rr(c, b.x, by, Math.max(10, b.size * ratio), 10, 5);
        c.fill();
        c.fillStyle = "rgba(255,255,255,.45)";
        c.fillRect(b.x + 4, by + 1.6, Math.max(2, b.size * ratio - 8), 1.8);
      },
    };
  });
})();
