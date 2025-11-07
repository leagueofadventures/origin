import pygame
import pytmx
from pytmx import util_pygame
import socket
import pickle
import sys
import json
import os
import argparse
from enhanced_detection import get_client_config, detector

red = (255, 0, 0)

black = (0, 0, 0)

# Определяем текущую директорию проекта
PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Парсинг аргументов командной строки
parser = argparse.ArgumentParser(description='Игровой клиент')
parser.add_argument('--interface', '-i', type=str, help='Выбрать конкретный сетевой интерфейс')
parser.add_argument('--list-interfaces', '-l', action='store_true', help='Показать все доступные интерфейсы')
parser.add_argument('--server', '-s', type=str, help='Адрес сервера для подключения')
parser.add_argument('--port', '-p', type=int, default=5555, help='Порт сервера (по умолчанию 5555)')
parser.add_argument('--auto', '-a', action='store_true', help='Автоматический режим без интерактивного ввода')

args = parser.parse_args()

# Если запрошено показать интерфейсы
if args.list_interfaces:
    detector.print_available_interfaces()
    sys.exit(0)

# Если не выбран автоматический режим и не указан сервер, показать интерфейсы и предложить выбор
if not args.auto and not args.server:
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

    # Предлагаем выбор
    choice = input(f"\nВыберите номер интерфейса (1-{len(interfaces)}) или введите IP сервера вручную: ").strip()

    if choice.isdigit():
        choice_num = int(choice) - 1
        if 0 <= choice_num < len(interfaces):
            selected_interface = interfaces[choice_num]
            if 'ip' in selected_interface:
                args.server = selected_interface['ip']
                print(f"✅ Выбран: {selected_interface.get('name', 'Unknown')} - {args.server}")
            else:
                print("❌ Выбранный интерфейс не имеет IP-адреса")
        else:
            print("❌ Неверный номер интерфейса")
    else:
        # Пользователь ввел IP вручную
        args.server = choice
        print(f"✅ Выбран сервер: {args.server}")

    print(f"\n🔌 Подключение к {args.server}:{args.port}")
    input("Нажмите Enter для продолжения...")

# Инициализация Pygame
pygame.init()
pygame.display.init()

# Полноэкранный режим
screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)

# Получение размеров экрана
info = pygame.display.Info()
width, height = info.current_w, info.current_h

# Загрузка TMX-карты
map_file = os.path.join(PROJECT_DIR, ' ', 'maps', 'безымянный.tmx')
try:
    tmx_data = util_pygame.load_pygame(map_file)
    map_width = tmx_data.width * tmx_data.tilewidth
    map_height = tmx_data.height * tmx_data.tileheight
except Exception as e:
    print(f"Ошибка загрузки карты: {e}")
    pygame.quit()
    sys.exit()

#Загружка изображений для текстовой части игры
images = []
for i in range(1, 12):
    try:
        name_image = str(i) + '.png'
        image_file = os.path.join(PROJECT_DIR, ' ', 'images', name_image)
        image = pygame.transform.scale(pygame.image.load(image_file), screen.get_size())
        images.append(image)
        print('SOSA')

    except FileNotFoundError:
        print('Ошибка. Файл не найден')

#Загрузка картинки главного меню
menu_file = os.path.join(PROJECT_DIR, ' ', 'images', 'меню.png')
try:
    menu_png = pygame.transform.scale(pygame.image.load(menu_file), screen.get_size())
except:
    print('Ошибка. Файл "Меню.png" не найден')
    pygame.quit()
    sys.exit()

#Загрузка картинки меню выхода
quit_file = os.path.join(PROJECT_DIR, ' ', 'images', 'quit_menu.jpg')
try:
    quit_png = pygame.transform.scale(pygame.image.load(quit_file), screen.get_size())
except:
    print('Ошибка. Файл "quit_menu.jpg" не найден.')
    pygame.quit()
    sys.exit()

#Загрузка заднего фона настроек
settings_file = os.path.join(PROJECT_DIR,  ' ', 'images', 'settings_background.png')
try:
    setting_png = pygame.transform.scale(pygame.image.load(settings_file), screen.get_size())
