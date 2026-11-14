import sys
import os
import shutil
import traceback
import ctypes
from PyQt6.QtWidgets import (
    QApplication, QMessageBox
)
import json
from GUI.main_window import MainWindow
from logger import logger
from config import DATA_FILE

def handle_exception(exc_type, exc_value, exc_traceback):
    """Глобальный перехватчик необработанных исключений"""
    if issubclass(exc_type, KeyboardInterrupt):
        # Даем возможность штатно выйти по Ctrl+C в консоли
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return

    # Логируем ошибку в консоль/файл
    error_msg = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))

    # Логируем ошибку через logger
    logger.critical(f"CRITICAL ERROR: \n{error_msg}")

    # Показываем пользователю красивое окно с ошибкой вместо тихого падения
    msg_box = QMessageBox()
    msg_box.setIcon(QMessageBox.Icon.Critical)
    msg_box.setWindowTitle("Критическая ошибка")
    msg_box.setText("В программе произошла непредвиденная ошибка.")
    msg_box.setDetailedText(error_msg)
    msg_box.setStandardButtons(QMessageBox.StandardButton.Ok)
    msg_box.exec()

# Устанавливаем хук ДО создания QApplication
sys.excepthook = handle_exception

if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    file_path = DATA_FILE
    items = []

    # 1. Проверяем, существует ли файл
    if not os.path.exists(file_path):
        logger.info("Файл data.json не найден. Создаем новый файл по умолчанию.")
        try:
            with open(file_path, "w", encoding="utf-8") as file:
                json.dump([], file, ensure_ascii=False, indent=4)
        except Exception as e:
            logger.error(f"Не удалось создать data.json: {e}")
            QMessageBox.critical(None, "Ошибка", f"Не удалось создать файл данных:\n\n{e}")
    else:
        # 2. Файл существует, пытаемся прочитать и распарсить
        try:
            with open(file_path, "r", encoding="utf-8-sig") as file:
                items = json.load(file)
            logger.info("Данные загружены с data.json!")
        except json.JSONDecodeError as e:
            # Настоящая ошибка повреждения JSON
            logger.error(f"Файл поврежден (JSONDecodeError): {e}")
            
            # Создаем бэкап поврежденного файла перед перезаписью
            backup_path = DATA_FILE.with_suffix(DATA_FILE.suffix + ".bak")
            try:
                shutil.copy2(file_path, backup_path)
                logger.info(f"Создан бэкап поврежденного файла: {backup_path}")
            except Exception as backup_err:
                logger.error(f"Не удалось создать бэкап: {backup_err}")

            QMessageBox.critical(
                None,
                "Ошибка",
                f"Файл data.json повреждён!\nСоздана резервная копия: {backup_path}\nФайл будет сброшен.\n\n[ERROR] {e}"
            )
            
            # Пересоздаем файл
            with open(file_path, "w", encoding="utf-8") as file:
                json.dump([], file, ensure_ascii=False, indent=4)
            items = []
        except Exception as e:
            # Прочие ошибки (например, проблемы с правами доступа)
            logger.error(f"Непредвиденная ошибка при чтении файла: {e}")
            QMessageBox.critical(
                None,
                "Ошибка",
                f"Ошибка при чтении файла data.json:\n\n[ERROR] {e}"
            )
            items = []

    # Сообщаем Windows, что это отдельное приложение со своим идентификатором модели
    if sys.platform == "win32":
        myappid = "TorgovecNoComp.ReaderBuildSS14.v1.0.5"  # Произвольная уникальная строка
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)

    window = MainWindow(items)
    window.show()
    sys.exit(app.exec())