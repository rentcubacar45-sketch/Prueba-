#!/usr/bin/env python3
"""
Bot de Telegram Avanzado para Subida de Archivos a Moodle, OJS y Next
Utiliza la clase UnifiedUploader sin modificaciones
"""

import asyncio
import logging
import os
import tempfile
from typing import Dict, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
import json
import datetime
from pathlib import Path

from telegram import (
    Update, 
    InlineKeyboardButton, 
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton
)
from telegram.ext import (
    Application, 
    CommandHandler, 
    MessageHandler, 
    CallbackQueryHandler,
    ContextTypes, 
    ConversationHandler,
    filters
)
from telegram.constants import ParseMode

# Importar el script de subida sin modificaciones
import sys
sys.path.append('.')  # Asegurar que se importe desde el directorio actual

try:
    from upload_script import UnifiedUploader, PROXY
    UPLOADER_AVAILABLE = True
except ImportError as e:
    print(f"Error importando el script de subida: {e}")
    print("AsegÃºrate de que el archivo 'upload_script.py' estÃ© en el mismo directorio")
    UPLOADER_AVAILABLE = False

# ConfiguraciÃ³n de logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Estados de la conversaciÃ³n
class States(Enum):
    PLATFORM_SELECTION = 1
    CREDENTIALS = 2
    HOST_INPUT = 3
    USERNAME_INPUT = 4
    PASSWORD_INPUT = 5
    REPO_ID_INPUT = 6
    FILE_UPLOAD = 7
    CONFIRM_UPLOAD = 8
    UPLOADING = 9

# Datos del usuario
@dataclass
class UserData:
    """Almacena los datos de sesiÃ³n del usuario"""
    platform: Optional[str] = None
    host: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    repo_id: Optional[str] = None
    uploader: Optional[UnifiedUploader] = None
    logged_in: bool = False
    upload_history: list = field(default_factory=list)
    
    def reset(self):
        """Restablece todos los datos del usuario"""
        self.platform = None
        self.host = None
        self.username = None
        self.password = None
        self.repo_id = None
        self.uploader = None
        self.logged_in = False
        
    def to_dict(self) -> dict:
        """Convierte a diccionario seguro (sin contraseÃ±a)"""
        return {
            'platform': self.platform,
            'host': self.host,
            'username': self.username,
            'repo_id': self.repo_id,
            'logged_in': self.logged_in,
            'upload_count': len(self.upload_history)
        }

# Almacenamiento en memoria (en producciÃ³n usar una base de datos)
user_sessions: Dict[int, UserData] = {}
upload_tasks: Dict[int, asyncio.Task] = {}

# Constantes de configuraciÃ³n
MAX_FILE_SIZE_MB = 50  # TamaÃ±o mÃ¡ximo de archivo permitido
SUPPORTED_EXTENSIONS = {'.pdf', '.txt', '.doc', '.docx', '.odt', '.rtf'}

# Textos y mensajes
WELCOME_MESSAGE = """
ð¤ *BOT DE SUBIDA AVANZADA*

Â¡Bienvenido! Este bot te permite subir archivos a diferentes plataformas:

â¢ *Moodle* - Sistemas de aprendizaje
â¢ *OJS* - Sistemas de revistas acadÃ©micas
â¢ *Next* - Almacenamiento en la nube

*Comandos disponibles:*
/start - Iniciar el bot
/login - Iniciar sesiÃ³n en una plataforma
/upload - Subir un archivo
/status - Ver estado de la sesiÃ³n
/logout - Cerrar sesiÃ³n
/history - Ver historial de subidas
/cancel - Cancelar operaciÃ³n actual
/help - Mostrar ayuda
"""

