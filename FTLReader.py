import re
from pathlib import Path

def parse_ftl_file(file_path):
    """
    Считывает .ftl файл и возвращает словарь с сырыми значениями:
    {
        'ent-CMOPDA': {'name': 'КПК главного врача', 'desc': '...'},
        ...
    }
    """
    ftl_data = {}
    current_id = None

    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f:
            line_str = line.strip()
            
            # Пропускаем пустые строки и комментарии
            if not line_str or line_str.startswith('#'):
                continue

            # Обработка атрибутов (.desc = ..., .suffix = ...)
            if line_str.startswith('.'):
                if current_id and '=' in line_str:
                    attr_part, val_part = line_str.split('=', 1)
                    attr_name = attr_part.lstrip('.').strip()
                    val_str = val_part.strip()

                    if attr_name == 'suffix':
                        # Разделяем по запятой, убираем пробелы и возможные кавычки
                        suffixes = [s.strip().strip('"\'') for s in val_str.split(',') if s.strip()]
                        ftl_data[current_id][attr_name] = suffixes
                    else:
                        ftl_data[current_id][attr_name] = val_str

            # Обработка основных ключей (ent-MedicalPDA = ...)
            elif '=' in line_str:
                key_part, val_part = line_str.split('=', 1)
                current_id = key_part.strip()
                ftl_data[current_id] = {
                    'name': val_part.strip()
                }

    return ftl_data


def resolve_ftl_references(ftl_data):
    """
    Рекурсивно подставляет ссылки вида { ent-MedicalPDA } 
    и { ent-MedicalPDA.desc } в значения.
    """
    ref_pattern = re.compile(r'\{\s*([a-zA-Z0-9_-]+)(?:\.([a-zA-Z0-9_-]+))?\s*\}')

    def get_value(entity_id, attr_name=None):
        if entity_id not in ftl_data:
            return ""
        entity = ftl_data[entity_id]
        val = entity.get(attr_name, "") if attr_name else entity.get('name', "")
        
        # Если ссылаются на список (например, suffix), превращаем обратно в строку
        if isinstance(val, list):
            return ", ".join(val)
        return val

    def resolve_string(text):
        curr_val = text
        for _ in range(5):
            matches = list(ref_pattern.finditer(curr_val))
            if not matches:
                break
            
            new_val = curr_val
            for match in reversed(matches):
                target_id = match.group(1)
                target_attr = match.group(2)
                replacement = get_value(target_id, target_attr)
                
                start, end = match.span()
                new_val = new_val[:start] + replacement + new_val[end:]
            
            curr_val = new_val
        return curr_val

    resolved_data = {}

    for eid, attrs in ftl_data.items():
        resolved_data[eid] = {}
        for key, value in attrs.items():
            if isinstance(value, list):
                resolved_data[eid][key] = [resolve_string(item) for item in value]
            else:
                resolved_data[eid][key] = resolve_string(value)

    return resolved_data


def load_ftl_directory(directory_path):
    """Обходит папку, собирает все .ftl файлы и разрешает ссылки."""
    root_dir = Path(directory_path)
    combined_raw_db = {}

    # 1. Сбор данных из всех .ftl файлов
    for file_path in root_dir.rglob('*.ftl'):
        try:
            file_data = parse_ftl_file(file_path)
            combined_raw_db.update(file_data)
        except Exception as e:
            print(f"Ошибка чтения FTL файла {file_path}: {e}")

    # 2. Разрешение ссылок
    return resolve_ftl_references(combined_raw_db)

if __name__ == "__main__":
    # dir = "C:/Users/Илья/Desktop/ADT_GIT/space_station_ADT/Resources/Locale/ru-RU/ss14-ru"
    dir = "C:/Users/Илья/Desktop/ADT_GIT/space_station_ADT/Resources/Locale/ru-RU/ss14-ru/prototypes/entities/objects/devices"
    ftl_db = load_ftl_directory(dir)
    print(ftl_db)
    print("-----")
    print({key: val.get('suffix') for key, val in ftl_db.items()})