except FileNotFoundError:
    print('Ошибка. Файл "settings_background.png" не найден.')
    pygame.quit()
    sys.exit()

# Камера
camera_x = 0
camera_y = 0
camera_speed = 10

#Создание кнопок главного меню

solo_play_button = pygame.Surface((300, 70), pygame.SRCALPHA)
solo_play_button.fill((0, 0, 0, 0))
solo_play_button_rect = solo_play_button.get_rect(topleft=(820, 520)) # Установите позицию

multi_play_button = pygame.Surface((300, 70), pygame.SRCALPHA)
multi_play_button.fill((0, 0, 0, 0))
multi_play_button_rect = multi_play_button.get_rect(topleft=(820, 620))

options_button = pygame.Surface((300, 70), pygame.SRCALPHA)
options_button.fill((0, 0, 0, 0))
options_button_rect = options_button.get_rect(topleft=(820, 730))

quit_button = pygame.Surface((300, 70), pygame.SRCALPHA)
quit_button.fill((0, 0, 0, 0))
quit_button_rect = quit_button.get_rect(topleft=(810, 840))

quit_yes_button = pygame.Surface((160, 65), pygame.SRCALPHA)
quit_yes_button.fill((0, 0, 0, 0))
quit_yes_button_rect = quit_yes_button.get_rect(topleft=(785, 590))

quit_no_button = pygame.Surface((160, 65), pygame.SRCALPHA)
quit_no_button.fill((0, 0, 0, 0))
quit_no_button_rect = quit_yes_button.get_rect(topleft=(975, 590))

