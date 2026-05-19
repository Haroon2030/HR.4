# HR Biometric Bridge (ZKTeco)

Pulls attendance from branch LAN devices and uploads to the cloud HR server via API.

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

For devices on `192.168.x.x`, use **Request sync** in HR — the branch agent executes within ~5 minutes.

Cloud server cannot connect to private LAN IPs directly.

## Server-side health check (production)

On the Docker server:

```bash
python manage.py check_attendance_production --verbose
```

Verifies DB connection, tables, agent API key, punch rows in `attendance_attendancepunch`, and employee enrollments.

## Central PC (optional)

Multiple branches via VPN/Tailscale: `setup_central.ps1` + `devices.list.example`.
