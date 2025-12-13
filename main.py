#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Bot de Telegram para subir archivos a Moodle, OJS y Next
Archivo principal - Versión Render-ready
"""

import logging
import os
import sys
import traceback
import time
from typing import Dict, Optional, Tuple
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
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
# TOKEN DEL BOT - ¡REEMPLAZA ESTO CON TU TOKEN REAL!
TELEGRAM_BOT_TOKEN = "8189412029:AAH2YH0WRe16oMYOoxISHlnxWK4zNEvOfio"  # Cambia esto por tu token real

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

def escape_html(text: str) -> str:
    """Escapa caracteres especiales para HTML."""
    return (text.replace('&', '&amp;')
                .replace('<', '&lt;')
                .replace('>', '&gt;')
                .replace('"', '&quot;'))

# ========= COMANDOS =========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Inicia la conversación."""
    user_id, username = get_user_info(update)
    username_escaped = escape_html(username)
    
    welcome_text = (
        f"👋 ¡Hola {username_escaped}!\n\n"
        "<b>🤖 Bot de Subida de Archivos</b>\n\n"
        "📤 <b>Puedo subir archivos a:</b>\n"
        "• 📚 Moodle\n"
        "• 📄 OJS (Open Journal Systems)\n"
        "• ☁️ Nextcloud\n\n"
        "⚠️ <b>IMPORTANTE:</b>\n"
        "• Este bot funciona mediante proxy\n"
        "• Los archivos se suben temporalmente\n"
        "• No se almacenan credenciales\n\n"
        "📝 Usa /help para ver comandos disponibles\n"
        "🚀 Usa /upload para comenzar"
    )
    
    await update.message.reply_text(welcome_text, parse_mode='HTML')
    return ConversationHandler.END

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Muestra la ayuda."""
    help_text = (
        "<b>📚 COMANDOS DISPONIBLES:</b>\n\n"
        "📝 /start - Inicia el bot\n"
        "📤 /upload - Subir un archivo\n"
        "❓ /help - Muestra esta ayuda\n"
        "ℹ️ /status - Estado del bot\n"
        "📊 /stats - Estadísticas (admin)\n"
        "🔄 /reset - Reinicia tu sesión\n\n"
        "<b>📋 PROCESO DE SUBIDA:</b>\n"
        "1. Selecciona plataforma\n"
        "2. Ingresa credenciales\n"
        "3. Envía el archivo\n"
        "4. ¡Listo! Obtén el enlace\n\n"
        "<b>📎 ARCHIVOS SOPORTADOS:</b>\n"
        "• PDF (.pdf)\n"
        "• Word (.doc, .docx)\n"
        "• Texto (.txt)\n\n"
        f"<b>⚡ ADMIN:</b> @{ADMIN_ALIAS}"
    )
    
    await update.message.reply_text(help_text, parse_mode='HTML')

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Muestra el estado del bot."""
    status_text = (
        "<b>✅ BOT ACTIVO</b>\n\n"
        "<b>🔧 Funcionalidades:</b>\n"
        "• Subida a Moodle ✓\n"
        "• Subida a OJS ✓\n"
        "• Subida a Nextcloud ✓\n"
        "• Proxy SOCKS5 ✓\n"
        "• Progreso de subida ✓\n\n"
        f"<b>📊 Estadísticas:</b>\n"
        f"• Usuarios activos: {len(user_data)}\n"
        "• Última actualización: Funcionando\n\n"
        f"<b>🛠️ Soporte:</b> Contacta a @{ADMIN_ALIAS}"
    )
    
    await update.message.reply_text(status_text, parse_mode='HTML')

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Muestra estadísticas (solo admin)."""
    if not is_admin(update):
        await update.message.reply_text(
            "❌ Solo el administrador puede ver estadísticas.",
            parse_mode='HTML'
        )
        return
    
    stats_text = (
        "<b>📊 ESTADÍSTICAS DEL BOT</b>\n\n"
        f"👥 Usuarios en sesión: {len(user_data)}\n"
        f"🆔 Tu ID: {update.effective_user.id}\n"
        f"👤 Tu alias: @{escape_html(update.effective_user.username or 'No disponible')}\n\n"
        "<b>💾 Almacenamiento temporal:</b>\n"
    )
    
    # Contar usuarios por plataforma
    platforms = {'Moodle': 0, 'OJS': 0, 'Next': 0}
    for data in user_data.values():
        if 'platform' in data:
            platforms[data['platform']] += 1
    
    stats_text += f"• Moodle: {platforms['Moodle']}\n"
    stats_text += f"• OJS: {platforms['OJS']}\n"
    stats_text += f"• Nextcloud: {platforms['Next']}\n"
    
    await update.message.reply_text(stats_text, parse_mode='HTML')

async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Reinicia la sesión del usuario."""
    user_id, username = get_user_info(update)
    
    if user_id in user_data:
        # Eliminar archivo temporal si existe
        if 'file_path' in user_data[user_id]:
            try:
                os.remove(user_data[user_id]['file_path'])
            except:
                pass
        del user_data[user_id]
    
    await update.message.reply_text(
        "<b>✅ Sesión reiniciada</b>\n\n"
        "Todos tus datos temporales han sido eliminados.\n"
        "Puedes comenzar de nuevo con /upload",
        parse_mode='HTML'
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
        "<b>📤 SUBIR ARCHIVO</b>\n\n"
        "<b>1️⃣ Selecciona la plataforma:</b>\n\n"
        "• <b>📚 Moodle:</b> Para cursos y materiales\n"
        "• <b>📄 OJS:</b> Para revistas académicas\n"
        "• <b>☁️ Nextcloud:</b> Almacenamiento en la nube\n\n"
        "⚠️ <b>Nota:</b> Necesitarás credenciales de acceso",
        reply_markup=reply_markup,
        parse_mode='HTML'
    )
    
    return PLATFORM

