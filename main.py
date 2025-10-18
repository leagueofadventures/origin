import pygame
import pytmx
from pytmx import util_pygame
import websocket
import json
import sys
import os
import argparse
import threading
import time

# Определяем текущую директорию проекта
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))

# Парсинг аргументов командной строки
parser = argparse.ArgumentParser(description='Игровой клиент')
parser.add_argument('--server', '-s', type=str, default='wss://test-server-2zf4.onrender.com/ws', help='WebSocket URL сервера')
parser.add_argument('--windowed', '-w', action='store_true', help='Оконный режим')

args = parser.parse_args()

SERVER_URL = args.server

# Инициализация Pygame
pygame.init()
pygame.display.init()

# Полноэкранный режим или окно
if args.windowed:
    screen = pygame.display.set_mode((1920, 1080))
else:
    screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)

# Получение размеров экрана
info = pygame.display.Info()
width, height = info.current_w, info.current_h

# Шрифты
font_large = pygame.font.SysFont(None, 48)
font = pygame.font.SysFont(None, 24)

# Анимация
animation_frame = 0

# Загрузка спрайтов персонажа
player_sprites = {}
attack_sprites = {}
directions = ['up', 'down', 'left', 'right']
try:
    for dir_name in directions:
        player_sprites[dir_name] = []
        attack_sprites[dir_name] = []
        for i in range(1, 7):  # 6 кадров анимации для каждой стороны
            # Walk sprites
            walk_path = os.path.join(PROJECT_DIR, 'sprites', 'PNG', 'Vampires1', 'Vampires1_Walk_without_shadow.png', f'{dir_name}{i}.jpg')
            img = pygame.image.load(walk_path).convert_alpha()
            player_sprites[dir_name].append(img)
            # Attack sprites (12 frames, but we use first 6 for simplicity)
            attack_path = os.path.join(PROJECT_DIR, 'sprites', 'PNG', 'Vampires1', 'Vampires1_Attack_without_shadow.png', f'{dir_name}{i}.jpg')
            img_attack = pygame.image.load(attack_path).convert_alpha()
            attack_sprites[dir_name].append(img_attack)
except Exception as e:
    print(f"Ошибка загрузки спрайтов персонажа: {e}. Используем квадраты.")
    player_sprites = {}
    attack_sprites = {}

