# Clinic Hardware Installation Guide (Post-RC1 Phase 2.5)

**Scope note (documented choice):** [`INSTALL.md`](INSTALL.md) already covers *software* local-dev setup (cloning the repo, running the backend/frontend, seeded logins) and is unchanged by this file. This guide is the **clinic-hardware-focused companion** — what to physically set up at a real clinic site (workstations, network, printers, TV display) once the software is deployed per [`DEPLOYMENT.md`](DEPLOYMENT.md) (VPS backend) or run fully on-prem (`DEPLOYMENT_MODE=local`, no VPS needed at all). Cross-links: this file → `INSTALL.md` for software setup steps, `INSTALL.md` → this file (added below) for the hardware side. Neither file duplicates the other.

**Post-RC1 Phase 2.6 note:** for the actual production *software* install on the Doctor Desktop machine described below — auto-starting on Windows boot as real Windows Services, not a developer `npm run dev` session — see [`LOCAL_DEPLOYMENT.md`](LOCAL_DEPLOYMENT.md), [`WINDOWS_SERVICE_SETUP.md`](WINDOWS_SERVICE_SETUP.md), and [`FIRST_CLINIC_INSTALLATION.md`](FIRST_CLINIC_INSTALLATION.md).

---

## 1. Network setup

- A clinic runs one of two topologies:
  - **Fully local** (`DEPLOYMENT_MODE=local`, no internet dependency): the backend runs on one on-site machine (a small server, a spare desktop, or a repurposed reception PC) on the clinic's own LAN. All workstations connect to it via the LAN's local IP (e.g. `http://192.168.1.50:8000`).
  - **Hybrid** (`DEPLOYMENT_MODE=hybrid`): the backend runs on a VPS (see `DEPLOYMENT.md`) reachable over the internet at `https://clinic-api.connectph-it.com`; the clinic's LAN just needs a working internet connection (any standard router/ISP setup), no local server machine required.
- Recommended: a dedicated Wi-Fi/Ethernet network for clinic workstations, separate from any public/guest Wi-Fi, with the local server (if fully-local mode) given a **static local IP** (or a DHCP reservation) so `NEXT_PUBLIC_API_URL` / workstation bookmarks don't break after a router reboot.
- Minimum bandwidth for hybrid mode: any always-on broadband connection is sufficient — the app is not bandwidth-heavy (JSON API calls, no video); sync/backup traffic is small and asynchronous, never blocking a clinic workflow (per Milestone 2's design).

## 2. Doctor Desktop

- **Hardware:** any modern desktop/laptop, 8 GB RAM+, a webcam is not required (no telehealth in this phase's scope).
- **Software:** a modern browser (Chrome/Edge/Firefox, latest). No local install needed — it's a web app.
- **Setup:** browser bookmark to the clinic's frontend URL (`https://clinic.connectph-it.com` hybrid, or the local server's LAN address:3000 for fully-local); log in with the Doctor's account; confirm the Doctor Workspace queue loads.
- **Printer:** optional at this station (prescriptions/lab requests are commonly printed from Reception/Cashier instead, but a doctor can print directly — see §7).

## 3. Reception Laptop/Desktop

- **Hardware:** any modern desktop/laptop.
- **Setup:** same browser-bookmark pattern as above, logged in with a Receptionist account.
- **Peripherals:** a receipt/thermal printer is common here for queue tickets (optional — the Reception Queue UI itself doesn't require a physical ticket print in this codebase's current feature set) and a standard printer for consent forms/patient handouts.
- Confirm: can create a walk-in queue ticket, can check in a booked appointment, TV Display (if present, §6) reflects new tickets in real time.

## 4. Laboratory PC

- **Hardware:** any modern desktop.
- **Setup:** browser bookmark, logged in with a Laboratory-role account.
- **Peripherals:** a printer for lab result printouts (A4/Letter, see Printer Settings in §7).
- Confirm: laboratory order queue loads, result entry/upload works, "Released" results become visible on the Patient Portal (if the clinic has it enabled) and to the ordering Doctor.

## 5. Cashier PC

- **Hardware:** any modern desktop.
- **Setup:** browser bookmark, logged in with a Cashier account.
- **Peripherals:** a receipt printer strongly recommended for payment receipts; a physical cash drawer is a hardware choice outside this app's scope (no cash-drawer-open integration exists).
- Confirm: can record a payment against an invoice, Shift open/close works, discount apply/void per the RBAC rules documented in `RELEASE_NOTES.md`.

## 6. TV Queue Display

- **Hardware:** any Smart TV or a TV + small PC/media box (e.g. an inexpensive mini-PC or an old laptop in kiosk mode) with a browser.
- **Setup:**
  - **Single-clinic/single-TV**: point the TV's browser at `http://<server-or-domain>/tv` (the bare route, zero per-display config — see `RELEASE_NOTES.md` v1.6.1). Requires `NEXT_PUBLIC_DEFAULT_TV_SLUG` set in the frontend's environment to the clinic's display slug.
  - **Multi-tenant/multiple displays**: use `/tv/<slug>` directly, one URL per physical display.
  - Recommended kiosk setup: full-screen browser (`?fullscreen=true` query param for best-effort auto-fullscreen; a one-time user gesture, e.g. tapping the screen once after load, may still be needed depending on the browser's autoplay/fullscreen policy — documented, not a bug), auto-hide cursor after idle (built in), and the TV/box set to auto-power-on and auto-launch the browser to that URL after a power outage so no manual intervention is needed each morning.
- **Audio:** if audible queue-calling is desired on the TV itself, ensure the TV/box's speakers are on and unmuted — the TV Display announces via the Web Speech API like other stations (see BUG-022 in `docs/BUGS.md` for one known Recall-repeat limitation).

## 7. Printer setup

- Printer selection/paper-size (A4 / Letter / Thermal 80mm / Half-Letter prescription pad) is a **per-browser** preference set on each workstation via the app's own Printer Settings, not a server-side/network-printer configuration this app manages directly.
- Physically: install each printer's normal OS driver on the workstation it's attached to (or configure it as a shared network printer via the OS if one printer serves multiple stations), then select it in the browser's native print dialog when printing a prescription/lab request/referral/receipt from the app.
- Browser printer-selection limitations (e.g. the browser print dialog itself, not this app, controls printer selection) are inherent to the "print via `window.print()`" approach used throughout this codebase — documented, not a bug.

## 8. Post-installation checklist

- [ ] All workstations can reach the backend (`curl <api-url>/api/v1/health` from each machine, or simply confirm login works).
- [ ] Each role (Owner/Administrator/Receptionist/Doctor/Laboratory/Cashier) has a real account and can log in from its intended station.
- [ ] TV Display shows "Now Serving" correctly with a real test ticket, in fullscreen, from across the room.
- [ ] At least one test print completes successfully from Reception, Doctor, Laboratory, and Cashier stations.
- [ ] (Hybrid mode only) `/system-status` (Owner/Administrator login) shows Cloud Server: Up, and a test-created patient appears as a `synced_records` row on the Cloud Server within one sync-worker tick — see `docs/TESTING.md`'s Phase 2.5 section for the exact reproduction steps.

See [`INSTALL.md`](INSTALL.md) for the software/developer-facing setup this hardware installation sits on top of, and [`DEPLOYMENT.md`](DEPLOYMENT.md) for VPS/Vercel production deployment.
