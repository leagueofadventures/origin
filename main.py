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
import math
import random
import queue
from enum import Enum

# ============================================================
# КОНФИГУРАЦИЯ
# ============================================================
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))

parser = argparse.ArgumentParser(description='Игровой клиент')
parser.add_argument('--server', '-s', type=str, default='ws://127.0.0.1:8080/ws')
parser.add_argument('--windowed', '-w', action='store_true')
args = parser.parse_args()

SERVER_URL = args.server if args.server.startswith('ws') else f'ws://{args.server}'

pygame.init()
pygame.mixer.init()
pygame.display.init()

if args.windowed:
    screen = pygame.display.set_mode((1920, 1080))
else:
    screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)

info = pygame.display.Info()
width, height = info.current_w, info.current_h

font_large = pygame.font.SysFont(None, 48)
font = pygame.font.SysFont(None, 24)

DEBUG_COLLISIONS = False
DEBUG_FOG = False

# ============================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ============================================================
def draw_square(surface, x, y, color, size=32):
    pygame.draw.rect(surface, color, (int(x - size // 2), int(y - size // 2), size, size))

def draw_circle(surface, x, y, color, radius):
    pygame.draw.circle(surface, color, (int(x), int(y)), radius)

def draw_entity(surface, x, y, color, size=32, sprite=None):
    if sprite:
        surface.blit(sprite, (int(x - sprite.get_width() // 2), int(y - sprite.get_height() // 2)))
    else:
        pygame.draw.rect(surface, color, (int(x - size // 2), int(y - size // 2), size, size))

# ============================================================
# ЗАГРУЗКА КАРТЫ
# ============================================================
def load_map():
    map_file = os.path.join(PROJECT_DIR, 'maps', 'безымянный.tmx')
    try:
        tmx_data = util_pygame.load_pygame(map_file)
    except Exception as e:
        print(f"Критическая ошибка загрузки карты: {e}")
        pygame.quit()
        sys.exit()
    
    map_width = tmx_data.width * tmx_data.tilewidth
    map_height = tmx_data.height * tmx_data.tileheight
    collision_rects = []
    
    tw = tmx_data.tilewidth
    th = tmx_data.tileheight
    
    print(f"\n📐 Карта: {tmx_data.width}x{tmx_data.height} тайлов")
    print(f"📋 Слои: {[getattr(l, 'name', '???') for l in tmx_data.layers]}")
    
    collision_layer = None
    for layer in tmx_data.layers:
        layer_name = getattr(layer, 'name', '').lower()
        if layer_name in ('objects', 'collision', 'collisions', 'walls'):
            collision_layer = layer
            break
    
    if collision_layer is None:
        print("⚠️ Слой 'objects' не найден!")
    else:
        print(f"✅ Найден слой коллизий: '{collision_layer.name}'")
        
        if isinstance(collision_layer, pytmx.TiledObjectGroup):
            for obj in collision_layer:
                rect = pygame.Rect(int(obj.x), int(obj.y),
                                   int(obj.width) if obj.width else tw,
                                   int(obj.height) if obj.height else th)
                collision_rects.append(rect)
            print(f"   📦 ObjectGroup: {len(collision_rects)} объектов")
            
        elif isinstance(collision_layer, pytmx.TiledTileLayer):
            for y in range(collision_layer.height):
                for x in range(collision_layer.width):
                    gid = collision_layer.data[y][x]
                    if gid != 0:
                        collision_rects.append(pygame.Rect(x * tw, y * th, tw, th))
            print(f"   🧱 TileLayer: {len(collision_rects)} тайлов-препятствий")
    
    return tmx_data, map_width, map_height, collision_rects

# ============================================================
# ОТРИСОВКА КАРТЫ
# ============================================================
def draw_map(surface, camera_x, camera_y, tmx_data, collision_rects=None):
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
                        surface.blit(tile, (x * tilewidth - camera_x, y * tileheight - camera_y))
        
        elif isinstance(layer, pytmx.TiledObjectGroup):
            for obj in layer:
                obj_rect = pygame.Rect(
                    int(obj.x - camera_x), int(obj.y - camera_y),
                    int(obj.width) if obj.width else tilewidth,
                    int(obj.height) if obj.height else tileheight
                )
                block_surface = pygame.Surface((obj_rect.width, obj_rect.height), pygame.SRCALPHA)
                block_surface.fill((30, 30, 30, 200))
                surface.blit(block_surface, obj_rect.topleft)
                
                if DEBUG_COLLISIONS:
                    pygame.draw.rect(surface, (255, 0, 255), obj_rect, 2)
    
   

# ============================================================
# КОЛЛИЗИИ И ТУМАН ВОЙНЫ
# ============================================================
def collides_with_objects(x, y, size, collision_rects):
    rect = pygame.Rect(int(x - size // 2), int(y - size // 2), size, size)
    return any(rect.colliderect(cr) for cr in collision_rects)

def line_intersects_rect(x1, y1, x2, y2, rect):
    if rect.collidepoint(int(x1), int(y1)) or rect.collidepoint(int(x2), int(y2)):
        return True
    result = rect.clipline(int(x1), int(y1), int(x2), int(y2))
    return bool(result)

def has_line_of_sight(x1, y1, x2, y2, collision_rects):
    min_x, max_x = min(x1, x2), max(x1, x2)
    min_y, max_y = min(y1, y2), max(y1, y2)
    line_rect = pygame.Rect(int(min_x), int(min_y), int(max_x - min_x) + 1, int(max_y - min_y) + 1)
    
    for rect in collision_rects:
        if not line_rect.colliderect(rect):
            continue
        if line_intersects_rect(x1, y1, x2, y2, rect):
            return False
    return True

def draw_fog_of_war(surface, camera_x, camera_y, tmx_data, player_x, player_y, collision_rects, view_radius=350):
    fog_surface = pygame.Surface((width, height), pygame.SRCALPHA)
    fog_surface.fill((0, 0, 0, 210))
    
    tw = tmx_data.tilewidth
    th = tmx_data.tileheight
    
    radius_tiles = int(view_radius / min(tw, th)) + 2
    center_tx = int(player_x // tw)
    center_ty = int(player_y // th)
    
    for ty in range(max(0, center_ty - radius_tiles), min(tmx_data.height, center_ty + radius_tiles + 1)):
        for tx in range(max(0, center_tx - radius_tiles), min(tmx_data.width, center_tx + radius_tiles + 1)):
            tile_center_x = tx * tw + tw // 2
            tile_center_y = ty * th + th // 2
            
            dist = math.hypot(tile_center_x - player_x, tile_center_y - player_y)
            if dist > view_radius:
                continue
            
            if has_line_of_sight(player_x, player_y, tile_center_x, tile_center_y, collision_rects):
                screen_x = tx * tw - camera_x
                screen_y = ty * th - camera_y
                pygame.draw.rect(fog_surface, (0, 0, 0, 0), (screen_x, screen_y, tw, th))
    
    surface.blit(fog_surface, (0, 0))

def draw_player_ui(surface, player):
    ui_width, ui_height, ui_x, ui_y = 300, 100, 10, 10
    ui_surface = pygame.Surface((ui_width, ui_height), pygame.SRCALPHA)
    ui_surface.fill((0, 0, 0, 180))
    surface.blit(ui_surface, (ui_x, ui_y))
    
    surface.blit(font_large.render(f"LVL: {player.lvl}", True, (255, 215, 0)), (ui_x + 10, ui_y + 10))
    surface.blit(font.render(f"HP: {player.health}/{player.maxHealth}", True, (255, 0, 0)), (ui_x + 10, ui_y + 40))
    surface.blit(font.render(f"EXP: {player.exp}/{player.exp_to_next_level}", True, (100, 200, 255)), (ui_x + 150, ui_y + 40))
    
    bar_width, bar_height, bar_x, bar_y = 280, 15, ui_x + 10, ui_y + 70
    pygame.draw.rect(surface, (50, 50, 50), (bar_x, bar_y, bar_width, bar_height))
    if player.exp_to_next_level > 0:
        fill_width = int(bar_width * min(1.0, player.exp / player.exp_to_next_level))
        pygame.draw.rect(surface, (100, 200, 255), (bar_x, bar_y, fill_width, bar_height))
    pygame.draw.rect(surface, (255, 255, 255), (bar_x, bar_y, bar_width, bar_height), 2)

# ============================================================
# КЛАССЫ СУЩНОСТЕЙ
# ============================================================
class Mob:
    def __init__(self, x, y, speed, health):
        self.x, self.y = float(x), float(y)
        self.speed = speed
        self.health, self.max_health = health, health
        self.last_attacking_time = 0
        self.exp_reward = 25

    def update(self, player, current_time, projectiles, collision_rects):
        dx = player.x - self.x
        dy = player.y - self.y
        distance = max(0.1, math.hypot(dx, dy))
        ndx = (dx / distance) * self.speed
        ndy = (dy / distance) * self.speed
        
        new_x = self.x + ndx
        new_y = self.y + ndy
        
        if not collides_with_objects(new_x, new_y, 28, collision_rects):
            self.x, self.y = new_x, new_y
        elif not collides_with_objects(new_x, self.y, 28, collision_rects):
            self.x = new_x
        elif not collides_with_objects(self.x, new_y, 28, collision_rects):
            self.y = new_y
        
        if current_time - self.last_attacking_time >= 1000:
            if has_line_of_sight(self.x, self.y, player.x, player.y, collision_rects):
                projectiles.append(Projectile(self.x, self.y, 5, player.x, player.y))
                self.last_attacking_time = current_time

    def draw(self, surface, camera_x, camera_y):
        draw_square(surface, self.x - camera_x, self.y - camera_y, (255, 0, 0))
        if self.health < self.max_health:
            bar_w, bar_h = 30, 4
            bx, by = int(self.x - camera_x - bar_w // 2), int(self.y - camera_y - 20)
            pygame.draw.rect(surface, (50, 50, 50), (bx, by, bar_w, bar_h))
            pygame.draw.rect(surface, (255, 0, 0), (bx, by, int(bar_w * (self.health / self.max_health)), bar_h))
            pygame.draw.rect(surface, (255, 255, 255), (bx, by, bar_w, bar_h), 1)


class Projectile:
    def __init__(self, x, y, speed, target_x, target_y):
        self.x, self.y = float(x), float(y)
        self.speed = speed
        dx, dy = target_x - self.x, target_y - self.y
        dist = max(0.1, math.hypot(dx, dy))
        self.dx, self.dy = dx / dist, dy / dist
        self.alive = True
        self.max_distance = 800
        self.traveled = 0

    def update(self, collision_rects=None):
        move_x = self.dx * self.speed
        move_y = self.dy * self.speed
        self.traveled += math.hypot(move_x, move_y)
        
        if self.traveled > self.max_distance:
            self.alive = False
            return
        
        new_x, new_y = self.x + move_x, self.y + move_y
        
        if collision_rects and collides_with_objects(new_x, new_y, 8, collision_rects):
            self.alive = False
            return
        
        self.x, self.y = new_x, new_y

    def draw(self, surface, camera_x, camera_y):
        draw_circle(surface, self.x - camera_x, self.y - camera_y, (255, 100, 0), 6)


class Player:
    def __init__(self, x, y, lvl, exp, speed, health, dmg):
        self.x, self.y = float(x), float(y)
        self.lvl, self.exp, self.exp_to_next_level = lvl, exp, 100
        self.speed = speed
        self.direction = 'down'
        self.moving, self.attacking = False, False
        self.health, self.maxHealth, self.dmg = health, health, dmg
        self.last_attacking_time = 0

    def lvl_up(self):
        self.maxHealth += 10
        self.health = self.maxHealth
        self.dmg += 5
        self.lvl += 1
        self.exp_to_next_level = int(self.exp_to_next_level * 1.5)

    def add_exp(self, amount):
        self.exp += amount
        while self.exp >= self.exp_to_next_level:
            self.exp -= self.exp_to_next_level
            self.lvl_up()

    def update(self, keys, collision_rects, current_time, mobs, projectiles):
        self.moving = False
        new_x, new_y = self.x, self.y
        
        if keys[pygame.K_w]: new_y -= self.speed; self.direction = 'up'; self.moving = True
        if keys[pygame.K_s]: new_y += self.speed; self.direction = 'down'; self.moving = True
        if keys[pygame.K_a]: new_x -= self.speed; self.direction = 'left'; self.moving = True
        if keys[pygame.K_d]: new_x += self.speed; self.direction = 'right'; self.moving = True
        
        self.attacking = keys[pygame.K_SPACE]
        
        if not collides_with_objects(new_x, self.y, 28, collision_rects):
            self.x = new_x
        if not collides_with_objects(self.x, new_y, 28, collision_rects):
            self.y = new_y
        
        if self.attacking and current_time - self.last_attacking_time >= 1000 and mobs:
            visible = [m for m in mobs if has_line_of_sight(self.x, self.y, m.x, m.y, collision_rects)]
            if visible:
                closest = min(visible, key=lambda m: math.hypot(m.x - self.x, m.y - self.y))
                projectiles.append(Projectile(self.x, self.y, 5, closest.x, closest.y))
                self.last_attacking_time = current_time

    def draw(self, surface, camera_x, camera_y, frame_index, sprites, attack_sprites):
        if sprites and self.direction in sprites and sprites[self.direction]:
            if self.attacking and attack_sprites and self.direction in attack_sprites:
                sprite = attack_sprites[self.direction][frame_index % len(attack_sprites[self.direction])]
            elif self.moving:
                sprite = sprites[self.direction][frame_index % len(sprites[self.direction])]
            else:
                sprite = sprites[self.direction][0]
            draw_entity(surface, self.x - camera_x, self.y - camera_y, (0, 255, 0), sprite=sprite)
        else:
            draw_square(surface, self.x - camera_x, self.y - camera_y, (0, 255, 0))


# ============================================================
# ЗАГРУЗКА РЕСУРСОВ
# ============================================================
def load_sprites():
    player_sprites, attack_sprites = {}, {}
    for dir_name in ['up', 'down', 'left', 'right']:
        player_sprites[dir_name], attack_sprites[dir_name] = [], []
        for i in range(1, 7):
            walk_path = os.path.join(PROJECT_DIR, 'sprites', 'PNG', 'Vampires1', 'Vampires1_Walk_without_shadow.png', f'{dir_name}{i}.png')
            attack_path = os.path.join(PROJECT_DIR, 'sprites', 'PNG', 'Vampires1', 'Vampires1_Attack_without_shadow.png', f'{dir_name}{i}.png')
            if os.path.exists(walk_path):
                player_sprites[dir_name].append(pygame.image.load(walk_path).convert_alpha())
            if os.path.exists(attack_path):
                attack_sprites[dir_name].append(pygame.image.load(attack_path).convert_alpha())
    return player_sprites, attack_sprites

def load_ui_assets():
    assets = {}
    for lang in ['ru', 'en']:
        assets[lang] = {}
        for theme in ['light', 'dark']:
            assets[lang][theme] = {}
            folder = os.path.join(PROJECT_DIR, 'images', lang, theme)
            if not os.path.exists(folder): continue
            for filename in os.listdir(folder):
                if filename.endswith(('.png', '.jpg', '.jpeg')):
                    key = os.path.splitext(filename)[0]
                    path = os.path.join(folder, filename)
                    try:
                        assets[lang][theme][key] = pygame.transform.scale(
                            pygame.image.load(path), screen.get_size()
                        )
                    except: pass
            
            assets[lang][theme]['intro_images'] = []
            for i in range(1, 11):
                path = os.path.join(folder, f'{i}.png')
                if os.path.exists(path):
                    try:
                        assets[lang][theme]['intro_images'].append(
                            pygame.transform.scale(pygame.image.load(path), screen.get_size())
                        )
                    except: pass
        
        for name, filename in [('menu', 'menu.jpg' if lang == 'ru' else 'меню.png'), ('pause', 'pause.jpg')]:
            path = os.path.join(PROJECT_DIR, 'images', lang, filename)
            if os.path.exists(path):
                try:
                    assets[lang][name] = pygame.transform.scale(pygame.image.load(path), screen.get_size())
                except: pass
    
    assets['toggles'], assets['off_toggles'] = [], []
    for i in range(3):
        for prefix, target in [('on_toggle', assets['toggles']), ('off_toggle', assets['off_toggles'])]:
            path = os.path.join(PROJECT_DIR, 'images', f'{prefix}{i}.png')
            if os.path.exists(path):
                try:
                    target.append(pygame.transform.scale(pygame.image.load(path), (max(1, width // 16), max(1, int(height // 15.43)))))
                except: pass
    return assets

# ============================================================
# STATE MACHINE И WEBSOCKET
# ============================================================
class GameState(Enum):
    MAIN_MENU = "menu"
    OPTIONS = "options"
    QUIT_CONFIRM = "quit"
    SOLO_INTRO = "solo_intro"
    SOLO_PLAY = "solo_play"
    PAUSE = "pause"
    MULTIPLAYER = "multiplayer"

def connect_websocket(ws_queue, state):
    def on_message(ws, message):
        if not message.strip(): return
        try:
            data = json.loads(message)
            if data['type'] == 'status': state['cid'] = data['cid']
            elif data['type'] == 'state':
                state['players'] = data.get('Players', {})
                state['mobs'] = data.get('Mobs', {})
                state['projectiles'] = data.get('Projectiles', {})
                state['chat_history'] = data.get('chat_history', [])
        except Exception as e: print(f"Parse error: {e}")

    def on_error(ws, error):
        state['connection_error'] = True

    def on_close(ws, *args): pass

    def on_open(ws):
        state['connection_error'] = False
        ws_queue.put({'type': 'handshake'})

    ws = websocket.WebSocketApp(SERVER_URL, on_message=on_message, on_error=on_error, on_close=on_close)
    ws.on_open = on_open

    def sender_thread():
        while state['running']:
            try:
                msg = ws_queue.get(timeout=1.0)
                ws.send(json.dumps(msg))
            except queue.Empty: continue
            except: break

    threading.Thread(target=sender_thread, daemon=True).start()
    ws.run_forever()

# ============================================================
# ИНИЦИАЛИЗАЦИЯ
# ============================================================
player_sprites, attack_sprites = load_sprites()
UI_ASSETS = load_ui_assets()
tmx_data, map_width, map_height, collision_rects = load_map()

state = {
    'current': GameState.MAIN_MENU, 'theme': 'dark', 'language': 'ru',
    'animation_frame': 0.0, 'camera_x': 0, 'camera_y': 0,
    'skip': False, 'skip_time': 0,
    'pause_start_time': 0, 'pause_close_time': 0, 'solo_start_time': 0,
    'change_time': 8000, 'chat_input_mode': False, 'chat_input_text': "",
    'toggle_states': [False, False, False],
    'solo_player': Player(map_width - (map_width // 3), map_height - (map_height // 3), 1, 0, 5, 100, 10),
    'solo_mobs': [], 'solo_projectiles': [], 'solo_mob_projectiles': [],
    'players': {}, 'mobs': {}, 'projectiles': {}, 'chat_history': [],
    'cid': None, 'connection_error': False, 'running': True,
    'ws_queue': queue.Queue()
}

solo_rect = pygame.Rect(int(width // 2.35), int(height // 1.78), int(width // 6.4), int(height // 15.4))
multi_rect = pygame.Rect(int(width // 2.34), int(height // 1.5), int(width // 6.4), int(height // 15.4))
opt_rect = pygame.Rect(int(width // 2.34), int(height // 1.31), int(width // 6.4), int(height // 15.4))
quit_rect = pygame.Rect(int(width // 2.31), int(height // 1.17), int(width // 7.1), int(height // 15.4))
yes_rect = pygame.Rect(int(width // 2.44), int(height // 1.83), int(width // 12), int(height // 16.6))
no_rect = pygame.Rect(int(width // 1.96), int(height // 1.83), int(width // 12), int(height // 16.6))
cont_rect = pygame.Rect(int(width // 2.60), int(height // 2.09), int(width // 4.08), int(height // 8.3))
exit_rect = pygame.Rect(int(width // 2.59), int(height // 1.57), int(width // 4.08), int(height // 8.3))
toggles_rect = [
    pygame.Rect(int(width // 1.5035), int(height // 2.4489), max(1, width // 16), max(1, int(height // 15.43))),
    pygame.Rect(int(width // 1.5035), int(height // 1.875), max(1, width // 16), max(1, int(height // 15.43))),
    pygame.Rect(int(width // 1.5035), int(height // 1.51898), max(1, width // 16), max(1, int(height // 15.43)))
]

# ============================================================
# ГЛАВНЫЙ ЦИКЛ
# ============================================================
clock = pygame.time.Clock()

while state['running']:
    dt = clock.tick(60)
    current_time = pygame.time.get_ticks()
    state['animation_frame'] += 0.2
    frame_index = int(state['animation_frame'])
    
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            state['running'] = False
        
        
                
        
        elif event.type == pygame.MOUSEBUTTONDOWN:
            mx, my = event.pos
            cur = state['current']
            
            if cur == GameState.MAIN_MENU:
                if solo_rect.collidepoint(mx, my):
                    state['current'] = GameState.SOLO_INTRO
                    state['solo_start_time'] = current_time
                    state['pause_close_time'] = 0
                elif multi_rect.collidepoint(mx, my):
                    state['connection_error'] = False
                    threading.Thread(target=connect_websocket, args=(state['ws_queue'], state), daemon=True).start()
                    time.sleep(1)
                    if not state['connection_error']:
                        state['current'] = GameState.MULTIPLAYER
                elif opt_rect.collidepoint(mx, my):
                    state['current'] = GameState.OPTIONS
                elif quit_rect.collidepoint(mx, my):
                    state['current'] = GameState.QUIT_CONFIRM
            
            elif cur == GameState.OPTIONS:
                for i in range(min(3, len(state['toggle_states']))):
                    if toggles_rect[i].collidepoint(mx, my):
                        state['toggle_states'][i] = not state['toggle_states'][i]
                        if i == 0:
                            if state['toggle_states'][0]: pygame.mixer.music.play(-1)
                            else: pygame.mixer.music.stop()
                        elif i == 1: state['language'] = 'en' if state['toggle_states'][1] else 'ru'
                        elif i == 2: state['theme'] = 'light' if state['toggle_states'][2] else 'dark'
                        break
            
            elif cur == GameState.QUIT_CONFIRM:
                if yes_rect.collidepoint(mx, my): state['running'] = False
                elif no_rect.collidepoint(mx, my): state['current'] = GameState.MAIN_MENU
            
            elif cur == GameState.PAUSE:
                if cont_rect.collidepoint(mx, my):
                    state['current'] = GameState.SOLO_PLAY
                    state['pause_close_time'] += current_time - state['pause_start_time']
                elif exit_rect.collidepoint(mx, my):
                    state['current'] = GameState.MAIN_MENU
        
        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                cur = state['current']
                if cur == GameState.OPTIONS: state['current'] = GameState.MAIN_MENU
                elif cur == GameState.SOLO_PLAY:
                    state['current'] = GameState.PAUSE
                    state['pause_start_time'] = current_time
                elif cur == GameState.PAUSE:
                    state['current'] = GameState.SOLO_PLAY
                    state['pause_close_time'] += current_time - state['pause_start_time']
                elif cur == GameState.MULTIPLAYER: state['current'] = GameState.MAIN_MENU
                elif state['chat_input_mode']: state['chat_input_mode'] = False
            
            if state['chat_input_mode']:
                if event.key == pygame.K_RETURN:
                    if state['chat_input_text'].strip():
                        state['ws_queue'].put({'type': 'input', 'chat': state['chat_input_text'].strip()})
                    state['chat_input_mode'], state['chat_input_text'] = False, ""
                elif event.key == pygame.K_BACKSPACE:
                    state['chat_input_text'] = state['chat_input_text'][:-1]
                elif event.unicode and event.unicode.isprintable():
                    state['chat_input_text'] += event.unicode
            else:
                if event.key == pygame.K_t and state['current'] == GameState.MULTIPLAYER:
                    state['chat_input_mode'], state['chat_input_text'] = True, ""
                elif event.key == pygame.K_SPACE and state['current'] == GameState.SOLO_INTRO:
                    state['skip'], state['skip_time'] = True, current_time
        
        elif event.type == pygame.KEYUP:
            if event.key == pygame.K_SPACE and state['skip'] and state['current'] == GameState.SOLO_INTRO:
                if current_time - state['skip_time'] > 200:
                    state['current'] = GameState.SOLO_PLAY
                    state['solo_player'].x = float(map_width - (map_width // 3))
                    state['solo_player'].y = float(map_height - (map_height // 3))
                state['skip'] = False
    
    # ============================================================
    # ОТРИСОВКА
    # ============================================================
    screen.fill((0, 0, 0))
    cur = state['current']
    lang, theme = state['language'], state['theme']
    
    if cur == GameState.MAIN_MENU:
        try: screen.blit(UI_ASSETS[lang]['menu'], (0, 0))
        except: screen.fill((40, 40, 60))
    
    elif cur == GameState.OPTIONS:
        try: screen.blit(UI_ASSETS[lang][theme]['settings_background'], (0, 0))
        except: screen.fill((60, 60, 80))
        for i in range(min(3, len(state['toggle_states']))):
            if state['toggle_states'][i] and i < len(UI_ASSETS.get('toggles', [])):
                screen.blit(UI_ASSETS['toggles'][i], toggles_rect[i])
            elif i < len(UI_ASSETS.get('off_toggles', [])):
                screen.blit(UI_ASSETS['off_toggles'][i], toggles_rect[i])
    
    elif cur == GameState.QUIT_CONFIRM:
        try: screen.blit(UI_ASSETS[lang][theme]['quit_menu'], (0, 0))
        except: screen.fill((100, 30, 30))
    
    elif cur == GameState.PAUSE:
        try: screen.blit(UI_ASSETS[lang]['pause'], (0, 0))
        except: screen.fill((30, 30, 30))
    
    # ============================================================
    #  КАТСЕНА 
    # ============================================================
    elif cur == GameState.SOLO_INTRO:
        elapsed = current_time - state['solo_start_time'] - state['pause_close_time']
        intros = UI_ASSETS.get(lang, {}).get(theme, {}).get('intro_images', [])
        
        if not state['skip']:
            if intros:
                image_index = min(int(elapsed / 2000), len(intros) - 1)
                screen.blit(intros[image_index], (0, 0))
            else:
                screen.fill((0, 0, 0))
                loading_text = font.render("Loading intro...", True, (255, 255, 255))
                screen.blit(loading_text, (width // 2 - 60, height // 2))
            
            
            
        
       
        auto_transition_time = 15000
        should_transition = elapsed > auto_transition_time
        
        if state['skip'] and current_time - state['skip_time'] > 200:
            should_transition = True
        
        if should_transition:
            state['current'] = GameState.SOLO_PLAY
            state['solo_player'].x = float(map_width - (map_width // 3))
            state['solo_player'].y = float(map_height - (map_height // 3))
            state['skip'] = False
    
    # ============================================================
    #  СОЛО ИГРА
    # ============================================================
    elif cur == GameState.SOLO_PLAY:
        if not state['solo_mobs']:
            for _ in range(50):
                sx = random.randint(100, max(101, map_width - 200))
                sy = random.randint(100, max(101, map_height - 200))
                if not collides_with_objects(sx, sy, 28, collision_rects):
                    state['solo_mobs'].append(Mob(sx, sy, 1, 100))
                    break
        
        keys = pygame.key.get_pressed()
        state['solo_player'].update(keys, collision_rects, current_time, state['solo_mobs'], state['solo_projectiles'])
        
        for mob in state['solo_mobs']:
            mob.update(state['solo_player'], current_time, state['solo_mob_projectiles'], collision_rects)
        
        for proj in state['solo_projectiles'] + state['solo_mob_projectiles']:
            proj.update(collision_rects)
        
        state['solo_projectiles'] = [p for p in state['solo_projectiles'] if p.alive]
        state['solo_mob_projectiles'] = [p for p in state['solo_mob_projectiles'] if p.alive]
        
        for proj in list(state['solo_projectiles']):
            for mob in state['solo_mobs']:
                if math.hypot(proj.x - mob.x, proj.y - mob.y) < 30 and mob.health > 0:
                    mob.health -= state['solo_player'].dmg
                    proj.alive = False
                    if mob.health <= 0:
                        state['solo_player'].add_exp(mob.exp_reward)
                    break
        
        state['solo_mobs'] = [m for m in state['solo_mobs'] if m.health > 0]
        
        for proj in list(state['solo_mob_projectiles']):
            if math.hypot(proj.x - state['solo_player'].x, proj.y - state['solo_player'].y) < 28:
                state['solo_player'].health -= 34
                proj.alive = False
        
        if state['solo_player'].health <= 0:
            state['current'] = GameState.MAIN_MENU
            state['solo_player'] = Player(map_width - (map_width // 3), map_height - (map_height // 3), 1, 0, 5, 100, 10)
            state['solo_mobs'] = []
            state['solo_projectiles'] = []
            state['solo_mob_projectiles'] = []
            continue
        
        state['camera_x'] = max(0, min(int(state['solo_player'].x - width // 2), map_width - width))
        state['camera_y'] = max(0, min(int(state['solo_player'].y - height // 2), map_height - height))
        
        draw_map(screen, state['camera_x'], state['camera_y'], tmx_data, collision_rects)
        
        px, py = state['solo_player'].x, state['solo_player'].y
        
        for mob in state['solo_mobs']:
            if has_line_of_sight(px, py, mob.x, mob.y, collision_rects):
                mob.draw(screen, state['camera_x'], state['camera_y'])
        
        for proj in state['solo_projectiles']:
            proj.draw(screen, state['camera_x'], state['camera_y'])
        
        for proj in state['solo_mob_projectiles']:
            if has_line_of_sight(px, py, proj.x, proj.y, collision_rects):
                proj.draw(screen, state['camera_x'], state['camera_y'])
        
        state['solo_player'].draw(screen, state['camera_x'], state['camera_y'], frame_index, player_sprites, attack_sprites)
        
        draw_fog_of_war(screen, state['camera_x'], state['camera_y'], tmx_data, px, py, collision_rects, view_radius=350)
        
        draw_player_ui(screen, state['solo_player'])
        
        debug = font.render(
            f"Collisions: {len(collision_rects)} | Mobs: {len(state['solo_mobs'])} | FPS: {int(clock.get_fps())} | F3:Collisions F4:Fog",
            True, (200, 200, 200)
        )
        screen.blit(debug, (10, height - 30))
    
    # ============================================================
    # МУЛЬТИПЛЕЕР
    # ============================================================
    elif cur == GameState.MULTIPLAYER:
        keys = pygame.key.get_pressed()
        if not state['chat_input_mode']:
            state['ws_queue'].put({
                'type': 'input',
                'left': bool(keys[pygame.K_a]), 'right': bool(keys[pygame.K_d]),
                'up': bool(keys[pygame.K_w]), 'down': bool(keys[pygame.K_s]),
                'attack': bool(keys[pygame.K_SPACE])
            })
        
        player_x, player_y = width // 2, height // 2
        if state['cid'] and state['cid'] in state['players']:
            player_x = state['players'][state['cid']]['x']
            player_y = state['players'][state['cid']]['y']
        
        state['camera_x'] = max(0, min(int(player_x - width // 2), map_width - width))
        state['camera_y'] = max(0, min(int(player_y - height // 2), map_height - height))
        
        draw_map(screen, state['camera_x'], state['camera_y'], tmx_data, collision_rects)
        
        if state['cid'] and state['cid'] in state['players']:
            pd = state['players'][state['cid']]
            sprite = None
            if player_sprites and pd.get('direction') in player_sprites:
                pdir = pd['direction']
                if pd.get('attacking') and attack_sprites.get(pdir):
                    sprite = attack_sprites[pdir][frame_index % len(attack_sprites[pdir])]
                elif pd.get('moving'):
                    sprite = player_sprites[pdir][frame_index % len(player_sprites[pdir])]
                else:
                    sprite = player_sprites[pdir][0]
            draw_entity(screen, player_x - state['camera_x'], player_y - state['camera_y'], (0, 255, 0), sprite=sprite)
        
        for pid, pos in state['players'].items():
            if pid != state['cid'] and has_line_of_sight(player_x, player_y, pos['x'], pos['y'], collision_rects):
                draw_entity(screen, pos['x'] - state['camera_x'], pos['y'] - state['camera_y'], (0, 0, 255))
        
        for mid, mob in state['mobs'].items():
            if has_line_of_sight(player_x, player_y, mob['x'], mob['y'], collision_rects):
                draw_square(screen, mob['x'] - state['camera_x'], mob['y'] - state['camera_y'], (255, 0, 0))
        
        draw_fog_of_war(screen, state['camera_x'], state['camera_y'], tmx_data, player_x, player_y, collision_rects, view_radius=350)
        
        if state['chat_input_mode'] or state['chat_history']:
            rect_w, rect_h, rect_x, rect_y = 400, 280, 10, height - 290
            chat_surf = pygame.Surface((rect_w, rect_h), pygame.SRCALPHA)
            chat_surf.fill((0, 0, 0, 150))
            screen.blit(chat_surf, (rect_x, rect_y))
            y_off = rect_y + 10
            for msg in state['chat_history'][-8:]:
                txt = msg.get('message', '') if isinstance(msg, dict) else str(msg)
                t = font.render(txt, True, (255, 255, 255))
                if y_off + t.get_height() > rect_y + rect_h - 30: break
                screen.blit(t, (rect_x + 10, y_off))
                y_off += 25
            if state['chat_input_mode']:
                inp_y = rect_y + rect_h - 30
                inp_surf = pygame.Surface((rect_w, 30), pygame.SRCALPHA)
                inp_surf.fill((0, 0, 0, 200))
                screen.blit(inp_surf, (rect_x, inp_y))
                screen.blit(font.render("> " + state['chat_input_text'], True, (255, 255, 0)), (rect_x + 10, inp_y + 5))
    
    pygame.display.flip()

pygame.quit()