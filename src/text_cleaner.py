"""
TFG: Netejador de Textos Històrics
Neteja el soroll típic d'OCR en llibres escaneats dels s. XVI-XIX:
- 's' llarga (ſ) → s normal
- Guions de final de línia
- Caràcters estranys d'OCR
- Línies en blanc múltiples
- Números de pàgina i capçaleres repetides

No elimina contingut — només normalitza per facilitar la feina del LLM.
"""

import re
from pathlib import Path


def clean_ocr_text(text: str) -> str:
    """
    Aplica totes les correccions d'OCR en seqüència.
    Retorna el text net.
    """
    text = strip_web_artifacts(text)
    text = fix_long_s(text)
    text = fix_hyphenation(text)
    text = fix_ligatures(text)
    text = remove_page_artifacts(text)
    text = normalize_whitespace(text)
    return text.strip()


def strip_web_artifacts(text: str) -> str:
    """
    Elimina contingut web (HTML, SVG, CSS, JS, Internet Archive)
    que contamina els PDFs descarregats d'Internet Archive.
    S'executa PRIMER, abans de qualsevol altra neteja.
    """
    # 1. Blocs SVG complets (<svg ...> ... </svg>)
    text = re.sub(r"<svg[\s\S]*?</svg>", "", text, flags=re.IGNORECASE)

    # 2. Blocs style, script, noscript, nav, header, footer, iframe
    for tag in ["style", "script", "noscript", "nav", "header", "footer", "iframe"]:
        text = re.sub(rf"<{tag}[\s\S]*?</{tag}>", "", text, flags=re.IGNORECASE)

    # 3. Línies que semblen CSS (.classe { ... }, @media, etc.)
    text = re.sub(r"^[ \t]*[.#][a-zA-Z_][\w-]*\s*\{[^}]*\}", "", text, flags=re.MULTILINE)
    text = re.sub(r"^[ \t]*@(media|font-face|keyframes|import|charset)[^\n]*(\{[\s\S]*?\})?", "", text, flags=re.MULTILINE)
    text = re.sub(r"^[ \t]*[a-z-]+\s*:\s*[^;\n]+;\s*$", "", text, flags=re.MULTILINE)

    # 4. Etiquetes HTML sueltes (conservant el text interior)
    text = re.sub(r"<[^>]+>", " ", text)

    # 5. URLs llargues (>20 chars)
    text = re.sub(r"https?://\S{20,}", "", text)

    # 6. Línies amb codi JavaScript
    js_patterns = [
        r"var\(--",  r"function\s*\(", r"document\.", r"window\.",
        r"addEventListener", r"querySelector", r"console\.log",
        r"xmlns", r"\.prototype\.", r"return\s+\w+\s*;",
    ]
    js_re = re.compile("|".join(js_patterns))
    lines = text.split("\n")
    lines = [l for l in lines if not js_re.search(l)]
    text = "\n".join(lines)

    # 7. Identificadors d'Internet Archive
    ia_patterns = [
        r"archive\.org", r"wayback", r"BookReader", r"ia-module",
        r"ia-icon", r"web\.archive", r"openlibrary\.org",
    ]
    ia_re = re.compile("|".join(ia_patterns), re.IGNORECASE)
    lines = text.split("\n")
    lines = [l for l in lines if not ia_re.search(l)]
    text = "\n".join(lines)

    # 8. Caràcters de control Unicode (excepte \n, \r, \t)
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]", "", text)

    return text


def fix_long_s(text: str) -> str:
    """Substitueix la 's' llarga medieval (ſ) per 's' normal."""
    return text.replace("ſ", "s").replace("ß", "ss")


def fix_hyphenation(text: str) -> str:
    """
    Uneix paraules partides per guió a final de línia.
    Ex: "des-\ncubrimiento" → "descubrimiento"
    """
    # Guió + salt de línia + paraula minúscula → unir
    text = re.sub(r"-\n([a-záéíóúüñ])", r"\1", text)
    # Variant amb espai
    text = re.sub(r"- \n([a-záéíóúüñ])", r"\1", text)
    return text


def fix_ligatures(text: str) -> str:
    """Substitueix lligadures tipogràfiques antigues."""
    replacements = {
        "æ": "ae",
        "œ": "oe",
        "ﬁ": "fi",
        "ﬂ": "fl",
        "ﬀ": "ff",
        "ﬃ": "ffi",
        "ﬄ": "ffl",
        "\uf001": "fi",   # lligadura fi corrupte
        "\uf002": "fl",
        "¬":  "",         # caràcter de final de línia en alguns OCR
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text


def remove_page_artifacts(text: str) -> str:
    """
    Elimina artefactes típics d'escaneig:
    - Números de pàgina sols en una línia
    - Capçaleres repetides curtes (< 6 paraules)
    - Línies amb >60% caràcters no alfanumèrics (soroll d'OCR)
    """
    lines = text.split("\n")
    cleaned = []

    for line in lines:
        stripped = line.strip()

        # Línia buida → conservar (estructura)
        if not stripped:
            cleaned.append("")
            continue

        # Número de pàgina sol (1-4 dígits)
        if re.fullmatch(r"\d{1,4}", stripped):
            continue

        # Línia molt curta amb majúscules → possible capçalera (ex: "CAPÍTULO IV")
        # Les conservem — poden contenir info geogràfica

        # Línia amb molt soroll d'OCR (>50% caràcters rars)
        alnum = sum(c.isalnum() or c.isspace() for c in stripped)
        if len(stripped) > 10 and alnum / len(stripped) < 0.5:
            continue

        cleaned.append(line)

    return "\n".join(cleaned)


def normalize_whitespace(text: str) -> str:
    """
    Normalitza espais i salts de línia:
    - Múltiples línies en blanc → màxim 2
    - Espais múltiples → un sol espai
    - Tabuladors → espai
    """
    # Tabuladors
    text = text.replace("\t", " ")
    # Espais múltiples
    text = re.sub(r" {2,}", " ", text)
    # Més de 2 línies en blanc seguides
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text


def clean_file(input_path: str | Path, output_path: str | Path = None) -> str:
    """
    Neteja un fitxer de text i el guarda (o retorna el text net).
    Si output_path és None, sobreescriu l'original.
    """
    input_path = Path(input_path)

    for enc in ["utf-8", "latin-1", "utf-16"]:
        try:
            raw = input_path.read_text(encoding=enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise ValueError(f"No s'ha pogut llegir {input_path}")

    original_len = len(raw)
    cleaned = clean_ocr_text(raw)
    cleaned_len = len(cleaned)

    reduction = (1 - cleaned_len / original_len) * 100 if original_len else 0
    print(f"   {input_path.name}: {original_len:,} → {cleaned_len:,} cars. (-{reduction:.1f}%)")

    dest = Path(output_path) if output_path else input_path
    dest.write_text(cleaned, encoding="utf-8")

    return cleaned


def clean_data_dir():
    """Neteja tots els .txt de TFG/data/ in-place."""
    data_dir = Path(__file__).parent.parent / "data"
    txt_files = list(data_dir.glob("*.txt"))

    if not txt_files:
        print("No s'han trobat fitxers .txt a data/")
        return

    print(f"\nNetejant {len(txt_files)} fitxers de {data_dir}\n")
    for f in sorted(txt_files):
        clean_file(f)
    print("\nNeteja completada")


if __name__ == "__main__":
    clean_data_dir()