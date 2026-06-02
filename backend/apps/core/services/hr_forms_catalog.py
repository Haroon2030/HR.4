"""فهرس النماذج — دمج القائمة الأساسية مع النماذج المطلوبة دون تكرار بالاسم."""

from __future__ import annotations


def _norm_title(title: str) -> str:
    t = (title or '').strip()
    for src, dst in (('أ', 'ا'), ('إ', 'ا'), ('آ', 'ا'), ('ة', 'ه'), ('ى', 'ي')):
        t = t.replace(src, dst)
    t = t.replace('نموذج ', '').replace('نموذج', '').strip()
    return ' '.join(t.split())


PRIMARY_FORM_SPECS = [
    {
        'key': 'permission_request',
        'title': 'نموذج استئذان',
        'description': 'طلب استئذان مختصر',
        'icon': 'clock',
        'color': 'primary',
    },
    {
        'key': 'promotion',
        'title': 'نموذج ترقية',
        'description': 'طلب ترقية موظف',
        'icon': 'trending-up',
        'color': 'emerald',
    },
    {
        'key': 'salary_adjustment',
        'title': 'نموذج تعديل راتب',
        'description': 'تعديل راتب مختصر',
        'icon': 'wallet',
        'color': 'amber',
    },
    {
        'key': 'transfer',
        'title': 'نموذج نقل',
        'description': 'نقل موظف بين الفروع أو الأقسام',
        'icon': 'arrow-left-right',
        'color': 'indigo',
    },
    {
        'key': 'clearance',
        'title': 'نموذج اخلاء طرف',
        'description': 'إخلاء طرف مختصر',
        'icon': 'file-check',
        'color': 'rose',
    },
    {
        'key': 'user_account',
        'title': 'نموذج حساب مستخدم',
        'description': 'طلب أو تعديل حساب مستخدم',
        'icon': 'user-cog',
        'color': 'cyan',
    },
]


def merge_forms_catalog(base_forms: list[dict], primary_specs: list[dict]) -> list[dict]:
    """دمج النماذج: تحديث الموجود بنفس العنوان/المفتاح دون تكرار."""
    by_key = {f['key']: dict(f) for f in base_forms}
    merged: list[dict] = []
    seen_keys: set[str] = set()
    seen_titles: set[str] = set()

    for spec in primary_specs:
        merge_key = spec.get('merge_key') or spec.get('key')
        if not merge_key:
            continue
        base = by_key.get(merge_key)
        if base:
            entry = {**base, **{k: v for k, v in spec.items() if k != 'merge_key'}}
            entry['key'] = merge_key
        else:
            entry = {k: v for k, v in spec.items() if k != 'merge_key'}
            entry.setdefault('icon', 'file-text')
            entry.setdefault('color', 'primary')
            entry.setdefault('description', entry.get('title', ''))

        title_norm = _norm_title(entry['title'])
        if entry['key'] in seen_keys or title_norm in seen_titles:
            continue
        merged.append(entry)
        seen_keys.add(entry['key'])
        seen_titles.add(title_norm)

    for form in base_forms:
        if form['key'] in seen_keys:
            continue
        title_norm = _norm_title(form['title'])
        if title_norm in seen_titles:
            continue
        merged.append(form)
        seen_keys.add(form['key'])
        seen_titles.add(title_norm)

    return merged
