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

class AnimatedSprite:
    def __init__(self):
        self.animations = {}
        self.current_animation = None
        self.current_frame = 0
        self.frame_time = 0

        base_path = os.path.join(PROJECT_DIR, 'Карта', 'sprites', 'PNG', 'Vampires1')



       # Загрузка анимаций из папок PNG
        anim_configs = {
            'walk': {'folder': 'Vampires1_Walk_without_shadow.png', 'frames': 6, 'prefix': '{dir}{i}.jpg'},
            'attack': {'folder': 'Vampires1_Attack_without_shadow.png', 'frames': 12, 'prefix': '{dir}{i}.jpg'},
            'hurt': {'folder': 'Vampires1_Hurt_without_shadow.png', 'frames': 4, 'prefix': '{dir}{i}.jpg'},
        }

        directions = ['down', 'left', 'right', 'up']

        for anim_type, config in anim_configs.items():
            for dir in directions:
                name = f'{anim_type}_{dir}'
                frames = []
                i = 1
                while True:
                    filename = config['prefix'].format(dir=dir, i=i)
                    path = os.path.join(base_path, config['folder'], filename)
                    if not os.path.exists(path):
                        break
                    try:
                        img = pygame.image.load(path)
                        img.set_colorkey((0, 0, 0))
                        scaled = pygame.transform.scale(img, (64, 64))
                        frames.append((scaled, 65))  # Ускоряем анимацию
                    except Exception as e:
                        print(f"Ошибка загрузки {path}: {e}")
                        break
                    i += 1
                if frames:
                    self.animations[name] = frames

        # Добавление анимаций idle с использованием первого кадра ходьбы
        for dir in directions:
            idle_name = f'idle_{dir}'
            walk_name = f'walk_{dir}'
            if walk_name in self.animations:
                self.animations[idle_name] = [self.animations[walk_name][0]]

        # Установка анимации по умолчанию
        if 'idle_down' in self.animations:
            self.set_animation('idle_down')

    def set_animation(self, name):
        if name in self.animations and name != self.current_animation:
            self.current_animation = name
            self.current_frame = 0
            self.frame_time = 0

    def update(self, dt):
        if self.current_animation:
            frames = self.animations[self.current_animation]
            if frames:
                self.frame_time += dt * 1000  # Преобразование в миллисекунды
                while self.frame_time >= frames[self.current_frame][1]:
                    self.frame_time -= frames[self.current_frame][1]
                    self.current_frame = (self.current_frame + 1) % len(frames)

    def get_image(self):
        if self.current_animation and self.current_animation in self.animations:
            frames = self.animations[self.current_animation]
            if frames:
                img = frames[self.current_frame][0]
                # Масштабируем спрайт до размера тайла карты (64x64)
                return pygame.transform.scale(img, (64, 64))
        return None

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

# Шрифты
font_large = pygame.font.SysFont(None, 48)
font = pygame.font.SysFont(None, 24)

# Загрузка TMX-карты
map_file = os.path.join(PROJECT_DIR, 'Карта', 'maps', 'безымянный.tmx')
try:
    tmx_data = util_pygame.load_pygame(map_file)
    map_width = tmx_data.width * tmx_data.tilewidth
    map_height = tmx_data.height * tmx_data.tileheight

    # Загрузка слоя объектов для столкновений
    collision_rects = []
    for layer in tmx_data.layers:
        if hasattr(layer, 'name') and layer.name == 'objects':
            if hasattr(layer, 'objects'):  # object layer
                for obj in layer.objects:
                    rect = pygame.Rect(obj.x, obj.y, obj.width or tmx_data.tilewidth, obj.height or tmx_data.tileheight)
                    collision_rects.append(rect)
            else:  # tile layer
                for x, y, gid in layer:
                    if gid != 0:
                        rect = pygame.Rect(x * tmx_data.tilewidth, y * tmx_data.tileheight, tmx_data.tilewidth, tmx_data.tileheight)
                        collision_rects.append(rect)
except Exception as e:
    print(f"Ошибка загрузки карты: {e}")
    pygame.quit()
    sys.exit()

# Камера
camera_x = 0
camera_y = 0
camera_speed = 10

# Создание анимированного спрайта
sprite = AnimatedSprite()
other_sprites = {}
last_direction = 'down'

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

