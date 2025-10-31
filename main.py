import os
import asyncio
from pyrogram import Client, filters
from pytgcalls import PyTgCalls, idle
from pytgcalls.types.input_stream import AudioPiped, HighQualityAudio
import yt_dlp
import shutil

API_ID = int(os.environ["API_ID"])
API_HASH = os.environ["API_HASH"]
BOT_TOKEN = os.environ["BOT_TOKEN"]
SESSION_STRING = os.environ["SESSION_STRING"]

bot = Client("music_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
user = Client("userbot", api_id=API_ID, api_hash=API_HASH, session_string=SESSION_STRING)
call = PyTgCalls(user)

@bot.on_message(filters.command("start"))
async def start(_, message):
await message.reply(
"👋 Hey!\nUse /play <song name> to play music in the voice chat.\nUse /stop to stop playback."
)

@bot.on_message(filters.command("play") & filters.group)
async def play(_, message):
chat_id = message.chat.id
query = " ".join(message.text.split()[1:])
if not query:
return await message.reply("❌ Please provide a song name to play!")

m = await message.reply("🔍 Searching for the song...")  
os.makedirs("downloads", exist_ok=True)  

# Clear old downloads  
for f in os.listdir("downloads"):  
    os.remove(os.path.join("downloads", f))  

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
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:  
        info = ydl.extract_info(f"ytsearch:{query}", download=True)  
        song = info["entries"][0]  
        title = song["title"]  
        base = os.path.splitext(ydl.prepare_filename(song))[0]  

    file_path = None  
    for ext in [".mp3", ".m4a", ".webm"]:  
        if os.path.exists(base + ext):  
            file_path = base + ext  
            break  
    if not file_path:  
        raise FileNotFoundError("Audio file not found after download.")  

    # Leave old call if any  
    try:  
        await call.leave_group_call(chat_id)  
    except:  
        pass  

    await m.edit("🎧 Download complete! Joining voice chat...")  

    await call.join_group_call(  
        chat_id,  
        AudioPiped(file_path, audio_parameters=HighQualityAudio())  
    )  

    await m.edit(f"🎶 **Now playing:** {title}")  

except Exception as e:  
    await m.edit(f"⚠️ Error: `{e}`")

@bot.on_message(filters.command("stop") & filters.group)
async def stop(_, message):
chat_id = message.chat.id
try:
await call.leave_group_call(chat_id)
shutil.rmtree("downloads", ignore_errors=True)
await message.reply("⏹️ Music stopped and left VC.")
except Exception as e:
await message.reply(f"⚠️ Error: {e}")

async def main():
await bot.start()
await user.start()
await call.start()
print("✅ Bot and Userbot both are LIVE and ready!")
await idle()

if name == "main":
try:
asyncio.run(main())
except KeyboardInterrupt:
print("🛑 Bot stopped manually.")
