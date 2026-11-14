"""Единый рендерер: направления, кадры, видимость слоёв, цвет, смещение."""
import pytest
from PIL import Image

from img_tools.sprite_processor import SpriteLayerProcessor, render
from conftest import DIR_COLORS, RED, GREEN, centre


@pytest.mark.parametrize("direction", range(4))
def test_render_direction_argument(make_rsi, make_item, four_dir_sheet, direction):
    rsi = make_rsi("Test/dir.rsi", "foo", four_dir_sheet, directions=4)
    img = render(make_item(rsi, "foo"), direction=direction)
    assert centre(img) == DIR_COLORS[direction]


def test_render_uses_layer_direction_when_set(make_rsi, make_item, four_dir_sheet):
    """Направление, выбранное в меню «Слои», хранится в layer['direction'] и должно доходить до рендера."""
    rsi = make_rsi("Test/dir.rsi", "foo", four_dir_sheet, directions=4)
    item = make_item(rsi, "foo", layers=[{"sprite": "Test/dir.rsi", "state": "foo", "direction": 1}])
    assert centre(render(item)) == GREEN


def test_layer_direction_beats_global_argument(make_rsi, make_item, four_dir_sheet):
    rsi = make_rsi("Test/dir.rsi", "foo", four_dir_sheet, directions=4)
    item = make_item(rsi, "foo", layers=[{"sprite": "Test/dir.rsi", "state": "foo", "direction": 1}])
    assert centre(render(item, direction=3)) == GREEN


def test_explicit_layer_configs_override(make_rsi, make_item, four_dir_sheet):
    rsi = make_rsi("Test/dir.rsi", "foo", four_dir_sheet, directions=4)
    item = make_item(rsi, "foo")
    cfg = [{"enabled": True, "layer": item["layers"][0], "frame": 0, "direction": 2}]
    assert centre(render(item, overrides={"layer_configs": cfg})) == DIR_COLORS[2]


def test_direction_wraps_around(make_rsi, make_item, four_dir_sheet):
    rsi = make_rsi("Test/dir.rsi", "foo", four_dir_sheet, directions=4)
    assert centre(render(make_item(rsi, "foo"), direction=5)) == GREEN  # 5 % 4 == 1


