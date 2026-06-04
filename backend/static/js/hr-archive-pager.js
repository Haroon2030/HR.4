/**
 * تصفية وجدولة صفوف أرشيف الموظف (إفادات / أرشيف زمني).
 */
(function () {
    'use strict';

    var FILTER_LABELS = {
        warnings: {
            all: 'كل الأنواع',
            statement: 'إفادة',
            warning: 'إنذار',
            final_warning: 'إنذار نهائي',
            acknowledgment: 'إقرار',
            other: 'أخرى',
        },
        archive: {
            all: 'كل الأنواع',
            hire: 'توظيف',
            statement: 'إفادة / إنذار',
            terminate: 'تصفية',
            reactivate: 'إعادة تفعيل',
            salary_adjust: 'تعديل راتب',
            transfer: 'نقل',
        },
    };

    window.archivePager = function (tabKey) {
        return {
            tabKey: tabKey || '',
            q: '',
            filter: 'all',
            filterOpen: false,
            page: 1,
            perPage: 6,
            totalPages: 1,
            _tabHandler: null,

            init() {
                var self = this;
                this.$nextTick(function () { self.refresh(); });
                this._tabHandler = function (e) {
                    if (e.detail && e.detail.tab === self.tabKey) {
                        self.filterOpen = false;
                        self.$nextTick(function () { self.refresh(); });
                    }
                };
                window.addEventListener('employee-tab-changed', this._tabHandler);
            },

            filterLabel() {
                var map = FILTER_LABELS[this.tabKey] || {};
                return map[this.filter] || map.all || 'كل الأنواع';
            },

            setFilter(val) {
                this.filter = val || 'all';
                this.filterOpen = false;
                this.page = 1;
                this.refresh();
            },

            refresh() {
                var rows = Array.from(this.$el.querySelectorAll('tr.archive-row'));
                var q = (this.q || '').toLowerCase();
                var filterVal = this.filter || 'all';
                var matches = rows.filter(function (r) {
                    var t = r.dataset.type || '';
                    var txt = (r.dataset.text || '').toLowerCase();
                    var okF = filterVal === 'all' || filterVal === t;
                    var okQ = q === '' || txt.indexOf(q) !== -1;
                    return okF && okQ;
                });
                matches.sort(function (a, b) {
                    return (b.dataset.ts || '').localeCompare(a.dataset.ts || '');
                });
                this.totalPages = Math.max(1, Math.ceil(matches.length / this.perPage));
                if (this.page > this.totalPages) this.page = this.totalPages;
                if (this.page < 1) this.page = 1;
                rows.forEach(function (r) { r.style.display = 'none'; });
                var emptyRow = this.$el.querySelector('tr.archive-empty');
                var start = (this.page - 1) * this.perPage;
                var slice = matches.slice(start, start + this.perPage);
                if (slice.length) {
                    var tbody = slice[0].parentNode;
                    slice.forEach(function (r) {
                        r.style.display = '';
                        tbody.appendChild(r);
                    });
                }
                if (emptyRow) {
                    emptyRow.style.display = rows.length && matches.length === 0 ? '' : 'none';
                }
                this.$nextTick(function () {
                    if (window.lucide) lucide.createIcons();
                });
            },
        };
    };
})();
