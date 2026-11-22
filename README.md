# Data Scraping – Swiss Hospitality Jobs

Python projekt na sledovanie pracovných ponúk na kariérnych stránkach hotelov a gastro prevádzok vo Švajčiarsku.

Projekt:
1. Stiahne HTML stránku zamestnávateľa.
2. Vyčistí HTML od technického balastu.
3. Uloží aktuálny HTML snapshot a zachová predchádzajúci snapshot.
4. Porovná starý a nový HTML obsah.
5. Pošle zmeny do Meta AI na identifikáciu nových alebo zmiznutých pracovných ponúk.
6. Vypíše výsledný JSON do terminálu.

**WordPress integrácia nie je implementovaná.** Projekt momentálne iba pripravuje a vypisuje JSON; nič neposiela do WordPress API.

---

## 1. Požiadavky

- Python 3
- Meta AI API key
- Internetové pripojenie
- Závislosti:
  - `crawl4ai`
  - `beautifulsoup4`
  - `openai`
  - `python-dotenv`

V projekte zatiaľ nie je `requirements.txt`, preto sa závislosti inštalujú ručne.

## 2. Inštalácia

V termináli prejdi do priečinka projektu.

### Vytvorenie virtuálneho prostredia

Windows / Git Bash:

```bash
python -m venv .venv
source .venv/Scripts/activate
```

Ak používaš Windows CMD:

```cmd
.venv\\Scripts\\activate
```

### Inštalácia knižníc

```bash
python -m pip install --upgrade pip
pip install crawl4ai beautifulsoup4 openai python-dotenv
```

Crawl4AI môže po inštalácii vyžadovať inicializáciu prehliadača:

```bash
crawl4ai-setup
```

## 3. Konfigurácia Meta AI

V koreňovom priečinku projektu vytvor súbor `.env`:

```env
META_API_KEY=your_meta_api_key
META_MODEL=muse-spark-1.3-contributor
```

- `META_API_KEY` – povinný API kľúč.
- `META_MODEL` – voliteľný názov modelu; ak nie je nastavený, použije sa predvolený model uvedený v `ai_prepare.py`.

Súbor `.env` je v `.gitignore` a nesmie sa commitovať do GitHubu.

---

## 4. Súbory projektu

| Súbor | Úloha |
|---|---|
| `main.py` | Hlavný produkčný workflow pre jedného zamestnávateľa. |
| `scrape.py` | Sťahuje webové stránky a čistí HTML pomocou Crawl4AI a BeautifulSoup. |
| `compare.py` | Porovnáva starý a nový HTML súbor a vytvára zoznam pridaných a odstránených riadkov. |
| `ai_prepare.py` | Pripravuje vstup pre Meta AI, volá API, spracuje JSON odpoveď a doplní údaje zamestnávateľa. |
| `test.py` | Samostatný testovací workflow nad dvoma ručne pripravenými HTML súbormi. |
| `sites.json` | Zoznam zamestnávateľov, ich URL, slug, adresa, kantón a rozsah pôsobenia. |
| `.env` | Lokálna konfigurácia API kľúča a voliteľného modelu. |
| `.gitignore` | Vylučuje virtuálne prostredie, API tajomstvá, Python cache a výstupné HTML súbory. |

### `main.py` – hlavný workflow

Spúšťa celý proces pre jedného zamestnávateľa podľa jeho slug.

Poradie:
1. Nájde zamestnávateľa v `sites.json`.
2. Určí názvy aktuálneho a starého HTML súboru.
3. Zistí, či ide o prvé skenovanie.
4. Spustí scraper.
5. Pri prvom skenovaní pošle aktuálne HTML do AI ako `FIRST_SCAN`.
6. Pri ďalších skenovaniach porovná starý a nový snapshot.
7. Pošle diff do Meta AI a vypíše výsledný JSON.

Ak scraping zlyhá alebo chýba očakávaný snapshot, workflow sa zastaví.

### `scrape.py` – scraping a čistenie

- Načíta zamestnávateľov z `sites.json`.
- Používa Crawl4AI s headless prehliadačom.
- Čaká na načítanie stránky pomocou `networkidle` (timeout 60 sekúnd).
- Pomocou BeautifulSoup odstraňuje skripty, štýly, obrázky, cookie bannery, pätičky a ďalší nepotrebný obsah.
- Zachováva text a odkazy.
- Pred prepísaním aktuálneho HTML skopíruje existujúci snapshot do súboru s príponou `-old.html`.

Scraper môže bežať pre jeden slug alebo pre všetkých zamestnávateľov.

### `compare.py` – porovnávanie HTML

Používa Python `difflib.SequenceMatcher` na porovnanie riadkov.

Výsledok obsahuje:
- `added` – riadky pridané v novom HTML,
- `removed` – riadky, ktoré boli v starom HTML a v novom chýbajú,
- počet riadkov v starom a novom súbore.

Porovnanie je založené na riadkoch HTML, nie na sémantickom porozumení pracovným ponukám. O tom, či ide o skutočnú pracovnú ponuku, rozhoduje následne AI.

### `ai_prepare.py` – Meta AI a JSON

- Načíta konfiguráciu zamestnávateľa zo `sites.json`.
- Pri prvom skenovaní pripraví celé HTML.
- Pri ďalších skenovaniach pripraví pridané a odstránené riadky.
- Ak sa HTML nezmenilo, AI volanie preskočí.
- Odošle požiadavku do Meta AI cez OpenAI-kompatibilné SDK.
- Parsuje JSON odpoveď.
- Doplní manuálne údaje zamestnávateľa, napríklad názov, adresu, kantón a slug.
- Vypíše finálny JSON a spotrebu tokenov.

