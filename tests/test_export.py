"""Экспорт PNG/GIF/WebP/APNG: путь сохранения, направление слоя, copyright/license."""
import pytest
from PIL import Image

import img_tools.gif_tool as gif_tool
import img_tools.img_tool as img_tool
from conftest import DIR_COLORS, GREEN, centre


@pytest.fixture
def composite(make_rsi, make_item, four_dir_sheet):
    rsi = make_rsi("Test/dir.rsi", "foo", four_dir_sheet, directions=4)
    layers = [{"sprite": "Test/dir.rsi", "state": "foo", "direction": 1}]
    return make_item(rsi, "foo", layers=layers)


def test_output_dir_follows_settings_change(app_settings, tmp_path):
    first = img_tool.output_dir()
    assert first == tmp_path / "out" / "Saves" / "images" and first.is_dir()
    app_settings(path_saves=tmp_path / "other")
    assert img_tool.output_dir() == tmp_path / "other" / "Saves" / "images"
    assert gif_tool.output_dir().parent.parent == tmp_path / "other"


def test_output_dir_relative_path_is_resolved_against_project(app_settings):
    import config
    app_settings(path_saves=".")
    assert img_tool.output_dir() == config.BASE_DIR / "Saves" / "images"


def test_save_sprite_composite_uses_layer_direction(app_settings, composite):
    out = img_tool.save_sprite("ignored.png", "comp", mode="Original", item=composite)
    with Image.open(out) as im:
        assert centre(im.convert("RGBA")) == GREEN


def test_save_sprite_composite_writes_item_copyright(app_settings, composite):
    composite.update(copyright="Item author", license="MIT")
    out = img_tool.save_sprite("x.png", "c1", item=composite)
    with Image.open(out) as im:
        assert im.text["Copyright"] == "Item author License: MIT"


@pytest.mark.xfail(strict=True, reason="img_tool: Path(item['path']).parent/meta.json — на уровень выше, чем нужно")
def test_save_sprite_composite_copyright_falls_back_to_meta_json(app_settings, composite):
    """item['path'] указывает на сам .rsi, значит meta.json лежит внутри него, а не рядом."""
    composite.pop("copyright", None)
    composite.pop("license", None)
    out = img_tool.save_sprite("x.png", "c2", item=composite)
    with Image.open(out) as im:
        assert "Made by tester" in im.text.get("Copyright", "")


def test_save_sprite_single_png_reads_meta_and_crops_direction(app_settings, make_rsi, four_dir_sheet):
    rsi = make_rsi("Test/dir.rsi", "foo", four_dir_sheet, directions=4)
    out = img_tool.save_sprite(rsi / "foo.png", "north", mode="North")
    with Image.open(out) as im:
        assert im.size == (32 * 8, 32 * 8)
        assert centre(im.convert("RGBA")) == DIR_COLORS[1]
        assert "Made by tester" in im.text["Copyright"]


def test_save_sprite_original_keeps_native_size(app_settings, make_rsi, four_dir_sheet):
    rsi = make_rsi("Test/dir.rsi", "foo", four_dir_sheet, directions=4)
    out = img_tool.save_sprite(rsi / "foo.png", "orig", mode="Original")
    with Image.open(out) as im:
        assert im.size == (64, 64)


def test_save_sprite_missing_file_returns_none(app_settings, tmp_path):
    assert img_tool.save_sprite(tmp_path / "nope.png") is None


@pytest.mark.parametrize("fmt", ["gif", "webp", "apng"])
def test_save_anim_creates_file(app_settings, fmt):
    sheet = Image.new("RGBA", (64, 32), (255, 0, 0, 255))
    sheet.paste(Image.new("RGBA", (32, 32), (0, 0, 255, 255)), (32, 0))
    out = gif_tool.save_anim(sheet, f"a_{fmt}", 32, 32, [0.1, 0.1], "Author", "CC0", format=fmt, frame_count=2)
    assert out.exists() and out.suffix == f".{fmt}"
    with Image.open(out) as im:
        assert im.n_frames == 2


def test_save_anim_picks_direction_on_wrapped_sheet(app_settings):
    """2 направления x 2 кадра, лист 2 колонки: направление 1 это вторая строка."""
    sheet = Image.new("RGBA", (64, 64))
    colours = [(255, 0, 0), (250, 0, 0), (0, 255, 0), (0, 250, 0)]
    for i, c in enumerate(colours):
        sheet.paste(Image.new("RGBA", (32, 32), (*c, 255)), ((i % 2) * 32, (i // 2) * 32))
    out = gif_tool.save_anim(sheet, "dirs", 32, 32, [0.1, 0.1], "A", "L",
                             format="apng", direction=1, directions_count=2, frame_count=2)
    with Image.open(out) as im:
        im.seek(0)
        assert centre(im.convert("RGBA"))[1] > 200  # зелёный, а не красный


@pytest.mark.parametrize("fmt", [
    "gif",
    pytest.param("webp", marks=pytest.mark.xfail(strict=True, reason="PIL игнорирует comment= для WebP: copyright теряется")),
    pytest.param("apng", marks=pytest.mark.xfail(strict=True, reason="PIL игнорирует comment= для PNG/APNG: нужен pnginfo")),
])
def test_composite_anim_runs_and_contains_copyright(app_settings, make_rsi, make_item, fmt):
    sheet = Image.new("RGBA", (64, 32), (255, 0, 0, 255))
    sheet.paste(Image.new("RGBA", (32, 32), (0, 0, 255, 255)), (32, 0))
    rsi = make_rsi("Test/anim.rsi", "a", sheet, delays=[[0.1, 0.1]])
    item = make_item(rsi, "a", copyright="Item author", license="MIT")
    gif_tool.process_composite_anim(item, "composite", fmt)
    files = list(gif_tool.output_dir().glob("composite*"))
    assert files, "анимация не создана"
    assert b"Item author" in files[0].read_bytes()
