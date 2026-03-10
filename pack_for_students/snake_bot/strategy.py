"""
Стратегия бота: как выбрать направление хода по состоянию мира.

Всё в одном файле: выбор цели, поиск пути к ней, запасной ход и конвейер.
Так проще разобраться — меняй функции ниже и константы DEFAULT_* в конце файла.

Схема работы:
  1. Цель — клетка (x, y), к которой хотим идти (яблоко, центр и т.д.). Может быть None — тогда просто уворачиваемся.
  2. Путь — по снимку мира и цели вычислить направление первого шага (up/down/left/right) или None, если путь не найден.
  3. Запасной ход — если цели нет или путь не найден, выбрать любое безопасное направление.

Сигнатуры (подставляй свои функции с такой же сигнатурой):
  - Цель:   функция(view) возвращает (x, y) или None
  - Путь:   функция(view, target) возвращает "up"/"down"/"left"/"right" или None
  - Запасной: функция(view) возвращает одно из "up", "down", "left", "right"
"""
import random
from collections import deque

from snake_bot import config
from snake_bot.world import WorldView, next_head


# =============================================================================
# ВЫБОР ЦЕЛИ — функции (view) -> (x, y) или None
# =============================================================================
# None = «цели нет», бот только уворачивается. Добавляй свои функции и подставляй в DEFAULT_GOAL_SELECTORS.


def no_goal(view):
    """Всегда без цели — бот только уворачивается."""
    return None


def nearest_apple(view):
    """Ближайшее хорошее яблоко (не бомба). Расстояние = |dx| + |dy| от головы."""
    if not view.good_apples:
        return None
    hx, hy = view.my_head
    best_apple = None
    best_dist = 999999
    for a in view.good_apples:
        dist = abs(a["x"] - hx) + abs(a["y"] - hy)
        if dist < best_dist:
            best_dist = dist
            best_apple = a
    if best_apple is None:
        return None
    return (best_apple["x"], best_apple["y"])


def nearest_golden_apple(view):
    """Ближайшее золотое яблоко (type == "golden"). Ставь первым в списке целей, потом nearest_apple."""
    gold = []
    for a in view.good_apples or []:
        if a.get("type") == "golden":
            gold.append(a)
    if not gold:
        return None
    hx, hy = view.my_head
    best_apple = None
    best_dist = 999999
    for a in gold:
        dist = abs(a["x"] - hx) + abs(a["y"] - hy)
        if dist < best_dist:
            best_dist = dist
            best_apple = a
    if best_apple is None:
        return None
    return (best_apple["x"], best_apple["y"])


def center_of_field(view):
    """Центр поля (width//2, height//2). Для тестов или стратегии «держаться центра»."""
    cx = view.width // 2
    cy = view.height // 2
    return (cx, cy)


def nearest_reachable_apple(view):
    """
    Ближайшее хорошее яблоко, до которого есть путь (BFS). Если такого нет — None.
    Сначала проверяем золотые, потом обычные; среди них берём ближайшее по длине пути.
    """
    hx, hy = view.my_head
    best_apple = None
    best_path_len = 999999
    # Сначала золотые, потом все хорошие
    candidates = []
    for a in view.good_apples or []:
        if a.get("type") == "golden":
            candidates.append(a)
    for a in view.good_apples or []:
        if a.get("type") != "golden":
            candidates.append(a)
    for a in candidates:
        tx, ty = a["x"], a["y"]
        if (tx, ty) == (hx, hy):
            return (tx, ty)
        path_len = _bfs_path_length(view, (hx, hy), (tx, ty))
        if path_len is not None and path_len < best_path_len:
            best_path_len = path_len
            best_apple = a
    if best_apple is None:
        return None
    return (best_apple["x"], best_apple["y"])


def _bfs_path_length(view, start, target):
    """Длина кратчайшего пути от start до target или None, если недостижимо."""
    if start == target:
        return 0
    q = deque()
    q.append((start, 0))
    visited = {start}
    while len(q) > 0:
        (cx, cy), dist = q.popleft()
        if (cx, cy) == target:
            return dist
        for neighbor in view.safe_neighbors(cx, cy):
            n = (neighbor[0], neighbor[1])
            if n in visited:
                continue
            visited.add(n)
            q.append((n, dist + 1))
    return None


# =============================================================================
# ПОИСК НАПРАВЛЕНИЯ К ЦЕЛИ — функции (view, target) -> direction | None
# =============================================================================
# Возвращают первый шаг к цели или None (тогда конвейер вызовет запасной ход).
# Для обхода стен используй bfs_first_step; для открытого поля хватает step_toward_manhattan.


def step_toward_manhattan(view, target):
    """
    Один шаг в сторону цели по прямой (расстояние |dx|+|dy|). Стены не обходим.
    Для обхода препятствий подставь bfs_first_step в DEFAULT_PATHFINDER.
    """
    hx, hy = view.my_head
    tx, ty = target
    allowed = view.safe_directions()
    if not allowed:
        return None
    best_d = None
    best_dist = (view.width + view.height) * 2
    for d in allowed:
        nx, ny = next_head(hx, hy, d)
        dist = abs(nx - tx) + abs(ny - ty)
        if dist < best_dist:
            best_dist = dist
            best_d = d
    return best_d


