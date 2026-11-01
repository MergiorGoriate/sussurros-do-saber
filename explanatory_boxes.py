"""Render explanatory boxes without accepting author-supplied HTML."""
import re
from html import escape

BOX = re.compile(
    r"^\[caixa:[ \t]*([^\]\n|]*)(?:\|(right|full))?\][ \t]*\n"
    r"([\s\S]*?)^\[/caixa\][ \t]*(?=\n|$)", re.M
)


# The first editor version emitted literal newline delimiters around the box.
# Repair that exact envelope only; backslashes inside the explanation stay intact.
LEGACY_BOX = re.compile(
    r"\\n\\n(\[caixa:[^\]\r\n]*\])\\n([\s\S]*?)\\n\[/caixa\]\\n\\n"
)


def prepare_explanatory_boxes(source, store_embed):
    # Native form submissions can use CRLF even when textarea.value uses LF.
    source = (source or "").replace("\r\n", "\n").replace("\r", "\n")
    source = LEGACY_BOX.sub(
        lambda match: "\n\n" + match.group(1) + "\n" + match.group(2) + "\n[/caixa]\n\n",
        source,
    )
    def replace(match):
        title, layout, body = match.groups()
        if not body.strip():
            return match.group(0)
        paragraphs = [
            "<p>" + escape(part.strip()).replace("\n", "<br>") + "</p>"
            for part in re.split(r"\n[ \t]*\n", body.strip()) if part.strip()
        ]
        heading = f"<strong class=\"article-explainer-title\">{escape(title.strip())}</strong>" if title.strip() else ""
        label = escape(title.strip() or "Caixa explicativa", quote=True)
        html = (
            f'<aside class="article-explainer article-explainer--{layout or "right"}" aria-label="{label}">'
            + heading + "".join(paragraphs) + "</aside>"
        )
        return store_embed("EXPLAINER", html)
    return BOX.sub(replace, source or "")
