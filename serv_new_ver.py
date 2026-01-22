import socket
import tkinter as tk
import time
import os

cikl = True
IP = "172.20.4.106"
PORT = 8888
x = "600"
y = "450"

"""

w=слева
e=справа
n=сверху
s=снизу

"""

def closing():
    client_socket.send(("_close_").encode('utf-8'))
    root.destroy()

def on_closing():
    pass

def send_socket():
    client_socket.send(input_cmd.encode('utf-8'))

def recv_socket():
    global recv_data
    recv_data = client_socket.recv(1024)
    print(str(recv_data.decode('utf-8')))
    
def cmd():
    global input_cmd
    while cikl:
        input_cmd = entry_cmd.get()
        send_socket()
        print(f'Отправлена команда "{input_cmd}"')
        recv_socket()
        break


def start_serv():
    global server_socket
    global client_socket
    global client_addr

    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.bind((IP, PORT))
    server_socket.listen(1)
    print("СЕРВЕР ЗАПУЩЕН")
    print("ОЖИДАЕМ ПОДКЛЮЧЕНИЕ")

    client_socket, client_addr = server_socket.accept()
    print(f'Подключено к клиенту {client_addr[0]}')



root = tk.Tk() #создаем окно
root.title('server')
root.geometry(f"{x}x{y}")
root.resizable(False, False)
root.protocol("WM_DELETE_WINDOW", on_closing)

Ip_label = tk.Label(root, text = f'IP: {IP}')
Port_label = tk.Label(root, text = f"Port: {PORT}")

entry_cmd = tk.Entry(root, width=40)

butt_cmd = tk.Button(text = "отправить команду", command = cmd)
butt_closing = tk.Button(text = "Закрыть соединение", command = closing)


Ip_label.pack(anchor = "nw")
Port_label.pack(anchor = "nw")
entry_cmd.pack(anchor = "nw")
butt_cmd.pack(anchor = "nw")
butt_closing.pack(anchor = "se")

start_serv()
root.mainloop()