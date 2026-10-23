"""Catalogue filtering, configured terms, migration and existing authorisation boundaries."""
import unittest
from sqlalchemy import create_engine, text
import test_premium as existing
from models import db
from premium_models import PremiumPlan, PremiumContent, PremiumAudit
from premium_catalogue_schema import upgrade_catalogue_schema


class CatalogueTests(unittest.TestCase):
    setUp = existing.PremiumTests.setUp
    tearDown = existing.PremiumTests.tearDown
    admin = existing.PremiumTests.admin
    login = existing.PremiumTests.login
    grant = existing.PremiumTests.grant
    plan_form = existing.PremiumTests.plan_form

    def test_search_combines_metadata_type_category_and_never_body(self):
        self.item.category = 'Investigação'
        db.session.add(PremiumContent(title='Outro', summary='Resumo', body='SEGREDO-PREMIUM', category='Saúde', kind='event', published=True))
        db.session.commit()
        response = self.client.get('/premium/biblioteca', query_string={'q':'métodos','tipo':'course','categoria':'Investigação'})
        self.assertEqual(response.status_code, 200)
        self.assertIn('Curso de métodos', response.text)
        self.assertNotIn('Outro', response.text)
        self.assertNotIn('SEGREDO-PREMIUM', response.text)
        self.assertIn('0 recursos encontrados', self.client.get('/premium/biblioteca?q=SEGREDO-PREMIUM').text)

    def test_search_wildcards_are_literal_and_input_bounded(self):
        for q in ['%', '_', '<script>']:
            self.assertIn('0 recursos encontrados', self.client.get('/premium/biblioteca', query_string={'q':q}).text)
        self.assertEqual(self.client.get('/premium/biblioteca', query_string={'q':'x'*121}).status_code, 400)
        self.assertEqual(self.client.get('/premium/biblioteca', query_string={'categoria':'x'*81}).status_code, 400)

    def test_categories_hide_drafts_and_filters_survive_pagination(self):
        self.item.category='Pública'
        db.session.add(PremiumContent(title='Rascunho',summary='Resumo',body='privado',category='OCULTA',kind='course',published=False))
        for i in range(13):
            db.session.add(PremiumContent(title=f'Recurso {i}',summary='Resumo',body='privado',category='Pública',kind='course',published=True))
        db.session.commit()
        response=self.client.get('/premium/biblioteca?tipo=course&q=Recurso&categoria=Pública')
        self.assertNotIn('OCULTA',response.text)
        self.assertIn('page=2',response.text)
        self.assertIn('q=Recurso',response.text)
        self.assertIn('categoria=',response.text)
        self.assertIn('Sem resultados',self.client.get('/premium/biblioteca?q=inexistente').text)

    def test_benefits_configurable_escaped_and_audited(self):
        self.admin()
        response=self.client.post('/admin/premium/planos/novo',data=self.plan_form(benefits='Curso avançado\n<script>exemplo</script>'))
        self.assertEqual(response.status_code,302)
        plan=PremiumPlan.query.filter_by(name='Novo plano anual').one()
        self.assertEqual(plan.benefits,['Curso avançado','<script>exemplo</script>'])
        self.assertEqual(PremiumAudit.query.one().detail['after']['benefits'],plan.benefits)
        self.assertIn('&lt;script&gt;exemplo&lt;/script&gt;',self.client.get('/premium').text)

    def test_invalid_benefits_do_not_write(self):
        self.admin()
        for benefits in ['x'*181,'x\nx','\n'.join(str(i) for i in range(21))]:
            self.assertEqual(self.client.post('/admin/premium/planos/novo',data=self.plan_form(benefits=benefits)).status_code,400)
        self.assertEqual(PremiumPlan.query.count(),1)

    def test_subscriber_displays_immutable_terms_not_current_plan(self):
        sub=self.grant()
        sub.plan_snapshot={**sub.plan_snapshot,'benefits':['Benefício contratado']}
        self.plan.benefits=['Benefício novo']; db.session.commit(); self.login()
        response=self.client.get('/premium/pagamentos')
        self.assertEqual(response.status_code,200)
        self.assertIn('Benefício contratado',response.text)
        self.assertNotIn('Benefício novo',response.text)
        self.assertIn('Oferta sem cobrança',response.text)

    def test_empty_account_has_existing_plan_link(self):
        self.login()
        response=self.client.get('/premium/pagamentos')
        self.assertEqual(response.status_code,200)
        self.assertIn('/premium/#planos',response.text)

    def test_category_save_preserves_access_control(self):
        self.admin()
        response=self.client.post(f'/admin/premium/conteudos/{self.item.id}', data={
            'csrf_token':'premium-csrf','version':self.item.version,'title':self.item.title,
            'summary':self.item.summary,'body':self.item.body,'kind':'course','category':'Métodos','published':'on'})
        self.assertEqual(response.status_code,302)
        self.assertEqual(self.item.category,'Métodos')
        self.assertEqual(self.client.get(f'/premium/conteudos/{self.item.id}').status_code,403)


class CatalogueMigrationTests(unittest.TestCase):
    def test_actual_previous_columns_upgrade_twice_without_record_loss(self):
        engine=create_engine('sqlite://')
        with engine.begin() as connection:
            connection.exec_driver_sql('CREATE TABLE premium_plan (id INTEGER PRIMARY KEY, name TEXT)')
            connection.exec_driver_sql('CREATE TABLE premium_content (id INTEGER PRIMARY KEY, body TEXT)')
            connection.exec_driver_sql("INSERT INTO premium_plan VALUES (1, 'Plano existente')")
            connection.exec_driver_sql("INSERT INTO premium_content VALUES (2, 'Conteúdo preservado')")
            upgrade_catalogue_schema(connection);upgrade_catalogue_schema(connection)
            self.assertEqual(connection.execute(text('SELECT name, benefits FROM premium_plan')).one(),('Plano existente','[]'))
            self.assertEqual(connection.execute(text('SELECT body, category FROM premium_content')).one(),('Conteúdo preservado',''))
        engine.dispose()
