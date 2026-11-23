"""Studievejleder-chat med profil, anbefalinger og favoritter."""

from __future__ import annotations

from copy import deepcopy
from contextlib import nullcontext
from html import escape
import json
import math
import os
import re
from collections.abc import Iterator, Mapping
import sqlite3
from typing import Any

import pandas as pd
import requests
import streamlit as st
import streamlit.components.v1 as components

from account_store import (
    AccountError,
    authenticate_account,
    create_account,
    delete_account_state,
    load_account_state,
    save_account_state,
)
from data.education_profiles import (
    PROFILE_DIMENSIONS,
    load_education_profiles,
    normalize_text,
)
from matching_service import (
    questionnaire_matching_preferences,
    rank_questionnaire_profile,
)


MODEL = "phi3.5"
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
MATCHING_RULES_VERSION = 3
AREAS = [
    "Teknologi og IT", "Matematik", "Naturvidenskab", "Medicin og sundhed",
    "Psykologi", "Mennesker og sociale forhold", "Samfund og politik",
    "Økonomi og business", "Jura", "Sprog og kommunikation",
    "Historie og kultur", "Kreativitet og design", "Medier og kommunikation",
    "Miljø og klima",
]
ABILITIES = [
    "Matematiske problemer", "Logisk tænkning", "Analyse", "Problemløsning",
    "Kreativ tænkning", "Skriftlig kommunikation", "Mundtlig kommunikation",
    "At lære nye ting", "At arbejde selvstændigt", "At arbejde sammen med andre",
    "Teknologi og computere", "At arbejde med data",
]
WORK_VALUES = [
    "Høj løn", "Jobsikkerhed", "Fleksibilitet", "Mulighed for hjemmearbejde",
    "Kreativ frihed", "At hjælpe andre mennesker", "At arbejde med teknologi",
    "At arbejde internationalt", "Gode muligheder for karriereudvikling",
    "God balance mellem arbejde og fritid",
]
SUBJECTS = [
    "Dansk", "Engelsk", "Matematik", "Fysik", "Kemi", "Biologi", "Bioteknologi",
    "Geografi", "Informatik", "Programmering", "Softwareudvikling", "Datalogi",
    "Teknikfag", "Samfundsfag", "Historie", "Psykologi", "International økonomi",
    "Virksomhedsøkonomi", "Afsætning", "Erhvervsjura", "Sprog", "Mediefag",
    "Design", "Kunstneriske fag", "Andet",
]
JOB_FIELDS = [
    "Teknologi / IT", "Ingeniørarbejde", "Sundhed", "Forskning", "Økonomi",
    "Business", "Jura", "Undervisning", "Psykologi", "Kommunikation", "Design",
    "Medier", "Politik / samfund", "Natur / miljø", "Noget andet",
]
WORKDAY = [
    "Arbejde ved computer", "Analysere information", "Løse problemer",
    "Arbejde med mennesker", "Skabe/design", "Arbejde med tal/data",
    "Bygge eller udvikle produkter", "Forske/undersøge", "Skrive og kommunikere",
    "Planlægge og organisere", "Noget andet",
]
DISLIKES = [
    "Teknologi og IT", "Matematik", "Naturvidenskab", "Medicin og sundhed",
    "Psykologi", "Mennesker og sociale forhold", "Samfund og politik",
    "Økonomi og business", "Jura", "Sprog og kommunikation",
    "Historie og kultur", "Kreativitet og design", "Medier og kommunikation",
    "Miljø og klima", "Andet",
]
SYSTEM_PROMPT = (
    "Du er en venlig, neutral og realistisk studievejleder for gymnasieelever i Danmark. "
    "Svar kort på dansk, normalt i 3-6 sætninger og højst 120 ord. "
    "Afslut svaret med hele, færdige sætninger; stop aldrig midt i en forklaring. "
    "Skriv korrekt og naturligt dansk med korrekt stavning og tegnsætning. "
    "Læs svaret igennem, og ret sproglige fejl, før du svarer. "
    "Brug elevens profil som kontekst, forklar dine begrundelser, "
    "stil højst ét afklarende spørgsmål ad gangen, og pres aldrig eleven mod ét valg. "
    "Anbefalinger er inspiration, ikke en beslutning. Skeln tydeligt mellem kendte fakta "
    "og usikkerhed. Opfind aldrig adgangskrav, uddannelser, links eller jobmuligheder."
)


st.set_page_config(
    page_title="Studiekompas",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="collapsed",
)
if "theme" not in st.session_state:
    st.session_state.theme = "Mørk"
if "selected_page" not in st.session_state:
    st.session_state.selected_page = "Start"
if "last_rendered_page" not in st.session_state:
    st.session_state.last_rendered_page = st.session_state.selected_page
if "profile_step" not in st.session_state:
    st.session_state.profile_step = 1

