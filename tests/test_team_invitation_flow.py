"""Team forms, scoped mandates and explicit account linking of existing invitations."""
from datetime import date
import secrets
import unittest
from bs4 import BeautifulSoup
from models import db, AdminUser, utcnow
from governance import has_permission
from governance_models import TeamMember, TeamRole, TeamAppointment, GovernanceAudit, StaffNotice
import test_staff_governance as fixtures


class TeamInvitationFlowTests(unittest.TestCase):
    def setUp(self):
        fixtures.StaffGovernanceTests.setUp(self)
        from extensions import limiter
        previous=limiter.enabled
        limiter.enabled=False
        self.addCleanup(setattr,limiter,'enabled',previous)

    tearDown=fixtures.StaffGovernanceTests.tearDown
    member=fixtures.StaffGovernanceTests.member
    signin=fixtures.StaffGovernanceTests.signin
    post=fixtures.StaffGovernanceTests.post

    def data(self,member):
        return dict(id=member.id,name=member.name,email=member.email,status=member.status,group=member.group,
                    admin_id=member.admin_id or '',author_id=member.author_id or '',acceptance_recorded='on',available='on')

    def unlinked(self,active=False):
        m=TeamMember(name='Convite '+self.token,email=secrets.token_hex(6)+'@example.org',status='active' if active else 'invited',accepted_at=utcnow() if active else None)
        db.session.add(m);db.session.flush()
        db.session.add(TeamAppointment(member=m,role=TeamRole.query.filter_by(code='portal_reviewer').one(),starts_on=date.today()))
        db.session.commit()
        return m

    def account_data(self,member):
        return dict(member_id=member.id,display_name='Conta da equipa',username='team-'+secrets.token_hex(6),
                    email=member.email,password='test-account-password-2026',password_confirmation='test-account-password-2026')

    def test_invalid_member_identifiers_never_create_or_unlink_records(self):
        self.signin(self.primary)
        for field in ['id','admin_id','author_id']:
            for invalid in ['bad','0','-1','1_0','2147483648']:
                with self.subTest(field=field,value=invalid):
                    member=self.member() if field!='id' else self.unlinked()
                    data=self.data(member);data[field]=invalid
                    before=TeamMember.query.count()
                    old=(member.admin_id,member.author_id)
                    self.assertEqual(self.post('/admin/equipa',**data).status_code,400)
                    db.session.refresh(member)
                    self.assertEqual((member.admin_id,member.author_id),old)
                    self.assertEqual(TeamMember.query.count(),before)

    def test_invalid_journal_scope_never_creates_global_mandate(self):
        member=self.unlinked()
        role=TeamRole.query.filter_by(code='chief_editor').one()
        self.signin(self.primary)
        for field in ['journal_id','substitute_id','role_id']:
            for invalid in ['bad','0','-1','1_0','2147483648']:
                with self.subTest(field=field,value=invalid):
                    data=dict(role_id=role.id,journal_id=self.journal.id,starts_on=str(date.today()))
                    data[field]=invalid
                    before=TeamAppointment.query.count()
                    self.assertEqual(self.post(f'/admin/equipa/{member.id}/mandatos',**data).status_code,400)
                    self.assertEqual(TeamAppointment.query.count(),before)

    def test_identical_mandate_retry_has_one_record_audit_and_notice(self):
        member=self.member()
        role=TeamRole.query.filter_by(code='portal_reviewer').one()
        self.signin(self.primary)
        path=f'/admin/equipa/{member.id}/mandatos'
        data=dict(role_id=role.id,starts_on=str(date.today()),weekly_hours='4',area='Divulgação',conditions='Revisão fundamentada')
        before=StaffNotice.query.filter_by(admin_id=member.admin_id).count()
        self.assertEqual(self.post(path,**data).status_code,302)
        self.assertEqual(self.post(path,**data).status_code,302)
        self.assertEqual(TeamAppointment.query.filter_by(member_id=member.id,role_id=role.id,starts_on=date.today()).count(),1)
        self.assertEqual(GovernanceAudit.query.filter_by(action='mandate.created',entity_id=member.id).count(),1)
        self.assertEqual(StaffNotice.query.filter_by(admin_id=member.admin_id).count(),before+1)

    def test_removed_or_missing_member_is_not_shown_as_editable(self):
        member=self.unlinked();member.removed_at=utcnow();db.session.commit()
        self.signin(self.primary)
        self.assertEqual(self.client.get(f'/admin/equipa?edit={member.id}').status_code,410)
        self.assertEqual(self.client.get('/admin/equipa?edit=2147483647').status_code,404)
        self.assertEqual(self.client.get('/admin/equipa?edit=bad').status_code,400)
        self.assertEqual(self.post('/admin/equipa',**self.data(member)).status_code,409)

    def test_account_and_author_choices_exclude_founder_and_other_members_links(self):
        selected=self.member();occupied=self.member()
        account=AdminUser(username='free-'+self.token,display_name='Conta disponível',password_hash='unused',governance_managed=True)
        db.session.add(account);db.session.commit()
        self.signin(self.primary)
        soup=BeautifulSoup(self.client.get(f'/admin/equipa?edit={selected.id}').data,'html.parser')
        accounts={o.get('value') for o in soup.select('select[name="admin_id"] option')}
        authors={o.get('value') for o in soup.select('select[name="author_id"] option')}
        self.assertIn(str(selected.admin_id),accounts)
        self.assertIn(str(account.id),accounts)
        self.assertNotIn(str(occupied.admin_id),accounts)
        self.assertNotIn(str(self.primary.id),accounts)
        self.assertIn(str(selected.author_id),authors)
        self.assertNotIn(str(occupied.author_id),authors)

    def test_team_manager_keeps_links_without_being_offered_founder_controls(self):
        manager=self.member('direction');target=self.member()
        self.signin(manager.admin)
        soup=BeautifulSoup(self.client.get(f'/admin/equipa?edit={target.id}').data,'html.parser')
        self.assertFalse(soup.select('select[name="admin_id"],select[name="author_id"]'))
        self.assertEqual(soup.select_one('input[name="admin_id"]')['value'],str(target.admin_id))
        self.assertEqual(self.post('/admin/equipa',**self.data(target)).status_code,302)
        data=self.data(target);data['admin_id']=''
        self.assertEqual(self.post('/admin/equipa',**data).status_code,403)
        db.session.refresh(target)
        self.assertIsNotNone(target.admin_id)

    def test_existing_invitation_account_preserves_member_and_does_not_activate_it(self):
        member=self.unlinked()
        grant_id=member.appointments[0].id
        before=TeamMember.query.count()
        self.signin(self.primary)
        page=self.client.get(f'/admin/administradores?member_id={member.id}')
        self.assertEqual(page.status_code,200)
        soup=BeautifulSoup(page.data,'html.parser')
        self.assertEqual(soup.select_one('select[name="member_id"] option[selected]')['value'],str(member.id))
        self.assertEqual(self.post('/admin/administradores',**self.account_data(member)).status_code,302)
        db.session.refresh(member)
        self.assertIsNotNone(member.admin_id)
        self.assertEqual(TeamMember.query.count(),before)
        self.assertEqual(member.status,'invited')
        self.assertIsNone(member.accepted_at)
        self.assertEqual(member.appointments[0].id,grant_id)
        self.assertFalse(has_permission('article.review',member=member))
        self.assertTrue(StaffNotice.query.filter_by(admin_id=member.admin_id,resource_type='member',resource_id=member.id).count())

    def test_existing_active_member_keeps_acceptance_and_mandates_when_account_created(self):
        member=self.unlinked(active=True)
        accepted=member.accepted_at
        self.signin(self.primary)
        self.assertEqual(self.post('/admin/administradores',**self.account_data(member)).status_code,302)
        db.session.refresh(member)
        self.assertEqual(member.status,'active')
        self.assertEqual(member.accepted_at,accepted)
        self.assertTrue(has_permission('article.review',member=member))

    def test_removed_or_linked_invitation_and_invalid_ids_cannot_create_account(self):
        removed=self.unlinked();removed.removed_at=utcnow();linked=self.member();db.session.commit()
        self.signin(self.primary)
        for member in [removed,linked]:
            before=AdminUser.query.count()
            self.assertEqual(self.post('/admin/administradores',**self.account_data(member)).status_code,409)
            self.assertEqual(AdminUser.query.count(),before)
        data=self.account_data(removed);data['member_id']='bad'
        self.assertEqual(self.post('/admin/administradores',**data).status_code,400)
