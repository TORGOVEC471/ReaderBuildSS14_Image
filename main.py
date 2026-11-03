import sys
import ctypes
from PyQt6.QtWidgets import (
    QApplication, QMessageBox
)
import json
from GUI.main_window import MainWindow
from logger import logger

if __name__ == "__main__":
    app = QApplication(sys.argv)
    # Открываем файл на чтение ('r') с указанием кодировки utf-8
    try:
        with open("data.json", "r", encoding="utf-8") as file:
            items = json.load(file)
    except Exception as e:
        logger.error({e})
        QMessageBox.critical(
                            None,
                            "Ошибка",
                            f"Файл data.json повреждён! Он будет стёрт!\n\n[ERROR] {e}"
                        )
        # Создаем data.json
        with open("data.json", "w", encoding="utf-8") as file:
            json.dump([], file, ensure_ascii=False, indent=4)
            items = []

    logger.info("Данные загружены с data.json!")

    # Сообщаем Windows, что это отдельное приложение со своим идентификатором модели
    if sys.platform == "win32":
        myappid = "TorgovecNoComp.ReaderBuildSS14.v1.0.4"  # Произвольная уникальная строка
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)


    window = MainWindow(items)
    window.show()
    sys.exit(app.exec())