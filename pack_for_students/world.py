"""
Представление мира игры: парсинг ответа API в структуры, геометрия, проверка безопасности.

Ответственность: только данные поля и вспомогательные функции (следующая клетка, занято ли).
Логику «куда идти» сюда не добавлять — она в strategy.py.
"""
from dataclasses import dataclass

from pack_for_students import config


# ---------------------------------------------------------------------------
# Геометрия хода
# ---------------------------------------------------------------------------

def next_head(x: int, y: int, direction: str) -> tuple[int, int]:
    """
    Координаты клетки после шага из (x, y) в заданном направлении.

    direction — "up" | "down" | "left" | "right".
    Ось Y: вверх = уменьшение y (up -> y-1), вниз = увеличение (down -> y+1).
    """
    if direction == "up":
        return (x, y - 1)
    if direction == "down":
        return (x, y + 1)
    if direction == "left":
        return (x - 1, y)
    return (x + 1, y)


# ---------------------------------------------------------------------------
# Снимок мира (одно состояние поля на один тик)
# ---------------------------------------------------------------------------

@dataclass
class WorldView:
    """
    Снимок мира: препятствия, яблоки, все змейки. Собран из сырого ответа GET /world.

    Поля:
      walls          — множество координат (x, y) стен; наступать нельзя.
      black_apples   — кислотные яблоки (бомбы); наступать нельзя.
      snakes_cells   — все клетки, занятые телами змеек (включая нашу); столкновение = смерть.
      good_apples    — список яблок-целей (red, gold и т.д.), каждое с ключами x, y, type.
      my_head        — (x, y) головы нашей змейки.
      my_direction   — текущее направление ("up"|"down"|"left"|"right"); разворот на 180° запрещён.
      width, height  — размер поля (координаты от 0 до width-1 и 0 до height-1).
    """

    walls: set[tuple[int, int]]
    black_apples: set[tuple[int, int]]
    snakes_cells: set[tuple[int, int]]
    good_apples: list[dict]
    my_head: tuple[int, int]
    my_direction: str
    width: int
    height: int

    @classmethod
    def from_api_response(cls, world: dict) -> "WorldView | None":
        """
        Построить WorldView из ответа GET /world.

        world — сырой dict с ключами me, walls, apples, snakes, width, height.
        Возвращает None, если в world нет тела нашей змейки (me.body пустой или отсутствует).
        """
        me = world.get("me") or {}
        body = me.get("body") or []
        if not body:
            return None
        # Голова — первый элемент тела (индекс 0)
        hx = body[0]["x"]
        hy = body[0]["y"]
        # Собираем стены
        walls = set()
        for w in world.get("walls") or []:
            walls.add((w["x"], w["y"]))
        # Бомбы (кислотные яблоки) — наступать нельзя
        black_apples = set()
        for a in world.get("apples") or []:
            if a.get("type") == "black":
                black_apples.add((a["x"], a["y"]))
        # Все клетки тел змеек (наша + чужие)
        snakes_cells = set()
        snakes = [me] + (world.get("snakes") or [])
        for s in snakes:
            for b in s.get("body") or []:
                snakes_cells.add((b["x"], b["y"]))
        # Хорошие яблоки (не бомбы)
        good_apples = []
        for a in world.get("apples") or []:
            if a.get("type") != "black":
                good_apples.append(a)
        width = world.get("width", 100)
        height = world.get("height", 100)
        return cls(
            walls=walls,
            black_apples=black_apples,
            snakes_cells=snakes_cells,
            good_apples=good_apples,
            my_head=(hx, hy),
            my_direction=me.get("direction", "right"),
            width=width,
            height=height,
        )

    # ---------------------------------------------------------------------------
    # Проверки клеток
    # ---------------------------------------------------------------------------

    def is_inside(self, x: int, y: int) -> bool:
        """Клетка (x, y) в границах поля (0 <= x < width, 0 <= y < height)."""
        return 0 <= x < self.width and 0 <= y < self.height

    def is_obstacle(self, x: int, y: int) -> bool:
        """Стена или бомба — наступать нельзя (смерть или обнуление счёта)."""
        if (x, y) in self.walls:
            return True
        if (x, y) in self.black_apples:
            return True
        return False

    def is_safe_cell(self, x: int, y: int) -> bool:
        """
        Клетка безопасна для шага: в границах, не стена, не бомба, не занята телом змейки.

        Своя голова (my_head) не считается занятой — мы с неё «уходим» на соседнюю клетку.
        """
        if not self.is_inside(x, y):
            return False
        if self.is_obstacle(x, y):
            return False
        if (x, y) in self.snakes_cells and (x, y) != self.my_head:
            return False
        return True

    # ---------------------------------------------------------------------------
    # Направления и соседи (для стратегии и поиска пути)
    # ---------------------------------------------------------------------------

    def safe_directions(self) -> list[str]:
        """
        Список направлений, в которые можно шагнуть с текущей головы.

        Исключён разворот на 180° (OPPOSITE[my_direction]).
        Каждое направление проверено: следующая клетка по is_safe_cell.
        """
        hx, hy = self.my_head
        current = self.my_direction
        allowed = []
        for d in config.DIRECTIONS:
            if d == config.OPPOSITE.get(current):
                continue
            nx, ny = next_head(hx, hy, d)
            if self.is_safe_cell(nx, ny):
                allowed.append(d)
        return allowed

    def count_safe_exits(self, x: int, y: int) -> int:
        """
        Сколько соседних клеток из (x, y) безопасны (0–4).

        Используется для эвристик: идти в клетку с большим числом выходов, чтобы не застрять в тупике.
        """
        return len(self.safe_neighbors(x, y))

    def safe_neighbors(self, x: int, y: int) -> list[tuple[int, int]]:
        """
        Список соседних клеток (до 4), в которые можно шагнуть из (x, y).

        Учитываются границы, стены, бомбы и тела змеек. Порядок не гарантирован.
        Удобно для обхода в ширину/глубину: for (nx, ny) in view.safe_neighbors(cx, cy): ...
        """
        out = []
        for d in config.DIRECTIONS:
            nx, ny = next_head(x, y, d)
            if self.is_inside(nx, ny) and not self.is_obstacle(nx, ny) and (nx, ny) not in self.snakes_cells:
                out.append((nx, ny))
        return out
