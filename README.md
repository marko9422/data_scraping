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
