from PyQt6.QtCore import pyqtSignal,QThread
import parsers.writer_data as WrtData
from config import PATH_BUILD

# Создаем класс-поток для выполнения тяжелой задачи в фоне
class SaveDataThread(QThread):
    finished_signal = pyqtSignal()

    def __init__(self):
        super().__init__()

    def run(self):
        # Эта функция теперь выполняется в фоновом потоке и не замораживает UI
        TARGET_DIR_YML = f"{PATH_BUILD}/Resources/Prototypes"
        TARGET_DIR_FTL = f"{PATH_BUILD}/Resources/Locale/ru-RU"
        WrtData.save_data_build(TARGET_DIR_YML, TARGET_DIR_FTL)
        self.finished_signal.emit()