async def platform_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Procesa la selección de plataforma."""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    
    if query.data == "cancel":
        await query.edit_message_text("❌ Subida cancelada.", parse_mode='HTML')
        if user_id in user_data:
            del user_data[user_id]
        return ConversationHandler.END
    
    user_data[user_id]['platform'] = query.data
    
    platform_info = {
        "Moodle": "📚 <b>PLATAFORMA: MOODLE</b>\n\n🔗 Ejemplo de URL: https://moodle.uclv.edu.cu/",
        "OJS": "📄 <b>PLATAFORMA: OJS</b>\n\n🔗 Ejemplo de URL: https://evea.uh.cu/",
        "Next": "☁️ <b>PLATAFORMA: NEXTCLOUD</b>\n\n🔗 Ejemplo de URL: https://minube.uh.cu/"
    }
    
    await query.edit_message_text(
        f"{platform_info[query.data]}\n\n"
        "<b>2️⃣ Ingresa la URL de la plataforma:</b>\n\n"
        "📝 Envíame la URL completa incluyendo https://\n"
        "Ejemplo: https://moodle.uclv.edu.cu/",
        parse_mode='HTML'
    )
    
    return CREDENTIALS

async def get_host(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Procesa la URL del host."""
    user_id, username = get_user_info(update)
    
    host = update.message.text.strip()
    
    # Validar URL básica
    if not host.startswith(('http://', 'https://')):
        await update.message.reply_text(
            "❌ <b>URL inválida</b>\n\n"
            "Debe comenzar con http:// o https://\n"
            "Por favor, envíala de nuevo:",
            parse_mode='HTML'
        )
        return CREDENTIALS
    
    user_data[user_id]['host'] = host
    
    # Pedir credenciales según plataforma
    platform = user_data[user_id]['platform']
    
    if platform == "Next":
        cred_text = (
            "<b>3️⃣ CREDENCIALES NEXTCLOUD</b>\n\n"
            "🔑 <b>Usuario:</b> Tu nombre de usuario de Nextcloud\n"
            "🔐 <b>Contraseña:</b> Tu contraseña de Nextcloud\n\n"
            "📝 <b>Envía las credenciales en este formato:</b>\n"
            "usuario:contraseña\n\n"
            "Ejemplo: estudiante:miContraseña123"
        )
    else:
        cred_text = (
            f"<b>3️⃣ CREDENCIALES {platform}</b>\n\n"
            "🔑 <b>Usuario:</b> Tu nombre de usuario\n"
            "🔐 <b>Contraseña:</b> Tu contraseña\n\n"
            "📝 <b>Envía las credenciales en este formato:</b>\n"
            "usuario:contraseña\n\n"
            "Ejemplo: estudiante:miContraseña123"
        )
    
    await update.message.reply_text(cred_text, parse_mode='HTML')
    
    return CREDENTIALS

