import os
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

# Token del bot de Telegram
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# Configuración de archivos
MAX_FILE_SIZE_MB = 50
SUPPORTED_EXTENSIONS = {'.mp4', '.txt', '.png', '.jpg', '.odt', '.rtf'}

# Configuración de proxy (opcional)
USE_PROXY = False
PROXY_CONFIG = {
    'http': 'socks5h://alian:alian@152.206.119.70:9092',
    'https': 'socks5h://alian:alian@152.206.119.70:9092'
}

# Configuración de logging
LOGGING_CONFIG = {
    'level': 'INFO',
    'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    'filename': 'bot.log'
}

# Usuarios administradores (opcional)
ADMIN_USERS = []
