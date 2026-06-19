"""Audit templates for duplicate HTML name= attributes in the same file.

Run: python backend/scripts/audit_duplicate_form_names.py

Flags pairs that likely live in the SAME form (heuristic: within 80 lines).
Separate <form> blocks are reported as INFO only.

Safe patterns (ignored):
- Multiple submit buttons: name="action" with different value=
- Known mutual-exclusion components (insurance_deduction_rate if/else)
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

TEMPLATES = Path(__file__).resolve().parents[1] / 'templates'
NAME_RE = re.compile(r'\bname=["\']([^"\']+)["\']', re.I)
FORM_RE = re.compile(r'<form\b', re.I)
FORM_END_RE = re.compile(r'</form>', re.I)
SUBMIT_ACTION_RE = re.compile(
    r'<(?:button|input)[^>]*\bname=["\']action["\'][^>]*\bvalue=["\']([^"\']+)["\']',
    re.I,
)

# Files/branches where duplicate grep is a false positive (mutually exclusive {% if %})
MUTUAL_EXCLUSION = {
    'components/insurance_deduction_rate_field.html': {'insurance_deduction_rate'},
    'pages/employees/_salary_tab_content.html': {'insurance_deduction_rate'},
    'components/bank_transfer_panel.html': {'bank', 'account_type'},
}


def _line_form_index(line_no: int, form_starts: list[int], form_ends: list[int]) -> int | None:
    for i, start in enumerate(form_starts):
        end = form_ends[i] if i < len(form_ends) else 10**9
        if start <= line_no <= end:
            return i
    return None


def audit_file(path: Path) -> list[dict]:
    text = path.read_text(encoding='utf-8', errors='replace')
    lines = text.splitlines()
    form_starts = [i + 1 for i, ln in enumerate(lines) if FORM_RE.search(ln)]
    form_ends = [i + 1 for i, ln in enumerate(lines) if FORM_END_RE.search(ln)]

    hits: list[tuple[int, str, int | None]] = []
    for i, ln in enumerate(lines, 1):
        for name in NAME_RE.findall(ln):
            if '{' in name or '{{' in name:
                continue
            hits.append((i, name, _line_form_index(i, form_starts, form_ends)))

    by_name: dict[str, list[tuple[int, int | None]]] = {}
    for line_no, name, form_idx in hits:
        by_name.setdefault(name, []).append((line_no, form_idx))

    findings = []
    for name, occurrences in by_name.items():
        if len(occurrences) < 2:
            continue
        form_ids = {f for _, f in occurrences}
        same_form = len(form_ids) == 1 and None not in form_ids
        findings.append({
            'name': name,
            'count': len(occurrences),
            'lines': [ln for ln, _ in occurrences],
            'same_form': same_form,
            'forms': sorted(form_ids, key=lambda x: (x is None, x or -1)),
        })
    return findings


def _is_submit_action_duplicate(path: Path, text: str, name: str) -> bool:
    if name != 'action':
        return False
    values = SUBMIT_ACTION_RE.findall(text)
    return len(values) >= 2 and len(set(values)) >= 2


def _is_mutual_exclusion(path: Path, name: str) -> bool:
    rel = str(path.relative_to(TEMPLATES)).replace('\\', '/')
    return name in MUTUAL_EXCLUSION.get(rel, set())


def main() -> int:
    critical = []
    review = []
    for path in sorted(TEMPLATES.rglob('*.html')):
        text = path.read_text(encoding='utf-8', errors='replace')
        findings = audit_file(path)
        if not findings:
            continue
        rel = path.relative_to(TEMPLATES)
        for f in findings:
            if f['same_form'] and f['name'] == 'action' and f['count'] >= 2:
                continue  # multiple submit buttons (save / save_and_approve)
            if _is_mutual_exclusion(path, f['name']):
                continue
            if f['same_form'] and _is_submit_action_duplicate(path, text, f['name']):
                continue
            entry = (str(rel), f)
            if f['same_form']:
                critical.append(entry)
            else:
                review.append(entry)

    print('CRITICAL (same <form>, duplicate name):')
    if not critical:
        print('  (none)')
    for rel, f in critical:
        print(f"  {rel}: name={f['name']!r} x{f['count']} lines={f['lines']}")

    print('\nREVIEW (duplicate name, different forms or outside form):')
    if not review:
        print('  (none)')
    for rel, f in review:
        print(f"  {rel}: name={f['name']!r} x{f['count']} lines={f['lines']} forms={f['forms']}")

    return 1 if critical else 0


if __name__ == '__main__':
    sys.exit(main())
