@echo off
:: Переходим в папку со скриптом
cd /d "%~dp0"

:: Проверяем, установлен ли Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [Ошибка] Python не найден в системе или не добавлен в переменную PATH!
    echo Пожалуйста, установите Python и перезапустите скрипт.
    pause
    exit /b 1
)

:: Запускаем скрипт без консольного окна
start /B pythonw "main.py"
exit