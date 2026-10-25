"""Deterministic type and official logo over AI illustrations, never AI lettering."""
import io
import os
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageOps
from dissemination_ai import GenerationError

SIZES = {'facebook': (1200, 1200), 'instagram': (1080, 1350),
         'bluesky': (1200, 1200), 'x': (1200, 1200), 'reddit': (1200, 1200)}


def font(size):
    configured = os.getenv('DISSEMINATION_FONT', '')
    paths = [configured, '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
             str(Path(__file__).parent / 'static/fonts/DejaVuSerif.ttf')]
    for path in paths:
        if path and Path(path).is_file():
            return ImageFont.truetype(path, size)
    raise GenerationError('Configure uma fonte TrueType para a composição dos materiais.')


def lines(draw, text, face, width):
    output = []
    line = ''
    for word in text.split():
        candidate = (line + ' ' + word).strip()
        if draw.textbbox((0, 0), word, font=face)[2] > width:
            raise GenerationError('Uma palavra é demasiado longa para a composição. Corrija o texto.')
        if draw.textbbox((0, 0), candidate, font=face)[2] > width:
            output.append(line)
            line = word
        else:
            line = candidate
    return output + ([line] if line else [])


def compose(payload, network, illustration, static_folder):
    width, height = SIZES[network]
    logo_path = Path(static_folder) / 'img/logo-sussurros-light.png'
    if not logo_path.is_file():
        raise GenerationError('O logotipo oficial não está disponível.')
    with Image.open(logo_path) as logo_file:
        logo = logo_file.convert('RGBA')
    logo.thumbnail((int(width * .50), 85))
    accent = {'teal': '#05756c', 'blue': '#184f83', 'purple': '#684487'}[payload['accent']]
    output = []
    for index, slide in enumerate(payload['slides']):
        canvas = Image.new('RGB', (width, height), '#f7f9f8')
        draw = ImageDraw.Draw(canvas)
        canvas.paste(logo, (55, 35), logo)
        draw.rectangle((0, 135, width, 149), fill=accent)
        image_y = 165
        image_h = int(height * (.38 if payload['layout'] == 'balanced' else .27))
        if illustration:
            with Image.open(io.BytesIO(illustration)) as raw:
                visual = ImageOps.fit(raw.convert('RGB'), (width - 110, image_h))
            canvas.paste(visual, (55, image_y))
        else:
            image_h = 0
        y = image_y + image_h + 25
        title_font = font(43)
        body_font = font(33)
        for value, face, spacing in ((slide['heading'], title_font, 54), (slide['body'], body_font, 44)):
            for line in lines(draw, value, face, width - 110):
                if y + spacing > height - 130:
                    raise GenerationError('O texto excede a área legível. Encurte o slide ou escolha composição compacta.')
                draw.text((55, y), line, font=face, fill='#132d36')
                y += spacing
            y += 18
        draw.text((55, height - 100), payload['visual_label'], font=font(24), fill='#425b62')
        draw.text((55, height - 58), 'sussurrosdosaber.com', font=font(25), fill=accent)
        draw.text((width - 135, height - 58), f'{index + 1}/{len(payload["slides"])}', font=font(24), fill=accent)
        stream = io.BytesIO()
        canvas.save(stream, format='PNG', optimize=True)
        output.append(stream.getvalue())
    return output
