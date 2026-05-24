/**
 * قوائم فلترة متعددة + خيار «الكل» للقوائم المفردة (.hr-filter-select).
 */
(function () {
    'use strict';

    function initMultiselect(select) {
        if (select.dataset.msReady === '1') return;
        select.dataset.msReady = '1';

        const allLabel = select.dataset.allLabel || 'الكل';
        const wrap = document.createElement('div');
        wrap.className = 'hr-ms';
        wrap.dir = 'rtl';

        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'hr-ms__btn';
        btn.setAttribute('aria-haspopup', 'listbox');
        btn.setAttribute('aria-expanded', 'false');

        const panel = document.createElement('div');
        panel.className = 'hr-ms__panel';
        panel.hidden = true;
        panel.setAttribute('role', 'listbox');

        const allRow = document.createElement('label');
        allRow.className = 'hr-ms__row hr-ms__row--all';
        const allCb = document.createElement('input');
        allCb.type = 'checkbox';
        allCb.className = 'hr-ms__cb';
        allCb.value = '';
        allRow.appendChild(allCb);
        allRow.appendChild(document.createTextNode(' ' + allLabel));
        panel.appendChild(allRow);

        const optionCbs = [];
        Array.from(select.options).forEach(function (opt) {
            if (!opt.value) return;
            const row = document.createElement('label');
            row.className = 'hr-ms__row';
            const cb = document.createElement('input');
            cb.type = 'checkbox';
            cb.className = 'hr-ms__cb';
            cb.value = opt.value;
            cb.checked = opt.selected;
            row.appendChild(cb);
            row.appendChild(document.createTextNode(' ' + opt.textContent.trim()));
            panel.appendChild(row);
            optionCbs.push({ cb: cb, opt: opt });
        });

        function syncFromNative() {
            const selected = optionCbs.filter(function (x) { return x.opt.selected; });
            if (selected.length === 0) {
                allCb.checked = true;
                optionCbs.forEach(function (x) { x.cb.checked = false; });
            } else {
                allCb.checked = false;
                optionCbs.forEach(function (x) { x.cb.checked = x.opt.selected; });
            }
            updateLabel();
        }

        function syncToNative() {
            if (allCb.checked) {
                optionCbs.forEach(function (x) {
                    x.opt.selected = false;
                    x.cb.checked = false;
                });
            } else {
                optionCbs.forEach(function (x) {
                    x.opt.selected = x.cb.checked;
                });
            }
            updateLabel();
        }

        function updateLabel() {
            if (allCb.checked || optionCbs.every(function (x) { return !x.opt.selected; })) {
                btn.textContent = allLabel;
                return;
            }
            const n = optionCbs.filter(function (x) { return x.opt.selected; }).length;
            if (n === 1) {
                const one = optionCbs.find(function (x) { return x.opt.selected; });
                btn.textContent = one ? one.opt.textContent.trim() : allLabel;
            } else {
                btn.textContent = n + ' محدّد';
            }
        }

        allCb.addEventListener('change', function () {
            if (allCb.checked) {
                optionCbs.forEach(function (x) { x.cb.checked = false; });
            }
            syncToNative();
        });

        optionCbs.forEach(function (x) {
            x.cb.addEventListener('change', function () {
                if (x.cb.checked) allCb.checked = false;
                if (optionCbs.every(function (y) { return !y.cb.checked; })) {
                    allCb.checked = true;
                }
                syncToNative();
            });
        });

        btn.addEventListener('click', function (e) {
            e.preventDefault();
            const open = !panel.hidden;
            document.querySelectorAll('.hr-ms__panel').forEach(function (p) { p.hidden = true; });
            document.querySelectorAll('.hr-ms__btn').forEach(function (b) {
                b.setAttribute('aria-expanded', 'false');
            });
            if (!open) {
                panel.hidden = false;
                btn.setAttribute('aria-expanded', 'true');
            }
        });

        document.addEventListener('click', function (e) {
            if (!wrap.contains(e.target)) {
                panel.hidden = true;
                btn.setAttribute('aria-expanded', 'false');
            }
        });

        select.classList.add('hr-filter-ms-native');
        select.parentNode.insertBefore(wrap, select);
        wrap.appendChild(btn);
        wrap.appendChild(panel);
        wrap.appendChild(select);

        select.addEventListener('change', syncFromNative);
        const form = select.closest('form');
        if (form) {
            form.addEventListener('submit', function () {
                const any = optionCbs.some(function (x) { return x.opt.selected; });
                select.disabled = !any;
            });
        }

        syncFromNative();
    }

    function ensureAllOption(select) {
        if (select.multiple || select.required) return;
        const first = select.options[0];
        if (first && first.value === '') return;
        const label = select.dataset.allLabel || 'الكل';
        const opt = document.createElement('option');
        opt.value = '';
        opt.textContent = label;
        select.insertBefore(opt, select.firstChild);
    }

    function init() {
        document.querySelectorAll('select.hr-filter-ms:not(.hr-filter-ms-native)').forEach(initMultiselect);
        document.querySelectorAll('select.hr-filter-select').forEach(ensureAllOption);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
