# Rollback Plan

Exact, human-executable steps to undo a CONNECT.PH Clinic Platform deployment if it needs to be reversed after go-live. Companion to `docs/DEPLOYMENT_READINESS_v1.2.md` (what was verified before deploying) and `docs/BACKUP.md` (the underlying database restore procedure, referenced but not duplicated here).

**Like the restore procedure in `BACKUP.md`, nothing here is automated.** A rollback is a human decision executed deliberately, one step at a time, with verification between steps — not a script that runs unattended.

---

## 1. Rollback decision tree

Start here. Not every problem after a deploy requires a full rollback.

```
Something is wrong after deploying a new version
    │
    ▼
Is the database schema affected (a new migration ran)?
    │
    ├── NO  → Application-only rollback (§2). Fast, low-risk.
    │
    └── YES → Did the migration only ADD columns/tables (additive)?
              │
              ├── YES → Application-only rollback (§2) is usually still safe:
              │         old code ignores new columns/tables it doesn't know
              │         about. Confirm this is actually true for the specific
              │         migration before assuming it (see §3 caveat).
              │
              └── NO (it altered/dropped/renamed something) → Full rollback
                        including a migration downgrade or database restore
                        (§3 and/or §4). Higher risk — read both sections
                        fully before acting.
```

Every migration shipped through v1.2.0 (`0001_initial` through `0018_patient_appointment_booking`) is additive-only (new tables/columns, one new partial unique index) — none of them rename or drop an existing column. This means, as of this version, **an application-only rollback (§2) is expected to be safe** without a matching migration downgrade. This assumption must be re-checked for any migration added after this document was written — read the specific migration file before trusting this blanket statement for a future deploy.

## 2. Application-only rollback (no schema change to undo)

This is the common case and should be tried first when the database schema hasn't changed.

1. **Stop the current (bad) version**:
   - Backend: stop the `uvicorn` process (`Ctrl+C` if foreground, or `kill <pid>` / your process supervisor's stop command).
   - Frontend: stop the `next start` process the same way.
2. **Check out or re-deploy the previous known-good version** of the code (the exact mechanism depends on how the deployment is done — e.g. `git checkout <previous-tag-or-commit>`, redeploying a previous build artifact, or promoting a previous Vercel/Railway deployment if using that hosting path per `DEPLOYMENT.md`).
3. **Rebuild and restart**, using the exact commands in `docs/DEPLOYMENT_READINESS_v1.2.md` §3:
   ```bash
   cd backend && python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
   cd frontend && npm run build && npm run start
   ```
4. **Verify before declaring the rollback complete**:
   - `GET /api/v1/health`, `/live`, `/ready` all return `200`.
   - Log in with a real account and confirm the dashboard loads.
   - Spot-check the one workflow that was broken in the bad version, confirming it now behaves correctly on the rolled-back version.
5. **Do not delete the bad version's code/artifact yet** — keep it available (a git commit, a tagged build, whatever the deploy mechanism preserves) so the specific failure can be investigated after the immediate incident is resolved.

## 3. Rollback involving a migration downgrade

Only needed if the new version's migration must be undone — e.g. it turns out to be genuinely destructive/incompatible with the old code, not just additive.

1. **Stop the application first** (§2 step 1) — never run a migration downgrade while the app is still writing to the database.
2. **Identify the exact migration to downgrade to.** Check current state:
   ```bash
   cd backend
   DATABASE_URL=<production-url> python -m alembic current
   ```
3. **Downgrade one migration at a time**, verifying after each step rather than jumping straight to an old target:
   ```bash
   DATABASE_URL=<production-url> python -m alembic downgrade -1
   ```
   Repeat as needed, or downgrade directly to a known revision:
   ```bash
   DATABASE_URL=<production-url> python -m alembic downgrade <revision-id>
   ```
4. **Verify the downgrade actually ran** (`alembic current` again) and spot-check that the specific column/table the new migration added is actually gone (or reverted), not just that the command exited `0`.
5. **Only then** redeploy the old application code (§2), since old code + new schema (or vice versa) is very likely to be broken in a different, possibly worse way than the original problem.

**Caveat, read before downgrading**: an Alembic `downgrade` only reverses schema (columns/tables/indexes) — it does **not** restore data that a migration's own `upgrade()` may have transformed or that was written under the new schema in the meantime (e.g. rows created in a new table since the bad deploy). If real data was written using the new version's schema/features before the rollback decision was made, a plain migration downgrade will likely **destroy that data** when it drops the now-unwanted table/column. Before downgrading in this situation:
- Take a fresh `pg_dump` backup first, unconditionally, even if it seems urgent to move fast (`docs/BACKUP.md` §1 — trigger via `POST /api/v1/platform-admin/backups`, or a manual `pg_dump` if the app itself is down).
- If any real, un-discardable data lives only in the new schema, a straight downgrade is the wrong tool — consider instead: keep the new schema, but roll back only the application code to a version that safely ignores the new columns/tables (§2), or handle the specific data migration by hand.

## 4. Full database restore (last resort)

Only when the database itself is corrupted, or a downgrade isn't sufficient to recover a good state. This is a superset of `docs/BACKUP.md`'s restore procedure — see that document for the full step-by-step (stop traffic → confirm the right dump → restore into a fresh database → verify `alembic_version` and row counts → cut over → resume traffic and monitor). Do not skip that document's verification step (§3.5 there) under time pressure — restoring from the wrong point in time, silently, is worse than the outage it was meant to fix.

## 5. Post-rollback checklist

Regardless of which section above was used:

- [ ] Confirm `/health`, `/live`, `/ready` all return `200` on the rolled-back version.
- [ ] Log in as a real user and confirm the dashboard and at least one core workflow (e.g. Patients list, Queue) render correctly.
- [ ] Confirm `alembic current` matches what the running application code actually expects (mismatched code/schema is a common source of a "successful-looking" rollback that's actually still broken).
- [ ] Notify whoever needs to know (clinic staff, if the outage was visible to them) that service has been restored.
- [ ] Preserve the bad version's code/build/logs for post-incident review — do not clean these up until the root cause is understood.
- [ ] Write up what went wrong and update `docs/BUGS.md` with a real entry (severity, root cause once known, fix) rather than letting the incident go undocumented.
