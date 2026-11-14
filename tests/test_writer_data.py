"""Сборка data.json: пути из текущих настроек, copyright/license, имена из .ftl."""
import json

import pytest

import parsers.writer_data as wd

YML = """\
- type: entity
  id: Foo
  parent: BaseFoo
  components:
  - type: Sprite
    sprite: Objects/foo.rsi
    state: foo
- type: entity
  id: BaseFoo
  abstract: true
"""
FTL = """\
ent-BaseFoo = Базовая штука
    .desc = Описание родителя.
ent-Foo = Штука
"""


@pytest.fixture
def data_file(tmp_path, monkeypatch):
    f = tmp_path / "data.json"
    monkeypatch.setattr(wd, "DATA_FILE", f)
    return f


def fill(build_root, make_rsi, image, yml=YML):
    make_rsi("Objects/foo.rsi", "foo", image, target_build=build_root)
    (build_root / "Resources/Prototypes/foo.yml").write_text(yml, encoding="utf-8")
    (build_root / "Resources/Locale/ru-RU/foo.ftl").write_text(FTL, encoding="utf-8")


def test_records_contain_meta_and_ftl(app_settings, data_file, build, make_rsi, four_dir_sheet):
    fill(build, make_rsi, four_dir_sheet)
    wd.save_data_build()
    rec = {r["id"]: r for r in json.loads(data_file.read_text(encoding="utf-8"))}["Foo"]
    assert rec["copyright"] == "Made by tester" and rec["license"] == "CC-BY-SA-3.0"
    assert rec["name_ftl"] == "Штука"
    assert rec["desc_ftl"] == "Описание родителя."  # описание берётся у родителя
    assert rec["size"] == {"x": 32, "y": 32}
    assert rec["state"] == "foo"
    assert rec["path"].replace("\\", "/").endswith("Textures/Objects/foo.rsi")


def test_abstract_entities_not_written(app_settings, data_file, build, make_rsi, four_dir_sheet):
    fill(build, make_rsi, four_dir_sheet)
    wd.save_data_build()
    assert "BaseFoo" not in {r["id"] for r in json.loads(data_file.read_text(encoding="utf-8"))}


def test_path_follows_build_change_without_restart(app_settings, data_file, build, tmp_path, make_rsi, four_dir_sheet):
    fill(build, make_rsi, four_dir_sheet)
    second = tmp_path / "build2"
    for sub in ("Prototypes", "Textures", "Locale/ru-RU"):
        (second / "Resources" / sub).mkdir(parents=True)
    fill(second, make_rsi, four_dir_sheet)
    app_settings(path_build=second)
    wd.save_data_build()
    rec = json.loads(data_file.read_text(encoding="utf-8"))[0]
    assert "build2" in rec["path"]


def test_load_rsi_info_missing_meta_gives_defaults(tmp_path):
    (tmp_path / "x.rsi").mkdir()
    (tmp_path / "x.rsi" / "only.png").write_bytes(b"")
    size, states, default, cr, lic = wd.load_rsi_info(tmp_path / "x.rsi")
    assert size == {"x": 32, "y": 32} and states == ["only"] and default is None and cr is None and lic is None


def test_load_rsi_info_reads_bom_meta(tmp_path):
    rsi = tmp_path / "x.rsi"
    rsi.mkdir()
    (rsi / "meta.json").write_text('{"size":{"x":48,"y":48},"copyright":"c","license":"l","states":[{"name":"s"}]}',
                                   encoding="utf-8-sig")
    size, states, default, cr, lic = wd.load_rsi_info(rsi)
    assert size["x"] == 48 and default == "s" and (cr, lic) == ("c", "l")
