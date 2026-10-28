COLUMNS = 3  # Желаемое количество колонок в сетке
PAGE_SIZE = 36 # Сколько элементов грузить за раз (кратно COLUMS)

# Стили
# Стиль для кнопок
btn_style = """
    QPushButton {
        background-color: #3498db;
        color: white;
        font-weight: bold;
        padding: 8px 16px;
        border-radius: 4px;
    }
    QPushButton:hover {
        background-color: #2980b9;
    }
"""
# Стиль для рамок (QGroupBox)
group_style = """
    QGroupBox {
        font-weight: bold;
        border: 1px solid #bdc3c7;
        border-radius: 6px;
        margin-top: 0px;
        padding-top: 20px;
    }
    QGroupBox::title {
        subcontrol-origin: margin;
        subcontrol-position: top center; /* Центрируем заголовок */
        padding: 0 5px;
        background-color: transparent;
        top: 5px
    }
"""