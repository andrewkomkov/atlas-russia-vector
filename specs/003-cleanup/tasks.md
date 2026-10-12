# Задачи: чистка данных и кода

## Запрос 1. Данные

- [x] T001 `pipeline/build.py`: правило `no_vector`, поле `nv`, удаление лишних векторов
- [x] T002 `pipeline/legend.py`: фильтр подписей (FR-005, FR-006), удаление мёртвого кода
- [x] T003 `pipeline/build_legends.py`, `pipeline/check.py`: учёт поля `nv`
- [x] T004 Сайт: показ помеченного листа как картинки, пометка в каталоге
- [x] T005 `tests/test_legend.py`
- [x] T006 Пересборка каталога и легенд, `check.py`, README и CLAUDE.md

## Запрос 2. Код

- [x] T007 `site/public/proj.js` и `tests/test_proj.py`
- [x] T008 `site/public/app.js`: строки не длиннее 120 знаков, `userMode` в `state`
- [x] T009 `pipeline/build.py`: один способ передать `FORCE`, поля каталога по FR-007
- [x] T010 `site/src/worker.js`: ответ 400 и `Range`
- [x] T011 `site/public/_headers`: заголовки безопасности
- [ ] T012 Публикация и проверка на живом сайте (SC-005)