def bfs_first_step(view, target):
    """
    Первый шаг кратчайшего пути до цели (поиск в ширину). Обходит стены и тела змеек.
    Возвращает направление первого шага или None, если до цели не добраться.
    """
    start = view.my_head
    if start == target:
        return None
    # Очередь клеток для обхода
    q = deque()
    q.append(start)
    visited = set()
    visited.add(start)
    parent = {}  # клетка -> откуда пришли

    found = False
    while len(q) > 0:
        cx, cy = q.popleft()
        if (cx, cy) == target:
            found = True
            break
        for neighbor in view.safe_neighbors(cx, cy):
            nx, ny = neighbor[0], neighbor[1]
            if (nx, ny) in visited:
                continue
            visited.add((nx, ny))
            parent[(nx, ny)] = (cx, cy)
            q.append((nx, ny))

    if not found:
        return None

    # Восстанавливаем путь от цели к старту: идём по parent
    path = []
    cur = target
    while cur in parent:
        path.append(cur)
        cur = parent[cur]
    path.append(start)
    path.reverse()
    if len(path) < 2:
        return None
    # Первый шаг — из path[0] (голова) в path[1]
    first_cell = path[1]
    fx, fy = first_cell[0], first_cell[1]
    hx, hy = start[0], start[1]
    for d in config.DIRECTIONS:
        nx, ny = next_head(hx, hy, d)
        if (nx, ny) == (fx, fy):
            return d
    return None


# =============================================================================
# ЗАПАСНОЙ ХОД — функции (view) -> direction
# =============================================================================
# Вызываются, когда цели нет или pathfinder вернул None. Должны вернуть безопасное направление из safe_directions().


def straight_then_random(view):
    """По возможности идём прямо, иначе случайный безопасный ход."""
    allowed = view.safe_directions()
    if not allowed:
        return view.my_direction
    if view.my_direction in allowed:
        return view.my_direction
    return random.choice(allowed)


def random_safe(view):
    """Случайный ход из безопасных направлений."""
    allowed = view.safe_directions()
    if not allowed:
        return view.my_direction
    return random.choice(allowed)


def prefer_more_exits(view):
    """Ход в клетку, из которой больше выходов — меньше шанс застрять в тупике."""
    allowed = view.safe_directions()
    if not allowed:
        return view.my_direction
    hx, hy = view.my_head
    best_dirs = []
    best_count = -1
    for d in allowed:
        nx, ny = next_head(hx, hy, d)
        count = view.count_safe_exits(nx, ny)
        if count > best_count:
            best_count = count
            best_dirs = [d]
        elif count == best_count:
            best_dirs.append(d)
    if view.my_direction in best_dirs:
        return view.my_direction
    return random.choice(best_dirs)


# =============================================================================
# КОНВЕЙЕР — один вызов выполняет: цель → путь → запасной ход
# =============================================================================


def run_pipeline(view, goal_selectors, pathfinder, fallback):
    """
    Конвейер: 1) выбрать цель, 2) найти направление к ней, 3) иначе — запасной ход.
    """
    target = None
    for select in goal_selectors:
        target = select(view)
        if target is not None:
            break
    if target is not None:
        direction = pathfinder(view, target)
        if direction is not None:
            return direction
    return fallback(view)


# =============================================================================
# КОНФИГУРАЦИЯ И ТОЧКА ВХОДА
# =============================================================================
# Умный алгоритм по умолчанию: цель — ближайшее достижимое яблоко (золотое приоритетнее),
# путь — BFS (обход стен и змеек), запасной ход — в сторону с большим числом выходов (избегаем тупиков).
# Можно заменить на no_goal / step_toward_manhattan / straight_then_random для минимального бота.

# Цель: сначала золотое/ближайшее достижимое по пути (BFS), иначе просто ближайшее по прямой.
DEFAULT_GOAL_SELECTORS = [nearest_reachable_apple, nearest_golden_apple, nearest_apple]
# Путь к цели — поиск в ширину, обходим стены и тела.
DEFAULT_PATHFINDER = bfs_first_step
# Запасной ход — в клетку с большим числом безопасных соседей, чтобы не застрять.
DEFAULT_FALLBACK = prefer_more_exits


def choose_direction(world):
    """
    По ответу API выбрать направление хода. Главная функция стратегии.

    world — сырой dict из GET /world. Парсится в WorldView, затем вызывается
    run_pipeline(view, goal_selectors, pathfinder, fallback). Результат — одна из "up"|"down"|"left"|"right".

    Как расширить:
      - Поменяй DEFAULT_GOAL_SELECTORS / DEFAULT_PATHFINDER / DEFAULT_FALLBACK выше.
      - Или в main подставь свою функцию (world: dict) -> str вместо choose_direction.
      - Новые цели и pathfinder — просто добавь функцию с нужной сигнатурой в этот файл и подставь в константы.
    """
    view = WorldView.from_api_response(world)
    if view is None:
        return random.choice(config.DIRECTIONS)
    return run_pipeline(
        view,
        goal_selectors=DEFAULT_GOAL_SELECTORS,
        pathfinder=DEFAULT_PATHFINDER,
        fallback=DEFAULT_FALLBACK,
    )