async def get_credentials(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Procesa las credenciales."""
    user_id, username = get_user_info(update)
    
    credentials = update.message.text.strip()
    
    # Validar formato
    if ':' not in credentials:
        await update.message.reply_text(
            "❌ <b>Formato incorrecto</b>\n\n"
            "Debe ser: usuario:contraseña\n\n"
            "Por favor, envíalo de nuevo:",
            parse_mode='HTML'
        )
        return CREDENTIALS
    
    username_input, password = credentials.split(':', 1)
    user_data[user_id]['login_user'] = username_input.strip()
    user_data[user_id]['login_pass'] = password.strip()
    
    # Pedir repo_id según plataforma
    platform = user_data[user_id]['platform']
    
    if platform == "Moodle":
        repo_text = (
            "<b>4️⃣ ID DEL REPOSITORIO MOODLE</b>\n\n"
            "🔢 <b>Repository ID:</b> Número del repositorio (generalmente 4)\n\n"
            "📝 <b>Envía solo el número:</b>\n"
            "Ejemplo: 4"
        )
    elif platform == "OJS":
        repo_text = (
            "<b>4️⃣ ID DE ENVÍO OJS</b>\n\n"
            "🔢 <b>Submission ID:</b> Número del envío\n\n"
            "📝 <b>Envía solo el número:</b>\n"
            "Ejemplo: 123"
        )
    else:  # Next
        repo_text = (
            "<b>4️⃣ CONFIRMACIÓN NEXTCLOUD</b>\n\n"
            "Para Nextcloud no se necesita ID.\n"
            "Envía cualquier texto para continuar:"
        )
    
    await update.message.reply_text(repo_text, parse_mode='HTML')
    
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
                "❌ <b>Debe ser un número</b>\n\n"
                "Por favor, envía solo el número:",
                parse_mode='HTML'
            )
            return FILE
    
    # Pedir archivo
    await update.message.reply_text(
        "<b>📎 ENVÍA EL ARCHIVO</b>\n\n"
        "⬆️ <b>Sube el archivo que deseas enviar:</b>\n\n"
        "📋 <b>Formatos soportados:</b>\n"
        "• PDF (.pdf)\n"
        "• Word (.doc, .docx)\n"
        "• Texto (.txt)\n\n"
        "⚠️ <b>Tamaño máximo:</b> 100MB\n"
        "⏱️ <b>Procesando:</b> ~1-2 minutos",
        parse_mode='HTML'
    )
    
    return UPLOAD

async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Procesa el archivo enviado."""
    user_id, username = get_user_info(update)
    
    # Verificar si es documento
    if not update.message.document:
        await update.message.reply_text(
            "❌ <b>Por favor, envía un archivo</b>\n\n"
            "Usa el clip 📎 para adjuntar un documento.",
            parse_mode='HTML'
        )
        return UPLOAD
    
    document = update.message.document
    
    # Verificar tipo de archivo
    allowed_types = ['application/pdf', 'application/msword', 
                    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                    'text/plain']
    
    if document.mime_type not in allowed_types:
        await update.message.reply_text(
            "❌ <b>Tipo de archivo no soportado</b>\n\n"
            "Solo se aceptan:\n"
            "• PDF (.pdf)\n"
            "• Word (.doc, .docx)\n"
            "• Texto (.txt)",
            parse_mode='HTML'
        )
        return UPLOAD
    
    # Verificar tamaño (100MB)
    if document.file_size > 100 * 1024 * 1024:
        await update.message.reply_text(
            "❌ <b>Archivo muy grande</b>\n\n"
            "El tamaño máximo es 100MB.",
            parse_mode='HTML'
        )
        return UPLOAD
    
    # Descargar archivo
    processing_msg = await update.message.reply_text(
        "⏬ <b>Descargando archivo...</b>\n"
        "Por favor espera...",
        parse_mode='HTML'
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
            "✅ <b>Archivo descargado</b>\n\n"
            "<b>📊 Información:</b>\n"
            f"• Nombre: {escape_html(document.file_name)}\n"
            f"• Tamaño: {document.file_size / 1024 / 1024:.2f} MB\n\n"
            "🚀 <b>Iniciando subida...</b>",
            parse_mode='HTML'
        )
        
        # Realizar la subida
        return await perform_upload(update, context, user_id, processing_msg)
        
    except Exception as e:
        logger.error(f"Error descargando archivo: {e}")
        await processing_msg.edit_text(
            "❌ <b>Error al descargar el archivo</b>\n\n"
            "Por favor, intenta de nuevo.",
            parse_mode='HTML'
        )
        return UPLOAD

async def perform_upload(update: Update, context: ContextTypes.DEFAULT_TYPE, 
                        user_id: int, processing_msg) -> int:
    """Realiza la subida del archivo."""
    try:
        user_info = user_data[user_id]
        
        await processing_msg.edit_text(
            "🔑 <b>Iniciando sesión...</b>\n"
            f"Usuario: {escape_html(user_info['login_user'])}\n"
            f"Plataforma: {user_info['platform']}",
            parse_mode='HTML'
        )
        
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
        
        # Iniciar sesión
        if not uploader.login():
            await processing_msg.edit_text(
                "❌ <b>Error de autenticación</b>\n\n"
                "Credenciales incorrectas o problema de conexión.\n"
                "Verifica usuario/contraseña e intenta de nuevo.",
                parse_mode='HTML'
            )
            
            # Limpiar archivo temporal
            if os.path.exists(user_info['file_path']):
                try:
                    os.remove(user_info['file_path'])
                except:
                    pass
            
            del user_data[user_id]
            return ConversationHandler.END
        
        # Subir archivo
        await processing_msg.edit_text(
            "📤 <b>Subiendo archivo...</b>\n"
            f"Archivo: {escape_html(user_info['file_name'])}\n"
            "Progreso: 0%",
            parse_mode='HTML'
        )
        
        # Función de progreso simple
        last_percent = 0
        
        def progress_callback(filename, bytes_read, total_bytes, speed, estimated_time, args):
            nonlocal last_percent
            percent = (bytes_read / total_bytes) * 100
            
            # Solo actualizar cada 10% de progreso
            if percent - last_percent >= 10 or percent >= 100:
                last_percent = percent
                # Nota: Esta función se ejecuta en un hilo diferente
                # No podemos actualizar el mensaje aquí directamente
                logger.info(f"Progreso de subida: {filename} - {percent:.1f}%")
        
        error_msg, result = uploader.upload_file(
            progressfunc=progress_callback,
            args=(),
            tokenize=False
        )
        
        # Cerrar sesión
        uploader.logout()
        
        # Limpiar archivo temporal
        if os.path.exists(user_info['file_path']):
            try:
                os.remove(user_info['file_path'])
            except:
                pass
        
        if error_msg:
            await processing_msg.edit_text(
                f"❌ <b>Error en la subida</b>\n\n"
                f"Detalles: {escape_html(error_msg)}\n\n"
                f"Por favor, intenta de nuevo.",
                parse_mode='HTML'
            )
        else:
            # Mostrar resultado
            platform_names = {
                "Moodle": "Moodle",
                "OJS": "OJS",
                "Next": "Nextcloud"
            }
            
            success_text = (
                f"✅ <b>¡ARCHIVO SUBIDO EXITOSAMENTE!</b>\n\n"
                f"<b>📋 Detalles:</b>\n"
                f"• Plataforma: {platform_names[user_info['platform']]}\n"
                f"• Archivo: {escape_html(user_info['file_name'])}\n"
                f"• Usuario: {escape_html(user_info['login_user'])}\n\n"
                f"<b>🔗 Enlace de descarga:</b>\n"
                f"<code>{escape_html(result['url'])}</code>\n\n"
                f"📝 <b>Nota:</b> El enlace puede tener límite de tiempo\n"
                f"🔄 Usa /upload para subir otro archivo"
            )
            
            await processing_msg.edit_text(success_text, parse_mode='HTML')
        
        # Limpiar datos del usuario
        if user_id in user_data:
            del user_data[user_id]
        
        return ConversationHandler.END
        
    except Exception as e:
        logger.error(f"Error en subida: {e}\n{traceback.format_exc()}")
        
        await processing_msg.edit_text(
            "❌ <b>Error inesperado</b>\n\n"
            "Ocurrió un problema durante la subida.\n"
            "Por favor, intenta de nuevo o contacta al administrador.\n\n"
            f"🛠️ Soporte: @{ADMIN_ALIAS}",
            parse_mode='HTML'
        )
        
        # Limpiar archivo temporal si existe
        if user_id in user_data and 'file_path' in user_data[user_id]:
            try:
                os.remove(user_data[user_id]['file_path'])
            except:
                pass
        
        if user_id in user_data:
            del user_data[user_id]
        
        return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancela la conversación."""
    user_id, username = get_user_info(update)
    
    # Limpiar datos
    if user_id in user_data:
        # Eliminar archivo temporal si existe
        if 'file_path' in user_data[user_id]:
            try:
                os.remove(user_data[user_id]['file_path'])
            except:
                pass
        del user_data[user_id]
    
    await update.message.reply_text(
        "❌ <b>Operación cancelada</b>\n\n"
        "Puedes comenzar de nuevo con /upload",
        parse_mode='HTML'
    )
    
    return ConversationHandler.END

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Maneja errores no capturados."""
    logger.error(f"Error: {context.error}", exc_info=True)
    
    if update and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "❌ <b>Error interno del bot</b>\n\n"
                "Por favor, intenta de nuevo o contacta al administrador.",
                parse_mode='HTML'
            )
        except:
            pass

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
    
    try:
        # Crear aplicación con ApplicationBuilder
        application = (
            ApplicationBuilder()
            .token(TELEGRAM_BOT_TOKEN)
            .concurrent_updates(True)
            .pool_timeout(30)
            .connect_timeout(30)
            .read_timeout(30)
            .write_timeout(30)
            .post_init(lambda app: print("✅ Bot configurado correctamente"))
            .build()
        )
        
        # Crear conversation handler para subida
        conv_handler = ConversationHandler(
            entry_points=[CommandHandler("upload", upload_start)],
            states={
                PLATFORM: [CallbackQueryHandler(platform_selection)],
                CREDENTIALS: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, get_host),
                ],
                FILE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_repo_id)],
                UPLOAD: [MessageHandler(filters.Document.ALL, handle_file)]
            },
            fallbacks=[CommandHandler("cancel", cancel)],
            allow_reentry=True
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
        print("=" * 50)
        
        # Ejecutar polling con drop_pending_updates
        application.run_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True,
            close_loop=False
        )
        
    except KeyboardInterrupt:
        print("\n🛑 Bot detenido por usuario")
        sys.exit(0)
    except Exception as e:
        print(f"❌ Error crítico al iniciar el bot: {e}")
        traceback.print_exc()
        sys.exit(1)

if __name__ == '__main__':
    main()
