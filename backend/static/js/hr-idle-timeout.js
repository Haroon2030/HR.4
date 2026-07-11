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

    var loggingOut = false;
    var lastActivityAt = Date.now();
    var timer = null;

    function getCsrfToken() {
        var meta = document.querySelector('meta[name="csrf-token"]');
        return meta ? meta.getAttribute('content') : '';
    }

    function redirectToLogin() {
        window.location.replace('/auth/login/?idle=1');
    }

    function onIdle() {
        if (loggingOut) {
            return;
        }
        if (Date.now() - lastActivityAt < idleMs) {
            scheduleCheck();
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

    function markActivity() {
        if (loggingOut) {
            return;
        }
        lastActivityAt = Date.now();
        scheduleCheck();
    }

    function scheduleCheck() {
        clearTimeout(timer);
        var remaining = idleMs - (Date.now() - lastActivityAt);
        timer = setTimeout(onIdle, Math.max(remaining, 1000));
    }

    ['mousemove', 'mousedown', 'keydown', 'touchstart', 'scroll', 'click'].forEach(function (eventName) {
        document.addEventListener(eventName, markActivity, { passive: true, capture: true });
    });

    document.addEventListener('visibilitychange', function () {
        if (document.visibilityState === 'visible') {
            onIdle();
        }
    });

    setInterval(function () {
        if (Date.now() - lastActivityAt >= idleMs) {
            onIdle();
        }
    }, 60000);

    scheduleCheck();
})();
