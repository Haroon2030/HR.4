/**
 * منتقي تاريخ HR — تقويم مخصص RTL يطابق تصميم النظام.
 */
(function () {
    'use strict';

    var MONTHS_AR = [
        'يناير', 'فبراير', 'مارس', 'أبريل', 'مايو', 'يونيو',
        'يوليو', 'أغسطس', 'سبتمبر', 'أكتوبر', 'نوفمبر', 'ديسمبر'
    ];
    var WEEKDAYS_AR = ['ح', 'ن', 'ث', 'ر', 'خ', 'ج', 'س'];

    var openPicker = null;

    function pad(n) {
        return n < 10 ? '0' + n : String(n);
    }

    function isoToDisplay(iso) {
        if (!iso) return '';
        var p = iso.split('-');
        if (p.length !== 3) return '';
        return p[0] + '/' + p[1] + '/' + p[2];
    }

    function parseIso(iso) {
        if (!iso) return null;
        var d = new Date(iso + 'T12:00:00');
        return isNaN(d.getTime()) ? null : d;
    }

    function formatIso(d) {
        return d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate());
    }

    function sameDay(a, b) {
        return a && b &&
            a.getFullYear() === b.getFullYear() &&
            a.getMonth() === b.getMonth() &&
            a.getDate() === b.getDate();
    }

    var YEAR_MIN = 1900;
    var YEAR_MAX = 2100;

    function clampYear(year) {
        var y = parseInt(year, 10);
        if (isNaN(y)) return null;
        if (y < YEAR_MIN) return YEAR_MIN;
        if (y > YEAR_MAX) return YEAR_MAX;
        return y;
    }

    function commitYearInput(picker, input) {
        if (!picker || !input) return;
        var raw = (input.value || '').trim();
        if (!raw || raw.length < 4) {
            input.value = picker.dataset.viewYear || String(new Date().getFullYear());
            return;
        }
        var y = clampYear(raw);
        if (y === null) {
            input.value = picker.dataset.viewYear || String(new Date().getFullYear());
            return;
        }
        picker.dataset.viewYear = String(y);
        input.value = String(y);
        if (picker.dataset.viewMode === 'months') {
            renderMonthsView(picker);
        } else {
            renderCalendar(picker);
        }
    }

    function bindYearInput(picker, input) {
        if (!input || input.dataset.hrYearBound === '1') return;
        input.dataset.hrYearBound = '1';

        input.addEventListener('click', function (e) {
            e.stopPropagation();
        });

        input.addEventListener('keydown', function (e) {
            e.stopPropagation();
            if (e.key === 'Enter') {
                e.preventDefault();
                commitYearInput(picker, input);
                input.blur();
            }
            if (e.key === 'Escape') {
                e.preventDefault();
                input.value = picker.dataset.viewYear || '';
                input.blur();
            }
        });

        input.addEventListener('input', function () {
            input.value = input.value.replace(/\D/g, '').slice(0, 4);
        });

        input.addEventListener('blur', function () {
            commitYearInput(picker, input);
        });
    }

    function syncYearInput(picker, year) {
        var pop = getPop(picker);
        if (!pop) return;
        var yearInput = pop.querySelector('.hr-date-picker__year-label');
        if (yearInput && document.activeElement !== yearInput) {
            yearInput.value = String(year);
        }
    }

        return picker._hrDatePop || null;
    }

    function getField(picker) {
        return picker._hrDateField || null;
    }

    function closePicker(picker) {
        if (!picker) return;
        var pop = getPop(picker);
        if (!pop) return;
        pop.hidden = true;
        picker.dataset.viewMode = 'days';
        if (pop.parentNode === document.body) {
            picker.appendChild(pop);
        }
        pop.style.cssText = '';
        picker.classList.remove('is-open');
        if (openPicker === picker) openPicker = null;
    }

    function closeAll(except) {
        document.querySelectorAll('.hr-date-picker.is-open').forEach(function (p) {
            if (except && p === except) return;
            closePicker(p);
        });
    }

    function positionPopover(picker) {
        var pop = getPop(picker);
        var field = getField(picker);
        if (!pop || !field) return;

        var rect = field.getBoundingClientRect();
        var popW = 300;
        if (pop.parentNode !== document.body) {
            document.body.appendChild(pop);
        }
        pop.style.position = 'fixed';
        pop.style.width = popW + 'px';
        pop.style.zIndex = '10070';
        pop.style.right = Math.round(window.innerWidth - rect.right) + 'px';
        pop.style.left = 'auto';

        var topAbove = rect.top - pop.offsetHeight - 8;
        if (topAbove >= 8) {
            pop.style.top = Math.round(topAbove) + 'px';
            pop.style.bottom = 'auto';
        } else {
            pop.style.top = Math.round(rect.bottom + 8) + 'px';
            pop.style.bottom = 'auto';
        }
    }

    function syncDisplay(picker) {
        var native = picker.querySelector('.hr-date-picker__native');
        var display = picker.querySelector('.hr-date-picker__display');
        if (!native || !display) return;
        display.value = isoToDisplay(native.value);
        display.classList.toggle('is-empty', !native.value);
    }

    function syncAllDisplays() {
        document.querySelectorAll('.hr-date-picker').forEach(syncDisplay);
    }

    function syncNative(picker, iso) {
        var native = picker.querySelector('.hr-date-picker__native');
        var display = picker.querySelector('.hr-date-picker__display');
        if (!native || !display) return;
        native.value = iso || '';
        display.value = isoToDisplay(iso);
        display.classList.toggle('is-empty', !iso);
        native.dispatchEvent(new Event('input', { bubbles: true }));
        native.dispatchEvent(new Event('change', { bubbles: true }));
    }

    function showDaysView(picker) {
        var pop = getPop(picker);
        if (!pop) return;
        picker.dataset.viewMode = 'days';
        var days = pop.querySelector('.hr-date-picker__days-view');
        var months = pop.querySelector('.hr-date-picker__months-view');
        if (days) days.hidden = false;
        if (months) months.hidden = true;
    }

    function showMonthsView(picker) {
        var pop = getPop(picker);
        if (!pop) return;
        picker.dataset.viewMode = 'months';
        renderMonthsView(picker);
        var days = pop.querySelector('.hr-date-picker__days-view');
        var months = pop.querySelector('.hr-date-picker__months-view');
        if (days) days.hidden = true;
        if (months) months.hidden = false;
        positionPopover(picker);
    }

    function renderMonthsView(picker) {
        var pop = getPop(picker);
        if (!pop) return;

        var viewYear = parseInt(picker.dataset.viewYear, 10);
        var viewMonth = parseInt(picker.dataset.viewMonth, 10);
        syncYearInput(picker, viewYear);

        var grid = pop.querySelector('.hr-date-picker__months-grid');
        if (!grid) return;
        grid.innerHTML = '';

        MONTHS_AR.forEach(function (name, idx) {
            var btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'hr-date-picker__month';
            btn.textContent = name;
            if (idx === viewMonth) btn.classList.add('is-active');
            btn.addEventListener('click', function (e) {
                e.preventDefault();
                e.stopPropagation();
                picker.dataset.viewMonth = String(idx);
                showDaysView(picker);
                renderCalendar(picker);
                positionPopover(picker);
            });
            grid.appendChild(btn);
        });
    }

    function renderCalendar(picker) {
        var pop = getPop(picker);
        var native = picker.querySelector('.hr-date-picker__native');
        if (!pop || !native) return;

        var viewYear = parseInt(picker.dataset.viewYear, 10);
        var viewMonth = parseInt(picker.dataset.viewMonth, 10);
        var selected = parseIso(native.value);
        var today = new Date();
        today.setHours(12, 0, 0, 0);

        var title = pop.querySelector('.hr-date-picker__title');
        if (title) {
            title.textContent = MONTHS_AR[viewMonth] + ' ' + viewYear;
        }

        var grid = pop.querySelector('.hr-date-picker__grid');
        if (!grid) return;
        grid.innerHTML = '';

        var first = new Date(viewYear, viewMonth, 1, 12, 0, 0, 0);
        var startDow = first.getDay();
        var daysInMonth = new Date(viewYear, viewMonth + 1, 0).getDate();

        var min = native.min ? parseIso(native.min) : null;
        var max = native.max ? parseIso(native.max) : null;

        var cell = 0;
        var totalCells = Math.ceil((startDow + daysInMonth) / 7) * 7;

        for (var i = 0; i < totalCells; i++) {
            var btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'hr-date-picker__day';

            if (i < startDow || cell >= daysInMonth) {
                btn.className += ' is-outside';
                btn.tabIndex = -1;
                btn.textContent = '';
                btn.disabled = true;
            } else {
                cell++;
                var d = new Date(viewYear, viewMonth, cell, 12, 0, 0, 0);
                btn.textContent = String(cell);
                btn.dataset.iso = formatIso(d);

                if (sameDay(d, selected)) btn.classList.add('is-selected');
                if (sameDay(d, today)) btn.classList.add('is-today');

                if (min && d < min) btn.disabled = true;
                if (max && d > max) btn.disabled = true;

                btn.addEventListener('click', function (e) {
                    e.preventDefault();
                    e.stopPropagation();
                    var iso = this.dataset.iso;
                    syncNative(picker, iso);
                    closePicker(picker);
                });
            }
            grid.appendChild(btn);
        }
    }

    function setViewMonth(picker, year, month) {
        if (month < 0) { month = 11; year--; }
        if (month > 11) { month = 0; year++; }
        picker.dataset.viewYear = String(year);
        picker.dataset.viewMonth = String(month);
        if (picker.dataset.viewMode === 'months') {
            renderMonthsView(picker);
        } else {
            renderCalendar(picker);
        }
    }

    function openDatePicker(picker) {
        var pop = getPop(picker);
        var field = getField(picker);
        var native = picker.querySelector('.hr-date-picker__native');
        if (!pop || !field || !native || native.disabled || native.readOnly) return;

        closeAll(picker);

        var base = parseIso(native.value) || new Date();
        picker.dataset.viewYear = String(base.getFullYear());
        picker.dataset.viewMonth = String(base.getMonth());
        picker.dataset.viewMode = 'days';
        showDaysView(picker);

        renderCalendar(picker);
        pop.hidden = false;
        picker.classList.add('is-open');
        positionPopover(picker);
        openPicker = picker;

        if (window.lucide) {
            lucide.createIcons({ attrs: { 'stroke-width': 2 } });
        }
    }

    function wrapInput(input) {
        if (!input || input.dataset.hrDateReady === '1') return;
        if (input.closest('.hr-date-picker')) return;
        if (input.dataset.hrDateNative === '1') return;

        input.dataset.hrDateReady = '1';

        var picker = document.createElement('div');
        picker.className = 'hr-date-picker';

        var field = document.createElement('div');
        field.className = 'hr-date-picker__field';

        var display = document.createElement('input');
        display.type = 'text';
        display.className = 'hr-date-picker__display';
        display.placeholder = input.getAttribute('data-placeholder') || 'YYYY/MM/DD';
        display.autocomplete = 'off';
        display.inputMode = 'numeric';
        display.dir = 'ltr';
        display.readOnly = true;
        display.tabIndex = input.tabIndex >= 0 ? input.tabIndex : 0;

        var icon = document.createElement('span');
        icon.className = 'hr-date-picker__icon';
        icon.innerHTML = '<i data-lucide="calendar"></i>';

        field.appendChild(display);
        field.appendChild(icon);

        input.classList.add('hr-date-picker__native');
        input.tabIndex = -1;

        var pop = document.createElement('div');
        pop.className = 'hr-date-picker__popover hr-sidebar-panel';
        pop.hidden = true;
        pop.innerHTML =
            '<div class="hr-date-picker__days-view">' +
            '  <div class="hr-date-picker__header">' +
            '    <button type="button" class="hr-date-picker__nav hr-date-picker__nav--prev" aria-label="الشهر السابق"><i data-lucide="chevron-right"></i></button>' +
            '    <button type="button" class="hr-date-picker__title" aria-label="اختيار الشهر والسنة"></button>' +
            '    <button type="button" class="hr-date-picker__nav hr-date-picker__nav--next" aria-label="الشهر التالي"><i data-lucide="chevron-left"></i></button>' +
            '  </div>' +
            '  <div class="hr-date-picker__weekdays">' +
            WEEKDAYS_AR.map(function (d) {
                return '<span class="hr-date-picker__weekday">' + d + '</span>';
            }).join('') +
            '  </div>' +
            '  <div class="hr-date-picker__grid"></div>' +
            '</div>' +
            '<div class="hr-date-picker__months-view" hidden>' +
            '  <div class="hr-date-picker__header hr-date-picker__header--year">' +
            '    <button type="button" class="hr-date-picker__nav hr-date-picker__nav--year-prev" aria-label="السنة السابقة"><i data-lucide="chevron-right"></i></button>' +
            '    <input type="text" inputmode="numeric" pattern="[0-9]*" maxlength="4" class="hr-date-picker__year-label" aria-label="السنة" dir="ltr">' +
            '    <button type="button" class="hr-date-picker__nav hr-date-picker__nav--year-next" aria-label="السنة التالية"><i data-lucide="chevron-left"></i></button>' +
            '  </div>' +
            '  <div class="hr-date-picker__months-grid"></div>' +
            '</div>';

        picker._hrDatePop = pop;
        picker._hrDateField = field;

        input.parentNode.insertBefore(picker, input);
        picker.appendChild(field);
        picker.appendChild(input);
        picker.appendChild(pop);

        display.value = isoToDisplay(input.value);
        display.classList.toggle('is-empty', !input.value);

        pop.addEventListener('click', function (e) {
            e.stopPropagation();
        });

        field.addEventListener('click', function (e) {
            e.preventDefault();
            e.stopPropagation();
            if (input.disabled || input.readOnly) return;
            if (picker.classList.contains('is-open')) closePicker(picker);
            else openDatePicker(picker);
        });

        display.addEventListener('keydown', function (e) {
            if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                openDatePicker(picker);
            }
            if (e.key === 'Escape') closePicker(picker);
        });

        pop.querySelector('.hr-date-picker__nav--prev').addEventListener('click', function (e) {
            e.preventDefault();
            e.stopPropagation();
            var y = parseInt(picker.dataset.viewYear, 10);
            var m = parseInt(picker.dataset.viewMonth, 10);
            setViewMonth(picker, y, m - 1);
            positionPopover(picker);
        });

        pop.querySelector('.hr-date-picker__nav--next').addEventListener('click', function (e) {
            e.preventDefault();
            e.stopPropagation();
            var y = parseInt(picker.dataset.viewYear, 10);
            var m = parseInt(picker.dataset.viewMonth, 10);
            setViewMonth(picker, y, m + 1);
            positionPopover(picker);
        });

        pop.querySelector('.hr-date-picker__title').addEventListener('click', function (e) {
            e.preventDefault();
            e.stopPropagation();
            if (picker.dataset.viewMode === 'months') showDaysView(picker);
            else showMonthsView(picker);
            positionPopover(picker);
        });

        pop.querySelector('.hr-date-picker__nav--year-prev').addEventListener('click', function (e) {
            e.preventDefault();
            e.stopPropagation();
            var y = parseInt(picker.dataset.viewYear, 10) - 1;
            picker.dataset.viewYear = String(y);
            renderMonthsView(picker);
            positionPopover(picker);
        });

        pop.querySelector('.hr-date-picker__nav--year-next').addEventListener('click', function (e) {
            e.preventDefault();
            e.stopPropagation();
            var y = parseInt(picker.dataset.viewYear, 10) + 1;
            picker.dataset.viewYear = String(y);
            renderMonthsView(picker);
            positionPopover(picker);
        });

        var yearInput = pop.querySelector('.hr-date-picker__year-label');
        if (yearInput) bindYearInput(picker, yearInput);

        input.addEventListener('change', function () {
            display.value = isoToDisplay(input.value);
            display.classList.toggle('is-empty', !input.value);
        });
    }

    function init(root) {
        var scope = root && root.querySelectorAll ? root : document;
        if (scope === document) {
            document.querySelectorAll('body.hr-app input[type="date"]').forEach(wrapInput);
        } else {
            scope.querySelectorAll('input[type="date"]').forEach(function (input) {
                if (input.closest('body.hr-app')) wrapInput(input);
            });
        }
        syncAllDisplays();
        if (window.lucide) {
            lucide.createIcons({ attrs: { 'stroke-width': 2 } });
        }
    }

    document.addEventListener('click', function (e) {
        if (e.target.closest('.hr-date-picker')) return;
        if (e.target.closest('.hr-date-picker__popover')) return;
        closeAll(null);
    });

    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') closeAll(null);
    });

    window.addEventListener('resize', function () { closeAll(null); });
    window.addEventListener('scroll', function () { closeAll(null); }, true);

    window.hrInitDatePickers = init;

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function () { init(document); });
    } else {
        init(document);
    }

    document.addEventListener('alpine:initialized', function () {
        syncAllDisplays();
    });
})();
