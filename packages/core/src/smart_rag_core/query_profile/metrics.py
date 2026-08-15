"""Per-field query-profile scoring and first-failure attribution."""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from smart_rag_core.evaluation.classes import RuntimeOwner
from smart_rag_core.evaluation.schema import (
    EvaluationCase,
    ExpectedProfile,
    FailureStage,
)
from smart_rag_core.query_profile.profiler import profile_query_sync

LANGUAGE_ACCURACY_MIN = 0.95
TEMPORAL_MACRO_F1_MIN = 0.90
CODE_DATE_F1_MIN = 0.98
ENTITY_ALIAS_MACRO_F1_MIN = 0.90
FILTER_PR_MIN = 0.95
TYPE_REL_TABLE_DECOMP_MACRO_F1_MIN = 0.90


@dataclass(frozen=True, slots=True)
class FieldScore:
    """One named metric with its signed threshold.

    Attributes:
        name: Metric name.
        value: Observed score in ``[0, 1]``.
        threshold: Signed minimum.
        passed: Whether the gate holds.
    """

    name: str
    value: float
    threshold: float
    passed: bool


@dataclass(frozen=True, slots=True)
class ProfileEvalReport:
    """Open-split profile evaluation for one split.

    Attributes:
        split: Split name.
        case_count: Scored cases.
        model_calls: Sum of profile model calls. Must stay 0 on the corpus path.
        scores: Gated metrics.
        extra: Ungated diagnostics including historical/variant fidelity.
        first_failures: Case id to first failing stage.
        passed: All gated scores met their thresholds.
    """

    split: str
    case_count: int
    model_calls: int
    scores: tuple[FieldScore, ...]
    extra: tuple[FieldScore, ...]
    first_failures: dict[str, str]
    passed: bool


def _as_list(value: object) -> list[str]:
    """Normalize a profile field value to a string list.

    Args:
        value: Profile field value.

    Returns:
        String items. ``None`` becomes empty.
    """

    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in cast("list[object]", value)]
    if isinstance(value, bool):
        return [str(value).lower()]
    return [str(value)]


def _f1(true_positive: int, false_positive: int, false_negative: int) -> float:
    """Return F1 with empty-empty defined as 1.0.

    Args:
        true_positive: Intersection count.
        false_positive: Predicted extras.
        false_negative: Missed gold.

    Returns:
        F1 in ``[0, 1]``.
    """

    if true_positive == 0 and false_positive == 0 and false_negative == 0:
        return 1.0
    precision = (
        true_positive / (true_positive + false_positive)
        if (true_positive + false_positive)
        else 0.0
    )
    recall = (
        true_positive / (true_positive + false_negative)
        if (true_positive + false_negative)
        else 0.0
    )
    if precision + recall == 0:
        return 0.0
    return 2.0 * precision * recall / (precision + recall)


def _token_prf(
    golds: list[list[str]], preds: list[list[str]]
) -> tuple[float, float, float]:
    """Micro precision, recall, and F1 over list fields.

    Args:
        golds: Gold token lists.
        preds: Predicted token lists.

    Returns:
        Precision, recall, F1.
    """

    true_positive = false_positive = false_negative = 0
    for gold, pred in zip(golds, preds, strict=True):
        gold_set, pred_set = set(gold), set(pred)
        true_positive += len(gold_set.intersection(pred_set))
        false_positive += len(pred_set - gold_set)
        false_negative += len(gold_set - pred_set)
    f1_value = _f1(true_positive, false_positive, false_negative)
    precision = (
        true_positive / (true_positive + false_positive)
        if (true_positive + false_positive)
        else 1.0
    )
    recall = (
        true_positive / (true_positive + false_negative)
        if (true_positive + false_negative)
        else 1.0
    )
    return precision, recall, f1_value


def _macro_f1(pairs: list[tuple[str, str]]) -> float:
    """Unweighted mean F1 over labels observed in gold or prediction.

    Args:
        pairs: ``(gold, pred)`` class labels.

    Returns:
        Macro-F1.
    """

    labels = sorted({gold for gold, _ in pairs} | {pred for _, pred in pairs})
    if not labels:
        return 1.0
    scores: list[float] = []
    for label in labels:
        true_positive = sum(gold == label and pred == label for gold, pred in pairs)
        false_positive = sum(gold != label and pred == label for gold, pred in pairs)
        false_negative = sum(gold == label and pred != label for gold, pred in pairs)
        scores.append(_f1(true_positive, false_positive, false_negative))
    return sum(scores) / len(scores)


def _boolean_f1(pairs: list[tuple[bool, bool]]) -> float:
    """F1 for a boolean field treating True as the positive class.

    Args:
        pairs: ``(gold, pred)`` booleans.

    Returns:
        F1. All-negative is 1.0.
    """

    true_positive = sum(gold and pred for gold, pred in pairs)
    false_positive = sum((not gold) and pred for gold, pred in pairs)
    false_negative = sum(gold and (not pred) for gold, pred in pairs)
    return _f1(true_positive, false_positive, false_negative)


