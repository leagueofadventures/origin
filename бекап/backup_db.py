import os
import psycopg2
from psycopg2 import sql
import json
from datetime import datetime
import sys
import getpass
import tkinter as tk
from tkinter import messagebox, simpledialog, scrolledtext
import threading

# Прямая ссылка на базу данных (только для личного использования)
DATABASE_URL = "postgresql://game_server_db_user:ekAlZOOApuFwCjQJH3WTYgIETgTJikdo@dpg-d47248m3jp1c73atkceg-a.oregon-postgres.render.com/game_server_db"

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
            'banned': []
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

        conn.commit()
        print(f"База данных восстановлена из {backup_file}")
        print(f"Восстановлено пользователей: {len(backup_data['users'])}")
        print(f"Восстановлено заблокированных: {len(backup_data.get('banned', []))}")

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

def show_menu():
    """Показывает меню управления"""
    print("\n=== Панель управления базой данных ===")
    print("1. Создать резервную копию")
    print("2. Восстановить из бэкапа")
    print("3. Добавить пользователя")
    print("4. Удалить пользователя")
    print("5. Показать список пользователей")
    print("6. Выход")
    print("=" * 40)

def main():
    while True:
        show_menu()
        choice = input("Выберите действие (1-6): ").strip()

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
            print("Выход...")
            break
        else:
            print("Неверный выбор")

        input("\nНажмите Enter для продолжения...")

class DatabaseManager:
    def __init__(self, root):
        self.root = root
        self.root.title("Панель управления базой данных")
        self.root.geometry("600x500")

        # Создаем виджеты
        self.create_widgets()

        # Обновляем список пользователей при запуске
        self.refresh_users()

    def create_widgets(self):
        # Кнопки действий
        button_frame = tk.Frame(self.root)
        button_frame.pack(pady=10)

        tk.Button(button_frame, text="Создать бэкап", command=self.backup_database).pack(side=tk.LEFT, padx=5)
        tk.Button(button_frame, text="Восстановить из бэкапа", command=self.restore_database).pack(side=tk.LEFT, padx=5)
        tk.Button(button_frame, text="Добавить пользователя", command=self.add_user_dialog).pack(side=tk.LEFT, padx=5)
        tk.Button(button_frame, text="Удалить пользователя", command=self.delete_user_dialog).pack(side=tk.LEFT, padx=5)
        tk.Button(button_frame, text="Обновить список", command=self.refresh_users).pack(side=tk.LEFT, padx=5)

        # Текстовое поле для списка пользователей
        self.users_text = scrolledtext.ScrolledText(self.root, width=70, height=20)
        self.users_text.pack(pady=10, padx=10, fill=tk.BOTH, expand=True)

        # Статус бар
        self.status_label = tk.Label(self.root, text="Готово", bd=1, relief=tk.SUNKEN, anchor=tk.W)
        self.status_label.pack(side=tk.BOTTOM, fill=tk.X)

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
        dialog.geometry("300x200")

        listbox = tk.Listbox(dialog, selectmode=tk.SINGLE)
        listbox.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        for file in sorted(backup_files, reverse=True):
            listbox.insert(tk.END, file)

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
                    except Exception as e:
                        self.root.after(0, lambda: messagebox.showerror("Ошибка", f"Ошибка восстановления: {e}"))
                        self.root.after(0, lambda: self.status_label.config(text="Ошибка восстановления"))

                threading.Thread(target=run_restore, daemon=True).start()

        tk.Button(dialog, text="Восстановить", command=on_select).pack(pady=5)

    def add_user_dialog(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("Добавить пользователя")
        dialog.geometry("300x200")

        tk.Label(dialog, text="Имя пользователя:").pack(pady=5)
        username_entry = tk.Entry(dialog)
        username_entry.pack(pady=5)

        tk.Label(dialog, text="Пароль:").pack(pady=5)
        password_entry = tk.Entry(dialog, show="*")
        password_entry.pack(pady=5)

        admin_var = tk.BooleanVar()
        tk.Checkbutton(dialog, text="Администратор", variable=admin_var).pack(pady=5)

        def on_add():
            username = username_entry.get().strip()
            password = password_entry.get().strip()
            is_admin = admin_var.get()

            if not username or not password:
                messagebox.showerror("Ошибка", "Имя пользователя и пароль обязательны")
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

        tk.Button(dialog, text="Добавить", command=on_add).pack(pady=10)

    def delete_user_dialog(self):
        users = self.get_users_list()
        if not users:
            messagebox.showinfo("Информация", "Нет пользователей для удаления")
            return

        dialog = tk.Toplevel(self.root)
        dialog.title("Удалить пользователя")
        dialog.geometry("300x150")

        tk.Label(dialog, text="Выберите пользователя:").pack(pady=5)
        user_var = tk.StringVar()
        user_menu = tk.OptionMenu(dialog, user_var, *users)
        user_menu.pack(pady=5)

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

        tk.Button(dialog, text="Удалить", command=on_delete).pack(pady=10)

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

    def get_users_info(self):
        try:
            conn = psycopg2.connect(DATABASE_URL)
            cursor = conn.cursor()
            cursor.execute("SELECT username, is_admin FROM users ORDER BY username")
            users = cursor.fetchall()

            info = "Список пользователей:\n\n"
            for username, is_admin in users:
                admin_status = " (админ)" if is_admin else ""
                info += f"• {username}{admin_status}\n"

            info += f"\nВсего пользователей: {len(users)}"

            # Добавляем информацию о бэкапах
            backup_files = [f for f in os.listdir('.') if f.startswith('db_backup_') and f.endswith('.json')]
            if backup_files:
                info += f"\n\nДоступные бэкапы: {len(backup_files)}"
                for file in sorted(backup_files, reverse=True)[:5]:  # Показываем последние 5
                    info += f"\n  - {file}"

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
        else:
            print("Использование:")
            print("  python backup_db.py backup")
            print("  python backup_db.py restore <backup_file.json>")
            print("  python backup_db.py gui  # графический интерфейс")
            print("  python backup_db.py      # консольный режим")
    else:
        main_gui()  # По умолчанию запускаем GUI
