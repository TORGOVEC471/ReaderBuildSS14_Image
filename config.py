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
    # Если приложение запущено как скомпилированный EXE
    if hasattr(sys, '_MEIPASS'):
        return Path(sys._MEIPASS)
    # Если приложение запущено как обычный .py скрипт
    return Path(__file__).resolve().parent


BASE_DIR = get_base_path()
SETTINGS_FILE = BASE_DIR / "settings.ini"
DATA_FILE = BASE_DIR / "data.json"

# Читаем или создаем конфиг
config = configparser.ConfigParser()

if not SETTINGS_FILE.exists():
    config["General"] = {
        "path_saves": ".",
        "path_build": "."
    }
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        config.write(f)

config.read(SETTINGS_FILE, encoding="utf-8")

# Экспортируем готовые переменные, чтобы их можно было импортировать в любой файл
PATH_BUILD = Path(config["General"]["path_build"])
PATH_SAVES = Path(config["General"]["path_saves"])

icon_path = str(get_base_path_ico() / "assets/ReaderIcon.ico")