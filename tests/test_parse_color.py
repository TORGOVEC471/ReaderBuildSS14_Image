import pytest

from img_tools.parse_color import parse_color
from img_tools.sprite_processor import apply_tint_to_image
from PIL import Image


@pytest.mark.parametrize("raw, expected", [
    ("#ff0000", (255, 0, 0, 255)),
    ("#f00", (255, 0, 0, 255)),
    ("#ff000080", (255, 0, 0, 128)),      # RRGGBBAA, а не AARRGGBB
    ("#f008", (255, 0, 0, 136)),
    ("Red", (255, 0, 0, 255)),
    ("red", (255, 0, 0, 255)),
    ("Yellow", (255, 255, 0, 255)),
])
def test_parse_color_valid(raw, expected):
    assert tuple(parse_color(raw)) == expected


@pytest.mark.parametrize("raw", ["", "notacolor", "#12345", None])
def test_parse_color_invalid_falls_back_to_white(raw):
    assert tuple(parse_color(raw)) == (255, 255, 255, 255)


def test_tint_multiplies_rgb_and_alpha():
    white = Image.new("RGBA", (1, 1), (255, 255, 255, 255))
    assert apply_tint_to_image(white, "#ff000080").getpixel((0, 0)) == (255, 0, 0, 128)


def test_tint_keeps_transparent_pixels_transparent():
    clear = Image.new("RGBA", (1, 1), (255, 255, 255, 0))
    assert apply_tint_to_image(clear, "#ff0000").getpixel((0, 0))[3] == 0
