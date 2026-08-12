# First Clinic Installation — Canora Medical Clinic (Post-RC1 Phase 2.6)

Step-by-step checklist for the first real install. Read
[`LOCAL_DEPLOYMENT.md`](LOCAL_DEPLOYMENT.md) and
[`WINDOWS_SERVICE_SETUP.md`](WINDOWS_SERVICE_SETUP.md) first for the "why";
this document is the "do this, in this order" checklist. Also see
[`INSTALLATION_GUIDE.md`](INSTALLATION_GUIDE.md) for the physical
hardware/network layout (which PC is Doctor Desktop, Reception, the TV
display, etc.) — this document assumes that layout is already in place.

## Pre-install

- [ ] Confirm which physical machine is "Doctor Desktop" (the machine that
      will run Postgres + Backend + Frontend — the primary/source-of-truth
      database for this clinic, per `INSTALLATION_GUIDE.md`).
- [ ] Confirm that machine's LAN IP, and make it **static** (DHCP
      reservation on the router, or a static IP set in Windows) — every
      bookmark/shortcut handed to staff below depends on this IP not
      changing after a router reboot.
- [ ] Install Python 3.11+ and Node.js 20+ on that machine.
- [ ] Download [NSSM](https://nssm.cc/download) and put `nssm.exe`
      somewhere on `PATH` (e.g. `C:\Tools\nssm\nssm.exe`).

## Install (Administrator)

1. Copy this repository to the machine (e.g. `D:\Projects\CMS`), including
   the existing `.devdb\` folder — the portable Postgres binaries and the
   clinic's data directory travel together, untouched.
2. Backend dependencies:
   ```
   cd backend
   python -m venv .venv
   .venv\Scripts\pip install -e .
   ```
3. Frontend production build:
   ```
   cd frontend
   npm ci
   npm run build
   ```
4. Environment files:
   - `backend\.env.local-production.example` → fill in → save as
     `backend\.env.production`, then copy/rename to `backend\.env`
     (`Settings` always loads a file literally named `.env`).
     - Generate a real `JWT_SECRET_KEY`:
       `python -c "import secrets; print(secrets.token_urlsafe(64))"`
     - Set `CORS_ORIGINS` to include `http://<static-LAN-IP>:3000`.
   - `frontend\.env.local-production.example` → fill in → save as
     `frontend\.env.production`. **Re-run `npm run build`** after editing
     this (Next.js bakes `NEXT_PUBLIC_*` in at build time).
5. Open Command Prompt **as Administrator**, `cd` to the repo root, then:
   ```
   deploy\windows\install_local_clinic.bat
   ```
   This registers all three Windows Services (Postgres, Backend, Frontend —
   auto-start, auto-restart, correctly ordered), opens firewall ports
   3000/8000 on the Private profile, and starts everything, polling each
   stage for real readiness.
6. Verify:
   ```
   deploy\windows\check_health.bat
   ```
   All four unauthenticated checks (Postgres, Backend, Backend DB
   readiness, Frontend) should read `[ OK ]`.
7. **Reboot the machine** and confirm, with no one logged in, that:
   - `check_health.bat` passes a few minutes after boot.
   - `http://localhost:3000` loads the login page from another machine on
     the LAN, at `http://<static-LAN-IP>:3000`.

   This is the one step in this whole checklist that requires a real
   reboot of the real target machine — it was not (and could not
   responsibly be) simulated on the shared dev machine this phase was
   built on. Everything up to this point has already been verified
   component-by-component (see `docs/TESTING.md`'s Phase 2.6 section).

## Post-install (per staff workstation)

- [ ] Auto-launch shortcut on the Doctor Desktop machine only (staff
      workstations just need a bookmark, not an auto-launch, since they
      aren't running the servers): install
      `deploy\windows\launch_clinic_browser.bat` into `shell:startup`
      (Win+R → `shell:startup` → drag a shortcut to the `.bat` file in) —
      see the script's own header for the Scheduled-Task alternative.
- [ ] Hand out the staff URL: `http://<static-LAN-IP>:3000` — bookmark it on
      Reception, Laboratory, Cashier PCs (see `INSTALLATION_GUIDE.md` for
      which PC is which).
- [ ] Waiting-room TV: `http://<static-LAN-IP>:3000/tv` (or bare `/tv` if
      `NEXT_PUBLIC_DEFAULT_TV_SLUG` is set for this clinic's single
      display — see `frontend/.env.production`).

## Backup & Restore

- **What to back up**: `.devdb\data\` (the live Postgres data directory).
  Do not edit or manually touch its files — only back it up via `pg_dump`
  or a filesystem-level copy while Postgres is stopped.
- **Daily backup** (recommended — a Scheduled Task, not covered by this
  phase's auto-start scripts since it's a separate operational concern):
  ```
  "<repo>\.devdb\pgsql\bin\pg_dump.exe" -p 5433 -U clinic_user -F c -f "<backup-folder>\connectph_%date%.dump" connectph_clinic
  ```
  Store `<backup-folder>` on a **second** drive or external media — a
  backup on the same disk as the live data protects against nothing.
- **Restore drill** (practice this before go-live, not after a real
  failure):
  ```
  deploy\windows\stop_clinic.bat
  "<repo>\.devdb\pgsql\bin\pg_restore.exe" -p 5433 -U clinic_user -d connectph_clinic --clean "<backup-folder>\connectph_YYYY-MM-DD.dump"
  deploy\windows\start_clinic.bat
  deploy\windows\check_health.bat
  ```
- Cloud backup (uploading to a Phase 2.5 Cloud Server) is a separate,
  optional, opt-in mechanism (`DEPLOYMENT_MODE=hybrid` + `CLOUD_*` vars) —
  not required for this local install to be considered backed up, and not
  part of this checklist.

## Troubleshooting

| Symptom | Check |
|---|---|
| `check_health.bat` shows Postgres `[FAIL]` | `nssm status CONNECTPH-Postgres`; check `.devdb\logfile.txt` and `deploy\windows\logs\postgres-service-error.log`. |
| Backend `[FAIL]` | `nssm status CONNECTPH-Backend`; check `deploy\windows\logs\backend-service-error.log` — usually a bad `.env` value (e.g. `DATABASE_URL`) or the DB not yet ready (see `WINDOWS_SERVICE_SETUP.md` §Startup order). |
| Frontend `[FAIL]` | `nssm status CONNECTPH-Frontend`; check `deploy\windows\logs\frontend-service-error.log` — most common cause is `.next\` missing (run `npm run build`) or wrong `NEXT_PUBLIC_API_URL` baked into the build. |
| Staff can't reach `http://<IP>:3000` from another PC | Confirm the firewall rule (`netsh advfirewall firewall show rule name="CONNECT.PH Clinic Platform"`), confirm both PCs are on the same Private network, confirm the Doctor Desktop's IP hasn't changed (see the static-IP step above). |
| Everything was fine, then a Windows Update rebooted the machine overnight | This is exactly the scenario `SERVICE_AUTO_START` + `DependOnService` + auto-restart-on-crash are for — should self-heal with no one logged in. If not, `check_health.bat` remotely (or on next login) to confirm, then `deploy\windows\restart_clinic.bat` as a manual fallback. |
