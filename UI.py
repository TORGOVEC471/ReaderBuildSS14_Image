import sys
import os
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QScrollArea,
    QGridLayout, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QPushButton, QLineEdit, QDialog, QGroupBox, QDialogButtonBox,
    QFileDialog, QMessageBox, QMenu
)
from PyQt6.QtGui import QPixmap, QColor, QFont, QDesktopServices, QPainter
from PyQt6.QtCore import Qt, pyqtSignal, QUrl, QSettings, QThread
import json
import configparser
import GIF as ToGIF
import IMAGE as ToIMAGE
from pathlib import Path
import WriterData as WrtData

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

print(items)
print("\n\nДанные загружены с data.json!")

SETTINGS_FILE = "settings.ini"
COLUMNS = 3  # Желаемое количество колонок в сетке
PAGE_SIZE = 36 # Сколько элементов грузить за раз (кратно COLUMS)

# Настройки
config = configparser.ConfigParser()
config.read("settings.ini", encoding="utf-8")

path_build = config["General"]["path_build"]
path_saves = config["General"]["path_saves"]

# Стили
# Стиль для кнопок
btn_style = """
    QPushButton {
        background-color: #3498db;
        color: white;
        font-weight: bold;
        padding: 8px 16px;
        border-radius: 4px;
    }
    QPushButton:hover {
        background-color: #2980b9;
    }
"""
# Стиль для рамок (QGroupBox)
group_style = """
    QGroupBox {
        font-weight: bold;
        border: 1px solid #bdc3c7;
        border-radius: 6px;
        margin-top: 0px;
        padding-top: 20px;
    }
    QGroupBox::title {
        subcontrol-origin: margin;
        subcontrol-position: top center; /* Центрируем заголовок */
        padding: 0 5px;
        background-color: transparent;
        top: 5px
    }
"""


# Кликабельный QLabel
class ClickableLabel(QLabel):
    """Специальный QLabel, который умеет излучать сигнал clicked при нажатии."""
    clicked = pyqtSignal()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


# Создаем класс-поток для выполнения тяжелой задачи в фоне
class SaveDataThread(QThread):
    finished_signal = pyqtSignal()

    def __init__(self, path_build):
        super().__init__()
        self.path_build = path_build

    def run(self):
        # Эта функция теперь выполняется в фоновом потоке и не замораживает UI
        WrtData.save_data_build(f"{self.path_build}/Resources/Prototypes/")
        self.finished_signal.emit()


