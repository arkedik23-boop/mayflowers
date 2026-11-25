# Тесты бота и сайта

Бот запускается локально с поддельным Telegram (мини-сервер на 127.0.0.1:18999 внутри теста), база — во временной папке `tests/_work/`.

```
python3 tests/card.py     # аудио/видео-открытка: QR, медиа, ответ голосом
python3 tests/cabadd.py   # открытка из кабинета: /api/card/add, /api/card/state
python3 tests/cabup.py    # запись на сайте: /api/card/upload, перекодировка (нужен ffmpeg)
python3 tests/rem.py      # напоминания за 3 дня и накануне
python3 tests/cabui.py    # сайт в браузере (Playwright) + кабинет, мини-апка
python3 tests/recui.py    # запись голоса и видео в браузере (виртуальные микрофон и камера)
```

✔ — проверка прошла, ✘ — нет. В конце `bot errors: none`.
