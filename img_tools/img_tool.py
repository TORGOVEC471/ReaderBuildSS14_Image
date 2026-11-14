import argparse
import json
from pathlib import Path
from PIL import Image
from PIL.PngImagePlugin import PngInfo
from config import settings, BASE_DIR
from logger import logger

from .sprite_processor import render


def output_dir():
    # Папка, куда сохраняются итоговые .png изображения
    # settings.path_saves уже гарантированно возвращает абсолютный путь (благодаря config.py).
    out_dir = settings.path_saves / "Saves" / "images"

    if not out_dir.exists():
        out_dir.mkdir(parents=True, exist_ok=True)

    return out_dir

# Источник по умолчанию теперь тоже привязан к корневой папке проекта/exe, а не к временной _MEIPASS
DEFAULT_SOURCE_DIR = BASE_DIR


def build_composite_image(item: dict, direction: int = 0, frame: int = 0) -> Image.Image | None:
    """Собирает слои предмета в единое изображение PIL."""
    if not item or not item.get("layers"):
        return None
    return render(item, direction=direction, frame=frame)


def save_sprite(
    png_path: Path | str,
    output_name: str = None,
    mode: str = "Original",
    item: dict = None
) -> Path | None:
    """Принимает путь к .png (или словарь item в режиме Сборщика), масштабирует и сохраняет в Saves/images."""
    png_path = Path(png_path)

    copyright_data = ""
    license_data = ""
    tile_w, tile_h = 32, 32
    image = None

    # Если передан item (активен режим "Сборщика")
    if item:
        tile_w = item.get("size", {}).get("x", 32) or 32
        tile_h = item.get("size", {}).get("y", 32) or 32
        image = build_composite_image(item)
        
        copyright_data = item.get("copyright", "")
        license_data = item.get("license", "")

        # Страховка: если в item копирайта нет, но указан путь к текстуре/файлу, попробуем поискать meta.json
        if not copyright_data and item.get("path"):
            texture_path = Path(item.get("path"))
            json_path = texture_path.parent / "meta.json"
            if json_path.exists():
                try:
                    with open(json_path, "r", encoding="utf-8-sig") as f:
                        meta_data = json.load(f)
                        if not copyright_data:
                            copyright_data = meta_data.get("copyright", "")
                        if not license_data:
                            license_data = meta_data.get("license", "")
                except Exception as e:
                    logger.warning(f"Failed to read metadata for composite item from {json_path}: {e}")

    # Стандартный режим отрисовки одного спрайта
    if image is None:
        if not png_path.exists():
            logger.error(f"PNG file not found: {png_path}")
            return None

        json_path = png_path.parent / "meta.json"
        has_directions = False

        if json_path.exists():
            try:
                with open(json_path, "r", encoding="utf-8-sig") as f:
                    data = json.load(f)
                    copyright_data = data.get("copyright", "")
                    license_data = data.get("license", "")

                    if "size" in data:
                        tile_w = data["size"].get("x", 32)
                        tile_h = data["size"].get("y", 32)

                    global_directions = data.get("directions")
                    states = data.get("states", [])
                    current_state = next((s for s in states if s.get("name") == png_path.stem), {})
                    state_directions = current_state.get("directions")

                    directions = state_directions if state_directions is not None else global_directions

                    if isinstance(directions, int) and directions > 1:
                        has_directions = True
                    elif isinstance(directions, (list, tuple)) and len(directions) > 0:
                        has_directions = True

            except Exception as e:
                logger.warning(f"Failed to read metadata from {json_path}: {e}")

        try:
            image = Image.open(png_path).convert("RGBA")
            if mode == "South" and has_directions:
                image = image.crop((0, 0, tile_w, tile_h))
            elif mode == "North" and has_directions:
                image = image.crop((tile_w, 0, tile_w * 2, tile_h))
            elif mode == "East" and has_directions:
                image = image.crop((0, tile_h, tile_w, tile_h * 2))
            elif mode == "West" and has_directions:
                image = image.crop((tile_w, tile_h, tile_w * 2, tile_h * 2))
        except Exception as e:
            logger.error(f"Failed to open sprite {png_path}: {e}")
            return None

    if not output_name:
        output_name = f"{png_path.parent.name}-{png_path.stem}"

    output_filepath = output_dir() / f"{output_name}.png"

    try:
        metadata = PngInfo()
        if copyright_data or license_data:
            metadata.add_text("Copyright", f"{copyright_data} License: {license_data}")

        if mode == "Original":
            SCALE_FACTOR = 1
        else:
            if max(tile_w, tile_h) > 64:
                SCALE_FACTOR = 4
            else:
                SCALE_FACTOR = 8

        new_width = image.width * SCALE_FACTOR
        new_height = image.height * SCALE_FACTOR

        resized_image = image.resize((new_width, new_height), Image.NEAREST)

        logger.info(f"Saving {output_filepath}")
        resized_image.save(output_filepath, format="PNG", pnginfo=metadata)

        return output_filepath

    except Exception as e:
        logger.error(f"Failed to save sprite {png_path}: {e}")
        return None


def process_path(target_path: Path | str, name_file: str = None, mode: str = "Original", item: dict = None) -> None:
    """Обрабатывает переданный путь или словарь item."""
    target_path = Path(target_path)

    if item:
        save_sprite(target_path, name_file, mode, item=item)
        return

    if not target_path.exists():
        logger.error(f"Path does not exist: {target_path}")
        return

    if target_path.is_file() and target_path.suffix.lower() == ".png":
        save_sprite(target_path, name_file, mode)

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
            for png_file in parent_dir.glob("*.png"):
                save_sprite(png_file)

    elif target_path.is_dir():
        png_files = sorted(target_path.glob("**/*.png"))
        for png_file in png_files:
            if output_dir() in png_file.parents:
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
        logger.error(f"Path does not exist: {target_path}")
        return

    with Image.open(target_path) as img:
        width, height = img.size
        return width, height


if __name__ == "__main__":
    main()