theme_tokens = {
    "page": "#151522",
    "surface": "#202031",
    "surface-soft": "#29293d",
    "text": "#f3f2fb",
    "muted": "#c0bfd2",
    "border": "#3c3c54",
    "input": "#29293d",
    "active": "#d5ceff",
} if st.session_state.theme == "Mørk" else {
    "page": "#f7f7fb",
    "surface": "#ffffff",
    "surface-soft": "#eeedf6",
    "text": "#191a2e",
    "muted": "#42445b",
    "border": "#d1d2e0",
    "input": "#ffffff",
    "active": "#4538a8",
}
theme_variables = "; ".join(f"--{name}: {value}" for name, value in theme_tokens.items())
theme_background = (
    "radial-gradient(ellipse at 5% 0%, rgba(91, 79, 179, .22), transparent 34rem), "
    "radial-gradient(ellipse at 100% 22%, rgba(123, 75, 136, .16), transparent 30rem), var(--page)"
    if st.session_state.theme == "Mørk"
    else "radial-gradient(ellipse at 5% 0%, rgba(204, 215, 255, .48), transparent 34rem), "
    "radial-gradient(ellipse at 100% 22%, rgba(255, 225, 211, .38), transparent 30rem), var(--page)"
)
st.markdown(
    """
    <style>
    .stApp {
        THEME_VARIABLES;
        background: THEME_BACKGROUND;
        color: var(--text);
    }
    .block-container { max-width: 1080px; padding-top: 2rem; padding-bottom: 5rem; }
    h1, h2, h3, h4, h5, h6 { letter-spacing: -.04em; color: var(--text); }
    h2 { margin-top: .8rem; font-size: clamp(1.65rem, 3vw, 2.15rem); }
    h3 { font-size: 1.25rem; }
    [data-testid="stMarkdownContainer"] p,
    [data-testid="stMarkdownContainer"] li,
    [data-testid="stMarkdownContainer"] strong,
    [data-testid="stMarkdownContainer"] em { color: var(--text); }
    [data-testid="stWidgetLabel"],
    [data-testid="stWidgetLabel"] *,
    [data-testid="stRadio"] label,
    [data-testid="stCheckbox"] label,
    [data-testid="stToggle"] label { color: var(--text) !important; }
    [data-testid="stMain"] [data-testid="stMarkdownContainer"] p { line-height: 1.7; }
    [data-testid="stMain"] [data-testid="stCaptionContainer"] { line-height: 1.55; }
    [data-testid="stSidebar"] {
        background: var(--surface);
        border-right: 1px solid var(--border);
        color: var(--text);
    }
    [data-testid="stSidebar"] .block-container { padding: 1rem 1rem 2rem; }
    [data-testid="stSidebar"] h2, [data-testid="stSidebar"] h3 { color: var(--text); }
    .side-brand {
        display: flex;
        align-items: center;
        gap: .75rem;
        margin: .15rem 0 1.3rem;
    }
    .side-brand-mark {
        display: grid;
        width: 2.7rem;
        height: 2.7rem;
        place-items: center;
        border-radius: 14px;
        background: linear-gradient(145deg, #5144bb, #9670de);
        color: #fff;
        font-size: 1.35rem;
        box-shadow: 0 7px 16px rgba(81, 68, 187, .24);
    }
    .side-brand-copy strong { display: block; color: var(--text); font-size: 1rem; }
    .side-brand-copy small {
        color: var(--muted);
        font-size: .64rem;
        font-weight: 750;
        letter-spacing: .11em;
    }
    [data-testid="stSidebar"] [data-testid="stRadio"] label {
        margin: .1rem 0;
        padding: .55rem .7rem;
        border: 1px solid transparent;
        border-radius: 13px;
        transition: background .18s ease, color .18s ease, border .18s ease;
    }
    [data-testid="stSidebar"] [data-testid="stRadio"] p { color: var(--text) !important; }
    [data-testid="stSidebar"] [data-testid="stRadio"] label:has(input:checked) {
        border-color: var(--border);
        background: var(--surface-soft);
    }
    [data-testid="stSidebar"] [data-testid="stRadio"] label:hover {
        background: var(--surface-soft);
        color: var(--active);
    }
    [data-testid="stSidebar"] [data-testid="stRadio"] input { accent-color: #796be2; }
    header[data-testid="stHeader"] { background: transparent; }
    [data-testid="stForm"] {
        padding: 1.6rem 1.75rem;
        background: var(--surface);
        border: 1px solid var(--border);
        border-radius: 24px;
        box-shadow: 0 16px 42px rgba(0, 0, 0, .12);
    }
    [data-testid="stForm"] h3 {
        margin: 1.3rem 0 .65rem;
        padding-top: 1.1rem;
        border-top: 1px solid var(--border);
    }
    [data-testid="stForm"] h3:first-child {
        margin-top: 0;
        padding-top: 0;
        border-top: 0;
    }
    [data-testid="stVerticalBlockBorderWrapper"] {
        background: var(--surface);
        border-color: var(--border);
        border-radius: 21px;
        box-shadow: 0 8px 24px rgba(0, 0, 0, .07);
    }
    [data-testid="stVerticalBlockBorderWrapper"] h3 { margin-bottom: .2rem; }
    [data-testid="stMain"] [data-testid="stRadio"] label[data-baseweb="radio"] {
        min-height: 2.7rem;
        margin: .15rem .2rem .15rem 0;
        padding: .55rem .8rem;
        border: 1px solid var(--border);
        border-radius: 13px;
        background: var(--surface);
        transition: border-color .15s ease, background .15s ease;
    }
    [data-testid="stMain"] [data-testid="stRadio"] label[data-baseweb="radio"]:has(input:checked) {
        border-color: #796be2;
        background: var(--surface-soft);
    }
    [data-testid="stMain"] [data-testid="stMultiSelect"] [data-baseweb="tag"] {
        border: 1px solid var(--border);
        border-radius: 999px;
        background: var(--surface-soft);
    }
    [data-testid="stForm"] [data-testid="stWidgetLabel"] {
        margin-bottom: .35rem;
    }
    [data-testid="stForm"] [data-testid="stElementContainer"] {
        margin-bottom: .45rem;
    }
    [data-baseweb="input"] > div, [data-baseweb="textarea"] > div,
    [data-baseweb="select"] > div {
        min-height: 2.8rem;
        border-radius: 13px;
        border-color: var(--border) !important;
        background: var(--input) !important;
        color: var(--text) !important;
    }
    [data-baseweb="textarea"] {
        border-color: var(--border) !important;
        background: var(--input) !important;
    }
    [data-baseweb="input"] > div:focus-within,
    [data-baseweb="textarea"] > div:focus-within,
    [data-baseweb="select"] > div:focus-within {
        border-color: #796be2;
        box-shadow: 0 0 0 1px #796be2;
    }
    [data-baseweb="input"] input, [data-baseweb="textarea"] textarea,
    [data-baseweb="select"] *, [data-baseweb="menu"] *,
    [role="listbox"] *,
    [data-testid="stMarkdownContainer"] p,
    [data-testid="stMarkdownContainer"] li { color: var(--text); }
    [data-baseweb="input"] input, [data-baseweb="textarea"] textarea {
        -webkit-text-fill-color: var(--text);
    }
    [data-baseweb="input"] input::placeholder,
    [data-baseweb="textarea"] textarea::placeholder {
        color: var(--muted);
        -webkit-text-fill-color: var(--muted);
        opacity: 1;
    }
    [data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] *,
    [data-testid="stWidgetLabel"] small { color: var(--muted) !important; }
    [data-testid="stBottom"] {
        background: var(--page);
    }
    [data-testid="stBottom"] > div {
        background: linear-gradient(transparent, var(--page) 28%);
    }
    [data-testid="stChatInput"] {
        background: var(--surface);
        border: 1px solid var(--border);
        border-radius: 16px;
    }
    [data-testid="stChatInput"] > div {
        background: var(--surface) !important;
    }
    [data-testid="stChatInput"] textarea {
        color: var(--text) !important;
        -webkit-text-fill-color: var(--text);
    }
    [data-testid="stChatInput"] button { color: var(--muted); }
    [data-testid="stAlert"] { border-color: var(--border); }
    [data-testid="stAlert"] p { color: var(--text); }
    [data-testid="stDataFrame"], [data-testid="stJson"] {
        border: 1px solid var(--border);
        border-radius: 12px;
    }
    .stButton > button, [data-testid="stFormSubmitButton"] > button,
    [data-testid="stLinkButton"] > a {
        min-height: 2.8rem;
        border-radius: 13px;
        font-weight: 650;
        transition: transform .16s ease, box-shadow .16s ease, background .16s ease, border-color .16s ease;
        color: var(--text) !important;
        -webkit-text-fill-color: var(--text) !important;
        border: 1px solid var(--border) !important;
        background: var(--surface) !important;
    }
    .stButton > button:not([kind="primary"]) *,
    [data-testid="stFormSubmitButton"] > button:not([kind="primary"]) *,
    [data-testid="stLinkButton"] > a * {
        color: var(--text) !important;
        -webkit-text-fill-color: var(--text) !important;
    }
    .stButton > button:hover, [data-testid="stFormSubmitButton"] > button:hover,
    [data-testid="stLinkButton"] > a:hover {
        transform: translateY(-1px);
        box-shadow: 0 7px 18px rgba(75, 62, 169, .15);
    }
    .stButton > button[kind="primary"],
    [data-testid="stFormSubmitButton"] > button[kind="primary"] {
        border: 0 !important;
        color: #fff !important;
        -webkit-text-fill-color: #fff !important;
        background: linear-gradient(110deg, #5144bb, #7960d8) !important;
        box-shadow: 0 7px 18px rgba(81, 68, 187, .2);
    }
    .stButton > button[kind="primary"] *,
    [data-testid="stFormSubmitButton"] > button[kind="primary"] * {
        color: #fff !important;
        -webkit-text-fill-color: #fff !important;
    }
    [data-testid="stChatMessage"] {
        background: var(--surface);
        border: 1px solid var(--border);
        border-radius: 16px;
        box-shadow: 0 6px 18px rgba(0, 0, 0, .1);
    }
    .welcome-hero {
        position: relative;
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 2rem;
        overflow: hidden;
        isolation: isolate;
        margin: .2rem 0 1rem;
        padding: 2rem 2.3rem;
        border: 1px solid rgba(255, 255, 255, .13);
        border-radius: 28px;
        color: #fff;
        background: linear-gradient(115deg, #252545 0%, #4b3da5 57%, #8760bd 100%);
        box-shadow: 0 20px 48px rgba(63, 52, 148, .23);
    }
    .welcome-hero::before, .welcome-hero::after {
        position: absolute;
        z-index: -1;
        content: "";
        border: 1px solid rgba(255, 255, 255, .11);
        border-radius: 50%;
    }
    .welcome-hero::before { width: 390px; height: 390px; right: 3%; top: -67%; }
    .welcome-hero::after { width: 270px; height: 270px; right: 8%; top: -43%; }
    .hero-copy { position: relative; z-index: 1; max-width: 700px; }
    .hero-eyebrow {
        display: inline-block;
        margin-bottom: .8rem;
        padding: .35rem .65rem;
        border: 1px solid rgba(255, 255, 255, .24);
        border-radius: 999px;
        background: rgba(255, 255, 255, .1);
        color: #f0edff;
        font-size: .68rem;
        font-weight: 750;
        letter-spacing: .12em;
    }
    .welcome-hero h1 {
        margin: 0;
        color: #fff;
        font-size: clamp(2rem, 4.5vw, 3.25rem);
        line-height: 1.08;
    }
    .welcome-hero p { margin: .8rem 0 0; color: #eeedff; font-size: 1.02rem; }
    .hero-orbit {
        position: relative;
        display: grid;
        width: 116px;
        height: 116px;
        flex: 0 0 116px;
        place-items: center;
        border: 1px solid rgba(255, 255, 255, .35);
        border-radius: 38%;
        background: rgba(255, 255, 255, .12);
        color: #fff;
        font-size: 3rem;
        transform: rotate(10deg);
    }
    .hero-orbit::before, .hero-orbit::after {
        position: absolute;
        content: "";
        border: 1px solid rgba(255, 255, 255, .22);
        border-radius: 38%;
        transform: rotate(-5deg);
    }
    .hero-orbit::before { inset: 10px; }
    .hero-orbit::after { inset: -12px; }
    .top-navigation {
        display: flex;
        align-items: center;
        gap: .65rem;
        height: 2.7rem;
        white-space: nowrap;
    }
    .top-navigation-mark {
        display: grid;
        width: 2.2rem;
        height: 2.2rem;
        place-items: center;
        border-radius: 11px;
        background: #5144bb;
        color: #fff;
        font-size: 1.05rem;
    }
    .top-navigation strong { color: var(--text); font-size: 1.02rem; }
    .st-key-top_navigation [data-testid="stRadio"] > div {
        gap: .2rem;
        justify-content: flex-end;
    }
    .st-key-top_navigation [data-testid="stRadio"] label[data-baseweb="radio"] {
        padding: .5rem .75rem;
        border: 1px solid transparent;
        border-radius: 12px;
        transition: background .15s ease, border-color .15s ease;
    }
    .st-key-top_navigation [data-testid="stRadio"] label[data-baseweb="radio"] > div:first-child {
        display: none;
    }
    .st-key-top_navigation [data-testid="stRadio"] label[data-baseweb="radio"] input {
        position: absolute;
        width: 1px;
        height: 1px;
        opacity: 0;
    }
    .st-key-top_navigation [data-testid="stRadio"] label[data-baseweb="radio"]:has(input:focus-visible) {
        outline: 2px solid #796be2;
        outline-offset: 2px;
    }
    .st-key-top_navigation [data-testid="stRadio"] label[data-baseweb="radio"]:has(input:checked) {
        border-color: var(--border);
        background: var(--surface);
    }
    .st-key-top_navigation [data-testid="stRadio"] p {
        color: var(--text) !important;
        font-size: .9rem;
        font-weight: 600;
    }
    .flow-label {
        display: flex;
        justify-content: space-between;
        gap: 1rem;
        margin: .5rem 0 .6rem;
        color: var(--muted);
        font-size: .82rem;
    }
    .flow-label strong { color: var(--text); font-weight: 650; }
    .flow-track {
        display: grid;
        grid-template-columns: repeat(8, minmax(0, 1fr));
        gap: .3rem;
        margin: 0 0 1.65rem;
    }
    .flow-track span {
        height: .24rem;
        border-radius: 999px;
        background: var(--border);
        transition: background .2s ease;
    }
    .flow-track span.is-complete,
    .flow-track span.is-active {
        background: #796be2;
        box-shadow: 0 0 10px rgba(121, 107, 226, .22);
    }
    .landing-page {
        max-width: 850px;
        margin: 4.2rem auto 2rem;
        text-align: center;
    }
    .landing-kicker {
        display: inline-block;
        margin-bottom: 1.1rem;
        padding: .45rem .8rem;
        border: 1px solid var(--border);
        border-radius: 999px;
        color: var(--active);
        font-size: .75rem;
        font-weight: 750;
        letter-spacing: .08em;
    }
    .landing-page h1 {
        margin: 0 auto;
        max-width: 780px;
        font-size: clamp(2.7rem, 7vw, 5rem);
        line-height: 1.02;
    }
    .landing-page > p {
        max-width: 680px;
        margin: 1.1rem auto 1.4rem;
        color: var(--muted);
        font-size: 1.08rem;
        line-height: 1.75;
    }
    .landing-points {
        display: flex;
        flex-wrap: wrap;
        justify-content: center;
        gap: .7rem 1.5rem;
        margin: 1.4rem auto;
        color: var(--muted);
        font-size: .9rem;
    }
    .landing-points span::first-letter { color: #7565d6; }
    .step-card {
        padding: .45rem .15rem .9rem;
    }
    .step-card h2 { margin: 0 0 .4rem; }
    .step-card > p { color: var(--muted); }
    .profile-insight {
        margin: .25rem 0 1.2rem;
        padding: 1rem 1.2rem;
        border: 1px solid var(--border);
        border-left: 3px solid #796be2;
        border-radius: 14px;
        background: var(--surface-soft);
        color: var(--text);
        line-height: 1.7;
    }
    .summary-item {
        display: flex;
        align-items: baseline;
        justify-content: space-between;
        gap: .7rem;
        padding: .55rem 0;
        border-bottom: 1px solid var(--border);
    }
    .summary-item:last-child { border-bottom: 0; }
    .summary-item span { color: var(--text); }
    .summary-item small { flex: 0 0 auto; color: var(--muted); }
    .recommendation-note {
        margin: .7rem 0;
        padding: .8rem 1rem;
        border: 1px solid var(--border);
        border-radius: 13px;
        background: var(--surface-soft);
    }
    .step-footer {
        display: flex;
        justify-content: space-between;
        gap: .8rem;
        margin-top: 1.1rem;
    }
    .profile-summary-label {
        margin-bottom: .2rem;
        color: var(--muted);
        font-size: .82rem;
        font-weight: 650;
    }
    .profile-summary-value { margin-bottom: 1rem; color: var(--text); }
    [data-testid="stMetric"] {
        padding: 1rem 1.1rem;
        border: 1px solid var(--border);
        border-radius: 17px;
        background: var(--surface);
        box-shadow: 0 8px 22px rgba(0, 0, 0, .07);
    }
    [data-testid="stMetricLabel"] { color: var(--muted); }
    [data-testid="stMetricValue"] { color: var(--text); }
    [data-testid="stExpander"] {
        overflow: hidden;
        border-color: var(--border);
        border-radius: 16px;
        background: var(--surface);
    }
    [data-testid="stChatMessage"] { padding: .9rem 1rem; }
    .stApp hr { border-color: var(--border); }
    #MainMenu, footer { visibility: hidden; }
    @media (max-width: 700px) {
        .block-container { padding: 1.6rem .85rem 3rem; }
        [data-testid="stForm"] { padding: 1rem; border-radius: 18px; }
        .landing-page { margin: 2.8rem auto 1.7rem; }
        .landing-page > p { font-size: 1rem; }
        .landing-points { align-items: flex-start; flex-direction: column; margin: 1.5rem 0; }
        .step-card { padding: 1.1rem; }
        .st-key-top_navigation [data-testid="stRadio"] > div { flex-wrap: wrap; justify-content: flex-start; }
        .st-key-top_navigation [data-testid="stRadio"] label[data-baseweb="radio"] { padding: .4rem .5rem; }
        .st-key-top_navigation [data-testid="stRadio"] p { font-size: .78rem; }
        .flow-track { gap: .2rem; margin-bottom: 1.2rem; }
        .flow-label { font-size: .75rem; }
        .summary-item { align-items: flex-start; flex-direction: column; gap: .15rem; }
    }
    </style>
    """.replace("THEME_VARIABLES", theme_variables).replace("THEME_BACKGROUND", theme_background),
    unsafe_allow_html=True,
)


def api_url(path: str) -> str:
    return f"{OLLAMA_URL}{path}"


def ollama_models() -> list[str]:
    response = requests.get(api_url("/api/tags"), timeout=5)
    response.raise_for_status()
    return [model["name"] for model in response.json().get("models", [])]


def model_is_installed(models: list[str]) -> bool:
    return any(name == MODEL or name.startswith(f"{MODEL}:") for name in models)


def pull_model(status: Any, progress: Any) -> None:
    with requests.post(
        api_url("/api/pull"), json={"name": MODEL, "stream": True},
        stream=True, timeout=(10, 900),
    ) as response:
        response.raise_for_status()
        for line in response.iter_lines():
            if not line:
                continue
            event = json.loads(line)
            if event.get("error"):
                raise RuntimeError(event["error"])
            status.update(label=event.get("status", "Henter model …").capitalize(), state="running")
            total, completed = event.get("total"), event.get("completed")
            if total and completed is not None:
                progress.progress(min(completed / total, 1.0), text=f"Henter {MODEL} · {completed / total:.0%}")


def warm_up_model() -> None:
    response = requests.post(
        api_url("/api/generate"),
        json={"model": MODEL, "prompt": "", "stream": False, "keep_alive": "30m"},
        timeout=300,
    )
    response.raise_for_status()


