(function () {
    'use strict';

    window.permsMatrix = function () {
        return {
            checkAll(state) {
                document.querySelectorAll('.perm-cb:not(:disabled)').forEach(function (cb) {
                    cb.checked = state;
                });
            },
            checkColumn(op, state) {
                document.querySelectorAll('.perm-cb[data-op="' + op + '"]:not(:disabled)').forEach(function (cb) {
                    cb.checked = state;
                });
            },
            checkRow(moduleCode, state) {
                document.querySelectorAll('.perm-cb[data-module="' + moduleCode + '"]:not(:disabled)').forEach(function (cb) {
                    cb.checked = state;
                });
            },
            rowAllChecked(moduleCode) {
                var cbs = document.querySelectorAll('.perm-cb[data-module="' + moduleCode + '"]:not(:disabled)');
                if (!cbs.length) return false;
                return Array.from(cbs).every(function (cb) { return cb.checked; });
            },
            selectedCount() {
                return document.querySelectorAll('.perm-cb:checked').length;
            },
        };
    };
})();
