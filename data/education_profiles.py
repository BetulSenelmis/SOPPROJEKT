"""Transform UFSN/Uddannelseszoom rows into explicit Studiekompas profiles."""

from __future__ import annotations

from pathlib import Path
import re
import unicodedata
from collections.abc import Mapping, Sequence
from typing import Any

import pandas as pd


DEFAULT_WORKBOOK_PATH = Path(__file__).with_name("ufm_samlet_19jun2026.xlsx")
SOURCE_SHEET = "UFM_samlet_19JUN2026"
ELIGIBLE_CATEGORIES = frozenset(
    {
        "Bacheloruddannelser",
        "Professionsbacheloruddannelser",
        "Erhvervsakademiuddannelser",
    }
)
PROFILE_DIMENSIONS = (
    "faglig_interesse",
    "faglige_styrker",
    "faglig_fordybelse",
    "teknologi",
    "data_analytisk",
    "kreativitet",
    "mennesker",
    "samarbejde",
    "selvstændighed",
    "praktisk_læring",
    "teoretisk_læring",
    "projektarbejde",
    "variation",
    "internationalitet",
    "jobsikkerhed",
    "løn_økonomi",
    "karrieremuligheder",
)

INTEREST_AREAS = (
    "Teknologi og IT",
    "Matematik",
    "Naturvidenskab",
    "Medicin og sundhed",
    "Psykologi",
    "Mennesker og sociale forhold",
    "Samfund og politik",
    "Økonomi og business",
    "Jura",
    "Sprog og kommunikation",
    "Historie og kultur",
    "Kreativitet og design",
    "Medier og kommunikation",
    "Miljø og klima",
)

ABILITIES = (
    "Matematiske problemer",
    "Logisk tænkning",
    "Analyse",
    "Problemløsning",
    "Kreativ tænkning",
    "Skriftlig kommunikation",
    "Mundtlig kommunikation",
    "At lære nye ting",
    "At arbejde selvstændigt",
    "At arbejde sammen med andre",
    "Teknologi og computere",
    "At arbejde med data",
)

_AREA_TERMS = {
    "Teknologi og IT": ("teknologi", "it-færdigheder", "it", "datalogi", "datamatiker", "software", "programmering", "computer", "automation", "robot", "digital", "kunstig intelligens", "maskinlæring", "algoritme", "informatik", "cybersikkerhed"),
    "Matematik": ("matematik", "matematisk", "statistik", "tal", "økonometr", "kvantitativ"),
    "Naturvidenskab": ("naturvidenskab", "fysik", "kemi", "biologi", "bioteknologi", "geologi", "laborator", "natur"),
    "Medicin og sundhed": ("medicin", "sundhed", "sygepleje", "læge", "bioanalyt", "fysioterap", "ergoterap", "farmaci", "klinisk", "patient"),
    "Psykologi": ("psykologi", "psykolog", "mental", "adfærd", "terapeut"),
    "Mennesker og sociale forhold": ("menneskelige kompetencer", "social", "pædagog", "socialrådgiv", "omsorg", "mennesker", "samarbejde"),
    "Samfund og politik": ("samfund", "politik", "statskundskab", "offentlig administration", "forvaltning", "sociologi"),
    "Økonomi og business": ("økonomi", "business", "erhvervsøkonomi", "finans", "regnskab", "handel", "marketing", "forretning", "virksomhed"),
    "Jura": ("jura", "juridisk", "ret", "lovgivning", "erhvervsjura"),
    "Sprog og kommunikation": ("sprog", "engelsk", "dansk", "fremmedsprog", "formidling", "kommunikation", "lingvistik"),
    "Historie og kultur": ("historie", "kultur", "kulturforståelse", "arkæologi", "religion", "filosofi"),
    "Kreativitet og design": ("kreativ", "design", "arkitektur", "kunst", "innovation", "visuel", "musik"),
    "Medier og kommunikation": ("medie", "journalistik", "kommunikation", "film", "tv", "public relations", "digitalt indhold"),
    "Miljø og klima": ("miljø", "klima", "bæredygt", "naturressource", "energi", "landbrug", "skovbrug"),
}

