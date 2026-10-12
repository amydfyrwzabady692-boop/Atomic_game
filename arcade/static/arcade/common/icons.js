/* نماد تصویری هر بازی برای منو و صفحه‌ی شروع: یک صحنه‌ی کوچک ۹۶×۹۶ که با همان جعبه‌ابزار گرافیکی
   بازی‌ها کشیده می‌شود (بدون فایل تصویر). اگر بازی‌ای نماد نداشته باشد، ایموجی‌اش نمایش داده می‌شود. */
(function (root) {
  "use strict";
  var TAU = Math.PI * 2;
  var S = 96;

  root.ArcadeIcons = function (env) {
    var art = env.art;

    function sky(c, top, bottom) {
      var g = c.createLinearGradient(0, 0, 0, S);
      g.addColorStop(0, top);
      g.addColorStop(1, bottom);
      c.fillStyle = g;
      c.fillRect(0, 0, S, S);
    }
    function slab(c, x, y, w, h, hue) {
      c.fillStyle = "hsl(" + hue + ",78%,76%)";
      c.beginPath();
      c.moveTo(x, y);
      c.lineTo(x + 6, y - 6);
      c.lineTo(x + w + 6, y - 6);
      c.lineTo(x + w, y);
      c.closePath();
      c.fill();
      c.fillStyle = "hsl(" + hue + ",62%,36%)";
      c.beginPath();
      c.moveTo(x + w, y);
      c.lineTo(x + w + 6, y - 6);
      c.lineTo(x + w + 6, y - 6 + h);
      c.lineTo(x + w, y + h);
      c.closePath();
      c.fill();
      var g = c.createLinearGradient(0, y, 0, y + h);
      g.addColorStop(0, "hsl(" + hue + ",80%,66%)");
      g.addColorStop(1, "hsl(" + hue + ",70%,46%)");
      c.fillStyle = g;
      c.fillRect(x, y, w, h);
    }
    function knife(c, x, y, angle) {
      c.save();
      c.translate(x, y);
      c.rotate(angle);
      var blade = c.createLinearGradient(-3, 0, 3, 0);
      blade.addColorStop(0, "#f4f7fb");
      blade.addColorStop(1, "#6b7482");
      c.fillStyle = blade;
      c.beginPath();
      c.moveTo(0, -20);
      c.quadraticCurveTo(3.4, -12, 3, -4);
      c.lineTo(-3, -4);
      c.quadraticCurveTo(-3.4, -12, 0, -20);
      c.fill();
      c.fillStyle = "#d9a441";
      c.fillRect(-5, -4, 10, 3);
      c.fillStyle = "#a8382c";
      art.rr(c, -3, -1, 6, 15, 2);
      c.fill();
      art.sphere(c, 0, 15, 3, "#d9a441");
      c.restore();
    }

    var painters = {
      pins: function (c) {
        art.wood(c, 0, 0, S, S, { base: "#3e2616", seed: 21, knots: 1 });
        art.shadow(c, 52, 48, 34, 34, 0.5);
        knife(c, 22, 70, 0.9);
        knife(c, 48, 82, 0);
        knife(c, 76, 66, -1.0);
        art.logSlice(c, 48, 42, 26, { seed: 3 });
        art.sphere(c, 48, 42, 7, "#d9a441", false);
      },
      stack: function (c) {
        sky(c, "#3f97ea", "#d7efff");
        art.cloud(c, 4, 8, 44, "#ffffff", "#a9bde0", 4);
        slab(c, 24, 70, 50, 14, 196);
        slab(c, 28, 56, 46, 14, 232);
        slab(c, 28, 42, 40, 14, 268);
        slab(c, 14, 24, 40, 14, 310);
      },
      flappy: function (c) {
        sky(c, "#2f6fc4", "#ffd9a8");
        art.cloud(c, 40, 10, 50, "#ffffff", "#a9c0e4", 3);
        var pipe = c.createLinearGradient(60, 0, 88, 0);
        pipe.addColorStop(0, "#1f6b33");
        pipe.addColorStop(0.3, "#a6efaa");
        pipe.addColorStop(1, "#145226");
        c.fillStyle = pipe;
        c.fillRect(62, 56, 24, 40);
        art.rr(c, 58, 50, 32, 10, 3);
        c.fill();
        c.fillStyle = "#e07b1a";
        c.beginPath();
        c.ellipse(20, 44, 9, 3.4, 0.3, 0, TAU);
        c.fill();
        art.sphere(c, 36, 42, 15, "#ffc633");
        c.fillStyle = "#fff";
        c.beginPath();
        c.arc(42, 37, 5, 0, TAU);
        c.fill();
        c.fillStyle = "#1b1f3a";
        c.beginPath();
        c.arc(43.6, 37.4, 2.3, 0, TAU);
        c.fill();
        c.fillStyle = "#ff6a3d";
        c.beginPath();
        c.moveTo(48, 41);
        c.lineTo(60, 44);
        c.lineTo(48, 49);
        c.closePath();
        c.fill();
      },
      colorswitch: function (c) {
        sky(c, "#1a1c2c", "#08090f");
        var colors = ["#2bc8f5", "#ffc233", "#ff4f93", "#3fdc94"];
        c.lineWidth = 9;
        for (var i = 0; i < 4; i++) {
          c.strokeStyle = colors[i];
          c.beginPath();
          c.arc(48, 46, 28, (i * Math.PI) / 2 + 0.4, ((i + 1) * Math.PI) / 2 + 0.4);
          c.stroke();
        }
        art.glow(c, 48, 46, 22, "#ffc233", 0.5);
        art.sphere(c, 48, 46, 9, "#ffc233");
      },
      g2048: function (c) {
        var g = c.createRadialGradient(48, 44, 6, 48, 48, 70);
        g.addColorStop(0, "#1f6f5c");
        g.addColorStop(1, "#0c3a31");
        c.fillStyle = g;
        c.fillRect(0, 0, S, S);
        c.save();
        art.rr(c, 12, 12, 72, 72, 12);
        c.clip();
        art.wood(c, 12, 12, 72, 72, { base: "#7b4b2a", seed: 31, horizontal: true, knots: 0 });
        c.restore();
        var tiles = [["#f3e9d8", "۲", "#6a5743"], ["#f5a95c", "۸", "#fffaf2"], ["#ee6c4c", "۳۲", "#fffaf2"], ["#f0c843", "۲۵۶", "#5c4410"]];
        for (var i = 0; i < 4; i++) {
          var x = 17 + (i % 2) * 32, y = 17 + Math.floor(i / 2) * 32;
          art.bevel(c, x, y, 30, 30, 6, tiles[i][0]);
          c.fillStyle = tiles[i][2];
          c.font = env.font(tiles[i][1].length > 2 ? 12 : 17, 900);
          c.textAlign = "center";
          c.textBaseline = "middle";
          c.fillText(tiles[i][1], x + 15, y + 16);
        }
      },
      timing: function (c) {
        sky(c, "#2c3442", "#11151c");
        var rim = c.createLinearGradient(10, 10, 86, 86);
        rim.addColorStop(0, "#f2f5fa");
        rim.addColorStop(0.5, "#6d778a");
        rim.addColorStop(1, "#c5ccd8");
        c.fillStyle = rim;
        c.beginPath();
        c.arc(48, 50, 38, 0, TAU);
        c.fill();
        c.fillStyle = "#141a28";
        c.beginPath();
        c.arc(48, 50, 33, 0, TAU);
        c.fill();
        c.lineCap = "butt";
        c.lineWidth = 8;
        c.strokeStyle = "#1f9d68";
        c.beginPath();
        c.arc(48, 50, 24, 4.0, 5.2);
        c.stroke();
        c.strokeStyle = "#ffd257";
        c.beginPath();
        c.arc(48, 50, 24, 4.45, 4.75);
        c.stroke();
        c.strokeStyle = "#ff3b4e";
        c.lineWidth = 3;
        c.lineCap = "round";
        c.beginPath();
        c.moveTo(48, 50);
        c.lineTo(66, 28);
        c.stroke();
        art.sphere(c, 48, 50, 4.5, "#c9d2e0");
      },
      timber: function (c) {
        sky(c, "#5fb1ee", "#fff3d6");
        art.grass(c, 0, 76, S, 20, { base: "#4b9a3f", seed: 14, density: 20 });
        art.wood(c, 50, 0, 30, 78, { base: "#8b5a33", seed: 61, round: true, knots: 1 });
        c.fillStyle = "#a8713f";
        c.fillRect(16, 26, 36, 7);
        art.leaves(c, 14, 30, 11, "#3aa655");
        art.leaves(c, 24, 22, 9, "#2f8f46");
        // تبر
        c.save();
        c.translate(34, 66);
        c.rotate(0.7);
        art.wood(c, -2.4, -34, 4.8, 40, { base: "#c79a63", seed: 5, knots: 0 });
        var blade = c.createLinearGradient(-18, 0, 2, 0);
        blade.addColorStop(0, "#f8fafc");
        blade.addColorStop(1, "#64748b");
        c.fillStyle = blade;
        c.beginPath();
        c.moveTo(3, -36);
        c.quadraticCurveTo(-18, -36, -17, -20);
        c.quadraticCurveTo(-8, -24, 3, -22);
        c.closePath();
        c.fill();
        c.restore();
      },
      runner: function (c) {
        sky(c, "#131f4e", "#ffc37a");
        var sun = c.createRadialGradient(48, 40, 2, 48, 40, 34);
        sun.addColorStop(0, "#fff8d6");
        sun.addColorStop(0.3, "#ffd27a");
        sun.addColorStop(1, "rgba(255,170,110,0)");
        c.fillStyle = sun;
        c.fillRect(0, 0, S, 60);
        c.fillStyle = "#3a4a3a";
        c.fillRect(0, 42, S, 54);
        c.fillStyle = "#3d3f49";
        c.beginPath();
        c.moveTo(44, 42);
        c.lineTo(52, 42);
        c.lineTo(S + 6, S);
        c.lineTo(-6, S);
        c.closePath();
        c.fill();
        c.fillStyle = "rgba(255,255,255,.85)";
        c.fillRect(47, 48, 2, 6);
        c.fillRect(46.5, 60, 3, 10);
        c.fillRect(46, 78, 4, 16);
        c.save();
        c.translate(52, 50);
        art.carRear(c, 40, 38, "#d8343f", "sedan");
        c.restore();
      },
      tiles: function (c) {
        for (var k = 0; k < 4; k++) {
          var g = c.createLinearGradient(k * 24, 0, k * 24 + 24, 0);
          g.addColorStop(0, "#e9e4d8");
          g.addColorStop(0.15, "#fbf8f0");
          g.addColorStop(1, "#d6cfbf");
          c.fillStyle = g;
          c.fillRect(k * 24, 0, 24, S);
          c.fillStyle = "rgba(40,30,20,.5)";
          c.fillRect(k * 24, 0, 1, S);
        }
        var cells = [[0, 4], [2, 34], [1, 64]];
        for (var i = 0; i < cells.length; i++) {
          var tile = c.createLinearGradient(cells[i][0] * 24, 0, cells[i][0] * 24 + 24, 0);
          tile.addColorStop(0, "#3a3a42");
          tile.addColorStop(1, "#08080a");
          c.fillStyle = tile;
          art.rr(c, cells[i][0] * 24 + 2, cells[i][1], 20, 28, 5);
          c.fill();
          c.fillStyle = "rgba(255,255,255,.22)";
          c.fillRect(cells[i][0] * 24 + 5, cells[i][1] + 3, 3, 22);
        }
        c.strokeStyle = "#ffd257";
        c.lineWidth = 2;
        art.rr(c, 26, 64, 20, 28, 5);
        c.stroke();
      },
      helix: function (c) {
        sky(c, "#2f6fd0", "#7fd3ff");
        var pillar = c.createLinearGradient(36, 0, 60, 0);
        pillar.addColorStop(0, "#9aa6bd");
        pillar.addColorStop(0.3, "#ffffff");
        pillar.addColorStop(1, "#77839c");
        c.fillStyle = pillar;
        c.fillRect(36, 0, 24, S);
        for (var i = 0; i < 2; i++) {
          var y = 40 + i * 34;
          c.fillStyle = "#a8872e";
          c.beginPath();
          c.ellipse(48, y + 6, 38, 12, 0, 0.1, Math.PI * (i ? 0.72 : 1) - 0.1);
          c.lineTo(48, y + 6);
          c.closePath();
          c.fill();
          c.fillStyle = "#ffd166";
          c.beginPath();
          c.ellipse(48, y, 38, 12, 0, 0, Math.PI * (i ? 0.72 : 1));
          c.ellipse(48, y, 12, 4, 0, Math.PI * (i ? 0.72 : 1), 0, true);
          c.closePath();
          c.fill();
          if (i === 0) {
            c.fillStyle = "#e63946";
            c.beginPath();
            c.ellipse(48, y, 38, 12, 0, 0.3, 0.9);
            c.ellipse(48, y, 12, 4, 0, 0.9, 0.3, true);
            c.closePath();
            c.fill();
          }
        }
        art.shadow(c, 50, 47, 8, 3, 0.4);
        art.sphere(c, 50, 30, 8, "#ff4d6d");
      },
      whack: function (c) {
        art.grass(c, 0, 0, S, S, { base: "#4f9e3e", seed: 21, density: 18 });
        c.fillStyle = "#7a4e28";
        c.beginPath();
        c.ellipse(48, 72, 36, 14, 0, 0, TAU);
        c.fill();
        c.fillStyle = "#120a05";
        c.beginPath();
        c.ellipse(48, 72, 27, 9, 0, 0, TAU);
        c.fill();
        // موش کور
        var body = c.createLinearGradient(26, 0, 70, 0);
        body.addColorStop(0, "#c08a52");
        body.addColorStop(0.45, "#8a5a33");
        body.addColorStop(1, "#4f3018");
        c.fillStyle = body;
        c.beginPath();
        c.moveTo(28, 74);
        c.lineTo(28, 40);
        c.arc(48, 40, 20, Math.PI, 0);
        c.lineTo(68, 74);
        c.closePath();
        c.fill();
        c.fillStyle = "#e9cfa6";
        c.beginPath();
        c.ellipse(48, 50, 10, 7.5, 0, 0, TAU);
        c.fill();
        art.sphere(c, 48, 46, 4, "#e2687c");
        c.fillStyle = "#fff";
        c.fillRect(45, 52, 2.6, 5);
        c.fillRect(48.4, 52, 2.6, 5);
        for (var side = -1; side <= 1; side += 2) {
          c.fillStyle = "#fff";
          c.beginPath();
          c.arc(48 + side * 8.5, 36, 4.6, 0, TAU);
          c.fill();
          c.fillStyle = "#1c120a";
          c.beginPath();
          c.arc(48 + side * 8.5, 36.6, 2.8, 0, TAU);
          c.fill();
        }
        c.fillStyle = "#7a4e28";
        c.beginPath();
        c.ellipse(48, 72, 36, 14, 0, 0.12, Math.PI - 0.12);
        c.ellipse(48, 72, 27, 9, 0, Math.PI - 0.12, 0.12, true);
        c.closePath();
        c.fill();
      },
      jumper: function (c) {
        sky(c, "#3a8fe4", "#cdeeff");
        art.cloud(c, 46, 8, 46, "#ffffff", "#c5d6f2", 11);
        art.cloud(c, 14, 62, 66, "#ffffff", "#9fb4e0", 4);
        var body = c.createRadialGradient(42, 36, 2, 48, 44, 22);
        body.addColorStop(0, "#e6dcff");
        body.addColorStop(0.45, "#a98bf7");
        body.addColorStop(1, "#5a2dc4");
        c.fillStyle = body;
        art.rr(c, 32, 26, 32, 38, 14);
        c.fill();
        c.fillStyle = "#fff";
        c.beginPath();
        c.arc(43, 42, 5.6, 0, TAU);
        c.arc(55, 42, 5.6, 0, TAU);
        c.fill();
        c.fillStyle = "#1b1f3a";
        c.beginPath();
        c.arc(44.6, 41, 2.7, 0, TAU);
        c.arc(56.6, 41, 2.7, 0, TAU);
        c.fill();
        c.strokeStyle = "#c4b5fd";
        c.lineWidth = 2.4;
        c.beginPath();
        c.moveTo(48, 26);
        c.quadraticCurveTo(43, 17, 46, 13);
        c.stroke();
        art.sphere(c, 46, 12, 3.6, "#ffc233");
      },
      snake: function (c) {
        art.grass(c, 0, 0, S, S, { base: "#63b548", seed: 9, density: 18 });
        c.lineCap = "round";
        c.lineJoin = "round";
        var path = function () {
          c.beginPath();
          c.moveTo(16, 72);
          c.lineTo(60, 72);
          c.lineTo(60, 48);
          c.lineTo(26, 48);
          c.lineTo(26, 26);
          c.lineTo(52, 26);
        };
        c.strokeStyle = "#1d6a37";
        c.lineWidth = 15;
        path();
        c.stroke();
        c.strokeStyle = "#3aa655";
        c.lineWidth = 11;
        path();
        c.stroke();
        c.fillStyle = "rgba(255,214,90,.8)";
        var dots = [[30, 72], [46, 72], [60, 60], [44, 48], [26, 38], [38, 26]];
        for (var i = 0; i < dots.length; i++) {
          c.beginPath();
          c.arc(dots[i][0], dots[i][1], 2.2, 0, TAU);
          c.fill();
        }
        art.sphere(c, 56, 26, 9.5, "#49b862", false);
        c.fillStyle = "#fff";
        c.beginPath();
        c.arc(59, 21.5, 3.2, 0, TAU);
        c.arc(59, 30.5, 3.2, 0, TAU);
        c.fill();
        c.fillStyle = "#12241a";
        c.beginPath();
        c.arc(60, 21.5, 1.7, 0, TAU);
        c.arc(60, 30.5, 1.7, 0, TAU);
        c.fill();
        art.sphere(c, 80, 60, 9, "#e5383b");
        c.fillStyle = "#4caf50";
        c.beginPath();
        c.ellipse(85, 50, 5, 2.4, -0.5, 0, TAU);
        c.fill();
      },
      breakout: function (c) {
        sky(c, "#27334d", "#0b0f1a");
        var colors = ["#ff5d73", "#ff9f43", "#ffd257", "#5ee6a8", "#38d9ff"];
        for (var row = 0; row < 3; row++) {
          for (var col = 0; col < 4; col++) {
            if (row === 2 && col === 1) continue;
            art.bevel(c, 6 + col * 21.5, 10 + row * 13, 19, 10.5, 3, colors[(row + col) % colors.length]);
          }
        }
        art.glow(c, 52, 60, 14, "#bfe9ff", 0.6);
        art.sphere(c, 52, 60, 5.5, "#dfe7f2");
        var paddle = c.createLinearGradient(0, 78, 0, 88);
        paddle.addColorStop(0, "#f4f7fb");
        paddle.addColorStop(1, "#3c4352");
        c.fillStyle = paddle;
        art.rr(c, 24, 78, 48, 10, 5);
        c.fill();
        c.fillStyle = "#d7263d";
        art.rr(c, 24, 78, 8, 10, 4);
        c.fill();
        art.rr(c, 64, 78, 8, 10, 4);
        c.fill();
        c.fillStyle = "#7fe3ff";
        c.fillRect(36, 82, 24, 2.4);
      },
    };

    return {
      has: function (key) { return !!painters[key]; },
      /* یک <canvas> آماده برای قرار گرفتن در صفحه برمی‌گرداند (px = اندازه‌ی نمایش) */
      element: function (key, px) {
        var painter = painters[key];
        if (!painter) return null;
        var ratio = Math.min(window.devicePixelRatio || 1, 2);
        var canvas = document.createElement("canvas");
        canvas.width = canvas.height = Math.round(px * ratio);
        canvas.style.width = canvas.style.height = px + "px";
        canvas.className = "game-icon";
        var c = canvas.getContext("2d");
        var k = (px * ratio) / S;
        c.scale(k, k);
        c.save();
        art.rr(c, 0, 0, S, S, 22);
        c.clip();
        painter(c);
        // برق بالای کاشی
        var gloss = c.createLinearGradient(0, 0, 0, S * 0.5);
        gloss.addColorStop(0, "rgba(255,255,255,.22)");
        gloss.addColorStop(1, "rgba(255,255,255,0)");
        c.fillStyle = gloss;
        c.fillRect(0, 0, S, S * 0.5);
        c.restore();
        c.strokeStyle = "rgba(255,255,255,.28)";
        c.lineWidth = 1.5;
        art.rr(c, 0.75, 0.75, S - 1.5, S - 1.5, 22);
        c.stroke();
        return canvas;
      },
    };
  };
})(typeof self !== "undefined" ? self : this);
