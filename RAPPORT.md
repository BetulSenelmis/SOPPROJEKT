# Rapport om Studiekompas

**Dato:** 15. oktober 2026  
**Grundlag:** Gennemgang af appens kode, uddannelsesdata, README og automatiske tests.

## 1. Kort fortalt

Studiekompas er en dansksproget webapp bygget med Streamlit. Den hjælper gymnasieelever med at udforske videregående uddannelser ved først at samle oplysninger om elevens fag, interesser, styrker og ønsker og derefter sammenligne profilen med uddannelsesdata.

Appens vigtigste funktion er **Matching v3**, som beregner en forklarlig lighedsscore og viser, hvilke områder der bidrager til eller trækker ned i et match. Appen kan bruges uden kunstig intelligens. En valgfri lokal AI-model via Ollama kan stille opfølgende spørgsmål og svare på spørgsmål om profilen og forslagene.

Studiekompas giver inspiration til videre undersøgelse. Det træffer ikke et valg på elevens vegne og afgør ikke, om eleven kan blive optaget eller vil trives på en uddannelse.

## 2. Hvad brugeren kan gøre

### Komme i gang

- Fortsætte som gæst uden at oprette en konto.
- Oprette en konto eller logge ind for at gemme sin profil og sine resultater.
- Vælge mellem lyst og mørkt udseende.
- Bruge spørgeskema og uddannelsesmatch, selv hvis Ollama eller AI ikke er tilgængelig.

Gæstedata ligger kun i den aktuelle app-session. En konto gemmer data lokalt, så brugeren kan fortsætte senere.

### Udfylde og redigere sin profil

Spørgeskemaet er fordelt på fem trin:

1. **Om dig:** gymnasial uddannelse og klassetrin.
2. **Dine fag:** yndlingsfag, mindst interessante fag, faglige styrker og eventuelle evnevurderinger.
3. **Interesser:** op til tre udvalgte interesseområder, vurdering af interesse og valgfrie fravalg.
4. **Arbejdsstil:** præference for selvstændigt arbejde eller samarbejde, teori eller praksis, variation samt betydningen af kreativitet, mennesker, teknologi og data.
5. **Din fremtid:** mulige arbejdsområder, uddannelser og fag i tankerne, ønsker til sted og længde, arbejdsdag, jobværdier og forhold, eleven helst vil undgå.

Flere felter er valgfrie, og spørgeskemaet giver plads til, at eleven endnu ikke ved, hvad vedkommende vil. En gemt profil kan redigeres trin for trin. Hvis der allerede findes anbefalinger, beregnes de igen efter gemte profilændringer. Appen viser også, hvilke uddannelsesnavne der er kommet til eller ikke længere vises efter ændringen.

### Få overblik og forslag

Efter spørgeskemaet kan brugeren se:

- En kort opsummering af interesser, faglige styrker og arbejdsstil.
- Udvalgte profilområder og mulighed for at åbne og gennemgå svarene.
- Op til fem rangerede uddannelsestitler, når der er nok sammenlignelige data.
- Matchscore, datadækning og stærke matchbidrag for hvert forslag.
- Uddannelsessteder og udbud, hvor oplysningerne findes, herunder sted og link.
- Detaljer om matchdimensioner og deres bidrag til scoren.
- Mulighed for at gemme forslag som favoritter, fjerne favoritter og sammenligne 2–3 forslag.
- Et personligt overblik på favoritsiden og mulighed for at sammenligne favoritter.

Et uddannelsesnavn kan dække over flere udbud eller steder. Appen samler udbud med samme normaliserede titel under ét forslag og viser de tilhørende udbud som alternativer.

### Bruge den valgfrie AI

Når brugeren åbner overblikket eller forslagene, forsøger appen at gøre Ollama klar. Første gang hentes modellen `phi3.5`, hvis den ikke allerede findes, hvorefter modellen varmes op. AI-funktionerne består af:

