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


def compose_infographic(payload, network, illustration, logo, accent):
    """Compose one editorial infographic with a central image and short callouts."""
    width, height = SIZES['instagram'] if network == 'instagram' else (2480, 3508)
    canvas = Image.new('RGB', (width, height), '#f7f9f8')
    draw = ImageDraw.Draw(canvas)
    margin_x, margin_y = round(width * .1), round(height * .1)
    usable_width = width - 2 * margin_x
    ink = '#132d36'
    scale = width / 1080
    slide = payload['slides'][0]
    points = [line.strip() for line in slide['body'].splitlines() if line.strip()]
    # Earlier versions and manually edited paragraphs retain a readable layout.
    if len(points) > 4 or any(len(point) > 60 for point in points):
        points = [' '.join(points)]

    def text_block(text, x, y, max_width, size, color):
        face = font(round(size * scale))
        step = round(size * scale * 1.28)
        for line in lines(draw, text, face, max_width):
            draw.text((x, y), line, font=face, fill=color, anchor='mt')
            y += step
        return y

    logo.thumbnail((round(width * .27), round(42 * scale)))
    canvas.paste(logo, ((width - logo.width) // 2, margin_y), logo)
    title_end = text_block(slide['heading'], width // 2, margin_y + logo.height + round(28 * scale),
                           usable_width, 46, ink)
    image_width = round(width * .42)
    image_height = round(height * .39)
    image_top = max(title_end + round(30 * scale), round(height * .32))
    if illustration:
        with Image.open(io.BytesIO(illustration)) as raw:
            visual = ImageOps.contain(raw.convert('RGB'), (image_width, image_height))
        canvas.paste(visual, ((width - visual.width) // 2,
                             image_top + (image_height - visual.height) // 2))
    label = payload['visual_label']
    if payload.get('language') == 'en':
        label = {'Ilustração conceptual': 'Conceptual illustration',
                 'Reconstrução hipotética': 'Hypothetical reconstruction'}[label]
    label_end = text_block(label, width // 2, image_top + image_height + round(12 * scale),
                           image_width, 17, ink)

    gap = round(width * .025)
    side_width = (usable_width - image_width) // 2 - gap
    for index, point in enumerate(points):
        if len(points) == 1 or (len(points) == 3 and index == 2):
            x, y, point_width = width // 2, label_end + round(24 * scale), usable_width
        else:
            x = margin_x + side_width // 2 if index % 2 == 0 else width - margin_x - side_width // 2
            y = image_top + round(image_height * (.08 if index < 2 else .58))
            point_width = side_width
        if len(points) > 1:
            y = text_block(f'{index + 1:02d}', x, y, point_width, 27, accent) + round(8 * scale)
        bottom = text_block(point, x, y, point_width, 22, ink)
        if bottom > height - margin_y:
            raise GenerationError('O texto do infográfico excede a área legível. Encurte os tópicos.')

    stream = io.BytesIO()
    canvas.save(stream, format='PNG', optimize=True)
    return [stream.getvalue()]


def compose(payload, network, illustration, static_folder, kind=None):
    width, height = SIZES[network]
    logo_path = Path(static_folder) / 'img/logo-sussurros-light.png'
    if not logo_path.is_file():
        raise GenerationError('O logotipo oficial não está disponível.')
    with Image.open(logo_path) as logo_file:
        logo = logo_file.convert('RGBA')
    accent = {'teal': '#05756c', 'blue': '#184f83', 'purple': '#684487'}[payload['accent']]
    if kind == 'infographic':
        return compose_infographic(payload, network, illustration, logo, accent)
    logo.thumbnail((int(width * .50), 85))
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
        label=payload['visual_label']
        if payload.get('language')=='en':
            label={'Ilustração conceptual':'Conceptual illustration','Reconstrução hipotética':'Hypothetical reconstruction'}[label]
        draw.text((55, height - 100), label, font=font(24), fill='#425b62')
        draw.text((55, height - 58), 'sussurrosdosaber.com', font=font(25), fill=accent)
        draw.text((width - 135, height - 58), f'{index + 1}/{len(payload["slides"])}', font=font(24), fill=accent)
        stream = io.BytesIO()
        canvas.save(stream, format='PNG', optimize=True)
        output.append(stream.getvalue())
    return output
