/**
 * سحب اليد (grab) للتمرير الأفقي في جداول المسير وداخل نافذة المعاينة.
 * مفوَّض على document حتى يعمل مع المحتوى المنقول (x-teleport) وHTMX.
 * النطاق محدود بالحاويات المذكورة فقط كي لا يتعارض مع تحديد النص في بقية النظام.
 */
(function () {
    'use strict';
    if (window.__hrDragScroll) return;
    window.__hrDragScroll = true;

    var SELECTOR = [
        '.hr-payroll-runs-datatable__viewport',
        '.hr-payroll-page .overflow-x-auto',
        '.payroll-lines-card .overflow-x-auto',
        '.hr-glass-modal--payroll-run .overflow-x-auto'
    ].join(',');
    var SKIP = 'a, button, input, select, textarea, label, summary, [data-no-drag]';
    var THRESHOLD = 5;

    var drag = null;

    function scrollerFor(target) {
        if (!target || !target.closest) return null;
        var el = target.closest(SELECTOR);
        return el && el.scrollWidth > el.clientWidth + 1 ? el : null;
    }

    document.addEventListener('mouseover', function (e) {
        var el = e.target && e.target.closest ? e.target.closest(SELECTOR) : null;
        if (el) el.classList.toggle('hr-drag-scroll', el.scrollWidth > el.clientWidth + 1);
    });

    document.addEventListener('pointerdown', function (e) {
        if (e.pointerType !== 'mouse' || e.button !== 0) return;
        if (e.target.closest && e.target.closest(SKIP)) return;
        var el = scrollerFor(e.target);
        if (!el) return;
        drag = { el: el, x: e.clientX, left: el.scrollLeft, moved: false };
    });

    document.addEventListener('pointermove', function (e) {
        if (!drag) return;
        var dx = e.clientX - drag.x;
        if (!drag.moved && Math.abs(dx) < THRESHOLD) return;
        if (!drag.moved) {
            drag.moved = true;
            drag.el.classList.add('is-dragging');
        }
        drag.el.scrollLeft = drag.left - dx;
        e.preventDefault();
    }, { passive: false });

    function stop() {
        if (!drag) return;
        var moved = drag.moved;
        drag.el.classList.remove('is-dragging');
        drag = null;
        if (moved) {
            // منع نقرة عرضية على رابط/زر بعد انتهاء السحب
            var block = function (ev) { ev.stopPropagation(); ev.preventDefault(); };
            document.addEventListener('click', block, { capture: true, once: true });
            window.setTimeout(function () { document.removeEventListener('click', block, true); }, 0);
        }
    }
    document.addEventListener('pointerup', stop);
    document.addEventListener('pointercancel', stop);
    document.addEventListener('dragstart', function (e) { if (drag) e.preventDefault(); });
})();
