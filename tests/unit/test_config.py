"""
Unit tests for Configuration Loading and Validation.

Tests the configuration module's ability to load from YAML/JSON files,
apply environment variable overrides, validate required fields, and
apply default values.

Requirements:
- 9.1: Load configuration from YAML or JSON file at startup
- 9.2: Support environment variable overrides for sensitive values
- 9.3: Fail fast with descriptive error messages
- 9.4: Provide default values for all optional configuration parameters
"""

import json
import os
import tempfile
from pathlib import Path
from unittest import mock

import pytest
import yaml

from lib.config import (
    AnalysisConfig,
    ConfigurationError,
    DatabaseConfig,
    LLMConfig,
    LoggingConfig,
    PionexConfig,
    RedisConfig,
    RiskConfig,
    TradingBotConfig,
    get_default_config,
    load_config,
    load_config_from_dict,
    load_config_from_file,
)


class TestDefaultValues:
    """Test that default values are applied correctly."""

    def test_get_default_config_returns_valid_config(self) -> None:
        """Default config should be valid and complete."""
        config = get_default_config()
        
        assert config.dry_run is True
        assert config.debug is False
        assert "localhost" in config.allowed_hosts

    def test_database_defaults(self) -> None:
        """Database config should have sensible defaults."""
        config = DatabaseConfig()
        
        assert "postgres" in config.url or "postgresql" in config.url
        assert config.use_sqlite is False
        assert config.conn_max_age == 600

    def test_redis_defaults(self) -> None:
        """Redis config should have sensible defaults."""
        config = RedisConfig()
        
        assert "redis" in config.url
        assert "6379" in config.url

    def test_risk_defaults(self) -> None:
        """Risk config should have sensible defaults."""
        config = RiskConfig()
        
        assert config.max_position_pct == 0.10
        assert config.max_risk_per_trade == 0.02
        assert config.max_drawdown == 0.20
        assert config.min_confidence == 0.85
        assert config.bot_loss_threshold == 0.10

    def test_analysis_defaults(self) -> None:
        """Analysis config should have sensible defaults."""
        config = AnalysisConfig()
        
        assert config.interval_seconds == 60
        assert config.rsi_period == 14
        assert config.macd_fast == 12
        assert config.macd_slow == 26
        assert config.macd_signal == 9
        assert config.bollinger_period == 20
        assert config.bollinger_std == 2.0

    def test_llm_defaults(self) -> None:
        """LLM config should have sensible defaults."""
        config = LLMConfig()
        
        assert config.enabled is False
        assert "11434" in config.ollama_url
        assert config.model == "llama3.2"

    def test_logging_defaults(self) -> None:
        """Logging config should have sensible defaults."""
        config = LoggingConfig()
        
        assert config.level == "INFO"
        assert config.max_bytes == 10 * 1024 * 1024
        assert config.backup_count == 5


class TestYAMLLoading:
    """Test loading configuration from YAML files."""

    def test_load_yaml_file(self) -> None:
        """Should load configuration from YAML file."""
        config_data = {
            "dry_run": False,
            "debug": True,
            "risk": {
                "max_position_pct": 0.15,
            },
            "pionex": {
                "api_key": "test-key",
                "api_secret": "test-secret",
            },
        }
        
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            yaml.dump(config_data, f)
            f.flush()
            
            try:
                # Clear env vars that might interfere
                with mock.patch.dict(os.environ, {}, clear=True):
                    config = load_config_from_file(f.name)
                
                assert config.dry_run is False
                assert config.debug is True
                assert config.risk.max_position_pct == 0.15
            finally:
                os.unlink(f.name)

    def test_load_yml_extension(self) -> None:
        """Should load configuration from .yml file."""
        config_data = {
            "dry_run": False,
            "pionex": {
                "api_key": "test-key",
                "api_secret": "test-secret",
            },
        }
        
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yml", delete=False
        ) as f:
            yaml.dump(config_data, f)
            f.flush()
            
            try:
                with mock.patch.dict(os.environ, {}, clear=True):
                    config = load_config_from_file(f.name)
                
                assert config.dry_run is False
            finally:
                os.unlink(f.name)

    def test_empty_yaml_uses_defaults(self) -> None:
        """Empty YAML file should use all defaults."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            f.write("")
            f.flush()
            
            try:
                with mock.patch.dict(os.environ, {}, clear=True):
                    config = load_config_from_file(f.name)
                
                # Should have all defaults
                assert config.dry_run is True
                assert config.risk.max_position_pct == 0.10
            finally:
                os.unlink(f.name)


class TestJSONLoading:
    """Test loading configuration from JSON files."""

    def test_load_json_file(self) -> None:
        """Should load configuration from JSON file."""
        config_data = {
            "dry_run": False,
            "analysis": {
                "rsi_period": 21,
            },
            "pionex": {
                "api_key": "test-key",
                "api_secret": "test-secret",
            },
        }
        
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump(config_data, f)
            f.flush()
            
            try:
                with mock.patch.dict(os.environ, {}, clear=True):
                    config = load_config_from_file(f.name)
                
                assert config.dry_run is False
                assert config.analysis.rsi_period == 21
            finally:
                os.unlink(f.name)

    def test_empty_json_uses_defaults(self) -> None:
        """Empty JSON file should use all defaults."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            f.write("{}")
            f.flush()
            
            try:
                with mock.patch.dict(os.environ, {}, clear=True):
                    config = load_config_from_file(f.name)
                
                assert config.dry_run is True
            finally:
                os.unlink(f.name)


