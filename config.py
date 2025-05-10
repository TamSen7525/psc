import os
from dotenv import load_dotenv

# Загружаем переменные окружения из .env файла
load_dotenv()

# Настройки Instagram
INSTAGRAM_LOGIN = os.getenv("INSTAGRAM_LOGIN")
INSTAGRAM_PASSWORD = os.getenv("INSTAGRAM_PASSWORD")

# ВРЕМЕННАЯ ПРОВЕРКА: Выводим загруженные учетные данные
print(f"[DEBUG] Загруженный логин из .env: {INSTAGRAM_LOGIN}")
print(f"[DEBUG] Загруженный пароль из .env: {'*' * len(INSTAGRAM_PASSWORD) if INSTAGRAM_PASSWORD else None}") # Пароль маскируем

# Настройки MongoDB
MONGO_CONNECTION_STRING = os.getenv("MONGO_CONNECTION_STRING", "mongodb://localhost:27017/")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "instagram_parser_db")
MONGO_COLLECTION_NAME = os.getenv("MONGO_COLLECTION_NAME", "giveaways")

# Максимальный возраст поста в днях
MAX_POST_AGE_DAYS = 14 