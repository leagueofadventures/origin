
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

# === Настройки ===
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
parser = argparse.ArgumentParser(description='Игровой клиент')
parser.add_argument('--server', '-s', type=str, default='ws://localhost:8765', help='WebSocket URL сервера')
parser.add_argument('--windowed', '-w', action='store_true', help='Оконный режим')
args = parser.parse_args()

SERVER_URL = args.server
WIDTH, HEIGHT = 1920, 1080

# === Инициализация Pygame ===
pygame.init()
screen = pygame.display.set_mode((WIDTH, HEIGHT) if args.windowed else (0, 0), pygame.FULLSCREEN)
pygame.display.set_caption("Мультиплеерная игра")
info = pygame.display.Info()
width, height = info.current_w, info.current_h

font = pygame.font.SysFont(None, 24)

# === Загрузка ресурсов ===
player_sprites = {}
attack_sprites = {}
directions = ['up', 'down', 'left', 'right']
try:
    walk_base_path = os.path.join(PROJECT_DIR, 'sprites', 'PNG', 'Vampires1', 'Vampires1_Walk_without_shadow.png')
    attack_base_path = os.path.join(PROJECT_DIR, 'sprites', 'PNG', 'Vampires1', 'Vampires1_Attack_without_shadow.png')
    for dir_name in directions:
        player_sprites[dir_name] = [
            pygame.image.load(os.path.join(walk_base_path, f"{dir_name}{i}.jpg")).convert_alpha() for i in range(1, 7)
        ]
        attack_sprites[dir_name] = [
            pygame.image.load(os.path.join(attack_base_path, f"{dir_name}{i}.jpg")).convert_alpha() for i in range(1, 7)
        ]
except Exception as e:
    print(f"Ошибка загрузки спрайтов: {e}")
    running = False

# === Загрузка карты ===
map_file = os.path.join(PROJECT_DIR, 'maps', 'безымянный.tmx')
try:
    tmx_data = util_pygame.load_pygame(map_file)
    map_width = tmx_data.width * tmx_data.tilewidth
    map_height = tmx_data.height * tmx_data.tileheight
except Exception as e:
    print(f"Карта не найдена: {e}")
    pygame.quit()
    sys.exit()

# === Состояние игры ===
animation_frame = 0.0
clock = pygame.time.Clock()

players = {}
mobs = {}
projectiles = {}
client_chat_history = []

cid = None
ws = None
running = True
chat_input_mode = False
chat_input_text = ""

is_attacking = False
attack_frame_index = 0

camera_x = 0
camera_y = 0