# Загрузка спрайта
sprite_path = os.path.join(PROJECT_DIR, ' ', 'sprites', 'lena.jpg')
try:
    sprite = pygame.image.load(sprite_path)
    sprite_rect = sprite.get_rect(center=(width // 2, height // 2))
except Exception as e:
    print(f"Ошибка загрузки спрайта: {e}")
    pygame.quit()
    sys.exit()

# Позиция персонажа
player_x = width // 2
player_y = height // 2
player_speed = 5

# Мультиплеер переменные
players = {}

# Получить конфигурацию клиента с автоопределением
if args.server:
    # Если указан сервер вручную
    client_config = {
        'server_host': args.server,
        'server_port': args.port
    }
else:
    # Автоопределение
    client_config = get_client_config(args.interface)

server_host = client_config['server_host']
server_port = args.port if args.server else int(client_config['server_port'])

print(f"Попытка подключения к {server_host}:{server_port}")

client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
try:
    client_socket.connect((server_host, server_port))
    print("Успешно подключено к серверу")
except Exception as e:
    print(f"Не удалось подключиться к серверу: {e}")
    print("Убедитесь, что сервер запущен и доступен")
    print("Попробуйте:")
    print("1. python client.py --list-interfaces  # Посмотреть доступные интерфейсы")
    print("2. python client.py --interface 'Radmin VPN'  # Выбрать интерфейс Radmin")
    print("3. python client.py --server 192.168.1.100  # Подключиться к конкретному серверу")
    pygame.quit()
    sys.exit()

def draw_map(surface, camera_x, camera_y):
    for layer in tmx_data.visible_layers:
        if isinstance(layer, pytmx.TiledTileLayer):
            for x, y, gid in layer:
                tile = tmx_data.get_tile_image_by_gid(gid)
                if tile:
                    surface.blit(tile, (x * tmx_data.tilewidth - camera_x,
                                        y * tmx_data.tileheight - camera_y))
                    
menu = True

solo_time = False


change_time = 8000

running = True
while running:
    clock = pygame.time.Clock()
    clock.tick(60)

    # Обработка событий
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False
        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                running = False
        
        if event.type == pygame.MOUSEBUTTONDOWN:
            if menu:
                if solo_play_button_rect.collidepoint(event.pos):
                    menu = False
                    screen.fill(black)
                    print(images)
                    screen.blit(images[0],  (0, 0))
                    solo_time = True
                    solo_start_time = pygame.time.get_ticks()

                if multi_play_button_rect.collidepoint(event.pos):
                    print('Оно тоже живое')
                    # screen.fill((0, 0, 0))
                    # draw_map(screen, camera_x, camera_y)
                    # print('Успешно')

                if options_button_rect.collidepoint(event.pos):
                    print('И оно живое')
                    menu = False
                    screen.fill(black)
                    screen.blit(setting_png, (0, 0))

                if quit_button_rect.collidepoint(event.pos):
                    menu = False
                    print('И Последнее живет')
                    screen.fill(black)
                    screen.blit(quit_png, (0, 0))
                    screen.blit(quit_yes_button, quit_yes_button_rect)
                    screen.blit(quit_no_button, quit_no_button_rect)
                    
                
            if quit_yes_button_rect.collidepoint(event.pos):
                print('Да тут все живое!')
                running = False

            if quit_no_button_rect.collidepoint(event.pos):
                menu = True

    if solo_time:
        elapsed = pygame.time.get_ticks() - solo_start_time
        if elapsed >= change_time:
            screen.blit(images[1],  (0, 0))
            if elapsed >= change_time + 8000:
                screen.blit(images[2], (0, 0))
                if elapsed >= change_time + 16000:
                    screen.blit(images[3], (0, 0))
                    if elapsed >= change_time + 24000:
                        screen.blit(images[4], (0, 0))
                        if elapsed >= change_time + 32000:
                            screen.blit(images[5], (0, 0))
                            if elapsed >= change_time + 40000:
                                screen.blit(images[6], (0, 0))
                                if elapsed >= change_time + 48000:
                                    screen.blit(images[7], (0, 0))
                                    if elapsed >= change_time + 56000:
                                        screen.blit(images[8], (0, 0))
                                        if elapsed >= change_time + 64000:
                                            screen.blit(images[9], (0, 0))
                                            if elapsed >= change_time + 72000:
                                                screen.blit(images[10], (0, 0))
                                                if elapsed >= change_time + 80000:
                                                    screen.blit(images[11], (0, 0))
                                                    
            

    # Отправляем вводы на сервер
    keys = pygame.key.get_pressed()
    inputs = {
        'left': keys[pygame.K_LEFT],
        'right': keys[pygame.K_RIGHT],
        'up': keys[pygame.K_UP],
        'down': keys[pygame.K_DOWN]
    }
    try:
        client_socket.send(pickle.dumps(inputs))
        data = client_socket.recv(1024)
        all_positions = pickle.loads(data)
        # Обновляем позиции
        if 'server' in all_positions and isinstance(all_positions['server'], dict):
            player_x = all_positions['server'].get('x', width // 2)
            player_y = all_positions['server'].get('y', height // 2)
        
        # Обновляем позиции других игроков
        if 'players' in all_positions:
            players = all_positions['players']
        else:
            players = {k: v for k, v in all_positions.items() if k != 'server' and k != 'server_time'}
    except Exception as e:
        print(f"Ошибка соединения: {e}")
        running = False

    # Синхронизация камеры с положением персонажа
    camera_x = max(0, min(player_x - (width // 2), map_width - width))
    camera_y = max(0, min(player_y - (height // 2), map_height - height))

    # Отрисовка меню
    if menu:
        screen.fill((0, 0, 0))
        screen.blit(menu_png, (0, 0))
        # pygame.draw.rect(screen, red, solo_play_button)
        # pygame.draw.rect(screen, red, multi_play_button)
        screen.blit(solo_play_button, solo_play_button_rect)
        screen.blit(multi_play_button, multi_play_button_rect)
        screen.blit(options_button, options_button_rect)
        screen.blit(quit_button, quit_button_rect)
    # draw_map(screen, camera_x, camera_y)

    # Отрисовка спрайта сервера
    # screen.blit(sprite, (player_x - camera_x, player_y - camera_y))

    # Отрисовка других игроков
    # for pid, pos in players.items():
    #     screen.blit(sprite, (pos['x'] - camera_x, pos['y'] - camera_y))
    
    pygame.display.flip()

client_socket.close()
pygame.quit()
