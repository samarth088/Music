import os
import asyncio
import logging
import traceback
from flask import Flask
from pyrogram import Client, filters
from pyrogram.errors import (
    FloodWait, 
    ChatAdminRequired, 
    UserNotParticipant,
    ChannelPrivate
)
import yt_dlp
import shutil
from typing import Optional

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Try importing py_tgcalls with error handling
PyTgCalls = None
idle = None
AudioPiped = None
HighQualityAudio = None

try:
    from pytgcalls import PyTgCalls, idle
    from pytgcalls.types import AudioPiped, HighQualityAudio
    PYTGCALLS_AVAILABLE = True
    logger.info("✅ pytgcalls imported successfully")
except ImportError as e:
    logger.error(f"❌ Failed to import pytgcalls: {e}")
    logger.info("Trying alternative import from py_tgcalls...")
    try:
        from py_tgcalls import PyTgCalls, idle
        from py_tgcalls.types import AudioPiped, HighQualityAudio
        PYTGCALLS_AVAILABLE = True
        logger.info("✅ py_tgcalls imported successfully")
    except ImportError as e2:
        logger.critical(f"❌ Both pytgcalls imports failed: {e2}")
        PYTGCALLS_AVAILABLE = False

# Environment variable validation
def get_env_var(key: str, required: bool = True) -> Optional[str]:
    """Safely get environment variable with validation"""
    value = os.environ.get(key)
    if required and not value:
        logger.error(f"❌ Missing required environment variable: {key}")
        raise ValueError(f"Environment variable {key} is required but not set")
    return value

# Initialize with error handling
try:
    API_ID = int(get_env_var("API_ID"))
    API_HASH = get_env_var("API_HASH")
    BOT_TOKEN = get_env_var("BOT_TOKEN")
    SESSION_STRING = get_env_var("SESSION_STRING")
    logger.info("✅ Environment variables loaded successfully")
except Exception as e:
    logger.critical(f"❌ Failed to load environment variables: {e}")
    raise

