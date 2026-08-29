from pathlib import Path
import yaml

# --- 1. Настройка обработчика кастомных тегов (например, !type:MechGunUi) ---
class SS14YamlLoader(yaml.SafeLoader):
    """Кастомный SafeLoader, прощающий неизвестные теги !type:..."""
    pass

def ignore_unknown_tags(loader, tag_suffix, node):
    if isinstance(node, yaml.MappingNode):
        return loader.construct_mapping(node)
    elif isinstance(node, yaml.SequenceNode):
        return loader.construct_sequence(node)
    return loader.construct_scalar(node)

# Перехватываем все теги, начинающиеся с '!'
SS14YamlLoader.add_multi_constructor('!', ignore_unknown_tags)


# --- 2. Функция для извлечения ID и Sprite из данных одного файла ---
def extract_id_and_sprites(data):
    results = []
    
    # Файлы прототипов SS14 представляют собой список объектов
    if not isinstance(data, list):
        return results

    for item in data:
        if not isinstance(item, dict):
            continue
        
        # Получаем id сущности (если он есть)
        entity_id = item.get('id')
        if not entity_id:
            continue

        # родитель пока не исппользуется
        sprite_parent = None
        sprite_path = None
        sprite_state = None
        sprite_layers = None
        
        # Ищем компонент Sprite среди всех компонентов
        components = item.get('components', [])
        if isinstance(components, list):
            for comp in components:
                if isinstance(comp, dict) and comp.get('type') == 'Sprite':
                    sprite_parent = comp.get('parent')
                    sprite_path = comp.get('sprite')
                    sprite_state = comp.get('state')
                    sprite_layers = comp.get('layers')

                    # Если state нет на верхнем уровне Sprite, ищем подходящий слой
                    if not sprite_state and sprite_layers and isinstance(sprite_layers, list):
                        target_layer = None

                        # 1. Приоритет: ищем слой, у которого НЕТ своего sprite 
                        # (значит, он относится к основному sprite_path)
                        for layer in sprite_layers:
                            if isinstance(layer, dict) and layer.get("state"):
                                if not layer.get("sprite") or layer.get("sprite") == sprite_path:
                                    target_layer = layer
                                    break

                        # 2. Если такой слой не найден, берем последний слой из списка (он отрисовывается поверх всех)
                        if not target_layer:
                            for layer in reversed(sprite_layers):
                                if isinstance(layer, dict) and layer.get("state"):
                                    target_layer = layer
                                    break

                        # Извлекаем данные из найденного слоя
                        if target_layer:
                            sprite_state = target_layer.get("state")

                            # Если YAML-парсер уже превратил 'on'/'off' в True/False:
                            if isinstance(sprite_state, bool):
                                sprite_state = "on" if sprite_state else "off"

                            # Если основной sprite_path не был задан на верхнем уровне, берем из слоя
                            if not sprite_path:
                                sprite_path = target_layer.get("sprite")

                    break  # Компонент Sprite найден

        results.append({
            'id': entity_id,
            'sprite': sprite_path,
            'state': sprite_state
        })

    return results

# --- 3. Главная функция обхода файлов ---
def process_prototypes(directory_path):
    root_dir = Path(directory_path)
    all_extracted_data = {}

    # Находим все .yml и .yaml файлы рекурсивно
    for file_path in root_dir.rglob('*.yml'):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = yaml.load(f, Loader=SS14YamlLoader)
                extracted = extract_id_and_sprites(content)
                
                if extracted:
                    all_extracted_data[str(file_path)] = extracted

        except Exception as e:
            print(f"Ошибка при чтении файла {file_path}: {e}")

    return all_extracted_data


# --- Пример использования ---
if __name__ == "__main__":
    # Укажите путь к вашей папке с прототипами
    TARGET_DIR = "Path/to/prototypes" 
    
    parsed_data = process_prototypes(TARGET_DIR)

    # Вывод результатов
    for file_name, entities in parsed_data.items():
        print(f"\nФайл: {file_name}")
        for entity in entities:
            print(f"  - ID: {entity['id']}")
            print(f"    Sprite: {entity['sprite']}")
            print(f"    State:  {entity['state']}")