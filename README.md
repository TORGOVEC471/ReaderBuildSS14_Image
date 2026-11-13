# ReaderBuildSS14_Image
Программа для чтения .yml файлов из билдов и извлечения из них изображений.<br>
**! Для работы требуется** [Python](https://www.python.org/downloads/) **и любой билд сервера, например билд** [Corvax](https://github.com/space-syndicate/space-station-14) **!**

# Установка
## Репозиторий
Для установки репозитория программы требуется установленный [Git](https://git-scm.com/) и [Python](https://www.python.org/downloads/), желательно версии 3.14 (на других я не проверял).<br>
1. Создайте папку в любом месте.<br>
	1. Нажмите на путь к папке вверху проводника.<br>
	2. Введите cmd и нажмите enter, откроется обычный терминал.<br>
	<img width="600" height="300" alt="image" src="https://github.com/user-attachments/assets/fe6550ae-ef19-453a-a461-b5cbb2a3427e" /><br>
	
2. Используйте следующие команды поочерёдно:
	1. ```git clone https://github.com/TORGOVEC471/ReaderBuildSS14_Image.git```
	2. ```cd ReaderBuildSS14_Image```
	3. ```pip install -r requirements.txt```
	
3. Запустите `start.bat` и подождите запуск программы.<br>
	1. Или введите `python main.py` в консоли чтобы запустить интерфейс.<br>
	<img width="600" height="300" alt="image" src="https://github.com/user-attachments/assets/e013872a-f488-4415-b4b3-29f58b451cf9" /><br>

## Файл
Для установки готовой сборки вы можете перейти в [Releases](https://github.com/TORGOVEC471/ReaderBuildSS14_Image/releases) и установить самую актуальную версию.<br>
`window.rar` — архив включающий в себя пустые `data.json`, `Saves/`, `Readme.md` и исполняемый файл `ReaderBuildSS14.exe`.<br>
`window_only_exe.rar` — архив который включает в себя только `ReaderBuildSS14.exe`, что может пригодиться при перерходе на новую версию. Файл `ReaderBuildSS14.exe` сам создаст файлы `data.json`, `settings.ini` и папку `Saves/` для своей работы.

# Работа
Вам остается только зайти в настройки и ввести путь до двух папок:<br>
- Папки сохранения спрайтов и анимаций (точка сохраняет всё в папке проекта)<br>
- Папки билда сервера (где должна находиться папка `Resources/`, внутри которой `Prototypes/`, `Textures/` и `Locale/`). Для корвакса это папка `space_station/`<br>
<img width="600" height="414.5" alt="image" src="https://github.com/user-attachments/assets/9ddafa14-a149-4746-914e-d39ed58e79ab" /><br>
