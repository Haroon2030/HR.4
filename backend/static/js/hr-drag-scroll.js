/**
 * سحب اليد (grab) للتمرير الأفقي في كل جداول الموقع — الصفحات والنوافذ المنبثقة.
 *
 * يعمل تلقائياً على أي حاوية تمرير أفقي (overflow-x: auto/scroll) تحتوي جدولاً وتتجاوز عرضها.
 * مفوَّض على document فيعمل مع المحتوى المنقول (x-teleport) وHTMX دون تهيئة.
 * - الأزرار والروابط وحقول الإدخال تعمل كالمعتاد (لا يبدأ السحب منها).
 * - لتحديد نص داخل الجدول: اضغط Alt أثناء السحب.
 * - لاستثناء حاوية: أضف لها data-no-drag.
 */
(function () {
    'use strict';
    if (window.__hrDragScroll) return;
    window.__hrDragScroll = true;

    var SKIP = 'a, button, input, select, textarea, label, summary, option, [contenteditable="true"], [data-no-drag]';
    var THRESHOLD = 5;
    var drag = null;

    var css = document.createElement('style');
    css.textContent =
        '.hr-drag-scroll{cursor:grab}' +
        '.hr-drag-scroll.is-dragging{cursor:grabbing;user-select:none;-webkit-user-select:none;scroll-behavior:auto}' +
        '.hr-drag-scroll.is-dragging *{cursor:grabbing!important}';
    (document.head || document.documentElement).appendChild(css);

    function isHorizontalScroller(el) {
        if (!el || el.nodeType !== 1 || el === document.body || el === document.documentElement) return false;
        if (el.scrollWidth <= el.clientWidth + 1) return false;
        var ox = window.getComputedStyle(el).overflowX;
        return ox === 'auto' || ox === 'scroll';
    }

    /** أقرب حاوية تمرير أفقي فيها جدول (أو هي جزء من جدول). */
    function scrollerFor(target) {
        var el = target && target.nodeType === 1 ? target : (target && target.parentElement);
        while (el && el !== document.body) {
            if (el.hasAttribute && el.hasAttribute('data-no-drag')) return null;
            if (isHorizontalScroller(el) && (el.tagName === 'TABLE' || el.querySelector('table'))) return el;
            el = el.parentElement;
        }
        return null;
    }

    var lastHover = null;
    document.addEventListener('mouseover', function (e) {
        var el = scrollerFor(e.target);
        if (lastHover && lastHover !== el) lastHover.classList.remove('hr-drag-scroll');
        if (el) el.classList.add('hr-drag-scroll');
        lastHover = el;
    });

    document.addEventListener('pointerdown', function (e) {
        if (e.pointerType !== 'mouse' || e.button !== 0 || e.altKey) return;
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
            drag.el.classList.add('hr-drag-scroll', 'is-dragging');
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
            // منع نقرة عرضية على صف/رابط بعد انتهاء السحب
            var block = function (ev) { ev.stopPropagation(); ev.preventDefault(); };
            document.addEventListener('click', block, { capture: true, once: true });
            window.setTimeout(function () { document.removeEventListener('click', block, true); }, 0);
        }
    }
    document.addEventListener('pointerup', stop);
    document.addEventListener('pointercancel', stop);
    document.addEventListener('dragstart', function (e) { if (drag) e.preventDefault(); });
})();
