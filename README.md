# Studievejleder

En lokal Streamlit-app, der bruger Matching v3 til at rangere videregående uddannelser ud fra brugerens profil. **Ollama** og modellen **phi3.5** er valgfrie og bruges kun til opfølgende spørgsmål og chat, ikke til matchscore eller rangering. Brugere kan oprette en konto og gemme profil, svar, forslag, favoritter og chat i en lokal SQLite-database.

## Start appen

1. Installér afhængighederne med: `python -m pip install -r requirements.txt`
2. Start appen med: `python -m streamlit run app.py`
3. Matching v3 virker uden Ollama. Hvis du vil bruge AI-opfølgning og chat, installér Ollama fra https://ollama.com/ og sørg for, at programmet kører. AI indlæses automatisk, når du åbner dit overblik eller dine forslag; første gang hentes modellen automatisk.

## Sådan bruges appen

Appen åbner på forsiden, hvor du kan vælge **Fortsæt som gæst** med det samme. Login og oprettelse af konto ligger samlet i et valgfrit, sammenklappet felt på forsiden. Log ind for at gemme profil, svar, forslag, favoritter og chat, så du kan fortsætte senere. Gæstedata findes kun i den aktuelle session og gemmes ikke til næste besøg. Første gang kan du gå gennem de fem korte profiltrin. Når profilen er oprettet, kan du gå mellem trinene med **Næste trin** og gemme ændringer undervejs uden at udfylde hele spørgeskemaet igen. Faglisten inkluderer bl.a. programmering, softwareudvikling og datalogi. Matching v3 bruger svar om interesser, fravalg, fag, styrker, arbejdsområder, arbejdsdag, arbejdsstil og jobværdier i de tilsvarende profildimensioner. Ønsker om uddannelsesnavn, uddannelsessted og længde påvirker også forslagets prioritering, når oplysningerne kan genkendes i uddannelsesdata. Matchscore viser fortsat kun profilens lighed med uddannelsesdata; prioriteringshensyn vises særskilt. Forslagssiden åbner ved det første forslag; sammenligning og chat ligger længere nede, så du selv kan rulle dertil. Resultaterne viser matchscore, sammenlignelige dimensioner og tilgængelige udbud. AI-chatten får en kort, konkret opsummering af dine spørgeskemasvar, dine opfølgende svar, aktuelle forslag og op til tre relevante rækker fra uddannelsesarbejdsbogen. Neutrale skalasvar sendes ikke som præferencer, og modellen instrueres i at knytte forslag til konkrete svar og skrive korrekt dansk. Rækkerne udvælges efter dit spørgsmål og dine forslag; relevante kompetencebeskrivelser og undervisningsformer medsendes, men modellen får ikke hele arbejdsbogen. Profilområder i arbejdsbogen er Studiekompas-estimater baseret på UFSN-data, ikke officielle vurderinger. AI’en skal sige til, når en konkret oplysning ikke findes i datagrundlaget, og må ikke opfinde adgangskrav eller andre uddannelsesfakta. `.pyc`-filerne i `__pycache__` er kompileret programkode, ikke brugerdata, og bruges ikke som AI-kontekst. Når AI er indlæst, kan den stille op til fem opfølgende spørgsmål og bruges til chat; svarene på opfølgningen er kun AI-chatkontekst og indgår ikke i matchscore eller rangering. AI beregner ikke matchscore eller vælger uddannelser.

Du kan når som helst ændre profilen. Hvis du allerede har fået forslag, beregnes de automatisk igen, når du gemmer profilændringer, så de tager udgangspunkt i dine nye svar. Ønsker om en bestemt institution, fx DTU, og tydelige fravalg af uddannelsestyper i friteksten under hensyn bliver også respekteret. Ønsker til by/sted og uddannelseslængde justerer prioriteringen, når de kan sammenholdes med tilbuddenes sted og brede uddannelseskategori. Uddannelseskategori er kun en grov stedfortræder for varighed, ikke en verificeret varighedsoplysning. Gymnasietype og klassetrin bruges ikke til adgangsfiltrering, fordi arbejdsbogen ikke indeholder verificerede adgangskrav. Den indeholder heller ikke sammenlignelige oplysninger om hjemmearbejde eller balance mellem arbejde og fritid; de svar kan derfor ikke ændre matchscore. Derefter vises hvilke uddannelser der er kommet til eller faldet fra. Favoritter kan ses og sammenlignes på deres egen side. Under indstillinger kan du valgfrit starte profilen forfra eller slette alle gemte data på kontoen.

Konti og gemte data ligger i `data/studiekompas.sqlite3`. Databasen kan flyttes med miljøvariablen `STUDIEKOMPAS_DB`. Adgangskoder gemmes som PBKDF2-hashes, ikke som klartekst. En lokal SQLite-database er beregnet til en lokal installation eller en enkelt app-server; ved offentlig drift skal appen desuden køre bag HTTPS og med passende sikkerhedskopiering og adgangskontrol.

