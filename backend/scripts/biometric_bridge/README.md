# HR Biometric Bridge (ZKTeco)

Pulls attendance from branch LAN devices and uploads to the cloud HR server via API.

## Per-device API key (recommended)

Each ZKTeco device in HR has its own agent key (not the global server key).

1. In HR web: **Attendance → Biometric devices** — note the device **ID** column.
2. Click **مفتاح وكيل** (or on server: `python manage.py generate_attendance_agent_key --device-id=ID`).
3. Copy the key once into `config.env` as `AGENT_API_KEY=...` and set `DEVICE_ID` to the same ID.
4. On server: `python manage.py check_attendance_production --details`

The raw key is shown only once; HR stores SHA-256 only.

## Branch PC (recommended)

1. Copy this folder to `C:\biometric_bridge`
2. Right-click **install_branch.bat** → Run as administrator
3. Right-click **install_task.bat** → Run as administrator (sync every 5 minutes)

### Manual commands

```cmd
cd /d C:\biometric_bridge
run_agent.bat --probe
run_agent.bat --once
```

### ZKBioTime Python error (`SRE module mismatch`)

If `python` points to `C:\ZKBioTime\Python311\`, it is **not** compatible with this agent.

1. Run **fix_python.bat** (installs Python 3.12 via winget if needed)
2. Or use full path:  
   `%LocalAppData%\Programs\Python\Python312\python.exe agent.py --probe`
3. Close CMD and open a new window after install

### Files

| File | Purpose |
|------|---------|
| `agent.py` | Core agent |
| `config.env` | Secrets (copy from `config.example.env`, gitignored) |
| `setup_branch.ps1` | Branch setup (single device) |
| `install_branch.bat` | Run branch setup as Admin |
| `install_task.bat` | Windows scheduled task (every 5 min) |
| `run_scheduled.bat` | Used by scheduled task |
| `run_agent.bat` | Manual agent run |
| `sync_devices.bat` | Refresh device list from server |

## Web UI

For devices on `192.168.x.x`, use **Request sync** (مزامنة) in HR — the branch agent executes within ~5 minutes.

Cloud server cannot connect to private LAN IPs directly.

## Sync on request only (default)

Set `SYNC_ON_REQUEST_ONLY=true` in `config.env` (default). The scheduled task still polls the server every 5 minutes, but **only checks for pending sync requests** — it does not pull from ZKTeco devices until someone clicks **مزامنة** in HR.

Manual override from the branch PC:

```cmd
run_agent.bat --once --device 1
run_agent.bat --once --force-sync
```

Legacy automatic pull for all devices every cycle: `SYNC_ON_REQUEST_ONLY=false`.

## Incremental sync (recommended)

Set `INCREMENTAL=true` in `config.env` (default). The agent:

1. Asks the server for the last saved punch time (`/api/v1/attendance/agent/sync-state/`).
2. **First sync** (no punches on server yet): uploads full history up to 365 days.
3. **Later syncs**: uploads **only punches newer** than that time (60s buffer).
4. Skips the HTTP upload entirely when there are no new punches.

The ZKTeco device still returns all logs over TCP (device limitation), but the server no longer receives the full history every 5 minutes.

For a **date-range pull** from the HR web UI, the agent uses the requested `date_from` / `date_to` instead.

## Server-side health check (production)

On the Docker server:

```bash
python manage.py check_attendance_production --details
```

Verifies DB connection, tables, agent API key, punch rows in `attendance_attendancepunch`, and employee enrollments.

## Multiple devices (no duplication)

Each ZKTeco device in HR has its **own** agent key. One key must not be reused for another device.

### Option A — one PC per branch (recommended)

| Branch | `config.env` | Scheduled task |
|--------|----------------|----------------|
| Branch 1 | `DEVICE_ID=1`, `AGENT_API_KEY=<key for device 1>` | One task on branch PC |
| Branch 2 | `DEVICE_ID=2`, `AGENT_API_KEY=<key for device 2>` | One task on branch PC |

Do **not** copy the same `config.env` to another branch. Do **not** run two scheduled tasks on the same PC for the same device.

### Option B — central PC (VPN/Tailscale to all branches)

1. `devices.list` — one line per device (ID, IP, port, comm_key, label).
2. `device_keys.env` — one line per device: `device_id=RAW_KEY_FROM_HR`.
3. `setup_central.ps1` or `python agent.py --sync-list` then `--probe`.

Attendance deduplication on the server is **per device** (same user + same second on the same device is skipped). Different devices keep separate punch rows.

### Fix repeated 403 errors

- `AGENT_API_KEY` must match the **device key** from HR (not an old or global key).
- `DEVICE_ID` must match the device **ID** column in HR.
- On Windows: `schtasks /query /fo LIST /v | findstr biometric` — remove duplicate tasks.

### HTTP 413 Request Entity Too Large (first sync)

The agent splits uploads into batches (`INGEST_BATCH_SIZE=500` in `config.env`). If you still see 413:

1. Update `agent.py` from the server (copy `biometric_bridge` folder again).
2. On nginx/Dokploy, raise `client_max_body_size` (e.g. `50m`) for the HR app proxy.
3. Re-run: `run_agent.bat --once --force-sync`

## Central PC (optional)

Multiple branches via VPN/Tailscale: `setup_central.ps1` + `devices.list.example` + `device_keys.env.example`.