class TestEnvironmentOverrides:
    """Test environment variable overrides."""

    def test_env_overrides_file_values(self) -> None:
        """Environment variables should override file values."""
        config_data = {"dry_run": True}
        
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            yaml.dump(config_data, f)
            f.flush()
            
            try:
                with mock.patch.dict(
                    os.environ,
                    {
                        "DRY_RUN": "false",
                        "PIONEX_API_KEY": "test-key",
                        "PIONEX_API_SECRET": "test-secret",
                    },
                    clear=True,
                ):
                    config = load_config_from_file(f.name)
                
                assert config.dry_run is False
            finally:
                os.unlink(f.name)

    def test_pionex_api_key_from_env(self) -> None:
        """Pionex API key should be loaded from environment."""
        with mock.patch.dict(
            os.environ,
            {"PIONEX_API_KEY": "test-key", "PIONEX_API_SECRET": "test-secret"},
            clear=True,
        ):
            config = load_config_from_dict({})
        
        assert config.pionex.api_key == "test-key"
        assert config.pionex.api_secret == "test-secret"

    def test_risk_config_from_env(self) -> None:
        """Risk configuration should be loaded from environment."""
        with mock.patch.dict(
            os.environ,
            {
                "RISK_MAX_POSITION_PCT": "0.20",
                "RISK_MAX_DRAWDOWN": "0.30",
            },
            clear=True,
        ):
            config = load_config_from_dict({})
        
        assert config.risk.max_position_pct == 0.20
        assert config.risk.max_drawdown == 0.30

    def test_analysis_config_from_env(self) -> None:
        """Analysis configuration should be loaded from environment."""
        with mock.patch.dict(
            os.environ,
            {
                "RSI_PERIOD": "21",
                "MACD_FAST": "8",
                "MACD_SLOW": "21",
            },
            clear=True,
        ):
            config = load_config_from_dict({})
        
        assert config.analysis.rsi_period == 21
        assert config.analysis.macd_fast == 8
        assert config.analysis.macd_slow == 21


