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


# --- 2. Нормализация и обработка списка слоёв ---
def process_layers(raw_layers, default_sprite):
    """
    Обрабатывает массив слоев, подставляя общий sprite элемента, 
    если в самом слое он явно не указан.
    """
    processed = []
    if not raw_layers:
        return processed

    for layer in raw_layers:
        if isinstance(layer, dict):
            layer_copy = layer.copy()
            if 'sprite' not in layer_copy or not layer_copy['sprite']:
                if default_sprite:
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


# --- 3. Извлечение локальных данных Sprite/Icon и Layers ---
def extract_sprite_and_layers(entity_dict):
    """Извлекает sprite, state и список layers из Sprite или Icon."""
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
            if layers and isinstance(layers, list):
                local_layers = layers
                if not local_state and local_layers:
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


# --- 6. Главная функция обхода с мемоизацией ---
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
                        if isinstance(item, dict) and item.get('type') == 'entity' and item.get('id'):
                            entities_db[item['id']] = {
                                'file': str(file_path),
                                'raw': item
                            }
        except Exception as e:
            print(f"Ошибка при чтении файла {file_path}: {e}")

    # --- Внутренние функции с lru_cache (используют entities_db из замыкания) ---

    @lru_cache(maxsize=None)
    def get_ancestor_chain(entity_id):
        if entity_id not in entities_db:
            return []

        entity_data = entities_db[entity_id]['raw']
        parents = entity_data.get('parent')
        chain = []

        if parents:
            if isinstance(parents, str):
                parents = [parents]
            for parent_id in parents:
                chain.extend(get_ancestor_chain(parent_id))

        chain.append(entity_id)
        return chain

    @lru_cache(maxsize=None)
    def resolve_entity_sprite_and_layers(entity_id):
        raw_chain = get_ancestor_chain(entity_id)
        if not raw_chain:
            return None, None, []

        dedup_chain = []
        for item in raw_chain:
            if item in dedup_chain:
                dedup_chain.remove(item)
            dedup_chain.append(item)

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

    # --- ЭТАП 2: Разрешение наследования ---
    results = {}
    for entity_id, info in entities_db.items():
        file_name = info['file']
        raw_suffix = info['raw'].get('suffix')
        chain = get_ancestor_chain(entity_id)
        sprite_path, sprite_state, layers = resolve_entity_sprite_and_layers(entity_id)

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
            'suffix': suffixes,
            'sprite': sprite_path,
            'state': sprite_state,
            'layers': layers,
            'parent': info['raw'].get('parent'),
            'parents_chain': chain[:-1] if chain else []
        })

    return results