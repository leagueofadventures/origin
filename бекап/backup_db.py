import os
import psycopg2
from psycopg2 import sql
import json
from datetime import datetime
import sys
import getpass
import tkinter as tk
from tkinter import messagebox, simpledialog, scrolledtext, ttk
import threading
import requests

# Прямая ссылка на базу данных (только для личного использования)
DATABASE_URL = "postgresql://game_server_db_user:ekAlZOOApuFwCjQJH3WTYgIETgTJikdo@dpg-d47248m3jp1c73atkceg-a.oregon-postgres.render.com/game_server_db"
SERVER_HOST = "https://test-server-2zf4.onrender.com"

def backup_database():
    """Создает резервную копию базы данных в JSON формате"""
    try:
        # Подключаемся к базе данных
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()

        # Создаем словарь для хранения данных
        backup_data = {
            'timestamp': datetime.now().isoformat(),
            'users': [],
            'admins': [],
            'banned': [],
            'version': get_current_version()
        }

        # Получаем всех пользователей
        cursor.execute("SELECT username, password, is_admin FROM users")
        users = cursor.fetchall()
        for user in users:
            user_dict = {
                'username': user[0],
                'password': user[1],
                'is_admin': user[2]
            }
            backup_data['users'].append(user_dict)

            # Если пользователь админ, добавляем в список админов
            if user[2]:
                backup_data['admins'].append(user[0])

        # Получаем заблокированных пользователей (если есть таблица banned)
        try:
            cursor.execute("SELECT username FROM banned")
            banned_users = cursor.fetchall()
            backup_data['banned'] = [user[0] for user in banned_users]
        except psycopg2.Error:
            print("Таблица banned не найдена, пропускаем")

        # Сохраняем данные в JSON файл
        filename = f"db_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(backup_data, f, indent=2, ensure_ascii=False)

        print(f"Резервная копия создана: {filename}")
        print(f"Пользователей: {len(backup_data['users'])}")
        print(f"Админов: {len(backup_data['admins'])}")
        print(f"Заблокированных: {len(backup_data['banned'])}")
        print(f"Версия: {backup_data['version']}")

    except psycopg2.Error as e:
        print(f"Ошибка базы данных: {e}")
    except Exception as e:
        print(f"Ошибка: {e}")
    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'conn' in locals():
            conn.close()

def restore_database(backup_file):
    """Восстанавливает базу данных из JSON бэкапа"""
    try:
        # Читаем бэкап файл
        with open(backup_file, 'r', encoding='utf-8') as f:
            backup_data = json.load(f)

        # Подключаемся к базе данных
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()

        # Очищаем существующие данные
        cursor.execute("DELETE FROM users")
        try:
            cursor.execute("DELETE FROM banned")
        except psycopg2.Error:
            print("Таблица banned не существует")

        # Восстанавливаем пользователей
        for user in backup_data['users']:
            cursor.execute(
                "INSERT INTO users (username, password, is_admin) VALUES (%s, %s, %s)",
                (user['username'], user['password'], user['is_admin'])
            )

        # Восстанавливаем заблокированных (если есть)
        if 'banned' in backup_data and backup_data['banned']:
            for banned_user in backup_data['banned']:
                cursor.execute("INSERT INTO banned (username) VALUES (%s)", (banned_user,))

        # Восстанавливаем версию (если есть в бэкапе)
        if 'version' in backup_data:
            set_current_version(backup_data['version'])

        conn.commit()
        print(f"База данных восстановлена из {backup_file}")
        print(f"Восстановлено пользователей: {len(backup_data['users'])}")
        print(f"Восстановлено заблокированных: {len(backup_data.get('banned', []))}")
        if 'version' in backup_data:
            print(f"Версия установлена: {backup_data['version']}")

    except FileNotFoundError:
        print(f"Файл {backup_file} не найден")
    except json.JSONDecodeError:
        print(f"Ошибка чтения JSON файла {backup_file}")
    except psycopg2.Error as e:
        print(f"Ошибка базы данных: {e}")
        conn.rollback()
    except Exception as e:
        print(f"Ошибка: {e}")
    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'conn' in locals():
            conn.close()

def add_user(username, password, is_admin=False):
    """Добавляет нового пользователя"""
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()

        cursor.execute(
            "INSERT INTO users (username, password, is_admin) VALUES (%s, %s, %s)",
            (username, password, is_admin)
        )
        conn.commit()
        print(f"Пользователь {username} добавлен {'как админ' if is_admin else ''}")

    except psycopg2.Error as e:
        print(f"Ошибка добавления пользователя: {e}")
        if 'conn' in locals():
            conn.rollback()
    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'conn' in locals():
            conn.close()

