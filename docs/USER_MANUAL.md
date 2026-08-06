# User Manual — Front Desk, Doctor, Laboratory, Cashier

Phase 17 pilot-readiness manual: a practical, task-oriented walkthrough of
the patient journey as it exists in this build today. It is written from
the scripted UAT run performed this phase (see `docs/PILOT_READINESS.md`
for the full pass/fail log) — every step below was actually exercised
against a running instance, not copied from a spec.

This is not a replacement for the real training session a pilot clinic's
staff need before go-live (see `docs/PILOT_READINESS.md`'s "what remains"
section) — it's the reference material that training session would use.

## 1. Logging in

Go to the app URL, sign in with your username/email and password. Your
role (Owner, Administrator, Receptionist, Doctor, Nurse, Cashier,
Laboratory, Pharmacy, Viewer) determines which sidebar sections and
actions you see — a Receptionist won't see Billing write actions, a
Doctor only edits consultations for their own assigned patients, etc.

## 2. Registration (Receptionist / Administrator / Owner)

**Patients → New Patient.** Fill in name, birth date, sex, civil status,
mobile number, address. The system checks for likely duplicates
(same name + birth date, or same mobile number) and shows a warning
before you can save anyway — this is deliberate: it does not block you,
it asks you to confirm. Only an Owner/Administrator can override the
duplicate warning.

## 3. Appointment booking (Receptionist / Administrator / Owner)

**Appointments → New Appointment.** Pick patient, doctor, branch,
department, service, date. Use the doctor's **available slots** lookup
to pick a real open slot — booking directly into an already-taken slot
is rejected with a clear "already has an appointment booked at this
time" error. Confirm the appointment once booked.

## 4. Check-in (Receptionist)

From the Appointments list, **Check In** the patient on the day of their
visit. This automatically creates a Queue ticket and a Visit record —
you don't create either of those by hand. Check-in requires the
appointment to already have a department and service set; if either is
missing you'll be told to edit the appointment first before check-in
will proceed.

## 5. Queue (Receptionist / Doctor)

The Reception Queue screen and the TV Display both show tickets in
real time. A ticket starts at **Waiting**. The doctor (from the Doctor
Workspace) uses **Call** to summon the patient, then **Start
Consultation** once they're in the room — these two actions are what
move both the Queue ticket and the underlying Visit forward together.
Skipping straight to opening a consultation without these two actions
still works for recording clinical data, but leaves the Visit's own
status stuck at an earlier stage — always use Call → Start Consultation
from the Doctor Workspace, not a shortcut.

## 6. Consultation (Doctor)

**Doctor Workspace → (patient) → Consultation.** Record SOAP notes
(Subjective/Objective/Assessment/Plan) and diagnoses. Only the
consultation's assigned doctor can edit it — Owner/Administrator have
view-only access here by design (matches the "Receptionist read-only"
and "Doctor-only edit" pattern used across every clinical module).

## 7. Orders & Prescriptions (Doctor)

From the same Consultation page, add **Clinical Orders** (Laboratory /
Radiology / Vaccination / Custom), **Procedures**, **Referrals**, and
**Prescriptions** (repeatable medicine line items with dosage/frequency/
duration/quantity). A Laboratory-category order automatically creates a
linked Laboratory workflow record — no separate step needed.

## 8. Completing the consultation (Doctor)

**Complete Consultation** locks in the SOAP note and diagnoses, and
automatically creates a Draft invoice priced from the doctor's
consultation fee (or the service's default price as a fallback) — you
never create the invoice by hand. If the Visit has correctly progressed
through Called → In Consultation (step 5), completing here also moves
the Visit itself to Completed once the invoice is fully paid.

## 9. Laboratory (Laboratory role / Owner / Administrator)

**Laboratory Dashboard** shows every pending order. Work a specimen
through **Collect → Start Processing → Enter Results → Release** — each
is its own button/action, in that order. Entering results supports
multiple parameters per test (name, numeric or text value, units,
normal range, interpretation). Releasing a result is the terminal step
and mirrors back onto the underlying clinical Order's status
automatically.

## 10. Billing & Payment (Cashier / Owner / Administrator)

**Cashier Dashboard → Invoices.** The consultation-completion invoice
already has its line items; add a **Discount** (Senior/PWD/Employee/
Custom, percentage or fixed) if applicable before payment. Record a
**Payment** — supports a single payment or a split across multiple
payment methods/amounts on the same invoice. Once the invoice's balance
reaches zero, its status becomes Paid and a printable **Receipt** is
available (`window.print()`-based, same pattern as the Queue slip).
Receptionist has read-only access to Billing; Doctor is view-only.

## 11. Completion

Once the invoice is Paid and the Visit has been correctly progressed
through the Queue's Call/Start-Consultation steps, the Visit's own
status reaches **Completed** — the end of the patient journey for that
encounter. You can review the whole encounter afterward from the
Patient Profile's Visits/Billing History/Prescriptions/Laboratory tabs.

## Getting help

See `docs/SUPPORT_GUIDE.md` for who to contact and what to check before
reporting an issue.
