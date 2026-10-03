"""Structured journal authors, compatible with previously saved author lines."""
import json
import re
from urllib.parse import urlparse

EDITORIAL_FIELDS = ("copyright_policy", "submission_history", "acknowledgements", "funding", "license_info")


def normalize_orcid(value):
    value = (value or "").strip()
    if not value:
        return ""
    if re.fullmatch(r"\d{4}-\d{4}-\d{4}-\d{3}[\dXx]", value):
        return "https://orcid.org/" + value.upper()
    parsed = urlparse(value)
    if (parsed.scheme not in ("http", "https") or parsed.netloc.lower() not in ("orcid.org", "www.orcid.org")
            or parsed.query or parsed.fragment):
        raise ValueError("Informe uma URL ORCID válida, por exemplo https://orcid.org/0000-0002-1825-0097.")
    identifier = parsed.path.strip("/")
    if not re.fullmatch(r"\d{4}-\d{4}-\d{4}-\d{3}[\dXx]", identifier):
        raise ValueError("O identificador ORCID deve seguir o formato 0000-0000-0000-0000.")
    return "https://orcid.org/" + identifier.upper()


def submitted_author_rows(form):
    columns = [form.getlist(field) for field in ("author_name", "author_orcid", "author_description")]
    return [dict(zip(("name", "orcid", "description"), [values[i] if i < len(values) else "" for values in columns]))
            for i in range(max((len(values) for values in columns), default=0))]


def validate_authors(rows):
    if len(rows) > 30:
        raise ValueError("Adicione no máximo 30 autores por artigo.")
    result = []
    for row in rows:
        name, orcid, description = (row.get(key, "").strip() for key in ("name", "orcid", "description"))
        if not any((name, orcid, description)):
            continue
        if len(name) > 180 or len(orcid) > 180 or len(description) > 4000:
            raise ValueError("Cada autor pode ter nome e ORCID com até 180 caracteres e descrição com até 4000.")
        if not name and not orcid:
            raise ValueError("Informe o nome ou ORCID do autor a que pertence a descrição.")
        result.append({"name": name, "orcid": normalize_orcid(orcid), "description": description})
    return result


def journal_authors(journal):
    raw = getattr(journal, "authors_data", "") or ""
    try:
        saved = json.loads(raw)
    except (ValueError, TypeError):
        saved = []
    if isinstance(saved, list) and saved:
        result = []
        for row in saved[:30]:
            if not isinstance(row, dict):
                continue
            cleaned = {key: str(row.get(key) or "").strip() for key in ("name", "orcid", "description")}
            try:
                cleaned["orcid"] = normalize_orcid(cleaned["orcid"])
            except ValueError:
                cleaned["orcid"] = ""
            if cleaned["name"] or cleaned["orcid"]:
                result.append(cleaned)
        if result:
            return result
    result = []
    for line in (getattr(journal, "authors_orcid", "") or "").splitlines()[:30]:
        line = line.strip()
        if not line:
            continue
        match = re.search(r"https?://(?:www\.)?orcid\.org/[^\s|—]+|\d{4}-\d{4}-\d{4}-\d{3}[\dXx]", line, re.I)
        orcid = ""
        if match:
            try:
                orcid = normalize_orcid(match.group())
            except ValueError:
                pass
            name = (line[:match.start()] + line[match.end():]).strip(" —–-|:")
        else:
            name = line.split("—", 1)[0].split("|", 1)[0].strip()
        result.append({"name": name, "orcid": orcid, "description": ""})
    return result


def legacy_author_lines(rows):
    return "\n".join(row["name"] + (" — " if row["name"] and row["orcid"] else "") + row["orcid"] for row in rows)
