import re
from pathlib import Path
from typing import Dict, Any, List, Set, Optional

def parse_ftl_file(file_path: Path) -> Dict[str, Dict[str, Any]]:
    """
    Считывает .ftl файл с поддержкой многострочных значений 
    и возвращает словарь с сырыми данными.
    """
    ftl_data: Dict[str, Dict[str, Any]] = {}
    current_id: Optional[str] = None
    current_attr: Optional[str] = None

    with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
        for line in f:
            raw_line = line.rstrip('\r\n')
            stripped = raw_line.strip()

            # Пропускаем пустые строки и комментарии
            if not stripped or stripped.startswith('#'):
                continue

            # Основной ключ сущности (например, ent-MedicalPDA = ...)
            if not raw_line.startswith((' ', '\t')) and '=' in stripped and not stripped.startswith('.'):
                key_part, val_part = stripped.split('=', 1)
                current_id = key_part.strip()
                current_attr = 'name'
                ftl_data[current_id] = {current_attr: val_part.strip()}
            
            # Атрибут (.desc = ...) или многострочное продолжение
            elif current_id:
                if stripped.startswith('.'):
                    attr_part, val_part = stripped.split('=', 1) if '=' in stripped else (stripped, '')
                    current_attr = attr_part.lstrip('.').strip()
                    val_str = val_part.strip()
                else:
                    # Это строка продолжения (multiline)
                    val_str = stripped

                if current_attr not in ftl_data[current_id]:
                    ftl_data[current_id][current_attr] = ""

                existing = ftl_data[current_id][current_attr]
                if isinstance(existing, str):
                    if existing:
                        # Объединяем через пробел или перенос строки
                        ftl_data[current_id][current_attr] = existing + " " + val_str
                    else:
                        ftl_data[current_id][current_attr] = val_str

    # Постобработка списков (например, suffix)
    for eid, attrs in ftl_data.items():
        if 'suffix' in attrs and isinstance(attrs['suffix'], str):
            cleaned_val = attrs['suffix'].strip('{} ').strip('"\'')
            suffixes = [s.strip().strip('"\'') for s in cleaned_val.split(',') if s.strip()]
            attrs['suffix'] = suffixes

    return ftl_data


def resolve_ftl_references(ftl_data: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """
    Рекурсивно подставляет ссылки с защитой от циклов и кэшированием.
    """
    ref_pattern = re.compile(r'\{\s*([a-zA-Z0-9_-]+)(?:\.([a-zA-Z0-9_-]+))?\s*\}')
    memo: Dict[str, str] = {}

    def get_value(entity_id: str, attr_name: Optional[str] = None) -> str:
        if entity_id not in ftl_data:
            return ""
        entity = ftl_data[entity_id]
        val = entity.get(attr_name, "") if attr_name else entity.get('name', "")
        
        if isinstance(val, list):
            return ", ".join(val)
        return str(val)

    def resolve_string(text: str, visiting: Optional[Set[str]] = None) -> str:
        if visiting is None:
            visiting = set()

        if text in memo:
            return memo[text]

        def replace_match(match) -> str:
            target_id = match.group(1)
            target_attr = match.group(2)
            ref_key = f"{target_id}.{target_attr}" if target_attr else target_id

            # Защита от бесконечной рекурсии (циклических ссылок)
            if ref_key in visiting:
                return match.group(0) # Оставляем как есть или возвращаем пустую строку

            visiting.add(ref_key)
            try:
                raw_val = get_value(target_id, target_attr)
                return resolve_string(raw_val, visiting)
            finally:
                visiting.remove(ref_key)

        result = ref_pattern.sub(replace_match, text)
        memo[text] = result
        return result

    resolved_data: Dict[str, Dict[str, Any]] = {}

    for eid, attrs in ftl_data.items():
        resolved_data[eid] = {}
        for key, value in attrs.items():
            if isinstance(value, list):
                resolved_data[eid][key] = [resolve_string(item) for item in value]
            else:
                resolved_data[eid][key] = resolve_string(value)

    return resolved_data


def load_ftl_directory(directory_path: str) -> Dict[str, Dict[str, Any]]:
    """Обходит папку, собирает все .ftl файлы и разрешает ссылки."""
    root_dir = Path(directory_path)
    combined_raw_db: Dict[str, Dict[str, Any]] = {}

    for file_path in root_dir.rglob('*.ftl'):
        try:
            file_data = parse_ftl_file(file_path)
            combined_raw_db.update(file_data)
        except Exception as e:
            print(f"Ошибка чтения FTL файла {file_path}: {e}")

    return resolve_ftl_references(combined_raw_db)


if __name__ == "__main__":
    target_dir = "Dir/To/Test"
    ftl_db = load_ftl_directory(target_dir)
    print(f"Загружено сущностей: {len(ftl_db)}")