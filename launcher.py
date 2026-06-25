import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import requests
import json
import os
import sys
import subprocess
import threading
import hashlib
from pathlib import Path

class GameLauncher:
    def __init__(self, root):
        self.root = root
        self.root.title("League of Adventures - Launcher")
        self.root.geometry("650x600")
        self.root.resizable(True, True)
        
        # Конфигурация
        self.current_version = "1.0.0"
        self.update_zip_path = "update.zip"
        self.game_exe = "game.exe" if sys.platform == "win32" else "python"
        self.game_script = "main.py"
        self.token_file = "auth_token.txt"
        self.config_file = "launcher_config.json"
        self.token = None
        
        # Пресеты серверов (потому что хардкодить URL — это моветон)
        self.server_presets = {
            "🌐 Render (Production)": "wss://leagueofadventures.onrender.com/ws",
            "🏠 Локальный (localhost)": "ws://localhost:8080/ws",
            "🔧 Локальный (127.0.0.1)": "ws://127.0.0.1:8080/ws",
            "✏️ Свой сервер": ""
        }
        
        self.setup_ui()
        self.load_config()
        self.load_saved_token()
        
    def setup_ui(self):
        # Заголовок
        title_frame = tk.Frame(self.root, bg="#2c3e50", height=80)
        title_frame.pack(fill=tk.X)
        title_frame.pack_propagate(False)
        
        title_label = tk.Label(
            title_frame, 
            text="⚔️ LEAGUE OF ADVENTURES ⚔️",
            font=("Arial", 24, "bold"),
            fg="#ecf0f1",
            bg="#2c3e50"
        )
        title_label.pack(pady=20)
        
        # Основная область
        main_frame = tk.Frame(self.root, bg="#34495e")
        main_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        # === БЛОК ВЫБОРА СЕРВЕРА ===
        server_frame = tk.LabelFrame(
            main_frame, 
            text="🌍 Выбор сервера",
            font=("Arial", 11, "bold"),
            fg="#ecf0f1",
            bg="#34495e",
            bd=2
        )
        server_frame.pack(fill=tk.X, pady=10)
        
        # Выпадающий список с пресетами
        preset_frame = tk.Frame(server_frame, bg="#34495e")
        preset_frame.pack(fill=tk.X, padx=10, pady=5)
        
        tk.Label(
            preset_frame,
            text="Пресет:",
            font=("Arial", 10),
            fg="#ecf0f1",
            bg="#34495e",
            width=10,
            anchor=tk.W
        ).pack(side=tk.LEFT)
        
        self.server_preset_var = tk.StringVar()
        self.server_preset_combo = ttk.Combobox(
            preset_frame,
            textvariable=self.server_preset_var,
            values=list(self.server_presets.keys()),
            state="readonly",
            width=30,
            font=("Arial", 10)
        )
        self.server_preset_combo.pack(side=tk.LEFT, padx=5)
        self.server_preset_combo.bind("<<ComboboxSelected>>", self.on_preset_selected)
        
        # Поле для ручного ввода URL
        url_frame = tk.Frame(server_frame, bg="#34495e")
        url_frame.pack(fill=tk.X, padx=10, pady=5)
        
        tk.Label(
            url_frame,
            text="URL:",
            font=("Arial", 10),
            fg="#ecf0f1",
            bg="#34495e",
            width=10,
            anchor=tk.W
        ).pack(side=tk.LEFT)
        
        self.server_url_var = tk.StringVar()
        self.server_url_entry = tk.Entry(
            url_frame,
            textvariable=self.server_url_var,
            font=("Consolas", 10),
            bg="#2c3e50",
            fg="#ecf0f1",
            insertbackground="#ecf0f1",
            relief=tk.FLAT,
            bd=2
        )
        self.server_url_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        
        # Индикатор статуса сервера
        self.server_status = tk.Label(
            server_frame,
            text="● Статус: не проверено",
            font=("Arial", 9),
            fg="#f39c12",
            bg="#34495e"
        )
        self.server_status.pack(padx=10, pady=5, anchor=tk.W)
        
        # Кнопка проверки сервера
        self.check_server_btn = tk.Button(
            server_frame,
            text="🔍 Проверить соединение",
            font=("Arial", 9, "bold"),
            bg="#3498db",
            fg="white",
            relief=tk.FLAT,
            cursor="hand2",
            command=self.check_server_connection
        )
        self.check_server_btn.pack(padx=10, pady=5, anchor=tk.W)
        
        # === ОСТАЛЬНЫЕ ЭЛЕМЕНТЫ ===
        
        # Информация о версии
        version_frame = tk.Frame(main_frame, bg="#34495e")
        version_frame.pack(fill=tk.X, pady=10)
        
        self.version_label = tk.Label(
            version_frame,
            text=f"Текущая версия: {self.current_version}",
            font=("Arial", 11),
            fg="#ecf0f1",
            bg="#34495e"
        )
        self.version_label.pack(side=tk.LEFT)
        
        self.status_label = tk.Label(
            version_frame,
            text="Готов к запуску",
            font=("Arial", 10),
            fg="#2ecc71",
            bg="#34495e"
        )
        self.status_label.pack(side=tk.RIGHT)
        
        # Прогресс-бар
        self.progress_frame = tk.Frame(main_frame, bg="#34495e")
        self.progress_frame.pack(fill=tk.X, pady=10)
        
        self.progress_bar = ttk.Progressbar(
            self.progress_frame,
            orient=tk.HORIZONTAL,
            length=610,
            mode='determinate'
        )
        self.progress_bar.pack(fill=tk.X)
        
        self.progress_label = tk.Label(
            self.progress_frame,
            text="",
            font=("Arial", 9),
            fg="#bdc3c7",
            bg="#34495e"
        )
        self.progress_label.pack(pady=5)
        
        # Лог
        log_frame = tk.Frame(main_frame, bg="#34495e")
        log_frame.pack(fill=tk.BOTH, expand=True, pady=10)
        
        tk.Label(
            log_frame,
            text="Лог:",
            font=("Arial", 10, "bold"),
            fg="#ecf0f1",
            bg="#34495e"
        ).pack(anchor=tk.W)
        
        self.log_text = scrolledtext.ScrolledText(
            log_frame,
            height=8,
            font=("Consolas", 9),
            bg="#2c3e50",
            fg="#ecf0f1",
            state=tk.DISABLED
        )
        self.log_text.pack(fill=tk.BOTH, expand=True, pady=5)
        
        # Кнопки
        button_frame = tk.Frame(main_frame, bg="#34495e")
        button_frame.pack(fill=tk.X, pady=10)
        
        self.check_update_btn = tk.Button(
            button_frame,
            text="🔄 Обновления",
            font=("Arial", 11, "bold"),
            bg="#3498db",
            fg="white",
            relief=tk.FLAT,
            cursor="hand2",
            command=self.check_updates
        )
        self.check_update_btn.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        
        self.play_btn = tk.Button(
            button_frame,
            text="▶️ ИГРАТЬ",
            font=("Arial", 12, "bold"),
            bg="#2ecc71",
            fg="white",
            relief=tk.FLAT,
            cursor="hand2",
            command=self.launch_game
        )
        self.play_btn.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        
        # Статус-бар
        status_bar = tk.Frame(self.root, bg="#2c3e50", height=30)
        status_bar.pack(fill=tk.X, side=tk.BOTTOM)
        status_bar.pack_propagate(False)
        
        self.connection_status = tk.Label(
            status_bar,
            text="● Сервер: не выбран",
            font=("Arial", 9),
            fg="#f39c12",
            bg="#2c3e50"
        )
        self.connection_status.pack(side=tk.LEFT, padx=10, pady=5)
        
    def on_preset_selected(self, event):
        """Обработка выбора пресета сервера"""
        selected = self.server_preset_var.get()
        if selected in self.server_presets:
            url = self.server_presets[selected]
            self.server_url_var.set(url)
            self.log(f"Выбран пресет: {selected}")
            
            # Блокируем редактирование, если не "Свой сервер"
            if selected == "✏️ Свой сервер":
                self.server_url_entry.config(state=tk.NORMAL)
            else:
                self.server_url_entry.config(state=tk.NORMAL)  # Всегда разрешаем редактировать
            
            # Сбрасываем статус
            self.server_status.config(text="● Статус: не проверено", fg="#f39c12")
            self.connection_status.config(text="● Сервер: не проверен", fg="#f39c12")
            
            # Автосохранение
            self.save_config()
    
    def get_server_url(self):
        """Получение текущего URL сервера"""
        url = self.server_url_var.get().strip()
        if not url:
            return None
        
        # Конвертируем ws:// в http:// для REST-запросов
        if url.startswith("wss://"):
            return url.replace("wss://", "https://").replace("/ws", "")
        elif url.startswith("ws://"):
            return url.replace("ws://", "http://").replace("/ws", "")
        
        return url
    
    def check_server_connection(self):
        """Проверка соединения с сервером"""
        url = self.get_server_url()
        if not url:
            messagebox.showwarning("Внимание", "Укажите URL сервера!")
            return
        
        self.check_server_btn.config(state=tk.DISABLED)
        self.server_status.config(text="● Статус: проверка...", fg="#f39c12")
        self.connection_status.config(text="● Сервер: проверка...", fg="#f39c12")
        self.log(f"Проверка соединения с {url}...")
        
        def check():
            try:
                response = requests.get(f"{url}/", timeout=5)
                if response.status_code == 200:
                    self.server_status.config(text="● Статус: онлайн ✓", fg="#2ecc71")
                    self.connection_status.config(text="● Сервер: онлайн ✓", fg="#2ecc71")
                    self.log("Сервер доступен и отвечает")
                else:
                    self.server_status.config(text=f"● Статус: код {response.status_code}", fg="#e74c3c")
                    self.connection_status.config(text="● Сервер: проблемы", fg="#e74c3c")
                    self.log(f"Сервер вернул статус {response.status_code}")
            except requests.exceptions.Timeout:
                self.server_status.config(text="● Статус: таймаут", fg="#e74c3c")
                self.connection_status.config(text="● Сервер: таймаут", fg="#e74c3c")
                self.log("Сервер не отвечает (таймаут)")
            except requests.exceptions.ConnectionError:
                self.server_status.config(text="● Статус: нет соединения", fg="#e74c3c")
                self.connection_status.config(text="● Сервер: недоступен", fg="#e74c3c")
                self.log("Не удалось подключиться к серверу")
            except Exception as e:
                self.server_status.config(text="● Статус: ошибка", fg="#e74c3c")
                self.connection_status.config(text="● Сервер: ошибка", fg="#e74c3c")
                self.log(f"Ошибка проверки: {e}")
            finally:
                self.check_server_btn.config(state=tk.NORMAL)
        
        threading.Thread(target=check, daemon=True).start()
    
    def save_config(self):
        """Сохранение конфигурации лаунчера"""
        try:
            config = {
                "server_preset": self.server_preset_var.get(),
                "server_url": self.server_url_var.get(),
                "current_version": self.current_version
            }
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
        except Exception as e:
            self.log(f"Ошибка сохранения конфига: {e}")
    
    def load_config(self):
        """Загрузка конфигурации лаунчера"""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                
                preset = config.get("server_preset", "🌐 Render (Production)")
                url = config.get("server_url", "wss://leagueofadventures.onrender.com/ws")
                
                if preset in self.server_presets:
                    self.server_preset_var.set(preset)
                else:
                    self.server_preset_var.set("✏️ Свой сервер")
                
                self.server_url_var.set(url)
                self.log(f"Загружен конфиг: {preset}")
            except Exception as e:
                self.log(f"Ошибка загрузки конфига: {e}")
                self.server_preset_var.set("🌐 Render (Production)")
                self.server_url_var.set("wss://leagueofadventures.onrender.com/ws")
        else:
            # Первый запуск — ставим Render по умолчанию
            self.server_preset_var.set("🌐 Render (Production)")
            self.server_url_var.set("wss://leagueofadventures.onrender.com/ws")
            self.log("Первый запуск, выбран сервер Render")
            self.save_config()
    
    def log(self, message):
        """Добавление сообщения в лог"""
        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, f"[{self.get_time()}] {message}\n")
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)
        self.root.update_idletasks()
        
    def get_time(self):
        """Получение текущего времени"""
        from datetime import datetime
        return datetime.now().strftime("%H:%M:%S")
        
    def check_updates(self):
        """Проверка наличия обновлений"""
        server_url = self.get_server_url()
        if not server_url:
            messagebox.showwarning("Внимание", "Укажите URL сервера!")
            return
            
        self.check_update_btn.config(state=tk.DISABLED)
        self.status_label.config(text="Проверка обновлений...", fg="#f39c12")
        self.log(f"Проверка обновлений на {server_url}...")
        
        def check():
            try:
                response = requests.get(
                    f"{server_url}/check_update",
                    params={"version": self.current_version},
                    timeout=10
                )
                
                if response.status_code == 200:
                    data = response.json()
                    
                    if data.get("update_available"):
                        latest_version = data.get("latest_version")
                        self.log(f"Доступна новая версия: {latest_version}")
                        
                        if messagebox.askyesno(
                            "Обновление доступно",
                            f"Доступна версия {latest_version}\n"
                            f"Текущая версия: {self.current_version}\n\n"
                            f"Скачать обновление?"
                        ):
                            self.download_update()
                        else:
                            self.status_label.config(text="Обновление отменено", fg="#e74c3c")
                    else:
                        self.log("У вас последняя версия")
                        self.status_label.config(text="Обновлений нет", fg="#2ecc71")
                        messagebox.showinfo("Обновления", "У вас установлена последняя версия!")
                else:
                    self.log(f"Ошибка проверки обновлений: {response.status_code}")
                    self.status_label.config(text="Ошибка проверки", fg="#e74c3c")
                    
            except Exception as e:
                self.log(f"Ошибка проверки обновлений: {e}")
                self.status_label.config(text="Ошибка сети", fg="#e74c3c")
            finally:
                self.check_update_btn.config(state=tk.NORMAL)
        
        threading.Thread(target=check, daemon=True).start()
        
    def download_update(self):
        """Скачивание обновления"""
        server_url = self.get_server_url()
        if not server_url:
            return
            
        self.status_label.config(text="Скачивание обновления...", fg="#f39c12")
        self.log("Начало скачивания обновления...")
        self.progress_bar['value'] = 0
        
        def download():
            try:
                response = requests.get(
                    f"{server_url}/download_update",
                    stream=True,
                    timeout=30
                )
                
                if response.status_code == 200:
                    total_size = int(response.headers.get('content-length', 0))
                    downloaded = 0
                    
                    with open(self.update_zip_path, 'wb') as f:
                        for chunk in response.iter_content(chunk_size=8192):
                            if chunk:
                                f.write(chunk)
                                downloaded += len(chunk)
                                
                                if total_size > 0:
                                    percent = (downloaded / total_size) * 100
                                    self.progress_bar['value'] = percent
                                    self.progress_label.config(
                                        text=f"Скачано: {downloaded // 1024} KB / {total_size // 1024} KB ({percent:.1f}%)"
                                    )
                                    
                    self.log("Обновление скачано")
                    self.install_update()
                else:
                    self.log(f"Ошибка скачивания: {response.status_code}")
                    self.status_label.config(text="Ошибка скачивания", fg="#e74c3c")
                    
            except Exception as e:
                self.log(f"Ошибка скачивания: {e}")
                self.status_label.config(text="Ошибка сети", fg="#e74c3c")
        
        threading.Thread(target=download, daemon=True).start()
        
    def install_update(self):
        """Установка обновления"""
        self.status_label.config(text="Установка обновления...", fg="#f39c12")
        self.log("Установка обновления...")
        
        def install():
            try:
                import zipfile
                
                with zipfile.ZipFile(self.update_zip_path, 'r') as zip_ref:
                    zip_ref.extractall(".")
                
                os.remove(self.update_zip_path)
                
                self.log("Обновление установлено")
                self.status_label.config(text="Обновление установлено", fg="#2ecc71")
                messagebox.showinfo("Обновление", "Обновление успешно установлено!")
                
            except Exception as e:
                self.log(f"Ошибка установки: {e}")
                self.status_label.config(text="Ошибка установки", fg="#e74c3c")
        
        threading.Thread(target=install, daemon=True).start()
        
    def save_token(self, token):
        """Сохранение токена в файл"""
        try:
            with open(self.token_file, 'w') as f:
                f.write(token)
            self.log("Токен сохранён")
        except Exception as e:
            self.log(f"Ошибка сохранения токена: {e}")
            
    def load_saved_token(self):
        """Загрузка сохранённого токена"""
        if os.path.exists(self.token_file):
            try:
                with open(self.token_file, 'r') as f:
                    self.token = f.read().strip()
                self.log("Загружен сохранённый токен")
            except Exception as e:
                self.log(f"Ошибка загрузки токена: {e}")
                self.token = None
                
    def launch_game(self):
        """Запуск игры"""
        server_url = self.server_url_var.get().strip()
        if not server_url:
            messagebox.showwarning("Внимание", "Укажите URL сервера!")
            return
        
        # Сохраняем конфиг перед запуском
        self.save_config()
        
        self.play_btn.config(state=tk.DISABLED)
        self.status_label.config(text="Запуск игры...", fg="#f39c12")
        self.log(f"Запуск игры с сервером: {server_url}")
        
        def launch():
            try:
                if sys.platform == "win32":
                    cmd = [self.game_exe]
                else:
                    cmd = ["python3", self.game_script]
                
                # Добавляем аргументы
                cmd.extend(["--server", server_url])
                
                if self.token:
                    cmd.extend(["--token", self.token])
                
                self.log(f"Команда: {' '.join(cmd)}")
                
                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )
                
                self.log("Игра запущена")
                self.status_label.config(text="Игра запущена", fg="#2ecc71")
                
                stdout, stderr = process.communicate()
                
                if process.returncode != 0:
                    self.log(f"Игра завершилась с ошибкой: {process.returncode}")
                    if stderr:
                        self.log(f"Ошибка: {stderr.decode('utf-8', errors='ignore')}")
                else:
                    self.log("Игра завершена")
                    
            except Exception as e:
                self.log(f"Ошибка запуска: {e}")
                self.status_label.config(text="Ошибка запуска", fg="#e74c3c")
                messagebox.showerror("Ошибка", f"Не удалось запустить игру:\n{e}")
            finally:
                self.play_btn.config(state=tk.NORMAL)
        
        threading.Thread(target=launch, daemon=True).start()


if __name__ == "__main__":
    root = tk.Tk()
    app = GameLauncher(root)
    root.mainloop()