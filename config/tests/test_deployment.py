from django.test import SimpleTestCase, TestCase, override_settings

from config.settings import database_config


class HealthCheckTests(TestCase):
    def test_healthz_is_public_and_touches_no_database(self):
        with self.assertNumQueries(0):
            response = self.client.get("/healthz/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})


class HttpsRedirectTests(TestCase):
    @override_settings(SECURE_SSL_REDIRECT=True)
    def test_pages_redirect_to_https_but_the_health_check_does_not(self):
        response = self.client.get("/tickets/")
        self.assertEqual(response.status_code, 301)
        self.assertTrue(response["Location"].startswith("https://"))
        self.assertEqual(self.client.get("/healthz/").status_code, 200)


class DatabaseConfigTests(SimpleTestCase):
    def test_database_url_is_used_and_parsed(self):
        config = database_config(
            {"DATABASE_URL": "postgresql://app_user:p%40ss@db.example.com:5432/devdesk?sslmode=require"}
        )
        self.assertEqual(config["NAME"], "devdesk")
        self.assertEqual(config["USER"], "app_user")
        self.assertEqual(config["PASSWORD"], "p@ss")
        self.assertEqual(config["HOST"], "db.example.com")
        self.assertEqual(config["OPTIONS"]["sslmode"], "require")
        self.assertEqual(config["CONN_MAX_AGE"], 600)
        self.assertTrue(config["CONN_HEALTH_CHECKS"])

    def test_separate_variables_are_used_without_a_url(self):
        config = database_config(
            {"DB_NAME": "devdesk", "DB_USER": "me", "DB_PASSWORD": "secret"}
        )
        self.assertEqual(config["ENGINE"], "django.db.backends.postgresql")
        self.assertEqual((config["HOST"], config["PORT"]), ("localhost", "5432"))

    def test_missing_variables_fail_loudly(self):
        with self.assertRaises(KeyError):
            database_config({})