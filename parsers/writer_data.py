import json
from pathlib import Path
import parsers.yml_parser as YMLF
import parsers.ftl_parser as FTLR
from config import PATH_BUILD, DATA_FILE

DIR_TEXTURES = 'Resources/Textures'
DIR_PROTOTYPES = 'Resources/Prototypes'
DIR_FTL_RU = 'Resources/Locale/ru-RU'

TARGET_DIR_YML = PATH_BUILD / DIR_PROTOTYPES
TARGET_DIR_FTL = PATH_BUILD / DIR_FTL_RU


def load_rsi_info(rsi_path: Path) -> tuple[dict, list[str], str | None]:
    """Загружает метаданные RSI (размер, список стейтов и дефолтный стейт) за один раз."""
    meta_path = rsi_path / "meta.json"
    size = {"x": 32, "y": 32}
    states = []
    default_state = None

    if meta_path.is_file():
        try:
            with open(meta_path, "r", encoding="utf-8-sig") as f:
                data = json.load(f)
                size = data.get("size", size)
                raw_states = data.get("states", [])
                if isinstance(raw_states, list):
                    states = [s.get("name") for s in raw_states if s.get("name")]
                    if states:
                        default_state = states[0]
        except Exception as e:
            print(f"[WARN] Failed to read metadata from {meta_path}: {e}")

    # Добавляем стейты из названий PNG-файлов, если они есть
    if rsi_path.is_dir():
        png_states = [file.stem for file in rsi_path.glob("*.png") if file.is_file()]
        # Объединяем списки без дубликатов, сохраняя порядок
        states = list(dict.fromkeys(states + png_states))

    return size, states, default_state


def find_ftl_info(entity: dict, parsed_ftl: dict) -> tuple[str | None, str | None, str | None]:
    """Ищет имя, описание и суффикс в FTL с учетом фоллбэка по цепочке родителей."""
    ftl_key = f"ent-{entity['id']}"
    local_info = parsed_ftl.get(ftl_key, {})

    name_ftl = local_info.get('name')
    desc_ftl = local_info.get('desc')
    suffix_ftl = local_info.get('suffix')

    # Фоллбэк: если своего FTL нет, подтягиваем из родителей
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


def save_data_build(target_dir_yml: Path, target_dir_ftl: Path):
    sprite_data_list = []
    parsed_data = YMLF.process_prototypes(target_dir_yml)
    parsed_ftl = FTLR.load_ftl_directory(target_dir_ftl)

    for file_name, entities in parsed_data.items():
        normalized_file = Path(file_name).as_posix()
        
        for entity in entities:
            sprite = entity.get('sprite')
            if not sprite:
                continue

            # Формируем путь к текстуре
            rsi_path = PATH_BUILD / DIR_TEXTURES / sprite.removeprefix("/Textures/")
            
            # Получаем всю информацию по RSI за один вызов
            size, states, default_state = load_rsi_info(rsi_path)
            
            # Если state не задан в сущности, берем дефолтный из RSI
            state_value = entity.get('state') or default_state

            # Получаем локализацию
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
                "size": size
            })

    # Сохранение результатов в JSON
    with open(DATA_FILE, "w", encoding="utf-8") as file:
        json.dump(
            sprite_data_list, 
            file, 
            ensure_ascii=False, 
            indent=4, 
            default=lambda obj: str(obj) if isinstance(obj, Path) else obj
        )
    
    print(f"Файлы успешно записаны в {DATA_FILE}")


# --- Пример использования ---
if __name__ == "__main__":
    save_data_build(TARGET_DIR_YML, TARGET_DIR_FTL)