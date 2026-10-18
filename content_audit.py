"""Read-only signals for editorial triage, never a policy or licence certificate."""
import re
from bs4 import BeautifulSoup

DEMO_ARTICLE_BODY = "A ciência começa com uma pergunta bem formulada. Este artigo apresenta o tema de forma acessível, sem perder o rigor nem a ligação às evidências.\n\nCombinando observação, experimentação e análise crítica, investigadores conseguem transformar fenómenos pouco visíveis em conhecimento verificável. O contexto local também importa: perguntas científicas relevantes surgem das necessidades das comunidades e dos ecossistemas onde a pesquisa acontece.\n\nCompreender ciência ajuda estudantes e cidadãos a tomar decisões informadas e aproxima a produção académica do público."


def normalized_text(value):
    return ' '.join(BeautifulSoup(value or '', 'html.parser').get_text(' ', strip=True).split())


def assess_article(row):
    body = row.get('body') or ''
    references = row.get('references') or ''
    combined = normalized_text(body + '\n' + references)
    flags = []
    if normalized_text(body) == normalized_text(DEMO_ARTICLE_BODY):
        flags.append('demo_body_published')
    if re.search(r'confirmar os autores completos|antes da publicação formal|imagem de destaque recomendada', combined, re.I):
        flags.append('unresolved_editorial_note')
    if not references.strip() and not re.search(r'referências|bibliografia|fontes consultadas', combined, re.I):
        flags.append('references_not_identified')
    if re.search(r'autor:\s*utilizador que carregou', combined, re.I):
        flags.append('generic_image_attribution')
    # A hosted image URL or credit text cannot establish permission or ownership.
    if row.get('image'):
        flags.append('cover_rights_require_documentary_check')
    dois = sorted(set(match.rstrip('.,;') for match in re.findall(r'10\.\d{4,9}/[^\s<>\]\"]+', body + '\n' + references, re.I)))
    return {'slug': row['slug'], 'title': row['title'], 'characters': len(combined),
            'flags': flags, 'dois': dois, 'scientific_accuracy_verified': False,
            'originality_verified': False, 'image_rights_verified': False}
