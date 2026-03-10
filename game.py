"""
Игровая логика: змейка, яблоки, поле.
4 тика в секунду, игра длится 3 минуты (720 тиков).
Уровни 1–5 и start_game — в levels.py и через start_game().
"""
import asyncio
import random
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from levels import LEVELS

INITIAL_SNAKE_LEN = 3

APPLE_NORMAL = "normal"
APPLE_BLACK = "black"
APPLE_GOLDEN = "golden"
APPLE_SPEED_15 = "speed_15"
APPLE_SPEED_30 = "speed_30"
APPLE_SHIELD = "shield"


class Direction(str, Enum):
    UP = "up"
    DOWN = "down"
    LEFT = "left"
    RIGHT = "right"


RESPAWN_AFTER_TICKS = 5
TICKS_PER_SECOND = 4
GAME_DURATION_SECONDS = 3 * 60  # 3 минуты
GAME_DURATION_TICKS = TICKS_PER_SECOND * GAME_DURATION_SECONDS  # 720
# Множитель для общего счёта: чем сложнее уровень, тем больше весит результат
LEVEL_MULTIPLIERS = {1: 1, 2: 2, 3: 3, 4: 4, 5: 5}


@dataclass
class Player:
    player_id: str
    name: str
    body: list[tuple[int, int]]  # голова = body[0]
    direction: Direction
    next_direction: Direction
    score: int = 0
    alive: bool = True
    death_tick: Optional[int] = None
    is_bot: bool = False
    speed_boost_until_tick: int = 0  # до этого тика змейка двигается дважды за тик
    shield_count: int = 0  # кол-во «жизней» от щита (одно врезание = -1)

    def head(self) -> tuple[int, int]:
        return self.body[0] if self.body else (0, 0)


def make_walls_for_level(level: int) -> set[tuple[int, int]]:
    """Рамка по краям + случайные препятствия по конфигу уровня. Размер поля из конфига."""
    cfg = LEVELS.get(level, LEVELS[1])
    wd, ht = cfg["grid_width"], cfg["grid_height"]
    n = cfg["obstacles"]
    w = set()
    for x in range(wd):
        w.add((x, 0))
        w.add((x, ht - 1))
    for y in range(ht):
        w.add((0, y))
        w.add((wd - 1, y))
    for _ in range(n):
        x = random.randint(1, wd - 2)
        y = random.randint(1, ht - 2)
        w.add((x, y))
    return w


