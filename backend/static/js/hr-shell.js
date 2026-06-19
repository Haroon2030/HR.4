/**
 * حالة الشريط الجانبي + القائمة الجوالية + القوائم المنسدلة.
 */
(function () {
    'use strict';

    var STORAGE_KEY = 'hr-sidebar-open';
    var mobileMenuOpen = false;

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
        if (!open) {
            aside.querySelectorAll('.hr-nav-dropdown.is-open').forEach(function (dropdown) {
                dropdown.classList.remove('is-open');
                syncNavDropdownAria(dropdown);
            });
        }
    }

    function syncMobileMenuDom(open) {
        mobileMenuOpen = !!open;
        var overlay = document.getElementById('hrMobileOverlay');
        var drawer = document.getElementById('hrMobileSidebar');
        var menuBtn = document.querySelector('[data-hr-mobile-menu-toggle]');

        if (overlay) {
            overlay.classList.toggle('is-open', mobileMenuOpen);
            overlay.hidden = !mobileMenuOpen;
            overlay.setAttribute('aria-hidden', mobileMenuOpen ? 'false' : 'true');
        }
        if (drawer) {
            drawer.classList.toggle('is-open', mobileMenuOpen);
            drawer.hidden = !mobileMenuOpen;
            drawer.setAttribute('aria-hidden', mobileMenuOpen ? 'false' : 'true');
        }
        if (menuBtn) {
            menuBtn.setAttribute('aria-expanded', mobileMenuOpen ? 'true' : 'false');
        }
        document.body.classList.toggle('overflow-hidden', mobileMenuOpen && !isDesktopShell());
    }

    function toggleMobileMenu() {
        syncMobileMenuDom(!mobileMenuOpen);
    }

    function closeMobileMenu() {
        syncMobileMenuDom(false);
    }

    window.hrCloseMobileMenu = closeMobileMenu;

    function syncNavDropdownAria(dropdown) {
        var trigger = dropdown.querySelector('[data-nav-dropdown-trigger]');
        if (!trigger) return;
        var open = dropdown.classList.contains('is-open');
        trigger.setAttribute('aria-expanded', open ? 'true' : 'false');
    }

    function closeMobileNavDropdowns(exceptDropdown) {
        document.querySelectorAll('.hr-sidebar--mobile-drawer .hr-nav-dropdown.is-open').forEach(function (dropdown) {
            if (dropdown === exceptDropdown) return;
            dropdown.classList.remove('is-open');
            syncNavDropdownAria(dropdown);
        });
    }

    function toggleNavDropdown(dropdown) {
        if (!dropdown) return;
        var willOpen = !dropdown.classList.contains('is-open');
        if (willOpen && dropdown.closest('.hr-sidebar--mobile-drawer')) {
            closeMobileNavDropdowns(dropdown);
        }
        dropdown.classList.toggle('is-open', willOpen);
        syncNavDropdownAria(dropdown);
    }

    function bindNavDropdowns(root) {
        var scope = root && root.querySelectorAll ? root : document;
        scope.querySelectorAll('[data-nav-dropdown-trigger]').forEach(function (trigger) {
            if (trigger.dataset.navDropdownBound === '1') return;
            trigger.dataset.navDropdownBound = '1';
            trigger.addEventListener('click', function (event) {
                event.preventDefault();
                event.stopPropagation();
                toggleNavDropdown(trigger.closest('[data-nav-dropdown]'));
            });
        });

        scope.querySelectorAll('.hr-sidebar--mobile-drawer .hr-nav-sublink').forEach(function (link) {
            if (link.dataset.mobileNavBound === '1') return;
            link.dataset.mobileNavBound = '1';
            link.addEventListener('click', function () {
                closeMobileMenu();
            });
        });

        scope.querySelectorAll('[data-nav-dropdown]').forEach(syncNavDropdownAria);
    }

    function bindMobileMenuControls() {
        document.querySelectorAll('[data-hr-mobile-menu-toggle]').forEach(function (btn) {
            if (btn.dataset.mobileMenuBound === '1') return;
            btn.dataset.mobileMenuBound = '1';
            btn.addEventListener('click', function (event) {
                event.preventDefault();
                event.stopPropagation();
                toggleMobileMenu();
            });
        });

        document.querySelectorAll('[data-hr-mobile-menu-close]').forEach(function (btn) {
            if (btn.dataset.mobileMenuBound === '1') return;
            btn.dataset.mobileMenuBound = '1';
            btn.addEventListener('click', function (event) {
                event.preventDefault();
                event.stopPropagation();
                closeMobileMenu();
            });
        });
    }

    function bindShellControls() {
        bindMobileMenuControls();
        bindNavDropdowns(document);
    }

    window.hrInitNavDropdowns = bindNavDropdowns;

    window.hrShellState = function hrShellState() {
        var defaultOpen = isDesktopShell();
        return {
            sidebarOpen: readSavedSidebarOpen(defaultOpen),
            toggleSidebar: function () {
                this.sidebarOpen = !this.sidebarOpen;
                writeSavedSidebarOpen(this.sidebarOpen);
                syncSidebarDom(this.sidebarOpen);
            },
            init: function () {
                if (!isDesktopShell()) {
                    this.sidebarOpen = false;
                    closeMobileMenu();
                }
                syncSidebarDom(this.sidebarOpen);
                bindShellControls();
                window.addEventListener('hr-close-mobile-menu', closeMobileMenu);
                window.addEventListener('resize', function () {
                    if (!isDesktopShell()) {
                        this.sidebarOpen = false;
                        return;
                    }
                    closeMobileMenu();
                    this.sidebarOpen = readSavedSidebarOpen(true);
                    syncSidebarDom(this.sidebarOpen);
                }.bind(this));
            },
        };
    };

    function bindSidebarFallback() {
        document.addEventListener('click', function (event) {
            var menuBtn = event.target.closest('[data-hr-mobile-menu-toggle]');
            if (menuBtn && !isDesktopShell()) {
                return;
            }

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

    function bootShell() {
        bindShellControls();
        bindSidebarFallback();
        document.addEventListener('keydown', function (event) {
            if (event.key === 'Escape') {
                closeMobileMenu();
            }
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', bootShell);
    } else {
        bootShell();
    }
})();
