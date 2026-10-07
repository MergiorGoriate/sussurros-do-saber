"""Produce a credential-bound synthetic principal cookie for browser layout tests.
Login and 2FA are covered by the existing browser suite; no app bypass is added.
"""
import os
import sys
import time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from app import app
from admin import admin_security_stamp
with app.app_context():
    cookie=app.session_interface.get_signing_serializer(app).dumps({
        'admin_authenticated':True,'admin_id':None,'admin_username':os.environ['ADMIN_USERNAME'],
        'admin_superuser':True,'admin_last_activity_at':time.time(),'admin_2fa_verified':True,
        'admin_security_stamp':admin_security_stamp(), 'csrf_token':'browser-staff-fixture',
    })
    print(cookie)
