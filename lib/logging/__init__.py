"""
Structured Logging Library.

This module provides structured logging for the trading system with:
- Configurable log levels (DEBUG, INFO, WARNING, ERROR)
- File rotation with configurable size and backup count
- Structured JSON logging for machine parsing
- Context-aware logging for trading decisions and bot events
- Separate log files for different components

Requirements:
- 8.1: Log all trading decisions with timestamp, signal details, confidence score
- 8.2: Log order details including symbol, side, type, price, quantity, order ID
- 8.3: Log errors with full context, stack trace, and recovery action
- 8.4: Support configurable log levels (DEBUG, INFO, WARNING, ERROR)
- 8.5: Log configuration parameters and mode at startup
- 8.6: Persist logs to files with configurable rotation policy
- 10.11: Log all bot creation, modification, and termination events
"""

from __future__ import annotations

import json
import logging
import logging.handlers
import os
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any


# Default log directory
DEFAULT_LOG_DIR = Path("logs")

# Default log file names
MAIN_LOG_FILE = "crypt-master.log"
TRADING_LOG_FILE = "trading.log"
BOT_LOG_FILE = "bots.log"
ERROR_LOG_FILE = "errors.log"


# Default rotation settings
DEFAULT_MAX_BYTES = 10 * 1024 * 1024  # 10 MB
DEFAULT_BACKUP_COUNT = 5


class LogLevel(Enum):
    """Log level enumeration."""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


@dataclass
class LoggingConfig:
    """
    Configuration for the logging system.
    
    Attributes:
        log_dir: Directory for log files
        log_level: Default log level for all loggers
        console_enabled: Whether to output to console
        file_enabled: Whether to output to files
        json_format: Whether to use JSON format for file logs
        max_bytes: Maximum size of each log file before rotation
        backup_count: Number of backup files to keep
        include_timestamp: Whether to include timestamp in log messages
        include_module: Whether to include module name in log messages
        include_process: Whether to include process ID in log messages
        include_thread: Whether to include thread ID in log messages
    """
    log_dir: Path = field(default_factory=lambda: DEFAULT_LOG_DIR)
    log_level: str = "INFO"
    console_enabled: bool = True
    file_enabled: bool = True
    json_format: bool = True
    max_bytes: int = DEFAULT_MAX_BYTES
    backup_count: int = DEFAULT_BACKUP_COUNT
    include_timestamp: bool = True
    include_module: bool = True
    include_process: bool = False
    include_thread: bool = False
    
    def __post_init__(self) -> None:
        """Validate and convert configuration values."""
        if isinstance(self.log_dir, str):
            self.log_dir = Path(self.log_dir)
        
        # Validate log level
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if self.log_level.upper() not in valid_levels:
            raise ValueError(
                f"Invalid log level: {self.log_level}. "
                f"Must be one of: {valid_levels}"
            )
        self.log_level = self.log_level.upper()


class DecimalEncoder(json.JSONEncoder):
    """JSON encoder that handles Decimal and datetime objects."""
    
    def default(self, obj: Any) -> Any:
        if isinstance(obj, Decimal):
            return str(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, Enum):
            return obj.value
        if hasattr(obj, "__dict__"):
            return obj.__dict__
        return super().default(obj)


class StructuredFormatter(logging.Formatter):
    """
    Formatter that outputs structured JSON log records.
    
    This formatter creates JSON-formatted log entries that include
    all relevant context for machine parsing and analysis.
    
    Requirements:
        - 8.1: Log all trading decisions with full context
        - 8.3: Log errors with full context and stack trace
    """
    
    def __init__(
        self,
        include_timestamp: bool = True,
        include_module: bool = True,
        include_process: bool = False,
        include_thread: bool = False,
    ) -> None:
        """Initialize the formatter."""
        super().__init__()
        self.include_timestamp = include_timestamp
        self.include_module = include_module
        self.include_process = include_process
        self.include_thread = include_thread
    
    def format(self, record: logging.LogRecord) -> str:
        """Format the log record as JSON."""
        log_data: dict[str, Any] = {
            "level": record.levelname,
            "message": record.getMessage(),
        }
        
        if self.include_timestamp:
            log_data["timestamp"] = datetime.now(tz=timezone.utc).isoformat()
        
        if self.include_module:
            log_data["module"] = record.module
            log_data["logger"] = record.name
        
        if self.include_process:
            log_data["process"] = record.process
        
        if self.include_thread:
            log_data["thread"] = record.thread
        
        # Include extra fields from the record
        if hasattr(record, "extra_data") and record.extra_data:
            log_data["context"] = record.extra_data
        
        # Include exception info if present
        if record.exc_info:
            log_data["exception"] = {
                "type": record.exc_info[0].__name__ if record.exc_info[0] else None,
                "message": str(record.exc_info[1]) if record.exc_info[1] else None,
                "traceback": self.formatException(record.exc_info),
            }
        
        return json.dumps(log_data, cls=DecimalEncoder, ensure_ascii=False)


