"""Custom test runner for the full suite.

Django already forces ``DEBUG=False`` during tests, which makes the suite run
against production-like settings. In this project that flips
``SECURE_SSL_REDIRECT`` on whenever settings were imported without a local
``.env`` (CI, or ``DEBUG=False manage.py test`` locally). ``SecurityMiddleware``
then 301-redirects every plain-HTTP test-client request to HTTPS before it
reaches a view, corrupting status-code assertions (301 instead of 200/401).

The suite must exercise views and their security logic, not transport
redirects, so the HTTPS redirect is disabled for the duration of the test run.
Everything else keeps its production form (secure cookies, JWT, proxies).
"""

from django.conf import settings
from django.test.runner import DiscoverRunner


class ProdLikeTestRunner(DiscoverRunner):
    """Discovers and runs tests with prod-like settings, minus the 301s."""

    def setup_test_environment(self, **kwargs):
        super().setup_test_environment(**kwargs)
        self._old_ssl_redirect = settings.SECURE_SSL_REDIRECT
        settings.SECURE_SSL_REDIRECT = False

    def teardown_test_environment(self, **kwargs):
        settings.SECURE_SSL_REDIRECT = self._old_ssl_redirect
        super().teardown_test_environment(**kwargs)
