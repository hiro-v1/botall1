import time
import asyncio
from pyrogram import Client, filters
from pymongo import MongoClient
from pyrogram.types import Message
from config import API_ID, API_HASH, BOT_TOKEN, MONGO_URI, CREATOR_ID
from dotenv import load_dotenv

load_dotenv()

# Koneksi ke MongoDB
client_mongo = MongoClient(MONGO_URI)
db = client_mongo["tagall_bot_db"]
users_collection = db["users"]
requests_collection = db["requests"]

# Inisialisasi bot dengan Pyrogram
bot = Client("botall", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# Fungsi untuk mendapatkan admin yang disetujui
def get_approved_admins():
    admins = users_collection.find({"role": "admin", "approved": True})
    return [admin["user_id"] for admin in admins]

# Fungsi untuk mendapatkan partnergc
def get_partnergcs():
    partnergcs = users_collection.find({"role": "partnergc"})
    return [partnergc["user_id"] for partnergc in partnergcs]

# Fungsi untuk menyimpan permintaan tagall ke MongoDB
def save_tagall_request(user_id, chat_id, message_text):
    requests_collection.insert_one({
        "user_id": user_id,
        "chat_id": chat_id,
        "message_text": message_text,
        "status": "pending",  # Menunggu persetujuan admin
        "timestamp": time.time()
    })

# Fungsi untuk memperbarui status permintaan tagall
def update_tagall_request_status(request_id, status):
    requests_collection.update_one(
        {"_id": request_id},
        {"$set": {"status": status}}
    )

# Fungsi untuk menjalankan tagall
async def perform_tagall(group_id, message_text, active_members):
    if active_members:
        tag_message = f"{message_text}\n" + " ".join([f"@{member}" for member in active_members])
        await bot.send_message(group_id, tag_message)
    else:
        await bot.send_message(group_id, "Tidak ada anggota aktif dalam 5 menit terakhir untuk ditandai.")

# Fungsi untuk melacak anggota yang aktif dalam 5 menit terakhir
async def track_active_members(message):
    active_members = []
    active_members.append(message.from_user.username)  # Menyimpan anggota yang aktif
    await asyncio.sleep(300)  # Tunggu selama 5 menit
    active_members = [member for member in active_members if time.time() - message.date.timestamp() <= 300]
    return active_members

# Perintah untuk mendaftarkan partnergc
@bot.on_message(filters.command("jadipt") & filters.private)
async def register_partnergc(client, message: Message):
    if message.from_user.id in get_partnergcs():
        await message.reply("Anda sudah terdaftar sebagai partnergc.")
        return
    
    users_collection.update_one(
        {"user_id": message.from_user.id},
        {"$set": {"role": "partnergc", "approved": False}},  # Menunggu persetujuan
        upsert=True
    )
    await message.reply("Anda telah terdaftar sebagai partnergc. Tunggu persetujuan dari pemilik bot atau admin.")

# Perintah untuk menyetujui partnergc
@bot.on_message(filters.command("setuju") & filters.private)
async def approve_partnergc(client, message: Message):
    if message.from_user.id != CREATOR_ID:
        await message.reply("Hanya pemilik bot yang dapat menyetujui partnergc.")
        return

    user_id = message.reply_to_message.from_user.id
    users_collection.update_one(
        {"user_id": user_id},
        {"$set": {"approved": True}},
        upsert=True
    )
    await message.reply(f"User {message.reply_to_message.from_user.username} telah disetujui sebagai partnergc.")

# Perintah untuk request tagall oleh partnergc
@bot.on_message(filters.command("all") & filters.group)
async def all_command(client, message: Message):
    if message.from_user.id not in get_partnergcs():
        await message.reply("Hanya partnergc yang terdaftar yang dapat meminta tagall.")
        return

    if len(message.text.split(" ", 1)) < 2:
        await message.reply("Harap kirim perintah 'all' diikuti pesan.")
        return

    message_text = message.text.split(" ", 1)[1]
    save_tagall_request(message.from_user.id, message.chat.id, message_text)

    await message.reply("Permintaan tagall Anda telah dikirim dan sedang menunggu persetujuan admin.")

# Perintah untuk menyetujui permintaan tagall oleh admin
@bot.on_message(filters.command("oktag") & filters.group)
async def approve_tagall(client, message: Message):
    if message.from_user.id not in get_approved_admins():
        await message.reply("Hanya admin yang disetujui yang dapat menyetujui permintaan tagall.")
        return

    request = requests_collection.find_one({"chat_id": message.chat.id, "status": "pending"})
    if request:
        active_members = await track_active_members(message)
        await perform_tagall(message.chat.id, request["message_text"], active_members)
        update_tagall_request_status(request["_id"], "approved")
        await message.reply("Permintaan tagall telah disetujui dan dieksekusi.")
    else:
        await message.reply("Tidak ada permintaan tagall yang menunggu persetujuan.")

# Perintah untuk menghentikan tagall oleh admin
@bot.on_message(filters.command("stop") & filters.group)
async def stop_tagall(client, message: Message):
    if message.from_user.id not in get_approved_admins():
        await message.reply("Hanya admin yang disetujui yang dapat menghentikan tagall.")
        return

    requests_collection.update_many(
        {"status": "pending", "chat_id": message.chat.id},
        {"$set": {"status": "stopped"}}
    )
    await message.reply("Semua permintaan tagall yang menunggu telah dihentikan.")

# Perintah bantuan (help)
@bot.on_message(filters.command("help"))
async def help(client, message: Message):
    help_text = """
    *Panduan Penggunaan Bot*:
    
    1. **Mendaftar sebagai Partnergc**: Kirim perintah `/jadipt` untuk mendaftar sebagai partnergc (menunggu persetujuan admin).
    2. **Menyetujui Partnergc**: Admin atau pemilik bot dapat menyetujui partnergc dengan perintah `/setuju`.
    3. **Meminta Tagall**: Partnergc yang disetujui dapat mengirim perintah `/all [pesan]` untuk meminta tagall.
    4. **Menyetujui Tagall**: Admin dapat menyetujui permintaan tagall dengan perintah `/oktag`.
    5. **Menghentikan Tagall**: Admin dapat menghentikan permintaan tagall dengan perintah `/stop`.
    6. **Aktifkan Bot**: Pemilik bot dapat mengaktifkan bot dengan perintah `/aktif`.

    Silakan ikuti petunjuk di atas untuk menggunakan bot ini.
    """
    await message.reply(help_text)

# Menjalankan bot
if __name__ == "__main__":
    bot.run()