# Модальное окно с увеличенной картинкой и кнопками
class ImageDetailDialog(QDialog):
    """Диалоговое окно детального просмотра изображения."""
    def __init__(self, item: dict, parent=None):
        super().__init__(parent)
        self.item = item
        self.setWindowTitle(f"Просмотр: {item.get('id', 'Элемент')}")
        self.setMinimumSize(400, 450)
        
        # Основной макет окна
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)

        # Загрузка и увеличение изображения
        sprite_path = f"{item.get("path", "")}/{item.get("state", "")}.png"
        pixmap = QPixmap()
        if sprite_path and os.path.exists(sprite_path):
            pixmap.load(sprite_path)
            # Масштабируем до 256x256 с сохранением пропорций
            pixmap = pixmap.scaled(
                256, 256,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.FastTransformation
            )
        else:
            pixmap = QPixmap(256, 256)
            pixmap.fill(QColor("#ff00ff"))

        # Виджет увеличенного изображения
        img_label = QLabel()
        img_label.setPixmap(pixmap)
        img_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(img_label)

        # Заголовок / Идентификатор
        title_label = QLabel(item.get("id", "Без названия"))
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_label.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        layout.addWidget(title_label)

        # Дополнительная информация (путь)
        width, height = ToIMAGE.info_size_image(f"{item.get("path", "")}/{item.get("state", "")}.png")
        path_label = QLabel(f"Путь: {sprite_path}\n\nИгровой размер: {item.get("size").get("x")}x{item.get("size").get("y")}\nРазмер картинки: {width}x{height}")
        path_label.setWordWrap(True)
        path_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        path_label.setStyleSheet("color: #666666;")
        layout.addWidget(path_label)

        # Растяжка перед кнопками
        layout.addStretch()

        # Группа ссылки
        group_links = QGroupBox("Ссылки")
        group_links.setStyleSheet(group_style)
        group_links_layout = QHBoxLayout()

        btn_yml = QPushButton("YML")
        btn_rsi = QPushButton("RSI")
        btn_yml.setStyleSheet(btn_style)
        btn_rsi.setStyleSheet(btn_style)

        group_links_layout.addWidget(btn_yml)
        group_links_layout.addWidget(btn_rsi)
        group_links.setLayout(group_links_layout)

        # Группа кнопок
        group_btns = QGroupBox("Кнопки")
        group_btns.setStyleSheet(group_style)
        group_btns_layout = QHBoxLayout()

        btn_img = QPushButton("IMG")
        btn_gif = QPushButton("GIF")
        btn_img.setStyleSheet(btn_style)
        btn_gif.setStyleSheet(btn_style)

        img_menu = QMenu(self)
        img_menu.addAction("1. Original", lambda: self.process_image_with_mode("Original"))
        img_menu.addAction("2. Resize", lambda: self.process_image_with_mode("Resize"))
        img_menu.addAction("3. South", lambda: self.process_image_with_mode("South"))

        # Привязываем меню к кнопке
        btn_img.setMenu(img_menu)

        # Подключение событий
        btn_yml.clicked.connect(self.on_yml_clicked)
        btn_rsi.clicked.connect(self.on_rsi_clicked)
        btn_gif.clicked.connect(self.on_gif_clicked)

        group_btns_layout.addWidget(btn_img)
        group_btns_layout.addWidget(btn_gif)
        group_btns.setLayout(group_btns_layout)

        # Главный слой
        main_btn_layout = QHBoxLayout()

        main_btn_layout.addWidget(group_links)
        main_btn_layout.addWidget(group_btns)

        layout.addLayout(main_btn_layout)

    def on_yml_clicked(self):
        """Открывает .yml файл картинки (item)"""
        url = QUrl.fromLocalFile(self.item.get("file", ""))
        if url:
            # Открываем системным приложением
            print("Открываем YML!")
            QDesktopServices.openUrl(url)
        else:
            print(f"Неверная ссылка: {url}")

    def on_rsi_clicked(self):
        """Открывает папку .rsi картинки (item)"""
        url = QUrl.fromLocalFile(f"{self.item.get("path", "")}")
        if url:
            # Открываем системным приложением
            print("Открываем RSI!")
            QDesktopServices.openUrl(url)
        else:
            print(f"Неверная ссылка: {url}")

    def on_gif_clicked(self):
        json_path = Path(self.item.get("path", "")) / "meta.json"
        state_name = self.item.get("state", "")
        file_name = self.item.get("id", "")
        ToGIF.process_json_file(json_path, state_name, file_name)

    def process_image_with_mode(self, mode: str):
        image_path = Path(f"{self.item.get('path', '')}/{self.item.get('state', '')}.png")
        image_name = self.item.get("id", "")
        print(f"Обработка с режимом: {mode}")
        ToIMAGE.process_path(image_path, image_name, mode=mode)


