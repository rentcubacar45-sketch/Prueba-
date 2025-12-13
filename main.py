#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Bot de Telegram para subir archivos a Moodle, OJS y Next
Archivo principal
"""

import logging
import os
import sys
import traceback
from typing import Dict, Optional, Tuple
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    filters,
    ContextTypes
)

# Importar el uploader unificado
from uploader import UnifiedUploader

# ========= CONFIGURACIÓN =========
# Token del bot de Telegram (REEMPLAZA CON TU TOKEN)
TELEGRAM_BOT_TOKEN = "8582821363:AAHNVj6XPxYoT7j5tF0U-9GI2qE_5bdtHSA"

# Alias del administrador (sin @)
ADMIN_ALIAS = "Eliel_21"

# Configuración de logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Estados de la conversación
PLATFORM, CREDENTIALS, FILE, UPLOAD = range(4)

# Almacenamiento temporal de datos de usuario
user_data: Dict[int, Dict] = {}

# ========= FUNCIONES DE AYUDA =========
def get_user_info(update: Update) -> Tuple[int, str]:
    """Obtiene información del usuario."""
    user_id = update.effective_user.id
    username = update.effective_user.username or update.effective_user.first_name
    return user_id, username

def is_admin(update: Update) -> bool:
    """Verifica si el usuario es administrador."""
    username = update.effective_user.username
    return username and username.lower() == ADMIN_ALIAS.lower()

# ========= COMANDOS =========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Inicia la conversación."""
    user_id, username = get_user_info(update)
    
    welcome_text = (
        f"👋 ¡Hola {username}!\n\n"
        "🤖 *Bot de Subida de Archivos*\n\n"
        "📤 Puedo subir archivos a:\n"
        "• 📚 Moodle\n"
        "• 📄 OJS (Open Journal Systems)\n"
        "• ☁️ Nextcloud\n\n"
        "⚠️ *IMPORTANTE:*\n"
        "• Este bot funciona mediante proxy\n"
        "• Los archivos se suben temporalmente\n"
        "• No se almacenan credenciales\n\n"
        "📝 Usa /help para ver comandos disponibles\n"
        "🚀 Usa /upload para comenzar"
    )
    
    await update.message.reply_text(welcome_text, parse_mode='Markdown')
    return ConversationHandler.END

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Muestra la ayuda."""
    help_text = (
        "📚 *COMANDOS DISPONIBLES:*\n\n"
        "📝 /start - Inicia el bot\n"
        "📤 /upload - Subir un archivo\n"
        "❓ /help - Muestra esta ayuda\n"
        "ℹ️ /status - Estado del bot\n"
        "📊 /stats - Estadísticas (admin)\n"
        "🔄 /reset - Reinicia tu sesión\n\n"
        "📋 *PROCESO DE SUBIDA:*\n"
        "1. Selecciona plataforma\n"
        "2. Ingresa credenciales\n"
        "3. Envía el archivo\n"
        "4. ¡Listo! Obtén el enlace\n\n"
        "📎 *ARCHIVOS SOPORTADOS:*\n"
        "• PDF (.pdf)\n"
        "• Word (.doc, .docx)\n"
        "• Texto (.txt)\n\n"
        "⚡ *ADMIN:* @" + ADMIN_ALIAS
    )
    
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Muestra el estado del bot."""
    status_text = (
        "✅ *BOT ACTIVO*\n\n"
        "🔧 *Funcionalidades:*\n"
        "• Subida a Moodle ✓\n"
        "• Subida a OJS ✓\n"
        "• Subida a Nextcloud ✓\n"
        "• Proxy SOCKS5 ✓\n"
        "• Progreso de subida ✓\n\n"
        "📊 *Estadísticas:*\n"
        f"• Usuarios activos: {len(user_data)}\n"
        "• Última actualización: Funcionando\n\n"
        "🛠️ *Soporte:* Contacta a @" + ADMIN_ALIAS
    )
    
    await update.message.reply_text(status_text, parse_mode='Markdown')

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Muestra estadísticas (solo admin)."""
    if not is_admin(update):
        await update.message.reply_text("❌ Solo el administrador puede ver estadísticas.")
        return
    
    stats_text = (
        "📊 *ESTADÍSTICAS DEL BOT*\n\n"
        f"👥 Usuarios en sesión: {len(user_data)}\n"
        f"🆔 Tu ID: {update.effective_user.id}\n"
        f"👤 Tu alias: @{update.effective_user.username}\n\n"
        "💾 *Almacenamiento temporal:*\n"
    )
    
    # Contar usuarios por plataforma
    platforms = {'Moodle': 0, 'OJS': 0, 'Next': 0}
    for data in user_data.values():
        if 'platform' in data:
            platforms[data['platform']] += 1
    
    stats_text += f"• Moodle: {platforms['Moodle']}\n"
    stats_text += f"• OJS: {platforms['OJS']}\n"
    stats_text += f"• Nextcloud: {platforms['Next']}\n"
    
    await update.message.reply_text(stats_text, parse_mode='Markdown')

async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Reinicia la sesión del usuario."""
    user_id, username = get_user_info(update)
    
    if user_id in user_data:
        del user_data[user_id]
    
    await update.message.reply_text(
        "✅ *Sesión reiniciada*\n\n"
        "Todos tus datos temporales han sido eliminados.\n"
        "Puedes comenzar de nuevo con /upload",
        parse_mode='Markdown'
    )