def prepare_chat_messages(
    messages: list[dict[str, str]],
    *,
    max_turns: int = 6,
    max_chars_per_message: int = 1200,
    max_chars_per_system_message: int = 6000,
) -> list[dict[str, str]]:
    cleaned: list[dict[str, str]] = []
    for message in messages:
        role = message.get("role")
        if role not in {"system", "user", "assistant"}:
            continue
        content = str(message.get("content", "") or "")
        max_chars = (
            max_chars_per_system_message
            if role == "system"
            else max_chars_per_message
        )
        if len(content) > max_chars:
            content = content[:max_chars].rstrip() + "…"
        cleaned.append({"role": role, "content": content})

    system_messages = [msg for msg in cleaned if msg["role"] == "system"]
    convo_messages = [msg for msg in cleaned if msg["role"] != "system"]
    if len(convo_messages) > max_turns:
        convo_messages = convo_messages[-max_turns:]
    return system_messages + convo_messages


def ollama_chat(messages: list[dict[str, str]], *, json_mode: bool = False) -> str:
    prepared = prepare_chat_messages(
        [{"role": "system", "content": SYSTEM_PROMPT}, *messages],
        max_turns=1,
        max_chars_per_message=6000,
        max_chars_per_system_message=6000,
    )
    payload: dict[str, Any] = {
        "model": MODEL,
        "messages": prepared,
        "stream": False,
        "keep_alive": "30m",
        "options": {
            "temperature": 0.2,
            "repeat_penalty": 1.2,
            "num_predict": 256,
        },
    }
    if json_mode:
        payload["format"] = "json"
    response = requests.post(api_url("/api/chat"), json=payload, timeout=(10, 600))
    response.raise_for_status()
    data = response.json()
    if data.get("error"):
        raise RuntimeError(data["error"])
    return data.get("message", {}).get("content", "")


def stream_chat(messages: list[dict[str, str]]) -> Iterator[str]:
    if messages and messages[0].get("role") == "system":
        system_content = messages[0].get("content", "")
        messages = messages[1:]
    else:
        system_content = SYSTEM_PROMPT

    prepared = prepare_chat_messages([
        {"role": "system", "content": system_content},
        *messages,
    ])
    options: dict[str, Any] = {
        "temperature": 0.2,
        "repeat_penalty": 1.2,
        "num_predict": 320,
    }
    answer_parts: list[str] = []
    for continuation in range(3):
        request_messages = prepared
        if answer_parts:
            request_messages = [
                *prepared,
                {"role": "assistant", "content": "".join(answer_parts)},
                {
                    "role": "user",
                    "content": (
                        "Fortsæt dit svar præcis fra det sted, hvor det sluttede. "
                        "Gentag ikke det allerede skrevne, og afslut med en hel sætning."
                    ),
                },
            ]
        payload = {
            "model": MODEL,
            "messages": request_messages,
            "stream": True,
            "keep_alive": "30m",
            "options": options,
        }
        segment_parts: list[str] = []
        done_reason = None
        completed = False
        for attempt in range(2):
            segment_parts = []
            done_reason = None
            completed = False
            try:
                with requests.post(
                    api_url("/api/chat"),
                    json=payload,
                    stream=True,
                    timeout=(10, 600),
                ) as response:
                    response.raise_for_status()
                    for line in response.iter_lines():
                        if not line:
                            continue
                        event = json.loads(line)
                        if event.get("error"):
                            raise RuntimeError(event["error"])
                        part = event.get("message", {}).get("content", "")
                        if part:
                            segment_parts.append(part)
                            yield part
                        if event.get("done"):
                            completed = True
                            done_reason = event.get("done_reason")
                if not completed:
                    raise RuntimeError(
                        "Ollama afbrød svaret, før det var færdigt."
                    )
                break
            except RuntimeError as error:
                if (
                    attempt == 0
                    and not segment_parts
                    and "repeat limit" in str(error).lower()
                ):
                    options["temperature"] = 0.2
                    options["repeat_penalty"] = 1.25
                    options["num_predict"] = 512
                    payload["options"] = options
                    continue
                raise
        answer_parts.extend(segment_parts)
        if done_reason != "length":
            return
    raise RuntimeError(
        "Ollama kunne ikke færdiggøre svaret efter flere fortsættelser. Prøv igen."
    )


def friendly_error(error: Exception) -> str:
    if isinstance(error, requests.ConnectionError):
        return "Jeg kan ikke få forbindelse til Ollama. Start Ollama-programmet (eller kør ollama serve), og prøv igen."
    if isinstance(error, requests.Timeout):
        return "Ollama svarede ikke i tide. Prøv igen om et øjeblik."
    if isinstance(error, requests.HTTPError):
        try:
            detail = error.response.json().get("error", "") if error.response is not None else ""
        except (ValueError, AttributeError):
            detail = error.response.text[:200] if error.response is not None else ""
        return f"Ollama returnerede en fejl{f': {detail}' if detail else '.'}"
    return f"Noget gik galt: {error}"


def empty_profile() -> dict[str, Any]:
    return {
        "uddannelse": "STX", "klassetrin": "1.g",
        "interesser": {area: 3 for area in AREAS}, "topinteresser": [],
        "undgaa": [], "undgaa_andet": "", "bedste_fag": [], "mindst_fag": [],
        "staerkeste_fag": [], "universitetsfag_svar": "Ved ikke", "universitetsfag": "",
        "evner": {item: 3 for item in ABILITIES}, "arbejdsform": 3, "teori_praksis": 3,
        "forudsigelighed": 3, "kreativitet_vigtigt": 3, "mennesker_vigtigt": 3,
        "teknologi_vigtigt": 3, "data_vigtigt": 3, "jobomraader": [],
        "jobvaerdier": {item: 3 for item in WORK_VALUES}, "uddannelser_tanker_svar": "Ved ikke",
        "uddannelser_tanker": "", "byer": "", "geografi_vigtigt": 3,
        "laengde": "Ved ikke", "jobmuligheder_vigtigt": 3, "arbejdsdag": [],
        "undgaa_job": "", "andet": "",
    }


def profile_context() -> str:
    return json.dumps(st.session_state.profile, ensure_ascii=False, indent=2)


def questionnaire_context_for_chat(profile: Mapping[str, Any]) -> str:
    """Summarize the student's explicit answers without sending neutral defaults."""
    lines = [
        "Elevens konkrete svar fra spørgeskemaet (brug dem aktivt i vejledningen):"
    ]

    def add_value(label: str, value: Any) -> None:
        if isinstance(value, (list, tuple, set)):
            items = [str(item).strip() for item in value if str(item).strip()]
            if items:
                lines.append(f"- {label}: {', '.join(items[:8])}")
        elif value is not None and str(value).strip() not in {"", "Ved ikke"}:
            text = str(value).strip()
            lines.append(f"- {label}: {text[:500].rstrip()}")

    def add_ratings(label: str, values: Any) -> None:
        if not isinstance(values, Mapping):
            return
        high, low = [], []
        for item, value in values.items():
            try:
                score = float(value)
            except (TypeError, ValueError):
                continue
            if score >= 4:
                high.append(str(item))
            elif score <= 2:
                low.append(str(item))
        if high:
            add_value(f"{label} (vurderet højt)", high)
        if low:
            add_value(f"{label} (vurderet lavt)", low)

    add_value("Gymnasial uddannelse og klassetrin", [
        profile.get("uddannelse", ""),
        profile.get("klassetrin", ""),
    ])
    interests = profile.get("topinteresser") or [
        name
        for name, score in sorted(
            (profile.get("interesser") or {}).items(),
            key=lambda item: item[1],
            reverse=True,
        )
        if isinstance(score, (int, float)) and score >= 4
    ][:5]
    add_value("Interesser", interests)
    add_value("Bedste fag", profile.get("bedste_fag"))
    add_value("Faglige styrker", profile.get("staerkeste_fag"))
    add_value("Fag, eleven helst undgår", profile.get("mindst_fag"))
    add_value("Faglige fravalg", profile.get("undgaa"))
    if profile.get("universitetsfag_svar") not in (None, "", "Ved ikke"):
        add_value(
            "Ønske om at læse universitetsfag videre",
            profile.get("universitetsfag_svar"),
        )
    add_value("Uddannelsesønske", profile.get("uddannelser_tanker"))
    if profile.get("uddannelser_tanker_svar") not in (None, "", "Ved ikke"):
        add_value(
            "Har en bestemt uddannelse i tankerne",
            profile.get("uddannelser_tanker_svar"),
        )
    add_value("Fag, eleven overvejer at læse videre", profile.get("universitetsfag"))
    add_ratings("Evner", profile.get("evner"))
    add_ratings("Det, eleven vægter i et arbejde", profile.get("jobvaerdier"))
    for key, label in (
        ("jobomraader", "Jobområder"),
        ("arbejdsdag", "Ønskede arbejdsopgaver"),
    ):
        add_value(label, profile.get(key))
    for key, label in (
        ("undgaa_andet", "Andre faglige fravalg"),
        ("undgaa_job", "Jobområder eller opgaver, eleven vil undgå"),
        ("byer", "Ønsket by eller uddannelsessted"),
        ("andet", "Andre ønsker eller oplysninger"),
    ):
        add_value(label, profile.get(key))
    for key, low_label, high_label in (
        (
            "arbejdsform",
            "Foretrækker selvstændigt arbejde",
            "Foretrækker samarbejde",
        ),
        (
            "teori_praksis",
            "Foretrækker teoretisk fordybelse",
            "Foretrækker praktisk læring",
        ),
    ):
        try:
            score = float(profile.get(key))
        except (TypeError, ValueError):
            continue
        if score <= 2:
            add_value("Arbejdsform", low_label)
        elif score >= 4:
            add_value("Arbejdsform", high_label)
    for key, label in (
        ("teknologi_vigtigt", "Betydning af teknologi"),
        ("data_vigtigt", "Betydning af data og analyse"),
        ("mennesker_vigtigt", "Betydning af menneskekontakt"),
        ("kreativitet_vigtigt", "Betydning af kreativitet"),
        ("geografi_vigtigt", "Betydning af geografi"),
        ("jobmuligheder_vigtigt", "Betydning af jobmuligheder"),
    ):
        try:
            score = float(profile.get(key))
        except (TypeError, ValueError):
            continue
        if score >= 4:
            add_value(label, "Høj")
        elif score <= 2:
            add_value(label, "Lav")
    add_value("Ønsket uddannelseslængde", profile.get("laengde"))

    return "\n".join(lines)


def profile_level(value: int) -> str:
    if value >= 4:
        return "Høj"
    if value <= 2:
        return "Lav"
    return "Middel"


def profile_summary_text(profile: dict[str, Any]) -> str:
    interests = profile["topinteresser"] or [
        area
        for area, score in sorted(
            profile["interesser"].items(), key=lambda item: item[1], reverse=True
        )
        if score >= 4
    ][:3]
    strengths = profile["staerkeste_fag"][:3]
    preferences = []
    if profile["arbejdsform"] <= 2:
        preferences.append("selvstændigt arbejde")
    elif profile["arbejdsform"] >= 4:
        preferences.append("samarbejde med andre")
    if profile["teori_praksis"] >= 4:
        preferences.append("praktisk læring")
    elif profile["teori_praksis"] <= 2:
        preferences.append("teoretisk fordybelse")
    if profile["teknologi_vigtigt"] >= 4:
        preferences.append("teknologi")
    if profile["mennesker_vigtigt"] >= 4:
        preferences.append("menneskekontakt")
    if profile["kreativitet_vigtigt"] >= 4:
        preferences.append("kreativitet")

    observations = []
    if interests:
        observations.append(f"du er nysgerrig på {', '.join(interests[:3])}")
    if strengths:
        observations.append(f"du har fremhævet {', '.join(strengths)} som faglige styrker")
    if preferences:
        observations.append(f"du lægger vægt på {', '.join(preferences[:3])}")
    if not observations:
        return "Du er stadig ved at udforske dine muligheder. Du kan altid redigere dine svar, efterhånden som du bliver klogere på, hvad der passer til dig."
    return "Ud fra dine svar ser det især ud til, at " + " og ".join(observations) + "."


def render_summary_item(label: str, value: str) -> None:
    st.markdown(
        f'<div class="summary-item"><span>{escape(label)}</span><small>{escape(value)}</small></div>',
        unsafe_allow_html=True,
    )


