/**

 * تصفية وجدولة صفوف أرشيف الموظف (إفادات / أرشيف زمني).

 */

(function () {

    'use strict';



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

            { value: 'leave', label: 'إجازة' },

            { value: 'statement', label: 'إفادة' },

            { value: 'warning', label: 'إنذار', match: ['warning', 'final_warning'] },

            { value: 'penalty', label: 'مخالفة' },

            { value: 'acknowledgment', label: 'إقرار' },

            { value: 'terminate', label: 'تصفية' },

            { value: 'contract_end', label: 'انتهاء عقد' },

            { value: 'end_of_service', label: 'نهاية خدمة' },

            { value: 'reactivate', label: 'إعادة تفعيل' },

            { value: 'salary_adjust', label: 'تعديل راتب', requiresSalary: true },

            { value: 'transfer', label: 'نقل' },

            { value: 'schedule', label: 'جدول دوام' },

            { value: 'custody_receive', label: 'استلام عهدة' },

            { value: 'custody_clear', label: 'تصفية عهدة' },

            { value: 'loan', label: 'سلفة' },

            { value: 'absence', label: 'غياب' },

            { value: 'other', label: 'أخرى' },

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

        var txt = (row.getAttribute('data-text') || row.dataset.text || '').toLowerCase();

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

            filterMenuStyle: '',

            canViewSalary: false,

            pagerReady: false,

            cachedMatches: [],

            _tabHandler: null,

            _searchTimer: null,

            _filterReflow: null,

            _filterOutsideReady: false,



            init() {

                var self = this;

                this.canViewSalary = this.$el.dataset.canViewSalary === '1';

                this.$nextTick(function () {

                    self.rebuildMatches();

                    self.pagerReady = true;

                });

                this._tabHandler = function (e) {

                    if (e.detail && e.detail.tab === self.tabKey) {

                        self.closeFilterMenu();

                        self.$nextTick(function () {

                            self.rebuildMatches();

                        });

                    }

                };

                window.addEventListener('employee-tab-changed', this._tabHandler);

                this._filterReflow = function () {

                    if (self.filterOpen) self.syncFilterMenuPosition();

                };

                window.addEventListener('resize', this._filterReflow);

                window.addEventListener('scroll', this._filterReflow, true);

            },



            getArchiveRows() {

                var body = document.getElementById('hr-archive-tbody-' + this.tabKey);

                if (body) {

                    return Array.from(body.getElementsByClassName('archive-row'));

                }

                if (this.$refs.archiveBody) {

                    return Array.from(this.$refs.archiveBody.getElementsByClassName('archive-row'));

                }

                return Array.from(this.$el.querySelectorAll('tr.archive-row'));

            },



            syncFilterMenuPosition() {

                var root = this.$refs.atfRoot;

                var btn = this.$refs.atfBtn || (root && root.querySelector('.hr-atf__btn'));

                if (!btn) return;

                var rect = btn.getBoundingClientRect();

                var w = Math.round(rect.width);

                var gap = 4;

                var spaceBelow = window.innerHeight - rect.bottom - gap - 12;

                var maxH = Math.max(120, Math.min(288, Math.floor(spaceBelow)));

                this.filterMenuStyle =

                    'position:fixed;' +

                    'top:' + Math.round(rect.bottom + gap) + 'px;' +

                    'right:' + Math.max(8, Math.round(window.innerWidth - rect.right)) + 'px;' +

                    'left:auto;' +

                    'width:' + w + 'px;' +

                    'min-width:' + w + 'px;' +

                    'max-width:' + w + 'px;' +

                    'max-height:' + maxH + 'px;' +

                    'z-index:10100;';

            },



            toggleFilter() {

                if (this.filterOpen) {

                    this.closeFilterMenu();

                    return;

                }

                this._filterOutsideReady = false;

                this.filterOpen = true;

                var self = this;

                this.$nextTick(function () {

                    self.syncFilterMenuPosition();

                    self._filterOutsideReady = true;

                    if (window.lucide) lucide.createIcons();

                });

            },



            onFilterOutsideClick(e) {

                if (!this.filterOpen || !this._filterOutsideReady || !e || !e.target) return;

                var root = this.$refs.atfRoot;

                var menu = this.$refs.atfMenu;

                var target = e.target;

                if (root && root.contains(target)) return;

                if (menu && menu.contains(target)) return;

                this.closeFilterMenu();

            },



            closeFilterMenu() {

                this.filterOpen = false;

                this.filterMenuStyle = '';

                this._filterOutsideReady = false;

            },



            onSearchInput() {

                var self = this;

                this.page = 1;

                if (this._searchTimer) clearTimeout(this._searchTimer);

                this._searchTimer = setTimeout(function () { self.rebuildMatches(); }, 180);

            },



            filterLabel() {

                var def = getFilterDef(this.tabKey, this.filter);

                return (def && def.label) || 'كل الأنواع';

            },



            updateFilterOptions() {

                var self = this;

                var rows = this.getArchiveRows();

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

                this.closeFilterMenu();

                this.page = 1;

                this.rebuildMatches();

            },



            rebuildMatches() {

                var self = this;

                var rows = this.getArchiveRows();

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

                this.cachedMatches = matches;

                this.updateFilterOptions();

                this.$nextTick(function () {

                    if (window.lucide) lucide.createIcons();

                });

            },



            refresh() {

                this.rebuildMatches();

            },



            archiveRowVisible(rowEl) {

                if (!this.pagerReady || !rowEl) return true;

                var matches = this.cachedMatches || [];

                var idx = matches.indexOf(rowEl);

                if (idx < 0) return false;

                var start = (this.page - 1) * this.perPage;

                return idx >= start && idx < start + this.perPage;

            },



            archiveShowEmpty() {

                return this.pagerReady && this.totalCount > 0 && this.matchedCount === 0;

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


