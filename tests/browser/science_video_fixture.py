"""Seed a synthetic watch page in the browser suite's isolated database."""
import os
from pathlib import Path
import sys

if not os.environ.get('DATABASE_URL', '').startswith('sqlite:') or os.environ.get('FLASK_ENV') == 'production':
    raise RuntimeError('Use an isolated browser test database.')

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app import app
from models import Category, db, utcnow
from video_media import media_fields
from video_models import ScienceVideo

with app.app_context():
    if not ScienceVideo.query.filter_by(language='en', slug='science-video-e2e').first():
        category = Category.query.filter_by(name='Saúde').one()
        db.session.add(ScienceVideo(
            language='en', slug='science-video-e2e', title='Synthetic science video',
            description='Browser test fixture', author='Test author', duration=1,
            thumbnail='https://example.test/science-video-e2e.jpg', category=category,
            status='published', published_at=utcnow(),
            **media_fields('https://example.test/science-video-e2e.webm', legacy=True),
        ))
        db.session.commit()
