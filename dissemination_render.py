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


def infographic_points(slide):
    points = []
    summary = ''
    for line in slide['body'].splitlines():
        if not line.strip():
            continue
        label, separator, detail = line.partition(':')
        if separator and label.strip().casefold() in {'síntese', 'summary'} and detail.strip():
            summary = detail.strip()
        elif separator and 0 < len(label.strip()) <= 26 and detail.strip():
            points.append((label.strip(), detail.strip()))
        else:
            points.append(('', line.strip()))
    if len(points) > 6 or not points:
        return [('', ' '.join(slide['body'].split()))], ''
    return points, summary


def illustration_label(payload):
    label = payload['visual_label']
    if payload.get('language') == 'en':
        return {'Ilustração conceptual': 'Conceptual illustration',
                'Reconstrução hipotética': 'Hypothetical reconstruction'}[label]
    return label


def infographic_text(draw, value, box, size, minimum, color):
    x, y, right, bottom = box
    for candidate in range(size, minimum - 1, -1):
        face = font(candidate)
        if any(draw.textlength(word, font=face) > right - x for word in value.split()):
            continue
        wrapped = lines(draw, value, face, right - x)
        step = round(candidate * 1.24)
        if y + len(wrapped) * step <= bottom:
            for line in wrapped:
                draw.text((x, y), line, font=face, fill=color, anchor='lt')
                y += step
            return y
    raise GenerationError('O texto do infográfico excede a área legível. Encurte os tópicos.')


def infographic_visual(canvas, raw, box):
    if raw:
        x, y, right, bottom = box
        with Image.open(io.BytesIO(raw)) as image:
            visual = ImageOps.contain(image.convert('RGB'), (right - x, bottom - y))
        canvas.paste(visual, ((x + right - visual.width) // 2, (y + bottom - visual.height) // 2))


def infographic_card(draw, point, index, box, palette):
    x, y, right, bottom = box
    fill, accent, ink = palette
    heading_ink = accent if ink == "#f5fbff" else ink
    draw.rounded_rectangle(box, radius=20, fill=fill)
    draw.ellipse((x + 15, y + 14, x + 48, y + 47), fill=accent)
    draw.text((x + 31, y + 30), str(index), font=font(17), fill='#06182b', anchor='mm')
    label, body = point
    start = y + 56
    if label:
        start = infographic_text(draw, label.upper(), (x + 15, start, right - 15, y + 120),
                                 23, 16, heading_ink) + 6
    infographic_text(draw, body, (x + 15, start, right - 15, bottom - 12), 23, 15, ink)


def compose_infographic(payload, network, illustration, logo, accent):
    compact = payload['layout'] == 'compact'
    width, height = (1536, 1024) if compact else SIZES['instagram']
    print_size = (2480, 3508)
    if not compact and network != 'instagram':
        height = round(width * print_size[1] / print_size[0])
    canvas = Image.new('RGB', (width, height), '#f1f6fa' if compact else '#06182b')
    draw = ImageDraw.Draw(canvas)
    slide = payload['slides'][0]
    points, summary = infographic_points(slide)
    cyan, white, navy = '#58e4fb', '#f5fbff', '#0a2743'
    footer = height - 140
    if compact:
        draw.rounded_rectangle((24, 24, width - 24, 300), radius=28, fill=navy)
        infographic_text(draw, slide['heading'], (58, 68, 866 if illustration else width - 58, 270),
                         64, 36, white)
        infographic_visual(canvas, illustration, (890, 38, width - 50, 254))
        if illustration:
            draw.text((1180, 266), illustration_label(payload), font=font(20), fill=white, anchor='mt')

        palettes = (('#dceffb', '#72cffa'), ('#e2f3d8', '#88d49c'), ('#ece6fa', '#c8aaf4'),
                    ('#fff0d2', '#f5c572'), ('#daf4ed', '#83ddc5'), ('#e3ebff', '#a3bdf9'))
        columns = min(3, len(points))
        rows = (len(points) + columns - 1) // columns
        card_width = (width - 48 - (columns - 1) * 16) // columns
        card_height = (footer - 330 - (rows - 1) * 16) // rows
        for index, point in enumerate(points):
            row, column = divmod(index, columns)
            x = 24 + column * (card_width + 16)
            y = 314 + row * (card_height + 16)
            fill, badge = palettes[index]
            infographic_card(draw, point, index + 1, (x, y, x + card_width, y + card_height),
                             (fill, badge, '#102b46'))
    else:
        cyan = {'#05756c': '#65e0d1', '#184f83': '#58e4fb', '#684487': '#dab7ff'}[accent]
        draw.text((34, 45), str(len(points)), font=font(112), fill=cyan, anchor='lt')
        infographic_text(draw, slide['heading'].upper(), (133, 45, width - 32, 230), 55, 32, white)
        draw.line((34, 246, width - 34, 246), fill=cyan, width=3)

        if len(points) == 1:
            infographic_visual(canvas, illustration, (80, 270, width - 80, 854))
            infographic_card(draw, points[0], 1, (36, 915, width - 36, footer - 20),
                             (navy, cyan, white))
            label_y = 874
        else:
            image_box = (312, 270, width - 312, footer - 84)
            infographic_visual(canvas, illustration, image_box)
            label_y = footer - 65
            rows = (len(points) + 1) // 2
            card_height = min(282, (footer - 298 - (rows - 1) * 14) // rows)
            for index, point in enumerate(points):
                row, side = divmod(index, 2)
                x = 25 if side == 0 else width - 301
                y = 272 + row * (card_height + 14)
                middle = y + card_height // 2
                draw.line((x + (276 if side == 0 else 0), middle,
                           image_box[0] if side == 0 else image_box[2], middle), fill=cyan, width=2)
                infographic_card(draw, point, index + 1, (x, y, x + 276, y + card_height),
                                 (navy, cyan, white))
        if illustration:
            draw.text((width // 2, label_y), illustration_label(payload),
                      font=font(19), fill=white, anchor='mt')

    draw.rounded_rectangle((24, footer, width - 24, height - 20), radius=24, fill=navy)
    draw.line((47, footer + 5, width - 47, footer + 5), fill=cyan, width=3)
    logo.thumbnail((212, 52))
    logo_y = footer + (120 - logo.height) // 2
    draw.rounded_rectangle((40, logo_y - 7, 62 + logo.width, logo_y + logo.height + 7),
                           radius=8, fill='white')
    canvas.paste(logo, (51, logo_y), logo)
    if summary:
        label = 'Summary' if payload.get('language') == 'en' else 'Síntese'
        draw.text((288, footer + 24), label, font=font(24), fill=cyan, anchor='lt')
        infographic_text(draw, summary, (288, footer + 55, width - 45, height - 28), 24, 16, white)
    else:
        draw.text((288, footer + 59), 'sussurrosdosaber.com', font=font(22), fill=white, anchor='lm')

    if not compact and network != 'instagram':
        canvas = canvas.resize(print_size, Image.Resampling.LANCZOS)
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
