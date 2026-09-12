import os
import tempfile
import unittest


database_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
database_file.close()
os.environ["DATABASE_URL"] = f"sqlite:///{database_file.name}"
os.environ["SECRET_KEY"] = "test-secret-key"
os.environ["ADMIN_USERNAME"] = "admin"
os.environ["ADMIN_PASSWORD"] = "a-strong-test-password"

from app import app  # noqa: E402
from models import AdminUser, Article, Journal, JournalIssue, db  # noqa: E402


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

    def setUp(self):
        with self.client.session_transaction() as session:
            session.clear()

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

    def test_admin_is_protected_and_not_indexed(self):
        response = self.client.get("/admin")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["X-Robots-Tag"], "noindex, nofollow")

    def test_administrator_can_be_created_and_sign_in(self):
        with self.client.session_transaction() as session:
            session["admin_authenticated"] = True
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

    def test_administrator_can_manage_journals(self):
        with self.client.session_transaction() as session:
            session["admin_authenticated"] = True
            session["csrf_token"] = "journal-csrf"
        response = self.client.post("/admin/revistas/nova", data={
            "csrf_token": "journal-csrf", "title": "Revista de Ciência Aberta", "abbreviation": "RCA",
            "field": "Ciência Aberta", "description": "Publicação dedicada à investigação aberta e à comunicação científica.",
            "frequency": "Semestral", "current_issue": "Vol. 1, N.º 1", "status": "Aceitando submissões",
            "contact_email": "revista@example.org", "guidelines": "## Submissão\n\nEnvie trabalhos originais.", "active": "on",
        })
        self.assertEqual(response.status_code, 302)
        with app.app_context():
            journal = Journal.query.filter_by(abbreviation="RCA").first()
            self.assertIsNotNone(journal)
            journal_id, journal_slug = journal.id, journal.slug
        self.assertEqual(self.client.get(f"/revistas/{journal_slug}").status_code, 200)
        self.assertEqual(self.client.get("/admin/revistas?q=Ciência&visibility=published").status_code, 200)
        response = self.client.post(f"/admin/revistas/{journal_id}/visibilidade", data={"csrf_token": "journal-csrf"})
        self.assertEqual(response.status_code, 302)
        with app.app_context():
            self.assertFalse(db.session.get(Journal, journal_id).active)
        response = self.client.post(f"/admin/revistas/{journal_id}/eliminar", data={"csrf_token": "journal-csrf"})
        self.assertEqual(response.status_code, 302)
        with app.app_context():
            self.assertIsNone(db.session.get(Journal, journal_id))

    def test_administrator_can_publish_issue_and_protect_linked_content(self):
        with self.client.session_transaction() as session:
            session["admin_authenticated"] = True
            session["csrf_token"] = "issue-csrf"
        with app.app_context():
            journal = Journal.query.first()
            journal_id, journal_slug = journal.id, journal.slug
        response = self.client.post(f"/admin/revistas/{journal_id}/edicoes/nova", data={
            "csrf_token": "issue-csrf", "volume": "2", "number": "1", "year": "2026",
            "title": "Ciência e comunidades", "description": "Edição dedicada à investigação aplicada.", "published": "on",
        })
        self.assertEqual(response.status_code, 302)
        with app.app_context():
            issue = JournalIssue.query.filter_by(journal_id=journal_id, volume=2, number=1, year=2026).first()
            self.assertIsNotNone(issue)
            article = Article.query.first()
            article.journal_issue_id = issue.id
            db.session.commit()
            issue_id = issue.id
        public_page = self.client.get(f"/revistas/{journal_slug}")
        self.assertEqual(public_page.status_code, 200)
        self.assertIn("Ciência e comunidades".encode(), public_page.data)
        response = self.client.post(f"/admin/revistas/edicoes/{issue_id}/eliminar", data={"csrf_token": "issue-csrf"})
        self.assertEqual(response.status_code, 302)
        with app.app_context():
            self.assertIsNotNone(db.session.get(JournalIssue, issue_id))

    def test_admin_dashboard_and_article_filters(self):
        with self.client.session_transaction() as session:
            session["admin_authenticated"] = True
            session["csrf_token"] = "filter-csrf"
        dashboard = self.client.get("/admin")
        self.assertEqual(dashboard.status_code, 200)
        self.assertIn("Serviços da plataforma".encode(), dashboard.data)
        self.assertEqual(self.client.get("/admin/artigos?q=Biologia&status=published").status_code, 200)

    def test_z_homepage_supports_empty_database(self):
        with app.app_context():
            Article.query.delete()
            db.session.commit()
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Novos artigos estão a ser preparados".encode(), response.data)


if __name__ == "__main__":
    unittest.main()