def run_followup_analysis() -> None:
    prompt = (
        "Vurder elevens spørgeskemasvar. Stil kun opfølgende spørgsmål ved uklare, "
        "modstridende eller væsentligt manglende oplysninger. Returnér JSON med format "
        '{"questions":["..."]}. Maksimalt 5 korte, konkrete spørgsmål; returnér en tom liste, '
        "hvis profilen er tilstrækkelig. Profil:\n" + profile_context()
    )
    raw = ollama_chat([{"role": "user", "content": prompt}], json_mode=True)
    data = json.loads(raw)
    if not isinstance(data, dict) or not isinstance(data.get("questions"), list):
        raise ValueError("AI-opfølgningen returnerede ikke en gyldig liste af spørgsmål.")
    questions = data["questions"]
    if any(not isinstance(question, str) for question in questions):
        raise ValueError("AI-opfølgningen returnerede et spørgsmål i et ugyldigt format.")
    st.session_state.followup_questions = [
        question.strip() for question in questions[:5] if question.strip()
    ]
    st.session_state.followup_answers = {q: "" for q in st.session_state.followup_questions}
    st.session_state.followup_index = 0
    st.session_state.followup_step_included = bool(st.session_state.followup_questions)
    st.session_state.stage = "opfølgning" if st.session_state.followup_questions else "gennemgang"


@st.cache_data(show_spinner=False)
def cached_education_profiles():
    return load_education_profiles()


@st.cache_data(show_spinner=False)
def cached_education_search_index() -> tuple[list[str], list[str], list[str]]:
    profiles = cached_education_profiles()
    searchable_fields = (
        "Titel",
        "institution",
        "kommune",
        "region",
        "Educational_Category",
        *(f"kompetencerudd_p{rank}" for rank in range(1, 6)),
        *(f"undervisningsform_p{rank}" for rank in range(1, 6)),
    )
    titles, identifiers, searchable_texts = [], [], []
    for _, row in profiles.iterrows():
        titles.append(normalize_text(str(row.get("Titel", ""))))
        identifiers.append(str(row.get("udbud_id", "")).removesuffix(".0"))
        searchable_texts.append(
            normalize_text(
                " ".join(
                    str(_clean_context_value(row.get(field)) or "")
                    for field in searchable_fields
                )
            )
        )
    return titles, identifiers, searchable_texts


def _clean_context_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _clean_context_value(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_clean_context_value(item) for item in value]
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(value, "item"):
        return _clean_context_value(value.item())
    if isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def education_context_for_chat(prompt: str) -> str:
    profiles = cached_education_profiles()
    titles, identifiers, searchable_texts = cached_education_search_index()
    ignored_terms = {
        "alle", "bare", "blive", "blev", "dem", "den", "der", "det",
        "dig", "din", "dine", "disse", "du", "eller", "er", "et", "for",
        "fra", "har", "hvad", "hvilke", "hvordan", "jeg", "kan", "med",
        "mig", "min", "mine", "muligt", "om", "og", "også", "passer",
        "på", "skal", "som", "til", "var", "ved", "vil", "være",
    }
    query_terms = {
        term
        for term in re.findall(r"[a-z0-9æøå]{3,}", normalize_text(prompt))
        if term not in ignored_terms
    }
    matching_rows: list[tuple[int, int]] = []
    if query_terms:
        for position, searchable_text in enumerate(searchable_texts):
            relevance = sum(term in searchable_text for term in query_terms)
            if relevance:
                matching_rows.append((relevance, position))
        matching_rows.sort(
            key=lambda item: (
                -item[0],
                titles[item[1]],
                identifiers[item[1]],
            )
        )

    recommended_ids = set()
    for recommendation in st.session_state.recommendations[:5]:
        offers = recommendation.get("offers", [])
        if not isinstance(offers, list):
            offers = []
        for offer in offers:
            if isinstance(offer, Mapping) and offer.get("udbud_id") is not None:
                recommended_ids.add(str(offer["udbud_id"]).removesuffix(".0"))
        if recommendation.get("udbud_id") is not None:
            recommended_ids.add(
                str(recommendation["udbud_id"]).removesuffix(".0")
            )
    selected_rows: list[pd.Series] = []
    seen_ids = set()
    for _, position in matching_rows[:2]:
        row = profiles.iloc[position]
        selected_rows.append(row)
        seen_ids.add(identifiers[position])
    if recommended_ids and len(selected_rows) < 3:
        for position, row_id in enumerate(identifiers):
            if row_id in recommended_ids and row_id not in seen_ids:
                selected_rows.append(profiles.iloc[position])
                seen_ids.add(row_id)
                if len(selected_rows) == 3:
                    break
    if not selected_rows:
        selected_rows = [
            profiles.iloc[position] for _, position in matching_rows[:3]
        ]

    education_records = []
    metadata_fields = (
        "Titel",
        "Educational_Category",
        "displaydocclass",
        "institution",
        "kommune",
        "region",
        "url",
        "udbud_id",
        "profile_origin",
    )
    for row in selected_rows:
        record = {
            field: _clean_context_value(row.get(field))
            for field in metadata_fields
            if _clean_context_value(row.get(field)) is not None
        }
        record["profilområder"] = {
            dimension: _clean_context_value(row.get(dimension))
            for dimension in PROFILE_DIMENSIONS
            if _clean_context_value(row.get(dimension)) is not None
        }
        record["faktiske kompetencebeskrivelser"] = [
            str(_clean_context_value(row.get(f"kompetencerudd_p{rank}")))[:240]
            for rank in range(1, 6)
            if _clean_context_value(row.get(f"kompetencerudd_p{rank}"))
        ][:3]
        record["undervisningsformer"] = [
            str(_clean_context_value(row.get(f"undervisningsform_p{rank}")))[:160]
            for rank in range(1, 6)
            if _clean_context_value(row.get(f"undervisningsform_p{rank}"))
        ][:3]
        education_records.append(record)

    return json.dumps(education_records, ensure_ascii=False, allow_nan=False)


def calculate_matching_results() -> None:
    st.session_state.selected_recommendation = None
    st.session_state.pop("detail_return_page", None)
    st.session_state.recommendations = rank_questionnaire_profile(
        st.session_state.profile,
        cached_education_profiles(),
    )
    st.session_state.matching_calculated = True
    st.session_state.matching_rules_version = MATCHING_RULES_VERSION
    st.session_state.stage = "anbefalinger"


def recommendation_title(item: dict[str, Any]) -> str:
    return str(item.get("Titel") or "Uddannelse")


def recommendation_institution(item: dict[str, Any]) -> str:
    return str(item.get("institution") or "Institution ikke angivet")


def render_advisor_chat() -> None:
    """Vis profilbaseret chat på både gennemgangs- og anbefalingssiden."""
    st.subheader("Spørg din studievejleder")
    st.caption("Assistenten bruger din profil, dine afklarende svar og eventuelle uddannelsesforslag som kontekst.")
    if not st.session_state.chat_messages:
        st.session_state.chat_messages.append({
            "role": "assistant",
            "content": (
                "Tak, jeg har gemt dine svar. Jeg bruger dem til at hjælpe dig med at udforske "
                "uddannelser, der kan passe til dine interesser og ønsker. Du kan spørge mig "
                "om dine fag, arbejdsformer eller mulige uddannelsesvalg – eller fortsætte "
                "til anbefalingerne, når du er klar."
            ),
        })
    for message in st.session_state.chat_messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    prompt = st.chat_input(
        "Spørg om interesser, fag eller uddannelsesvalg …",
        disabled=not st.session_state.model_ready,
        key="advisor_chat_input",
    )
    pending_question = st.session_state.pop("pending_chat_question", None)
    if not prompt:
        prompt = pending_question
    if prompt:
        st.session_state.chat_messages.append({"role": "user", "content": prompt})
        with st.chat_message("assistant"):
            try:
                recommendation_context = [
                    {
                        "Titel": recommendation_title(item),
                        "institution": recommendation_institution(item),
                        "matchscore": item.get("match_score"),
                        "stærkeste_matchbidrag": [
                            {
                                "område": match.get("dimension"),
                                "lighed": match.get("similarity"),
                            }
                            for match in item.get(
                                "strongest_positive_dimensions", []
                            )[:3]
                        ],
                        "udbud": [
                            {
                                field: offer.get(field)
                                for field in (
                                    "institution",
                                    "kommune",
                                    "region",
                                    "url",
                                )
                                if offer.get(field)
                            }
                            for offer in item.get("offers", [])[:5]
                        ],
                    }
                    for item in st.session_state.recommendations[:3]
                ]
                messages = [
                    {
                        "role": "system",
                        "content": (
                            "Svar på elevens konkrete spørgsmål på dansk ud fra "
                            "elevens konkrete spørgeskemasvar, opfølgende svar, "
                            "forslagene og relevante "
                            "uddannelsesdata. Brug kun de medsendte fakta om konkrete "
                            "uddannelser. Nævn relevante svar fra spørgeskemaet, "
                            "og forklar konkret, hvordan de hænger sammen med "
                            "forslagene; behandl ikke neutrale svar som præferencer. "
                            "Skriv korrekt og naturligt dansk med korrekt stavning "
                            "og tegnsætning, og læs svaret igennem for sproglige fejl. "
                            "Sig tydeligt, hvis en oplysning mangler. "
                            "Profilområder i arbejdsbogen er Studiekompas-estimater "
                            "baseret på UFSN-data, ikke officielle vurderinger. "
                            "Opfind aldrig adgangskrav, varighed, fagindhold eller "
                            "andre uddannelsesfakta."
                        ),
                    },
                    {
                        "role": "system",
                        "content": (
                            "Elevens spørgeskemasvar:\n"
                            + questionnaire_context_for_chat(
                                st.session_state.profile
                            )
                            + "\nAfklarende svar:\n"
                            + json.dumps(
                                st.session_state.followup_answers,
                                ensure_ascii=False,
                            )
                        ),
                    },
                    {
                        "role": "system",
                        "content": (
                            "Aktuelle forslag:\n"
                            + json.dumps(
                                recommendation_context,
                                ensure_ascii=False,
                            )
                            + "\nRelevante uddannelsesdata fra arbejdsbogen "
                            "(op til 3 rækker; tom liste betyder, at ingen kunne "
                            "findes):\n"
                            + education_context_for_chat(prompt)
                        ),
                    },
                ]
                messages.extend(st.session_state.chat_messages)
                answer = st.write_stream(stream_chat(messages))
                st.session_state.chat_messages.append({"role": "assistant", "content": answer or ""})
            except (OSError, requests.RequestException, RuntimeError, ValueError) as error:
                st.error(friendly_error(error))


ACCOUNT_STATE_KEYS = (
    "profile",
    "profile_completed",
    "stage",
    "profile_step",
    "selected_page",
    "followup_questions",
    "followup_index",
    "followup_step_included",
    "followup_answers",
    "followup_analysis_pending",
    "recommendations",
    "matching_error",
    "matching_calculated",
    "matching_rules_version",
    "previous_recommendations",
    "selected_recommendation",
    "detail_return_page",
    "favorites",
    "chat_messages",
)
ACCOUNT_STATE_DEFAULTS: dict[str, Any] = {
    "profile": empty_profile(),
    "profile_completed": False,
    "stage": "spørgeskema",
    "profile_step": 1,
    "selected_page": "Start",
    "followup_questions": [],
    "followup_index": 0,
    "followup_step_included": False,
    "followup_answers": {},
    "followup_analysis_pending": False,
    "recommendations": [],
    "matching_error": None,
    "matching_calculated": False,
    "matching_rules_version": 0,
    "previous_recommendations": [],
    "selected_recommendation": None,
    "detail_return_page": None,
    "favorites": [],
    "chat_messages": [],
}


def restore_account_state(username: str) -> None:
    saved_state = load_account_state(username)
    for key in list(st.session_state.keys()):
        if key.startswith("q_") or key in ACCOUNT_STATE_KEYS or key in {
            "model_ready", "pending_page", "pending_chat_question",
        }:
            st.session_state.pop(key, None)
    for key, default in ACCOUNT_STATE_DEFAULTS.items():
        st.session_state[key] = saved_state.get(key, deepcopy(default))
    st.session_state.model_ready = False
    st.session_state.pop("ai_load_attempted", None)
    st.session_state.pop("ai_load_error", None)
    st.session_state.active_account = username


