/**
 * بحث ذكي فوري في جداول HTML (تصفية صفوف data-search).
 */
(function () {
    'use strict';

    function normalize(text) {
        return String(text || '')
            .toLowerCase()
            .replace(/\s+/g, ' ')
            .trim();
    }

    function tokensFromQuery(query) {
        return normalize(query).split(' ').filter(Boolean);
    }

    function rowMatches(row, tokens) {
        if (!tokens.length) return true;
        var hay = normalize(row.getAttribute('data-search') || row.textContent);
        for (var i = 0; i < tokens.length; i++) {
            if (hay.indexOf(tokens[i]) === -1) return false;
        }
        return true;
    }

    function firstCellNumber(row, index) {
        var cell = row.querySelector('td');
        if (cell) cell.textContent = String(index);
    }

    function applyPanelSearch(panel) {
        if (!panel) return;
        var input = panel.querySelector('[data-hr-table-search-input]');
        var table = panel.querySelector('[data-hr-table-search]');
        if (!input || !table) return;

        var tbody = table.tBodies[0];
        if (!tbody) return;

        var rows = tbody.querySelectorAll('tr[data-search]');
        var emptyRow = tbody.querySelector('[data-hr-table-search-empty]');
        var meta = panel.querySelector('[data-hr-table-search-meta]');
        var clearBtn = panel.querySelector('[data-hr-table-search-clear]');
        var tokens = tokensFromQuery(input.value);
        var visible = 0;
        var total = rows.length;

        rows.forEach(function (row) {
            var show = rowMatches(row, tokens);
            row.hidden = !show;
            if (show) {
                visible += 1;
                firstCellNumber(row, visible);
            }
        });

        if (emptyRow) {
            emptyRow.hidden = !(total > 0 && visible === 0 && tokens.length > 0);
        }

        if (clearBtn) {
            clearBtn.classList.toggle('hidden', !input.value);
        }

        if (meta) {
            if (tokens.length && total > 0) {
                meta.textContent = visible === total
                    ? 'عرض ' + total + ' نتيجة'
                    : 'عرض ' + visible + ' من ' + total;
                meta.classList.remove('hidden');
            } else {
                meta.textContent = '';
                meta.classList.add('hidden');
            }
        }
    }

    function refresh(root) {
        var scope = root && root.querySelectorAll ? root : document;
        scope.querySelectorAll('[data-hr-table-search-panel]').forEach(applyPanelSearch);
    }

    document.addEventListener('input', function (event) {
        var input = event.target.closest('[data-hr-table-search-input]');
        if (!input) return;
        var panel = input.closest('[data-hr-table-search-panel]');
        applyPanelSearch(panel);
    });

    document.addEventListener('click', function (event) {
        var btn = event.target.closest('[data-hr-table-search-clear]');
        if (!btn) return;
        var panel = btn.closest('[data-hr-table-search-panel]');
        if (!panel) return;
        var input = panel.querySelector('[data-hr-table-search-input]');
        if (!input) return;
        input.value = '';
        input.focus();
        applyPanelSearch(panel);
    });

    document.addEventListener('keydown', function (event) {
        if (event.key !== 'Escape') return;
        var input = event.target.closest('[data-hr-table-search-input]');
        if (!input || !input.value) return;
        event.preventDefault();
        input.value = '';
        applyPanelSearch(input.closest('[data-hr-table-search-panel]'));
    });

    document.addEventListener('DOMContentLoaded', function () {
        refresh(document);
    });

    window.hrTableSmartSearch = { refresh: refresh };
})();
