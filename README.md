# Data Scraping – pracovné ponuky

Malý Python projekt, ktorý sleduje pracovné ponuky na stránkach hotelov a gastro prevádzok vo Švajčiarsku.

**Čo robí:** stiahne stránku → vyčistí HTML → porovná starú a novú verziu → pošle zmeny do Meta AI → vypíše výsledok v JSON.

**WordPress zatiaľ nie je prepojený.** Projekt nič neposiela do WordPressu.

---

## 1. Najčastejšie príkazy

Príkazy spúšťaj v termináli v priečinku projektu.

### Hlavný príkaz – celý proces pre jeden hotel

```bash
python main.py stoos-hotels
python main.py gasthof-zum-ochsen
python main.py les-trois-rois
```

Čo sa stane:
1. Stiahne stránku zamestnávateľa.
2. Uloží nové HTML a predchádzajúcu verziu.
3. Porovná ich.
4. Pošle zmeny do Meta AI.
5. Vypíše výsledok v termináli.

Názov za `main.py` je slug z `sites.json`.

### Stiahnuť HTML bez AI

Iba jeden zamestnávateľ:

```bash
python scrape.py stoos-hotels
```

Všetci zamestnávatelia:

```bash
python scrape.py
```

Tento príkaz iba stiahne a uloží HTML. AI sa nespustí.

### Otestovať vlastné HTML súbory

Priprav si tieto dva súbory v priečinku `scrape_output`:

```text
scrape_output/
├── test.html       # nová verzia
└── test-old.html   # stará verzia
```

**Testovací zamestnávateľ** je nastavený priamo v `test.py` cez konštantu `TEST_EMPLOYER_SLUG` (aktuálne `stoos-hotels`). Tento slug sa používa na načítanie údajov zo `sites.json`, rozpoznanie relatívnych URL a vytvorenie rovnakého `job_id` ako v hlavnom workflow. Pri testovaní iného zamestnávateľa zmeň túto konštantu.

Spustenie kompletného testu:

```bash
python test.py
```

Skript porovná `test.html` s `test-old.html`. Ak nájde rozdiely, odošle ich do Meta AI a následne vytvorí finálny JSON rovnakým spôsobom ako `ai_prepare.py` – vrátane `job_id`, `job_category` a údajov zamestnávateľa. Ak sú súbory identické, AI sa nevolá.

Ak chceš iba porovnanie bez AI:

```bash
python test.py --no-ai
```

Tento režim vypíše rozdiely medzi testovacími HTML súbormi a skončí. Meta AI sa nespustí a finálny JSON sa nevytvorí.

Testovací režim používa iba lokálne súbory. Nespúšťa scraping, nemení HTML súbory a nikdy nevolá WordPress API.

### Iba porovnať HTML

```bash
python compare.py
```

Porovná predvolené súbory pre Stoos Hotels.

Vlastné súbory:

```bash
python compare.py test.html test-old.html
```

Názvy súborov sa hľadajú v priečinku `scrape_output`.

### Spustiť iba AI spracovanie

```bash
python ai_prepare.py stoos-hotels
```

Použije už uložené HTML pre daný slug, porovná ho a pošle zmeny do Meta AI. Nespúšťa nový scraping.

---

## 2. Čo robia jednotlivé súbory

| Súbor | Jednoduché vysvetlenie |
|---|---|
| `main.py` | Hlavný príkaz. Spustí celý proces pre jedného zamestnávateľa. |
| `scrape.py` | Stiahne webovú stránku a uloží vyčistené HTML. |
| `compare.py` | Porovná dve HTML verzie a vypíše, čo pribudlo a čo zmizlo. |
| `ai_prepare.py` | Pošle zmeny do Meta AI a pripraví výsledný JSON. |
| `test.py` | Testuje vlastné súbory `test.html` a `test-old.html`. |
| `sites.json` | Zoznam webov, ktoré sa majú sledovať, spolu s ich údajmi. |
| `.env` | Obsahuje API kľúč pre Meta AI. |
| `.gitignore` | Zoznam súborov, ktoré sa nemajú ukladať na GitHub. |

### Čo sa stane, keď spustím jednotlivé Python súbory?

- `python main.py <slug>` – spustí celý proces.
- `python scrape.py <slug>` – stiahne HTML a uloží ho. Ak už existuje staršia verzia, presunie ju do súboru s `-old`.
- `python scrape.py` – stiahne HTML všetkých webov v `sites.json`.
- `python compare.py` – iba porovná HTML a vypíše zmeny.
- `python ai_prepare.py <slug>` – použije uložené HTML a zavolá Meta AI.
- `python test.py` – porovná `test.html` a `test-old.html`; ak nájde diff, zavolá Meta AI a vytvorí finálny JSON.
- `python test.py --no-ai` – iba porovná testovacie HTML a vypíše diff, bez AI.

**Pozor:** samostatné spustenie `scrape.py` môže prepísať aktuálne HTML a uložiť jeho predchádzajúcu verziu. Príkazy s Meta AI môžu spotrebovať API tokeny.

---

## 3. Ako fungujú uložené HTML súbory

