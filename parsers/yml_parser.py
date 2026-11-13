from functools import lru_cache
from pathlib import Path
import json
import sqlite3
import yaml
from logger import logger

# --- 1. Быстрый кастомный SafeLoader с откатом на стандартный ---
try:
    from yaml import CSafeLoader as YamlSafeLoader
except ImportError:
    from yaml import SafeLoader as YamlSafeLoader

class SS14YamlLoader(YamlSafeLoader):
    pass

def ignore_unknown_tags(loader, tag_suffix, node):
    if isinstance(node, yaml.MappingNode):
        return loader.construct_mapping(node)
    elif isinstance(node, yaml.SequenceNode):
        return loader.construct_sequence(node)
    return loader.construct_scalar(node)

SS14YamlLoader.add_multi_constructor('!', ignore_unknown_tags)


# --- 2. Вспомогательные функции ---

def process_layers(raw_layers, default_sprite):
    """Обрабатывает массив слоев, подставляя общий sprite элемента."""
    if not raw_layers:
        return []

    processed = []
    for layer in raw_layers:
        if isinstance(layer, dict):
            layer_copy = layer.copy()
            if not layer_copy.get('sprite') and default_sprite:
                layer_copy['sprite'] = default_sprite

            if isinstance(layer_copy.get('state'), bool):
                layer_copy['state'] = "on" if layer_copy['state'] else "off"

            processed.append(layer_copy)
        elif isinstance(layer, str):
            processed.append({
                'sprite': default_sprite,
                'state': layer
            })
    return processed


def extract_sprite_and_layers(entity_dict):
    """Извлекает отдельно данные для Sprite и для Icon."""
    components = entity_dict.get('components', [])
    
    if isinstance(components, dict):
        comp_list = [{**comp_data, 'type': comp_name} for comp_name, comp_data in components.items() if isinstance(comp_data, dict)]
    elif isinstance(components, list):
        comp_list = components
    else:
        comp_list = []

    local_sprite = None
    local_state = None
    local_layers = []

    local_icon_sprite = None
    local_icon_state = None

    for comp in comp_list:
        if not isinstance(comp, dict):
            continue

        comp_type = comp.get('type')

        if comp_type == 'Sprite':
            if comp.get('sprite'):
                local_sprite = comp.get('sprite')
            if comp.get('state'):
                local_state = comp.get('state')
            elif comp.get('icon'):
                local_state = comp.get('icon')

            layers = comp.get('layers')
            if isinstance(layers, list) and layers:
                local_layers = layers
                if not local_state:
                    first_layer = local_layers[0]
                    if isinstance(first_layer, dict):
                        local_state = first_layer.get('state')
                    elif isinstance(first_layer, str):
                        local_state = first_layer

        elif comp_type == 'Icon':
            if comp.get('sprite'):
                local_icon_sprite = comp.get('sprite')
            if comp.get('state'):
                local_icon_state = comp.get('state')

    return local_sprite, local_state, local_layers, local_icon_sprite, local_icon_state


def parse_suffixes(raw_suffix):
    """Безопасно парсит суффиксы сущности."""
    if isinstance(raw_suffix, str):
        return [s.strip().strip('"\'') for s in raw_suffix.split(',') if s.strip()]
    elif isinstance(raw_suffix, list):
        return [str(s).strip() for s in raw_suffix if s]
    return []


# --- 3. Главная функция обработки прототипов с SQLite и инкрементальностью по mtime ---

