# Змейка — мультиплеер по WebSocket

Сервер и веб-интерфейс для многопользовательской змейки. Игра идёт **только по WebSocket**: бот подключается к `ws://HOST/ws/play`, получает состояние пушами после каждого тика и шлёт ход. Раунд 3 минуты, 5 уровней.

---

## Как запускать

### 1. Установить зависимости и запустить сервер

```bash
pip install -r requirements.txt
python -m uvicorn main:app --host 0.0.0.0 --port 8002
```

(Вариант: `python run_game.py` — выведет ссылки для LAN и запустит тот же сервер; пароль админа при этом фиксированный, см. ниже.)

### 2. Открыть в браузере

- **Главная / наблюдение:** http://127.0.0.1:8002/
- **Админка:** http://127.0.0.1:8002/admin

Пароль админа **фиксированный** (задан в коде): `Edhvevcbbohc`. При **первом** запуске игры админ вводит логины игроков (по одному на строку или через запятую; можно оставить player_1, player_2… или указать свои) и нажимает «Создать аккаунты и начать игру». Сервер один раз сохраняет логины и пароли; при следующих стартах выбирается только уровень, те же учётки используются. Логины и пароли отображаются в таблице — раздай их участникам.

### 3. Запустить бота (игрока)

Из папки `pack_for_students`. Нужна библиотека для WebSocket: `pip install websockets` (или `pip install -r requirements.txt` в этой папке). Логин и пароль — из таблицы в админке после старта игры:

```bash
cd pack_for_students
pip install -r requirements.txt
python bot.py http://127.0.0.1:8002 player_1 ПАРОЛЬ_ИЗ_АДМИНКИ
```

Для локального сервера URL можно не указывать: `python bot.py player_1 ПАРОЛЬ_ИЗ_АДМИНКИ`  
Четвёртый аргумент — имя игрока: `python bot.py ... ПАРОЛЬ МойБот`

### Ссылки

- Наблюдение: **http://ADDRESS:8002/**
- Админка: **http://ADDRESS:8002/admin**
- Документация API: **http://ADDRESS:8002/docs**

---

# Справочник: объекты на карте, JSON, карта логики

## Объекты на карте

На поле есть только следующие сущности (все с целочисленными координатами `x`, `y`):

| Объект | Описание | В JSON / WorldView |
|--------|----------|--------------------|
| **Стены (walls)** | Непроходимые клетки: рамка по краям поля + случайные препятствия (число зависит от уровня). Наступил — смерть. | `walls` — список `{"x": x, "y": y}`. В WorldView: `view.walls` — `set[(x,y)]`. |
| **Яблоки (apples)** | Разные типы; каждая клетка — одно яблоко с полем `type`. | В ответе API: `apples`: `[{"x", "y", "type"}, ...]`. В WorldView: `black_apples` — set координат бомб; `good_apples` — список dict с `x`, `y`, `type` (все кроме бомб). |
| **Змейки (snakes / me)** | Игроки и боты. Тело — список клеток; первая клетка — голова. Есть направление движения, очки, флаги alive, бафы. | `me` — наша змейка; `snakes` — остальные. В WorldView все тела собраны в `snakes_cells`, наша голова — `my_head`, направление — `my_direction`. |

### Типы яблок (поле `type` в API)

| type | Название | Эффект |
|------|----------|--------|
| **normal** | Красное яблоко | +1 очко, змейка удлиняется. |
| **golden** | Золотое | +10 очков, удлинение. |
| **black** | Кислотное (бомба) | Наступить нельзя: обнуление счёта, смерть. В боте это `black_apples`; в цели не выбирать. |
| **speed_15** | Голубое (скорость) | Баф: 15 тиков змейка двигается дважды за тик. |
| **speed_30** | Голубое (длинный баф) | То же на 30 тиков. |
| **shield** | Фиолетовое (щит) | До 2 щитов: одно столкновение забирает щит вместо жизни. |

