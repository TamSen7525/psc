import sys
import time
from datetime import datetime, timezone, timedelta
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from bs4 import BeautifulSoup
import re
from pymongo import MongoClient, errors
from config import *
from keywords import KEYWORDS
import random
import os

# Проверка наличия учетных данных
if not INSTAGRAM_LOGIN or not INSTAGRAM_PASSWORD:
    print("Ошибка: Переменные INSTAGRAM_LOGIN или INSTAGRAM_PASSWORD не найдены в .env файле.")
    sys.exit()

# --- Подключение к MongoDB ---
mongo_client = None
db = None
collection = None
try:
    print(f"Подключение к MongoDB: {MONGO_CONNECTION_STRING}...")
    mongo_client = MongoClient(MONGO_CONNECTION_STRING, serverSelectionTimeoutMS=5000)
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

def setup_driver(headless=True, profile_directory_name=None):
    """Создание и настройка драйвера Chrome"""
    options = uc.ChromeOptions()
    if headless:
        options.add_argument('--headless')
    
    if profile_directory_name:
        # Создаем или используем существующий каталог профиля в текущей директории скрипта
        # Это поможет изолировать сессии, если undetected-chromedriver сам не справляется
        current_script_path = os.path.dirname(os.path.abspath(__file__))
        profile_path = os.path.join(current_script_path, profile_directory_name)
        options.add_argument(f"--user-data-dir={profile_path}")
        print(f"Для этого экземпляра браузера будет использоваться профиль: {profile_path}")

    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--window-size=1920,1080')
    options.add_argument('--lang=ru-RU')
    return uc.Chrome(options=options)

def login_to_instagram(driver):
    """Логин в Instagram"""
    print("Переход на страницу входа Instagram...")
    driver.get("https://www.instagram.com/accounts/login/")
    wait = WebDriverWait(driver, 10)

    try:
        # Обработка куки
        cookie_button_xpath = "//button[contains(text(), 'Разрешить') or contains(text(), 'Allow')]"
        cookie_button = wait.until(EC.element_to_be_clickable((By.XPATH, cookie_button_xpath)))
        cookie_button.click()
        time.sleep(2)
    except Exception as e:
        print("Не удалось найти или нажать кнопку Cookie:", e)

    # Ввод логина и пароля
    try:
        username_field = wait.until(EC.visibility_of_element_located((By.NAME, "username")))
        username_field.send_keys(INSTAGRAM_LOGIN)
        time.sleep(0.5)

        password_field = wait.until(EC.visibility_of_element_located((By.NAME, "password")))
        password_field.send_keys(INSTAGRAM_PASSWORD)
        time.sleep(1)

        # Более точный XPath для кнопки входа, проверяющий также текст
        login_button_xpath = "//button[@type='submit' and (descendant::div[contains(text(),'Войти')] or descendant::div[contains(text(),'Log In')] or contains(text(),'Войти') or contains(text(),'Log In'))]"
        # Увеличим ожидание для кнопки входа
        login_button = WebDriverWait(driver, 15).until(EC.element_to_be_clickable((By.XPATH, login_button_xpath)))
        login_button.click()
        print("Кнопка входа нажата.")

        # ОЖИДАНИЕ ПОСЛЕ ВХОДА: Ждем появления элемента, характерного для главной страницы
        # Например, кнопка "Не сейчас" для уведомлений или поле поиска
        try:
            print("Ожидание загрузки главной страницы после входа (до 30 секунд)...")
            # Попробуем подождать кнопку "Не сейчас" (может отличаться в зависимости от языка интерфейса)
            # или какой-либо другой элемент, например, иконку профиля или поле поиска
            # XPath для "Не сейчас" может быть '//button[text()="Не сейчас"]' или '//button[text()="Not Now"]'
            # Более общий подход - ждать элемент, который точно есть на главной странице, например, навигационную панель
            # WebDriverWait(driver, 30).until(
            #    EC.presence_of_element_located((By.XPATH, "//div[text()='Не сейчас']/parent::button | //button[text()='Not Now'] | //nav"))
            # )
            # Простой вариант - подождать появления кнопки "Сохранить данные для входа" или "Не сейчас" для уведомлений
            # Эти селекторы могут потребовать корректировки
            save_login_info_button_xpath = "//button[text()='Сохранить данные'] | //button[text()='Save Info']"
            not_now_button_xpath = "//button[text()='Не сейчас'] | //button[text()='Not Now'] | //div[@role='dialog']//button[contains(text(),'Not Now') or contains(text(),'Не сейчас')]" # Более широкий поиск кнопки "Не сейчас" в диалогах

            # Ждем, пока либо кнопка "Сохранить данные", либо "Не сейчас" станет кликабельной, или просто появится
            # Используем any_of для ожидания одного из нескольких условий
            WebDriverWait(driver, 10).until(
                EC.any_of(
                    EC.element_to_be_clickable((By.XPATH, save_login_info_button_xpath)),
                    EC.element_to_be_clickable((By.XPATH, not_now_button_xpath)),
                    EC.presence_of_element_located((By.XPATH, "//nav")) # Общий навигационный элемент
                )
            )
            print("Главная страница загружена (или появилось диалоговое окно).")

            # Попытка нажать "Не сейчас", если такое окно появилось (для уведомлений)
            try:
                not_now_buttons = driver.find_elements(By.XPATH, not_now_button_xpath)
                for btn in not_now_buttons:
                    if btn.is_displayed() and btn.is_enabled():
                        print("Найдена кнопка 'Не сейчас' для уведомлений, пытаюсь нажать...")
                        btn.click()
                        print("Кнопка 'Не сейчас' нажата.")
                        # Ждем немного, чтобы диалог закрылся
                        WebDriverWait(driver, 10).until_not(EC.presence_of_element_located((By.XPATH, "//div[@role='dialog']")))
                        print("Диалог уведомлений закрыт.")
                        break # Выходим после первого успешного нажатия
            except Exception as e_dialog:
                print(f"Не удалось нажать 'Не сейчас' или диалог не появился: {e_dialog}")

        except TimeoutException:
            print("Не удалось дождаться характерного элемента главной страницы или диалогового окна после входа в течение 30 секунд.")
            # Можно добавить скриншот для отладки
            # driver.save_screenshot("debug_after_login_timeout.png")
            # return None # Если считаем это критической ошибкой для функции логина

        print("Вход в Instagram выполнен успешно.")
        return driver
    except TimeoutException as e:
        print(f"Ошибка при входе в Instagram или ожидании элементов: {e}")
    except Exception as e:
        print(f"Непредвиденная ошибка в процессе входа: {e}")
    return None

