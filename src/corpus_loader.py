"""
TFG: Carregador de Documents
==============================
Llegeix qualsevol fitxer de TFG/data/ i retorna el text net.
Suporta: .txt, .pdf, carpetes senceres.

Instal·lació: pip install pymupdf
"""

from pathlib import Path
from typing import Optional


DATA_DIR = Path(__file__).parent.parent / "data"


def read_txt(path: Path) -> str:
    for enc in ["utf-8", "latin-1", "utf-16"]:
        try:
            return path.read_text(encoding=enc)
        except UnicodeDecodeError:
            continue
    raise ValueError(f"No s'ha pogut llegir {path}")


def read_pdf(path: Path) -> str:
    try:
        import fitz
        doc  = fitz.open(str(path))
        text = "\n\n".join(page.get_text() for page in doc)
        doc.close()
        return text.strip()
    except ImportError:
        raise ImportError("Instal·la pymupdf: pip install pymupdf")


def load_file(path: str | Path) -> Optional[dict]:
    """
    Carrega un fitxer i retorna un dict amb name, text, file_path.
    Retorna None si el format no és suportat.
    """
    path = Path(path)
    if not path.exists():
        print(f"   ⚠️  No trobat: {path}")
        return None

    if path.suffix.lower() == ".txt":
        text = read_txt(path)
    elif path.suffix.lower() == ".pdf":
        text = read_pdf(path)
    else:
        print(f"   ⚠️  Format no suportat: {path.suffix}")
        return None

    if not text.strip():
        print(f"   ⚠️  Fitxer buit: {path.name}")
        return None

    return {
        "name":      path.stem,          # nom sense extensió → títol del document
        "text":      text,
        "file_path": str(path.resolve()),
    }


def load_from_data_dir(extensions: list[str] = [".txt", ".pdf"]) -> list[dict]:
    """
    Carrega automàticament tots els fitxers de TFG/data/
    que siguin .txt o .pdf.
    """
    if not DATA_DIR.exists():
        print(f"⚠️  Carpeta data/ no trobada: {DATA_DIR}")
        return []

    files  = [f for f in DATA_DIR.iterdir() if f.suffix.lower() in extensions]
    docs   = []

    print(f"\n📁 Carregant fitxers de {DATA_DIR}")
    print(f"   Trobats: {len(files)} fitxers\n")

    for f in sorted(files):
        doc = load_file(f)
        if doc:
            docs.append(doc)

    return docs


def load_files(paths: list[str | Path]) -> list[dict]:
    """Carrega una llista específica de fitxers."""
    docs = []
    for p in paths:
        doc = load_file(p)
        if doc:
            docs.append(doc)
    return docs