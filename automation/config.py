"""Allowlisted settings shared by the worker and administration."""
from dataclasses import dataclass

SITE_ORIGIN = 'https://www.sussurrosdosaber.com'
SEO_PATHS = ('/', '/en/', '/artigos', '/en/artigos', '/noticias', '/en/news',
             '/videos', '/en/videos', '/revistas', '/en/revistas')
RESEARCH_TOPICS = {
    'astronomia': 'astronomy', 'matematica': 'mathematics', 'educacao': 'science education',
    'clima': 'climate science', 'energia': 'renewable energy', 'geologia': 'geology',
    'oceanos': 'ocean science', 'ecologia': 'ecosystem conservation',
    'computacao': 'computer science education', 'historia': 'history of science',
}


@dataclass(frozen=True)
class OperatorSpec:
    name: str
    description: str
    interval: int
    settings: dict
    version: str = '1.0'


REGISTRY = {
    'editorial': OperatorSpec('Qualidade editorial', 'Revisão de conteúdo e ligações editoriais, por lotes.', 120, {'batch': 20}),
    'seo': OperatorSpec('SEO e indexação', 'Metadados técnicos, disponibilidade e directivas públicas.', 180, {'paths': ['/', '/en/', '/noticias', '/en/news'], 'timeout': 5}),
    'infrastructure': OperatorSpec('Infraestrutura e backups', 'Disponibilidade, base de dados, disco e evidência de restauro.', 60, {'timeout': 5, 'backup_age_days': 7}),
    'research': OperatorSpec('Investigação científica', 'Novas publicações e metadados bibliográficos da Crossref.', 720, {'topics': ['astronomia', 'educacao', 'clima'], 'days': 14, 'timeout': 5}),
    'workflow': OperatorSpec('Fluxo editorial', 'Processos e tarefas em atraso ou a aguardar acção.', 120, {'age_days': 7}),
}


def bounded_int(value, low, high):
    try:
        value = int(value)
    except (TypeError, ValueError):
        raise ValueError('Indique um número válido.') from None
    if not low <= value <= high:
        raise ValueError(f'Indique um valor entre {low} e {high}.')
    return value


def choices(values, allowed, maximum):
    if not isinstance(values, list) or not values or len(values) > maximum:
        raise ValueError('Seleccione uma quantidade válida de opções.')
    if any(not isinstance(value, str) or value not in allowed for value in values):
        raise ValueError('Seleccione apenas opções autorizadas.')
    return list(dict.fromkeys(values))


def validate_settings(code, raw):
    if not isinstance(raw, dict) or set(raw) - set(REGISTRY[code].settings):
        raise ValueError('Configuração inválida.')
    values = {**REGISTRY[code].settings, **raw}
    if 'timeout' in values:
        values['timeout'] = bounded_int(values['timeout'], 2, 8)
    if code == 'seo':
        values['paths'] = choices(values['paths'], SEO_PATHS, 6)
    elif code == 'research':
        values['topics'] = choices(values['topics'], RESEARCH_TOPICS, 4)
        values['days'] = bounded_int(values['days'], 1, 30)
    elif code == 'editorial':
        values['batch'] = bounded_int(values['batch'], 1, 40)
    elif code == 'workflow':
        values['age_days'] = bounded_int(values['age_days'], 1, 60)
    elif code == 'infrastructure':
        values['backup_age_days'] = bounded_int(values['backup_age_days'], 1, 60)
    return values