@dataclass
class GameState:
    players: dict[str, Player] = field(default_factory=dict)
    apples: dict[tuple[int, int], str] = field(default_factory=dict)
    walls: set[tuple[int, int]] = field(default_factory=set)
    tick: int = 0
    game_started: bool = False
    game_ended: bool = False  # True после GAME_DURATION_TICKS
    level: int = 1
    width: int = 80  # из LEVELS[1], обновляется в start_game
    height: int = 80
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    # Очки по уровням и взвешенный общий счёт (сохраняются между раундами)
    _level_scores: dict[str, dict[int, int]] = field(default_factory=dict)  # player_id -> { level -> лучший счёт }
    _total_weighted: dict[str, int] = field(default_factory=dict)  # player_id -> сумма level_scores[l]*multiplier[l]
    _last_tick_time: float = 0.0  # monotonic time последнего тика (для sleep_until_next_tick)
    # История раундов: последние игры (уровень, тик окончания, результаты игроков)
    _game_history: list[dict] = field(default_factory=list)
    _game_history_max: int = 50

    def _random_empty_cell(self, exclude: set[tuple[int, int]]) -> Optional[tuple[int, int]]:
        for _ in range(50_000):
            x = random.randint(0, self.width - 1)
            y = random.randint(0, self.height - 1)
            if (x, y) not in self.walls and (x, y) not in exclude:
                return (x, y)
        return None

    def spawn_apples(self):
        """Доводим количество яблок/бафов до минимума по конфигу уровня. Если из-за смертей стало больше — не трогаем."""
        cfg = LEVELS.get(self.level, LEVELS[1])
        occupied = set(self.apples.keys())
        for p in self.players.values():
            if p.alive:
                occupied.update(p.body)
        for kind, key in [
            (APPLE_NORMAL, "normal"),
            (APPLE_BLACK, "black"),
            (APPLE_GOLDEN, "golden"),
            (APPLE_SPEED_15, "speed_15"),
            (APPLE_SPEED_30, "speed_30"),
            (APPLE_SHIELD, "shield"),
        ]:
            required = cfg.get(key, 0)
            current = sum(1 for t in self.apples.values() if t == kind)
            to_spawn = max(0, required - current)
            for _ in range(to_spawn):
                cell = self._random_empty_cell(occupied)
                if cell:
                    self.apples[cell] = kind
                    occupied.add(cell)

    def _finalize_round(self) -> None:
        """Зафиксировать результаты раунда: обновить лучшие очки по уровням, общий счёт и историю игр."""
        current_level = self.level
        # Обновляем лучшие результаты по уровням и взвешенный общий счёт
        for pid, p in list(self.players.items()):
            if pid not in self._level_scores:
                self._level_scores[pid] = {}
            best_for_level = self._level_scores[pid].get(current_level, 0)
            if p.score > best_for_level:
                self._level_scores[pid][current_level] = p.score
            total = 0
            for lvl, sc in self._level_scores[pid].items():
                mult = LEVEL_MULTIPLIERS.get(lvl, 1)
                total += sc * mult
            self._total_weighted[pid] = total

        # Сохраняем «снимок» раунда в историю
        results = []
        for p in self.players.values():
            results.append({
                "id": p.player_id,
                "name": p.name,
                "score": p.score,
                "alive": p.alive,
            })
        results.sort(key=lambda r: r["score"], reverse=True)
        place = 1
        for r in results:
            r["place"] = place
            place += 1

        entry = {
            "level": current_level,
            "tick_end": self.tick,
            "players": results,
        }
        self._game_history.append(entry)
        if len(self._game_history) > self._game_history_max:
            self._game_history = self._game_history[-self._game_history_max:]

    def _opposite_direction(self, d: Direction) -> Direction:
        if d == Direction.UP:
            return Direction.DOWN
        if d == Direction.DOWN:
            return Direction.UP
        if d == Direction.LEFT:
            return Direction.RIGHT
        return Direction.LEFT

    def _bot_choose_direction(self, p: Player) -> Direction:
        """Тот же алгоритм, что в bot.py: безопасные ходы (стенки и бомбы избегаем), затем шаг к ближайшему хорошему яблоку."""
        hx, hy = p.head()
        walls = self.walls
        black_apples = {pos for pos, t in self.apples.items() if t == APPLE_BLACK}
        snakes_cells = set()
        for other in self.players.values():
            for pos in other.body:
                snakes_cells.add(pos)

        def safe(d: Direction) -> bool:
            nh = self._move_head((hx, hy), d)
            if nh in walls:
                return False
            if nh in black_apples:
                return False
            if nh[0] < 0 or nh[0] >= self.width or nh[1] < 0 or nh[1] >= self.height:
                return False
            if nh in snakes_cells:
                return False
            return True

        opposite = self._opposite_direction(p.direction)
        allowed = [d for d in Direction if d != opposite and safe(d)]
        if not allowed:
            return p.direction

        # Только яблоки, которые дают очки (боты не целятся в бомбы)
        good_apples = [pos for pos, t in self.apples.items() if t != APPLE_BLACK]
        if not good_apples:
            return random.choice(allowed)

        def dist_to(pos: tuple[int, int]) -> int:
            return abs(pos[0] - hx) + abs(pos[1] - hy)

        nearest = min(good_apples, key=dist_to)
        best_d = None
        best_dist = dist_to(nearest) + 1
        for d in allowed:
            nh = self._move_head((hx, hy), d)
            d2 = abs(nearest[0] - nh[0]) + abs(nearest[1] - nh[1])
            if d2 < best_dist:
                best_dist = d2
                best_d = d
        return best_d or random.choice(allowed)

    def _spawn_body(self, start: tuple[int, int]) -> list[tuple[int, int]]:
        x, y = start
        body = [(x, y)]
        # без телепорта по краям: тянем влево или вправо, чтобы влезло в поле
        if x >= INITIAL_SNAKE_LEN:
            for i in range(1, INITIAL_SNAKE_LEN):
                body.append((x - i, y))
        else:
            for i in range(1, INITIAL_SNAKE_LEN):
                body.append((x + i, y))
        return body

    async def add_player(self, player_id: str, name: str = "Player", is_bot: bool = False) -> bool:
        async with self._lock:
            if player_id in self.players:
                return False
            occupied = set(self.apples.keys()) | self.walls
            for p in self.players.values():
                occupied.update(p.body)
            start = self._random_empty_cell(occupied)
            if not start:
                return False
            self.players[player_id] = Player(
                player_id=player_id,
                name=name,
                body=self._spawn_body(start),
                direction=Direction.RIGHT,
                next_direction=Direction.RIGHT,
                is_bot=is_bot,
            )
            self.spawn_apples()
            return True

    async def set_direction(self, player_id: str, direction: Direction) -> bool:
        async with self._lock:
            p = self.players.get(player_id)
            if not p or not p.alive:
                return False
            # нельзя развернуться на 180
            if direction == Direction.UP and p.direction != Direction.DOWN:
                p.next_direction = direction
            elif direction == Direction.DOWN and p.direction != Direction.UP:
                p.next_direction = direction
            elif direction == Direction.LEFT and p.direction != Direction.RIGHT:
                p.next_direction = direction
            elif direction == Direction.RIGHT and p.direction != Direction.LEFT:
                p.next_direction = direction
            return True

    def _move_head(self, head: tuple[int, int], d: Direction) -> tuple[int, int]:
        x, y = head
        if d == Direction.UP:
            y = y - 1
        elif d == Direction.DOWN:
            y = y + 1
        elif d == Direction.LEFT:
            x = x - 1
        else:
            x = x + 1
        return (x, y)

    def _kill_player(self, p: Player) -> None:
        """Смерть: из головы и каждого второго сегмента (0, 2, 4, 6…) падают яблоки; столько же очков снимается."""
        p.alive = False
        p.death_tick = self.tick
        dropped = 0
        for i in range(0, len(p.body), 2):
            pos = p.body[i]
            if pos not in self.walls:
                self.apples[pos] = APPLE_NORMAL
                dropped += 1
        p.score = max(0, p.score - dropped)

    async def start_game(self, level: int, player_ids: list[str]) -> bool:
        """Запуск (или перезапуск) раунда: уровень, стены, спавн всех игроков."""
        async with self._lock:
            old_level = self.level
            for pid, p in list(self.players.items()):
                if pid not in self._level_scores:
                    self._level_scores[pid] = {}
                self._level_scores[pid][old_level] = max(
                    self._level_scores[pid].get(old_level, 0), p.score
                )
                self._total_weighted[pid] = sum(
                    self._level_scores[pid].get(l, 0) * LEVEL_MULTIPLIERS.get(l, 1)
                    for l in range(1, 6)
                )
            self.level = max(1, min(5, level))
            cfg = LEVELS.get(self.level, LEVELS[1])
            self.width = cfg["grid_width"]
            self.height = cfg["grid_height"]
            self.walls = make_walls_for_level(self.level)
            self.apples.clear()
            self.players.clear()
            self.tick = 0
            occupied = set(self.walls)
            # Игроки по API + боты (количество = уровень * 2)
            bot_count = self.level * 2
            all_ids = list(player_ids) + [f"bot_{i}" for i in range(1, bot_count + 1)]
            for pid in all_ids:
                start = self._random_empty_cell(occupied)
                if start:
                    is_bot = pid.startswith("bot_")
                    self.players[pid] = Player(
                        player_id=pid,
                        name=pid,
                        body=self._spawn_body(start),
                        direction=Direction.RIGHT,
                        next_direction=Direction.RIGHT,
                        is_bot=is_bot,
                    )
                    occupied.update(self.players[pid].body)
            self.spawn_apples()
            self.game_started = True
            self.game_ended = False
            return True

    async def do_tick(self):
        async with self._lock:
            if not self.game_started or self.game_ended:
                return
            self._last_tick_time = time.monotonic()
            self.tick += 1
            if self.tick > GAME_DURATION_TICKS:
                # Игра закончилась по таймеру — фиксируем результаты раунда один раз
                self._finalize_round()
                self.game_ended = True
                return

            def would_die(pl: Player, nh: tuple[int, int]) -> bool:
                if nh in self.walls or nh[0] < 0 or nh[0] >= self.width or nh[1] < 0 or nh[1] >= self.height:
                    return True
                if nh in pl.body[:-1]:
                    return True
                for other in self.players.values():
                    if other.player_id != pl.player_id and other.alive and nh in other.body:
                        return True
                return False

            for p in list(self.players.values()):
                if not p.alive:
                    continue
                if p.is_bot:
                    p.next_direction = self._bot_choose_direction(p)
                p.direction = p.next_direction

                moves_this_tick = 2 if p.speed_boost_until_tick >= self.tick else 1
                for _ in range(moves_this_tick):
                    if not p.alive:
                        break
                    new_head = self._move_head(p.head(), p.direction)
                    if would_die(p, new_head):
                        if p.shield_count > 0:
                            p.shield_count -= 1
                            break
                        self._kill_player(p)
                        break
                    p.body.insert(0, new_head)
                    apple_type = self.apples.pop(new_head, None)
                    if apple_type == APPLE_NORMAL:
                        p.score += 1
                    elif apple_type == APPLE_BLACK:
                        p.score = 0
                    elif apple_type == APPLE_GOLDEN:
                        p.score += 10
                    elif apple_type == APPLE_SPEED_15:
                        p.speed_boost_until_tick = max(p.speed_boost_until_tick, self.tick) + 15
                    elif apple_type == APPLE_SPEED_30:
                        p.speed_boost_until_tick = max(p.speed_boost_until_tick, self.tick) + 30
                    elif apple_type == APPLE_SHIELD:
                        p.shield_count = min(p.shield_count + 1, 2)
                    if not apple_type:
                        p.body.pop()

            # Респавн через 5 тиков (и люди, и бот)
            for p in self.players.values():
                if not p.alive and p.death_tick is not None and self.tick >= p.death_tick + RESPAWN_AFTER_TICKS:
                    occupied = set(self.apples.keys()) | self.walls
                    for other in self.players.values():
                        if other.alive:
                            occupied.update(other.body)
                    start = self._random_empty_cell(occupied)
                    if start:
                        p.body = self._spawn_body(start)
                        p.alive = True
                        p.death_tick = None
                        p.direction = Direction.RIGHT
                        p.next_direction = Direction.RIGHT
                        p.speed_boost_until_tick = 0
                        p.shield_count = 0

            self.spawn_apples()

    def _in_radius(self, cx: int, cy: int, x: int, y: int, radius: int) -> bool:
        """Чебышёв: в квадрате radius от (cx, cy)."""
        return abs(x - cx) <= radius and abs(y - cy) <= radius

    async def set_player_name(self, player_id: str, name: str) -> None:
        """Обновить отображаемое имя игрока (никнейм). Вызывается при GET /world?name=..."""
        async with self._lock:
            p = self.players.get(player_id)
            if p and name and str(name).strip():
                p.name = str(name).strip()

    async def get_sleep_until_next_tick(self) -> float:
        """Секунды до следующего тика (0 если игра не идёт). Клиент может sleep на это время."""
        async with self._lock:
            if not self.game_started or self.game_ended or self._last_tick_time == 0:
                return 1.0 / TICKS_PER_SECOND
            elapsed = time.monotonic() - self._last_tick_time
            return max(0.0, (1.0 / TICKS_PER_SECOND) - elapsed)

    def get_world_around(self, player_id: str, radius: int = 50) -> dict:
        """
        Всё в радиусе radius от головы игрока: свои координаты, яблоки, змейки, стены.
        Ручка для клиента — только видимое окружение.
        """
        p = self.players.get(player_id)
        if not p:
            return {"error": "player not found"}
        hx, hy = p.head()
        # Стены в радиусе
        walls = [{"x": x, "y": y} for (x, y) in self.walls if self._in_radius(hx, hy, x, y, radius)]
        # Яблоки в радиусе
        apples = [
            {"x": x, "y": y, "type": t}
            for (x, y), t in self.apples.items()
            if self._in_radius(hx, hy, x, y, radius)
        ]
        # Змейки, у которых хотя бы один сегмент в радиусе (отдаём всю змейку)
        snakes = []
        for other in self.players.values():
            if not other.body:
                continue
            if any(self._in_radius(hx, hy, bx, by, radius) for (bx, by) in other.body):
                snakes.append({
                    "id": other.player_id,
                    "name": other.name,
                    "body": [{"x": x, "y": y} for x, y in other.body],
                    "score": other.score,
                    "alive": other.alive,
                    "speed_boost_until_tick": getattr(other, "speed_boost_until_tick", 0),
                    "shield_count": getattr(other, "shield_count", 0),
                })
        def _player_stats(pl: Player) -> dict:
            ls = self._level_scores.get(pl.player_id, {})
            tw = self._total_weighted.get(pl.player_id, 0)
            return {
                "id": pl.player_id,
                "name": pl.name,
                "score": pl.score,
                "alive": pl.alive,
                "level_scores": {str(k): v for k, v in ls.items()},
                "total_weighted": tw,
            }
        leaderboard = [_player_stats(pl) for pl in self.players.values()]
        leaderboard.sort(key=lambda x: -x["total_weighted"])
        me_data = {
            "id": p.player_id,
            "name": p.name,
            "body": [{"x": x, "y": y} for x, y in p.body],
            "direction": p.direction.value,
            "score": p.score,
            "alive": p.alive,
            "speed_boost_until_tick": p.speed_boost_until_tick,
            "shield_count": p.shield_count,
        }
        me_data["level_scores"] = {str(k): v for k, v in self._level_scores.get(p.player_id, {}).items()}
        me_data["total_weighted"] = self._total_weighted.get(p.player_id, 0)
        return {
            "tick": self.tick,
            "width": self.width,
            "height": self.height,
            "level": self.level,
            "game_ended": self.game_ended,
            "game_duration_ticks": GAME_DURATION_TICKS,
            "level_multipliers": LEVEL_MULTIPLIERS,
            "me": me_data,
            "walls": walls,
            "apples": apples,
            "snakes": snakes,
            "leaderboard": leaderboard,
        }

    def get_walls(self) -> list[dict]:
        """Стенки (один раз запросить и закэшировать на клиенте)."""
        return [{"x": x, "y": y} for x, y in self.walls]

    def get_state(self) -> dict:
        def _pl(p: Player) -> dict:
            ls = self._level_scores.get(p.player_id, {})
            tw = self._total_weighted.get(p.player_id, 0)
            return {
                "id": p.player_id,
                "name": p.name,
                "body": [{"x": x, "y": y} for x, y in p.body],
                "direction": p.direction.value,
                "score": p.score,
                "alive": p.alive,
                "speed_boost_until_tick": getattr(p, "speed_boost_until_tick", 0),
                "shield_count": getattr(p, "shield_count", 0),
                "level_scores": {str(k): v for k, v in ls.items()},
                "total_weighted": tw,
            }
        return {
            "tick": self.tick,
            "width": self.width,
            "height": self.height,
            "level": self.level,
            "game_started": self.game_started,
            "game_ended": self.game_ended,
            "game_duration_ticks": GAME_DURATION_TICKS,
            "level_multipliers": LEVEL_MULTIPLIERS,
            "apples": [{"x": x, "y": y, "type": t} for (x, y), t in self.apples.items()],
            "walls": [{"x": x, "y": y} for x, y in self.walls],
            "players": [_pl(p) for p in self.players.values()],
            "game_history": self._game_history,
        }