def get_post_text(driver, post_url):
    """Получение текста поста"""
    try:
        driver.get(post_url)
        wait = WebDriverWait(driver, 10)
        
        # Ждем загрузки текста поста
        post_text_element = wait.until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "h1"))
        )
        return post_text_element.text
    except Exception as e:
        print(f"Ошибка при получении текста поста {post_url}: {e}")
        return None

def search_posts_by_hashtag(driver, keyword):
    """Поиск постов по хештегу и сбор ссылок на них."""
    tag_name = keyword.replace(' ', '').lower()
    if not tag_name:
        print(f"Ключевое слово '{keyword}' пустое или некорректное, пропускаем.")
        return []

    hashtag_url = f"https://www.instagram.com/explore/tags/{tag_name}/"
    print(f"--- Переход на страницу хештега: #{tag_name} ---")

    post_links = []
    try:
        driver.get(hashtag_url)
        wait = WebDriverWait(driver, 20) # Увеличим ожидание для страницы хештега
        
        # Ждем загрузки сетки постов или сообщения "Ничего не найдено"
        posts_grid_xpath = "//main[@role='main']//a[contains(@href, '/p/')]"
        # XPath для случая, если посты не найдены (текст может отличаться)
        no_results_xpath = "//span[contains(text(),'Ничего не найдено') or contains(text(),'No posts yet') or contains(text(),'К сожалению, по вашему запросу ничего не найдено')]"

        try:
            # Пробуем дождаться постов
            wait.until(EC.presence_of_element_located((By.XPATH, posts_grid_xpath)))
            print(f"Посты для #{tag_name} найдены, собираем ссылки...")
            
            # Прокрутка страницы для загрузки большего количества постов (опционально, можно настроить)
            # last_height = driver.execute_script("return document.body.scrollHeight")
            # for _ in range(2): # Прокрутить несколько раз
            #     driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            #     time.sleep(2) # Дать время на загрузку
            #     new_height = driver.execute_script("return document.body.scrollHeight")
            #     if new_height == last_height:
            #         break
            #     last_height = new_height
            # time.sleep(1) # Дополнительная пауза после прокрутки

            post_elements = driver.find_elements(By.XPATH, posts_grid_xpath)
            
            for element in post_elements[:20]:  # Берем, например, первые 20 постов
                post_url = element.get_attribute('href')
                if post_url and post_url not in post_links:
                    post_links.append(post_url)
            print(f"Найдено {len(post_links)} ссылок на посты для #{tag_name}")

        except TimeoutException:
            # Если посты не найдены в течение времени ожидания, проверяем, есть ли сообщение "Ничего не найдено"
            try:
                driver.find_element(By.XPATH, no_results_xpath)
                print(f"Посты по хештегу #{tag_name} не найдены (сообщение 'Ничего не найдено').")
            except:
                print(f"Не удалось загрузить посты для #{tag_name} (тайм-аут) и не найдено сообщение 'Ничего не найдено'.")
                # driver.save_screenshot(f"debug_hashtag_{tag_name}_timeout.png") # Для отладки
        
    except Exception as e:
        print(f"Ошибка при обработке хештега #{tag_name}: {e}")
        # driver.save_screenshot(f"debug_hashtag_{tag_name}_error.png") # Для отладки
        
    return list(set(post_links)) # Возвращаем уникальные ссылки

