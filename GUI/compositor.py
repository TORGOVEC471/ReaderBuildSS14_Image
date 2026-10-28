from pathlib import Path
import os
from PyQt6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QListWidget, QListWidgetItem,
    QLineEdit, QSplitter, QFileDialog, QMessageBox,
    QGroupBox, QComboBox, QCheckBox
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap, QPainter

class LayerSelectorDialog(QDialog):
    """Окно выбора элемента из базы данных через ваш поиск."""
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
        for item in items_to_show[:100]:  # Ограничение для производительности при поиске
            item_id = item.get("id", "Без ID")
            name_ftl = item.get("name_ftl", "")
            display_text = f"{item_id}" + (f" ({name_ftl})" if name_ftl else "")

            list_item = QListWidgetItem(display_text)
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
    """Главное окно композитора сцены из нескольких слоев/предметов с индивидуальными настройками."""
    def __init__(self, items: list, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Композитор изображений и сцен (Scene Builder)")
        self.setMinimumSize(950, 750)
        self.items = items

        # Список слоев сцены: каждый элемент — отдельный объект со своими настройками
        # Структура: {"item": dict, "state": str, "frame": int, "enabled": bool}
        self.scene_layers = []

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

        # Кнопки экспорта сцены
        btn_export = QPushButton("💾 Экспортировать итоговую картинку")
        btn_export.setStyleSheet("background-color: #1abc9c; color: white; font-weight: bold; padding: 8px;")
        btn_export.clicked.connect(self.export_scene)
        left_layout.addWidget(btn_export)

        splitter.addWidget(left_widget)

        # --- Правая панель: Управление слоями сцены ---
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)

        right_layout.addWidget(QLabel("<b>Слои сцены (снизу вверх):</b>"))

        # Список слоев
        self.layers_list_widget = QListWidget()
        self.layers_list_widget.currentRowChanged.connect(self.on_layer_row_changed)
        right_layout.addWidget(self.layers_list_widget)

        # Кнопки управления слоями
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

        # Выбор состояния (state)
        state_layout = QHBoxLayout()
        state_layout.addWidget(QLabel("Состояние (state):"))
        self.state_combo = QComboBox()
        self.state_combo.currentIndexChanged.connect(self.on_state_changed)
        state_layout.addWidget(self.state_combo)
        settings_layout.addLayout(state_layout)

        # Чекбокс видимости
        self.enabled_checkbox = QCheckBox("Слой активен (отображать)")
        self.enabled_checkbox.toggled.connect(self.on_enabled_toggled)
        settings_layout.addWidget(self.enabled_checkbox)

        right_layout.addWidget(self.settings_group)
        self.settings_group.setEnabled(False)  #по умолчанию выключено, пока ничего не выбрано

        splitter.addWidget(right_widget)
        splitter.setSizes([550, 400])

        layout.addWidget(splitter)
        self.render_scene()

    def add_layer_from_search(self):
        """Открывает окно поиска для добавления нового элемента в сцену."""
        dialog = LayerSelectorDialog(self.items, self)
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.selected_item:
            item = dialog.selected_item
            states = item.get("states", [item.get("state", "default")])
            
            # Пытаемся по умолчанию выбрать человеческий вариант, если он есть, иначе первый попавшийся
            default_state = "equipped-INNERCLOTHING"
            if default_state not in states:
                default_state = states[0] if states else "default"

            # Добавляем слой в сцену
            self.scene_layers.append({
                "item": item,
                "state": default_state,
                "frame": 0,
                "enabled": True
            })
            self.update_layers_ui()
            # Автоматически выделяем добавленный слой
            self.layers_list_widget.setCurrentRow(len(self.scene_layers) - 1)
            self.render_scene()

    def update_layers_ui(self):
        """Обновляет виджет списка слоев на панели без потери текущего выделения."""
        current_row = self.layers_list_widget.currentRow()
        self.layers_list_widget.blockSignals(True)
        self.layers_list_widget.clear()
        
        for i, layer_data in enumerate(self.scene_layers):
            item_id = layer_data["item"].get("id", f"Слой {i+1}")
            state = layer_data["state"]
            status = "👁" if layer_data["enabled"] else "🚫"

            list_item = QListWidgetItem(f"{status} [{i+1}] {item_id} ({state})")
            self.layers_list_widget.addItem(list_item)
            
        self.layers_list_widget.blockSignals(False)

        # Восстанавливаем выделение
        if 0 <= current_row < len(self.scene_layers):
            self.layers_list_widget.setCurrentRow(current_row)
        elif self.scene_layers:
            self.layers_list_widget.setCurrentRow(len(self.scene_layers) - 1)
        else:
            self.settings_group.setEnabled(False)

    def on_layer_row_changed(self, row):
        """Вызывается при переключении выбора слоя в списке. Заполняет панель настроек."""
        if row < 0 or row >= len(self.scene_layers):
            self.settings_group.setEnabled(False)
            return

        self.settings_group.setEnabled(True)
        layer_data = self.scene_layers[row]
        item = layer_data["item"]

        # Блокируем сигналы элементов управления во время заполнения
        self.state_combo.blockSignals(True)
        self.enabled_checkbox.blockSignals(True)

        # Заполняем комбобокс состояниями из data.json элемента
        self.state_combo.clear()
        states = item.get("states", [item.get("state", "default")])
        self.state_combo.addItems(states)

        # Выбираем текущее состояние слоя
        current_state = layer_data["state"]
        state_idx = self.state_combo.findText(current_state)
        if state_idx >= 0:
            self.state_combo.setCurrentIndex(state_idx)

        # Устанавливаем чекбокс видимости
        self.enabled_checkbox.setChecked(layer_data["enabled"])

        # Разблокируем сигналы
        self.state_combo.blockSignals(False)
        self.enabled_checkbox.blockSignals(False)

    def on_state_changed(self, index):
        """Срабатывает при изменении состояния в выпадающем списке."""
        row = self.layers_list_widget.currentRow()
        if 0 <= row < len(self.scene_layers):
            new_state = self.state_combo.currentText()
            if new_state:
                self.scene_layers[row]["state"] = new_state
                self.update_layers_ui()
                self.render_scene()

    def on_enabled_toggled(self, checked):
        """Срабатывает при переключении галочки активности слоя."""
        row = self.layers_list_widget.currentRow()
        if 0 <= row < len(self.scene_layers):
            self.scene_layers[row]["enabled"] = checked
            self.update_layers_ui()
            self.render_scene()

    def render_scene(self):
        """Рендерит все включенные слои сцены на общий холст."""
        native_w, native_h = 32, 32  # Стандартный игровой размер спрайта SS14

        canvas = QPixmap(native_w, native_h)
        canvas.fill(Qt.GlobalColor.transparent)

        with QPainter(canvas) as painter:
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)

            for layer_data in self.scene_layers:
                if not layer_data["enabled"]:
                    continue

                item = layer_data["item"]
                state = layer_data["state"]
                sprite_path = Path(item.get("path", "")) / f"{state}.png"

                if not sprite_path.exists():
                    continue

                full_pixmap = QPixmap(str(sprite_path))
                if full_pixmap.isNull():
                    continue

                # Упрощенная отрисовка кадра (если спрайт содержит кадры в ряд)
                frame_idx = layer_data["frame"]
                if full_pixmap.width() > native_w and full_pixmap.width() % native_w == 0:
                    cols = full_pixmap.width() // native_w
                    col = frame_idx % cols
                    row = frame_idx // cols
                    layer_pixmap = full_pixmap.copy(col * native_w, row * native_h, native_w, native_h)
                else:
                    layer_pixmap = full_pixmap

                # Центрируем слой на холсте
                cx = (native_w - layer_pixmap.width()) // 2
                cy = (native_h - layer_pixmap.height()) // 2
                painter.drawPixmap(cx, cy, layer_pixmap)

        # Масштабируем для удобного просмотра (например, 256x256)
        display_pixmap = canvas.scaled(
            256, 256,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.FastTransformation
        )
        self.canvas_label.setPixmap(display_pixmap)
        self.current_rendered_canvas = canvas

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
        """Сохранение готовой сборки на диск."""
        if not self.scene_layers:
            QMessageBox.warning(self, "Внимание", "Сцена пуста! Добавьте хотя бы один слой.")
            return

        file_path, _ = QFileDialog.getSaveFileName(self, "Сохранить сборку", "composite_scene.png", "PNG Images (*.png)")
        if file_path:
            self.current_rendered_canvas.scaled(256, 256, Qt.AspectRatioMode.KeepAspectRatio).save(file_path, "PNG")
            QMessageBox.information(self, "Успех", f"Сцена успешно сохранена:\n{file_path}")