# ========= FLUJO DE SUBIDA =========
async def upload_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Inicia el proceso de subida."""
    user_id, username = get_user_info(update)
    
    # Inicializar datos del usuario
    user_data[user_id] = {
        'username': username,
        'step': 'platform'
    }
    
    keyboard = [
        [
            InlineKeyboardButton("📚 Moodle", callback_data="Moodle"),
            InlineKeyboardButton("📄 OJS", callback_data="OJS"),
        ],
        [
            InlineKeyboardButton("☁️ Nextcloud", callback_data="Next"),
            InlineKeyboardButton("❌ Cancelar", callback_data="cancel"),
        ]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "📤 *SUBIR ARCHIVO*\n\n"
        "1️⃣ *Selecciona la plataforma:*\n\n"
        "• 📚 *Moodle:* Para cursos y materiales\n"
        "• 📄 *OJS:* Para revistas académicas\n"
        "• ☁️ *Nextcloud:* Almacenamiento en la nube\n\n"
        "⚠️ *Nota:* Necesitarás credenciales de acceso",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )
    
    return PLATFORM

async def platform_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Procesa la selección de plataforma."""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    
    if query.data == "cancel":
        await query.edit_message_text("❌ Subida cancelada.")
        del user_data[user_id]
        return ConversationHandler.END
    
    user_data[user_id]['platform'] = query.data
    
    platform_info = {
        "Moodle": "📚 *PLATAFORMA: MOODLE*\n\n🔗 Ejemplo de URL: https://moodle.uclv.edu.cu/",
        "OJS": "📄 *PLATAFORMA: OJS*\n\n🔗 Ejemplo de URL: https://evea.uh.cu/",
        "Next": "☁️ *PLATAFORMA: NEXTCLOUD*\n\n🔗 Ejemplo de URL: https://minube.uh.cu/"
    }
    
    await query.edit_message_text(
        f"{platform_info[query.data]}\n\n"
        "2️⃣ *Ingresa la URL de la plataforma:*\n\n"
        "📝 Envíame la URL completa incluyendo https://\n"
        "Ejemplo: https://moodle.uclv.edu.cu/",
        parse_mode='Markdown'
    )
    
    return CREDENTIALS

