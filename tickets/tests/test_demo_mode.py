from io import StringIO

from django.core.management import call_command
from django.test import TestCase, override_settings

from tickets.models import Ticket


@override_settings(DEBUG=False, DEMO_MODE=True)
class DemoModeTests(TestCase):
    def test_seed_commands_run_in_demo_mode(self):
        call_command("seed_demo", stdout=StringIO())
        call_command("seed_bulk", "--count", "5", stdout=StringIO())
        self.assertEqual(Ticket.objects.count(), 15)