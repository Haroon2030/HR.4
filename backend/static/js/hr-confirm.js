/**
 * نافذة تأكيد مدمجة بديلة عن window.confirm.
 * السبب: المتصفحات المدمجة (مثل لوحة المعاينة) تحجب confirm() وتُرجع false فوراً،
 * فتبدو أزرار الحذف/الترحيل وكأنها لا تعمل.
 *
 * الاستخدام: أضف على <form> أو على زر الإرسال:
 *   data-hr-confirm="نص التأكيد"
 *   data-hr-confirm-ok="حذف"            (اختياري — نص زر التأكيد)
 *   data-hr-confirm-variant="danger"    (اختياري — danger | primary)
 */
(function () {
    'use strict';
    if (window.hrConfirm) return;

    var overlay = null;

    function ensureDom() {
        if (overlay) return overlay;
        var css = document.createElement('style');
        css.textContent = [
            '.hr-cf-ov{position:fixed;inset:0;z-index:100000;display:none;align-items:center;justify-content:center;padding:1rem;background:rgba(15,23,42,.45);backdrop-filter:blur(2px)}',
            '.hr-cf-ov.is-open{display:flex}',
            '.hr-cf-box{width:100%;max-width:23rem;background:#fff;border-radius:1rem;box-shadow:0 24px 60px rgba(15,23,42,.3);padding:1.25rem 1.25rem 1rem;direction:rtl;font-family:inherit}',
            '.hr-cf-msg{margin:0 0 1rem;font-size:.95rem;font-weight:800;color:#0f172a;line-height:1.6}',
            '.hr-cf-row{display:flex;gap:.5rem;justify-content:flex-start}',
            '.hr-cf-btn{flex:1;height:2.4rem;border-radius:.65rem;border:1px solid #cbd5e1;background:#fff;color:#1e293b;font-weight:800;font-size:.85rem;cursor:pointer}',
            '.hr-cf-btn:hover{background:#f8fafc}',
            '.hr-cf-btn--ok{border-color:transparent;background:#2563eb;color:#fff}',
            '.hr-cf-btn--ok:hover{background:#1d4ed8}',
            '.hr-cf-btn--danger{background:#dc2626}',
            '.hr-cf-btn--danger:hover{background:#b91c1c}'
        ].join('');
        document.head.appendChild(css);

        overlay = document.createElement('div');
        overlay.className = 'hr-cf-ov';
        overlay.setAttribute('role', 'alertdialog');
        overlay.setAttribute('aria-modal', 'true');
        overlay.innerHTML =
            '<div class="hr-cf-box"><p class="hr-cf-msg"></p>' +
            '<div class="hr-cf-row">' +
            '<button type="button" class="hr-cf-btn hr-cf-btn--ok" data-ok></button>' +
            '<button type="button" class="hr-cf-btn" data-cancel>إلغاء</button>' +
            '</div></div>';
        document.body.appendChild(overlay);
        return overlay;
    }

    function ask(message, opts) {
        opts = opts || {};
        var ov = ensureDom();
        var ok = ov.querySelector('[data-ok]');
        var cancel = ov.querySelector('[data-cancel]');
        ov.querySelector('.hr-cf-msg').textContent = message || 'هل أنت متأكد؟';
        ok.textContent = opts.ok || 'تأكيد';
        ok.className = 'hr-cf-btn hr-cf-btn--ok' + (opts.variant === 'danger' ? ' hr-cf-btn--danger' : '');
        ov.classList.add('is-open');
        cancel.focus();

        return new Promise(function (resolve) {
            function done(value) {
                ov.classList.remove('is-open');
                ok.removeEventListener('click', onOk);
                cancel.removeEventListener('click', onCancel);
                ov.removeEventListener('click', onBackdrop);
                document.removeEventListener('keydown', onKey, true);
                resolve(value);
            }
            function onOk() { done(true); }
            function onCancel() { done(false); }
            function onBackdrop(e) { if (e.target === ov) done(false); }
            function onKey(e) {
                if (e.key === 'Escape') { e.preventDefault(); done(false); }
            }
            ok.addEventListener('click', onOk);
            cancel.addEventListener('click', onCancel);
            ov.addEventListener('click', onBackdrop);
            document.addEventListener('keydown', onKey, true);
        });
    }

    window.hrConfirm = ask;

    // اعتراض إرسال النماذج التي تحمل data-hr-confirm (على النموذج أو على زر الإرسال)
    document.addEventListener('submit', function (e) {
        var form = e.target;
        if (!form || form.tagName !== 'FORM' || form.__hrConfirmed) return;
        var submitter = e.submitter || null;
        var src = (submitter && submitter.dataset.hrConfirm) ? submitter : form;
        var message = src.dataset.hrConfirm;
        if (!message) return;
        e.preventDefault();
        e.stopImmediatePropagation();
        ask(message, { ok: src.dataset.hrConfirmOk, variant: src.dataset.hrConfirmVariant }).then(function (yes) {
            if (!yes) return;
            form.__hrConfirmed = true;
            try {
                if (form.requestSubmit) form.requestSubmit(submitter || undefined);
                else form.submit();
            } finally {
                form.__hrConfirmed = false;
            }
        });
    }, true);
})();