Pre každý web sa ukladajú dve verzie. Napríklad:

```text
scrape_output/
├── stoos-hotels.html
└── stoos-hotels-old.html
```

- `stoos-hotels.html` – aktuálna verzia stránky.
- `stoos-hotels-old.html` – predchádzajúca verzia.

Pri ďalšom scrapovaní sa aktuálna verzia najskôr skopíruje do `-old.html` a potom sa uloží nová.

Prvýkrát ešte stará verzia neexistuje. Vtedy sa celé aktuálne HTML pošle do AI, aby našla pracovné ponuky.

Priečinok `scrape_output` je lokálny a neukladá sa na GitHub.

---

## 4. Zoznam webov – sites.json

Každý web má tieto údaje:

- `name` – názov zamestnávateľa.
- `slug` – krátky názov používaný v príkazoch.
- `url` – adresa kariérnej stránky.
- `address` – adresa zamestnávateľa.
- `canton` – kantón.
- `scope` – napríklad `local` alebo `national`.

Ak chceš pridať ďalší web, doplň ho do `sites.json`.

---

## 5. Nastavenie a knižnice

Použité Python knižnice:

- **Crawl4AI** – otvorí a stiahne webovú stránku.
- **BeautifulSoup** – vyčistí HTML od nepotrebného obsahu.
- **OpenAI SDK** – posiela požiadavky do Meta AI API.
- **python-dotenv** – načíta API kľúč zo súboru `.env`.

V koreňovom priečinku musíš mať súbor `.env`:

```env
META_API_KEY=tvoj_api_kluc
META_MODEL=muse-spark-1.3-contributor
```

Inštalácia knižníc:

```bash
pip install crawl4ai beautifulsoup4 openai python-dotenv
```

Ak Crawl4AI ešte nemá pripravený prehliadač:

```bash
crawl4ai-setup
```

---

## 6. Dôležité

- Projekt zatiaľ **neodosiela nič do WordPressu**. Iba vypisuje JSON.
- Ak pracovná ponuka zmizne zo stránky, nemusí to automaticky znamenať, že bola obsadená.
- Predchádzajúce HTML súbory sa pri ďalšom scrapovaní prepíšu novšou zálohou.
- Testuj zmeny najskôr cez `test.py`, aby si nemusel opakovane sťahovať reálne stránky.


---

## 7. JOB_ID a kategórie pracovných ponúk

Každá pracovná ponuka dostane stabilné unikátne pole `job_id`. Python ho vypočíta, AI ho negeneruje.

### Ako sa vytvára JOB_ID

Základom je kombinácia:

```text
employer_slug + normalized_job_url
```

Napríklad:

```text
stoos-hotels|https://stoos-hotels.ch/jobs/koch
```

Python z tejto kombinácie vypočíta SHA-256 hash. Rovnaký zamestnávateľ a rovnaká normalizovaná URL vždy vytvoria rovnaké `job_id`.

- Názov pracovnej pozície nie je súčasťou ID.
- Zmena názvu pozície nemení ID.
- Rovnaká URL u iného zamestnávateľa vytvorí iné ID.
- Zmena URL vytvorí nové ID.
- Pred hashovaním sa URL normalizuje: odstráni sa fragment, bežné tracking parametre a koncová lomka (okrem koreňovej URL). Ostatné query parametre zostávajú, pretože môžu identifikovať konkrétnu ponuku.

### Kategórie

Pri akcii `create` AI priradí presne jednu kategóriu podľa názvu pracovnej pozície. Môže vybrať iba z tohto pevného zoznamu:

| JSON hodnota | Význam |
|---|---|
| `kitchen` | Kitchen – kuchyňa |
| `service` | Service – servis |
| `reception` | Reception – recepcia |
| `housekeeping` | Housekeeping – upratovanie a izby |
| `management` | Management – vedenie a manažment |
| `office` | Office – administratíva, HR, účtovníctvo, marketing |
| `bar` | Bar – barman, barista |
| `wellness` | Wellness – spa a masáže |
| `technical` | Technical – údržba a technické služby |
| `apprenticeship` | Apprenticeship – učni, stáže a prax |
| `other` | Other – ostatné pozície |

AI nesmie vytvárať vlastné kategórie. Python kontroluje, či je vrátená kategória v povolenom zozname. Pri `delete` sa kategória neposiela.

### Príklad výsledného JSON – create

AI vráti názov, URL a kategóriu. Python doplní `job_id`, údaje zamestnávateľa a dátum:

```json
{
  "changes": [
    {
      "action": "create",
      "job_id": "sha256-hash-generated-by-python",
      "job_title": "Koch / Köchin",
      "job_url": "https://example.ch/jobs/koch",
      "employer_name": "Stoos Hotels",
      "job_location": "Ringstrasse 10, 6433 Stoos, Switzerland",
      "source_url": "https://stoos-hotels.ch/karriere/",
      "canton": "Schwyz",
      "scope": "local",
      "employer_slug": "stoos-hotels",
      "job_category": "kitchen",
      "employment_type": "100%",
      "job_description": "Preparing meals and working in the kitchen",
      "scraped_at": "2026-11-23"
    }
  ]
}
```

