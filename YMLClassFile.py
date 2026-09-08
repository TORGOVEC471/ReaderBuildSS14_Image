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
            # Если у слоя нет своего sprite, подставляем основной sprite компонента/родителя
            if 'sprite' not in layer_copy or not layer_copy['sprite']:
                if default_sprite:
                    layer_copy['sprite'] = default_sprite

            # Приведение булевых state к строкам ("on" / "off")
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

        # Обработка компонента Sprite
        if comp_type == 'Sprite':
            if comp.get('sprite'):
                local_sprite = comp.get('sprite')
            if comp.get('state'):
                local_state = comp.get('state')
            elif comp.get('icon'):
                local_state = comp.get('icon')

            # sprite_layers = comp.get('layers')
            # if not local_state and sprite_layers and isinstance(sprite_layers, list):
            #     target_layer = None
            #     for layer in sprite_layers:
            #         if isinstance(layer, dict) and layer.get("state"):
            #             if not layer.get("sprite") or layer.get("sprite") == local_sprite:
            #                 target_layer = layer
            #                 break

            #     if not target_layer:
            #         for layer in reversed(sprite_layers):
            #             if isinstance(layer, dict) and layer.get("state"):
            #                 target_layer = layer
            #                 break

            #     if target_layer:
            #         layer_state = target_layer.get("state")
            #         if isinstance(layer_state, bool):
            #             layer_state = "on" if layer_state else "off"
            #         local_state = layer_state
            #         if not local_sprite:
            #             local_sprite = target_layer.get("sprite")

            layers = comp.get('layers')
            if layers and isinstance(layers, list):
                local_layers = layers
                if not local_state and local_layers:
                    first_layer = local_layers[0]
                    if isinstance(first_layer, dict):
                        local_state = first_layer.get('state')
                    elif isinstance(first_layer, str):
                        local_state = first_layer

        # Обработка компонента Icon
        elif comp_type == 'Icon':
            if comp.get('sprite'):
                local_sprite = comp.get('sprite')
            if comp.get('state'):
                local_state = comp.get('state')

    return local_sprite, local_state, local_layers


# --- 4. Рекурсивное построение цепочки родителей (Top-Down) ---
def get_ancestor_chain(entity_id, entities_db, visited=None):
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


# --- 5. Резолвер с учетом слоев ---
def resolve_entity_sprite_and_layers(entity_id, entities_db):
    raw_chain = get_ancestor_chain(entity_id, entities_db)
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

    # Нормализуем и подставляем итоговый sprite в каждый слой
    processed_layers = process_layers(final_layers, final_sprite)

    # Если массив layers был пуст, но заданы базовые state и sprite
    if not processed_layers and final_state:
        processed_layers = [{
            'sprite': final_sprite,
            'state': final_state
        }]

    return final_sprite, final_state, processed_layers


# --- 6. Главная функция обхода ---
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

    # ЭТАП 2: Разрешение наследования
    results = {}
    for entity_id, info in entities_db.items():
        file_name = info['file']
        raw_suffix = info['raw'].get('suffix')
        chain = get_ancestor_chain(entity_id, entities_db)
        sprite_path, sprite_state, layers = resolve_entity_sprite_and_layers(entity_id, entities_db)

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