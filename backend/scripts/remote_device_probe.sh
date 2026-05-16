#!/bin/sh
set -e
CONTAINER="${1:-hr-alrsheed-gg7yyl.1.58q2g8jalcb6g4zp3fvaewvzx}"
docker exec "$CONTAINER" python manage.py shell <<'PY'
import socket
from apps.attendance.models import BiometricDevice
from apps.attendance.services.zk_client import probe_device

host, port = "192.168.51.3", 4370
s = socket.socket()
s.settimeout(8)
try:
    s.connect((host, port))
    print(f"TCP {host}:{port} => OK")
except Exception as exc:
    print(f"TCP {host}:{port} => FAIL: {exc}")
finally:
    s.close()

d = BiometricDevice.objects.filter(ip_address=host).first()
if not d:
    print("DEVICE => not found in DB")
else:
    r = probe_device(d, force_mock=False)
    print(f"DEVICE => id={d.pk} name={d.name}")
    print(f"PROBE => ok={r.ok} msg={r.message}")
    if r.ok:
        print(f"STATS => users={r.user_count} attendance={r.attendance_count}")
PY
