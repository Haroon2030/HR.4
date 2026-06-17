#!/usr/bin/env python3
"""
وكيل وسيط: يسحب من أجهزة ZKTeco ويرفع للسيرفر السحابي.

جهاز واحد: config.env (DEVICE_ID + DEVICE_IP)
عدة أجهزة من مكان واحد: devices.list (يتطلب وصول الشبكة لكل IP — VPN/Tailscale)

  pip install -r requirements.txt
  python agent.py --once
  python agent.py --probe
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import logging
import sys
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
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

# يطابق حدود السيرفر في agent_ingest.py
MAX_PAST_DAYS_INCREMENTAL = 93
MAX_PAST_DAYS_FULL_SYNC = 365
MAX_FUTURE_MINUTES = 10
WATERMARK_BUFFER_SECONDS = 60


@dataclass
class PullRequest:
    device_id: int
    date_from: date | None = None
    date_to: date | None = None


@dataclass
class AgentSettings:
    server_url: str
    api_key: str
    agent_id: str
    poll_interval_sec: int
    timeout_sec: int
    incremental: bool
    sync_on_request_only: bool = True


@dataclass
class DeviceTarget:
    device_id: int
    device_ip: str
    device_port: int
    comm_key: int
    label: str = ''
    api_key: str = ''


def _api_key_for(device: DeviceTarget | None, settings: AgentSettings) -> str:
    if device and device.api_key:
        return device.api_key
    return settings.api_key


def load_device_keys(config_path: Path) -> dict[int, str]:
    """مفاتيح وكيل لكل جهاز — device_keys.env (سطر: device_id=KEY)."""
    keys_path = config_path.parent / 'device_keys.env'
    result: dict[int, str] = {}
    for key, val in _parse_env_file(keys_path).items():
        if key.isdigit() and val:
            result[int(key)] = val
    return result


def bind_device_api_keys(
    devices: list[DeviceTarget],
    settings: AgentSettings,
    config_path: Path,
) -> list[DeviceTarget]:
    keys_map = load_device_keys(config_path)
    bound: list[DeviceTarget] = []
    for device in devices:
        api_key = keys_map.get(device.device_id, '')
        if not api_key and len(devices) == 1:
            api_key = settings.api_key
        bound.append(
            DeviceTarget(
                device_id=device.device_id,
                device_ip=device.device_ip,
                device_port=device.device_port,
                comm_key=device.comm_key,
                label=device.label,
                api_key=api_key,
            )
        )
    if len(bound) > 1:
        missing = [d.device_id for d in bound if not d.api_key]
        if missing:
            raise ValueError(
                'عدة أجهزة تتطلب مفتاحاً لكل جهاز في device_keys.env '
                f'(الناقص: {", ".join(str(i) for i in missing)}). '
                'ولّد «مفتاح وكيل» من HR لكل جهاز — أو استخدم PC منفصل لكل فرع.'
            )
    return bound


def _parse_env_file(path: Path) -> dict[str, str]:
    data: dict[str, str] = {}
    if not path.exists():
        return data
    for line in path.read_text(encoding='utf-8-sig').splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, val = line.split('=', 1)
        data[key.strip().lstrip('\ufeff')] = val.strip()
    return data


def load_settings(path: Path) -> AgentSettings:
    data = _parse_env_file(path)
    if not path.exists():
        raise FileNotFoundError(f'ملف الإعداد غير موجود: {path}')

    def req(key: str) -> str:
        if key not in data or not data[key]:
            raise ValueError(f'مطلوب في config.env: {key}')
        return data[key]

    return AgentSettings(
        server_url=req('SERVER_URL').rstrip('/'),
        api_key=req('AGENT_API_KEY'),
        agent_id=data.get('AGENT_ID', 'central-agent'),
        poll_interval_sec=int(data.get('POLL_INTERVAL_SEC', '300')),
        timeout_sec=int(data.get('TIMEOUT_SEC', '20')),
        incremental=data.get('INCREMENTAL', 'true').lower() in ('1', 'true', 'yes'),
        sync_on_request_only=data.get('SYNC_ON_REQUEST_ONLY', 'true').lower()
        in ('1', 'true', 'yes'),
    )


def _parse_device_line(line: str, line_no: int) -> DeviceTarget | None:
    line = line.strip()
    if not line or line.startswith('#'):
        return None
    # device_id ip [port] [comm_key] [label...]
    parts = line.replace(';', ' ').split()
    if len(parts) < 2:
        raise ValueError(f'سطر {line_no} في devices.list غير صالح: {line}')
    device_id = int(parts[0])
    device_ip = parts[1]
    port = int(parts[2]) if len(parts) > 2 else 4370
    comm_key = int(parts[3]) if len(parts) > 3 else 0
    label = ' '.join(parts[4:]) if len(parts) > 4 else ''
    return DeviceTarget(
        device_id=device_id,
        device_ip=device_ip,
        device_port=port,
        comm_key=comm_key,
        label=label,
    )


def _sort_devices(devices: list[DeviceTarget]) -> list[DeviceTarget]:
    return sorted(devices, key=lambda d: d.device_id)


def _tcp_reachable(device: DeviceTarget, *, timeout_sec: int = 5) -> bool:
    import socket

    sock = socket.socket()
    sock.settimeout(timeout_sec)
    try:
        sock.connect((device.device_ip, device.device_port))
        return True
    except OSError:
        return False
    finally:
        sock.close()


def load_devices(config_path: Path, settings: AgentSettings) -> list[DeviceTarget]:
    data = _parse_env_file(config_path)
    base_dir = config_path.parent

    # 1) ملف devices.list (مفضل لعدة فروع)
    list_path = base_dir / 'devices.list'
    if list_path.exists():
        devices: list[DeviceTarget] = []
        for i, line in enumerate(list_path.read_text(encoding='utf-8-sig').splitlines(), 1):
            row = _parse_device_line(line, i)
            if row:
                devices.append(row)
        if not devices:
            raise ValueError(f'لا أجهزة في {list_path}')
        return _sort_devices(devices)

    # 2) سطر DEVICES في config.env: id|ip|port|key,id|ip|...
    devices_raw = data.get('DEVICES', '').strip()
    if devices_raw:
        devices = []
        for chunk in devices_raw.split(','):
            chunk = chunk.strip()
            if not chunk:
                continue
            parts = chunk.replace('|', ' ').replace(';', ' ').split()
            if len(parts) < 2:
                raise ValueError(f'صيغة DEVICES غير صالحة: {chunk}')
            devices.append(
                DeviceTarget(
                    device_id=int(parts[0]),
                    device_ip=parts[1],
                    device_port=int(parts[2]) if len(parts) > 2 else 4370,
                    comm_key=int(parts[3]) if len(parts) > 3 else 0,
                    label=' '.join(parts[4:]) if len(parts) > 4 else '',
                )
            )
        if devices:
            return _sort_devices(devices)

    # 3) جهاز واحد (توافق قديم)
    def req(key: str) -> str:
        if key not in data or not data[key]:
            raise ValueError(f'مطلوب في config.env: {key} (أو أنشئ devices.list)')
        return data[key]

    return [
        DeviceTarget(
            device_id=int(req('DEVICE_ID')),
            device_ip=req('DEVICE_IP'),
            device_port=int(data.get('DEVICE_PORT', '4370')),
            comm_key=int(data.get('COMM_KEY', '0')),
            label=data.get('DEVICE_LABEL', ''),
        )
    ]


def punch_type_for_status(status: int | None) -> str:
    if status is None:
        return 'unknown'
    return PUNCH_STATUS.get(status, 'unknown')


def fetch_from_device(device: DeviceTarget, *, timeout_sec: int) -> tuple[list[dict], list[dict], str | None]:
    conn = None
    try:
        zk = ZK(
            device.device_ip,
            port=device.device_port,
            timeout=timeout_sec,
            password=device.comm_key,
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


def _parse_punch_time(value: str) -> datetime:
    dt = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def filter_punches_for_upload(
    punches: list[dict],
    *,
    incremental: bool,
    watermark: datetime | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> tuple[list[dict], int]:
    """
    يُبقي البصمات الجديدة فقط قبل الرفع للسيرفر.

    - تزايدي + watermark: بعد آخر بصمة محفوظة (مع هامش 60 ثانية).
    - طلب سحب بفترة: ضمن date_from/date_to فقط.
    - أول مزامنة بدون watermark: آخر 93 يوماً كحد أقصى.
    """
    now = datetime.now(timezone.utc)
    max_past = MAX_PAST_DAYS_INCREMENTAL if incremental else MAX_PAST_DAYS_FULL_SYNC
    cutoff = now - timedelta(days=max_past)
    future_limit = now + timedelta(minutes=MAX_FUTURE_MINUTES)

    time_cut: datetime | None = None
    if date_from or date_to:
        if date_from:
            start = datetime.combine(date_from, datetime.min.time(), tzinfo=timezone.utc)
            time_cut = start if time_cut is None else max(time_cut, start)
        if date_to:
            end = datetime.combine(date_to, datetime.max.time(), tzinfo=timezone.utc)
            future_limit = min(future_limit, end)
    elif incremental and watermark is not None:
        wm = watermark
        if wm.tzinfo is None:
            wm = wm.replace(tzinfo=timezone.utc)
        time_cut = wm - timedelta(seconds=WATERMARK_BUFFER_SECONDS)

    kept: list[dict] = []
    skipped = 0
    for punch in punches:
        try:
            ts = _parse_punch_time(punch['punched_at'])
        except (KeyError, TypeError, ValueError):
            skipped += 1
            continue
        if ts < cutoff or ts > future_limit:
            skipped += 1
            continue
        if time_cut is not None and ts <= time_cut:
            skipped += 1
            continue
        kept.append(punch)
    return kept, skipped


def _ingest_signature(api_key: str, body: bytes) -> str:
    digest = hmac.new(
        api_key.encode('utf-8'),
        body,
        hashlib.sha256,
    ).hexdigest()
    return f'sha256={digest}'


def push_to_server(
    settings: AgentSettings,
    device: DeviceTarget,
    punches: list[dict],
    users: list[dict],
    *,
    incremental: bool | None = None,
) -> dict:
    url = f'{settings.server_url}/api/v1/attendance/agent/ingest/'
    agent_suffix = device.label or str(device.device_id)
    use_incremental = settings.incremental if incremental is None else incremental
    payload = {
        'device_id': device.device_id,
        'agent_id': f'{settings.agent_id}:{agent_suffix}',
        'incremental': use_incremental,
        'punches': punches,
        'users': users,
    }
    body = json.dumps(payload, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    api_key = _api_key_for(device, settings)
    signature = _ingest_signature(api_key, body)
    resp = requests.post(
        url,
        headers={
            'X-Attendance-Agent-Key': api_key,
            'Content-Type': 'application/json',
            'X-Attendance-Signature': signature,
            'Authorization': f'Attendance-HMAC {signature}',
            'X-Attendance-Agent-Version': '2',
        },
        data=body,
        timeout=180,
    )
    try:
        body = resp.json()
    except Exception:
        body = {'message': resp.text[:500]}
    if resp.status_code >= 400:
        hint = ''
        if resp.status_code in (401, 403):
            code = body.get('code', '')
            if code == 'missing_signature':
                hint = (
                    ' — حدّث agent.py من السيرفر (يرسل X-Attendance-Signature) '
                    'أو عطّل ATTENDANCE_REQUIRE_INGEST_SIGNATURE على السيرفر مؤقتاً.'
                )
            elif code == 'invalid_signature':
                hint = (
                    ' — المفتاح في config.env يجب أن يطابق AGENT_API_KEY '
                    'الذي وُقّع به الطلب (مفتاح وكيل الجهاز من HR).'
                )
            else:
                hint = (
                    ' — تحقق: AGENT_API_KEY = مفتاح هذا الجهاز من HR (مفتاح وكيل) '
                    'و DEVICE_ID يطابق id الجهاز. لا تستخدم ATTENDANCE_AGENT_API_KEY العام.'
                )
        raise RuntimeError(f'HTTP {resp.status_code}: {body.get("message", body)}{hint}')
    return body


def _device_title(device: DeviceTarget) -> str:
    name = device.label or f'جهاز {device.device_id}'
    return f'{name} ({device.device_ip}:{device.device_port})'


def run_device_cycle(
    settings: AgentSettings,
    device: DeviceTarget,
    *,
    pull_request: PullRequest | None = None,
) -> bool:
    LOG.info('── %s ──', _device_title(device))
    if not _tcp_reachable(device, timeout_sec=min(5, settings.timeout_sec)):
        LOG.error(
            'تخطي: لا يوجد اتصال TCP بـ %s:%s (فعّل VPN هذا الفرع أو --device %s فقط)',
            device.device_ip,
            device.device_port,
            device.device_id,
        )
        return False
    LOG.info('سحب من %s:%s (id=%s) ...', device.device_ip, device.device_port, device.device_id)
    punches, users, err = fetch_from_device(device, timeout_sec=settings.timeout_sec)
    if err:
        LOG.error('فشل السحب: %s', err)
        return False

    use_incremental = settings.incremental
    date_from = None
    date_to = None
    if pull_request and pull_request.device_id == device.device_id:
        date_from = pull_request.date_from
        date_to = pull_request.date_to
        if date_from or date_to:
            use_incremental = False
            LOG.info('طلب سحب بفترة: %s → %s', date_from or '—', date_to or '—')

    watermark: datetime | None = None
    if not (date_from or date_to):
        try:
            watermark = fetch_sync_watermark(settings, device)
        except Exception as exc:
            LOG.warning('تعذّر جلب آخر بصمة من السيرفر — سحب كامل مؤقت: %s', exc)

        if watermark is None:
            use_incremental = False
            LOG.info(
                'أول مزامنة للجهاز — سحب كامل (حتى %s يوماً)',
                MAX_PAST_DAYS_FULL_SYNC,
            )
        else:
            use_incremental = True
            LOG.info('مزامنة تزايدية — بعد آخر بصمة %s', watermark.isoformat())

    upload_punches, skipped_bounds = filter_punches_for_upload(
        punches,
        incremental=use_incremental,
        watermark=watermark,
        date_from=date_from,
        date_to=date_to,
    )
    if skipped_bounds:
        LOG.info(
            'تصفية: %s سجل قديم/خارج النطاق — يُرفع %s فقط',
            skipped_bounds,
            len(upload_punches),
        )
    LOG.info(
        'على الجهاز: %s سجل، %s مستخدم — رفع %s ...',
        len(punches),
        len(users),
        len(upload_punches),
    )

    if use_incremental and not upload_punches and not (date_from or date_to):
        LOG.info('لا بصمات جديدة — تخطي الرفع (تزايدي)')
        return True

    try:
        result = push_to_server(
            settings,
            device,
            upload_punches,
            users,
            incremental=use_incremental,
        )
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


def filter_devices(
    devices: list[DeviceTarget],
    *,
    device_id: int | None = None,
) -> list[DeviceTarget]:
    if device_id is None:
        return devices
    matched = [d for d in devices if d.device_id == device_id]
    if not matched:
        ids = ', '.join(str(d.device_id) for d in devices)
        raise ValueError(f'جهاز id={device_id} غير موجود في devices.list (المتاح: {ids})')
    return matched


def fetch_sync_watermark(settings: AgentSettings, device: DeviceTarget) -> datetime | None:
    """آخر بصمة محفوظة على السيرفر — للسحب التزايدي."""
    url = f'{settings.server_url}/api/v1/attendance/agent/sync-state/'
    resp = requests.get(
        url,
        headers={'X-Attendance-Agent-Key': _api_key_for(device, settings)},
        params={'device_id': device.device_id},
        timeout=30,
    )
    try:
        body = resp.json()
    except Exception:
        body = {}
    if resp.status_code >= 400:
        msg = body.get('message', body.get('detail', resp.text[:200]))
        raise RuntimeError(f'sync-state HTTP {resp.status_code}: {msg}')
    raw = (body.get('data') or {}).get('last_punch_at')
    if not raw:
        return None
    return _parse_punch_time(str(raw))


def _fetch_pull_requests_with_key(settings: AgentSettings, api_key: str) -> list[PullRequest]:
    url = f'{settings.server_url}/api/v1/attendance/agent/pull-requests/'
    resp = requests.get(
        url,
        headers={'X-Attendance-Agent-Key': api_key},
        timeout=30,
    )
    try:
        body = resp.json()
    except Exception:
        body = {}
    if resp.status_code >= 400:
        msg = body.get('message', body.get('detail', resp.text[:200]))
        raise RuntimeError(f'pull-requests HTTP {resp.status_code}: {msg}')
    rows: list[PullRequest] = []
    for row in body.get('data') or []:
        try:
            device_id = int(row['device_id'])
        except (KeyError, TypeError, ValueError):
            continue
        date_from = None
        date_to = None
        raw_from = row.get('date_from')
        raw_to = row.get('date_to')
        if raw_from:
            date_from = date.fromisoformat(str(raw_from)[:10])
        if raw_to:
            date_to = date.fromisoformat(str(raw_to)[:10])
        rows.append(PullRequest(device_id=device_id, date_from=date_from, date_to=date_to))
    return rows


def fetch_pull_requests(
    settings: AgentSettings,
    devices: list[DeviceTarget] | None = None,
) -> list[PullRequest]:
    """طلبات سحب أرسلها المستخدم من موقع HR."""
    if not devices:
        return _fetch_pull_requests_with_key(settings, settings.api_key)
    if len(devices) == 1:
        return _fetch_pull_requests_with_key(settings, _api_key_for(devices[0], settings))

    merged: dict[int, PullRequest] = {}
    for device in devices:
        try:
            for row in _fetch_pull_requests_with_key(settings, _api_key_for(device, settings)):
                merged[row.device_id] = row
        except Exception as exc:
            LOG.warning('تعذّر جلب طلبات السحب لجهاز %s: %s', device.device_id, exc)
    return list(merged.values())


def fetch_pull_request_ids(
    settings: AgentSettings,
    devices: list[DeviceTarget] | None = None,
) -> list[int]:
    return [r.device_id for r in fetch_pull_requests(settings, devices)]


def ack_pull_request(
    settings: AgentSettings,
    device: DeviceTarget,
) -> None:
    url = f'{settings.server_url}/api/v1/attendance/agent/pull-requests/'
    resp = requests.post(
        url,
        headers={
            'X-Attendance-Agent-Key': _api_key_for(device, settings),
            'Content-Type': 'application/json',
        },
        json={'device_id': device.device_id},
        timeout=30,
    )
    if resp.status_code >= 400:
        LOG.warning('تعذّر إغلاق طلب السحب لجهاز %s: HTTP %s', device.device_id, resp.status_code)


def run_all_cycles(
    settings: AgentSettings,
    devices: list[DeviceTarget],
    *,
    force_sync: bool = False,
) -> bool:
    pull_requests: list[PullRequest] = []
    try:
        pull_requests = fetch_pull_requests(settings, devices)
    except Exception as exc:
        LOG.warning('تعذّر جلب طلبات السحب من الموقع: %s', exc)

    pull_by_device = {r.device_id: r for r in pull_requests}
    pull_ids = list(pull_by_device.keys())

    if force_sync:
        devices_to_run = list(devices)
        if pull_ids:
            LOG.info('سحب يدوي — أجهزة: %s', [d.device_id for d in devices_to_run])
    elif settings.sync_on_request_only:
        if not pull_ids:
            LOG.info(
                'لا طلب مزامنة من الموقع — تخطي السحب '
                '(اضغط «مزامنة» من أجهزة البصمة في HR)'
            )
            return True
        targeted: list[DeviceTarget] = []
        for did in pull_ids:
            try:
                targeted.extend(filter_devices(devices, device_id=did))
            except ValueError:
                LOG.warning(
                    'طلب سحب لجهاز id=%s غير مضبوط في هذا الوكيل (devices.list / config.env)',
                    did,
                )
        if not targeted:
            LOG.warning('طلبات مزامنة موجودة لكن لا جهاز مطابق في هذا الوكيل')
            return True
        LOG.info('طلب مزامنة من الموقع — أجهزة: %s', [d.device_id for d in targeted])
        devices_to_run = targeted
    elif pull_ids:
        LOG.info('طلب سحب من الموقع — أجهزة: %s', pull_ids)
        targeted = []
        for did in pull_ids:
            try:
                targeted.extend(filter_devices(devices, device_id=did))
            except ValueError:
                LOG.warning(
                    'طلب سحب لجهاز id=%s غير مضبوط في هذا الوكيل (devices.list / config.env)',
                    did,
                )
        devices_to_run = targeted if targeted else list(devices)
    else:
        devices_to_run = list(devices)

    ok = 0
    for device in devices_to_run:
        if run_device_cycle(
            settings,
            device,
            pull_request=pull_by_device.get(device.device_id),
        ):
            ok += 1
            if device.device_id in pull_ids:
                ack_pull_request(settings, device)
    total = len(devices_to_run)
    LOG.info('النتيجة: %s/%s جهاز نجح', ok, total)
    if ok == 0:
        return False
    if ok < total:
        LOG.warning(
            'بعض الأجهزة فشلت — تحقق من VPN/Tailscale لكل فرع، '
            'أو شغّل جهازاً واحداً: python agent.py --once --device 1'
        )
    return ok == total


def fetch_devices_from_server(settings: AgentSettings, *, api_key: str | None = None) -> list[DeviceTarget]:
    """جلب قائمة الأجهزة المسجّلة في HR (بعد إضافتها من لوحة البصمة)."""
    url = f'{settings.server_url}/api/v1/attendance/agent/devices/'
    resp = requests.get(
        url,
        headers={'X-Attendance-Agent-Key': api_key or settings.api_key},
        timeout=60,
    )
    try:
        body = resp.json()
    except Exception:
        body = {}
    if resp.status_code >= 400:
        msg = body.get('message', body.get('detail', resp.text[:300]))
        raise RuntimeError(f'فشل جلب الأجهزة HTTP {resp.status_code}: {msg}')
    rows = body.get('data') or []
    devices: list[DeviceTarget] = []
    for row in rows:
        devices.append(
            DeviceTarget(
                device_id=int(row['id']),
                device_ip=str(row['ip_address']).strip(),
                device_port=int(row.get('port') or 4370),
                comm_key=int(row.get('comm_key') or 0),
                label=(row.get('name') or '').strip(),
            )
        )
    return devices


def _comm_keys_from_devices_list(list_path: Path) -> dict[int, int]:
    """قراءة comm_key المحلي من devices.list (لا يُنشر من السحابة)."""
    keys: dict[int, int] = {}
    if not list_path.exists():
        return keys
    for i, line in enumerate(list_path.read_text(encoding='utf-8-sig').splitlines(), 1):
        row = _parse_device_line(line, i)
        if row:
            keys[row.device_id] = row.comm_key
    return keys


def write_devices_list(path: Path, devices: list[DeviceTarget]) -> None:
    lines = [
        '# أُنشئ تلقائياً من السيرفر — comm_key يُضبط محلياً (probe) ولا يُنشر من API',
        '# يجب أن يصل هذا PC لكل IP (Tailscale/VPN لكل فرع)',
        '',
    ]
    for d in devices:
        label = d.label.replace('\n', ' ')
        lines.append(f'{d.device_id}  {d.device_ip}  {d.device_port}  {d.comm_key}  {label}'.rstrip())
    path.write_text('\n'.join(lines) + '\n', encoding='utf-8')


def sync_devices_list_file(config_path: Path, settings: AgentSettings) -> list[DeviceTarget]:
    list_path = config_path.parent / 'devices.list'
    local_keys = _comm_keys_from_devices_list(list_path)
    keys_map = load_device_keys(config_path)
    list_api_key = next(iter(keys_map.values()), None) or settings.api_key
    devices = fetch_devices_from_server(settings, api_key=list_api_key)
    if not devices:
        raise ValueError('لا أجهزة نشطة على السيرفر — أضفها من: البصمة → أجهزة البصمة')
    merged: list[DeviceTarget] = []
    for d in devices:
        merged.append(
            DeviceTarget(
                device_id=d.device_id,
                device_ip=d.device_ip,
                device_port=d.device_port,
                comm_key=local_keys.get(d.device_id, 0),
                label=d.label,
            )
        )
    devices = merged
    write_devices_list(list_path, devices)
    LOG.info('تم حفظ %s جهاز في %s', len(devices), list_path)
    return devices


def probe_devices(settings: AgentSettings, devices: list[DeviceTarget]) -> int:
    """اختبار اتصال TCP + ZK لكل جهاز."""
    import socket

    failed = 0
    for device in devices:
        title = _device_title(device)
        LOG.info('فحص %s ...', title)
        sock = socket.socket()
        sock.settimeout(settings.timeout_sec)
        try:
            sock.connect((device.device_ip, device.device_port))
            LOG.info('  TCP %s:%s OK', device.device_ip, device.device_port)
        except OSError as exc:
            LOG.error('  TCP فشل: %s', exc)
            failed += 1
            continue
        finally:
            sock.close()

        punches, users, err = fetch_from_device(device, timeout_sec=settings.timeout_sec)
        if err:
            LOG.error('  ZK فشل: %s', err)
            failed += 1
        else:
            LOG.info('  ZK OK — %s مستخدم، %s سجل', len(users), len(punches))

    if failed:
        LOG.error('أجهزة فاشلة: %s/%s', failed, len(devices))
        return 1
    LOG.info('كل الأجهزة (%s) متاحة من هذا PC', len(devices))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description='وكيل بصمة HR — جهاز أو عدة أجهزة → سيرفر')
    parser.add_argument('--config', default=str(Path(__file__).parent / 'config.env'))
    parser.add_argument('--once', action='store_true', help='دورة واحدة ثم خروج')
    parser.add_argument('--probe', action='store_true', help='فحص اتصال كل الأجهزة فقط')
    parser.add_argument(
        '--sync-list',
        action='store_true',
        help='جلب الأجهزة من السيرفر وحفظ devices.list',
    )
    parser.add_argument(
        '--device',
        type=int,
        metavar='ID',
        help='مزامنة جهاز واحد فقط (مثال: 1 لسكاي مول، 2 للوحة)',
    )
    parser.add_argument(
        '--force-sync',
        action='store_true',
        help='سحب فوري لكل الأجهزة المضبوطة (يتجاوز SYNC_ON_REQUEST_ONLY)',
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s',
        datefmt='%H:%M:%S',
    )

    config_path = Path(args.config)
    settings = load_settings(config_path)

    if args.sync_list:
        devices = sync_devices_list_file(config_path, settings)
        for d in devices:
            LOG.info('  • id=%s %s:%s comm_key=%s %s', d.device_id, d.device_ip, d.device_port, d.comm_key, d.label)
        return 0

    devices = filter_devices(
        bind_device_api_keys(load_devices(config_path, settings), settings, config_path),
        device_id=args.device,
    )

    LOG.info('السيرفر: %s | أجهزة: %s', settings.server_url, len(devices))
    for d in devices:
        LOG.info('  • id=%s %s:%s comm_key=%s', d.device_id, d.device_ip, d.device_port, d.comm_key)

    force_sync = args.force_sync or args.device is not None

    if args.probe:
        return probe_devices(settings, devices)

    if args.once:
        return 0 if run_all_cycles(settings, devices, force_sync=force_sync) else 1

    while True:
        run_all_cycles(settings, devices, force_sync=force_sync)
        LOG.info('انتظار %s ثانية ...', settings.poll_interval_sec)
        time.sleep(settings.poll_interval_sec)


if __name__ == '__main__':
    raise SystemExit(main())
