/**
 * صفحة ملصق باركود الموظف — معاينة وطباعة
 */
(function () {
    'use strict';

    function num(v, fallback) {
        var n = parseFloat(v);
        return isNaN(n) ? fallback : n;
    }

    function intVal(v, fallback) {
        var n = parseInt(v, 10);
        return isNaN(n) ? fallback : n;
    }

    function clamp(v, lo, hi) {
        return Math.min(hi, Math.max(lo, v));
    }

    function readPickerEmployeeId(root) {
        var pickerEl = root.querySelector('.employee-search-picker');
        if (!pickerEl) return '';
        if (window.Alpine) {
            var data = Alpine.$data(pickerEl);
            if (data && data.selected && data.selected.id) {
                return String(data.selected.id);
            }
        }
        var input = pickerEl.querySelector('input[type=hidden]');
        if (!input) return '';
        return String(input.value || input.getAttribute('value') || '').trim();
    }

    function buildPrintUrl(root, employeeId) {
        var raw = root.dataset.barcodePrintUrl || '';
        var tpl = raw.replace('999999', '__ID__');
        var copies = intVal(root.querySelector('#barcode-copies') && root.querySelector('#barcode-copies').value, 1);
        copies = clamp(copies, 1, 50);
        var minW = num(root.dataset.minW, 30);
        var maxW = num(root.dataset.maxW, 150);
        var minH = num(root.dataset.minH, 15);
        var maxH = num(root.dataset.maxH, 100);
        var defW = num(root.dataset.defaultWidth, 100);
        var defH = num(root.dataset.defaultHeight, 40);
        var wInput = root.querySelector('#barcode-width-mm');
        var hInput = root.querySelector('#barcode-height-mm');
        var w = clamp(num(wInput && wInput.value, defW), minW, maxW);
        var h = clamp(num(hInput && hInput.value, defH), minH, maxH);
        try {
            localStorage.setItem('hr_barcode_label_w', String(w));
            localStorage.setItem('hr_barcode_label_h', String(h));
        } catch (e) { /* ignore */ }
        var qs = 'copies=' + encodeURIComponent(copies)
            + '&w=' + encodeURIComponent(w)
            + '&h=' + encodeURIComponent(h);
        return tpl.replace('__ID__', String(employeeId)) + '?' + qs;
    }

    function openBarcodePrint(root) {
        if (!root) return false;
        var id = readPickerEmployeeId(root);
        if (!id) {
            if (window.showToast) showToast('اختر موظفاً أولاً', 'warning');
            return false;
        }
        var url = buildPrintUrl(root, id);
        if (window.hrGlassLoader) window.hrGlassLoader.hide();
        var tab = window.open(url, '_blank', 'noopener,noreferrer');
        if (!tab) window.location.assign(url);
        return true;
    }

    function buildHrBarcodeLabelPage() {
        return {
            copies: 1,
            widthMm: 100,
            heightMm: 40,
            minW: 30,
            maxW: 150,
            minH: 15,
            maxH: 100,
            printTpl: '',

            init: function () {
                var ds = this.$el.dataset;
                var defW = num(ds.defaultWidth, 100);
                var defH = num(ds.defaultHeight, 40);
                this.copies = intVal(ds.defaultCopies, 1);
                this.minW = num(ds.minW, 30);
                this.maxW = num(ds.maxW, 150);
                this.minH = num(ds.minH, 15);
                this.maxH = num(ds.maxH, 100);
                var raw = ds.barcodePrintUrl || '';
                this.printTpl = raw.replace('999999', '__ID__');
                if (ds.urlHasSize === '1') {
                    this.widthMm = clamp(num(ds.initialWidth, defW), this.minW, this.maxW);
                    this.heightMm = clamp(num(ds.initialHeight, defH), this.minH, this.maxH);
                } else {
                    this.widthMm = defW;
                    this.heightMm = defH;
                }
            },

            clamp: clamp,

            resetSize: function () {
                var ds = this.$el.dataset;
                this.widthMm = num(ds.defaultWidth, 100);
                this.heightMm = num(ds.defaultHeight, 40);
                try {
                    localStorage.setItem('hr_barcode_label_w', String(this.widthMm));
                    localStorage.setItem('hr_barcode_label_h', String(this.heightMm));
                } catch (e) { /* ignore */ }
            },

            selectedEmployeeId: function () {
                return readPickerEmployeeId(this.$el);
            },

            openPrint: function () {
                openBarcodePrint(this.$el);
            },
        };
    }

    window.hrBarcodeLabelPage = function () {
        return buildHrBarcodeLabelPage();
    };

    window.hrBarcodeLabelOpenPrint = function (evt) {
        if (evt && typeof evt.preventDefault === 'function') evt.preventDefault();
        var root = document.getElementById('hr-barcode-label-root');
        if (!root) return false;
        if (window.Alpine) {
            var data = Alpine.$data(root);
            if (data && typeof data.openPrint === 'function') {
                data.openPrint();
                return false;
            }
        }
        openBarcodePrint(root);
        return false;
    };

    function registerAlpine() {
        if (!window.Alpine || typeof Alpine.data !== 'function') return;
        Alpine.data('hrBarcodeLabelPage', buildHrBarcodeLabelPage);
    }

    document.addEventListener('alpine:init', registerAlpine);
    registerAlpine();
})();
