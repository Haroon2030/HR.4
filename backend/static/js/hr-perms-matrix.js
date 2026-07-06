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

    window.permsTreeMatrix = function (defaultGroupId) {
        var base = window.permsMatrix();
        return Object.assign({}, base, {
            activeGroupId: defaultGroupId || '',
            openSystems: [],

            initTree() {
                var self = this;
                document.querySelectorAll('.hr-perm-tree__leaf').forEach(function (btn) {
                    if (btn.getAttribute('data-group-id') === self.activeGroupId) {
                        var sysId = btn.getAttribute('data-system-id');
                        if (sysId && self.openSystems.indexOf(sysId) === -1) {
                            self.openSystems.push(sysId);
                        }
                    }
                });
                if (!this.openSystems.length) {
                    var firstSys = document.querySelector('.hr-perm-tree__system-btn');
                    if (firstSys) {
                        var sid = firstSys.getAttribute('data-system-id');
                        if (sid) this.openSystems.push(sid);
                    }
                }
                this.$nextTick(function () {
                    if (window.lucide) lucide.createIcons();
                });
            },

            toggleSystem(systemId) {
                var idx = this.openSystems.indexOf(systemId);
                if (idx >= 0) {
                    this.openSystems.splice(idx, 1);
                } else {
                    this.openSystems.push(systemId);
                }
            },

            isSystemOpen(systemId) {
                return this.openSystems.indexOf(systemId) !== -1;
            },

            isSystemActive(systemId) {
                if (!this.activeGroupId) return false;
                return !!document.querySelector(
                    '.hr-perm-tree__leaf[data-group-id="' + this.activeGroupId + '"][data-system-id="' + systemId + '"]'
                );
            },

            selectGroup(groupId, systemId) {
                this.activeGroupId = groupId;
                if (systemId && this.openSystems.indexOf(systemId) === -1) {
                    this.openSystems.push(systemId);
                }
            },

            groupHasVisibleRows() {
                if (!this.activeGroupId) return true;
                return document.querySelectorAll(
                    '.hr-perm-erp-row[data-group="' + this.activeGroupId + '"]'
                ).length > 0;
            },

            checkColumn(op, state) {
                var group = this.activeGroupId;
                var sel = '.perm-cb[data-op="' + op + '"]:not(:disabled)';
                if (group) {
                    sel = '.perm-cb[data-op="' + op + '"][data-group="' + group + '"]:not(:disabled)';
                }
                document.querySelectorAll(sel).forEach(function (cb) {
                    cb.checked = state;
                });
            },
        });
    };
})();