# Функция для рисования сущностей
def draw_entity(surface, x, y, color, size=32, sprite=None, frame=0):
    if sprite:
        surface.blit(sprite, (x - sprite.get_width()//2, y - sprite.get_height()//2))
    else:
        pygame.draw.rect(surface, color, (x - size//2, y - size//2, size, size))

# Загрузка TMX-карты
map_file = os.path.join(PROJECT_DIR, 'maps', 'безымянный.tmx')
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

# Позиция персонажа
player_x = width // 2
player_y = height - 100  # Спавн еще ниже, чтобы избежать застревания в текстурах
player_speed = 5

# Мультиплеер переменные
players = {}
mobs = {}
projectiles = {}
client_chat_history = []
cid = None
ws = None
running = True
chat_input_mode = False
chat_input_text = ""

# WebSocket connection
def on_message(ws, message):
    global players, mobs, projectiles, client_chat_history, player_x, player_y, cid
    if not message.strip():
        return
    try:
        data = json.loads(message)
        if data['type'] == 'status':
            cid = data['cid']
            print(f"Connected as {cid}")
        elif data['type'] == 'state':
            players = data.get('Players', {})
            mobs = data.get('Mobs', {})
            projectiles = data.get('Projectiles', {})
            client_chat_history = data.get('chat_history', [])
            # Update self position if available
            if cid and cid in players:
                player_x = players[cid]['x']
                player_y = players[cid]['y']
    except Exception as e:
        print(f"Error parsing message: {e}")

def on_error(ws, error):
    print(f"WebSocket error: {error}")

def on_close(ws, close_status_code, close_msg):
    print("WebSocket closed")

def on_open(ws):
    print("WebSocket opened")
    # Send handshake
    ws.send(json.dumps({'type': 'handshake'}))

def connect_websocket():
    global ws
    ws = websocket.WebSocketApp(SERVER_URL,
                                on_message=on_message,
                                on_error=on_error,
                                on_close=on_close)
    ws.on_open = on_open
    ws.run_forever()

# Start WebSocket in a thread
ws_thread = threading.Thread(target=connect_websocket)
ws_thread.daemon = True
ws_thread.start()

# Wait for connection
time.sleep(1)

def draw_map(surface, camera_x, camera_y):
    tilewidth = tmx_data.tilewidth
    tileheight = tmx_data.tileheight
    start_col = max(0, camera_x // tilewidth)
    end_col = min(tmx_data.width, (camera_x + width) // tilewidth + 1)
    start_row = max(0, camera_y // tileheight)
    end_row = min(tmx_data.height, (camera_y + height) // tileheight + 1)
    for layer in tmx_data.visible_layers:
        if isinstance(layer, pytmx.TiledTileLayer):
            for x in range(start_col, end_col):
                for y in range(start_row, end_row):
                    gid = layer.data[y][x]
                    tile = tmx_data.get_tile_image_by_gid(gid)
                    if tile:
                        surface.blit(tile, (x * tilewidth - camera_x,
                                            y * tileheight - camera_y))

# Simple shapes for entities
def draw_square(surface, x, y, color, size=32):
    pygame.draw.rect(surface, color, (x - size//2, y - size//2, size, size))

def draw_circle(surface, x, y, color, radius):
    pygame.draw.circle(surface, color, (x, y), radius)

def collides_with_objects(x, y, size):
    rect = pygame.Rect(x - size//2, y - size//2, size, size)
    for collision_rect in collision_rects:
        if rect.colliderect(collision_rect):
            return True
    return False

while running:
    clock = pygame.time.Clock()
    clock.tick(60)

    # Update animation frame (slower for smoother animation)
    animation_frame += 0.2
    frame_index = int(animation_frame)

    # Обработка событий
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False
        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                running = False
            elif event.key == pygame.K_t:  # T for chat
                chat_input_mode = not chat_input_mode
                if chat_input_mode:
                    chat_input_text = ""
            elif chat_input_mode:
                if event.key == pygame.K_RETURN:
                    if chat_input_text.strip():
                        if ws and ws.sock and ws.sock.connected:
                            try:
                                ws.send(json.dumps({'type': 'input', 'chat': chat_input_text.strip()}))
                            except Exception as e:
                                print(f"Chat send error: {e}")
                        chat_input_text = ""
                        chat_input_mode = False
                elif event.key == pygame.K_BACKSPACE:
                    chat_input_text = chat_input_text[:-1]
                else:
                    if event.unicode.isprintable():
                        chat_input_text += event.unicode

    if not chat_input_mode:
        # Send inputs
        keys = pygame.key.get_pressed()
        inputs = {
            'type': 'input',
            'left': keys[pygame.K_LEFT],
            'right': keys[pygame.K_RIGHT],
            'up': keys[pygame.K_UP],
            'down': keys[pygame.K_DOWN],
            'attack': keys[pygame.K_SPACE]
        }
        if ws and ws.sock and ws.sock.connected:
            try:
                ws.send(json.dumps(inputs))
            except Exception as e:
                print(f"Send error: {e}")

    # Camera follow player
    if cid and cid in players:
        player_x = players[cid]['x']
        player_y = players[cid]['y']
        camera_x = max(0, min(player_x - (width // 2), map_width - width))
        camera_y = max(0, min(player_y - (height // 2), map_height - height))

    # Rendering
    screen.fill((0, 0, 0))

    # Draw map
    draw_map(screen, camera_x, camera_y)

    # Draw self (assuming cid is set)
    if cid:
        player_dir = players[cid].get('direction', 'down')
        is_moving = players[cid].get('moving', False)
        is_attacking = players[cid].get('attacking', False)
        if player_sprites and player_dir in player_sprites:
            if is_attacking and attack_sprites and player_dir in attack_sprites:
                sprite = attack_sprites[player_dir][frame_index % len(attack_sprites[player_dir])]
            elif is_moving:
                sprite = player_sprites[player_dir][frame_index % len(player_sprites[player_dir])]
            else:
                # Idle animation, use first frame
                sprite = player_sprites[player_dir][0]
            draw_entity(screen, player_x - camera_x, player_y - camera_y, (0, 255, 0), sprite=sprite)
        else:
            draw_square(screen, player_x - camera_x, player_y - camera_y, (0, 255, 0))  # Green for self

    # Draw other players
    for pid, pos in players.items():
        if pid != cid:
            player_dir = pos.get('direction', 'down')
            is_moving = pos.get('moving', False)
            is_attacking = pos.get('attacking', False)
            if player_sprites and player_dir in player_sprites:
                if is_attacking and attack_sprites and player_dir in attack_sprites:
                    sprite = attack_sprites[player_dir][frame_index % len(attack_sprites[player_dir])]
                elif is_moving:
                    sprite = player_sprites[player_dir][frame_index % len(player_sprites[player_dir])]
                else:
                    sprite = player_sprites[player_dir][0]
                draw_entity(screen, pos['x'] - camera_x, pos['y'] - camera_y, (0, 0, 255), sprite=sprite)
            else:
                draw_square(screen, pos['x'] - camera_x, pos['y'] - camera_y, (0, 0, 255))  # Blue for others

    # Draw mobs
    for mid, mob in mobs.items():
        draw_square(screen, mob['x'] - camera_x, mob['y'] - camera_y, (255, 0, 0))  # Red for mobs

    # Draw projectiles
    for pid, proj in projectiles.items():
        draw_circle(screen, proj['x'] - camera_x, proj['y'] - camera_y, (255, 0, 0), 6)  # Red circle for projectiles

    # Draw chat
    rect_width = 400
    rect_height = 250 + (30 if chat_input_mode else 0)
    rect_x = 10
    rect_y = height - rect_height - 10
    chat_surface = pygame.Surface((rect_width, rect_height), pygame.SRCALPHA)
    chat_surface.fill((0, 0, 0, 128))
    screen.blit(chat_surface, (rect_x, rect_y))
    y_offset = rect_y + 10
    for msg in client_chat_history[-8:]:
        text = font.render(msg['message'], True, (255, 255, 255))
        if y_offset + text.get_height() > rect_y + rect_height - (30 if chat_input_mode else 0):
            break
        screen.blit(text, (rect_x + 10, y_offset))
        y_offset += 25
    if chat_input_mode:
        input_y = rect_y + rect_height - 30
        input_surface = pygame.Surface((rect_width, 30), pygame.SRCALPHA)
        input_surface.fill((0, 0, 0, 128))
        screen.blit(input_surface, (rect_x, input_y))
        input_text = font.render("> " + chat_input_text, True, (255, 255, 255))
        screen.blit(input_text, (rect_x + 10, input_y + 5))

    pygame.display.flip()

if ws:
    ws.close()
pygame.quit()
