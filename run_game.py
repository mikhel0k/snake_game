#!/usr/bin/env python3
"""
Запуск игры: в консоли спрашивает количество игроков,
генерирует логины и пароли, сохраняет в credentials.json и запускает сервер.
"""
import json
import os
import secrets
import socket
import subprocess
import sys

CREDENTIALS_FILE = os.path.join(os.path.dirname(__file__), "credentials.json")


def generate_password(length=10):
    return secrets.token_urlsafe(length)[:length]


def _is_lan_ip(ip):
    """Проверка: это нормальный LAN-адрес (не 127, не 198.18 VPN и т.п.)."""
    if not ip or ip.startswith("127."):
        return False
    if ip.startswith("198.18.") or ip.startswith("198.19."):  # VPN / бенчмарк
        return False
    parts = ip.split(".")
    if len(parts) != 4:
        return False
    try:
        a, b = int(parts[0]), int(parts[1])
        if a == 10:  # 10.0.0.0/8
            return True
        if a == 192 and b == 168:  # 192.168.0.0/16
            return True
        if a == 172 and 16 <= b <= 31:  # 172.16.0.0/12
            return True
    except ValueError:
        pass
    return False


def get_local_ips():
    """Список LAN IP (192.168.x.x, 10.x.x.x и т.д.) для доступа с других устройств."""
    found = []
    # macOS / Linux: ifconfig
    try:
        out = subprocess.run(
            ["ifconfig"] if sys.platform != "win32" else ["ipconfig"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        text = (out.stdout or "") + (out.stderr or "")
        if sys.platform == "win32":
            for line in text.splitlines():
                if "IPv4" in line or "IPv4-адрес" in line:
                    for part in line.replace(":", " ").split():
                        if _is_lan_ip(part):
                            found.append(part)
        else:
            for line in text.splitlines():
                if "inet " in line and "inet6" not in line:
                    parts = line.strip().split()
                    for i, p in enumerate(parts):
                        if p == "inet" and i + 1 < len(parts):
                            ip = parts[i + 1].split("%")[0]
                            if _is_lan_ip(ip):
                                found.append(ip)
                            break
    except Exception:
        pass
    # Fallback: сокет (может дать 198.18.x при VPN — не показываем как LAN)
    if not found:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(0)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            if _is_lan_ip(ip):
                found.append(ip)
        except Exception:
            pass
    return found


def main():
    print("=== Запуск игры Змейка ===\n")
    try:
        n = input("Сколько игроков? ").strip()
        n = int(n)
        if n < 1 or n > 100:
            raise ValueError("Введите число от 1 до 100")
    except ValueError as e:
        print(e)
        sys.exit(1)

    admin_password = generate_password(12)
    players = []
    for i in range(1, n + 1):
        login = f"player_{i}"
        password = generate_password(10)
        players.append({"login": login, "password": password})

    data = {
        "admin_password": admin_password,
        "players": players,
        "game_started": False,
        "level": 1,
    }
    with open(CREDENTIALS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print("\n--- Сохранено в credentials.json ---\n")
    print("Админ:")
    print(f"  Логин: admin")
    print(f"  Пароль: {admin_password}")
    print("\nИгроки:")
    for p in players:
        print(f"  {p['login']} / {p['password']}")
    port = 8002
    lan_ips = get_local_ips()
    print("\n--- Ссылки ---")
    print(f"  Локально:        http://127.0.0.1:{port}/")
    if lan_ips:
        for ip in lan_ips[:3]:  # не больше 3
            print(f"  В сети (LAN):   http://{ip}:{port}/")
        print(f"  Админка:        http://{lan_ips[0]}:{port}/admin")
    else:
        print(f"  Админка:        http://127.0.0.1:{port}/admin")
        print("  (LAN-IP не найден — с другого компа подключайся по 127.0.0.1 не получится.)")
    print("\n  С другого ПК в сети открой ссылку «В сети (LAN)». Если не открывается — проверь фаервол (разреши порт 8002).")
    print("\nЗапуск сервера...\n")

    os.environ["CREDENTIALS_FILE"] = CREDENTIALS_FILE
    subprocess.run([
        sys.executable, "-m", "uvicorn", "main:app",
        "--host", "0.0.0.0", "--port", "8002"
    ])


if __name__ == "__main__":
    main()