def persist_account_state() -> bool:
    username = st.session_state.get("active_account")
    if not username:
        return True
    try:
        state_json = json.dumps(
            {key: st.session_state.get(key) for key in ACCOUNT_STATE_KEYS},
            ensure_ascii=False,
        )
        save_account_state(username, state_json)
    except (OSError, sqlite3.Error, TypeError, ValueError) as error:
        st.error(f"Dine ændringer kunne ikke gemmes: {error}")
        return False
    return True


def save_and_rerun() -> None:
    if persist_account_state():
        st.rerun()


def reset_profile(*, delete_all_saved_data: bool = False) -> None:
    if delete_all_saved_data:
        try:
            delete_account_state(st.session_state.active_account)
        except (OSError, sqlite3.Error) as error:
            st.error(f"De gemte data kunne ikke slettes: {error}")
            return

    for key, default in ACCOUNT_STATE_DEFAULTS.items():
        if key in {"favorites"} and not delete_all_saved_data:
            continue
        st.session_state[key] = deepcopy(default)
    for key in list(st.session_state.keys()):
        if key.startswith("q_"):
            st.session_state.pop(key, None)
    st.session_state.selected_recommendation = None
    st.session_state.pop("detail_return_page", None)
    st.session_state.pop("pending_chat_question", None)
    st.session_state.model_ready = False
    save_and_rerun()


def start_guest_session(*, reset: bool = False) -> None:
    if reset:
        for key in list(st.session_state.keys()):
            if key.startswith("q_") or key in set(ACCOUNT_STATE_KEYS) - {"selected_page"}:
                st.session_state.pop(key, None)
        for key, default in ACCOUNT_STATE_DEFAULTS.items():
            if key != "selected_page":
                st.session_state[key] = deepcopy(default)
        st.session_state.selected_page = "Start"
        st.session_state.model_ready = False
        st.session_state.pop("ai_load_attempted", None)
        st.session_state.pop("ai_load_error", None)
    st.session_state.guest_mode = True


if "pending_account_login" in st.session_state:
    account = st.session_state.pop("pending_account_login")
    restore_account_state(account)

for key, default in ACCOUNT_STATE_DEFAULTS.items():
    if key not in st.session_state:
        st.session_state[key] = deepcopy(default)
if "model_ready" not in st.session_state:
    st.session_state.model_ready = False
if "pending_page" in st.session_state:
    st.session_state.selected_page = st.session_state.pop("pending_page")


with st.sidebar:
    st.subheader("Indstillinger")
    if st.session_state.get("active_account"):
        st.caption(f"Logget ind som **{st.session_state.active_account}**")
        if st.button("Log ud", use_container_width=True):
            if persist_account_state():
                st.session_state.pop("active_account", None)
                start_guest_session(reset=True)
                st.session_state.pop("ai_load_attempted", None)
                st.session_state.pop("ai_load_error", None)
                save_and_rerun()
    else:
        st.caption("Du bruger appen uden en konto.")
    st.radio("Udseende", ["Lys", "Mørk"], horizontal=True, key="theme")
    if st.session_state.model_ready:
        st.success("AI-opfølgning og chat er klar")
    elif (
        st.session_state.profile_completed
        and st.session_state.selected_page in {"Gennemgang", "Anbefalinger"}
        and not st.session_state.get("ai_load_attempted", False)
    ):
        st.session_state.ai_load_attempted = True
        try:
            with st.status("Gør AI klar …", expanded=True) as load_status:
                models = ollama_models()
                progress = st.progress(0, text="Kontrollerer model …")
                if model_is_installed(models):
                    progress.progress(1, text="Modellen er klar")
                else:
                    load_status.write(
                        f"Henter {MODEL}. Første gang kan det tage et par minutter."
                    )
                    pull_model(load_status, progress)
                    progress.progress(1, text="Modellen er hentet")
                load_status.update(label="Indlæser modellen …", state="running")
                warm_up_model()
                st.session_state.model_ready = True
                if st.session_state.followup_analysis_pending:
                    try:
                        with st.spinner("AI'en ser efter uklare eller modstridende svar …"):
                            run_followup_analysis()
                    except (
                        requests.RequestException,
                        RuntimeError,
                        ValueError,
                        json.JSONDecodeError,
                    ) as error:
                        st.warning(
                            "AI-opfølgningen kunne ikke gennemføres. "
                            f"Du kan fortsætte uden den. Detalje: {friendly_error(error)}"
                        )
                    st.session_state.followup_analysis_pending = False
                load_status.update(
                    label="AI'en er klar", state="complete", expanded=False
                )
            persist_account_state()
        except (requests.RequestException, RuntimeError, ValueError) as error:
            st.session_state.ai_load_error = friendly_error(error)
            st.warning(
                f"{st.session_state.ai_load_error} Du kan fortsætte uden AI."
            )
    else:
        st.info(
            "AI indlæses automatisk, når du åbner dit overblik eller dine forslag. "
            "Uddannelsesmatch virker også uden AI."
        )
    if st.button("Start spørgeskema forfra", use_container_width=True):
        reset_profile()
    with st.expander("Slet alle gemte data"):
        st.caption("Dette sletter din profil, dine forslag, favoritter og chat fra kontoen.")
        confirm_delete = st.checkbox(
            "Jeg forstår, at mine gemte data bliver slettet.",
            key="confirm_delete_saved_data",
        )
        if st.button(
            "Slet mine data",
            disabled=not confirm_delete,
            use_container_width=True,
        ):
            reset_profile(delete_all_saved_data=True)


profile = st.session_state.profile

with st.container(key="top_navigation"):
    nav_brand, nav_links = st.columns([1.45, 5.5], vertical_alignment="center")
    with nav_brand:
        st.markdown(
            '<div class="top-navigation"><span class="top-navigation-mark">✦</span>'
            "<strong>Studiekompas</strong></div>",
            unsafe_allow_html=True,
        )
    with nav_links:
        selected_page = st.radio(
            "Navigation",
            ["Start", "Spørgeskema", "Gennemgang", "Anbefalinger", "Favoritter"],
            format_func=lambda page: {
                "Start": "Start",
                "Spørgeskema": "Min profil",
                "Gennemgang": "Overblik",
                "Anbefalinger": "Forslag",
                "Favoritter": "Favoritter",
            }[page],
            horizontal=True,
            label_visibility="collapsed",
            key="selected_page",
        )

scroll_recommendations_to_top = (
    selected_page == "Anbefalinger"
    and selected_page != st.session_state.get("last_rendered_page", selected_page)
)
if selected_page != st.session_state.get("last_rendered_page", selected_page):
    st.session_state.last_rendered_page = selected_page
if scroll_recommendations_to_top:
    components.html(
        """
        <script>
            const parentDocument = window.parent.document;
            const scrollToFirstProposal = () => {
                const scrollContainer = window.parent.document.querySelector(
                    '[data-testid="stAppScrollToBottomContainer"], [data-testid="stMain"]'
                );
                if (scrollContainer) {
                    const firstProposal = parentDocument.querySelector(
                        "#first-recommendation"
                    );
                    const top = firstProposal
                        ? scrollContainer.scrollTop
                            + firstProposal.getBoundingClientRect().top
                            - scrollContainer.getBoundingClientRect().top
                        : 0;
                    scrollContainer.scrollTop = top;
                }
                return Boolean(scrollContainer && parentDocument.querySelector(
                    "#first-recommendation"
                ));
            };
            scrollToFirstProposal();
            window.parent.requestAnimationFrame(scrollToFirstProposal);
            window.setTimeout(scrollToFirstProposal, 100);
            window.setTimeout(scrollToFirstProposal, 300);
            window.setTimeout(scrollToFirstProposal, 700);
        </script>
        """,
        height=0,
    )
if (
    selected_page == "Anbefalinger"
    and st.session_state.matching_calculated
    and st.session_state.matching_rules_version != MATCHING_RULES_VERSION
):
    try:
        with st.spinner("Opdaterer dine forslag efter de nyeste ønsker …"):
            calculate_matching_results()
        persist_account_state()
    except (OSError, ValueError, TypeError, KeyError, ImportError) as error:
        st.session_state.recommendations = []
        st.session_state.matching_calculated = False
        st.session_state.matching_error = str(error)
        persist_account_state()

if selected_page != "Start":
    has_followup_step = (
        st.session_state.followup_step_included
        or bool(st.session_state.followup_questions)
    )
    flow_labels = ["Om dig", "Dine fag", "Interesser", "Arbejdsstil", "Din fremtid"]
    if has_followup_step:
        flow_labels.append("AI-opfølgning")
    flow_labels.extend(["Dit overblik", "Forslag"])
    if selected_page == "Spørgeskema":
        current_flow_step = min(max(int(st.session_state.profile_step), 1), 5)
    else:
        if selected_page == "Gennemgang" and st.session_state.followup_questions:
            current_flow_step = 6
        elif selected_page == "Gennemgang":
            current_flow_step = len(flow_labels) - 1
        else:
            current_flow_step = len(flow_labels)
    st.markdown(
        f"""
        <div class="flow-label">
            <span>DIT FORLØB</span>
            <strong>{current_flow_step} af {len(flow_labels)} · {flow_labels[current_flow_step - 1]}</strong>
        </div>
        <div class="flow-track" role="progressbar" aria-label="Trin i dit forløb"
             aria-valuemin="1" aria-valuemax="{len(flow_labels)}" aria-valuenow="{current_flow_step}">
            {''.join(f'<span class="{"is-complete" if i < current_flow_step - 1 else "is-active" if i == current_flow_step - 1 else ""}"></span>' for i in range(len(flow_labels)))}
        </div>
        """,
        unsafe_allow_html=True,
    )