def get_post_data_from_page(driver, post_url):
    """Получение текста и даты поста со страницы"""
    post_text = ""
    post_date = None
    
    try:
        print(f"Загрузка страницы поста: {post_url}")
        driver.get(post_url)
        # Увеличиваем ожидание для страницы поста, так как она может быть "тяжелой"
        # и элементы могут появляться не сразу.
        wait = WebDriverWait(driver, 20) # Увеличено до 20 секунд

        # 1. Приоритетное извлечение текста из мета-тегов
        try:
            # Сначала ищем og:description
            try:
                meta_og_desc_element = driver.find_element(By.XPATH, "//meta[@property='og:description']")
                meta_og_description = meta_og_desc_element.get_attribute("content")
                if meta_og_description and meta_og_description.strip():
                    # Попытка извлечь текст после двоеточия и в кавычках (самый частый паттерн)
                    match = re.search(r':\\s*"(.*)"\\s*$', meta_og_description, re.DOTALL)
                    if match and match.group(1).strip():
                        post_text = match.group(1).strip()
                        print(f"Извлечен текст поста из meta[og:description] (регекс): {post_text[:100]}...")
                    # Если регекс не сработал, пробуем более общий метод: взять все, что в первых внешних кавычках
                    elif '"' in meta_og_description:
                        try:
                            # Извлекаем текст между первой и последней кавычкой, если они есть
                            # Это может быть менее точно, но лучше, чем ничего
                            parts = meta_og_description.split('"', 2)
                            if len(parts) >= 2:
                                potential_text = parts[1]
                                # Убираем возможный хвост "N likes, M comments..." если он в начале
                                # Это очень грубый фильтр
                                if "likes" not in potential_text[:50].lower() and "comments" not in potential_text[:50].lower():
                                    post_text = potential_text.strip()
                                    print(f"Извлечен текст поста из meta[og:description] (общий анализ кавычек): {post_text[:100]}...")
                        except Exception: # Просто игнорируем ошибку, если разделение по кавычкам не удалось
                            pass 
            except Exception: # NoSuchElementException или другая ошибка для og:description
                print("Мета-тег og:description не найден или ошибка при его обработке.")
                pass # Просто продолжаем, если og:description не найден

            # Если текст не найден в og:description, ищем в name="description"
            if not post_text:
                try:
                    meta_desc_element = driver.find_element(By.XPATH, "//meta[@name='description']")
                    meta_description = meta_desc_element.get_attribute("content")
                    if meta_description and meta_description.strip():
                        match = re.search(r':\\s*"(.*)"\\s*$', meta_description, re.DOTALL)
                        if match and match.group(1).strip():
                            post_text = match.group(1).strip()
                            print(f"Извлечен текст поста из meta[name=description] (регекс): {post_text[:100]}...")
                        elif '"' in meta_description:
                            try:
                                parts = meta_description.split('"', 2)
                                if len(parts) >= 2:
                                    potential_text = parts[1]
                                    if "likes" not in potential_text[:50].lower() and "comments" not in potential_text[:50].lower():
                                        post_text = potential_text.strip()
                                        print(f"Извлечен текст поста из meta[name=description] (общий анализ кавычек): {post_text[:100]}...")
                            except Exception:
                                pass
                except Exception: # NoSuchElementException или другая ошибка для name="description"
                    print("Мета-тег name=description не найден или ошибка при его обработке.")
                    pass
                                
        except Exception as e_meta_outer:
            print(f"Общая ошибка при работе с мета-тегами: {e_meta_outer}")

        # 2. Резервное извлечение текста из <body>, если мета-теги не дали результата
        if not post_text:
            print("Текст не найден в мета-тегах, попытка извлечения из body...")
            post_text_candidates_xpath = "//article//h1 | //article//span[normalize-space(text())]"
            try:
                # Ждем появления хотя бы одного из кандидатов
                wait.until(EC.presence_of_element_located((By.XPATH, post_text_candidates_xpath)))
                post_text_elements = driver.find_elements(By.XPATH, post_text_candidates_xpath)
                
                longest_text_body = ""
                if post_text_elements:
                    for el in post_text_elements:
                        current_text = el.text.strip()
                        if current_text and len(current_text) > len(longest_text_body):
                            if len(current_text) > 20: 
                                longest_text_body = current_text
                    
                    if longest_text_body:
                        post_text = longest_text_body
                        print(f"Извлечен текст поста из body (самый длинный кандидат > 20 симв.): {post_text[:100]}...")
                    else:
                        for el in post_text_elements: # Берем первый непустой, если длинный не найден
                            current_text = el.text.strip()
                            if current_text:
                                post_text = current_text
                                print(f"Извлечен текст поста из body (первый непустой кандидат): {post_text[:100]}...")
                                break
                if not post_text: 
                    print(f"Текст поста не найден или пуст в body с XPath: {post_text_candidates_xpath}.")
            except TimeoutException:
                print(f"Тайм-аут при ожидании элементов текста в body для {post_url}")
            except Exception as e_body:
                 print(f"Ошибка при извлечении текста из body: {e_body}")

        # 3. Извлечение даты публикации
        try:
            date_element_xpath = "//main//a//time[@datetime]"
            # Ожидаем элемент с датой, если он есть
            date_element = wait.until(EC.presence_of_element_located((By.XPATH, date_element_xpath)))
            date_iso_string = date_element.get_attribute('datetime')
            if date_iso_string:
                post_date = datetime.fromisoformat(date_iso_string.replace('Z', '+00:00'))
                print(f"Извлечена дата поста: {post_date}")
            else:
                print(f"Атрибут datetime не найден для элемента time на {post_url} (XPath: {date_element_xpath})")
        except TimeoutException:
            print(f"Элемент <time> с датой не найден (тайм-аут) на странице {post_url} по XPath: {date_element_xpath}")
        except ValueError as ve:
            print(f"Ошибка конвертации строки даты: {ve}")
        except Exception as e_date: # Ловим другие возможные ошибки при работе с датой
            print(f"Непредвиденная ошибка при извлечении даты: {e_date}")

        # Возвращаем результат
        if not post_text and not post_date:
            print(f"Не удалось извлечь ни текст, ни дату для {post_url}")
            return None # Если ничего не извлекли
        
        # Если текст не извлечен, но есть дата (или наоборот), все равно возвращаем то, что есть
        return {'text': post_text if post_text else "Текст не извлечен", 'date': post_date}

    except TimeoutException: # Тайм-аут на уровне driver.get() или общего ожидания страницы
        print(f"Общий тайм-аут при загрузке страницы поста {post_url}")
        return None 
    except Exception as e_main_func:
        print(f"Критическая ошибка в get_post_data_from_page для {post_url}: {e_main_func}")
        return None

