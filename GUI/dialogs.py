import os
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QLineEdit, QDialog,
    QGroupBox, QDialogButtonBox, QFileDialog, QMessageBox,
    QMenu, QCheckBox, QWidgetAction, QSpinBox,
    QComboBox, QProgressBar
)
from PyQt6.QtGui import QPixmap, QColor, QFont, QDesktopServices, QPainter, QIcon
from PyQt6.QtCore import Qt, QUrl, QSettings, QPoint, QTimer, pyqtSignal
import json
import img_tools.gif_tool as ToGIF
import img_tools.img_tool as ToIMAGE
from pathlib import Path
from GUI.styles import (btn_style, group_style, btn_copy_style, btn_copyright_style)
from GUI.threads import SaveDataThread
from config import SETTINGS_FILE, icon_path, settings
import copy
from logger import logger
import re

from img_tools.sprite_processor import render
from GUI.qt_image_tool import pil_to_qimage
from img_tools.parse_color import parse_color

# Модальное окно с увеличенной картинкой и кнопками
class ImageDetailDialog(QDialog):
    def __init__(self, item: dict, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.is_loading = False  # Флаг процесса загрузки
        self.item = copy.deepcopy(item)
        self.setWindowTitle(f"Просмотр: {item.get('id', 'Элемент')}")
        self.setMinimumSize(420, 520)
        
        # Предварительно вычисляем базовые пути
        self.base_textures_path = self._resolve_base_textures_path()
        self.current_sprite_path = ""

        # Инициализация конфигурации слоев с кэшированием frame_count
        self.layer_configs = []
        
        # Если в YML нет слоев (например, у пинпоинтера), создаем дефолтный слой
        layers_data = self.item.get("layers", [])
        if not layers_data:
            item_state = self.item.get("state", "default")
            layers_data = [{"state": item_state, "visible": True}]
            self.item["layers"] = layers_data

        for layer in layers_data:
            default_visible = layer.get("visible", True)
            state_name = layer.get("state", "")
            
            frame_count = self._get_layer_frame_count(layer, state_name)
            directions_count = self._get_layer_directions(layer, state_name)
            
            self.layer_configs.append({
                "layer": layer,
                "enabled": default_visible,
                "frame": layer.get("frame", 0),
                "frame_count": frame_count,
                "direction": layer.get("direction", 0),
                "directions_count": directions_count
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

        # Кнопка настройки слоев
        self.btn_layers = QPushButton("⚙ Слои")
        self.btn_layers.setStyleSheet(btn_style)
        # self.btn_layers.setVisible(False)
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

        # --- Секция информации с кнопками копирования для каждой строки ---
        info_layout = QVBoxLayout()
        info_layout.setSpacing(8)

        # Вспомогательный метод для создания строки "Текст + Кнопка копирования"
        def add_copy_row(label_title, initial_val=""):
            row_layout = QHBoxLayout()
            row_layout.setContentsMargins(0, 0, 0, 0)
            
            lbl = QLabel(f"<b>{label_title}:</b> {initial_val}")
            lbl.setWordWrap(True)
            lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            
            btn = QPushButton("📋")
            btn.setFixedSize(28, 28)
            btn.setToolTip(f"Скопировать {label_title.lower()}")
            btn.setStyleSheet(btn_copy_style)
            
            row_layout.addWidget(lbl, 1)
            row_layout.addWidget(btn)
            info_layout.addLayout(row_layout)
            return lbl, btn

        # Создаем строки с кнопками копирования для ключевых полей
        self.lbl_name, self.btn_copy_name = add_copy_row("Название", item.get('name_ftl', ''))
        self.lbl_desc, self.btn_copy_desc = add_copy_row("Описание", item.get('desc_ftl', ''))

        # Подключаем сигналы копирования
        self.btn_copy_name.clicked.connect(lambda: self.copy_field_to_clipboard(self.item.get('name_ftl', ''), self.btn_copy_name))
        self.btn_copy_desc.clicked.connect(lambda: self.copy_field_to_clipboard(self.item.get('desc_ftl', ''), self.btn_copy_desc))

        # Дополнительная метаинформация (размеры, суффиксы, родители)
        self.path_label = QLabel()
        self.path_label.setWordWrap(True)
        self.path_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse | 
            Qt.TextInteractionFlag.LinksAccessibleByMouse
        )
        # НЕ включаем setOpenExternalLinks(True), будем обрабатывать вручную через сигнал
        self.path_label.linkActivated.connect(self.handle_link_clicked)
        info_layout.addWidget(self.path_label)

        # --- СВОРАЧИВАЕМАЯ СЕКЦИЯ COPYRIGHT ---
        self.btn_toggle_copyright = QPushButton("▶ Copyright и лицензия")
        self.btn_toggle_copyright.setCheckable(True)
        self.btn_toggle_copyright.setChecked(False)
        self.btn_toggle_copyright.setStyleSheet(btn_copyright_style)
        self.btn_toggle_copyright.toggled.connect(self.on_copyright_toggled)
        info_layout.addWidget(self.btn_toggle_copyright)

        # Контейнер для содержимого copyright, чтобы делать его скрытым/видимым
        self.copyright_container = QWidget()
        copyright_layout = QVBoxLayout(self.copyright_container)
        copyright_layout.setContentsMargins(15, 0, 0, 0) # Небольшой отступ слева для красоты

        self.lbl_copyright = QLabel()
        self.lbl_copyright.setWordWrap(True)
        self.lbl_copyright.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse | 
            Qt.TextInteractionFlag.LinksAccessibleByMouse
        )
        self.lbl_copyright.linkActivated.connect(self.handle_link_clicked)
        copyright_layout.addWidget(self.lbl_copyright)

        self.copyright_container.setVisible(False) # Скрыто по умолчанию
        info_layout.addWidget(self.copyright_container)
        # -------------------------------------

        layout.addLayout(info_layout)

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

        # Группа кнопок экспорта
        group_btns = QGroupBox("Кнопки")
        group_btns.setStyleSheet(group_style)
        group_btns_layout = QHBoxLayout()

        btn_img = QPushButton("IMG")
        btn_gif = QPushButton("GIF")
        btn_webp = QPushButton("WebP")
        # btn_apng = QPushButton("APNG") # APNG работает, но я незнаю зачем он нам. Пока-что будет закомментирован
        btn_img.setStyleSheet(btn_style)
        btn_gif.setStyleSheet(btn_style)
        btn_webp.setStyleSheet(btn_style)
        # btn_apng.setStyleSheet(btn_style)

        img_menu = QMenu(self)
        img_menu.addAction("1. Original", lambda: self.process_image_with_mode("Original"))
        img_menu.addAction("2. Resize", lambda: self.process_image_with_mode("Resize"))

        # Ссылки на направления
        self.action_south = img_menu.addAction("3.1 South (лицо)", lambda: self.process_image_with_mode("South"))
        self.action_north = img_menu.addAction("3.2 North (зад)", lambda: self.process_image_with_mode("North"))
        self.action_east = img_menu.addAction("3.3 East (правый профиль)", lambda: self.process_image_with_mode("East"))
        self.action_west = img_menu.addAction("3.4 West (левый профиль)", lambda: self.process_image_with_mode("West"))
        
        btn_img.setMenu(img_menu)

        btn_yml.clicked.connect(self.on_yml_clicked)
        btn_rsi.clicked.connect(self.on_rsi_clicked)
        btn_gif.clicked.connect(self.on_gif_clicked)
        btn_webp.clicked.connect(self.on_webp_clicked)
        # btn_apng.clicked.connect(self.on_apng_clicked)

        group_btns_layout.addWidget(btn_img)
        group_btns_layout.addWidget(btn_gif)
        group_btns_layout.addWidget(btn_webp)
        # group_btns_layout.addWidget(btn_apng)
        group_btns.setLayout(group_btns_layout)

        # Главный слой кнопок
        main_btn_layout = QHBoxLayout()
        main_btn_layout.addWidget(group_links)
        main_btn_layout.addWidget(group_btns)

        layout.addLayout(main_btn_layout)

        # Включение сборщика по умолчанию
        self.cb_builder.setChecked(True)

    def copy_field_to_clipboard(self, text: str, button: QPushButton):
        """Копирует переданный текст в буфер обмена с анимацией успешного отклика."""
        clipboard = QApplication.clipboard()
        clipboard.setText(text)
        
        # Визуальный отклик
        original_text = button.text()
        button.setText("✓")
        button.setEnabled(False)
        
        QTimer.singleShot(1200, lambda: [button.setText(original_text), button.setEnabled(True)])

    def on_copyright_toggled(self, checked: bool):
        """Сворачивает/разворачивает секцию Copyright по клику на стрелочку."""
        self.copyright_container.setVisible(checked)
        if checked:
            self.btn_toggle_copyright.setText("▼ Copyright и лицензия")
        else:
            self.btn_toggle_copyright.setText("▶ Copyright и лицензия")

        self.adjustSize()

    def on_builder_toggled(self, checked: bool):
        """Поведение при включении/выключении режима Сборщик."""
        # self.btn_layers.setVisible(checked)
        self.btn_layers.setEnabled(checked)

        hide_actions = checked
        if hasattr(self, 'action_south'):
            self.action_south.setVisible(not hide_actions)
            self.action_north.setVisible(not hide_actions)
            self.action_east.setVisible(not hide_actions)
            self.action_west.setVisible(not hide_actions)

        self.change_state(self.item.get("state", ""))

    def _resolve_base_textures_path(self) -> Path | None:
        """Централизованный поиск папки текстур."""
        file_path = Path(self.item.get("file", ""))
        resources_dir = next((p for p in file_path.parents if p.name == "Resources"), None)
        return resources_dir / "Textures" if resources_dir else None

    def _get_layer_frame_count(self, layer: dict, state_name: str) -> int:
        """Определяет количество кадров слоя из meta.json."""
        if not self.base_textures_path:
            return 1
            
        sprite_rel_path = layer.get("sprite")
        layer_dir = self.base_textures_path / sprite_rel_path if sprite_rel_path else Path(self.item.get("path", ""))
        item_state = self.item.get("state", "default")
        st_name = state_name or item_state
        
        meta_path = layer_dir / "meta.json"
        f_count = 1
        
        if meta_path.exists():
            try:
                with open(meta_path, "r", encoding="utf-8-sig") as f:
                    meta_data = json.load(f)
                    for st in meta_data.get("states", []):
                        if st.get("name") == st_name:
                            if "delays" in st:
                                delays_data = st["delays"]
                                if isinstance(delays_data, list) and len(delays_data) > 0:
                                    # Если это двумерный массив (список списков), 
                                    # то количество кадров — это длина одного направления (первого вложенного списка)
                                    if isinstance(delays_data[0], list):
                                        f_count = len(delays_data[0])
                                    else:
                                        f_count = len(delays_data)
                                else:
                                    f_count = 1
                            else:
                                f_count = st.get("frameCount", 1)
                            break
            except Exception as e:
                logger.warning(f"Не удалось прочитать {meta_path}: {e}")

        if f_count == 1:
            layer_file_path = layer_dir / f"{st_name}.png"
            if not layer_file_path.exists() or layer_file_path.is_dir():
                layer_file_path = layer_dir / "default.png"
            if layer_file_path.exists() and not layer_file_path.is_dir():
                pix = QPixmap(str(layer_file_path))
                if not pix.isNull():
                    native_w = self.item.get("size", {}).get("x", 32) or 32
                    native_h = self.item.get("size", {}).get("y", 32) or 32
                    fw, fh = pix.width(), pix.height()
                    if (fw > native_w or fh > native_h) and (fw % native_w == 0) and (fh % native_h == 0):
                        f_count = (fw // native_w) * (fh // native_h)

        return f_count

    def _get_layer_directions(self, layer: dict, state_name: str) -> int:
        """Определяет количество направлений (directions) слоя из meta.json."""
        if not self.base_textures_path:
            return 1
            
        sprite_rel_path = layer.get("sprite")
        layer_dir = self.base_textures_path / sprite_rel_path if sprite_rel_path else Path(self.item.get("path", ""))
        item_state = self.item.get("state", "default")
        st_name = state_name or item_state
        
        meta_path = layer_dir / "meta.json"
        if meta_path.exists():
            try:
                with open(meta_path, "r", encoding="utf-8-sig") as f:
                    meta_data = json.load(f)
                    for st in meta_data.get("states", []):
                        if st.get("name") == st_name:
                            return st.get("directions", 1)
            except Exception as e:
                logger.warning(f"Не удалось прочитать направления из {meta_path}: {e}")
        return 1

    def show_layers_menu(self):
        """Выпадающее меню слоев с кнопками управления и добавления/удаления."""
        menu = QMenu(self)
        
        # --- СЕКЦИЯ ГЛОБАЛЬНОГО УПРАВЛЕНИЯ (Применить сторону ко всем слоям) ---
        global_dir_widget = QWidget()
        global_dir_layout = QHBoxLayout(global_dir_widget)
        global_dir_layout.setContentsMargins(8, 6, 8, 6)
        
        global_dir_layout.addWidget(QLabel("<b>Все слои (Сторона):</b>"))
        global_dir_combo = QComboBox()
        
        # Определяем максимальное количество направлений среди всех слоев для списка
        max_directions = max([config.get("directions_count", 1) for config in self.layer_configs], default=4)
        
        if max_directions == 4:
            global_dir_names = ["South (лицо)", "North (зад)", "East (правый профиль)", "West (левый профиль)"]
        elif max_directions == 8:
            global_dir_names = ["South (лицо)", "South-East", "East (правый профиль)", "North-East", "North (зад)", "North-West", "West (левый профиль)", "South-West"]
        else:
            global_dir_names = [str(d) for d in range(max_directions)]
            
        global_dir_combo.addItems(global_dir_names[:max_directions])
        global_dir_layout.addWidget(global_dir_combo)
        
        btn_apply_all = QPushButton("Применить")
        btn_apply_all.setStyleSheet(btn_style)
        btn_apply_all.clicked.connect(lambda: [
            menu.close(),
            self.apply_direction_to_all_layers(global_dir_combo.currentIndex())
        ])
        global_dir_layout.addWidget(btn_apply_all)
        
        global_action = QWidgetAction(menu)
        global_action.setDefaultWidget(global_dir_widget)
        menu.addAction(global_action)
        menu.addSeparator()

        # --- СЕКЦИЯ ОТДЕЛЬНЫХ СЛОЕВ ---
        for i, config in enumerate(self.layer_configs):
            layer = config["layer"]
            state_name = layer.get("state", "")
            maps = layer.get("map", [f"Слой {i+1}"])
            layer_name = str(maps[0]).split(".")[-1] if maps else f"Слой {i+1}"
            frame_count = config["frame_count"]
            directions_count = config.get("directions_count", 1)

            widget = QWidget()
            h_layout = QHBoxLayout(widget)
            h_layout.setContentsMargins(8, 4, 8, 4)

            chk = QCheckBox(f"{layer_name} ({state_name})")
            chk.setChecked(config["enabled"])
            chk.toggled.connect(lambda checked, idx=i: self.toggle_layer(idx, checked))
            h_layout.addWidget(chk)

            # Выбор стороны / направления для конкретного слоя
            if directions_count > 1:
                h_layout.addWidget(QLabel("Сторона:"))
                dir_combo = QComboBox()
                
                if directions_count == 4:
                    dir_names = ["South (лицо)", "North (зад)", "East (правый профиль)", "West (левый профиль)"]
                elif directions_count == 8:
                    dir_names = ["South (лицо)", "South-East", "East (правый профиль)", "North-East", "North (зад)", "North-West", "West (левый профиль)", "South-West"]
                else:
                    dir_names = [str(d) for d in range(directions_count)]
                    
                dir_combo.addItems(dir_names[:directions_count])
                dir_combo.setCurrentIndex(config.get("direction", 0))
                dir_combo.currentIndexChanged.connect(lambda val, idx=i: self.change_layer_direction(idx, val))
                h_layout.addWidget(dir_combo)

            # Выбор кадра анимации
            if frame_count > 1:
                h_layout.addWidget(QLabel("Кадр:"))
                spin = QSpinBox()
                spin.setRange(0, frame_count - 1)
                spin.setValue(config["frame"])
                spin.valueChanged.connect(lambda val, idx=i: self.change_layer_frame(idx, val))
                h_layout.addWidget(spin)

            # Кнопка удаления слоя
            if len(self.layer_configs) > 1:
                btn_del = QPushButton("❌")
                btn_del.setFixedSize(24, 24)
                btn_del.setToolTip("Удалить слой")
                btn_del.setStyleSheet(btn_copy_style)
                btn_del.clicked.connect(lambda _, idx=i: self.delete_layer(idx, menu))
                h_layout.addWidget(btn_del)

            action = QWidgetAction(menu)
            action.setDefaultWidget(widget)
            menu.addAction(action)

        # --- СЕКЦИЯ ДОБАВЛЕНИЯ НОВОГО СЛОЯ ---
        menu.addSeparator()
        add_widget = QWidget()
        add_layout = QHBoxLayout(add_widget)
        add_layout.setContentsMargins(8, 4, 8, 4)

        combo_states = QComboBox()
        available_states = self.item.get("states", [self.item.get("state", "default")])
        combo_states.addItems(available_states)
        add_layout.addWidget(combo_states)

        btn_add = QPushButton("➕ Добавить слой")
        btn_add.setStyleSheet(btn_style)
        btn_add.clicked.connect(lambda: [
            menu.close(), 
            self.add_layer(combo_states.currentText())
        ])
        add_layout.addWidget(btn_add)

        add_action = QWidgetAction(menu)
        add_action.setDefaultWidget(add_widget)
        menu.addAction(add_action)

        menu.exec(self.btn_layers.mapToGlobal(QPoint(0, self.btn_layers.height())))

    def add_layer(self, state_name=None):
        """Добавляет новый дефолтный слой."""
        if not state_name:
            return

        new_layer = {
            "state": state_name,
            "visible": True
        }
        
        frame_count = self._get_layer_frame_count(new_layer, state_name)
        directions_count = self._get_layer_directions(new_layer, state_name) # <-- Вычисляем направления
        
        self.layer_configs.append({
            "layer": new_layer,
            "enabled": True,
            "frame": 0,
            "frame_count": frame_count,
            "direction": 0,                      # <-- На всякий случай добавляем direction
            "directions_count": directions_count # <-- Добавляем недостающий ключ
        })
        
        if "layers" not in self.item or not isinstance(self.item["layers"], list):
            self.item["layers"] = []
        self.item["layers"].append(new_layer)
        
        self.change_state(self.item.get("state", ""))

    def delete_layer(self, index: int, menu: QMenu):
        """Удаляет слой по индексу (с ограничением: минимум 1 слой)."""
        if len(self.layer_configs) <= 1:
            QMessageBox.warning(self, "Внимание", "Должен остаться как минимум 1 слой!")
            return
        
        menu.close()
        
        # Удаляем из локальных конфигураций и данных предмета
        self.layer_configs.pop(index)
        layers = self.item.get("layers", [])
        if index < len(layers):
            layers.pop(index)
            self.item["layers"] = layers
            
        self.change_state(self.item.get("state", ""))

    def apply_direction_to_all_layers(self, direction_index):
        """Применяет выбранный индекс направления ко всем существующим слоям."""
        for i, config in enumerate(self.layer_configs):
            directions_count = config.get("directions_count", 1)
            
            # Проверяем, поддерживает ли конкретный слой выбранное направление (например, если у слоя всего 1 или 4 направления)
            if direction_index < directions_count:
                config["direction"] = direction_index
                # Если у вас есть метод обновления отдельного слоя, можно вызвать его:
                # self.change_layer_direction(i, direction_index, update_ui=False)

        # Вызовите ваш метод перерисовки сцены/холста, чтобы изменения отобразились сразу
        self.change_state(self.item.get("state", ""))

    def toggle_layer(self, index: int, enabled: bool):
        self.layer_configs[index]["enabled"] = enabled
        if index < len(self.item.get("layers", [])):
            self.item["layers"][index]["enabled"] = enabled
        self.change_state(self.item.get("state", ""))

    def change_layer_frame(self, index: int, frame: int):
        self.layer_configs[index]["frame"] = frame
        if index < len(self.item.get("layers", [])):
            self.item["layers"][index]["frame"] = frame
        self.change_state(self.item.get("state", ""))

    def change_layer_direction(self, index: int, direction: int):
        """Изменяет выбранное направление (сторону) для слоя."""
        self.layer_configs[index]["direction"] = direction
        if index < len(self.item.get("layers", [])):
            self.item["layers"][index]["direction"] = direction
        self.change_state(self.item.get("state", ""))

    def apply_layer_color(self, pixmap: QPixmap, color_hex: str) -> QPixmap:
        if not color_hex or pixmap.isNull():
            return pixmap

        result = QPixmap(pixmap.size())
        result.fill(Qt.GlobalColor.transparent)

        painter = QPainter(result)
        painter.drawPixmap(0, 0, pixmap)
        
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Multiply)
        
        # Получаем честные RGBA компоненты из любого формата цвета
        r, g, b, a = parse_color(color_hex)
        painter.fillRect(result.rect(), QColor(r, g, b, a))
        
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
        painter.drawPixmap(0, 0, pixmap)
        
        painter.end()
        return result

    def render_single_image(self, state_name: str) -> tuple[QPixmap, int, int]:
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

    def render_composite_image(self) -> QPixmap:
        target_item = getattr(self, 'item', {})
        overrides = {"layer_configs": getattr(self, 'layer_configs', None)}
        
        # Исправлено: передаём корректные параметры direction и frame (из первого слоя или дефолтные 0)
        default_dir = self.layer_configs[0].get("direction", 0) if self.layer_configs else 0
        default_frame = self.layer_configs[0].get("frame", 0) if self.layer_configs else 0
        
        pil_img = render(target_item, overrides=overrides, direction=default_dir, frame=default_frame)
        qimg = pil_to_qimage(pil_img)
        pixmap = QPixmap.fromImage(qimg)
        
        display_size = 256
        return pixmap.scaled(
            display_size, display_size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.FastTransformation
        )

    def change_state(self, new_state: str):
        """Обновляет состояние и перерисовывает данные."""
        self.item["state"] = new_state
        self.btn_state.setText(f"State: {new_state}")

        if self.cb_builder.isChecked():
            pixmap = self.render_composite_image()
            img_w, img_h = 256, 256
        else:
            pixmap, img_w, img_h = self.render_single_image(new_state)

        self.img_label.setPixmap(pixmap)

        # ---- РЕЖИМ СТРИМЕРА ----
        # Читаем состояние галочки из настроек
        settings = QSettings(str(SETTINGS_FILE), QSettings.Format.IniFormat)
        streamer_mode = settings.value("streamer_mode", False, type=bool)

        # Вывод путей и метаданных
        raw_sprite_path = f"{self.item.get('path', '')}/{new_state}.png"

        if streamer_mode:
            # Заменяем имя пользователя в пути на ~
            home_dir = os.path.expanduser("~")
            sprite_path = raw_sprite_path.replace(home_dir, "~")
        else:
            sprite_path = raw_sprite_path
        # ------------------------

        width = self.item.get("size", {}).get("x", 0)
        height = self.item.get("size", {}).get("y", 0)

        suffix = self.item.get("suffix")
        suffix_ftl = self.item.get("suffix_ftl")
        parent = self.item.get('parent')
        parents_chain = self.item.get('parents_chain')

        suffix_text = f"<b>Суффиксы:</b><br> - {suffix or []}<br> - {suffix_ftl or []}<br><br>" if (suffix or suffix_ftl) else ""
        parent_text = f"<b>Родитель:</b> {parent}<br>" if parent else ""
        parents_text = f"<b>Цепочка родителей:</b> {parents_chain}<br>" if parents_chain else ""

        # Основной блок информации (без копирайта)
        self.path_label.setText(
            f"{suffix_text}"
            f"<b>Путь:</b> {sprite_path}<br><br>"
            f"<b>Игровой размер:</b> {width}x{height}<br>"
            f"<b>Размер файла:</b> {img_w}x{img_h}<br><br>"
            f"{parent_text}"
            f"{parents_text}"
        )

        # Заполняем скрываемый блок copyright и лицензией
        copyright_data = self.item.get("copyright", "")
        license_data = self.item.get("license", "")

        def make_links_html(text):
            url_pattern = re.compile(r'((https?://[^/]+/[^/]+)/([^/\s]+)([^\s]*))')
            return url_pattern.sub(r'<a href="\1">Github/\3</a>', text)

        formatted_copyright = make_links_html(copyright_data)

        self.lbl_copyright.setText(
            f"<b>Copyright:</b> {formatted_copyright}<br><br>"
            f"<b>Лицензия:</b> {license_data}"
        )

    def on_yml_clicked(self):
        url = QUrl.fromLocalFile(self.item.get("file", ""))
        if url:
            QDesktopServices.openUrl(url)

    def on_rsi_clicked(self):
        url = QUrl.fromLocalFile(f"{self.item.get('path', '')}")
        if url:
            QDesktopServices.openUrl(url)

    def handle_link_clicked(self, url_str: str):
        """Обработчик клика по любой ссылке внутри QLabel"""
        logger.info(f"Кликнули на ссылку: {url_str}")
        
        # Преобразуем строку в QUrl и открываем стандартным способом
        url = QUrl(url_str)
        if url.isValid():
            QDesktopServices.openUrl(url)

    def _sync_layer_configs_to_item(self):
        """Синхронизирует текущие конфигурации слоев (direction, frame, enabled) в self.item["layers"] перед экспортом."""
        if self.cb_builder.isChecked():
            for i, config in enumerate(self.layer_configs):
                if i < len(self.item.get("layers", [])):
                    self.item["layers"][i]["enabled"] = config["enabled"]
                    self.item["layers"][i]["frame"] = config["frame"]
                    self.item["layers"][i]["direction"] = config.get("direction", 0)
            return self.item
        return None

    def on_gif_clicked(self):
        json_path = Path(self.item.get("path", "")) / "meta.json"
        state_name = self.item.get("state", "")
        file_name = self.item.get("id", "")
        item_data = self._sync_layer_configs_to_item()
        
        ToGIF.process_json_file(json_path, state_name, file_name, format="gif", item=item_data, layer_configs=self.layer_configs)
    
    def on_webp_clicked(self):
        json_path = Path(self.item.get("path", "")) / "meta.json"
        state_name = self.item.get("state", "")
        file_name = self.item.get("id", "")
        item_data = self._sync_layer_configs_to_item()

        ToGIF.process_json_file(json_path, state_name, file_name, format="webp", item=item_data, layer_configs=self.layer_configs)

    def on_apng_clicked(self):
        json_path = Path(self.item.get("path", "")) / "meta.json"
        state_name = self.item.get("state", "")
        file_name = self.item.get("id", "")
        item_data = self._sync_layer_configs_to_item()

        ToGIF.process_json_file(json_path, state_name, file_name, format="apng", item=item_data, layer_configs=self.layer_configs)

    def process_image_with_mode(self, mode: str):
        image_path = Path(f"{self.item.get('path', '')}/{self.item.get('state', '')}.png")
        image_name = f"{self.item.get('id', '')}-{self.item.get('state', '')}"
        item_data = self._sync_layer_configs_to_item()
    
        ToIMAGE.process_path(image_path, image_name, mode=mode, item=item_data)


# Класс окна настроек
class SettingsDialog(QDialog):
    # Сигнал для уведомления главного окна об успешной пересборке данных
    data_reloaded = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose) # Уничтожит объект при закрытии окна

        # Инициализируем флаг загрузки заранее, чтобы методы проверки не падали
        self.is_loading = False

        self.setWindowTitle("Настройки")
        self.setFixedSize(800, 650) # Немного увеличили высоту под прогресс-бар
        self.setWindowIcon(QIcon(icon_path))

        # Компоновка элементов
        main_layout = QVBoxLayout()

        # Инициализация работы ini-файла
        self.settings = QSettings(str(SETTINGS_FILE), QSettings.Format.IniFormat)

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

        saves_label = QLabel("""
Путь для сохранения файлов:<br>
Точка (.) = та же папка где находится главный файл
        """)

        group_saves_layout.addWidget(saves_label)

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

        build_label = QLabel("""
Путь сборки<br><br>
Впишите путь до сборки (space_station).<br>
Для работы программы необходимы папки Locale, Prototypes, Textures, которые должны находиться в Resources!
        """)

        group_build_layout.addWidget(build_label)

        btn_line_build_layout.addWidget(self.path_build_input)
        btn_line_build_layout.addWidget(browse_build_btn)
        group_build_layout.addLayout(btn_line_build_layout)
        group_build.setLayout(group_build_layout)

        # Подключаем нажатие кнопки к вызову диалога файловой системы
        browse_build_btn.clicked.connect(
            lambda: self.select_directory(self.path_build_input)
        )

        main_layout.addWidget(group_build)

        # Блок режима стримера / конфиденциальности
        group_privacy = QGroupBox("Приватность")
        group_privacy.setStyleSheet(group_style)
        group_privacy_layout = QVBoxLayout()

        self.cb_streamer_mode = QCheckBox("Режим стримера (скрывать пути и личные данные)")
        group_privacy_layout.addWidget(self.cb_streamer_mode)
        group_privacy.setLayout(group_privacy_layout)

        main_layout.addWidget(group_privacy)

        # Перезагрузка данных
        group_reloads = QGroupBox("Перезагрузить данные")
        group_reloads.setStyleSheet(group_style)
        group_reloads_layout = QVBoxLayout()

        # Обновленный текст подсказки (без требования перезапуска приложения)
        reload_label = QLabel("""
Если вы поменяли путь сборки или впервые его установили:<br>
- Нажмите кнопку "OK", чтобы сохранить настройки.<br>
- После этого нажмите кнопку "ПЕРЕЗАГРУЗИТЬ", и данные обновятся автоматически без перезапуска программы!
        """)

        self.btn_reload = QPushButton("ПЕРЕЗАГРУЗИТЬ")
        self.btn_reload.setStyleSheet(btn_style)

        group_reloads_layout.addWidget(reload_label)
        group_reloads_layout.addWidget(self.btn_reload)
        group_reloads.setLayout(group_reloads_layout)

        self.btn_reload.clicked.connect(self.confirm_action)

        main_layout.addWidget(group_reloads)

        # Добавляем прогресс-бар (по умолчанию скрыт)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0) # Анимация "бегущей строки" ожидания
        self.progress_bar.setVisible(False)
        main_layout.addWidget(self.progress_bar)

        # ----------------------------------------------------
        # 3. Кнопки сохранения / отмены
        # ----------------------------------------------------
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.on_accept_clicked)
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
        saved_path_save = self.settings.value("path_saves", "", type=str)
        saved_path_build = self.settings.value("path_build", ".", type=str)
        streamer_mode = self.settings.value("streamer_mode", False, type=bool) # Читаем настройку

        # Устанавливаем пути в QLineEdit
        self.path_save_input.setText(saved_path_save)
        self.path_build_input.setText(saved_path_build)
        self.cb_streamer_mode.setChecked(streamer_mode) # Устанавливаем галочку

    def on_accept_clicked(self):
        self.save_settings()
        self.accept()

    def save_settings(self):
        """Сохранение данных из виджетов в settings.ini."""
        self.settings.setValue("path_build", self.path_build_input.text())
        self.settings.setValue("path_saves", self.path_save_input.text())
        self.settings.setValue("streamer_mode", self.cb_streamer_mode.isChecked()) # Сохраняем галочку

    def confirm_action(self):
        # Используем runtime-объект настроек
        if settings.path_build == Path("."):
            logger.info("Отсутствует путь билда!")
            QMessageBox.information(
                self,
                "Уведомление",
                "Отсутствует путь билда.\nУкажите путь в настройках, чтобы программа могла получить данные!"
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
            self.is_loading = True
            self.btn_reload.setText("🔄 ЗАГРУЖАЕТСЯ 🔄")
            self.btn_reload.setEnabled(False)
            
            # Показываем прогресс-бар и блокируем интерфейс
            self.progress_bar.setVisible(True)
            self.set_ui_locked(True)

            QApplication.processEvents()

            try:
                self.save_thread = SaveDataThread()
                self.save_thread.finished_signal.connect(self.on_save_finished)
                self.save_thread.failed_signal.connect(self.on_save_failed)  # Подключаем обработчик ошибок
                self.save_thread.finished.connect(self.save_thread.deleteLater)
                self.save_thread.start()
            except Exception as e:
                self.is_loading = False
                self.progress_bar.setVisible(False)
                self.set_ui_locked(False)
                logger.error(f"Не удалось запустить SaveDataThread: {e}")
                QMessageBox.critical(self, "Error!", f"{e}")

    def on_save_finished(self):
        self.is_loading = False
        self.progress_bar.setVisible(False)
        self.set_ui_locked(False)
        self.btn_reload.setText("ПЕРЕЗАГРУЗИТЬ")
        self.btn_reload.setEnabled(True)

        QMessageBox.information(
            self, 
            "Готово!", 
            "Перезагрузка данных успешно завершена!"
        )
        self.data_reloaded.emit()

    def on_save_failed(self, error_message):
        """Срабатывает, если в потоке сохранения произошла ошибка (например, SQLite недоступен)"""
        self.is_loading = False
        self.progress_bar.setVisible(False)
        self.set_ui_locked(False)
        self.btn_reload.setText("ПЕРЕЗАГРУЗИТЬ")
        self.btn_reload.setEnabled(True)

        logger.error(f"Ошибка в потоке сохранения данных: {error_message}")
        QMessageBox.critical(
            self,
            "Ошибка!",
            f"Не удалось выполнить перезагрузку данных:\n{error_message}"
        )

    def set_ui_locked(self, locked):
        """Блокирует/разблокирует интерфейс на время загрузки"""
        button_box = self.findChild(QDialogButtonBox)
        if button_box:
            button_box.setEnabled(not locked)

    def reject(self):
        """Защита от закрытия окна по нажатию Esc во время работы потока"""
        if self.is_loading:
            QMessageBox.warning(
                self,
                "Внимание",
                "Идет процесс перезагрузки данных!\nПожалуйста, дождитесь окончания процесса."
            )
            return
        super().reject()

    def closeEvent(self, event):
        """Защита от закрытия окна крестиком во время работы потока"""
        if self.is_loading:
            QMessageBox.warning(
                self,
                "Внимание",
                "Идет процесс перезагрузки данных!\nПожалуйста, дождитесь окончания процесса."
            )
            event.ignore()  # Запрещаем закрывать окно
        else:
            event.accept()
