"""
Unit tests for extraction_utils.py helper functions.

Run with:  pytest tests/test_extraction_utils.py -v
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from unittest.mock import MagicMock, call
from extraction_utils import retry_api_call, validate_extracted_entities


# ---------------------------------------------------------------------------
# retry_api_call
# ---------------------------------------------------------------------------

class TestRetryApiCall:
    def test_succeeds_on_first_try(self):
        func = MagicMock(return_value="ok")
        result = retry_api_call(func, "arg1", key="val")
        assert result == "ok"
        func.assert_called_once_with("arg1", key="val")

    def test_retries_on_rate_limit(self, monkeypatch):
        monkeypatch.setattr("extraction_utils.time.sleep", lambda _: None)
        error = Exception("429 rate_limit exceeded")
        func = MagicMock(side_effect=[error, error, "success"])
        result = retry_api_call(func, max_retries=3, base_delay=0.0)
        assert result == "success"
        assert func.call_count == 3

    def test_raises_after_max_retries(self, monkeypatch):
        monkeypatch.setattr("extraction_utils.time.sleep", lambda _: None)
        error = Exception("503 service unavailable")
        func = MagicMock(side_effect=error)
        with pytest.raises(Exception, match="503"):
            retry_api_call(func, max_retries=2, base_delay=0.0)
        assert func.call_count == 3  # 1 initial + 2 retries

    def test_raises_immediately_on_permanent_error(self):
        error = ValueError("bad request: invalid parameter")
        func = MagicMock(side_effect=error)
        with pytest.raises(ValueError, match="bad request"):
            retry_api_call(func, max_retries=3, base_delay=0.0)
        # Should not retry a permanent error
        func.assert_called_once()

    def test_passes_args_and_kwargs(self):
        func = MagicMock(return_value=42)
        retry_api_call(func, 1, 2, key="value")
        func.assert_called_once_with(1, 2, key="value")


# ---------------------------------------------------------------------------
# validate_extracted_entities
# ---------------------------------------------------------------------------

class TestValidateExtractedEntities:
    def test_valid_events_no_warning(self, caplog):
        entities = [
            {"title": "Rio Summit", "year": 1992, "description": "Earth Summit"},
            {"title": "Kyoto Protocol", "year": 1997, "description": "Climate treaty"},
        ]
        result = validate_extracted_entities("event", entities)
        assert result is entities  # Returns same list unchanged
        assert "[schema]" not in caplog.text

    def test_missing_required_field_logs_warning(self, caplog):
        import logging
        with caplog.at_level(logging.WARNING):
            entities = [{"title": "Rio Summit"}]  # Missing 'year' and 'description'
            validate_extracted_entities("event", entities)
        assert "missing required fields" in caplog.text

    def test_valid_actors_no_warning(self, caplog):
        entities = [{"name": "UNEP", "type": "Government"}]
        validate_extracted_entities("actor", entities)
        assert "[schema]" not in caplog.text

    def test_unknown_entity_type_returns_unchanged(self):
        entities = [{"foo": "bar"}]
        result = validate_extracted_entities("unknown_type", entities)
        assert result == entities

    def test_empty_list_returns_empty(self):
        result = validate_extracted_entities("event", [])
        assert result == []

    def test_returns_all_entities_even_if_invalid(self, caplog):
        import logging
        with caplog.at_level(logging.WARNING):
            entities = [
                {"title": "Good Event", "year": 2020, "description": "ok"},
                {"title": "Bad Event"},  # Missing required fields
            ]
            result = validate_extracted_entities("event", entities)
        # All entities returned — validation is advisory only
        assert len(result) == 2
