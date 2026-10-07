/**
 * شريط التبويبات (صف واحد قابل للتمرير): يُظهر التبويب النشط في منتصف الشريط
 * عند فتح الصفحة وعند التبديل بين التبويبات.
 */
(function () {
    'use strict';

    var BAR = '.hr-page-tabs__bar, .hr-tabs__bar';
    var ACTIVE = '.hr-tab-btn.is-active, .hr-tab-btn.hr-tab--active, .hr-tab-btn[aria-selected="true"]';

    function centerActive(bar) {
        var tab = bar.querySelector(ACTIVE);
        if (!tab || bar.scrollWidth <= bar.clientWidth) return;
        var target = tab.offsetLeft - (bar.clientWidth - tab.offsetWidth) / 2;
        bar.scrollTo({ left: target, behavior: 'auto' });
    }

    function centerAll() {
        document.querySelectorAll(BAR).forEach(centerActive);
    }

    document.addEventListener('DOMContentLoaded', centerAll);
    window.addEventListener('load', centerAll);

    // بعد الضغط على تبويب (Alpine يبدّل الصنف بعد الحدث مباشرة)
    document.addEventListener('click', function (e) {
        var tab = e.target.closest && e.target.closest('.hr-tab-btn');
        if (!tab) return;
        var bar = tab.closest(BAR);
        if (!bar) return;
        setTimeout(function () {
            var active = bar.querySelector(ACTIVE) || tab;
            if (bar.scrollWidth <= bar.clientWidth) return;
            var left = active.offsetLeft - (bar.clientWidth - active.offsetWidth) / 2;
            bar.scrollTo({ left: left, behavior: 'smooth' });
        }, 30);
    });
})();
