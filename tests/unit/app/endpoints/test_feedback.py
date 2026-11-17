"""Unit tests for feedback endpoint handlers."""

import json
import warnings
from datetime import UTC, datetime
from unittest.mock import patch

import pytest

from ols import config

# needs to be setup there before is_user_authorized is imported
config.ols_config.authentication_config.module = "k8s"

# pylint: disable=C0413
from ols.app.endpoints import feedback  # noqa:E402
from ols.app.models.config import UserDataCollection  # noqa:E402


@pytest.fixture
def feedback_location(tmpdir):
    """Fixture sets feedback location to tmpdir and return the path."""
    full_path = (tmpdir / "feedback").strpath
    config.ols_config.user_data_collection = UserDataCollection(
        feedback_disabled=False, feedback_storage=full_path
    )
    return full_path


def store_fake_feedback(path, filename, data):
    """Store feedback data."""
    with open(f"{path}/{filename}.json", "w", encoding="utf-8") as f:
        f.write(json.dumps(data))


def load_fake_feedback(filename):
    """Load feedback data."""
    feedback_file = (
        f"{config.ols_config.user_data_collection.feedback_storage}/{filename}.json"
    )
    with open(feedback_file, encoding="utf-8") as f:
        return json.loads(f.read())


def test_get_feedback_status(feedback_location):
    """Test is_feedback_enabled function."""
    config.ols_config.user_data_collection.feedback_disabled = False
    assert feedback.is_feedback_enabled()

    config.ols_config.user_data_collection.feedback_disabled = True
    assert not feedback.is_feedback_enabled()


def test_store_feedback(feedback_location):
    """Test store_feedback function."""
    user_id = "12345678-abcd-0000-0123-456789abcdef"
    feedback_data = {"testy": "test"}

    with patch("ols.app.endpoints.feedback.datetime") as mocked_datetime:
        mocked_datetime.now = lambda tz=None: datetime(2000, 1, 1, 1, 23, 45, tzinfo=tz)
        with patch("ols.app.endpoints.feedback.get_suid", return_value="fake-uuid"):
            feedback.store_feedback(user_id, feedback_data)

        stored_data = load_fake_feedback("fake-uuid")
        assert stored_data == {
            "user_id": "12345678-abcd-0000-0123-456789abcdef",
            "timestamp": "2000-01-01 01:23:45+00:00",
            **feedback_data,
        }


def test_store_feedback_utc_without_deprecation_warning(feedback_location):
    """Test unmocked store_feedback writes UTC timestamp without DeprecationWarning."""
    user_id = "12345678-abcd-0000-0123-456789abcdef"
    feedback_data = {"testy": "test"}

    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        with patch("ols.app.endpoints.feedback.get_suid", return_value="real-utc-uuid"):
            feedback.store_feedback(user_id, feedback_data)

    stored_data = load_fake_feedback("real-utc-uuid")
    parsed_timestamp = datetime.fromisoformat(stored_data["timestamp"])
    assert parsed_timestamp.tzinfo == UTC
