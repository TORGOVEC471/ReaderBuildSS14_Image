import json
from pathlib import Path
import parsers.yml_parser as YMLF
import parsers.ftl_parser as FTLR
from config import DATA_FILE, settings, LOCALE
from logger import logger

DIR_TEXTURES = 'Resources/Textures'
DIR_PROTOTYPES = 'Resources/Prototypes'
DIR_FTL_LOCALE = f'Resources/Locale/{LOCALE}'


def load_rsi_info(rsi_path: Path) -> tuple[dict, list[str], str | None, str | None, str | None]:
    """Загружает метаданные RSI (размер, список стейтов, дефолтный стейт, copyright и license)."""
    meta_path = rsi_path / "meta.json"
    size = {"x": 32, "y": 32}
    states = []
    default_state = None
    copyright_data = None
    license_data = None

    if meta_path.is_file():
        try:
            with open(meta_path, "r", encoding="utf-8-sig") as f:
                data = json.load(f)
                size = data.get("size", size)
                copyright_data = data.get("copyright")
                license_data = data.get("license")
                raw_states = data.get("states", [])
                if isinstance(raw_states, list):
                    states = [s.get("name") for s in raw_states if s.get("name")]
                    if states:
                        default_state = states[0]
        except Exception as e:
            logger.warning(f"Failed to read metadata from {meta_path}: {e}")

    # Добавляем стейты из названий PNG-файлов, если они есть
    if rsi_path.is_dir():
        png_states = [file.stem for file in rsi_path.glob("*.png") if file.is_file()]
        states = list(dict.fromkeys(states + png_states))

    return size, states, default_state, copyright_data, license_data


def find_ftl_info(entity: dict, parsed_ftl: dict) -> tuple[str | None, str | None, str | None]:
    """Ищет имя, описание и суффикс в FTL с учетом фоллбэка по цепочке родителей."""
    ftl_key = f"ent-{entity['id']}"
    local_info = parsed_ftl.get(ftl_key, {})

    name_ftl = local_info.get('name')
    desc_ftl = local_info.get('desc')
    suffix_ftl = local_info.get('suffix')

    if (not name_ftl or not desc_ftl) and entity.get('parents_chain'):
        for parent_id in entity['parents_chain']:
            parent_key = f"ent-{parent_id}"
            if parent_key in parsed_ftl:
                p_info = parsed_ftl[parent_key]
                if not name_ftl:
                    name_ftl = p_info.get('name')
                if not desc_ftl:
                    desc_ftl = p_info.get('desc')
                if name_ftl and desc_ftl:
                    break

    return name_ftl, desc_ftl, suffix_ftl


def save_data_build(target_dir_yml: Path = None, target_dir_ftl: Path = None):
    # Динамически получаем актуальный путь билда из настроек в момент вызова
    path_build = settings.path_build
    
    if target_dir_yml is None:
        target_dir_yml = path_build / DIR_PROTOTYPES
    if target_dir_ftl is None:
        target_dir_ftl = path_build / DIR_FTL_LOCALE

    logger.info(f"Начинаем запись в {DATA_FILE} для локали: {LOCALE} (Путь билда: {path_build})")
    sprite_data_list = []
    parsed_data = YMLF.process_prototypes(target_dir_yml)
    
    parsed_ftl = FTLR.load_ftl_directory(target_dir_ftl)

    for file_name, entities in parsed_data.items():
        normalized_file = Path(file_name).as_posix()
        
        for entity in entities:
            sprite = entity.get('sprite')
            if not sprite:
                continue

            rsi_path = path_build / DIR_TEXTURES / sprite.removeprefix("/Textures/")
            size, states, default_state, copyright_data, license_data = load_rsi_info(rsi_path)
            state_value = entity.get('state') or default_state
            name_ftl, desc_ftl, suffix_ftl = find_ftl_info(entity, parsed_ftl)

            sprite_data_list.append({
                "file": normalized_file,
                "id": entity['id'],
                "name_ftl": name_ftl,
                "desc_ftl": desc_ftl,
                "suffix_ftl": suffix_ftl,
                "suffix": entity.get('suffix'),
                "parent": entity.get("parent"),
                "parents_chain": entity.get('parents_chain'),
                "sprite": sprite,
                "path": rsi_path,
                "state": state_value,
                "states": states,
                "layers": entity.get('layers'),
                "size": size,
                "copyright": copyright_data,   # <--- Добавлено
                "license": license_data        # <--- Добавлено
            })

    with open(DATA_FILE, "w", encoding="utf-8") as file:
        json.dump(
            sprite_data_list, 
            file, 
            ensure_ascii=False, 
            indent=4, 
            default=lambda obj: str(obj) if isinstance(obj, Path) else obj
        )
    
    logger.info(f"Файлы успешно записаны в {DATA_FILE}")


if __name__ == "__main__":
    save_data_build()