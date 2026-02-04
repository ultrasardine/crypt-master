"""
Property-based tests for Configuration Module.

Feature: pionex-trading-bot
Property 17: Configuration Defaults

These tests use the hypothesis library to verify that the configuration
module correctly applies default values for all optional parameters.

**Validates: Requirements 9.4**
"""

import os
from unittest import mock

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from lib.config import (
    AnalysisConfig,
    LoggingConfig,
    RiskConfig,
    get_default_config,
    load_config_from_dict,
)

# =============================================================================
# Custom Strategies for Configuration Testing
# =============================================================================

# Strategy for valid percentage values (0 < x <= 1)
percentage_strategy = st.floats(
    min_value=0.001,
    max_value=1.0,
    allow_nan=False,
    allow_infinity=False,
)

# Strategy for positive integers
positive_int_strategy = st.integers(min_value=1, max_value=10000)

# Strategy for positive floats
positive_float_strategy = st.floats(
    min_value=0.001,
    max_value=100.0,
    allow_nan=False,
    allow_infinity=False,
)

# Strategy for valid log levels
log_level_strategy = st.sampled_from(["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"])

# Strategy for boolean values
bool_strategy = st.booleans()

# Strategy for non-empty strings
non_empty_string_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "P")),
    min_size=1,
    max_size=50,
)


@st.composite
def partial_risk_config_strategy(draw: st.DrawFn) -> dict:
    """
    Generate partial risk configuration dictionaries.

    Creates dictionaries with random subsets of risk configuration fields,
    used to test that missing fields get default values.
    """
    fields = {
        "max_position_pct": draw(percentage_strategy),
        "max_risk_per_trade": draw(percentage_strategy),
        "max_drawdown": draw(percentage_strategy),
        "min_confidence": draw(st.floats(min_value=0.0, max_value=1.0, allow_nan=False)),
        "bot_loss_threshold": draw(percentage_strategy),
    }

    # Randomly include/exclude each field
    result = {}
    for key, value in fields.items():
        if draw(st.booleans()):
            result[key] = value

    return result


@st.composite
def partial_analysis_config_strategy(draw: st.DrawFn) -> dict:
    """
    Generate partial analysis configuration dictionaries.

    Creates dictionaries with random subsets of analysis configuration fields.
    """
    # Generate MACD values ensuring fast < slow
    macd_fast = draw(st.integers(min_value=1, max_value=20))
    macd_slow = draw(st.integers(min_value=macd_fast + 1, max_value=50))

    fields = {
        "interval_seconds": draw(positive_int_strategy),
        "rsi_period": draw(positive_int_strategy),
        "macd_fast": macd_fast,
        "macd_slow": macd_slow,
        "macd_signal": draw(positive_int_strategy),
        "bollinger_period": draw(positive_int_strategy),
        "bollinger_std": draw(positive_float_strategy),
    }

    # Randomly include/exclude each field
    result = {}
    for key, value in fields.items():
        if draw(st.booleans()):
            result[key] = value

    # If we include macd_fast, we must include macd_slow to maintain constraint
    if "macd_fast" in result and "macd_slow" not in result:
        result["macd_slow"] = macd_slow
    if "macd_slow" in result and "macd_fast" not in result:
        result["macd_fast"] = macd_fast

    return result


@st.composite
def partial_logging_config_strategy(draw: st.DrawFn) -> dict:
    """
    Generate partial logging configuration dictionaries.
    """
    fields = {
        "level": draw(log_level_strategy),
        "max_bytes": draw(st.integers(min_value=1024, max_value=100 * 1024 * 1024)),
        "backup_count": draw(st.integers(min_value=0, max_value=100)),
    }

    # Randomly include/exclude each field
    result = {}
    for key, value in fields.items():
        if draw(st.booleans()):
            result[key] = value

    return result


# =============================================================================
# Property 17: Configuration Defaults
# =============================================================================


