"""Render explanatory boxes without accepting author-supplied HTML."""
import re
from html import escape

BOX = re.compile(
    r"^\[caixa:[ \t]*([^\]\n|]*)(?:\|(right|full))?(?:\|([^\]\n]*))?\][ \t]*\n"
    r"([\s\S]*?)^\[/caixa\][ \t]*(?=\n|$)", re.M
)


# The first editor version emitted literal newline delimiters around the box.
# Repair that exact envelope only; backslashes inside the explanation stay intact.
LEGACY_BOX = re.compile(
    r"\\n\\n(\[caixa:[^\]\r\n]*\])\\n([\s\S]*?)\\n\[/caixa\]\\n\\n"
)


def box_colors(value):
    """Accept one opaque RGB colour and choose the highest-contrast text."""
    value = (value or "").strip()
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", value):
        return None
    rgb = [int(value[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
    luminance = sum(c * weight for c, weight in zip(linear, (0.2126, 0.7152, 0.0722)))
    black_contrast = (luminance + 0.05) / 0.05
    white_contrast = 1.05 / (luminance + 0.05)
    return value.lower(), "#000000" if black_contrast >= white_contrast else "#ffffff"


def prepare_explanatory_boxes(source, store_embed):
    # Native form submissions can use CRLF even when textarea.value uses LF.
    source = (source or "").replace("\r\n", "\n").replace("\r", "\n")
    source = LEGACY_BOX.sub(
        lambda match: "\n\n" + match.group(1) + "\n" + match.group(2) + "\n[/caixa]\n\n",
        source,
    )
    def replace(match):
        title, layout, color, body = match.groups()
        if not body.strip():
            return match.group(0)
        paragraphs = [
            "<p>" + escape(part.strip()).replace("\n", "<br>") + "</p>"
            for part in re.split(r"\n[ \t]*\n", body.strip()) if part.strip()
        ]
        heading = f"<strong class=\"article-explainer-title\">{escape(title.strip())}</strong>" if title.strip() else ""
        label = escape(title.strip() or "Caixa explicativa", quote=True)
        colors = box_colors(color)
        style = f' style="--explainer-bg:{colors[0]};--explainer-fg:{colors[1]}"' if colors else ""
        html = (
            f'<aside class="article-explainer article-explainer--{layout or "right"}" aria-label="{label}"{style}>'
            + heading + "".join(paragraphs) + "</aside>"
        )
        return store_embed("EXPLAINER", html)
    return BOX.sub(replace, source or "")
