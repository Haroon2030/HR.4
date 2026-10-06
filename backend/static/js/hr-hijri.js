/**
 * تعبئة التاريخ الهجري تلقائياً عند اختيار التاريخ الميلادي.
 *
 * الاستخدام: على حقل التاريخ الميلادي ضع data-hijri-target="<name حقل الهجري>"
 * (الحقلان داخل نفس الـ form). الناتج بصيغة YYYY/MM/DD (تقويم أم القرى).
 * الحقل الهجري يبقى قابلاً للتعديل ليطابق الهوية؛ يُعاد حسابه فقط عند تغيير الميلادي.
 */
(function () {
    'use strict';

    var formatter = null;
    try {
        formatter = new Intl.DateTimeFormat('en-u-ca-islamic-umalqura-nu-latn', {
            day: 'numeric', month: 'numeric', year: 'numeric', timeZone: 'UTC',
        });
    } catch (e) {
        return; // المتصفح لا يدعم التقويم الهجري — يبقى الإدخال يدوياً
    }

    function pad(n) { return (n < 10 ? '0' : '') + n; }

    function toHijri(iso) {
        var m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso || '');
        if (!m) return '';
        var parts = formatter.formatToParts(new Date(Date.UTC(+m[1], +m[2] - 1, +m[3])));
        var out = {};
        parts.forEach(function (p) { out[p.type] = p.value; });
        if (!out.year || !out.month || !out.day) return '';
        return out.year + '/' + pad(+out.month) + '/' + pad(+out.day);
    }

    function sync(source) {
        var form = source.form;
        var name = source.getAttribute('data-hijri-target');
        var target = form && name ? form.elements[name] : null;
        if (!target) return;
        target.value = toHijri(source.value);
        target.dispatchEvent(new Event('input', { bubbles: true }));
    }

    ['change', 'input'].forEach(function (evt) {
        document.addEventListener(evt, function (e) {
            var t = e.target;
            if (t && t.matches && t.matches('input[data-hijri-target]')) sync(t);
        });
    });
})();
