import json
import os
import tempfile
import unittest
from uuid import uuid4
from unittest.mock import Mock, patch

import pandas as pd
import requests
import streamlit as st
from streamlit.testing.v1 import AppTest

from matching_service import rank_questionnaire_profile
from account_store import create_account, load_account_state

APP_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "app.py"))


class AppFlowTests(unittest.TestCase):
    def setUp(self):
        st.cache_data.clear()
        self.database_dir = tempfile.TemporaryDirectory()
        self.previous_database = os.environ.get("STUDIEKOMPAS_DB")
        os.environ["STUDIEKOMPAS_DB"] = os.path.join(
            self.database_dir.name, "accounts.sqlite3"
        )

    def tearDown(self):
        if self.previous_database is None:
            os.environ.pop("STUDIEKOMPAS_DB", None)
        else:
            os.environ["STUDIEKOMPAS_DB"] = self.previous_database
        self.database_dir.cleanup()

    @staticmethod
    def new_app():
        username = f"test_{uuid4().hex[:12]}"
        create_account(username, "test-password-123")
        app = AppTest.from_file(APP_PATH, default_timeout=60)
        app.session_state["active_account"] = username
        return app

    @staticmethod
    def widget(app, collection_name, key):
        return next(
            item
            for item in list(getattr(app, collection_name))
            if item.key == key
        )

    def click(self, app, predicate):
        buttons = [
            *list(app.button),
            *list(getattr(app, "form_submit_button", [])),
        ]
        button = next(item for item in buttons if predicate(item))
        button.click().run()
        # AppTest 1.51 retains widget nodes across st.rerun; this models the next browser render.
        app.run()
        self.assertEqual(list(app.exception), [])

    def click_once(self, app, predicate):
        buttons = [
            *list(app.button),
            *list(getattr(app, "form_submit_button", [])),
        ]
        button = next(item for item in buttons if predicate(item))
        button.click().run()
        self.assertEqual(list(app.exception), [])

    def start_questionnaire(self, app):
        self.click(app, lambda button: button.label.startswith("Kom i gang"))
        self.assertEqual(app.session_state["selected_page"], "Spørgeskema")
        self.assertEqual(app.session_state["profile_step"], 1)

    def submit_current_step(self, app, final=False):
        prefix = "Se mit overblik" if final else "Forts"
        self.click(app, lambda button: button.label.startswith(prefix))

    @staticmethod
    def flow_label(app):
        return next(item.value for item in app.markdown if "DIT FORLØB" in item.value)

    def open_final_questionnaire_step(self, app, model_ready):
        app.session_state["selected_page"] = "Spørgeskema"
        app.session_state["profile_step"] = 5
        app.session_state["model_ready"] = model_ready
        app.run()

    def test_complete_questionnaire_match_details_favorites_and_restart(self):
        with (
            patch.object(st, "rerun", lambda: None),
            patch("requests.get", side_effect=requests.ConnectionError("offline")),
        ):
            app = self.new_app().run()
            self.assertEqual(app.session_state["selected_page"], "Start")
            self.start_questionnaire(app)

            self.widget(app, "selectbox", "q_uddannelse").set_value("HTX")
            self.widget(app, "selectbox", "q_klassetrin").set_value("2.g")
            self.submit_current_step(app)

            self.widget(app, "multiselect", "q_best_subjects").set_value(["Matematik"])
            self.widget(app, "multiselect", "q_strong_subjects").set_value(["Fysik"])
            self.widget(app, "radio", "q_uni_yes").set_value("Ja")
            self.widget(app, "text_input", "q_uni_subjects").set_value("Fysik")
            self.submit_current_step(app)

            self.widget(app, "multiselect", "q_top").set_value(["Teknologi og IT"])
            app.run()
            interest_slider = self.widget(app, "slider", "q_interest_0")
            interest_slider.set_value(5)
            app.run()
            self.assertEqual(
                self.widget(app, "slider", "q_interest_0").value,
                5,
            )
            self.submit_current_step(app)

            self.widget(app, "slider", "q_workstyle").set_value(4)
            self.widget(app, "slider", "q_theory").set_value(5)
            self.submit_current_step(app)

            self.widget(app, "multiselect", "q_jobareas").set_value(["Teknologi / IT"])
            self.widget(app, "text_input", "q_study_ideas").set_value("Ingeniøruddannelse")
            self.click(app, lambda button: button.label.startswith("← Tilbage"))
            self.assertEqual(app.session_state["profile_step"], 4)
            self.assertEqual(app.session_state["profile"]["jobomraader"], ["Teknologi / IT"])
            self.assertEqual(
                app.session_state["profile"]["uddannelser_tanker"],
                "Ingeniøruddannelse",
            )

            self.widget(app, "slider", "q_workstyle").set_value(2)
            self.click(app, lambda button: button.label.startswith("← Tilbage"))
            self.assertEqual(app.session_state["profile_step"], 3)
            self.assertEqual(app.session_state["profile"]["arbejdsform"], 2)
            self.assertEqual(
                self.widget(app, "slider", "q_interest_0").value,
                5,
            )
            self.click(app, lambda button: button.label.startswith("← Tilbage"))
            self.assertEqual(app.session_state["profile_step"], 2)
            self.assertEqual(
                self.widget(app, "multiselect", "q_best_subjects").value,
                ["Matematik"],
            )
            self.submit_current_step(app)
            self.assertEqual(
                self.widget(app, "slider", "q_interest_0").value,
                5,
            )
            self.submit_current_step(app)
            self.assertEqual(self.widget(app, "slider", "q_workstyle").value, 2)
            self.submit_current_step(app)
            self.assertEqual(
                self.widget(app, "multiselect", "q_jobareas").value,
                ["Teknologi / IT"],
            )
            self.assertEqual(
                self.widget(app, "text_input", "q_study_ideas").value,
                "Ingeniøruddannelse",
            )
            self.submit_current_step(app, final=True)

            profile = app.session_state["profile"]
            self.assertEqual(profile["uddannelse"], "HTX")
            self.assertEqual(profile["klassetrin"], "2.g")
            self.assertEqual(profile["bedste_fag"], ["Matematik"])
            self.assertEqual(profile["staerkeste_fag"], ["Fysik"])
            self.assertEqual(profile["topinteresser"], ["Teknologi og IT"])
            self.assertEqual(profile["interesser"]["Teknologi og IT"], 5)
            self.assertEqual(profile["arbejdsform"], 2)
            self.assertEqual(profile["teori_praksis"], 5)
            self.assertEqual(profile["jobomraader"], ["Teknologi / IT"])
            self.assertEqual(app.session_state["selected_page"], "Gennemgang")
            self.assertFalse(app.session_state["model_ready"])

            self.click(app, lambda button: button.label == "← Rediger mine svar")
            self.assertEqual(app.session_state["selected_page"], "Spørgeskema")
            self.widget(app, "selectbox", "q_klassetrin").set_value("3.g")
            self.click(
                app,
                lambda button: button.label.startswith("Næste trin"),
            )
            self.assertEqual(app.session_state["profile_step"], 2)
            self.widget(app, "multiselect", "q_best_subjects").set_value(["Programmering"])
            self.click(
                app,
                lambda button: button.label.startswith("Næste trin"),
            )
            self.assertEqual(app.session_state["profile_step"], 3)
            self.click(
                app,
                lambda button: button.label == "Gem ændringer",
            )
            self.assertEqual(app.session_state["selected_page"], "Gennemgang")
            self.assertEqual(app.session_state["profile"]["klassetrin"], "3.g")
            self.assertEqual(app.session_state["profile"]["bedste_fag"], ["Programmering"])
            self.assertTrue(app.session_state["profile_completed"])
            self.assertEqual(
                load_account_state(app.session_state["active_account"])["profile"]["klassetrin"],
                "3.g",
            )
            self.assertEqual(
                load_account_state(app.session_state["active_account"])["profile"]["bedste_fag"],
                ["Programmering"],
            )

            with patch(
                "matching_service.rank_questionnaire_profile",
                wraps=rank_questionnaire_profile,
            ) as rank_profile:
                self.click(
                    app,
                    lambda button: button.label.startswith(
                        "Find uddannelser med Matching v3"
                    ),
                )
            self.assertEqual(
                rank_profile.call_args.args[0]["arbejdsform"],
                2,
            )
            self.assertTrue(app.session_state["matching_calculated"])
            self.assertEqual(app.session_state["selected_page"], "Anbefalinger")
            self.assertTrue(app.session_state["recommendations"])
            ranked_titles = [
                (item["Titel"], item["match_score"])
                for item in app.session_state["recommendations"]
            ]
            self.widget(app, "radio", "selected_page").set_value("Gennemgang")
            app.run()
            self.click(
                app,
                lambda button: button.label.startswith("Find uddannelser med Matching v3"),
            )
            self.assertEqual(
                [
                    (item["Titel"], item["match_score"])
                    for item in app.session_state["recommendations"]
                ],
                ranked_titles,
            )
            result_items = app.session_state["recommendations"]
            self.assertEqual(
                [
                    (metric.label, metric.value)
                    for metric in app.metric
                    if metric.label in {"Matchscore", "Datadækning"}
                ],
                [
                    value
                    for item in result_items
                    for value in (
                        ("Matchscore", f"{item['match_score']:.1f}/100"),
                        (
                            "Datadækning",
                            f"{item['data_coverage_count']}/"
                            f"{item['data_coverage_total']} dimensioner",
                        ),
                    )
                ],
            )
            result_captions = "\n".join(caption.value for caption in app.caption)
            self.assertIn("ikke sandsynlighed for optagelse", result_captions)
            self.assertIn("mindst 8 sammenlignelige dimensioner", result_captions)
            self.assertIn("Adgangskrav skal kontrolleres", result_captions)
            self.assertTrue(result_items[0]["strongest_positive_dimensions"])
            self.assertEqual(
                ranked_titles,
                sorted(ranked_titles, key=lambda result: -result[1]),
            )
            comparison_labels = [
                f"{item['Titel']} · {item.get('institution') or 'Institution ikke angivet'}"
                for item in result_items[:2]
            ]
            self.widget(app, "multiselect", "compare_choices").set_value(
                comparison_labels
            )
            app.run()
            comparison_text = "\n".join(
                repr(dataframe.value) for dataframe in app.dataframe
            )
            self.assertIn("Sammenlignelige dimensioner", comparison_text)
            self.assertIn("Stærkeste matchbidrag", comparison_text)

            first_title = app.session_state["recommendations"][0]["Titel"]
            self.click(app, lambda button: button.label.startswith("Se uddannelsen"))
            self.assertEqual(
                app.session_state["selected_recommendation"]["Titel"],
                first_title,
            )
            detail_captions = "\n".join(caption.value for caption in app.caption)
            self.assertIn("ikke en sandsynlighed for optagelse", detail_captions)
            self.assertIn("Adgangskrav er ikke verificeret", detail_captions)
            self.assertTrue(
                any(metric.label == "Datadækning" for metric in app.metric)
            )
            self.assertTrue(app.expander)
            self.click(app, lambda button: button.label == "Gem som favorit")
            self.assertEqual(len(app.session_state["favorites"]), 1)
            self.click(app, lambda button: button.label == "Fjern fra favoritter")
            self.assertEqual(app.session_state["favorites"], [])
            self.click(app, lambda button: button.label == "Gem som favorit")
            self.assertEqual(len(app.session_state["favorites"]), 1)
            self.widget(app, "radio", "selected_page").set_value("Favoritter")
            app.run()
            favorite_captions = "\n".join(
                caption.value for caption in app.caption
            )
            self.assertIn("ikke sandsynlighed for optagelse", favorite_captions)
            self.assertEqual(
                [
                    metric.label
                    for metric in app.metric
                    if metric.label in {"Matchscore", "Datadækning"}
                ],
                ["Matchscore", "Datadækning"],
            )
            self.click(app, lambda button: button.label.startswith("Se uddannelsen"))
            self.assertEqual(app.session_state["detail_return_page"], "Favoritter")
            self.click(
                app,
                lambda button: button.label == "Tilbage til mine favoritter",
            )
            self.assertEqual(app.session_state["selected_page"], "Favoritter")

            self.click(app, lambda button: button.label == "Start spørgeskema forfra")
            self.assertEqual(app.session_state["selected_page"], "Start")
            self.assertEqual(app.session_state["profile_step"], 1)
            self.assertEqual(app.session_state["profile"]["uddannelse"], "STX")
            self.assertEqual(app.session_state["profile"]["klassetrin"], "1.g")
            self.assertEqual(app.session_state["profile"]["topinteresser"], [])
            self.assertEqual(app.session_state["recommendations"], [])
            self.assertFalse(app.session_state["matching_calculated"])
            self.assertIsNone(app.session_state["selected_recommendation"])
            self.assertIsNone(app.session_state["matching_error"])
            self.assertEqual(app.session_state["followup_questions"], [])
            self.assertEqual(app.session_state["followup_answers"], {})
            self.assertEqual(app.session_state["previous_recommendations"], [])
            self.assertEqual(app.session_state["chat_messages"], [])
            self.assertEqual(len(app.session_state["favorites"]), 1)

            self.widget(app, "radio", "selected_page").set_value("Anbefalinger")
            app.run()
            self.assertIsNone(app.session_state["selected_recommendation"])
            self.assertTrue(any("endnu ikke beregnet" in item.value for item in app.info))
            self.assertEqual(list(app.exception), [])

    def test_profile_edits_recalculate_existing_recommendations(self):
        with (
            patch.object(st, "rerun", lambda: None),
            patch("requests.get", side_effect=requests.ConnectionError("offline")),
            patch(
                "matching_service.rank_questionnaire_profile",
                return_value=[],
            ) as rank_profile,
        ):
            app = self.new_app().run()
            app.session_state["profile_completed"] = True
            app.session_state["matching_calculated"] = True
            app.session_state["recommendations"] = [{"Titel": "Tidligere forslag"}]
            app.session_state["selected_page"] = "Spørgeskema"
            app.session_state["profile_step"] = 5
            app.run()

            self.widget(app, "multiselect", "q_jobareas").set_value(["Sundhed"])
            self.click(app, lambda button: button.label == "Gem ændringer")

        self.assertTrue(app.session_state["matching_calculated"])
        self.assertEqual(app.session_state["selected_page"], "Anbefalinger")
        self.assertEqual(app.session_state["profile"]["jobomraader"], ["Sundhed"])
        self.assertEqual(
            rank_profile.call_args.args[0]["jobomraader"],
            ["Sundhed"],
        )
        saved_state = load_account_state(app.session_state["active_account"])
        self.assertEqual(saved_state["profile"]["jobomraader"], ["Sundhed"])
        self.assertEqual(list(app.exception), [])

    def test_account_signup_opens_saved_profile_without_forcing_questionnaire(self):
        with patch.object(st, "rerun", lambda: None):
            app = AppTest.from_file(APP_PATH, default_timeout=60).run()
            self.assertEqual(app.session_state["selected_page"], "Start")
            self.assertTrue(any(button.label == "Fortsæt som gæst →" for button in app.button))

            self.widget(app, "text_input", "new_username").set_value("new_student")
            self.widget(app, "text_input", "new_password").set_value("secure-password")
            self.widget(app, "text_input", "confirm_password").set_value("secure-password")
            self.click(app, lambda button: button.label == "Opret konto")

        self.assertEqual(app.session_state["active_account"], "new_student")
        self.assertEqual(app.session_state["selected_page"], "Start")
        self.assertFalse(app.session_state["profile_completed"])
        self.assertTrue(any(button.label == "Kom i gang →" for button in app.button))
        self.assertEqual(list(app.exception), [])
        self.click(app, lambda button: button.label == "Log ud")
        self.assertNotIn("active_account", app.session_state)
        self.assertEqual(app.session_state["selected_page"], "Start")
        self.assertTrue(any(button.label == "Fortsæt som gæst →" for button in app.button))

    def test_guest_can_continue_without_account_and_end_guest_session(self):
        with patch.object(st, "rerun", lambda: None):
            app = AppTest.from_file(APP_PATH, default_timeout=60).run()
            self.assertEqual(app.session_state["selected_page"], "Start")
            self.click(app, lambda button: button.label == "Fortsæt som gæst →")

            self.assertTrue(app.session_state["guest_mode"])
            self.assertNotIn("active_account", app.session_state)
            self.assertEqual(app.session_state["selected_page"], "Spørgeskema")
            self.assertEqual(list(app.exception), [])

    def test_no_qualified_results_are_presented_as_no_results(self):
        with (
            patch.object(st, "rerun", lambda: None),
            patch(
                "data.education_profiles.load_education_profiles",
                return_value=pd.DataFrame(),
            ),
        ):
            st.cache_data.clear()
            app = self.new_app()
            app.session_state["selected_page"] = "Gennemgang"
            app.run()
            self.click(
                app,
                lambda button: button.label.startswith("Find uddannelser med Matching v3"),
            )

        self.assertTrue(app.session_state["matching_calculated"])
        self.assertEqual(app.session_state["recommendations"], [])
        self.assertEqual(app.session_state["selected_page"], "Anbefalinger")
        self.assertTrue(any("Ingen tilbud kunne rangeres" in item.value for item in app.info))

    def test_education_data_failure_is_visible_and_not_marked_as_calculated(self):
        with (
            patch.object(st, "rerun", lambda: None),
            patch(
                "data.education_profiles.load_education_profiles",
                side_effect=FileNotFoundError("UFSN workbook missing"),
            ),
        ):
            st.cache_data.clear()
            app = self.new_app()
            app.session_state["selected_page"] = "Gennemgang"
            app.run()
            self.click_once(
                app,
                lambda button: button.label.startswith("Find uddannelser med Matching v3"),
            )

        self.assertFalse(app.session_state["matching_calculated"])
        self.assertEqual(app.session_state["recommendations"], [])
        self.assertIn("UFSN workbook missing", app.session_state["matching_error"])
        self.assertTrue(any("UFSN workbook missing" in item.value for item in app.error))

    def test_matching_processing_failure_is_visible_and_not_marked_as_calculated(self):
        with (
            patch.object(st, "rerun", lambda: None),
            patch(
                "data.education_profiles.load_education_profiles",
                return_value=pd.DataFrame([{"Titel": "Test"}]),
            ),
            patch(
                "matching_service.rank_questionnaire_profile",
                side_effect=ValueError("profile cannot be matched"),
            ),
        ):
            st.cache_data.clear()
            app = self.new_app()
            app.session_state["selected_page"] = "Gennemgang"
            app.run()
            self.click_once(
                app,
                lambda button: button.label.startswith("Find uddannelser med Matching v3"),
            )

        self.assertFalse(app.session_state["matching_calculated"])
        self.assertEqual(app.session_state["recommendations"], [])
        self.assertIn("profile cannot be matched", app.session_state["matching_error"])
        self.assertTrue(any("profile cannot be matched" in item.value for item in app.error))

    def test_unavailable_ollama_autoload_keeps_matching_independent(self):
        with (
            patch.object(st, "rerun", lambda: None),
            patch("requests.get", side_effect=requests.ConnectionError("offline")),
        ):
            app = self.new_app()
            app.session_state["profile_completed"] = True
            app.session_state["selected_page"] = "Gennemgang"
            app.run()

        self.assertFalse(app.session_state["model_ready"])
        self.assertTrue(app.session_state["ai_load_attempted"])
        self.assertTrue(any("kan ikke få forbindelse til Ollama" in item.value for item in app.warning))
        self.assertFalse(any(button.label == "Indlæs AI" for button in app.button))
        self.assertEqual(list(app.exception), [])

    def test_optional_ai_unavailable_uses_seven_step_flow_and_explains_matching(self):
        with (
            patch.object(st, "rerun", lambda: None),
            patch("requests.get", side_effect=requests.ConnectionError("offline")),
        ):
            app = self.new_app().run()
            self.assertTrue(
                any(
                    "AI indlæses automatisk" in item.value
                    for item in app.info
                )
            )
            self.open_final_questionnaire_step(app, model_ready=False)
            self.click_once(
                app, lambda button: button.label.startswith("Se mit overblik")
            )
            app.run()

        self.assertFalse(app.session_state["followup_step_included"])
        self.assertIn("6 af 7 · Dit overblik", self.flow_label(app))
        self.assertTrue(
            any(
                "AI-opfølgning blev sprunget over" in item.value
                and "Matching v3" in item.value
                for item in app.info
            )
        )
        self.widget(app, "radio", "selected_page").set_value("Anbefalinger")
        app.run()
        self.assertIn("7 af 7 · Forslag", self.flow_label(app))
        self.assertEqual(list(app.exception), [])

    def test_ai_followup_question_adds_step_and_keeps_it_after_answering(self):
        response = Mock()
        response.json.return_value = {
            "message": {"content": '{"questions":["Hvilke fag vil du gerne arbejde videre med?"]}'}
        }
        with (
            patch.object(st, "rerun", lambda: None),
            patch("requests.post", return_value=response),
        ):
            app = self.new_app()
            self.open_final_questionnaire_step(app, model_ready=True)
            self.click_once(
                app, lambda button: button.label.startswith("Se mit overblik")
            )
            app.run()

            self.assertTrue(app.session_state["followup_step_included"])
            self.assertEqual(
                app.session_state["followup_questions"],
                ["Hvilke fag vil du gerne arbejde videre med?"],
            )
            self.assertIn("6 af 8 · AI-opfølgning", self.flow_label(app))
            self.widget(app, "text_area", "followup_answer_0").set_value(
                "Jeg vil gerne arbejde videre med matematik."
            )
            app.run()
            self.click_once(app, lambda button: button.label.startswith("Gem svar"))
            app.run()

        self.assertEqual(app.session_state["followup_questions"], [])
        self.assertEqual(app.session_state["followup_answers"][
            "Hvilke fag vil du gerne arbejde videre med?"
        ], "Jeg vil gerne arbejde videre med matematik.")
        self.assertIn("7 af 8 · Dit overblik", self.flow_label(app))
        self.widget(app, "radio", "selected_page").set_value("Anbefalinger")
        app.run()
        self.assertIn("8 af 8 · Forslag", self.flow_label(app))
        self.assertEqual(list(app.exception), [])

    def test_ai_without_followup_questions_skips_optional_step(self):
        response = Mock()
        response.json.return_value = {"message": {"content": '{"questions":[]}'}}
        with (
            patch.object(st, "rerun", lambda: None),
            patch("requests.post", return_value=response),
        ):
            app = self.new_app()
            self.open_final_questionnaire_step(app, model_ready=True)
            self.click_once(
                app, lambda button: button.label.startswith("Se mit overblik")
            )
            app.run()

        self.assertFalse(app.session_state["followup_step_included"])
        self.assertEqual(app.session_state["followup_questions"], [])
        self.assertIn("6 af 7 · Dit overblik", self.flow_label(app))
        self.widget(app, "radio", "selected_page").set_value("Anbefalinger")
        app.run()
        self.assertIn("7 af 7 · Forslag", self.flow_label(app))
        self.assertEqual(list(app.exception), [])

    def test_invalid_ai_followup_shape_does_not_block_profile_review(self):
        response = Mock()
        response.json.return_value = {"message": {"content": "[]"}}
        with (
            patch.object(st, "rerun", lambda: None),
            patch("requests.post", return_value=response),
        ):
            app = self.new_app()
            app.session_state["selected_page"] = "Spørgeskema"
            app.session_state["profile_step"] = 5
            app.session_state["model_ready"] = True
            app.run()
            self.click_once(app, lambda button: button.label.startswith("Se mit overblik"))
            warning_shown = any(
                "AI-opfølgningen kunne ikke gennemføres" in item.value
                and "uddannelsesmatch" in item.value
                for item in app.warning
            )
            app.run()

        self.assertEqual(app.session_state["selected_page"], "Gennemgang")
        self.assertEqual(app.session_state["stage"], "gennemgang")
        self.assertEqual(app.session_state["followup_questions"], [])
        self.assertFalse(app.session_state["followup_step_included"])
        self.assertIn("6 af 7 · Dit overblik", self.flow_label(app))
        self.assertTrue(warning_shown)
        self.assertEqual(list(app.exception), [])

    def test_ai_chat_continues_when_ollama_reaches_token_limit(self):
        def response(*events):
            mocked = Mock()
            mocked.__enter__ = Mock(return_value=mocked)
            mocked.__exit__ = Mock(return_value=False)
            mocked.iter_lines.return_value = [
                json.dumps(event).encode("utf-8") for event in events
            ]
            return mocked

        responses = [
            response(
                {"message": {"content": "Et svar, der blev afbrudt"}, "done": False},
                {"message": {"content": ""}, "done": True, "done_reason": "length"},
            ),
            response(
                {"message": {"content": " og fortsatte helt."}, "done": True},
            ),
        ]
        with (
            patch.object(st, "rerun", lambda: None),
            patch("requests.post", side_effect=responses) as post,
        ):
            app = self.new_app()
            app.session_state["profile_completed"] = True
            app.session_state["model_ready"] = True
            app.session_state["recommendations"] = [
                {
                    "Titel": "Testuddannelse",
                    "institution": "Testinstitution",
                    "match_score": 80.0,
                    "data_coverage_count": 8,
                    "data_coverage_total": 17,
                    "offers_with_match_score": 1,
                    "offer_count": 1,
                    "strongest_positive_dimensions": [],
                }
            ]
            app.run()
            self.widget(app, "radio", "selected_page").set_value("Anbefalinger")
            app.session_state["pending_chat_question"] = "Kan du forklare det?"
            app.run()

        assistant_messages = [
            item["content"]
            for item in app.session_state["chat_messages"]
            if item["role"] == "assistant"
        ]
        self.assertEqual(post.call_count, 2)
        self.assertEqual(
            assistant_messages[-1],
            "Et svar, der blev afbrudt og fortsatte helt.",
        )
        continuation_messages = post.call_args_list[1].kwargs["json"]["messages"]
        self.assertEqual(
            continuation_messages[-2]["content"],
            "Et svar, der blev afbrudt",
        )
        self.assertIn("Fortsæt dit svar", continuation_messages[-1]["content"])
        self.assertEqual(list(app.exception), [])

    def test_ai_chat_displays_tokens_before_ollama_finishes(self):
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        server_state = {"done": False}

        def streamed_events():
            yield json.dumps(
                {"message": {"content": "Første del"}, "done": False}
            ).encode("utf-8")
            server_state["done"] = True
            yield json.dumps(
                {
                    "message": {"content": ""},
                    "done": True,
                    "done_reason": "stop",
                }
            ).encode("utf-8")

        response.iter_lines.return_value = streamed_events()
        displayed_chunks = []

        def capture_stream(chunks):
            collected = []
            for chunk in chunks:
                displayed_chunks.append((chunk, server_state["done"]))
                collected.append(chunk)
            return "".join(collected)

        with (
            patch.object(st, "rerun", lambda: None),
            patch("requests.post", return_value=response),
            patch("streamlit.write_stream", side_effect=capture_stream),
        ):
            app = self.new_app()
            app.session_state["profile_completed"] = True
            app.session_state["model_ready"] = True
            app.session_state["recommendations"] = [
                {
                    "Titel": "Testuddannelse",
                    "institution": "Testinstitution",
                    "match_score": 80.0,
                    "data_coverage_count": 8,
                    "data_coverage_total": 17,
                    "offers_with_match_score": 1,
                    "offer_count": 1,
                    "strongest_positive_dimensions": [],
                }
            ]
            app.run()
            self.widget(app, "radio", "selected_page").set_value("Anbefalinger")
            app.run()
            app.session_state["pending_chat_question"] = "Hvad passer til mig?"
            app.run()

        self.assertEqual(displayed_chunks, [("Første del", False)])
        self.assertEqual(list(app.exception), [])

    def test_user_chat_prompt_takes_precedence_over_pending_comparison_prompt(self):
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.iter_lines.return_value = [
            json.dumps(
                {
                    "message": {"content": "Jeg svarer på dit spørgsmål."},
                    "done": True,
                    "done_reason": "stop",
                }
            ).encode("utf-8")
        ]
        with (
            patch.object(st, "rerun", lambda: None),
            patch("requests.post", return_value=response) as post,
        ):
            app = self.new_app()
            app.session_state["profile_completed"] = True
            app.session_state["model_ready"] = True
            app.session_state["recommendations"] = [
                {
                    "Titel": "Testuddannelse",
                    "institution": "Testinstitution",
                    "match_score": 80.0,
                    "data_coverage_count": 8,
                    "data_coverage_total": 17,
                    "offers_with_match_score": 1,
                    "offer_count": 1,
                    "strongest_positive_dimensions": [],
                }
            ]
            app.run()
            self.widget(app, "radio", "selected_page").set_value("Anbefalinger")
            app.run()
            app.session_state["pending_chat_question"] = (
                "Sammenlign forslagene automatisk"
            )
            self.widget(app, "chat_input", "advisor_chat_input").set_value(
                "Kan du forklare programmering?"
            )
            app.run()

        sent_messages = post.call_args.kwargs["json"]["messages"]
        self.assertEqual(sent_messages[-1]["content"], "Kan du forklare programmering?")
        self.assertNotIn(
            "Sammenlign forslagene automatisk",
            [message["content"] for message in sent_messages],
        )
        self.assertNotIn("pending_chat_question", app.session_state)
        self.assertEqual(list(app.exception), [])

    def test_ai_chat_includes_relevant_education_workbook_data(self):
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.iter_lines.return_value = [
            json.dumps(
                {
                    "message": {"content": "Datamatiker-data er med."},
                    "done": True,
                    "done_reason": "stop",
                }
            ).encode("utf-8")
        ]
        with (
            patch.object(st, "rerun", lambda: None),
            patch("requests.post", return_value=response) as post,
        ):
            app = self.new_app()
            app.session_state["profile_completed"] = True
            app.session_state["model_ready"] = True
            app.session_state["recommendations"] = [
                {
                    "Titel": "Testuddannelse",
                    "institution": "Testinstitution",
                    "match_score": 80.0,
                    "data_coverage_count": 8,
                    "data_coverage_total": 17,
                    "offers_with_match_score": 1,
                    "offer_count": 1,
                    "strongest_positive_dimensions": [],
                }
            ]
            app.run()
            self.widget(app, "radio", "selected_page").set_value("Anbefalinger")
            app.run()
            app.session_state["profile"]["topinteresser"] = [
                "Kreativitet og design",
                "Teknologi og IT",
            ]
            app.session_state["profile"]["bedste_fag"] = ["Design"]
            app.session_state["profile"]["undgaa"] = ["Økonomi og business"]
            app.session_state["profile"]["byer"] = "Aarhus"
            app.session_state["followup_answers"] = {
                "Hvad vil du gerne arbejde med?": "Jeg vil gerne designe apps."
            }
            app.session_state["pending_chat_question"] = (
                "Hvad siger uddannelsesdata om Datamatiker?"
            )
            app.run()

        system_context = "\n".join(
            message["content"]
            for message in post.call_args.kwargs["json"]["messages"]
            if message["role"] == "system"
        )
        self.assertIn("Relevante uddannelsesdata fra arbejdsbogen", system_context)
        self.assertIn('"Titel": "Datamatiker"', system_context)
        self.assertIn("profilområder", system_context)
        self.assertIn("faktiske kompetencebeskrivelser", system_context)
        self.assertIn("ikke officielle vurderinger", system_context)
        self.assertIn("Kreativitet og design", system_context)
        self.assertIn("Bedste fag: Design", system_context)
        self.assertIn("Faglige fravalg: Økonomi og business", system_context)
        self.assertIn("Ønsket by eller uddannelsessted: Aarhus", system_context)
        self.assertIn("Jeg vil gerne designe apps.", system_context)
        self.assertIn("korrekt stavning", system_context)
        self.assertIn("Nævn relevante svar fra spørgeskemaet", system_context)
        self.assertLessEqual(
            post.call_args.kwargs["json"]["options"]["num_predict"],
            320,
        )
        self.assertEqual(list(app.exception), [])


if __name__ == "__main__":
    unittest.main()