if selected_page == "Start":
    if st.session_state.profile_completed:
        welcome_title = "Velkommen tilbage til dit studiekompas"
        welcome_copy = (
            "Din profil og dine gemte forslag er her stadig. Du kan ændre enkelte svar "
            "når som helst eller fortsætte, hvor du slap."
        )
        start_button_label = "Rediger min profil →"
    elif not st.session_state.get("active_account"):
        welcome_title = "Find din vej efter gymnasiet"
        welcome_copy = (
            "Du behøver ikke vide præcis, hvad du vil endnu. Studiekompas hjælper dig med "
            "at udforske uddannelser, der passer til dine interesser, faglige styrker og "
            "ønsker til fremtiden."
        )
        start_button_label = "Fortsæt som gæst →"
    else:
        welcome_title = "Find din vej efter gymnasiet"
        welcome_copy = (
            "Du behøver ikke vide præcis, hvad du vil endnu. Studiekompas hjælper dig med "
            "at udforske uddannelser, der passer til dine interesser, faglige styrker og "
            "ønsker til fremtiden."
        )
        start_button_label = "Kom i gang →"
    st.markdown(
        f"""
        <section class="landing-page">
            <span class="landing-kicker">ET STUDIEKOMPAS TIL DIT NÆSTE KAPITEL</span>
            <h1>{escape(welcome_title)}</h1>
            <p>{escape(welcome_copy)}</p>
            <p>Du kan få uddannelsesmatch uden AI. AI-opfølgning og chat er valgfri.</p>
        </section>
        """,
        unsafe_allow_html=True,
    )
    start_left, start_center, start_right = st.columns([2, 3, 2])
    with start_center:
        if st.button(start_button_label, type="primary", use_container_width=True):
            if not st.session_state.get("active_account"):
                start_guest_session()
            st.session_state.profile_step = 1
            st.session_state.pending_page = "Spørgeskema"
            save_and_rerun()
    st.markdown(
        """
        <div class="landing-points">
            <span>✓ Lær dine interesser bedre at kende</span>
            <span>✓ Udforsk uddannelser, der passer til dig</span>
            <span>✓ Forstå, hvorfor de bliver foreslået</span>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if not st.session_state.get("active_account"):
        with st.expander("Log ind eller opret konto"):
            login_tab, create_tab = st.tabs(["Log ind", "Opret konto"])
            with login_tab:
                with st.form("login_form"):
                    login_username = st.text_input("Brugernavn", key="login_username")
                    login_password = st.text_input(
                        "Adgangskode", type="password", key="login_password"
                    )
                    login_submitted = st.form_submit_button(
                        "Log ind", type="primary", use_container_width=True
                    )
                if login_submitted:
                    try:
                        account = authenticate_account(login_username, login_password)
                        if account is None:
                            st.error("Brugernavn eller adgangskode er forkert.")
                        else:
                            st.session_state.pending_account_login = account
                            st.rerun()
                    except (OSError, sqlite3.Error, ValueError) as error:
                        st.error(f"Kunne ikke indlæse din konto: {error}")
            with create_tab:
                st.caption(
                    "Brugernavn: 3–32 tegn med engelske bogstaver, tal, punktum, "
                    "bindestreg eller understreg. Adgangskode: 8–128 tegn."
                )
                with st.form("create_account_form"):
                    new_username = st.text_input("Vælg brugernavn", key="new_username")
                    new_password = st.text_input(
                        "Vælg adgangskode", type="password", key="new_password"
                    )
                    confirm_password = st.text_input(
                        "Gentag adgangskode", type="password", key="confirm_password"
                    )
                    account_submitted = st.form_submit_button(
                        "Opret konto", type="primary", use_container_width=True
                    )
                if account_submitted:
                    if new_password != confirm_password:
                        st.error("Adgangskoderne er ikke ens.")
                    else:
                        try:
                            account = create_account(new_username, new_password)
                            st.session_state.pending_account_login = account
                            st.rerun()
                        except AccountError as error:
                            st.error(str(error))
                        except (OSError, sqlite3.Error, ValueError) as error:
                            st.error(f"Kontoen kunne ikke oprettes: {error}")

elif selected_page == "Spørgeskema":
    form_steps = [
        ("Om dig", "Fortæl lidt om dig", "Vi starter med nogle få spørgsmål, så Studiekompas kan forstå din situation."),
        ("Dine fag", "Dine fag", "Hvilke fag kan du bedst lide, og hvor føler du dig stærk?"),
        ("Interesser", "Hvad interesserer dig?", "Vælg de områder, du er nysgerrig på. Du kan altid ændre dine svar senere."),
        ("Arbejdsstil", "Hvordan vil du helst arbejde?", "Der er ingen rigtige svar — tænk på, hvad der passer bedst til dig."),
        ("Din fremtid", "Hvad forestiller du dig efter gymnasiet?", "Del kun det, du allerede ved. Det er helt okay stadig at være i tvivl."),
    ]
    step_index = int(st.session_state.profile_step) - 1
    step_name, step_title, step_description = form_steps[step_index]
    st.markdown(
        f'<section class="step-card"><span class="landing-kicker">TRIN {step_index + 1} AF 5 · {step_name.upper()}</span>'
        f'<h2>{step_title}</h2><p>{step_description}</p>'
        f'{"<p>Du redigerer din gemte profil. Gem kun dette trin, når du er færdig.</p>" if st.session_state.profile_completed else ""}'
        '</section>',
        unsafe_allow_html=True,
    )
    form_context = (
        st.form(f"profile_form_{step_index}")
        if step_index != 2
        else nullcontext()
    )
    with form_context:
        step_updates: dict[str, Any] = {}
        if step_index == 0:
            st.subheader("Din gymnasietid")
            c1, c2 = st.columns(2)
            with c1:
                step_updates["uddannelse"] = st.selectbox(
                    "Hvilken gymnasial uddannelse går du på?",
                    ["STX", "HHX", "HTX", "HF", "Andet"],
                    index=["STX", "HHX", "HTX", "HF", "Andet"].index(profile["uddannelse"]),
                    key="q_uddannelse",
                )
            with c2:
                step_updates["klassetrin"] = st.selectbox(
                    "Hvilket klassetrin går du på?",
                    ["1.g", "2.g", "3.g", "Andet"],
                    index=["1.g", "2.g", "3.g", "Andet"].index(profile["klassetrin"]),
                    key="q_klassetrin",
                )
        elif step_index == 1:
            st.subheader("Fag, du holder af")
            step_updates["bedste_fag"] = st.multiselect(
                "Hvilke fag kan du bedst lide? (vælg op til 5)",
                SUBJECTS, default=profile["bedste_fag"], max_selections=5,
                placeholder="Vælg fag …", key="q_best_subjects",
            )
            step_updates["mindst_fag"] = st.multiselect(
                "Hvilke fag synes du er mindst interessante? (vælg op til 5)",
                SUBJECTS, default=profile["mindst_fag"], max_selections=5,
                placeholder="Vælg fag …", key="q_least_subjects",
            )
            step_updates["staerkeste_fag"] = st.multiselect(
                "Hvilke fag føler du dig stærkest i? (vælg op til 5)",
                SUBJECTS, default=profile["staerkeste_fag"], max_selections=5,
                placeholder="Vælg fag …", key="q_strong_subjects",
            )
            with st.expander("Vurdér dine styrker (valgfrit)"):
                st.caption("Vurdér, hvor godt du synes, du klarer dig på hvert område.")
                abilities = {}
                ability_cols = st.columns(2)
                for i, ability in enumerate(ABILITIES):
                    with ability_cols[i % 2]:
                        abilities[ability] = st.slider(
                            ability, 1, 5, int(profile["evner"].get(ability, 3)), key=f"q_ability_{i}"
                        )
                step_updates["evner"] = abilities
            if "evner" not in step_updates:
                step_updates["evner"] = profile["evner"].copy()
            step_updates["universitetsfag_svar"] = st.radio(
                "Er der fag, du gerne vil arbejde videre med?",
                ["Ja", "Nej", "Ved ikke"],
                index=["Ja", "Nej", "Ved ikke"].index(profile["universitetsfag_svar"]),
                horizontal=True, key="q_uni_yes",
            )
            step_updates["universitetsfag"] = st.text_input(
                "Hvilke fag? (valgfrit)", value=profile["universitetsfag"], key="q_uni_subjects"
            )
        elif step_index == 2:
            st.subheader("Vælg det, du er nysgerrig på")
            step_updates["topinteresser"] = st.multiselect(
                "Hvilke områder interesserer dig mest? (vælg op til 3)",
                AREAS, default=profile["topinteresser"], max_selections=3,
                placeholder="Vælg interesser …", key="q_top",
            )
            st.caption("Vurdér dine valgte områder fra 1 (lidt) til 5 (meget).")
            interests = profile["interesser"].copy()
            interest_cols = st.columns(2)
            for i, area in enumerate(step_updates["topinteresser"]):
                with interest_cols[i % 2]:
                    interests[area] = st.slider(
                        area, 1, 5, int(interests.get(area, 3)), key=f"q_interest_{AREAS.index(area)}"
                    )
            step_updates["interesser"] = interests
            with st.expander("Områder, du helst vil undgå (valgfrit)"):
                step_updates["undgaa"] = st.multiselect(
                    "Er der områder, du helst vil undgå?",
                    DISLIKES, default=profile["undgaa"], placeholder="Vælg områder …", key="q_avoid",
                )
                step_updates["undgaa_andet"] = st.text_input(
                    "Andet, du gerne vil undgå?",
                    value=profile["undgaa_andet"], key="q_avoid_other",
                )
        elif step_index == 3:
            st.subheader("Sådan arbejder du bedst")
            step_updates["arbejdsform"] = st.slider(
                "Alene  ←→  Sammen med andre", 1, 5, int(profile["arbejdsform"]), key="q_workstyle"
            )
            step_updates["teori_praksis"] = st.slider(
                "Teoretisk  ←→  Praktisk", 1, 5, int(profile["teori_praksis"]), key="q_theory"
            )
            step_updates["forudsigelighed"] = st.slider(
                "Fast arbejdsdag  ←→  Varieret arbejdsdag", 1, 5,
                int(profile["forudsigelighed"]), key="q_variety",
            )
            st.subheader("Det, der betyder noget for dig")
            value_controls = [
                ("Kreativitet", "kreativitet_vigtigt"),
                ("At arbejde med mennesker", "mennesker_vigtigt"),
                ("At arbejde med teknologi", "teknologi_vigtigt"),
                ("At arbejde med data og information", "data_vigtigt"),
            ]
            value_columns = st.columns(2)
            for i, (label, field) in enumerate(value_controls):
                with value_columns[i % 2]:
                    step_updates[field] = st.slider(
                        f"{label} (1–5)", 1, 5, int(profile[field]), key=f"q_{field}"
                    )
        else:
            st.subheader("Mulige retninger")
            step_updates["jobomraader"] = st.multiselect(
                "Hvilke områder kunne du forestille dig at arbejde med?",
                JOB_FIELDS, default=profile["jobomraader"],
                placeholder="Vælg arbejdsområder …", key="q_jobareas",
            )
            step_updates["uddannelser_tanker_svar"] = st.radio(
                "Har du allerede nogle uddannelser i tankerne?",
                ["Ja", "Nej", "Ved ikke"],
                index=["Ja", "Nej", "Ved ikke"].index(profile["uddannelser_tanker_svar"]),
                horizontal=True, key="q_study_yes",
            )
            step_updates["uddannelser_tanker"] = st.text_input(
                "Hvilke uddannelser? (valgfrit)",
                value=profile["uddannelser_tanker"], key="q_study_ideas",
            )
            with st.expander("Dine praktiske ønsker (valgfrit)"):
                step_updates["byer"] = st.text_input(
                    "Har du byer eller uddannelsessteder i tankerne?",
                    value=profile["byer"], key="q_cities",
                )
                step_updates["geografi_vigtigt"] = st.slider(
                    "Hvor vigtigt er det, hvor i Danmark du studerer? (1–5)",
                    1, 5, int(profile["geografi_vigtigt"]), key="q_geo",
                )
                step_updates["laengde"] = st.radio(
                    "Hvor lang må uddannelsen gerne være?",
                    ["Åben for alle længder", "Helst kortere", "Helst længere", "Ved ikke"],
                    index=["Åben for alle længder", "Helst kortere", "Helst længere", "Ved ikke"].index(profile["laengde"]),
                    horizontal=True, key="q_length",
                )
                step_updates["jobmuligheder_vigtigt"] = st.slider(
                    "Hvor vigtigt er det, at uddannelsen fører til bestemte jobs? (1–5)",
                    1, 5, int(profile["jobmuligheder_vigtigt"]), key="q_job_importance",
                )
                step_updates["arbejdsdag"] = st.multiselect(
                    "Hvad ville du helst lave på en typisk arbejdsdag? (vælg op til 3)",
                    WORKDAY, default=profile["arbejdsdag"], max_selections=3,
                    placeholder="Vælg aktiviteter …", key="q_workday",
                )
            with st.expander("Hvad betyder mest i et fremtidigt arbejde?"):
                st.caption("1 = mindre vigtigt, 5 = meget vigtigt.")
                job_values = {}
                value_cols = st.columns(2)
                for i, value in enumerate(WORK_VALUES):
                    with value_cols[i % 2]:
                        job_values[value] = st.slider(
                            value, 1, 5, int(profile["jobvaerdier"].get(value, 3)), key=f"q_jobvalue_{i}"
                        )
                step_updates["jobvaerdier"] = job_values
            if "jobvaerdier" not in step_updates:
                step_updates["jobvaerdier"] = profile["jobvaerdier"].copy()
            with st.expander("Hensyn og andet (valgfrit)"):
                step_updates["undgaa_job"] = st.text_area(
                    "Er der noget, du helst vil undgå i et fremtidigt arbejde?",
                    value=profile["undgaa_job"], key="q_avoid_job",
                )
                step_updates["andet"] = st.text_area(
                    "Er der andet, du gerne vil have, at vi tager højde for?",
                    value=profile["andet"], key="q_other",
                )

        back_label = "← Forside" if step_index == 0 else "← Tilbage"
        is_editing_profile = st.session_state.profile_completed
        continue_label = (
            "Næste trin →" if step_index < 4 else "Til overblik →"
        ) if is_editing_profile else (
            "Se mit overblik →" if step_index == 4 else "Fortsæt →"
        )
        action_columns = st.columns([1, 1, 1] if is_editing_profile else [1, 2])
        with action_columns[0]:
            if step_index == 2:
                go_back = st.button(back_label, key="previous_profile_step")
            else:
                go_back = st.form_submit_button(back_label, use_container_width=True)
        with action_columns[1]:
            if step_index == 2:
                submitted = st.button(
                    continue_label,
                    type="primary",
                    use_container_width=True,
                    key="continue_interest_step",
                )
            else:
                submitted = st.form_submit_button(
                    continue_label,
                    type="primary",
                    use_container_width=True,
                )
        save_changes = False
        if is_editing_profile:
            with action_columns[2]:
                if step_index == 2:
                    save_changes = st.button(
                        "Gem ændringer",
                        use_container_width=True,
                        key="save_interest_changes",
                    )
                else:
                    save_changes = st.form_submit_button(
                        "Gem ændringer", use_container_width=True
                    )
    if go_back:
        st.session_state.profile.update(step_updates)
        if step_index > 0:
            st.session_state.profile_step -= 1
        else:
            st.session_state.pending_page = "Start"
        save_and_rerun()
    elif submitted or save_changes:
        st.session_state.profile.update(step_updates)
        if st.session_state.profile_completed:
            if submitted and step_index < 4:
                st.session_state.profile_step += 1
                save_and_rerun()
            else:
                refresh_recommendations = bool(
                    st.session_state.matching_calculated
                    or st.session_state.recommendations
                )
                if st.session_state.recommendations:
                    st.session_state.previous_recommendations = (
                        st.session_state.recommendations.copy()
                    )
                st.session_state.recommendations = []
                st.session_state.matching_error = None
                st.session_state.matching_calculated = False
                st.session_state.selected_recommendation = None
                st.session_state.pop("detail_return_page", None)
                st.session_state.chat_messages = []
                st.session_state.followup_questions = []
                st.session_state.followup_answers = {}
                st.session_state.followup_index = 0
                st.session_state.followup_step_included = False
                st.session_state.followup_analysis_pending = False
                st.session_state.stage = "gennemgang"
                st.session_state.profile_step = 1
                st.session_state.pending_page = "Gennemgang"
                if refresh_recommendations:
                    try:
                        with st.spinner(
                            "Opdaterer forslag ud fra dine ændringer …"
                        ):
                            calculate_matching_results()
                        st.session_state.pending_page = "Anbefalinger"
                    except (
                        OSError,
                        ValueError,
                        TypeError,
                        KeyError,
                        ImportError,
                    ) as error:
                        st.session_state.matching_error = str(error)
                        st.session_state.pending_page = "Anbefalinger"
                save_and_rerun()
        elif step_index < 4:
            st.session_state.profile_step += 1
            save_and_rerun()
        else:
            st.session_state.profile_completed = True
            if st.session_state.recommendations:
                st.session_state.previous_recommendations = st.session_state.recommendations.copy()
            st.session_state.recommendations = []
            st.session_state.selected_recommendation = None
            st.session_state.pop("detail_return_page", None)
            st.session_state.matching_error = None
            st.session_state.matching_calculated = False
            st.session_state.chat_messages = []
            st.session_state.followup_questions = []
            st.session_state.followup_answers = {}
            st.session_state.followup_index = 0
            st.session_state.followup_step_included = False
            if st.session_state.model_ready:
                st.session_state.followup_analysis_pending = False
                try:
                    with st.spinner("AI'en ser efter uklare eller modstridende svar …"):
                        run_followup_analysis()
                except (requests.RequestException, RuntimeError, ValueError, json.JSONDecodeError) as error:
                    st.session_state.stage = "gennemgang"
                    st.warning(
                        "Din profil er gemt, men AI-opfølgningen kunne ikke gennemføres. "
                        "Du kan stadig fortsætte til uddannelsesmatch."
                    )
            else:
                st.session_state.stage = "gennemgang"
                st.session_state.followup_analysis_pending = True
            st.session_state.profile_step = 1
            st.session_state.pending_page = "Gennemgang"
            save_and_rerun()
elif selected_page == "Gennemgang":
    if st.session_state.followup_questions:
        st.header("Jeg vil lige lære dig lidt bedre at kende")
        st.caption(
            "Dine svar bruges som kontekst til AI-chatten, men indgår ikke i Matching v3-score eller rangering."
        )
        followup_index = min(
            int(st.session_state.followup_index),
            len(st.session_state.followup_questions) - 1,
        )
        followup_question = st.session_state.followup_questions[followup_index]
        st.markdown(
            f'<section class="step-card"><h3>Jeg vil lige lære dig lidt bedre at kende</h3>'
            f'<p>Spørgsmål {followup_index + 1} af {len(st.session_state.followup_questions)}</p>'
            f'<strong>{followup_question}</strong></section>',
            unsafe_allow_html=True,
        )
        with st.form("followup_form"):
            answer = st.text_area(
                "Dit svar",
                value=st.session_state.followup_answers.get(followup_question, ""),
                placeholder="Skriv dit svar her …",
                key=f"followup_answer_{followup_index}",
                label_visibility="collapsed",
            )
            answer_column, skip_column = st.columns([2, 1])
            with answer_column:
                save_answer = st.form_submit_button(
                    "Gem svar →", type="primary", use_container_width=True
                )
            with skip_column:
                skip_answer = st.form_submit_button(
                    "Spring over", use_container_width=True
                )
            if save_answer or skip_answer:
                if save_answer and not answer.strip():
                    st.warning("Skriv et svar, eller vælg Spring over.")
                else:
                    st.session_state.followup_answers[followup_question] = (
                        answer.strip() if save_answer else ""
                    )
                    if followup_index + 1 >= len(st.session_state.followup_questions):
                        st.session_state.followup_questions = []
                        st.session_state.followup_index = 0
                        st.session_state.stage = "gennemgang"
                    else:
                        st.session_state.followup_index += 1
                    save_and_rerun()
    else:
        st.header("Her er det, jeg har lært om dig")
        st.caption("Et overblik over dine svar — ikke en personlighedstype eller en fastlåst konklusion.")
        if not st.session_state.model_ready:
            st.info(
                "AI-opfølgning blev sprunget over. Du kan stadig fortsætte til "
                "uddannelsesmatch med Matching v3."
            )
        st.markdown(
            f'<div class="profile-insight">{escape(profile_summary_text(profile))}</div>',
            unsafe_allow_html=True,
        )

        interests = profile["topinteresser"] or [
            area
            for area, score in sorted(
                profile["interesser"].items(), key=lambda item: item[1], reverse=True
            )
            if score > 3
        ][:3]
        work_style = [
            ("Selvstændigt arbejde", 6 - profile["arbejdsform"]),
            ("Samarbejde", profile["arbejdsform"]),
            ("Praktisk arbejde", profile["teori_praksis"]),
            ("Variation i hverdagen", 6 - profile["forudsigelighed"]),
            ("Teknologi", profile["teknologi_vigtigt"]),
            ("Kreativitet", profile["kreativitet_vigtigt"]),
            ("Menneskekontakt", profile["mennesker_vigtigt"]),
            ("Data og information", profile["data_vigtigt"]),
        ]
        work_style.sort(key=lambda item: item[1], reverse=True)
        summary_cards = st.columns(3)
        with summary_cards[0]:
            with st.container(border=True):
                st.markdown("#### Dine stærkeste interesser")
                if interests:
                    for interest in interests[:3]:
                        score = int(profile["interesser"].get(interest, 3))
                        render_summary_item(interest, profile_level(score))
                else:
                    st.caption("Du har ikke valgt nogle interesser endnu.")
        with summary_cards[1]:
            with st.container(border=True):
                st.markdown("#### Dine faglige styrker")
                strengths = profile["staerkeste_fag"][:3]
                high_abilities = [
                    (name, score)
                    for name, score in profile["evner"].items()
                    if score >= 4 and name not in strengths
                ]
                if strengths:
                    for strength in strengths:
                        render_summary_item(strength, "Fremhævet af dig")
                for ability, score in high_abilities[: max(0, 3 - len(strengths))]:
                    render_summary_item(ability, profile_level(score))
                if not strengths and not high_abilities:
                    st.caption("Du har ikke valgt faglige styrker endnu.")
        with summary_cards[2]:
            with st.container(border=True):
                st.markdown("#### Din arbejdsstil")
                for label, score in work_style[:4]:
                    render_summary_item(label, profile_level(score))

        with st.expander("Se og redigér alle dine svar"):
            left, right = st.columns(2)
            with left:
                st.markdown("**Om dig og dine fag**")
                st.write(f"{profile['uddannelse']} · {profile['klassetrin']}")
                st.write("Bedst kan lide: " + (", ".join(profile["bedste_fag"]) or "Ikke angivet"))
                st.write("Vil helst undgå: " + (", ".join(profile["undgaa"]) or "Ikke angivet"))
                st.write("Fag, du vil læse videre: " + (profile["universitetsfag"] or profile["universitetsfag_svar"]))
            with right:
                st.markdown("**Dine ønsker til fremtiden**")
                st.write("Mulige arbejdsområder: " + (", ".join(profile["jobomraader"]) or "Ikke angivet"))
                st.write("Uddannelser i tankerne: " + (profile["uddannelser_tanker"] or profile["uddannelser_tanker_svar"]))
                st.write("Byer/steder: " + (profile["byer"] or "Ikke angivet"))
                st.write("Arbejdsdag: " + (", ".join(profile["arbejdsdag"]) or "Ikke angivet"))
                st.write("Vil helst undgå: " + (profile["undgaa_job"] or "Ikke angivet"))
        edit_column, suggestion_column = st.columns(2)
        with edit_column:
            if st.button("← Rediger mine svar", use_container_width=True):
                st.session_state.profile_step = 1
                st.session_state.pending_page = "Spørgeskema"
                save_and_rerun()
        with suggestion_column:
            if st.button(
                "Find uddannelser med Matching v3 →",
                type="primary",
                use_container_width=True,
            ):
                try:
                    st.session_state.recommendations = []
                    st.session_state.matching_calculated = False
                    st.session_state.matching_error = None
                    with st.spinner("Sammenligner din profil med uddannelsesdata …"):
                        calculate_matching_results()
                    st.session_state.matching_error = None
                    st.session_state.pending_page = "Anbefalinger"
                    save_and_rerun()
                except (OSError, ValueError, TypeError, KeyError, ImportError) as error:
                    st.session_state.matching_error = str(error)
                    st.error(
                        "Matching kunne ikke beregnes. Kontrollér uddannelsesdata og dine profilværdier, "
                        f"og prøv igen. Detalje: {error}"
                    )


elif (
    selected_page == "Anbefalinger"
    and st.session_state.get("selected_recommendation") is not None
):
    item = st.session_state.selected_recommendation
    st.caption("UDDANNELSESDETALJER")
    st.header(recommendation_title(item))
    st.caption(recommendation_institution(item))
    detail_metrics = st.columns(2)
    detail_metrics[0].metric("Matchscore", f"{item['match_score']:.1f}/100")
    detail_metrics[1].metric(
        "Datadækning",
        f"{item['data_coverage_count']}/{item['data_coverage_total']} dimensioner",
    )
    st.caption(item["score_interpretation"])
    if item.get("preference_reasons"):
        st.caption(
            "Også prioriteret efter: "
            + ", ".join(item["preference_reasons"])
            + "."
        )
    if item["matched_dimensions"]:
        st.subheader("Det indgår i matchberegningen")
        for dimension in item["matched_dimensions"]:
            st.write(
                f"**{dimension['dimension'].replace('_', ' ')}:** "
                f"lighed {dimension['similarity']:.1f}/100 · "
                f"bidrag {dimension['impact_from_neutral_points']:+.2f} scorepoint"
            )
    else:
        st.info("Der er ingen sammenlignelige dimensioner at vise for dette resultat.")
    st.caption(
        "Adgangskrav er ikke verificeret her. Kontrollér dem altid hos uddannelsesstedet."
    )
    offers = item.get("offers", [])
    if offers:
        with st.expander(f"Se udbud og datadækning ({len(offers)})"):
            for offer in offers:
                location = " · ".join(
                    str(offer[key])
                    for key in ("institution", "kommune", "region")
                    if offer.get(key)
                )
                coverage = (
                    f"{offer['data_coverage_count']}/{offer['data_coverage_total']} dimensioner"
                    if offer.get("data_coverage_count") is not None
                    and offer.get("data_coverage_total") is not None
                    else "Coverage ikke angivet"
                )
                if offer.get("match_score") is None:
                    st.write(
                        f"**{location or 'Udbud'}** · {coverage} · "
                        "ikke kvalificeret til rangering"
                    )
                else:
                    st.write(
                        f"**{location or 'Udbud'}** · {coverage} · "
                        f"matchscore {offer['match_score']:.1f}/100"
                    )
                url = offer.get("url")
                if isinstance(url, str) and url.startswith(("https://", "http://")):
                    st.link_button("Åbn udbudsside", url)
    detail_actions = st.columns(2)
    with detail_actions[0]:
        is_favorite = item in st.session_state.favorites
        if st.button(
            "Fjern fra favoritter" if is_favorite else "Gem som favorit",
            type="primary" if not is_favorite else "secondary",
            use_container_width=True,
            key="detail_favorite",
        ):
            if is_favorite:
                st.session_state.favorites.remove(item)
            else:
                st.session_state.favorites.append(item)
            save_and_rerun()
    with detail_actions[1]:
        return_page = st.session_state.get("detail_return_page", "Anbefalinger")
        return_label = "Tilbage til mine favoritter" if return_page == "Favoritter" else "Tilbage til mine forslag"
        if st.button(return_label, use_container_width=True, key="detail_back"):
            st.session_state.selected_recommendation = None
            st.session_state.pending_page = return_page
            save_and_rerun()

elif selected_page == "Anbefalinger":
    st.header("Uddannelser, du kan undersøge")
    st.caption(
        "Her er uddannelser, der matcher det, du har fortalt. Brug forslagene som "
        "inspiration — ikke som et svar på, hvad du skal vælge."
    )
    matching_preferences = questionnaire_matching_preferences(profile)
    if matching_preferences["institution"] == "DTU":
        st.caption("Forslagene er begrænset til DTU, fordi du har angivet DTU i dine ønsker.")
    if matching_preferences["exclude_diploma_engineering"]:
        st.caption("Diplomingeniøruddannelser er udeladt efter dit ønske.")
    if not st.session_state.recommendations:
        if st.session_state.matching_error:
            st.error(
                "Matchingresultaterne kunne ikke indlæses. Ret fejlen fra overblikket, "
                "og prøv igen."
            )
        else:
            if st.session_state.matching_calculated:
                if matching_preferences["institution"] == "DTU":
                    st.info(
                        "Der blev ikke fundet DTU-uddannelser med nok sammenlignelige "
                        "data til at lave forslag. Du kan fjerne DTU fra dine ønsker "
                        "for også at se uddannelser fra andre steder."
                    )
                else:
                    st.info(
                        "Ingen tilbud kunne rangeres med de tilgængelige data. Et tilbud "
                        "skal have mindst 8 sammenlignelige dimensioner; manglende data "
                        "tæller ikke som et match."
                    )
            else:
                st.info(
                    "Der er endnu ikke beregnet Matching v3-resultater. Gennemgå din profil "
                    "og vælg Find uddannelser med Matching v3."
                )
        if st.button("Gå til overblik →"):
            st.session_state.pending_page = "Gennemgang"
            save_and_rerun()
    else:
        recommendations = st.session_state.recommendations
        st.caption(
            "Matchscore viser lighed med din profil — ikke sandsynlighed for optagelse "
            "eller et facit på dit valg. Datadækning viser, hvor mange profilområder "
            "der kunne sammenlignes. Adgangskrav skal kontrolleres hos uddannelsesstedet. "
            "Et udbud rangeres kun med mindst 8 sammenlignelige dimensioner. "
            "Rækkefølgen tager også højde for dine valgte arbejdsområder, fravalg og "
            "arbejdsstil samt konkrete ønsker til uddannelse, sted og længde. "
            "Gymnasietype og klassetrin filtrerer ikke på adgangskrav, da de ikke er "
            "verificeret i dataene. Hjemmearbejde og balance mellem arbejde og fritid "
            "kan ikke sammenlignes med de tilgængelige uddannelsesdata. "
            "Matchscore er fortsat kun profilens lighed med uddannelsesdata."
        )
        if st.session_state.previous_recommendations:
            previous_names = {
                recommendation_title(item)
                for item in st.session_state.previous_recommendations
            }
            current_names = {recommendation_title(item) for item in recommendations}
            newly_suggested = current_names - previous_names
            no_longer_suggested = previous_names - current_names
            with st.expander("Sådan ændrede forslagene sig efter din profil blev opdateret"):
                st.write("**Nye forslag:** " + (", ".join(sorted(newly_suggested)) or "Ingen – listen blev justeret i begrundelser eller prioritering."))
                st.write("**Forslag fra før, som ikke længere vises:** " + (", ".join(sorted(no_longer_suggested)) or "Ingen."))
                st.caption("Sammenligningen ser på uddannelsesnavne. Begrundelser og match kan også være ændret.")
        labels = [
            f"{recommendation_title(item)} · {recommendation_institution(item)}"
            for item in recommendations
        ]
        st.markdown(
            '<div id="first-recommendation"></div>',
            unsafe_allow_html=True,
        )
        for index, item in enumerate(recommendations, 1):
            title = recommendation_title(item)
            institution = recommendation_institution(item)
            with st.container(border=True):
                st.caption(f"FORSLAG {index:02}")
                st.subheader(title)
                st.caption(institution)
                score_columns = st.columns(2)
                score_columns[0].metric("Matchscore", f"{item['match_score']:.1f}/100")
                score_columns[1].metric(
                    "Datadækning",
                    f"{item['data_coverage_count']}/{item['data_coverage_total']} dimensioner",
                )
                preference_reasons = item.get("preference_reasons", [])
                if preference_reasons:
                    st.caption(
                        "Også prioriteret efter: "
                        + ", ".join(preference_reasons)
                        + "."
                    )
                positive_matches = item.get("strongest_positive_dimensions", [])
                if positive_matches:
                    st.markdown("**Stærkeste matchbidrag**")
                    for match in positive_matches[:3]:
                        st.write(
                            f"• {match['dimension'].replace('_', ' ').capitalize()} · "
                            f"{match['similarity']:.0f}% lighed · "
                            f"+{match['impact_from_neutral_points']:.2f} point"
                        )
                st.caption(
                    f"{item['offers_with_match_score']} af {item['offer_count']} udbud "
                    "opfylder datakravet."
                )
                action_columns = st.columns(2)
                with action_columns[0]:
                    if st.button(
                        "Se uddannelsen →", key=f"details_{index}", use_container_width=True
                    ):
                        st.session_state.selected_recommendation = item
                        st.session_state.detail_return_page = "Anbefalinger"
                        save_and_rerun()
                with action_columns[1]:
                    if st.button(
                        "★ Fjern fra favoritter" if item in st.session_state.favorites else "☆ Gem som favorit",
                        key=f"fav_{index}",
                        use_container_width=True,
                    ):
                        if item in st.session_state.favorites:
                            st.session_state.favorites.remove(item)
                        else:
                            st.session_state.favorites.append(item)
                        save_and_rerun()
        st.subheader("Sammenlign uddannelser")
        chosen = st.multiselect(
            "Vælg 2–3 forslag", labels, max_selections=3,
            placeholder="Vælg uddannelser …", key="compare_choices",
        )
        if len(chosen) >= 2:
            picked = [recommendations[labels.index(label)] for label in chosen]
            rows = []
            rows.append(
                {
                    "Område": "Matchscore (0–100)",
                    **{
                        recommendation_title(item): f"{item['match_score']:.1f}/100"
                        for item in picked
                    },
                }
            )
            rows.append(
                {
                    "Område": "Sammenlignelige dimensioner",
                    **{
                        recommendation_title(item): (
                            f"{item['data_coverage_count']}/{item['data_coverage_total']}"
                        )
                        for item in picked
                    },
                }
            )
            rows.append(
                {
                    "Område": "Stærkeste matchbidrag",
                    **{
                        recommendation_title(item): ", ".join(
                            match["dimension"].replace("_", " ").capitalize()
                            for match in item.get("strongest_positive_dimensions", [])[:3]
                        )
                        or "Ingen tydelige positive bidrag"
                        for item in picked
                    },
                }
            )
            st.dataframe(rows, hide_index=True, use_container_width=True)
            if st.button(
                "Spørg AI om forskellen",
                key="compare_ai",
                disabled=not st.session_state.model_ready,
            ):
                st.session_state.pending_chat_question = (
                    "Hvad er den vigtigste forskel mellem disse uddannelser: "
                    + " og ".join(recommendation_title(item) for item in picked)
                    + "? Forklar forskellen ud fra de viste Matching v3-scorer og "
                    "coverage. Opfind ikke manglende uddannelsesoplysninger."
                )
        elif chosen:
            st.caption("Vælg mindst to forslag for at sammenligne.")

        st.divider()
        render_advisor_chat()


else:
    st.header("Dine favoritter")
    st.caption(
        "Matchscore viser lighed med din profil — ikke sandsynlighed for optagelse. "
        "Datadækning viser, hvor mange profilområder der kunne sammenlignes."
    )
    metric_columns = st.columns(3)
    with metric_columns[0]:
        st.metric("Gemte favoritter", len(st.session_state.favorites))
    with metric_columns[1]:
        st.metric("Uddannelsesforslag", len(st.session_state.recommendations))
    with metric_columns[2]:
        st.metric("Dit klassetrin", profile["klassetrin"])
    if not st.session_state.favorites:
        st.info("Du har ikke gemt nogen uddannelser endnu. Gem forslag fra siden Anbefalinger.")
    else:
        for index, item in enumerate(st.session_state.favorites):
            with st.container(border=True):
                st.subheader(recommendation_title(item))
                st.caption(recommendation_institution(item))
                favorite_metrics = st.columns(2)
                favorite_metrics[0].metric(
                    "Matchscore", f"{item['match_score']:.1f}/100"
                )
                favorite_metrics[1].metric(
                    "Datadækning",
                    f"{item['data_coverage_count']}/{item['data_coverage_total']} dimensioner",
                )
                favorite_actions = st.columns(2)
                with favorite_actions[0]:
                    if st.button(
                        "Se uddannelsen →",
                        key=f"favorite_details_{index}",
                        use_container_width=True,
                    ):
                        st.session_state.selected_recommendation = item
                        st.session_state.detail_return_page = "Favoritter"
                        st.session_state.pending_page = "Anbefalinger"
                        save_and_rerun()
                with favorite_actions[1]:
                    if st.button(
                        "Fjern favorit",
                        key=f"remove_favorite_{index}",
                        use_container_width=True,
                    ):
                        st.session_state.favorites.pop(index)
                        save_and_rerun()
        if len(st.session_state.favorites) >= 2:
            st.subheader("Sammenlign favoritter")
            favorite_labels = [
                f"{recommendation_title(item)} · {recommendation_institution(item)}"
                for item in st.session_state.favorites
            ]
            chosen_favorites = st.multiselect(
                "Vælg 2–3 favoritter", favorite_labels, max_selections=3,
                placeholder="Vælg favoritter …", key="favorite_compare_choices",
            )
            if len(chosen_favorites) >= 2:
                picked_favorites = [st.session_state.favorites[favorite_labels.index(label)] for label in chosen_favorites]
                favorite_rows = []
                favorite_rows.append(
                    {
                        "Område": "Matchscore (0–100)",
                        **{
                            recommendation_title(item): f"{item['match_score']:.1f}/100"
                            for item in picked_favorites
                        },
                    }
                )
                favorite_rows.append(
                    {
                        "Område": "Sammenlignelige dimensioner",
                        **{
                            recommendation_title(item): (
                                f"{item['data_coverage_count']}/"
                                f"{item['data_coverage_total']}"
                            )
                            for item in picked_favorites
                        },
                    }
                )
                favorite_rows.append(
                    {
                        "Område": "Stærkeste matchbidrag",
                        **{
                            recommendation_title(item): ", ".join(
                                match["dimension"].replace("_", " ").capitalize()
                                for match in item.get(
                                    "strongest_positive_dimensions", []
                                )[:3]
                            )
                            or "Ingen tydelige positive bidrag"
                            for item in picked_favorites
                        },
                    }
                )
                st.dataframe(favorite_rows, hide_index=True, use_container_width=True)
    if st.session_state.profile:
        top_areas = sorted(profile["interesser"].items(), key=lambda pair: pair[1], reverse=True)[:3]
        with st.container(border=True):
            st.subheader("Dit personlige overblik")
            st.caption("En hurtig opsummering af det, du har fortalt om dig selv.")
            overview_left, overview_right = st.columns(2)
            with overview_left:
                st.markdown("**Det interesserer dig**")
                st.write(", ".join(profile["topinteresser"]) or ", ".join(
                    f"{name} ({score}/5)" for name, score in top_areas
                ))
                st.markdown("**Fag, du bedst kan lide**")
                st.write(", ".join(profile["bedste_fag"]) or "Ikke angivet endnu")
                st.markdown("**Dine faglige styrker**")
                st.write(", ".join(profile["staerkeste_fag"]) or "Ikke angivet endnu")
            with overview_right:
                st.markdown("**Fag, du helst vil undgå**")
                st.write(", ".join(profile["mindst_fag"]) or "Ikke angivet endnu")
                st.markdown("**Uddannelser, du kan udforske**")
                st.write(", ".join(
                    recommendation_title(item)
                    for item in st.session_state.recommendations
                ) or "Lav anbefalinger ud fra din profil for at se forslag.")
                st.markdown("**Dine næste skridt**")
                st.write("Du kan til enhver tid opdatere din profil eller lave nye anbefalinger.")

persist_account_state()
