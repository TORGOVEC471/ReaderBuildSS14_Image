from PyQt6.QtCore import pyqtSignal, QThread
import parsers.writer_data as WrtData
from config import settings, LOCALE

class SaveDataThread(QThread):
    finished_signal = pyqtSignal()
    failed_signal = pyqtSignal(str)  # Сигнал для передачи текста ошибки в главный поток

    def __init__(self):
        super().__init__()

    def run(self):
        try:
            TARGET_DIR_YML = settings.path_build / "Resources" / "Prototypes"
            TARGET_DIR_FTL = settings.path_build / "Resources" / "Locale" / LOCALE
            WrtData.save_data_build(TARGET_DIR_YML, TARGET_DIR_FTL)
            self.finished_signal.emit()
        except Exception as e:
            # Безопасно передаем ошибку наружу, не вызывая QMessageBox из потока
            self.failed_signal.emit(str(e))