В логике бота «хорошие» яблоки — все, у которых `type != "black"` (это `view.good_apples`). Целью можно выбирать любую клетку из `good_apples`; тип можно смотреть в `a["type"]` (например приоритет золоту).

---

## Формат JSON: ответ GET /world

Сервер отдаёт мир **в радиусе** от головы запрашивающего игрока (радиус задаётся на сервере). Структура:

```json
{
  "game_started": true,
  "tick": 42,
  "width": 80,
  "height": 80,
  "level": 1,
  "game_ended": false,
  "game_duration_ticks": 720,
  "level_multipliers": {"1": 1, "2": 2, "3": 3, "4": 4, "5": 5},

  "me": {
    "id": "player_1",
    "name": "Player",
    "body": [{"x": 10, "y": 5}, {"x": 9, "y": 5}, {"x": 8, "y": 5}],
    "direction": "right",
    "score": 12,
    "alive": true,
    "speed_boost_until_tick": 0,
    "shield_count": 0,
    "level_scores": {"1": 12},
    "total_weighted": 12
  },

  "walls": [{"x": 0, "y": 0}, {"x": 1, "y": 0}, ...],

  "apples": [
    {"x": 15, "y": 8, "type": "normal"},
    {"x": 20, "y": 10, "type": "golden"},
    {"x": 7, "y": 3, "type": "black"}
  ],

  "snakes": [
    {
      "id": "player_2",
      "name": "Player 2",
      "body": [{"x": 30, "y": 20}, ...],
      "score": 5,
      "alive": true,
      "speed_boost_until_tick": 0,
      "shield_count": 0
    }
  ],

  "leaderboard": [
    {"id": "player_1", "name": "Player", "score": 12, "alive": true, "level_scores": {...}, "total_weighted": 12},
    ...
  ]
}
```

- **me.body** — список клеток от головы к хвосту; **body[0]** — голова.
- **me.direction** — текущее направление: `"up"` | `"down"` | `"left"` | `"right"`.
- **walls** / **apples** — только те, что попали в радиус обзора.
- **snakes** — другие змейки, у которых хотя бы один сегмент в радиусе; у каждой полное **body**.
- Если игрок не найден или игра не начата, может вернуться `{"game_started": false}` или `{"error": "..."}`.

POST /step: тело запроса `{"direction": "up"|"down"|"left"|"right"}`. Ответ при успехе: `{"ok": true}`.

---

## Карта логики: где какая функция и что можно делать

Ниже — по файлам и функциям: что вызывается, что делают, куда можно встраивать свой код.

### Корень и точка входа

| Файл | Функция / объект | Что делает | Что можно делать |
|------|------------------|------------|------------------|
| **bot.py** | `run()` (из main) | Запуск бота. | Менять не обязательно; при необходимости запускать свой модуль вместо `snake_bot.main.run()`. |

### snake_bot — конфиг и API

| Файл | Функция / объект | Что делает | Что можно делать |
|------|------------------|------------|------------------|
| **config.py** | `DIRECTIONS`, `OPPOSITE` | Константы направлений и запрет разворота на 180°. | Использовать в своей логике при переборе ходов. |
| **config.py** | `BASE_URL`, `PLAYER_ID`, `PASSWORD`, `NAME` | Параметры подключения и имя. | Задавать через аргументы при запуске или менять по умолчанию. |
| **config.py** | `from_argv()` | Читает из `sys.argv` URL, логин, пароль, имя. | Вызывается в main при старте; порядок аргументов: URL, player_id, password, name. |
| **config.py** | `TICK_INTERVAL`, `RETRY_INTERVAL` | Пауза между ходами и при повторе при ошибке. | При необходимости изменить под свою частоту запросов. |
| **api.py** | `get_world()` | GET /world, возвращает dict или None. | Не менять; использовать результат как вход для стратегии. |
| **api.py** | `step(direction)` | POST /step с выбранным направлением. | Не менять; вызывается из main после `choose_direction`. |

### snake_bot — мир (данные поля)

