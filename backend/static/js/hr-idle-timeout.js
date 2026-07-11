(function () {
    'use strict';

    var body = document.body;
    if (!body || body.dataset.sessionIdleSeconds === undefined) {
        return;
    }

    var idleMs = parseInt(body.dataset.sessionIdleSeconds, 10) * 1000;
    if (!idleMs || idleMs < 60000) {
        return;
    }

    var timer = null;
    var loggingOut = false;

    function getCsrfToken() {
        var meta = document.querySelector('meta[name="csrf-token"]');
        return meta ? meta.getAttribute('content') : '';
    }

    function redirectToLogin() {
        window.location.href = '/auth/login/?idle=1';
    }

    function onIdle() {
        if (loggingOut) {
            return;
        }
        loggingOut = true;
        fetch('/auth/idle-logout/', {
            method: 'POST',
            credentials: 'same-origin',
            headers: {
                'X-CSRFToken': getCsrfToken(),
                'X-Requested-With': 'XMLHttpRequest',
            },
        }).finally(redirectToLogin);
    }

    function resetTimer() {
        if (loggingOut) {
            return;
        }
        clearTimeout(timer);
        timer = setTimeout(onIdle, idleMs);
    }

    ['mousemove', 'mousedown', 'keydown', 'touchstart', 'scroll', 'click'].forEach(function (eventName) {
        document.addEventListener(eventName, resetTimer, { passive: true, capture: true });
    });

    document.addEventListener('visibilitychange', function () {
        if (document.visibilityState === 'visible') {
            resetTimer();
        }
    });

    resetTimer();
})();