class TestConfigurationDefaults:
    """
    Property 17: Configuration Defaults

    *For any* config with missing optional fields, defaults SHALL be applied.

    This property ensures that the configuration system correctly applies
    default values when optional fields are not provided, allowing users
    to specify only the values they want to override.

    **Validates: Requirements 9.4**
    """

    @settings(max_examples=100)
    @given(partial_config=partial_risk_config_strategy())
    def test_risk_config_defaults_applied(
        self,
        partial_config: dict,
    ) -> None:
        """
        Property: For any partial risk config, missing fields SHALL have defaults.

        **Validates: Requirements 9.4**
        """
        # Get default values
        defaults = RiskConfig()

        # Load config with partial values
        with mock.patch.dict(os.environ, {}, clear=True):
            config = load_config_from_dict({"risk": partial_config})

        # Check that all fields have values (either provided or default)
        assert config.risk.max_position_pct is not None
        assert config.risk.max_risk_per_trade is not None
        assert config.risk.max_drawdown is not None
        assert config.risk.min_confidence is not None
        assert config.risk.bot_loss_threshold is not None

        # Check that provided values are used
        for key, value in partial_config.items():
            actual = getattr(config.risk, key)
            assert actual == pytest.approx(value, rel=0.001), (
                f"Provided value for {key} not used: expected {value}, got {actual}"
            )

        # Check that missing values have defaults
        for key in [
            "max_position_pct",
            "max_risk_per_trade",
            "max_drawdown",
            "min_confidence",
            "bot_loss_threshold",
        ]:
            if key not in partial_config:
                actual = getattr(config.risk, key)
                expected = getattr(defaults, key)
                assert actual == expected, (
                    f"Default not applied for {key}: expected {expected}, got {actual}"
                )

    @settings(max_examples=100)
    @given(partial_config=partial_analysis_config_strategy())
    def test_analysis_config_defaults_applied(
        self,
        partial_config: dict,
    ) -> None:
        """
        Property: For any partial analysis config, missing fields SHALL have defaults.

        **Validates: Requirements 9.4**
        """
        # Get default values
        defaults = AnalysisConfig()

        # Load config with partial values
        with mock.patch.dict(os.environ, {}, clear=True):
            config = load_config_from_dict({"analysis": partial_config})

        # Check that all fields have values
        assert config.analysis.interval_seconds is not None
        assert config.analysis.rsi_period is not None
        assert config.analysis.macd_fast is not None
        assert config.analysis.macd_slow is not None
        assert config.analysis.macd_signal is not None
        assert config.analysis.bollinger_period is not None
        assert config.analysis.bollinger_std is not None

        # Check that provided values are used
        for key, value in partial_config.items():
            actual = getattr(config.analysis, key)
            if isinstance(value, float):
                assert actual == pytest.approx(value, rel=0.001), (
                    f"Provided value for {key} not used: expected {value}, got {actual}"
                )
            else:
                assert actual == value, (
                    f"Provided value for {key} not used: expected {value}, got {actual}"
                )

        # Check that missing values have defaults
        for key in [
            "interval_seconds",
            "rsi_period",
            "macd_fast",
            "macd_slow",
            "macd_signal",
            "bollinger_period",
            "bollinger_std",
        ]:
            if key not in partial_config:
                actual = getattr(config.analysis, key)
                expected = getattr(defaults, key)
                assert actual == expected, (
                    f"Default not applied for {key}: expected {expected}, got {actual}"
                )

    @settings(max_examples=100)
    @given(partial_config=partial_logging_config_strategy())
    def test_logging_config_defaults_applied(
        self,
        partial_config: dict,
    ) -> None:
        """
        Property: For any partial logging config, missing fields SHALL have defaults.

        **Validates: Requirements 9.4**
        """
        # Get default values
        defaults = LoggingConfig()

        # Load config with partial values
        with mock.patch.dict(os.environ, {}, clear=True):
            config = load_config_from_dict({"logging": partial_config})

        # Check that all fields have values
        assert config.logging.level is not None
        assert config.logging.max_bytes is not None
        assert config.logging.backup_count is not None

        # Check that provided values are used
        for key, value in partial_config.items():
            actual = getattr(config.logging, key)
            assert actual == value, (
                f"Provided value for {key} not used: expected {value}, got {actual}"
            )

        # Check that missing values have defaults
        for key in ["level", "max_bytes", "backup_count"]:
            if key not in partial_config:
                actual = getattr(config.logging, key)
                expected = getattr(defaults, key)
                assert actual == expected, (
                    f"Default not applied for {key}: expected {expected}, got {actual}"
                )

    @settings(max_examples=100)
    @given(st.data())
    def test_empty_config_uses_all_defaults(
        self,
        data: st.DataObject,
    ) -> None:
        """
        Property: An empty config dictionary SHALL use all default values.

        **Validates: Requirements 9.4**
        """
        # Load config with empty dictionary
        with mock.patch.dict(os.environ, {}, clear=True):
            config = load_config_from_dict({})

        # Get default config
        defaults = get_default_config()

        # All values should match defaults
        assert config.dry_run == defaults.dry_run
        assert config.debug == defaults.debug

        # Risk defaults
        assert config.risk.max_position_pct == defaults.risk.max_position_pct
        assert config.risk.max_risk_per_trade == defaults.risk.max_risk_per_trade
        assert config.risk.max_drawdown == defaults.risk.max_drawdown
        assert config.risk.min_confidence == defaults.risk.min_confidence
        assert config.risk.bot_loss_threshold == defaults.risk.bot_loss_threshold

        # Analysis defaults
        assert config.analysis.interval_seconds == defaults.analysis.interval_seconds
        assert config.analysis.rsi_period == defaults.analysis.rsi_period
        assert config.analysis.macd_fast == defaults.analysis.macd_fast
        assert config.analysis.macd_slow == defaults.analysis.macd_slow
        assert config.analysis.macd_signal == defaults.analysis.macd_signal
        assert config.analysis.bollinger_period == defaults.analysis.bollinger_period
        assert config.analysis.bollinger_std == defaults.analysis.bollinger_std

        # Logging defaults
        assert config.logging.level == defaults.logging.level
        assert config.logging.max_bytes == defaults.logging.max_bytes
        assert config.logging.backup_count == defaults.logging.backup_count

        # LLM defaults
        assert config.llm.enabled == defaults.llm.enabled
        assert config.llm.ollama_url == defaults.llm.ollama_url
        assert config.llm.model == defaults.llm.model

    @settings(max_examples=100)
    @given(
        debug=bool_strategy,
    )
    def test_top_level_defaults_applied(
        self,
        debug: bool,
    ) -> None:
        """
        Property: Top-level config fields SHALL use defaults when not provided.

        Note: We only test with dry_run=True to avoid API credential requirements.

        **Validates: Requirements 9.4**
        """
        defaults = get_default_config()

        # Test with only debug provided (dry_run defaults to True)
        with mock.patch.dict(os.environ, {}, clear=True):
            config = load_config_from_dict({"debug": debug})

        assert config.dry_run == defaults.dry_run  # Should be default (True)
        assert config.debug == debug

    @settings(max_examples=100)
    @given(
        max_position_pct=percentage_strategy,
    )
    def test_single_field_override_preserves_other_defaults(
        self,
        max_position_pct: float,
    ) -> None:
        """
        Property: Overriding one field SHALL NOT affect defaults of other fields.

        **Validates: Requirements 9.4**
        """
        defaults = RiskConfig()

        with mock.patch.dict(os.environ, {}, clear=True):
            config = load_config_from_dict({"risk": {"max_position_pct": max_position_pct}})

        # Overridden field should have new value
        assert config.risk.max_position_pct == pytest.approx(max_position_pct, rel=0.001)

        # Other fields should have defaults
        assert config.risk.max_risk_per_trade == defaults.max_risk_per_trade
        assert config.risk.max_drawdown == defaults.max_drawdown
        assert config.risk.min_confidence == defaults.min_confidence
        assert config.risk.bot_loss_threshold == defaults.bot_loss_threshold