### Príklad výsledného JSON – delete

Python vypočíta rovnaké `job_id` z `employer_slug` a normalizovanej URL starej ponuky. Kategória ani ostatné údaje zamestnávateľa pri odstránení nie sú potrebné.

```json
{
  "changes": [
    {
      "action": "delete",
      "job_id": "sha256-hash-generated-by-python",
      "job_title": "Koch / Köchin",
      "job_url": "https://example.ch/jobs/koch"
    }
  ]
}
```

**Dôležité pre budúce prepojenie s WordPressom:** WordPress musí ukladať `job_id` ako vlastné pole. Pri CREATE sa podľa neho bude kontrolovať duplicita a pri DELETE sa podľa neho nájde presná ponuka.

---

## 8. Ako vyzerá JSON z AI

Pri bežnom workflowe (`main.py` alebo `ai_prepare.py`) AI vracia objekt `changes`.

### Nová pracovná ponuka – create

Toto sú polia, ktoré AI dostáva v zadaní:

```json
{
  "changes": [
    {
      "action": "create",
      "job_title": "Koch / Köchin",
      "job_url": "https://example.ch/jobs/koch",
      "job_category": "kitchen",
      "employment_type": "100%",
      "job_description": "Príprava jedál a práca v kuchyni"
    }
  ]
}
```

AI dodáva:
- `action` – `create`
- `job_title` – názov pracovnej pozície
- `job_url` – odkaz na pracovnú ponuku
- `job_category` – jedna povolená anglická kategória (napr. `kitchen`, `service`)
- `employment_type` – úväzok, ak ho vie z HTML zistiť
- `job_description` – popis práce, ak ho vie z HTML zistiť

Posledné dve polia AI nemusí vrátiť, ak ich nevie spoľahlivo zistiť.

### Zmiznutá pracovná ponuka – delete

```json
{
  "changes": [
    {
      "action": "delete",
      "job_id": "sha256-hash-generated-by-python",
      "job_title": "Koch / Köchin",
      "job_url": "https://example.ch/jobs/koch"
    }
  ]
}
```

AI dodáva:
- `action` – `delete`
- `job_title` – názov pozície, ak ho vie zistiť
- `job_url` – odkaz, ak ho vie zistiť

Pri `delete` Python nepridáva údaje zamestnávateľa.

### Čo doplní Python zo sites.json?

Pri bežnom workflowe Python vezme údaje zamestnávateľa z príslušného záznamu v `sites.json` a doplní ich k zmene typu `create`.

| Výsledné JSON pole | Odkiaľ pochádza |
|---|---|
| `action` | AI |
| `job_title` | AI |
| `job_url` | AI; Python prevedie relatívny odkaz na úplnú a normalizovanú URL |
| `job_id` | Python – SHA-256 z `employer_slug + normalized_job_url` |
| `job_category` | AI – jedna kategória z pevného povoleného zoznamu |
| `employer_name` | `name` zo sites.json |
| `job_location` | `address` zo sites.json |
| `source_url` | `url` zo sites.json |
| `canton` | `canton` zo sites.json |
| `scope` | `scope` zo sites.json |
| `employer_slug` | `slug` zo sites.json |
| `employment_type` | AI |
| `job_description` | AI |
| `scraped_at` | Python – aktuálny dátum |

Príklad výsledného JSON pre `create` po doplnení údajov Python-om:

```json
{
  "changes": [
    {
      "action": "create",
      "job_title": "Koch / Köchin",
      "job_url": "https://example.ch/jobs/koch",
      "employer_name": "Stoos Hotels",
      "job_location": "Ringstrasse 10, 6433 Stoos, Switzerland",
      "source_url": "https://stoos-hotels.ch/karriere/",
      "canton": "Schwyz",
      "scope": "local",
      "employer_slug": "stoos-hotels",
      "job_category": "kitchen",
      "employment_type": "100%",
      "job_description": "Príprava jedál a práca v kuchyni",
      "scraped_at": "2026-11-22"
    }
  ]
}
```

Pri `delete` Python doplní rovnaké `job_id` vypočítané z employer slug a URL. Výsledok bude mať tento tvar:

```json
{
  "changes": [
    {
      "action": "delete",
      "job_title": "Koch / Köchin",
      "job_url": "https://example.ch/jobs/koch"
    }
  ]
}
```

Ak niektorú voliteľnú hodnotu Python nevie získať, doplní text `Unavailable`. Bez platnej URL však `job_id` nemožno bezpečne vytvoriť a spracovanie danej zmeny skončí chybou. Dátum `scraped_at` vytvára Python, nie AI.

**Poznámka k test.py:** testovací skript používa rovnaký AI prompt, povolené kategórie, URL normalizáciu a tvorbu finálneho JSON ako hlavný workflow. Employer slug sa nezadáva v príkazovom riadku; je nastavený v konštante `TEST_EMPLOYER_SLUG` v `test.py`. Skript používa iba lokálne testovacie HTML a nikdy nespúšťa scraping ani WordPress API.
