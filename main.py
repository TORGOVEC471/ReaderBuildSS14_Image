import sys
from PyQt6.QtWidgets import (
    QApplication, QMessageBox
)
import json
from GUI.main_window import MainWindow

if __name__ == "__main__":
    app = QApplication(sys.argv)
    # Открываем файл на чтение ('r') с указанием кодировки utf-8
    try:
        with open("data.json", "r", encoding="utf-8") as file:
            items = json.load(file)
    except Exception as e:
        print(f"[ERROR] {e}")
        QMessageBox.critical(
                            None,
                            "Ошибка",
                            f"Файл data.json повреждён! Он будет стёрт!\n\n[ERROR] {e}"
                        )
        # Создаем data.json
        with open("data.json", "w", encoding="utf-8") as file:
            json.dump([], file, ensure_ascii=False, indent=4)
            items = []

    # print(items)
    print("Данные загружены с data.json!")

    window = MainWindow(items)
    window.show()
    sys.exit(app.exec())