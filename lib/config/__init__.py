"""
Configuration Loading and Validation Library.

This module provides configuration management with YAML/JSON loading,
environment variable overrides, validation, and default value handling.

Requirements:
- 9.1: Load configuration from YAML or JSON file at startup
- 9.2: Support environment variable overrides for sensitive values (API keys)
- 9.3: Fail fast with descriptive error messages when configuration is invalid
- 9.4: Provide default values for all optional configuration parameters
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


class ConfigurationError(Exception):
    """
    Exception raised when configuration is invalid.
    
    Provides descriptive error messages for configuration issues.
    
    Requirements:
        - 9.3: Fail fast with descriptive error messages
    """
    
    def __init__(self, message: str, field: str | None = None) -> None:
        """
        Initialize the configuration error.
        
        Args:
            message: Descriptive error message
            field: Optional field name that caused the error
        """
        self.field = field
        if field:
            super().__init__(f"Configuration error in '{field}': {message}")
        else:
            super().__init__(f"Configuration error: {message}")


@dataclass
class DatabaseConfig:
    """Database configuration with defaults."""
    url: str = "postgres://cryptmaster:cryptmaster@localhost:5432/cryptmaster"
    use_sqlite: bool = False
    conn_max_age: int = 600
    
    def __post_init__(self) -> None:
        """Validate database configuration."""
        if not self.url:
            raise ConfigurationError("Database URL cannot be empty", "database.url")
        if self.conn_max_age < 0:
            raise ConfigurationError(
                f"conn_max_age must be non-negative, got {self.conn_max_age}",
                "database.conn_max_age"
            )


@dataclass
class RedisConfig:
    """Redis configuration with defaults."""
    url: str = "redis://localhost:6379/0"
    
    def __post_init__(self) -> None:
        """Validate Redis configuration."""
        if not self.url:
            raise ConfigurationError("Redis URL cannot be empty", "redis.url")


@dataclass
class PionexConfig:
    """Pionex API configuration."""
    api_key: str = ""
    api_secret: str = ""
    
    def validate_for_live_trading(self) -> None:
        """
        Validate that API credentials are set for live trading.
        
        Raises:
            ConfigurationError: If credentials are missing for live trading
        """
        if not self.api_key:
            raise ConfigurationError(
                "API key is required for live trading",
                "pionex.api_key"
            )
        if not self.api_secret:
            raise ConfigurationError(
                "API secret is required for live trading",
                "pionex.api_secret"
            )


@dataclass
class RiskConfig:
    """
    Risk management configuration with defaults.
    
    Requirements:
        - 9.4: Provide default values for all optional configuration parameters
    """
    max_position_pct: float = 0.10
    max_risk_per_trade: float = 0.02
    max_drawdown: float = 0.20
    min_confidence: float = 0.85
    bot_loss_threshold: float = 0.10
    
    def __post_init__(self) -> None:
        """Validate risk configuration."""
        if not 0 < self.max_position_pct <= 1.0:
            raise ConfigurationError(
                f"max_position_pct must be between 0 (exclusive) and 1.0 (inclusive), "
                f"got {self.max_position_pct}",
                "risk.max_position_pct"
            )
        if not 0 < self.max_risk_per_trade <= 1.0:
            raise ConfigurationError(
                f"max_risk_per_trade must be between 0 (exclusive) and 1.0 (inclusive), "
                f"got {self.max_risk_per_trade}",
                "risk.max_risk_per_trade"
            )
        if not 0 < self.max_drawdown <= 1.0:
            raise ConfigurationError(
                f"max_drawdown must be between 0 (exclusive) and 1.0 (inclusive), "
                f"got {self.max_drawdown}",
                "risk.max_drawdown"
            )
        if not 0 <= self.min_confidence <= 1.0:
            raise ConfigurationError(
                f"min_confidence must be between 0 and 1.0, got {self.min_confidence}",
                "risk.min_confidence"
            )
        if not 0 < self.bot_loss_threshold <= 1.0:
            raise ConfigurationError(
                f"bot_loss_threshold must be between 0 (exclusive) and 1.0 (inclusive), "
                f"got {self.bot_loss_threshold}",
                "risk.bot_loss_threshold"
            )


@dataclass
class AnalysisConfig:
    """
    Analysis configuration with defaults.
    
    Requirements:
        - 9.4: Provide default values for all optional configuration parameters
    """
    interval_seconds: int = 60
    rsi_period: int = 14
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9
    bollinger_period: int = 20
    bollinger_std: float = 2.0
    
    def __post_init__(self) -> None:
        """Validate analysis configuration."""
        if self.interval_seconds < 1:
            raise ConfigurationError(
                f"interval_seconds must be at least 1, got {self.interval_seconds}",
                "analysis.interval_seconds"
            )
        if self.rsi_period < 1:
            raise ConfigurationError(
                f"rsi_period must be at least 1, got {self.rsi_period}",
                "analysis.rsi_period"
            )
        if self.macd_fast < 1:
            raise ConfigurationError(
                f"macd_fast must be at least 1, got {self.macd_fast}",
                "analysis.macd_fast"
            )
        if self.macd_slow < 1:
            raise ConfigurationError(
                f"macd_slow must be at least 1, got {self.macd_slow}",
                "analysis.macd_slow"
            )
        if self.macd_fast >= self.macd_slow:
            raise ConfigurationError(
                f"macd_fast ({self.macd_fast}) must be less than macd_slow ({self.macd_slow})",
                "analysis.macd_fast"
            )
        if self.macd_signal < 1:
            raise ConfigurationError(
                f"macd_signal must be at least 1, got {self.macd_signal}",
                "analysis.macd_signal"
            )
        if self.bollinger_period < 1:
            raise ConfigurationError(
                f"bollinger_period must be at least 1, got {self.bollinger_period}",
                "analysis.bollinger_period"
            )
        if self.bollinger_std <= 0:
            raise ConfigurationError(
                f"bollinger_std must be positive, got {self.bollinger_std}",
                "analysis.bollinger_std"
            )


@dataclass
class LLMConfig:
    """
    LLM (Ollama) configuration with defaults.
    
    Requirements:
        - 9.4: Provide default values for all optional configuration parameters
    """
    enabled: bool = False
    ollama_url: str = "http://localhost:11434"
    model: str = "llama3.2"
    
    def __post_init__(self) -> None:
        """Validate LLM configuration."""
        if self.enabled and not self.ollama_url:
            raise ConfigurationError(
                "ollama_url is required when LLM is enabled",
                "llm.ollama_url"
            )
        if self.enabled and not self.model:
            raise ConfigurationError(
                "model is required when LLM is enabled",
                "llm.model"
            )


@dataclass
class LoggingConfig:
    """
    Logging configuration with defaults.
    
    Requirements:
        - 9.4: Provide default values for all optional configuration parameters
    """
    level: str = "INFO"
    max_bytes: int = 10 * 1024 * 1024  # 10 MB
    backup_count: int = 5
    
    VALID_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
    
    def __post_init__(self) -> None:
        """Validate logging configuration."""
        if self.level.upper() not in self.VALID_LEVELS:
            raise ConfigurationError(
                f"Invalid log level '{self.level}'. "
                f"Valid levels: {', '.join(sorted(self.VALID_LEVELS))}",
                "logging.level"
            )
        self.level = self.level.upper()
        
        if self.max_bytes < 1024:
            raise ConfigurationError(
                f"max_bytes must be at least 1024, got {self.max_bytes}",
                "logging.max_bytes"
            )
        if self.backup_count < 0:
            raise ConfigurationError(
                f"backup_count must be non-negative, got {self.backup_count}",
                "logging.backup_count"
            )


@dataclass
class TradingBotConfig:
    """
    Main configuration container for the trading bot.
    
    This class aggregates all configuration sections and provides
    methods for loading from files and environment variables.
    
    Requirements:
        - 9.1: Load configuration from YAML or JSON file at startup
        - 9.2: Support environment variable overrides for sensitive values
        - 9.3: Fail fast with descriptive error messages
        - 9.4: Provide default values for all optional configuration parameters
    """
    dry_run: bool = True
    debug: bool = False
    secret_key: str = "django-insecure-dev-key-change-in-production"
    allowed_hosts: list[str] = field(default_factory=lambda: ["localhost", "127.0.0.1"])
    
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    redis: RedisConfig = field(default_factory=RedisConfig)
    pionex: PionexConfig = field(default_factory=PionexConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    analysis: AnalysisConfig = field(default_factory=AnalysisConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    
    def __post_init__(self) -> None:
        """Validate the complete configuration."""
        # Validate that live trading has API credentials
        if not self.dry_run:
            self.pionex.validate_for_live_trading()
    
    def validate(self) -> None:
        """
        Perform full validation of the configuration.
        
        This method is called after loading to ensure all values are valid.
        
        Raises:
            ConfigurationError: If any configuration value is invalid
            
        Requirements:
            - 9.3: Fail fast with descriptive error messages
        """
        # Re-validate all sub-configs
        self.database.__post_init__()
        self.redis.__post_init__()
        self.risk.__post_init__()
        self.analysis.__post_init__()
        self.llm.__post_init__()
        self.logging.__post_init__()
        
        # Validate live trading requirements
        if not self.dry_run:
            self.pionex.validate_for_live_trading()


def _get_nested_value(data: dict[str, Any], key_path: str, default: Any = None) -> Any:
    """
    Get a nested value from a dictionary using dot notation.
    
    Args:
        data: The dictionary to search
        key_path: Dot-separated path (e.g., "risk.max_position_pct")
        default: Default value if key not found
        
    Returns:
        The value at the path, or default if not found
    """
    keys = key_path.split(".")
    value = data
    
    for key in keys:
        if isinstance(value, dict) and key in value:
            value = value[key]
        else:
            return default
    
    return value


def _apply_env_overrides(config_dict: dict[str, Any]) -> dict[str, Any]:
    """
    Apply environment variable overrides to configuration.
    
    Environment variables take precedence over file configuration.
    
    Args:
        config_dict: Configuration dictionary from file
        
    Returns:
        Configuration dictionary with environment overrides applied
        
    Requirements:
        - 9.2: Support environment variable overrides for sensitive values
    """
    # Map of environment variables to config paths
    env_mappings = {
        # Django settings
        "DJANGO_SECRET_KEY": ("secret_key", str),
        "DEBUG": ("debug", lambda x: x.lower() in ("true", "1", "yes")),
        "ALLOWED_HOSTS": ("allowed_hosts", lambda x: x.split(",")),
        "DRY_RUN": ("dry_run", lambda x: x.lower() in ("true", "1", "yes")),
        
        # Database
        "DATABASE_URL": ("database.url", str),
        "USE_SQLITE": ("database.use_sqlite", lambda x: x.lower() in ("true", "1", "yes")),
        
        # Redis
        "REDIS_URL": ("redis.url", str),
        
        # Pionex API (sensitive)
        "PIONEX_API_KEY": ("pionex.api_key", str),
        "PIONEX_API_SECRET": ("pionex.api_secret", str),
        
        # Risk management
        "RISK_MAX_POSITION_PCT": ("risk.max_position_pct", float),
        "RISK_MAX_PER_TRADE": ("risk.max_risk_per_trade", float),
        "RISK_MAX_DRAWDOWN": ("risk.max_drawdown", float),
        "RISK_MIN_CONFIDENCE": ("risk.min_confidence", float),
        "RISK_BOT_LOSS_THRESHOLD": ("risk.bot_loss_threshold", float),
        
        # Analysis
        "ANALYSIS_INTERVAL_SECONDS": ("analysis.interval_seconds", int),
        "RSI_PERIOD": ("analysis.rsi_period", int),
        "MACD_FAST": ("analysis.macd_fast", int),
        "MACD_SLOW": ("analysis.macd_slow", int),
        "MACD_SIGNAL": ("analysis.macd_signal", int),
        "BOLLINGER_PERIOD": ("analysis.bollinger_period", int),
        "BOLLINGER_STD": ("analysis.bollinger_std", float),
        
        # LLM
        "LLM_ENABLED": ("llm.enabled", lambda x: x.lower() in ("true", "1", "yes")),
        "OLLAMA_URL": ("llm.ollama_url", str),
        "OLLAMA_MODEL": ("llm.model", str),
        
        # Logging
        "LOG_LEVEL": ("logging.level", str),
        "LOG_MAX_BYTES": ("logging.max_bytes", int),
        "LOG_BACKUP_COUNT": ("logging.backup_count", int),
    }
    
    for env_var, (config_path, converter) in env_mappings.items():
        env_value = os.environ.get(env_var)
        if env_value is not None:
            try:
                converted_value = converter(env_value)
                _set_nested_value(config_dict, config_path, converted_value)
            except (ValueError, TypeError) as e:
                raise ConfigurationError(
                    f"Invalid value for environment variable {env_var}: {e}",
                    config_path
                )
    
    return config_dict


def _set_nested_value(data: dict[str, Any], key_path: str, value: Any) -> None:
    """
    Set a nested value in a dictionary using dot notation.
    
    Args:
        data: The dictionary to modify
        key_path: Dot-separated path (e.g., "risk.max_position_pct")
        value: The value to set
    """
    keys = key_path.split(".")
    current = data
    
    for key in keys[:-1]:
        if key not in current:
            current[key] = {}
        current = current[key]
    
    current[keys[-1]] = value


def _dict_to_config(config_dict: dict[str, Any]) -> TradingBotConfig:
    """
    Convert a configuration dictionary to a TradingBotConfig instance.
    
    Args:
        config_dict: Configuration dictionary
        
    Returns:
        TradingBotConfig instance with all values set
        
    Requirements:
        - 9.4: Provide default values for all optional configuration parameters
    """
    # Extract sub-configurations with defaults
    database_dict = config_dict.get("database", {})
    redis_dict = config_dict.get("redis", {})
    pionex_dict = config_dict.get("pionex", {})
    risk_dict = config_dict.get("risk", {})
    analysis_dict = config_dict.get("analysis", {})
    llm_dict = config_dict.get("llm", {})
    logging_dict = config_dict.get("logging", {})
    
    # Create sub-config instances
    database = DatabaseConfig(
        url=database_dict.get("url", DatabaseConfig.url),
        use_sqlite=database_dict.get("use_sqlite", DatabaseConfig.use_sqlite),
        conn_max_age=database_dict.get("conn_max_age", DatabaseConfig.conn_max_age),
    )
    
    redis = RedisConfig(
        url=redis_dict.get("url", RedisConfig.url),
    )
    
    pionex = PionexConfig(
        api_key=pionex_dict.get("api_key", PionexConfig.api_key),
        api_secret=pionex_dict.get("api_secret", PionexConfig.api_secret),
    )
    
    risk = RiskConfig(
        max_position_pct=risk_dict.get("max_position_pct", RiskConfig.max_position_pct),
        max_risk_per_trade=risk_dict.get("max_risk_per_trade", RiskConfig.max_risk_per_trade),
        max_drawdown=risk_dict.get("max_drawdown", RiskConfig.max_drawdown),
        min_confidence=risk_dict.get("min_confidence", RiskConfig.min_confidence),
        bot_loss_threshold=risk_dict.get("bot_loss_threshold", RiskConfig.bot_loss_threshold),
    )
    
    analysis = AnalysisConfig(
        interval_seconds=analysis_dict.get("interval_seconds", AnalysisConfig.interval_seconds),
        rsi_period=analysis_dict.get("rsi_period", AnalysisConfig.rsi_period),
        macd_fast=analysis_dict.get("macd_fast", AnalysisConfig.macd_fast),
        macd_slow=analysis_dict.get("macd_slow", AnalysisConfig.macd_slow),
        macd_signal=analysis_dict.get("macd_signal", AnalysisConfig.macd_signal),
        bollinger_period=analysis_dict.get("bollinger_period", AnalysisConfig.bollinger_period),
        bollinger_std=analysis_dict.get("bollinger_std", AnalysisConfig.bollinger_std),
    )
    
    llm = LLMConfig(
        enabled=llm_dict.get("enabled", LLMConfig.enabled),
        ollama_url=llm_dict.get("ollama_url", LLMConfig.ollama_url),
        model=llm_dict.get("model", LLMConfig.model),
    )
    
    logging_config = LoggingConfig(
        level=logging_dict.get("level", LoggingConfig.level),
        max_bytes=logging_dict.get("max_bytes", LoggingConfig.max_bytes),
        backup_count=logging_dict.get("backup_count", LoggingConfig.backup_count),
    )
    
    # Get top-level values
    allowed_hosts = config_dict.get("allowed_hosts", ["localhost", "127.0.0.1"])
    if isinstance(allowed_hosts, str):
        allowed_hosts = allowed_hosts.split(",")
    
    return TradingBotConfig(
        dry_run=config_dict.get("dry_run", True),
        debug=config_dict.get("debug", False),
        secret_key=config_dict.get("secret_key", "django-insecure-dev-key-change-in-production"),
        allowed_hosts=allowed_hosts,
        database=database,
        redis=redis,
        pionex=pionex,
        risk=risk,
        analysis=analysis,
        llm=llm,
        logging=logging_config,
    )


def load_config_from_file(file_path: str | Path) -> TradingBotConfig:
    """
    Load configuration from a YAML or JSON file.
    
    The file format is determined by the file extension:
    - .yaml, .yml: YAML format
    - .json: JSON format
    
    Environment variables override file values for sensitive data.
    
    Args:
        file_path: Path to the configuration file
        
    Returns:
        TradingBotConfig instance with all values loaded
        
    Raises:
        ConfigurationError: If file cannot be read or parsed
        FileNotFoundError: If file does not exist
        
    Requirements:
        - 9.1: Load configuration from YAML or JSON file at startup
        - 9.2: Support environment variable overrides
        - 9.3: Fail fast with descriptive error messages
    """
    path = Path(file_path)
    
    if not path.exists():
        raise FileNotFoundError(f"Configuration file not found: {path}")
    
    try:
        content = path.read_text(encoding="utf-8")
    except OSError as e:
        raise ConfigurationError(f"Failed to read configuration file: {e}")
    
    # Parse based on file extension
    suffix = path.suffix.lower()
    
    try:
        if suffix in (".yaml", ".yml"):
            config_dict = yaml.safe_load(content) or {}
        elif suffix == ".json":
            config_dict = json.loads(content) if content.strip() else {}
        else:
            raise ConfigurationError(
                f"Unsupported configuration file format: {suffix}. "
                f"Use .yaml, .yml, or .json"
            )
    except yaml.YAMLError as e:
        raise ConfigurationError(f"Invalid YAML syntax: {e}")
    except json.JSONDecodeError as e:
        raise ConfigurationError(f"Invalid JSON syntax: {e}")
    
    # Apply environment variable overrides
    config_dict = _apply_env_overrides(config_dict)
    
    # Convert to config object
    return _dict_to_config(config_dict)


def load_config_from_dict(config_dict: dict[str, Any]) -> TradingBotConfig:
    """
    Load configuration from a dictionary.
    
    Environment variables override dictionary values for sensitive data.
    
    Args:
        config_dict: Configuration dictionary
        
    Returns:
        TradingBotConfig instance with all values loaded
        
    Requirements:
        - 9.2: Support environment variable overrides
        - 9.4: Provide default values for all optional configuration parameters
    """
    # Apply environment variable overrides
    config_dict = _apply_env_overrides(config_dict.copy())
    
    # Convert to config object
    return _dict_to_config(config_dict)


def load_config(
    file_path: str | Path | None = None,
    config_dict: dict[str, Any] | None = None,
) -> TradingBotConfig:
    """
    Load configuration from file, dictionary, or defaults.
    
    Priority order:
    1. Environment variables (highest priority)
    2. File configuration (if provided)
    3. Dictionary configuration (if provided)
    4. Default values (lowest priority)
    
    Args:
        file_path: Optional path to configuration file
        config_dict: Optional configuration dictionary
        
    Returns:
        TradingBotConfig instance with all values loaded
        
    Requirements:
        - 9.1: Load configuration from YAML or JSON file at startup
        - 9.2: Support environment variable overrides
        - 9.3: Fail fast with descriptive error messages
        - 9.4: Provide default values for all optional configuration parameters
    """
    if file_path is not None:
        return load_config_from_file(file_path)
    elif config_dict is not None:
        return load_config_from_dict(config_dict)
    else:
        # Load with defaults and environment overrides only
        return load_config_from_dict({})


def get_default_config() -> TradingBotConfig:
    """
    Get a configuration instance with all default values.
    
    This does NOT apply environment variable overrides.
    
    Returns:
        TradingBotConfig instance with default values
        
    Requirements:
        - 9.4: Provide default values for all optional configuration parameters
    """
    return TradingBotConfig()


# Export public API
__all__ = [
    "ConfigurationError",
    "TradingBotConfig",
    "DatabaseConfig",
    "RedisConfig",
    "PionexConfig",
    "RiskConfig",
    "AnalysisConfig",
    "LLMConfig",
    "LoggingConfig",
    "load_config",
    "load_config_from_file",
    "load_config_from_dict",
    "get_default_config",
]
