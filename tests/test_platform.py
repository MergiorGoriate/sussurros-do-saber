import os
import tempfile
import unittest


database_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
database_file.close()
os.environ["DATABASE_URL"] = f"sqlite:///{database_file.name}"
os.environ["SECRET_KEY"] = "test-secret-key"
os.environ["ADMIN_USERNAME"] = "admin"
os.environ["ADMIN_PASSWORD"] = "a-strong-test-password"

from app import app, render_markdown, responsive_image_url, social_image_url  # noqa: E402
from sqlalchemy import inspect
from models import AdminUser, Article, Author, Journal, db  # noqa: E402


class PlatformTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app.config.update(TESTING=True, RATELIMIT_ENABLED=False)
        cls.client = app.test_client()

    @classmethod
    def tearDownClass(cls):
        with app.app_context():
            db.session.remove()
            db.engine.dispose()
        os.unlink(database_file.name)

    def test_cookie_consent_controls_and_policy_are_available(self):
        response = self.client.get("/")
        self.assertIn(b'id="cookieConsent"', response.data)
        self.assertIn(b'id="cookieAccept"', response.data)
        self.assertIn(b'id="cookieReject"', response.data)
        self.assertIn(b'id="cookieSettingsLink"', response.data)
        policy = self.client.get("/politica-de-privacidade")
        self.assertIn("Cookies e consentimento".encode(), policy.data)

    def test_footer_contains_accessible_social_links(self):
        response = self.client.get("/")
        for network in ["Facebook", "Instagram", "YouTube", "LinkedIn", "X", "WhatsApp"]:
            self.assertIn(f'aria-label="'.encode(), response.data)
            self.assertIn(network.encode(), response.data)

    def test_public_routes_and_discovery_files(self):
        for path in ["/", "/artigos", "/autores", "/revistas", "/contacto", "/feed.xml", "/sitemap.xml", "/robots.txt", "/healthz"]:
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 200)

    def test_article_sharing_uses_cover_image(self):
        with app.app_context():
            article = Article.public_query().first()
            slug = article.slug
            expected_image = social_image_url(article.image)
        response = self.client.get(f"/artigo/{slug}")
        self.assertEqual(response.status_code, 200)
        self.assertIn(f'<meta property="og:image" content="{expected_image}">'.encode(), response.data)
        self.assertIn(f'<meta property="og:image:url" content="{expected_image}">'.encode(), response.data)
        self.assertIn(f'<meta name="twitter:image" content="{expected_image}">'.encode(), response.data)
        self.assertIn(b'<meta name="twitter:card" content="summary_large_image">', response.data)
        self.assertIn(b'?share=', response.data)

    def test_external_social_images_are_converted_to_jpeg(self):
        previous = os.environ.get("CLOUDINARY_CLOUD_NAME")
        os.environ["CLOUDINARY_CLOUD_NAME"] = "demo"
        try:
            source = "https://commons.wikimedia.org/wiki/Special:FilePath/Neuron_Hand-tuned.svg"
            result = social_image_url(source)
            self.assertTrue(result.startswith("https://res.cloudinary.com/demo/image/fetch/"))
            self.assertIn("f_jpg,q_auto:good,w_1200,h_630,c_fill,g_auto,fl_force_strip", result)
            self.assertIn("Neuron_Hand-tuned.svg", result)
            self.assertNotEqual(result, source)
        finally:
            if previous is None:
                os.environ.pop("CLOUDINARY_CLOUD_NAME", None)
            else:
                os.environ["CLOUDINARY_CLOUD_NAME"] = previous

    def test_external_images_use_responsive_cloudinary_fetch(self):
        previous = os.environ.get("CLOUDINARY_CLOUD_NAME")
        os.environ["CLOUDINARY_CLOUD_NAME"] = "demo"
        try:
            result = responsive_image_url("https://example.org/large-image.jpg", 480)
            self.assertIn("/image/fetch/f_auto,q_auto:eco,w_480,c_limit/", result)
            self.assertIn("https%3A%2F%2Fexample.org%2Flarge-image.jpg", result)
        finally:
            if previous is None:
                os.environ.pop("CLOUDINARY_CLOUD_NAME", None)
            else:
                os.environ["CLOUDINARY_CLOUD_NAME"] = previous

    def test_static_assets_have_long_immutable_cache(self):
        response = self.client.get("/static/css/style.css")
        self.assertIn("max-age=31536000", response.headers.get("Cache-Control", ""))
        self.assertIn("immutable", response.headers.get("Cache-Control", ""))

    def test_articles_are_paginated(self):
        response = self.client.get("/artigos?page=1")
        self.assertEqual(response.status_code, 200)
        self.assertLessEqual(response.data.count(b'class="story-card group relative"'), 12)

    def test_cloudinary_images_get_responsive_variants(self):
        source = "https://res.cloudinary.com/demo/image/upload/sample.webp"
        self.assertIn(
            "/upload/f_auto,q_auto:eco,w_480,c_limit/",
            responsive_image_url(source, 480),
        )
        self.assertEqual(
            responsive_image_url("https://example.org/image.jpg", 480),
            "https://example.org/image.jpg",
        )

    def test_markdown_renders_tables_and_safe_charts(self):
        table = render_markdown("| Grupo | Valor |\n| --- | --- |\n| A | 12 |")
        self.assertIn("<table>", str(table))
        chart = render_markdown("[chart: bar|Participantes|Grupo A=12; Grupo B=8]")
        self.assertIn('class="article-chart"', str(chart))
        self.assertIn("<svg", str(chart))
        self.assertIn("Participantes", str(chart))

    def test_invalid_chart_data_is_not_embedded(self):
        chart = render_markdown("[chart: pie|Teste|A=texto]")
        self.assertNotIn('class="article-chart"', str(chart))

    def test_gzip_compression_for_public_html(self):
        response = self.client.get("/", headers={"Accept-Encoding": "gzip"})
        self.assertEqual(response.headers.get("Content-Encoding"), "gzip")
        self.assertIn("Accept-Encoding", response.headers.get("Vary", ""))

    def test_security_headers(self):
        response = self.client.get("/", base_url="https://sussurrosdosaber.com")
        self.assertIn("default-src 'self'", response.headers["Content-Security-Policy"])
        self.assertIn("max-age=31536000", response.headers["Strict-Transport-Security"])
        self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")

    def test_input_validation(self):
        self.assertEqual(self.client.post("/api/newsletter", json={"email": "invalido"}).status_code, 400)
        self.assertEqual(self.client.post("/api/contacto", json={}).status_code, 400)
        self.assertEqual(self.client.post("/api/assistente", json={"message": ""}).status_code, 400)

    def test_admin_is_protected_and_not_indexed(self):
        response = self.client.get("/admin")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["X-Robots-Tag"], "noindex, nofollow")

    def test_administrator_can_be_created_and_sign_in(self):
        with self.client.session_transaction() as session:
            session["admin_authenticated"] = True
            session["admin_superuser"] = True
            session["csrf_token"] = "test-csrf"
        response = self.client.post("/admin/administradores", data={
            "csrf_token": "test-csrf",
            "display_name": "Editor Científico",
            "username": "editor.cientifico",
            "email": "editor@example.org",
            "password": "uma-palavra-passe-segura",
            "password_confirmation": "uma-palavra-passe-segura",
        })
        self.assertEqual(response.status_code, 302)
        with app.app_context():
            self.assertIsNotNone(AdminUser.query.filter_by(username="editor.cientifico").first())
        with self.client.session_transaction() as session:
            session.clear()
            session["csrf_token"] = "login-csrf"
        response = self.client.post("/admin/login", data={"csrf_token": "login-csrf", "username": "editor.cientifico", "password": "uma-palavra-passe-segura"})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.location.endswith("/admin"))
        with self.client.session_transaction() as session:
            self.assertFalse(session["admin_superuser"])
            session.clear()
            session["admin_authenticated"] = True
            session["admin_superuser"] = True
            session["csrf_token"] = "manage-csrf"
        with app.app_context():
            administrator = AdminUser.query.filter_by(username="editor.cientifico").first()
            administrator_id = administrator.id
        response = self.client.post(f"/admin/administradores/{administrator_id}/editar", data={
            "csrf_token": "manage-csrf",
            "display_name": "Editor Atualizado",
            "username": "editor.atualizado",
            "email": "atualizado@example.org",
            "password": "",
            "password_confirmation": "",
            "active": "on",
        })
        self.assertEqual(response.status_code, 302)
        with app.app_context():
            self.assertIsNotNone(AdminUser.query.filter_by(username="editor.atualizado").first())
        response = self.client.post(
            f"/admin/administradores/{administrator_id}/eliminar",
            data={"csrf_token": "manage-csrf"},
        )
        self.assertEqual(response.status_code, 302)
        with app.app_context():
            self.assertIsNone(db.session.get(AdminUser, administrator_id))

    def test_author_photo_url_is_saved_and_rendered(self):
        with self.client.session_transaction() as session:
            session.clear()
            session["admin_authenticated"] = True
            session["csrf_token"] = "author-csrf"
        response = self.client.post("/admin/autores", data={
            "csrf_token": "author-csrf",
            "name": "Autora com Fotografia",
            "email": "autora.foto@example.org",
            "bio": "Investigadora e divulgadora científica.",
            "photo_url": "https://images.example.org/autora.webp",
        })
        self.assertEqual(response.status_code, 302)
        with app.app_context():
            author = Author.query.filter_by(email="autora.foto@example.org").first()
            self.assertEqual(author.photo, "https://images.example.org/autora.webp")
        response = self.client.get("/autores")
        self.assertIn(b"https://images.example.org/autora.webp", response.data)

    def test_journal_schema_contains_all_management_columns(self):
        with app.app_context():
            columns = {column["name"] for column in inspect(db.engine).get_columns("journal")}
        self.assertTrue({
            "issn", "frequency", "current_issue", "guidelines",
            "cover_image", "cover_alt", "published", "created_at", "updated_at",
        }.issubset(columns))

    def test_journal_can_be_managed_and_published(self):
        with self.client.session_transaction() as session:
            session.clear()
            session["admin_authenticated"] = True
            session["csrf_token"] = "journal-csrf"
        response = self.client.post("/admin/revistas/nova", data={
            "csrf_token": "journal-csrf",
            "title": "Revista de Teste Científico",
            "description": "Uma descrição suficientemente completa para a revista científica.",
            "field": "Ciências Biológicas",
            "abbreviation": "RTC",
            "issn": "1234-567X",
            "frequency": "Semestral",
            "current_issue": "Vol. 1 · N.º 1",
            "guidelines": "Diretrizes editoriais da revista.",
            "published": "on",
        })
        self.assertEqual(response.status_code, 302)
        with app.app_context():
            journal = Journal.query.filter_by(slug="revista-de-teste-cientifico").first()
            self.assertIsNotNone(journal)
            self.assertTrue(journal.published)
        response = self.client.get("/revistas/revista-de-teste-cientifico")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Revista de Teste Científico".encode(), response.data)

    def test_secondary_administrator_cannot_manage_accounts(self):
        with self.client.session_transaction() as session:
            session.clear()
            session["admin_authenticated"] = True
            session["admin_superuser"] = False
            session["csrf_token"] = "secondary-csrf"
        self.assertEqual(self.client.get("/admin/administradores").status_code, 403)

    def test_z_homepage_supports_empty_database(self):
        with app.app_context():
            Article.query.delete()
            db.session.commit()
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Novos artigos estão a ser preparados".encode(), response.data)


if __name__ == "__main__":
    unittest.main()
