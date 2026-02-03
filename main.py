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
parser.add_argument('--server', '-s', type=str, default='wss://league-of-adventures.onrender.com/ws', help='WebSocket URL сервера')
parser.add_argument('--windowed', '-w', action='store_true', help='Оконный режим')

args = parser.parse_args()

SERVER_URL = args.server

# Инициализация Pygame
pygame.init()
pygame.mixer.init()
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

# Переменные меню
menu = True
in_options = False  # Добавляем флаг для меню настроек
solo_time = False
solo_start_time = 0
pause_close_time = 0  # Добавляем переменную для учета времени паузы
change_time = 8000

theme = 'dark'

# Цвета
red = (255, 0, 0)
black = (0, 0, 0)



# Загрузка переключателей для настроек
toggles = []
toggles_rect = []
for i in range(3):
    try:
        toggle_image = 'on_toggle' + str(i) + '.png'
        toggle_file = os.path.join(PROJECT_DIR, 'images', toggle_image)
        image = pygame.transform.scale(pygame.image.load(toggle_file), (120, 70))
        image_rect = image.get_rect()
        toggles_rect.append(image_rect)
        toggles.append(image)
    except FileNotFoundError:
        print('Ошибка. Один из toggle не найден') 

off_toggles = []
off_toggles_rect = []
for i in range(3):
    try:
        off_toggle_image = 'off_toggle' + str(i) + '.png'
        off_toggle_file = os.path.join(PROJECT_DIR, 'images', off_toggle_image)
        image = pygame.transform.scale(pygame.image.load(off_toggle_file), (120, 70))
        image_rect = image.get_rect()
        off_toggles_rect.append(image_rect)
        off_toggles.append(image)
    except FileNotFoundError:
        print('Ошибка. Один из off_toggle не найден')

# Состояния переключателей (True = включен, False = выключен)
toggle_states = [False, False, False]

# Загрузка изображений для текстовой части игры
light_images = []
for i in range(1, 11):
    try:
        light_name_image = str(i) + '.png'
        light_image_file = os.path.join(PROJECT_DIR, 'images', 'light', light_name_image)
        light_image = pygame.transform.scale(pygame.image.load(light_image_file), screen.get_size())
        light_images.append(light_image)
    except FileNotFoundError:
        print('Ошибка. Файл light не найден')

dark_images = []
for i in range(1, 10):
    try:
        dark_name_image = str(i) + '.png'
        dark_image_file = os.path.join(PROJECT_DIR, 'images', 'dark', dark_name_image)
        dark_image = pygame.transform.scale(pygame.image.load(dark_image_file), screen.get_size())
        dark_images.append(dark_image)
    except FileNotFoundError:
        print('Ошибка. Файл dark не найден')

menu_music_file = os.path.join(PROJECT_DIR, 'music', 'menu.mp3')
try:
    menu_music = pygame.mixer.music.load(menu_music_file)
except FileNotFoundError:
    print('Ошибка. Файл "menu.mp3 не найден')

# Загрузка картинки главного меню
menu_file = os.path.join(PROJECT_DIR, 'images', 'меню.png')
try:
    menu_png = pygame.transform.scale(pygame.image.load(menu_file), screen.get_size())
except FileNotFoundError:
    print('Ошибка. Файл "меню.png" не найден')
    pygame.quit()
    sys.exit()

# Загрузка меню паузы 
pause_file = os.path.join(PROJECT_DIR, 'images', 'pause.jpg')
try:
    pause_png = pygame.transform.scale(pygame.image.load(pause_file), screen.get_size())
except FileNotFoundError:
    print('Ошибка. Файл "pause.png" не найден')
    pygame.quit()
    sys.exit()

# Загрузка картинки меню выхода
dark_quit_file = os.path.join(PROJECT_DIR, 'images', 'dark', 'quit_menu.jpg')
try:
    dark_quit_png = pygame.transform.scale(pygame.image.load(dark_quit_file), screen.get_size())
except FileNotFoundError:
    print('Ошибка. Файл "quit_menu.jpg" не найден.')
    pygame.quit()
    sys.exit()