# Получаем начальное сообщение от сервера
try:
    data = client_socket.recv(1024)
    initial = pickle.loads(data)
    if 'banned' in initial:
        banned = True
        ban_reason = initial.get('reason', 'Неизвестная причина')
        # Отображаем экран бана
        screen.fill((0, 0, 0))
        font_large = pygame.font.SysFont(None, 48)
        text = font_large.render("Вы забанены", True, (255, 0, 0))
        screen.blit(text, (width // 2 - text.get_width() // 2, height // 2 - 50))
        reason_text = font.render(f"Причина: {ban_reason}", True, (255, 255, 255))
        screen.blit(reason_text, (width // 2 - reason_text.get_width() // 2, height // 2 + 10))
        pygame.display.flip()
        # Ждем закрытия
        waiting = True
        while waiting:
            for event in pygame.event.get():
                if event.type == pygame.QUIT or (event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE):
                    waiting = False
        client_socket.close()
        pygame.quit()
        sys.exit()
    elif 'status' in initial and initial['status'] == 'ok':
        pass  # Продолжаем
    else:
        print("Неожиданное начальное сообщение")
        pygame.quit()
        sys.exit()
except Exception as e:
    print(f"Ошибка при получении начального сообщения: {e}")
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

running = True

console_mode = False
command_text = ""
last_message = ""
banned = False
ban_reason = ""

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
            elif event.key == pygame.K_BACKQUOTE or event.unicode == 'ё':
                console_mode = not console_mode
                if console_mode:
                    command_text = ""
            elif console_mode:
                if event.key == pygame.K_RETURN:
                    if command_text.strip():
                        # Отправляем команду на сервер
                        try:
                            client_socket.send(pickle.dumps({'command': command_text.strip()}))
                            data = client_socket.recv(1024)
                            response = pickle.loads(data)
                            if 'message' in response:
                                last_message = response['message']
                        except Exception as e:
                            print(f"Ошибка отправки команды: {e}")
                    command_text = ""
                    console_mode = False
                elif event.key == pygame.K_BACKSPACE:
                    command_text = command_text[:-1]
                else:
                    if event.unicode.isprintable():
                        command_text += event.unicode

    if not console_mode:
        # Отправляем вводы на сервер
        keys = pygame.key.get_pressed()
        inputs = {
            'left': keys[pygame.K_LEFT],
            'right': keys[pygame.K_RIGHT],
            'up': keys[pygame.K_UP],
            'down': keys[pygame.K_DOWN]
        }

        # Проверка столкновений перед отправкой вводов
        dx = (inputs['right'] - inputs['left']) * player_speed
        dy = (inputs['down'] - inputs['up']) * player_speed
        new_x = player_x + dx
        new_y = player_y + dy
        player_rect = pygame.Rect(new_x + 16, new_y + 16, 32, 32)  # Хитбокс 32x32 в центре спрайта
        if any(player_rect.colliderect(rect) for rect in collision_rects):
            inputs = {'left': False, 'right': False, 'up': False, 'down': False}

        try:
            client_socket.send(pickle.dumps(inputs))
            data = client_socket.recv(1024)
            all_positions = pickle.loads(data)
            # Обновляем позиции
            if 'self' in all_positions and isinstance(all_positions['self'], dict):
                player_x = all_positions['self'].get('x', width // 2)
                player_y = all_positions['self'].get('y', height // 2)
            
            # Обновляем позиции других игроков
            players = all_positions.get('players', {})
            # Если есть сообщение от сервера, выводим в игре
            if 'message' in all_positions:
                last_message = all_positions['message']
        except Exception as e:
            print(f"Ошибка соединения: {e}")
            running = False

    # Определение анимации
    dx = 0
    dy = 0
    if not console_mode:
        keys = pygame.key.get_pressed()
        if keys[pygame.K_LEFT]: dx = -1
        if keys[pygame.K_RIGHT]: dx = 1
        if keys[pygame.K_UP]: dy = -1
        if keys[pygame.K_DOWN]: dy = 1
    else:
        dx = 0
        dy = 0
    
    attack_pressed = keys[pygame.K_SPACE] if not console_mode else False
    hurt_pressed = keys[pygame.K_h] if not console_mode else False

    if attack_pressed:
        anim = 'attack_' + last_direction
    elif hurt_pressed:
        anim = 'hurt_' + last_direction
    elif dx != 0 or dy != 0:
        if dy < 0: direction = 'up'
        elif dy > 0: direction = 'down'
        elif dx < 0: direction = 'left'
        elif dx > 0: direction = 'right'
        else: direction = last_direction
        anim = 'walk_' + direction
        last_direction = direction
    else:
        anim = 'idle_' + last_direction

    sprite.set_animation(anim)
    dt = clock.get_time() / 1000.0
    sprite.update(dt)

    # Синхронизация камеры с положением персонажа
    camera_x = max(0, min(player_x - (width // 2), map_width - width))
    camera_y = max(0, min(player_y - (height // 2), map_height - height))

    # Отрисовка карты
    screen.fill((0, 0, 0))

    # Отрисовка всех слоев карты
    for layer in tmx_data.visible_layers:
        if isinstance(layer, pytmx.TiledTileLayer):
            for x, y, gid in layer:
                tile = tmx_data.get_tile_image_by_gid(gid)
                if tile:
                    screen.blit(tile, (x * tmx_data.tilewidth - camera_x,
                                        y * tmx_data.tileheight - camera_y))

    # Отрисовка спрайта сервера
    img = sprite.get_image()
    if img:
        screen.blit(img, (player_x - camera_x, player_y - camera_y))

    # Отрисовка других игроков
    for pid, pos in players.items():
        if pid not in other_sprites:
            other_sprites[pid] = AnimatedSprite()
        moving = pos.get('moving', False)
        direction = pos.get('direction', 'down')
        anim = ('walk_' if moving else 'idle_') + direction
        other_sprites[pid].set_animation(anim)
        other_sprites[pid].update(dt)
        img = other_sprites[pid].get_image()
        if img:
            screen.blit(img, (pos['x'] - camera_x, pos['y'] - camera_y))

    # Отрисовка консоли
    if console_mode:
        console_surface = pygame.Surface((width, 30))
        console_surface.set_alpha(180)
        console_surface.fill((0, 0, 0))
        screen.blit(console_surface, (0, height - 30))
        text_surface = font.render("> " + command_text, True, (255, 255, 255))
        screen.blit(text_surface, (10, height - 25))

    # Отрисовка последнего сообщения
    if last_message:
        message_surface = pygame.Surface((width, 50))
        message_surface.set_alpha(180)
        message_surface.fill((0, 0, 0))
        screen.blit(message_surface, (0, 0))
        text_surface = font.render(last_message, True, (255, 255, 255))
        screen.blit(text_surface, (10, 10))

    pygame.display.flip()

client_socket.close()
pygame.quit()
