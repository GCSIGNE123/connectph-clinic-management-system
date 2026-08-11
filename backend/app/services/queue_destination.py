"""Shared "resolve a queue ticket's destination room label" helper.

Extracted from `tv_display_service.py` (Post-RC1 room-based TV
announcements) so `QueueService` can compute the exact same room label for
a single ticket (Receptionist Call/Re-announce) without duplicating the
"narrowest scope wins" resolution logic. Behavior is unchanged - this is a
pure move, not a rewrite.
"""

from uuid import UUID

from app.models.queue_setting import QueueSetting


def resolve_room_label(
    settings: list[QueueSetting], *, branch_id: UUID | None, department_id: UUID | None, doctor_id: UUID | None
) -> str | None:
    """In-memory re-implementation of `QueueSettingRepository.get_effective_for_doctor`'s
    exact "narrowest scope wins" resolution (doctor override -> department
    override -> branch/clinic default), operating over an already-fetched
    settings list instead of issuing a query per ticket. The winning row's
    `room_label` is used as-is (including `None` if that specific row never
    had one configured) - deliberately NOT cascading further up the chain
    looking for an ancestor row's room_label, since prefix and room are
    configured together on the same override row in the admin UI; a row
    that exists for prefix purposes but leaves room blank means "no room
    for this destination", not "inherit the parent's room"."""

    def find(b: UUID | None, d: UUID | None, doc: UUID | None) -> QueueSetting | None:
        for s in settings:
            if s.branch_id == b and s.department_id == d and s.doctor_id == doc:
                return s
        return None

    if doctor_id is not None:
        row = find(branch_id, department_id, doctor_id)
        if row is not None:
            return row.room_label
    if department_id is not None:
        row = find(branch_id, department_id, None)
        if row is not None:
            return row.room_label
    row = find(branch_id, None, None)
    return row.room_label if row is not None else None