class TestConfigurationDefaultsConsistency:
    """
    Additional consistency tests for configuration defaults.

    These tests verify that default values are consistent and sensible
    across different loading methods.

    **Validates: Requirements 9.4**
    """

    @settings(max_examples=100)
    @given(st.data())
    def test_get_default_config_is_deterministic(
        self,
        data: st.DataObject,
    ) -> None:
        """
        Property: get_default_config() SHALL return identical values on each call.

        **Validates: Requirements 9.4**
        """
        config1 = get_default_config()
        config2 = get_default_config()

        # All values should be identical
        assert config1.dry_run == config2.dry_run
        assert config1.debug == config2.debug

        assert config1.risk.max_position_pct == config2.risk.max_position_pct
        assert config1.risk.max_risk_per_trade == config2.risk.max_risk_per_trade
        assert config1.risk.max_drawdown == config2.risk.max_drawdown

        assert config1.analysis.rsi_period == config2.analysis.rsi_period
        assert config1.analysis.macd_fast == config2.analysis.macd_fast
        assert config1.analysis.macd_slow == config2.analysis.macd_slow

        assert config1.logging.level == config2.logging.level
        assert config1.logging.max_bytes == config2.logging.max_bytes

    @settings(max_examples=100)
    @given(st.data())
    def test_load_empty_dict_matches_get_default_config(
        self,
        data: st.DataObject,
    ) -> None:
        """
        Property: load_config_from_dict({}) SHALL match get_default_config().

        **Validates: Requirements 9.4**
        """
        with mock.patch.dict(os.environ, {}, clear=True):
            loaded = load_config_from_dict({})

        defaults = get_default_config()

        # All values should match
        assert loaded.dry_run == defaults.dry_run
        assert loaded.debug == defaults.debug

        assert loaded.risk.max_position_pct == defaults.risk.max_position_pct
        assert loaded.risk.max_risk_per_trade == defaults.risk.max_risk_per_trade
        assert loaded.risk.max_drawdown == defaults.risk.max_drawdown
        assert loaded.risk.min_confidence == defaults.risk.min_confidence
        assert loaded.risk.bot_loss_threshold == defaults.risk.bot_loss_threshold

        assert loaded.analysis.interval_seconds == defaults.analysis.interval_seconds
        assert loaded.analysis.rsi_period == defaults.analysis.rsi_period
        assert loaded.analysis.macd_fast == defaults.analysis.macd_fast
        assert loaded.analysis.macd_slow == defaults.analysis.macd_slow
        assert loaded.analysis.macd_signal == defaults.analysis.macd_signal
        assert loaded.analysis.bollinger_period == defaults.analysis.bollinger_period
        assert loaded.analysis.bollinger_std == defaults.analysis.bollinger_std

        assert loaded.logging.level == defaults.logging.level
        assert loaded.logging.max_bytes == defaults.logging.max_bytes
        assert loaded.logging.backup_count == defaults.logging.backup_count

        assert loaded.llm.enabled == defaults.llm.enabled
        assert loaded.llm.ollama_url == defaults.llm.ollama_url
        assert loaded.llm.model == defaults.llm.model

    @settings(max_examples=100)
    @given(
        max_position_pct=percentage_strategy,
        max_drawdown=percentage_strategy,
    )
    def test_defaults_are_sensible_values(
        self,
        max_position_pct: float,
        max_drawdown: float,
    ) -> None:
        """
        Property: Default values SHALL be within valid ranges.

        **Validates: Requirements 9.4**
        """
        defaults = get_default_config()

        # Risk defaults should be valid percentages
        assert 0 < defaults.risk.max_position_pct <= 1.0
        assert 0 < defaults.risk.max_risk_per_trade <= 1.0
        assert 0 < defaults.risk.max_drawdown <= 1.0
        assert 0 <= defaults.risk.min_confidence <= 1.0
        assert 0 < defaults.risk.bot_loss_threshold <= 1.0

        # Analysis defaults should be positive
        assert defaults.analysis.interval_seconds > 0
        assert defaults.analysis.rsi_period > 0
        assert defaults.analysis.macd_fast > 0
        assert defaults.analysis.macd_slow > 0
        assert defaults.analysis.macd_fast < defaults.analysis.macd_slow
        assert defaults.analysis.macd_signal > 0
        assert defaults.analysis.bollinger_period > 0
        assert defaults.analysis.bollinger_std > 0

        # Logging defaults should be valid
        assert defaults.logging.level in LoggingConfig.VALID_LEVELS
        assert defaults.logging.max_bytes >= 1024
        assert defaults.logging.backup_count >= 0

        # LLM defaults
        assert isinstance(defaults.llm.enabled, bool)
        assert len(defaults.llm.ollama_url) > 0
        assert len(defaults.llm.model) > 0

        # Dry run should default to True for safety
        assert defaults.dry_run is True
