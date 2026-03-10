"""
Конфиги уровней 1–5: размер поля, препятствия, яблоки.
Яблоки и объекты — пропорционально площади карты.
Препятствия — пропорционально площади и уровню (плотность растёт = сложность растёт).
Размер поля 50→100, внутренняя площадь (без стен): L1≈2304, L2≈3600, L3≈5329, L4≈7225, L5≈9604.
"""
from typing import TypedDict


class LevelConfig(TypedDict):
    grid_width: int
    grid_height: int
    obstacles: int
    normal: int
    black: int
    golden: int
    speed_15: int
    speed_30: int
    shield: int


def _area(w: int, h: int) -> int:
    return (w - 2) * (h - 2)


# Плотность препятствий растёт с уровнем (сложность)
def _obstacles(level: int, w: int, h: int) -> int:
    a = _area(w, h)
    density = 0.015 + 0.003 * level  # L1: 0.018, L5: 0.030
    return max(20, int(a * density))


# Яблоки пропорционально площади
def _normal(area: int) -> int:
    return max(8, area // 220)


def _black(level: int, area: int) -> int:
    if level < 2:
        return 0
    return max(1, area // 1200 + level - 2)


def _golden(level: int, area: int) -> int:
    if level < 2:
        return 0
    return max(1, area // 1800 + level - 1)


def _speed_15(level: int, area: int) -> int:
    if level < 3:
        return 0
    return max(1, area // 3500)


def _speed_30(level: int, area: int) -> int:
    if level < 3:
        return 0
    return max(0, area // 6000)


def _shield(level: int, area: int) -> int:
    if level < 3:
        return 0
    return max(1, area // 4500)


def _make_level(level: int, w: int, h: int) -> LevelConfig:
    a = _area(w, h)
    return {
        "grid_width": w,
        "grid_height": h,
        "obstacles": _obstacles(level, w, h),
        "normal": _normal(a),
        "black": _black(level, a),
        "golden": _golden(level, a),
        "speed_15": _speed_15(level, a),
        "speed_30": _speed_30(level, a),
        "shield": _shield(level, a),
    }


LEVELS: dict[int, LevelConfig] = {
    1: _make_level(1, 50, 50),
    2: _make_level(2, 62, 62),
    3: _make_level(3, 75, 75),
    4: _make_level(4, 87, 87),
    5: _make_level(5, 100, 100),
}
