import socket
import subprocess
import platform
import json
import os
import re
from typing import Dict, List, Optional, Tuple
import logging

# Определяем текущую директорию проекта
PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

class NetworkDetector:
    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def get_local_ip(self) -> str:
        """Получить локальный IP-адрес машины"""
        try:
            # Создаем сокет для определения локального IP
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
            s.close()
            return local_ip
        except Exception as e:
            self.logger.warning(f"Не удалось определить локальный IP: {e}")
            return "127.0.0.1"

    def get_all_interfaces(self) -> List[Dict[str, str]]:
        """Получить все доступные сетевые интерфейсы"""
        interfaces = []
        try:
            if platform.system() == "Windows":
                result = subprocess.run(['ipconfig'], capture_output=True, text=True, encoding='cp1251')
                # Разбор вывода ipconfig для Windows
                lines = result.stdout.split('\n')
                current_interface = {}
                for line in lines:
                    if 'адаптер' in line.lower() or 'adapter' in line.lower():
                        if current_interface:
                            interfaces.append(current_interface)
                        current_interface = {'name': line.strip()}
                    elif 'ipv4' in line.lower():
                        ip = line.split(':')[-1].strip()
                        if ip and ip != '0.0.0.0':
                            current_interface['ip'] = ip
                    elif 'маска' in line.lower() or 'subnet' in line.lower():
                        mask = line.split(':')[-1].strip()
                        current_interface['subnet'] = mask
                if current_interface:
                    interfaces.append(current_interface)
            else:
                # Unix-подобные системы
                result = subprocess.run(['ip', 'addr', 'show'], capture_output=True, text=True)
                lines = result.stdout.split('\n')
                current_interface = {}
                for line in lines:
                    if line.strip().startswith('state UP'):
                        if current_interface:
                            interfaces.append(current_interface)
                        current_interface = {'name': line.split(':')[1].strip()}
                    elif 'inet ' in line and '127.0.0.1' not in line:
                        parts = line.strip().split()
                        if len(parts) >= 2:
                            current_interface['ip'] = parts[1].split('/')[0]
                if current_interface:
                    interfaces.append(current_interface)
        except Exception as e:
            self.logger.warning(f"Не удалось получить сетевые интерфейсы: {e}")

        return interfaces

    def detect_vpn_interfaces(self, interfaces: List[Dict[str, str]]) -> List[Dict[str, str]]:
        """Определить VPN интерфейсы (Radmin, Hamachi и т.д.)"""
        vpn_interfaces = []

        for interface in interfaces:
            name = interface.get('name', '').lower()
            ip = interface.get('ip', '')

            # Проверяем на Radmin VPN
            if 'radmin' in name or 'radmin' in interface.get('description', ''):
                interface['type'] = 'radmin_vpn'
                interface['priority'] = 10
                vpn_interfaces.append(interface)

            # Проверяем на Hamachi
            elif 'hamachi' in name:
                interface['type'] = 'hamachi'
                interface['priority'] = 9
                vpn_interfaces.append(interface)

            # Проверяем на другие VPN (OpenVPN, WireGuard и т.д.)
            elif any(vpn_keyword in name for vpn_keyword in ['vpn', 'tun', 'tap', 'wg']):
                interface['type'] = 'vpn'
                interface['priority'] = 8
                vpn_interfaces.append(interface)

            # Проверяем на виртуальные адаптеры
            elif any(virtual_keyword in name for virtual_keyword in ['virtual', 'vmware', 'virtualbox']):
                interface['type'] = 'virtual'
                interface['priority'] = 5
                vpn_interfaces.append(interface)

            # Проверяем на локальные сети (192.168.x.x, 10.x.x.x, 172.16-31.x.x)
            elif ip.startswith(('192.168.', '10.', '172.')):
                interface['type'] = 'lan'
                interface['priority'] = 7
                vpn_interfaces.append(interface)

        # Сортируем по приоритету (чем выше, тем лучше)
        vpn_interfaces.sort(key=lambda x: x.get('priority', 0), reverse=True)
        return vpn_interfaces

    def detect_optimal_host(self, preferred_interface: str = None) -> Tuple[str, int]:
        """Определить оптимальный хост и порт для сервера"""
        interfaces = self.get_all_interfaces()
        vpn_interfaces = self.detect_vpn_interfaces(interfaces)

        # Если указан предпочтительный интерфейс
        if preferred_interface:
            for interface in interfaces:
                if preferred_interface.lower() in interface.get('name', '').lower():
                    if 'ip' in interface:
                        return interface['ip'], 5555

        # Сначала пробуем VPN интерфейсы
        test_port = 5555
        for interface in vpn_interfaces:
            if 'ip' in interface:
                try:
                    test_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    test_socket.bind((interface['ip'], test_port))
                    test_socket.close()
                    self.logger.info(f"Выбран VPN интерфейс: {interface.get('name', 'Unknown')} - {interface['ip']}")
                    return interface['ip'], test_port
                except OSError:
                    continue

        # Затем пробуем обычные интерфейсы
        for interface in interfaces:
            if 'ip' in interface:
                try:
                    test_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    test_socket.bind((interface['ip'], test_port))
                    test_socket.close()
                    self.logger.info(f"Выбран обычный интерфейс: {interface.get('name', 'Unknown')} - {interface['ip']}")
                    return interface['ip'], test_port
                except OSError:
                    continue

        # Запасной вариант - localhost
        self.logger.warning("Не удалось найти подходящий интерфейс, используем localhost")
        return "127.0.0.1", test_port

    def print_available_interfaces(self):
        """Вывести список доступных интерфейсов"""
        interfaces = self.get_all_interfaces()
        vpn_interfaces = self.detect_vpn_interfaces(interfaces)

        print("\n=== ДОСТУПНЫЕ СЕТЕВЫЕ ИНТЕРФЕЙСЫ ===")

        if vpn_interfaces:
            print("\n🔥 VPN интерфейсы (рекомендуется):")
            for interface in vpn_interfaces:
                ip = interface.get('ip', 'N/A')
                name = interface.get('name', 'Unknown')
                interface_type = interface.get('type', 'unknown')
                print(f"  {name} - {ip} [{interface_type}]")

        print("\n🌐 Все интерфейсы:")
        for interface in interfaces:
            ip = interface.get('ip', 'N/A')
            name = interface.get('name', 'Unknown')
            print(f"  {name} - {ip}")

        print("\n💡 Для выбора интерфейса укажите его имя при запуске:")
        print("   python server.py --interface 'Radmin VPN'")
        print("   python client.py --interface 'Radmin VPN'")

    def generate_client_config(self, server_host: str, server_port: int) -> Dict[str, str]:
        """Сгенерировать конфигурацию для клиента"""
        return {
            'server_host': server_host,
            'server_port': server_port,
            'local_ip': self.get_local_ip(),
            'interfaces': json.dumps(self.get_all_interfaces())
        }

# Глобальный экземпляр детектора
detector = NetworkDetector()

def get_server_config(preferred_interface: str = None) -> Dict[str, str]:
    """Получить конфигурацию сервера с автоопределением"""
    host, port = detector.detect_optimal_host(preferred_interface)
    return {
        'host': host,
        'port': port,
        'bind_address': '0.0.0.0',  # Привязка ко всем интерфейсам
        'interface': preferred_interface or 'auto'
    }

def get_client_config(preferred_interface: str = None) -> Dict[str, str]:
    """Получить конфигурацию клиента с автоопределением"""
    host, port = detector.detect_optimal_host(preferred_interface)
    return detector.generate_client_config(host, port)
