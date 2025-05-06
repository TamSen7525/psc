import os
import sys
import time
from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.edge.service import Service as EdgeService
from selenium.webdriver.edge.options import Options as EdgeOptions
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from bs4 import BeautifulSoup
import re
from datetime import datetime, timedelta, timezone
from pymongo import MongoClient, errors # Импорт pymongo

# Загружаем переменные окружения из .env файла
load_dotenv()

INSTAGRAM_LOGIN = os.getenv("INSTAGRAM_LOGIN")
INSTAGRAM_PASSWORD = os.getenv("INSTAGRAM_PASSWORD")

# Настройки MongoDB (значения по умолчанию, если нет в .env)
MONGO_CONNECTION_STRING = os.getenv("MONGO_CONNECTION_STRING", "mongodb://localhost:27017/")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "instagram_parser_db")
MONGO_COLLECTION_NAME = os.getenv("MONGO_COLLECTION_NAME", "giveaways")


# Путь к драйверу Edge
DRIVER_PATH = os.path.join(os.path.dirname(__file__), 'msedgedriver.exe')

if not INSTAGRAM_LOGIN or not INSTAGRAM_PASSWORD:
    print("Ошибка: Переменные INSTAGRAM_LOGIN или INSTAGRAM_PASSWORD не найдены в .env файле.")
    sys.exit()

if not os.path.exists(DRIVER_PATH):
    print(f"Ошибка: Драйвер Edge не найден по пути: {DRIVER_PATH}")
    sys.exit()

# Список ключевых слов для поиска - ПЕРЕМЕЩАЕМ СЮДА
KEYWORDS = [
    "розыгрыш призов", "Розыгрыш подарков", "Розыгрыш денег", "Деньги бесплатно",
    "Подарки бесплатно", "Раздача подарков", "Дарю", "Дарим", "Дарю подарок",
    "Дарю приз", "Дарим подарок", "Дарим приз", "Дарим сертификат", "Дарю сертификат",
    "Раздача денег", "Раздача призов", "Проведение конкурса", "Итоги конкурса",
    "Итоги акции", "Итоги розыгрыша", "Конкурс", "Конкурсы", "Бесплатно",
    "Получи деньги", "Получи подарок", "Получи бесплатно", "Подарок", "Подарки",
    "Участвуй в акции", "Участвуйте в акции", "Участвуй в розыгрыше",
    "Участие в розыгрыше", "Участие в акции", "Акция", "Акции", "Мега акция",
    "Бесплатно", "Призы", "Приз", "Главный приз", "Выигрывай приз", "Выигрывай призы",
    "Выигрывайте приз", "Выигрывайте призы", "Халява", "Халявный", "На халяву",
    "Выиграй", "Скидка 100"
]

# Максимальный возраст поста в днях
MAX_POST_AGE_DAYS = 14

# --- Подключение к MongoDB ---
mongo_client = None
db = None
collection = None
try:
    print(f"Подключение к MongoDB: {MONGO_CONNECTION_STRING}...")
    mongo_client = MongoClient(MONGO_CONNECTION_STRING, serverSelectionTimeoutMS=5000)
    # Проверка соединения
    mongo_client.admin.command('ping')
    db = mongo_client[MONGO_DB_NAME]
    collection = db[MONGO_COLLECTION_NAME]
    print(f"Успешно подключено к MongoDB. База: '{MONGO_DB_NAME}', Коллекция: '{MONGO_COLLECTION_NAME}'.")
except errors.ConnectionFailure as e:
    print(f"Ошибка подключения к MongoDB: {e}")
    sys.exit("Не удалось подключиться к MongoDB. Проверьте строку подключения и доступность сервера.")
except Exception as e:
    print(f"Произошла непредвиденная ошибка при подключении к MongoDB: {e}")
    sys.exit("Ошибка инициализации MongoDB.")


