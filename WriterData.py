import YMLClassFile as YMLF
import json
import configparser
from pathlib import Path

config = configparser.ConfigParser()
config.read("settings.ini", encoding="utf-8")

path_build = config["General"]["path_build"]

dir_textures = '/Resources/Textures/'
dir_prototypes = '/Resources/Prototypes/'
list_SpriteID = []
TARGET_DIR = f"{path_build+dir_prototypes}"

def save_data_build(TARGET_DIR):
    parsed_data = YMLF.process_prototypes(TARGET_DIR)

    # Вывод результатов
    for file_name, entities in parsed_data.items():
        print(f"\nФайл: {file_name}")
        for entity in entities:
            if entity.get('sprite') is not None:
                # Определение значения state
                state_value = entity.get('state')

                # Если state равен None, получаем его из meta.json
                rsi_path = path_build + dir_textures + entity['sprite'].removeprefix("/Textures/")
                meta_path = rsi_path + "/meta.json"
                if state_value is None:
                    state_value = process_meta(meta_path)

                try:
                    with open(Path(meta_path), "r", encoding="utf-8-sig") as f:
                        data = json.load(f)
                        size = data.get("size", {"x": 32, "y": 32})
                except Exception as e:
                    print(f"[WARN] Failed to read metadata from {meta_path}: {e}")

                list_SpriteID.append({
                    "file": file_name.replace("\\", "/"),
                    "id": entity['id'],
                    "sprite": entity['sprite'],
                    "path": path_build + dir_textures + entity['sprite'].removeprefix("/Textures/"),
                    "state": state_value,
                    "states": get_states(rsi_path),
                    "size": size
                    },
                    )
    # Открываем файл на запись ('w') с указанием кодировки utf-8
    with open("data.json", "w", encoding="utf-8") as file:
        json.dump(list_SpriteID, file, ensure_ascii=False, indent=4)
    print("Файлы записаны в data.json")

# функция поиска первого state в meta.json
def process_meta(directory_path) -> None:
    """Берёт первый попавшийся .png в meta.json"""
    root_dir = Path(directory_path)

    if not root_dir.exists():
        print(f"[ERROR] Path does not exist: {root_dir}")
        return

    # 2. Если передан .json файл — обрабатываем все .png состояния из него
    if root_dir.is_file() and root_dir.suffix.lower() == ".json":
        try:
            # Открываем сам файл root_dir, а не parent_dir
            with open(root_dir, "r", encoding="utf-8-sig") as f:
                data = json.load(f)

            states = data.get("states", [])
            if states and isinstance(states, list):
                return states[0].get("name")

        except Exception as e:
            print(f"[ERROR] Ошибка при чтении {root_dir}: {e}")
            return None

def get_states(directory_path : str | Path) -> list[Path]:
    """Возвращает список всех .png файлов в папке .rsi"""
    rsi_dir = Path(directory_path)

    if not rsi_dir.is_dir():
        print(f"[ERROR] Указанный путь не является директорией: {rsi_dir}")
        return []

    # Получаем все .png файлы в папке
    png_files = [file.stem for file in rsi_dir.glob("*.png") if file.is_file()]

    return png_files

# --- Пример использования ---
if __name__ == "__main__":
    save_data_build(TARGET_DIR)