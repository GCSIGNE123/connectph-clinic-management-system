"""Pure, side-effect-free laboratory result interpretation (Feature 3).

Computes BELOW/NORMAL/ABOVE (`LaboratoryInterpretation.LOW`/`NORMAL`/`HIGH`)
for numeric results against a structured range, or NORMAL/ABNORMAL for
qualitative (Text) results against an expected-normal value.

Never guesses: any missing input (either range bound absent, no
expected-normal value configured, or no result value entered at all)
returns `None` rather than assuming an interpretation. This matters
clinically - a computed interpretation is a suggestion for the clinician
to review or override, never something the software should present as if
a reference range existed when one wasn't actually configured.

Deliberately has zero dependency on the ORM/DB session - callable in
isolation, which is what makes the "thoroughly test this first" ordering
in the Feature 3 design report possible before wiring it into
`LaboratoryService.enter_results`.
"""

from decimal import Decimal

from app.models.laboratory_result import LaboratoryInterpretation, LaboratoryResultType


def interpret_result(
    *,
    result_type: LaboratoryResultType,
    numeric_value: Decimal | None,
    text_value: str | None,
    range_low: Decimal | None,
    range_high: Decimal | None,
    expected_normal_text: str | None,
) -> LaboratoryInterpretation | None:
    """Returns the suggested interpretation, or `None` if it cannot be
    safely computed (missing range/expected value, or missing/invalid
    result value)."""
    if result_type == LaboratoryResultType.NUMERIC:
        if range_low is None or range_high is None:
            return None
        if numeric_value is None:
            return None
        if numeric_value < range_low:
            return LaboratoryInterpretation.LOW
        if numeric_value > range_high:
            return LaboratoryInterpretation.HIGH
        return LaboratoryInterpretation.NORMAL

    if result_type == LaboratoryResultType.TEXT:
        if expected_normal_text is None or not expected_normal_text.strip():
            return None
        if text_value is None or not text_value.strip():
            return None
        return (
            LaboratoryInterpretation.NORMAL
            if text_value.strip().lower() == expected_normal_text.strip().lower()
            else LaboratoryInterpretation.ABNORMAL
        )

    return None
