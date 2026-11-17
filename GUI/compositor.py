import os
from PyQt6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QListWidget, QListWidgetItem,
    QLineEdit, QSplitter, QFileDialog, QMessageBox,
    QGroupBox, QComboBox, QCheckBox, QColorDialog,
    QSpinBox
)
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QPixmap, QColor, QIcon

from PIL import Image
from img_tools.sprite_processor import render
from GUI.qt_image_tool import pil_to_qimage
from GUI.animator import AnimationBuilderDialog

_icon_cache = {}

def item_icon(item: dict, size: int = 48) -> QIcon:
    """Превью предмета, собранное из всех его слоёв (с кэшем)."""
    key = (item.get("id"), size)
    if key not in _icon_cache:
        pil_img = render(item)
        pix = QPixmap.fromImage(pil_to_qimage(pil_img)).scaled(
            size, size, Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.FastTransformation)
        _icon_cache[key] = QIcon(pix)
    return _icon_cache[key]


def build_layer_configs(layer_data: dict) -> list:
    """Конфиги подслоёв предмета: свои state/color сохраняются, как в ImageDetailDialog."""
    item = layer_data["item"]
    state = layer_data["state"]
    color = layer_data.get("custom_color") or ""
    force_state = layer_data.get("force_state", False)
    frame = layer_data.get("frame", 0)
    direction = layer_data.get("direction", 0)

    sub_layers = item.get("layers", [])
    if not sub_layers:
        return [{
            "enabled": True,
            "layer": {"state": state, "sprite": None, **({"color": color} if color else {})},
            "frame": frame,
            "direction": direction,
        }]

    configs = []
    for l in sub_layers:
        sub_l = dict(l)
        if force_state or not sub_l.get("state"):
            sub_l["state"] = state
        if color:                      # красим только если пользователь выбрал цвет
            sub_l["color"] = color
        configs.append({
            "enabled": sub_l.get("visible", True) and sub_l.get("enabled", True),
            "layer": sub_l,
            "frame": frame,
            "direction": direction,
        })
    return configs

class LayerSelectorDialog(QDialog):
    """Окно выбора элемента из базы данных."""
    def __init__(self, items: list, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Выбор элемента для композитора")
        self.setMinimumSize(500, 600)
        self.selected_item = None
        self.items = items

        layout = QVBoxLayout(self)

        # Строка поиска
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("🔍 Поиск по названию или ID...")
        self.search_input.textChanged.connect(self.filter_list)
        layout.addWidget(self.search_input)

        # Список элементов
        self.list_widget = QListWidget()
        self.list_widget.itemDoubleClicked.connect(self.on_item_double_clicked)
        self.list_widget.setIconSize(QSize(48, 48))
        layout.addWidget(self.list_widget)

        # Кнопки
        btn_layout = QHBoxLayout()
        self.btn_select = QPushButton("Выбрать")
        self.btn_select.clicked.connect(self.accept_selection)
        btn_cancel = QPushButton("Отмена")
        btn_cancel.clicked.connect(self.reject)

        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_select)
        btn_layout.addWidget(btn_cancel)
        layout.addLayout(btn_layout)

        self.populate_list(self.items)

    def populate_list(self, items_to_show):
        self.list_widget.clear()
        for item in items_to_show[:100]:  # Ограничение для производительности
            item_id = item.get("id", "Без ID")
            name_ftl = item.get("name_ftl", "")
            display_text = f"{item_id}" + (f" ({name_ftl})" if name_ftl else "")

            list_item = QListWidgetItem(display_text)
            list_item.setIcon(item_icon(item))
            list_item.setData(Qt.ItemDataRole.UserRole, item)
            self.list_widget.addItem(list_item)

    def filter_list(self, text: str):
        query = text.strip().lower()
        if not query:
            filtered = self.items
        else:
            filtered = [
                item for item in self.items
                if query in str(item.get("id", "")).lower()
                or query in str(item.get("name_ftl", "")).lower()
                or query in os.path.basename(item.get("path", "")).lower()
            ]
        self.populate_list(filtered)

    def on_item_double_clicked(self, list_item):
        self.selected_item = list_item.data(Qt.ItemDataRole.UserRole)
        self.accept()

    def accept_selection(self):
        current_item = self.list_widget.currentItem()
        if current_item:
            self.selected_item = current_item.data(Qt.ItemDataRole.UserRole)
            self.accept()


