/**
 * نافذة تحميل زجاجية عامة — لكل تبويبات الموقع وطلبات HTMX الجزئية.
 */
(function () {
    'use strict';

    function hrTabLabel(el) {
        if (!el) return 'القسم';
        var textEl = el.querySelector('.hr-nav-text, .hr-tab-btn span, span:not(.hr-payroll-tab-count):not(.hr-glass-loading__dots span)');
        var raw = (textEl ? textEl.textContent : el.textContent) || '';
        return raw.replace(/\s+/g, ' ').trim().split(/\d/)[0].trim() || 'القسم';
    }

    function hrBindTabGlassLoader() {
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
                    if (url.origin === window.location.origin) {
                        store.show('جاري تحميل ' + label);
                    }
                } catch (err) { /* ignore */ }
                return;
            }

            if (tab.closest('[data-hr-tab-lazy]')) {
                return;
            }

            if (tab.tagName === 'BUTTON' || tab.getAttribute('role') === 'tab') {
                store.show('جاري تحميل ' + label);
                store.scheduleHide(200);
            }
        }, true);
    }

    function hrBindHtmxGlassLoader() {
        if (!document.body) return;

        document.body.addEventListener('htmx:beforeRequest', function (evt) {
            var target = evt.detail && evt.detail.target;
            if (!target || target.id === 'notif-dropdown-content') return;
            if (!window.Alpine || !Alpine.store('glassLoader')) return;
            Alpine.store('glassLoader').show('جاري التحميل');
        });

        document.body.addEventListener('htmx:afterRequest', function (evt) {
            var target = evt.detail && evt.detail.target;
            if (!target || target.id === 'notif-dropdown-content') return;
            if (!window.Alpine || !Alpine.store('glassLoader')) return;
            Alpine.store('glassLoader').hide();
        });
    }

    document.addEventListener('alpine:init', function () {
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
                }, ms || 200);
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

        hrBindTabGlassLoader();
        hrBindHtmxGlassLoader();
    });

    window.addEventListener('pageshow', function () {
        if (window.Alpine && Alpine.store('glassLoader')) {
            Alpine.store('glassLoader').hide();
        }
    });
})();