Výstup používa akcie:
- `create` – nová pracovná ponuka,
- `delete` – pracovná ponuka, ktorá zmizla zo stránky.

**Pozor:** zmiznutie odkazu zo stránky automaticky nedokazuje, že pracovná pozícia bola definitívne obsadená alebo zrušená. Výsledky AI je vhodné pred ďalším automatickým spracovaním kontrolovať.

### `test.py` – samostatný testovací režim

Testovací režim nepotrebuje slug, `sites.json` ani živú webovú stránku.

Používa výhradne tieto dva súbory:

```text
scrape_output/
├── test.html
└── test-old.html
```

- `test.html` – nová verzia HTML.
- `test-old.html` – staršia verzia HTML.

Súbory si pripravíš ručne skopírovaním HTML, ktoré chceš porovnať.

Skript:
1. Porovná HTML cez funkciu z `compare.py`.
2. Vypíše zmeny do terminálu.
3. Pri štandardnom spustení odošle diff do Meta AI.
4. Vypíše surovú odpoveď AI a výsledný JSON.

Testovací režim nemení HTML súbory, nespúšťa scraping a nevolá WordPress API. Pri relatívnych URL ich ponecháva v pôvodnom tvare, pretože nemá nastavenú zdrojovú adresu stránky.

---

## 5. Príkazy

### Hlavný workflow – jeden zamestnávateľ

```bash
python main.py stoos-hotels
python main.py gasthof-zum-ochsen
python main.py les-trois-rois
```

Slug musí existovať v `sites.json`.

### Samostatný scraping

Scrapovanie jedného zamestnávateľa:

```bash
python scrape.py stoos-hotels
```

Scrapovanie všetkých zamestnávateľov:

```bash
python scrape.py
```

Tento príkaz iba stiahne a uloží HTML. Nespúšťa porovnávanie ani AI.

### Samostatné porovnanie

Predvolené súbory pre Stoos Hotels:

```bash
python compare.py
```

Vlastné názvy súborov (musia byť v `scrape_output`):

```bash
python compare.py test.html test-old.html
```

### Samostatné AI spracovanie

```bash
python ai_prepare.py stoos-hotels
```

Používa HTML súbory konkrétneho zamestnávateľa a jeho metadata z `sites.json`.

### Testovací workflow

Porovnanie a Meta AI:

```bash
python test.py
```

Iba porovnanie, bez API volania:

```bash
python test.py --no-ai
```

---

## 6. Ako fungujú HTML snapshoty

Pre každého zamestnávateľa sa v `scrape_output` ukladajú dva súbory:

```text
scrape_output/
├── stoos-hotels.html
└── stoos-hotels-old.html
```

Pri ďalšom scrapovaní sa existujúci aktuálny súbor najskôr skopíruje do `-old.html` a až potom sa uloží nové HTML.

Následne sa porovná:
- starý snapshot: `stoos-hotels-old.html`
- nový snapshot: `stoos-hotels.html`

Pri prvom skenovaní ešte starý snapshot neexistuje. `main.py` preto pošle aktuálne HTML do AI ako prvé skenovanie, nie ako diff.

**Dôležité:** `scrape_output/` je v `.gitignore`. HTML snapshoty sú lokálne a Git ich nesynchronizuje. Pri práci na inom počítači alebo po čistej inštalácii ich treba znovu vytvoriť.

---

## 7. Konfigurácia zamestnávateľov – `sites.json`

Každý záznam obsahuje:

| Pole | Význam |
|---|---|
| `name` | Názov zamestnávateľa |
| `slug` | Jedinečný identifikátor používaný v príkazoch a názvoch súborov |
| `url` | Kariérna stránka, ktorú scraper otvorí |
| `address` | Adresa zamestnávateľa alebo pracoviska |
| `canton` | Kantón |
| `scope` | Rozsah pôsobenia, napr. `local` alebo `national` |

Pri pridaní zamestnávateľa doplň nový objekt do JSON poľa a použi jedinečný slug.

---

## 8. Čo projekt zatiaľ nerobí

- Neodosiela pracovné ponuky do WordPressu.
- Neoveruje, či je pracovná ponuka na externom webe stále aktívna.
- Nemá automatické plánovanie scrapingov.
- Nemá databázu histórie pracovných ponúk.
- Nemá automatické testy ani samostatný `requirements.txt`.
- Diff porovnáva HTML po riadkoch; zmena formátovania môže vytvoriť zbytočné rozdiely.

---

## 9. Odporúčané ďalšie zlepšenia

Nie je potrebné pridávať zložité architektonické vrstvy. Najväčší prínos by mali tieto kroky, v tomto poradí:

1. **Pridať `requirements.txt`** – reprodukovateľná inštalácia závislostí na inom počítači.
2. **Zjednotiť detekciu prvého skenovania** – `main.py` a samostatné `ai_prepare.py` momentálne určujú prvé skenovanie odlišne. Je vhodné používať rovnakú logiku.
3. **Pridať základné automatické testy** – najmä pre diff, parsovanie AI JSON a správanie pri chýbajúcich súboroch.
4. **Zlepšiť porovnávanie HTML** – pred diffom extrahovať relevantné pracovné ponuky a porovnávať ich podľa URL alebo stabilného identifikátora. Tým sa zníži šum z nepodstatných zmien stránky.
5. **Pridať kontrolný krok pred budúcim zápisom do WordPressu** – validácia JSON a kontrola, či sa pracovná ponuka skutočne zmenila, skôr než sa vykoná create/delete.

Najprv odporúčam dokončiť prvé tri body. WordPress integráciu má zmysel riešiť až po stabilnom a otestovanom JSON výstupe.
