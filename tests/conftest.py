"""Общие фикстуры. Тесты не требуют билда SS14 и PyQt6: RSI-спрайты генерируются на лету.

Запуск из корня проекта:  python -m pytest -q
"""
import json
import sys
from pathlib import Path

import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import config  # noqa: E402  (создаёт settings.ini рядом с проектом, он в .gitignore)

# Цвета четырёх направлений: South, North, East, West
RED, GREEN, BLUE, YELLOW = (255, 0, 0, 255), (0, 255, 0, 255), (0, 0, 255, 255), (255, 255, 0, 255)
DIR_COLORS = [RED, GREEN, BLUE, YELLOW]  # индекс = номер направления в SS14


def centre(img: Image.Image) -> tuple:
    return tuple(img.getpixel((img.width // 2, img.height // 2)))


@pytest.fixture
def build(tmp_path):
    """Игровой билд-пустышка: <tmp>/build/Resources/{Prototypes,Textures,Locale/ru-RU}."""
    root = tmp_path / "build"
    for sub in ("Prototypes", "Textures", "Locale/ru-RU"):
        (root / "Resources" / sub).mkdir(parents=True)
    return root


@pytest.fixture
def app_settings(tmp_path, monkeypatch, build):
    """Подменяет settings.ini на временный и возвращает функцию для его изменения.

    По умолчанию: path_build = <tmp>/build, path_saves = <tmp>/out.
    Рабочая папка тоже временная, чтобы prototypes_cache.db не попадал в проект.
    """
    ini = tmp_path / "settings.ini"
    monkeypatch.setattr(config, "SETTINGS_FILE", ini)
    monkeypatch.chdir(tmp_path)

    def write(path_build=None, path_saves=None):
        pb = build if path_build is None else path_build
        ps = tmp_path / "out" if path_saves is None else path_saves
        ini.write_text(f"[General]\npath_saves = {ps}\npath_build = {pb}\n", encoding="utf-8")
        return Path(pb), Path(ps)

    write()
    return write


@pytest.fixture
def make_rsi(build):
    """Создаёт <build>/Resources/Textures/<rel> с одним состоянием и meta.json."""

    def _make(rel, state, sheet, directions=None, delays=None, size=32,
              copyright_="Made by tester", license_="CC-BY-SA-3.0", target_build=None):
        root = target_build or build
        rsi = root / "Resources" / "Textures" / rel
        rsi.mkdir(parents=True, exist_ok=True)
        sheet.save(rsi / f"{state}.png")
        st = {"name": state}
        if directions:
            st["directions"] = directions
        if delays:
            st["delays"] = delays
        meta = {"version": 1, "size": {"x": size, "y": size}, "license": license_,
                "copyright": copyright_, "states": [st]}
        (rsi / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
        return rsi

    return _make


@pytest.fixture
def four_dir_sheet():
    """2x2 лист: South красный, North зелёный, East синий, West жёлтый."""
    sheet = Image.new("RGBA", (64, 64))
    for colour, (x, y) in zip(DIR_COLORS, [(0, 0), (32, 0), (0, 32), (32, 32)], strict=True):
        sheet.paste(Image.new("RGBA", (32, 32), colour), (x, y))
    return sheet


@pytest.fixture
def make_item(build):
    """Собирает словарь предмета в том же формате, что пишет parsers/writer_data."""

    def _make(rsi, state, layers=None, size=32, **extra):
        rel = rsi.relative_to(build / "Resources" / "Textures").as_posix()
        item = {
            "file": str(build / "Resources" / "Prototypes" / "test.yml"),
            "id": "TestItem",
            "path": str(rsi),
            "state": state,
            "size": {"x": size, "y": size},
            "layers": layers if layers is not None else [{"sprite": rel, "state": state}],
        }
        item.update(extra)
        return item

    return _make
