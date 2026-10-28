from PyQt6.QtCore import pyqtSignal,QThread
import parsers.writer_data as WrtData

# Создаем класс-поток для выполнения тяжелой задачи в фоне
class SaveDataThread(QThread):
    finished_signal = pyqtSignal()

    def __init__(self, path_build):
        super().__init__()
        self.path_build = path_build

    def run(self):
        # Эта функция теперь выполняется в фоновом потоке и не замораживает UI
        TARGET_DIR_YML = f"{self.path_build}/Resources/Prototypes/"
        TARGET_DIR_FTL = f"{self.path_build}/Resources/Locale/ru-RU"
        WrtData.save_data_build(TARGET_DIR_YML, TARGET_DIR_FTL)
        self.finished_signal.emit()
