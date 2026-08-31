from pathlib import Path
import yaml

# --- 1. Кастомный SafeLoader ---
class SS14YamlLoader(yaml.SafeLoader):
    pass

def ignore_unknown_tags(loader, tag_suffix, node):
    if isinstance(node, yaml.MappingNode):
        return loader.construct_mapping(node)
    elif isinstance(node, yaml.SequenceNode):
        return loader.construct_sequence(node)
    return loader.construct_scalar(node)

SS14YamlLoader.add_multi_constructor('!', ignore_unknown_tags)


# --- 2. Извлечение локальных данных Sprite из конкретного dict ---
def get_local_sprite_info(entity_dict):
    """Извлекает sprite (path) и state из компонентов Sprite или Icon."""
    components = entity_dict.get('components', [])

    comp_list = []
    if isinstance(components, list):
        comp_list = components
    elif isinstance(components, dict):
        for comp_name, comp_data in components.items():
            if isinstance(comp_data, dict):
                c = comp_data.copy()
                c['type'] = comp_name
                comp_list.append(c)

    local_sprite = None
    local_state = None

    for comp in comp_list:
        if not isinstance(comp, dict):
            continue

        comp_type = comp.get('type')

        # 1. Обработка компонента Sprite
        if comp_type == 'Sprite':
            if comp.get('sprite'):
                local_sprite = comp.get('sprite')
            if comp.get('state'):
                local_state = comp.get('state')
            elif comp.get('icon'):
                local_state = comp.get('icon')

            sprite_layers = comp.get('layers')
            if not local_state and sprite_layers and isinstance(sprite_layers, list):
                target_layer = None
                for layer in sprite_layers:
                    if isinstance(layer, dict) and layer.get("state"):
                        if not layer.get("sprite") or layer.get("sprite") == local_sprite:
                            target_layer = layer
                            break

                if not target_layer:
                    for layer in reversed(sprite_layers):
                        if isinstance(layer, dict) and layer.get("state"):
                            target_layer = layer
                            break

                if target_layer:
                    layer_state = target_layer.get("state")
                    if isinstance(layer_state, bool):
                        layer_state = "on" if layer_state else "off"
                    local_state = layer_state
                    if not local_sprite:
                        local_sprite = target_layer.get("sprite")

        # 2. Обработка компонента Icon
        elif comp_type == 'Icon':
            if comp.get('sprite'):
                local_sprite = comp.get('sprite')
            if comp.get('state'):
                local_state = comp.get('state')

    return local_sprite, local_state


# --- 3. Рекурсивное построение цепочки родителей (Top-Down) ---
def get_ancestor_chain(entity_id, entities_db, visited=None):
    """Возвращает список ID сущностей от самого базового родителя к текущему ребенку."""
    if visited is None:
        visited = set()

    if entity_id in visited or entity_id not in entities_db:
        return []

    visited.add(entity_id)
    entity_data = entities_db[entity_id]['raw']

    parents = entity_data.get('parent')
    chain = []

    if parents:
        if isinstance(parents, str):
            parents = [parents]
        for parent_id in parents:
            chain.extend(get_ancestor_chain(parent_id, entities_db, visited.copy()))

    chain.append(entity_id)
    return chain


# --- 4. Резолвер с переопределением (Override) ---
def resolve_entity_sprite(entity_id, entities_db):
    """
    Проходит цепочку от Главного Родителя к Ребенку.
    Ребенок переопределяет state/sprite родителя, если имеет свои значения.
    """
    raw_chain = get_ancestor_chain(entity_id, entities_db)
    if not raw_chain:
        return None, None

    # Убираем дубликаты с сохранением порядка (от корня к ребенку)
    dedup_chain = []
    for item in raw_chain:
        if item in dedup_chain:
            dedup_chain.remove(item)
        dedup_chain.append(item)

    final_sprite = None
    final_state = None

    # Накапливаем и переопределяем значения сверху вниз
    for eid in dedup_chain:
        entity_data = entities_db[eid]['raw']
        local_sprite, local_state = get_local_sprite_info(entity_data)

        if local_sprite:
            final_sprite = local_sprite
        if local_state:
            final_state = local_state

    return final_sprite, final_state


# --- 5. Главная функция обхода ---
def process_prototypes(directory_path):
    root_dir = Path(directory_path)
    entities_db = {}

    # ЭТАП 1: Индексация всех файлов
    for file_path in root_dir.rglob('*.yml'):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = yaml.load(f, Loader=SS14YamlLoader)
                if isinstance(content, list):
                    for item in content:
                        if isinstance(item, dict) and item.get('id'):
                            entities_db[item['id']] = {
                                'file': str(file_path),
                                'raw': item
                            }
        except Exception as e:
            print(f"Ошибка при чтении файла {file_path}: {e}")

    # ЭТАП 2: Разрешение наследования
    results = {}
    for entity_id, info in entities_db.items():
        file_name = info['file']
        raw_suffix = info['raw'].get('suffix')
        chain = get_ancestor_chain(entity_id, entities_db)
        sprite_path, sprite_state = resolve_entity_sprite(entity_id, entities_db)

        if file_name not in results:
            results[file_name] = []

        if isinstance(raw_suffix, str):
            suffixes = [s.strip().strip('"\'') for s in raw_suffix.split(',') if s.strip()]
        elif isinstance(raw_suffix, list):
            suffixes = raw_suffix
        else:
            suffixes = []

        results[file_name].append({
            'id': entity_id,
            # 'suffix': info['raw'].get('suffix', []),
            'suffix': suffixes,
            'sprite': sprite_path,
            'state': sprite_state,
            'parent': info['raw'].get('parent'),
            'parents_chain': chain[:-1] if chain else []
        })

    return results