class SceneBuilderDialog(QDialog):
    """Главное окно сборщика сцены с динамическим холстом и настройкой направления."""
    def __init__(self, items: list, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Сборщик изображений и сцен (Scene Builder)")
        self.setMinimumSize(950, 750)
        self.items = items

        # Список слоев сцены
        self.scene_layers = []
        self.current_rendered_canvas = QPixmap()

        self.current_pil_canvas = Image.new("RGBA", (32, 32))
        self.anim_dialog = None

        layout = QHBoxLayout(self)
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # --- Левая панель: Предпросмотр холста ---
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)

        self.canvas_label = QLabel()
        self.canvas_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.canvas_label.setStyleSheet("background-color: #222222; border-radius: 8px;")
        self.canvas_label.setMinimumSize(400, 400)
        left_layout.addWidget(self.canvas_label)

        btn_export = QPushButton("💾 Экспортировать итоговую картинку")
        btn_export.setStyleSheet("background-color: #1abc9c; color: white; font-weight: bold; padding: 8px;")
        btn_export.clicked.connect(self.export_scene)
        left_layout.addWidget(btn_export)

        btn_to_anim = QPushButton("🎞 Кадр в анимацию")
        btn_to_anim.clicked.connect(self.add_frame_to_animation)
        left_layout.addWidget(btn_to_anim)

        btn_open_anim = QPushButton("🎬 Окно анимаций")
        btn_open_anim.clicked.connect(self.open_animator)
        left_layout.addWidget(btn_open_anim)

        splitter.addWidget(left_widget)

        # --- Правая панель: Управление слоями сцены ---
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)

        right_layout.addWidget(QLabel("<b>Слои сцены (снизу вверх):</b>"))

        self.layers_list_widget = QListWidget()
        self.layers_list_widget.currentRowChanged.connect(self.on_layer_row_changed)
        right_layout.addWidget(self.layers_list_widget)

        btn_add_layer = QPushButton("➕ Добавить элемент из поиска")
        btn_add_layer.clicked.connect(self.add_layer_from_search)
        right_layout.addWidget(btn_add_layer)

        h_btn_layout = QHBoxLayout()
        btn_move_up = QPushButton("⬆ Вверх")
        btn_move_down = QPushButton("⬇ Вниз")
        btn_delete = QPushButton("🗑 Удалить")

        btn_move_up.clicked.connect(self.move_layer_up)
        btn_move_down.clicked.connect(self.move_layer_down)
        btn_delete.clicked.connect(self.delete_layer)

        h_btn_layout.addWidget(btn_move_up)
        h_btn_layout.addWidget(btn_move_down)
        h_btn_layout.addWidget(btn_delete)
        right_layout.addLayout(h_btn_layout)

        # --- Панель настроек выбранного слоя ---
        self.settings_group = QGroupBox("⚙️ Настройки выбранного слоя")
        settings_layout = QVBoxLayout(self.settings_group)

        # Состояние
        state_layout = QHBoxLayout()
        state_layout.addWidget(QLabel("Состояние:"))
        self.state_combo = QComboBox()
        self.state_combo.currentIndexChanged.connect(self.on_state_changed)
        state_layout.addWidget(self.state_combo)
        settings_layout.addLayout(state_layout)

        # Направление (Direction)
        dir_layout = QHBoxLayout()
        dir_layout.addWidget(QLabel("Направление (Direction):"))
        self.dir_spin = QSpinBox()
        self.dir_spin.setRange(0, 7)  # Стандартный диапазон направлений (0-7 или 0-3)
        self.dir_spin.valueChanged.connect(self.on_direction_changed)
        dir_layout.addWidget(self.dir_spin)
        settings_layout.addLayout(dir_layout)

        # Цвет
        color_layout = QHBoxLayout()
        color_layout.addWidget(QLabel("Цвет объекта:"))
        self.btn_color_picker = QPushButton("🎨 Выбрать цвет")
        self.btn_color_picker.clicked.connect(self.pick_layer_color)
        color_layout.addWidget(self.btn_color_picker)
        
        self.lbl_color_preview = QLabel()
        self.lbl_color_preview.setFixedSize(24, 24)
        self.lbl_color_preview.setStyleSheet("border: 1px solid #555; border-radius: 4px; background-color: transparent;")
        color_layout.addWidget(self.lbl_color_preview)
        settings_layout.addLayout(color_layout)

        # Активность
        self.enabled_checkbox = QCheckBox("Слой активен (отображать)")
        self.enabled_checkbox.toggled.connect(self.on_enabled_toggled)
        settings_layout.addWidget(self.enabled_checkbox)

        # Чекбокс "принудительно применить состояние ко всем подслоям"
        self.force_state_cb = QCheckBox("Состояние для всех подслоёв (игнорировать свои)")
        self.force_state_cb.toggled.connect(self.on_force_state_toggled)
        settings_layout.addWidget(self.force_state_cb)

        right_layout.addWidget(self.settings_group)
        self.settings_group.setEnabled(False)

        splitter.addWidget(right_widget)
        splitter.setSizes([550, 400])

        layout.addWidget(splitter)
        self.render_scene()

    def on_force_state_toggled(self, checked):
        row = self.layers_list_widget.currentRow()
        if 0 <= row < len(self.scene_layers):
            self.scene_layers[row]["force_state"] = checked
            self.render_scene()

    def get_item_states(self, item: dict) -> list:
        raw_states = item.get("states")
        if not raw_states:
            single_state = item.get("state", "default")
            return [single_state] if single_state else ["default"]
        return raw_states

    def add_layer_from_search(self):
        dialog = LayerSelectorDialog(self.items, self)
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.selected_item:
            item = dialog.selected_item
            states = self.get_item_states(item)
            default_state = "equipped-INNERCLOTHING" if "equipped-INNERCLOTHING" in states else (states[0] if states else "default")

            self.scene_layers.append({
                "item": item,
                "state": default_state,
                "frame": 0,
                "direction": 0,
                "enabled": True,
                "custom_color": "",       # было: initial_color
                "force_state": False,
            })
            self.update_layers_ui()
            self.layers_list_widget.setCurrentRow(len(self.scene_layers) - 1)
            self.render_scene()

    def update_layers_ui(self):
        current_row = self.layers_list_widget.currentRow()
        self.layers_list_widget.blockSignals(True)
        self.layers_list_widget.clear()
        
        for i, layer_data in enumerate(self.scene_layers):
            item_id = layer_data["item"].get("id", f"Слой {i+1}")
            state = layer_data["state"]
            direction = layer_data.get("direction", 0)
            status = "👁" if layer_data["enabled"] else "🚫"
            color_info = f" [{layer_data['custom_color']}]" if layer_data["custom_color"] else ""

            list_item = QListWidgetItem(f"{status} [{i+1}] {item_id} (st: {state}, dir: {direction}){color_info}")
            list_item.setIcon(item_icon(layer_data["item"], 32))
            self.layers_list_widget.addItem(list_item)
            
        self.layers_list_widget.blockSignals(False)

        if 0 <= current_row < len(self.scene_layers):
            self.layers_list_widget.setCurrentRow(current_row)
        elif self.scene_layers:
            self.layers_list_widget.setCurrentRow(len(self.scene_layers) - 1)
        else:
            self.settings_group.setEnabled(False)

    def on_layer_row_changed(self, row):
        if row < 0 or row >= len(self.scene_layers):
            self.settings_group.setEnabled(False)
            return

        self.settings_group.setEnabled(True)
        layer_data = self.scene_layers[row]
        item = layer_data["item"]

        self.state_combo.blockSignals(True)
        self.dir_spin.blockSignals(True)
        self.enabled_checkbox.blockSignals(True)

        self.force_state_cb.blockSignals(True)
        self.force_state_cb.setChecked(layer_data.get("force_state", False))
        self.force_state_cb.blockSignals(False)

        self.state_combo.clear()
        self.state_combo.addItems(self.get_item_states(item))

        current_state = layer_data["state"]
        state_idx = self.state_combo.findText(current_state)
        if state_idx >= 0:
            self.state_combo.setCurrentIndex(state_idx)

        self.dir_spin.setValue(layer_data.get("direction", 0))
        self.enabled_checkbox.setChecked(layer_data["enabled"])
        
        c = layer_data["custom_color"]
        if c:
            self.lbl_color_preview.setStyleSheet(f"border: 1px solid #555; border-radius: 4px; background-color: {c};")
        else:
            self.lbl_color_preview.setStyleSheet("border: 1px solid #555; border-radius: 4px; background-color: transparent;")

        self.state_combo.blockSignals(False)
        self.dir_spin.blockSignals(False)
        self.enabled_checkbox.blockSignals(False)

    def on_state_changed(self, index):
        row = self.layers_list_widget.currentRow()
        if 0 <= row < len(self.scene_layers):
            new_state = self.state_combo.currentText()
            if new_state:
                self.scene_layers[row]["state"] = new_state
                self.update_layers_ui()
                self.render_scene()

    def on_direction_changed(self, value):
        row = self.layers_list_widget.currentRow()
        if 0 <= row < len(self.scene_layers):
            self.scene_layers[row]["direction"] = value
            self.update_layers_ui()
            self.render_scene()

    def on_enabled_toggled(self, checked):
        row = self.layers_list_widget.currentRow()
        if 0 <= row < len(self.scene_layers):
            self.scene_layers[row]["enabled"] = checked
            self.update_layers_ui()
            self.render_scene()

    def pick_layer_color(self):
        row = self.layers_list_widget.currentRow()
        if 0 <= row < len(self.scene_layers):
            current_color = self.scene_layers[row]["custom_color"] or "#ffffff"
            color = QColorDialog.getColor(QColor(current_color), self, "Выберите цвет предмета")
            if color.isValid():
                hex_color = color.name(QColor.NameFormat.HexArgb) if hasattr(QColor, 'NameFormat') else color.name()
                self.scene_layers[row]["custom_color"] = hex_color
                self.lbl_color_preview.setStyleSheet(f"border: 1px solid #555; border-radius: 4px; background-color: {hex_color};")
                self.update_layers_ui()
                self.render_scene()

    def render_scene(self):
        """Рендерит сцену с динамическим расчетом максимальных размеров холста и поддержкой direction."""
        native_w, native_h = 32, 32
        
        # ИСПРАВЛЕНИЕ: Вычисляем максимальный размер холста по ВСЕМ активным слоям сцены
        if self.scene_layers:
            max_w = 32
            max_h = 32
            for layer_data in self.scene_layers:
                if not layer_data["enabled"]:
                    continue
                item = layer_data["item"]
                size = item.get("size", {})
                w = size.get("x", 32) or 32
                h = size.get("y", 32) or 32
                if w > max_w:
                    max_w = w
                if h > max_h:
                    max_h = h
            native_w, native_h = max_w, max_h

        # Создаем итоговый холст через PIL под максимальные размеры
        final_canvas = Image.new("RGBA", (native_w, native_h), (0, 0, 0, 0))

        for layer_data in self.scene_layers:
            if not layer_data["enabled"]:
                continue

            item = layer_data["item"]
            render_item = {**item, "state": layer_data["state"]}   # state как fallback для render/resolve
            overrides = {
                "layer_configs": build_layer_configs(layer_data),
                "color": layer_data.get("custom_color") or None,
            }
            img = render(render_item,
                        direction=layer_data.get("direction", 0),
                        frame=layer_data.get("frame", 0),
                        overrides=overrides)

            if img.size == (0, 0):
                continue
            if img.size != final_canvas.size:
                tmp = Image.new("RGBA", final_canvas.size, (0, 0, 0, 0))
                tmp.paste(img, (max(0, (final_canvas.width - img.width) // 2),
                                max(0, (final_canvas.height - img.height) // 2)))
                img = tmp
            final_canvas = Image.alpha_composite(final_canvas, img)

        self.current_pil_canvas = final_canvas      # понадобится для аниматора и экспорта

        # Конвертируем PIL Image в QImage -> QPixmap через стандартный метод
        q_img = pil_to_qimage(final_canvas)
        canvas_pixmap = QPixmap.fromImage(q_img)
        self.current_rendered_canvas = canvas_pixmap

        # Масштабируем для отображения в QLabel с сохранением пиксельной четкости
        display_pixmap = canvas_pixmap.scaled(
            256, 256,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.FastTransformation
        )
        self.canvas_label.setPixmap(display_pixmap)

    def move_layer_up(self):
        idx = self.layers_list_widget.currentRow()
        if idx > 0:
            self.scene_layers[idx], self.scene_layers[idx-1] = self.scene_layers[idx-1], self.scene_layers[idx]
            self.update_layers_ui()
            self.layers_list_widget.setCurrentRow(idx-1)
            self.render_scene()

    def move_layer_down(self):
        idx = self.layers_list_widget.currentRow()
        if 0 <= idx < len(self.scene_layers) - 1:
            self.scene_layers[idx], self.scene_layers[idx+1] = self.scene_layers[idx+1], self.scene_layers[idx]
            self.update_layers_ui()
            self.layers_list_widget.setCurrentRow(idx+1)
            self.render_scene()

    def delete_layer(self):
        idx = self.layers_list_widget.currentRow()
        if 0 <= idx < len(self.scene_layers):
            del self.scene_layers[idx]
            self.update_layers_ui()
            self.render_scene()

    def export_scene(self):
        if not self.scene_layers:
            QMessageBox.warning(self, "Внимание", "Сцена пуста! Добавьте хотя бы один слой.")
            return

        file_path, _ = QFileDialog.getSaveFileName(self, "Сохранить сборку", "composite_scene.png", "PNG Images (*.png)")
        if file_path:
            # Сохранение итогового холста в исходном разрешении
            self.current_pil_canvas.save(file_path, "PNG")
            QMessageBox.information(self, "Успех", f"Сцена успешно сохранена:\n{file_path}")

    def open_animator(self):
        if self.anim_dialog is None:
            self.anim_dialog = AnimationBuilderDialog(self)
        self.anim_dialog.show()
        self.anim_dialog.raise_()
        return self.anim_dialog

    def add_frame_to_animation(self):
        dlg = self.open_animator()
        n = len(dlg.frames) + 1
        dlg.add_frame(self.current_pil_canvas.copy(), f"scene_{n}")