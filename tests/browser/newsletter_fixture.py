"""Synthetic cancellation link in an isolated E2E database."""
import json
import os
import secrets
import sys
from pathlib import Path

if not os.environ.get('DATABASE_URL','').startswith('sqlite:') or os.environ.get('FLASK_ENV')=='production' or os.environ.get('RENDER','').lower()=='true':
    raise RuntimeError('Newsletter fixture requires isolated SQLite outside production')
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from app import app
from models import Subscriber, db
from newsletter_service import unsubscribe_token

with app.app_context():
    subscriber=Subscriber(email='newsletter-'+secrets.token_hex(8)+'@example.test')
    db.session.add(subscriber);db.session.commit()
    print(json.dumps({'email':subscriber.email,'path':'/boletim/cancelar/'+unsubscribe_token(subscriber)}))
