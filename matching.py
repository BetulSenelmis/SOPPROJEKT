"""Standalone explainable distance-based education matching."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

import pandas as pd

from data.education_profiles import (
    ABILITIES,
    INTEREST_AREAS,
    PROFILE_DIMENSIONS,
    normalize_text,
)

MIN_SHARED_DIMENSIONS = 8
CORE_DIMENSIONS = (
    "faglig_interesse",
    "faglige_styrker",
    "faglig_fordybelse",
    "praktisk_læring",
    "teoretisk_læring",
    "samarbejde",
    "selvstændighed",
    "projektarbejde",
    "teknologi",
    "data_analytisk",
    "jobsikkerhed",
    "løn_økonomi",
    "karrieremuligheder",
)
SECONDARY_DIMENSIONS = (
    "kreativitet",
    "mennesker",
    "variation",
    "internationalitet",
)
DIMENSION_WEIGHTS = {
    "faglig_interesse": 1.5,
    "faglige_styrker": 1.25,
    "faglig_fordybelse": 1.5,
    "praktisk_læring": 1.0,
    "teoretisk_læring": 1.0,
    "samarbejde": 0.8,
    "selvstændighed": 0.8,
    "projektarbejde": 0.8,
    "teknologi": 1.25,
    "data_analytisk": 1.25,
    "jobsikkerhed": 0.75,
    "løn_økonomi": 0.75,
    "karrieremuligheder": 0.75,
    "kreativitet": 0.5,
    "mennesker": 0.5,
    "variation": 0.5,
    "internationalitet": 0.5,
}
BLOCK_WEIGHTS = {"core": 0.8, "secondary": 0.2}
SCORE_INTERPRETATION = (
    "Samlet lighed mellem brugerprofilen og de tilgængelige uddannelsesdata; "
    "ikke en sandsynlighed for optagelse, gennemførelse eller trivsel, "
    "og ikke en objektiv vurdering af, hvilken uddannelse eleven bør vælge."
)


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _flatten_dimensions(profile: Mapping[str, Any]) -> dict[str, dict[str, float]]:
    flattened: dict[str, dict[str, float]] = {}
    for dimension in PROFILE_DIMENSIONS:
        value = profile.get(dimension)
        if isinstance(value, Mapping):
            values = {
                str(key): number
                for key, item in value.items()
                if (number := _number(item)) is not None
            }
        else:
            number = _number(value)
            values = {"value": number} if number is not None else {}
        if any(not 1 <= number <= 5 for number in values.values()):
            raise ValueError("Dimensionsscorer skal ligge på skalaen 1-5.")
        if values:
            flattened[dimension] = values
    return flattened


def _subject_areas(subjects: Sequence[str]) -> set[str]:
    mapped: set[str] = set()
    subject_map = {
        "matematik": ("Matematik",),
        "programmering": ("Teknologi og IT", "Matematik"),
        "softwareudvikling": ("Teknologi og IT", "Matematik"),
        "datalogi": ("Teknologi og IT", "Matematik"),
        "fysik": ("Naturvidenskab", "Teknologi og IT"),
        "kemi": ("Naturvidenskab", "Medicin og sundhed"),
        "biologi": ("Naturvidenskab", "Medicin og sundhed", "Miljø og klima"),
        "bioteknologi": ("Naturvidenskab", "Medicin og sundhed", "Teknologi og IT"),
        "geografi": ("Naturvidenskab", "Miljø og klima", "Samfund og politik"),
        "informatik": ("Teknologi og IT", "Matematik"),
        "teknikfag": ("Teknologi og IT", "Naturvidenskab"),
        "samfundsfag": ("Samfund og politik", "Mennesker og sociale forhold"),
        "historie": ("Historie og kultur", "Samfund og politik"),
        "psykologi": ("Psykologi", "Mennesker og sociale forhold"),
        "international økonomi": ("Økonomi og business", "Samfund og politik"),
        "virksomhedsøkonomi": ("Økonomi og business", "Matematik"),
        "afsætning": ("Økonomi og business", "Medier og kommunikation"),
        "erhvervsjura": ("Jura", "Økonomi og business"),
        "sprog": ("Sprog og kommunikation", "Historie og kultur"),
        "dansk": ("Sprog og kommunikation", "Medier og kommunikation"),
        "engelsk": ("Sprog og kommunikation", "Historie og kultur"),
        "mediefag": ("Medier og kommunikation", "Kreativitet og design"),
        "design": ("Kreativitet og design", "Teknologi og IT"),
        "kunstneriske fag": ("Kreativitet og design", "Historie og kultur"),
    }
    for subject in subjects:
        normalized = normalize_text(subject)
        for term, areas in subject_map.items():
            if normalize_text(term) in normalized:
                mapped.update(areas)
    return mapped


def _areas_from_text(value: Any) -> set[str]:
    if not isinstance(value, str) or not value.strip():
        return set()
    normalized = normalize_text(value)
    mapped = _subject_areas([value])
    for area in INTEREST_AREAS:
        if normalize_text(area) in normalized:
            mapped.add(area)
    return mapped


def user_profile_from_questionnaire(profile: Mapping[str, Any]) -> dict[str, Any]:
    """Map existing app answers into matching dimensions without merging signals.

    Favorite/least-liked subjects affect interest; self-assessed abilities and
    strongest subjects affect strengths; intended further-study subjects remain
    a separate focus dimension.
    """
    interests = profile.get("interesser", {})
    interests = interests if isinstance(interests, Mapping) else {}
    favorite_subjects = profile.get("bedste_fag", [])
    least_subjects = profile.get("mindst_fag", [])
    study_intent = profile.get("universitetsfag", "")
    strongest_subjects = profile.get("staerkeste_fag", [])
    job_area_map = {
        "Teknologi / IT": {"Teknologi og IT", "Matematik"},
        "Ingeniørarbejde": {"Teknologi og IT", "Naturvidenskab", "Matematik"},
        "Sundhed": {"Medicin og sundhed", "Naturvidenskab", "Mennesker og sociale forhold"},
        "Forskning": {"Naturvidenskab", "Matematik", "Samfund og politik"},
        "Økonomi": {"Økonomi og business", "Matematik"},
        "Business": {"Økonomi og business", "Samfund og politik"},
        "Jura": {"Jura", "Samfund og politik"},
        "Undervisning": {"Mennesker og sociale forhold", "Sprog og kommunikation"},
        "Psykologi": {"Psykologi", "Mennesker og sociale forhold"},
        "Kommunikation": {"Sprog og kommunikation", "Medier og kommunikation"},
        "Design": {"Kreativitet og design", "Medier og kommunikation"},
        "Medier": {"Medier og kommunikation", "Kreativitet og design"},
        "Politik / samfund": {"Samfund og politik", "Mennesker og sociale forhold"},
        "Natur / miljø": {"Naturvidenskab", "Miljø og klima"},
    }
    selected_job_areas = profile.get("jobomraader", [])
    selected_job_areas = (
        selected_job_areas
        if isinstance(selected_job_areas, Sequence) and not isinstance(selected_job_areas, str)
        else []
    )
    desired_areas = set().union(
        *(
            job_area_map.get(str(area), set())
            for area in selected_job_areas
        )
    ) if selected_job_areas else set()
    excluded_areas = set()
    excluded_interest_areas = profile.get("undgaa", [])
    if isinstance(excluded_interest_areas, Sequence) and not isinstance(excluded_interest_areas, str):
        for area in excluded_interest_areas:
            excluded_areas.update(_areas_from_text(str(area)))
    excluded_areas.update(_areas_from_text(profile.get("undgaa_andet")))
    excluded_areas.update(_areas_from_text(profile.get("undgaa_job")))

    area_interest: dict[str, float | None] = {}
    for area in INTEREST_AREAS:
        value = _number(interests.get(area))
        if area in desired_areas:
            value = max(value or 1.0, 4.5)
        if value is None:
            area_interest[area] = None
        else:
            adjustment = 0.5 * (area in _subject_areas(favorite_subjects))
            adjustment -= 0.5 * (area in _subject_areas(least_subjects))
            area_interest[area] = min(5.0, max(1.0, value + adjustment))
        if area in excluded_areas:
            area_interest[area] = min(area_interest[area] or 3.0, 1.5)

    ability_values = profile.get("evner", {})
    ability_values = ability_values if isinstance(ability_values, Mapping) else {}
    strengths: dict[str, float | None] = {
        ability: _number(ability_values.get(ability)) for ability in ABILITIES
    }
    strongest_areas = _subject_areas(strongest_subjects)
    strength_to_area = {
        "Matematiske problemer": {"Matematik"},
        "Logisk tænkning": {"Matematik", "Teknologi og IT"},
        "Analyse": {"Matematik", "Naturvidenskab", "Data og information"},
        "Problemløsning": {"Matematik", "Teknologi og IT", "Naturvidenskab"},
        "Kreativ tænkning": {"Kreativitet og design", "Medier og kommunikation"},
        "Skriftlig kommunikation": {"Sprog og kommunikation", "Medier og kommunikation"},
        "Mundtlig kommunikation": {"Sprog og kommunikation", "Mennesker og sociale forhold"},
        "At lære nye ting": set(INTEREST_AREAS),
        "At arbejde selvstændigt": set(),
        "At arbejde sammen med andre": {"Mennesker og sociale forhold"},
        "Teknologi og computere": {"Teknologi og IT"},
        "At arbejde med data": {"Matematik", "Økonomi og business", "Teknologi og IT"},
    }
    for ability, related_areas in strength_to_area.items():
        if strongest_areas.intersection(related_areas):
            current = strengths[ability]
            strengths[ability] = max(current or 1.0, 4.5)

    intent_areas = (
        _subject_areas([study_intent])
        if isinstance(study_intent, str) and study_intent.strip()
        else set()
    )
    study_ideas = profile.get("uddannelser_tanker", "")
    if profile.get("uddannelser_tanker_svar") == "Ja" and isinstance(study_ideas, str):
        intent_areas.update(_subject_areas([study_ideas]))
    intent_areas.update(desired_areas)
    focused_studies = {
        area: 5.0 if area in intent_areas else None
        for area in INTEREST_AREAS
    }
    if profile.get("universitetsfag_svar") != "Ja":
        focused_studies = {area: None for area in INTEREST_AREAS}
    for area in desired_areas - excluded_areas:
        focused_studies[area] = 4.0
    for area in excluded_areas:
        focused_studies[area] = None
    if profile.get("uddannelser_tanker_svar") == "Ja":
        for area in intent_areas - excluded_areas:
            focused_studies[area] = 4.5

    work_style = _number(profile.get("arbejdsform"))
    practical_learning = _number(profile.get("teori_praksis"))
    work_values = profile.get("jobvaerdier", {})
    work_values = work_values if isinstance(work_values, Mapping) else {}
    workday = profile.get("arbejdsdag", [])
    workday = (
        workday
        if isinstance(workday, Sequence) and not isinstance(workday, str)
        else []
    )
    selected_tasks = {normalize_text(str(activity)) for activity in workday}
    work_values = {
        str(key): _number(value)
        for key, value in work_values.items()
    }
    human_workday = "arbejde med mennesker" in selected_tasks
    data_workday = "arbejde med tal/data" in selected_tasks
    analysis_workday = "analysere information" in selected_tasks
    creative_workday = "skabe/design" in selected_tasks
    technology_workday = "arbejde ved computer" in selected_tasks or (
        "bygge eller udvikle produkter" in selected_tasks
    )
    research_workday = "forske/undersøge" in selected_tasks
    project_workday = any(
        task in selected_tasks
        for task in (
            "planlægge og organisere",
            "bygge eller udvikle produkter",
            "lose problemer",
            "skabe/design",
        )
    )
    technology_value = _mean_valid(
        [_number(profile.get("teknologi_vigtigt")), work_values.get("At arbejde med teknologi")]
    )
    creativity_value = _mean_valid(
        [_number(profile.get("kreativitet_vigtigt")), work_values.get("Kreativ frihed")]
    )
    people_value = _mean_valid(
        [_number(profile.get("mennesker_vigtigt")), work_values.get("At hjælpe andre mennesker")]
    )
    variation_value = _mean_valid(
        [_number(profile.get("forudsigelighed")), work_values.get("Fleksibilitet")]
    )
    technology_value = max(
        [value for value in (technology_value, 4.5 if technology_workday else None) if value is not None],
        default=None,
    )
    creativity_value = max(
        [value for value in (creativity_value, 4.5 if creative_workday else None) if value is not None],
        default=None,
    )
    people_value = max(
        [value for value in (people_value, 4.5 if human_workday else None) if value is not None],
        default=None,
    )
    data_value = max(
        [
            value
            for value in (
                _number(profile.get("data_vigtigt")),
                4.5 if data_workday or analysis_workday or research_workday else None,
            )
            if value is not None
        ],
        default=None,
    )
    project_value = (
        4.5 if project_workday
        else 3.0 if workday
        else None
    )
    if project_value is None and research_workday:
        project_value = 4.0
    if "skrive og kommunikere" in selected_tasks:
        area_interest["Sprog og kommunikation"] = max(
            area_interest["Sprog og kommunikation"] or 1.0, 4.5
        )
        area_interest["Medier og kommunikation"] = max(
            area_interest["Medier og kommunikation"] or 1.0, 4.5
        )
    if technology_workday:
        area_interest["Teknologi og IT"] = max(
            area_interest["Teknologi og IT"] or 1.0, 4.5
        )
    if research_workday:
        area_interest["Naturvidenskab"] = max(
            area_interest["Naturvidenskab"] or 1.0, 4.0
        )
    return {
        "faglig_interesse": area_interest,
        "faglige_styrker": strengths,
        "faglig_fordybelse": focused_studies,
        "teknologi": technology_value,
        "data_analytisk": data_value,
        "kreativitet": creativity_value,
        "mennesker": people_value,
        "samarbejde": work_style,
        "selvstændighed": 6.0 - work_style if work_style is not None else None,
        "praktisk_læring": practical_learning,
        "teoretisk_læring": 6.0 - practical_learning if practical_learning is not None else None,
        "projektarbejde": project_value,
        "variation": variation_value,
        "internationalitet": _number(work_values.get("At arbejde internationalt")),
        "jobsikkerhed": _number(work_values.get("Jobsikkerhed")),
        "løn_økonomi": _number(work_values.get("Høj løn")),
        "karrieremuligheder": _mean_valid(
            [
                _number(profile.get("jobmuligheder_vigtigt")),
                _number(work_values.get("Gode muligheder for karriereudvikling")),
            ]
        ),
        "study_intent_answer": profile.get("universitetsfag_svar"),
        "study_intent_subjects": study_intent,
    }


def _mean_valid(values: Sequence[Any]) -> float | None:
    numbers = [number for item in values if (number := _number(item)) is not None]
    return sum(numbers) / len(numbers) if numbers else None


def filter_by_admission_requirements(
    education_profiles: pd.DataFrame,
    eligibility_by_udbud_id: Mapping[Any, bool | None] | None = None,
    *,
    require_verified: bool = False,
) -> pd.DataFrame:
    """Apply external, verified eligibility independently from fit scoring.

    UFSN workbook rows do not contain admission requirements. `True` marks a
    verified eligible offer, `False` excludes it, and `None` remains unknown.
    Strict filtering excludes unknown records as well.
    """
    filtered = education_profiles.copy()
    if eligibility_by_udbud_id is None:
        if require_verified:
            return filtered.iloc[0:0].assign(admission_status=pd.Series(dtype="object"))
        if "admission_status" not in filtered.columns:
            filtered["admission_status"] = "unknown"
        return filtered

    statuses = []
    for offer_id in filtered.get("udbud_id", pd.Series(index=filtered.index, dtype="object")):
        status = eligibility_by_udbud_id.get(offer_id)
        if status is None:
            status = eligibility_by_udbud_id.get(str(offer_id))
        statuses.append("eligible" if status is True else "not_eligible" if status is False else "unknown")
    filtered["admission_status"] = statuses
    if require_verified:
        return filtered.loc[filtered["admission_status"] == "eligible"].copy()
    return filtered.loc[filtered["admission_status"] != "not_eligible"].copy()


def _row_profile(row: pd.Series) -> dict[str, Any]:
    return {dimension: row.get(dimension) for dimension in PROFILE_DIMENSIONS}


def _dimension_matches(
    user_dimensions: Mapping[str, Mapping[str, float]],
    education_dimensions: Mapping[str, Mapping[str, float]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    matches: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []
    for dimension in PROFILE_DIMENSIONS:
        user_values = user_dimensions.get(dimension, {})
        education_values = education_dimensions.get(dimension, {})
        common = sorted(user_values.keys() & education_values.keys())
        if not common:
            user_keys = sorted(user_values)
            education_keys = sorted(education_values)
            missing_from = []
            if not user_keys:
                missing_from.append("user")
            if not education_keys:
                missing_from.append("education")
            missing.append(
                {
                    "dimension": dimension,
                    "missing_from": missing_from or ["no_common_values"],
                    "user_values_available": len(user_keys),
                    "education_values_available": len(education_keys),
                }
            )
            continue
        errors = [
            (user_values[key] - education_values[key]) ** 2
            for key in common
        ]
        group_distance = math.sqrt(sum(errors) / len(errors))
        matches.append(
            {
                "dimension": dimension,
                "similarity": round(max(0.0, 100.0 * (1.0 - group_distance / 4.0)), 1),
                "compared_values": len(common),
                "user_values_available": len(user_values),
                "education_values_available": len(education_values),
            }
        )
    return matches, missing


def _coverage_level(coverage_ratio: float) -> str:
    if coverage_ratio < 0.5:
        return "low"
    if coverage_ratio < 0.8:
        return "medium"
    return "high"


def _score_dimensions(
    matches: Sequence[Mapping[str, Any]],
) -> tuple[float | None, list[dict[str, Any]], dict[str, float]]:
    core = [item for item in matches if item["dimension"] in CORE_DIMENSIONS]
    secondary = [item for item in matches if item["dimension"] in SECONDARY_DIMENSIONS]
    if not core:
        return None, [], {}

    def weighted_mean(items: Sequence[Mapping[str, Any]]) -> float:
        denominator = sum(DIMENSION_WEIGHTS[str(item["dimension"])] for item in items)
        return sum(
            DIMENSION_WEIGHTS[str(item["dimension"])] * float(item["similarity"])
            for item in items
        ) / denominator

    core_score = weighted_mean(core)
    secondary_score = weighted_mean(secondary) if secondary else None
    available_blocks = {
        "core": BLOCK_WEIGHTS["core"],
        **({"secondary": BLOCK_WEIGHTS["secondary"]} if secondary else {}),
    }
    normalization = sum(available_blocks.values())
    effective_block_weights = {
        block: weight / normalization for block, weight in available_blocks.items()
    }
    final_score = effective_block_weights["core"] * core_score
    if secondary_score is not None:
        final_score += effective_block_weights["secondary"] * secondary_score

    explanations: list[dict[str, Any]] = []
    for item in matches:
        dimension = str(item["dimension"])
        block = "core" if dimension in CORE_DIMENSIONS else "secondary"
        block_items = core if block == "core" else secondary
        block_dimension_weight = sum(
            DIMENSION_WEIGHTS[str(other["dimension"])] for other in block_items
        )
        share = (
            effective_block_weights[block]
            * DIMENSION_WEIGHTS[dimension]
            / block_dimension_weight
        )
        unrounded_impact = share * (float(item["similarity"]) - 50.0)
        explanations.append(
            {
                **item,
                "group": block,
                "weight": DIMENSION_WEIGHTS[dimension],
                "weighted_score_points": round(share * float(item["similarity"]), 2),
                "impact_from_neutral_points": round(unrounded_impact, 2),
                "_unrounded_impact_from_neutral_points": unrounded_impact,
            }
        )
    explanations.sort(
        key=lambda item: (
            -item["impact_from_neutral_points"],
            -item["similarity"],
            item["dimension"],
        )
    )
    return round(final_score, 1), explanations, effective_block_weights


def _title_key(title: Any) -> str:
    from data.education_profiles import normalize_text

    return normalize_text(title)


def rank_education(
    user_profile: Mapping[str, Any],
    education_profiles: pd.DataFrame,
    *,
    top_n: int = 5,
) -> list[dict[str, Any]]:
    """Rank unique education titles; keep all offer locations as alternatives.

    The match score represents fit only. Data coverage is reported separately
    as the number of comparable dimensions out of the complete profile schema.
    """
    if top_n < 1:
        raise ValueError("top_n skal være mindst 1.")
    if education_profiles.empty:
        return []
    if not isinstance(user_profile, Mapping):
        raise TypeError("user_profile skal være en mapping af dimensionsnavne til scorer.")

    user_dimensions = _flatten_dimensions(user_profile)
    if not user_dimensions:
        raise ValueError("Brugerprofilen har ingen numeriske værdier, der kan matches.")

    ranked_offers: list[dict[str, Any]] = []
    for _, row in education_profiles.iterrows():
        education_dimensions = _flatten_dimensions(_row_profile(row))
        dimension_matches, missing_dimensions = _dimension_matches(
            user_dimensions,
            education_dimensions,
        )
        score, explanations, block_weights = _score_dimensions(dimension_matches)
        positive_dimensions = [
            item
            for item in explanations
            if item["_unrounded_impact_from_neutral_points"] > 0
        ]
        negative_dimensions = [
            item
            for item in explanations
            if item["_unrounded_impact_from_neutral_points"] < 0
        ]
        positive_dimensions.sort(
            key=lambda item: (
                -item["impact_from_neutral_points"],
                -item["similarity"],
                item["dimension"],
            )
        )
        negative_dimensions.sort(
            key=lambda item: (
                item["impact_from_neutral_points"],
                item["similarity"],
                item["dimension"],
            )
        )
        weakest_dimensions = sorted(
            explanations,
            key=lambda item: (
                item["similarity"],
                item["impact_from_neutral_points"],
                item["dimension"],
            ),
        )[:5]
        partial_dimensions = [
            {
                "dimension": item["dimension"],
                "compared_values": item["compared_values"],
                "user_values_available": item["user_values_available"],
                "education_values_available": item["education_values_available"],
            }
            for item in dimension_matches
            if item["compared_values"]
            < max(item["user_values_available"], item["education_values_available"])
        ]
        for explanation in explanations:
            explanation.pop("_unrounded_impact_from_neutral_points")
        item = {
            column: row[column]
            for column in (
                "artikel_id",
                "udbud_id",
                "url",
                "udd6",
                "Titel",
                "Educational_Category",
                "displaydocclass",
                "institution",
                "kommune",
                "region",
                "education_profile_coverage_count",
                "education_profile_coverage_total",
                "education_profile_coverage_ratio",
                "admission_status",
                "profile_origin",
            )
            if column in row.index
        }
        item.setdefault("admission_status", "unknown")
        item["match_score"] = score
        item["score_interpretation"] = SCORE_INTERPRETATION
        item["matched_dimensions"] = explanations
        item["strongest_positive_dimensions"] = positive_dimensions[:5]
        item["weakest_dimensions"] = weakest_dimensions
        item["negative_impact_dimensions"] = negative_dimensions[:5]
        item["missing_dimensions"] = missing_dimensions
        item["partial_dimensions"] = partial_dimensions
        item["scoring_block_weights"] = block_weights
        item["dimensions_compared"] = len(dimension_matches)
        item["data_coverage_count"] = len(dimension_matches)
        item["data_coverage_total"] = len(PROFILE_DIMENSIONS)
        item["data_coverage_ratio"] = len(dimension_matches) / len(PROFILE_DIMENSIONS)
        item["data_coverage_level"] = _coverage_level(item["data_coverage_ratio"])
        item["eligible_for_ranking"] = (
            score is not None
            and len(dimension_matches) >= MIN_SHARED_DIMENSIONS
        )
        ranked_offers.append(item)

    by_title: dict[str, list[dict[str, Any]]] = {}
    for item in ranked_offers:
        by_title.setdefault(_title_key(item.get("Titel", "")), []).append(item)

    ranked_titles: list[dict[str, Any]] = []
    for title_offers in by_title.values():
        title_offers.sort(
            key=lambda item: (
                not item["eligible_for_ranking"],
                -item["match_score"] if item["eligible_for_ranking"] else 0.0,
                -item["data_coverage_count"],
                str(item.get("udbud_id", "")),
            )
        )
        ranked_offers_for_title = [item for item in title_offers if item["eligible_for_ranking"]]
        if not ranked_offers_for_title:
            continue
        best = ranked_offers_for_title[0].copy()
        best["offers"] = [
            {
                "artikel_id": offer.get("artikel_id"),
                "udbud_id": offer.get("udbud_id"),
                "url": offer.get("url"),
                "udd6": offer.get("udd6"),
                "Educational_Category": offer.get("Educational_Category"),
                "institution": offer.get("institution"),
                "kommune": offer.get("kommune"),
                "region": offer.get("region"),
                "displaydocclass": offer.get("displaydocclass"),
                "admission_status": offer.get("admission_status"),
                "match_score": offer.get("match_score") if offer["eligible_for_ranking"] else None,
                "data_coverage_count": offer.get("data_coverage_count"),
                "data_coverage_total": offer.get("data_coverage_total"),
                "data_coverage_ratio": offer.get("data_coverage_ratio"),
                "data_coverage_level": offer.get("data_coverage_level"),
                "education_profile_coverage_count": offer.get("education_profile_coverage_count"),
                "education_profile_coverage_total": offer.get("education_profile_coverage_total"),
                "education_profile_coverage_ratio": offer.get("education_profile_coverage_ratio"),
            }
            for offer in title_offers
        ]
        best["offers_with_match_score"] = len(ranked_offers_for_title)
        best["offer_count"] = len(title_offers)
        ranked_titles.append(best)

    ranked_titles.sort(
        key=lambda item: (
            -item["match_score"],
            -item["data_coverage_count"],
            _title_key(item.get("Titel", "")),
            str(item.get("udbud_id", "")),
        )
    )
    return ranked_titles[:top_n]


__all__ = [
    "filter_by_admission_requirements",
    "rank_education",
    "user_profile_from_questionnaire",
]
