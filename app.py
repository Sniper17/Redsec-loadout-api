from flask import Flask, request
import json
import os
import re
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from bs4 import BeautifulSoup

app = Flask(__name__)

DATA = os.path.join(os.path.dirname(__file__), "data", "weapons.json")
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; RedSecLoadoutAPI/3.0)"}
TIMEOUT = (5, 15)

ALIASES = {
    "svd": "SVDM", "svdm": "SVDM",
    "kord": "KORD 6P67", "kord6p67": "KORD 6P67",
    "pw5": "PW5A3", "pw5a3": "PW5A3",
    "m4": "M4A1", "m4a1": "M4A1",
    "sgx": "SGX",
    "sg553": "SG-553R", "sg553r": "SG-553R",
    "m16": "M16A4", "m16a4": "M16A4",
    "b36": "B36A4", "b36a4": "B36A4",
    "nvo": "NVO-228E", "nvo228e": "NVO-228E",
    "rpk": "RPK-74M", "rpk74m": "RPK-74M",
    "m2010": "M2010 ESR", "m2010esr": "M2010 ESR",
    "psr": "PSR", "l115": "L115",
    "kts": "KTS100 MK8", "kts100": "KTS100 MK8",
    "cz": "CZ3A1", "cz3a1": "CZ3A1",
    "pp19": "PP-19", "drsiar": "DRS-IAR",
    "qbz": "QBZ-192", "qbz192": "QBZ-192",
}

SOURCES = [
    ("BattlefieldMeta", "https://battlefieldmeta.gg/pt/melhores-configuracoes/{slug}"),
    ("BattlefieldMeta EN", "https://battlefieldmeta.gg/best-loadouts/{slug}"),
]

SLOT_MAP = {
    "barrel": "Cano",
    "underbarrel": "Acoplamento",
    "under barrel": "Acoplamento",
    "ammunition": "Munição",
    "muzzle": "Boca",
    "magazine": "Carregador",
    "scope": "Mira",
    "optic": "Mira",
    "right accessory": "Acessório",
    "top accessory": "Acessório",
    "left accessory": "Acessório",
    "ergonomics": "Ergonomia",
}

def norm(value):
    value = unicodedata.normalize("NFKD", str(value or "").lower().strip())
    return "".join(c for c in value if not unicodedata.combining(c))

# Correção principal da v2:
# compact() era chamado por canonical(), mas não existia no arquivo publicado.
def compact(value):
    return re.sub(r"[^a-z0-9]+", "", norm(value))

def slug(value):
    return re.sub(r"[^a-z0-9]+", "-", norm(value)).strip("-")

def load_catalog():
    with open(DATA, encoding="utf-8") as f:
        return json.load(f)

def canonical(query):
    key = compact(query)

    if key in ALIASES:
        return ALIASES[key]

    for name, item in load_catalog().get("weapons", {}).items():
        aliases = item.get("aliases", [])
        if key == compact(name) or key in [compact(x) for x in aliases]:
            return name

    return query.strip()

def get_text_tokens(html):
    soup = BeautifulSoup(html, "html.parser")
    result = []

    for text in soup.stripped_strings:
        value = " ".join(str(text).split()).strip()
        if value and len(value) <= 120:
            result.append(value)

    return result

def is_slot(value):
    return norm(value) in SLOT_MAP

def is_noise(value):
    n = norm(value)

    if re.fullmatch(r"[\d\s/+\-.]+", value):
        return True

    return n in {
        "level", "nivel", "nível", "premium",
        "recommended", "recomendado",
        "lowest recoil", "menor recuo",
        "fastest ads", "hip fire",
        "100/100", "95/100", "90/100",
    }

def extract_recommended(tokens):
    start = None

    for i, token in enumerate(tokens):
        if norm(token) in {"recommended", "recomendado"}:
            start = i + 1
            break

    if start is None:
        return []

    end = len(tokens)

    for i in range(start, len(tokens)):
        if norm(tokens[i]) in {
            "lowest recoil",
            "menor recuo",
            "fastest ads",
            "hip fire",
        }:
            end = i
            break

    section = tokens[start:end]
    attachments = []
    seen_slots = set()

    # Nas páginas atuais, o nome do acessório aparece próximo do slot.
    # Procuramos o slot e retrocedemos até encontrar um texto útil.
    for i, token in enumerate(section):
        slot = SLOT_MAP.get(norm(token))

        if not slot or slot in seen_slots:
            continue

        j = i - 1

        while j >= 0 and (is_noise(section[j]) or is_slot(section[j])):
            j -= 1

        if j >= 0:
            value = section[j].strip()

            if value and len(value) <= 90:
                attachments.append({
                    "slot": slot,
                    "name": value
                })
                seen_slots.add(slot)

    return attachments[:8]

def fetch_source(source_name, url, weapon):
    try:
        response = requests.get(
            url,
            headers=HEADERS,
            timeout=TIMEOUT
        )

        if response.status_code != 200:
            return None

        tokens = get_text_tokens(response.text)
        attachments = extract_recommended(tokens)

        # Não aceita uma resposta incompleta como "loadout confirmado".
        if len(attachments) < 4:
            return None

        return {
            "weapon": weapon,
            "attachments": attachments,
            "source": source_name,
            "source_url": url,
        }

    except Exception:
        return None

def find_loadout(query):
    weapon = canonical(query)
    weapon_slug = slug(weapon)

    jobs = [
        (name, url.format(slug=weapon_slug), weapon)
        for name, url in SOURCES
    ]

    results = []

    with ThreadPoolExecutor(max_workers=len(jobs)) as executor:
        futures = [
            executor.submit(fetch_source, *job)
            for job in jobs
        ]

        for future in as_completed(futures):
            result = future.result()
            if result:
                results.append(result)

    # Primeira fonte é preferida; nunca mistura acessórios entre fontes.
    priority = {
        "BattlefieldMeta": 0,
        "BattlefieldMeta EN": 1,
    }

    results.sort(
        key=lambda item: priority.get(item["source"], 99)
    )

    return results[0] if results else None

def format_loadout(loadout):
    parts = [f"🔫 {loadout['weapon']}"]

    for attachment in loadout["attachments"]:
        parts.append(
            f"{attachment['slot']}: {attachment['name']}"
        )

    return " • ".join(parts)

@app.get("/")
def home():
    return "🔥 REDSEC Loadout API v3 online!"

@app.get("/status")
def status():
    catalog = load_catalog()

    return {
        "online": True,
        "api_version": "3.0",
        "game": "Battlefield REDSEC",
        "sources": [source[0] for source in SOURCES],
        "cached_weapons": len(catalog.get("weapons", {})),
    }

@app.get("/classe")
def classe():
    weapon_query = request.args.get("arma", "").strip()

    if not weapon_query:
        return "⚠️ Informe a arma. Exemplo: /classe?arma=svdm"

    loadout = find_loadout(weapon_query)

    if loadout:
        return format_loadout(loadout)

    return (
        f"⚠️ Não encontrei um loadout confiável para "
        f"'{weapon_query}'."
    )

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000))
    )
