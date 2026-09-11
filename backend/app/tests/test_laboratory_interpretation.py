"""Unit tests for the pure Feature 3 interpretation function
(`app.services.laboratory_interpretation.interpret_result`).

No DB, no fixtures, no app - pure function in, enum/None out. Covers every
case enumerated in the Feature 3 design report + implementation approval:
numeric below/within/above range, missing lower/upper/both bounds, missing
or invalid numeric value, qualitative match/mismatch/no-expected-value.
"""

from decimal import Decimal

import pytest

from app.models.laboratory_result import LaboratoryInterpretation, LaboratoryResultType
from app.services.laboratory_interpretation import interpret_result

NUMERIC = LaboratoryResultType.NUMERIC
TEXT = LaboratoryResultType.TEXT
CATEGORICAL = LaboratoryResultType.CATEGORICAL
TITER = LaboratoryResultType.TITER
LOW = LaboratoryInterpretation.LOW
NORMAL = LaboratoryInterpretation.NORMAL
HIGH = LaboratoryInterpretation.HIGH
ABNORMAL = LaboratoryInterpretation.ABNORMAL


def _numeric(value, low=Decimal("12.0"), high=Decimal("16.0")):
    return interpret_result(
        result_type=NUMERIC, numeric_value=value, text_value=None,
        range_low=low, range_high=high, expected_normal_text=None,
    )


def _titer(value, low=None, high=Decimal("200")):
    return interpret_result(
        result_type=TITER, numeric_value=None, text_value=value,
        range_low=low, range_high=high, expected_normal_text=None,
    )


def _text(value, expected="Negative"):
    return interpret_result(
        result_type=TEXT, numeric_value=None, text_value=value,
        range_low=None, range_high=None, expected_normal_text=expected,
    )


def _categorical(value, expected="Negative"):
    return interpret_result(
        result_type=CATEGORICAL, numeric_value=None, text_value=None,
        range_low=None, range_high=None, expected_normal_text=expected,
        categorical_value=value,
    )


class TestNumericInterpretation:
    def test_value_below_range_is_low(self):
        assert _numeric(Decimal("10.0")) == LOW

    def test_value_at_exact_lower_bound_is_normal(self):
        # Inclusive bounds: exactly the lower bound is still within range.
        assert _numeric(Decimal("12.0")) == NORMAL

    def test_value_within_range_is_normal(self):
        assert _numeric(Decimal("14.0")) == NORMAL

    def test_value_at_exact_upper_bound_is_normal(self):
        assert _numeric(Decimal("16.0")) == NORMAL

    def test_value_above_range_is_high(self):
        assert _numeric(Decimal("18.0")) == HIGH

    def test_missing_lower_bound_returns_none(self):
        assert _numeric(Decimal("14.0"), low=None, high=Decimal("16.0")) is None

    def test_missing_upper_bound_returns_none(self):
        assert _numeric(Decimal("14.0"), low=Decimal("12.0"), high=None) is None

    def test_missing_both_bounds_returns_none(self):
        assert _numeric(Decimal("14.0"), low=None, high=None) is None

    def test_missing_numeric_value_returns_none_even_with_valid_range(self):
        assert _numeric(None) is None

    def test_missing_numeric_value_and_missing_range_returns_none(self):
        assert _numeric(None, low=None, high=None) is None


class TestQualitativeInterpretation:
    def test_case_insensitive_exact_match_is_normal(self):
        assert _text("negative") == NORMAL
        assert _text("Negative") == NORMAL
        assert _text("NEGATIVE") == NORMAL

    def test_match_with_incidental_whitespace_is_normal(self):
        assert _text("  Negative  ") == NORMAL

    def test_mismatch_is_abnormal(self):
        assert _text("Positive") == ABNORMAL
        assert _text("Trace") == ABNORMAL

    def test_no_expected_normal_text_returns_none(self):
        assert _text("Negative", expected=None) is None

    def test_blank_expected_normal_text_returns_none(self):
        assert _text("Negative", expected="   ") is None

    def test_missing_text_value_returns_none_even_with_expected_value(self):
        assert _text(None) is None

    def test_blank_text_value_returns_none(self):
        assert _text("   ") is None


