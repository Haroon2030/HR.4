"""أيقونات SVG مضمّنة — بدون الاعتماد على lucide.createIcons (لوحة التحكم والشارات)."""
from __future__ import annotations

from django.utils.html import format_html
from django.utils.safestring import SafeString

_SVG_OPEN = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
    'stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" '
    'class="{css_class}" aria-hidden="true">'
)

_GLYPH_PATHS: dict[str, str] = {
    'user-check': (
        '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/>'
        '<circle cx="9" cy="7" r="4"/>'
        '<polyline points="16 11 18 13 22 9"/>'
    ),
    'calendar-off': (
        '<path d="M8 2v4"/>'
        '<path d="M16 2v4"/>'
        '<path d="M21 17V8a2 2 0 0 0-2-2H7a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2h7"/>'
        '<path d="M3 10h18"/>'
        '<path d="m17 22-5-5-5 5"/>'
    ),
    'plane': (
        '<path d="M17.8 19.2 16 11l3.5-3.5C21 6 21.5 4 21 3c-1-.5-3 0-4.5 1.5L13 8 4.8 6.2c-.5-.1-.9.1-1.1.5l-.3.5c-.2.5-.1 1 .3 1.3L9 12l-2 3H4l-1 1 3 2 2 3 1-1v-3l3-2 3.5 5.3c.3.4.8.5 1.3.3l.5-.2c.4-.3.6-.7.5-1.2z"/>'
    ),
    'user-x': (
        '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/>'
        '<circle cx="9" cy="7" r="4"/>'
        '<line x1="17" x2="22" y1="8" y2="13"/>'
        '<line x1="22" x2="17" y1="8" y2="13"/>'
    ),
    'user-minus': (
        '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/>'
        '<circle cx="9" cy="7" r="4"/>'
        '<line x1="22" x2="16" y1="11" y2="11"/>'
    ),
    'user': (
        '<path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2"/>'
        '<circle cx="12" cy="7" r="4"/>'
    ),
    'building-2': (
        '<path d="M6 22V4a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v18Z"/>'
        '<path d="M6 12H4a2 2 0 0 0-2 2v6a2 2 0 0 0 2 2h2"/>'
        '<path d="M18 9h2a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2h-2"/>'
        '<path d="M10 6h4"/>'
        '<path d="M10 10h4"/>'
        '<path d="M10 14h4"/>'
        '<path d="M10 18h4"/>'
    ),
    'globe': (
        '<circle cx="12" cy="12" r="10"/>'
        '<path d="M12 2a14.5 14.5 0 0 0 0 20 14.5 14.5 0 0 0 0-20"/>'
        '<path d="M2 12h20"/>'
    ),
    'flag': (
        '<path d="M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1z"/>'
        '<line x1="4" x2="4" y1="22" y2="15"/>'
    ),
    'mars': (
        '<path d="M16 3h5v5"/>'
        '<path d="m21 3-6.75 6.75"/>'
        '<circle cx="10" cy="14" r="6"/>'
    ),
    'venus': (
        '<path d="M12 15v7"/>'
        '<path d="M9 19h6"/>'
        '<circle cx="12" cy="9" r="6"/>'
    ),
    'users': (
        '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/>'
        '<circle cx="9" cy="7" r="4"/>'
        '<path d="M22 21v-2a4 4 0 0 0-3-3.87"/>'
        '<path d="M16 3.13a4 4 0 0 1 0 7.75"/>'
    ),
    'pie-chart': (
        '<path d="M21.21 15.89A10 10 0 1 1 8 2.83"/>'
        '<path d="M22 12A10 10 0 0 0 12 2v10z"/>'
    ),
    'search': (
        '<circle cx="11" cy="11" r="8"/>'
        '<path d="m21 21-4.3-4.3"/>'
    ),
    'plus': (
        '<path d="M5 12h14"/>'
        '<path d="M12 5v14"/>'
    ),
    'save': (
        '<path d="M15.2 3a2 2 0 0 1 1.4.6l3.8 3.8a2 2 0 0 1 .6 1.4V19a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2z"/>'
        '<path d="M17 21v-7a1 1 0 0 0-1-1H8a1 1 0 0 0-1 1v7"/>'
        '<path d="M7 3v4a1 1 0 0 0 1 1h7"/>'
    ),
    'pencil': (
        '<path d="M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z"/>'
        '<path d="m15 5 4 4"/>'
    ),
    'x': (
        '<path d="M18 6 6 18"/>'
        '<path d="m6 6 12 12"/>'
    ),
    'check': (
        '<path d="M20 6 9 17l-5-5"/>'
    ),
    'refresh-cw': (
        '<path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/>'
        '<path d="M21 3v5h-5"/>'
        '<path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"/>'
        '<path d="M8 16H3v5"/>'
    ),
    'undo-2': (
        '<path d="M9 14 4 9l5-5"/>'
        '<path d="M4 9h10.5a5.5 5.5 0 0 1 5.5 5.5v0a5.5 5.5 0 0 1-5.5 5.5H11"/>'
    ),
    'user-cog': (
        '<circle cx="18" cy="15" r="3"/>'
        '<path d="m16.5 17.5 1 1"/>'
        '<path d="m19.5 14.5 1 1"/>'
        '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/>'
        '<circle cx="9" cy="7" r="4"/>'
    ),
    'printer': (
        '<path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2"/>'
        '<path d="M6 9V3a1 1 0 0 1 1-1h10a1 1 0 0 1 1 1v6"/>'
        '<rect x="6" y="14" width="12" height="8" rx="1"/>'
    ),
    'eye': (
        '<path d="M2.062 12.348a1 1 0 0 1 0-.696 10.75 10.75 0 0 1 19.876 0 1 1 0 0 1 0 .696 10.75 10.75 0 0 1-19.876 0"/>'
        '<circle cx="12" cy="12" r="3"/>'
    ),
    'bar-chart-2': (
        '<path d="M18 20V10"/>'
        '<path d="M12 20V4"/>'
        '<path d="M6 20v-6"/>'
    ),
    'list': (
        '<path d="M3 12h.01"/>'
        '<path d="M3 18h.01"/>'
        '<path d="M3 6h.01"/>'
        '<path d="M8 12h13"/>'
        '<path d="M8 18h13"/>'
        '<path d="M8 6h13"/>'
    ),
    'settings': (
        '<path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"/>'
        '<circle cx="12" cy="12" r="3"/>'
    ),
    'file-spreadsheet': (
        '<path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"/>'
        '<path d="M14 2v4a2 2 0 0 0 2 2h4"/>'
        '<path d="M8 13h2"/>'
        '<path d="M14 13h2"/>'
        '<path d="M8 17h2"/>'
        '<path d="M14 17h2"/>'
    ),
    'unlock': (
        '<rect width="18" height="11" x="3" y="11" rx="2" ry="2"/>'
        '<path d="M7 11V7a5 5 0 0 1 9.9-1"/>'
    ),
    'activity': (
        '<path d="M22 12h-2.48a2 2 0 0 0-1.93 1.46l-2.35 8.36a.25.25 0 0 1-.48 0L9.24 2.18a.25.25 0 0 0-.48 0l-2.35 8.36A2 2 0 0 1 4.49 12H2"/>'
    ),
    'download': (
        '<path d="M12 15V3"/>'
        '<path d="m7 10 5 5 5-5"/>'
        '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>'
    ),
    'key-round': (
        '<path d="M2 18v3c0 .6.4 1 1 1h3"/>'
        '<path d="M16.5 11.5 19 9l-5-5-2.5 2.5"/>'
        '<path d="m12 15 4.5 4.5"/>'
        '<circle cx="5.5" cy="11.5" r="4.5"/>'
    ),
    'trash-2': (
        '<path d="M3 6h18"/>'
        '<path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"/>'
        '<path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"/>'
        '<line x1="10" x2="10" y1="11" y2="17"/>'
        '<line x1="14" x2="14" y1="11" y2="17"/>'
    ),
    'filter': (
        '<polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3"/>'
    ),
    'external-link': (
        '<path d="M15 3h6v6"/>'
        '<path d="M10 14 21 3"/>'
        '<path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>'
    ),
}


def render_lucide_glyph(name: str, css_class: str = '') -> SafeString:
    paths = _GLYPH_PATHS.get(name or '')
    if not paths:
        paths = _GLYPH_PATHS['user']
    return format_html(_SVG_OPEN + paths + '</svg>', css_class=css_class)
