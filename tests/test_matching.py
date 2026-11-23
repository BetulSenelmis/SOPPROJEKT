from pathlib import Path
import unittest

import pandas as pd

from data.education_profiles import (
    ABILITIES,
    DEFAULT_WORKBOOK_PATH,
    INTEREST_AREAS,
    PROFILE_DIMENSIONS,
    transform_education_profiles,
)
from matching import (
    BLOCK_WEIGHTS,
    CORE_DIMENSIONS,
    DIMENSION_WEIGHTS,
    SECONDARY_DIMENSIONS,
    SCORE_INTERPRETATION,
    _score_dimensions,
    filter_by_admission_requirements,
    rank_education,
    user_profile_from_questionnaire,
)


class EducationMatchingTests(unittest.TestCase):
    @staticmethod
    def _profile(value=3.0, **overrides):
        profile = {}
        for dimension in PROFILE_DIMENSIONS:
            if dimension in {"faglig_interesse", "faglig_fordybelse"}:
                profile[dimension] = {
                    area: value for area in INTEREST_AREAS
                }
            elif dimension == "faglige_styrker":
                profile[dimension] = {ability: value for ability in ABILITIES}
            else:
                profile[dimension] = value
        profile.update(overrides)
        return profile

    @staticmethod
    def _education_row(title, offer_id, value=3.0, **overrides):
        row = {
            "Titel": title,
            "udbud_id": offer_id,
            "admission_status": "unknown",
        }
        row.update(EducationMatchingTests._profile(value, **overrides))
        return row

    def test_transform_filters_categories_preserves_metadata_and_missing_values(self):
        source = pd.DataFrame(
            [
                {
                    "artikel_id": "ba-1",
                    "udbud_id": 1001,
                    "url": "https://example.test/ba-1",
                    "udd6": "123456",
                    "Titel": "Datamatiker",
                    "Educational_Category": "Erhvervsakademiuddannelser",
                    "displaydocclass": "Erhvervsakademiuddannelse",
                    "hovedinsttx": "Testakademi",
                    "instkommunetx": "Aarhus",
                    "instregiontx": "Midtjylland",
                    "uddaktivitet_praktik_pct": "25,00",
                    "uddaktivitet_udlandsophold_pct": None,
                    "kompetencerudd_p1": "IT-færdigheder",
                    "undervisningsform_p1": "Projektarbejde",
                    "arbejdsform_skiftende_pct": None,
                },
                {
                    "artikel_id": "ba-1",
                    "udbud_id": 999999,
                    "Titel": "Datamatiker",
                    "Educational_Category": "Erhvervsakademiuddannelser",
                },
                {
                    "artikel_id": "master-1",
                    "udbud_id": 2001,
                    "url": "https://example.test/master-1",
                    "udd6": "654321",
                    "Titel": "Datavidenskab",
                    "Educational_Category": "Kandidatuddannelser",
                },
            ]
        )

        profiles = transform_education_profiles(source)

        self.assertEqual(profiles["udbud_id"].tolist(), [1001])
        self.assertEqual(profiles.loc[0, "institution"], "Testakademi")
        self.assertEqual(profiles.loc[0, "kommune"], "Aarhus")
        self.assertEqual(profiles.loc[0, "admission_status"], "unknown")
        self.assertEqual(profiles.loc[0, "displaydocclass"], "Erhvervsakademiuddannelse")
        self.assertEqual(profiles.loc[0, "kompetencerudd_p1"], "IT-færdigheder")
        self.assertEqual(profiles.loc[0, "undervisningsform_p1"], "Projektarbejde")
        self.assertAlmostEqual(profiles.loc[0, "praktisk_læring"], 2.0)
        self.assertTrue(pd.isna(profiles.loc[0, "internationalitet"]))
        self.assertTrue(pd.isna(profiles.loc[0, "variation"]))
        self.assertTrue(profiles.loc[0, "profile_origin"].startswith("Studiekompas-model"))

    def test_admission_filter_is_separate_from_fit(self):
        candidates = pd.DataFrame(
            {
                "udbud_id": [11, 12, 13],
                "teknologi": [5.0, 4.0, 3.0],
            }
        )

        ordinary = filter_by_admission_requirements(candidates, {11: True, 12: False})
        verified = filter_by_admission_requirements(
            candidates,
            {11: True, 12: False},
            require_verified=True,
        )

        self.assertEqual(ordinary["udbud_id"].tolist(), [11, 13])
        self.assertEqual(ordinary["admission_status"].tolist(), ["eligible", "unknown"])
        self.assertEqual(verified["udbud_id"].tolist(), [11])

    def test_rank_education_ignores_missing_dimensions_and_returns_top_five(self):
        compared = [
            "teknologi",
            "data_analytisk",
            "praktisk_læring",
            "teoretisk_læring",
            "projektarbejde",
            "samarbejde",
            "variation",
            "internationalitet",
        ]
        candidates = pd.DataFrame(
            [
                {
                    "Titel": f"Uddannelse {index}",
                    "udbud_id": index,
                    **{
                        dimension: (
                            4.0
                            if dimension != "teknologi"
                            else 1.0 + (index - 1) * 4.0 / 6.0
                        )
                        for dimension in compared
                    },
                    "jobsikkerhed": None,
                }
                for index in range(1, 8)
            ]
        )

        results = rank_education(
            {**{dimension: 4.0 for dimension in compared}, "teknologi": 5.0, "jobsikkerhed": 1.0},
            candidates,
        )

        self.assertEqual(len(results), 5)
        self.assertEqual(results[0]["udbud_id"], 7)
        self.assertEqual(results[0]["match_score"], 100.0)
        self.assertEqual(results[0]["dimensions_compared"], 8)
        self.assertEqual(
            {item["dimension"] for item in results[0]["matched_dimensions"]},
            set(compared),
        )
        self.assertEqual(results[0]["data_coverage_count"], 8)
        self.assertEqual(results[0]["data_coverage_total"], 17)
        self.assertEqual(results[0]["data_coverage_ratio"], 8 / 17)
        self.assertEqual(results[0]["data_coverage_level"], "low")
        self.assertEqual(results[0]["admission_status"], "unknown")
        self.assertEqual(results[0]["score_interpretation"], SCORE_INTERPRETATION)

    def test_rank_education_does_not_score_one_shared_dimension_as_a_match(self):
        candidates = pd.DataFrame(
            [{"Titel": "Uddannelse", "teknologi": 5.0, "data_analytisk": None}]
        )

        self.assertEqual(
            rank_education(
                {"teknologi": 5.0, "data_analytisk": 5.0, "kreativitet": 4.0},
                candidates,
            ),
            [],
        )

    def test_minimum_coverage_and_coverage_label_are_separate_from_fit(self):
        user = {dimension: 4.0 for dimension in PROFILE_DIMENSIONS}
        candidates = pd.DataFrame(
            [
                {
                    "Titel": title,
                    "udbud_id": index,
                    **{
                        dimension: (4.0 if position < count else None)
                        for position, dimension in enumerate(PROFILE_DIMENSIONS)
                    },
                }
                for index, (title, count) in enumerate(
                    [
                        ("Too thin", 7),
                        ("Limited", 8),
                        ("Medium", 10),
                        ("Well covered", 14),
                    ],
                    start=1,
                )
            ]
        )

        results = rank_education(user, candidates, top_n=5)

        by_title = {item["Titel"]: item for item in results}
        self.assertEqual(set(by_title), {"Limited", "Medium", "Well covered"})
        self.assertEqual(by_title["Limited"]["match_score"], by_title["Well covered"]["match_score"])
        self.assertEqual(by_title["Limited"]["data_coverage_level"], "low")
        self.assertEqual(by_title["Medium"]["data_coverage_level"], "medium")
        self.assertEqual(by_title["Well covered"]["data_coverage_level"], "high")
        self.assertEqual(by_title["Limited"]["data_coverage_count"], 8)
        self.assertEqual(by_title["Medium"]["data_coverage_count"], 10)
        self.assertEqual(by_title["Well covered"]["data_coverage_count"], 14)

    def test_top_five_are_unique_titles_and_keep_all_offer_options(self):
        candidates = pd.DataFrame(
            [
                {
                    "Titel": title,
                    "udbud_id": offer_id,
                    "institution": f"Institution {offer_id}",
                    **{dimension: 4.0 for dimension in PROFILE_DIMENSIONS[:8]},
                }
                for title, offer_id in (
                    ("Datamatiker", 101),
                    ("Datamatiker", 102),
                    ("Pædagog", 201),
                    ("Datamatiker", 103),
                    ("Arkitektur", 301),
                    ("Sygeplejerske", 401),
                )
            ]
            + [
                {
                    "Titel": "Datamatiker",
                    "udbud_id": 104,
                    "institution": "Institution 104",
                    **{dimension: None for dimension in PROFILE_DIMENSIONS},
                }
            ]
        )

        results = rank_education(
            {dimension: 4.0 for dimension in PROFILE_DIMENSIONS[:8]},
            candidates,
        )

        titles = [result["Titel"] for result in results]
        self.assertEqual(len(titles), len(set(titles)))
        datamatiker = next(result for result in results if result["Titel"] == "Datamatiker")
        self.assertEqual(datamatiker["offer_count"], 4)
        self.assertEqual(
            {offer["udbud_id"] for offer in datamatiker["offers"]},
            {101, 102, 103, 104},
        )
        self.assertIsNone(
            next(offer for offer in datamatiker["offers"] if offer["udbud_id"] == 104)["match_score"]
        )

    def test_explicit_dimension_weights_are_applied_within_core_block(self):
        self.assertEqual(
            DIMENSION_WEIGHTS,
            {
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
            },
        )
        matches = [
            {"dimension": "faglig_interesse", "similarity": 100.0, "compared_values": 1},
            {"dimension": "teknologi", "similarity": 0.0, "compared_values": 1},
        ]

        score, details, block_weights = _score_dimensions(matches)

        expected = (
            DIMENSION_WEIGHTS["faglig_interesse"] * 100
            + DIMENSION_WEIGHTS["teknologi"] * 0
        ) / (
            DIMENSION_WEIGHTS["faglig_interesse"]
            + DIMENSION_WEIGHTS["teknologi"]
        )
        self.assertEqual(score, round(expected, 1))
        self.assertEqual(block_weights, {"core": 1.0})
        self.assertEqual(len(details), 2)

    def test_secondary_dimensions_cannot_dominate_core_block(self):
        core_mismatch = [
            {"dimension": dimension, "similarity": 0.0, "compared_values": 1}
            for dimension in CORE_DIMENSIONS
        ]
        secondary_match = [
            {"dimension": dimension, "similarity": 100.0, "compared_values": 1}
            for dimension in SECONDARY_DIMENSIONS
        ]
        core_match = [
            {"dimension": dimension, "similarity": 100.0, "compared_values": 1}
            for dimension in CORE_DIMENSIONS
        ]
        secondary_mismatch = [
            {"dimension": dimension, "similarity": 0.0, "compared_values": 1}
            for dimension in SECONDARY_DIMENSIONS
        ]

        low_core_score, _, weights = _score_dimensions(core_mismatch + secondary_match)
        high_core_score, _, _ = _score_dimensions(core_match + secondary_mismatch)

        self.assertEqual(weights, BLOCK_WEIGHTS)
        self.assertEqual(low_core_score, 20.0)
        self.assertEqual(high_core_score, 80.0)

    def test_explanation_lists_positive_negative_missing_and_partial_dimensions(self):
        user = self._profile(4.0)
        education = self._profile(4.0)
        education["teknologi"] = 1.0
        education["internationalitet"] = None
        education["faglig_interesse"] = {"Matematik": 4.0}

        result = rank_education(
            user,
            pd.DataFrame([{"Titel": "Forklarbar", "udbud_id": 1, **education}]),
        )[0]

        self.assertIn("teknologi", {item["dimension"] for item in result["weakest_dimensions"]})
        self.assertIn(
            "teknologi",
            {item["dimension"] for item in result["negative_impact_dimensions"]},
        )
        self.assertIn("internationalitet", {item["dimension"] for item in result["missing_dimensions"]})
        self.assertIn("faglig_interesse", {item["dimension"] for item in result["partial_dimensions"]})
        self.assertTrue(result["matched_dimensions"])
        self.assertIn("impact_from_neutral_points", result["matched_dimensions"][0])
        self.assertIn("score_interpretation", result)
        self.assertIn("ikke en sandsynlighed", result["score_interpretation"])
        self.assertIn("ikke en objektiv vurdering", result["score_interpretation"])

    def test_weakest_dimensions_are_exposed_even_without_negative_impact(self):
        user = self._profile(4.0)
        result = rank_education(
            user,
            pd.DataFrame([{"Titel": "Godt match", "udbud_id": 1, **self._profile(4.0)}]),
        )[0]

        self.assertTrue(result["weakest_dimensions"])
        self.assertEqual(result["negative_impact_dimensions"], [])

    def test_negative_impact_uses_unrounded_value_just_below_neutral(self):
        user = self._profile(1.0)
        education = self._profile(3.0, jobsikkerhed=3.004)

        result = rank_education(
            user,
            pd.DataFrame([{"Titel": "Negativ rand", "udbud_id": 1, **education}]),
        )[0]

        jobsikkerhed = next(
            item
            for item in result["matched_dimensions"]
            if item["dimension"] == "jobsikkerhed"
        )
        self.assertEqual(jobsikkerhed["similarity"], 49.9)
        self.assertEqual(jobsikkerhed["impact_from_neutral_points"], -0.0)
        self.assertIn(
            "jobsikkerhed",
            {item["dimension"] for item in result["negative_impact_dimensions"]},
        )
        self.assertNotIn(
            "_unrounded_impact_from_neutral_points",
            jobsikkerhed,
        )

    def test_neutral_impact_is_not_classified_as_positive_or_negative(self):
        user = self._profile(1.0)
        education = self._profile(1.0, jobsikkerhed=3.0)

        result = rank_education(
            user,
            pd.DataFrame([{"Titel": "Neutral rand", "udbud_id": 1, **education}]),
        )[0]

        jobsikkerhed = next(
            item
            for item in result["matched_dimensions"]
            if item["dimension"] == "jobsikkerhed"
        )
        self.assertEqual(jobsikkerhed["similarity"], 50.0)
        self.assertEqual(jobsikkerhed["impact_from_neutral_points"], 0.0)
        self.assertNotIn(
            "jobsikkerhed",
            {item["dimension"] for item in result["strongest_positive_dimensions"]},
        )
        self.assertNotIn(
            "jobsikkerhed",
            {item["dimension"] for item in result["negative_impact_dimensions"]},
        )

    def test_positive_impact_uses_unrounded_value_just_above_neutral(self):
        user = self._profile(1.0)
        education = self._profile(3.0, jobsikkerhed=2.996)

        result = rank_education(
            user,
            pd.DataFrame([{"Titel": "Positiv rand", "udbud_id": 1, **education}]),
        )[0]

        jobsikkerhed = next(
            item
            for item in result["matched_dimensions"]
            if item["dimension"] == "jobsikkerhed"
        )
        self.assertEqual(jobsikkerhed["similarity"], 50.1)
        self.assertEqual(jobsikkerhed["impact_from_neutral_points"], 0.0)
        self.assertIn(
            "jobsikkerhed",
            {item["dimension"] for item in result["strongest_positive_dimensions"]},
        )
        self.assertNotIn(
            "jobsikkerhed",
            {item["dimension"] for item in result["negative_impact_dimensions"]},
        )

    def test_hard_constraint_metadata_never_changes_score_or_rank(self):
        user = self._profile(4.0)
        candidates = pd.DataFrame(
            [
                self._education_row("Eligible flag", 1, admission_status="eligible"),
                self._education_row("Not eligible flag", 2, admission_status="not_eligible"),
            ]
        )

        results = rank_education(user, candidates)

        self.assertEqual({item["Titel"] for item in results}, {"Eligible flag", "Not eligible flag"})
        self.assertEqual(results[0]["match_score"], results[1]["match_score"])
        self.assertEqual(
            {item["admission_status"] for item in results},
            {"eligible", "not_eligible"},
        )

    def test_same_user_profile_returns_deterministic_results(self):
        user = self._profile(4.0, teknologi=5.0)
        candidates = pd.DataFrame(
            [
                self._education_row("Zulu", 2, teknologi=4.0),
                self._education_row("Alpha", 1, teknologi=4.0),
            ]
        )

        first = rank_education(user, candidates)
        second = rank_education(user, candidates.sample(frac=1, random_state=10))

        self.assertEqual(
            [(item["Titel"], item["match_score"], item["data_coverage_count"]) for item in first],
            [(item["Titel"], item["match_score"], item["data_coverage_count"]) for item in second],
        )

    def test_strong_it_humanities_and_mixed_profiles_rank_plausible_candidates(self):
        it_user = self._profile(
            2.0,
            teknologi=5.0,
            data_analytisk=5.0,
            faglig_interesse={
                area: (5.0 if area in {"Teknologi og IT", "Matematik"} else 2.0)
                for area in INTEREST_AREAS
            },
        )
        humanist_user = self._profile(
            2.0,
            teknologi=1.0,
            data_analytisk=1.0,
            faglig_interesse={
                area: (5.0 if area in {"Historie og kultur", "Sprog og kommunikation"} else 2.0)
                for area in INTEREST_AREAS
            },
            faglige_styrker={
                ability: (5.0 if ability in {"Skriftlig kommunikation", "Mundtlig kommunikation"} else 2.0)
                for ability in ABILITIES
            },
        )
        mixed_user = self._profile(
            3.0,
            teknologi=5.0,
            data_analytisk=4.0,
            faglig_interesse={
                area: (5.0 if area in {"Teknologi og IT", "Medier og kommunikation"} else 3.0)
                for area in INTEREST_AREAS
            },
        )
        education = pd.DataFrame(
            [
                self._education_row(
                    "Software Engineering",
                    1,
                    3.0,
                    teknologi=5.0,
                    data_analytisk=5.0,
                    faglig_interesse={
                        area: (5.0 if area in {"Teknologi og IT", "Matematik"} else 2.0)
                        for area in INTEREST_AREAS
                    },
                ),
                self._education_row(
                    "Historie",
                    2,
                    3.0,
                    teknologi=1.0,
                    data_analytisk=1.0,
                    faglig_interesse={
                        area: (5.0 if area in {"Historie og kultur", "Sprog og kommunikation"} else 2.0)
                        for area in INTEREST_AREAS
                    },
                    faglige_styrker={
                        ability: (5.0 if ability in {"Skriftlig kommunikation", "Mundtlig kommunikation"} else 2.0)
                        for ability in ABILITIES
                    },
                ),
                self._education_row(
                    "Digital mediedesign",
                    3,
                    3.0,
                    teknologi=4.0,
                    data_analytisk=3.0,
                    faglig_interesse={
                        area: (5.0 if area in {"Teknologi og IT", "Medier og kommunikation"} else 3.0)
                        for area in INTEREST_AREAS
                    },
                ),
            ]
        )

        it_results = rank_education(it_user, education)
        humanities_results = rank_education(humanist_user, education)
        mixed_results = rank_education(mixed_user, education)

        self.assertEqual(it_results[0]["Titel"], "Software Engineering")
        self.assertEqual(humanities_results[0]["Titel"], "Historie")
        self.assertEqual(mixed_results[0]["Titel"], "Digital mediedesign")

    def test_questionnaire_keeps_interest_strength_and_further_study_intent_separate(self):
        profile = {
            "interesser": {"Matematik": 3},
            "bedste_fag": ["Matematik"],
            "mindst_fag": [],
            "staerkeste_fag": ["Matematik"],
            "evner": {"Matematiske problemer": 2},
            "universitetsfag_svar": "Ja",
            "universitetsfag": "Matematik",
        }

        mapped = user_profile_from_questionnaire(profile)

        self.assertEqual(mapped["faglig_interesse"]["Matematik"], 3.5)
        self.assertEqual(mapped["faglige_styrker"]["Matematiske problemer"], 4.5)
        self.assertEqual(mapped["faglig_fordybelse"]["Matematik"], 5.0)
        career_profile = user_profile_from_questionnaire(
            {
                "jobmuligheder_vigtigt": 5,
                "jobvaerdier": {
                    "Jobsikkerhed": 4,
                    "Høj løn": 2,
                    "Gode muligheder for karriereudvikling": 3,
                },
            }
        )
        self.assertEqual(career_profile["jobsikkerhed"], 4)
        self.assertEqual(career_profile["løn_økonomi"], 2)
        self.assertEqual(career_profile["karrieremuligheder"], 4)
        self.assertNotIn("karriereorientering", career_profile)

    def test_questionnaire_uses_avoided_areas_job_choices_values_and_workday(self):
        profile = {
            "interesser": {area: 3 for area in INTEREST_AREAS},
            "undgaa": ["Naturvidenskab"],
            "jobomraader": ["Teknologi / IT"],
            "arbejdsdag": ["Arbejde med mennesker", "Arbejde med tal/data"],
            "mennesker_vigtigt": 2,
            "teknologi_vigtigt": 3,
            "data_vigtigt": 2,
            "forudsigelighed": 3,
            "jobvaerdier": {
                "At hjælpe andre mennesker": 5,
                "At arbejde med teknologi": 5,
                "Fleksibilitet": 5,
                "At arbejde internationalt": 5,
            },
        }

        mapped = user_profile_from_questionnaire(profile)

        self.assertEqual(mapped["faglig_interesse"]["Naturvidenskab"], 1.5)
        self.assertEqual(mapped["faglig_interesse"]["Teknologi og IT"], 4.5)
        self.assertEqual(mapped["faglig_fordybelse"]["Teknologi og IT"], 4.0)
        self.assertGreaterEqual(mapped["mennesker"], 4.5)
        self.assertEqual(mapped["teknologi"], 4.0)
        self.assertEqual(mapped["data_analytisk"], 4.5)
        self.assertEqual(mapped["variation"], 4.0)
        self.assertEqual(mapped["internationalitet"], 5.0)

    def test_real_workbook_loads_and_produces_ranked_recommendations(self):
        self.assertTrue(Path(DEFAULT_WORKBOOK_PATH).is_file())
        from data.education_profiles import load_education_profiles

        profiles = load_education_profiles()
        self.assertGreater(len(profiles), 5)
        self.assertTrue(
            profiles["Educational_Category"].isin(
                [
                    "Bacheloruddannelser",
                    "Professionsbacheloruddannelser",
                    "Erhvervsakademiuddannelser",
                ]
            ).all()
        )
        self.assertFalse(profiles["udbud_id"].astype(str).eq("999999").any())
        self.assertIn("displaydocclass", profiles.columns)
        self.assertIn("education_profile_coverage_count", profiles.columns)

        datamatiker = profiles.loc[profiles["Titel"].eq("Datamatiker")]
        self.assertGreaterEqual(len(datamatiker), 1)
        self.assertTrue(datamatiker["teknologi"].ge(4.0).all())
        self.assertTrue(
            datamatiker["faglig_interesse"].map(
                lambda areas: areas["Teknologi og IT"] >= 4.0
            ).all()
        )
        ai_education = profiles.loc[
            profiles["Titel"].str.contains("kunstig intelligens", case=False, na=False)
        ]
        self.assertGreaterEqual(len(ai_education), 1)
        self.assertTrue(ai_education["teknologi"].ge(4.0).all())
        self.assertTrue(
            ai_education["faglig_interesse"].map(
                lambda areas: areas["Teknologi og IT"] >= 4.0
            ).all()
        )

        questionnaire = {
            "interesser": {area: 3 for area in INTEREST_AREAS},
            "bedste_fag": ["Matematik"],
            "mindst_fag": ["Historie"],
            "staerkeste_fag": ["Matematik"],
            "evner": {ability: 3 for ability in ABILITIES},
            "universitetsfag_svar": "Ja",
            "universitetsfag": "Matematik",
            "arbejdsform": 4,
            "teori_praksis": 4,
            "forudsigelighed": 4,
            "kreativitet_vigtigt": 3,
            "mennesker_vigtigt": 3,
            "teknologi_vigtigt": 5,
            "data_vigtigt": 5,
            "arbejdsdag": ["Analysere information", "Løse problemer"],
            "jobmuligheder_vigtigt": 4,
            "jobvaerdier": {
                "Høj løn": 4,
                "Jobsikkerhed": 4,
                "Gode muligheder for karriereudvikling": 4,
                "At arbejde internationalt": 3,
            },
        }
        user_profile = user_profile_from_questionnaire(questionnaire)
        matches = rank_education(user_profile, profiles)
        self.assertEqual(len(matches), 5)
        self.assertTrue(all(0 <= item["match_score"] <= 100 for item in matches))
        self.assertTrue(all(item["dimensions_compared"] >= 8 for item in matches))
        self.assertEqual(
            len({item["Titel"] for item in matches}),
            len(matches),
        )
