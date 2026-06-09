/**
 * تصفية وجدولة صفوف أرشيف الموظف (إفادات / أرشيف زمني).
 */
(function () {
    'use strict';

    var STATEMENT_TYPES = [
        'statement',
        'warning',
        'final_warning',
        'acknowledgment',
        'other',
        'penalty',
    ];

    var FILTER_DEFS = {
        warnings: [
            { value: 'all', label: 'كل الأنواع' },
            { value: 'statement', label: 'إفادة' },
            { value: 'warning', label: 'إنذار' },
            { value: 'final_warning', label: 'إنذار نهائي' },
            { value: 'penalty', label: 'مخالفة (خصم مالي)' },
            { value: 'acknowledgment', label: 'إقرار' },
            { value: 'other', label: 'أخرى' },
        ],
        archive: [
            { value: 'all', label: 'كل الأنواع' },
            { value: 'hire', label: 'توظيف' },
            { value: 'statement', label: 'إفادة / إنذار', match: STATEMENT_TYPES },
            { value: 'terminate', label: 'تصفية' },
            { value: 'reactivate', label: 'إعادة تفعيل' },
            { value: 'salary_adjust', label: 'تعديل راتب', requiresSalary: true },
            { value: 'transfer', label: 'نقل' },
        ],
    };

    function getFilterDef(tabKey, filterVal) {
        var defs = FILTER_DEFS[tabKey] || [];
        for (var i = 0; i < defs.length; i++) {
            if (defs[i].value === filterVal) return defs[i];
        }
        return null;
    }

    function rowMatchesFilter(rowType, filterVal, tabKey) {
        if (!filterVal || filterVal === 'all') return true;
        var def = getFilterDef(tabKey, filterVal);
        if (def && def.match) {
            return def.match.indexOf(rowType) !== -1;
        }
        return rowType === filterVal;
    }

    function rowMatchesSearch(row, query) {
        if (!query) return true;
        var txt = (row.dataset.text || '').toLowerCase();
        return txt.indexOf(query) !== -1;
    }

    function buildArchivePager(tabKey) {
        return {
            tabKey: tabKey || '',
            q: '',
            filter: 'all',
            filterOpen: false,
            page: 1,
            perPage: 6,
            totalPages: 1,
            matchedCount: 0,
            totalCount: 0,
            filterOptionsList: [],
            canViewSalary: false,
            _tabHandler: null,
            _searchTimer: null,

            init() {
                var self = this;
                this.canViewSalary = this.$el.dataset.canViewSalary === '1';
                this.$nextTick(function () {
                    self.updateFilterOptions();
                    self.refresh();
                });
                this._tabHandler = function (e) {
                    if (e.detail && e.detail.tab === self.tabKey) {
                        self.filterOpen = false;
                        self.$nextTick(function () {
                            self.updateFilterOptions();
                            self.refresh();
                        });
                    }
                };
                window.addEventListener('employee-tab-changed', this._tabHandler);
            },

            onSearchInput() {
                var self = this;
                this.page = 1;
                if (this._searchTimer) clearTimeout(this._searchTimer);
                this._searchTimer = setTimeout(function () { self.refresh(); }, 180);
            },

            filterLabel() {
                var def = getFilterDef(this.tabKey, this.filter);
                return (def && def.label) || 'كل الأنواع';
            },

            updateFilterOptions() {
                var self = this;
                var rows = Array.from(this.$el.querySelectorAll('tr.archive-row'));
                var defs = (FILTER_DEFS[this.tabKey] || []).filter(function (d) {
                    return !(d.requiresSalary && !self.canViewSalary);
                });
                this.filterOptionsList = defs.map(function (d) {
                    var count = 0;
                    rows.forEach(function (r) {
                        var t = (r.getAttribute('data-type') || r.dataset.type || '').trim();
                        if (rowMatchesFilter(t, d.value, self.tabKey)) count++;
                    });
                    return { value: d.value, label: d.label, count: count };
                });
            },

            setFilter(val) {
                this.filter = val || 'all';
                this.filterOpen = false;
                this.page = 1;
                var self = this;
                this.$nextTick(function () { self.refresh(); });
            },

            refresh() {
                var self = this;
                var rows = Array.from(this.$el.querySelectorAll('tr.archive-row'));
                var q = (this.q || '').toLowerCase().trim();
                var filterVal = this.filter || 'all';
                var matches = rows.filter(function (r) {
                    var t = (r.getAttribute('data-type') || r.dataset.type || '').trim();
                    return rowMatchesFilter(t, filterVal, self.tabKey) && rowMatchesSearch(r, q);
                });
                matches.sort(function (a, b) {
                    var tsA = a.getAttribute('data-ts') || a.dataset.ts || '';
                    var tsB = b.getAttribute('data-ts') || b.dataset.ts || '';
                    return tsB.localeCompare(tsA);
                });

                this.totalCount = rows.length;
                this.matchedCount = matches.length;
                this.totalPages = Math.max(1, Math.ceil(matches.length / this.perPage));
                if (this.page > this.totalPages) this.page = this.totalPages;
                if (this.page < 1) this.page = 1;

                rows.forEach(function (r) {
                    r.classList.add('is-filtered-out');
                    r.setAttribute('aria-hidden', 'true');
                });

                var emptyRow = this.$el.querySelector('tr.archive-empty');
                var start = (this.page - 1) * this.perPage;
                var slice = matches.slice(start, start + this.perPage);
                if (slice.length) {
                    var tbody = slice[0].parentNode;
                    slice.forEach(function (r) {
                        r.classList.remove('is-filtered-out');
                        r.removeAttribute('aria-hidden');
                        tbody.appendChild(r);
                    });
                }

                if (emptyRow) {
                    var showEmpty = rows.length > 0 && matches.length === 0;
                    emptyRow.classList.toggle('is-filtered-out', !showEmpty);
                    if (showEmpty) {
                        emptyRow.removeAttribute('aria-hidden');
                    } else {
                        emptyRow.setAttribute('aria-hidden', 'true');
                    }
                }

                this.updateFilterOptions();
                this.$nextTick(function () {
                    if (window.lucide) lucide.createIcons();
                });
            },
        };
    }

    window.archivePager = buildArchivePager;

    function registerArchivePager() {
        if (!window.Alpine || typeof window.Alpine.data !== 'function') return;
        window.Alpine.data('archivePager', function (tabKey) {
            return buildArchivePager(tabKey);
        });
    }

    document.addEventListener('alpine:init', registerArchivePager);
    registerArchivePager();
})();
