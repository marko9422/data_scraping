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

Potom spusti:

```bash
python test.py
```

Porovná súbory, vypíše zmeny a odošle ich do Meta AI.

Ak chceš iba porovnanie bez AI:

```bash
python test.py --no-ai
```

Testovací režim nič nesťahuje a nemení tvoje HTML súbory.

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
- `python test.py` – porovná testovacie HTML a zavolá Meta AI.
- `python test.py --no-ai` – iba porovná testovacie HTML, bez AI.

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

## 7. Ako vyzerá JSON z AI

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
- `employment_type` – úväzok, ak ho vie z HTML zistiť
- `job_description` – popis práce, ak ho vie z HTML zistiť

Posledné dve polia AI nemusí vrátiť, ak ich nevie spoľahlivo zistiť.

### Zmiznutá pracovná ponuka – delete

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
| `job_url` | AI; Python prevedie relatívny odkaz na úplnú URL pomocou adresy webu |
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
      "employment_type": "100%",
      "job_description": "Príprava jedál a práca v kuchyni",
      "scraped_at": "2026-11-22"
    }
  ]
}
```

Pri `delete` Python výsledok ponechá len v tomto tvare:

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

Ak niektorú hodnotu Python nevie získať, doplní text `Unavailable`. Dátum `scraped_at` vytvára Python, nie AI.

**Poznámka k test.py:** testovací skript má vlastný AI prompt. Vypíše priamo JSON od AI a nedopĺňa doň údaje zo `sites.json`. Preto jeho výstup nemusí obsahovať polia zamestnávateľa ani `scraped_at`.