class TestValidation:
    """Test configuration validation."""

    def test_invalid_risk_max_position_pct(self) -> None:
        """Should reject invalid max_position_pct."""
        with pytest.raises(ConfigurationError) as exc_info:
            RiskConfig(max_position_pct=1.5)
        
        assert "max_position_pct" in str(exc_info.value)

    def test_invalid_risk_max_position_pct_zero(self) -> None:
        """Should reject zero max_position_pct."""
        with pytest.raises(ConfigurationError) as exc_info:
            RiskConfig(max_position_pct=0.0)
        
        assert "max_position_pct" in str(exc_info.value)

    def test_invalid_analysis_macd_fast_slow(self) -> None:
        """Should reject macd_fast >= macd_slow."""
        with pytest.raises(ConfigurationError) as exc_info:
            AnalysisConfig(macd_fast=26, macd_slow=12)
        
        assert "macd_fast" in str(exc_info.value)

    def test_invalid_logging_level(self) -> None:
        """Should reject invalid log level."""
        with pytest.raises(ConfigurationError) as exc_info:
            LoggingConfig(level="INVALID")
        
        assert "level" in str(exc_info.value)

    def test_live_trading_requires_api_credentials(self) -> None:
        """Live trading should require API credentials."""
        with pytest.raises(ConfigurationError) as exc_info:
            with mock.patch.dict(os.environ, {}, clear=True):
                TradingBotConfig(dry_run=False)
        
        assert "api_key" in str(exc_info.value).lower() or "api" in str(exc_info.value).lower()

    def test_live_trading_with_credentials_succeeds(self) -> None:
        """Live trading with credentials should succeed."""
        with mock.patch.dict(os.environ, {}, clear=True):
            config = TradingBotConfig(
                dry_run=False,
                pionex=PionexConfig(api_key="key", api_secret="secret"),
            )
        
        assert config.dry_run is False

    def test_database_url_cannot_be_empty(self) -> None:
        """Database URL cannot be empty."""
        with pytest.raises(ConfigurationError) as exc_info:
            DatabaseConfig(url="")
        
        assert "url" in str(exc_info.value).lower()

    def test_llm_enabled_requires_url(self) -> None:
        """LLM enabled requires ollama_url."""
        with pytest.raises(ConfigurationError) as exc_info:
            LLMConfig(enabled=True, ollama_url="")
        
        assert "ollama_url" in str(exc_info.value)


class TestFileErrors:
    """Test error handling for file operations."""

    def test_file_not_found(self) -> None:
        """Should raise FileNotFoundError for missing file."""
        with pytest.raises(FileNotFoundError):
            load_config_from_file("/nonexistent/config.yaml")

    def test_invalid_yaml_syntax(self) -> None:
        """Should raise ConfigurationError for invalid YAML."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            f.write("invalid: yaml: syntax: [")
            f.flush()
            
            try:
                with pytest.raises(ConfigurationError) as exc_info:
                    load_config_from_file(f.name)
                
                assert "YAML" in str(exc_info.value)
            finally:
                os.unlink(f.name)

    def test_invalid_json_syntax(self) -> None:
        """Should raise ConfigurationError for invalid JSON."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            f.write("{invalid json}")
            f.flush()
            
            try:
                with pytest.raises(ConfigurationError) as exc_info:
                    load_config_from_file(f.name)
                
                assert "JSON" in str(exc_info.value)
            finally:
                os.unlink(f.name)

    def test_unsupported_file_format(self) -> None:
        """Should raise ConfigurationError for unsupported format."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False
        ) as f:
            f.write("some content")
            f.flush()
            
            try:
                with pytest.raises(ConfigurationError) as exc_info:
                    load_config_from_file(f.name)
                
                assert "Unsupported" in str(exc_info.value)
            finally:
                os.unlink(f.name)


class TestLoadConfigFunction:
    """Test the main load_config function."""

    def test_load_config_with_file(self) -> None:
        """load_config should work with file path."""
        config_data = {
            "dry_run": False,
            "pionex": {
                "api_key": "test-key",
                "api_secret": "test-secret",
            },
        }
        
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            yaml.dump(config_data, f)
            f.flush()
            
            try:
                with mock.patch.dict(os.environ, {}, clear=True):
                    config = load_config(file_path=f.name)
                
                assert config.dry_run is False
            finally:
                os.unlink(f.name)

    def test_load_config_with_dict(self) -> None:
        """load_config should work with dictionary."""
        with mock.patch.dict(os.environ, {}, clear=True):
            config = load_config(
                config_dict={
                    "dry_run": False,
                    "pionex": {
                        "api_key": "test-key",
                        "api_secret": "test-secret",
                    },
                }
            )
        
        assert config.dry_run is False

    def test_load_config_defaults_only(self) -> None:
        """load_config with no args should use defaults + env."""
        with mock.patch.dict(os.environ, {}, clear=True):
            config = load_config()
        
        assert config.dry_run is True


class TestConfigurationError:
    """Test ConfigurationError exception."""

    def test_error_with_field(self) -> None:
        """Error should include field name."""
        error = ConfigurationError("Invalid value", field="risk.max_position_pct")
        
        assert "risk.max_position_pct" in str(error)
        assert "Invalid value" in str(error)

    def test_error_without_field(self) -> None:
        """Error should work without field name."""
        error = ConfigurationError("General error")
        
        assert "General error" in str(error)