# Загрузка картинки меню выхода
light_quit_file = os.path.join(PROJECT_DIR, 'images', 'light', 'quit_menu.jpg')
try:
    light_quit_png = pygame.transform.scale(pygame.image.load(light_quit_file), screen.get_size())
except FileNotFoundError:
    print('Ошибка. Файл "light_quit_menu.jpg" не найден.')
    pygame.quit()
    sys.exit()

# Загрузка заднего фона настроек
dark_settings_file = os.path.join(PROJECT_DIR, 'images', 'dark', 'settings_background.png')
try:
    dark_setting_png = pygame.transform.scale(pygame.image.load(dark_settings_file), screen.get_size())
except FileNotFoundError:
    print('Ошибка. Файл "settings_background.png" не найден.')
    pygame.quit()
    sys.exit()

# Загрузка заднего фона настроек
light_settings_file = os.path.join(PROJECT_DIR, 'images', 'light', 'settings_background.png')
try:
    light_setting_png = pygame.transform.scale(pygame.image.load(light_settings_file), screen.get_size())
except FileNotFoundError:
    print('Ошибка. Файл "settings_background.png" не найден.')
    pygame.quit()
    sys.exit()

# Создание кнопок главного меню
solo_play_button = pygame.Surface((300, 70), pygame.SRCALPHA)
solo_play_button.fill((0, 0, 0, 0))
solo_play_button_rect = solo_play_button.get_rect(topleft=(815, 605))

multi_play_button = pygame.Surface((300, 70), pygame.SRCALPHA)
multi_play_button.fill((0, 0, 0, 0))
multi_play_button_rect = multi_play_button.get_rect(topleft=(820, 720))

options_button = pygame.Surface((300, 70), pygame.SRCALPHA)
options_button.fill((0, 0, 0, 0))
options_button_rect = options_button.get_rect(topleft=(820, 820))

quit_button = pygame.Surface((270, 70), pygame.SRCALPHA)
quit_button.fill((0, 0, 0, 0))
quit_button_rect = quit_button.get_rect(topleft=(830, 920))

quit_yes_button = pygame.Surface((160, 65), pygame.SRCALPHA)
quit_yes_button.fill((0, 0, 0, 0))
quit_yes_button_rect = quit_yes_button.get_rect(topleft=(785, 590))

quit_no_button = pygame.Surface((160, 65), pygame.SRCALPHA)
quit_no_button.fill((0, 0, 0, 0))
quit_no_button_rect = quit_no_button.get_rect(topleft=(975, 590))

continue_solo_button = pygame.Surface((470, 130), pygame.SRCALPHA)
continue_solo_button.fill((0, 0, 0, 250))
continue_solo_button_rect = continue_solo_button.get_rect(topleft=(738, 516))

exit_to_menu_button = pygame.Surface((470, 130), pygame.SRCALPHA)
exit_to_menu_button.fill((0, 0, 0, 250))
exit_to_menu_button_rect = exit_to_menu_button.get_rect(topleft=(739, 687))

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
in_pause = False
image_counter = 0
in_quit = False

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

multi_play = False
chat = False
music_counter = 0

# Установка позиций для переключателей при инициализации
toggles_rect[0].topleft = (1277, 441)
toggles_rect[1].topleft = (1277, 576)
toggles_rect[2].topleft = (1277, 711)

off_toggles_rect[0].topleft = (1277, 441)
off_toggles_rect[1].topleft = (1277, 576)
off_toggles_rect[2].topleft = (1277, 711)

