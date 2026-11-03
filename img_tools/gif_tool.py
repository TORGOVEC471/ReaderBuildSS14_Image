import numpy as np
import json
import os
import argparse

from pathlib import Path
from chardet import UniversalDetector
from PIL import Image
from typing import Literal

from config import PATH_SAVES

from img_tools.sprite_processor import SpriteLayerProcessor


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


def parse_state_delays(state_data: dict, direction: int = 0) -> tuple[list, int]:
    """Извлекает задержки и количество кадров для конкретного направления из структуры state."""
    delays_raw = state_data.get("delays", [])
    if not delays_raw:
        return [0.1], 1
    
    # Если delays — это двумерный массив (список списков: направления x кадры)
    if isinstance(delays_raw, list) and delays_raw and isinstance(delays_raw[0], list):
        dir_idx = direction % len(delays_raw)
        d_list = delays_raw[dir_idx]
    else:
        d_list = delays_raw
        
    flat_delays = np.array(d_list).flatten().tolist()
    return flat_delays, len(flat_delays) if flat_delays else 1


def save_anim(
        sprite: Image.Image | os.PathLike,
        name: str,
        tile_w: int, #M
        tile_h: int, #N
        delays: list,
        image_copyright: str,
        image_license: str,
        format: Literal["gif", "webp"] = "gif",
        direction: int = 0,
        directions_count: int = 1,
        frame_count: int = 1
    ) -> Path:
    if isinstance(sprite, Image.Image):
        raw_img = np.array(sprite)
    elif isinstance(sprite, (os.PathLike, str)):
        with Image.open(sprite) as img:
            raw_img = np.array(img)

    sheet_h, sheet_w = raw_img.shape[0], raw_img.shape[1]
    cols = sheet_w // tile_w if tile_w > 0 else 1
    rows = sheet_h // tile_h if sheet_h > 0 else 1

    dir_idx = direction % directions_count if directions_count > 0 else 0
    if dir_idx >= rows:
        dir_idx = 0

    # Нарезаем кадры строго для выбранного направления (строки спрайт-листа)
    frames = []
    effective_frames = frame_count if frame_count > 0 else cols
    for f_idx in range(effective_frames):
        col = f_idx % cols
        row = dir_idx
        
        x1 = col * tile_w
        y1 = row * tile_h
        x2 = x1 + tile_w
        y2 = y1 + tile_h
        
        if y2 <= sheet_h and x2 <= sheet_w:
            tile = raw_img[y1:y2, x1:x2]
            frames.append(Image.fromarray(tile))

    if not frames:
        frames = [Image.fromarray(raw_img)]

    # Если объект больше 64px, уменьшаем scale_factor до 4 или 2
    if max(tile_w, tile_h) > 64:
        SCALE_FACTOR = 4
    else:
        SCALE_FACTOR = 8 # Размер умножения

    target_width = tile_w * SCALE_FACTOR   # N = size.x
    target_height = tile_h * SCALE_FACTOR  # M = size.y

    resized_frames = [
        frame.resize((target_width, target_height), Image.NEAREST)
        for frame in frames
    ]

    metadata_text = f"{name}\n{image_copyright} License: {image_license}"
    
    # Pillow принимает время кадра в миллисекундах (0.2 сек -> 200 мс)
    durations_ms = [int(d * 1000) if d < 10 else int(d) for d in delays[:len(resized_frames)]]
    if not durations_ms:
        durations_ms = [200] * len(resized_frames)

    output_filepath = OUTPUT_DIR / f"{name}.{format}"
    try:
        print(f"[INFO] Saving {output_filepath}")
        if format == "gif":
            resized_frames[0].save(
                output_filepath,
                format='GIF',
                optimize=True,
                append_images=resized_frames[1:],
                disposal=2,
                save_all=True,
                duration=durations_ms,
                loop=0,
                comment=metadata_text
            )
        elif format == "webp":
            resized_frames[0].save(
                output_filepath,
                format='WEBP',
                lossless=True,
                append_images=resized_frames[1:],
                save_all=True,
                duration=durations_ms,
                loop=0,
                comment=metadata_text
            )
        return output_filepath
    except Exception as e:
        print(f"[ERROR] {e}")

