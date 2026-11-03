import argparse
import json
from pathlib import Path
from PIL import Image
from PIL.PngImagePlugin import PngInfo
from config import PATH_SAVES
from logger import logger

from .sprite_processor import SpriteLayerProcessor

# Папка, куда сохраняются итоговые .png изображения
OUTPUT_DIR = Path(PATH_SAVES).parent / "Saves/images"
if not OUTPUT_DIR.exists():
    OUTPUT_DIR.mkdir(parents=True)
elif OUTPUT_DIR == Path("."):
    OUTPUT_DIR = Path(__file__).parent / "Saves/images"

DEFAULT_SOURCE_DIR = Path(__file__).parent


def apply_tint_to_image(img: Image.Image, color_hex: str) -> Image.Image:
    """Накладывает цвет (tint) путем умножения RGB каналов с сохранением объёма и текстуры."""
    color_hex = str(color_hex).lstrip("#")
    if len(color_hex) < 6:
        return img

    try:
        r_t = int(color_hex[0:2], 16)
        g_t = int(color_hex[2:4], 16)
        b_t = int(color_hex[4:6], 16)
    except ValueError:
        return img

    r, g, b, a = img.split()
    r = r.point(lambda i: int(i * r_t / 255))
    g = g.point(lambda i: int(i * g_t / 255))
    b = b.point(lambda i: int(i * b_t / 255))
    return Image.merge("RGBA", (r, g, b, a))


def build_composite_image(item: dict, mode: str = "Original") -> Image.Image | None:
    """Собирает слои предмета в единое изображение PIL с учётом видимости, цвета, offset, кадров и ракурса."""
    native_w = item.get("size", {}).get("x", 32) or 32
    native_h = item.get("size", {}).get("y", 32) or 32

    layers = item.get("layers", [])
    if not layers:
        return None

    base_textures_path = SpriteLayerProcessor.get_base_textures_path(item)
    item_state = item.get("state", "default")

    canvas = Image.new("RGBA", (native_w, native_h), (0, 0, 0, 0))

    for layer in layers:
        # Проверяем видимость слоя
        if not layer.get("enabled", layer.get("visible", True)):
            continue

        ldir = base_textures_path / layer.get("sprite") if layer.get("sprite") else Path(item.get("path", ""))
        layer_file_path, state_name = SpriteLayerProcessor.resolve_layer_file(item, layer, base_textures_path, item_state)

        if not layer_file_path or not layer_file_path.exists() or layer_file_path.is_dir():
            continue

        try:
            layer_img = Image.open(layer_file_path).convert("RGBA")
        except Exception as e:
            logger.warning(f"Failed to open layer image {layer_file_path}: {e}")
            continue

        fw, fh = layer_img.width, layer_img.height

        # Анализируем метаданные через общий класс
        f_count, _, _, has_directions = SpriteLayerProcessor.parse_meta_and_frames(
            layer_file_path, ldir, state_name, native_w, native_h
        )

        frame_idx = layer.get("frame", 0)
        selected_dir = layer.get("direction", 0)

        # Вырезание кадра и направления (сетка)
        if (fw > native_w or fh > native_h) and (fw % native_w == 0) and (fh % native_h == 0):
            col, row = SpriteLayerProcessor.calculate_grid_coords(
                fw, fh, native_w, native_h, selected_dir, frame_idx, f_count
            )
            layer_img = layer_img.crop((col * native_w, row * native_h, (col + 1) * native_w, (row + 1) * native_h))

        # Определение ракурса по режиму (статическая сборка)
        layer_img = SpriteLayerProcessor.apply_static_mode_crop(layer_img, mode, native_w, native_h, has_directions)

        # Применение цвета (tint)
        if layer.get("color"):
            layer_img = apply_tint_to_image(layer_img, layer["color"])

        # Центрирование и смещение (offset)
        lw, lh = layer_img.size
        center_x = (native_w - lw) // 2
        center_y = (native_h - lh) // 2

        offset_x, offset_y = SpriteLayerProcessor.parse_offset(layer.get("offset"), native_w, native_h)
        final_x = center_x + offset_x
        final_y = center_y + offset_y

        temp_canvas = Image.new("RGBA", (native_w, native_h), (0, 0, 0, 0))
        temp_canvas.paste(layer_img, (final_x, final_y))
        canvas = Image.alpha_composite(canvas, temp_canvas)

    return canvas


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
        image = build_composite_image(item, mode)

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

    output_filepath = OUTPUT_DIR / f"{output_name}.png"

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
        logger.error(f"Path does not exist: {target_path}")
        return

    with Image.open(target_path) as img:
        width, height = img.size
        return width, height


if __name__ == "__main__":
    main()