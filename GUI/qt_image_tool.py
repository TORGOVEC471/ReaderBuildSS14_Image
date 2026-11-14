from PIL import Image
from PIL.ImageQt import ImageQt
from PyQt6.QtGui import QImage

def pil_to_qimage(pil_img: Image.Image) -> QImage:
    """Конвертирует PIL.Image в QImage для использования в PyQt."""
    if pil_img.mode != "RGBA":
        pil_img = pil_img.convert("RGBA")
    # Используем стандартный ImageQt из библиотеки Pillow
    return QImage(ImageQt(pil_img)).copy()