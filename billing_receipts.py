"""Private internal payment evidence, rendered without remote assets or user card data."""
from io import BytesIO
from xml.sax.saxutils import escape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle


def render_receipt(order, entries):
    output=BytesIO()
    styles=getSampleStyleSheet()
    def text(value):return Paragraph(escape(str(value)),styles['BodyText'])
    story=[Paragraph('Sussurros do Saber',styles['Title']),
           Paragraph('Comprovativo interno de pagamento',styles['Heading1'])]
    if not order.live:story.append(Paragraph('TESTE - sem valor de pagamento real',styles['Heading2']))
    story.extend([text('Pedido: '+order.id),text('Plano: '+order.snapshot.get('name','')),
                  text('Fornecedor: '+order.provider),text('Referência: '+(order.payment_ref or order.provider_ref or order.id)),Spacer(1,16)])
    rows=[[text('Registo / data UTC'),text('Movimento'),text('Valor')]]
    for entry in entries:
        rows.append([text(str(entry.id)+' / '+entry.created_at.strftime('%Y-%m-%d %H:%M:%S')),
                     text('Recebimento' if entry.kind=='receipt' else 'Reembolso'),
                     text(f'{entry.amount_minor//100},{entry.amount_minor%100:02d} {entry.currency}')])
    table=Table(rows,colWidths=[220,130,130],repeatRows=1)
    table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#e7eef6')),
                              ('VALIGN',(0,0),(-1,-1),'TOP'),('BOTTOMPADDING',(0,0),(-1,-1),12)]))
    story.extend([table,Spacer(1,18),text('Este comprovativo interno não substitui uma factura fiscal nem prova liquidação bancária. Os reembolsos registados são apresentados separadamente. Não contém dados de cartão ou credenciais bancárias.')])
    SimpleDocTemplate(output,title='Comprovativo '+order.id,author='Sussurros do Saber').build(story)
    output.seek(0)
    return output
