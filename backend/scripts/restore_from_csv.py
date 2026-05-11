"""
Restore old DB CSV exports into Neon Postgres.
Handles schema drift: only copies columns that exist in destination.
Usage:
    DATABASE_URL='postgresql://...' python scripts/restore_from_csv.py /tmp/hrdb
"""
import csv
import sys
import os
import psycopg2
from psycopg2.extras import execute_values

DUMP_DIR = sys.argv[1] if len(sys.argv) > 1 else '/tmp/hrdb'
DB_URL = os.environ['DATABASE_URL']

# Order matters (FK dependencies). Skip auth_permission/content_type/migrations (Django-managed).
LOAD_ORDER = [
    'core_company',
    'core_branch',
    'cost_centers',
    'departments',
    'core_nationality',
    'core_profession',
    'core_sponsorship',
    'core_insurance',
    'core_insuranceclass',
    'core_appmodule',
    'core_permission',
    'core_role',
    'core_role_permissions',
    'auth_user',                 # users (admin will be re-inserted; we'll skip duplicates)
    'core_userprofile',
    'core_userprofile_assigned_branches',
    'core_userprofile_denied_permissions',
    'core_userprofile_extra_permissions',
    'setup_bank',
    'setup_building',
    'employees_employmentrequest',
    'employees_employee',
    'employees_employeeleave',
    'employees_employeestatement',
    'core_pendingaction',
    'core_notification',
    'core_systemsettings',
    # historicals (django-simple-history) — load last
    'core_historicalbranch',
    'core_historicalcompany',
    'core_historicalrole',
    'core_historicaluserprofile',
    'core_historicalnationality',
    'core_historicalprofession',
    'core_historicalsponsorship',
    'core_historicalinsurance',
    'core_historicalinsuranceclass',
    'core_historicalpendingaction',
    'core_historicalappmodule',
    'core_historicalpermission',
    'cost_centers_historicalcostcenter',
    'departments_historicaldepartment',
    'employees_historicalemployee',
    'employees_historicalemployeeleave',
    'employees_historicalemployeestatement',
    'employees_historicalemploymentrequest',
    'setup_historicalbank',
    'setup_historicalbuilding',
]

conn = psycopg2.connect(DB_URL)
conn.autocommit = False
cur = conn.cursor()


def get_dest_columns(table):
    """Return {col_name: (data_type, is_nullable, has_default)}"""
    cur.execute(
        "SELECT column_name, data_type, is_nullable, column_default "
        "FROM information_schema.columns "
        "WHERE table_schema='public' AND table_name=%s",
        (table,),
    )
    return {r[0]: (r[1], r[2] == 'YES', r[3] is not None) for r in cur.fetchall()}


def default_for(dtype):
    if dtype == 'boolean':
        return False
    if dtype in ('text', 'character varying', 'character'):
        return ''
    if dtype in ('integer', 'bigint', 'smallint', 'numeric', 'double precision', 'real'):
        return 0
    if dtype.startswith('json'):
        return '{}'
    return None


def convert(val, dtype, nullable):
    """Convert CSV string to proper Python value for given Postgres type."""
    if val == '':
        if not nullable:
            return default_for(dtype)
        return None
    if dtype == 'boolean':
        return val in ('1', 't', 'true', 'True', 'TRUE')
    return val


def load_table(table):
    path = os.path.join(DUMP_DIR, table + '.csv')
    if not os.path.isfile(path):
        print(f'  SKIP (no file): {table}')
        return 0
    dest_cols = get_dest_columns(table)
    if not dest_cols:
        print(f'  SKIP (no table): {table}')
        return 0
    with open(path, encoding='utf-8-sig', newline='') as f:
        reader = csv.reader(f)
        header = next(reader)
        # only columns existing in destination
        keep_idx = [i for i, c in enumerate(header) if c in dest_cols]
        keep_cols = [header[i] for i in keep_idx]
        col_meta = [dest_cols[c] for c in keep_cols]  # (dtype, nullable, has_default)
        # NOT NULL columns missing from CSV with no DB default — must supply default
        csv_set = set(keep_cols)
        extra_cols = []
        extra_meta = []
        for cname, (dtype, nullable, has_default) in dest_cols.items():
            if cname in csv_set:
                continue
            if nullable or has_default:
                continue
            # synthesize default
            extra_cols.append(cname)
            extra_meta.append((dtype, nullable, has_default))
        rows = []
        for row in reader:
            vals = []
            for j, i in enumerate(keep_idx):
                v = row[i] if i < len(row) else ''
                dtype, nullable, _ = col_meta[j]
                vals.append(convert(v, dtype, nullable))
            for dtype, _, _ in extra_meta:
                vals.append(default_for(dtype))
            rows.append(tuple(vals))
        if not rows:
            print(f'  empty: {table}')
            return 0
        all_cols = keep_cols + extra_cols
        col_list = ','.join(f'"{c}"' for c in all_cols)
        sql = f'INSERT INTO "{table}" ({col_list}) VALUES %s ON CONFLICT DO NOTHING'
        cur.execute(f'SAVEPOINT sp_{table}')
        try:
            execute_values(cur, sql, rows, page_size=200)
            cur.execute(f'RELEASE SAVEPOINT sp_{table}')
            print(f'  OK: {table} -> {len(rows)} rows')
            return len(rows)
        except Exception as e:
            print(f'  FAIL: {table}: {e}')
            cur.execute(f'ROLLBACK TO SAVEPOINT sp_{table}')
            return -1


def fix_sequences():
    """Reset all sequences to max(id)+1."""
    cur.execute("""
        SELECT t.table_name, c.column_name
        FROM information_schema.tables t
        JOIN information_schema.columns c
          ON c.table_name=t.table_name AND c.table_schema=t.table_schema
        WHERE t.table_schema='public' AND t.table_type='BASE TABLE'
          AND c.column_name='id'
          AND c.column_default LIKE 'nextval%%'
    """)
    for tbl, col in cur.fetchall():
        try:
            cur.execute(
                f'SELECT setval(pg_get_serial_sequence(%s, %s), '
                f'COALESCE((SELECT MAX("{col}") FROM "{tbl}"), 1), true)',
                (tbl, col),
            )
        except Exception as e:
            print(f'  seq fail {tbl}: {e}')
            conn.rollback()
    conn.commit()


total = 0
cur.execute("SET CONSTRAINTS ALL DEFERRED")
for t in LOAD_ORDER:
    n = load_table(t)
    if n > 0:
        total += n
try:
    conn.commit()
    print(f'\nLoaded {total} rows total. Committed.')
except Exception as e:
    print(f'\nFinal COMMIT FAILED: {e}')
    conn.rollback()
    sys.exit(1)
print('Fixing sequences...')
fix_sequences()
print('Done.')
cur.close()
conn.close()