HELP_MESSAGE = """
ð *AYUDA DEL BOT*

*Flujo de trabajo:*
1. Usa /login para iniciar sesiÃ³n
2. Selecciona la plataforma (Moodle, OJS o Next)
3. Proporciona tus credenciales
4. Usa /upload para subir archivos

*Limitaciones:*
â¢ TamaÃ±o mÃ¡ximo: {max_size}MB
â¢ Formatos: {formats}

*Seguridad:*
â¢ Tus credenciales se almacenan solo en memoria
â¢ Se eliminan al cerrar sesiÃ³n
â¢ No se registran contraseÃ±as

Para comenzar, usa /login
""".format(max_size=MAX_FILE_SIZE_MB, formats=', '.join(SUPPORTED_EXTENSIONS))

# Funciones auxiliares
def get_user_data(user_id: int) -> UserData:
    """Obtiene o crea datos de usuario"""
    if user_id not in user_sessions:
        user_sessions[user_id] = UserData()
    return user_sessions[user_id]

def format_file_size(size_bytes: int) -> str:
    """Formatea el tamaÃ±o del archivo"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.2f} TB"

def validate_file(file_path: str) -> Tuple[bool, str]:
    """Valida un archivo antes de subir"""
    try:
        # Verificar existencia
        if not os.path.exists(file_path):
            return False, "El archivo no existe"
        
        # Verificar tamaÃ±o
        file_size = os.path.getsize(file_path)
        if file_size > MAX_FILE_SIZE_MB * 1024 * 1024:
            return False, f"Archivo demasiado grande (> {MAX_FILE_SIZE_MB}MB)"
        
        # Verificar extensiÃ³n
        file_ext = os.path.splitext(file_path)[1].lower()
        if file_ext not in SUPPORTED_EXTENSIONS:
            return False, f"Formato no soportado. Usa: {', '.join(SUPPORTED_EXTENSIONS)}"
        
        return True, "Archivo vÃ¡lido"
        
    except Exception as e:
        return False, f"Error al validar archivo: {str(e)}"

# Handlers de comandos
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Maneja el comando /start"""
    user_id = update.effective_user.id
    user_data = get_user_data(user_id)
    
    # Crear teclado principal
    keyboard = [
        [KeyboardButton("ð¤ Subir archivo")],
        [KeyboardButton("ð Iniciar sesiÃ³n"), KeyboardButton("ð Estado")],
        [KeyboardButton("ð Historial"), KeyboardButton("â Ayuda")]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    await update.message.reply_text(
        WELCOME_MESSAGE,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=reply_markup
    )
    
    return ConversationHandler.END

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Maneja el comando /help"""
    await update.message.reply_text(
        HELP_MESSAGE,
        parse_mode=ParseMode.MARKDOWN
    )

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Maneja el comando /status - Muestra el estado de la sesiÃ³n"""
    user_id = update.effective_user.id
    user_data = get_user_data(user_id)
    
    if not user_data.logged_in:
        await update.message.reply_text(
            "ð *No has iniciado sesiÃ³n*\n\nUsa /login para iniciar sesiÃ³n",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    status_text = f"""
â *SESIÃN ACTIVA*

*Plataforma:* {user_data.platform}
*Host:* {user_data.host}
*Usuario:* {user_data.username}
*ID Repositorio:* {user_data.repo_id or 'No requerido'}
*Subidas realizadas:* {len(user_data.upload_history)}

Usa /upload para subir un archivo
"""
    
    await update.message.reply_text(
        status_text,
        parse_mode=ParseMode.MARKDOWN
    )

async def history_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Maneja el comando /history - Muestra el historial de subidas"""
    user_id = update.effective_user.id
    user_data = get_user_data(user_id)
    
    if not user_data.upload_history:
        await update.message.reply_text(
            "ð­ *No hay historial de subidas*\n\nUsa /upload para subir tu primer archivo",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    history_text = "ð *HISTORIAL DE SUBIDAS*\n\n"
    
    for i, upload in enumerate(user_data.upload_history[-10:], 1):  # Ãltimas 10
        history_text += f"*{i}. {upload['filename']}*\n"
        history_text += f"  ð {upload['timestamp']}\n"
        history_text += f"  ð {upload['size']}\n"
        history_text += f"  ð {upload['url'][:50]}...\n\n"
    
    if len(user_data.upload_history) > 10:
        history_text += f"\n*Mostrando las Ãºltimas 10 de {len(user_data.upload_history)} subidas*"
    
    await update.message.reply_text(
        history_text,
        parse_mode=ParseMode.MARKDOWN
    )

async def logout_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Maneja el comando /logout"""
    user_id = update.effective_user.id
    user_data = get_user_data(user_id)
    
    if not user_data.logged_in:
        await update.message.reply_text("No hay sesiÃ³n activa para cerrar.")
        return
    
    # Cerrar sesiÃ³n en el uploader si existe
    if user_data.uploader:
        try:
            user_data.uploader.logout()
        except:
            pass
    
    # Resetear datos
    user_data.reset()
    
    await update.message.reply_text(
        "â *SesiÃ³n cerrada correctamente*\n\nTus credenciales han sido eliminadas.",
        parse_mode=ParseMode.MARKDOWN
    )

async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancela la operaciÃ³n actual"""
    user_id = update.effective_user.id
    
    # Cancelar tarea de subida si existe
    if user_id in upload_tasks:
        upload_tasks[user_id].cancel()
        del upload_tasks[user_id]
    
    await update.message.reply_text(
        "â *OperaciÃ³n cancelada*",
        parse_mode=ParseMode.MARKDOWN
    )
    
    return ConversationHandler.END

# Handlers de login
async def login_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Inicia el proceso de login"""
    user_id = update.effective_user.id
    user_data = get_user_data(user_id)
    
    # Verificar si ya estÃ¡ logueado
    if user_data.logged_in:
        keyboard = [
            [
                InlineKeyboardButton("â Mantener sesiÃ³n", callback_data="keep_session"),
                InlineKeyboardButton("ð Reiniciar", callback_data="restart_login")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "Ya tienes una sesiÃ³n activa. Â¿QuÃ© deseas hacer?",
            reply_markup=reply_markup
        )
        return States.PLATFORM_SELECTION
    
    # SelecciÃ³n de plataforma
    keyboard = [
        [
            InlineKeyboardButton("ð Moodle", callback_data="platform_moodle"),
            InlineKeyboardButton("ð OJS", callback_data="platform_ojs")
        ],
        [
            InlineKeyboardButton("âï¸ Next", callback_data="platform_next"),
            InlineKeyboardButton("â Cancelar", callback_data="cancel")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "ð *INICIAR SESIÃN*\n\nSelecciona la plataforma:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=reply_markup
    )
    
    return States.PLATFORM_SELECTION

async def platform_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Maneja la selecciÃ³n de plataforma"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    user_data = get_user_data(user_id)
    
    if query.data == "cancel":
        await query.edit_message_text("â Login cancelado")
        return ConversationHandler.END
    
    if query.data == "keep_session":
        await query.edit_message_text("â Manteniendo sesiÃ³n actual")
        return ConversationHandler.END
    
    if query.data == "restart_login":
        user_data.reset()
        await query.edit_message_text("ð Reiniciando login...")
        # Volver a mostrar selecciÃ³n de plataforma
        return await login_command(update, context)
    
    # Guardar plataforma seleccionada
    platform_map = {
        "platform_moodle": "Moodle",
        "platform_ojs": "OJS",
        "platform_next": "Next"
    }
    
    user_data.platform = platform_map.get(query.data)
    
    await query.edit_message_text(
        f"â *Plataforma seleccionada:* {user_data.platform}\n\n"
        f"Ahora ingresa la URL del sitio (ej: https://moodle.ejemplo.edu/):",
        parse_mode=ParseMode.MARKDOWN
    )
    
    return States.HOST_INPUT

async def host_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recibe y valida el host"""
    user_id = update.effective_user.id
    user_data = get_user_data(user_id)
    
    host = update.message.text.strip()
    
    # ValidaciÃ³n bÃ¡sica de URL
    if not host.startswith(('http://', 'https://')):
        host = 'https://' + host
    
    user_data.host = host
    
    await update.message.reply_text(
        f"â *Host configurado:* {host}\n\n"
        f"Ahora ingresa tu nombre de usuario:",
        parse_mode=ParseMode.MARKDOWN
    )
    
    return States.USERNAME_INPUT

async def username_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recibe el nombre de usuario"""
    user_id = update.effective_user.id
    user_data = get_user_data(user_id)
    
    username = update.message.text.strip()
    user_data.username = username
    
    await update.message.reply_text(
        f"â *Usuario:* {username}\n\n"
        f"Ahora ingresa tu contraseÃ±a:",
        parse_mode=ParseMode.MARKDOWN
    )
    
    return States.PASSWORD_INPUT

async def password_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recibe la contraseÃ±a"""
    user_id = update.effective_user.id
    user_data = get_user_data(user_id)
    
    password = update.message.text.strip()
    user_data.password = password
    
    # Preguntar por repo_id si es necesario
    if user_data.platform in ["Moodle", "OJS"]:
        platform_name = "Moodle" if user_data.platform == "Moodle" else "OJS"
        repo_text = "ID del repositorio" if user_data.platform == "Moodle" else "submissionId"
        
        await update.message.reply_text(
            f"â *ContraseÃ±a configurada*\n\n"
            f"Para {platform_name}, necesitamos el {repo_text}:\n"
            f"(Para Next, puedes ingresar cualquier valor o '0')",
            parse_mode=ParseMode.MARKDOWN
        )
        return States.REPO_ID_INPUT
    else:
        # Para Next, no se necesita repo_id
        user_data.repo_id = "0"
        return await perform_login(update, context)

async def repo_id_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recibe el repo_id o submissionId"""
    user_id = update.effective_user.id
    user_data = get_user_data(user_id)
    
    repo_id = update.message.text.strip()
    user_data.repo_id = repo_id
    
    return await perform_login(update, context)

async def perform_login(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Realiza el login con las credenciales proporcionadas"""
    user_id = update.effective_user.id
    user_data = get_user_data(user_id)
    
    try:
        # Crear instancia del uploader
        user_data.uploader = UnifiedUploader(
            platform=user_data.platform,
            username=user_data.username,
            password=user_data.password,
            host=user_data.host,
            repo_id=user_data.repo_id or "0",
            max_file_size_mb=MAX_FILE_SIZE_MB
        )
        
        # Intentar login
        loading_msg = await update.message.reply_text("ð *Intentando login...*", parse_mode=ParseMode.MARKDOWN)
        
        success = user_data.uploader.login()
        
        if success:
            user_data.logged_in = True
            await loading_msg.edit_text(
                f"â *Â¡Login exitoso!*\n\n"
                f"Te has conectado a *{user_data.platform}* correctamente.\n\n"
                f"Usa /upload para subir archivos o /status para ver tu sesiÃ³n.",
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            await loading_msg.edit_text(
                "â *Error de login*\n\n"
                "Verifica tus credenciales y asegÃºrate de que:\n"
                "1. La URL es correcta\n"
                "2. El usuario y contraseÃ±a son vÃ¡lidos\n"
                "3. Tienes acceso a la plataforma\n\n"
                "Usa /login para intentar nuevamente",
                parse_mode=ParseMode.MARKDOWN
            )
            user_data.reset()
            
    except Exception as e:
        logger.error(f"Error en login: {e}")
        await update.message.reply_text(
            f"â *Error durante el login:* {str(e)}\n\n"
            f"Intenta nuevamente con /login",
            parse_mode=ParseMode.MARKDOWN
        )
        user_data.reset()
    
    return ConversationHandler.END

# Handlers de upload
async def upload_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Inicia el proceso de subida de archivo"""
    user_id = update.effective_user.id
    user_data = get_user_data(user_id)
    
    # Verificar login
    if not user_data.logged_in:
        await update.message.reply_text(
            "ð *Debes iniciar sesiÃ³n primero*\n\nUsa /login para iniciar sesiÃ³n",
            parse_mode=ParseMode.MARKDOWN
        )
        return ConversationHandler.END
    
    await update.message.reply_text(
        f"ð¤ *SUBIR ARCHIVO*\n\n"
        f"Plataforma: {user_data.platform}\n"
        f"Host: {user_data.host}\n\n"
        f"EnvÃ­ame el archivo que deseas subir.\n"
        f"*Formatos soportados:* {', '.join(SUPPORTED_EXTENSIONS)}\n"
        f"*TamaÃ±o mÃ¡ximo:* {MAX_FILE_SIZE_MB}MB\n\n"
        f"Usa /cancel para abortar",
        parse_mode=ParseMode.MARKDOWN
    )
    
    return States.FILE_UPLOAD

async def receive_file(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recibe y procesa el archivo"""
    user_id = update.effective_user.id
    user_data = get_user_data(user_id)
    
    if not update.message.document and not update.message.photo:
        await update.message.reply_text(
            "â Por favor, envÃ­a un archivo vÃ¡lido.\n"
            "Formatos: " + ", ".join(SUPPORTED_EXTENSIONS)
        )
        return States.FILE_UPLOAD
    
    try:
        # Obtener el archivo
        if update.message.document:
            file = update.message.document
            file_ext = os.path.splitext(file.file_name)[1].lower() if file.file_name else ''
        else:
            # Para fotos, usar la de mayor calidad
            file = update.message.photo[-1]
            file_ext = '.jpg'
        
        # Validar extensiÃ³n
        if file_ext not in SUPPORTED_EXTENSIONS and update.message.document:
            await update.message.reply_text(
                f"â Formato no soportado. Usa: {', '.join(SUPPORTED_EXTENSIONS)}"
            )
            return States.FILE_UPLOAD
        
        # Verificar tamaÃ±o
        if file.file_size > MAX_FILE_SIZE_MB * 1024 * 1024:
            await update.message.reply_text(
                f"â Archivo demasiado grande. MÃ¡ximo: {MAX_FILE_SIZE_MB}MB"
            )
            return States.FILE_UPLOAD
        
        # Descargar archivo
        loading_msg = await update.message.reply_text("â¬ï¸ *Descargando archivo...*", parse_mode=ParseMode.MARKDOWN)
        
        file_obj = await file.get_file()
        
        # Crear directorio temporal si no existe
        temp_dir = Path("temp_uploads")
        temp_dir.mkdir(exist_ok=True)
        
        # Nombre Ãºnico para el archivo
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_filename = f"upload_{user_id}_{timestamp}{file_ext}"
        file_path = temp_dir / safe_filename
        
        await file_obj.download_to_drive(file_path)
        
        await loading_msg.edit_text(
            f"â *Archivo recibido*\n\n"
            f"*Nombre:* {safe_filename}\n"
            f"*TamaÃ±o:* {format_file_size(file.file_size)}\n\n"
            f"Â¿Deseas subirlo a *{user_data.platform}*?\n"
            f"Host: {user_data.host}",
            parse_mode=ParseMode.MARKDOWN
        )
        
        # Guardar ruta temporal en context
        context.user_data['file_path'] = str(file_path)
        context.user_data['file_name'] = file.file_name if update.message.document else f"foto_{timestamp}.jpg"
        
        # Botones de confirmaciÃ³n
        keyboard = [
            [
                InlineKeyboardButton("â Subir", callback_data="confirm_upload"),
                InlineKeyboardButton("â Cancelar", callback_data="cancel_upload")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "Confirma la subida:",
            reply_markup=reply_markup
        )
        
        return States.CONFIRM_UPLOAD
        
    except Exception as e:
        logger.error(f"Error al recibir archivo: {e}")
        await update.message.reply_text(
            f"â Error al procesar el archivo: {str(e)}"
        )
        return ConversationHandler.END

async def confirm_upload(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Confirma y realiza la subida"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    user_data = get_user_data(user_id)
    
    if query.data == "cancel_upload":
        # Limpiar archivo temporal
        if 'file_path' in context.user_data and os.path.exists(context.user_data['file_path']):
            try:
                os.remove(context.user_data['file_path'])
            except:
                pass
        
        await query.edit_message_text("â Subida cancelada")
        return ConversationHandler.END
    
    # Realizar subida
    file_path = context.user_data.get('file_path')
    file_name = context.user_data.get('file_name', 'archivo')
    
    if not file_path or not os.path.exists(file_path):
        await query.edit_message_text("â Archivo no encontrado. Intenta nuevamente.")
        return ConversationHandler.END
    
    await query.edit_message_text("ð *Iniciando subida...*", parse_mode=ParseMode.MARKDOWN)
    
    try:
        # Crear tarea asÃ­ncrona para la subida (que es sÃ­ncrona)
        upload_task = asyncio.create_task(
            perform_upload(user_id, file_path, file_name, query.message)
        )
        upload_tasks[user_id] = upload_task
        
    except Exception as e:
        logger.error(f"Error al iniciar subida: {e}")
        await query.message.reply_text(f"â Error al iniciar subida: {str(e)}")
        
        # Limpiar archivo temporal
        try:
            os.remove(file_path)
        except:
            pass
        
        return ConversationHandler.END
    
    return States.UPLOADING

async def perform_upload(user_id: int, file_path: str, file_name: str, message):
    """Realiza la subida del archivo en segundo plano"""
    user_data = get_user_data(user_id)
    
    try:
        # Callback para progreso
        def progress_callback(filename, bytes_read, total_bytes, speed, estimated_time, args):
            # Esta funciÃ³n se llama desde el uploader sÃ­ncrono
            # No podemos usar await aquÃ­, asÃ­ que usamos asyncio.run_coroutine_threadsafe
            percent = (bytes_read / total_bytes) * 100
            
            asyncio.run_coroutine_threadsafe(
                update_progress(message, percent, bytes_read, total_bytes, speed),
                asyncio.get_event_loop()
            )
        
        # Realizar subida
        error_msg, result = user_data.uploader.upload_file(
            file_path=file_path,
            progressfunc=progress_callback,
            args=(user_id,),
            tokenize=False
        )
        
        if error_msg:
            await message.edit_text(f"â *Error en subida:* {error_msg}", parse_mode=ParseMode.MARKDOWN)
        else:
            # Guardar en historial
            upload_record = {
                'timestamp': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                'filename': file_name,
                'size': format_file_size(os.path.getsize(file_path)),
                'url': result.get('url', 'No disponible'),
                'platform': user_data.platform
            }
            user_data.upload_history.append(upload_record)
            
            # Mensaje de Ã©xito
            success_text = f"""
â *Â¡ARCHIVO SUBIDO CON ÃXITO!*

*Nombre:* {file_name}
*Plataforma:* {user_data.platform}
*TamaÃ±o:* {format_file_size(os.path.getsize(file_path))}
*Fecha:* {upload_record['timestamp']}

*Enlace de descarga:*
{result.get('url', 'No disponible')}

Usa /upload para subir mÃ¡s archivos
"""
            await message.edit_text(success_text, parse_mode=ParseMode.MARKDOWN)
        
    except Exception as e:
        logger.error(f"Error en subida: {e}")
        await message.edit_text(f"â *Error durante la subida:* {str(e)}", parse_mode=ParseMode.MARKDOWN)
    
    finally:
        # Limpiar archivo temporal
        try:
            os.remove(file_path)
        except:
            pass
        
        # Eliminar tarea
        if user_id in upload_tasks:
            del upload_tasks[user_id]

async def update_progress(message, percent: float, bytes_read: int, total_bytes: int, speed: int):
    """Actualiza el mensaje de progreso"""
    try:
        progress_bar = "[" + "â" * int(percent / 10) + "â" * (10 - int(percent / 10)) + "]"
        
        progress_text = f"""
ð¤ *Subiendo archivo...*

{progress_bar} {percent:.1f}%

*Progreso:* {format_file_size(bytes_read)} / {format_file_size(total_bytes)}
*Velocidad:* {format_file_size(speed)}/s

Por favor, espera...
"""
        
        # Solo actualizar cada 5% para no saturar
        if percent % 5 < 0.5 or percent >= 100:
            await message.edit_text(progress_text, parse_mode=ParseMode.MARKDOWN)
            
    except Exception as e:
        logger.error(f"Error al actualizar progreso: {e}")

# Handler de mensajes de texto
async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Maneja mensajes de texto segÃºn el estado actual"""
    text = update.message.text
    
    if text == "ð¤ Subir archivo":
        await upload_command(update, context)
    elif text == "ð Iniciar sesiÃ³n":
        await login_command(update, context)
    elif text == "ð Estado":
        await status_command(update, context)
    elif text == "ð Historial":
        await history_command(update, context)
    elif text == "â Ayuda":
        await help_command(update, context)
    else:
        await update.message.reply_text(
            "Usa los botones del teclado o los comandos disponibles.\n"
            "Escribe /help para ver todas las opciones."
        )

# Manejo de errores
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Maneja errores del bot"""
    logger.error(f"Error: {context.error}", exc_info=context.error)
    
    if update and update.effective_message:
        await update.effective_message.reply_text(
            "â OcurriÃ³ un error inesperado. Por favor, intenta nuevamente."
        )

# ConfiguraciÃ³n principal
def main() -> None:
    """Inicia el bot"""
    if not UPLOADER_AVAILABLE:
        print("ERROR: No se pudo importar el script de subida.")
        print("AsegÃºrate de que el archivo con la clase UnifiedUploader estÃ© disponible.")
        return
    
    # Token del bot (debes configurarlo desde variables de entorno)
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        print("ERROR: No se encontrÃ³ TELEGRAM_BOT_TOKEN en las variables de entorno")
        print("Exporta tu token con: export TELEGRAM_BOT_TOKEN='tu_token'")
        return
    
    # Crear aplicaciÃ³n
    application = Application.builder().token(token).build()
    
    # Handler de conversaciÃ³n para login
    login_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("login", login_command)],
        states={
            States.PLATFORM_SELECTION: [
                CallbackQueryHandler(platform_selection, pattern="^(platform_|keep_session|restart_login|cancel)$")
            ],
            States.HOST_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, host_input)],
            States.USERNAME_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, username_input)],
            States.PASSWORD_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, password_input)],
            States.REPO_ID_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, repo_id_input)],
        },
        fallbacks=[CommandHandler("cancel", cancel_command)],
        allow_reentry=True
    )
    
    # Handler de conversaciÃ³n para upload
    upload_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("upload", upload_command)],
        states={
            States.FILE_UPLOAD: [
                MessageHandler(
                    filters.DOCUMENT | filters.PHOTO,
                    receive_file
                ),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message)
            ],
            States.CONFIRM_UPLOAD: [
                CallbackQueryHandler(confirm_upload, pattern="^(confirm_upload|cancel_upload)$")
            ],
            States.UPLOADING: [
                # Solo esperar a que termine la subida
            ]
        },
        fallbacks=[CommandHandler("cancel", cancel_command)],
        allow_reentry=True
    )
    
    # AÃ±adir handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("history", history_command))
    application.add_handler(CommandHandler("logout", logout_command))
    application.add_handler(CommandHandler("cancel", cancel_command))
    
    application.add_handler(login_conv_handler)
    application.add_handler(upload_conv_handler)
    
    # Handler para mensajes de texto con teclado
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))
    
    # Handler de errores
    application.add_error_handler(error_handler)
    
    # Iniciar bot
    print("ð¤ Bot iniciado. Presiona Ctrl+C para detener.")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