# === Функция отрисовки карты ===
def draw_map(surface, cam_x, cam_y):
    tw, th = tmx_data.tilewidth, tmx_data.tileheight
    start_col = max(0, cam_x // tw)
    end_col = min(tmx_data.width, (cam_x + width) // tw + 1)
    start_row = max(0, cam_y // th)
    end_row = min(tmx_data.height, (cam_y + height) // th + 1)

    for layer in tmx_data.visible_layers:
        if isinstance(layer, pytmx.TiledTileLayer):
            for x in range(start_col, end_col):
                for y in range(start_row, end_row):
                    gid = layer.data[y][x]
                    tile = tmx_data.get_tile_image_by_gid(gid)
                    if tile:
                        surface.blit(tile, (x * tw - cam_x, y * th - cam_y))

# === WebSocket логика ===
def on_message(ws, message):
    global players, mobs, projectiles, client_chat_history, cid
    try:
        if not message.strip():
            return
        data = json.loads(message)
        if data['type'] == 'status':
            cid = data['cid']
            print(f"Подключён как {cid}")
        elif data['type'] == 'state':
            players = data.get('Players', {})
            mobs = data.get('Mobs', {})
            projectiles = data.get('Projectiles', {})
            client_chat_history = data.get('chat_history', [])
        elif data['type'] == 'attack' and data['target'] in players:
            players[data['target']]['hp'] = max(0, players[data['target']].get('hp', 100) - data['damage'])
    except Exception as e:
        print(f"Ошибка парсинга: {e}")

def on_error(ws, error):
    print(f"Ошибка WebSocket: {error}")

def on_close(ws, *args):
    print("Соединение закрыто")

def on_open(ws):
    ws.send(json.dumps({'type': 'handshake'}))

def connect_websocket():
    global ws
    ws = websocket.WebSocketApp(
        SERVER_URL,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close,
        on_open=on_open
    )
    ws.run_forever()

# === Запуск WebSocket в потоке ===
threading.Thread(target=connect_websocket, daemon=True).start()
time.sleep(1)

# === Главный цикл ===
while running:
    dt = clock.tick(60) / 1000.0  # Дельта-время
    animation_frame = (animation_frame + 0.2 * dt * 60) % 6  # Синхронизация с FPS

    # === Обработка событий ===
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False
        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                running = False
            elif event.key == pygame.K_t:
                chat_input_mode = not chat_input_mode
                chat_input_text = ""
            elif chat_input_mode:
                if event.key == pygame.K_RETURN and chat_input_text.strip():
                    if ws and ws.sock and ws.sock.connected:
                        ws.send(json.dumps({
                            'type': 'chat',
                            'message': chat_input_text.strip(),
                            'author': cid
                        }))
                    chat_input_text = ""
                    chat_input_mode = False
                elif event.key == pygame.K_BACKSPACE:
                    chat_input_text = chat_input_text[:-1]
                else:
                    if event.unicode.isprintable() and len(chat_input_text) < 100:
                        chat_input_text += event.unicode
            elif event.key == pygame.K_SPACE and cid and cid in players and not is_attacking:
                is_attacking = True
                attack_frame_index = 0

    # === Логика атаки ===
    if is_attacking:
        attack_frame_index += 0.2 * dt * 60
        if attack_frame_index >= len(attack_sprites[players[cid]['direction']]):
            is_attacking = False
            # Отправка атаки
            ws.send(json.dumps({'type': 'attack', 'target': cid, 'damage': 10}))

    # === Камера следует за игроком ===
    if cid and cid in players:
        px, py = players[cid]['x'], players[cid]['y']
        camera_x = max(0, min(px - width // 2, map_width - width))
        camera_y = max(0, min(py - height // 2, map_height - height))

    # === Отрисовка ===
    screen.fill((0, 0, 0))
    draw_map(screen, camera_x, camera_y)

    # Отрисовка игроков
    for pid, p in players.items():
        px, py = p['x'] - camera_x, p['y'] - camera_y
        direction = p.get('direction', 'down')
        frame = int(animation_frame)
        sprite = None

        if pid == cid and is_attacking:
            sprite_list = attack_sprites[direction]
            sprite = sprite_list[int(attack_frame_index) % len(sprite_list)]
        elif p.get('moving'):
            sprite_list = player_sprites[direction]
            sprite = sprite_list[frame % len(sprite_list)]
        else:
            sprite = player_sprites[direction][0]

        if sprite:
            screen.blit(sprite, (px - 16, py - 16))
        else:
            pygame.draw.rect(screen, (0, 255, 0), (px - 16, py - 16, 32, 32))

        # HP bar
        hp = p.get('hp', 100)
        if hp < 100:
            pygame.draw.rect(screen, (255, 0, 0), (px - 16, py - 32, 32, 5))
            pygame.draw.rect(screen, (0, 255, 0), (px - 16, py - 32, 32 * (hp / 100), 5))

    # === Чат ===
    chat_rect = pygame.Rect(10, height - 260, 400, 250 + (30 if chat_input_mode else 0))
    pygame.draw.rect(screen, (0, 0, 0, 180), chat_rect, border_radius=8)

    y = chat_rect.y + 10
    for msg in client_chat_history[-8:]:
        text = font.render(f"{msg.get('author', '??')}: {msg.get('message', '')}", True, (255, 255, 255))
        screen.blit(text, (chat_rect.x + 10, y))
        y += 25

    if chat_input_mode:
        input_text = font.render(f"> {chat_input_text}", True, (255, 255, 255))
        screen.blit(input_text, (chat_rect.x + 10, chat_rect.y + chat_rect.h - 25))

    pygame.display.flip()

# === Очистка ===
if ws:
    ws.close()
pygame.quit()
