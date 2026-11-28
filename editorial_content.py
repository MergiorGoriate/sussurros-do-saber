"""Stable heading anchors for the author guidelines, including custom content."""
import re
import unicodedata
from bs4 import BeautifulSoup
from markupsafe import Markup


# Legacy English translations may contain translated spellings of this marker.
DROP_CAP_MARKER = r"(?i:\[(?:capitular|drop[ -]?cap)\])"


def prepare_guidelines(html):
    soup = BeautifulSoup(str(html), "html.parser")
    used = {"diretrizes-conteudo"}
    manuscript_types_id = None
    for heading in soup.find_all(["h2", "h3"]):
        label = heading.get_text(" ", strip=True)
        if not label:
            continue
        normalized = unicodedata.normalize("NFKD", label).encode("ascii", "ignore").decode().lower()
        base = re.sub(r"[^a-z0-9]+", "-", normalized).strip("-") or "secao"
        if "tipo" in normalized and "manuscrit" in normalized and manuscript_types_id is None:
            base = "tipos"
        candidate, suffix = base, 2
        while candidate in used:
            candidate, suffix = f"{base}-{suffix}", suffix + 1
        used.add(candidate)
        heading["id"] = candidate
        if base == "tipos" and manuscript_types_id is None:
            manuscript_types_id = candidate
    return Markup(str(soup)), manuscript_types_id
