# Support Guide

Who to contact and what to check before reporting an issue, for a pilot
clinic running CONNECT.PH. This is a template for a real pilot — fill in
real names/contacts before go-live (see `docs/PILOT_READINESS.md`).

## Before reporting anything

1. **What role were you logged in as, and what were you trying to do?**
   Most "it doesn't work" reports turn out to be a role gate working as
   intended (e.g. a Receptionist can't edit a SOAP note — that's by
   design, not a bug). Check `docs/USER_MANUAL.md`'s role table first.
2. **What's the exact error message?** The API returns a `request_id` on
   every error response — capture it, it lets whoever investigates find
   the exact server-side log line instantly instead of guessing.
3. **Can you reproduce it, or did it happen once?** A one-off is still
   worth reporting, but say so — it changes how urgently it needs
   investigating.

## Severity triage (matches `docs/BUGS.md`'s scale)

- **Critical** (data loss, security issue, tenant data leaking, whole
  system down) — stop what you're doing, contact the on-call/technical
  contact immediately, don't wait for a ticket queue.
- **High** (a core workflow — registration, appointments, queue,
  consultation, billing, payment — broken with no workaround) — report
  same day.
- **Medium** (a workflow broken but there's a workaround, or a
  non-core feature broken) — report normally, expect a fix in the next
  update cycle.
- **Low** (cosmetic, minor annoyance, edge case) — report whenever
  convenient; batched into future updates.

## Where to report

Use `docs/BUGS.md`'s entry format directly, or your organization's real
issue tracker once one is adopted (the file itself says this is meant to
be retired once you have one — see its intro). Fill in every field in
the format, especially **Steps to reproduce** — a report without
reproduction steps is much slower to act on.

## What technical support will ask for

- Clinic/tenant name and the approximate time the issue occurred (for
  log correlation).
- The `request_id` from the error response, if there was one.
- Screenshot or exact text of the error.
- Whether it affects one user/one browser or everyone.

## What this pilot cannot yet support

Per `docs/PILOT_READINESS.md`, this is a technical-readiness pilot, not
a live production deployment with 24/7 support infrastructure. Real
support coverage (on-call rotation, SLAs, escalation paths, a real
ticketing system) is one of the "next steps for the real clinic team"
listed there — do not assume production-grade support response times
exist yet in a sandboxed/dev-only environment.
