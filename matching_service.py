"""Application-level integration for questionnaire-based Matching v3 results."""

from collections.abc import Mapping
import re
from typing import Any

import pandas as pd

from data.education_profiles import load_education_profiles, normalize_text
from matching import rank_education, user_profile_from_questionnaire


_DIPLOMA_ENGINEER_PATTERN = re.compile(
    r"diplom[\s-]*(?:ingeni[oø]r\w*|engin[oø]r\w*|engi[oø]r\w*)",
    re.IGNORECASE,
)
_NEGATION_PATTERN = re.compile(
    r"\b(?:ikke|ingen|uden|undga\w*|udeluk\w*|fravalg\w*|nej)\b",
    re.IGNORECASE,
)
_DTU_PATTERN = re.compile(
    r"\bdtu\b|danmarks\s+tekniske\s+universitet",
    re.IGNORECASE,
)


def questionnaire_matching_preferences(
    questionnaire_answers: Mapping[str, Any],
) -> dict[str, Any]:
    """Extract explicit institution and study-type preferences from profile text."""
    institution_text = " ".join(
        str(questionnaire_answers.get(field, "") or "")
        for field in ("byer", "uddannelser_tanker", "universitetsfag", "andet")
    )
    avoid_work_text = str(questionnaire_answers.get("undgaa_job", "") or "")
    other_text = " ".join(
        str(questionnaire_answers.get(field, "") or "")
        for field in ("andet", "uddannelser_tanker")
    )
    excludes_diploma_engineering = bool(
        _DIPLOMA_ENGINEER_PATTERN.search(avoid_work_text)
        or any(
            (degree_match := _DIPLOMA_ENGINEER_PATTERN.search(clause))
            and _NEGATION_PATTERN.search(clause[: degree_match.start()])
            for clause in re.split(r"[.!?;\n]+", other_text)
        )
    )
    return {
        "institution": "DTU" if _DTU_PATTERN.search(institution_text) else None,
        "exclude_diploma_engineering": excludes_diploma_engineering,
        "locations": str(questionnaire_answers.get("byer", "") or "").strip(),
        "geography_importance": questionnaire_answers.get("geografi_vigtigt"),
        "length": questionnaire_answers.get("laengde"),
        "study_ideas": str(
            questionnaire_answers.get("uddannelser_tanker", "") or ""
        ).strip()
        if questionnaire_answers.get("uddannelser_tanker_svar") == "Ja"
        else "",
    }


def _apply_matching_preferences(
    questionnaire_answers: Mapping[str, Any],
    education_profiles: pd.DataFrame,
) -> pd.DataFrame:
    preferences = questionnaire_matching_preferences(questionnaire_answers)
    selected = education_profiles
    if preferences["exclude_diploma_engineering"]:
        title = selected.get("Titel", pd.Series("", index=selected.index)).astype("string")
        selected = selected.loc[
            ~title.str.contains(
                r"diplom[\s-]*ingeni[oø]r",
                case=False,
                na=False,
                regex=True,
            )
        ]
    institution_text = normalize_text(
        " ".join(
            str(questionnaire_answers.get(field, "") or "")
            for field in ("byer", "uddannelser_tanker", "universitetsfag", "andet")
        )
    )
    known_institutions = selected.get(
        "institution", pd.Series(index=selected.index, dtype="object")
    ).dropna().astype(str).unique()
    requested_institutions = {
        institution
        for institution in known_institutions
        if len(normalize_text(institution)) >= 5
        and normalize_text(institution) in institution_text
    }
    if preferences["institution"] == "DTU":
        requested_institutions.update(
            institution
            for institution in known_institutions
            if _DTU_PATTERN.search(str(institution))
        )
    if requested_institutions:
        selected_institutions = selected.get(
            "institution", pd.Series("", index=selected.index)
        ).astype("string")
        selected = selected.loc[
            selected_institutions.isin(requested_institutions)
        ]
    elif preferences["institution"] == "DTU":
        institution = selected.get(
            "institution", pd.Series("", index=selected.index)
        ).astype("string")
        selected = selected.loc[
            institution.str.contains(
                r"\bDTU\b|Danmarks\s+Tekniske\s+Universitet",
                case=False,
                na=False,
                regex=True,
            )
        ]
    return selected


def _result_locations(result: Mapping[str, Any]) -> list[str]:
    locations = []
    offers = result.get("offers", [])
    if not isinstance(offers, list):
        offers = []
    for record in [result, *offers]:
        if isinstance(record, Mapping):
            locations.extend(
                str(record[field])
                for field in ("institution", "kommune", "region")
                if record.get(field)
            )
    return locations


def _location_matches_preference(result: Mapping[str, Any], preference: str) -> bool:
    normalized_preference = normalize_text(preference)
    return any(
        len(normalized_location := normalize_text(location)) >= 3
        and (
            normalized_location in normalized_preference
            or normalized_preference in normalized_location
        )
        for location in _result_locations(result)
    )


def _apply_preference_ordering(
    results: list[dict[str, Any]],
    preferences: Mapping[str, Any],
) -> list[dict[str, Any]]:
    location_preference = str(preferences.get("locations", "") or "")
    try:
        geography_importance = float(preferences.get("geography_importance", 3))
    except (TypeError, ValueError):
        geography_importance = 3.0
    geography_importance = min(5.0, max(1.0, geography_importance))
    has_location_match = bool(location_preference) and any(
        _location_matches_preference(result, location_preference)
        for result in results
    )
    study_ideas = normalize_text(str(preferences.get("study_ideas", "") or ""))
    length_preference = preferences.get("length")

    for result in results:
        adjustment = 0.0
        reasons = []
        if has_location_match:
            location_adjustment = geography_importance * 0.6
            if _location_matches_preference(result, location_preference):
                adjustment += location_adjustment
                reasons.append("ønsket uddannelsessted")
            else:
                adjustment -= location_adjustment

        title = normalize_text(str(result.get("Titel", "")))
        if study_ideas and title and (
            title in study_ideas or study_ideas in title
        ):
            adjustment += 4.0
            reasons.append("uddannelse nævnt i dine ønsker")

        category = normalize_text(str(result.get("Educational_Category", "")))
        if length_preference == "Helst kortere" and category:
            if "erhvervsakademi" in category:
                adjustment += 2.5
                reasons.append("ønske om en kortere uddannelse")
            else:
                adjustment -= 1.0
        elif length_preference == "Helst længere" and category:
            if "erhvervsakademi" in category:
                adjustment -= 2.5
            elif "bachelor" in category:
                adjustment += 2.0
                reasons.append("ønske om en længere uddannelse")

        result["preference_reasons"] = reasons
        result["recommendation_score"] = min(
            100.0,
            max(0.0, float(result["match_score"]) + adjustment),
        )

    return sorted(
        results,
        key=lambda result: (
            -result["recommendation_score"],
            -result["match_score"],
            -result["data_coverage_count"],
            normalize_text(str(result.get("Titel", ""))),
        ),
    )


def rank_questionnaire_profile(
    questionnaire_answers: Mapping[str, Any],
    education_profiles: pd.DataFrame | None = None,
) -> list[dict[str, Any]]:
    """Map existing questionnaire answers and rank them with Matching v3."""
    profiles = (
        education_profiles
        if education_profiles is not None
        else load_education_profiles()
    )
    profiles = _apply_matching_preferences(questionnaire_answers, profiles)
    user_profile = user_profile_from_questionnaire(questionnaire_answers)
    results = rank_education(user_profile, profiles)
    return _apply_preference_ordering(
        results,
        questionnaire_matching_preferences(questionnaire_answers),
    )