# Класс окна настроек
class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Настройки")
        self.resize(600, 250)

        # Компоновка элементов
        main_layout = QVBoxLayout()

        # Инициализация работы ini-файла
        self.settings = QSettings(SETTINGS_FILE, QSettings.Format.IniFormat)

        # ----------------------------------------------------
        # 2. Поле выбора пути к папке (QLineEdit + QPushButton)
        # ----------------------------------------------------
        # Сохранение
        group_saves = QGroupBox("Saves")
        group_saves.setStyleSheet(group_style)
        group_saves_layout = QVBoxLayout()
        btn_line_save_layout = QHBoxLayout()

        self.path_save_input = QLineEdit()
        self.path_save_input.setPlaceholderText("Выберите путь...")
        
        browse_save_btn = QPushButton("Обзор...")
        browse_save_btn.setStyleSheet(btn_style)

        group_saves_layout.addWidget(QLabel("Путь для сохранения файлов:"))
        group_saves_layout.addWidget(QLabel("Точка (.) = та же папка где находится главный файл"))

        btn_line_save_layout.addWidget(self.path_save_input)
        btn_line_save_layout.addWidget(browse_save_btn)
        group_saves_layout.addLayout(btn_line_save_layout)
        group_saves.setLayout(group_saves_layout)

        # Подключаем нажатие кнопки к вызову диалога файловой системы
        browse_save_btn.clicked.connect(
            lambda: self.select_directory(self.path_save_input)
        )

        main_layout.addWidget(group_saves)


        # Билд
        group_build = QGroupBox("Build")
        group_build.setStyleSheet(group_style)
        group_build_layout = QVBoxLayout()
        btn_line_build_layout = QHBoxLayout()

        self.path_build_input = QLineEdit()
        self.path_build_input.setPlaceholderText("Выберите путь...")
        
        browse_build_btn = QPushButton("Обзор...")
        browse_build_btn.setStyleSheet(btn_style)

        group_build_layout.addWidget(QLabel("Путь сборки"))

        btn_line_build_layout.addWidget(self.path_build_input)
        btn_line_build_layout.addWidget(browse_build_btn)
        group_build_layout.addLayout(btn_line_build_layout)
        group_build.setLayout(group_build_layout)

        # Подключаем нажатие кнопки к вызову диалога файловой системы
        browse_build_btn.clicked.connect(
            lambda: self.select_directory(self.path_build_input)
        )

        main_layout.addWidget(group_build)

        # Перезагрузка данных
        group_reloads = QGroupBox("Перезагрузить данные")
        group_reloads.setStyleSheet(group_style)
        group_reloads_layout = QVBoxLayout()

        self.btn_reload = QPushButton("ПЕРЕЗАГРУЗИТЬ")
        self.btn_reload.setStyleSheet(btn_style)

        group_reloads_layout.addWidget(self.btn_reload)
        group_reloads.setLayout(group_reloads_layout)

        self.btn_reload.clicked.connect(self.confirm_action)

        main_layout.addWidget(group_reloads)

        # ----------------------------------------------------
        # 3. Кнопки сохранения / отмены
        # ----------------------------------------------------
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)

        main_layout.addWidget(button_box)
        self.setLayout(main_layout)

        # Загружаем настройки при открытии окна
        self.load_settings()

    # Универсальный метод, принимающий целевое поле ввода
    def select_directory(self, target_line_edit):
        dir_path = QFileDialog.getExistingDirectory(self, "Выберите директорию", "")
        if dir_path:
            target_line_edit.setText(dir_path)

    def load_settings(self):
        """Загрузка данных из settings.ini в виджеты."""
        saved_path_save = self.settings.value("Path_Saves", "", type=str)
        saved_path_build = self.settings.value("Path_Build", ".", type=str)

        # Устанавливаем пути в QLineEdit
        self.path_save_input.setText(saved_path_save)
        self.path_build_input.setText(saved_path_build)

    def save_settings(self):
        """Сохранение данных из виджетов в settings.ini."""
        self.settings.setValue("path_build", self.path_build_input.text())
        self.settings.setValue("path_saves", self.path_save_input.text())

    def confirm_action(self):
        if path_build == ".":
            print("[INFO] Отсутсвует путь билда!")
            QMessageBox.information(
                self,
                "Уведомление",
                "Отсутствует путь билда.\nУкажите путь в наcтройках, чтобы программа могла получить данные!"
            )
            return

        reply = QMessageBox.question(
            self,
            "Подтверждение",
            "Вы действительно хотите продолжить?\nЗагрузка может длиться вплоть до 2-х минут!",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            # меняем текст и блокируем кнопку
            self.btn_reload.setText("🔄ЗАГРУЖАЕТСЯ🔄")
            self.btn_reload.setEnabled(False)

            # принудительно обновляем интерфейс
            QApplication.processEvents()

            # Запускаем фоновый поток
            try:
                self.save_thread = SaveDataThread(path_build)
                self.save_thread.finished_signal.connect(self.on_save_finished)
                self.save_thread.start()
            except Exception as e:
                QMessageBox.information(
                    self,
                    "Error!",
                    f"{e}"
                )

    def on_save_finished(self):
        # Этот метод вызовется автоматически, когда поток закончит работу
        QMessageBox.information(
            self, 
            "Готово!", 
            "Перезагрузка завершена.\nПерезагрузите программу чтобы применить изменения!"
        )
        self.btn_reload.setText("ПЕРЕЗАГРУЗИТЬ")
        self.btn_reload.setEnabled(True)

# Главное окно
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("ReaderBuildSS14_Image")
        self.setFixedSize(1200, 800)

        # Переменные полигинации
        self.filtered_items = items
        self.loaded_count = 0

        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        layout = QHBoxLayout()

        # меню
        menu_bar = self.create_menu_bar()

        # картинки
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("background-color: #99ee99;")

        ## Событие прокрутки для "бесконечной" загрузки
        self.scroll_area.verticalScrollBar().valueChanged.connect(self.on_scroll)

        ## контейнер
        self.container = QWidget()
        self.grid_layout = QGridLayout(self.container)
        self.grid_layout.setSpacing(15)
        self.grid_layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)

        ## Помещаем контейнер внутрь области прокрутки
        self.scroll_area.setWidget(self.container)

        # Добавляем виджеты в главный макет
        layout.addWidget(menu_bar)
        layout.addWidget(self.scroll_area)
        central_widget.setLayout(layout)

        # Первоначальная загрузка первой порции
        self.reset_and_render()

    def reset_and_render(self):
        """Очищает сетку, сбрасывает скролл и загружает первую порцию элементов."""
        # 1. Удаляем все текущие виджеты из сетки
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        # 2. Сбрасываем счетчики и поднимаем скролл наверх
        self.loaded_count = 0
        self.scroll_area.verticalScrollBar().setValue(0)

        # 3. Загружаем первую порцию
        self.load_next_batch()

    def load_next_batch(self):
        """Подгружает следующую порцию (PAGE_SIZE) карточек."""
        if self.loaded_count >= len(self.filtered_items):
            return  # Все элементы уже загружены

        # Берем срезом только нужный кусок массива
        next_items = self.filtered_items[self.loaded_count : self.loaded_count + PAGE_SIZE]

        for index_in_batch, item in enumerate(next_items):
            global_index = self.loaded_count + index_in_batch
            row_num = global_index // COLUMNS
            col_num = global_index % COLUMNS

            card = self.create_card(item)
            self.grid_layout.addWidget(card, row_num, col_num)

        self.loaded_count += len(next_items)

    def on_scroll(self, value: int):
        """Проверяет, дошел ли пользователь до низа страницы."""
        vbar = self.scroll_area.verticalScrollBar()
        # Если до конца скролла осталось меньше 150 пикселей — подгружаем новые карточки
        if value >= vbar.maximum() - 150:
            self.load_next_batch()

    def filter_items(self, text: str):
        """Срабатывает при вводе текста в строку поиска."""
        query = text.strip().lower()

        if not query:
            # Если поле поиска пустое, показываем все элементы
            self.filtered_items = items
        else:
            # Ищем совпадения по названию карточки (title) ИЛИ по имени файла (path)
            self.filtered_items = [
                item for item in items
                if query in str(item.get("id", "")).lower() or query in os.path.basename(item.get("path", "")).lower()
            ]

        self.reset_and_render()

    def create_card(self, item: dict) -> QFrame:
        """Создаёт карточки"""
        card = QFrame()
        # Стилизация рамки (границы и фон карточки)
        card.setStyleSheet("""
            QFrame {
                border: 1px solid #c0c0c0;
                border-radius: 6px;
                background-color: #ffffff;
            }
        """)

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(8, 8, 8, 8)
        card_layout.setSpacing(6)

        # Разрешаем путь к картинке через фоллбэк
        # sprite_path = self.resolve_sprite_path(item.get("path", ""))
        sprite_path = f"{item.get("path", "")}/{item.get("state", "")}.png"

        # Загрузка изображения
        pixmap = QPixmap()
        if sprite_path and os.path.exists(sprite_path):
            pixmap.load(sprite_path)
            x_img = item.get("size", {}).get("x", 32)
            y_img = item.get("size", {}).get("y", 32)
            cropped = self.get_cropped_preview(pixmap, crop_w=x_img, crop_h=y_img, center=False)
            scaled_sprite = cropped.scaled(
                64, 64,
                # Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.FastTransformation
            )

            # Создаем прозрачный квадратный холст 64x64 и рисуем спрайт по центру
            final_pixmap = QPixmap(64, 64)
            final_pixmap.fill(Qt.GlobalColor.transparent)
            
            painter = QPainter(final_pixmap)
            # Вычисляем смещение для центрирования
            x_offset = (64 - scaled_sprite.width()) // 2
            y_offset = (64 - scaled_sprite.height()) // 2
            
            painter.drawPixmap(x_offset, y_offset, scaled_sprite)
            painter.end()
            
            pixmap = final_pixmap
        else:
            # Заглушка фиолетовым цветом, если файл не найден
            pixmap = QPixmap(64, 64)
            pixmap.fill(QColor("#ff00ff"))


        # Виджет для изображения
        img_label = ClickableLabel()
        img_label.setPixmap(pixmap)
        img_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        img_label.setStyleSheet("border: none;")  # Убираем внутреннюю рамку у картинки
        img_label.setCursor(Qt.CursorShape.PointingHandCursor)

        img_label.clicked.connect(lambda i=item: self.open_detail_dialog(i))

        # Виджет для текста
        title_label = QLabel(item["id"])
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_label.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        title_label.setStyleSheet("border: none; color: #000000;")

        # Добавляем в компоновку карточки
        card_layout.addWidget(img_label)
        card_layout.addWidget(title_label)

        return card

    def open_detail_dialog(self, item: dict):
        """Открывает диалоговое окно с деталями и кнопками."""
        dialog = ImageDetailDialog(item, self)
        dialog.exec()  # exec() делает окно модальным (блокирует родительское окно)

    def get_cropped_preview(self, pixmap: QPixmap, crop_w=32, crop_h=32, center=True) -> QPixmap:
        """Возвращает обрезанную копию QPixmap"""
        img_w, img_h = pixmap.width(), pixmap.height()
        
        # Защита на случай, если картинка меньше 32x32
        target_w = min(crop_w, img_w)
        target_h = min(crop_h, img_h)

        if center:
            # Координаты для обрезки по центру
            x = (img_w - target_w) // 2
            y = (img_h - target_h) // 2
        else:
            # Обрезка с левого верхнего угла (0, 0)
            x, y = 0, 0

        # copy(x, y, width, height) вырезает только нужную область
        return pixmap.copy(x, y, target_w, target_h)

    def create_menu_bar(self) -> QWidget:
        """Создаёт меню для левой стороны программы"""
        menu_bar = QFrame()
        menu_bar.setFixedWidth(220)
        menu_bar.setStyleSheet("""
            QFrame {
                background-color: #2c3e50;
                border: none;
            }
            QPushButton {
                color: #ecf0f1;
                background-color: transparent;
                border: none;
                padding: 12px 15px;
                text-align: left;
                font-size: 14px;
                font-weight: bold;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #34495e;
                color: #ffffff;
            }
            QPushButton:pressed {
                background-color: #1abc9c;
            }
        """)

        menu_bar_layout = QVBoxLayout(menu_bar)
        menu_bar_layout.setContentsMargins(10, 20, 10, 20)
        menu_bar_layout.setSpacing(10)

        # Заголовок
        menu_bar_title = QLabel("Reader Image SS14")
        menu_bar_title.setStyleSheet("color: #ffffff; font-size: 18px; font-weight: bold; padding: 10px 5px;")
        menu_bar_layout.addWidget(menu_bar_title)

        # Кнопки меню
        btn_all = QPushButton("📁 Все элементы")
        btn_all.clicked.connect(lambda: self.search_input.clear())  # Сброс поиска при клике

        # Поле ввода поиска
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("🔍 Поиск по названию...")
        # Подключаем сигнал textChanged к методу фильтрации
        self.search_input.textChanged.connect(self.filter_items)
        menu_bar_layout.addWidget(self.search_input)

        btn_settings = QPushButton("⚙️ Настройки")
        btn_settings.clicked.connect(self.on_settings_clicked)

        menu_bar_layout.addWidget(btn_all)
        menu_bar_layout.addWidget(self.search_input)

        # Растяжка, чтобы push-нуть настройки вниз
        menu_bar_layout.addStretch()
        menu_bar_layout.addWidget(btn_settings)

        return menu_bar

    def on_settings_clicked(self):
        dialog = SettingsDialog(self)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            dialog.save_settings()
            self.load_app_settings()

    def load_app_settings(self):
        """Загрузка и применение настроек в главном окне."""
        settings = QSettings(SETTINGS_FILE, QSettings.Format.IniFormat)
        build = settings.value("Path_Build", "Не выбран", type=str)
        save = settings.value("Path_Saves", "Не выбран", type=str)

        print(f"Build: {build} | Saves: {save}")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())