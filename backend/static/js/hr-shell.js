/**
 * حالة الشريط الجانبي — يُحمَّل قبل Alpine.
 */
(function () {
    'use strict';

    var STORAGE_KEY = 'hr-sidebar-open';

    function readSavedSidebarOpen(defaultOpen) {
        try {
            var saved = localStorage.getItem(STORAGE_KEY);
            if (saved === '0') return false;
            if (saved === '1') return true;
        } catch (e) {}
        return defaultOpen;
    }

    function writeSavedSidebarOpen(open) {
        try {
            localStorage.setItem(STORAGE_KEY, open ? '1' : '0');
        } catch (e) {}
    }

    function isDesktopShell() {
        return window.matchMedia('(min-width: 768px)').matches;
    }

    function syncSidebarDom(open) {
        var aside = document.getElementById('hrDesktopSidebar');
        if (!aside) return;
        aside.classList.toggle('hr-sidebar--expanded', !!open);
        aside.classList.toggle('hr-sidebar--collapsed', !open);
    }

    window.hrShellState = function hrShellState() {
        var defaultOpen = isDesktopShell();
        return {
            sidebarOpen: readSavedSidebarOpen(defaultOpen),
            mobileMenuOpen: false,
            toggleSidebar: function () {
                this.sidebarOpen = !this.sidebarOpen;
                writeSavedSidebarOpen(this.sidebarOpen);
                syncSidebarDom(this.sidebarOpen);
            },
            toggleMobileMenu: function () {
                this.mobileMenuOpen = !this.mobileMenuOpen;
            },
            init: function () {
                if (!isDesktopShell()) {
                    this.sidebarOpen = false;
                }
                syncSidebarDom(this.sidebarOpen);
                var self = this;
                window.addEventListener('resize', function () {
                    if (!isDesktopShell()) {
                        self.sidebarOpen = false;
                        return;
                    }
                    self.sidebarOpen = readSavedSidebarOpen(true);
                    syncSidebarDom(self.sidebarOpen);
                });
            },
        };
    };

    function bindSidebarFallback() {
        document.addEventListener('click', function (event) {
            if (window.Alpine) return;
            var collapseBtn = event.target.closest('.hr-topbar-collapse-btn');
            if (!collapseBtn || !isDesktopShell()) return;

            event.preventDefault();
            var aside = document.getElementById('hrDesktopSidebar');
            if (!aside) return;
            var nextOpen = !aside.classList.contains('hr-sidebar--expanded');
            syncSidebarDom(nextOpen);
            writeSavedSidebarOpen(nextOpen);
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', bindSidebarFallback);
    } else {
        bindSidebarFallback();
    }
})();