class TestCategoricalInterpretation:
    """Qualitative/Categorical result-entry simplification: same
    match-against-`expected_normal_text` rule as `TestQualitativeInterpretation`
    above (Text), just reading the selected value from `categorical_value`
    instead of `text_value` - see HBsAg (Positive/Negative) example."""

    def test_matching_value_is_normal(self):
        assert _categorical("Negative") == NORMAL
        assert _categorical("negative") == NORMAL
        assert _categorical("  Negative  ") == NORMAL

    def test_mismatching_value_is_abnormal(self):
        assert _categorical("Positive") == ABNORMAL

    def test_no_expected_normal_text_returns_none(self):
        assert _categorical("Negative", expected=None) is None

    def test_blank_expected_normal_text_returns_none(self):
        assert _categorical("Negative", expected="   ") is None

    def test_missing_categorical_value_returns_none_even_with_expected_value(self):
        assert _categorical(None) is None

    def test_blank_categorical_value_returns_none(self):
        assert _categorical("   ") is None


class TestTiterInterpretation:
    """Titer results are free text in the clinic's own "1:N" ratio
    notation (e.g. "1:400") - never a parseable plain number like Numeric.
    Only the denominator (N) is compared against a configured threshold.
    Unlike Numeric, EITHER bound alone is enough to interpret (real titer
    reporting is almost always one-sided, e.g. ASO "< 1:200" with no
    clinically meaningful floor)."""

    def test_denominator_above_high_threshold_is_high(self):
        assert _titer("1:400", high=Decimal("200")) == HIGH

    def test_denominator_at_exact_high_threshold_is_normal(self):
        assert _titer("1:200", high=Decimal("200")) == NORMAL

    def test_denominator_below_high_threshold_is_normal(self):
        assert _titer("1:100", high=Decimal("200")) == NORMAL

    def test_denominator_below_low_threshold_is_low(self):
        assert _titer("1:5", low=Decimal("10"), high=None) == LOW

    def test_denominator_at_exact_low_threshold_is_normal(self):
        assert _titer("1:10", low=Decimal("10"), high=None) == NORMAL

    def test_only_high_threshold_configured_is_sufficient(self):
        # Unlike Numeric, a single configured bound is enough - most real
        # titer templates only ever set a ceiling.
        assert _titer("1:400", low=None, high=Decimal("200")) == HIGH
        assert _titer("1:100", low=None, high=Decimal("200")) == NORMAL

    def test_only_low_threshold_configured_is_sufficient(self):
        assert _titer("1:5", low=Decimal("10"), high=None) == LOW
        assert _titer("1:50", low=Decimal("10"), high=None) == NORMAL

    def test_missing_both_bounds_returns_none(self):
        assert _titer("1:400", low=None, high=None) is None

    def test_missing_text_value_returns_none_even_with_valid_range(self):
        assert _titer(None) is None

    def test_blank_text_value_returns_none(self):
        assert _titer("   ") is None

    def test_unparseable_value_returns_none_never_guesses(self):
        assert _titer("Reactive") is None
        assert _titer("Negative") is None
        assert _titer("1/400") is None
        assert _titer("400") is None

    def test_whitespace_around_colon_is_tolerated(self):
        assert _titer("1 : 400", high=Decimal("200")) == HIGH
        assert _titer("1:  400", high=Decimal("200")) == HIGH


class TestUnknownOrUnsupportedInput:
    def test_unsupported_result_type_defensive_fallback_returns_none(self):
        # interpret_result only knows NUMERIC/TEXT - anything else (should
        # never happen given the enum, but defensively) must not guess.
        class _Bogus:
            pass

        result = interpret_result(
            result_type=_Bogus(), numeric_value=Decimal("1"), text_value="x",
            range_low=Decimal("0"), range_high=Decimal("2"), expected_normal_text="x",
        )
        assert result is None


@pytest.mark.parametrize(
    ("value", "low", "high", "expected"),
    [
        (Decimal("11.9999"), Decimal("12.0"), Decimal("16.0"), LOW),
        (Decimal("16.0001"), Decimal("12.0"), Decimal("16.0"), HIGH),
        (Decimal("0"), Decimal("0"), Decimal("0"), NORMAL),
        (Decimal("-5"), Decimal("-10"), Decimal("10"), NORMAL),
        (Decimal("-15"), Decimal("-10"), Decimal("10"), LOW),
    ],
)
def test_numeric_boundary_and_edge_cases(value, low, high, expected):
    assert _numeric(value, low=low, high=high) == expected