def _aligned_codes(
    case: EvaluationCase, profile: ExpectedProfile
) -> tuple[list[str], list[str]]:
    """Score only codes that appear in the query.

    Packet 1 labels sometimes attach the class index code even when it is not
    in the query text. Extraction F1 uses in-query gold.

    Args:
        case: Labeled case.
        profile: Predicted profile.

    Returns:
        Aligned gold and predicted code lists.
    """

    gold = [
        item
        for item in _as_list(case.expected_profile.codes.value)
        if item in case.query
    ]
    pred = [item for item in _as_list(profile.codes.value) if item in case.query]
    return gold, pred


def _aligned_entities(
    case: EvaluationCase, profile: ExpectedProfile
) -> tuple[list[str], list[str]]:
    """Align entities to in-query codes plus resolved aliases.

    Args:
        case: Labeled case.
        profile: Predicted profile.

    Returns:
        Aligned gold and predicted entity lists.
    """

    gold_raw = _as_list(case.expected_profile.entities.value)
    gold = [
        item
        for item in gold_raw
        if item in case.query
        or item in _as_list(case.expected_profile.approved_aliases.value)
    ]
    return gold, _as_list(profile.entities.value)


def _score_row(name: str, value: float, threshold: float) -> FieldScore:
    """Build one gated score row.

    Args:
        name: Metric name.
        value: Observed value.
        threshold: Minimum.

    Returns:
        Field score.
    """

    return FieldScore(
        name=name, value=value, threshold=threshold, passed=value + 1e-12 >= threshold
    )