async def get_host(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Procesa la URL del host."""
    user_id, username = get_user_info(update)
    
    host = update.message.text.strip()
    
    # Validar URL básica
    if not host.startswith(('http://', 'https://')):
        await update.message.reply_text(
            "❌ *URL inválida*\n\n"
            "Debe comenzar con http:// o https://\n"
            "Por favor, envíala de nuevo:",
            parse_mode='Markdown'
        )
        return CREDENTIALS
    
    user_data[user_id]['host'] = host
    
    # Pedir credenciales según plataforma
    platform = user_data[user_id]['platform']
    
    if platform == "Next":
        cred_text = (
            "3️⃣ *CREDENCIALES NEXTCLOUD*\n\n"
            "🔑 *Usuario:* Tu nombre de usuario de Nextcloud\n"
            "🔐 *Contraseña:* Tu contraseña de Nextcloud\n\n"
            "📝 *Envía las credenciales en este formato:*\n"
            "usuario:contraseña\n\n"
            "Ejemplo: estudiante:miContraseña123"
        )
    else:
        cred_text = (
            f"3️⃣ *CREDENCIALES {platform}*\n\n"
            "🔑 *Usuario:* Tu nombre de usuario\n"
            "🔐 *Contraseña:* Tu contraseña\n\n"
            "📝 *Envía las credenciales en este formato:*\n"
            "usuario:contraseña\n\n"
            "Ejemplo: estudiante:miContraseña123"
        )
    
    await update.message.reply_text(cred_text, parse_mode='Markdown')
    
    return CREDENTIALS

async def get_credentials(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Procesa las credenciales."""
    user_id, username = get_user_info(update)
    
    credentials = update.message.text.strip()
    
    # Validar formato
    if ':' not in credentials:
        await update.message.reply_text(
            "❌ *Formato incorrecto*\n\n"
            "Debe ser: usuario:contraseña\n\n"
            "Por favor, envíalo de nuevo:",
            parse_mode='Markdown'
        )
        return CREDENTIALS
    
    username_input, password = credentials.split(':', 1)
    user_data[user_id]['login_user'] = username_input.strip()
    user_data[user_id]['login_pass'] = password.strip()
    
    # Pedir repo_id según plataforma
    platform = user_data[user_id]['platform']
    
    if platform == "Moodle":
        repo_text = (
            "4️⃣ *ID DEL REPOSITORIO MOODLE*\n\n"
            "🔢 *Repository ID:* Número del repositorio (generalmente 4)\n\n"
            "📝 *Envía solo el número:*\n"
            "Ejemplo: 4"
        )
    elif platform == "OJS":
        repo_text = (
            "4️⃣ *ID DE ENVÍO OJS*\n\n"
            "🔢 *Submission ID:* Número del envío\n\n"
            "📝 *Envía solo el número:*\n"
            "Ejemplo: 123"
        )
    else:  # Next
        repo_text = (
            "4️⃣ *CONFIRMACIÓN NEXTCLOUD*\n\n"
            "Para Nextcloud no se necesita ID.\n"
            "Envía cualquier texto para continuar:"
        )
    
    await update.message.reply_text(repo_text, parse_mode='Markdown')
    
    return FILE

async def get_repo_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Procesa el repo_id o confirma para Next."""
    user_id, username = get_user_info(update)
    
    platform = user_data[user_id]['platform']
    
    if platform == "Next":
        # Para Next, no necesitamos repo_id
        user_data[user_id]['repo_id'] = 0
    else:
        try:
            repo_id = int(update.message.text.strip())
            user_data[user_id]['repo_id'] = repo_id
        except ValueError:
            await update.message.reply_text(
                "❌ *Debe ser un número*\n\n"
                "Por favor, envía solo el número:",
                parse_mode='Markdown'
            )
            return FILE
    
    # Pedir archivo
    await update.message.reply_text(
        "📎 *ENVÍA EL ARCHIVO*\n\n"
        "⬆️ *Sube el archivo que deseas enviar:*\n\n"
        "📋 *Formatos soportados:*\n"
        "• PDF (.pdf)\n"
        "• Word (.doc, .docx)\n"
        "• Texto (.txt)\n\n"
        "⚠️ *Tamaño máximo:* 100MB\n"
        "⏱️ *Procesando:* ~1-2 minutos",
        parse_mode='Markdown'
    )
    
    return UPLOAD

async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Procesa el archivo enviado."""
    user_id, username = get_user_info(update)
    
    # Verificar si es documento
    if not update.message.document:
        await update.message.reply_text(
            "❌ *Por favor, envía un archivo*\n\n"
            "Usa el clip 📎 para adjuntar un documento.",
            parse_mode='Markdown'
        )
        return UPLOAD
    
    document = update.message.document
    
    # Verificar tipo de archivo
    allowed_types = ['application/pdf', 'application/msword', 
                    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                    'text/plain']
    
    if document.mime_type not in allowed_types:
        await update.message.reply_text(
            "❌ *Tipo de archivo no soportado*\n\n"
            "Solo se aceptan:\n"
            "• PDF (.pdf)\n"
            "• Word (.doc, .docx)\n"
            "• Texto (.txt)",
            parse_mode='Markdown'
        )
        return UPLOAD
    
    # Verificar tamaño (100MB)
    if document.file_size > 100 * 1024 * 1024:
        await update.message.reply_text(
            "❌ *Archivo muy grande*\n\n"
            "El tamaño máximo es 100MB.",
            parse_mode='Markdown'
        )
        return UPLOAD
    
    # Descargar archivo
    processing_msg = await update.message.reply_text(
        "⏬ *Descargando archivo...*\n"
        "Por favor espera...",
        parse_mode='Markdown'
    )
    
    try:
        # Crear directorio temporal si no existe
        os.makedirs('temp', exist_ok=True)
        
        # Descargar archivo
        file = await document.get_file()
        file_path = f"temp/{user_id}_{document.file_name}"
        await file.download_to_drive(file_path)
        
        user_data[user_id]['file_path'] = file_path
        user_data[user_id]['file_name'] = document.file_name
        
        await processing_msg.edit_text(
            "✅ *Archivo descargado*\n\n"
            "📊 *Información:*\n"
            f"• Nombre: {document.file_name}\n"
            f"• Tamaño: {document.file_size / 1024 / 1024:.2f} MB\n\n"
            "🚀 *Iniciando subida...*",
            parse_mode='Markdown'
        )
        
        # Realizar la subida
        return await perform_upload(update, context, user_id)
        
    except Exception as e:
        logger.error(f"Error descargando archivo: {e}")
        await processing_msg.edit_text(
            "❌ *Error al descargar el archivo*\n\n"
            "Por favor, intenta de nuevo.",
            parse_mode='Markdown'
        )
        return UPLOAD

async def perform_upload(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int) -> int:
    """Realiza la subida del archivo."""
    try:
        user_info = user_data[user_id]
        
        # Configurar uploader
        uploader = UnifiedUploader(
            platform=user_info['platform'],
            username=user_info['login_user'],
            password=user_info['login_pass'],
            host=user_info['host'],
            repo_id=user_info['repo_id'],
            file_path=user_info['file_path'],
            max_file_size_mb=100
        )
        
        # Actualizar mensaje
        if 'processing_msg' in context.user_data:
            await context.user_data['processing_msg'].edit_text(
                "🔑 *Iniciando sesión...*\n"
                "Conectando con la plataforma...",
                parse_mode='Markdown'
            )
        
        # Iniciar sesión
        if not uploader.login():
            await update.message.reply_text(
                "❌ *Error de autenticación*\n\n"
                "Credenciales incorrectas o problema de conexión.\n"
                "Verifica usuario/contraseña e intenta de nuevo.",
                parse_mode='Markdown'
            )
            
            # Limpiar archivo temporal
            if os.path.exists(user_info['file_path']):
                os.remove(user_info['file_path'])
            
            del user_data[user_id]
            return ConversationHandler.END
        
        # Función de progreso
        def progress_callback(filename, bytes_read, total_bytes, speed, estimated_time, args):
            percent = (bytes_read / total_bytes) * 100
            speed_mb = speed / 1024 / 1024 if speed > 0 else 0
            
            # Solo actualizar cada 5% o cuando se complete
            if hasattr(progress_callback, 'last_percent'):
                if percent - progress_callback.last_percent < 5 and percent < 100:
                    return
            progress_callback.last_percent = percent
            
            # Enviar actualización (en un bot real, usaríamos editar mensaje)
            # Por simplicidad, solo mostramos en logs
            logger.info(f"Progreso: {filename} - {percent:.1f}%")
        
        progress_callback.last_percent = 0
        
        # Subir archivo
        error_msg, result = uploader.upload_file(
            progressfunc=progress_callback,
            args=(),
            tokenize=False
        )
        
        # Cerrar sesión
        uploader.logout()
        
        # Limpiar archivo temporal
        if os.path.exists(user_info['file_path']):
            os.remove(user_info['file_path'])
        
        if error_msg:
            await update.message.reply_text(
                f"❌ *Error en la subida*\n\n"
                f"Detalles: {error_msg}\n\n"
                f"Por favor, intenta de nuevo.",
                parse_mode='Markdown'
            )
        else:
            # Mostrar resultado
            platform_names = {
                "Moodle": "Moodle",
                "OJS": "OJS",
                "Next": "Nextcloud"
            }
            
            success_text = (
                f"✅ *¡ARCHIVO SUBIDO EXITOSAMENTE!*\n\n"
                f"📋 *Detalles:*\n"
                f"• Plataforma: {platform_names[user_info['platform']]}\n"
                f"• Archivo: {user_info['file_name']}\n"
                f"• Usuario: {user_info['login_user']}\n\n"
                f"🔗 *Enlace de descarga:*\n"
                f"`{result['url']}`\n\n"
                f"📝 *Nota:* El enlace puede tener límite de tiempo\n"
                f"🔄 Usa /upload para subir otro archivo"
            )
            
            await update.message.reply_text(
                success_text,
                parse_mode='Markdown'
            )
        
        # Limpiar datos del usuario
        del user_data[user_id]
        
        return ConversationHandler.END
        
    except Exception as e:
        logger.error(f"Error en subida: {e}\n{traceback.format_exc()}")
        
        # Limpiar archivo temporal si existe
        if user_id in user_data and 'file_path' in user_data[user_id]:
            if os.path.exists(user_data[user_id]['file_path']):
                os.remove(user_data[user_id]['file_path'])
        
        if user_id in user_data:
            del user_data[user_id]
        
        await update.message.reply_text(
            "❌ *Error inesperado*\n\n"
            "Ocurrió un problema durante la subida.\n"
            "Por favor, intenta de nuevo o contacta al administrador.\n\n"
            f"🛠️ Soporte: @{ADMIN_ALIAS}",
            parse_mode='Markdown'
        )
        
        return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancela la conversación."""
    user_id, username = get_user_info(update)
    
    # Limpiar datos
    if user_id in user_data:
        # Eliminar archivo temporal si existe
        if 'file_path' in user_data[user_id]:
            if os.path.exists(user_data[user_id]['file_path']):
                os.remove(user_data[user_id]['file_path'])
        del user_data[user_id]
    
    await update.message.reply_text(
        "❌ *Operación cancelada*\n\n"
        "Puedes comenzar de nuevo con /upload",
        parse_mode='Markdown'
    )
    
    return ConversationHandler.END

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Maneja errores no capturados."""
    logger.error(f"Error: {context.error}")
    
    if update and update.effective_message:
        await update.effective_message.reply_text(
            "❌ *Error interno del bot*\n\n"
            "Por favor, intenta de nuevo o contacta al administrador.",
            parse_mode='Markdown'
        )

# ========= FUNCIÓN PRINCIPAL =========
def main() -> None:
    """Inicia el bot."""
    # Verificar token
    if TELEGRAM_BOT_TOKEN == "TU_TOKEN_AQUI":
        print("❌ ERROR: Debes configurar el token del bot en TELEGRAM_BOT_TOKEN")
        print("💡 Reemplaza 'TU_TOKEN_AQUI' con tu token real")
        sys.exit(1)
    
    print("🤖 Iniciando bot de subida de archivos...")
    print(f"👑 Administrador: @{ADMIN_ALIAS}")
    print("🔗 Proxy SOCKS5 configurado")
    print("📁 Uploader unificado cargado")
    
    # Crear aplicación
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    # Crear conversation handler para subida
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("upload", upload_start)],
        states={
            PLATFORM: [CallbackQueryHandler(platform_selection)],
            CREDENTIALS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, get_host),
                MessageHandler(filters.TEXT & ~filters.COMMAND, get_credentials)
            ],
            FILE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_repo_id)],
            UPLOAD: [MessageHandler(filters.Document.ALL, handle_file)]
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    
    # Añadir handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("status", status))
    application.add_handler(CommandHandler("stats", stats))
    application.add_handler(CommandHandler("reset", reset))
    application.add_handler(conv_handler)
    
    # Añadir manejador de errores
    application.add_error_handler(error_handler)
    
    # Iniciar bot
    print("✅ Bot iniciado correctamente")
    print("📡 Escuchando mensajes...")
    print("🛑 Presiona Ctrl+C para detener")
    
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
