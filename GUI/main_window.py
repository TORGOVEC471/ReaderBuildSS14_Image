import os
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QScrollArea, QGridLayout,
    QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QPushButton, QLineEdit, QMessageBox
)
from PyQt6.QtGui import QPixmap, QColor, QFont, QPainter, QIcon
from PyQt6.QtCore import Qt, QSettings, QTimer
from GUI.styles import (COLUMNS, PAGE_SIZE, menu_bar_style)
from GUI.widgets import ClickableLabel
from GUI.dialogs import ImageDetailDialog, SettingsDialog
from GUI.compositor import SceneBuilderDialog
from config import SETTINGS_FILE, icon_path
from logger import logger
import json
from img_tools.sprite_processor import render, pil_to_qimage

# Главное окно
class MainWindow(QMainWindow):
    def __init__(self, items):
        super().__init__()
        self.items = items
        self.filtered_items = items
        self.loaded_count = 0

        # Таймер для дебаунса поиска (чтобы не фризило при вводе)
        self.search_timer = QTimer()
        self.search_timer.setSingleShot(True)
        self.search_timer.setInterval(200) # задержка 200 мс
        self.search_timer.timeout.connect(self._execute_filter)

        self.setWindowTitle("ReaderBuildSS14_Image")
        self.setFixedSize(1200, 800)

        self.setWindowIcon(QIcon(icon_path))

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
        """Запускает таймер фильтрации (дебаунс)"""
        self.search_query = text.strip().lower()
        self.search_timer.start()

    def _execute_filter(self):
        """Реальная логика фильтрации, вызываемая после паузы ввода"""
        query = self.search_query

        if not query:
            self.filtered_items = self.items
        else:
            filtered = []
            for item in self.items:
                if not isinstance(item, dict):
                    continue
                
                # 1. Проверка ID
                item_id = str(item.get("id", ""))
                if query in item_id.lower():
                    filtered.append(item)
                    continue

                # 2. Проверка name_ftl
                name_ftl = str(item.get("name_ftl", ""))
                if query in name_ftl.lower():
                    filtered.append(item)
                    continue

                # 3. Проверка path
                path = str(item.get("path", ""))
                if query in os.path.basename(path).lower():
                    filtered.append(item)
                    continue

                # 4. Безопасная проверка suffix (может быть списком, строкой или чем угодно)
                suffix_data = item.get("suffix", [])
                if isinstance(suffix_data, list):
                    if any(isinstance(x, str) and query in x.lower() for x in suffix_data):
                        filtered.append(item)
                        continue
                elif isinstance(suffix_data, str):
                    if query in suffix_data.lower():
                        filtered.append(item)
                        continue

                # 5. Безопасная проверка suffix_ftl
                suffix_ftl_data = item.get("suffix_ftl", [])
                if isinstance(suffix_ftl_data, list):
                    if any(isinstance(x, str) and query in x.lower() for x in suffix_ftl_data):
                        filtered.append(item)
                        continue
                elif isinstance(suffix_ftl_data, str):
                    if query in suffix_ftl_data.lower():
                        filtered.append(item)
                        continue

            self.filtered_items = filtered

        self.reset_and_render()


    def apply_layer_color(self, pixmap: QPixmap, color_hex: str) -> QPixmap:
            """Накладывает цвет через режимы Multiply и DestinationIn."""
            if not color_hex or pixmap.isNull():
                return pixmap
    
            result = QPixmap(pixmap.size())
            result.fill(Qt.GlobalColor.transparent)
    
            painter = QPainter(result)
            painter.drawPixmap(0, 0, pixmap)
            
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Multiply)
            painter.fillRect(result.rect(), QColor(color_hex))
            
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
            painter.drawPixmap(0, 0, pixmap)
            
            painter.end()
            return result

    def render_color_image(self, item: dict = None, layer_configs: list = None, display_size: int = None, direction: int = 0, frame: int = 0) -> QPixmap:
        target_item = item if item is not None else getattr(self, 'item', {})
        overrides = {"layer_configs": layer_configs} if layer_configs else {}
        
        # Получаем результат через единый PIL-рендерер
        pil_img = render(target_item, direction=direction, frame=frame, overrides=overrides)
        
        # Сохраняем флаг наличия контента (проверка альфа-канала)
        self._last_render_has_content = any(pil_img.getextrema()[3])

        # Конвертируем в QPixmap для отображения
        qimg = pil_to_qimage(pil_img)
        pixmap = QPixmap.fromImage(qimg)

        if display_size:
            return pixmap.scaled(
                display_size, display_size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.FastTransformation
            )
        return pixmap


    def create_card(self, item: dict) -> QFrame:
        """Создаёт карточки"""
        
        card = QFrame()
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

        # Получаем готовый собранный и окрашенный холст
        native_pixmap = self.render_color_image(item=item)

        # Проверяем, действительно ли что-то было отрисовано
        if getattr(self, '_last_render_has_content', False) and not native_pixmap.isNull():
            # Масштабируем под размер превью карточки (64x64)
            scaled_sprite = native_pixmap.scaled(
                64, 64,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.FastTransformation
            )

            # Создаем прозрачный квадратный холст 64x64 и рисуем спрайт по центру
            final_pixmap = QPixmap(64, 64)
            final_pixmap.fill(Qt.GlobalColor.transparent)
            
            painter = QPainter(final_pixmap)
            x_offset = (64 - scaled_sprite.width()) // 2
            y_offset = (64 - scaled_sprite.height()) // 2
            
            painter.drawPixmap(x_offset, y_offset, scaled_sprite)
            painter.end()
            
            pixmap = final_pixmap
        else:
            # Заглушка фиолетовым цветом, если файлы не найдены
            pixmap = QPixmap(64, 64)
            pixmap.fill(QColor("#ff00ff"))

        # Виджет для изображения
        img_label = ClickableLabel()
        img_label.setPixmap(pixmap)
        img_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        img_label.setStyleSheet("border: none;")
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
        menu_bar.setStyleSheet(menu_bar_style)

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
        # Подключаем к методу запуска таймера вместо прямого вызова
        self.search_input.textChanged.connect(self.filter_items)

        btn_settings = QPushButton("⚙️ Настройки")
        btn_settings.clicked.connect(self.on_settings_clicked)

        btn_builder = QPushButton("🧩 Конструктор сцен")
        btn_builder.clicked.connect(self.open_scene_builder)

        menu_bar_layout.addWidget(btn_all)
        menu_bar_layout.addWidget(btn_builder)
        menu_bar_layout.addWidget(self.search_input)

        # Растяжка, чтобы push-нуть настройки вниз
        menu_bar_layout.addStretch()
        menu_bar_layout.addWidget(btn_settings)

        return menu_bar

    def on_settings_clicked(self):
        dialog = SettingsDialog(self)
        # Подключаем сигнал успешной перезагрузки данных из окна настроек
        dialog.data_reloaded.connect(self.reload_items_and_grid)
        dialog.exec()

    def reload_items_and_grid(self):
        """Перечитывает data.json и обновляет сетку карточек без перезапуска приложения"""
        file_path = "data.json"
        try:
            if os.path.exists(file_path):
                with open(file_path, "r", encoding="utf-8") as file:
                    self.items = json.load(file)
                logger.info("Данные в MainWindow успешно обновлены из data.json!")
                
                # Сбрасываем фильтры/поиск и перерисовываем сетку заново
                self.filtered_items = self.items
                if hasattr(self, 'search_input') and self.search_input.text():
                    self._execute_filter()
                else:
                    self.reset_and_render()
        except Exception as e:
            logger.error(f"Не удалось обновить данные в MainWindow: {e}")
            QMessageBox.critical(self, "Ошибка", f"Не удалось обновить данные:\n{e}")

    def load_app_settings(self):
        """Загрузка и применение настроек в главном окне."""
        settings = QSettings(str(SETTINGS_FILE), QSettings.Format.IniFormat)
        build = settings.value("Path_Build", "Не выбран", type=str)
        save = settings.value("Path_Saves", "Не выбран", type=str)

        logger.info(f"Build: {build} | Saves: {save}")

    def open_scene_builder(self):
        dialog = SceneBuilderDialog(self.items, self)
        dialog.exec()
