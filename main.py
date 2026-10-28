import sys
from PyQt6.QtWidgets import (
    QApplication, QMessageBox
)
import json
import configparser
from pathlib import Path
from GUI.main_window import MainWindow

SETTINGS_FILE = "settings.ini"

# Настройки
config = configparser.ConfigParser()

if not Path(SETTINGS_FILE).exists():
    config["General"] = {
        "path_saves":".",
        "path_build":"."
    }
    # Записываем настройки в файл
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        config.write(f)
    print(f"Файл {SETTINGS_FILE} успешно создан.")
else:
    print(f"Файл {SETTINGS_FILE} уже существует.")

config.read("settings.ini", encoding="utf-8")

path_build = Path(config["General"]["path_build"])
path_saves = Path(config["General"]["path_saves"])


if __name__ == "__main__":
    app = QApplication(sys.argv)
    # Открываем файл на чтение ('r') с указанием кодировки utf-8
    try:
        with open("data.json", "r", encoding="utf-8") as file:
            items = json.load(file)
    except Exception as e:
        print(f"[ERROR] {e}")
        # Создаем data.json
        with open("data.json", "w", encoding="utf-8") as file:
            json.dump([], file, ensure_ascii=False, indent=4)
            items = []
            QMessageBox.critical(
                            None,
                            "Ошибка",
                            f"Файл data.json повреждён! Он будет стёрт!\n\n[ERROR] {e}"
                        )

    # print(items)
    print("Данные загружены с data.json!")

    window = MainWindow(items, SETTINGS_FILE, path_build)
    window.show()
    sys.exit(app.exec())