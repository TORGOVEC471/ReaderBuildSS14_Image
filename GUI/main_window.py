import os
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QScrollArea, QGridLayout,
    QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QPushButton, QLineEdit, QDialog,
)
from PyQt6.QtGui import QPixmap, QColor, QFont, QPainter
from PyQt6.QtCore import Qt, QSettings, QTimer
from pathlib import Path
from GUI.styles import (COLUMNS, PAGE_SIZE, menu_bar_style)
from GUI.widgets import ClickableLabel
from GUI.dialogs import ImageDetailDialog, SettingsDialog
from GUI.compositor import SceneBuilderDialog
from config import SETTINGS_FILE

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
            self.filtered_items = [
                item for item in self.items
                if query in str(item.get("id", "")).lower()
                or query in str(item.get("name_ftl", "")).lower()
                or query in os.path.basename(item.get("path", "")).lower()
                or query.lower() in [x.lower() for x in item.get("suffix", [])]
                or any(query.lower() in x.lower() for x in (item.get("suffix_ftl") or []) if isinstance(x, str))
            ]

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

    def render_color_image(self, item: dict = None, layer_configs: list = None, display_size: int = None) -> QPixmap:
        """Собирает включенные слои на базовом холсте с учетом видимости, кадров и offset."""
        target_item = item if item is not None else getattr(self, 'item', {})
        
        native_w = target_item.get("size", {}).get("x", 32) or 32
        native_h = target_item.get("size", {}).get("y", 32) or 32

        native_pixmap = QPixmap(native_w, native_h)
        native_pixmap.fill(Qt.GlobalColor.transparent)

        # Если конфиги слоев не переданы явно, берем их из словаря item["layers"]
        if layer_configs is None:
            layers = target_item.get("layers", [])
            if layers:
                layer_configs = [{"enabled": True, "layer": l, "frame": 0} for l in layers]
            else:
                # Если слоев нет, но есть дефолтный state и path
                state_val = target_item.get("state")
                if state_val:
                    layer_configs = [{
                        "enabled": True,
                        "layer": {"state": state_val, "sprite": None},
                        "frame": 0
                    }]
                else:
                    layer_configs = []

        with QPainter(native_pixmap) as painter:
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)

            file_path = Path(target_item.get("file", ""))
            resources_dir = next((p for p in file_path.parents if p.name == "Resources"), None)
            base_textures_path = resources_dir / "Textures" if resources_dir else None

            if base_textures_path:
                for config in layer_configs:
                    if not config.get("enabled", True):
                        continue

                    layer = config["layer"]
                    state_name = layer.get("state")
                    sprite_rel_path = layer.get("sprite")

                    if sprite_rel_path:
                        layer_dir = base_textures_path / sprite_rel_path
                    else:
                        layer_dir = Path(target_item.get("path", ""))

                    layer_file_path = layer_dir / f"{state_name}.png" if state_name else layer_dir

                    if not layer_file_path.exists() or layer_file_path.is_dir():
                        continue

                    full_pixmap = QPixmap(str(layer_file_path))
                    if full_pixmap.isNull():
                        continue

                    # Если спрайт содержит несколько кадров (сетка или строка), вырезаем нужный кадр
                    frame_idx = config.get("frame", 0)
                    if (full_pixmap.width() > native_w or full_pixmap.height() > native_h) and \
                       (full_pixmap.width() % native_w == 0) and (full_pixmap.height() % native_h == 0):
                        
                        frame_w = native_w
                        frame_h = native_h
                        cols = full_pixmap.width() // native_w
                        col = frame_idx % cols
                        row = frame_idx // cols
                        
                        layer_pixmap = full_pixmap.copy(col * frame_w, row * frame_h, frame_w, frame_h)
                    else:
                        layer_pixmap = full_pixmap

                    # Применение цвета (tint) из слоя
                    if "color" in layer and layer["color"]:
                        layer_pixmap = self.apply_layer_color(layer_pixmap, layer["color"])

                    layer_w = layer_pixmap.width()
                    layer_h = layer_pixmap.height()

                    center_x = (native_w - layer_w) // 2
                    center_y = (native_h - layer_h) // 2

                    offset_x, offset_y = 0, 0
                    if "offset" in layer and layer["offset"]:
                        try:
                            parts = [float(p.strip()) for p in str(layer["offset"]).split(",")]
                            if len(parts) == 2:
                                offset_x = int(round(parts[0] * native_w))
                                offset_y = int(round(-parts[1] * native_h))
                        except ValueError:
                            pass

                    final_x = center_x + offset_x
                    final_y = center_y + offset_y

                    painter.drawPixmap(final_x, final_y, layer_pixmap)

        if display_size:
            return native_pixmap.scaled(
                display_size, display_size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.FastTransformation
            )
        return native_pixmap


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

        # Получаем готовый собранный и окрашенный холст (в оригинальном разрешении предмета)
        native_pixmap = self.render_color_image(item=item)

        if not native_pixmap.isNull():
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
        dialog = SettingsDialog()

        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.load_app_settings()

    def load_app_settings(self):
        """Загрузка и применение настроек в главном окне."""
        settings = QSettings(str(SETTINGS_FILE), QSettings.Format.IniFormat)
        build = settings.value("Path_Build", "Не выбран", type=str)
        save = settings.value("Path_Saves", "Не выбран", type=str)

        print(f"Build: {build} | Saves: {save}")

    def open_scene_builder(self):
        dialog = SceneBuilderDialog(self.items, self)
        dialog.exec()
