/* «مار کلاسیک» — رندر و افکت‌ها: زمین چمن با قاب چوبی، مار لوله‌ای با حرکت نرم بین خانه‌ها و سیب براق. */
(function () {
  "use strict";
  Arcade.registerRenderer("snake", function (env) {
    var core = Arcade.cores.snake, art = env.art;
    var DIRS = { up: 0, right: 1, down: 2, left: 3 };
    var TAU = Math.PI * 2;
    // برای حرکت نرم: خانه‌ای که دم در گام قبل ترک کرده
    var lastHead = -1, lastTail = -1, lastLen = 0, prevTail = -1, stepped = false;
    var gulp = 0;
    var xs = [], ys = [];

    function board() {
      var top = env.safeTop + 10;
      var cell = Math.floor(Math.min((env.W - 24) / core.COLS, (env.H - top - 22) / core.ROWS));
      var w = cell * core.COLS, h = cell * core.ROWS;
      return { x: (env.W - w) / 2, y: top + Math.max(0, (env.H - top - 22 - h) / 2), cell: cell, w: w, h: h };
    }
    function cx(b, index) { return b.x + (index % core.COLS + 0.5) * b.cell; }
    function cy(b, index) { return b.y + (Math.floor(index / core.COLS) + 0.5) * b.cell; }

    // ---------------------------------------------------------------- اسپرایت‌ها
    function paintScene(c, w, h, bleed) {
      var b = board();
      // بیرون زمین: پرچین تیره
      var g = c.createLinearGradient(0, -bleed, 0, h + bleed);
      g.addColorStop(0, "#143522");
      g.addColorStop(1, "#0b2016");
      c.fillStyle = g;
      c.fillRect(-bleed, -bleed, w + bleed * 2, h + bleed * 2);
      art.grass(c, -bleed, -bleed, w + bleed * 2, h + bleed * 2, { base: "#17402a", seed: 5, density: 60 });
      // قاب چوبی
      var f = 7;
      art.shadow(c, b.x + b.w / 2 + 3, b.y + b.h / 2 + 8, b.w * 0.6, b.h * 0.56, 0.6);
      c.save();
      art.rr(c, b.x - f, b.y - f, b.w + f * 2, b.h + f * 2, 10);
      c.clip();
      art.wood(c, b.x - f, b.y - f, b.w + f * 2, b.h + f * 2, { base: "#8a5a32", seed: 12, knots: 4 });
      c.restore();
      c.strokeStyle = "rgba(30,15,5,.75)";
      c.lineWidth = 1.5;
      art.rr(c, b.x - f, b.y - f, b.w + f * 2, b.h + f * 2, 10);
      c.stroke();
      c.strokeStyle = "rgba(255,225,180,.3)";
      c.lineWidth = 1;
      art.rr(c, b.x - f + 1.5, b.y - f + 1.5, b.w + f * 2 - 3, b.h + f * 2 - 3, 9);
      c.stroke();
      // چمن شطرنجی
      c.save();
      c.beginPath();
      c.rect(b.x, b.y, b.w, b.h);
      c.clip();
      art.grass(c, b.x, b.y, b.w, b.h, { base: "#63b548", seed: 9, density: 34 });
      c.fillStyle = "rgba(20,70,20,.13)";
      for (var gy = 0; gy < core.ROWS; gy++) {
        for (var gx = gy % 2; gx < core.COLS; gx += 2) c.fillRect(b.x + gx * b.cell, b.y + gy * b.cell, b.cell, b.cell);
      }
      // سایه‌ی لبه‌ی قاب روی چمن
      var inner = c.createLinearGradient(0, b.y, 0, b.y + 14);
      inner.addColorStop(0, "rgba(0,0,0,.35)");
      inner.addColorStop(1, "rgba(0,0,0,0)");
      c.fillStyle = inner;
      c.fillRect(b.x, b.y, b.w, 14);
      var side = c.createLinearGradient(b.x, 0, b.x + 10, 0);
      side.addColorStop(0, "rgba(0,0,0,.28)");
      side.addColorStop(1, "rgba(0,0,0,0)");
      c.fillStyle = side;
      c.fillRect(b.x, b.y, 10, b.h);
      c.restore();
      art.vignette(c, w, h, 0.4);
    }

    function paintApple(r) {
      return function (c) {
        var m = r * 1.2;
        art.shadow(c, m + r * 0.15, m + r * 0.85, r * 0.95, r * 0.35, 0.55);
        art.sphere(c, m, m, r, "#e5383b");
        // فرورفتگی بالای سیب، دم و برگ
        c.fillStyle = "rgba(90,10,10,.5)";
        c.beginPath();
        c.ellipse(m, m - r * 0.78, r * 0.3, r * 0.12, 0, 0, TAU);
        c.fill();
        c.strokeStyle = "#5a3414";
        c.lineWidth = Math.max(1.2, r * 0.16);
        c.lineCap = "round";
        c.beginPath();
        c.moveTo(m, m - r * 0.78);
        c.quadraticCurveTo(m + r * 0.1, m - r * 1.1, m + r * 0.3, m - r * 1.18);
        c.stroke();
        c.fillStyle = "#4caf50";
        c.beginPath();
        c.ellipse(m + r * 0.62, m - r * 0.98, r * 0.42, r * 0.2, -0.5, 0, TAU);
        c.fill();
        c.strokeStyle = "rgba(20,80,20,.6)";
        c.lineWidth = 0.8;
        c.beginPath();
        c.moveTo(m + r * 0.28, m - r * 0.84);
        c.lineTo(m + r * 0.94, m - r * 1.12);
        c.stroke();
      };
    }

    /* سر مار رو به راست؛ dead چشم‌های ضربدری می‌کشد */
    function paintHead(s, dead) {
      return function (c) {
        var m = s; // مرکز
        var g = c.createRadialGradient(m - s * 0.15, m - s * 0.2, s * 0.05, m, m, s * 0.75);
        g.addColorStop(0, "#7ddc6b");
        g.addColorStop(0.6, "#3aa655");
        g.addColorStop(1, "#1d6a37");
        c.fillStyle = g;
        c.beginPath();
        c.ellipse(m + s * 0.08, m, s * 0.66, s * 0.52, 0, 0, TAU);
        c.fill();
        c.strokeStyle = "rgba(15,60,30,.7)";
        c.lineWidth = 1;
        c.stroke();
        for (var side = -1; side <= 1; side += 2) {
          var ex = m + s * 0.2, ey = m + side * s * 0.27;
          if (dead) {
            c.strokeStyle = "#102a18";
            c.lineWidth = Math.max(1.5, s * 0.1);
            c.lineCap = "round";
            c.beginPath();
            c.moveTo(ex - s * 0.11, ey - s * 0.11);
            c.lineTo(ex + s * 0.11, ey + s * 0.11);
            c.moveTo(ex + s * 0.11, ey - s * 0.11);
            c.lineTo(ex - s * 0.11, ey + s * 0.11);
            c.stroke();
          } else {
            c.fillStyle = "#ffffff";
            c.beginPath();
            c.arc(ex, ey, s * 0.17, 0, TAU);
            c.fill();
            c.fillStyle = "#12241a";
            c.beginPath();
            c.arc(ex + s * 0.05, ey, s * 0.095, 0, TAU);
            c.fill();
            c.fillStyle = "#ffffff";
            c.beginPath();
            c.arc(ex + s * 0.02, ey - s * 0.04, s * 0.035, 0, TAU);
            c.fill();
          }
          c.fillStyle = "rgba(15,60,30,.7)";
          c.beginPath();
          c.arc(m + s * 0.6, m + side * s * 0.1, s * 0.03, 0, TAU);
          c.fill();
        }
      };
    }

    function trace(c, from, to) {
      c.beginPath();
      c.moveTo(xs[from], ys[from]);
      for (var i = from + 1; i <= to; i++) c.lineTo(xs[i], ys[i]);
    }

    return {
      controls: "swipe",
      ownBackground: true,
      reset: function () {
        lastHead = lastTail = prevTail = -1;
        lastLen = 0;
        stepped = false;
        gulp = 0;
      },
      input: function (kind, data) {
        if (kind !== "swipe") return null;
        return [DIRS[data.dir]];
      },
      hud: function (state) {
        return state ? "طول " + env.fa(state.body.length) : "";
      },
      event: function (name, state) {
        var b = board();
        var head = state.body[state.body.length - 1];
        var hx = cx(b, head), hy = cy(b, head);
        if (name === "eat") {
          gulp = 1;
          env.fx.burst(hx, hy, "#ff6b6b", 12, 3);
          env.fx.debris(hx, hy, "#e5383b", 5, 2.5, 2.5);
          env.fx.text(hx, hy - 12, "+۱۰", env.colors.gold);
          env.haptic("light");
          env.sound("good");
        } else if (name === "fail") {
          env.fx.flash(env.colors.danger, 0.5);
          env.fx.shake(10);
          env.fx.burst(hx, hy, "#b6f09a", 22, 4.5);
          env.haptic("error");
          env.sound("bad");
        }
      },
      draw: function (c, state, alpha) {
        var b = board(), cell = b.cell, i;
        var body = state.body, n = body.length;
        env.scene(c, "snake", paintScene);
        gulp *= 0.88;

        // تشخیص گام تازه برای درون‌یابی دم
        var head = body[n - 1];
        if (head !== lastHead || n !== lastLen) {
          if (lastHead >= 0) {
            stepped = true;
            prevTail = n > lastLen ? body[0] : lastTail;
          }
          lastHead = head;
          lastTail = body[0];
          lastLen = n;
        }
        var p = state.over || !stepped ? 1 : env.clamp((state.counter + alpha) / core.stepEvery(state.foods), 0, 1);

        // سیب
        if (state.food >= 0) {
          var ar = cell * 0.4;
          var bob = Math.sin(env.now() / 300) * 1.2;
          env.blit(c, env.sprite("snake:apple", ar * 2.4, ar * 2.4, paintApple(ar), 3), cx(b, state.food) - ar * 1.2, cy(b, state.food) - ar * 1.2 - bob);
        }

        // مسیر بدن: دم (در حال رسیدن به خانه‌ی خودش) ← خانه‌ها ← سر (در حال رسیدن به خانه‌ی تازه)
        var count = 0;
        if (n >= 2) {
          var tailFrom = prevTail >= 0 ? prevTail : body[0];
          xs[0] = env.lerp(cx(b, tailFrom), cx(b, body[0]), p);
          ys[0] = env.lerp(cy(b, tailFrom), cy(b, body[0]), p);
          count = 1;
          for (i = p >= 1 ? 1 : 0; i < n - 1; i++) {
            xs[count] = cx(b, body[i]);
            ys[count] = cy(b, body[i]);
            count++;
          }
          xs[count] = env.lerp(cx(b, body[n - 2]), cx(b, head), p);
          ys[count] = env.lerp(cy(b, body[n - 2]), cy(b, head), p);
          count++;
        } else {
          xs[0] = cx(b, head);
          ys[0] = cy(b, head);
          count = 1;
        }
        var last = count - 1;
        var hx = xs[last], hy = ys[last];

        c.lineJoin = "round";
        c.lineCap = "round";
        if (count >= 2) {
          // سایه روی چمن
          c.save();
          c.translate(2.5, 4);
          c.strokeStyle = "rgba(0,30,0,.28)";
          c.lineWidth = cell * 0.78;
          trace(c, 0, last);
          c.stroke();
          c.restore();
          // بدن: خط دور تیره، رنگ اصلی و نوار روشن پشت
          var dead = state.over && state.cause !== "win";
          c.strokeStyle = dead ? "#3d5a48" : "#1d6a37";
          c.lineWidth = cell * 0.8;
          trace(c, 0, last);
          c.stroke();
          c.strokeStyle = dead ? "#6f8f7c" : "#3aa655";
          c.lineWidth = cell * 0.62;
          c.stroke();
          c.strokeStyle = dead ? "rgba(200,220,205,.4)" : "rgba(170,240,130,.55)";
          c.lineWidth = cell * 0.2;
          c.save();
          c.translate(-cell * 0.08, -cell * 0.1);
          c.stroke();
          c.restore();
          // خال‌های پشت مار
          c.fillStyle = dead ? "rgba(40,60,48,.5)" : "rgba(255,214,90,.75)";
          c.beginPath();
          for (i = 1; i < last; i++) {
            c.moveTo(xs[i] + cell * 0.11, ys[i]);
            c.arc(xs[i], ys[i], cell * 0.11, 0, TAU);
          }
          c.fill();
        }

        // سر (رو به جهت حرکت) و زبان
        var angle = n >= 2 ? Math.atan2(cy(b, head) - cy(b, body[n - 2]), cx(b, head) - cx(b, body[n - 2])) : 0;
        var hs = cell * (0.86 + gulp * 0.12);
        if (!state.over && Math.sin(env.now() / 130) > 0.55) {
          c.save();
          c.translate(hx, hy);
          c.rotate(angle);
          c.strokeStyle = "#e5383b";
          c.lineWidth = Math.max(1.2, cell * 0.07);
          c.beginPath();
          c.moveTo(hs * 0.6, 0);
          c.lineTo(hs * 0.95, 0);
          c.lineTo(hs * 1.12, -hs * 0.12);
          c.moveTo(hs * 0.95, 0);
          c.lineTo(hs * 1.12, hs * 0.12);
          c.stroke();
          c.restore();
        }
        var deadHead = state.over && state.cause !== "win";
        env.blitC(c, env.sprite(deadHead ? "snake:dead" : "snake:head", cell * 2, cell * 2, paintHead(cell, deadHead), 2), hx, hy, angle, 0.86 + gulp * 0.12);
      },
    };
  });
})();
