import numpy as np
import json
import os
import argparse

from pathlib import Path
from chardet import UniversalDetector
from PIL import Image
from typing import Literal

from config import PATH_SAVES


# Папка, куда сохраняются итоговые .gif анимации
OUTPUT_DIR = Path(PATH_SAVES).parent / "Saves/animations"
if not OUTPUT_DIR.exists():
    OUTPUT_DIR.mkdir(parents=True)
elif OUTPUT_DIR == Path("."):
    OUTPUT_DIR = Path(__file__).parent / "Saves/animations"

# Путь по умолчанию (если не переданы аргументы при запуске)
DEFAULT_SOURCE_DIR = Path(__file__).parent


def check_and_reencode_utf_sig(file: Path) -> None:
    """Проверяет наличие BOM (UTF-8-SIG) и перезаписывает файл в чистый UTF-8."""
    u = UniversalDetector()
    u.reset()

    with open(file, 'rb') as bfile:
        for line in bfile:
            u.feed(line)
            if u.done:
                break
    u.close()

    if u.result["encoding"] == "UTF-8-SIG":
        print(f"[WARN] Found UTF-8-SIG in {file} \nChange encoding to UTF-8 (removing BOM)")
        content_sig_file = file.read_text(encoding="UTF-8-SIG")
        new_file = file.with_suffix(".tmp")

        new_file.write_text(content_sig_file, encoding="UTF-8")
        new_file.replace(file)
        print("Encoding changed successfully")


def save_anim(
        sprite: Image.Image | os.PathLike,
        name: str,
        tile_w: int, #M
        tile_h: int, #N
        delays: list,
        image_copyright: str,
        image_license: str,
        format: Literal["gif", "webp"] = "gif"
    ) -> Path:
    if isinstance(sprite, Image.Image):
        raw_img = np.array(sprite)
    elif isinstance(sprite, (os.PathLike, str)):
        with Image.open(sprite) as img:
            raw_img = np.array(img)

    tiles = [
        raw_img[x:x+tile_h, y:y+tile_w]
        for x in range(0, raw_img.shape[0], tile_h)
        for y in range(0, raw_img.shape[1], tile_w)
    ]

    # Если объект больше 64px, уменьшаем scale_factor до 4 или 2
    if max(tile_w, tile_h) > 64:
        SCALE_FACTOR = 4
    else:
        SCALE_FACTOR = 8 # Размер умножения

    target_width = tile_w * SCALE_FACTOR   # N = size.x
    target_height = tile_h * SCALE_FACTOR  # M = size.y

    # 1. Создаем кадры из ВСЕХ нарезанных тайлов
    frames = [
        Image.fromarray(tile).resize((target_width, target_height), Image.NEAREST)
        for tile in tiles
    ]

    # 2. Обрезаем кадры до количества задержек, указанных в meta.json
    if delays:
        frames = frames[:len(delays)]

    if not frames:
        print(f"[WARN] No frames created for {name}")
        return

    metadata_text = f"{name}\n{image_copyright} License: {image_license}"
    
    # Pillow принимает время кадра в миллисекундах (0.2 сек -> 200 мс)
    durations_ms = [int(d * 1000) if d < 10 else int(d) for d in delays[:len(frames)]]

    if format == "gif":
        output_filepath = OUTPUT_DIR / f"{name}.gif"
        try:
            print(f"[INFO] Saving {output_filepath}")
            frames[0].save(
                output_filepath,
                format='GIF',
                optimize=True,
                append_images=frames[1:],
                disposal=2,
                save_all=True,
                duration=durations_ms,
                loop=0,
                comment=metadata_text
            )
            return output_filepath
        except Exception as e:
            print(f"[ERROR] {e}")
    elif format == "webp":
        output_filepath = OUTPUT_DIR / f"{name}.webp" # Расширение .webp вместо .gif
        try:
            print(f"[INFO] Saving {output_filepath}")
            frames[0].save(
                output_filepath,
                format='WEBP',
                lossless=True,          # Без потерь качества для пиксель-арта
                append_images=frames[1:],
                save_all=True,
                duration=durations_ms,
                loop=0,
                comment=metadata_text
            )
            return output_filepath
        except Exception as e:
            print(f"[ERROR] {e}")

