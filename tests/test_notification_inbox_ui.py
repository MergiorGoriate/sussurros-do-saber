"""Private notification filters, destinations and read state across page and summary."""
from bs4 import BeautifulSoup
from datetime import timedelta
import unittest
from models import db, utcnow
from governance_models import StaffNotice
import test_lifecycle_notifications as fixtures


class NotificationInboxUITests(unittest.TestCase):
    def setUp(self):
        fixtures.LifecycleNotificationTests.setUp(self)
        from extensions import limiter
        previous=limiter.enabled;limiter.enabled=False
        self.addCleanup(setattr,limiter,'enabled',previous)

    tearDown=fixtures.LifecycleNotificationTests.tearDown
    member=fixtures.LifecycleNotificationTests.member
    signin=fixtures.LifecycleNotificationTests.signin
    post=fixtures.LifecycleNotificationTests.post
    article=fixtures.LifecycleNotificationTests.article

    def alert(self,member,subject,**kwargs):
        n=StaffNotice(admin_id=member.admin_id,subject=subject,body='Actualização privada.',**kwargs)
        db.session.add(n);db.session.commit();return n

    def test_filters_counts_and_bulk_read_are_private_and_preserve_filter(self):
        owner=self.member();other=self.member()
        self.alert(owner,'Aviso por ler')
        self.alert(owner,'Aviso já lido',read_at=utcnow())
        self.alert(other,'Aviso confidencial de outra conta')
        self.signin(owner.admin)
        page=self.client.get('/admin/notificacoes?status=unread')
        soup=BeautifulSoup(page.data,'html.parser')
        cards=soup.select('.management-notice')
        self.assertEqual(len(cards),1)
        self.assertIn('Aviso por ler',cards[0].get_text())
        self.assertNotIn('Aviso confidencial',page.get_data(as_text=True))
        self.assertEqual(soup.select_one('.notice-filters [aria-current]')['href'],'/admin/notificacoes?status=unread')
        response=self.post('/admin/notificacoes?status=unread',action='read_all')
        self.assertEqual(response.status_code,303)
        self.assertTrue(response.location.endswith('?status=unread'))
        page=self.client.get(response.location)
        self.assertIn('Sem notificações por ler.'.encode(),page.data)
        self.assertEqual(StaffNotice.query.filter_by(admin_id=other.admin_id,read_at=None).count(),1)
        self.assertEqual(len(BeautifulSoup(self.client.get('/admin/notificacoes?status=read').data,'html.parser').select('.management-notice')),2)

    def test_opening_authorized_resource_marks_read_once_and_updates_summary(self):
        owner=self.member();article=self.article(owner)
        n=self.alert(owner,'Abrir artigo',resource_type='article',resource_id=article.id)
        self.signin(owner.admin)
        self.assertEqual(self.client.get('/admin/api/notificacoes').get_json()['unread'],1)
        result=self.client.get(f'/admin/notificacoes/{n.id}/abrir')
        self.assertTrue(result.location.endswith(f'/admin/fluxo-artigos/{article.id}'))
        db.session.refresh(n);timestamp=n.read_at
        self.assertIsNotNone(timestamp)
        self.client.get(f'/admin/notificacoes/{n.id}/abrir')
        db.session.refresh(n);self.assertEqual(n.read_at,timestamp)
        self.assertEqual(self.client.get('/admin/api/notificacoes').get_json()['unread'],0)

    def test_revoked_resource_has_no_dead_link_in_page_preview_or_summary(self):
        owner=self.member();reviewer=self.member('portal_reviewer');article=self.article(owner)
        n=self.alert(reviewer,'Acesso já revogado',resource_type='article',resource_id=article.id)
        self.signin(reviewer.admin)
        body=self.client.get('/admin/notificacoes').data
        soup=BeautifulSoup(body,'html.parser')
        self.assertFalse(soup.select(f'a[href="/admin/notificacoes/{n.id}/abrir"]'))
        self.assertIn('Recurso indisponível ou sem acesso.'.encode(),body)
        self.assertIsNone(self.client.get('/admin/api/notificacoes').get_json()['items'][0]['url'])
        self.assertTrue(self.client.get(f'/admin/notificacoes/{n.id}/abrir').location.endswith('/admin/notificacoes'))
        db.session.refresh(n);self.assertIsNone(n.read_at)

    def test_removed_member_notice_opens_responsibilities_for_founder(self):
        removed=self.member();removed.removed_at=utcnow();removed.status='ended';db.session.commit()
        n=StaffNotice(admin_id=self.primary.id,subject='Colaborador removido',resource_type='member',resource_id=removed.id)
        db.session.add(n);db.session.commit()
        self.signin(self.primary)
        target=self.client.get(f'/admin/notificacoes/{n.id}/abrir').location
        self.assertTrue(target.endswith(f'/admin/equipa/{removed.id}/responsabilidades'))
        self.assertEqual(self.client.get(target).status_code,200)

    def test_missing_member_has_no_destination(self):
        member=self.member('direction')
        self.alert(member,'Histórico sem ficha',resource_type='member',resource_id=2147483647)
        self.signin(member.admin)
        self.assertIsNone(self.client.get('/admin/api/notificacoes').get_json()['items'][0]['url'])

    def test_pagination_normalizes_empty_pages_and_keeps_read_filter(self):
        member=self.member()
        for i in range(31):
            db.session.add(StaffNotice(admin_id=member.admin_id,subject=f'Lida {i}',read_at=utcnow(),created_at=utcnow()-timedelta(minutes=i)))
        db.session.commit();self.signin(member.admin)
        page=self.client.get('/admin/notificacoes?status=read&page=2')
        soup=BeautifulSoup(page.data,'html.parser')
        self.assertEqual(len(soup.select('.management-notice')),1)
        self.assertIn('status=read',soup.select_one('.notice-pagination a')['href'])
        n=StaffNotice.query.filter_by(admin_id=member.admin_id).order_by(StaffNotice.created_at).first()
        response=self.post('/admin/notificacoes?status=read&page=2',action='delete',id=n.id)
        result=self.client.get(response.location,follow_redirects=True)
        self.assertEqual(result.status_code,200)
        self.assertEqual(len(BeautifulSoup(result.data,'html.parser').select('.management-notice')),30)
        self.assertIn('status=read',self.client.get('/admin/notificacoes?status=read&page=99').location)
        self.assertEqual(self.client.get('/admin/notificacoes?page=999999999999999999999999999').status_code,302)
        self.assertEqual(self.client.get('/admin/notificacoes?status=unknown').status_code,400)
        self.assertEqual(self.client.get('/admin/notificacoes?page=0').status_code,400)

    def test_empty_inbox_disables_bulk_action_and_has_clear_empty_state(self):
        member=self.member();self.signin(member.admin)
        soup=BeautifulSoup(self.client.get('/admin/notificacoes').data,'html.parser')
        self.assertIsNotNone(soup.select_one('.notifications-page button[value="read_all"][disabled]'))
        self.assertIn('Sem notificações.',soup.select_one('.notice-empty').get_text())
