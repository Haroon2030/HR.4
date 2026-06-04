/**
 * قائمة اختيار التقرير — مكوّن مستقل (لا يستخدم hr-multiselect).
 */
(function () {
    'use strict';

    function closeAll(except) {
        document.querySelectorAll('.hr-rpt-picker').forEach(function (picker) {
            if (except && picker === except) return;
            closePicker(picker);
        });
    }

    function closePicker(picker) {
        var menu = picker.querySelector('.hr-rpt-picker__menu');
        var btn = picker.querySelector('.hr-rpt-picker__trigger');
        if (!menu || !btn) return;
        menu.hidden = true;
        if (menu.parentNode === document.body) {
            picker.appendChild(menu);
        }
        menu.style.cssText = '';
        btn.setAttribute('aria-expanded', 'false');
    }

    function positionMenu(picker, menu, btn) {
        var rect = btn.getBoundingClientRect();
        var maxW = Math.min(420, window.innerWidth - 16);
        var w = Math.max(Math.round(rect.width), 260);
        w = Math.min(Math.max(w, 260), maxW);
        if (menu.parentNode !== document.body) {
            document.body.appendChild(menu);
        }
        menu.style.position = 'fixed';
        menu.style.top = Math.round(rect.bottom + 4) + 'px';
        menu.style.right = Math.round(window.innerWidth - rect.right) + 'px';
        menu.style.left = 'auto';
        menu.style.width = w + 'px';
        menu.style.minWidth = w + 'px';
        menu.style.maxWidth = maxW + 'px';
        menu.style.zIndex = '10060';
        menu.style.display = 'block';
    }

    function setValue(picker, value, label) {
        var input = picker.querySelector('#reportSelect') || picker.querySelector('[name="report"]');
        var labelEl = picker.querySelector('.hr-rpt-picker__label');
        var ph = picker.getAttribute('data-placeholder') || '— اختر —';
        if (!input || !labelEl) return;
        input.value = value || '';
        labelEl.textContent = value ? label : ph;
        labelEl.classList.toggle('is-placeholder', !value);
        picker.querySelectorAll('.hr-rpt-picker__option').forEach(function (opt) {
            var on = opt.getAttribute('data-value') === value;
            opt.classList.toggle('is-selected', on);
            opt.setAttribute('aria-selected', on ? 'true' : 'false');
        });
        input.dispatchEvent(new Event('change', { bubbles: true }));
    }

    function openPicker(picker) {
        var menu = picker.querySelector('.hr-rpt-picker__menu');
        var btn = picker.querySelector('.hr-rpt-picker__trigger');
        if (!menu || !btn || menu.querySelectorAll('.hr-rpt-picker__option').length === 0) return;
        closeAll(picker);
        menu.hidden = false;
        positionMenu(picker, menu, btn);
        btn.setAttribute('aria-expanded', 'true');
    }

    function initPicker(picker) {
        if (!picker || picker.dataset.rptPickerReady === '1') return;
        picker.dataset.rptPickerReady = '1';

        var btn = picker.querySelector('.hr-rpt-picker__trigger');
        var menu = picker.querySelector('.hr-rpt-picker__menu');
        var input = picker.querySelector('[name="report"]');
        if (!btn || !menu || !input) return;

        btn.addEventListener('click', function (e) {
            e.preventDefault();
            e.stopPropagation();
            if (menu.hidden) openPicker(picker);
            else closePicker(picker);
        });

        menu.querySelectorAll('.hr-rpt-picker__option').forEach(function (opt) {
            opt.addEventListener('click', function (e) {
                e.preventDefault();
                e.stopPropagation();
                var val = opt.getAttribute('data-value') || '';
                if (!val) return;
                setValue(picker, val, (opt.textContent || '').trim());
                closePicker(picker);
            });
        });

        var form = picker.closest('form');
        if (form) {
            form.addEventListener('submit', function (e) {
                if (!input.value) {
                    e.preventDefault();
                    openPicker(picker);
                    btn.focus();
                }
            });
        }
    }

    function init(root) {
        var scope = root && root.querySelectorAll ? root : document;
        scope.querySelectorAll('.hr-rpt-picker').forEach(initPicker);
    }

    document.addEventListener('click', function (e) {
        if (e.target.closest('.hr-rpt-picker')) return;
        closeAll(null);
    });

    window.addEventListener('resize', function () { closeAll(null); });
    window.addEventListener('scroll', function () { closeAll(null); }, true);

    window.hrInitReportPickers = init;

    function boot() {
        init();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', boot);
    } else {
        boot();
    }
})();
