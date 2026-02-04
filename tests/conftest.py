"""Pytest configuration for crypt-master tests."""

import os

# Set environment variables for tests
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.test_settings")
os.environ["USE_SQLITE"] = "True"

import pytest
from django.core.management import call_command


@pytest.fixture(scope="session")
def django_db_setup(django_db_blocker):
    """Configure Django database for testing.

    Creates all tables using migrations for the in-memory SQLite database.
    """
    with django_db_blocker.unblock():
        call_command("migrate", "--run-syncdb", verbosity=0)


@pytest.fixture
def api_client():
    """Create an API client for testing."""
    from rest_framework.test import APIClient

    return APIClient()
