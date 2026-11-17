from PIL import Image
from PyQt6.QtWidgets import (
    QDialog, QHBoxLayout, QVBoxLayout, QLabel, QPushButton, QListWidget,
    QListWidgetItem, QSpinBox, QCheckBox, QComboBox, QFileDialog,
    QMessageBox, QGroupBox
)
from PyQt6.QtCore import Qt, QTimer, QSize
from PyQt6.QtGui import QPixmap, QIcon
from GUI.qt_image_tool import pil_to_qimage


def _pix(img: Image.Image, size: int) -> QPixmap:
    return QPixmap.fromImage(pil_to_qimage(img)).scaled(
        size, size, Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.FastTransformation)


class AnimationBuilderDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Конструктор анимаций")
        self.setMinimumSize(800, 560)
        self.frames = []            # [{"image": PIL RGBA, "duration": ms, "name": str}]
        self.play_idx = 0
        self.play_timer = QTimer(self)
        self.play_timer.setSingleShot(True)
        self.play_timer.timeout.connect(self._next_play_frame)

        root = QHBoxLayout(self)

        # --- превью ---
        left = QVBoxLayout()
        self.preview = QLabel(alignment=Qt.AlignmentFlag.AlignCenter)
        self.preview.setMinimumSize(320, 320)
        self.preview.setStyleSheet("background-color: #222; border-radius: 8px;")
        left.addWidget(self.preview, 1)
        self.btn_play = QPushButton("▶ Играть")
        self.btn_play.setCheckable(True)
        self.btn_play.toggled.connect(self.toggle_play)
        left.addWidget(self.btn_play)
        root.addLayout(left, 3)

        # --- кадры ---
        right = QVBoxLayout()
        self.list = QListWidget()
        self.list.setIconSize(QSize(48, 48))
        self.list.currentRowChanged.connect(self.on_row_changed)
        right.addWidget(self.list, 1)

        row = QHBoxLayout()
        for text, slot in [("📂 Из файла", self.add_from_files),
                           ("⬆", lambda: self.move(-1)),
                           ("⬇", lambda: self.move(1)),
                           ("⧉", self.duplicate),
                           ("🗑", self.delete)]:
            b = QPushButton(text)
            b.clicked.connect(slot)
            row.addWidget(b)
        right.addLayout(row)

        dur = QHBoxLayout()
        dur.addWidget(QLabel("Длительность кадра, мс:"))
        self.dur_spin = QSpinBox()
        self.dur_spin.setRange(10, 10000)
        self.dur_spin.setSingleStep(10)
        self.dur_spin.setValue(100)
        self.dur_spin.valueChanged.connect(self.on_duration_changed)
        dur.addWidget(self.dur_spin)
        btn_all = QPushButton("Всем")
        btn_all.clicked.connect(self.apply_duration_to_all)
        dur.addWidget(btn_all)
        right.addLayout(dur)

        grp = QGroupBox("Экспорт")
        g = QVBoxLayout(grp)
        h = QHBoxLayout()
        self.fmt_combo = QComboBox()
        self.fmt_combo.addItems(["GIF", "WebP"])
        h.addWidget(self.fmt_combo)
        h.addWidget(QLabel("Масштаб ×"))
        self.scale_spin = QSpinBox()
        self.scale_spin.setRange(1, 16)
        self.scale_spin.setValue(4)
        h.addWidget(self.scale_spin)
        g.addLayout(h)
        self.loop_cb = QCheckBox("Зациклить")
        self.loop_cb.setChecked(True)
        g.addWidget(self.loop_cb)
        btn_export = QPushButton("💾 Сохранить анимацию")
        btn_export.setStyleSheet("background-color: #1abc9c; color: white; font-weight: bold; padding: 8px;")
        btn_export.clicked.connect(self.export)
        g.addWidget(btn_export)
        right.addWidget(grp)
        root.addLayout(right, 2)

    # ---------- кадры ----------
    def add_frame(self, image: Image.Image, name: str = "frame", duration: int = None):
        self.frames.append({
            "image": image.convert("RGBA"),
            "duration": duration or self.dur_spin.value(),
            "name": name,
        })
        self.refresh_list(len(self.frames) - 1)

    def add_from_files(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Выберите изображения", "", "Images (*.png *.gif *.webp)")
        for p in sorted(paths):
            try:
                with Image.open(p) as im:
                    self.add_frame(im.copy(), p.replace("\\", "/").split("/")[-1])
            except Exception as e:
                QMessageBox.warning(self, "Ошибка", f"{p}:\n{e}")

    def refresh_list(self, select: int = None):
        self.list.blockSignals(True)
        self.list.clear()
        for i, f in enumerate(self.frames):
            it = QListWidgetItem(f"#{i+1}  {f['name']}  ({f['duration']} мс)")
            it.setIcon(QIcon(_pix(f["image"], 48)))
            self.list.addItem(it)
        self.list.blockSignals(False)
        if select is not None and 0 <= select < len(self.frames):
            self.list.setCurrentRow(select)
        self.on_row_changed(self.list.currentRow())

    def move(self, delta: int):
        i = self.list.currentRow()
        j = i + delta
        if 0 <= i < len(self.frames) and 0 <= j < len(self.frames):
            self.frames[i], self.frames[j] = self.frames[j], self.frames[i]
            self.refresh_list(j)

    def duplicate(self):
        i = self.list.currentRow()
        if i >= 0:
            f = self.frames[i]
            self.frames.insert(i + 1, {**f, "image": f["image"].copy()})
            self.refresh_list(i + 1)

    def delete(self):
        i = self.list.currentRow()
        if i >= 0:
            del self.frames[i]
            self.refresh_list(min(i, len(self.frames) - 1))

    def on_row_changed(self, row):
        if 0 <= row < len(self.frames):
            self.dur_spin.blockSignals(True)
            self.dur_spin.setValue(self.frames[row]["duration"])
            self.dur_spin.blockSignals(False)
            if not self.play_timer.isActive():
                self.preview.setPixmap(_pix(self.frames[row]["image"], 320))
        else:
            self.preview.clear()

    def on_duration_changed(self, v):
        i = self.list.currentRow()
        if 0 <= i < len(self.frames):
            self.frames[i]["duration"] = v
            self.list.item(i).setText(f"#{i+1}  {self.frames[i]['name']}  ({v} мс)")

    def apply_duration_to_all(self):
        for f in self.frames:
            f["duration"] = self.dur_spin.value()
        self.refresh_list(self.list.currentRow())

    # ---------- предпросмотр ----------
    def toggle_play(self, on: bool):
        if on and self.frames:
            self.btn_play.setText("⏹ Стоп")
            self.play_idx = 0
            self._next_play_frame()
        else:
            self.play_timer.stop()
            self.btn_play.setText("▶ Играть")
            self.btn_play.blockSignals(True)
            self.btn_play.setChecked(False)
            self.btn_play.blockSignals(False)
            self.on_row_changed(self.list.currentRow())

    def _next_play_frame(self):
        if not self.frames:
            return self.toggle_play(False)
        f = self.frames[self.play_idx % len(self.frames)]
        self.preview.setPixmap(_pix(f["image"], 320))
        self.play_idx = (self.play_idx + 1) % len(self.frames)
        self.play_timer.start(f["duration"])

    # ---------- экспорт ----------
    def _normalized_frames(self, scale: int):
        w = max(f["image"].width for f in self.frames)
        h = max(f["image"].height for f in self.frames)
        out = []
        for f in self.frames:
            img = f["image"]
            canvas = Image.new("RGBA", (w, h), (0, 0, 0, 0))
            canvas.paste(img, ((w - img.width) // 2, (h - img.height) // 2))
            if scale > 1:
                canvas = canvas.resize((w * scale, h * scale), Image.NEAREST)
            out.append(canvas)
        return out

    @staticmethod
    def _to_gif_frame(img: Image.Image) -> Image.Image:
        """RGBA -> P с одним прозрачным индексом (GIF не умеет полупрозрачность)."""
        alpha = img.getchannel("A")
        p = img.convert("RGB").convert("P", palette=Image.Palette.ADAPTIVE, colors=255)
        p.paste(255, alpha.point(lambda a: 255 if a < 128 else 0))
        p.info["transparency"] = 255
        return p

    def export(self):
        if not self.frames:
            QMessageBox.warning(self, "Внимание", "Добавьте хотя бы один кадр!")
            return
        fmt = self.fmt_combo.currentText()
        ext = "gif" if fmt == "GIF" else "webp"
        path, _ = QFileDialog.getSaveFileName(
            self, "Сохранить анимацию", f"animation.{ext}", f"{fmt} (*.{ext})")
        if not path:
            return

        frames = self._normalized_frames(self.scale_spin.value())
        durations = [f["duration"] for f in self.frames]
        try:
            if fmt == "GIF":
                gif_frames = [self._to_gif_frame(f) for f in frames]
                kwargs = dict(save_all=True, append_images=gif_frames[1:],
                              duration=durations, disposal=2,
                              transparency=255, optimize=False)
                if self.loop_cb.isChecked():
                    kwargs["loop"] = 0
                gif_frames[0].save(path, "GIF", **kwargs)
            else:
                frames[0].save(path, "WEBP", save_all=True,
                               append_images=frames[1:], duration=durations,
                               loop=0 if self.loop_cb.isChecked() else 1,
                               lossless=True, method=6)
            QMessageBox.information(self, "Успех", f"Анимация сохранена:\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось сохранить:\n{e}")