# Переменная для хранения времени начала паузы
pause_start_time = 0

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
                # Если мы в меню настроек, возвращаемся в главное меню
                if in_options:
                    in_options = False
                    menu = True
                
                if multi_play:
                    multi_play = False
                    menu = True
                    screen.fill(black)
                    
                elif solo_time and not in_pause:
                    solo_time = False
                    in_pause = True
                    pause_start_time = pygame.time.get_ticks()
                elif in_pause:
                    # Если уже в паузе, нажатие ESC выходит из паузы
                    in_pause = False
                    solo_time = True
                    pause_close_time += pygame.time.get_ticks() - pause_start_time
                
            
            if event.key == pygame.K_t and not chat_input_mode:  # T for chat
                chat_input_mode = not chat_input_mode
                print(f"chat_input_mode: {chat_input_mode}")
                if chat_input_mode:
                    chat_input_text = ""
            elif event.type == pygame.KEYDOWN and chat_input_mode:
                if chat_input_mode:
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

        if event.type == pygame.MOUSEBUTTONDOWN: 
            x, y = event.pos
            print(f"Click at: {x}, {y}")
            
            if menu:    
                if solo_play_button_rect.collidepoint(x, y):
                    menu = False
                    in_options = False
                    multi_play = False
                    solo_time = True
                    solo_start_time = pygame.time.get_ticks()
                    pause_close_time = 0
                    screen.fill(black)
                    if theme == 'dark':
                        screen.blit(dark_images[0], (0, 0))
                    else:
                        screen.blit(light_images[0], (0, 0))
              
                elif multi_play_button_rect.collidepoint(event.pos):
                    multi_play = True
                    menu = False
                    solo_time = False

                # Обработка нажатий на кнопку настроек
                elif options_button_rect.collidepoint(event.pos):
                    menu = False
                    in_options = True
                    screen.fill(black)
                    if theme == 'light':
                        screen.blit(light_setting_png, (0, 0))
                        print(f'theme = {theme}')
                    elif theme == 'dark':
                        print(f'theme = {theme}')
                        screen.blit(dark_setting_png, (0, 0))
                    # Рисуем переключатели в соответствии с их состояниями
                    for i in range(3):
                        if toggle_states[i]:
                            theme = 'light'
                            screen.blit(toggles[i], toggles_rect[i])
                        else:
                            screen.blit(off_toggles[i], off_toggles_rect[i])
    

                # Обработка нажатий на кнопку выхода 
                elif quit_button_rect.collidepoint(event.pos):
                    in_quit = True
                    menu = False
                    if theme == 'dark':
                        screen.blit(dark_quit_png, (0, 0))
                    elif theme == 'light':
                        screen.blit(light_quit_png, (0, 0))
                    screen.blit(quit_yes_button, quit_yes_button_rect)
                    screen.blit(quit_no_button, quit_no_button_rect)

            if in_pause:
                if exit_to_menu_button_rect.collidepoint(event.pos):
                    in_pause = False
                    solo_time = False
                    menu = True
                    continue

                if continue_solo_button_rect.collidepoint(event.pos):
                    in_pause = False
                    solo_time = True
                    pause_close_time += pygame.time.get_ticks() - pause_start_time
                    print('Пауза снята, продолжаем играть')
                    continue
            
            # Обработка нажатий в меню настроек
            if in_options:
                # Проверяем нажатия на все переключатели
                for i in range(3):
                    if toggles_rect[i].collidepoint(event.pos) or off_toggles_rect[i].collidepoint(event.pos):
                        toggle_states[i] = not toggle_states[i]
                        if toggle_states[0]:
                            pygame.mixer.music.play()
                        elif not toggle_states[0]:
                            pygame.mixer.music.stop()
                        print(f"Toggle {i} changed to: {toggle_states[i]}")
                        # Перерисовываем экран настроек
                        screen.fill(black)
                        # Определяем текущую тему для фона
                        current_theme = 'light' if toggle_states[2] else 'dark'
                        if current_theme == 'light':
                            theme = 'light'
                            screen.blit(light_setting_png, (0, 0))
                        else:
                            theme = 'dark'
                            screen.blit(dark_setting_png, (0, 0))
                        
                        # Рисуем все переключатели
                        for j in range(3):   
                            if toggle_states[j]:
                                screen.blit(toggles[j], toggles_rect[j])
                            else:
                                screen.blit(off_toggles[j], off_toggles_rect[j])
                        break
            
            # Обработка нажатий на кнопку подтверждения выхода
            if in_quit:
                if quit_yes_button_rect.collidepoint(event.pos):
                    running = False
                
                # Обработка нажатий на кнопку отказа от выхода
                if quit_no_button_rect.collidepoint(event.pos):
                    menu = True
                    in_quit = False

    # Отрисовка меню паузы
    if in_pause:
        screen.blit(pause_png, (0, 0))
        screen.blit(exit_to_menu_button, exit_to_menu_button_rect)
        screen.blit(continue_solo_button, continue_solo_button_rect)
        pygame.display.flip()
        continue  # Пропускаем остальную отрисовку

    # Смена картинок по кд
    if solo_time:
        if theme == 'dark':
            elapsed = pygame.time.get_ticks() - solo_start_time - pause_close_time
            # Отображаем соответствующую картинку в зависимости от прошедшего времени
            if elapsed < change_time:
                screen.blit(dark_images[0], (0, 0))
            elif elapsed < change_time + 8000:
                screen.blit(dark_images[1], (0, 0))
            elif elapsed < change_time + 16000:
                screen.blit(dark_images[2], (0, 0))
            elif elapsed < change_time + 24000:
                screen.blit(dark_images[3], (0, 0))
            elif elapsed < change_time + 32000:
                screen.blit(dark_images[4], (0, 0))
            elif elapsed < change_time + 40000:
                screen.blit(dark_images[5], (0, 0))
            elif elapsed < change_time + 48000:
                screen.blit(dark_images[6], (0, 0))
            elif elapsed < change_time + 56000:
                screen.blit(dark_images[7], (0, 0))
            elif elapsed < change_time + 64000:
                screen.blit(dark_images[8], (0, 0))
            else:
                screen.blit(dark_images[9], (0, 0))
        
        if theme == 'light':
            elapsed = pygame.time.get_ticks() - solo_start_time - pause_close_time
            if elapsed < change_time:
                screen.blit(light_images[0], (0, 0))
            elif elapsed < change_time + 8000:
                screen.blit(light_images[1], (0, 0))
            elif elapsed < change_time + 16000:
                screen.blit(light_images[2], (0, 0))
            elif elapsed < change_time + 24000:
                screen.blit(light_images[3], (0, 0))
            elif elapsed < change_time + 32000:
                screen.blit(light_images[4], (0, 0))
            elif elapsed < change_time + 40000:
                screen.blit(light_images[5], (0, 0))
            elif elapsed < change_time + 48000:
                screen.blit(light_images[6], (0, 0))
            elif elapsed < change_time + 56000:
                screen.blit(light_images[7], (0, 0))
            elif elapsed < change_time + 64000:
                screen.blit(light_images[8], (0, 0))
            elif elapsed < change_time + 72000:
                screen.blit(light_images[9], (0, 0))
            else:
                screen.blit(light_images[10] if len(light_images) > 10 else light_images[9], (0, 0))
        
        # Обновляем экран для solo_time
        pygame.display.flip()

    if multi_play:
        if cid and cid in players:
            player_x = players[cid]['x']
            player_y = players[cid]['y']
            camera_x = max(0, min(player_x - (width // 2), map_width - width))
            camera_y = max(0, min(player_y - (height // 2), map_height - height))

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
            if chat_input_mode:
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

    if not chat_input_mode and not menu and not solo_time and not in_options and not in_pause and not in_quit:
        # Send inputs
        keys = pygame.key.get_pressed()
        inputs = {
            'type': 'input',
            'left': keys[pygame.K_a],
            'right': keys[pygame.K_d],
            'up': keys[pygame.K_w],
            'down': keys[pygame.K_s],
            'attack': keys[pygame.K_SPACE]
        }
        if ws and ws.sock and ws.sock.connected:
            try:
                ws.send(json.dumps(inputs))
            except Exception as e:
                print(f"Send error: {e}")

    # Отрисовка главного меню
    if menu:
        screen.fill((250, 250, 250))
        screen.blit(menu_png, (0, 0))
        screen.blit(multi_play_button, multi_play_button_rect)
        screen.blit(options_button, options_button_rect)
        screen.blit(quit_button, quit_button_rect)
        screen.blit(solo_play_button, solo_play_button_rect)
        pygame.display.flip()
    
    # Отрисовка меню выхода
    if in_quit:
        if theme == 'dark':
            screen.blit(dark_quit_png, (0, 0))
        elif theme == 'light':
            screen.blit(light_quit_png, (0, 0))
        screen.blit(quit_yes_button, quit_yes_button_rect)
        screen.blit(quit_no_button, quit_no_button_rect)
        pygame.display.flip()

    pygame.display.flip()

if ws:
    ws.close()
pygame.quit()