def delete_user(username):
    """Удаляет пользователя"""
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()

        cursor.execute("DELETE FROM users WHERE username = %s", (username,))
        deleted_count = cursor.rowcount
        conn.commit()

        if deleted_count > 0:
            print(f"Пользователь {username} удален")
        else:
            print(f"Пользователь {username} не найден")

    except psycopg2.Error as e:
        print(f"Ошибка удаления пользователя: {e}")
        if 'conn' in locals():
            conn.rollback()
    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'conn' in locals():
            conn.close()

def ban_user(username):
    """Банит пользователя (добавляет в таблицу banned)"""
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()

        # Проверяем, существует ли пользователь
        cursor.execute("SELECT username FROM users WHERE username = %s", (username,))
        if cursor.fetchone() is None:
            print(f"Пользователь {username} не найден")
            return

        # Добавляем в banned (ON CONFLICT DO NOTHING предотвращает дубликаты)
        cursor.execute("INSERT INTO banned (username) VALUES (%s) ON CONFLICT (username) DO NOTHING", (username,))
        banned_count = cursor.rowcount
        conn.commit()

        if banned_count > 0:
            print(f"Пользователь {username} забанен")
        else:
            print(f"Пользователь {username} уже забанен")

    except psycopg2.Error as e:
        print(f"Ошибка бана пользователя: {e}")
        if 'conn' in locals():
            conn.rollback()
    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'conn' in locals():
            conn.close()

def unban_user(username):
    """Разбанивает пользователя (удаляет из таблицы banned)"""
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()

        cursor.execute("DELETE FROM banned WHERE username = %s", (username,))
        unbanned_count = cursor.rowcount
        conn.commit()

        if unbanned_count > 0:
            print(f"Пользователь {username} разбанен")
        else:
            print(f"Пользователь {username} не был забанен")

    except psycopg2.Error as e:
        print(f"Ошибка разбана пользователя: {e}")
        if 'conn' in locals():
            conn.rollback()
    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'conn' in locals():
            conn.close()

def list_banned_users():
    """Показывает список забаненных пользователей"""
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()

        cursor.execute("SELECT username FROM banned ORDER BY username")
        banned_users = cursor.fetchall()

        print("Забаненные пользователи:")
        for user in banned_users:
            print(f"  - {user[0]}")

        print(f"\nВсего забанено: {len(banned_users)}")

    except psycopg2.Error as e:
        print(f"Ошибка получения списка забаненных: {e}")
    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'conn' in locals():
            conn.close()

def list_users():
    """Показывает список всех пользователей"""
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()

        cursor.execute("SELECT username, is_admin FROM users ORDER BY username")
        users = cursor.fetchall()

        print("Список пользователей:")
        for user in users:
            admin_status = " (админ)" if user[1] else ""
            print(f"  - {user[0]}{admin_status}")

        print(f"\nВсего пользователей: {len(users)}")

    except psycopg2.Error as e:
        print(f"Ошибка получения списка пользователей: {e}")
    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'conn' in locals():
            conn.close()

