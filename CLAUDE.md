# atlas-russia-vector

Векторизация карт nationalatlas.ru и сайт https://atlas.ebpm.center. Описание и команды —
в `README.md`. Проект ведётся через spec-kit: `.specify/memory/constitution.md` обязательна,
текущая фича — в `.specify/feature.json`.

## Правила

- Данные в `site/public/data/` руками не править: менять код в `pipeline/` и пересобирать.
- Порог привязки — константы `MIN_*` и `MAX_ROT` в `pipeline/georef.py`. После изменения
  порога или алгоритма привязки пересобрать (`build.py --force`) и просмотреть листы
  `qa_georef.py` по всем томам.
- Формат `data/v/*.json` читает `site/public/app.js` (`toGeoJSON`); формула обратной
  проекции продублирована там (`invProj`) и должна совпадать с `pipeline/geo.py`.
- Библиотеки сайта: `npm install` в `site/` копирует MapLibre в `site/public/vendor/`. Версия
  зафиксирована в `site/package.json`. CDN не используется, папка `vendor/` в git не входит.
- Лист без полезного вектора помечает `no_vector` в `pipeline/build.py` (поле `nv` каталога).
  После изменения порогов запустить `build.py` без `--force`: он пересоберёт нужные слои.
  Затем запустить `build_legends.py`.
- Окружение Python: `.venv` (создаётся по `requirements.txt`).
- `data/` и `site/public/data/` в git не входят.

## Проверка

- `pipeline/check.py` — полнота данных.
- `.venv/bin/python -m unittest discover -s tests` — тесты.
- Локально: `cd site && npx wrangler dev`.