# Настройки Edge
edge_options = EdgeOptions()
edge_options.add_argument("--disable-gpu")
edge_options.add_argument("--window-size=1920,1080")
edge_options.add_argument("--lang=ru-RU")

# Инициализация сервиса драйвера
edge_service = EdgeService(executable_path=DRIVER_PATH)


# --- Инициализация Selenium ---
print("Запуск браузера Edge...")
driver = webdriver.Edge(service=edge_service, options=edge_options)
wait_page_load = WebDriverWait(driver, 15) # Увеличил ожидание до 15

try:
    # --- Логин в Instagram ---
    print("Переход на страницу входа Instagram...")
    driver.get("https://www.instagram.com/accounts/login/")

    # Ожидание и обработка куки (селекторы могут измениться)
    wait = WebDriverWait(driver, 10) # Ждем до 10 секунд
    try:
        # Пробуем найти кнопку "Разрешить все файлы cookie" (текст может отличаться)
        # Используем XPath для поиска кнопки, содержащей нужный текст
        cookie_button_xpath = "//button[contains(text(), 'Разрешить') or contains(text(), 'Allow')]"
        cookie_button = wait.until(EC.element_to_be_clickable((By.XPATH, cookie_button_xpath)))
        print("Найдена кнопка Cookie. Нажимаем...")
        cookie_button.click()
        time.sleep(2) # Небольшая пауза после нажатия
    except Exception as e:
        print("Не удалось найти или нажать кнопку Cookie (возможно, ее нет или селектор изменился):", e)

    # Ввод логина
    try:
        print("Ввод логина...")
        username_field = wait.until(EC.visibility_of_element_located((By.NAME, "username")))
        username_field.send_keys(INSTAGRAM_LOGIN)
        time.sleep(0.5) # Короткая пауза
    except Exception as e:
        print("Не удалось найти поле логина:", e)
        raise # Передаем ошибку выше, чтобы сработал finally

    # Ввод пароля
    try:
        print("Ввод пароля...")
        password_field = wait.until(EC.visibility_of_element_located((By.NAME, "password")))
        password_field.send_keys(INSTAGRAM_PASSWORD)
        time.sleep(0.5) # Короткая пауза
    except Exception as e:
        print("Не удалось найти поле пароля:", e)
        raise # Передаем ошибку выше

    # Нажатие кнопки входа
    try:
        print("Нажатие кнопки 'Войти'...")
        # Кнопка входа часто <button type="submit"> или содержит текст "Log in" / "Войти"
        login_button_xpath = "//button[@type='submit' and descendant::div[contains(text(), 'Войти') or contains(text(), 'Log in')]]"
        login_button = wait.until(EC.element_to_be_clickable((By.XPATH, login_button_xpath)))
        login_button.click()
        print("Вход выполнен. Ожидание загрузки страницы...")
        time.sleep(5) # Пауза для загрузки главной страницы
    except Exception as e:
        print("Не удалось найти или нажать кнопку входа:", e)
        raise # Передаем ошибку выше

    # Явное ожидание загрузки главной страницы после логина
    print("Ожидание загрузки главной страницы...")
    main_page_element_xpath = "//main[@role='main']" # Ждем появления основного контента
    try:
        wait_page_load.until(EC.presence_of_element_located((By.XPATH, main_page_element_xpath)))
        print("Главная страница загружена.")
        time.sleep(2) # Небольшая доп. пауза на всякий случай
    except Exception as e:
        print(f"Не удалось дождаться загрузки главной страницы: {e}")
        raise # Передаем ошибку выше


    # --- Начало логики парсинга по прямым ссылкам ---
    total_posts_saved = 0
    for keyword in KEYWORDS:
        # Формируем имя тега: убираем пробелы и переводим в нижний регистр для надежности
        tag_name = keyword.replace(' ', '').lower()
        if not tag_name:
            continue # Пропускаем пустые ключевые слова, если есть

        hashtag_url = f"https://www.instagram.com/explore/tags/{tag_name}/"
        print(f"\n--- Переход на страницу хештега: #{tag_name} ---")
        print(f"URL: {hashtag_url}")

        try:
            driver.get(hashtag_url)
            # Ждем загрузки сетки постов (можно улучшить селектор)
            posts_grid_xpath = "//main[@role='main']//a[contains(@href, '/p/')]"
            wait_page_load.until(EC.presence_of_element_located((By.XPATH, posts_grid_xpath)))
            print(f"Страница #{tag_name} загружена.")
            time.sleep(3) # Дополнительная пауза на прогрузку контента

            # --- Сбор ссылок на посты ---
            print(f"Ищем ссылки на посты для #{tag_name}...")
            post_links_elements = []
            post_urls = []
            try:
                # Ищем все ссылки, ведущие на посты, внутри основного блока main
                post_links_xpath = "//main[@role='main']//a[contains(@href, '/p/')]"
                wait_page_load.until(EC.presence_of_element_located((By.XPATH, post_links_xpath)))
                post_links_elements = driver.find_elements(By.XPATH, post_links_xpath)

                if not post_links_elements:
                    print(f"Не найдено ссылок на посты для #{tag_name}.")
                else:
                    # Ограничиваем количество первыми 15 постами
                    limit = 15
                    print(f"Найдено {len(post_links_elements)} ссылок. Берем первые {min(len(post_links_elements), limit)}.")
                    for link_element in post_links_elements[:limit]:
                        try:
                            post_url = link_element.get_attribute('href')
                            if post_url and post_url not in post_urls: # Проверяем что URL не пустой и уникальный
                                post_urls.append(post_url)
                        except Exception as link_e:
                            print(f"Ошибка при извлечении href из элемента: {link_e}")

                    print(f"Собраны URL постов ({len(post_urls)}):")
                    # for url in post_urls: # Убрал вывод URL здесь
                    #     print(f"- {url}")

            except Exception as find_e:
                print(f"Ошибка при поиске ссылок на посты для #{tag_name}: {find_e}")
                continue # Пропускаем этот хештег, если не нашли ссылок


            # --- Обработка найденных постов ---
            print(f"--- Обработка {len(post_urls)} постов для #{tag_name} ---")
            # posts_data = [] # Список больше не нужен

            for post_url in post_urls:
                print(f"Обработка поста: {post_url}") # Немного изменил сообщение
                post_text = ""
                datetime_str = ""
                post_date_obj = None

                try: # Начало try для обработки одного поста
                    driver.get(post_url)

                    # 1. Ждем элемент времени публикации
                    post_time_xpath = "//time[@datetime]"
                    time_element = wait_page_load.until(
                        EC.visibility_of_element_located((By.XPATH, post_time_xpath))
                    )
                    datetime_str = time_element.get_attribute("datetime")

                    # Пытаемся преобразовать строку в datetime объект (с учетом UTC)
                    try:
                        post_date_obj = datetime.fromisoformat(datetime_str.replace('Z', '+00:00'))
                        if post_date_obj.tzinfo is None:
                            post_date_obj = post_date_obj.replace(tzinfo=timezone.utc)
                    except ValueError as date_parse_e:
                        print(f"   ! Ошибка парсинга даты '{datetime_str}': {date_parse_e}")
                        continue # Пропускаем пост

                    time.sleep(1)

                    # 2. Получаем HTML и парсим с BeautifulSoup
                    html_source = driver.page_source
                    soup = BeautifulSoup(html_source, 'html.parser')

                    # 3. Ищем текст в мета-теге og:description
                    og_description_tag = soup.find('meta', property='og:description')
                    if og_description_tag and og_description_tag.get('content'):
                        content = og_description_tag.get('content')
                        # Используем нежадный regex
                        match = re.search(r':\s*"(.*?)"', content, re.DOTALL)
                        if match:
                            post_text = match.group(1).strip()
                            # print(f"Текст поста (og:desc): {post_text[:200]}...") # Убрал вывод текста
                        else:
                            print("   ! Не удалось извлечь текст из og:description (regex не сработал).")
                    else:
                        print("   ! Не найден мета-тег og:description.")


                    # 4. Проверяем актуальность поста
                    is_recent = False
                    if post_date_obj:
                        cutoff_date = datetime.now(timezone.utc) - timedelta(days=MAX_POST_AGE_DAYS)
                        if post_date_obj >= cutoff_date:
                            is_recent = True
                            # print("Пост актуальный.") # Убрал вывод
                        # else:
                            # print("Пост слишком старый.") # Убрал вывод

                    # 5. Сохраняем данные в MongoDB, если пост актуальный и текст найден
                    if is_recent and post_text and post_date_obj:
                        document_to_save = {
                            "url": post_url,
                            "text": post_text,
                            "parsed_date_utc": post_date_obj, # Сохраняем как datetime объект
                            "keyword": keyword, # Добавляем ключевое слово, по которому нашли
                            "hashtag": tag_name, # И сам хештег
                            "scraped_at_utc": datetime.now(timezone.utc) # Время парсинга
                        }
                        try:
                            # Используем upsert=True, чтобы вставить, если URL нет, или обновить, если есть
                            update_result = collection.update_one(
                                {"url": post_url},
                                {"$set": document_to_save},
                                upsert=True
                            )
                            if update_result.upserted_id:
                                print(f"   -> Новый пост сохранен в MongoDB.")
                                total_posts_saved += 1
                            elif update_result.modified_count > 0:
                                print(f"   -> Данные поста обновлены в MongoDB.")
                            # else: # Нет смысла выводить, если ничего не изменилось
                            #     print(f"   -> Пост уже существует в MongoDB без изменений (URL: {post_url})\")

                        except errors.PyMongoError as mongo_e:
                            print(f"   !!! Ошибка записи в MongoDB для поста {post_url}: {mongo_e}")
                    elif not is_recent:
                         print("   -> Пост пропущен (старый).")
                    elif not post_text:
                         print("   -> Пост пропущен (текст не найден).")


                    time.sleep(2) # Пауза между постами

                # Конец try для обработки одного поста
                except TimeoutException: # ИСПОЛЬЗУЕМ TimeoutException из Selenium
                     print(f"   ! Timeout при ожидании элемента <time> для поста {post_url}. Пропуск.")
                     continue # К следующему посту
                except Exception as post_e: # Отлов других ошибок при обработке поста
                    print(f"   ! Не удалось обработать пост {post_url}: {post_e}")
                    continue # К следующему посту внутри хештега

            print(f"--- Обработка постов для #{tag_name} завершена. ---")

        # Конец try для обработки страницы хэштега
        except TimeoutException: # ИСПОЛЬЗUЕМ TimeoutException из Selenium
             print(f"   ! Timeout при ожидании сетки постов для хештега #{tag_name}. Пропуск хештега.")
             continue # К следующему хештегу
        except Exception as page_e: # Отлов других ошибок на странице хэштега
            print(f"   ! Не удалось загрузить или обработать страницу для хештега #{tag_name}: {page_e}")
            continue # К следующему хештегу

    print(f"\nПарсинг завершен. Всего новых постов сохранено: {total_posts_saved}")

except Exception as main_e:
    print(f"Произошла критическая ошибка: {main_e}")
    try:
        # Пытаемся сделать скриншот только если драйвер еще существует
        if 'driver' in locals() and driver:
            driver.save_screenshot("parser_critical_error.png")
            print("Скриншот ошибки сохранен как parser_critical_error.png")
    except Exception as screenshot_e:
        print(f"Не удалось сохранить скриншот: {screenshot_e}")

finally:
    # --- Закрытие соединений ---
    if 'driver' in locals() and driver:
        print("Закрытие браузера.")
        driver.quit()
    if mongo_client:
        print("Закрытие соединения с MongoDB.")
        mongo_client.close()
    print("Скрипт завершен.")