def process_prototypes(directory_path, db_path="prototypes_cache.db"):
    root_dir = Path(directory_path)
    
    # Инициализация SQLite базы для кэширования
    db_conn = sqlite3.connect(db_path)
    cursor = db_conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS files (
            file_path TEXT PRIMARY KEY,
            mtime REAL
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS entities (
            entity_id TEXT PRIMARY KEY,
            file_path TEXT,
            raw_data TEXT,
            FOREIGN KEY(file_path) REFERENCES files(file_path) ON DELETE CASCADE
        )
    """)
    db_conn.commit()

    # Получаем текущие файлы на диске и их mtime
    current_files = {}
    for file_path in root_dir.rglob('*.yml'):
        try:
            current_files[str(file_path)] = file_path.stat().st_mtime
        except OSError as e:
            logger.error(f"Не удалось получить mtime файла {file_path}: {e}")

    # Получаем старые mtime из базы
    cursor.execute("SELECT file_path, mtime FROM files")
    cached_files = {row[0]: row[1] for row in cursor.fetchall()}

    # Определяем, какие файлы изменились или были удалены/добавлены
    files_to_parse = []
    active_file_paths = set(current_files.keys())
    cached_file_paths = set(cached_files.keys())

    deleted_files = cached_file_paths - active_file_paths
    if deleted_files:
        cursor.executemany("DELETE FROM files WHERE file_path = ?", [(f,) for f in deleted_files])
        db_conn.commit()

    for f_path, mtime in current_files.items():
        if f_path not in cached_files or cached_files[f_path] != mtime:
            files_to_parse.append(f_path)

    # ЭТАП 1: Инкрементальное парсинг (только измененные/новые файлы)
    for file_path_str in files_to_parse:
        file_path = Path(file_path_str)
        try:
            # Удаляем старые записи сущностей для этого файла перед обновлением
            cursor.execute("DELETE FROM entities WHERE file_path = ?", (file_path_str,))
            
            with open(file_path, 'r', encoding='utf-8-sig') as f:
                content = yaml.load(f, Loader=SS14YamlLoader)
                if not isinstance(content, list):
                    continue
                
                entities_to_insert = []
                for item in content:
                    if isinstance(item, dict) and item.get('type') == 'entity' and item.get('id'):
                        entities_to_insert.append((
                            item['id'],
                            file_path_str,
                            json.dumps(item, ensure_ascii=False)
                        ))
                
                if entities_to_insert:
                    cursor.executemany(
                        "INSERT OR REPLACE INTO entities (entity_id, file_path, raw_data) VALUES (?, ?, ?)",
                        entities_to_insert
                    )
            
            # Обновляем mtime файла в базе
            cursor.execute(
                "INSERT OR REPLACE INTO files (file_path, mtime) VALUES (?, ?)",
                (file_path_str, current_files[file_path_str])
            )
            db_conn.commit()
        except Exception as e:
            logger.error(f"Ошибка при чтении файла {file_path_str}: {e}")
            db_conn.rollback()

    # Загружаем всю актуальную базу сущностей в оперативную память для быстрого построения цепочек
    cursor.execute("SELECT entity_id, file_path, raw_data FROM entities")
    entities_db = {}
    for row in cursor.fetchall():
        entities_db[row[0]] = {
            'file': row[1],
            'raw': json.loads(row[2])
        }

    db_conn.close()

    # Кэширующие функции для обхода дерева с защитой от циклов
    @lru_cache(maxsize=None)
    def get_ancestor_chain(entity_id, visited=frozenset()):
        if entity_id not in entities_db or entity_id in visited:
            return []

        entity_data = entities_db[entity_id]['raw']
        parents = entity_data.get('parent')
        chain = []

        new_visited = visited | {entity_id}

        if parents:
            # Поддержка нескольких родителей (если parent — список) или одного (строка)
            if isinstance(parents, str):
                parents = [parents]
            elif isinstance(parents, list):
                parents = [str(p) for p in parents if p]
                
            for parent_id in parents:
                chain.extend(get_ancestor_chain(parent_id, new_visited))

        chain.append(entity_id)
        return chain

    @lru_cache(maxsize=None)
    def resolve_entity_sprite_and_layers(entity_id):
        raw_chain = get_ancestor_chain(entity_id)
        if not raw_chain:
            return None, None, [], None, None

        dedup_chain = list(dict.fromkeys(raw_chain))

        final_sprite = None
        final_state = None
        final_layers = []

        final_icon_sprite = None
        final_icon_state = None

        for eid in dedup_chain:
            entity_data = entities_db[eid]['raw']
            local_sprite, local_state, local_layers, local_icon_sprite_local, local_icon_state_local = extract_sprite_and_layers(entity_data)

            if local_sprite:
                final_sprite = local_sprite
            if local_state:
                final_state = local_state
            if local_layers:
                final_layers = local_layers

            if local_icon_sprite_local:
                final_icon_sprite = local_icon_sprite_local
            if local_icon_state_local:
                final_icon_state = local_icon_state_local

        processed_layers = process_layers(final_layers, final_sprite)

        if not processed_layers and final_state:
            processed_layers = [{
                'sprite': final_sprite,
                'state': final_state
            }]

        return final_sprite, final_state, processed_layers, final_icon_sprite, final_icon_state

    # --- ЭТАП 2: Сборка результатов ---
    results = {}
    for entity_id, info in entities_db.items():
        file_name = info['file']
        raw_entity = info['raw']
        
        # 🟢 ФИЛЬТР: Пропускаем абстрактные прототипы, чтобы они не попадали в карточки
        if raw_entity.get('abstract', False):
            continue

        chain = get_ancestor_chain(entity_id)
        sprite_path, sprite_state, layers, icon_sprite, icon_state = resolve_entity_sprite_and_layers(entity_id)

        if file_name not in results:
            results[file_name] = []

        results[file_name].append({
            'id': entity_id,
            'suffix': parse_suffixes(raw_entity.get('suffix')),
            'sprite': sprite_path,
            'state': sprite_state,
            'layers': layers,
            'parent': raw_entity.get('parent'),
            'parents_chain': chain[:-1] if chain else []
        })

    return results