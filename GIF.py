import numpy as np
import json
import os
import argparse

from pathlib import Path
from chardet import UniversalDetector
from PIL import Image
import configparser

# Настройки
config = configparser.ConfigParser()

SETTINGS_FILE = "settings.ini"
if not Path(SETTINGS_FILE).exists():
    config["General"] = {
        "path_saves":".",
        "path_build":"."
    }
    # Записываем настройки в файл
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        config.write(f)
    print(f"Файл {SETTINGS_FILE} успешно создан.")
else:
    print(f"Файл {SETTINGS_FILE} уже существует.")

config.read("settings.ini", encoding="utf-8")

path_saves = config["General"]["path_Saves"]

# Папка, куда сохраняются итоговые .gif анимации
OUTPUT_DIR = Path(path_saves).parent / "Saves/animations"
if not OUTPUT_DIR.exists():
    OUTPUT_DIR.mkdir(parents=True)
elif OUTPUT_DIR == ".":
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
        image_license: str
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

    metadata_text = f"{name} - {image_copyright} License: {image_license}"
    output_filepath = OUTPUT_DIR / f"{name}.gif"
    
    # Pillow принимает время кадра в миллисекундах (0.2 сек -> 200 мс)
    durations_ms = [int(d * 1000) if d < 10 else int(d) for d in delays[:len(frames)]]

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


def process_json_file(json_file: Path | str, target_state: str = None, name_file: str = "") -> None:
    """
    Обрабатывает один конкретный .json файл.
    Если передан target_state, обрабатывает ТОЛЬКО это состояние.
    """
    # если строка то делаем Path
    json_file = Path(json_file)

    check_and_reencode_utf_sig(json_file)
    
    with open(json_file, "r", encoding="utf-8") as json_content:
        data = json.load(json_content)
        
    copyright_data = data.get('copyright', '')
    license_data = data.get('license', '')

    for state in data.get('states', []):
        state_name = state.get("name")

        # Если передали конкретный файл/стейт, остальные прогоняем мимо
        if target_state and state_name != target_state:
            continue

        if "delays" in state:
            sprite_name = name_file or f"{json_file.parent.name}-{state_name}"
            state_delays = np.array(state["delays"]).flatten().tolist()
            
            # .png ищется в той же папке, где лежит .json
            spritesheet_file = json_file.parent / f"{state_name}.png"

            if not spritesheet_file.exists():
                print(f"[WARN] File not found: {spritesheet_file}, skipping state {state_name}")
                continue

            # size.x = ширина (width), size.y = высота (height)
            tile_width = data['size']['x']
            tile_height = data['size']['y']

            save_anim(
                sprite=spritesheet_file,
                name=sprite_name,
                delays=state_delays,
                tile_w=tile_width,
                tile_h=tile_height,
                image_copyright=copyright_data,
                image_license=license_data,
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