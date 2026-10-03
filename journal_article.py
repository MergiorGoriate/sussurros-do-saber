"""Campos opcionais e ordem de apresentação do artigo científico."""
PREFIX_FIELDS = (("summary", "Resumo"), ("keywords", "Palavras-chave"),
                 ("abstract", "Abstract"), ("abstract_keywords", "Keywords"))
DECLARATION_FIELDS = (("author_contributions", "Contribuição dos autores"),
                      ("acknowledgements", "Agradecimentos"), ("funding", "Financiamento"),
                      ("conflicts_of_interest", "Conflitos de interesse"),
                      ("ethics_approval", "Aprovação ética"),
                      ("informed_consent", "Consentimento informado"),
                      ("data_availability", "Disponibilidade de dados"))
ARTICLE_FIELD_LIMITS = {name: (2000 if name in {"keywords", "abstract_keywords"} else 20000)
                        for name, _ in (*PREFIX_FIELDS, *DECLARATION_FIELDS, ("notes", "Notas"))}


def render_article_fields(source, fields, render_markdown):
    sections = []
    for name, label in fields:
        value = (getattr(source, name, "") or "").strip()
        if value:
            sections.append(f'<section class="journal-article-section" data-article-field="{name}"><h2>{label}</h2>{render_markdown(value)}</section>')
    return "".join(sections)


def structured_article_content(source, body_html, render_markdown):
    return (render_article_fields(source, PREFIX_FIELDS, render_markdown) + body_html +
            render_article_fields(source, DECLARATION_FIELDS, render_markdown))
