import os
import glob
from datetime import datetime
import logging
from pathlib import Path

def setup_logger(logger_name="ReaderBuildSS14"):
    # 1. Создаем папку Logs, если она не существует
    folder_path_log = Path("Logs")
    folder_path_log.mkdir(exist_ok=True) # exist_ok=True защитит от ошибки, если папка уже есть

    # 2. Формируем уникальное имя файла на основе текущего времени запуска
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    log_filename = f"app_{timestamp}.log"
    log_path = folder_path_log / log_filename

    # 3. Настраиваем логирование
    # (force=True полезно, если basicConfig вызывается повторно, доступно в Python 3.8+)
    logging.basicConfig(
        filename=log_path,
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] — %(message)s",
        encoding="utf-8",
        force=True 
    )

    # Получаем логгер ПОСЛЕ базовой настройки
    logger = logging.getLogger(logger_name)

    # 4. Очистка старых файлов: оставляем максимум 5 последних
    log_files = sorted(
        glob.glob(os.path.join(folder_path_log, "app_*.log")), 
        key=os.path.getmtime
    )

    # Если файлов больше 5, удаляем самые старые излишки
    if len(log_files) > 5:
        files_to_delete = log_files[:-5]  # Все, кроме последних 5
        for old_file in files_to_delete:
            try:
                os.remove(old_file)
                logger.info(f"Удален старый лог-файл: {old_file}")
            except Exception as e:
                logger.info(f"Не удалось удалить файл {old_file}: {e}")

    # 5. Возвращаем готовый логгер наружу
    return logger

logger = setup_logger()

# --- Пример использования ---
if __name__ == "__main__":
    # Вызываем функцию один раз, инициализируем логгер и сохраняем его в переменную
    logger = setup_logger()
    
    logger.info("Программа успешно запущена.")
    logger.warning("Это предупреждение (warning).")
    logger.error("Это сообщение об ошибке (error).")
    
    print("Логирование настроено. Проверьте папку Logs.")