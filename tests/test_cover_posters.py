"""Video-only covers must deliver images without loading video on article lists."""
import unittest
from cover_media import cover_poster_url
import test_article_covers as fixtures
VIDEO = fixtures.VIDEO
from app import app
from models import db
from bs4 import BeautifulSoup


class CoverPosterURLTests(unittest.TestCase):
    def test_video_frame_and_explicit_photograph(self):
        poster = VIDEO.replace('/upload/', '/upload/so_0/').replace('.mp4', '.jpg')
        self.assertEqual(cover_poster_url('', VIDEO), poster)
        self.assertEqual(cover_poster_url(VIDEO), poster)
        self.assertEqual(cover_poster_url('https://example.org/photo.jpg', VIDEO), 'https://example.org/photo.jpg')

    def test_unusable_and_untrusted_values_do_not_become_images(self):
        for value in ['javascript:alert(1)', 'https://res.cloudinary.com.evil/x.mp4',
                      'https://user:secret@res.cloudinary.com/c/video/upload/a.mp4',
                      'https://example.org/video.mp4', 'https://res.cloudinary.com/c/video/upload/../a.mp4']:
            self.assertEqual(cover_poster_url('', value), '')
        self.assertEqual(cover_poster_url('', VIDEO+'?signature=abc'), '')


class VideoOnlyArticleTests(unittest.TestCase):
    setUp = fixtures.ArticleCoverTests.setUp
    tearDown = fixtures.ArticleCoverTests.tearDown
    member = fixtures.ArticleCoverTests.member
    article = fixtures.ArticleCoverTests.article

    def test_poster_is_used_in_detail_lists_favourites_metadata_and_api(self):
        owner = self.member()
        article = self.article(owner)
        article.status = 'published'
        article.image = ''
        article.cover_video = VIDEO
        article.cover_mode = 'video_controls'
        article.featured = True
        db.session.commit()
        client = app.test_client()
        for path in ['/', '/artigos', '/artigo/'+article.slug, '/autor/'+article.author_rel.slug]:
            response = client.get(path)
            self.assertEqual(response.status_code, 200, path)
            soup = BeautifulSoup(response.data, 'html.parser')
            images = [img for img in soup.select('img') if 'sample.jpg' in img.get('src', '')]
            self.assertTrue(images, path)
            self.assertFalse(any('.mp4' in img.get('src', '') for img in soup.select('img')), path)
            if path == '/artigo/'+article.slug:
                self.assertIn('sample.jpg', soup.select_one('meta[property="og:image"]')['content'])
                self.assertTrue(soup.select_one('video')['data-src'].endswith('.mp4'))
            else:
                self.assertFalse(soup.select('video.cover-video'))
        response = client.get('/api/artigos')
        self.assertEqual(response.status_code, 200)
        self.assertIn('sample.jpg', response.get_data(as_text=True))