# Initialize clients with error handling
try:
    bot = Client("music_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
    user = Client("userbot", api_id=API_ID, api_hash=API_HASH, session_string=SESSION_STRING)
    if PYTGCALLS_AVAILABLE:
        call = PyTgCalls(user)
    else:
        call = None
    logger.info("✅ Telegram clients initialized")
except Exception as e:
    logger.critical(f"❌ Failed to initialize clients: {e}")
    raise

# Flask server
app = Flask(__name__)

@app.route('/')
def home():
    status = "✅" if PYTGCALLS_AVAILABLE else "⚠️"
    return f"{status} Telegram Music Bot - pytgcalls: {'Available' if PYTGCALLS_AVAILABLE else 'Not Available'}"

@app.route('/health')
def health():
    """Health check endpoint for monitoring"""
    return {
        "status": "healthy" if PYTGCALLS_AVAILABLE else "degraded",
        "pytgcalls": PYTGCALLS_AVAILABLE,
        "bot": "running"
    }

# Error handler decorator
def error_handler(func):
    """Decorator to handle errors in command handlers"""
    async def wrapper(client, message):
        try:
            return await func(client, message)
        except FloodWait as e:
            logger.warning(f"FloodWait: sleeping for {e.x} seconds")
            await message.reply(f"⏳ Rate limited. Please wait {e.x} seconds.")
            await asyncio.sleep(e.x)
        except ChatAdminRequired:
            logger.error("Bot needs admin rights")
            await message.reply("❌ I need admin rights to perform this action!")
        except UserNotParticipant:
            await message.reply("❌ Please join the voice chat first!")
        except ChannelPrivate:
            await message.reply("❌ This is a private channel I can't access.")
        except Exception as e:
            logger.error(f"Unexpected error in {func.__name__}: {traceback.format_exc()}")
            await message.reply(f"❌ An error occurred: `{str(e)[:100]}`")
    return wrapper

# Commands
@bot.on_message(filters.command("start"))
@error_handler
async def start(_, message):
    status_msg = "✅ All systems operational" if PYTGCALLS_AVAILABLE else "⚠️ Voice features unavailable"
    await message.reply(
        f"👋 **Hey!**\n\n"
        f"Status: {status_msg}\n\n"
        f"Use `/play <song name>` to play music in the voice chat.\n"
        f"Use `/stop` to stop playback.\n"
        f"Use `/status` to check bot status."
    )

@bot.on_message(filters.command("status"))
@error_handler
async def status(_, message):
    """Check bot status"""
    await message.reply(
        f"**Bot Status:**\n\n"
        f"🤖 Bot: ✅ Running\n"
        f"👤 Userbot: ✅ Connected\n"
        f"🎵 Voice Calls: {'✅ Available' if PYTGCALLS_AVAILABLE else '❌ Not Available'}\n"
        f"📁 Downloads: {'✅ Ready' if os.path.exists('downloads') else '⚠️ Creating...'}"
    )

@bot.on_message(filters.command("play") & filters.group)
@error_handler
async def play(_, message):
    if not PYTGCALLS_AVAILABLE:
        return await message.reply("❌ Voice call features are not available. Check deployment logs.")
    
    chat_id = message.chat.id
    query = " ".join(message.text.split()[1:])
    
    if not query:
        return await message.reply("❌ Please provide a song name!\nUsage: `/play song name`")

    m = await message.reply("🔍 Searching for the song...")
    
    # Ensure downloads directory exists
    try:
        os.makedirs("downloads", exist_ok=True)
        logger.info("Downloads directory ready")
    except Exception as e:
        logger.error(f"Failed to create downloads directory: {e}")
        return await m.edit("❌ Failed to prepare download directory")

    # Clear old downloads
    try:
        for f in os.listdir("downloads"):
            file_path = os.path.join("downloads", f)
            try:
                os.remove(file_path)
            except Exception as e:
                logger.warning(f"Could not remove {file_path}: {e}")
    except Exception as e:
        logger.warning(f"Error cleaning downloads: {e}")

    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": "downloads/%(title)s.%(ext)s",
        "quiet": True,
        "noplaylist": True,
        "geo_bypass": True,
        "nocheckcertificate": True,
        "postprocessors": [
            {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}
        ],
    }

    try:
        await m.edit("⬇️ Downloading audio...")
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(f"ytsearch:{query}", download=True)
            
            if not info or "entries" not in info or not info["entries"]:
                raise ValueError("No results found for this query")
            
            song = info["entries"][0]
            title = song.get("title", "Unknown Title")
            base = os.path.splitext(ydl.prepare_filename(song))[0]

        # Find the downloaded file
        file_path = None
        for ext in [".mp3", ".m4a", ".webm", ".opus"]:
            potential_path = base + ext
            if os.path.exists(potential_path):
                file_path = potential_path
                logger.info(f"Found audio file: {file_path}")
                break

        if not file_path:
            raise FileNotFoundError(f"Audio file not found. Expected base: {base}")

        # Leave any existing call
        try:
            await call.leave_group_call(chat_id)
            logger.info(f"Left existing call in {chat_id}")
        except Exception as e:
            logger.debug(f"No existing call to leave: {e}")

        await m.edit("🎧 Joining voice chat...")

        # Join voice chat
        await call.join_group_call(
            chat_id,
            AudioPiped(file_path, audio_parameters=HighQualityAudio())
        )

        await m.edit(f"🎶 **Now playing:** {title}")
        logger.info(f"Successfully playing: {title} in chat {chat_id}")

    except yt_dlp.utils.DownloadError as e:
        logger.error(f"YouTube download error: {e}")
        await m.edit(f"❌ Download failed: Video unavailable or restricted")
    except FileNotFoundError as e:
        logger.error(f"File not found: {e}")
        await m.edit("❌ Downloaded file not found. Try again.")
    except Exception as e:
        logger.error(f"Play command error: {traceback.format_exc()}")
        await m.edit(f"❌ Error: `{str(e)[:150]}`")

@bot.on_message(filters.command("stop") & filters.group)
@error_handler
async def stop(_, message):
    if not PYTGCALLS_AVAILABLE:
        return await message.reply("❌ Voice call features are not available.")
    
    chat_id = message.chat.id
    try:
        await call.leave_group_call(chat_id)
        shutil.rmtree("downloads", ignore_errors=True)
        await message.reply("⏹️ Music stopped and left voice chat.")
        logger.info(f"Stopped playback in chat {chat_id}")
    except Exception as e:
        logger.error(f"Stop command error: {e}")
        await message.reply(f"⚠️ Error stopping: `{str(e)[:100]}`")

# Main Function
async def main():
    """Main bot initialization"""
    try:
        logger.info("Starting bot...")
        await bot.start()
        logger.info("✅ Bot started")
        
        await user.start()
        logger.info("✅ Userbot started")
        
        if PYTGCALLS_AVAILABLE and call:
            await call.start()
            logger.info("✅ PyTgCalls started")
        else:
            logger.warning("⚠️ PyTgCalls not available - voice features disabled")
        
        logger.info("🎉 All systems ready!")
        await idle()
    except Exception as e:
        logger.critical(f"❌ Failed to start bot: {traceback.format_exc()}")
        raise

if __name__ == "__main__":
    import threading

    # Run Flask server on separate thread for Render
    port = int(os.environ.get("PORT", 10000))
    threading.Thread(
        target=lambda: app.run(host="0.0.0.0", port=port, debug=False),
        daemon=True
    ).start()
    logger.info(f"✅ Flask server started on port {port}")

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 Bot stopped manually")
    except Exception as e:
        logger.critical(f"🔥 Fatal error: {traceback.format_exc()}")