def process_composite_anim(item: dict, name_file: str, format: Literal["gif", "webp"] = "gif"):
    """Собирает многослойную анимацию (сборщик) с учетом выбранных направлений, кадров, смещений и цветов."""
    base_textures_path = SpriteLayerProcessor.get_base_textures_path(item)
    
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

    # 1. Анализируем слои
    for layer in layers:
        if not layer.get("enabled", layer.get("visible", True)):
            continue
        
        ldir = base_textures_path / layer.get("sprite") if layer.get("sprite") else Path(item.get("path", ""))
        lfile, st_name = SpriteLayerProcessor.resolve_layer_file(item, layer, base_textures_path, item_state)
        if not lfile or not lfile.exists():
            continue

        f_count, directions_count, l_delays, _ = SpriteLayerProcessor.parse_meta_and_frames(
            lfile, ldir, st_name, native_w, native_h
        )

        selected_dir = layer.get("direction", 0) % directions_count if directions_count > 0 else 0
        # Если в метаданных deltas/delays были для конкретного направления:
        meta_path = ldir / "meta.json"
        if meta_path.exists():
            try:
                with open(meta_path, "r", encoding="utf-8") as f:
                    meta_data = json.load(f)
                    for st in meta_data.get("states", []):
                        if st.get("name") == st_name and "delays" in st:
                            raw_delays = st["delays"]
                            if isinstance(raw_delays, list) and raw_delays and isinstance(raw_delays[0], list):
                                dir_idx = selected_dir % len(raw_delays)
                                l_delays = raw_delays[dir_idx]
                                f_count = len(l_delays)
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
            "directions_count": directions_count,
            "delays": l_delays
        })

    if not layer_infos:
        print(f"[WARN] No valid layers for composite animation {name_file}")
        return

    if not primary_delays:
        primary_delays = [0.1] * max_frames

    if len(primary_delays) < max_frames:
        primary_delays = (primary_delays * ((max_frames // len(primary_delays)) + 1))[:max_frames]

    SCALE_FACTOR = 4 if max(native_w, native_h) > 64 else 8
    target_width = native_w * SCALE_FACTOR
    target_height = native_h * SCALE_FACTOR

    frames = []
    
    # 2. Построение каждого кадра
    for t in range(max_frames):
        native_img = Image.new("RGBA", (native_w, native_h), (0, 0, 0, 0))

        for info in layer_infos:
            layer = info["layer"]
            lfile = info["file"]
            f_count = info["frame_count"]
            directions_count = info["directions_count"]
            
            selected_dir = layer.get("direction", 0) % directions_count if directions_count > 0 else 0
            base_frame = layer.get("frame", 0)
            frame_idx = (t + base_frame) % f_count if f_count > 0 else 0

            try:
                with Image.open(lfile) as full_img:
                    full_img = full_img.convert("RGBA")
                    fw, fh = full_img.width, full_img.height

                    col, row = SpriteLayerProcessor.calculate_grid_coords(
                        fw, fh, native_w, native_h, selected_dir, frame_idx, f_count
                    )

                    if fw > native_w or fh > native_h:
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

                    offset_x, offset_y = SpriteLayerProcessor.parse_offset(layer.get("offset"), native_w, native_h)
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

    with open(json_file, "r", encoding="utf-8") as json_content:
        data = json.load(json_content)
        
    copyright_data = data.get('copyright', '')
    license_data = data.get('license', '')

    for state in data.get('states', []):
        state_name = state.get("name")
        if target_state and state_name != target_state:
            continue

        directions_count = state.get("directions", 1)
        direction = 0
        if item and "layers" in item:
            for l in item["layers"]:
                if l.get("state") == state_name or not l.get("state"):
                    direction = l.get("direction", 0)
                    break

        state_delays, f_count = parse_state_delays(state, direction)
        spritesheet_file = json_file.parent / f"{state_name}.png"

        if not spritesheet_file.exists():
            print(f"[WARN] File not found: {spritesheet_file}, skipping state {state_name}")
            continue

        sprite_name = name_file or f"{json_file.parent.name}-{state_name}"

        save_anim(
            sprite=spritesheet_file,
            name=sprite_name,
            delays=state_delays,
            tile_w=data['size']['x'],
            tile_h=data['size']['y'],
            image_copyright=copyright_data,
            image_license=license_data,
            format=format,
            direction=direction,
            directions_count=directions_count,
            frame_count=f_count
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

        if target_path.is_file() and target_path.suffix == ".json":
            process_json_file(target_path)
        
        elif target_path.is_file() and target_path.suffix == ".png":
            parent_dir = target_path.parent
            meta_json = parent_dir / "meta.json"

            if not meta_json.exists():
                json_files = list(parent_dir.glob("*.json"))
                if not json_files:
                    print(f"[ERROR] No .json file found in {parent_dir} for {target_path.name}")
                    continue
                meta_json = json_files[0]

            target_state_name = target_path.stem
            process_json_file(meta_json, target_state=target_state_name)

        elif target_path.is_dir():
            json_files = sorted(target_path.glob("**/*.json"))
            for json_file in json_files:
                if OUTPUT_DIR in json_file.parents:
                    continue
                process_json_file(json_file)


if __name__ == "__main__":
    main()