| Файл | Функция / объект | Что делает | Что можно делать |
|------|------------------|------------|------------------|
| **world.py** | `next_head(x, y, direction)` | Возвращает координаты клетки после шага из (x,y) в направлении. | Использовать для перебора соседей и восстановления направления по пути (pathfinding). |
| **world.py** | `WorldView` | Dataclass: walls, black_apples, snakes_cells, good_apples, my_head, my_direction, width, height. | Читать поля; не менять разбор (он завязан на формат API). |
| **world.py** | `WorldView.from_api_response(world)` | Парсит dict ответа GET /world в WorldView. | Вызывать в стратегии или в своей функции из main; при отсутствии тела вернёт None. |
| **world.py** | `view.is_inside(x, y)` | Клетка в границах поля. | Использовать в своих проверках и обходах. |
| **world.py** | `view.is_obstacle(x, y)` | Стена или бомба. | Определять непроходимые клетки. |
| **world.py** | `view.is_safe_cell(x, y)` | Свободная клетка (границы, не стена, не бомба, не тело змейки). | Проверка, можно ли наступить. |
| **world.py** | `view.safe_directions()` | Список направлений, в которые можно шагнуть с головы (без разворота на 180°). | Основа для выбора хода и fallback. |
| **world.py** | `view.safe_neighbors(x, y)` | Список соседних безопасных клеток из (x,y). | BFS/A* и любые обходы по полю. |
| **world.py** | `view.count_safe_exits(x, y)` | Число безопасных соседей (0–4). | Эвристики «избегать тупиков» в fallback. |

### snake_bot — стратегия и конвейер

| Файл | Функция / объект | Что делает | Что можно делать |
|------|------------------|------------|------------------|
| **strategy.py** | `DEFAULT_GOAL_SELECTORS` | Список функций выбора цели. | Подставить свои или готовые: `no_goal`, `nearest_apple`, `nearest_golden_apple`, `center_of_field`. |
| **strategy.py** | `DEFAULT_PATHFINDER` | Функция (view, target) → direction \| None. | Подставить `step_toward_manhattan`, `bfs_first_step` или свою. |
| **strategy.py** | `DEFAULT_FALLBACK` | Функция (view) → direction. | Подставить `straight_then_random`, `random_safe`, `prefer_more_exits` или свою. |
| **strategy.py** | `choose_direction(world)` | Парсит world в WorldView, вызывает run_pipeline с константами выше. | Заменить вызов в main на свою функцию с сигнатурой (world) → str — если нужна полностью своя логика. |

### snake_bot — логика (цели, путь, fallback, конвейер)