Uddannelsesforslag er vejledning og inspiration. Matchscore er lighed med de tilgængelige profildata, ikke en sandsynlighed for optagelse eller trivsel. Manglende uddannelsesdata indgår ikke som et match, og kun tilbud med mindst otte sammenlignelige dimensioner kan rangeres. Kontrollér altid aktuelle adgangskrav og uddannelsesdetaljer på institutionens officielle hjemmeside. AI'en kan mangle eller tage fejl af oplysninger.

Hvis Ollama kører på en anden adresse, kan den angives med miljøvariablen OLLAMA_URL.

## Matching v3

Matching v3 kan også afprøves direkte uden Streamlit eller Ollama:

```python
from data.education_profiles import load_education_profiles
from matching import rank_education, user_profile_from_questionnaire

education_profiles = load_education_profiles()
user_profile = user_profile_from_questionnaire(existing_questionnaire_answers)
recommendations = rank_education(user_profile, education_profiles)
```

`load_education_profiles()` læser `data/ufm_samlet_19jun2026.xlsx` uden at ændre originalfilen. V3 medtager bachelor-, professionsbachelor- og erhvervsakademiuddannelser og udelader rækker med `udbud_id=999999`. Profilerne bevarer også `displaydocclass`. De genererede dimensionsscorer er Studiekompas-estimater, ikke officielle UFSN-scorer. Manglende kildedata forbliver manglende og indgår ikke som nul i afstanden.

De vigtigste kilder og transformationer er:

| Profilområde | UFSN-kilder / Studiekompas-transformation |
| --- | --- |
| Faglig interesse | `Titel` og `kompetencerudd_p1-p5` klassificeret med Studiekompas' fagområdetermer; et nøgleordstræf giver 4, flere giver 5 |
| Faglige styrker | `kompetencerudd_p1-p5` klassificeret mod spørgeskemaets evneområder |
| Faglig fordybelse | `Titel` klassificeret mod de samme fagområder; brugerens ønske om at læse fag videre er et separat signal |
| Teknologi | Titelaliaser for bl.a. datamatiker, datalogi, software og kunstig intelligens giver 5; teknologikompetencer/-nøgleord giver mindst 4; informations- og kommunikationsbranchens andel bruges som svagere reservekilde |
| Data/analytisk, kreativitet, mennesker | Titel- og kompetencetekster klassificeret med Studiekompas' nøgleord |
| Samarbejde | `arbmedstud_likert`, samarbejdskompetencer og gruppearbejde/projektarbejde i `undervisningsform_p1-p5` |
| Selvstændighed | `arbejdsform_tilretteselv_pct` og placeringen af selvstudie i `undervisningsform_p1-p5` |
| Praktisk læring | `uddaktivitet_praktik_pct`, praktiske kompetencer og praktik/værksted/laboratorium i undervisningsformerne |
| Teoretisk læring | teori-/metodekompetencer og forelæsning/klasseundervisning i `undervisningsform_p1-p5` |
| Projektarbejde | projektkompetencer og projektarbejde i undervisningsformerne |
| Variation | `arbejdsform_fleksible_pct`, `arbejdsform_skiftende_pct`, `arbejdsform_andet_pct` |
| Internationalitet | `uddaktivitet_udlandsophold_pct` og `udlandet_udlandet_pct` |
| Jobsikkerhed | Inverterede percentilrangeringer af `ledighed_nyudd` og `ledighed_10aar` |
| Løn/økonomi | Percentilrangeringer af `maanedloen_nyudd` og `maanedloen_10aar` |
| Karrieremuligheder/jobrelevans | `relevans_overens_udd_job_likert` og `ruster_til_job_likert` |

UFSN-filen indeholder ikke adgangskrav. Education profiles sætter derfor `admission_status="unknown"`. Adgangsstatus er ikke en del af `rank_education()` og indgår ikke i scoren. Den tidligere separate `filter_by_admission_requirements()`-hjælper er ikke kaldt af v3-rangeringen.

V3 bruger ikke kNN: den eksisterende prototype beregner en vægtet afstand til hver uddannelsesprofil direkte. Der bruges heller ikke Ollama til scoring eller rangering.

### V3 vægte og score

Dimensionernes eksplicitte vægte er samlet i `matching.py` som `DIMENSION_WEIGHTS`. De vægtes først inden for to blokke: kerne og sekundære signaler. `BLOCK_WEIGHTS` fastsætter kerneblokkens vægt til 0,8 og den sekundære blok til 0,2. Når sekundære dimensioner mangler helt, normaliseres kerneblokken til 1,0.

