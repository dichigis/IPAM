"""
Конфигурация логирования для IPAM.
"""
import logging
import sys
from pathlib import Path
from logging.handlers import RotatingFileHandler

DEFAULT_LOG_DIR = Path(__file__).parent.parent.parent / "logs"
DEFAULT_LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
DEFAULT_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def setup_logging(
    log_dir: Path = DEFAULT_LOG_DIR,
    log_level: int = logging.DEBUG,
    log_to_console: bool = False,
    app_name: str = "ipam"
) -> logging.Logger:
    """
    Настраивает логирование для приложения.

    Args:
        log_dir: Директория для log файлов
        log_level: Уровень логирования
        log_to_console: Выводить ли логи в консоль (по умолчанию нет)
        app_name: Имя приложения для лог файла

    Returns:
        Корневой логгер
    """
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"{app_name}.log"

    # Форматтер
    formatter = logging.Formatter(DEFAULT_LOG_FORMAT, DEFAULT_DATE_FORMAT)

    # Файловый handler с ротацией
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=5,
        encoding="utf-8"
    )
    file_handler.setLevel(log_level)
    file_handler.setFormatter(formatter)

    # Корневой логгер
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Очищаем существующие handlers
    root_logger.handlers.clear()

    root_logger.addHandler(file_handler)

    # Консольный handler (только если запрошен)
    if log_to_console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(log_level)
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)

    # Уменьшаем verbosity для grpc
    logging.getLogger("grpc").setLevel(logging.WARNING)

    root_logger.info(f"Логирование настроено. Лог файл: {log_file}")
    return root_logger