def score_cases(cases: list[EvaluationCase], *, split: str) -> ProfileEvalReport:
    """Score profile fields independently and record first failures.

    Args:
        cases: Open-split cases only. Callers must not pass holdout.
        split: Split label for the report.

    Returns:
        Report with gated and extra metrics.

    Side Effects:
        None. Does not load holdout or call a model.
    """

    languages: list[tuple[str, str]] = []
    locales: list[tuple[str, str]] = []
    temporals: list[tuple[str, str]] = []
    query_types: list[tuple[str, str]] = []
    code_gold: list[list[str]] = []
    code_pred: list[list[str]] = []
    date_gold: list[list[str]] = []
    date_pred: list[list[str]] = []
    alias_gold: list[list[str]] = []
    alias_pred: list[list[str]] = []
    entity_gold: list[list[str]] = []
    entity_pred: list[list[str]] = []
    filter_gold: list[list[str]] = []
    filter_pred: list[list[str]] = []
    rel_pairs: list[tuple[bool, bool]] = []
    table_pairs: list[tuple[bool, bool]] = []
    media_pairs: list[tuple[bool, bool]] = []
    hist_pairs: list[tuple[bool, bool]] = []
    scope_pairs: list[tuple[str, str]] = []
    neg_pairs: list[tuple[str, str]] = []
    decomp_gold: list[list[str]] = []
    decomp_pred: list[list[str]] = []
    variant_gold: list[list[str]] = []
    variant_pred: list[list[str]] = []
    first_failures: dict[str, str] = {}
    model_calls = 0

    for case in cases:
        result = profile_query_sync(case.query)
        model_calls += result.model_calls
        predicted = result.profile
        gold = case.expected_profile
        languages.append((str(gold.language.value), str(predicted.language.value)))
        locales.append(
            (
                str(gold.locale_configuration.value),
                str(predicted.locale_configuration.value),
            )
        )
        temporals.append(
            (str(gold.temporal_intent.value), str(predicted.temporal_intent.value))
        )
        query_types.append(
            (str(gold.query_type.value), str(predicted.query_type.value))
        )
        g_codes, p_codes = _aligned_codes(case, predicted)
        code_gold.append(g_codes)
        code_pred.append(p_codes)
        date_gold.append(_as_list(gold.dates.value))
        date_pred.append(_as_list(predicted.dates.value))
        alias_gold.append(_as_list(gold.approved_aliases.value))
        alias_pred.append(_as_list(predicted.approved_aliases.value))
        g_ent, p_ent = _aligned_entities(case, predicted)
        entity_gold.append(g_ent)
        entity_pred.append(p_ent)
        filter_gold.append(_as_list(gold.metadata_filters.value))
        filter_pred.append(_as_list(predicted.metadata_filters.value))
        rel_pairs.append(
            (
                bool(gold.relationship_intent.value),
                bool(predicted.relationship_intent.value),
            )
        )
        table_pairs.append(
            (bool(gold.table_intent.value), bool(predicted.table_intent.value))
        )
        media_pairs.append(
            (bool(gold.media_dependence.value), bool(predicted.media_dependence.value))
        )
        hist_pairs.append(
            (
                bool(gold.historical_relationship.value),
                bool(predicted.historical_relationship.value),
            )
        )
        scope_pairs.append(
            (str(gold.document_scope.value), str(predicted.document_scope.value))
        )
        neg_pairs.append(
            (str(gold.negation_scope.value), str(predicted.negation_scope.value))
        )
        decomp_gold.append(_as_list(gold.subquestions.value))
        decomp_pred.append(_as_list(predicted.subquestions.value))
        variant_gold.append(_as_list(gold.variants.value))
        variant_pred.append(_as_list(predicted.variants.value))

        gated_ok = (
            str(gold.language.value) == str(predicted.language.value)
            and str(gold.temporal_intent.value) == str(predicted.temporal_intent.value)
            and str(gold.query_type.value) == str(predicted.query_type.value)
            and set(g_codes) == set(p_codes)
            and set(_as_list(gold.dates.value)) == set(_as_list(predicted.dates.value))
            and set(_as_list(gold.approved_aliases.value))
            == set(_as_list(predicted.approved_aliases.value))
            and set(_as_list(gold.metadata_filters.value))
            == set(_as_list(predicted.metadata_filters.value))
            and bool(gold.relationship_intent.value)
            == bool(predicted.relationship_intent.value)
            and bool(gold.table_intent.value) == bool(predicted.table_intent.value)
            and set(_as_list(gold.subquestions.value))
            == set(_as_list(predicted.subquestions.value))
        )
        if not gated_ok:
            first_failures[case.case_id] = FailureStage.PROFILE.value
        elif case.runtime_owner is not RuntimeOwner.PHASE_4:
            first_failures[case.case_id] = FailureStage.DEFERRED_OWNER.value
        else:
            first_failures[case.case_id] = FailureStage.NONE.value

    lang_acc = sum(g == p for g, p in languages) / len(languages)
    loc_acc = sum(g == p for g, p in locales) / len(locales)
    lang_config = min(lang_acc, loc_acc)
    _code_p, _code_r, code_f1 = _token_prf(code_gold, code_pred)
    _date_p, _date_r, date_f1 = _token_prf(date_gold, date_pred)
    code_date_f1 = min(code_f1, date_f1)
    _alias_p, _alias_r, alias_f1 = _token_prf(alias_gold, alias_pred)
    _ent_p, _ent_r, entity_f1 = _token_prf(entity_gold, entity_pred)
    entity_alias = (alias_f1 + entity_f1) / 2.0
    filter_p, filter_r, _filter_f1 = _token_prf(filter_gold, filter_pred)
    type_f1 = _macro_f1(query_types)
    rel_f1 = _boolean_f1(rel_pairs)
    table_f1 = _boolean_f1(table_pairs)
    _d_p, _d_r, decomp_f1 = _token_prf(decomp_gold, decomp_pred)
    type_bundle = min(type_f1, rel_f1, table_f1, decomp_f1)
    temporal_f1 = _macro_f1(temporals)
    scores = (
        _score_row(
            "language_configuration_accuracy", lang_config, LANGUAGE_ACCURACY_MIN
        ),
        _score_row("temporal_macro_f1", temporal_f1, TEMPORAL_MACRO_F1_MIN),
        _score_row("code_date_f1", code_date_f1, CODE_DATE_F1_MIN),
        _score_row("entity_alias_macro_f1", entity_alias, ENTITY_ALIAS_MACRO_F1_MIN),
        _score_row("metadata_filter_precision", filter_p, FILTER_PR_MIN),
        _score_row("metadata_filter_recall", filter_r, FILTER_PR_MIN),
        _score_row(
            "query_type_relationship_table_decomposition_macro_f1",
            type_bundle,
            TYPE_REL_TABLE_DECOMP_MACRO_F1_MIN,
        ),
    )
    extra = (
        _score_row("negation_accuracy", _macro_f1(neg_pairs), 0.0),
        _score_row(
            "document_scope_accuracy",
            sum(gold == pred for gold, pred in scope_pairs) / len(scope_pairs),
            0.0,
        ),
        _score_row("media_dependence_f1", _boolean_f1(media_pairs), 0.0),
        _score_row("historical_relationship_f1", _boolean_f1(hist_pairs), 0.0),
        _score_row("variant_list_f1", _token_prf(variant_gold, variant_pred)[2], 0.0),
        _score_row("code_f1", code_f1, CODE_DATE_F1_MIN),
        _score_row("date_f1", date_f1, CODE_DATE_F1_MIN),
    )
    passed = all(item.passed for item in scores) and model_calls == 0
    return ProfileEvalReport(
        split=split,
        case_count=len(cases),
        model_calls=model_calls,
        scores=scores,
        extra=extra,
        first_failures=first_failures,
        passed=passed,
    )
