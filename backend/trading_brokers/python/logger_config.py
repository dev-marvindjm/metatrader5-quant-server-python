import os
import sys
import logging
from logging.handlers import RotatingFileHandler
from typing import Optional

class ExactLevelFilter(logging.Filter):
    """Filter that matches a specific logging level exactly."""
    def __init__(self, level: int):
        super().__init__()
        self.level = level

    def filter(self, record: logging.LogRecord) -> bool:
        return record.levelno == self.level

class MinLevelFilter(logging.Filter):
    """Filter that matches a minimum logging level and higher (e.g. ERROR and CRITICAL)."""
    def __init__(self, min_level: int):
        super().__init__()
        self.min_level = min_level

    def filter(self, record: logging.LogRecord) -> bool:
        return record.levelno >= self.min_level

class LoggerWriter:
    """Redirects standard stream writes (stdout/stderr) to a logger."""
    def __init__(self, logger: logging.Logger, level: int):
        self.logger = logger
        self.level = level
        self._buffer = ""

    def write(self, message: str):
        if not message:
            return
        self._buffer += message
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            line = line.strip("\r")
            if line:
                self.logger.log(self.level, line)

    def flush(self):
        if self._buffer:
            line = self._buffer.strip("\r\n")
            if line:
                self.logger.log(self.level, line)
            self._buffer = ""

    def isatty(self) -> bool:
        return False

def get_logs_dir() -> str:
    """Determines and creates the logs directory."""
    if "LOGS_DIR" in os.environ and os.environ["LOGS_DIR"]:
        logs_dir = os.path.abspath(os.environ["LOGS_DIR"])
    else:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        # If inside trading_brokers/python or similar subfolder
        candidate_root = os.path.abspath(os.path.join(base_dir, "..", ".."))
        if os.path.exists(os.path.join(candidate_root, "Cargo.toml")):
            logs_dir = os.path.join(candidate_root, "logs")
        elif os.path.exists(os.path.join(base_dir, "Cargo.toml")):
            logs_dir = os.path.join(base_dir, "logs")
        else:
            logs_dir = os.path.join(os.getcwd(), "logs")

    os.makedirs(logs_dir, exist_ok=True)
    return logs_dir

def setup_logging(redirect_stdio: bool = False, max_bytes: int = 10 * 1024 * 1024, backup_count: int = 5) -> str:
    """
    Configures Python logging to write exclusively to files, separated by level:
      - debug.log   : DEBUG level messages
      - info.log    : INFO level messages
      - warning.log : WARNING level messages
      - error.log   : ERROR and CRITICAL level messages
      - all.log     : Complete chronological logs across all levels

    No logs are output to the console.
    """
    logs_dir = get_logs_dir()
    formatter = logging.Formatter(
        '[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # 1. Debug file handler (exact DEBUG)
    debug_handler = RotatingFileHandler(
        os.path.join(logs_dir, "debug.log"),
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8"
    )
    debug_handler.setLevel(logging.DEBUG)
    debug_handler.addFilter(ExactLevelFilter(logging.DEBUG))
    debug_handler.setFormatter(formatter)

    # 2. Info file handler (exact INFO)
    info_handler = RotatingFileHandler(
        os.path.join(logs_dir, "info.log"),
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8"
    )
    info_handler.setLevel(logging.INFO)
    info_handler.addFilter(ExactLevelFilter(logging.INFO))
    info_handler.setFormatter(formatter)

    # 3. Warning file handler (exact WARNING)
    warning_handler = RotatingFileHandler(
        os.path.join(logs_dir, "warning.log"),
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8"
    )
    warning_handler.setLevel(logging.WARNING)
    warning_handler.addFilter(ExactLevelFilter(logging.WARNING))
    warning_handler.setFormatter(formatter)

    # 4. Error file handler (ERROR and CRITICAL)
    error_handler = RotatingFileHandler(
        os.path.join(logs_dir, "error.log"),
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8"
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.addFilter(MinLevelFilter(logging.ERROR))
    error_handler.setFormatter(formatter)

    # 5. Combined all.log handler (ALL levels)
    all_handler = RotatingFileHandler(
        os.path.join(logs_dir, "all.log"),
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8"
    )
    all_handler.setLevel(logging.DEBUG)
    all_handler.setFormatter(formatter)

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)

    # Remove all existing handlers (e.g. default StreamHandler writing to console)
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)

    root_logger.addHandler(debug_handler)
    root_logger.addHandler(info_handler)
    root_logger.addHandler(warning_handler)
    root_logger.addHandler(error_handler)
    root_logger.addHandler(all_handler)

    # Clear console handlers from all pre-existing loggers
    for logger_name, logger_obj in logging.Logger.manager.loggerDict.items():
        if isinstance(logger_obj, logging.Logger):
            for h in list(logger_obj.handlers):
                if isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler):
                    logger_obj.removeHandler(h)

    # Redirect stdout and stderr if requested (e.g. for background daemon)
    if redirect_stdio:
        stdout_logger = logging.getLogger("stdout")
        stderr_logger = logging.getLogger("stderr")
        sys.stdout = LoggerWriter(stdout_logger, logging.DEBUG)
        sys.stderr = LoggerWriter(stderr_logger, logging.ERROR)

    return logs_dir

def get_logger(name: str = "broker_daemon") -> logging.Logger:
    """Returns a logger with the given name."""
    return logging.getLogger(name)
