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

Qualitative/Categorical result-entry simplification: `Categorical` results
(e.g. HBsAg Positive/Negative) are interpreted with the exact same
match-against-`expected_normal_text` rule as `Text` above - opt-in per
parameter (an Administrator must configure `expected_normal_text`, same as
Text), never invented. This intentionally reuses the Text branch's rule
rather than adding a second interpretation engine; the only difference is
which submitted field holds the value to compare (`categorical_value`
instead of `text_value`), since a Categorical result is stored in
`structured_value`, not `text_value`.

Phase 2A (Structured Result Backend Foundation): `critical_low`/
`critical_high` are additive, keyword-only, default-`None` parameters. No
existing caller passes them, so every existing call site's behavior is
byte-for-byte unchanged. They are intentionally NOT wired into
`LaboratoryService.enter_results`/`_resolve_interpretation` in this phase -
per Phase 2A's scope, this stays a foundation piece a future phase can call
with resolved reference-range values, not a live behavior change today. If
a caller does supply both, an out-of-critical-range numeric value takes
precedence over the ordinary Low/Normal/High result (checked first) -
still returns `None` (never guesses) if the critical bounds themselves are
only partially configured (one of the two is None) or the result value is
missing, matching this function's existing "never guess" contract.
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
    critical_low: Decimal | None = None,
    critical_high: Decimal | None = None,
    categorical_value: str | None = None,
) -> LaboratoryInterpretation | None:
    """Returns the suggested interpretation, or `None` if it cannot be
    safely computed (missing range/expected value, or missing/invalid
    result value)."""
    if result_type == LaboratoryResultType.NUMERIC:
        if numeric_value is None:
            return None
        if critical_low is not None and critical_high is not None:
            if numeric_value < critical_low:
                return LaboratoryInterpretation.CRITICAL_LOW
            if numeric_value > critical_high:
                return LaboratoryInterpretation.CRITICAL_HIGH
        if range_low is None or range_high is None:
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

    if result_type == LaboratoryResultType.CATEGORICAL:
        if expected_normal_text is None or not expected_normal_text.strip():
            return None
        if categorical_value is None or not categorical_value.strip():
            return None
        return (
            LaboratoryInterpretation.NORMAL
            if categorical_value.strip().lower() == expected_normal_text.strip().lower()
            else LaboratoryInterpretation.ABNORMAL
        )

    return None