- **Opfølgende spørgsmål:** AI’en kan foreslå op til fem spørgsmål, hvis den vurderer, at svarene er uklare, modstridende eller mangelfulde. Brugeren kan besvare eller springe hvert spørgsmål over.
- **Studievejlederchat:** Brugeren kan stille spørgsmål om egne interesser, fag, arbejdsform og uddannelsesforslag.
- **Sammenligningshjælp:** For to eller tre valgte forslag kan brugeren bede AI’en forklare forskellene.

Chatten sender en kort opsummering af konkrete spørgeskemasvar, eventuelle opfølgende svar, aktuelle forslag og op til tre relevante poster fra uddannelsesdataene. Den forsøger dermed at holde elevens egne svar og relevante uddannelsesoplysninger tæt på spørgsmålet. Modellen får ikke hele regnearket.

AI’en er ikke ansvarlig for matchscore eller rangering. Hvis Ollama ikke virker, kan brugeren fortsat se overblikket og beregne uddannelsesmatch uden AI.

## 3. Sådan beregnes uddannelsesmatch

### Datagrundlag

Appen læser den medfølgende Excel-arbejdsbog `data/ufm_samlet_19jun2026.xlsx`, fra arket `UFM_samlet_19JUN2026`. Den medfølgende transformation medtager:

- Bacheloruddannelser.
- Professionsbacheloruddannelser.
- Erhvervsakademiuddannelser.

Nationale aggregeringsrækker med `udbud_id=999999` fjernes. Originalarbejdsbogen ændres ikke af indlæsningen. Manglende kildeværdier bevares som manglende i stedet for at blive behandlet som nul.

### Profilområder

Uddannelserne får beregnede profiler inden for 17 områder:

- Faglig interesse, faglige styrker og faglig fordybelse.
- Teknologi og data/analytik.
- Kreativitet og menneskearbejde.
- Samarbejde, selvstændighed, praktisk læring, teoretisk læring og projektarbejde.
- Variation og internationalitet.
- Jobsikkerhed, løn/økonomi og karrieremuligheder.

Nogle værdier er omregnet fra arbejdsbogens tal, andre bygger på nøgleord i uddannelsestitler, kompetencebeskrivelser og undervisningsformer. Eksempelvis kan en titel som “Datamatiker” udløse en høj teknologiværdi. Det er Studiekompas’ egne, dokumenterede modelregler — ikke en officiel UFSN-vurdering.

### Score og forklaringer

Brugersvar mappes til tilsvarende dimensioner på en skala fra 1 til 5. Scoringen:

- Sammenligner kun værdier, som faktisk findes på begge sider.
- Beregner lighed inden for hver dimension og kombinerer dimensionerne med fastlagte vægte.
- Lægger hovedvægten på kerneområder; sekundære områder har mindre samlet vægt.
- Kræver mindst otte sammenlignelige dimensioner for at rangere et udbud.
- Returnerer op til fem unikke uddannelsestitler.

Resultaterne forklarer blandt andet stærke bidrag, svagere områder, manglende data, delvise sammenligninger og datadækning. Datadækningen vises separat fra matchscoren; den er ikke i sig selv en matchscore.

### Personlige ønsker ud over matchscoren

Nogle eksplicitte ønsker påvirker, hvilke tilbud der medtages eller deres prioriteringsrækkefølge:

- En tydelig DTU-præference kan begrænse resultaterne til DTU.
- Et klart fravalg af diplomingeniøruddannelser kan udelukke disse titler.
- Ønske om by/sted kan prioritere udbud, hvis stedet kan genkendes i dataene.
- Uddannelsesnavne skrevet i fritekst kan få højere prioritet, hvis et match findes.
- Ønske om kortere eller længere uddannelse kan påvirke prioriteringen ud fra uddannelseskategorien.

Disse hensyn ændrer prioriteringen, men matchscoren rapporteres stadig som ligheden mellem profil og uddannelsesdata.

## 4. Hvad programmet ikke kan afgøre

