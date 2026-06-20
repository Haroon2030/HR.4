/**
 * نافذة تحميل زجاجية عامة — لكل تبويبات الموقع وطلبات HTMX الجزئية.
 * يجب تحميل هذا الملف قبل alpine.min.js
 */
(function () {
    'use strict';

    var tabBound = false;
    var htmxBound = false;
    var navSafetyTimer = null;

    function hrTabLabel(el) {
        if (!el) return 'القسم';
        var textEl = el.querySelector('.hr-nav-text, .hr-tab-btn > span, .hr-tab > span, span:not(.hr-payroll-tab-count):not(.hr-tab-badge):not(.hr-glass-loading__dots span)');
        var raw = (textEl ? textEl.textContent : el.textContent) || '';
        return raw.replace(/\s+/g, ' ').trim().replace(/\s*\d+\s*$/, '').trim() || 'القسم';
    }

    function hrSameDocumentUrl(a, b) {
        return a.pathname === b.pathname && a.search === b.search;
    }

    function hrHideGlassLoader() {
        clearTimeout(navSafetyTimer);
        navSafetyTimer = null;
        hrDefineGlassLoaderStore();
        if (window.Alpine && Alpine.store('glassLoader')) {
            Alpine.store('glassLoader').hide();
        }
    }

    function hrArmNavLoaderSafety(ms) {
        clearTimeout(navSafetyTimer);
        navSafetyTimer = setTimeout(hrHideGlassLoader, ms || 15000);
    }

    function hrDefineGlassLoaderStore() {
        if (!window.Alpine || typeof Alpine.store !== 'function') return false;
        if (Alpine.store('glassLoader')) return true;

        Alpine.store('glassLoader', {
            visible: false,
            label: 'جاري التحميل',
            hint: 'لحظة واحدة — يتم تجهيز البيانات',
            _seq: 0,
            _abort: null,
            _hideTimer: null,

            show: function (label, hint) {
                if (label) this.label = label;
                if (hint) this.hint = hint;
                clearTimeout(this._hideTimer);
                this.visible = true;
            },

            hide: function () {
                clearTimeout(this._hideTimer);
                this.visible = false;
            },

            scheduleHide: function (ms) {
                var self = this;
                clearTimeout(this._hideTimer);
                this._hideTimer = setTimeout(function () {
                    self.hide();
                }, ms || 220);
            },

            fetchHtml: function (url, targetId, label, hint) {
                var self = this;
                var seq = ++this._seq;
                if (this._abort) this._abort.abort();
                this._abort = new AbortController();
                var signal = this._abort.signal;
                this.show(label || 'جاري التحميل', hint);

                return fetch(url, {
                    method: 'GET',
                    signal: signal,
                    credentials: 'same-origin',
                    headers: {
                        Accept: 'text/html',
                        'X-Requested-With': 'XMLHttpRequest',
                    },
                })
                    .then(function (res) {
                        if (!res.ok) throw new Error('request failed: ' + res.status);
                        return res.text();
                    })
                    .then(function (html) {
                        if (seq !== self._seq) return;
                        var el = document.getElementById(targetId);
                        if (el) el.innerHTML = html;
                        if (window.lucide) lucide.createIcons();
                    })
                    .catch(function (err) {
                        if (err && err.name !== 'AbortError') console.error(err);
                    })
                    .finally(function () {
                        if (seq === self._seq) self.hide();
                    });
            },
        });

        return true;
    }

    function hrBindTabGlassLoader() {
        if (tabBound) return;
        tabBound = true;

        document.addEventListener('click', function (e) {
            if (e.defaultPrevented || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
            if (!window.Alpine || !Alpine.store('glassLoader')) return;

            var tab = e.target.closest(
                '[role="tablist"] [role="tab"], [role="tablist"] .hr-tab-btn, .hr-tabs__bar .hr-tab, .hr-page-tabs__bar .hr-tab-btn'
            );
            if (!tab || tab.getAttribute('data-hr-tab-skip-loader') !== null) return;

            var store = Alpine.store('glassLoader');
            var label = hrTabLabel(tab);

            if (tab.tagName === 'A' && tab.href) {
                try {
                    var url = new URL(tab.href, window.location.href);
                    var current = new URL(window.location.href);
                    if (url.origin !== window.location.origin) return;
                    if (hrSameDocumentUrl(url, current)) return;
                    store.show('جاري تحميل ' + label);
                    store.scheduleHide(350);
                    hrArmNavLoaderSafety(15000);
                } catch (err) { /* ignore */ }
                return;
            }

            if (tab.closest('[data-hr-tab-lazy]')) {
                return;
            }

            if (tab.tagName === 'BUTTON' || tab.getAttribute('role') === 'tab') {
                store.show('جاري تحميل ' + label);
                store.scheduleHide(220);
            }
        }, true);
    }

    function hrBindHtmxGlassLoader() {
        if (htmxBound || !document.body) return;
        htmxBound = true;

        document.body.addEventListener('htmx:beforeRequest', function (evt) {
            var target = evt.detail && evt.detail.target;
            if (!target || target.id === 'notif-dropdown-content') return;
            if (!window.Alpine || !Alpine.store('glassLoader')) return;
            Alpine.store('glassLoader').show('جاري التحميل');
        });

        document.body.addEventListener('htmx:afterRequest', function (evt) {
            var target = evt.detail && evt.detail.target;
            if (!target || target.id === 'notif-dropdown-content') return;
            hrHideGlassLoader();
        });

        document.body.addEventListener('htmx:afterSwap', function (evt) {
            var target = evt.detail && evt.detail.target;
            if (!target || target.id !== 'hr-page-inner') return;
            hrHideGlassLoader();
        });
    }

    function hrInitGlassLoader() {
        hrDefineGlassLoaderStore();
        hrBindTabGlassLoader();
        hrBindHtmxGlassLoader();
        hrHideGlassLoader();
    }

    document.addEventListener('alpine:init', hrInitGlassLoader);
    document.addEventListener('DOMContentLoaded', hrHideGlassLoader);

    window.hrGlassLoader = {
        show: function (label, hint) {
            hrDefineGlassLoaderStore();
            var store = window.Alpine && Alpine.store('glassLoader');
            if (store) store.show(label, hint);
        },
        hide: function () {
            var store = window.Alpine && Alpine.store('glassLoader');
            if (store) store.hide();
        },
        scheduleHide: function (ms) {
            var store = window.Alpine && Alpine.store('glassLoader');
            if (store) store.scheduleHide(ms);
        },
        fetchHtml: function (url, targetId, label, hint) {
            hrDefineGlassLoaderStore();
            var store = window.Alpine && Alpine.store('glassLoader');
            if (store) return store.fetchHtml(url, targetId, label, hint);
            return fetch(url, {
                credentials: 'same-origin',
                headers: { Accept: 'text/html', 'X-Requested-With': 'XMLHttpRequest' },
            })
                .then(function (r) {
                    if (!r.ok) throw new Error('tab request failed');
                    return r.text();
                })
                .then(function (html) {
                    var el = document.getElementById(targetId);
                    if (el) el.innerHTML = html;
                    if (window.lucide) lucide.createIcons();
                });
        },
    };

    window.addEventListener('pageshow', hrHideGlassLoader);
    window.addEventListener('load', hrHideGlassLoader);
})();