| Blok | Dimension | Vægt |
| --- | --- | ---: |
| Kerne | `faglig_interesse` | 1,5 |
| Kerne | `faglige_styrker` | 1,25 |
| Kerne | `faglig_fordybelse` | 1,5 |
| Kerne | `praktisk_læring` | 1,0 |
| Kerne | `teoretisk_læring` | 1,0 |
| Kerne | `samarbejde` | 0,8 |
| Kerne | `selvstændighed` | 0,8 |
| Kerne | `projektarbejde` | 0,8 |
| Kerne | `teknologi` | 1,25 |
| Kerne | `data_analytisk` | 1,25 |
| Kerne | `jobsikkerhed` | 0,75 |
| Kerne | `løn_økonomi` | 0,75 |
| Kerne | `karrieremuligheder` | 0,75 |
| Sekundær | `kreativitet` | 0,5 |
| Sekundær | `mennesker` | 0,5 |
| Sekundær | `variation` | 0,5 |
| Sekundær | `internationalitet` | 0,5 |

For hver dimensionsgruppe beregnes RMS-afstanden mellem brugerens og uddannelsens fælles gyldige værdier; lighed er `max(0, 100 × (1 − RMS-afstand / 4))`. Vektorgrupper sammenligner kun fælles fag-/evneområder. Inden for hver blok beregnes en vægtet middelværdi over dimensioner med fælles data. Den endelige matchscore er 0,8 × kernescore + 0,2 × sekundær score, renormaliseret hvis én blok helt mangler. En kandidat skal have mindst otte sammenlignelige dimensioner og mindst én sammenlignelig kernedimension.

Scoren betyder **samlet lighed mellem brugerprofilen og de tilgængelige uddannelsesdata**. Den er ikke en sandsynlighed for optagelse, gennemførelse eller trivsel og er ikke en objektiv vurdering af, hvilken uddannelse eleven bør vælge.

Uddannelsesudbud grupperes på accent-/mellemrum-/bindestregsnormaliseret titel, så top 5 indeholder unikke uddannelsestitler; hver titel bevarer sine udbud i feltet `offers`. Matchscoren for et titelresultat er bedste score blandt dets rangerbare udbud; ved ens score prioriteres højere match coverage.

`education_profile_coverage_count/total` tæller tilstedeværende dimensionsgrupper på uddannelsesprofilen. `data_coverage_count/total` tæller dimensionsgrupper med mindst én faktisk fælles bruger-/uddannelsesværdi i det konkrete match. Coverage er rapporteret separat, ikke en del af scoren; den bruges som tie-breaker ved ens score. Niveauer er under 50 % `low`, 50 % til under 80 % `medium`, og mindst 80 % `high` (fx 8/17 low, 10/17 medium, 14/17 high).

Resultatet indeholder maskinlæsbare `matched_dimensions`, `strongest_positive_dimensions`, `weakest_dimensions`, `negative_impact_dimensions`, `missing_dimensions` og `partial_dimensions`. `weakest_dimensions` er de laveste ligheder blandt sammenlignede dimensioner, også hvis deres bidrag stadig er over neutralpunktet. `negative_impact_dimensions` viser dimensioner under neutralpunktet. Positiv/negativ påvirkning opgøres i scorepoint relativt til 50 som neutral reference; manglende dimensioner angiver, om værdier manglede hos brugeren, i uddannelsesprofilen eller begge steder. For vektorgrupper angiver `partial_dimensions`, når kun nogle af værdierne kunne sammenlignes.

UFSN-kompetencefelterne er proxyer for kompetencer knyttet til uddannelsen, ikke direkte målinger af nødvendige elevstyrker. Titelaliaserne er eksplicitte Studiekompas-heuristikker i `data/education_profiles.py`, ikke officielle UFSN-klassifikationer: teknologialiaserne er `datamatiker`, `datalogi`, `software`, `computer science`, `kunstig intelligens`, `maskinlæring`, `cybersikkerhed`, `informatik`, `programmering`, `webudvikling`, `automationsteknolog`, `informationsteknologi` og `it-arkitektur`. Eksempel: `Datamatiker → teknologi = 5` er en modelregel alene baseret på titlen. De nuværende dataaliaser er `datamatiker`, `datalogi`, `data science`, `datavidenskab`, `kunstig intelligens`, `maskinlæring`, `business intelligence`, `dataanalyse` og `statistik`.

Karrieredimensioner sammenligner brugerens præferencer med observerede/rapporterede uddannelsesudfald på samme 1–5-skala; dette er en modelantagelse, ikke en valideret psykometrisk skala. Matchscore er hverken sandsynlighed for optagelse, gennemførelse eller trivsel eller en objektiv vurdering af, hvilken uddannelse eleven bør vælge.

Kør de isolerede tests med `python -m unittest discover -s tests`.
