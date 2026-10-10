/* ثبت core و renderer هر بازی. برای اضافه کردن بازی جدید کافی است پوشه‌ی
   static/arcade/<key>/ با core.js و render.js و معادل پایتونی arcade/sim/<key>.py ساخته شود. */
(function (root) {
  "use strict";
  root.Arcade = root.Arcade || {
    cores: {},
    renderers: {},
    registerCore: function (key, core) {
      this.cores[key] = core;
    },
    registerRenderer: function (key, factory) {
      this.renderers[key] = factory;
    },
  };
})(typeof self !== "undefined" ? self : this);