def test_wrapped_sheet_every_direction_and_frame(make_rsi, make_item):
    """4 направления x 4 кадра в 2 колонки: перенос строк не должен путать кадры."""
    sheet = Image.new("RGBA", (64, 32 * 8))
    for d in range(4):
        for f in range(4):
            flat = d * 4 + f
            sheet.paste(Image.new("RGBA", (32, 32), (d * 60 + 20, f * 60 + 20, 100, 255)),
                        ((flat % 2) * 32, (flat // 2) * 32))
    rsi = make_rsi("Test/wrapped.rsi", "w", sheet, directions=4, delays=[[0.1] * 4] * 4)
    item = make_item(rsi, "w")
    for d in range(4):
        for f in range(4):
            assert centre(render(item, direction=d, frame=f)) == (d * 60 + 20, f * 60 + 20, 100, 255)


def test_hidden_layer_skipped_by_default(make_rsi, make_item, four_dir_sheet):
    rsi = make_rsi("Test/dir.rsi", "foo", four_dir_sheet, directions=4)
    item = make_item(rsi, "foo", layers=[{"sprite": "Test/dir.rsi", "state": "foo", "visible": False}])
    assert centre(render(item))[3] == 0


def test_hidden_layer_can_be_enabled_by_user(make_rsi, make_item, four_dir_sheet):
    rsi = make_rsi("Test/dir.rsi", "foo", four_dir_sheet, directions=4)
    item = make_item(rsi, "foo", layers=[{"sprite": "Test/dir.rsi", "state": "foo", "visible": False}])
    cfg = [{"enabled": True, "layer": item["layers"][0], "frame": 0, "direction": 0}]
    assert centre(render(item, overrides={"layer_configs": cfg})) == RED


def test_disabled_layer_is_skipped(make_rsi, make_item, four_dir_sheet):
    rsi = make_rsi("Test/dir.rsi", "foo", four_dir_sheet, directions=4)
    item = make_item(rsi, "foo")
    cfg = [{"enabled": False, "layer": item["layers"][0], "frame": 0, "direction": 0}]
    assert centre(render(item, overrides={"layer_configs": cfg}))[3] == 0


def test_layers_are_stacked_in_order(make_rsi, make_item):
    red = make_rsi("Test/a.rsi", "a", Image.new("RGBA", (32, 32), (255, 0, 0, 255)))
    make_rsi("Test/b.rsi", "b", Image.new("RGBA", (32, 32), (0, 0, 255, 255)))
    layers = [{"sprite": "Test/a.rsi", "state": "a"}, {"sprite": "Test/b.rsi", "state": "b"}]
    assert centre(render(make_item(red, "a", layers=layers)))[:3] == (0, 0, 255)  # верхний слой побеждает


def test_layer_tint(make_rsi, make_item):
    rsi = make_rsi("Test/w.rsi", "w", Image.new("RGBA", (32, 32), (255, 255, 255, 255)))
    layers = [{"sprite": "Test/w.rsi", "state": "w", "color": "#00ff00"}]
    assert centre(render(make_item(rsi, "w", layers=layers))) == (0, 255, 0, 255)


def test_layer_offset_moves_pixels(make_rsi, make_item):
    rsi = make_rsi("Test/o.rsi", "o", Image.new("RGBA", (32, 32), (255, 0, 0, 255)))
    layers = [{"sprite": "Test/o.rsi", "state": "o", "offset": "0.5, 0"}]  # +16 px вправо
    img = render(make_item(rsi, "o", layers=layers))
    assert img.getpixel((4, 16))[3] == 0     # левая часть опустела
    assert img.getpixel((28, 16))[3] == 255  # правая занята


def test_missing_texture_does_not_crash(make_rsi, make_item, four_dir_sheet):
    rsi = make_rsi("Test/dir.rsi", "foo", four_dir_sheet, directions=4)
    layers = [{"sprite": "Test/dir.rsi", "state": "nope"}, {"sprite": "Test/dir.rsi", "state": "foo"}]
    assert centre(render(make_item(rsi, "foo", layers=layers))) == RED


@pytest.mark.xfail(strict=True, reason="render(): после except нет continue -> UnboundLocalError")
def test_corrupt_texture_is_skipped_not_crash(make_rsi, make_item, four_dir_sheet):
    """Регрессия: битый PNG в одном слое не должен ронять рендер и подменять слой чужой картинкой."""
    good = make_rsi("Test/dir.rsi", "foo", four_dir_sheet, directions=4)
    bad = make_rsi("Test/bad.rsi", "bad", Image.new("RGBA", (32, 32)))
    (bad / "bad.png").write_bytes(b"this is not a png")
    layers = [{"sprite": "Test/bad.rsi", "state": "bad"}, {"sprite": "Test/dir.rsi", "state": "foo"}]
    assert centre(render(make_item(good, "foo", layers=layers))) == RED


@pytest.mark.xfail(strict=True, reason="render(): после except нет continue -> UnboundLocalError")
def test_corrupt_only_layer_gives_empty_canvas(make_rsi, make_item):
    bad = make_rsi("Test/bad.rsi", "bad", Image.new("RGBA", (32, 32)))
    (bad / "bad.png").write_bytes(b"this is not a png")
    img = render(make_item(bad, "bad"))
    assert centre(img)[3] == 0


@pytest.mark.parametrize("raw, expected", [
    ("0, 0.5", (0, -16)),
    ("-0.5,0", (-16, 0)),
    ("1, 1", (32, -32)),
    ("", (0, 0)),
    (None, (0, 0)),
    ("garbage", (0, 0)),
])
def test_parse_offset(raw, expected):
    assert SpriteLayerProcessor.parse_offset(raw) == expected
