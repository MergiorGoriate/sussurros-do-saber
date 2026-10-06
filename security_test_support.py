"""Create current credential-bound sessions for existing test fixtures only."""
from admin import admin_security_stamp
from app import app
from models import AdminUser, db


def authenticate_test_session(session):
    with app.app_context():
        identifier = session.get('admin_id')
        account = db.session.get(AdminUser, identifier) if identifier is not None else None
        if identifier is None:
            primary = bool(session.get('admin_superuser'))
            username = 'fixture-primary' if primary else 'fixture-editor'
            account = AdminUser.query.filter_by(username=username).first()
            if account is None:
                account = AdminUser(username=username, display_name='Test fixture',
                                    password_hash='unused-test-fixture', is_superadmin=primary,
                                    two_factor_enabled=True, totp_secret='JBSWY3DPEHPK3PXP')
                db.session.add(account)
                db.session.commit()
            account.is_superadmin = primary
            db.session.commit()
            session['admin_id'] = account.id
            session['admin_2fa_verified'] = True
        session['admin_security_stamp'] = admin_security_stamp(account)
