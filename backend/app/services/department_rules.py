"""Tiny, dependency-free home for the "is this the Laboratory department"
rule - factored out of `queue_service.py` so `visit_service.py` can reuse
the exact same definition too, without a circular import (`queue_service`
already imports `VisitService`, so `visit_service` importing back from
`queue_service` would cycle). Kept in its own module rather than a shared
utility grab-bag - one function, one reason to change.
"""

from app.models.department import Department


def is_laboratory_department(department: Department) -> bool:
    # Matched by NAME, not `department.department_code == "LAB"` - a clinic
    # that created its own Laboratory department manually (a real, observed
    # case) would never match a fixed code. Used everywhere something needs
    # to agree on what counts as "the Laboratory department" for a given
    # clinic - the Laboratory pay-first payment gate, the walk-in lab-order
    # auto-linking gate, and the Laboratory-services department-match
    # validation - so all of them stay in sync by construction.
    return department.name.strip().lower() == "laboratory"
