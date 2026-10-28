import os
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QLineEdit, QDialog,
    QGroupBox, QDialogButtonBox, QFileDialog, QMessageBox,
    QMenu, QCheckBox, QWidgetAction, QSpinBox
)
from PyQt6.QtGui import QPixmap, QColor, QFont, QDesktopServices, QPainter
from PyQt6.QtCore import Qt, QUrl, QSettings, QPoint
import json
import img_tools.GIF as ToGIF
import img_tools.IMAGE as ToIMAGE
from pathlib import Path
from GUI.styles import (btn_style, group_style)
from GUI.threads import SaveDataThread

# Модальное окно с увеличенной картинкой и кнопками
class ImageDetailDialog(QDialog):
    """Диалоговое окно детального просмотра изображения."""
    def __init__(self, item: dict, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose) # Уничтожит объект при закрытии окна

        self.item = item
        self.setWindowTitle(f"Просмотр: {item.get('id', 'Элемент')}")
        self.setMinimumSize(400, 500)
        
        # Инициализация конфигурации слоев (видимость и текущий кадр)
        self.layer_configs = []
        for layer in self.item.get("layers", []):
            # Если в YAML явно указано visible: false, по умолчанию выключаем слой
            default_visible = layer.get("visible", True)
            self.layer_configs.append({
                "layer": layer,
                "enabled": default_visible,
                "frame": 0
            })

        # Основной макет окна
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)

        # --- Верхний макет: Кнопка состояний + Галочка "Сборщик" + Кнопка слоев ---
        top_layout = QHBoxLayout()

        self.btn_state = QPushButton()
        self.btn_state.setStyleSheet(btn_style)
        
        states = self.item.get("states", [self.item.get("state", "default")])
        state_menu = QMenu(self)
        for state in states:
            state_menu.addAction(str(state), lambda s=state: self.change_state(s))

        self.btn_state.setMenu(state_menu)
        top_layout.addWidget(self.btn_state)

        # Галочка переключения режима Сборщика
        self.cb_builder = QCheckBox("Сборщик")
        self.cb_builder.toggled.connect(self.on_builder_toggled)
        top_layout.addWidget(self.cb_builder)

        # Кнопка настройки слоев (активна только в режиме Сборщик)
        self.btn_layers = QPushButton("⚙ Слои")
        self.btn_layers.setStyleSheet(btn_style)
        self.btn_layers.setVisible(False)
        self.btn_layers.clicked.connect(self.show_layers_menu)
        top_layout.addWidget(self.btn_layers)

        layout.addLayout(top_layout)

        # --- Виджет изображения ---
        self.img_label = QLabel()
        self.img_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.img_label)

        # Заголовок / Идентификатор
        title_label = QLabel(item.get("id", "Без названия"))
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_label.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        layout.addWidget(title_label)

        # --- Дополнительная информация ---
        self.path_label = QLabel()
        self.path_label.setWordWrap(True)
        self.path_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.path_label.setStyleSheet("color: #666666;")
        layout.addWidget(self.path_label)

        # Установка начального состояния
        current_state = self.item.get("state") or (states[0] if states else "")
        self.change_state(current_state)

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
        btn_webp = QPushButton("WebP")
        btn_img.setStyleSheet(btn_style)
        btn_gif.setStyleSheet(btn_style)
        btn_webp.setStyleSheet(btn_style)

        img_menu = QMenu(self)
        img_menu.addAction("1. Original", lambda: self.process_image_with_mode("Original"))
        img_menu.addAction("2. Resize", lambda: self.process_image_with_mode("Resize"))
        img_menu.addAction("3.1 South (лицо)", lambda: self.process_image_with_mode("South"))
        img_menu.addAction("3.2 North (зад)", lambda: self.process_image_with_mode("North"))
        img_menu.addAction("3.3 East (правый профиль)", lambda: self.process_image_with_mode("East"))
        img_menu.addAction("3.4 West (левый профиль)", lambda: self.process_image_with_mode("West"))
        btn_img.setMenu(img_menu)

        btn_yml.clicked.connect(self.on_yml_clicked)
        btn_rsi.clicked.connect(self.on_rsi_clicked)
        btn_gif.clicked.connect(self.on_gif_clicked)
        btn_webp.clicked.connect(self.on_webp_clicked)

        group_btns_layout.addWidget(btn_img)
        group_btns_layout.addWidget(btn_gif)
        group_btns_layout.addWidget(btn_webp)
        group_btns.setLayout(group_btns_layout)

        # Главный слой кнопок
        main_btn_layout = QHBoxLayout()
        main_btn_layout.addWidget(group_links)
        main_btn_layout.addWidget(group_btns)

        layout.addLayout(main_btn_layout)

    def on_builder_toggled(self, checked: bool):
        """Поведение при включении/выключении режима Сборщик."""
        self.btn_layers.setVisible(checked)
        self.change_state(self.item.get("state", ""))

    def show_layers_menu(self):
        """Выпадающее меню для настройки видимости и кадров слоев."""
        menu = QMenu(self)
        
        file_path = Path(self.item.get("file", ""))
        resources_dir = next((p for p in file_path.parents if p.name == "Resources"), None)
        base_textures_path = resources_dir / "Textures" if resources_dir else None

        for i, config in enumerate(self.layer_configs):
            layer = config["layer"]
            state_name = layer.get("state", "")
            maps = layer.get("map", [f"Слой {i+1}"])
            # Извлекаем красивое имя из enum (например, "DoorVisualLayers.Base" -> "Base")
            layer_name = str(maps[0]).split(".")[-1] if maps else f"Слой {i+1}"
            
            # Определяем количество кадров (frameCount) из meta.json
            frame_count = 1
            if base_textures_path:
                sprite_rel_path = layer.get("sprite")
                layer_dir = base_textures_path / sprite_rel_path if sprite_rel_path else Path(self.item.get("path", ""))
                meta_path = layer_dir / "meta.json"
                if meta_path.exists():
                    try:
                        with open(meta_path, "r", encoding="utf-8") as f:
                            meta_data = json.load(f)
                            for st in meta_data.get("states", []):
                                if st.get("name") == state_name:
                                    frame_count = st.get("frameCount", 1)
                                    break
                    except Exception:
                        pass

            # Виджет для пункта меню (Чекбокс + Спиннер кадров при необходимости)
            widget = QWidget()
            h_layout = QHBoxLayout(widget)
            h_layout.setContentsMargins(8, 4, 8, 4)

            chk = QCheckBox(f"{layer_name} ({state_name})")
            chk.setChecked(config["enabled"])
            
            def make_toggle_handler(idx=i, c=chk):
                return lambda state: self.toggle_layer(idx, c.isChecked())
            chk.toggled.connect(make_toggle_handler())
            h_layout.addWidget(chk)

            if frame_count > 1:
                lbl = QLabel("Кадр:")
                h_layout.addWidget(lbl)
                spin = QSpinBox()
                spin.setRange(0, frame_count - 1)
                spin.setValue(config["frame"])
                
                def make_spin_handler(idx=i, s=spin):
                    return lambda val: self.change_layer_frame(idx, val)
                spin.valueChanged.connect(make_spin_handler())
                h_layout.addWidget(spin)

            action = QWidgetAction(menu)
            action.setDefaultWidget(widget)
            menu.addAction(action)

        menu.exec(self.btn_layers.mapToGlobal(QPoint(0, self.btn_layers.height())))

    def toggle_layer(self, index: int, enabled: bool):
        self.layer_configs[index]["enabled"] = enabled
        # Синхронизируем состояние в сам словарь item
        if index < len(self.item.get("layers", [])):
            self.item["layers"][index]["enabled"] = enabled
        self.change_state(self.item.get("state", ""))

    def change_layer_frame(self, index: int, frame: int):
        self.layer_configs[index]["frame"] = frame
        # Синхронизируем кадр в сам словарь item
        if index < len(self.item.get("layers", [])):
            self.item["layers"][index]["frame"] = frame
        self.change_state(self.item.get("state", ""))

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

    def render_single_image(self, state_name: str) -> tuple[QPixmap, int, int]:
        """Отрисовывает обычное (одиночное) изображение без слоёв."""
        sprite_path = f"{self.item.get('path', '')}/{state_name}.png"
        
        pixmap = QPixmap()
        if sprite_path and os.path.exists(sprite_path):
            pixmap.load(sprite_path)
            width, height = pixmap.width(), pixmap.height()
            pixmap = pixmap.scaled(
                256, 256,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.FastTransformation
            )
        else:
            pixmap = QPixmap(256, 256)
            pixmap.fill(QColor("#ff00ff"))
            width, height = 0, 0

        return pixmap, width, height


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


    def render_composite_image(self) -> QPixmap:
        """Собирает включенные слои на базовом холсте с учетом видимости, кадров и offset."""
        native_w = self.item.get("size", {}).get("x", 32) or 32
        native_h = self.item.get("size", {}).get("y", 32) or 32

        native_pixmap = QPixmap(native_w, native_h)
        native_pixmap.fill(Qt.GlobalColor.transparent)

        with QPainter(native_pixmap) as painter:
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)

            file_path = Path(self.item.get("file", ""))
            resources_dir = next((p for p in file_path.parents if p.name == "Resources"), None)
            base_textures_path = resources_dir / "Textures" if resources_dir else None

            if base_textures_path:
                for config in self.layer_configs:
                    if not config["enabled"]:
                        continue

                    layer = config["layer"]
                    state_name = layer.get("state")
                    sprite_rel_path = layer.get("sprite")

                    if sprite_rel_path:
                        layer_dir = base_textures_path / sprite_rel_path
                    else:
                        layer_dir = Path(self.item.get("path", ""))

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
                        
                        # Количество кадров в одной строке (колонок)
                        cols = full_pixmap.width() // native_w
                        
                        # Вычисляем колонку и строку для текущего frame_idx
                        col = frame_idx % cols
                        row = frame_idx // cols
                        
                        layer_pixmap = full_pixmap.copy(col * frame_w, row * frame_h, frame_w, frame_h)
                    else:
                        layer_pixmap = full_pixmap

                    # Применение цвета (tint)
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

        display_size = 256
        return native_pixmap.scaled(
            display_size, display_size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.FastTransformation
        )

    def change_state(self, new_state: str):
        """Обновляет состояние и выбирает режим отрисовки в зависимости от галочки."""
        self.item["state"] = new_state
        self.btn_state.setText(f"State: {new_state}")

        if self.cb_builder.isChecked():
            pixmap = self.render_composite_image()
            img_w, img_h = 256, 256
        else:
            pixmap, img_w, img_h = self.render_single_image(new_state)

        self.img_label.setPixmap(pixmap)

        # Вывод метаинформации
        sprite_path = f"{self.item.get('path', '')}/{new_state}.png"
        width = self.item.get("size", {}).get("x", 0)
        height = self.item.get("size", {}).get("y", 0)

        suffix = self.item.get("suffix")
        suffix_ftl = self.item.get("suffix_ftl")
        parent = self.item.get('parent')
        parents_chain = self.item.get('parents_chain')

        suffix_text = f"<b>Суффиксы:</b><br> - {suffix or []}<br> - {suffix_ftl or []}<br><br>" if (suffix or suffix_ftl) else "<br>"
        parent_text = f"<b>Родитель:</b> {parent}<br>" if parent else ""
        parents_text = f"<b>Цепочка родителей:</b> {parents_chain}<br>" if parents_chain else ""

        self.path_label.setText(
            f"<b>Название:</b> {self.item.get('name_ftl', '')}<br>"
            f"<b>Описание:</b> {self.item.get('desc_ftl', '')}<br>"
            f"{suffix_text}"
            f"<b>Путь:</b> {sprite_path}<br><br>"
            f"<b>Игровой размер:</b> {width}x{height}<br>"
            f"<b>Размер файла:</b> {img_w}x{img_h}<br><br>"
            f"{parent_text}"
            f"{parents_text}"
        )

    def on_yml_clicked(self):
        url = QUrl.fromLocalFile(self.item.get("file", ""))
        if url:
            QDesktopServices.openUrl(url)

    def on_rsi_clicked(self):
        url = QUrl.fromLocalFile(f"{self.item.get('path', '')}")
        if url:
            QDesktopServices.openUrl(url)

    def on_gif_clicked(self):
        json_path = Path(self.item.get("path", "")) / "meta.json"
        state_name = self.item.get("state", "")
        file_name = self.item.get("id", "")
        ToGIF.process_json_file(json_path, state_name, file_name, format="gif")
    
    def on_webp_clicked(self):
        json_path = Path(self.item.get("path", "")) / "meta.json"
        state_name = self.item.get("state", "")
        file_name = self.item.get("id", "")
        ToGIF.process_json_file(json_path, state_name, file_name, format="webp")

    def process_image_with_mode(self, mode: str):
            image_path = Path(f"{self.item.get('path', '')}/{self.item.get('state', '')}.png")
            image_name = f"{self.item.get('id', '')}-{self.item.get('state', '')}"
            
            if self.cb_builder.isChecked():
                # Гарантированно обновляем все слои в item перед передачей в ToIMAGE
                for i, config in enumerate(self.layer_configs):
                    if i < len(self.item.get("layers", [])):
                        self.item["layers"][i]["enabled"] = config["enabled"]
                        self.item["layers"][i]["frame"] = config["frame"]
                item_data = self.item
            else:
                item_data = None
    
            ToIMAGE.process_path(image_path, image_name, mode=mode, item=item_data)


# Класс окна настроек
class SettingsDialog(QDialog):
    def __init__(self, SETTINGS_FILE, path_build, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose) # Уничтожит объект при закрытии окна

        self.SETTINGS_FILE = SETTINGS_FILE
        self.path_build = path_build

        self.setWindowTitle("Настройки")
        self.resize(600, 250)

        # Компоновка элементов
        main_layout = QVBoxLayout()

        # Инициализация работы ini-файла
        self.settings = QSettings(self.SETTINGS_FILE, QSettings.Format.IniFormat)

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
        if self.path_build == Path("."):
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
            "Вы действительно хотите продолжить?\nЗагрузка может длиться вплоть до 2-х и более минут!",
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
                self.save_thread = SaveDataThread(self.path_build)
                self.save_thread.finished_signal.connect(self.on_save_finished)
                self.save_thread.finished.connect(self.save_thread.deleteLater)
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
