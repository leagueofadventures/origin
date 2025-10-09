import socket
import threading
import pickle
import sys
import json
import argparse
from enhanced_detection import get_server_config, detector
from advanced_logger import logger
import time

# Парсинг аргументов командной строки
parser = argparse.ArgumentParser(description='Игровой сервер')
parser.add_argument('--interface', '-i', type=str, help='Выбрать конкретный сетевой интерфейс')
parser.add_argument('--list-interfaces', '-l', action='store_true', help='Показать все доступные интерфейсы')
parser.add_argument('--port', '-p', type=int, default=5555, help='Порт сервера (по умолчанию 5555)')
parser.add_argument('--auto', '-a', action='store_true', help='Автоматический режим без интерактивного ввода')

args = parser.parse_args()

# Если запрошено показать интерфейсы
if args.list_interfaces:
    detector.print_available_interfaces()
    sys.exit(0)

# Получить конфигурацию сервера с автоопределением
server_config = get_server_config(args.interface)
host = server_config['host']
port = args.port  # Используем порт из аргументов
bind_address = server_config['bind_address']
interface = server_config['interface']

# Если не выбран автоматический режим, показать интерфейсы и предложить выбор
if not args.auto:
    print("\n=== ДОСТУПНЫЕ СЕТЕВЫЕ ИНТЕРФЕЙСЫ ===")
    interfaces = detector.get_all_interfaces()
    vpn_interfaces = detector.detect_vpn_interfaces(interfaces)

    if vpn_interfaces:
        print("\n🔥 VPN интерфейсы (рекомендуется):")
        for i, interface in enumerate(vpn_interfaces, 1):
            ip = interface.get('ip', 'N/A')
            name = interface.get('name', 'Unknown')
            interface_type = interface.get('type', 'unknown')
            print(f"  {i}. {name} - {ip} [{interface_type}]")

    print("\n🌐 Все интерфейсы:")
    for i, interface in enumerate(interfaces, len(vpn_interfaces) + 1):
        ip = interface.get('ip', 'N/A')
        name = interface.get('name', 'Unknown')
        print(f"  {i}. {name} - {ip}")

    print(f"\n📍 Текущий выбор: {host}:{port}")

    # Предлагаем выбор
    choice = input(f"\nВыберите номер интерфейса (1-{len(interfaces)}) или нажмите Enter для текущего: ").strip()

    if choice.isdigit():
        choice_num = int(choice) - 1
        if 0 <= choice_num < len(interfaces):
            selected_interface = interfaces[choice_num]
            if 'ip' in selected_interface:
                host = selected_interface['ip']
                print(f"✅ Выбран: {selected_interface.get('name', 'Unknown')} - {host}")
            else:
                print("❌ Выбранный интерфейс не имеет IP-адреса")
        else:
            print("❌ Неверный номер интерфейса")

    print(f"\n🚀 Сервер будет запущен на {host}:{port}")
    input("Нажмите Enter для продолжения...")

# Игровые константы
width = 1920
height = 1080
map_width = 10000
map_height = 10000
player_speed = 5

# Мультиплеер переменные
players = {}  # {client_id: {'x': x, 'y': y, 'last_update': timestamp}}
client_id = 0
server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

try:
    server_socket.bind((bind_address, port))
    server_socket.listen(5)
    logger.logger.info(f"Сервер запущен на {host}:{port} (привязан к {bind_address})")
    print(f"Сервер запущен на {host}:{port}")
except Exception as e:
    logger.log_error(e, "Запуск сервера")
    print(f"Не удалось запустить сервер: {e}")
    sys.exit(1)

def handle_client(client_sock, addr):
    global client_id
    cid = client_id
    client_id += 1
    
    # Инициализируем игрока
    players[cid] = {
        'x': width // 2,
        'y': height // 2,
        'direction': 'down',
        'moving': False,
        'last_update': time.time()
    }
    
    # Устанавливаем контекст логирования
    logger.set_request_context(cid, addr[0])
    logger.log_connection(cid, "подключен", {'ip': addr[0], 'port': addr[1]})
    
    try:
        while True:
            data = client_sock.recv(1024)
            if not data:
                break
                
            inputs = pickle.loads(data)
            current_time = time.time()
            
            # Обновляем позицию игрока
            player = players[cid]
            dx = 0
            dy = 0
            if inputs['left']: dx = -1
            if inputs['right']: dx = 1
            if inputs['up']: dy = -1
            if inputs['down']: dy = 1

            moving = dx != 0 or dy != 0
            if dy < 0: direction = 'up'
            elif dy > 0: direction = 'down'
            elif dx < 0: direction = 'left'
            elif dx > 0: direction = 'right'
            else: direction = player['direction']  # keep last direction if not moving

            player['x'] += dx * player_speed
            player['y'] += dy * player_speed

            # Проверяем границы
            player['x'] = max(0, min(player['x'], map_width))
            player['y'] = max(0, min(player['y'], map_height))
            player['direction'] = direction
            player['moving'] = moving
            player['last_update'] = current_time
            
            # Подготавливаем ответ
            all_positions = {
                'self': players[cid].copy(),
                'players': {k: v.copy() for k, v in players.items() if k != cid},
                'server_time': current_time
            }
            
            client_sock.send(pickle.dumps(all_positions))
            
            # Логируем игровое событие
            logger.log_game_event("обновление_позиции", {
                'client_id': cid,
                'position': {'x': player['x'], 'y': player['y']},
                'inputs': inputs
            })
            
    except Exception as e:
        logger.log_error(e, f"Обработка клиента {cid}")
    finally:
        logger.log_connection(cid, "отключен")
        if cid in players:
            del players[cid]
        client_sock.close()

def server_loop():
    while True:
        try:
            client_sock, addr = server_socket.accept()
            threading.Thread(target=handle_client, args=(client_sock, addr)).start()
        except KeyboardInterrupt:
            break
        except Exception as e:
            logger.log_error(e, "Цикл сервера")

if __name__ == "__main__":
    print("Сервер запущен.")
    try:
        server_loop()
    except KeyboardInterrupt:
        print("Сервер остановлен.")
    finally:
        server_socket.close()
        logger.logger.info("Сервер выключен")