_ABILITY_TERMS = {
    "Matematiske problemer": ("matematik", "tal", "statistik", "kvantitativ"),
    "Logisk tænkning": ("logisk", "programmering", "datalogi", "teknisk", "metode"),
    "Analyse": ("analytisk", "analyse", "undersøg", "forskning", "statistik"),
    "Problemløsning": ("problemløs", "teknisk", "udvikl", "diagnost", "design"),
    "Kreativ tænkning": ("kreativ", "innovativ", "design", "kunst", "udvikl"),
    "Skriftlig kommunikation": ("skriftlig", "formidling", "sprog", "kommunikation", "rapport"),
    "Mundtlig kommunikation": ("mundtlig", "formidling", "kommunikation", "undervisning", "vejledning"),
    "At lære nye ting": ("tilegnelse af ny viden", "viden", "forskning", "udvikling"),
    "At arbejde selvstændigt": ("selvstændig", "selvstudie", "tilrettelægge selv", "ansvar"),
    "At arbejde sammen med andre": ("samarbejde", "tværfaglig", "gruppe", "menneskelige kompetencer"),
    "Teknologi og computere": ("it-færdigheder", "teknologi", "teknisk", "software", "computer", "digital"),
    "At arbejde med data": ("data", "statistik", "analyse", "information", "regnskab"),
}

