import numpy as np
import json
import os
import argparse
import math

from pathlib import Path
from PIL import Image
from typing import Literal
from logger import logger

from config import settings, BASE_DIR
from img_tools.sprite_processor import SpriteLayerProcessor


def output_dir():
    # Папка, куда сохраняются итоговые анимации
    # settings.path_saves уже гарантированно возвращает абсолютный путь (благодаря config.py).
    out_dir = settings.path_saves / "Saves" / "animations"

    if not out_dir.exists():
        out_dir.mkdir(parents=True, exist_ok=True)

    return out_dir

# Источник по умолчанию теперь тоже привязан к корневой папке проекта/exe, а не к временной _MEIPASS
DEFAULT_SOURCE_DIR = BASE_DIR

def parse_state_delays(state_data: dict, direction: int = 0) -> tuple[list, int]:
    """Извлекает задержки и количество кадров для конкретного направления из структуры state."""
    delays_raw = state_data.get("delays", [])
    if not delays_raw:
        return [0.1], 1
    
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
        tile_w: int,
        tile_h: int,
        delays: list,
        image_copyright: str,
        image_license: str,
        format: Literal["gif", "webp", "apng"] = "gif",
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
    rows = sheet_h // tile_h if tile_h > 0 else 1

    dir_idx = direction % directions_count if directions_count > 0 else 0
    if dir_idx >= rows:
        dir_idx = 0

    frames = []
    effective_frames = frame_count if frame_count > 0 else cols
    
    # Вычисляем, сколько строк занимает одно направление с учетом переноса кадров по колонкам
    frames_per_row = cols if cols > 0 else 1
    rows_per_direction = (effective_frames + frames_per_row - 1) // frames_per_row

    for f_idx in range(effective_frames):
        c_offset = f_idx % frames_per_row
        r_offset = f_idx // frames_per_row
        
        col = c_offset
        # Учитываем смещение по строкам для конкретного направления
        row = (dir_idx * rows_per_direction) + r_offset
        
        x1 = col * tile_w
        y1 = row * tile_h
        x2 = x1 + tile_w
        y2 = y1 + tile_h
        
        if y2 <= sheet_h and x2 <= sheet_w:
            tile = raw_img[y1:y2, x1:x2]
            frames.append(Image.fromarray(tile))

    if not frames:
        frames = [Image.fromarray(raw_img)]

    SCALE_FACTOR = 4 if max(tile_w, tile_h) > 64 else 8
    target_width = tile_w * SCALE_FACTOR
    target_height = tile_h * SCALE_FACTOR

    resized_frames = [
        frame.resize((target_width, target_height), Image.NEAREST)
        for frame in frames
    ]

    metadata_text = f"{name}\n{image_copyright} License: {image_license}"
    durations_ms = [int(d * 1000) if d < 10 else int(d) for d in delays[:len(resized_frames)]]
    if not durations_ms:
        durations_ms = [200] * len(resized_frames)

    output_filepath = output_dir() / f"{name}.{format}"
    try:
        logger.info(f"Saving {output_filepath}")
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
        elif format == "apng":
            # APNG сохраняется через формат PNG с флагами save_all и append_images
            resized_frames[0].save(
                output_filepath,
                format='PNG',
                append_images=resized_frames[1:],
                save_all=True,
                duration=durations_ms,
                loop=0,
                comment=metadata_text
            )
        return output_filepath
    except Exception as e:
        logger.error({e})


