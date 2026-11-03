import json
from pathlib import Path
from PIL import Image
from logger import logger

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
    def parse_offset(offset_val, native_w: int, native_h: int) -> tuple[int, int]:
        """Парсит offset в пиксели."""
        if not offset_val:
            return 0, 0
        try:
            parts = [float(p.strip()) for p in str(offset_val).split(",")]
            if len(parts) == 2:
                offset_x = int(round(parts[0] * native_w))
                offset_y = int(round(-parts[1] * native_h))
                return offset_x, offset_y
        except ValueError:
            pass
        return 0, 0