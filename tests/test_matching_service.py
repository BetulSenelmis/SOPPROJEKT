import unittest
from unittest.mock import patch

import pandas as pd

from data.education_profiles import ABILITIES, INTEREST_AREAS, PROFILE_DIMENSIONS
from matching_service import rank_questionnaire_profile


class MatchingServiceTests(unittest.TestCase):
    @staticmethod
    def questionnaire_answers():
        return {
            "interesser": {area: 3 for area in INTEREST_AREAS},
            "bedste_fag": ["Matematik"],
            "mindst_fag": [],
            "staerkeste_fag": ["Matematik"],
            "evner": {ability: 3 for ability in ABILITIES},
            "universitetsfag_svar": "Nej",
            "universitetsfag": "",
            "arbejdsform": 4,
            "teori_praksis": 4,
            "forudsigelighed": 3,
            "teknologi_vigtigt": 5,
            "data_vigtigt": 4,
            "kreativitet_vigtigt": 3,
            "mennesker_vigtigt": 3,
            "jobmuligheder_vigtigt": 4,
            "jobvaerdier": {
                "Jobsikkerhed": 4,
                "Høj løn": 3,
                "At arbejde internationalt": 3,
                "Gode muligheder for karriereudvikling": 4,
            },
            "arbejdsdag": ["Løse problemer"],
        }

    @staticmethod
    def education_profiles():
        profile = {
            "Titel": "Testuddannelse",
            "udbud_id": 123,
            "institution": "Testinstitution",
        }
        for dimension in PROFILE_DIMENSIONS:
            if dimension in {"faglig_interesse", "faglig_fordybelse"}:
                profile[dimension] = {area: 4.0 for area in INTEREST_AREAS}
            elif dimension == "faglige_styrker":
                profile[dimension] = {ability: 4.0 for ability in ABILITIES}
            else:
                profile[dimension] = 4.0
        return pd.DataFrame([profile])

    def test_questionnaire_is_mapped_and_ranked_by_matching_v3(self):
        questionnaire = self.questionnaire_answers()

        results = rank_questionnaire_profile(
            questionnaire,
            self.education_profiles(),
        )

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["Titel"], "Testuddannelse")
        self.assertEqual(results[0]["udbud_id"], 123)
        self.assertIsNotNone(results[0]["match_score"])
        self.assertGreaterEqual(results[0]["dimensions_compared"], 8)
        self.assertTrue(results[0]["matched_dimensions"])

    def test_explicit_dtu_preference_excludes_other_institutions_and_unwanted_degree(self):
        questionnaire = self.questionnaire_answers()
        questionnaire["byer"] = "Jeg vil gerne på DTU"
        questionnaire["andet"] = (
            "Jeg vil ikke have noget med diplomenginør."
        )
        base = self.education_profiles().iloc[0].to_dict()
        candidates = []
        for title, institution in (
            ("Softwareteknologi", "Danmarks Tekniske Universitet"),
            ("Computer engineering (diplomingeniør)", "Danmarks Tekniske Universitet"),
            ("Softwareudvikling", "Aalborg Universitet"),
        ):
            candidate = base.copy()
            candidate["Titel"] = title
            candidate["institution"] = institution
            candidates.append(candidate)

        results = rank_questionnaire_profile(
            questionnaire,
            pd.DataFrame(candidates),
        )

        self.assertEqual([item["Titel"] for item in results], ["Softwareteknologi"])
        self.assertEqual(
            results[0]["institution"],
            "Danmarks Tekniske Universitet",
        )

    def test_diploma_engineering_is_excluded_when_requested_without_dtu_filter(self):
        questionnaire = self.questionnaire_answers()
        questionnaire["andet"] = "Jeg vil ikke have noget med diplomingeniør."
        base = self.education_profiles().iloc[0].to_dict()
        candidates = []
        for title in ("Softwareteknologi", "Softwareteknologi (diplomingeniør)"):
            candidate = base.copy()
            candidate["Titel"] = title
            candidates.append(candidate)

        results = rank_questionnaire_profile(
            questionnaire,
            pd.DataFrame(candidates),
        )

        self.assertEqual([item["Titel"] for item in results], ["Softwareteknologi"])

    def test_neutral_diploma_engineering_mention_is_not_treated_as_a_rejection(self):
        questionnaire = self.questionnaire_answers()
        questionnaire["andet"] = "Jeg er stadig i tvivl om diplomingeniør."

        results = rank_questionnaire_profile(
            questionnaire,
            self.education_profiles(),
        )

        self.assertEqual([item["Titel"] for item in results], ["Testuddannelse"])

    def test_dtu_preference_does_not_fall_back_to_other_institutions(self):
        questionnaire = self.questionnaire_answers()
        questionnaire["uddannelser_tanker"] = "DTU"

        results = rank_questionnaire_profile(
            questionnaire,
            self.education_profiles(),
        )

        self.assertEqual(results, [])

    def test_named_institution_preference_uses_the_candidate_dataset(self):
        questionnaire = self.questionnaire_answers()
        questionnaire["byer"] = "Jeg vil gerne læse på Aalborg Universitet"
        base = self.education_profiles().iloc[0].to_dict()
        candidates = []
        for institution in ("Aalborg Universitet", "Aarhus Universitet"):
            candidate = base.copy()
            candidate["institution"] = institution
            candidates.append(candidate)

        results = rank_questionnaire_profile(
            questionnaire,
            pd.DataFrame(candidates),
        )

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["institution"], "Aalborg Universitet")

    def test_place_length_and_named_study_preferences_adjust_recommendation_order(self):
        questionnaire = self.questionnaire_answers()
        questionnaire.update(
            {
                "byer": "Jeg vil helst studere i København",
                "geografi_vigtigt": 5,
                "laengde": "Helst kortere",
                "uddannelser_tanker_svar": "Ja",
                "uddannelser_tanker": "Jeg overvejer Kort programmering",
            }
        )
        base = self.education_profiles().iloc[0].to_dict()
        short_program = {
            **base,
            "Titel": "Kort programmering",
            "Educational_Category": "Erhvervsakademiuddannelser",
            "kommune": "København",
        }
        long_program = {
            **base,
            "Titel": "Lang programmering",
            "Educational_Category": "Bacheloruddannelser",
            "kommune": "Aarhus",
        }

        results = rank_questionnaire_profile(
            questionnaire,
            pd.DataFrame([long_program, short_program]),
        )

        self.assertEqual(
            [item["Titel"] for item in results],
            ["Kort programmering", "Lang programmering"],
        )
        self.assertEqual(results[0]["match_score"], results[1]["match_score"])
        self.assertEqual(
            results[0]["preference_reasons"],
            [
                "ønsket uddannelsessted",
                "uddannelse nævnt i dine ønsker",
                "ønske om en kortere uddannelse",
            ],
        )
        self.assertGreater(
            results[0]["recommendation_score"],
            results[1]["recommendation_score"],
        )

    def test_empty_dataset_returns_no_results(self):
        results = rank_questionnaire_profile(
            self.questionnaire_answers(),
            pd.DataFrame(),
        )

        self.assertEqual(results, [])

    def test_empty_questionnaire_profile_is_rejected_instead_of_scored(self):
        with self.assertRaisesRegex(ValueError, "ingen numeriske værdier"):
            rank_questionnaire_profile({}, self.education_profiles())

    def test_invalid_questionnaire_values_raise_instead_of_fabricating_a_match(self):
        questionnaire = self.questionnaire_answers()
        questionnaire["evner"]["Matematiske problemer"] = 6

        with self.assertRaisesRegex(ValueError, "1-5"):
            rank_questionnaire_profile(questionnaire, self.education_profiles())

    def test_missing_education_data_error_is_not_hidden(self):
        with patch(
            "matching_service.load_education_profiles",
            side_effect=FileNotFoundError("UFSN workbook missing"),
        ):
            with self.assertRaisesRegex(FileNotFoundError, "workbook missing"):
                rank_questionnaire_profile(self.questionnaire_answers())


if __name__ == "__main__":
    unittest.main()
