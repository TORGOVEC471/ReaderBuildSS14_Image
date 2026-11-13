from PyQt6.QtCore import pyqtSignal,QThread
import parsers.writer_data as WrtData
from config import settings, LOCALE

# Создаем класс-поток для выполнения тяжелой задачи в фоне
class SaveDataThread(QThread):
    finished_signal = pyqtSignal()

    def __init__(self):
        super().__init__()

    def run(self):
        # Эта функция теперь выполняется в фоновом потоке и не замораживает UI
        TARGET_DIR_YML = settings.path_build / "Resources" / "Prototypes"
        TARGET_DIR_FTL = settings.path_build / "Resources" / "Locale" / LOCALE
        WrtData.save_data_build(TARGET_DIR_YML, TARGET_DIR_FTL)
        self.finished_signal.emit()
