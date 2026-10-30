
import os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

api_key = os.getenv("META_API_KEY")
model = os.getenv("META_MODEL", "muse-spark-1.3-contributor")

if not api_key:
    raise ValueError("Chýba META_API_KEY v súbore .env")

client = OpenAI(
    base_url="https://api.meta.ai/v1",
    api_key=api_key,
)

print(f"Testujem pripojenie k modelu: {model}")

response = client.chat.completions.create(
    model=model,
    messages=[
        {
            "role": "user",
            "content": (
                "Odpovedz iba slovom READY. "
                "Nepíš žiadne ďalšie vysvetlenie."
            ),
        }
    ],
)

print("\nOdpoveď modelu:")
print(response.choices[0].message.content)

if response.usage:
    print("\nSpotreba tokenov:")
    print(f"Vstup: {response.usage.prompt_tokens}")
    print(f"Výstup: {response.usage.completion_tokens}")