| Файл | Функция / объект | Что делает | Что можно делать |
|------|------------------|------------|------------------|
| **logic/pipeline.py** | `run(view, goal_selectors, pathfinder, fallback)` | Перебирает цели → pathfinder → при отсутствии пути fallback; возвращает направление. | Вызывать из своей стратегии с своими списками/функциями; не обязательно менять файл. |
| **logic/goals.py** | `no_goal(view)` | Всегда None. | Использовать когда цель не нужна. |
| **logic/goals.py** | `nearest_apple(view)` | Ближайшее яблоко по Манхэттену (из good_apples). | Добавить в goal_selectors. |
| **logic/goals.py** | `nearest_golden_apple(view)` | Ближайшее яблоко с type "golden". | Добавить первым в goal_selectors для приоритета золота. |
| **logic/goals.py** | `center_of_field(view)` | Центр (width//2, height//2). | Тесты или стратегия «держаться центра». |
| **logic/goals.py** | — | Сигнатура своей цели: `(view) -> (x,y)|None`. | Добавить функцию в этот файл и подставить в DEFAULT_GOAL_SELECTORS. |
| **logic/pathfinding.py** | `step_toward_manhattan(view, target)` | Один шаг к цели по Манхэттену, без обхода стен. | Открытое поле или быстрый выбор направления. |
| **logic/pathfinding.py** | `bfs_first_step(view, target)` | Первый шаг BFS-пути до цели (учёт стен и змеек). | Подставить как DEFAULT_PATHFINDER для лабиринтов. |
| **logic/pathfinding.py** | — | Своя функция: `(view, target) -> direction|None`. | Реализовать A* или другой алгоритм по safe_neighbors и подставить в конвейер. |
| **logic/fallback.py** | `straight_then_random(view)` | Прямо, иначе случайный из safe_directions. | Стандартный запасной ход. |
| **logic/fallback.py** | `random_safe(view)` | Случайный из safe_directions. | Когда не нужен приоритет «прямо». |
| **logic/fallback.py** | `prefer_more_exits(view)` | Ход в клетку с большим count_safe_exits. | Снижение риска тупика. |
| **logic/fallback.py** | — | Своя функция: `(view) -> direction`. | Обязательно возвращать направление из safe_directions (или my_direction в крайнем случае). |
| **logic/types.py** | `GoalSelector`, `Pathfinder`, `FallbackStrategy`, `Strategy` | Protocol-типы для аннотаций. | Использовать в типах своих функций; наследование не требуется. |

### snake_bot — главный цикл

| Файл | Функция / объект | Что делает | Что можно делать |
|------|------------------|------------|------------------|
| **main.py** | `run()` | Цикл: get_world → проверки → choose_direction(world) → step → sleep. | Подменить только вызов стратегии: заменить `choose_direction` на свою функцию (world) → str; остальное не трогать. |

Итого: объекты на карте и типы яблок заданы сервером; JSON — как выше; свою логику удобнее всего встраивать через константы в **strategy.py** (цели, pathfinder, fallback) или через отдельные функции в **logic/** и подстановку в конвейер; при полной кастомизации — своя функция в **main** вместо `choose_direction`.

---

# Полное руководство: как писать код бота с нуля

Ниже — всё, что нужно знать, чтобы разобраться в проекте и правильно использовать готовые интерфейсы для своей логики.

---

## 1. Как устроена игра

- **Управления в браузере нет.** Игра идёт только через API.
- Сервер **тикает 2 раза в секунду** (интервал 0.5 сек). За один тик каждый игрок может отправить **один ход** (направление).
- **Один раунд** длится 3 минуты; есть 5 уровней с разным полем и объектами.
- Твой код в каждом тике должен:
  1. Запросить текущее состояние мира (**GET /world**).
  2. По этому состоянию решить, куда идти.
  3. Отправить ход (**POST /step** с телом `{"direction": "up"|"down"|"left"|"right"}`).

В репозитории уже есть бот, который это делает в цикле. Тебе нужно только подставить **свою логику выбора направления**, используя готовые интерфейсы.

---

## 2. Как устроен бот (общий поток)

- **Точка входа:** `bot.py` вызывает `snake_bot.main.run()`.
- **main.run()** в бесконечном цикле:
  1. Читает конфиг из аргументов (`config.from_argv()`).
  2. Запрашивает мир: `world = get_world()` (это dict из GET /world).
  3. Проверяет: нет ответа, ошибка, игра не начата, игра окончена, мы мёртвы — тогда ждёт и повторяет.
  4. Вызывает **`direction = choose_direction(world)`** — **единственное место, где принимается решение о ходе.**
  5. Отправляет ход: `step(direction)`.
  6. Спит ~0.5 сек до следующего тика.

Чтобы писать свой код «правильно», нужно понимать:

- Что такое **world** (сырой ответ API) и зачем он превращается в **WorldView**.
- Что такое **конвейер** (цель → путь → запасной ход) и какие у него **интерфейсы**.
- **Где** и **как** подставлять свои функции, не ломая запросы к серверу и цикл.

Дальше по шагам: данные мира, интерфейсы, затем — как именно писать свой код.

---

## 3. Данные мира: от API к WorldView

### 3.1 Сырой ответ API (world)

`get_world()` возвращает **dict** с ключами вроде:

- `me` — наша змейка: `body` (список клеток, первая — голова), `direction`, `score`, `alive` и т.д.
- `walls` — список объектов с `x`, `y`.
- `apples` — список яблок с `x`, `y`, `type` (normal, golden, black, speed_15, speed_30, shield — см. раздел «Объекты на карте» выше).
- `snakes` — другие змейки (та же структура тела).
- `width`, `height` — размер поля.
- `tick`, `level`, `game_started`, `game_ended` и др.

С этим dict можно работать напрямую, но в коде бота он обычно **сразу превращается в WorldView** — так проще и безопаснее писать логику.

### 3.2 WorldView — снимок поля на один тик

**WorldView** — это уже разобранный и удобный снимок мира. Создаётся так:

```python
from snake_bot.world import WorldView

view = WorldView.from_api_response(world)  # world — dict из get_world()
```

Если по какой-то причине нет данных о нашей змейке, `from_api_response` вернёт `None`. Иначе у тебя есть объект **view** со всеми полями и методами ниже.

#### Поля (только чтение)

| Поле | Тип | Описание |
|------|-----|----------|
| **walls** | `set[tuple[int, int]]` | Координаты `(x, y)` стен. Наступать нельзя. |
| **black_apples** | `set[tuple[int, int]]` | Координаты кислотных яблок (бомб). Наступать нельзя. |
| **snakes_cells** | `set[tuple[int, int]]` | Все клетки, занятые телами змеек (включая нашу). Столкновение головой = смерть. |
| **good_apples** | `list[dict]` | Яблоки-цели (не бомбы). У каждого есть `x`, `y`, `type` (например `"red"`, `"gold"`). |
| **my_head** | `tuple[int, int]` | Координаты `(x, y)` головы нашей змейки. |
| **my_direction** | `str` | Текущее направление: `"up"` \| `"down"` \| `"left"` \| `"right"`. Разворот на 180° за один тик запрещён. |
| **width** | `int` | Ширина поля. Координата x от 0 до width-1. |
| **height** | `int` | Высота поля. Координата y от 0 до height-1. |

Координаты: **x** растёт вправо, **y** растёт вниз. **up** = уменьшение y, **down** = увеличение y.

#### Методы WorldView

- **`view.is_inside(x, y) -> bool`**  
  Клетка в границах поля (0 ≤ x < width, 0 ≤ y < height).

- **`view.is_obstacle(x, y) -> bool`**  
  Клетка — стена или бомба; наступать нельзя.

- **`view.is_safe_cell(x, y) -> bool`**  
  Клетка безопасна для шага: в границах, не стена, не бомба, не занята телом змейки. Своя голова не считается «занятой» (мы с неё уходим).

- **`view.safe_directions() -> list[str]`**  
  Список направлений, в которые **можно** шагнуть с текущей головы: учтены границы, стены, бомбы, тела змеек и запрет разворота на 180°. Каждый элемент — одна из `"up"`, `"down"`, `"left"`, `"right"`.

- **`view.safe_neighbors(x, y) -> list[tuple[int, int]]`**  
  Список соседних клеток `(nx, ny)` (до 4), в которые можно шагнуть из `(x, y)`. Учитываются границы, стены, бомбы и тела змеек. Нужен для обхода в ширину/глубину (BFS, A* и т.п.).

- **`view.count_safe_exits(x, y) -> int`**  
  Сколько у клетки `(x, y)` безопасных соседей (0–4). Полезно для эвристик «не заходить в тупик».

#### Вспомогательная функция (модуль world)

- **`next_head(x, y, direction) -> tuple[int, int]`**  
  Координаты клетки после шага из `(x, y)` в заданном направлении.  
  Пример: `next_head(5, 5, "up")` → `(5, 4)`.

Итого: для своей логики тебе дают **view** (WorldView) и **next_head**. Этого достаточно, чтобы выбирать цель, строить путь и решать, куда идти, если цели нет.

---

## 4. Как устроен выбор хода: конвейер (pipeline)

В коде решение «куда идти» разбито на **три шага**. Так проще подставлять свою логику по частям.

1. **Выбор цели** — есть ли клетка `(x, y)`, к которой мы хотим идти (яблоко, центр поля и т.д.)? Если нет — переходим сразу к шагу 3.
2. **Поиск направления к цели** — по снимку мира и цели вычислить первый шаг (направление). Если путь не найден — переходим к шагу 3.
3. **Запасной ход** — когда цели нет или путь к ней не найден, выбрать любое безопасное направление (например «прямо» или «в клетку с большим числом выходов»).

Каждый шаг реализован **отдельными функциями**. Их список и сигнатуры — это и есть **интерфейсы**, которые ты используешь.

### 4.1 Интерфейс «выбор цели» (GoalSelector)

- **Сигнатура:** функция принимает один аргумент — **view: WorldView**, возвращает **tuple[int, int] | None**.
- **Смысл:** вернуть координаты цели `(x, y)` или `None`, если цели нет (тогда конвейер сразу пойдёт в запасной ход).

Примеры готовых функций (модуль `snake_bot.logic.goals`):

- **no_goal(view)** — всегда `None` (бот только уворачивается).
- **nearest_apple(view)** — ближайшее по Манхэттену «хорошее» яблоко; иначе `None`.
- **nearest_golden_apple(view)** — ближайшее золотое яблоко; иначе `None`.
- **center_of_field(view)** — центр поля `(width//2, height//2)`.

Ты можешь написать свою функцию с той же сигнатурой и использовать её в конвейере.

### 4.2 Интерфейс «направление к цели» (Pathfinder)

- **Сигнатура:** функция принимает **view: WorldView** и **target: tuple[int, int]**, возвращает **str | None**.
- **Смысл:** вернуть направление **первого шага** к цели (`"up"` \| `"down"` \| `"left"` \| `"right"`) или `None`, если путь не найден / недостижим (тогда конвейер вызовет запасной ход).

Примеры готовых (модуль `snake_bot.logic.pathfinding`):

- **step_toward_manhattan(view, target)** — один шаг, уменьшающий Манхэттеново расстояние до цели. Не обходит стены.
- **bfs_first_step(view, target)** — первый шаг кратчайшего пути (BFS), с учётом стен и змеек через `view.safe_neighbors`.

Ты можешь добавить свою (например A*) с сигнатурой `(view, target) -> str | None` и подставить в конвейер.

### 4.3 Интерфейс «запасной ход» (FallbackStrategy)

- **Сигнатура:** функция принимает **view: WorldView**, возвращает **str** — одно из `"up"`, `"down"`, `"left"`, `"right"`.
- **Смысл:** когда цели нет или pathfinder вернул `None`, эта функция должна вернуть **безопасное** направление (лучше из `view.safe_directions()`; если список пуст — можно вернуть `view.my_direction`).

Примеры готовых (модуль `snake_bot.logic.fallback`):

- **straight_then_random(view)** — по возможности прямо, иначе случайный из безопасных.
- **random_safe(view)** — случайный из безопасных.
- **prefer_more_exits(view)** — ход в клетку с большим числом безопасных выходов (меньше шанс тупика).

Свою функцию с сигнатурой `(view) -> str` тоже можно подставить.

### 4.4 Как конвейер вызывается в коде

В **strategy.py** определена одна точка входа:

```python
def choose_direction(world: dict) -> str:
    view = WorldView.from_api_response(world)
    if view is None:
        return random.choice(config.DIRECTIONS)  # крайний случай
    return run_pipeline(
        view,
        goal_selectors=DEFAULT_GOAL_SELECTORS,
        pathfinder=DEFAULT_PATHFINDER,
        fallback=DEFAULT_FALLBACK,
    )
```

Константы в **strategy.py**:

- **DEFAULT_GOAL_SELECTORS** — список функций «выбор цели». Перебираются по порядку; первая, вернувшая не `None`, даёт цель.
- **DEFAULT_PATHFINDER** — одна функция «направление к цели».
- **DEFAULT_FALLBACK** — одна функция «запасной ход».

**run_pipeline** (модуль `snake_bot.logic.pipeline`) делает ровно то, что описано выше: перебирает цели → вызывает pathfinder → при необходимости fallback. Возвращает всегда одно из четырёх направлений.

---

## 5. Как правильно писать свой код: пошагово

Ниже — конкретные способы встроить свою логику, от самого простого к более свободному.

### 5.1 Только поменять константы (без нового кода)

Файл: **snake_bot/strategy.py**.

- Чтобы бот шёл к **ближайшему яблоку** по прямой (Manhattan), замени:
  - `DEFAULT_GOAL_SELECTORS = [no_goal]` на  
    `DEFAULT_GOAL_SELECTORS = [nearest_apple]`  
  (импорт `nearest_apple` добавь из `snake_bot.logic`).
- Чтобы **сначала золото, потом любое яблоко**:
  - `DEFAULT_GOAL_SELECTORS = [nearest_golden_apple, nearest_apple]`.
- Чтобы путь к цели **обходил стены** (BFS):
  - `DEFAULT_PATHFINDER = step_toward_manhattan` замени на  
    `DEFAULT_PATHFINDER = bfs_first_step`  
  (импорт из `snake_bot.logic`).
- Чтобы запасной ход **избегал тупиков**:
  - `DEFAULT_FALLBACK = straight_then_random` замени на  
    `DEFAULT_FALLBACK = prefer_more_exits`.

Никаких новых файлов не нужно — только правка констант и импортов в **strategy.py**.

### 5.2 Добавить свою цель (GoalSelector)

1. Открой **snake_bot/logic/goals.py**.
2. Напиши функцию с сигнатурой **`(view: WorldView) -> tuple[int, int] | None`**.
   - Внутри используй `view.my_head`, `view.good_apples`, `view.width`, `view.height` и т.д.
   - Верни `(x, y)` клетки-цели или `None`.
3. В **strategy.py** импортируй эту функцию и добавь её в **DEFAULT_GOAL_SELECTORS** (например в начало списка).

Пример: цель — ближайшее яблоко с типом `"red"`:

```python
# в logic/goals.py
def nearest_red_apple(view: WorldView) -> tuple[int, int] | None:
    red = [a for a in (view.good_apples or []) if a.get("type") == "red"]
    if not red:
        return None
    hx, hy = view.my_head
    a = min(red, key=lambda ap: abs(ap["x"] - hx) + abs(ap["y"] - hy))
    return (a["x"], a["y"])
```

В strategy.py: `from snake_bot.logic.goals import ..., nearest_red_apple` и `DEFAULT_GOAL_SELECTORS = [nearest_red_apple]` (или добавь в список).

### 5.3 Добавить свой pathfinder (направление к цели)

1. Открой **snake_bot/logic/pathfinding.py**.
2. Напиши функцию **`(view: WorldView, target: tuple[int, int]) -> str | None`**.
   - Для обхода препятствий используй `view.safe_neighbors(cx, cy)` и, при желании, `next_head` из `snake_bot.world`.
   - Верни направление первого шага к цели или `None`, если путь не найден.
3. В **strategy.py** импортируй её и задай **DEFAULT_PATHFINDER = твоя_функция**.

Пример каркаса BFS уже есть — `bfs_first_step`. Свой A* или жадный алгоритм можно сделать по тому же принципу: обход по `safe_neighbors`, восстановление пути, первый шаг → направление через `next_head`.

### 5.4 Добавить свой fallback (запасной ход)

1. Открой **snake_bot/logic/fallback.py**.
2. Напиши функцию **`(view: WorldView) -> str`**.
   - Обязательно возвращай направление из **view.safe_directions()** (или в крайнем случае **view.my_direction**).
3. В **strategy.py** задай **DEFAULT_FALLBACK = твоя_функция**.

### 5.5 Полностью своя логика (без конвейера)

Если хочешь решать направление целиком по-своему:

1. Напиши функцию с сигнатурой **`(world: dict) -> str`** (как у `choose_direction`).
2. Внутри по желанию построй view:  
   `view = WorldView.from_api_response(world)`  
   и используй **view** и **next_head** как угодно.
3. В **snake_bot/main.py** замени импорт и вызов: вместо  
   `from snake_bot.strategy import choose_direction`  
   импортируй свою функцию и в цикле вызывай её вместо `choose_direction(world)`.

Тогда конвейер можно не использовать — ты сам решаешь, как из world/view получить направление.

---

## 6. Структура файлов бота (навигация)

| Путь | Назначение |
|------|------------|
| **bot.py** | Точка входа: запуск `snake_bot.main.run()`. |
| **snake_bot/config.py** | URL, player_id, password, DIRECTIONS, OPPOSITE, TICK_INTERVAL; парсинг argv. |
| **snake_bot/api.py** | `get_world()` → dict, `step(direction)` → bool. |
| **snake_bot/world.py** | `WorldView`, `next_head`; парсинг world в view, проверки клеток, safe_directions, safe_neighbors. |
| **snake_bot/logic/goals.py** | Функции выбора цели: no_goal, nearest_apple, nearest_golden_apple, center_of_field. |
| **snake_bot/logic/pathfinding.py** | Функции направления к цели: step_toward_manhattan, bfs_first_step. |
| **snake_bot/logic/fallback.py** | Запасной ход: straight_then_random, random_safe, prefer_more_exits. |
| **snake_bot/logic/pipeline.py** | `run(view, goal_selectors, pathfinder, fallback)` — конвейер. |
| **snake_bot/logic/types.py** | Protocol-типы GoalSelector, Pathfinder, FallbackStrategy, Strategy (для аннотаций). |
| **snake_bot/strategy.py** | `choose_direction(world)` и константы DEFAULT_GOAL_SELECTORS, DEFAULT_PATHFINDER, DEFAULT_FALLBACK. |
| **snake_bot/main.py** | Цикл: get_world → проверки → choose_direction(world) → step → sleep. |

Используй интерфейсы (WorldView, цели, pathfinder, fallback) и константы в strategy.py — так твой код остаётся предсказуемым и масштабируемым.

---

## 7. Правила игры (кратко)

- **Уровни:** 1–5, разный размер поля и число ботов. Раунд 3 минуты. Общий счёт — взвешенная сумма лучших очков по уровням.
- **Яблоки:** красное +1, золотое +10; кислотное (чёрное) — бомба, обнуляет счёт, наступать нельзя; голубое — баф скорости, фиолетовое — щит.
- **Смерть:** стена, своё тело или голова другой змейки. Респавн через несколько тиков.

---

## 8. API (кратко)

| Метод | Путь | Описание |
|-------|------|----------|
| GET | /world | Мир. Параметры: player_id, password, name (опц.). Ответ: me, apples, snakes, walls, width, height, tick, level, game_ended и др. |
| POST | /step | Ход. Параметры: player_id, password. Body: `{"direction": "up"\|"down"\|"left"\|"right"}`. |

Подробный формат ответов — в **http://ADDRESS:8002/docs** (OpenAPI).

Примеры curl:

```bash
curl "http://127.0.0.1:8002/world?player_id=p1&password=SECRET&name=Player"
curl -X POST "http://127.0.0.1:8002/step?player_id=p1&password=SECRET" \
  -H "Content-Type: application/json" -d '{"direction":"up"}'
```

---

## 9. Игра по Wi‑Fi

Запуск сервера с доступом в локальную сеть:

```bash
python -m uvicorn main:app --host 0.0.0.0 --port 8002
```

Узнать свой IP: на Mac `ipconfig getifaddr en0`, в Windows — `ipconfig` (IPv4). Подключаться по **http://IP:8002**. Файрвол должен разрешать порт.
