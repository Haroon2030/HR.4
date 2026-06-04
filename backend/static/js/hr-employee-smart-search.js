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

    function queryTrimmed(ctx) {
        return (ctx.query || '').trim();
    }

    function hasMinQuery(ctx) {
        return queryTrimmed(ctx).length >= ctx.minQueryLen;
    }

    function localMatches(ctx) {
        return window.hrEmployeeSearchFilter(
            ctx.employees,
            ctx.query,
            ctx.minQueryLen
        );
    }

    function syncFilteredList(ctx) {
        var local = localMatches(ctx);
        if (!ctx.searchUrl) {
            ctx.filteredList = local;
            return;
        }
        if (ctx.remoteResults && ctx.remoteResults.length) {
            ctx.filteredList = ctx.remoteResults;
        } else {
            ctx.filteredList = local;
        }
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
        var searchUrl = opts.searchUrl || '';

        return {
            query: '',
            showList: false,
            selected: null,
            activeIndex: 0,
            currentPage: 1,
            pageSize: pageSize,
            minQueryLen: minQueryLen,
            employees: [],
            searchUrl: searchUrl,
            remoteResults: [],
            filteredList: [],
            searchLoading: false,
            _searchTimer: null,
            _searchRequestId: 0,

            get hasQuery() {
                return hasMinQuery(this);
            },

            get filtered() {
                return this.filteredList;
            },

            get totalPages() {
                return Math.max(1, Math.ceil(this.filteredList.length / this.pageSize));
            },

            get pagedItems() {
                var start = (this.currentPage - 1) * this.pageSize;
                return this.filteredList.slice(start, start + this.pageSize);
            },

            onQueryInput() {
                this.currentPage = 1;
                this.activeIndex = 0;
                if (!hasMinQuery(this)) {
                    this.showList = false;
                    this.remoteResults = [];
                    this.filteredList = [];
                    return;
                }
                syncFilteredList(this);
                this.showList = this.filteredList.length > 0 || !!this.searchUrl;
                if (this.searchUrl) {
                    this.scheduleRemoteSearch();
                }
            },

            scheduleRemoteSearch() {
                var self = this;
                if (self._searchTimer) clearTimeout(self._searchTimer);
                self._searchTimer = setTimeout(function () {
                    self.runRemoteSearch();
                }, 280);
            },

            runRemoteSearch() {
                var self = this;
                var q = queryTrimmed(self);
                if (!self.searchUrl || !q || q.length < self.minQueryLen) {
                    self.remoteResults = [];
                    self.searchLoading = false;
                    syncFilteredList(self);
                    return;
                }
                var reqId = ++self._searchRequestId;
                self.searchLoading = true;
                fetch(self.searchUrl + '?q=' + encodeURIComponent(q), {
                    method: 'GET',
                    credentials: 'same-origin',
                    headers: {
                        'X-Requested-With': 'XMLHttpRequest',
                        Accept: 'application/json',
                    },
                })
                    .then(function (res) {
                        if (!res.ok) {
                            throw new Error('search ' + res.status);
                        }
                        var ct = (res.headers.get('content-type') || '');
                        if (ct.indexOf('application/json') === -1) {
                            throw new Error('not json');
                        }
                        return res.json();
                    })
                    .then(function (data) {
                        if (reqId !== self._searchRequestId) return;
                        self.remoteResults = data.results || [];
                        self.searchLoading = false;
                        syncFilteredList(self);
                        self.showList = hasMinQuery(self);
                        self.$nextTick(function () {
                            if (window.lucide) lucide.createIcons();
                        });
                    })
                    .catch(function () {
                        if (reqId !== self._searchRequestId) return;
                        self.searchLoading = false;
                        self.remoteResults = [];
                        syncFilteredList(self);
                        self.showList = hasMinQuery(self) && self.filteredList.length > 0;
                    });
            },

            onSearchFocus() {
                if (!hasMinQuery(this)) return;
                syncFilteredList(this);
                this.showList = this.filteredList.length > 0 || !!this.searchUrl;
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
                this.filteredList = [];
                this.remoteResults = [];
            },

            clearSelection() {
                this.selected = null;
                this.query = '';
                this.showList = false;
                this.filteredList = [];
                this.remoteResults = [];
                this.currentPage = 1;
                var self = this;
                this.$nextTick(function () {
                    if (self.$refs && self.$refs.searchInput) self.$refs.searchInput.focus();
                });
            },

            clearQuery() {
                this.query = '';
                this.showList = false;
                this.filteredList = [];
                this.remoteResults = [];
                this.currentPage = 1;
                this.activeIndex = 0;
                if (this.$refs && this.$refs.searchInput) this.$refs.searchInput.focus();
            },

            highlightMatch(text) {
                var t = String(text || '');
                var q = queryTrimmed(this);
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
        ctx.$watch('filteredList', function () { ctx.$nextTick(refreshIcons); });
        ctx.$watch('query', function () {
            ctx.currentPage = 1;
            ctx.activeIndex = 0;
            if (!hasMinQuery(ctx)) {
                ctx.showList = false;
                ctx.remoteResults = [];
                ctx.filteredList = [];
            } else {
                syncFilteredList(ctx);
            }
        });
        ctx.$watch('currentPage', function () { ctx.activeIndex = 0; });
    };
})();