def process_composite_anim(item: dict, name_file: str, format: Literal["gif", "webp"] = "gif"):
    """Собирает многослойную анимацию (сборщик) с учетом разной длины слоев, смещений и цветов."""
    file_path = Path(item.get("file", ""))
    resources_dir = next((p for p in file_path.parents if p.name == "Resources"), None)
    base_textures_path = resources_dir / "Textures" if resources_dir else None
    
    if not base_textures_path:
        print("[WARN] Base textures path not found for composite animation.")
        return

    native_w = item.get("size", {}).get("x", 32) or 32
    native_h = item.get("size", {}).get("y", 32) or 32
    layers = item.get("layers", [])
    item_state = item.get("state", "default")

    layer_infos = []
    max_frames = 1
    primary_delays = []

    # 1. Анализируем слои и определяем общую длительность (максимальное число кадров)
    for layer in layers:
        if not layer.get("enabled", layer.get("visible", True)):
            continue
        
        # Fallback состояния: если у слоя нет state, используем состояние предмета
        st_name = layer.get("state") or item_state
        sprite_rel = layer.get("sprite")
        ldir = base_textures_path / sprite_rel if sprite_rel else Path(item.get("path", ""))
        
        if not ldir.exists():
            continue

        lfile = ldir / f"{st_name}.png"
        if not lfile.exists():
            # Если конкретного стейта нет, пробуем fallback на default.png
            if (ldir / "default.png").exists():
                st_name = "default"
                lfile = ldir / "default.png"
            else:
                continue

        # Читаем meta.json слоя для определения кадров и задержек
        meta_path = ldir / "meta.json"
        f_count = 1
        l_delays = []
        if meta_path.exists():
            try:
                with open(meta_path, "r", encoding="utf-8") as f:
                    meta_data = json.load(f)
                    for st in meta_data.get("states", []):
                        if st.get("name") == st_name:
                            if "delays" in st:
                                l_delays = np.array(st["delays"]).flatten().tolist()
                                f_count = len(l_delays)  # <-- Берем количество кадров из длины delays
                            else:
                                f_count = st.get("frameCount", 1)
            except Exception as e:
                print(f"[WARNING] Не удалось прочитать {meta_path}: {e}")

        # Автоопределение по размерам файла, если в meta.json нет данных
        if f_count == 1 and lfile.exists():
            try:
                with Image.open(lfile) as img:
                    fw, fh = img.width, img.height
                    if (fw > native_w or fh > native_h) and (fw % native_w == 0) and (fh % native_h == 0):
                        f_count = (fw // native_w) * (fh // native_h)
            except Exception:
                pass

        if f_count > max_frames:
            max_frames = f_count
            if l_delays:
                primary_delays = l_delays

        layer_infos.append({
            "layer": layer,
            "file": lfile,
            "frame_count": f_count,
            "delays": l_delays
        })

    if not layer_infos:
        print(f"[WARN] No valid layers for composite animation {name_file}")
        return

    if not primary_delays:
        primary_delays = [0.1] * max_frames

    # Выравниваем массив задержек по максимальному числу кадров
    if len(primary_delays) < max_frames:
        primary_delays = (primary_delays * ((max_frames // len(primary_delays)) + 1))[:max_frames]

    SCALE_FACTOR = 4 if max(native_w, native_h) > 64 else 8
    target_width = native_w * SCALE_FACTOR
    target_height = native_h * SCALE_FACTOR

    frames = []
    
    # 2. Построение каждого кадра итоговой анимации
    for t in range(max_frames):
        native_img = Image.new("RGBA", (native_w, native_h), (0, 0, 0, 0))

        for info in layer_infos:
            layer = info["layer"]
            lfile = info["file"]
            f_count = info["frame_count"]
            
            # Учитываем смещение стартового кадра из настроек сборщика и цикличность
            base_frame = layer.get("frame", 0)
            frame_idx = (t + base_frame) % f_count

            try:
                with Image.open(lfile) as full_img:
                    full_img = full_img.convert("RGBA")
                    fw, fh = full_img.width, full_img.height

                    if (fw > native_w or fh > native_h) and (fw % native_w == 0) and (fh % native_h == 0):
                        cols = fw // native_w
                        col = frame_idx % cols
                        row = frame_idx // cols
                        layer_img = full_img.crop((col * native_w, row * native_h, (col + 1) * native_w, (row + 1) * native_h))
                    else:
                        layer_img = full_img

                    # Применение цвета (tint)
                    color_hex = layer.get("color")
                    if color_hex:
                        color_hex_clean = color_hex.lstrip("#")
                        if len(color_hex_clean) == 6:
                            r = int(color_hex_clean[0:2], 16)
                            g = int(color_hex_clean[2:4], 16)
                            b = int(color_hex_clean[4:6], 16)
                            r_ch, g_ch, b_ch, a_ch = layer_img.split()
                            r_ch = r_ch.point(lambda i, v=r: int(i * v / 255))
                            g_ch = g_ch.point(lambda i, v=g: int(i * v / 255))
                            b_ch = b_ch.point(lambda i, v=b: int(i * v / 255))
                            layer_img = Image.merge("RGBA", (r_ch, g_ch, b_ch, a_ch))

                    lw, lh = layer_img.width, layer_img.height
                    center_x = (native_w - lw) // 2
                    center_y = (native_h - lh) // 2

                    offset_x, offset_y = 0, 0
                    offset_val = layer.get("offset")
                    if offset_val:
                        try:
                            parts = [float(p.strip()) for p in str(offset_val).split(",")]
                            if len(parts) == 2:
                                offset_x = int(round(parts[0] * native_w))
                                offset_y = int(round(-parts[1] * native_h))
                        except ValueError:
                            pass

                    final_x = center_x + offset_x
                    final_y = center_y + offset_y

                    native_img.alpha_composite(layer_img, (final_x, final_y))
            except Exception as e:
                print(f"[ERROR] Error processing layer in composite animation: {e}")

        frame_res = native_img.resize((target_width, target_height), Image.NEAREST)
        frames.append(frame_res)

    if not frames:
        print(f"[WARN] No frames generated for {name_file}")
        return

    copyright_data = item.get('copyright', '')
    license_data = item.get('license', '')
    metadata_text = f"{name_file}\n{copyright_data} License: {license_data}"
    durations_ms = [int(d * 1000) if d < 10 else int(d) for d in primary_delays[:len(frames)]]

    output_filepath = OUTPUT_DIR / f"{name_file}.{format}"
    print(f"[INFO] Saving composite animation: {output_filepath}")

    try:
        if format == "gif":
            frames[0].save(
                output_filepath, format='GIF', optimize=True,
                append_images=frames[1:], disposal=2, save_all=True,
                duration=durations_ms, loop=0, comment=metadata_text
            )
        elif format == "webp":
            frames[0].save(
                output_filepath, format='WEBP', lossless=True,
                append_images=frames[1:], save_all=True,
                duration=durations_ms, loop=0, comment=metadata_text
            )
        return output_filepath
    except Exception as e:
        print(f"[ERROR] {e}")

def process_json_file(json_file: Path | str, target_state: str = None, name_file: str = "", format: Literal["gif", "webp"] = "gif", item: dict = None) -> None:
    json_file = Path(json_file)
    check_and_reencode_utf_sig(json_file)
    
    # Если передан словарь item со слоями (режим сборщика), обрабатываем как составную анимацию
    if item and item.get("layers"):
        sprite_name = name_file or item.get("id", "composite_anim")
        process_composite_anim(item, sprite_name, format=format)
        return

    # Стандартная логика для одиночного файла...
    with open(json_file, "r", encoding="utf-8") as json_content:
        data = json.load(json_content)
        
    copyright_data = data.get('copyright', '')
    license_data = data.get('license', '')

    for state in data.get('states', []):
        state_name = state.get("name")
        if target_state and state_name != target_state:
            continue

        if "delays" in state:
            sprite_name = name_file or f"{json_file.parent.name}-{state_name}"
            state_delays = np.array(state["delays"]).flatten().tolist()
            spritesheet_file = json_file.parent / f"{state_name}.png"

            if not spritesheet_file.exists():
                print(f"[WARN] File not found: {spritesheet_file}, skipping state {state_name}")
                continue

            save_anim(
                sprite=spritesheet_file,
                name=sprite_name,
                delays=state_delays,
                tile_w=data['size']['x'],
                tile_h=data['size']['y'],
                image_copyright=copyright_data,
                image_license=license_data,
                format=format
            )


def main():
    parser = argparse.ArgumentParser(description="Конвертация спрайтшитов в GIF на основе JSON описания.")
    parser.add_argument(
        "paths", 
        nargs="*", 
        type=Path, 
        default=[DEFAULT_SOURCE_DIR],
        help="Пути к папкам, конкретным .json файлам или конкретным .png файлам."
    )
    args = parser.parse_args()

    for target_path in args.paths:
        if not target_path.exists():
            print(f"[ERROR] Path does not exist: {target_path}")
            continue

        # 1. Передан конкретный .json файл
        if target_path.is_file() and target_path.suffix == ".json":
            process_json_file(target_path)
        
        # 2. Передан конкретный .png файл (например: .../Sprites/row.png)
        elif target_path.is_file() and target_path.suffix == ".png":
            parent_dir = target_path.parent
            meta_json = parent_dir / "meta.json"

            # Ищем meta.json или любой другой .json в этой же папке
            if not meta_json.exists():
                json_files = list(parent_dir.glob("*.json"))
                if not json_files:
                    print(f"[ERROR] No .json file found in {parent_dir} for {target_path.name}")
                    continue
                meta_json = json_files[0]

            target_state_name = target_path.stem  # Название файла без расширения ("row")
            process_json_file(meta_json, target_state=target_state_name)

        # 3. Передана папка — обрабатываем все .json файлы внутри
        elif target_path.is_dir():
            json_files = sorted(target_path.glob("**/*.json"))
            for json_file in json_files:
                if OUTPUT_DIR in json_file.parents:
                    continue
                process_json_file(json_file)


if __name__ == "__main__":
    main()