def get_current_version():
    """Получает текущую версию из базы данных"""
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        
        # Создаем таблицу версий если её нет
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS app_settings (
                key VARCHAR(50) PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute("SELECT value FROM app_settings WHERE key = 'latest_version'")
        result = cursor.fetchone()
        
        if result:
            return result[0]
        else:
            # Устанавливаем версию по умолчанию
            default_version = "1.0.0"
            cursor.execute(
                "INSERT INTO app_settings (key, value) VALUES ('latest_version', %s)",
                (default_version,)
            )
            conn.commit()
            return default_version
            
    except psycopg2.Error as e:
        print(f"Ошибка получения версии: {e}")
        return "1.0.0"
    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'conn' in locals():
            conn.close()

def set_current_version(version):
    """Устанавливает новую версию в базе данных"""
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS app_settings (
                key VARCHAR(50) PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute(
            "INSERT INTO app_settings (key, value) VALUES ('latest_version', %s) "
            "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = CURRENT_TIMESTAMP",
            (version,)
        )
        conn.commit()
        print(f"Версия установлена: {version}")
        return True
        
    except psycopg2.Error as e:
        print(f"Ошибка установки версии: {e}")
        return False
    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'conn' in locals():
            conn.close()

def test_server_connection():
    """Проверяет соединение с сервером"""
    try:
        response = requests.get(f"{SERVER_HOST}/check_update?version=1.0.0", timeout=5)
        return response.status_code == 200
    except:
        return False

def show_menu():
    """Показывает меню управления"""
    current_version = get_current_version()
    print(f"\n=== Панель управления базой данных (v{current_version}) ===")
    print("1. Создать резервную копию")
    print("2. Восстановить из бэкапа")
    print("3. Добавить пользователя")
    print("4. Удалить пользователя")
    print("5. Показать список пользователей")
    print("6. Управление версиями")
    print("7. Выход")
    print("=" * 50)

def version_management():
    """Меню управления версиями"""
    while True:
        current_version = get_current_version()
        server_status = "✓ Доступен" if test_server_connection() else "✗ Недоступен"
        
        print(f"\n=== Управление версиями ===")
        print(f"Текущая версия: {current_version}")
        print(f"Статус сервера: {server_status}")
        print("1. Установить новую версию")
        print("2. Проверить обновления на сервере")
        print("3. Назад")
        
        choice = input("Выберите действие (1-3): ").strip()
        
        if choice == '1':
            new_version = input("Введите новую версию (формат X.X.X): ").strip()
            if new_version and all(part.isdigit() for part in new_version.split('.')):
                if set_current_version(new_version):
                    print(f"Версия успешно обновлена на {new_version}")
                else:
                    print("Ошибка обновления версии")
            else:
                print("Неверный формат версии. Используйте формат X.X.X (например: 1.2.3)")
                
        elif choice == '2':
            print("Проверка обновлений на сервере...")
            try:
                response = requests.get(f"{SERVER_HOST}/check_update?version={current_version}", timeout=5)
                if response.status_code == 200:
                    update_info = response.json()
                    print(f"Текущая версия на сервере: {update_info.get('latest_version', 'неизвестно')}")
                    print(f"Доступно обновление: {'Да' if update_info.get('update_available') else 'Нет'}")
                else:
                    print("Ошибка при проверке обновлений")
            except Exception as e:
                print(f"Ошибка подключения к серверу: {e}")
                
        elif choice == '3':
            break
        else:
            print("Неверный выбор")

def main():
    while True:
        show_menu()
        choice = input("Выберите действие (1-7): ").strip()

        if choice == '1':
            backup_database()
        elif choice == '2':
            backup_files = [f for f in os.listdir('.') if f.startswith('db_backup_') and f.endswith('.json')]
            if not backup_files:
                print("Нет доступных файлов бэкапа")
                continue

            print("Доступные бэкапы:")
            for i, file in enumerate(sorted(backup_files, reverse=True), 1):
                print(f"{i}. {file}")

            try:
                file_choice = int(input("Выберите файл (номер): ")) - 1
                if 0 <= file_choice < len(backup_files):
                    restore_database(backup_files[file_choice])
                else:
                    print("Неверный номер файла")
            except ValueError:
                print("Введите число")
        elif choice == '3':
            username = input("Имя пользователя: ").strip()
            password = getpass.getpass("Пароль: ")
            is_admin = input("Сделать админом? (y/n): ").strip().lower() == 'y'
            if username and password:
                add_user(username, password, is_admin)
            else:
                print("Имя пользователя и пароль обязательны")
        elif choice == '4':
            username = input("Имя пользователя для удаления: ").strip()
            if username:
                confirm = input(f"Удалить пользователя {username}? (y/n): ").strip().lower()
                if confirm == 'y':
                    delete_user(username)
            else:
                print("Имя пользователя обязательно")
        elif choice == '5':
            list_users()
        elif choice == '6':
            version_management()
        elif choice == '7':
            print("Выход...")
            break
        else:
            print("Неверный выбор")

        input("\nНажмите Enter для продолжения...")

class DatabaseManager:
    def __init__(self, root):
        self.root = root
        self.root.title("Панель управления базой данных")
        self.root.geometry("700x600")
        
        # Центрирование окна
        self.center_window()

        # Создаем виджеты
        self.create_widgets()

        # Обновляем список пользователей при запуске
        self.refresh_users()

    def center_window(self):
        """Центрирует окно на экране"""
        self.root.update_idletasks()
        width = self.root.winfo_width()
        height = self.root.winfo_height()
        x = (self.root.winfo_screenwidth() // 2) - (width // 2)
        y = (self.root.winfo_screenheight() // 2) - (height // 2)
        self.root.geometry(f'700x600+{x}+{y}')

    def create_widgets(self):
        # Основной фрейм
        main_frame = tk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Фрейм версии и статуса
        info_frame = tk.Frame(main_frame)
        info_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.version_label = tk.Label(info_frame, text="Версия: загрузка...", font=("Arial", 10))
        self.version_label.pack(side=tk.LEFT)
        
        self.server_status_label = tk.Label(info_frame, text="Сервер: проверка...", font=("Arial", 10))
        self.server_status_label.pack(side=tk.RIGHT)

        # Кнопки действий
        button_frame = tk.Frame(main_frame)
        button_frame.pack(fill=tk.X, pady=(0, 10))

        # Первый ряд кнопок
        row1_frame = tk.Frame(button_frame)
        row1_frame.pack(fill=tk.X)
        
        tk.Button(row1_frame, text="Создать бэкап", command=self.backup_database, width=15).pack(side=tk.LEFT, padx=2)
        tk.Button(row1_frame, text="Восстановить из бэкапа", command=self.restore_database, width=18).pack(side=tk.LEFT, padx=2)
        tk.Button(row1_frame, text="Добавить пользователя", command=self.add_user_dialog, width=18).pack(side=tk.LEFT, padx=2)
        tk.Button(row1_frame, text="Удалить пользователя", command=self.delete_user_dialog, width=18).pack(side=tk.LEFT, padx=2)

        # Второй ряд кнопок
        row2_frame = tk.Frame(button_frame)
        row2_frame.pack(fill=tk.X, pady=(5, 0))
        
        tk.Button(row2_frame, text="Забанить пользователя", command=self.ban_user_dialog, width=18).pack(side=tk.LEFT, padx=2)
        tk.Button(row2_frame, text="Разбанить пользователя", command=self.unban_user_dialog, width=18).pack(side=tk.LEFT, padx=2)
        tk.Button(row2_frame, text="Управление версиями", command=self.version_management_dialog, width=18).pack(side=tk.LEFT, padx=2)
        tk.Button(row2_frame, text="Обновить список", command=self.refresh_users, width=15).pack(side=tk.LEFT, padx=2)

        # Текстовое поле для списка пользователей
        text_frame = tk.Frame(main_frame)
        text_frame.pack(fill=tk.BOTH, expand=True)
        
        tk.Label(text_frame, text="Информация о базе данных:", font=("Arial", 11, "bold")).pack(anchor=tk.W)
        self.users_text = scrolledtext.ScrolledText(text_frame, width=80, height=20, font=("Consolas", 9))
        self.users_text.pack(fill=tk.BOTH, expand=True, pady=(5, 0))

        # Статус бар
        self.status_label = tk.Label(self.root, text="Готово", bd=1, relief=tk.SUNKEN, anchor=tk.W)
        self.status_label.pack(side=tk.BOTTOM, fill=tk.X)
        
        # Обновляем информацию о версии
        self.update_version_info()

    def update_version_info(self):
        """Обновляет информацию о версии и статусе сервера"""
        def update():
            current_version = get_current_version()
            server_available = test_server_connection()
            
            self.root.after(0, lambda: self.version_label.config(
                text=f"Версия: {current_version}"
            ))
            self.root.after(0, lambda: self.server_status_label.config(
                text=f"Сервер: {'✓ Доступен' if server_available else '✗ Недоступен'}",
                fg="green" if server_available else "red"
            ))
        
        threading.Thread(target=update, daemon=True).start()

    def backup_database(self):
        def run_backup():
            self.status_label.config(text="Создание бэкапа...")
            try:
                backup_database()
                self.root.after(0, lambda: self.status_label.config(text="Бэкап создан успешно"))
                self.root.after(0, self.refresh_users)
            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror("Ошибка", f"Ошибка создания бэкапа: {e}"))
                self.root.after(0, lambda: self.status_label.config(text="Ошибка создания бэкапа"))

        threading.Thread(target=run_backup, daemon=True).start()

    def restore_database(self):
        backup_files = [f for f in os.listdir('.') if f.startswith('db_backup_') and f.endswith('.json')]
        if not backup_files:
            messagebox.showinfo("Информация", "Нет доступных файлов бэкапа")
            return

        # Создаем диалог выбора файла
        dialog = tk.Toplevel(self.root)
        dialog.title("Выберите файл бэкапа")
        dialog.geometry("400x300")
        dialog.transient(self.root)
        dialog.grab_set()
        
        # Центрируем диалог
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - (400 // 2)
        y = (dialog.winfo_screenheight() // 2) - (300 // 2)
        dialog.geometry(f'400x300+{x}+{y}')

        tk.Label(dialog, text="Выберите файл для восстановления:", font=("Arial", 10)).pack(pady=10)

        listbox_frame = tk.Frame(dialog)
        listbox_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        listbox = tk.Listbox(listbox_frame, selectmode=tk.SINGLE, font=("Consolas", 9))
        scrollbar = tk.Scrollbar(listbox_frame, orient=tk.VERTICAL, command=listbox.yview)
        listbox.config(yscrollcommand=scrollbar.set)
        
        listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        for file in sorted(backup_files, reverse=True):
            listbox.insert(tk.END, file)

        button_frame = tk.Frame(dialog)
        button_frame.pack(fill=tk.X, pady=10)

        def on_select():
            selection = listbox.curselection()
            if selection:
                filename = listbox.get(selection[0])
                dialog.destroy()

                def run_restore():
                    self.status_label.config(text="Восстановление из бэкапа...")
                    try:
                        restore_database(filename)
                        self.root.after(0, lambda: self.status_label.config(text="База данных восстановлена"))
                        self.root.after(0, self.refresh_users)
                        self.root.after(0, self.update_version_info)
                    except Exception as e:
                        self.root.after(0, lambda: messagebox.showerror("Ошибка", f"Ошибка восстановления: {e}"))
                        self.root.after(0, lambda: self.status_label.config(text="Ошибка восстановления"))

                threading.Thread(target=run_restore, daemon=True).start()

        def on_cancel():
            dialog.destroy()

        tk.Button(button_frame, text="Восстановить", command=on_select, width=12).pack(side=tk.LEFT, padx=10)
        tk.Button(button_frame, text="Отмена", command=on_cancel, width=12).pack(side=tk.RIGHT, padx=10)

    def add_user_dialog(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("Добавить пользователя")
        dialog.geometry("300x250")
        dialog.transient(self.root)
        dialog.grab_set()
        
        # Центрируем диалог
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - (300 // 2)
        y = (dialog.winfo_screenheight() // 2) - (250 // 2)
        dialog.geometry(f'300x250+{x}+{y}')

        tk.Label(dialog, text="Имя пользователя:", font=("Arial", 10)).pack(pady=10)
        username_entry = tk.Entry(dialog, width=25, font=("Arial", 10))
        username_entry.pack(pady=5)
        username_entry.focus()

        tk.Label(dialog, text="Пароль:", font=("Arial", 10)).pack(pady=10)
        password_entry = tk.Entry(dialog, show="*", width=25, font=("Arial", 10))
        password_entry.pack(pady=5)

        admin_var = tk.BooleanVar()
        tk.Checkbutton(dialog, text="Администратор", variable=admin_var, font=("Arial", 10)).pack(pady=10)

        button_frame = tk.Frame(dialog)
        button_frame.pack(pady=20)

        def on_add():
            username = username_entry.get().strip()
            password = password_entry.get().strip()
            is_admin = admin_var.get()

            if not username or not password:
                messagebox.showerror("Ошибка", "Имя пользователя и пароль обязательны")
                return

            if len(username) < 3:
                messagebox.showerror("Ошибка", "Имя пользователя должно содержать минимум 3 символа")
                return

            dialog.destroy()

            def run_add():
                self.status_label.config(text="Добавление пользователя...")
                try:
                    add_user(username, password, is_admin)
                    self.root.after(0, lambda: self.status_label.config(text="Пользователь добавлен"))
                    self.root.after(0, self.refresh_users)
                except Exception as e:
                    self.root.after(0, lambda: messagebox.showerror("Ошибка", f"Ошибка добавления пользователя: {e}"))
                    self.root.after(0, lambda: self.status_label.config(text="Ошибка добавления пользователя"))

            threading.Thread(target=run_add, daemon=True).start()

        def on_cancel():
            dialog.destroy()

        tk.Button(button_frame, text="Добавить", command=on_add, width=10).pack(side=tk.LEFT, padx=5)
        tk.Button(button_frame, text="Отмена", command=on_cancel, width=10).pack(side=tk.RIGHT, padx=5)

    def delete_user_dialog(self):
        users = self.get_users_list()
        if not users:
            messagebox.showinfo("Информация", "Нет пользователей для удаления")
            return

        dialog = tk.Toplevel(self.root)
        dialog.title("Удалить пользователя")
        dialog.geometry("300x180")
        dialog.transient(self.root)
        dialog.grab_set()
        
        # Центрируем диалог
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - (300 // 2)
        y = (dialog.winfo_screenheight() // 2) - (180 // 2)
        dialog.geometry(f'300x180+{x}+{y}')

        tk.Label(dialog, text="Выберите пользователя:", font=("Arial", 10)).pack(pady=15)
        user_var = tk.StringVar()
        user_menu = ttk.Combobox(dialog, textvariable=user_var, values=users, state="readonly", width=25)
        user_menu.pack(pady=10)
        user_menu.current(0)

        button_frame = tk.Frame(dialog)
        button_frame.pack(pady=20)

        def on_delete():
            username = user_var.get()
            if not username:
                messagebox.showerror("Ошибка", "Выберите пользователя")
                return

            if not messagebox.askyesno("Подтверждение", f"Удалить пользователя {username}?"):
                return

            dialog.destroy()

            def run_delete():
                self.status_label.config(text="Удаление пользователя...")
                try:
                    delete_user(username)
                    self.root.after(0, lambda: self.status_label.config(text="Пользователь удален"))
                    self.root.after(0, self.refresh_users)
                except Exception as e:
                    self.root.after(0, lambda: messagebox.showerror("Ошибка", f"Ошибка удаления пользователя: {e}"))
                    self.root.after(0, lambda: self.status_label.config(text="Ошибка удаления пользователя"))

            threading.Thread(target=run_delete, daemon=True).start()

        def on_cancel():
            dialog.destroy()

        tk.Button(button_frame, text="Удалить", command=on_delete, width=10).pack(side=tk.LEFT, padx=5)
        tk.Button(button_frame, text="Отмена", command=on_cancel, width=10).pack(side=tk.RIGHT, padx=5)

    def refresh_users(self):
        def run_refresh():
            self.status_label.config(text="Обновление списка...")
            try:
                users_info = self.get_users_info()
                self.root.after(0, lambda: self.users_text.delete(1.0, tk.END))
                self.root.after(0, lambda: self.users_text.insert(tk.END, users_info))
                self.root.after(0, lambda: self.status_label.config(text="Список обновлен"))
            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror("Ошибка", f"Ошибка обновления списка: {e}"))
                self.root.after(0, lambda: self.status_label.config(text="Ошибка обновления списка"))

        threading.Thread(target=run_refresh, daemon=True).start()

    def get_users_list(self):
        try:
            conn = psycopg2.connect(DATABASE_URL)
            cursor = conn.cursor()
            cursor.execute("SELECT username FROM users ORDER BY username")
            users = [row[0] for row in cursor.fetchall()]
            return users
        except Exception as e:
            messagebox.showerror("Ошибка", f"Ошибка получения списка пользователей: {e}")
            return []
        finally:
            if 'cursor' in locals():
                cursor.close()
            if 'conn' in locals():
                conn.close()

    def ban_user_dialog(self):
        users = self.get_users_list()
        if not users:
            messagebox.showinfo("Информация", "Нет пользователей для бана")
            return

        dialog = tk.Toplevel(self.root)
        dialog.title("Забанить пользователя")
        dialog.geometry("300x180")
        dialog.transient(self.root)
        dialog.grab_set()
        
        # Центрируем диалог
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - (300 // 2)
        y = (dialog.winfo_screenheight() // 2) - (180 // 2)
        dialog.geometry(f'300x180+{x}+{y}')

        tk.Label(dialog, text="Выберите пользователя:", font=("Arial", 10)).pack(pady=15)
        user_var = tk.StringVar()
        user_menu = ttk.Combobox(dialog, textvariable=user_var, values=users, state="readonly", width=25)
        user_menu.pack(pady=10)
        user_menu.current(0)

        button_frame = tk.Frame(dialog)
        button_frame.pack(pady=20)

        def on_ban():
            username = user_var.get()
            if not username:
                messagebox.showerror("Ошибка", "Выберите пользователя")
                return

            if not messagebox.askyesno("Подтверждение", f"Забанить пользователя {username}?"):
                return

            dialog.destroy()

            def run_ban():
                self.status_label.config(text="Бан пользователя...")
                try:
                    ban_user(username)
                    self.root.after(0, lambda: self.status_label.config(text="Пользователь забанен"))
                    self.root.after(0, self.refresh_users)
                except Exception as e:
                    self.root.after(0, lambda: messagebox.showerror("Ошибка", f"Ошибка бана пользователя: {e}"))
                    self.root.after(0, lambda: self.status_label.config(text="Ошибка бана пользователя"))

            threading.Thread(target=run_ban, daemon=True).start()

        def on_cancel():
            dialog.destroy()

        tk.Button(button_frame, text="Забанить", command=on_ban, width=10).pack(side=tk.LEFT, padx=5)
        tk.Button(button_frame, text="Отмена", command=on_cancel, width=10).pack(side=tk.RIGHT, padx=5)

    def unban_user_dialog(self):
        banned_users = self.get_banned_users_list()
        if not banned_users:
            messagebox.showinfo("Информация", "Нет забаненных пользователей")
            return

        dialog = tk.Toplevel(self.root)
        dialog.title("Разбанить пользователя")
        dialog.geometry("300x180")
        dialog.transient(self.root)
        dialog.grab_set()
        
        # Центрируем диалог
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - (300 // 2)
        y = (dialog.winfo_screenheight() // 2) - (180 // 2)
        dialog.geometry(f'300x180+{x}+{y}')

        tk.Label(dialog, text="Выберите пользователя:", font=("Arial", 10)).pack(pady=15)
        user_var = tk.StringVar()
        user_menu = ttk.Combobox(dialog, textvariable=user_var, values=banned_users, state="readonly", width=25)
        user_menu.pack(pady=10)
        user_menu.current(0)

        button_frame = tk.Frame(dialog)
        button_frame.pack(pady=20)

        def on_unban():
            username = user_var.get()
            if not username:
                messagebox.showerror("Ошибка", "Выберите пользователя")
                return

            if not messagebox.askyesno("Подтверждение", f"Разбанить пользователя {username}?"):
                return

            dialog.destroy()

            def run_unban():
                self.status_label.config(text="Разбан пользователя...")
                try:
                    unban_user(username)
                    self.root.after(0, lambda: self.status_label.config(text="Пользователь разбанен"))
                    self.root.after(0, self.refresh_users)
                except Exception as e:
                    self.root.after(0, lambda: messagebox.showerror("Ошибка", f"Ошибка разбана пользователя: {e}"))
                    self.root.after(0, lambda: self.status_label.config(text="Ошибка разбана пользователя"))

            threading.Thread(target=run_unban, daemon=True).start()

        def on_cancel():
            dialog.destroy()

        tk.Button(button_frame, text="Разбанить", command=on_unban, width=10).pack(side=tk.LEFT, padx=5)
        tk.Button(button_frame, text="Отмена", command=on_cancel, width=10).pack(side=tk.RIGHT, padx=5)

    def version_management_dialog(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("Управление версиями")
        dialog.geometry("400x300")
        dialog.transient(self.root)
        dialog.grab_set()
        
        # Центрируем диалог
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - (400 // 2)
        y = (dialog.winfo_screenheight() // 2) - (300 // 2)
        dialog.geometry(f'400x300+{x}+{y}')

        # Текущая версия
        current_version = get_current_version()
        server_available = test_server_connection()
        
        info_frame = tk.Frame(dialog)
        info_frame.pack(fill=tk.X, padx=20, pady=15)
        
        tk.Label(info_frame, text="Текущая версия:", font=("Arial", 10, "bold")).grid(row=0, column=0, sticky="w")
        tk.Label(info_frame, text=current_version, font=("Arial", 10)).grid(row=0, column=1, sticky="w", padx=(10, 0))
        
        tk.Label(info_frame, text="Статус сервера:", font=("Arial", 10, "bold")).grid(row=1, column=0, sticky="w", pady=(5, 0))
        status_label = tk.Label(info_frame, 
                               text="✓ Доступен" if server_available else "✗ Недоступен",
                               fg="green" if server_available else "red",
                               font=("Arial", 10))
        status_label.grid(row=1, column=1, sticky="w", padx=(10, 0), pady=(5, 0))

        # Поле для новой версии
        version_frame = tk.Frame(dialog)
        version_frame.pack(fill=tk.X, padx=20, pady=15)
        
        tk.Label(version_frame, text="Новая версия:", font=("Arial", 10)).pack(anchor="w")
        version_entry = tk.Entry(version_frame, width=15, font=("Arial", 10))
        version_entry.pack(anchor="w", pady=(5, 0))
        version_entry.insert(0, current_version)

        # Кнопки
        button_frame = tk.Frame(dialog)
        button_frame.pack(fill=tk.X, padx=20, pady=20)

        def on_set_version():
            new_version = version_entry.get().strip()
            if not new_version:
                messagebox.showerror("Ошибка", "Введите версию")
                return
                
            if not all(part.isdigit() for part in new_version.split('.')):
                messagebox.showerror("Ошибка", "Неверный формат версии. Используйте X.X.X")
                return
                
            if set_current_version(new_version):
                messagebox.showinfo("Успех", f"Версия установлена: {new_version}")
                self.update_version_info()
                self.refresh_users()
            else:
                messagebox.showerror("Ошибка", "Не удалось установить версию")

        def on_check_updates():
            def check():
                try:
                    response = requests.get(f"{SERVER_HOST}/check_update?version={current_version}", timeout=5)
                    if response.status_code == 200:
                        update_info = response.json()
                        server_version = update_info.get('latest_version', 'неизвестно')
                        has_update = update_info.get('update_available', False)
                        
                        message = (f"Версия на сервере: {server_version}\n"
                                  f"Доступно обновление: {'Да' if has_update else 'Нет'}")
                        
                        if has_update and server_version != current_version:
                            message += f"\n\nРекомендуется установить версию {server_version}"
                            
                        self.root.after(0, lambda: messagebox.showinfo("Проверка обновлений", message))
                    else:
                        self.root.after(0, lambda: messagebox.showerror("Ошибка", "Не удалось проверить обновления"))
                except Exception as e:
                    self.root.after(0, lambda: messagebox.showerror("Ошибка", f"Ошибка подключения: {e}"))
            
            threading.Thread(target=check, daemon=True).start()

        def on_close():
            dialog.destroy()

        tk.Button(button_frame, text="Установить версию", command=on_set_version, width=15).pack(side=tk.LEFT, padx=5)
        tk.Button(button_frame, text="Проверить обновления", command=on_check_updates, width=15).pack(side=tk.LEFT, padx=5)
        tk.Button(button_frame, text="Закрыть", command=on_close, width=10).pack(side=tk.RIGHT, padx=5)

    def get_banned_users_list(self):
        try:
            conn = psycopg2.connect(DATABASE_URL)
            cursor = conn.cursor()
            cursor.execute("SELECT username FROM banned ORDER BY username")
            banned_users = [row[0] for row in cursor.fetchall()]
            return banned_users
        except Exception as e:
            messagebox.showerror("Ошибка", f"Ошибка получения списка забаненных: {e}")
            return []
        finally:
            if 'cursor' in locals():
                cursor.close()
            if 'conn' in locals():
                conn.close()

    def get_users_info(self):
        try:
            conn = psycopg2.connect(DATABASE_URL)
            cursor = conn.cursor()
            cursor.execute("SELECT username, password, is_admin FROM users ORDER BY username")
            users = cursor.fetchall()

            # Получаем список забаненных
            cursor.execute("SELECT username FROM banned")
            banned_set = set(row[0] for row in cursor.fetchall())
            
            # Получаем текущую версию
            current_version = get_current_version()

            info = f"=== ИНФОРМАЦИЯ О БАЗЕ ДАННЫХ ===\n"
            info += f"Текущая версия: {current_version}\n"
            info += f"Сервер: {'✓ Доступен' if test_server_connection() else '✗ Недоступен'}\n\n"
            
            info += "СПИСОК ПОЛЬЗОВАТЕЛЕЙ:\n"
            info += "-" * 50 + "\n"
            
            for username, password, is_admin in users:
                admin_status = " (АДМИН)" if is_admin else ""
                banned_status = " (ЗАБАНЕН)" if username in banned_set else ""
                info += f"• {username} | Пароль: {password}{admin_status}{banned_status}\n"

            info += f"\nВСЕГО: {len(users)} пользователей"
            
            admin_count = sum(1 for _, _, is_admin in users if is_admin)
            if admin_count > 0:
                info += f", {admin_count} админов"
                
            if banned_set:
                info += f", {len(banned_set)} забанено"

            # Добавляем информацию о бэкапах
            backup_files = [f for f in os.listdir('.') if f.startswith('db_backup_') and f.endswith('.json')]
            if backup_files:
                info += f"\n\nДОСТУПНЫЕ БЭКАПЫ: {len(backup_files)}\n"
                info += "-" * 30 + "\n"
                for file in sorted(backup_files, reverse=True)[:3]:  # Показываем последние 3
                    file_time = file.replace('db_backup_', '').replace('.json', '')
                    info += f"  - {file_time} -> {file}\n"

            return info
        except Exception as e:
            return f"Ошибка получения информации: {e}"
        finally:
            if 'cursor' in locals():
                cursor.close()
            if 'conn' in locals():
                conn.close()

def main_gui():
    root = tk.Tk()
    app = DatabaseManager(root)
    root.mainloop()

if __name__ == "__main__":
    if len(sys.argv) > 1:
        if sys.argv[1] == 'backup':
            backup_database()
        elif sys.argv[1] == 'restore' and len(sys.argv) > 2:
            restore_database(sys.argv[2])
        elif sys.argv[1] == 'gui':
            main_gui()
        elif sys.argv[1] == 'version':
            if len(sys.argv) > 2:
                set_current_version(sys.argv[2])
            else:
                print(f"Текущая версия: {get_current_version()}")
        else:
            print("Использование:")
            print("  python backup_db.py backup")
            print("  python backup_db.py restore <backup_file.json>")
            print("  python backup_db.py version [new_version]")
            print("  python backup_db.py gui  # графический интерфейс")
            print("  python backup_db.py      # консольный режим")
    else:
        main_gui()  # По умолчанию запускаем GUI