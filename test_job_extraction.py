
import os
import json
from datetime import datetime

from dotenv import load_dotenv
from openai import OpenAI

# Načítanie nastavení zo súboru .env
load_dotenv()

api_key = os.getenv("META_API_KEY")
model = os.getenv("META_MODEL", "muse-spark-1.3-contributor")

if not api_key:
    raise ValueError("Chýba META_API_KEY v súbore .env")

# Vytvorenie klienta Meta API
client = OpenAI(
    base_url="https://api.meta.ai/v1",
    api_key=api_key,
)

# Načítanie vyčisteného HTML
html_file = "scrape_output/page_ai.html"

with open(html_file, "r", encoding="utf-8") as file:
    html = file.read()

# Čas scrapovania
scraped_at = datetime.now().astimezone().isoformat(timespec="seconds")

# Pokyny pre AI
messages = [
    {
        "role": "system",
        "content": """
        Extrahuj z HTML konkrétne pracovné ponuky.

        Vráť iba validný JSON v tomto formáte:
        {
          "employer": "názov zamestnávateľa alebo Neznáme",
          "jobs": [
            {
              "title": "názov pracovnej pozície",
              "url": "úplný odkaz na ponuku"
            }
          ]
        }

        Pravidlá:
        - Uveď iba konkrétne pracovné pozície.
        - Ignoruj navigáciu, benefity, všeobecné stránky a kontaktné odkazy.
        - Ak názov zamestnávateľa nemožno zistiť, použi "Neznáme".
        - Nevymýšľaj chýbajúce údaje.
        - Pri URL použi úplný odkaz vrátane domény.
        - Nepridávaj žiadne vysvetlenie mimo JSON.
        """
    },
    {
        "role": "user",
        "content": f"Extrahuj pracovné ponuky z tohto HTML:\n\n{html}"
    }
]

# Odoslanie požiadavky AI
response = client.chat.completions.create(
    model=model,
    messages=messages,
    temperature=0,
    max_tokens=2000,
)

# Získanie odpovede AI
ai_text = response.choices[0].message.content

# Premena odpovede na Python objekt
try:
    result = json.loads(ai_text)
except (json.JSONDecodeError, TypeError):
    print("AI nevrátila validný JSON. Pôvodná odpoveď:")
    print(ai_text)
    raise

# Pridanie času scrapovania
result["scraped_at"] = scraped_at

# Výpis výsledku
print(json.dumps(result, ensure_ascii=False, indent=2))

# Výpis spotreby tokenov
if response.usage:
    print("\nSpotreba tokenov:")
    print(f"Vstup: {response.usage.prompt_tokens}")
    print(f"Výstup: {response.usage.completion_tokens}")
