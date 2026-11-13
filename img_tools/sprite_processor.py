import json
from pathlib import Path
from PIL import Image
from PIL.ImageQt import ImageQt
from PyQt6.QtGui import QImage
from logger import logger
from .parse_color import parse_color

class SpriteLayerProcessor:
    @staticmethod
    def get_base_textures_path(item: dict) -> Path | None:
        file_path_str = item.get("file", "")
        file_path = Path(file_path_str)
        resources_dir = next((p for p in file_path.parents if p.name == "Resources"), None)
        return resources_dir / "Textures" if resources_dir else Path(item.get("path", ""))

    @staticmethod
    def resolve_layer_file(item: dict, layer: dict, base_textures_path: Path, item_state: str) -> tuple[Path | None, str]:
        """Определяет корректный путь к файлу текстуры слоя и актуальное имя стейта."""
        st_name = layer.get("state") or item_state
        sprite_rel = layer.get("sprite")
        
        # Проверяем, есть ли resources_dir родитель для пути
        resources_dir = next((p for p in Path(item.get("file", "")).parents if p.name == "Resources"), None)
        if sprite_rel and resources_dir:
            ldir = base_textures_path / sprite_rel
        else:
            ldir = Path(item.get("path", ""))
        
        if not ldir.exists():
            return None, st_name

        lfile = ldir / f"{st_name}.png" if st_name else ldir
        if not lfile.exists() or lfile.is_dir():
            if (ldir / "default.png").exists():
                st_name = "default"
                lfile = ldir / "default.png"
            else:
                return None, st_name
        return lfile, st_name

    @staticmethod
    def parse_meta_and_frames(lfile: Path, ldir: Path, st_name: str, native_w: int, native_h: int) -> tuple[int, int, list, bool]:
        """Анализирует meta.json и размеры файла для определения кадров, направлений, задержек и флага has_directions."""
        meta_path = ldir / "meta.json"
        f_count = 1
        l_delays = []
        directions_count = 1
        has_directions = False
        
        if meta_path.exists():
            try:
                with open(meta_path, "r", encoding="utf-8-sig") as f:
                    meta_data = json.load(f)
                    dirs = meta_data.get("directions")
                    states = meta_data.get("states", [])
                    curr_s = next((s for s in states if s.get("name") == st_name), {})
                    
                    if curr_s.get("directions") is not None:
                        dirs = curr_s.get("directions")
                        
                    if isinstance(dirs, int) and dirs > 1:
                        directions_count = dirs
                        has_directions = True
                    elif isinstance(dirs, (list, tuple)) and len(dirs) > 0:
                        directions_count = len(dirs)
                        has_directions = True

                    if "delays" in curr_s:
                        raw_delays = curr_s["delays"]
                        if isinstance(raw_delays, list) and raw_delays and isinstance(raw_delays[0], list):
                            l_delays = raw_delays[0]
                        else:
                            l_delays = raw_delays
                        f_count = len(l_delays)
            except Exception as e:
                logger.warning(f"Не удалось прочитать {meta_path}: {e}")

        # Автоопределение по размерам файла, если в meta.json нет данных
        if f_count == 1 and lfile.exists():
            try:
                with Image.open(lfile) as img:
                    fw, fh = img.width, img.height
                    cols = fw // native_w if native_w > 0 else 1
                    rows = fh // native_h if native_h > 0 else 1
                    if rows > 1 and directions_count == 1:
                        directions_count = rows
                        has_directions = True
                    
                    if directions_count == 1 and cols > 1:
                        f_count = cols
                    elif not has_directions and rows > 1:
                        has_directions = True
            except Exception:
                pass

        return f_count, directions_count, l_delays, has_directions

    @staticmethod
    def calculate_grid_coords(fw: int, fh: int, native_w: int, native_h: int, selected_dir: int, frame_idx: int, f_count: int) -> tuple[int, int]:
        """Вычисляет координаты столбца и строки спрайт-листа."""
        sheet_cols = fw // native_w if native_w > 0 else 1
        flat_index = (selected_dir * f_count) + frame_idx
        col = flat_index % sheet_cols if sheet_cols > 0 else 0
        row = flat_index // sheet_cols if sheet_cols > 0 else 0
        return col, row

    @staticmethod
    def apply_static_mode_crop(layer_img: Image.Image, mode: str, native_w: int, native_h: int, has_directions: bool) -> Image.Image:
        """Обрезает спрайт под конкретный ракурс (для статического режима image_tool)."""
        if not has_directions:
            return layer_img

        if layer_img.width == native_w and layer_img.height == native_h:
            return layer_img
            
        if mode == "South":
            return layer_img.crop((0, 0, native_w, native_h))
        elif mode == "North":
            return layer_img.crop((native_w, 0, native_w * 2, native_h))
        elif mode == "East":
            return layer_img.crop((0, native_h, native_w, native_h * 2))
        elif mode == "West":
            return layer_img.crop((native_w, native_h, native_w * 2, native_h * 2))
        return layer_img

    @staticmethod
    def parse_offset(offset_val) -> tuple[int, int]:
        """Парсит offset в пиксели (в SS14 единицы смещения привязаны к тайлу 32x32)."""
        if not offset_val:
            return 0, 0
        try:
            parts = [float(p.strip()) for p in str(offset_val).split(",")]
            if len(parts) == 2:
                # Стандартный размер тайла в SS14 — 32 пикселя
                base_tile_size = 32
                offset_x = int(round(parts[0] * base_tile_size))
                offset_y = int(round(-parts[1] * base_tile_size))
                return offset_x, offset_y
        except ValueError:
            pass
        return 0, 0

