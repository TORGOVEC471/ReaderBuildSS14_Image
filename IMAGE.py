import argparse
import json
from pathlib import Path
from PIL import Image
from PIL.PngImagePlugin import PngInfo
import configparser

# Настройки
config = configparser.ConfigParser()
config.read("settings.ini", encoding="utf-8")

path_saves = config["General"]["path_saves"]

# Папка, куда сохраняются итоговые .png изображения
OUTPUT_DIR = Path(path_saves).parent / "Saves/images"
if not OUTPUT_DIR.exists():
    OUTPUT_DIR.mkdir(parents=True)
elif OUTPUT_DIR == ".":
    OUTPUT_DIR = Path(__file__).parent / "Saves/images"

# Путь по умолчанию (если не переданы аргументы)
DEFAULT_SOURCE_DIR = Path(__file__).parent


def save_sprite(png_path: Path | str, output_name: str = None, mode: str = "Original") -> Path | None:
    """
    Принимает путь к .png (Path или str), ресайзит его и сохраняет в Saves/images.
    Оригинальный файл не изменяется.
    Если в meta.json указан параметр directions, берется первое направление (0, 0, tile_w, tile_h)
    """
    png_path = Path(png_path)

    if not png_path.exists():
        print(f"[ERROR] PNG file not found: {png_path}")
        return None

    # Попытка прочитать метаданные из meta.json в той же папке
    json_path = png_path.parent / "meta.json"
    copyright_data = ""
    license_data = ""
    tile_w, tile_h = 32, 32  # Дефолтный размер кадра, если meta.json нет
    has_directions = False

    if json_path.exists():
        try:
            with open(json_path, "r", encoding="utf-8-sig") as f:
                data = json.load(f)
                copyright_data = data.get("copyright", "")
                license_data = data.get("license", "")
                # Получаем размер ОДНОГО кадра

                if "size" in data:
                    tile_w = data["size"].get("x", 32)
                    tile_h = data["size"].get("y", 32)

                # Проверяем directions на глобальном уровне
                global_directions = data.get("directions")

                # Ищем текущий state по имени файла
                states = data.get("states", [])
                current_state = next((s for s in states if s.get("name") == png_path.stem), {})
                state_directions = current_state.get("directions")

                # Используем directions из state, если есть, иначе глобальный
                directions = state_directions if state_directions is not None else global_directions

                # Проверяем, заданы ли направления (число > 1 или непустой список)
                if isinstance(directions, int) and directions > 1:
                    has_directions = True
                elif isinstance(directions, (list, tuple)) and len(directions) > 0:
                    has_directions = True

        except Exception as e:
            print(f"[WARN] Failed to read metadata from {json_path}: {e}")

    # Формируем имя итогового файла: папка-название.png (например: items-row.png)
    if not output_name:
        output_name = f"{png_path.parent.name}-{png_path.stem}"

    output_filepath = OUTPUT_DIR / f"{output_name}.png"

    try:
        with Image.open(png_path) as image:
            # Запись метаданных
            metadata = PngInfo()
            if copyright_data or license_data:
                metadata.add_text("Copyright", f"{copyright_data} License: {license_data}")

            if mode == "South": # лицо
                if has_directions:
                    image = image.crop((0, 0, tile_w, tile_h))
            if mode == "North": # спина
                # Если есть directions — обрезаем до первого направления (первого кадра)
                if has_directions:
                    image = image.crop((tile_w, 0, tile_w*2, tile_h))
            if mode == "East": # правый профиль
                # Если есть directions — обрезаем до первого направления (первого кадра)
                if has_directions:
                    image = image.crop((0, tile_h, tile_w, tile_h*2))
            if mode == "West": # левый профиль
                # Если есть directions — обрезаем до первого направления (первого кадра)
                if has_directions:
                    image = image.crop((tile_w, tile_h, tile_w*2, tile_h*2))

            if mode == "Original":
                SCALE_FACTOR = 1
            else:
                # Пропорциональное изменение размера по ширине до 256px
                # Если объект больше 64px, уменьшаем scale_factor до 4
                if max(tile_w, tile_h) > 64:
                    SCALE_FACTOR = 4
                else:
                    SCALE_FACTOR = 8 # Размер умножения

            new_width = image.width * SCALE_FACTOR
            new_height = image.height * SCALE_FACTOR

            resized_image = image.resize((new_width, new_height), Image.NEAREST)

            print(f"[INFO] Saving {output_filepath}")
            resized_image.save(output_filepath, format="PNG", pnginfo=metadata)

        return output_filepath

    except Exception as e:
        print(f"[ERROR] Failed to save sprite {png_path}: {e}")
        return None


def process_path(target_path: Path | str, name_file: str, mode: str) -> None:
    """Обрабатывает переданный путь: файл .png, файл .json или папку."""
    target_path = Path(target_path)

    if not target_path.exists():
        print(f"[ERROR] Path does not exist: {target_path}")
        return

    # 1. Если передан конкретный .png файл
    if target_path.is_file() and target_path.suffix.lower() == ".png":
        save_sprite(target_path, name_file, mode)

    # 2. Если передан .json файл — обрабатываем все .png состояния из него
    elif target_path.is_file() and target_path.suffix.lower() == ".json":
        parent_dir = target_path.parent
        try:
            with open(target_path, "r", encoding="utf-8-sig") as f:
                data = json.load(f)
            for state in data.get("states", []):
                state_name = state.get("name")
                if state_name:
                    png_file = parent_dir / f"{state_name}.png"
                    if png_file.exists():
                        save_sprite(png_file)
        except Exception:
            # В случае ошибки парсинга json обрабатываем все png рядом
            for png_file in parent_dir.glob("*.png"):
                save_sprite(png_file)

    # 3. Если передана папка — ищем все .png рекурсивно
    elif target_path.is_dir():
        png_files = sorted(target_path.glob("**/*.png"))
        for png_file in png_files:
            # Игнорируем файлы, которые уже лежат в папке результатов
            if OUTPUT_DIR in png_file.parents:
                continue
            save_sprite(png_file)


def main():
    parser = argparse.ArgumentParser(
        description="Конвертация и изменением размера PNG спрайтов в папку Saves."
    )
    parser.add_argument(
        "paths",
        nargs="*",
        type=Path,
        default=[DEFAULT_SOURCE_DIR],
        help="Пути к папкам, конкретным .png или .json файлам.",
    )
    args = parser.parse_args()

    for path in args.paths:
        process_path(path)

def info_size_image(target_path: Path | str) -> None:
    target_path = Path(target_path)

    if not target_path.exists():
        print(f"[ERROR] Path does not exist: {target_path}")
        return

    with Image.open(target_path) as img:
        width, height = img.size
        return width, height


if __name__ == "__main__":
    main()