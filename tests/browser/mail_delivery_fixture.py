"""Only synthetic records in the isolated browser test database."""
import json
import os
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
if not os.getenv('DATABASE_URL','').startswith('sqlite:'):
    raise RuntimeError('This browser fixture requires isolated SQLite')
from app import app
from models import db,Subscriber
from submission_models import NewsletterCampaign,EditorialNotification
with app.app_context():
    campaign=NewsletterCampaign.query.filter_by(issue='2099-W50').first()
    if campaign is None:
        campaign=NewsletterCampaign(issue='2099-W50',subject='Sussurros do Saber — Boletim 2099-W50',fingerprint='e'*64)
        db.session.add(campaign);db.session.flush()
    campaign.status='prepared';campaign.approved_at=None;campaign.scheduled_at=None
    reader=Subscriber.query.filter_by(email='mail-browser@example.test').first()
    if reader is None:
        reader=Subscriber(email='mail-browser@example.test');db.session.add(reader);db.session.flush()
    if not EditorialNotification.query.filter_by(campaign_id=campaign.id).first():
        db.session.add(EditorialNotification(recipient=reader.email,subject=campaign.subject,body='Conteúdo de teste para revisão editorial.\nNenhum e-mail real será enviado.',campaign_id=campaign.id,subscriber_id=reader.id))
    db.session.commit();print(json.dumps({'campaign_id':campaign.id}))
