import sys
import configparser
from pathlib import Path

def get_base_path():
    """Возвращает папку, где лежит .exe (или главный скрипт)"""
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).parent.resolve()
    else:
        return Path(__file__).parent.resolve()

def get_base_path_ico():
    if hasattr(sys, '_MEIPASS'):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent

BASE_DIR = get_base_path()
SETTINGS_FILE = BASE_DIR / "settings.ini"
DATA_FILE = BASE_DIR / "data.json"
LOCALE = "ru-RU"

# Создаем конфигурационный файл по умолчанию, если его нет
if not SETTINGS_FILE.exists():
    config = configparser.ConfigParser()
    config["General"] = {
        "path_saves": ".",
        "path_build": "."
    }
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        config.write(f)

# Runtime-объект настроек: читает актуальные пути динамически
class AppSettings:
    @property
    def path_build(self) -> Path:
        config = configparser.ConfigParser()
        if SETTINGS_FILE.exists():
            config.read(SETTINGS_FILE, encoding="utf-8")
            raw_path = config.get("General", "path_build", fallback=".")
            p = Path(raw_path)
            return (BASE_DIR / p).resolve() if not p.is_absolute() else p.resolve()
        return BASE_DIR

    @property
    def path_saves(self) -> Path:
        config = configparser.ConfigParser()
        if SETTINGS_FILE.exists():
            config.read(SETTINGS_FILE, encoding="utf-8")
            raw_path = config.get("General", "path_saves", fallback=".")
            p = Path(raw_path)
            return (BASE_DIR / p).resolve() if not p.is_absolute() else p.resolve()
        return BASE_DIR

# Экспортируем экземпляр объекта настроек
settings = AppSettings()

icon_path = str(get_base_path_ico() / "assets/ReaderIcon.ico")