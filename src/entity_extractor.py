"""
TFG: Generació i Validació d'Hipòtesis Arqueològiques
Pipeline LLM - Extracció d'Entitats Geogràfiques
=====================================================
Intenta usar Claude (cloud) i fa fallback a Ollama (local).
Configuració via .env — veure .env per detalls.
"""

import json
import os
import re
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Optional

from dotenv import load_dotenv

# Carregar variables d'entorn
load_dotenv(Path(__file__).parent / ".env")

# ── Configuració ─────────────────────────────────────────────────────────────

LLM_PROVIDER    = os.getenv("LLM_PROVIDER", "claude").lower()
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL    = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-20250514")
OLLAMA_MODEL   = os.getenv("OLLAMA_MODEL", "qwen2.5:14b")
OLLAMA_HOST    = os.getenv("OLLAMA_HOST", "http://localhost:11434")
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.1"))
LLM_MAX_TOKENS  = int(os.getenv("LLM_MAX_TOKENS", "8192"))

OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(exist_ok=True)


# ── Dataclass per a cada entitat extreta ──────────────────────────────────────

@dataclass
class GeographicEntity:
    name: str                          # Nom del lloc
    entity_type: str                   # 'river' | 'settlement' | 'region' | 'route' | 'other'
    description: str                   # Descripció original del text
    context: str                       # Fragment de text on apareix
    lat: Optional[float] = None        # Coordenada si s'esmenta al text
    lon: Optional[float] = None
    confidence: str = "low"            # 'high' | 'medium' | 'low'
    source_text: str = ""              # Nom del text font


# ── Prompt principal ──────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are a geographic entity extraction API specialized in historical and archaeological texts from South American expeditions (16th-19th centuries). These texts may be written in old Spanish, Portuguese, or include indigenous language place names (Quechua, Aymara, Guarani, Tupi, Mojeno, etc.). Place names may use archaic spelling (e.g., "Mojos" for "Moxos", "Chiquitos" for "Chiquitania").

You are NOT a conversational assistant. You do NOT summarize, explain, or comment on the text.

Your ONLY function is to output a JSON array of geographic entities found in the input text.

Each object in the array must have these fields:
- "name": the place name exactly as written in the text (preserve original spelling)
- "entity_type": one of ["river", "settlement", "region", "route", "mountain", "other"]
- "description": any physical or cultural description of the place mentioned in the text
- "context": the exact sentence or phrase where this place appears
- "lat": your best estimate of the latitude (decimal degrees, negative for south). You MUST provide coordinates for every entity — see coordinate rules below.
- "lon": your best estimate of the longitude (decimal degrees, negative for west). You MUST provide coordinates for every entity — see coordinate rules below.
- "confidence": "high" or "medium" ONLY (see criteria below)

===============================================================
COORDINATE ESTIMATION RULES:
===============================================================

For the lat and lon fields, you MUST provide your best estimate of geographic coordinates for EVERY entity. Use your knowledge of South American geography and history. Do NOT leave lat/lon as null unless you truly have zero basis to estimate.

Reference coordinates for calibration:
- Santa Cruz de la Sierra = lat -17.78, lon -63.18
- río Mamoré = lat -10.15, lon -65.37
- Moxos / Llanos de Mojos = lat -15.28, lon -65.61
- Cochabamba = lat -17.41, lon -66.17
- La Paz = lat -16.50, lon -68.15
- Trinidad (Beni) = lat -14.83, lon -64.90
- río Beni = lat -14.82, lon -67.53
- río Guaporé = lat -12.68, lon -63.42
- Chiquitos = lat -16.33, lon -60.75
- lago Titicaca = lat -15.84, lon -69.33
- Iquitos = lat -3.75, lon -73.25
- Manaus = lat -3.12, lon -60.02

For lesser-known places (indigenous missions, local streams, named parajes), estimate based on textual context. For example:
- If the text says a place is "near río Beni", place it near the Beni river coordinates.
- If it says a mission is "in Moxos province", estimate coordinates within the Moxos region.
- If a settlement is described as "between Santa Cruz and Cochabamba", interpolate.
Only use null if you truly have no basis to estimate (no geographic context at all in the text).

===============================================================
WHAT TO EXTRACT (only proper-named geographic entities):
===============================================================