def pil_to_qimage(pil_img: Image.Image) -> QImage:
    """Конвертирует PIL.Image в QImage для использования в PyQt."""
    if pil_img.mode != "RGBA":
        pil_img = pil_img.convert("RGBA")
    # Используем стандартный ImageQt из библиотеки Pillow
    return QImage(ImageQt(pil_img))

def apply_tint_to_image(img: Image.Image, color_hex: str) -> Image.Image:
    """Накладывает цвет (tint) путем умножения RGB и альфа каналов с сохранением объёма и текстуры."""
    r_t, g_t, b_t, a_t = parse_color(color_hex)

    r, g, b, a = img.split()
    r = r.point(lambda i: int(i * r_t / 255))
    g = g.point(lambda i: int(i * g_t / 255))
    b = b.point(lambda i: int(i * b_t / 255))
    
    # Если в цвете задана прозрачность (#RRGGBBAA), умножаем её на исходную альфу
    if a_t < 255:
        a = a.point(lambda i: int(i * a_t / 255))
        
    return Image.merge("RGBA", (r, g, b, a))

def render(item: dict, direction: int = 0, frame: int = 0, overrides: dict = None) -> Image.Image:
    """
    Единый рендерер слоев предмета. Возвращает PIL.Image в нативном разрешении.
    """
    if overrides is None:
        overrides = {}

    native_w = item.get("size", {}).get("x", 32) or 32
    native_h = item.get("size", {}).get("y", 32) or 32

    canvas = Image.new("RGBA", (native_w, native_h), (0, 0, 0, 0))

    # Получаем конфиги слоев (из overrides или самого item)
    layer_configs = overrides.get("layer_configs")
    if layer_configs is None:
        layers = item.get("layers", [])
        if layers:
            layer_configs = [{"enabled": True, "layer": l, "frame": frame, "direction": direction} for l in layers]
        else:
            state_val = item.get("state")
            if state_val:
                layer_configs = [{
                    "enabled": True,
                    "layer": {"state": state_val, "sprite": None},
                    "frame": frame,
                    "direction": direction
                }]
            else:
                layer_configs = []

    base_textures_path = SpriteLayerProcessor.get_base_textures_path(item)
    item_state = item.get("state", "default")

    if not base_textures_path:
        return canvas

    for config in layer_configs:
        if not config.get("enabled", True):
            continue

        layer = config.get("layer", {})
        if layer.get("visible") is False or layer.get("enabled") is False:
            continue

        # Позволяем переопределять направление и кадр точечно через конфиг или аргументы
        layer_frame = config.get("frame", frame)
        layer_dir = config.get("direction", direction)

        state_name = layer.get("state")
        sprite_rel_path = layer.get("sprite")
        
        # Разрешаем путь через штатный резолвер
        layer_file_path, resolved_state = SpriteLayerProcessor.resolve_layer_file(
            item, layer, base_textures_path, item_state
        )
        if resolved_state:
            state_name = resolved_state

        if not layer_file_path or not layer_file_path.exists() or layer_file_path.is_dir():
            continue

        try:
            with Image.open(layer_file_path) as full_img:
                layer_img = full_img.convert("RGBA")
        except Exception as e:
            continue

        fw, fh = layer_img.width, layer_img.height

        # Анализ метаданных и кадров
        f_count, directions_count, _, _ = SpriteLayerProcessor.parse_meta_and_frames(
            layer_file_path, layer_file_path.parent, state_name, native_w, native_h
        )

        if f_count > 1:
            layer_frame = layer_frame % f_count
        if directions_count > 1:
            layer_dir = layer_dir % directions_count

        # Вырезание кадра / направления из спрайт-листа (сетки)
        if (fw > native_w or fh > native_h) and (fw % native_w == 0) and (fh % native_h == 0):
            col, row = SpriteLayerProcessor.calculate_grid_coords(
                fw, fh, native_w, native_h, layer_dir, layer_frame, f_count
            )
            layer_img = layer_img.crop((col * native_w, row * native_h, (col + 1) * native_w, (row + 1) * native_h))

        # Применение цвета (tint)
        color_hex = layer.get("color") or overrides.get("color")
        if color_hex:
            layer_img = apply_tint_to_image(layer_img, color_hex)

        # Центрирование и смещение (offset)
        lw, lh = layer_img.size
        center_x = (native_w - lw) // 2
        center_y = (native_h - lh) // 2

        offset_x, offset_y = SpriteLayerProcessor.parse_offset(layer.get("offset"))
        final_x = center_x + offset_x
        final_y = center_y + offset_y

        temp_canvas = Image.new("RGBA", (native_w, native_h), (0, 0, 0, 0))
        temp_canvas.paste(layer_img, (final_x, final_y))
        canvas = Image.alpha_composite(canvas, temp_canvas)

    return canvas