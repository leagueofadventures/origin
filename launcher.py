import tkinter as tk
from tkinter import messagebox, ttk
import requests
import json
import subprocess
import os
import sys
import hashlib
import threading
import zipfile
import tempfile
import shutil
from pathlib import Path

# Настройки сервера
SERVER_HOST = "https://league-of-adventures.onrender.com"
CLIENT_VERSION = "1.0.0"  # Будет обновляться автоматически
UPDATE_CHECK_TIMEOUT = 10
DOWNLOAD_TIMEOUT = 30

class Launcher:
    def __init__(self, root):
        self.root = root
        self.root.title("League of adventures - Launcher")
        self.root.geometry("450x400")
        self.root.resizable(True, True)
        
        # Центрирование окна
        self.center_window()
        
        # Переменные
        self.token = None
        self.username = tk.StringVar()
        self.password = tk.StringVar()
        self.is_downloading = False
        self.download_thread = None
        self.server_version = CLIENT_VERSION
        
        # Создание виджетов
        self.create_widgets()
        
        # Проверка обновлений при запуске
        self.root.after(1000, self.auto_check_updates)

    def center_window(self):
        """Центрирует окно на экране"""
        self.root.update_idletasks()
        width = self.root.winfo_width()
        height = self.root.winfo_height()
        x = (self.root.winfo_screenwidth() // 2) - (width // 2)
        y = (self.root.winfo_screenheight() // 2) - (height // 2)
        self.root.geometry(f'450x400+{x}+{y}')

    def create_widgets(self):
        # Основной фрейм
        main_frame = tk.Frame(self.root, padx=20, pady=20)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Заголовок
        title_label = tk.Label(main_frame, text="League of adventures", 
                              font=("Arial", 18, "bold"), fg="#2E86AB")
        title_label.pack(pady=10)
        
        # Версия
        self.version_label = tk.Label(main_frame, text=f"Версия клиента: {CLIENT_VERSION}", 
                                    font=("Arial", 10), fg="#666")
        self.version_label.pack(pady=5)
        
        # Статус сервера
        self.server_version_label = tk.Label(main_frame, text="Версия сервера: проверка...", 
                                           font=("Arial", 9), fg="#666")
        self.server_version_label.pack(pady=2)

        # Поля ввода
        input_frame = tk.Frame(main_frame)
        input_frame.pack(pady=20, fill=tk.X)

        tk.Label(input_frame, text="Логин:", font=("Arial", 10)).grid(row=0, column=0, sticky="w", padx=5, pady=8)
        self.username_entry = tk.Entry(input_frame, textvariable=self.username, width=25, font=("Arial", 10))
        self.username_entry.grid(row=0, column=1, padx=5, pady=8, sticky="ew")
        self.username_entry.bind('<Return>', lambda e: self.login())

        tk.Label(input_frame, text="Пароль:", font=("Arial", 10)).grid(row=1, column=0, sticky="w", padx=5, pady=8)
        self.password_entry = tk.Entry(input_frame, textvariable=self.password, show="*", width=25, font=("Arial", 10))
        self.password_entry.grid(row=1, column=1, padx=5, pady=8, sticky="ew")
        self.password_entry.bind('<Return>', lambda e: self.login())
        
        input_frame.columnconfigure(1, weight=1)

        # Кнопки
        button_frame = tk.Frame(main_frame)
        button_frame.pack(pady=15)

        self.login_button = tk.Button(button_frame, text="Войти", command=self.login,
                                     bg="#27AE60", fg="white", font=("Arial", 10, "bold"),
                                     width=12, height=1)
        self.login_button.grid(row=0, column=0, padx=5)

        self.register_button = tk.Button(button_frame, text="Регистрация", command=self.register,
                                        bg="#3498DB", fg="white", font=("Arial", 10, "bold"),
                                        width=12, height=1)
        self.register_button.grid(row=0, column=1, padx=5)

        # Кнопка выхода
        self.exit_button = tk.Button(button_frame, text="Выход", command=self.safe_exit,
                                    bg="#E74C3C", fg="white", font=("Arial", 10, "bold"),
                                    width=12, height=1)
        self.exit_button.grid(row=0, column=2, padx=5)

        # Прогресс-бар для обновлений
        self.progress_frame = tk.Frame(main_frame)
        self.progress_frame.pack(pady=10, fill="x")
        
        self.progress_label = tk.Label(self.progress_frame, text="", font=("Arial", 9))
        self.progress_label.pack(pady=2)
        
        self.progress = ttk.Progressbar(self.progress_frame, orient="horizontal", 
                                       length=350, mode="determinate")
        self.progress.pack(pady=2, fill="x")
        
        self.progress_percent = tk.Label(self.progress_frame, text="", font=("Arial", 9))
        self.progress_percent.pack(pady=2)
        
        self.hide_progress()

        # Статус
        self.status_label = tk.Label(main_frame, text="Готов к работе", 
                                    font=("Arial", 9), fg="#666", wraplength=400)
        self.status_label.pack(pady=10)
                      
        # Информация об обновлениях 
        self.update_info_label = tk.Label(main_frame, text="", font=("Arial", 8), fg="#888")
        self.update_info_label.pack(pady=5)

        # Бинд для закрытия окна
        self.root.protocol("WM_DELETE_WINDOW", self.safe_exit)

    def hide_progress(self):
        """Скрывает элементы прогресса"""
        self.progress_frame.pack_forget()

    def show_progress(self):
        """Показывает элементы прогресса"""
        self.progress_frame.pack(pady=10, fill="x")

    def safe_exit(self):
        """Безопасный выход с проверкой загрузок"""
        if self.is_downloading:
            if not messagebox.askyesno("Выход", "Идет загрузка обновления. Прервать и выйти?"):
                return
        self.root.quit()
        self.root.destroy()

    def update_status(self, message, is_error=False):
        """Обновляет статус с цветом"""
        color = "#E74C3C" if is_error else "#27AE60"
        self.status_label.config(text=message, fg=color)
        self.root.update_idletasks()

    def update_server_info(self, version, has_update=False):
        """Обновляет информацию о сервере"""
        if has_update:
            self.server_version_label.config(
                text=f"Версия сервера: {version} (доступно обновление!)", 
                fg="#E74C3C"
            )
        else:
            self.server_version_label.config(
                text=f"Версия сервера: {version}", 
                fg="#27AE60"
            )

    def auto_check_updates(self):
        """Автоматическая проверка обновлений при запуске"""
        def check():
            try:
                response = requests.get(
                    f"{SERVER_HOST}/check_update?version={CLIENT_VERSION}",
                    timeout=UPDATE_CHECK_TIMEOUT
                )
                if response.status_code == 200:
                    update_info = response.json()
                    self.server_version = update_info.get('latest_version', CLIENT_VERSION)
                    has_update = update_info.get('update_available', False)
                    
                    self.root.after(0, lambda: self.update_server_info(
                        self.server_version, has_update
                    ))
                    
                    if has_update:
                        self.root.after(0, lambda: self.update_info_label.config(
                            text=f"Доступна новая версия {self.server_version}",
                            fg="#E74C3C"
                        ))
            except Exception as e:
                print(f"Автопроверка обновлений: {e}")
                self.root.after(0, lambda: self.server_version_label.config(
                    text="Сервер: недоступен", 
                    fg="#E74C3C"
                ))

        threading.Thread(target=check, daemon=True).start()

    def login(self):
        if self.is_downloading:
            messagebox.showwarning("Внимание", "Дождитесь завершения загрузки")
            return

        username = self.username.get().strip()
        password = self.password.get()

        if not username or not password:
            messagebox.showerror("Ошибка", "Введите логин и пароль")
            return

        self.set_buttons_state(False)
        self.update_status("Выполняется вход...")

        def do_login():
            try:
                response = requests.post(
                    f"{SERVER_HOST}/login",
                    json={"username": username, "password": password},
                    timeout=UPDATE_CHECK_TIMEOUT
                )
                
                if response.status_code == 200:
                    data = response.json()
                    if data.get("success"):
                        self.token = data["token"]
                        self.root.after(0, lambda: self.update_status("Вход успешен. Проверка обновлений..."))
                        self.root.after(0, self.check_updates)
                    else:
                        self.root.after(0, lambda: messagebox.showerror(
                            "Ошибка", 
                            data.get("message", "Ошибка входа")
                        ))
                        self.root.after(0, lambda: self.update_status("Ошибка входа", True))
                else:
                    self.root.after(0, lambda: messagebox.showerror(
                        "Ошибка", 
                        f"Ошибка сервера: {response.status_code}"
                    ))
                    self.root.after(0, lambda: self.update_status("Ошибка сервера", True))
                    
            except requests.exceptions.Timeout:
                self.root.after(0, lambda: messagebox.showerror(
                    "Ошибка", 
                    "Таймаут подключения к серверу"
                ))
                self.root.after(0, lambda: self.update_status("Сервер недоступен", True))
            except requests.exceptions.ConnectionError:
                self.root.after(0, lambda: messagebox.showerror(
                    "Ошибка", 
                    "Не удалось подключиться к серверу"
                ))
                self.root.after(0, lambda: self.update_status("Нет подключения", True))
            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror(
                    "Ошибка", 
                    f"Неизвестная ошибка: {e}"
                ))
                self.root.after(0, lambda: self.update_status("Ошибка подключения", True))
            finally:
                self.root.after(0, lambda: self.set_buttons_state(True))

        threading.Thread(target=do_login, daemon=True).start()

    def register(self):
        if self.is_downloading:
            return

        username = self.username.get().strip()
        password = self.password.get()

        if not username or not password:
            messagebox.showerror("Ошибка", "Введите логин и пароль")
            return

        if len(username) < 3:
            messagebox.showerror("Ошибка", "Логин должен содержать минимум 3 символа")
            return

        if len(password) < 4:
            messagebox.showerror("Ошибка", "Пароль должен содержать минимум 4 символа")
            return

        self.set_buttons_state(False)
        self.update_status("Регистрация...")

        def do_register():
            try:
                response = requests.post(
                    f"{SERVER_HOST}/register",
                    json={"username": username, "password": password},
                    timeout=UPDATE_CHECK_TIMEOUT
                )
                
                if response.status_code == 200:
                    data = response.json()
                    if data.get("success"):
                        self.root.after(0, lambda: messagebox.showinfo(
                            "Успех", 
                            "Регистрация успешна. Теперь войдите."
                        ))
                        self.root.after(0, lambda: self.update_status("Регистрация успешна"))
                    else:
                        self.root.after(0, lambda: messagebox.showerror(
                            "Ошибка", 
                            data.get("message", "Ошибка регистрации")
                        ))
                        self.root.after(0, lambda: self.update_status("Ошибка регистрации", True))
                elif response.status_code == 409:
                    self.root.after(0, lambda: messagebox.showerror(
                        "Ошибка", 
                        "Имя пользователя уже существует"
                    ))
                    self.root.after(0, lambda: self.update_status("Логин занят", True))
                else:
                    self.root.after(0, lambda: messagebox.showerror(
                        "Ошибка", 
                        f"Ошибка сервера: {response.status_code}"
                    ))
                    self.root.after(0, lambda: self.update_status("Ошибка сервера", True))
                    
            except requests.exceptions.Timeout:
                self.root.after(0, lambda: messagebox.showerror(
                    "Ошибка", 
                    "Таймаут подключения к серверу"
                ))
                self.root.after(0, lambda: self.update_status("Сервер недоступен", True))
            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror(
                    "Ошибка", 
                    f"Ошибка подключения: {e}"
                ))
                self.root.after(0, lambda: self.update_status("Ошибка подключения", True))
            finally:
                self.root.after(0, lambda: self.set_buttons_state(True))

        threading.Thread(target=do_register, daemon=True).start()

    def check_updates(self):
        """Проверяет наличие обновлений"""
        self.update_status("Проверка обновлений...")
        
        def do_check():
            try:
                response = requests.get(
                    f"{SERVER_HOST}/check_update?version={CLIENT_VERSION}",
                    timeout=UPDATE_CHECK_TIMEOUT
                )
                
                if response.status_code == 200:
                    update_info = response.json()
                    self.root.after(0, lambda: self.handle_update_check(update_info))
                else:
                    self.root.after(0, lambda: self.update_status("Сервер недоступен, запуск игры..."))
                    self.root.after(0, self.launch_game)
                    
            except Exception as e:
                print(f"Ошибка проверки обновлений: {e}")
                self.root.after(0, lambda: self.update_status("Не удалось проверить обновления, запуск игры..."))
                self.root.after(0, self.launch_game)

        threading.Thread(target=do_check, daemon=True).start()

    def handle_update_check(self, update_info):
        """Обрабатывает результат проверки обновлений"""
        if update_info.get("update_available"):
            latest_version = update_info.get("latest_version", "неизвестно")
            
            # Обновляем информацию о сервере
            self.root.after(0, lambda: self.update_server_info(latest_version, True))
            
            if messagebox.askyesno(
                "Доступно обновление", 
                f"Доступна версия {latest_version} (у вас {CLIENT_VERSION}).\n"
                f"Хотите обновиться перед запуском игры?"
            ):
                self.download_update(update_info)
            else:
                self.launch_game()
        else:
            self.root.after(0, lambda: self.update_server_info(
                update_info.get("latest_version", CLIENT_VERSION), False
            ))
            self.update_status("Обновлений не требуется")
            self.launch_game()

    def download_update(self, update_info):
        """Скачивает и устанавливает обновление"""
        if self.is_downloading:
            return

        self.is_downloading = True
        self.set_buttons_state(False)
        self.show_progress()
        
        self.progress["value"] = 0
        self.progress_label.config(text="Подготовка к загрузке...")
        self.progress_percent.config(text="0%")

        def do_download():
            temp_dir = None
            try:
                # Создаем временную директорию
                temp_dir = tempfile.mkdtemp()
                update_zip = os.path.join(temp_dir, "update.zip")
                
                # Загрузка файла
                self.root.after(0, lambda: self.progress_label.config(text="Скачивание обновления..."))
                
                response = requests.get(
                    f"{SERVER_HOST}/download_update", 
                    stream=True,
                    timeout=DOWNLOAD_TIMEOUT
                )
                
                if response.status_code != 200:
                    raise Exception(f"HTTP {response.status_code}")
                
                total_size = int(response.headers.get('content-length', 0))
                downloaded = 0
                
                with open(update_zip, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if not self.is_downloading:  # Проверка отмены
                            break
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)
                            if total_size > 0:
                                percent = (downloaded / total_size) * 100
                                self.root.after(0, lambda: self.update_progress(
                                    percent, 
                                    f"Скачивание: {downloaded//1024}KB / {total_size//1024}KB"
                                ))

                if not self.is_downloading:
                    return

                # Распаковка
                self.root.after(0, lambda: self.progress_label.config(text="Распаковка обновления..."))
                self.root.after(0, lambda: self.progress_percent.config(text=""))
                
                with zipfile.ZipFile(update_zip, 'r') as zip_ref:
                    zip_ref.extractall(".")
                
                # Обновление завершено
                self.root.after(0, lambda: self.update_status("Обновление завершено!"))
                self.root.after(0, self.launch_game)
                
            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror(
                    "Ошибка обновления", 
                    f"Не удалось установить обновление: {e}"
                ))
                self.root.after(0, lambda: self.update_status("Ошибка обновления", True))
                self.root.after(0, self.launch_game)  # Запускаем игру даже при ошибке
            finally:
                # Очистка
                if temp_dir and os.path.exists(temp_dir):
                    try:
                        shutil.rmtree(temp_dir)
                    except:
                        pass
                self.is_downloading = False
                self.root.after(0, lambda: self.set_buttons_state(True))
                self.root.after(0, self.hide_progress)

        self.download_thread = threading.Thread(target=do_download, daemon=True)
        self.download_thread.start()

    def update_progress(self, value, text):
        """Обновляет прогресс-бар"""
        self.progress["value"] = value
        self.progress_label.config(text=text)
        self.progress_percent.config(text=f"{int(value)}%")

    def launch_game(self):
        """Запускает игру"""
        self.update_status("Запуск игры...")
        
        try:
            # Проверяем существование main.py
            script_dir = os.path.dirname(os.path.abspath(__file__))
            game_path = os.path.join(script_dir, "main.py")
            
            if not os.path.exists(game_path):
                messagebox.showerror("Ошибка", f"Файл игры не найден: {game_path}")
                self.update_status("Файл игры не найден", True)
                return

            # Подготавливаем окружение
            env = os.environ.copy()
            if self.token:
                env["GAME_TOKEN"] = self.token
            
            # Запускаем игру
            subprocess.Popen([
                sys.executable, 
                game_path, 
                "--server", 
                SERVER_HOST.replace("https://", "wss://").replace("http://", "ws://") + "/ws"
            ], env=env)
            
            self.update_status("Игра запущена!")
            
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось запустить игру: {e}")
            self.update_status("Ошибка запуска", True)

    def set_buttons_state(self, enabled):
        """Включает/отключает кнопки"""
        state = "normal" if enabled else "disabled"
        self.login_button.config(state=state)
        self.register_button.config(state=state)
        self.exit_button.config(state=state)

if __name__ == "__main__":
  
        
        
    root = tk.Tk()
    launcher = Launcher(root)
    root.mainloop()