- Proper-named places WITHIN the Amazonian study area: "Santa Cruz de la Sierra", "rio Amazonas", "Llanos de Mojos", "Cochabamba"
- Rivers WITH a proper name: "rio Beni", "rio Mamore", "rio Guapore", "arroyo Yapacani"
- Named regions: "Gran Chaco", "Alto Peru", "Chiquitos", "Moxos"
- Named settlements: cities, towns, villages, missions, forts, reductions with a proper name
- Named landforms: "lago Titicaca", "Cordillera de los Andes", "cerro Potosi", "sierra de Aguarague"

===============================================================
WHAT TO NEVER EXTRACT (strict exclusions):
===============================================================

1. GENERIC NOUNS without a proper name: "el rio", "los rios", "la laguna", "el bosque", "pantanos", "montanas", "llanuras", "campos", "esteros", "arroyo", "cerro", "monte" (bare common nouns).
2. LANDSCAPE DESCRIPTIONS: "orillas de los rios", "bordes de los pantanos", "campos abiertos", "selvas virgenes", "llanuras gredosas", "terrenos quebrados", "campanas llanas", "tierras bajas", "tierras altas".
3. FLORA, FAUNA, or CLIMATE vocabulary: "arboles muertos", "charcos de agua", "bancos de arena", "malezas", "matorrales", "zarzales", "vegetacion espesa".
4. BUILDINGS or STRUCTURES (unless they ARE the name of a settlement): "iglesia de la Merced", "convento", "Plaza Mayor", "Cabildo", "muelle". Exception: "Mision de San Ignacio" IS a settlement.
5. GENERIC DIRECTION or RELATIVE TERMS: "margen derecha", "costa brasilena", "orillas fangosas", "aguas arriba", "rio arriba".
6. ALL EUROPEAN PLACES, always: Paris, Francia, Nantes, La Rochelle, Coueron, Poitou, Bretana, Tenerife, Cadiz, Madrid, Lisboa, etc. No exceptions.
7. BARE CONTINENTS as standalone terms: "Europa", "Africa", "America".
8. PLACES OUTSIDE THE AMAZONIAN STUDY AREA, even if they are real South American proper names. The study area is: Amazonia, Bolivia, Peru, western Brazil, eastern Ecuador, and southern Colombia (roughly lat -20 to 5, lon -80 to -45). Do NOT extract:
   - Rio de la Plata region: Buenos Aires, Montevideo, Corrientes, Asuncion, Rosario, Santa Fe, Entre Rios, Banda Oriental.
   - Patagonia and southern Argentina: Patagonia, Tierra del Fuego, Cabo de Hornos, Bahia Blanca, Carmen de Patagones.
   - Coastal Chile: Santiago, Valparaiso, Arica, Iquique, Atacama.
   - Atlantic coast of Brazil: Rio de Janeiro, Bahia, Pernambuco, Sao Paulo.
   - Any other place clearly outside the Amazonian basin and adjacent zones.
   The author (d'Orbigny and others) traveled widely across South America, but we ONLY care about the Amazonian basin and surrounding regions (Bolivia, Peru, western Brazil, eastern Ecuador, southern Colombia). If a place is mentioned as a departure/arrival port or biographical detail outside this zone, skip it.

THE KEY TEST: Does the phrase contain a PROPER NAME that identifies a specific, unique geographic location WITHIN THE AMAZONIAN STUDY AREA? If yes, extract it. If it is outside the study area, or it is just a common noun or a landscape description, DO NOT extract it.

===============================================================
ENTITY TYPE CRITERIA:
===============================================================

- "settlement": any ciudad, pueblo, villa, aldea, mision, fuerte, reduccion, comandancia, puerto WITH a proper name.
- "river": rios, arroyos, riachos, afluentes, lagunas, lagos WITH a proper name.
- "region": provincias, comarcas, regiones, territorios, llanos, departamentos, paises WITH a proper name.
- "route": caminos, rutas, pasos WITH a proper name.
- "mountain": sierras, cordilleras, cerros, picos, cabos WITH a proper name.
- "other": AVOID. Only use if the entity does not fit any category above AND is clearly a real place with a proper name.

===============================================================
CONFIDENCE CRITERIA (only "high" or "medium" -- NEVER use "low"):
===============================================================

- "high": unambiguous proper name of a well-known, real place WITHIN the study area (rio Amazonas, Cochabamba, lago Titicaca, Cordillera de los Andes, Potosi, Santa Cruz de la Sierra).
- "medium": proper-named place that is real but minor or harder to locate precisely (a named indigenous mission, a local named stream, a named paraje -- e.g., "mision de San Ignacio de Moxos", "arroyo Yapacani").
- NEVER assign "low". If you are not confident that something is a real, named place, simply DO NOT extract it.

===============================================================
FEW-SHOT EXAMPLES:
===============================================================

EXAMPLE 1:
Input: "Partimos de Santa Cruz de la Sierra el 15 de agosto, siguiendo el curso del rio Piray hasta llegar a las misiones de Chiquitos. El terreno era llano y los bosques densos."
Output:
[
  {"name": "Santa Cruz de la Sierra", "entity_type": "settlement", "description": "punto de partida de la expedicion", "context": "Partimos de Santa Cruz de la Sierra el 15 de agosto", "lat": -17.78, "lon": -63.18, "confidence": "high"},
  {"name": "rio Piray", "entity_type": "river", "description": "rio cuyo curso se siguio desde Santa Cruz", "context": "siguiendo el curso del rio Piray", "lat": -17.65, "lon": -63.30, "confidence": "high"},
  {"name": "Chiquitos", "entity_type": "region", "description": "region donde se encontraban las misiones", "context": "llegar a las misiones de Chiquitos", "lat": -16.33, "lon": -60.75, "confidence": "high"}
]
NOTE: "bosques" and "terreno llano" are NOT extracted -- they are generic landscape descriptions. All entities have coordinate estimates.

EXAMPLE 2:
Input: "Navegamos por el rio Mamore hasta su confluencia con el Beni, pasando por la mision de San Ignacio de Moxos. Las orillas estaban cubiertas de vegetacion espesa y pantanos."
Output:
[
  {"name": "rio Mamore", "entity_type": "river", "description": "rio navegado hasta confluencia con el Beni", "context": "Navegamos por el rio Mamore hasta su confluencia con el Beni", "lat": -10.15, "lon": -65.37, "confidence": "high"},
  {"name": "Beni", "entity_type": "river", "description": "rio que confluye con el Mamore", "context": "su confluencia con el Beni", "lat": -14.82, "lon": -67.53, "confidence": "high"},
  {"name": "San Ignacio de Moxos", "entity_type": "settlement", "description": "mision visitada durante la navegacion", "context": "pasando por la mision de San Ignacio de Moxos", "lat": -14.95, "lon": -65.63, "confidence": "high"},
  {"name": "Moxos", "entity_type": "region", "description": "region de la mision de San Ignacio", "context": "la mision de San Ignacio de Moxos", "lat": -15.28, "lon": -65.61, "confidence": "medium"}
]
NOTE: "orillas", "vegetacion espesa", and "pantanos" are NOT extracted -- they are landscape/flora vocabulary.

EXAMPLE 3:
Input: "D'Orbigny nacio en Coueron, cerca de Nantes, y estudio en Paris. Se embarco en Buenos Aires y remonto el Parana hasta Corrientes, antes de internarse en los llanos de Mojos."
Output:
[
  {"name": "llanos de Mojos", "entity_type": "region", "description": "destino final del viaje de D'Orbigny", "context": "internarse en los llanos de Mojos", "lat": -15.28, "lon": -65.61, "confidence": "high"}
]
NOTE: Coueron, Nantes, Paris are European biographical context -- NOT extracted. Buenos Aires, Parana, and Corrientes are real proper names but OUTSIDE the Amazonian study area -- NOT extracted. Only "llanos de Mojos" falls within the study zone.

===============================================================
OUTPUT RULES:
===============================================================

- Respond ONLY with a valid JSON array. No prose, no markdown, no explanation.
- If no geographic entities are found, respond with exactly: []
- Never wrap the JSON in code blocks or add any text before or after it.
- NEVER wrap the response in markdown code blocks (no ```json). Return the raw JSON array directly.
- Be SELECTIVE. It is far better to miss a marginal entity than to extract garbage. Aim for precision over recall."""

USER_PROMPT_TEMPLATE = """Extract ONLY proper-named geographic entities from the following historical text. Remember: no generic landscape words, no flora/fauna, no buildings, no European biographical places. Only real places with proper names.

\"\"\"
{text}
\"\"\"
"""


# ── Funcions per cridar els LLMs ─────────────────────────────────────────────

def _query_claude(user_message: str) -> str:
    """Envia un prompt a Claude (Anthropic) i retorna la resposta com a string."""
    import anthropic

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=LLM_MAX_TOKENS,
        temperature=LLM_TEMPERATURE,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )
    return response.content[0].text


def _query_ollama(user_message: str) -> str:
    """Envia un prompt a Ollama i retorna la resposta com a string."""
    import ollama

    response = ollama.chat(
        model=OLLAMA_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
        options={"temperature": LLM_TEMPERATURE, "num_predict": LLM_MAX_TOKENS},
        format="json",
    )
    return response.message.content


def query_llm(user_message: str) -> str:
    """
    Intenta el provider preferit (per defecte Claude).
    Si falla, fa fallback a l'altre provider.
    """
    providers = (
        [("claude", _query_claude), ("ollama", _query_ollama)]
        if LLM_PROVIDER == "claude"
        else [("ollama", _query_ollama), ("claude", _query_claude)]
    )

    for name, fn in providers:
        try:
            result = fn(user_message)
            return result
        except Exception as e:
            print(f"   ⚠️  {name} ha fallat: {e}")
            if name == providers[0][0] and len(providers) > 1:
                print(f"   🔄 Fallback a {providers[1][0]}...")
            continue

    raise RuntimeError("Cap provider LLM disponible (Claude i Ollama han fallat)")


# ── Funció per netejar i parsejar JSON ───────────────────────────────────────

def _sanitize_json_escapes(s: str) -> str:
    """
    Sanititza un string JSON reemplaçant backslashes invàlides.
    """
    result = []
    i = 0
    in_string = False
    while i < len(s):
        ch = s[i]

        if not in_string:
            if ch == '"':
                in_string = True
            result.append(ch)
            i += 1
            continue

        if ch == '"':
            in_string = False
            result.append(ch)
            i += 1
            continue

        if ch == '\\':
            if i + 1 < len(s):
                nxt = s[i + 1]
                if nxt in ('"', '\\', '/', 'n', 'r', 't', 'b', 'f'):
                    result.append(ch)
                    result.append(nxt)
                    i += 2
                    continue
                elif nxt == 'u':
                    hex_part = s[i+2:i+6]
                    if len(hex_part) == 4 and all(c in '0123456789abcdefABCDEF' for c in hex_part):
                        result.append(s[i:i+6])
                        i += 6
                        continue
                    else:
                        result.append('\\\\')
                        i += 1
                        continue
                else:
                    result.append('\\\\')
                    i += 1
                    continue
            else:
                result.append('\\\\')
                i += 1
                continue
        else:
            result.append(ch)
            i += 1

    return "".join(result)


def _aggressive_json_cleanup(s: str) -> str:
    """
    Neteja agressiva: elimina caràcters de control i backslashes
    problemàtiques quan la sanitització normal falla.
    """
    s = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]', '', s)
    result = []
    i = 0
    in_string = False
    while i < len(s):
        ch = s[i]
        if not in_string:
            if ch == '"':
                in_string = True
            result.append(ch)
            i += 1
            continue
        if ch == '"':
            in_string = False
            result.append(ch)
            i += 1
            continue
        if ch == '\\':
            if i + 1 < len(s) and s[i + 1] in ('"', '\\', '/', 'n', 'r', 't', 'b', 'f'):
                result.append(ch)
                result.append(s[i + 1])
                i += 2
                continue
            elif i + 1 < len(s) and s[i + 1] == 'u':
                hex_part = s[i+2:i+6]
                if len(hex_part) == 4 and all(c in '0123456789abcdefABCDEF' for c in hex_part):
                    result.append(s[i:i+6])
                    i += 6
                    continue
            i += 1
            continue
        result.append(ch)
        i += 1
    return "".join(result)


def _extract_list_from_parsed(parsed) -> list[dict]:
    """
    FIX 1: Si el LLM retorna un dict en lloc d'una llista,
    busca dins del dict alguna key que contingui una llista d'entitats.
    """
    # Ja és una llista
    if isinstance(parsed, list):
        return parsed

    # És un dict → buscar una llista dins
    if isinstance(parsed, dict):
        for key in ("entities", "results", "data", "geographic_entities",
                     "geographic_references", "places", "locations", "features"):
            if key in parsed and isinstance(parsed[key], list):
                return parsed[key]

        # Qualsevol valor que sigui una llista no buida
        for value in parsed.values():
            if isinstance(value, list) and len(value) > 0:
                return value

    return []


def parse_json_response(raw: str) -> list[dict]:
    """Extreu i parseja el JSON de la resposta del LLM, amb sanitització robusta."""
    cleaned = raw.strip()

    # Eliminar code blocks markdown (```json ... ``` o truncats sense tancar)
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        # Eliminar primera línia (```json o ```)
        lines = lines[1:]
        # Eliminar última línia si és el tancament ```
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()

    # Intent 1: parseig directe (funciona quan format="json" retorna un dict o array net)
    try:
        parsed = json.loads(cleaned)
        return _extract_list_from_parsed(parsed)
    except json.JSONDecodeError:
        pass

    # Intent 2: buscar array [ ] i sanititzar escapes
    start = cleaned.find("[")
    end = cleaned.rfind("]") + 1
    if start != -1 and end > 0:
        json_str = cleaned[start:end]
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            pass
        try:
            sanitized = _sanitize_json_escapes(json_str)
            return json.loads(sanitized)
        except json.JSONDecodeError:
            pass
        try:
            aggressive = _aggressive_json_cleanup(json_str)
            return json.loads(aggressive)
        except json.JSONDecodeError as e:
            print(f"⚠️  Error parsejant JSON (després de 3 intents): {e}")
            print("JSON intentat:", json_str[:300])
            return []

    # Intent 3: JSON truncat — hi ha '[' però no ']' (resposta tallada per max_tokens)
    if start != -1 and cleaned.rfind("]") == -1:
        truncated = cleaned[start:]
        # Intentar tancar l'array afegint ']' (recuperem entitats pre-truncament)
        for suffix in ("]", "}]"):
            try:
                recovered = json.loads(truncated + suffix)
                print(f"⚠️  JSON truncat recuperat parcialment ({len(recovered)} entitats)")
                return _extract_list_from_parsed(recovered)
            except json.JSONDecodeError:
                continue
        # Intentar trobar l'últim objecte complet i tallar allà
        last_brace = truncated.rfind("}")
        if last_brace != -1:
            try:
                recovered = json.loads(truncated[:last_brace + 1] + "]")
                print(f"⚠️  JSON truncat recuperat parcialment ({len(recovered)} entitats)")
                return _extract_list_from_parsed(recovered)
            except json.JSONDecodeError:
                pass
        print("⚠️  JSON truncat: no s'ha pogut recuperar cap entitat.")

    # Intent 4: sanititzar tot el text (pot ser un dict amb escapes)
    try:
        sanitized = _sanitize_json_escapes(cleaned)
        parsed = json.loads(sanitized)
        return _extract_list_from_parsed(parsed)
    except json.JSONDecodeError:
        pass

    print("⚠️  No s'ha trobat cap JSON vàlid a la resposta.")
    print("Resposta raw:", raw[:500])
    return []


# ── Pipeline principal ────────────────────────────────────────────────────────

def is_useful_chunk(chunk: str, min_words: int = 30, min_alpha_ratio: float = 0.5) -> bool:
    """
    Determina si un chunk conté text real o és basura web/OCR.
    """
    words = chunk.split()
    if len(words) < min_words:
        return False
    alpha_chars = sum(c.isalpha() for c in chunk)
    total_chars = len(chunk)
    if total_chars == 0:
        return False
    return (alpha_chars / total_chars) >= min_alpha_ratio


def extract_entities(text: str, source_name: str = "unknown") -> list[GeographicEntity]:
    """
    Donada una cadena de text, retorna una llista d'entitats geogràfiques
    extretes pel LLM.
    """
    print(f"\n📄 Processant: '{source_name}' ({len(text)} caràcters)")

    chunks = split_text(text, max_chars=20000)
    all_entities: list[GeographicEntity] = []

    skipped = 0
    for i, chunk in enumerate(chunks):
        if not is_useful_chunk(chunk):
            skipped += 1
            continue
        active = CLAUDE_MODEL if LLM_PROVIDER == "claude" else OLLAMA_MODEL
        print(f"   🔍 Chunk {i+1}/{len(chunks)} → enviant a {active}...")
        try:
            user_msg = USER_PROMPT_TEMPLATE.format(text=chunk)
            raw      = query_llm(user_msg)
            entities = parse_json_response(raw)
        except Exception as e:
            print(f"   ⚠️  Error al chunk {i+1}: {e}")
            continue

        for e in entities:
            # FIX 2: saltar elements que no siguin dicts
            if not isinstance(e, dict):
                continue

            name = e.get("name")
            if not name or not str(name).strip() or name == "null":
                continue
            entity = GeographicEntity(
                name        = str(name).strip(),
                entity_type = e.get("entity_type", "other"),
                description = e.get("description", ""),
                context     = e.get("context", ""),
                lat         = e.get("lat"),
                lon         = e.get("lon"),
                confidence  = e.get("confidence", "low"),
                source_text = source_name,
            )
            all_entities.append(entity)

    if skipped:
        print(f"   ⏭️  {skipped}/{len(chunks)} chunks saltats (basura detectada)")
    print(f"   ✅ {len(all_entities)} entitats extretes")
    return all_entities


def split_text(text: str, max_chars: int = 20000) -> list[str]:
    """Divideix el text en fragments per no superar el context del LLM."""
    if len(text) <= max_chars:
        return [text]

    chunks = []
    paragraphs = text.split("\n\n")
    current = ""
    for para in paragraphs:
        if len(current) + len(para) > max_chars and current:
            chunks.append(current.strip())
            current = para
        else:
            current += "\n\n" + para
    if current.strip():
        chunks.append(current.strip())
    return chunks


# ── Guardar resultats ─────────────────────────────────────────────────────────

def save_results(entities: list[GeographicEntity], filename: str = "entities.json"):
    """Guarda les entitats en JSON i mostra un resum."""
    output_path = OUTPUT_DIR / filename
    data = [asdict(e) for e in entities]

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"\n💾 Guardat a: {output_path}")
    print_summary(entities)
    return output_path


def print_summary(entities: list[GeographicEntity]):
    """Mostra un resum de les entitats trobades."""
    print("\n" + "="*55)
    print(f"  RESUM D'ENTITATS EXTRETES: {len(entities)} total")
    print("="*55)

    by_type: dict[str, list] = {}
    for e in entities:
        by_type.setdefault(e.entity_type, []).append(e)

    for etype, ents in sorted(by_type.items()):
        print(f"\n  📍 {etype.upper()} ({len(ents)})")
        for e in ents:
            coords = f" [{e.lat}, {e.lon}]" if e.lat else ""
            print(f"     • {e.name}{coords}  [{e.confidence}]")

    with_coords = [e for e in entities if e.lat and e.lon]
    print(f"\n  🗺️  Entitats amb coordenades: {len(with_coords)}/{len(entities)}")
    print("="*55)


# ── Punt d'entrada ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    sample_text = """
    En el año 1542, Francisco de Orellana navegó por el río Amazonas desde su confluencia 
    con el Napo hasta el océano Atlántico. Durante el viaje, el cronista Gaspar de Carvajal 
    describió grandes poblaciones en las riberas del río, especialmente en la región del 
    Tapajós, donde observó numerosas aldeas conectadas por caminos bien trazados.

    Más al sur, cerca del río Madre de Dios en el actual territorio boliviano, los relatos 
    indígenas hablaban de una ciudad llamada Paititi, rodeada de estructuras de tierra elevadas 
    conocidas como geoglifos. Estas estructuras, visibles desde las alturas, formaban patrones 
    geométricos regulares cerca de la confluencia del río Beni con el Mamoré.

    Expediciones posteriores del siglo XVII documentaron asentamientos en la región del 
    Llanos de Mojos, al noreste de Bolivia, donde la población construía plataformas elevadas 
    para protegerse de las inundaciones estacionales del río Iténez.
    """

    print("🏛️  TFG - Pipeline d'Extracció d'Entitats Geogràfiques")
    active = CLAUDE_MODEL if LLM_PROVIDER == "claude" else OLLAMA_MODEL
    print(f"   Provider: {LLM_PROVIDER} | Model: {active}")

    entities = extract_entities(sample_text, source_name="carvajal_relacion_1542")
    save_results(entities, "entities_test.json")