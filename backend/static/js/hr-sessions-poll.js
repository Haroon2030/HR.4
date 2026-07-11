(function () {
    'use strict';

    function syncRevokeAllWrap(panelRoot) {
        var wrap = document.getElementById('hr-sessions-revoke-all-wrap');
        if (!wrap || !panelRoot) {
            return;
        }
        var badge = panelRoot.querySelector('.px-2.py-0\\.5.text-xs.font-bold.bg-primary-100');
        if (!badge) {
            badge = panelRoot.querySelector('[class*="bg-primary-100"]');
        }
        var count = badge ? parseInt(badge.textContent.trim(), 10) : 0;
        if (!count || Number.isNaN(count)) {
            wrap.innerHTML = '';
            return;
        }
        if (wrap.querySelector('form')) {
            return;
        }
    }

    window.hrSessionsPollAfterSwap = function (target) {
        syncRevokeAllWrap(target);
        if (window.lucide && typeof window.lucide.createIcons === 'function') {
            window.lucide.createIcons();
        }
    };

    document.body.addEventListener('htmx:beforeSwap', function (evt) {
        var detail = evt.detail || {};
        var target = detail.target;
        if (!target || target.id !== 'hr-sessions-live') {
            return;
        }
        var xhr = detail.xhr;
        var responseUrl = xhr && xhr.responseURL ? xhr.responseURL : '';
        if (responseUrl.indexOf('/auth/login') !== -1) {
            detail.shouldSwap = false;
            window.location.replace(responseUrl);
        }
    });

    document.body.addEventListener('htmx:afterSwap', function (evt) {
        var target = evt.detail && evt.detail.target;
        if (!target || target.id !== 'hr-sessions-live') {
            return;
        }
        window.hrSessionsPollAfterSwap(target);
    });

    document.addEventListener('visibilitychange', function () {
        if (document.visibilityState !== 'visible' || !window.htmx) {
            return;
        }
        document.body.dispatchEvent(new Event('sessions-refresh'));
    });
})();
