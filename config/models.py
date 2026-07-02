# Скопируй этот файл в .env и заполни своими значениями.
# Никогда не коммить .env с реальными значениями в git!

# --- Azure AI Foundry ---
# Project endpoint (не resource endpoint!), вида:
# https://<your-project>.<region>.api.azureml.ms
# или https://<your-project>.services.ai.azure.com/api/projects/<project-name>
FOUNDRY_PROJECT_ENDPOINT=

# Аутентификация идёт через DefaultAzureCredential.
# Локально достаточно выполнить `az login` в терминале перед запуском —
# отдельный ключ сюда писать не нужно.

# --- GitHub ---
# Personal Access Token (classic) со scope "repo" — нужен для клонирования
# приватных репозиториев. Создать: GitHub -> Settings -> Developer settings
# -> Personal access tokens -> Tokens (classic) -> Generate new token.
GITHUB_TOKEN=

# --- Опционально: переопределить модели по ролям ---
# Если не задано — берутся значения по умолчанию из config/models.py
# MODEL_CTO=o3
# MODEL_BACKEND=gpt-5.1
# MODEL_PRODUCT=gpt-5.4-mini
# MODEL_QA=gpt-5.1
# MODEL_CODE_SCOUT=gpt-5.3-codex
# MODEL_MODERATOR=gpt-5.4-mini

# Куда клонировать репозитории локально
AI_TEAM_WORKDIR=./repos

# --- Совет директоров (main_board.py) ---
# Опционально переопределить модели по ролям (если не задано —
# значения по умолчанию из config/models.py)
# MODEL_BOARD_MEKHMAT=o3
# MODEL_BOARD_FIZTECH=gpt-5.1
# MODEL_BOARD_FIZMAT=o3
# MODEL_BOARD_TEHMAT=gpt-5.1
# MODEL_BOARD_SECRETARY=gpt-5.4-mini
# MODEL_BOARD_AGENDA=gpt-5.4-mini

# --- Telegram (для отправки отчёта заседания совета) ---
# Токен бота: создать через @BotFather в Telegram -> /newbot
TELEGRAM_BOT_TOKEN=
# Chat ID: напиши что-нибудь своему боту, затем открой в браузере
# https://api.telegram.org/bot<TOKEN>/getUpdates и найди "chat":{"id": ...}
TELEGRAM_CHAT_ID=
