"""Unit tests for health check endpoint."""

from datetime import timedelta

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone
from django_celery_beat.models import IntervalSchedule, PeriodicTask


@pytest.mark.django_db
class TestHealthCheckView:
    """Test health check endpoint."""

    @pytest.fixture
    def client(self):
        """Create a test client."""
        return Client()

    @pytest.fixture
    def setup_tasks(self):
        """Set up periodic tasks for testing."""
        # Create interval schedules
        interval_5min = IntervalSchedule.objects.create(every=5, period="minutes")
        interval_2min = IntervalSchedule.objects.create(every=2, period="minutes")
        interval_1hr = IntervalSchedule.objects.create(every=1, period="hours")

        # Create periodic tasks
        tasks = {
            "sync-portfolios": PeriodicTask.objects.create(
                name="sync-portfolios",
                task="apps.core.tasks.sync_portfolios",
                interval=interval_5min,
                enabled=True,
            ),
            "sync-bots": PeriodicTask.objects.create(
                name="sync-bots",
                task="apps.core.tasks.sync_bots",
                interval=interval_2min,
                enabled=True,
            ),
            "fetch-public-market-data": PeriodicTask.objects.create(
                name="fetch-public-market-data",
                task="apps.core.tasks.fetch_public_market_data",
                interval=interval_1hr,
                enabled=True,
            ),
            "update-signal-accuracy": PeriodicTask.objects.create(
                name="update-signal-accuracy",
                task="apps.trading.tasks.update_signal_accuracy",
                interval=interval_1hr,
                enabled=True,
            ),
        }
        return tasks

    def test_health_check_endpoint_exists(self, client):
        """Test health check endpoint is accessible."""
        url = reverse("api:health_check")
        response = client.get(url)
        assert response.status_code == 200

    def test_health_check_returns_json(self, client):
        """Test health check returns JSON response."""
        url = reverse("api:health_check")
        response = client.get(url)
        assert response["Content-Type"] == "application/json"

    def test_health_check_structure(self, client, setup_tasks):
        """Test health check response has correct structure."""
        url = reverse("api:health_check")
        response = client.get(url)
        data = response.json()

        # Check top-level keys
        assert "overall_status" in data
        assert "services" in data
        assert "timestamp" in data

        # Check overall_status is valid
        assert data["overall_status"] in ["healthy", "degraded", "unhealthy"]

        # Check services structure
        assert isinstance(data["services"], dict)

    def test_health_check_pending_tasks(self, client, setup_tasks):
        """Test health check reports pending status for tasks that haven't run."""
        url = reverse("api:health_check")
        response = client.get(url)
        data = response.json()

        # All tasks should be pending since they haven't run yet
        assert data["overall_status"] == "degraded"

        # Check individual service statuses
        for service_name, service_data in data["services"].items():
            assert service_data["status"] in ["pending", "unknown"]
            assert service_data["last_run"] is None

    def test_health_check_healthy_tasks(self, client, setup_tasks):
        """Test health check reports healthy status for recently run tasks."""
        # Update tasks with recent last_run_at
        now = timezone.now()
        for task in setup_tasks.values():
            task.last_run_at = now
            task.save()

        url = reverse("api:health_check")
        response = client.get(url)
        data = response.json()

        # All tasks should be healthy
        assert data["overall_status"] == "healthy"

        # Check individual service statuses
        for service_name, service_data in data["services"].items():
            assert service_data["status"] == "healthy"
            assert service_data["last_run"] is not None
            assert "age_minutes" in service_data

    def test_health_check_stale_tasks(self, client, setup_tasks):
        """Test health check reports stale status for old tasks."""
        # Update tasks with old last_run_at
        old_time = timezone.now() - timedelta(hours=2)
        for task in setup_tasks.values():
            task.last_run_at = old_time
            task.save()

        url = reverse("api:health_check")
        response = client.get(url)
        data = response.json()

        # All tasks should be stale
        assert data["overall_status"] == "unhealthy"

        # Check individual service statuses
        for service_name, service_data in data["services"].items():
            assert service_data["status"] == "stale"
            assert service_data["last_run"] is not None
            assert service_data["age_minutes"] > 60

    def test_health_check_disabled_tasks(self, client, setup_tasks):
        """Test health check reports disabled status for disabled tasks."""
        # Disable all tasks
        for task in setup_tasks.values():
            task.enabled = False
            task.save()

        url = reverse("api:health_check")
        response = client.get(url)
        data = response.json()

        # Overall status should be degraded
        assert data["overall_status"] == "degraded"

        # Check individual service statuses
        for service_name, service_data in data["services"].items():
            assert service_data["status"] == "disabled"

    def test_health_check_mixed_status(self, client, setup_tasks):
        """Test health check with mixed task statuses."""
        now = timezone.now()

        # Make some tasks healthy
        setup_tasks["sync-portfolios"].last_run_at = now
        setup_tasks["sync-portfolios"].save()

        # Make some tasks stale
        setup_tasks["sync-bots"].last_run_at = now - timedelta(hours=1)
        setup_tasks["sync-bots"].save()

        # Leave others pending (no last_run_at)

        url = reverse("api:health_check")
        response = client.get(url)
        data = response.json()

        # Overall status should be unhealthy due to stale task
        assert data["overall_status"] == "unhealthy"

        # Check specific service statuses
        assert data["services"]["Portfolio Sync"]["status"] == "healthy"
        assert data["services"]["Bot Sync"]["status"] == "stale"

    def test_health_check_no_authentication_required(self, client):
        """Test health check endpoint is public (no authentication required)."""
        url = reverse("api:health_check")
        response = client.get(url)

        # Should succeed without authentication
        assert response.status_code == 200