def process_composite_anim(item: dict, name_file: str, format: Literal["gif", "webp", "apng"] = "gif", layer_configs: list = None):
    """Собирает многослойную анимацию с синхронизацией слоев по времени."""
    base_textures_path = SpriteLayerProcessor.get_base_textures_path(item)
    
    if not base_textures_path:
        logger.warning("Base textures path not found for composite animation.")
        return

    native_w = item.get("size", {}).get("x", 32) or 32
    native_h = item.get("size", {}).get("y", 32) or 32
    item_state = item.get("state", "default")

    # Использование layer_configs из интерфейса или fallback на item["layers"]
    if layer_configs is not None:
        configs = layer_configs
    else:
        configs = [{"layer": l, "enabled": l.get("visible", True) and l.get("enabled", True), "direction": l.get("direction", 0)} for l in item.get("layers", [])]

    layer_infos = []

    # 1. Анализируем слои и собираем их кадры + задержки
    for config in configs:
        if isinstance(config, dict) and "layer" in config:
            layer = config["layer"]
            is_enabled = config.get("enabled", True)
            selected_dir = config.get("direction", 0)
        else:
            layer = config
            is_enabled = layer.get("visible", True) and layer.get("enabled", True)
            selected_dir = layer.get("direction", 0)

        if not is_enabled:
            continue
        
        ldir = base_textures_path / layer.get("sprite") if layer.get("sprite") else Path(item.get("path", ""))
        lfile, st_name = SpriteLayerProcessor.resolve_layer_file(item, layer, base_textures_path, item_state)
        if not lfile or not lfile.exists():
            continue

        f_count, directions_count, l_delays, _ = SpriteLayerProcessor.parse_meta_and_frames(
            lfile, ldir, st_name, native_w, native_h
        )

        selected_dir = selected_dir % directions_count if directions_count > 0 else 0
        meta_path = ldir / "meta.json"
        if meta_path.exists():
            try:
                with open(meta_path, "r", encoding="utf-8-sig") as f:
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

        if not l_delays:
            l_delays = [0.1] * f_count

        delays_ms = [int(d * 1000) if d < 10 else int(d) for d in l_delays]
        if len(delays_ms) < f_count:
            delays_ms = (delays_ms * ((f_count // len(delays_ms)) + 1))[:f_count]

        with Image.open(lfile) as img:
            img = img.convert("RGBA")
            raw_img = np.array(img)

        sheet_h, sheet_w = raw_img.shape[0], raw_img.shape[1]
        cols = sheet_w // native_w if native_w > 0 else 1
        rows = sheet_h // native_h if native_h > 0 else 1
        dir_idx = selected_dir % rows if rows > 0 else 0

        layer_frames = []
        for f_idx in range(f_count):
            col = f_idx % cols
            x1 = col * native_w
            y1 = dir_idx * native_h
            x2 = x1 + native_w
            y2 = y1 + native_h
            if y2 <= sheet_h and x2 <= sheet_w:
                tile = raw_img[y1:y2, x1:x2]
                layer_frames.append(Image.fromarray(tile))

        if not layer_frames:
            layer_frames = [Image.fromarray(raw_img)]

        layer_infos.append({
            "frames": layer_frames,
            "delays_ms": delays_ms,
            "frame_count": len(layer_frames)
        })

    if not layer_infos:
        logger.warning(f"No valid layers for composite animation {name_file}")
        return

    # 2. Построение единого таймлайна (синхронизация по времени, а не по индексам)
    # Вычисляем длительность цикла каждого слоя в миллисекундах
    cycle_durations = [sum(info["delays_ms"]) for info in layer_infos]
    
    # Находим общую длительность анимации (LCM циклов или максимум для предотвращения переполнения)
    total_duration = math.lcm(*cycle_durations) if all(d > 0 for d in cycle_durations) else max(cycle_durations)
    if total_duration > 10000:  # Ограничение на случай слишком больших значений LCM
        total_duration = max(cycle_durations)

    # Собираем все уникальные точки смены кадров по времени от всех слоев
    timeline_points = {0}
    for info, cycle_dur in zip(layer_infos, cycle_durations, strict=True):
        current_t = 0
        # Проходим циклы до общей длительности total_duration
        repeats = total_duration // cycle_dur if cycle_dur > 0 else 1
        for _ in range(max(1, repeats)):
            for delay in info["delays_ms"]:
                current_t += delay
                if current_t <= total_duration:
                    timeline_points.add(current_t)

    sorted_times = sorted(list(timeline_points))
    
    # Формируем интервалы (кадры итоговой анимации)
    timeline_frames = []
    durations_ms = []

    for i in range(len(sorted_times) - 1):
        t_start = sorted_times[i]
        t_end = sorted_times[i + 1]
        step_duration = t_end - t_start
        if step_duration <= 0:
            continue

        # Создаем холст для текущего среза времени
        SCALE_FACTOR = 4 if max(native_w, native_h) > 64 else 8
        target_width = native_w * SCALE_FACTOR
        target_height = native_h * SCALE_FACTOR

        canvas = Image.new("RGBA", (target_width, target_height), (0, 0, 0, 0))

        # Для каждого слоя находим правильный индекс кадра на момент времени t_start
        for info in layer_infos:
            accum = 0
            frame_idx = 0
            # Вычисляем текущую позицию внутри зацикленного слоя
            cycle_dur = sum(info["delays_ms"])
            t_in_cycle = t_start % cycle_dur if cycle_dur > 0 else 0
            
            for idx, d in enumerate(info["delays_ms"]):
                if accum <= t_in_cycle < accum + d:
                    frame_idx = idx
                    break
                accum += d
            
            layer_img = info["frames"][frame_idx % info["frame_count"]]
            resized_layer = layer_img.resize((target_width, target_height), Image.NEAREST).convert("RGBA")  # <--- Гарантирует RGBA
            canvas.alpha_composite(resized_layer)

        timeline_frames.append(canvas)
        durations_ms.append(step_duration)

    if not timeline_frames:
        logger.warning(f"No frames generated for {name_file}")
        return

    # Получаем copyright и license с фоллбэком на meta.json
    copyright_data = item.get('copyright', '')
    license_data = item.get('license', '')

    if not copyright_data or not license_data:
        # Пробуем найти meta.json через базовый путь текстур слоя или самого item
        meta_path = base_textures_path / "meta.json"
        if not meta_path.exists() and item.get("path"):
            meta_path = Path(item.get("path")) / "meta.json"
            
        if meta_path.exists():
            try:
                with open(meta_path, "r", encoding="utf-8-sig") as f:
                    meta_json_data = json.load(f)
                    if not copyright_data:
                        copyright_data = meta_json_data.get('copyright', '')
                    if not license_data:
                        license_data = meta_json_data.get('license', '')
            except Exception:
                pass

    copyrights = [copyright_data] if copyright_data else []
    licenses = [license_data] if license_data else []

    metadata_text = f"{name_file}\n{', '.join(copyrights)} License: {', '.join(licenses)}"

    output_filepath = output_dir() / f"{name_file}.{format}"
    logger.info(f"Saving composite animation: {output_filepath}")

    try:
        if format == "gif":
            timeline_frames[0].save(
                output_filepath, format='GIF', optimize=True,
                append_images=timeline_frames[1:], disposal=2, save_all=True,
                duration=durations_ms, loop=0, comment=metadata_text
            )
        elif format == "webp":
            timeline_frames[0].save(
                output_filepath, format='WEBP', lossless=True,
                append_images=timeline_frames[1:], save_all=True,
                duration=durations_ms, loop=0, comment=metadata_text
            )
        elif format == "apng":
            timeline_frames[0].save(
                output_filepath, format='PNG',
                append_images=timeline_frames[1:], save_all=True,
                duration=durations_ms, loop=0, comment=metadata_text
            )
        return output_filepath
    except Exception as e:
        logger.error({e})


def process_json_file(
        json_file: Path | str,
        target_state: str = None,
        name_file: str = "",
        format: Literal["gif", "webp", "apng"] = "gif",
        item: dict = None,
        layer_configs: list = None
    ) -> None:
    json_file = Path(json_file)
    
    if item and item.get("layers"):
        sprite_name = name_file or item.get("id", "composite_anim")
        process_composite_anim(item, sprite_name, format=format, layer_configs=layer_configs)
        return

    with open(json_file, "r", encoding="utf-8-sig") as json_content:
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
            logger.warning(f"File not found: {spritesheet_file}, skipping state {state_name}")
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
    parser = argparse.ArgumentParser(description="Конвертация спрайтшитов в анимации (GIF, WebP, APNG) на основе JSON описания.")
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
            logger.error(f"Path does not exist: {target_path}")
            continue

        if target_path.is_file() and target_path.suffix == ".json":
            process_json_file(target_path)
        
        elif target_path.is_file() and target_path.suffix == ".png":
            parent_dir = target_path.parent
            meta_json = parent_dir / "meta.json"

            if not meta_json.exists():
                json_files = list(parent_dir.glob("*.json"))
                if not json_files:
                    logger.error(f"No .json file found in {parent_dir} for {target_path.name}")
                    continue
                meta_json = json_files[0]

            target_state_name = target_path.stem
            process_json_file(meta_json, target_state=target_state_name)

        elif target_path.is_dir():
            json_files = sorted(target_path.glob("**/*.json"))
            for json_file in json_files:
                if output_dir() in json_file.parents:
                    continue
                process_json_file(json_file)


if __name__ == "__main__":
    main()