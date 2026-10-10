/* mulberry32 — دقیقاً معادل arcade/sim/rng.py. همه‌ی خروجی‌ها عدد صحیح‌اند تا
   نتیجه در JS و Python بیت‌به‌بیت یکی باشد. */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.ArcadeRng = factory();
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  function Rng(seed) {
    this.a = seed >>> 0;
  }
  Rng.prototype.nextU32 = function () {
    this.a = (this.a + 0x6d2b79f5) >>> 0;
    var a = this.a;
    var t = Math.imul(a ^ (a >>> 15), 1 | a) >>> 0;
    t = (((t + Math.imul(t ^ (t >>> 7), 61 | t)) >>> 0) ^ t) >>> 0;
    return (t ^ (t >>> 14)) >>> 0;
  };
  /** عدد صحیح در [0, n) */
  Rng.prototype.int = function (n) {
    return this.nextU32() % n;
  };
  /** عدد صحیح در بازه‌ی بسته‌ی [lo, hi] */
  Rng.prototype.range = function (lo, hi) {
    return lo + (this.nextU32() % (hi - lo + 1));
  };
  Rng.prototype.chance = function (percent) {
    return this.nextU32() % 100 < percent;
  };

  /** تقسیم صحیح رو به پایین، مثل // در پایتون */
  function idiv(a, b) {
    return Math.floor(a / b);
  }
  /** باقیمانده‌ی همیشه نامنفی، مثل % در پایتون (برای b مثبت) */
  function mod(a, b) {
    return ((a % b) + b) % b;
  }

  return { Rng: Rng, idiv: idiv, mod: mod };
});
