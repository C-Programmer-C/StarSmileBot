import logging
import os
import re
import sys
from logging.handlers import RotatingFileHandler
from typing import Dict, Optional
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    SECURITY_KEY: str
    REQUEST_FORM_FIELDS: Dict[str, int] = {
        "client": 25,
        "fio": 26,
        "telephone": 27,
        "name": 26,
        "tg_account": 28,
        "tg_id": 29,
        "name_tg": 10,
        "theme": 5,
        "email": 11,
        "description": 8,
        "task_is_new": 31,
    }
    
    LOGIN: str
    
    MAX_FILE_SIZE: int

    BOT_TOKEN: str

    BASE_URL: str

    class Config:  
        env_file = ".env"

settings = Settings() # type: ignore

class StripAnsiFilter(logging.Filter):
    ANSI_ESCAPE = re.compile(r'\x1B\[[0-?]*[ -/]*[@-~]')
    def filter(self, record: logging.LogRecord):
        record.msg = self.ANSI_ESCAPE.sub('', str(record.msg))
        return True


def conf_logger(log_path: Optional[str] = None):
    if log_path is None:
        log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '../app.log')

    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    file_handler = RotatingFileHandler(log_path, maxBytes=10*1024*1024, backupCount=5, encoding='utf-8')
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)
    file_handler.addFilter(StripAnsiFilter())

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    root_logger.handlers = []
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

    root_logger.debug("Logger initialized, log file created")
