/**
 * جداول مضغوطة قابلة للتوسّع: الأعمدة المعلَّمة data-secondary تُخفى من الصف،
 * ويظهر زر لفتح صف تفاصيل تحت كل سجل يعرضها.
 *
 * الاستخدام: <table data-hr-dyn> ... <th data-secondary>عمود ثانوي</th>
 * العناصر داخل الخلايا الثانوية (أزرار العرض/الملفات) تُنسخ إلى صف التفاصيل،
 * أما <template> فيبقى في الصف الأصلي المخفي ليبقى مرجعها (id) صالحاً.
 */
(function () {
    'use strict';

    var EMPTY = /^[\s—–-]*$/;

    function isEmptyCell(cell) {
        if (cell.querySelector('a, button, img, svg, input, i[data-lucide]')) return false;
        return EMPTY.test(cell.textContent || '');
    }

    function cloneContent(cell) {
        var wrap = document.createElement('div');
        wrap.className = 'hr-dyn-value';
        Array.prototype.forEach.call(cell.childNodes, function (node) {
            if (node.nodeType === 1 && node.tagName === 'TEMPLATE') return;
            wrap.appendChild(node.cloneNode(true));
        });
        if (window.lucide && wrap.querySelector('[data-lucide]')) {
            try { window.lucide.createIcons({ nameAttr: 'data-lucide' }); } catch (e) { /* ignore */ }
        }
        return wrap;
    }

    function setup(table) {
        if (table.dataset.hrDynReady || !table.tHead || !table.tHead.rows.length) return;
        var headRow = table.tHead.rows[0];
        var headers = Array.prototype.slice.call(headRow.cells);
        var secondary = [];
        headers.forEach(function (th, index) {
            if (th.hasAttribute('data-secondary')) secondary.push(index);
        });
        if (!secondary.length) return;
        table.dataset.hrDynReady = '1';
        table.classList.add('hr-dyn-table');

        secondary.forEach(function (i) { headers[i].classList.add('hr-dyn-hide'); });
        var corner = document.createElement('th');
        corner.className = 'hr-dyn-toggle-col';
        corner.setAttribute('scope', 'col');
        corner.innerHTML = '<span class="sr-only">تفاصيل</span>';
        headRow.insertBefore(corner, headRow.cells[0]);

        var visibleCount = headers.length - secondary.length + 1;

        Array.prototype.forEach.call(table.tBodies, function (body) {
            Array.prototype.slice.call(body.rows).forEach(function (tr) {
                if (tr.cells.length !== headers.length) return; // صفوف الدمج (colspan)
                var cells = Array.prototype.slice.call(tr.cells);
                var items = [];
                secondary.forEach(function (i) {
                    cells[i].classList.add('hr-dyn-hide');
                    if (!isEmptyCell(cells[i])) {
                        items.push({ label: headers[i].textContent.trim(), cell: cells[i] });
                    }
                });

                var td = document.createElement('td');
                td.className = 'hr-dyn-toggle-col';
                if (items.length) {
                    var btn = document.createElement('button');
                    btn.type = 'button';
                    btn.className = 'hr-dyn-toggle';
                    btn.setAttribute('aria-expanded', 'false');
                    btn.setAttribute('aria-label', 'عرض التفاصيل');
                    btn.title = 'عرض التفاصيل';
                    td.appendChild(btn);
                    bind(tr, btn, items, visibleCount);
                }
                tr.insertBefore(td, tr.cells[0]);
            });
        });
    }

    function bind(tr, btn, items, colspan) {
        var detail = null;

        function build() {
            detail = document.createElement('tr');
            detail.className = 'hr-dyn-detail';
            var cell = document.createElement('td');
            cell.colSpan = colspan;
            var grid = document.createElement('div');
            grid.className = 'hr-dyn-grid';
            items.forEach(function (item) {
                var box = document.createElement('div');
                box.className = 'hr-dyn-item';
                var label = document.createElement('span');
                label.className = 'hr-dyn-label';
                label.textContent = item.label;
                box.appendChild(label);
                box.appendChild(cloneContent(item.cell));
                grid.appendChild(box);
            });
            cell.appendChild(grid);
            detail.appendChild(cell);
            tr.after(detail);
            syncVisibility();
        }

        function syncVisibility() {
            if (detail) detail.style.display = tr.style.display === 'none' ? 'none' : '';
        }

        // الصفوف المفلترة (Alpine x-show) تُخفي تفاصيلها أيضاً
        new MutationObserver(syncVisibility).observe(tr, { attributes: true, attributeFilter: ['style'] });

        btn.addEventListener('click', function () {
            var open = btn.getAttribute('aria-expanded') !== 'true';
            if (open && !detail) build();
            if (detail) detail.hidden = !open;
            btn.setAttribute('aria-expanded', open ? 'true' : 'false');
            tr.classList.toggle('is-expanded', open);
        });
    }

    function init(root) {
        (root || document).querySelectorAll('table[data-hr-dyn]').forEach(setup);
    }

    window.hrInitDynTables = init;
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function () { init(document); });
    } else {
        init(document);
    }
    // تبويبات Alpine تُنشئ محتواها بعد التحميل
    document.addEventListener('alpine:initialized', function () { init(document); });
})();
