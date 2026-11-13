from PIL import ImageColor

def parse_color(color_str: str) -> tuple[int, int, int, int]:
    """
    Универсальный парсер цветов: поддерживает именованные цвета (red, yellow),
    короткие HEX (#f00, #f008), стандартные (#ff0000) и с альфа-каналом (#ff000088).
    Возвращает кортеж (r, g, b, a) в диапазоне 0-255.
    """
    if not color_str:
        return (255, 255, 255, 255)
    
    color_str = str(color_str).strip()
    
    # 1. Пробуем через PIL.ImageColor (поддерживает имена цветов и базовые hex)
    try:
        rgb = ImageColor.getrgb(color_str)
        if len(rgb) == 4:
            return rgb
        return (*rgb, 255)
    except ValueError:
        pass

    clean = color_str.lstrip("#").lower()
    
    # 2. Обработка коротких форматов (#rgb -> #rrggbb, #rgba -> #rrggbbaa)
    if len(clean) == 3:
        clean = "".join([c * 2 for c in clean]) + "ff"
    elif len(clean) == 4:
        clean = "".join([c * 2 for c in clean])
        
    # 3. Обработка 6-значных и 8-значных HEX
    if len(clean) == 6:
        try:
            return (
                int(clean[0:2], 16),
                int(clean[2:4], 16),
                int(clean[4:6], 16),
                255
            )
        except ValueError:
            pass
    elif len(clean) == 8:
        try:
            return (
                int(clean[0:2], 16),
                int(clean[2:4], 16),
                int(clean[4:6], 16),
                int(clean[6:8], 16)
            )
        except ValueError:
            pass
            
    return (255, 255, 255, 255)