/* «آجرشکن» — رندر و افکت‌ها: آجرهای براق سه‌بعدی (آجرهای مقاوم روکش برنز و فولاد دارند)، راکت فلزی
   و توپ کروم. موقعیت راکت حداکثر ۳۰ بار در ثانیه به‌عنوان ورودی ثبت می‌شود.

   دیوار آجرها در یک لایه‌ی جدا نگه داشته می‌شود و فقط وقتی آجری ضربه بخورد دوباره کشیده می‌شود. */
(function () {
  "use strict";
  Arcade.registerRenderer("breakout", function (env) {
    var core = Arcade.cores.breakout, art = env.art;
    var TAU = Math.PI * 2;
    var ROW_COLORS = ["#ff5d73", "#ff9f43", "#ffd257", "#5ee6a8", "#38d9ff", "#6c8cff", "#b388ff", "#ff7ac8"];
    var BRONZE = "#c98a4b", STEEL = "#9aa7ba";
    var ITEM_COLORS = ["#3fdc94", "#ff5d8f", "#ffd257"];
    var ITEM_ICONS = ["↔", "♥", "★"];
    var targetX = null, sentX = null;
    var trail = [];
    var wall = null; // { canvas, ctx, res, w, h }
    var wallDirty = true, bricksRef = null;
    var paddleHit = 0;
    var WALL_PAD = 60; // حاشیه‌ی لایه‌ی دیوار (واحد core) برای سایه‌ی آجرها

    function layout() {
      var scale = Math.min(env.W / core.WIDTH, env.H / core.HEIGHT);
      return { s: scale, ox: (env.W - core.WIDTH * scale) / 2, oy: (env.H - core.HEIGHT * scale) / 2 };
    }
    function brickColor(index, hp) {
      return hp >= 3 ? STEEL : hp === 2 ? BRONZE : ROW_COLORS[Math.floor(index / core.COLS) % ROW_COLORS.length];
    }

    // ---------------------------------------------------------------- اسپرایت‌ها
    function paintScene(c, w, h, b) {
      var l = layout(), fw = core.WIDTH * l.s, fh = core.HEIGHT * l.s;
      var g = c.createLinearGradient(0, -b, 0, h + b);
      g.addColorStop(0, "#10141f");
      g.addColorStop(1, "#06080d");
      c.fillStyle = g;
      c.fillRect(-b, -b, w + b * 2, h + b * 2);
      // کف زمین بازی با شبکه‌ی کم‌رنگ
      var floor = c.createRadialGradient(l.ox + fw / 2, l.oy + fh * 0.4, 20, l.ox + fw / 2, l.oy + fh * 0.5, fh * 0.7);
      floor.addColorStop(0, "#27334d");
      floor.addColorStop(1, "#121827");
      c.fillStyle = floor;
      c.fillRect(l.ox - b, l.oy, fw + b * 2, fh);
      c.fillStyle = "rgba(255,255,255,.035)";
      for (var gx = l.ox; gx <= l.ox + fw; gx += 22.5) c.fillRect(gx, l.oy, 1, fh);
      for (var gy = l.oy; gy <= l.oy + fh; gy += 22.5) c.fillRect(l.ox - b, gy, fw + b * 2, 1);
      art.grain(c, -b, -b, w + b * 2, h + b * 2, 0.14);
      // تیرک فلزی بالا
      art.metal(c, l.ox - b, l.oy - 9, fw + b * 2, 9, { base: "#8793a8" });
      c.fillStyle = "rgba(0,0,0,.5)";
      c.fillRect(l.ox - b, l.oy, fw + b * 2, 5);
      // سایه‌ی دیواره‌های کناری
      var left = c.createLinearGradient(l.ox, 0, l.ox + 14, 0);
      left.addColorStop(0, "rgba(0,0,0,.5)");
      left.addColorStop(1, "rgba(0,0,0,0)");
      c.fillStyle = left;
      c.fillRect(l.ox, l.oy, 14, fh);
      var right = c.createLinearGradient(l.ox + fw, 0, l.ox + fw - 14, 0);
      right.addColorStop(0, "rgba(0,0,0,.5)");
      right.addColorStop(1, "rgba(0,0,0,0)");
      c.fillStyle = right;
      c.fillRect(l.ox + fw - 14, l.oy, 14, fh);
      // خط خطر پایین زمین
      var danger = c.createLinearGradient(0, l.oy + fh - 46, 0, l.oy + fh);
      danger.addColorStop(0, "rgba(255,60,90,0)");
      danger.addColorStop(1, "rgba(255,60,90,.32)");
      c.fillStyle = danger;
      c.fillRect(l.ox - b, l.oy + fh - 46, fw + b * 2, 46);
      c.fillStyle = "#ff3c5a";
      c.fillRect(l.ox - b, l.oy + fh - 1.5, fw + b * 2, 1.5);
      art.vignette(c, w, h, 0.45);
    }

    function paintBrick(color, hp, w, h) {
      return function (c) {
        env.dropShadow(c, 2, 1.5, 0.5);
        art.bevel(c, 0, 0, w, h, 4, color, 1);
        env.dropShadow(c);
        if (hp >= 2) {
          // روکش فلزی با پرچ
          c.strokeStyle = art.shade(color, -0.45);
          c.lineWidth = 1;
          art.rr(c, 3, 3, w - 6, h - 6, 2.5);
          c.stroke();
          c.strokeStyle = "rgba(255,255,255,.35)";
          art.rr(c, 4, 4, w - 8, h - 8, 2);
          c.stroke();
          var rivets = [[5.5, 5.5], [w - 5.5, 5.5], [5.5, h - 5.5], [w - 5.5, h - 5.5]];
          for (var i = 0; i < rivets.length; i++) art.sphere(c, rivets[i][0], rivets[i][1], 1.5, art.shade(color, 0.25), false);
          if (hp >= 3) {
            c.fillStyle = "rgba(255,255,255,.3)";
            c.fillRect(w / 2 - 6, h / 2 - 1, 12, 2);
          }
        } else {
          // شیشه‌ی رنگی: برق مورب
          c.save();
          art.rr(c, 0, 0, w, h, 4);
          c.clip();
          c.fillStyle = "rgba(255,255,255,.22)";
          c.beginPath();
          c.moveTo(w * 0.12, 0);
          c.lineTo(w * 0.34, 0);
          c.lineTo(w * 0.2, h);
          c.lineTo(w * -0.02, h);
          c.closePath();
          c.fill();
          c.restore();
        }
      };
    }

    function paintPaddle(w, wide) {
      return function (c) {
        var h = 13;
        env.dropShadow(c, 4, 3, 0.55);
        var body = c.createLinearGradient(0, 0, 0, h);
        body.addColorStop(0, "#f4f7fb");
        body.addColorStop(0.35, "#aab4c6");
        body.addColorStop(0.6, "#6d778a");
        body.addColorStop(1, "#3c4352");
        c.fillStyle = body;
        art.rr(c, 0, 0, w, h, 6.5);
        c.fill();
        env.dropShadow(c);
        // سرهای لاستیکی
        var cap = wide ? "#1fa56b" : "#d7263d";
        c.save();
        art.rr(c, 0, 0, w, h, 6.5);
        c.clip();
        var rubber = c.createLinearGradient(0, 0, 0, h);
        rubber.addColorStop(0, art.shade(cap, 0.3));
        rubber.addColorStop(1, art.shade(cap, -0.4));
        c.fillStyle = rubber;
        c.fillRect(0, 0, 11, h);
        c.fillRect(w - 11, 0, 11, h);
        c.restore();
        // نوار انرژی وسط
        c.fillStyle = wide ? "#8dffcb" : "#7fe3ff";
        art.rr(c, 16, 4.5, w - 32, 3.2, 1.6);
        c.fill();
        c.fillStyle = "rgba(255,255,255,.7)";
        c.fillRect(8, 1.6, w - 16, 1);
      };
    }

    function paintBall(r) {
      return function (c) {
        env.dropShadow(c, 2, 1.5, 0.4);
        art.sphere(c, r, r, r, "#dfe7f2");
      };
    }

    function paintItem(type) {
      return function (c) {
        var w = 28, h = 15;
        env.dropShadow(c, 2.5, 2, 0.5);
        art.bevel(c, 0, 0, w, h, 7.5, ITEM_COLORS[type], 1);
        env.dropShadow(c);
        c.fillStyle = "rgba(10,14,30,.85)";
        c.font = env.font(11, 900);
        c.textAlign = "center";
        c.textBaseline = "middle";
        c.fillText(ITEM_ICONS[type], w / 2, h / 2 + 0.8);
      };
    }

    /* لایه‌ی دیوار آجرها: فقط بعد از ضربه یا مرحله‌ی تازه دوباره کشیده می‌شود */
    function wallLayer(state, l) {
      var bw = core.BRICK_W * l.s, bh = core.BRICK_H * l.s;
      var w = core.WIDTH * l.s, h = (core.ROWS * core.STEP_Y + WALL_PAD * 2) * l.s;
      if (!wall || wall.res !== env.res || wall.w !== w || wall.h !== h) {
        var cv = document.createElement("canvas");
        cv.width = Math.ceil(w * env.res);
        cv.height = Math.ceil(h * env.res);
        wall = { canvas: cv, ctx: cv.getContext("2d"), res: env.res, w: w, h: h };
        wallDirty = true;
      }
      if (state.bricks !== bricksRef) {
        bricksRef = state.bricks;
        wallDirty = true;
      }
      if (wallDirty) {
        wallDirty = false;
        var c = wall.ctx;
        c.setTransform(1, 0, 0, 1, 0, 0);
        c.clearRect(0, 0, wall.canvas.width, wall.canvas.height);
        c.setTransform(env.res, 0, 0, env.res, 0, 0);
        for (var i = 0; i < state.bricks.length; i++) {
          var hp = state.bricks[i];
          if (hp <= 0) continue;
          var color = brickColor(i, hp);
          var sp = env.sprite("breakout:brick:" + color, bw, bh, paintBrick(color, hp, bw, bh), 4);
          env.blit(c, sp, (core.LEFT + (i % core.COLS) * core.STEP_X) * l.s, (WALL_PAD + Math.floor(i / core.COLS) * core.STEP_Y) * l.s);
        }
      }
      return wall;
    }

    return {
      controls: "drag",
      ownBackground: true,
      reset: function () {
        targetX = sentX = null;
        trail = [];
        wallDirty = true;
        bricksRef = null;
      },
      input: function (kind, data) {
        if (kind === "tap" || kind === "drag") {
          var l = layout();
          targetX = Math.round((data.x - l.ox) / l.s);
        }
        return null;
      },
      sample: function (state) {
        if (targetX === null || state.tick % 2 !== 0) return null;
        var x = Math.max(0, Math.min(core.WIDTH, targetX));
        if (sentX !== null && Math.abs(x - sentX) < 8) return null;
        sentX = x;
        return [x];
      },
      hud: function (state) {
        if (!state) return "";
        return "مرحله " + env.fa(state.level + 1) + "   " + "❤️".repeat(Math.max(state.lives, 0));
      },
      event: function (name, state) {
        var l = layout();
        var bx = l.ox + state.bx * l.s, by = l.oy + state.by * l.s;
        if (name === "break" || name === "crack") {
          wallDirty = true;
          var index = state.lastHit;
          var x = l.ox + (core.LEFT + (index % core.COLS) * core.STEP_X + core.BRICK_W / 2) * l.s;
          var y = l.oy + (core.TOP + Math.floor(index / core.COLS) * core.STEP_Y + core.BRICK_H / 2) * l.s;
          if (name === "break") {
            var color = ROW_COLORS[Math.floor(index / core.COLS) % ROW_COLORS.length];
            env.fx.debris(x, y, color, 7, 3.4, 4);
            env.fx.burst(x, y, "#ffffff", 5, 2.4);
            env.haptic("light");
            env.sound("good");
          } else {
            env.fx.burst(x, y, "#ffe9b0", 6, 2.6);
            env.sound("tap");
          }
        } else if (name === "paddle") {
          paddleHit = 1;
          env.fx.burst(bx, by + core.BALL_R * l.s, "#7fe3ff", 5, 2);
          env.haptic("light");
          env.sound("tick");
        } else if (name === "wall") {
          env.sound("tick");
        } else if (name === "item") {
          env.fx.burst(bx, l.oy + core.PADDLE_Y * l.s, ITEM_COLORS[state.lastItem], 16, 4);
          env.fx.ring(l.ox + (state.px + core.paddleWidth(state) / 2) * l.s, l.oy + core.PADDLE_Y * l.s, ITEM_COLORS[state.lastItem], 10, 60);
          env.fx.text(env.W / 2, l.oy + core.PADDLE_Y * l.s - 24, ["راکت پهن!", "+۱ جان", "+۵۰"][state.lastItem], env.colors.good);
          env.haptic("medium");
          env.sound("bonus");
        } else if (name === "clear") {
          env.fx.burst(env.W / 2, env.H / 2, env.colors.good, 40, 7);
          env.fx.ring(env.W / 2, env.H / 2, "#ffffff", 30, 200);
          env.fx.flash(env.colors.good, 0.3);
          env.haptic("success");
          env.sound("clear");
        } else if (name === "lose") {
          env.fx.flash(env.colors.danger, 0.4);
          env.fx.shake(9);
          env.haptic("error");
          env.sound("bad");
        }
      },
      draw: function (c, state, alpha) {
        var l = layout(), s = l.s;
        env.scene(c, "breakout", paintScene);
        paddleHit *= 0.8;

        var layer = wallLayer(state, l);
        c.drawImage(layer.canvas, l.ox, l.oy + (core.TOP - WALL_PAD) * s, layer.w, layer.h);

        // آیتم‌های در حال سقوط
        for (var k = 0; k < state.items.length; k++) {
          var item = state.items[k];
          var ix = l.ox + item.x * s, iy = l.oy + item.y * s;
          art.glow(c, ix, iy, 22, ITEM_COLORS[item.type], 0.35);
          env.blitC(c, env.sprite("breakout:item:" + item.type, 28, 15, paintItem(item.type), 5), ix, iy, Math.sin(env.now() / 200 + k) * 0.18);
        }

        // راکت
        var wide = state.wide > 0;
        var w = core.paddleWidth(state) * s;
        var px = l.ox + state.px * s, py = l.oy + core.PADDLE_Y * s + paddleHit * 2.5;
        art.glow(c, px + w / 2, py + 8, w * 0.7, wide ? "#3fdc94" : "#38d9ff", 0.28);
        env.blit(c, env.sprite(wide ? "breakout:paddleWide" : "breakout:paddle", w, 13, paintPaddle(w, wide), 8), px, py);

        // توپ و ردش
        var moving = state.attach === 0 && state.pause === 0 && !state.over;
        var r = core.BALL_R * s;
        var bx = l.ox + (state.bx + (moving ? state.vx * alpha : 0)) * s;
        var by = l.oy + (state.by + (moving ? state.vy * alpha : 0)) * s;
        if (moving) trail.push(bx, by);
        else trail.length = 0;
        if (trail.length > 16) trail.splice(0, 2);
        c.fillStyle = "#bfe9ff";
        for (var t = 0; t < trail.length; t += 2) {
          var f = t / trail.length;
          c.globalAlpha = f * 0.3;
          c.beginPath();
          c.arc(trail[t], trail[t + 1], r * (0.35 + f * 0.6), 0, TAU);
          c.fill();
        }
        c.globalAlpha = 1;
        if (!(state.over && state.lives <= 0)) {
          art.glow(c, bx, by, r * 2.8, "#bfe9ff", 0.45);
          env.blitC(c, env.sprite("breakout:ball", r * 2, r * 2, paintBall(r), 4), bx, by);
        }
      },
    };
  });
})();