def main():
    total_posts_saved = 0
    driver = None 
    mongo_client_local = None

    try:
        # --- Подключение к MongoDB --- (перенесено внутрь try, чтобы закрывалось в finally)
        global mongo_client, db, collection # Объявляем, что будем использовать глобальные переменные
        try:
            print(f"Подключение к MongoDB: {MONGO_CONNECTION_STRING}...")
            mongo_client = MongoClient(MONGO_CONNECTION_STRING, serverSelectionTimeoutMS=5000)
            mongo_client.admin.command('ping')
            db = mongo_client[MONGO_DB_NAME]
            collection = db[MONGO_COLLECTION_NAME]
            mongo_client_local = mongo_client # Сохраняем ссылку для закрытия в finally
            print(f"Успешно подключено к MongoDB. База: '{MONGO_DB_NAME}', Коллекция: '{MONGO_COLLECTION_NAME}'.")
        except errors.ConnectionFailure as e_mongo_conn:
            print(f"Ошибка подключения к MongoDB: {e_mongo_conn}")
            sys.exit("Не удалось подключиться к MongoDB. Проверьте строку подключения и доступность сервера.")
        except Exception as e_mongo_init:
            print(f"Произошла непредвиденная ошибка при подключении к MongoDB: {e_mongo_init}")
            sys.exit("Ошибка инициализации MongoDB.")
        # --- Конец подключения к MongoDB ---

        print("Инициализация основного драйвера...")
        driver = setup_driver(headless=False)
        
        if not driver:
            print("Не удалось инициализировать драйвер. Завершение работы.")
            return

        print("\nЭтап 1: Вход в Instagram...")
        if not login_to_instagram(driver):
            print("Не удалось войти в Instagram. Завершение работы.")
            return

        print("\nЭтап 2: Сбор ссылок на посты по всем ключевым словам...")
        all_post_links = []
        for keyword in KEYWORDS:
            print(f"Поиск постов по ключевому слову: {keyword}")
            post_links_for_keyword = search_posts_by_hashtag(driver, keyword)
            if post_links_for_keyword:
                unique_new_links = [link for link in post_links_for_keyword if link not in all_post_links]
                if unique_new_links:
                    all_post_links.extend(unique_new_links)
                    print(f"Добавлено {len(unique_new_links)} новых уникальных ссылок для '{keyword}'. Всего собрано: {len(all_post_links)}")
                else:
                    print(f"Для '{keyword}' не найдено новых уникальных ссылок.")
            else:
                print(f"Для '{keyword}' ссылки не найдены.")
            pause_duration = random.uniform(2, 5) 
            print(f"Пауза на {pause_duration:.1f} сек. перед следующим ключевым словом...")
            time.sleep(pause_duration)

        if not all_post_links:
            print("Не найдено ни одной ссылки на посты по всем ключевым словам. Завершение работы.")
            return
        
        print(f"\nСбор ссылок завершен. Всего найдено уникальных ссылок для парсинга: {len(all_post_links)}")

        print("\nЭтап 3: Парсинг данных по собранным ссылкам (в той же сессии)...")
        processed_links_count = 0
        for post_url in all_post_links:
            processed_links_count += 1
            print(f"Обработка поста: {processed_links_count}/{len(all_post_links)} URL: {post_url}")
            post_data_dict = get_post_data_from_page(driver, post_url)

            if post_data_dict and post_data_dict.get('date'):
                post_date_obj = post_data_dict['date'] 
                post_text = post_data_dict.get('text', "Текст не извлечен")
                if post_date_obj and (datetime.now(timezone.utc) - post_date_obj <= timedelta(days=MAX_POST_AGE_DAYS)):
                    print(f"Пост {post_url} свежий (опубликован {post_date_obj.strftime('%Y-%m-%d')}).")
                    if collection.count_documents({'post_url': post_url}) == 0:
                        db_entry = {
                            'post_url': post_url,
                            'text': post_text,
                            'published_at': post_date_obj,
                            'parsed_at': datetime.now(timezone.utc)
                        }
                        try:
                            collection.insert_one(db_entry)
                            total_posts_saved += 1
                            print("Свежий пост сохранен в MongoDB.")
                        except errors.PyMongoError as e_mongo_insert:
                            print(f"Ошибка при сохранении данных поста {post_url} в MongoDB: {e_mongo_insert}")
                    else:
                        print(f"Пост {post_url} уже существует в базе данных. Пропускаем.")
                elif post_date_obj:
                    print(f"Пост {post_url} слишком старый (опубликован {post_date_obj.strftime('%Y-%m-%d')}). Пропускаем.")
                else:
                     print(f"Не удалось извлечь или некорректна дата для поста: {post_url}. Пропускаем сохранение.")
            elif post_data_dict:
                 print(f"Не удалось извлечь дату для поста: {post_url}. Пропускаем сохранение.")
            else:
                print(f"Не удалось получить данные (текст/дату) для поста: {post_url}. Пропускаем.")
            
            post_parse_pause = random.uniform(2, 5) 
            print(f"Пауза на {post_parse_pause:.1f} сек. перед следующим постом...")
            time.sleep(post_parse_pause)

        print("\nПарсинг данных постов завершен.")
        print(f"Всего новых постов сохранено в MongoDB: {total_posts_saved}")

    except Exception as e_main:
        print(f"Произошла критическая ошибка в main: {e_main}")
        if driver: 
            try:
                driver.save_screenshot("critical_error_screenshot.png")
                print("Скриншот ошибки сохранен как critical_error_screenshot.png")
            except Exception as screenshot_e:
                print(f"Не удалось сохранить скриншот: {screenshot_e}")
    finally:
        if driver:
            print("\nЗавершение работы драйвера...")
            try:
                driver.quit()
                print("Драйвер успешно завершил работу.")
            except Exception as e_quit:
                print(f"Ошибка при закрытии драйвера: {e_quit}")
        if mongo_client_local: 
            try:
                mongo_client_local.close()
                print("Соединение с MongoDB закрыто.")
            except Exception as e_mongo_close:
                print(f"Ошибка при закрытии соединения с MongoDB: {e_mongo_close}")
        print("Скрипт завершен.")

if __name__ == "__main__":
    main()
