import os
import tempfile
import unittest
from werkzeug.security import generate_password_hash


database_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
database_file.close()
os.environ["DATABASE_URL"] = f"sqlite:///{database_file.name}"
os.environ["SECRET_KEY"] = "test-secret-key"
os.environ["ADMIN_USERNAME"] = "admin"
os.environ["ADMIN_PASSWORD"] = "a-strong-test-password"

from app import app  # noqa: E402
from models import AdminUser, Article, Author, Category, Journal, db  # noqa: E402


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

    def test_public_routes_and_discovery_files(self):
        for path in ["/", "/artigos", "/autores", "/revistas", "/contacto", "/feed.xml", "/sitemap.xml", "/robots.txt", "/healthz"]:
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 200)

    def test_security_headers(self):
        response = self.client.get("/", base_url="https://sussurrosdosaber.com")
        self.assertIn("default-src 'self'", response.headers["Content-Security-Policy"])
        self.assertIn("max-age=31536000", response.headers["Strict-Transport-Security"])
        self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")

    def test_input_validation(self):
        self.assertEqual(self.client.post("/api/newsletter", json={"email": "invalido"}).status_code, 400)
        self.assertEqual(self.client.post("/api/contacto", json={}).status_code, 400)
        self.assertEqual(self.client.post("/api/assistente", json={"message": ""}).status_code, 400)

    def test_journal_management_and_public_visibility(self):
        with app.app_context():
            owner = AdminUser.query.filter_by(username="owner").first()
            if not owner:
                owner = AdminUser(username="owner", display_name="Owner", role="superadmin", password_hash=generate_password_hash("Owner-password-2026"))
                db.session.add(owner); db.session.commit()
            owner_id, owner_version = owner.id, owner.session_version
        with self.client.session_transaction() as session:
            session.clear(); session["admin_authenticated"] = True; session["admin_id"] = owner_id; session["admin_session_version"] = owner_version; session["admin_role"] = "superadmin"; session["csrf_token"] = "journal-csrf"
        response = self.client.post("/admin/revistas/nova", data={
            "csrf_token": "journal-csrf", "title": "Revista Teste", "abbreviation": "RT",
            "field": "Biologia", "description": "Descrição científica suficientemente completa para teste.",
            "issn": "1234-567X", "frequency": "Semestral", "current_issue": "Vol. 1, N.º 1",
            "guidelines": "## Diretrizes\n\nSubmeta manuscritos originais.", "cover_image": "https://example.org/capa.webp",
            "cover_alt": "Capa verde da Revista Teste", "published": "on",
        })
        self.assertEqual(response.status_code, 302)
        with app.app_context():
            journal = Journal.query.filter_by(title="Revista Teste").first()
            self.assertIsNotNone(journal); journal_id, slug = journal.id, journal.slug
        self.assertEqual(self.client.get(f"/revistas/{slug}").status_code, 200)
        self.client.post(f"/admin/revistas/{journal_id}/estado", data={"csrf_token": "journal-csrf"})
        self.assertEqual(self.client.get(f"/revistas/{slug}").status_code, 404)
        self.client.post(f"/admin/revistas/{journal_id}/eliminar", data={"csrf_token": "journal-csrf"})
        with app.app_context():
            self.assertIsNone(db.session.get(Journal, journal_id))

    def test_admin_is_protected_and_not_indexed(self):
        response = self.client.get("/admin")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login", response.location)
        self.assertEqual(response.headers["X-Robots-Tag"], "noindex, nofollow")

        with self.client.session_transaction() as session:
            session["admin_authenticated"] = True
            session["admin_id"] = 999999
            session["admin_session_version"] = 1
        response = self.client.get("/admin")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login", response.location)

    def test_administrator_can_be_created_and_sign_in(self):
        with app.app_context():
            owner = AdminUser.query.filter_by(username="owner").first()
            if not owner:
                owner = AdminUser(username="owner", display_name="Owner", role="superadmin", password_hash=generate_password_hash("Owner-password-2026"))
                db.session.add(owner); db.session.commit()
            owner_id, owner_version = owner.id, owner.session_version
        with self.client.session_transaction() as session:
            session.clear()
            session["admin_authenticated"] = True
            session["admin_id"] = owner_id
            session["admin_session_version"] = owner_version
            session["admin_role"] = "superadmin"
            session["csrf_token"] = "test-csrf"
        response = self.client.post("/admin/administradores", data={
            "csrf_token": "test-csrf",
            "display_name": "Editor Científico",
            "username": "editor.cientifico",
            "email": "editor@example.org",
            "role": "editor",
            "password": "Uma-palavra-passe-segura-2026",
            "password_confirmation": "Uma-palavra-passe-segura-2026",
        })
        self.assertEqual(response.status_code, 302)
        with app.app_context():
            self.assertIsNotNone(AdminUser.query.filter_by(username="editor.cientifico").first())
        with self.client.session_transaction() as session:
            session.clear()
            session["csrf_token"] = "login-csrf"
        response = self.client.post("/admin/login", data={"csrf_token": "login-csrf", "username": "editor.cientifico", "password": "Uma-palavra-passe-segura-2026"})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.location.endswith("/admin"))

    def test_csrf_and_role_enforcement(self):
        with app.app_context():
            owner = AdminUser.query.filter_by(username="owner").first()
            owner_id, owner_version = owner.id, owner.session_version
        with self.client.session_transaction() as session:
            session["admin_authenticated"] = True; session["admin_id"] = owner_id; session["admin_session_version"] = owner_version; session["admin_role"] = "superadmin"; session["csrf_token"] = "x"
        self.assertEqual(self.client.post("/admin/logout", data={}).status_code, 400)
        with app.app_context():
            editor = AdminUser.query.filter_by(username="editor.cientifico").first()
            editor_id, editor_version = editor.id, editor.session_version
        with self.client.session_transaction() as session:
            session.clear(); session["admin_authenticated"] = True; session["admin_id"] = editor_id; session["admin_session_version"] = editor_version; session["admin_role"] = "editor"; session["csrf_token"] = "x"
        self.assertEqual(self.client.get("/admin/administradores").status_code, 403)

    def test_disabled_admin_session_is_revoked(self):
        with app.app_context():
            account = AdminUser.query.filter_by(username="editor.cientifico").first()
            account.active = False
            db.session.commit()
            account_id, version = account.id, account.session_version
        with self.client.session_transaction() as session:
            session.clear(); session["admin_authenticated"] = True; session["admin_id"] = account_id; session["admin_session_version"] = version
        self.assertEqual(self.client.get("/admin").status_code, 302)

    def test_slug_route_and_legacy_redirect(self):
        with app.app_context():
            article = Article.public_query().first()
            article_id, slug = article.id, article.slug
        response = self.client.get(f"/artigo/{article_id}")
        self.assertEqual(response.status_code, 301)
        self.assertTrue(response.location.endswith(f"/artigo/{slug}"))
        self.assertEqual(self.client.get(f"/artigo/{slug}").status_code, 200)

    def test_api_pagination_limit(self):
        response = self.client.get("/api/artigos?limit=1")
        self.assertEqual(response.status_code, 200)
        self.assertLessEqual(len(response.get_json()), 1)

    def test_z_homepage_supports_empty_database(self):
        with app.app_context():
            Article.query.delete()
            db.session.commit()
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Novos artigos estão a ser preparados".encode(), response.data)


if __name__ == "__main__":
    unittest.main()
