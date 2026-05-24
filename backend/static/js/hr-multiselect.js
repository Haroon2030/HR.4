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

        function positionPanel() {
            const rect = btn.getBoundingClientRect();
            panel.style.position = 'fixed';
            panel.style.top = Math.round(rect.bottom + 2) + 'px';
            panel.style.left = Math.round(rect.left) + 'px';
            panel.style.width = Math.round(rect.width) + 'px';
            panel.style.right = 'auto';
            panel.style.zIndex = '9999';
            panel.classList.add('hr-ms__panel--open');
        }

        panel._hrMsWrap = wrap;
        panel._hrMsSelect = select;

        function closePanel() {
            panel.hidden = true;
            panel.classList.remove('hr-ms__panel--open');
            panel.style.position = '';
            panel.style.top = '';
            panel.style.left = '';
            panel.style.right = '';
            panel.style.width = '';
            panel.style.zIndex = '';
            if (panel.parentNode !== wrap) {
                wrap.insertBefore(panel, select);
            }
            btn.setAttribute('aria-expanded', 'false');
        }

        function closeOtherPanels() {
            document.querySelectorAll('.hr-ms__panel').forEach(function (p) {
                if (p === panel || p.hidden) return;
                p.hidden = true;
                p.classList.remove('hr-ms__panel--open');
                p.style.position = '';
                p.style.top = '';
                p.style.left = '';
                p.style.right = '';
                p.style.width = '';
                p.style.zIndex = '';
                if (p._hrMsWrap && p.parentNode === document.body) {
                    p._hrMsWrap.insertBefore(p, p._hrMsSelect);
                }
                const otherBtn = p._hrMsWrap && p._hrMsWrap.querySelector('.hr-ms__btn');
                if (otherBtn) otherBtn.setAttribute('aria-expanded', 'false');
            });
        }

        function openPanel() {
            closeOtherPanels();
            if (panel.parentNode !== document.body) {
                document.body.appendChild(panel);
            }
            panel.hidden = false;
            positionPanel();
            btn.setAttribute('aria-expanded', 'true');
        }

        btn.addEventListener('click', function (e) {
            e.preventDefault();
            e.stopPropagation();
            if (panel.hidden) {
                openPanel();
            } else {
                closePanel();
            }
        });

        document.addEventListener('click', function (e) {
            if (!wrap.contains(e.target) && !panel.contains(e.target)) {
                closePanel();
            }
        });

        window.addEventListener('resize', closePanel);
        window.addEventListener('scroll', function (e) {
            if (!panel.hidden && !panel.contains(e.target)) closePanel();
        }, true);

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
