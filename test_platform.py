import os
import tempfile
import time
import unittest
from werkzeug.security import generate_password_hash


database_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
database_file.close()
os.environ["DATABASE_URL"] = f"sqlite:///{database_file.name}"
os.environ["SECRET_KEY"] = "test-secret-key"
os.environ["ADMIN_USERNAME"] = "admin"
os.environ["ADMIN_PASSWORD"] = "a-strong-test-password"

from app import app, ensure_legacy_columns  # noqa: E402
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

    def test_security_headers(self):
        response = self.client.get("/", base_url="https://www.sussurrosdosaber.com")
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
            session.clear(); session["admin_authenticated"] = True; session["admin_last_activity_at"] = time.time(); session["admin_id"] = owner_id; session["admin_session_version"] = owner_version; session["admin_role"] = "superadmin"; session["csrf_token"] = "journal-csrf"
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
            session["admin_last_activity_at"] = time.time()
            session["admin_id"] = 999999
            session["admin_session_version"] = 1
        response = self.client.get("/admin")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login", response.location)

    def test_admin_api_rejects_unauthenticated_requests_with_json(self):
        with self.client.session_transaction() as session:
            session.clear()
        response = self.client.post("/admin/api/imagens")
        self.assertEqual(response.status_code, 401)
        self.assertFalse(response.get_json()["ok"])
        self.assertIn("Autenticação", response.get_json()["error"])
        self.assertEqual(response.headers["Cache-Control"], "no-store, no-cache, must-revalidate, private, max-age=0")

    def test_admin_gate_protects_routes_without_relying_on_visibility(self):
        with self.client.session_transaction() as session:
            session.clear()
        for path in ["/admin", "/admin/artigos", "/admin/autores", "/admin/revistas", "/admin/contactos"]:
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 302)
                self.assertIn("/admin/login", response.location)

    def test_admin_login_disables_password_autofill(self):
        response = self.client.get("/admin/login")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'autocomplete="off"', response.data)
        self.assertIn(b'autocomplete="new-password"', response.data)

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
            session["admin_last_activity_at"] = time.time()
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
            session["admin_authenticated"] = True; session["admin_last_activity_at"] = time.time(); session["admin_id"] = owner_id; session["admin_session_version"] = owner_version; session["admin_role"] = "superadmin"; session["csrf_token"] = "x"
        self.assertEqual(self.client.post("/admin/logout", data={}).status_code, 400)
        with app.app_context():
            editor = AdminUser.query.filter_by(username="editor.cientifico").first()
            editor_id, editor_version = editor.id, editor.session_version
        with self.client.session_transaction() as session:
            session.clear(); session["admin_authenticated"] = True; session["admin_last_activity_at"] = time.time(); session["admin_id"] = editor_id; session["admin_session_version"] = editor_version; session["admin_role"] = "editor"; session["csrf_token"] = "x"
        self.assertEqual(self.client.get("/admin/administradores").status_code, 403)

    def test_disabled_admin_session_is_revoked(self):
        with app.app_context():
            account = AdminUser.query.filter_by(username="editor.cientifico").first()
            account.active = False
            db.session.commit()
            account_id, version = account.id, account.session_version
        with self.client.session_transaction() as session:
            session.clear(); session["admin_authenticated"] = True; session["admin_last_activity_at"] = time.time(); session["admin_id"] = account_id; session["admin_session_version"] = version
        self.assertEqual(self.client.get("/admin").status_code, 302)

    def test_slug_route_and_legacy_redirect(self):
        with app.app_context():
            article = Article.public_query().first()
            article_id, slug = article.id, article.slug
        response = self.client.get(f"/artigo/{article_id}")
        self.assertEqual(response.status_code, 301)
        self.assertTrue(response.location.endswith(f"/artigo/{slug}"))
        self.assertEqual(self.client.get(f"/artigo/{slug}").status_code, 200)

    def test_y_legacy_journal_schema_is_upgraded(self):
        from sqlalchemy import inspect, text
        with app.app_context():
            db.session.execute(text("DROP TABLE journal"))
            db.session.execute(text("CREATE TABLE journal (id INTEGER PRIMARY KEY, title VARCHAR(180) NOT NULL, slug VARCHAR(200) NOT NULL, field VARCHAR(140) NOT NULL, description TEXT NOT NULL, abbr VARCHAR(30), issue VARCHAR(120), status VARCHAR(30))"))
            db.session.execute(text("INSERT INTO journal (id,title,slug,field,description,abbr,issue,status) VALUES (1,'Revista Antiga','revista-antiga','Biologia','Descrição da revista antiga','RA','Vol. 1','published')"))
            db.session.commit()
            ensure_legacy_columns()
            columns = {column["name"] for column in inspect(db.engine).get_columns("journal")}
            self.assertTrue({"abbreviation", "current_issue", "cover_public_id", "published", "guidelines"}.issubset(columns))
            journal = Journal.query.filter_by(slug="revista-antiga").first()
            self.assertEqual(journal.abbreviation, "RA")
            self.assertTrue(journal.published)

    def test_api_pagination_limit(self):
        response = self.client.get("/api/artigos?limit=1")
        self.assertEqual(response.status_code, 200)
        self.assertLessEqual(len(response.get_json()), 1)
        self.assertIn("stale-while-revalidate", response.headers["Cache-Control"])

    def test_api_articles_can_fetch_only_saved_ids(self):
        with app.app_context():
            article = Article.public_query().first()
            article_id = article.id
        response = self.client.get(f"/api/artigos?ids={article_id},999999")
        self.assertEqual(response.status_code, 200)
        self.assertEqual([item["id"] for item in response.get_json()], [article_id])

    def test_resources_api_has_shared_cache_policy(self):
        response = self.client.get("/api/recursos")
        self.assertEqual(response.status_code, 200)
        self.assertIn("max-age=600", response.headers["Cache-Control"])

    def test_z_homepage_supports_empty_database(self):
        with app.app_context():
            Article.query.delete()
            db.session.commit()
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Novos artigos estão a ser preparados".encode(), response.data)


if __name__ == "__main__":
    unittest.main()
