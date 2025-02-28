import subprocess
import configparser
import os
import getpass
from colorama import Fore, init
import asyncio
import logging

init()

# Оставляем только нужные константы
CONFIG_PATH = '\\\\srv-edolog-dcb\\Parsing\\config-deshurka-sed.ini'
LOG_PATH = '\\\\srv-edolog-dcb\\Parsing\\degurkaSED.log'

config = configparser.ConfigParser()

try:
    config.read(CONFIG_PATH, encoding='utf-8')
    cod = config.get('SERVER', 'COD')
except Exception as e:
    logging.critical(f"Failed to read configuration: {e}")
    print(Fore.RED + "Ошибка чтения конфигурации" + Fore.RESET)
    exit(1)

username = getpass.getuser()
domain = os.environ['USERDOMAIN']
full_username = f"{domain}\\{username}"

logging.basicConfig(filename=LOG_PATH, level=logging.DEBUG, 
                    format='%(asctime)s - %(levelname)s - %(message)s', encoding='utf-8')

async def start_task(task_name, server_name):
    if not task_name or not server_name:
        logging.error("Отсутствует имя задачи или сервера")
        return False

    server_short_name = server_name.split('\\')[-1]
    
    username = "t_sed_degurniy"
    password = "da0T8eQVeEi9Yv"
    
    try:
        # Проверяем доступность по короткому имени
        ping_command = f'ping -n 1 -w 1000 {server_short_name}'
        try:
            ping_output = subprocess.check_output(ping_command, shell=True, stderr=subprocess.STDOUT)
            logging.info(f"Сервер {server_short_name} доступен: {ping_output.decode('cp866', errors='ignore').strip()}")
        except subprocess.CalledProcessError as e:
            logging.error(f"Сервер {server_short_name} недоступен: {e.output.decode('cp866', errors='ignore')}")
            return False

        # Выполняем основную команду
        command = f'schtasks /Run /S {server_short_name} -U {username} -P {password} /TN "{task_name}"'
        logging.info(f"Выполняется команда для {task_name} на сервере {server_short_name}")
        
        output = subprocess.check_output(
            command,
            shell=True,
            stderr=subprocess.STDOUT,
            timeout=60
        )

        decoded_output = output.decode('cp866', errors='ignore')
        logging.info(f"Результат выполнения {task_name} на {server_short_name}: {decoded_output.strip()}")
        return True

    except subprocess.CalledProcessError as e:
        error_output = e.output.decode('cp866', errors='ignore')
        if ("уже остановлена" in error_output.lower() or 
            "already stopped" in error_output.lower() or
            "уже запущена" in error_output.lower() or
            "already running" in error_output.lower()):
            logging.info(f"Сервис {task_name} на {server_short_name} уже в требуемом состоянии: {error_output.strip()}")
            return True
            
        logging.error(f"Ошибка выполнения {task_name} на {server_short_name}: {error_output.strip()}")
        return False
    except subprocess.TimeoutExpired:
        logging.error(f"Таймаут выполнения команды {task_name} на {server_short_name} (60 сек)")
        return False
    except Exception as e:
        logging.error(f"Системная ошибка при выполнении {task_name} на {server_short_name}: {str(e)}")
        return False

logging.info(f"{full_username} - Запустил скрипт перезапуска IIS")

# Проверка на дурака
confirm = input(f"Перезапустить Edoc IIS и XDE IIS ? Y/n: ")
if confirm.lower() != 'y':
    print("Отмена.")
    logging.info("Script execution cancelled by user.")
    exit()

async def loading_indicator(duration, message):
    """Показывает индикатор загрузки с сообщением"""
    width = 30
    delay = 0.1
    steps = int(duration / delay)
    
    for i in range(steps):
        pos = i % (width - 3)
        bar = ' ' * pos + '<=>' + ' ' * (width - 3 - pos)
        print(f"\r{Fore.CYAN}[{bar}] {message}{Fore.RESET}", end='', flush=True)
        await asyncio.sleep(delay)
    print("\r" + " " * (width + len(message) + 3) + "\r", end='')  # Очистка строки

async def main():
    server_edoc = f"\\\\srv-edoc1-{cod}"
    server_xde = f"\\\\srv-xdeapp-{cod}"
    
    max_retries = 3
    retry_delay = 5  # seconds

    async def execute_task_with_retry(task_name, server_name, action_description):
        logging.info(f"Начало процесса: {action_description} ({task_name} на {server_name})")
        print(Fore.YELLOW + f"\nНачало процесса: {action_description}" + Fore.RESET)
        
        for attempt in range(max_retries):
            if attempt > 0:
                logging.info(f"Повторная попытка {attempt + 1}/{max_retries} для {task_name}")
                print(Fore.YELLOW + f"Повторная попытка {attempt + 1}/{max_retries}" + Fore.RESET)
                await asyncio.sleep(retry_delay)
            
            if await start_task(task_name, server_name):
                wait_time = 20  # Фиксированное время ожидания
                logging.info(f"Ожидание {wait_time} секунд после выполнения {task_name}")
                await loading_indicator(wait_time, action_description)
                logging.info(f"Успешно завершено: {action_description}")
                print(Fore.GREEN + f"Успешно: {action_description}" + Fore.RESET)
                return True
            
            if attempt < max_retries - 1:
                continue
        
        error_msg = f"Не удалось выполнить {action_description} после {max_retries} попыток"
        logging.error(error_msg)
        print(Fore.RED + f"\n{error_msg}" + Fore.RESET)
        return False

    # Остановка EDOC
    if not await execute_task_with_retry('IIS_STOP', server_edoc, 'Остановка IIS Edoc'):
        print(Fore.RED + "\nОшибка остановки IIS EDOC" + Fore.RESET)
        return

    # Убираем отдельные вызовы loading_indicator, так как они теперь внутри execute_task_with_retry
    
    # Остановка xDE
    if not await execute_task_with_retry('IIS_STOP', server_xde, 'Остановка IIS xDE'):
        print(Fore.RED + "\nОшибка остановки IIS xDE" + Fore.RESET)
        return

    # Запуск EDOC
    if not await execute_task_with_retry('IIS_START', server_edoc, 'Запуск IIS Edoc'):
        print(Fore.RED + "\nОшибка запуска IIS EDOC" + Fore.RESET)
        return

    # Запуск xDE
    if not await execute_task_with_retry('IIS_START', server_xde, 'Запуск IIS xDE'):
        print(Fore.RED + "\nОшибка запуска IIS xDE" + Fore.RESET)
        return

    print(Fore.GREEN + "\nВсе операции успешно завершены" + Fore.RESET)
    logging.info("Script finished successfully.")
    
    input(Fore.BLUE + "Нажмите любую клавишу для завершения..." + Fore.RESET)

if __name__ == "__main__":
    asyncio.run(main())