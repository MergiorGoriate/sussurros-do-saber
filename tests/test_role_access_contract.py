"""Built-in roles and account prerequisites for operational staff permissions."""
import secrets
import unittest
from datetime import date, timedelta
from flask import session
from app import app
from models import db, utcnow
from governance import DEFAULT_ROLES, PERMISSIONS, has_permission, has_any_permission, eligible
from governance_models import TeamMember, TeamRole, TeamAppointment, StaffTask
import test_staff_governance as fixtures
import test_permission_matrix as matrix


class RoleAccessContractTests(unittest.TestCase):
    def setUp(self):
        fixtures.StaffGovernanceTests.setUp(self)
        from extensions import limiter
        previous=limiter.enabled
        limiter.enabled=False
        self.addCleanup(setattr,limiter,'enabled',previous)

    tearDown = fixtures.StaffGovernanceTests.tearDown
    member = fixtures.StaffGovernanceTests.member
    signin = fixtures.StaffGovernanceTests.signin
    post = fixtures.StaffGovernanceTests.post
    article = fixtures.StaffGovernanceTests.article
    manuscript = fixtures.StaffGovernanceTests.manuscript
    operation = matrix.PermissionMatrixTests.operation

    def unlinked_member(self):
        role=TeamRole(code='no_account_'+secrets.token_hex(6), name='Conta necessária', permissions=list(PERMISSIONS))
        member=TeamMember(name='Colaborador sem conta', email=self.token+'@example.org', status='active', accepted_at=utcnow())
        db.session.add_all([role,member]);db.session.flush()
        db.session.add(TeamAppointment(member=member,role=role,starts_on=date.today()))
        db.session.commit()
        return member

    def test_no_account_never_grants_permissions_or_eligibility(self):
        member=self.unlinked_member()
        for permission in PERMISSIONS:
            with self.subTest(permission=permission):
                self.assertFalse(has_permission(permission,member=member))
                self.assertNotIn(member,eligible(permission))
                self.assertFalse(has_permission(permission,self.journal.id,member=member))

    def test_tasks_cannot_be_created_or_reassigned_to_inaccessible_account(self):
        inaccessible=self.unlinked_member()
        assignee=self.member()
        task=StaffTask(title='Responsabilidade acessível',assignee=assignee,due_on=date.today(),created_by=self.primary.id)
        db.session.add(task);db.session.commit()
        self.signin(self.primary)
        self.assertEqual(self.post('/admin/trabalho',title='Tarefa impossível',assignee_id=inaccessible.id,due_on=str(date.today())).status_code,400)
        self.assertEqual(self.post('/admin/trabalho',id=task.id,status='pending',assignee_id=inaccessible.id).status_code,400)
        self.assertEqual(self.post(f'/admin/equipa/{assignee.id}/responsabilidades',kind='task',resource_id=task.id,target_id=inaccessible.id).status_code,400)
        db.session.refresh(task)
        self.assertEqual(task.assignee_id,assignee.id)
        self.assertIsNone(StaffTask.query.filter_by(title='Tarefa impossível').first())

    def test_each_default_role_grants_exact_permissions_and_revokes_them_live(self):
        for code,name,purpose,permissions in DEFAULT_ROLES:
            with self.subTest(role=code):
                member=self.member(code)
                # Existing role customisations are valid; isolate the factory configuration.
                role=TeamRole(code='contract_'+secrets.token_hex(6),name=name,purpose=purpose,permissions=permissions)
                db.session.add(role);db.session.flush()
                grant=member.appointments[0];grant.role=role
                db.session.commit()
                self.signin(member.admin)
                with app.test_request_context():
                    session['admin_id']=member.admin_id
                    for permission in PERMISSIONS:
                        self.assertEqual(has_permission(permission),permission in permissions,(code,permission))
                        self.assertEqual(has_any_permission(permission),permission in permissions,(code,permission))
                    grant.active=False;db.session.commit()
                    for permission in permissions:self.assertFalse(has_permission(permission))
                    grant.active=True;member.status='suspended';db.session.commit()
                    for permission in permissions:self.assertFalse(has_permission(permission))
                    member.status='active';member.accepted_at=None;db.session.commit()
                    for permission in permissions:self.assertFalse(has_permission(permission))
                    member.accepted_at=utcnow();grant.ends_on=date.today()-timedelta(days=1);db.session.commit()
                    for permission in permissions:self.assertFalse(has_permission(permission))
                    grant.ends_on=None;grant.starts_on=date.today()+timedelta(days=1);db.session.commit()
                    for permission in permissions:self.assertFalse(has_permission(permission))
                    grant.starts_on=date.today();member.admin.active=False;db.session.commit()
                    for permission in permissions:self.assertFalse(has_permission(permission))
                    member.admin.active=True;member.removed_at=utcnow();db.session.commit()
                    for permission in permissions:self.assertFalse(has_permission(permission))
                    member.removed_at=None;db.session.commit()
                    for permission in permissions:self.assertTrue(has_permission(permission))

    def test_every_builtin_role_executes_its_real_allowed_operations(self):
        for code,name,purpose,permissions in DEFAULT_ROLES:
            for permission in permissions:
                with self.subTest(role=code,permission=permission):
                    member=self.member(code)
                    role=TeamRole(code='operation_'+secrets.token_hex(6),name=name,permissions=permissions)
                    db.session.add(role);db.session.flush()
                    member.appointments[0].role=role
                    db.session.commit()
                    ui,action,data,check=self.operation(permission,member)
                    self.signin(member.admin)
                    self.assertEqual(self.client.get(ui).status_code,200,(code,permission,ui))
                    response=self.post(action,**data) if data is not None else self.client.get(action)
                    self.assertEqual(response.status_code,200 if data is None or permission=='categories.manage' else 302,(code,permission,response.data[:300]))
                    self.assertTrue(check(),(code,permission))
