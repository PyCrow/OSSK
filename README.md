# StreamSaver

A program to automate the tracking of YouTube channels and recording their streams.

All records will be saved in a folder next to the program: `./records/<CHANNEL_NAME>`

The event log is stored in the `stream_saver.log` file.

Channel management:
- To add a channel, enter its YouTube tag in the box and click "Add channel"
- To configure a channel, right-click on its line and select "Channel settings"
- To delete a channel, right-click on its line and select "Delete channel"

Settings (`settings` file):
- in the _ffmpeg field_, enter the path to the ffmpeg library / .exe file
- in the _yt-dlp_ field, enter the run command or the path to the yt-dlp library / .exe file (default: `python -m yt_dlp`)
- you can specify a maximum number of concurrent downloads to limit CPU, disk and network usage (default: `2`)
- you can specify the idle time between full channel scan cycles in minutes (default: `5`).
This option will avoid a ban from YouTube, which may consider the scan as a DoS attack.

Channel settings:
- if an alias is specified, it will be displayed in the channel line instead of its ID
- stream video quality[`480`, `720`, `1080`]: an attempt will be made downloads
 in this capacity. If the format is not available, the download will be cancelled.
- stream video quality[`best`]: search for the best available format (top to bottom).
---

Программа для автоматизации отслеживания YouTube каналов и записи их стримов.

Все записи будут сохраняться в папку, рядом с программой: `./records/<НАЗВАНИЕ_КАНАЛА>`

Журнал событий сохраняется в файл `stream_saver.log`.

Управление каналами:
- для добавления канала введите его YouTube тэг в поле, и нажмите "Добавить канал"
- для настройки канала щелкните по его строке правой кнопкой и выберите "Настройки канал"
- для удаления канала щелкните по его строке правой кнопкой и выберите "Удалить канал"

Настройки (файл `settings`):
- в поле _ffmpeg_ введите путь до библиотеки / .exe-файла ffmpeg;
- в поле _yt-dlp_ введите команду запуска или путь до библиотеки / .exe-файла yt-dlp (по-умолчанию: `python -m yt_dlp`)
- можно указать максимальное количество одновременных загрузок для ограничения нагрузки на CPU, диск и сеть (по-умолчанию: `2`)
- можно указать время простоя между полными циклами сканирования каналов в минутах (по-умолчанию: `5`).
Эта опция позволит избежать бана со стороны YouTube, который может счесть сканирование за DoS атаку.

Настройки канала:
- если указан псевдоним, то он будет отображаться в строке канала вместо его ID
- качество записи видео-потока[`480`, `720`, `1080`]: будет произведена попытка
загрузки именно в этом качестве. Если формат недоступен - загрузка будет отменена.
- качество записи видео-потока[`best`]: будет произведен поиск лучшего
доступного формата (сверху вниз).
