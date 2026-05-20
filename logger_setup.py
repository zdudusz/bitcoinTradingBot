"""
logger_setup.py
---------------
Configura o sistema de logs do bot.

Saídas:
  - Console (stdout): nível INFO com cores (se suportado)
  - Arquivo rotativo: logs/trading_bot.log (máx 10MB, 5 backups)

Formato:
  [2024-01-15 14:32:01 UTC] [INFO] [main] Mensagem aqui
"""

import logging
import os
from logging.handlers import RotatingFileHandler
from config import Config


def setup_logger(name: str = "trading_bot") -> logging.Logger:
    """
    Cria e configura o logger principal do bot.

    Args:
        name: Nome do logger (padrão: "trading_bot").

    Returns:
        Instância configurada de logging.Logger.
    """
    config = Config()

    # Garante que o diretório de logs existe
    log_dir = os.path.dirname(config.LOG_FILE)
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)

    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, config.LOG_LEVEL.upper(), logging.INFO))

    # Evita duplicar handlers se setup_logger for chamado mais de uma vez
    if logger.handlers:
        return logger

    # Formato padrão
    fmt = "[%(asctime)s UTC] [%(levelname)s] [%(module)s] %(message)s"
    datefmt = "%Y-%m-%d %H:%M:%S"
    formatter = logging.Formatter(fmt=fmt, datefmt=datefmt)
    formatter.converter = __import__("time").gmtime  # Força UTC

    # --- Handler: Console ---
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)

    # --- Handler: Arquivo Rotativo ---
    # Máximo de 10MB por arquivo, mantém 5 backups
    file_handler = RotatingFileHandler(
        filename=config.LOG_FILE,
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)

    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

    return logger