- **Optagelse:** Arbejdsbogen indeholder ikke verificerede adgangskrav. Gymnasietype og klassetrin bruges derfor ikke til at afgøre, om eleven opfylder kravene.
- **Trivsel eller succes:** Scoren er ikke en sandsynlighed for optagelse, gennemførelse, arbejdsglæde eller trivsel.
- **Verificeret uddannelseslængde:** Ønske om længde behandles kun via brede uddannelseskategorier; det er ikke en kontrol af den faktiske varighed.
- **Alle arbejdsvilkår:** Der er ikke sammenlignelige data om eksempelvis hjemmearbejde eller balance mellem arbejde og fritid, så sådanne ønsker kan ikke indgå på samme måde.
- **Officielle kompetencevurderinger:** Uddannelsesprofilerne er Studiekompas-estimater og nøgleordsbaserede proxyer. De beskriver ikke nødvendigvis de kompetencer, en bestemt elev skal have for at gennemføre uddannelsen.
- **Fejlfri AI-svar:** AI’en kan stadig misforstå, skrive forkert eller mangle oplysninger. Instruktioner om korrekt dansk og om ikke at opfinde fakta er ikke en garanti.
- **Garanti for hurtige AI-svar:** AI’en kører lokalt med Ollama og afhænger blandt andet af modelindlæsning, computerens ressourcer og antallet af genererede tokens. Appens tests måler ikke svartid på en rigtig model.

Brugeren bør altid kontrollere aktuelle adgangskrav og uddannelsesdetaljer på uddannelsesstedets officielle hjemmeside.

## 5. Teknisk opbygning og data

- **Brugerflade:** Python og Streamlit.
- **Matching:** Python, pandas og projektets egne moduler `matching.py` og `matching_service.py`.
- **Uddannelsesdata:** Excel læst med pandas/openpyxl og transformeret af `data/education_profiles.py`.
- **Valgfri AI:** Ollama HTTP API med modellen `phi3.5`; standardadressen er `http://127.0.0.1:11434` og kan ændres med `OLLAMA_URL`.
- **Konti og gemt tilstand:** Lokal SQLite i `data/studiekompas.sqlite3`; placeringen kan ændres med `STUDIEKOMPAS_DB`.
- **Test:** Isolerede `unittest`-tests for konti, spørgeskemaflow, matching og matching-service.

Adgangskoder hashes med PBKDF2-HMAC-SHA256, individuel salt og 310.000 iterationer. Profil, chat, favoritter og øvrig konto-tilstand gemmes som JSON i SQLite. Kontoindholdet er ikke krypteret af denne lagring. Databasen er beregnet til lokal brug eller en enkelt app-server; offentlig drift kræver særskilt vurdering af adgangskontrol, HTTPS, sikkerhedskopiering og databeskyttelse.

## 6. Kørsel og test

Installér afhængigheder og start appen fra projektmappen:

```powershell
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

Matching virker uden Ollama. For AI-funktioner skal Ollama være installeret og køre. Appen forsøger selv at hente `phi3.5`, hvis modellen mangler.

Projektets test-suite køres med:

```powershell
python -m unittest discover -s tests
```

Ved rapportens udarbejdelse bestod alle **48 automatiske tests**. AI-relaterede tests bruger simulerede Ollama-svar; de bekræfter appens flow og de data, der sendes til modellen, men ikke den virkelige models sproglige kvalitet eller svartid.

## 7. Samlet vurdering

Studiekompas er et værktøj til tidlig uddannelsesafklaring: det hjælper brugeren med at sætte ord på egne præferencer, se uddannelsesmuligheder og forstå, hvorfor bestemte forslag vises. Styrken er kombinationen af et redigerbart spørgeskema, en deterministisk og forklarlig matchingberegning samt valgfri AI-dialog.

Resultaterne bør bruges som et udgangspunkt for videre research og samtaler med en vejleder — ikke som en automatisk beslutning om, hvad eleven bør vælge.

## Centrale projektfiler

- `app.py` — Streamlit-brugerflade, spørgeskema, AI-flow, resultater og favoritter.
- `matching.py` — profilmapping, score, rangering og forklaringer.
- `matching_service.py` — anvendelse af brugerønsker på matchingresultater.
- `data/education_profiles.py` — indlæsning og transformation af arbejdsbogen.
- `account_store.py` — lokale konti og gemt tilstand.
- `tests/` — automatiske tests.
- `README.md` — installation, anvendelse og teknisk dokumentation af Matching v3.
