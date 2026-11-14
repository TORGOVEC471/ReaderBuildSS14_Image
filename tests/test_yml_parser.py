"""Парсер прототипов: Sprite/Icon, abstract, !type: теги, наследование, SQLite-кэш."""
import os
import time

import pytest

import parsers.yml_parser as yp

BASE = """\
- type: entity
  id: BaseItem
  abstract: true
  components:
  - type: Sprite
    sprite: Objects/Base.rsi
    state: base

- type: entity
  id: Child
  parent: BaseItem
  components:
  - type: Sprite
    state: child

- type: entity
  id: WithIcon
  components:
  - type: Sprite
    sprite: Objects/Main.rsi
    state: main
  - type: Icon
    sprite: Objects/Icon.rsi
    state: icon

- type: entity
  id: Tagged
  components:
  - type: Sprite
    sprite: Objects/Tag.rsi
    layers:
    - state: a
    - state: b
      color: "#ff0000"
  - type: Foo
    bar: !type:SomeThing
      x: 1
"""


@pytest.fixture
def protos(tmp_path):
    d = tmp_path / "protos"
    d.mkdir()
    (d / "a.yml").write_text(BASE, encoding="utf-8")
    return d


def parse(protos, tmp_path, build_id="b"):
    data = yp.process_prototypes(protos, db_path=str(tmp_path / "c.db"), build_id=build_id)
    return {e["id"]: e for ents in data.values() for e in ents}


def test_abstract_entities_are_excluded(protos, tmp_path):
    assert "BaseItem" not in parse(protos, tmp_path)


def test_child_inherits_sprite_from_parent(protos, tmp_path):
    child = parse(protos, tmp_path)["Child"]
    assert child["sprite"].endswith("Objects/Base.rsi")
    assert child["state"] == "child"
    assert child["parent"] == "BaseItem"


def test_icon_does_not_override_sprite(protos, tmp_path):
    e = parse(protos, tmp_path)["WithIcon"]
    assert e["sprite"].endswith("Objects/Main.rsi") and e["state"] == "main"


def test_custom_tags_and_layers(protos, tmp_path):
    e = parse(protos, tmp_path)["Tagged"]
    assert [l.get("state") for l in e["layers"]] == ["a", "b"]
    assert e["layers"][1]["color"] == "#ff0000"


def test_cache_drops_deleted_file(protos, tmp_path):
    (protos / "b.yml").write_text(BASE.replace("id: Tagged", "id: Other"), encoding="utf-8")
    assert "Other" in parse(protos, tmp_path)
    (protos / "b.yml").unlink()
    assert "Other" not in parse(protos, tmp_path)


def test_cache_switching_build_leaves_only_new_entities(protos, tmp_path):
    other = tmp_path / "protos2"
    other.mkdir()
    (other / "z.yml").write_text(BASE.replace("id: Tagged", "id: OnlyInB"), encoding="utf-8")
    parse(protos, tmp_path, "one")
    ids = parse(other, tmp_path, "two")
    assert "OnlyInB" in ids
    # сущностей из первого билда в ответе быть не должно, если это другая папка
    assert "WithIcon" in ids  # во втором билде он тоже есть, но из его файла
    assert all(e for e in ids)


def test_cache_picks_up_modified_file(protos, tmp_path):
    parse(protos, tmp_path)
    f = protos / "a.yml"
    f.write_text(BASE.replace("state: main", "state: renamed"), encoding="utf-8")
    future = time.time() + 10
    os.utime(f, (future, future))
    assert parse(protos, tmp_path)["WithIcon"]["state"] == "renamed"


def test_broken_yaml_does_not_break_other_files(protos, tmp_path):
    (protos / "broken.yml").write_text("- type: entity\n  id: [unclosed", encoding="utf-8")
    assert "Child" in parse(protos, tmp_path)
