"""Pytest configuration for crypt-master tests."""

import os

# Set environment variables for tests
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.test_settings")
os.environ["USE_SQLITE"] = "True"

import pytest
from django.core.management import call_command


@pytest.fixture(scope="session", autouse=True)
def django_db_setup(django_db_setup, django_db_blocker):
    """Configure Django database for testing.

    Ensures all migrations are applied to the test database.
    """
    # The django_db_setup fixture from pytest-django already runs migrations
    # This fixture just ensures it's called
    pass


@pytest.fixture
def api_client():
    """Create an API client for testing."""
    from rest_framework.test import APIClient

    return APIClient()
