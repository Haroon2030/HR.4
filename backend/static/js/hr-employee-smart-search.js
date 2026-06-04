/**
 * بحث موظف ذكي — النتائج تظهر عند الكتابة فقط (بدون قائمة كاملة عند التركيز).
 */
(function () {
    'use strict';

    var DEFAULT_MIN_LEN = 1;
    var DEFAULT_PAGE_SIZE = 8;

    function escapeHtml(s) {
        return String(s).replace(/[&<>"']/g, function (c) {
            return ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c];
        });
    }

    window.hrEmployeeSearchFilter = function (employees, query, minLen) {
        minLen = minLen == null ? DEFAULT_MIN_LEN : minLen;
        var q = (query || '').trim().toLowerCase();
        if (!q || q.length < minLen) return [];
        var terms = q.split(/\s+/).filter(Boolean);
        return (employees || []).filter(function (e) {
            var hay = [e.name, e.number, e.id_number, e.dept, e.branch]
                .filter(Boolean)
                .join(' ')
                .toLowerCase();
            return terms.every(function (t) { return hay.indexOf(t) !== -1; });
        });
    };

    window.employeePickerBase = function (opts) {
        opts = opts || {};
        var minQueryLen = opts.minQueryLen != null ? opts.minQueryLen : DEFAULT_MIN_LEN;
        var pageSize = opts.pageSize || DEFAULT_PAGE_SIZE;

        return {
            query: '',
            showList: false,
            selected: null,
            activeIndex: 0,
            currentPage: 1,
            pageSize: pageSize,
            minQueryLen: minQueryLen,
            employees: [],

            get hasQuery() {
                return (this.query || '').trim().length >= this.minQueryLen;
            },

            get filtered() {
                return window.hrEmployeeSearchFilter(this.employees, this.query, this.minQueryLen);
            },

            get totalPages() {
                return Math.max(1, Math.ceil(this.filtered.length / this.pageSize));
            },

            get pagedItems() {
                var start = (this.currentPage - 1) * this.pageSize;
                return this.filtered.slice(start, start + this.pageSize);
            },

            onQueryInput() {
                this.currentPage = 1;
                this.activeIndex = 0;
                this.showList = this.hasQuery;
            },

            onSearchFocus() {
                if (this.hasQuery) this.showList = true;
            },

            moveActive(delta) {
                var max = this.pagedItems.length;
                if (max === 0) return;
                var next = this.activeIndex + delta;
                if (next < 0) {
                    if (this.currentPage > 1) {
                        this.currentPage--;
                        var self = this;
                        this.$nextTick(function () { self.activeIndex = self.pagedItems.length - 1; });
                    }
                } else if (next >= max) {
                    if (this.currentPage < this.totalPages) {
                        this.currentPage++;
                        var self2 = this;
                        this.$nextTick(function () { self2.activeIndex = 0; });
                    }
                } else {
                    this.activeIndex = next;
                }
            },

            pickActive() {
                var list = this.pagedItems;
                if (list.length === 0) return;
                this.selectEmployee(list[this.activeIndex] || list[0]);
            },

            prevPage() {
                if (this.currentPage > 1) this.currentPage--;
            },

            nextPage() {
                if (this.currentPage < this.totalPages) this.currentPage++;
            },

            selectEmployee(emp) {
                this.selected = emp;
                this.query = '';
                this.showList = false;
            },

            clearSelection() {
                this.selected = null;
                this.query = '';
                this.showList = false;
                this.currentPage = 1;
                var self = this;
                this.$nextTick(function () {
                    if (self.$refs && self.$refs.searchInput) self.$refs.searchInput.focus();
                });
            },

            clearQuery() {
                this.query = '';
                this.showList = false;
                this.currentPage = 1;
                this.activeIndex = 0;
                if (this.$refs && this.$refs.searchInput) this.$refs.searchInput.focus();
            },

            highlightMatch(text) {
                var t = String(text || '');
                var q = (this.query || '').trim();
                if (!q) return escapeHtml(t);
                var re = new RegExp('(' + q.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + ')', 'gi');
                return escapeHtml(t).replace(re, '<mark class="hr-smart-search__mark">$1</mark>');
            },
        };
    };

    window.initEmployeePicker = function (ctx) {
        if (!ctx || typeof ctx.$nextTick !== 'function') return;
        var refreshIcons = function () {
            if (window.lucide) lucide.createIcons();
        };
        ctx.$nextTick(refreshIcons);
        ctx.$watch('selected', refreshIcons);
        ctx.$watch('showList', function (v) { if (v) ctx.$nextTick(refreshIcons); });
        ctx.$watch('pagedItems', function () { ctx.$nextTick(refreshIcons); });
        ctx.$watch('query', function () {
            ctx.currentPage = 1;
            ctx.activeIndex = 0;
            if (!ctx.hasQuery) ctx.showList = false;
        });
        ctx.$watch('currentPage', function () { ctx.activeIndex = 0; });
    };
})();