_SUBJECT_AREA_TERMS = {
    "matematik": ("Matematik",),
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

# Explicit title-based model heuristics, not official UFSN classifications.
_TITLE_TECHNOLOGY_HEURISTICS = (
    "datamatiker",
    "datalogi",
    "software",
    "computer science",
    "kunstig intelligens",
    "maskinlæring",
    "cybersikkerhed",
    "informatik",
    "programmering",
    "webudvikling",
    "automationsteknolog",
    "informationsteknologi",
    "it-arkitektur",
)
_TITLE_DATA_ANALYTICAL_HEURISTICS = (
    "datamatiker",
    "datalogi",
    "data science",
    "datavidenskab",
    "kunstig intelligens",
    "maskinlæring",
    "business intelligence",
    "dataanalyse",
    "statistik",
)


def normalize_text(value: Any) -> str:
    """Normalize text for deterministic, accent-insensitive keyword matching."""
    text = unicodedata.normalize("NFKD", str(value).casefold())
    text = "".join(character for character in text if not unicodedata.combining(character))
    return re.sub(r"\s+", " ", text.replace("-", " ")).strip()


def parse_numeric(values: pd.Series) -> pd.Series:
    """Parse UFSN numbers, including Danish decimal commas, without filling nulls."""
    text = values.astype("string").str.replace(",", ".", regex=False)
    return pd.to_numeric(text, errors="coerce")


def _mean(values: Sequence[Any]) -> float:
    valid: list[float] = []
    for value in values:
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if pd.notna(number):
            valid.append(number)
    return sum(valid) / len(valid) if valid else float("nan")


def _to_profile_scale(value: Any, minimum: float, maximum: float, *, reverse: bool = False) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return float("nan")
    if pd.isna(number):
        return float("nan")
    fraction = (number - minimum) / (maximum - minimum)
    fraction = min(max(fraction, 0.0), 1.0)
    if reverse:
        fraction = 1.0 - fraction
    return 1.0 + fraction * 4.0


def _keyword_score(text: str, terms: Sequence[str]) -> float:
    hits = sum(1 for term in terms if _contains_term(text, term))
    return float(min(5, 3 + hits)) if hits else float("nan")


def _contains_term(text: Any, term: str) -> bool:
    normalized_text = normalize_text(text)
    normalized_term = normalize_text(term)
    if len(normalized_term) <= 3:
        return re.search(
            rf"(?<!\w){re.escape(normalized_term)}(?!\w)",
            normalized_text,
        ) is not None
    return normalized_term in normalized_text


def _ranked_form_score(row: pd.Series, terms: Sequence[str]) -> float:
    rank_scores: list[float] = []
    for rank in range(1, 6):
        value = row.get(f"undervisningsform_p{rank}")
        if pd.notna(value) and any(_contains_term(value, term) for term in terms):
            rank_scores.append(float(6 - rank))
    return _mean(rank_scores)


def _text_fields(row: pd.Series, columns: Sequence[str]) -> str:
    return " ".join(str(row[column]) for column in columns if column in row.index and pd.notna(row[column]))


def _percentile_scores(frame: pd.DataFrame, column: str, *, reverse: bool = False) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(float("nan"), index=frame.index)
    values = parse_numeric(frame[column])
    ranks = values.rank(pct=True, method="average")
    if reverse:
        ranks = 1.0 - ranks
    return 1.0 + ranks * 4.0


def _education_metadata(frame: pd.DataFrame) -> pd.DataFrame:
    metadata = pd.DataFrame(index=frame.index)
    for column in (
        "artikel_id",
        "udbud_id",
        "url",
        "udd6",
        "Titel",
        "Educational_Category",
        "displaydocclass",
        "hovedinst",
        "hovedinsttx",
        "instkommune",
        "instkommunetx",
        "instregion",
        "instregiontx",
    ):
        if column in frame.columns:
            metadata[column] = frame[column]
    metadata["institution"] = frame.get("hovedinsttx", pd.Series(index=frame.index, dtype="object"))
    metadata["kommune"] = frame.get("instkommunetx", pd.Series(index=frame.index, dtype="object"))
    metadata["region"] = frame.get("instregiontx", pd.Series(index=frame.index, dtype="object"))
    metadata["admission_status"] = "unknown"
    metadata["profile_origin"] = "Studiekompas-model baseret på UFSN-data; ikke en officiel UFSN-score"
    return metadata


def transform_education_profiles(
    raw_data: pd.DataFrame,
    *,
    include_postgraduate: bool = False,
) -> pd.DataFrame:
    """Filter the source rows and create a fixed, explainable profile schema.

    Null source values remain null/NaN. The generated dimensions are model
    estimates and must not be presented as official UFSN ratings.
    """
    required = {"artikel_id", "udbud_id", "Titel", "Educational_Category"}
    missing = required.difference(raw_data.columns)
    if missing:
        raise ValueError(f"Excel-data mangler nødvendige kolonner: {', '.join(sorted(missing))}")

    selected = raw_data.copy()
    if not include_postgraduate:
        selected = selected.loc[selected["Educational_Category"].isin(ELIGIBLE_CATEGORIES)].copy()
    is_national_aggregate = (
        selected["udbud_id"]
        .astype("string")
        .str.replace(r"\.0$", "", regex=True)
        .eq("999999")
    )
    selected = selected.loc[~is_national_aggregate].copy()
    selected = selected.drop_duplicates(["artikel_id", "udbud_id"], keep="first").reset_index(drop=True)
    if selected.empty:
        raise ValueError("Der blev ikke fundet relevante bachelor- eller erhvervsakademiuddannelser.")

    result = _education_metadata(selected)
    profile_text_columns = (
        "Titel",
        "kompetencerudd_p1",
        "kompetencerudd_p2",
        "kompetencerudd_p3",
        "kompetencerudd_p4",
        "kompetencerudd_p5",
    )
    source_detail_columns = (
        *profile_text_columns[1:],
        *(f"undervisningsform_p{rank}" for rank in range(1, 6)),
    )
    for column in source_detail_columns:
        if column in selected.columns:
            result[column] = selected[column]
    titles = selected["Titel"].fillna("").astype(str)
    education_text = selected.apply(
        lambda row: _text_fields(row, profile_text_columns),
        axis=1,
    )
    competency_text = selected.apply(
        lambda row: _text_fields(
            row,
            tuple(f"kompetencerudd_p{rank}" for rank in range(1, 6)),
        ),
        axis=1,
    )

    area_scores: list[dict[str, float]] = []
    focus_scores: list[dict[str, float]] = []
    ability_scores: list[dict[str, float]] = []
    for index in selected.index:
        area_scores.append(
            {area: _keyword_score(education_text.iloc[index], terms) for area, terms in _AREA_TERMS.items()}
        )
        focus_scores.append(
            {area: _keyword_score(titles.iloc[index], terms) for area, terms in _AREA_TERMS.items()}
        )
        ability_scores.append(
            {
                ability: _keyword_score(competency_text.iloc[index], terms)
                for ability, terms in _ABILITY_TERMS.items()
            }
        )
    result["faglig_interesse"] = area_scores
    result["faglig_fordybelse"] = focus_scores
    result["faglige_styrker"] = ability_scores

    competence = competency_text
    teaching_forms = selected.apply(
        lambda row: " ".join(
            str(row.get(f"undervisningsform_p{rank}"))
            for rank in range(1, 6)
            if pd.notna(row.get(f"undervisningsform_p{rank}"))
        ),
        axis=1,
    )
    tech_text = education_text + " " + teaching_forms
    technology_terms = (
        "teknologi",
        "it-færdigheder",
        "tekniske kompetencer",
        "software",
        "computer",
        "digital",
        "automation",
        "datalogi",
        "kunstig intelligens",
        "maskinlæring",
        "algoritme",
        "informatik",
        "programmering",
    )
    data_terms = (
        "data",
        "datavidenskab",
        "data science",
        "kunstig intelligens",
        "maskinlæring",
        "algoritme",
        "analytiske kompetencer",
        "statistik",
        "matematik",
        "information",
    )

    technology_scores = []
    data_scores = []
    for index, row in selected.iterrows():
        title = titles.loc[index]
        title_is_technology = any(
            _contains_term(title, term) for term in _TITLE_TECHNOLOGY_HEURISTICS
        )
        title_is_data = any(
            _contains_term(title, term) for term in _TITLE_DATA_ANALYTICAL_HEURISTICS
        )
        technology_evidence = _keyword_score(tech_text.loc[index], technology_terms)
        data_evidence = _keyword_score(education_text.loc[index], data_terms)

        branch_evidence: list[float] = []
        for rank in range(1, 4):
            industry = row.get(f"branchetxt{rank}")
            share = _to_profile_scale(row.get(f"branchepct{rank}"), 0, 100)
            if pd.notna(industry) and _contains_term(industry, "Information og kommunikation") and pd.notna(share):
                branch_evidence.append(share)

        if title_is_technology:
            technology_scores.append(5.0)
        elif pd.notna(technology_evidence):
            technology_scores.append(max(4.0, technology_evidence))
        elif branch_evidence:
            technology_scores.append(max(3.0, _mean(branch_evidence)))
        else:
            technology_scores.append(float("nan"))

        if title_is_data:
            data_scores.append(5.0)
        elif pd.notna(data_evidence):
            data_scores.append(max(4.0, data_evidence))
        else:
            data_scores.append(float("nan"))

    result["teknologi"] = technology_scores
    result["data_analytisk"] = data_scores
    result["kreativitet"] = [
        _keyword_score(text, ("kreativ", "innovativ", "design", "kunst", "arkitektur", "visuel"))
        for text in education_text
    ]
    result["mennesker"] = [
        _keyword_score(text, ("menneskelige kompetencer", "mennesker", "patient", "pædagog", "social", "vejledning", "omsorg"))
        for text in education_text
    ]

    collaboration = []
    independence = []
    practical = []
    theory = []
    project = []
    for _, row in selected.iterrows():
        collaboration.append(
            _mean(
                [
                    _to_profile_scale(parse_numeric(pd.Series([row.get("arbmedstud_likert")])).iloc[0], 1, 5),
                    _keyword_score(competence.loc[row.name], ("samarbejde", "tværfaglige")),
                    _ranked_form_score(row, ("gruppearbejde", "projektarbejde")),
                ]
            )
        )
        independence.append(
            _mean(
                [
                    _to_profile_scale(parse_numeric(pd.Series([row.get("arbejdsform_tilretteselv_pct")])).iloc[0], 0, 100),
                    _ranked_form_score(row, ("selvstudie",)),
                ]
            )
        )
        practical.append(
            _mean(
                [
                    _to_profile_scale(parse_numeric(pd.Series([row.get("uddaktivitet_praktik_pct")])).iloc[0], 0, 100),
                    _keyword_score(competence.loc[row.name], ("praktiske færdigheder", "omsætte teori til praksis")),
                    _ranked_form_score(row, ("praktik", "værksteds", "laboratorie", "øvelsestimer")),
                ]
            )
        )
        theory.append(
            _mean(
                [
                    _keyword_score(competence.loc[row.name], ("teori og metode", "teoretisk")),
                    _ranked_form_score(row, ("forelæsninger", "klasseundervisning")),
                ]
            )
        )
        project.append(
            _mean(
                [
                    _keyword_score(competence.loc[row.name], ("projektorienterede", "projekt")),
                    _ranked_form_score(row, ("projektarbejde",)),
                ]
            )
        )
    result["samarbejde"] = collaboration
    result["selvstændighed"] = independence
    result["praktisk_læring"] = practical
    result["teoretisk_læring"] = theory
    result["projektarbejde"] = project

    variation_columns = [
        column
        for column in (
            "arbejdsform_fleksible_pct",
            "arbejdsform_skiftende_pct",
            "arbejdsform_andet_pct",
        )
        if column in selected.columns
    ]
    result["variation"] = [
        _mean(
            [
                _to_profile_scale(value, 0, 100)
                for value in (
                    parse_numeric(selected.loc[index, variation_columns])
                    if variation_columns
                    else []
                )
            ]
        )
        for index in selected.index
    ]
    result["internationalitet"] = [
        _mean(
            [
                _to_profile_scale(selected.at[index, column], 0, 100)
                for column in ("uddaktivitet_udlandsophold_pct", "udlandet_udlandet_pct")
                if column in selected.columns
            ]
        )
        for index in selected.index
    ]

    result["jobsikkerhed"] = _mean_columns(
        [
            _percentile_scores(selected, "ledighed_nyudd", reverse=True),
            _percentile_scores(selected, "ledighed_10aar", reverse=True),
        ],
        selected.index,
    )
    result["løn_økonomi"] = _mean_columns(
        [
            _percentile_scores(selected, "maanedloen_nyudd"),
            _percentile_scores(selected, "maanedloen_10aar"),
        ],
        selected.index,
    )
    result["karrieremuligheder"] = _mean_columns(
        [
            _to_scale_series(
                selected.get("relevans_overens_udd_job_likert", pd.Series(index=selected.index, dtype="object")),
                1,
                5,
            ),
            _to_scale_series(
                selected.get("ruster_til_job_likert", pd.Series(index=selected.index, dtype="object")),
                1,
                5,
            ),
        ],
        selected.index,
    )
    result["education_profile_coverage_count"] = result.apply(
        lambda row: sum(_has_profile_value(row[dimension]) for dimension in PROFILE_DIMENSIONS),
        axis=1,
    )
    result["education_profile_coverage_total"] = len(PROFILE_DIMENSIONS)
    result["education_profile_coverage_ratio"] = (
        result["education_profile_coverage_count"] / len(PROFILE_DIMENSIONS)
    )
    return result


def _has_profile_value(value: Any) -> bool:
    if isinstance(value, Mapping):
        return any(pd.notna(item) for item in value.values())
    return pd.notna(value)


def _mean_columns(columns: Sequence[pd.Series], index: pd.Index) -> pd.Series:
    if not columns:
        return pd.Series(float("nan"), index=index)
    frame = pd.concat(columns, axis=1)
    return frame.mean(axis=1, skipna=True).where(frame.notna().any(axis=1))


def _to_scale_series(values: pd.Series, minimum: float, maximum: float) -> pd.Series:
    numeric = parse_numeric(values)
    return numeric.clip(lower=minimum, upper=maximum).sub(minimum).div(maximum - minimum).mul(4).add(1)


def load_education_profiles(
    excel_path: str | Path | None = None,
    *,
    sheet_name: str | int = SOURCE_SHEET,
    include_postgraduate: bool = False,
) -> pd.DataFrame:
    """Load the unmodified UFSN workbook and return transformed profiles."""
    path = Path(excel_path) if excel_path is not None else DEFAULT_WORKBOOK_PATH
    if not path.is_file():
        raise FileNotFoundError(f"UFSN Excel-filen blev ikke fundet: {path}")
    raw_data = pd.read_excel(path, sheet_name=sheet_name)
    return transform_education_profiles(raw_data, include_postgraduate=include_postgraduate)


__all__ = [
    "ABILITIES",
    "DEFAULT_WORKBOOK_PATH",
    "ELIGIBLE_CATEGORIES",
    "INTEREST_AREAS",
    "PROFILE_DIMENSIONS",
    "SOURCE_SHEET",
    "load_education_profiles",
    "normalize_text",
    "parse_numeric",
    "transform_education_profiles",
]
