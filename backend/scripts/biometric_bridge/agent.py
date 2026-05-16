#!/usr/bin/env python3
"""
وكيل وسيط: يسحب من جهاز ZKTeco على الشبكة المحلية ويرفع للسيرفر السحابي.

التثبيت (مرة واحدة على PC الفرع):
  pip install -r requirements.txt

الإعداد:
  انسخ config.example.env إلى config.env وعدّل القيم.

التشغيل:
  python agent.py
  python agent.py --once
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from dataclasses import dataclass
from datetime import timezone
from pathlib import Path

try:
    import requests
except ImportError:
    print('ثبّت: pip install requests', file=sys.stderr)
    raise

try:
    from zk import ZK
    from zk.exception import ZKErrorResponse, ZKNetworkError
except ImportError:
    print('ثبّت: pip install pyzk', file=sys.stderr)
    raise

LOG = logging.getLogger('biometric_bridge')

PUNCH_STATUS = {
    0: 'in',
    1: 'out',
    2: 'break_out',
    3: 'break_in',
}


@dataclass
class Config:
    server_url: str
    api_key: str
    device_id: int
    device_ip: str
    device_port: int
    comm_key: int
    agent_id: str
    poll_interval_sec: int
    timeout_sec: int
    incremental: bool


def load_config(path: Path) -> Config:
    data: dict[str, str] = {}
    if not path.exists():
        raise FileNotFoundError(f'ملف الإعداد غير موجود: {path}')
    # utf-8-sig: Notepad على Windows يضيف BOM فيُفسد قراءة SERVER_URL
    for line in path.read_text(encoding='utf-8-sig').splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, val = line.split('=', 1)
        data[key.strip().lstrip('\ufeff')] = val.strip()

    def req(key: str) -> str:
        if key not in data or not data[key]:
            raise ValueError(f'مطلوب في config.env: {key}')
        return data[key]

    return Config(
        server_url=req('SERVER_URL').rstrip('/'),
        api_key=req('AGENT_API_KEY'),
        device_id=int(req('DEVICE_ID')),
        device_ip=req('DEVICE_IP'),
        device_port=int(data.get('DEVICE_PORT', '4370')),
        comm_key=int(data.get('COMM_KEY', '0')),
        agent_id=data.get('AGENT_ID', 'branch-agent-1'),
        poll_interval_sec=int(data.get('POLL_INTERVAL_SEC', '300')),
        timeout_sec=int(data.get('TIMEOUT_SEC', '20')),
        incremental=data.get('INCREMENTAL', 'true').lower() in ('1', 'true', 'yes'),
    )


def punch_type_for_status(status: int | None) -> str:
    if status is None:
        return 'unknown'
    return PUNCH_STATUS.get(status, 'unknown')


def fetch_from_device(cfg: Config) -> tuple[list[dict], list[dict], str | None]:
    conn = None
    try:
        zk = ZK(
            cfg.device_ip,
            port=cfg.device_port,
            timeout=cfg.timeout_sec,
            password=cfg.comm_key,
            force_udp=False,
            ommit_ping=True,
        )
        conn = zk.connect()
        users_out: list[dict] = []
        for user in conn.get_users() or []:
            user_id = getattr(user, 'user_id', None) or getattr(user, 'uid', None)
            if user_id is None:
                continue
            users_out.append({
                'device_user_id': int(user_id),
                'name': (getattr(user, 'name', None) or '').strip(),
                'card': str(getattr(user, 'card', None) or ''),
                'privilege': getattr(user, 'privilege', None),
            })

        punches_out: list[dict] = []
        for rec in conn.get_attendance() or []:
            ts = rec.timestamp
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            status = getattr(rec, 'status', None)
            punches_out.append({
                'device_user_id': int(rec.user_id),
                'punched_at': ts.isoformat(),
                'punch_type': punch_type_for_status(status),
                'verify_mode': getattr(rec, 'punch', None),
                'raw_status': status,
                'device_record_uid': getattr(rec, 'uid', None),
            })
        return punches_out, users_out, None
    except (ZKNetworkError, ZKErrorResponse, OSError, TimeoutError) as exc:
        return [], [], str(exc)
    finally:
        if conn:
            try:
                conn.disconnect()
            except Exception:
                pass


def push_to_server(cfg: Config, punches: list[dict], users: list[dict]) -> dict:
    url = f'{cfg.server_url}/api/v1/attendance/agent/ingest/'
    payload = {
        'device_id': cfg.device_id,
        'agent_id': cfg.agent_id,
        'incremental': cfg.incremental,
        'punches': punches,
        'users': users,
    }
    resp = requests.post(
        url,
        headers={
            'X-Attendance-Agent-Key': cfg.api_key,
            'Content-Type': 'application/json',
        },
        json=payload,
        timeout=180,
    )
    try:
        body = resp.json()
    except Exception:
        body = {'message': resp.text[:500]}
    if resp.status_code >= 400:
        hint = ''
        if resp.status_code in (401, 403):
            hint = (
                ' — تحقق: AGENT_API_KEY في config.env = ATTENDANCE_AGENT_API_KEY في Dokploy '
                '(نفس الحروف، بدون مسافات).'
            )
        raise RuntimeError(f'HTTP {resp.status_code}: {body.get("message", body)}{hint}')
    return body


def run_cycle(cfg: Config) -> bool:
    LOG.info('سحب من الجهاز %s:%s ...', cfg.device_ip, cfg.device_port)
    punches, users, err = fetch_from_device(cfg)
    if err:
        LOG.error('فشل السحب من الجهاز: %s', err)
        return False

    LOG.info('على الجهاز: %s سجل، %s مستخدم — رفع للسيرفر ...', len(punches), len(users))
    try:
        result = push_to_server(cfg, punches, users)
    except Exception as exc:
        LOG.error('فشل الرفع: %s', exc)
        return False

    data = result.get('data', {})
    LOG.info(
        'تم: %s | مستورد %s | مكرر %s',
        result.get('message', 'OK'),
        data.get('imported', 0),
        data.get('skipped_duplicate', 0),
    )
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description='وكيل بصمة HR — فرع → سيرفر')
    parser.add_argument('--config', default=str(Path(__file__).parent / 'config.env'))
    parser.add_argument('--once', action='store_true', help='دورة واحدة ثم خروج')
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s',
        datefmt='%H:%M:%S',
    )

    cfg = load_config(Path(args.config))
    LOG.info('السيرفر: %s | الجهاز: %s (id=%s)', cfg.server_url, cfg.device_ip, cfg.device_id)

    if args.once:
        return 0 if run_cycle(cfg) else 1

    while True:
        run_cycle(cfg)
        LOG.info('انتظار %s ثانية ...', cfg.poll_interval_sec)
        time.sleep(cfg.poll_interval_sec)


if __name__ == '__main__':
    raise SystemExit(main())
