import os
import tempfile
import unittest
from unittest.mock import patch
import re
import time
from pathlib import Path


database_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
database_file.close()
os.environ["DATABASE_URL"] = f"sqlite:///{database_file.name}"
os.environ["SECRET_KEY"] = "test-secret-key"
os.environ["ADMIN_USERNAME"] = "admin"
os.environ["ADMIN_PASSWORD"] = "a-strong-test-password"

from app import app, render_markdown, responsive_image_url, safe_image_url, social_image_url  # noqa: E402
from admin import generate_recovery_codes, totp_code, verify_totp  # noqa: E402
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

    def test_google_search_console_verification_and_discovery(self):
        previous = os.environ.get("GOOGLE_SITE_VERIFICATION")
        os.environ["GOOGLE_SITE_VERIFICATION"] = '"google-test-verification-token"'
        try:
            response = self.client.get("/")
            self.assertIn(
                b'<meta name="google-site-verification" content="google-test-verification-token">',
                response.data,
            )
            self.assertNotIn(b"&quot;google-test-verification-token&quot;", response.data)

            os.environ["GOOGLE_SITE_VERIFICATION"] = (
                '<meta name="google-site-verification" '
                'content="google-complete-tag-verification" />'
            )
            response = self.client.get("/")
            self.assertIn(
                b'<meta name="google-site-verification" content="google-complete-tag-verification">',
                response.data,
            )
        finally:
            if previous is None:
                os.environ.pop("GOOGLE_SITE_VERIFICATION", None)
            else:
                os.environ["GOOGLE_SITE_VERIFICATION"] = previous

        sitemap = self.client.get("/sitemap.xml")
        self.assertEqual(sitemap.status_code, 200)
        self.assertIn(b"<urlset", sitemap.data)
        self.assertIn(b"<lastmod>", sitemap.data)
        self.assertIn("max-age=3600", sitemap.headers.get("Cache-Control", ""))

        robots = self.client.get("/robots.txt")
        self.assertIn(b"Sitemap: https://www.sussurrosdosaber.com/sitemap.xml", robots.data)
        self.assertIn(b"Disallow: /admin", robots.data)

    def test_indexing_directives_distinguish_public_and_duplicate_pages(self):
        homepage = self.client.get("/")
        self.assertIn(
            b'<meta name="robots" content="index,follow,max-image-preview:large,max-snippet:-1,max-video-preview:-1">',
            homepage.data,
        )
        filtered = self.client.get("/artigos?categoria=Biologia")
        self.assertIn(b'<meta name="robots" content="noindex,follow">', filtered.data)
        self.assertEqual(filtered.headers["X-Robots-Tag"], "noindex, follow")
        favorites = self.client.get("/favoritos")
        self.assertIn(b'<meta name="robots" content="noindex,follow">', favorites.data)
        missing = self.client.get("/artigo/nao-existe")
        self.assertEqual(missing.status_code, 404)
        self.assertEqual(missing.headers["X-Robots-Tag"], "noindex, nofollow")

    def test_sitemap_contains_canonical_articles_and_cover_images(self):
        with app.app_context():
            article = Article.public_card_query().filter(Article.image != "").first()
            self.assertIsNotNone(article)
            article_url = f"https://www.sussurrosdosaber.com/artigo/{article.slug}"
            cover_url = safe_image_url(article.image)
        response = self.client.get("/sitemap.xml")
        self.assertIn(b'xmlns:image="http://www.google.com/schemas/sitemap-image/1.1"', response.data)
        self.assertIn(article_url.encode(), response.data)
        self.assertIn(b"<image:image>", response.data)
        self.assertIn(cover_url.replace("&", "&amp;").encode(), response.data)

    def test_website_schema_and_content_language_are_present(self):
        response = self.client.get("/")
        self.assertEqual(response.headers["Content-Language"], "pt-MZ")
        self.assertIn(b'"@type":"WebSite"', response.data)
        self.assertIn(b'"@type":"SearchAction"', response.data)
        self.assertIn(b'<html lang="pt-MZ">', response.data)

    def test_google_tag_manager_consent_mode_and_events(self):
        previous = os.environ.get("GTM_CONTAINER_ID")
        os.environ["GTM_CONTAINER_ID"] = "GTM-TEST123"
        try:
            response = self.client.get("/")
            self.assertIn(b"https://www.googletagmanager.com/gtm.js?id=", response.data)
            self.assertIn(b"GTM-TEST123", response.data)
            self.assertIn(b"analytics_storage:'denied'", response.data)
            self.assertIn("'strict-dynamic'", response.headers["Content-Security-Policy"])
            javascript = self.client.get("/static/js/main.js").data
            for event in [b"article_view", b"search", b"share", b"scroll_depth", b"outbound_click", b"consent_update"]:
                self.assertIn(event, javascript)
        finally:
            if previous is None:
                os.environ.pop("GTM_CONTAINER_ID", None)
            else:
                os.environ["GTM_CONTAINER_ID"] = previous

    def test_footer_contains_accessible_social_links(self):
        response = self.client.get("/")
        for network in ["Facebook", "Instagram", "YouTube", "LinkedIn", "X", "WhatsApp"]:
            self.assertIn(f'aria-label="'.encode(), response.data)
            self.assertIn(network.encode(), response.data)
        for address in [
            "https://x.com/sussurrodosaber",
            "https://www.instagram.com/sussurrodosaber?stkn=djl2d2s5cmJnZzE5",
            "https://www.youtube.com/channel/UCMxbh7jSRUxxX48JSWszc8g",
            "https://wa.me/258852130099",
            "https://web.facebook.com/profile.php?id=61584597102517",
        ]:
            self.assertIn(address.replace("&", "&amp;").encode(), response.data)

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
        escaped_image = expected_image.replace("&", "&amp;")
        self.assertIn(f'<meta property="og:image" content="{escaped_image}">'.encode(), response.data)
        self.assertIn(f'<meta property="og:image:url" content="{escaped_image}">'.encode(), response.data)
        self.assertIn(f'<meta name="twitter:image" content="{escaped_image}">'.encode(), response.data)
        self.assertIn(b'<meta name="twitter:card" content="summary_large_image">', response.data)
        self.assertIn(b'?share=', response.data)

    def test_external_images_keep_their_original_reliable_url(self):
        previous = os.environ.get("CLOUDINARY_CLOUD_NAME")
        os.environ["CLOUDINARY_CLOUD_NAME"] = "demo"
        try:
            source = "https://commons.wikimedia.org/wiki/Special:FilePath/Neuron_Hand-tuned.svg"
            self.assertEqual(social_image_url(source), source)
            self.assertEqual(responsive_image_url(source, 480), source)
        finally:
            if previous is None:
                os.environ.pop("CLOUDINARY_CLOUD_NAME", None)
            else:
                os.environ["CLOUDINARY_CLOUD_NAME"] = previous

    def test_image_urls_are_normalized_and_unsafe_values_rejected(self):
        self.assertEqual(
            safe_image_url("  //images.example.org/photo.jpg  "),
            "https://images.example.org/photo.jpg",
        )
        self.assertEqual(
            safe_image_url("https://images.example.org/photo.jpg?a=1&amp;b=2"),
            "https://images.example.org/photo.jpg?a=1&b=2",
        )
        self.assertEqual(safe_image_url("javascript:alert(1)"), "")
        self.assertEqual(responsive_image_url("not-a-url", 480), "")

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

    def test_bare_domain_redirects_permanently_to_www(self):
        response = self.client.get(
            "/artigos?page=2",
            base_url="https://sussurrosdosaber.com",
        )
        self.assertEqual(response.status_code, 308)
        self.assertEqual(
            response.location,
            "https://www.sussurrosdosaber.com/artigos?page=2",
        )

    def test_canonical_metadata_uses_www(self):
        response = self.client.get(
            "/",
            base_url="https://www.sussurrosdosaber.com",
        )
        self.assertIn(
            b'<link rel="canonical" href="https://www.sussurrosdosaber.com/">',
            response.data,
        )

    def test_tailwind_is_local_and_cdn_is_not_loaded(self):
        response = self.client.get("/")
        self.assertIn(b"/static/css/tailwind.css", response.data)
        self.assertNotIn(b"cdn.tailwindcss.com", response.data)

    def test_local_image_fallback_is_available(self):
        response = self.client.get("/static/img/image-fallback.svg")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Imagem temporariamente indispon", response.data)
        script = self.client.get("/static/js/main.js")
        self.assertIn(b"image-fallback.svg", script.data)

    def test_strict_csp_uses_unique_nonce_and_no_inline_handlers(self):
        first = self.client.get("/")
        second = self.client.get("/")
        first_policy = first.headers["Content-Security-Policy"]
        second_policy = second.headers["Content-Security-Policy"]
        first_nonce = re.search(r"script-src 'nonce-([^']+)'", first_policy)
        second_nonce = re.search(r"script-src 'nonce-([^']+)'", second_policy)
        self.assertIsNotNone(first_nonce)
        self.assertIsNotNone(second_nonce)
        self.assertNotEqual(first_nonce.group(1), second_nonce.group(1))
        self.assertIn("'strict-dynamic'", first_policy)
        self.assertIn("script-src-attr 'none'", first_policy)
        self.assertNotIn("'unsafe-inline'", first_policy.split("script-src", 1)[1].split(";", 1)[0])
        self.assertIn(
            f'nonce="{first_nonce.group(1)}"'.encode(),
            first.data,
        )
        self.assertNotIn(b"onclick=", first.data)
        self.assertNotIn(b"onload=", first.data)

    def test_security_headers(self):
        response = self.client.get("/", base_url="https://www.sussurrosdosaber.com")
        self.assertIn("default-src 'self'", response.headers["Content-Security-Policy"])
        self.assertNotIn("cdn.tailwindcss.com", response.headers["Content-Security-Policy"])
        self.assertNotIn("'unsafe-eval'", response.headers["Content-Security-Policy"])
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
            session["admin_last_activity_at"] = time.time()
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
            session["admin_last_activity_at"] = time.time()
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

    def test_secondary_admin_without_2fa_is_forced_to_enrol(self):
        from werkzeug.security import generate_password_hash

        with app.app_context():
            administrator = AdminUser.query.filter_by(username="sem.2fa").first()
            if administrator is None:
                administrator = AdminUser(
                    username="sem.2fa",
                    display_name="Administrador sem 2FA",
                    email="sem.2fa@example.org",
                    password_hash=generate_password_hash("palavra-passe-2fa-obrigatoria"),
                    active=True,
                    two_factor_enabled=False,
                )
                db.session.add(administrator)
                db.session.commit()
            administrator_id = administrator.id

        with self.client.session_transaction() as session:
            session.clear()
            session["admin_authenticated"] = True
            session["admin_id"] = administrator_id
            session["admin_superuser"] = False
            session["admin_2fa_verified"] = False
            session["admin_last_activity_at"] = time.time()
        response = self.client.get("/admin")
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.location.endswith("/admin/seguranca/2fa"))

    def test_totp_algorithm_and_recovery_code_format(self):
        secret = "JBSWY3DPEHPK3PXP"
        code = totp_code(secret)
        self.assertEqual(len(code), 6)
        self.assertTrue(verify_totp(secret, code, window=0))
        recovery_codes = generate_recovery_codes()
        self.assertEqual(len(recovery_codes), 8)
        self.assertTrue(all(re.fullmatch(r"[A-Z2-9]{4}(?:-[A-Z2-9]{4}){2}", item) for item in recovery_codes))

    def test_two_factor_login_requires_second_step(self):
        from werkzeug.security import generate_password_hash

        secret = "JBSWY3DPEHPK3PXP"
        with app.app_context():
            administrator = AdminUser.query.filter_by(username="dois.fatores").first()
            if administrator is None:
                administrator = AdminUser(
                    username="dois.fatores",
                    display_name="Administrador 2FA",
                    email="dois.fatores@example.org",
                    password_hash=generate_password_hash("palavra-passe-2fa-segura"),
                    active=True,
                    two_factor_enabled=True,
                    totp_secret=secret,
                )
                db.session.add(administrator)
                db.session.commit()

        with self.client.session_transaction() as session:
            session.clear()
            session["csrf_token"] = "first-step-csrf"
        first = self.client.post("/admin/login", data={
            "csrf_token": "first-step-csrf",
            "username": "dois.fatores",
            "password": "palavra-passe-2fa-segura",
        })
        self.assertEqual(first.status_code, 302)
        self.assertTrue(first.location.endswith("/admin/verificar-2fa"))
        with self.client.session_transaction() as session:
            self.assertFalse(session.get("admin_authenticated", False))
            second_csrf = session["csrf_token"]

        second = self.client.post("/admin/verificar-2fa", data={
            "csrf_token": second_csrf,
            "code": totp_code(secret),
        })
        self.assertEqual(second.status_code, 302)
        self.assertTrue(second.location.endswith("/admin"))
        with self.client.session_transaction() as session:
            self.assertTrue(session["admin_authenticated"])
            self.assertTrue(session["admin_2fa_verified"])

    def test_author_photo_url_is_saved_and_rendered(self):
        with self.client.session_transaction() as session:
            session.clear()
            session["admin_authenticated"] = True
            session["admin_last_activity_at"] = time.time()
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
            session["admin_last_activity_at"] = time.time()
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
            session["admin_last_activity_at"] = time.time()
            session["csrf_token"] = "secondary-csrf"
        self.assertEqual(self.client.get("/admin/administradores").status_code, 403)

    def test_homepage_uses_four_most_read_and_six_latest_discoveries(self):
        template = Path(app.root_path, "templates", "index.html").read_text(encoding="utf-8")
        self.assertIn("articles[1:5]", template)
        self.assertIn("articles[1:7]", template)
        response = self.client.get("/")
        self.assertLessEqual(response.data.count(b'class="number-story group"'), 4)
        self.assertLessEqual(response.data.count(b'class="story-card group"'), 6)

    def test_homepage_loads_featured_article_and_six_discoveries(self):
        class QuerySpy:
            limit_value = None

            def order_by(self, *args):
                return self

            def limit(self, value):
                self.limit_value = value
                return self

            def all(self):
                return []

        query = QuerySpy()
        with patch.object(Article, "public_card_query", return_value=query):
            response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(query.limit_value, 7)

    def test_z_homepage_supports_empty_database(self):
        with app.app_context():
            Article.query.delete()
            db.session.commit()
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Novos artigos estão a ser preparados".encode(), response.data)


if __name__ == "__main__":
    unittest.main()
