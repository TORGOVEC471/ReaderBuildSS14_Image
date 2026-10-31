from functools import lru_cache
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
    """Извлекает sprite, state и список layers из Sprite или Icon."""
    components = entity_dict.get('components', [])
    
    # Приводим компоненты к единому списку словарей
    if isinstance(components, dict):
        comp_list = [{**comp_data, 'type': comp_name} for comp_name, comp_data in components.items() if isinstance(comp_data, dict)]
    elif isinstance(components, list):
        comp_list = components
    else:
        comp_list = []

    local_sprite = None
    local_state = None
    local_layers = []

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
                local_sprite = comp.get('sprite')
            if comp.get('state'):
                local_state = comp.get('state')

    return local_sprite, local_state, local_layers


def parse_suffixes(raw_suffix):
    """Безопасно парсит суффиксы сущности."""
    if isinstance(raw_suffix, str):
        return [s.strip().strip('"\'') for s in raw_suffix.split(',') if s.strip()]
    elif isinstance(raw_suffix, list):
        return [str(s).strip() for s in raw_suffix if s]
    return []


# --- 3. Главная функция обработки прототипов ---

def process_prototypes(directory_path):
    root_dir = Path(directory_path)
    entities_db = {}

    # ЭТАП 1: Индексация всех файлов
    for file_path in root_dir.rglob('*.yml'):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = yaml.load(f, Loader=SS14YamlLoader)
                if not isinstance(content, list):
                    continue
                for item in content:
                    if isinstance(item, dict) and item.get('type') == 'entity' and item.get('id'):
                        entities_db[item['id']] = {
                            'file': str(file_path),
                            'raw': item
                        }
        except Exception as e:
            print(f"Ошибка при чтении файла {file_path}: {e}")

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
            if isinstance(parents, str):
                parents = [parents]
            for parent_id in parents:
                chain.extend(get_ancestor_chain(parent_id, new_visited))

        chain.append(entity_id)
        return chain

    @lru_cache(maxsize=None)
    def resolve_entity_sprite_and_layers(entity_id):
        raw_chain = get_ancestor_chain(entity_id)
        if not raw_chain:
            return None, None, []

        # Быстрая дедупликация с сохранением порядка (аналог OrderedDict.fromkeys)
        dedup_chain = list(dict.fromkeys(raw_chain))

        final_sprite = None
        final_state = None
        final_layers = []

        for eid in dedup_chain:
            entity_data = entities_db[eid]['raw']
            local_sprite, local_state, local_layers = extract_sprite_and_layers(entity_data)

            if local_sprite:
                final_sprite = local_sprite
            if local_state:
                final_state = local_state
            if local_layers:
                final_layers = local_layers

        processed_layers = process_layers(final_layers, final_sprite)

        if not processed_layers and final_state:
            processed_layers = [{
                'sprite': final_sprite,
                'state': final_state
            }]

        return final_sprite, final_state, processed_layers

    # --- ЭТАП 2: Сборка результатов ---
    results = {}
    for entity_id, info in entities_db.items():
        file_name = info['file']
        raw_entity = info['raw']
        
        chain = get_ancestor_chain(entity_id)
        sprite_path, sprite_state, layers = resolve_entity_sprite_and_layers(entity_id)

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