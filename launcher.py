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

# Настройки сервера
SERVER_HOST = "https://test-server-2zf4.onrender.com"  # Измените на ваш сервер

CLIENT_VERSION = "1.0.0"

class Launcher:
    def __init__(self, root):
        self.root = root
        self.root.title("League of adventures")
        self.root.geometry("400x300")
        self.root.resizable(False, False)

        # Переменные
        self.token = None
        self.username = tk.StringVar()
        self.password = tk.StringVar()

        # Создание виджетов
        self.create_widgets()

    def create_widgets(self):
        # Заголовок
        title_label = tk.Label(self.root, text="League of adventures", font=("Arial", 16))
        title_label.pack(pady=10)

        # Поля ввода
        frame = tk.Frame(self.root)
        frame.pack(pady=10)

        tk.Label(frame, text="Логин:").grid(row=0, column=0, sticky="e", padx=5, pady=5)
        self.username_entry = tk.Entry(frame, textvariable=self.username)
        self.username_entry.grid(row=0, column=1, padx=5, pady=5)

        tk.Label(frame, text="Пароль:").grid(row=1, column=0, sticky="e", padx=5, pady=5)
        self.password_entry = tk.Entry(frame, textvariable=self.password, show="*")
        self.password_entry.grid(row=1, column=1, padx=5, pady=5)

        # Кнопки
        button_frame = tk.Frame(self.root)
        button_frame.pack(pady=10)

        self.login_button = tk.Button(button_frame, text="Войти", command=self.login)
        self.login_button.grid(row=0, column=0, padx=5)

        self.register_button = tk.Button(button_frame, text="Регистрация", command=self.register)
        self.register_button.grid(row=0, column=1, padx=5)

        # Прогресс-бар для обновлений
        self.progress = ttk.Progressbar(self.root, orient="horizontal", length=300, mode="determinate")
        self.progress.pack(pady=10)
        self.progress.pack_forget()  # Скрыть изначально

        self.status_label = tk.Label(self.root, text="")
        self.status_label.pack(pady=5)

    def login(self):
        username = self.username.get()
        password = self.password.get()

        if not username or not password:
            messagebox.showerror("Ошибка", "Введите логин и пароль")
            return

        try:
            response = requests.post(f"{SERVER_HOST}/login", json={"username": username, "password": password}, timeout=30)
            data = response.json()

            if data.get("success"):
                self.token = data["token"]
                self.status_label.config(text="Вход успешен. Проверка обновлений...")
                self.check_updates()
            else:
                messagebox.showerror("Ошибка", data.get("message", "Ошибка входа"))
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось подключиться к серверу: {e}")

    def register(self):
        username = self.username.get()
        password = self.password.get()

        if not username or not password:
            messagebox.showerror("Ошибка", "Введите логин и пароль")
            return

        try:
            response = requests.post(f"{SERVER_HOST}/register", json={"username": username, "password": password}, timeout=30)
            data = response.json()

            if data.get("success"):
                messagebox.showinfo("Успех", "Регистрация успешна. Теперь войдите.")
            else:
                messagebox.showerror("Ошибка", data.get("message", "Ошибка регистрации"))
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось подключиться к серверу: {e}")

    def check_updates(self):
        try:
            response = requests.get(f"{SERVER_HOST}/check_update")
            if response.status_code == 200:
                update_info = response.json()
                if update_info.get("update_available") and update_info.get("version") != CLIENT_VERSION:
                    self.download_update(update_info)
                else:
                    self.launch_game()
            else:
                self.launch_game()  # Если эндпоинт не существует, запускаем игру
        except Exception as e:
            print(f"Ошибка проверки обновлений: {e}")
            self.launch_game()

    def download_update(self, update_info):
        self.status_label.config(text="Скачивание обновления...")
        self.progress.pack()
        self.progress["value"] = 0

        try:
            response = requests.get(f"{SERVER_HOST}/download_update", stream=True)
            if response.status_code == 200:
                total_size = int(response.headers.get('content-length', 0))
                downloaded = 0
                update_zip = "update.zip"
                with open(update_zip, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)
                            if total_size > 0:
                                self.progress["value"] = (downloaded / total_size) * 100
                                self.root.update_idletasks()

                self.status_label.config(text="Распаковка обновления...")
                with zipfile.ZipFile(update_zip, 'r') as zip_ref:
                    zip_ref.extractall(".")
                os.remove(update_zip)
                self.status_label.config(text="Обновление завершено.")
                self.progress["value"] = 100
                self.launch_game()
            else:
                messagebox.showerror("Ошибка", "Не удалось скачать обновление")
                self.launch_game()
        except Exception as e:
            messagebox.showerror("Ошибка", f"Ошибка при обновлении: {e}")
            self.launch_game()

    def launch_game(self):
        self.status_label.config(text="Запуск игры...")
        try:
            # Запуск main.py с токеном и сервером
            env = os.environ.copy()
            env["GAME_TOKEN"] = self.token or ""
            script_dir = os.path.dirname(os.path.abspath(__file__))
            game_path = os.path.join(script_dir, "main.py")
            subprocess.Popen([sys.executable, game_path, "--server", "wss://test-server-2zf4.onrender.com/ws"], env=env)
            self.root.quit()
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось запустить игру: {e}")

if __name__ == "__main__":
    root = tk.Tk()
    launcher = Launcher(root)
    root.mainloop()