class ConsoleFormatter(logging.Formatter):
    """
    Formatter for console output with colors and readable format.
    
    Requirements:
        - 8.4: Support configurable log levels
    """
    
    # ANSI color codes
    COLORS = {
        "DEBUG": "\033[36m",     # Cyan
        "INFO": "\033[32m",      # Green
        "WARNING": "\033[33m",   # Yellow
        "ERROR": "\033[31m",     # Red
        "CRITICAL": "\033[35m",  # Magenta
    }
    RESET = "\033[0m"
    
    def __init__(self, use_colors: bool = True) -> None:
        """Initialize the formatter."""
        super().__init__(
            fmt="%(levelname)s %(asctime)s %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        self.use_colors = use_colors and sys.stdout.isatty()
    
    def format(self, record: logging.LogRecord) -> str:
        """Format the log record with optional colors."""
        formatted = super().format(record)
        
        if self.use_colors:
            color = self.COLORS.get(record.levelname, "")
            formatted = f"{color}{formatted}{self.RESET}"
        
        return formatted


class ContextLogger(logging.LoggerAdapter):
    """
    Logger adapter that adds context to all log messages.
    
    This adapter allows adding persistent context (like symbol, bot_id)
    that will be included in all subsequent log messages.
    
    Example:
        >>> logger = get_trading_logger("BTC_USDT")
        >>> logger.info("Signal generated", confidence=85.5, direction="BUY")
    """
    
    def __init__(
        self,
        logger: logging.Logger,
        extra: dict[str, Any] | None = None,
    ) -> None:
        """Initialize the adapter."""
        super().__init__(logger, extra or {})
    
    def process(
        self,
        msg: str,
        kwargs: dict[str, Any],
    ) -> tuple[str, dict[str, Any]]:
        """Process the log message and add context."""
        # Merge extra data from kwargs with adapter's extra
        extra_data = dict(self.extra)
        
        # Extract any extra fields passed to the log call
        if "extra" not in kwargs:
            kwargs["extra"] = {}
        
        # Add any additional keyword arguments as context
        for key, value in list(kwargs.items()):
            if key not in ("exc_info", "stack_info", "stacklevel", "extra"):
                extra_data[key] = value
                del kwargs[key]
        
        kwargs["extra"]["extra_data"] = extra_data
        
        return msg, kwargs
    
    def with_context(self, **context: Any) -> "ContextLogger":
        """Create a new logger with additional context."""
        new_extra = dict(self.extra)
        new_extra.update(context)
        return ContextLogger(self.logger, new_extra)


def setup_logging(config: LoggingConfig | None = None) -> None:
    """
    Configure the logging system.
    
    This function sets up all loggers with appropriate handlers,
    formatters, and log levels based on the configuration.
    
    Args:
        config: Logging configuration. Uses defaults if not provided.
        
    Requirements:
        - 8.4: Support configurable log levels
        - 8.5: Log configuration parameters and mode at startup
        - 8.6: Persist logs to files with configurable rotation policy
    """
    config = config or LoggingConfig()
    
    # Ensure log directory exists
    config.log_dir.mkdir(parents=True, exist_ok=True)
    
    # Get the root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, config.log_level))
    
    # Clear existing handlers
    root_logger.handlers.clear()
    
    # Console handler
    if config.console_enabled:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(getattr(logging, config.log_level))
        console_handler.setFormatter(ConsoleFormatter())
        root_logger.addHandler(console_handler)
    
    # File handlers
    if config.file_enabled:
        # Main log file (all logs)
        main_handler = logging.handlers.RotatingFileHandler(
            filename=config.log_dir / MAIN_LOG_FILE,
            maxBytes=config.max_bytes,
            backupCount=config.backup_count,
            encoding="utf-8",
        )
        main_handler.setLevel(getattr(logging, config.log_level))
        if config.json_format:
            main_handler.setFormatter(StructuredFormatter(
                include_timestamp=config.include_timestamp,
                include_module=config.include_module,
                include_process=config.include_process,
                include_thread=config.include_thread,
            ))
        else:
            main_handler.setFormatter(logging.Formatter(
                fmt="%(levelname)s %(asctime)s %(name)s: %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            ))
        root_logger.addHandler(main_handler)
        
        # Error log file (ERROR and above only)
        error_handler = logging.handlers.RotatingFileHandler(
            filename=config.log_dir / ERROR_LOG_FILE,
            maxBytes=config.max_bytes,
            backupCount=config.backup_count,
            encoding="utf-8",
        )
        error_handler.setLevel(logging.ERROR)
        if config.json_format:
            error_handler.setFormatter(StructuredFormatter(
                include_timestamp=True,
                include_module=True,
                include_process=True,
                include_thread=True,
            ))
        else:
            error_handler.setFormatter(logging.Formatter(
                fmt="%(levelname)s %(asctime)s %(name)s %(process)d: %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            ))
        root_logger.addHandler(error_handler)
    
    # Configure specific loggers
    _configure_component_loggers(config)


def _configure_component_loggers(config: LoggingConfig) -> None:
    """Configure loggers for specific components."""
    # Trading logger
    trading_logger = logging.getLogger("trading")
    trading_logger.setLevel(getattr(logging, config.log_level))
    
    if config.file_enabled:
        trading_handler = logging.handlers.RotatingFileHandler(
            filename=config.log_dir / TRADING_LOG_FILE,
            maxBytes=config.max_bytes,
            backupCount=config.backup_count,
            encoding="utf-8",
        )
        trading_handler.setLevel(logging.DEBUG)
        if config.json_format:
            trading_handler.setFormatter(StructuredFormatter())
        else:
            trading_handler.setFormatter(logging.Formatter(
                fmt="%(levelname)s %(asctime)s: %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            ))
        trading_logger.addHandler(trading_handler)
    
    # Bot logger
    bot_logger = logging.getLogger("bots")
    bot_logger.setLevel(getattr(logging, config.log_level))
    
    if config.file_enabled:
        bot_handler = logging.handlers.RotatingFileHandler(
            filename=config.log_dir / BOT_LOG_FILE,
            maxBytes=config.max_bytes,
            backupCount=config.backup_count,
            encoding="utf-8",
        )
        bot_handler.setLevel(logging.DEBUG)
        if config.json_format:
            bot_handler.setFormatter(StructuredFormatter())
        else:
            bot_handler.setFormatter(logging.Formatter(
                fmt="%(levelname)s %(asctime)s: %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            ))
        bot_logger.addHandler(bot_handler)
    
    # Agents logger
    agents_logger = logging.getLogger("agents")
    agents_logger.setLevel(getattr(logging, config.log_level))
    
    # Apps logger
    apps_logger = logging.getLogger("apps")
    apps_logger.setLevel(getattr(logging, config.log_level))


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger by name.
    
    Args:
        name: Logger name (e.g., "trading", "bots", "agents.market")
        
    Returns:
        Logger instance
    """
    return logging.getLogger(name)


def get_context_logger(
    name: str,
    **context: Any,
) -> ContextLogger:
    """
    Get a context-aware logger.
    
    Args:
        name: Logger name
        **context: Initial context to include in all log messages
        
    Returns:
        ContextLogger instance
    """
    return ContextLogger(logging.getLogger(name), context)


# =============================================================================
# Specialized Loggers for Trading and Bot Events
# =============================================================================

class TradingLogger:
    """
    Specialized logger for trading decisions and orders.
    
    This logger provides methods for logging trading-specific events
    with all required context.
    
    Requirements:
        - 8.1: Log all trading decisions with timestamp, signal details, confidence
        - 8.2: Log order details including symbol, side, type, price, quantity, order ID
    """
    
    def __init__(self, symbol: str | None = None) -> None:
        """Initialize the trading logger."""
        self._logger = get_context_logger("trading", symbol=symbol)
        self._symbol = symbol
    
    def for_symbol(self, symbol: str) -> "TradingLogger":
        """Create a new logger for a specific symbol."""
        return TradingLogger(symbol)
    
    def log_signal(
        self,
        symbol: str,
        direction: str,
        confidence: float,
        indicators: list[dict[str, Any]] | None = None,
        reasoning: str | None = None,
        meets_threshold: bool = True,
        threshold: float = 85.0,
    ) -> None:
        """
        Log a trading signal generation.
        
        Args:
            symbol: Trading pair symbol
            direction: Signal direction (BUY/SELL/HOLD)
            confidence: Confidence score (0-100)
            indicators: List of indicator results
            reasoning: Human-readable reasoning
            meets_threshold: Whether signal meets confidence threshold
            threshold: Confidence threshold used
            
        Requirements:
            - 8.1: Log all trading decisions with full context
        """
        self._logger.info(
            f"Signal generated: {symbol} {direction} ({confidence:.1f}%)",
            event_type="signal_generated",
            symbol=symbol,
            direction=direction,
            confidence=confidence,
            meets_threshold=meets_threshold,
            threshold=threshold,
            indicators=indicators or [],
            reasoning=reasoning,
        )
    
    def log_order(
        self,
        order_id: str,
        symbol: str,
        side: str,
        order_type: str,
        price: Decimal | float,
        quantity: Decimal | float,
        status: str = "SUBMITTED",
        is_simulated: bool = False,
    ) -> None:
        """
        Log an order submission or execution.
        
        Args:
            order_id: Unique order identifier
            symbol: Trading pair symbol
            side: Order side (BUY/SELL)
            order_type: Order type (LIMIT/MARKET)
            price: Order price
            quantity: Order quantity
            status: Order status
            is_simulated: Whether this is a simulated order
            
        Requirements:
            - 8.2: Log order details including symbol, side, type, price, quantity, order ID
        """
        self._logger.info(
            f"Order {status}: {order_id} - {side} {quantity} {symbol} @ {price}",
            event_type="order",
            order_id=order_id,
            symbol=symbol,
            side=side,
            order_type=order_type,
            price=str(price),
            quantity=str(quantity),
            status=status,
            is_simulated=is_simulated,
        )
    
    def log_trade_execution(
        self,
        trade_id: str,
        order_id: str,
        symbol: str,
        side: str,
        price: Decimal | float,
        quantity: Decimal | float,
        pnl: Decimal | float | None = None,
        is_simulated: bool = False,
    ) -> None:
        """
        Log a trade execution.
        
        Args:
            trade_id: Unique trade identifier
            order_id: Associated order ID
            symbol: Trading pair symbol
            side: Trade side
            price: Execution price
            quantity: Executed quantity
            pnl: Realized P&L (if closing trade)
            is_simulated: Whether this is a simulated trade
        """
        msg = f"Trade executed: {trade_id} - {side} {quantity} {symbol} @ {price}"
        if pnl is not None:
            msg += f" (P&L: {pnl})"
        
        self._logger.info(
            msg,
            event_type="trade_execution",
            trade_id=trade_id,
            order_id=order_id,
            symbol=symbol,
            side=side,
            price=str(price),
            quantity=str(quantity),
            pnl=str(pnl) if pnl is not None else None,
            is_simulated=is_simulated,
        )


class BotLogger:
    """
    Specialized logger for bot lifecycle events.
    
    This logger provides methods for logging bot-specific events
    including creation, modification, performance updates, and termination.
    
    Requirements:
        - 10.11: Log all bot creation, modification, and termination events
    """
    
    def __init__(self, bot_id: str | None = None) -> None:
        """Initialize the bot logger."""
        self._logger = get_context_logger("bots", bot_id=bot_id)
        self._bot_id = bot_id
    
    def for_bot(self, bot_id: str) -> "BotLogger":
        """Create a new logger for a specific bot."""
        return BotLogger(bot_id)
    
    def log_bot_created(
        self,
        bot_id: str,
        bot_type: str,
        symbol: str,
        invested: Decimal | float,
        params: dict[str, Any],
        reasoning: str,
        is_simulated: bool = False,
    ) -> None:
        """
        Log bot creation event.
        
        Args:
            bot_id: Unique bot identifier
            bot_type: Type of bot (GRID/DCA)
            symbol: Trading pair symbol
            invested: Investment amount
            params: Bot parameters
            reasoning: Reason for creation
            is_simulated: Whether this is a simulated bot
            
        Requirements:
            - 10.11: Log all bot creation events with full parameters and reasoning
        """
        self._logger.info(
            f"Bot created: {bot_id} ({bot_type}) for {symbol}, invested: {invested}",
            event_type="bot_created",
            bot_id=bot_id,
            bot_type=bot_type,
            symbol=symbol,
            invested=str(invested),
            params=params,
            reasoning=reasoning,
            is_simulated=is_simulated,
        )
    
    def log_bot_stopped(
        self,
        bot_id: str,
        symbol: str,
        reason: str,
        final_pnl: Decimal | float | None = None,
        is_simulated: bool = False,
    ) -> None:
        """
        Log bot termination event.
        
        Args:
            bot_id: Bot identifier
            symbol: Trading pair symbol
            reason: Reason for stopping
            final_pnl: Final P&L at stop
            is_simulated: Whether this is a simulated bot
            
        Requirements:
            - 10.11: Log all bot termination events with full parameters and reasoning
        """
        msg = f"Bot stopped: {bot_id} for {symbol}"
        if final_pnl is not None:
            msg += f" (Final P&L: {final_pnl})"
        
        self._logger.info(
            msg,
            event_type="bot_stopped",
            bot_id=bot_id,
            symbol=symbol,
            reason=reason,
            final_pnl=str(final_pnl) if final_pnl is not None else None,
            is_simulated=is_simulated,
        )
    
    def log_bot_modified(
        self,
        bot_id: str,
        symbol: str,
        changes: dict[str, Any],
        reasoning: str,
    ) -> None:
        """
        Log bot modification event.
        
        Args:
            bot_id: Bot identifier
            symbol: Trading pair symbol
            changes: Dictionary of changed parameters
            reasoning: Reason for modification
            
        Requirements:
            - 10.11: Log all bot modification events with full parameters and reasoning
        """
        self._logger.info(
            f"Bot modified: {bot_id} for {symbol}",
            event_type="bot_modified",
            bot_id=bot_id,
            symbol=symbol,
            changes=changes,
            reasoning=reasoning,
        )
    
    def log_bot_performance(
        self,
        bot_id: str,
        symbol: str,
        pnl: Decimal | float,
        pnl_percent: float,
        current_value: Decimal | float,
        is_underperforming: bool = False,
    ) -> None:
        """
        Log bot performance update.
        
        Args:
            bot_id: Bot identifier
            symbol: Trading pair symbol
            pnl: Current P&L
            pnl_percent: P&L as percentage
            current_value: Current bot value
            is_underperforming: Whether bot is flagged as underperforming
        """
        level = logging.WARNING if is_underperforming else logging.DEBUG
        
        self._logger.logger.log(
            level,
            f"Bot performance: {bot_id} - P&L: {pnl} ({pnl_percent:.2f}%)",
            extra={
                "extra_data": {
                    "event_type": "bot_performance",
                    "bot_id": bot_id,
                    "symbol": symbol,
                    "pnl": str(pnl),
                    "pnl_percent": pnl_percent,
                    "current_value": str(current_value),
                    "is_underperforming": is_underperforming,
                }
            },
        )


class SystemLogger:
    """
    Specialized logger for system-level events.
    
    This logger provides methods for logging system startup, configuration,
    errors, and other system-wide events.
    
    Requirements:
        - 8.3: Log errors with full context, stack trace, and recovery action
        - 8.5: Log configuration parameters and mode at startup
    """
    
    def __init__(self) -> None:
        """Initialize the system logger."""
        self._logger = get_context_logger("system")
    
    def log_startup(
        self,
        service_name: str,
        mode: str,
        config: dict[str, Any],
    ) -> None:
        """
        Log system startup with configuration.
        
        Args:
            service_name: Name of the service starting
            mode: Operating mode (e.g., "dry-run", "live")
            config: Configuration parameters
            
        Requirements:
            - 8.5: Log configuration parameters and mode at startup
        """
        # Filter sensitive values from config
        safe_config = _filter_sensitive_config(config)
        
        self._logger.info(
            f"Starting {service_name} in {mode} mode",
            event_type="startup",
            service_name=service_name,
            mode=mode,
            config=safe_config,
        )
    
    def log_shutdown(
        self,
        service_name: str,
        reason: str = "normal",
    ) -> None:
        """
        Log system shutdown.
        
        Args:
            service_name: Name of the service shutting down
            reason: Reason for shutdown
        """
        self._logger.info(
            f"Shutting down {service_name}: {reason}",
            event_type="shutdown",
            service_name=service_name,
            reason=reason,
        )
    
    def log_error(
        self,
        message: str,
        error: Exception | None = None,
        recovery_action: str | None = None,
        **context: Any,
    ) -> None:
        """
        Log an error with full context.
        
        Args:
            message: Error message
            error: Exception object (if available)
            recovery_action: Action taken to recover
            **context: Additional context
            
        Requirements:
            - 8.3: Log errors with full context, stack trace, and recovery action
        """
        self._logger.logger.error(
            message,
            exc_info=error is not None,
            extra={
                "extra_data": {
                    "event_type": "error",
                    "error_type": type(error).__name__ if error else None,
                    "error_message": str(error) if error else None,
                    "recovery_action": recovery_action,
                    **context,
                }
            },
        )
    
    def log_warning(
        self,
        message: str,
        **context: Any,
    ) -> None:
        """
        Log a warning.
        
        Args:
            message: Warning message
            **context: Additional context
        """
        self._logger.warning(message, **context)
    
    def log_config_change(
        self,
        key: str,
        old_value: Any,
        new_value: Any,
    ) -> None:
        """
        Log a configuration change.
        
        Args:
            key: Configuration key
            old_value: Previous value
            new_value: New value
        """
        self._logger.info(
            f"Configuration changed: {key}",
            event_type="config_change",
            key=key,
            old_value=_sanitize_value(old_value),
            new_value=_sanitize_value(new_value),
        )


def _filter_sensitive_config(config: dict[str, Any]) -> dict[str, Any]:
    """Filter sensitive values from configuration."""
    sensitive_keys = {
        "api_key", "api_secret", "secret", "password", "token",
        "PIONEX_API_KEY", "PIONEX_API_SECRET", "SECRET_KEY",
    }
    
    filtered = {}
    for key, value in config.items():
        key_lower = key.lower()
        if any(s in key_lower for s in sensitive_keys):
            filtered[key] = "***REDACTED***"
        elif isinstance(value, dict):
            filtered[key] = _filter_sensitive_config(value)
        else:
            filtered[key] = value
    
    return filtered


def _sanitize_value(value: Any) -> Any:
    """Sanitize a value for logging."""
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    return value


# =============================================================================
# Singleton Logger Instances
# =============================================================================

_trading_logger: TradingLogger | None = None
_bot_logger: BotLogger | None = None
_system_logger: SystemLogger | None = None


def get_trading_logger(symbol: str | None = None) -> TradingLogger:
    """
    Get the trading logger instance.
    
    Args:
        symbol: Optional symbol to create a symbol-specific logger
        
    Returns:
        TradingLogger instance
    """
    global _trading_logger
    if _trading_logger is None:
        _trading_logger = TradingLogger()
    
    if symbol:
        return _trading_logger.for_symbol(symbol)
    return _trading_logger


def get_bot_logger(bot_id: str | None = None) -> BotLogger:
    """
    Get the bot logger instance.
    
    Args:
        bot_id: Optional bot ID to create a bot-specific logger
        
    Returns:
        BotLogger instance
    """
    global _bot_logger
    if _bot_logger is None:
        _bot_logger = BotLogger()
    
    if bot_id:
        return _bot_logger.for_bot(bot_id)
    return _bot_logger


def get_system_logger() -> SystemLogger:
    """
    Get the system logger instance.
    
    Returns:
        SystemLogger instance
    """
    global _system_logger
    if _system_logger is None:
        _system_logger = SystemLogger()
    return _system_logger


# =============================================================================
# Django Integration
# =============================================================================

def configure_django_logging() -> dict[str, Any]:
    """
    Generate Django LOGGING configuration dictionary.
    
    This function returns a configuration dictionary suitable for
    Django's LOGGING setting.
    
    Returns:
        Django LOGGING configuration dictionary
        
    Requirements:
        - 8.4: Support configurable log levels
        - 8.6: Persist logs to files with configurable rotation policy
    """
    log_level = os.environ.get("LOG_LEVEL", "INFO")
    log_dir = Path(os.environ.get("LOG_DIR", "logs"))
    max_bytes = int(os.environ.get("LOG_MAX_BYTES", str(DEFAULT_MAX_BYTES)))
    backup_count = int(os.environ.get("LOG_BACKUP_COUNT", str(DEFAULT_BACKUP_COUNT)))
    json_format = os.environ.get("LOG_JSON_FORMAT", "true").lower() == "true"
    
    # Ensure log directory exists
    log_dir.mkdir(parents=True, exist_ok=True)
    
    config: dict[str, Any] = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "verbose": {
                "format": "{levelname} {asctime} {module} {process:d} {thread:d} {message}",
                "style": "{",
            },
            "simple": {
                "format": "{levelname} {asctime} {module} {message}",
                "style": "{",
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "simple",
            },
            "file": {
                "class": "logging.handlers.RotatingFileHandler",
                "filename": str(log_dir / MAIN_LOG_FILE),
                "maxBytes": max_bytes,
                "backupCount": backup_count,
                "formatter": "verbose",
            },
            "trading_file": {
                "class": "logging.handlers.RotatingFileHandler",
                "filename": str(log_dir / TRADING_LOG_FILE),
                "maxBytes": max_bytes,
                "backupCount": backup_count,
                "formatter": "verbose",
            },
            "bot_file": {
                "class": "logging.handlers.RotatingFileHandler",
                "filename": str(log_dir / BOT_LOG_FILE),
                "maxBytes": max_bytes,
                "backupCount": backup_count,
                "formatter": "verbose",
            },
            "error_file": {
                "class": "logging.handlers.RotatingFileHandler",
                "filename": str(log_dir / ERROR_LOG_FILE),
                "maxBytes": max_bytes,
                "backupCount": backup_count,
                "formatter": "verbose",
                "level": "ERROR",
            },
        },
        "root": {
            "handlers": ["console"],
            "level": log_level,
        },
        "loggers": {
            "django": {
                "handlers": ["console"],
                "level": os.environ.get("DJANGO_LOG_LEVEL", "INFO"),
                "propagate": False,
            },
            "apps": {
                "handlers": ["console", "file"],
                "level": os.environ.get("APP_LOG_LEVEL", "DEBUG"),
                "propagate": False,
            },
            "agents": {
                "handlers": ["console", "file"],
                "level": os.environ.get("AGENT_LOG_LEVEL", "DEBUG"),
                "propagate": False,
            },
            "trading": {
                "handlers": ["console", "trading_file"],
                "level": "DEBUG",
                "propagate": False,
            },
            "bots": {
                "handlers": ["console", "bot_file"],
                "level": "DEBUG",
                "propagate": False,
            },
            "system": {
                "handlers": ["console", "file", "error_file"],
                "level": "DEBUG",
                "propagate": False,
            },
        },
    }
    
    return config


# =============================================================================
# Public API
# =============================================================================

__all__ = [
    # Configuration
    "LoggingConfig",
    "LogLevel",
    "setup_logging",
    "configure_django_logging",
    # Formatters
    "StructuredFormatter",
    "ConsoleFormatter",
    # Loggers
    "ContextLogger",
    "TradingLogger",
    "BotLogger",
    "SystemLogger",
    # Logger getters
    "get_logger",
    "get_context_logger",
    "get_trading_logger",
    "get_bot_logger",
    "get_system_logger",
    # Constants
    "DEFAULT_LOG_DIR",
    "DEFAULT_MAX_BYTES",
    "DEFAULT_BACKUP_COUNT",
    "MAIN_LOG_FILE",
    "TRADING_LOG_FILE",
    "BOT_LOG_FILE",
    "ERROR_LOG_FILE",
]
