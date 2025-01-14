import asyncio
import random
from pyrogram import Client, filters
from pymongo import MongoClient
from pyrogram.types import Message
from config import API_ID, API_HASH, BOT_TOKEN, CREATOR_ID, MONGO_URI
from dotenv import load_dotenv
import time

load_dotenv()

# Koneksi ke MongoDB
client_mongo = MongoClient(MONGO_URI)
db = client_mongo["tagall_bot_db"]
users_collection = db["users"]
requests_collection = db["requests"]

# Inisialisasi bot dengan Pyrogram
bot = Client("botall", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# Fungsi untuk mendapatkan daftar admin yang disetujui
def get_approved_admins():
    admins = users_collection.find({"role": "admin", "approved": True})
    return [admin["user_id"] for admin in admins]

# Fungsi untuk mendapatkan daftar partnergc
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

# Perintah untuk mengajukan diri menjadi admin
@bot.on_message(filters.command("jadiadm") & filters.private)
async def request_admin(client, message: Message):
    if message.from_user.id == CREATOR_ID:
        await message.reply("Anda sudah menjadi pemilik bot.")
        return
    
    existing_admin = users_collection.find_one({"user_id": message.from_user.id, "role": "admin"})
    if existing_admin:
        await message.reply("Anda sudah menjadi admin bot.")
        return
    
    users_collection.update_one(
        {"user_id": message.from_user.id},
        {"$set": {"role": "admin", "approved": False}},  # Menunggu persetujuan pemilik
        upsert=True
    )
    await bot.send_message(CREATOR_ID, f"Pengguna @{message.from_user.username} mengajukan diri sebagai admin bot. Ketik /setuju atau /batal untuk menyetujui atau menolak permintaan ini.")

# Perintah untuk menyetujui admin
@bot.on_message(filters.command("setuju") & filters.private)
async def approve_admin(client, message: Message):
    if message.from_user.id != CREATOR_ID:
        await message.reply("Hanya pemilik bot yang dapat menyetujui permintaan admin.")
        return

    user_id = message.reply_to_message.from_user.id
    users_collection.update_one(
        {"user_id": user_id},
        {"$set": {"approved": True}},
        upsert=True
    )
    await message.reply(f"User @{message.reply_to_message.from_user.username} telah disetujui sebagai admin.")

# Perintah untuk menolak permintaan admin
@bot.on_message(filters.command("batal") & filters.private)
async def reject_admin(client, message: Message):
    if message.from_user.id != CREATOR_ID:
        await message.reply("Hanya pemilik bot yang dapat menolak permintaan admin.")
        return

    user_id = message.reply_to_message.from_user.id
    users_collection.update_one(
        {"user_id": user_id},
        {"$set": {"approved": False}},
        upsert=True
    )
    await message.reply(f"User @{message.reply_to_message.from_user.username} telah dibatalkan permintaannya untuk menjadi admin.")

# Perintah untuk request tagall oleh partnergc
@bot.on_message(filters.command("tagin") & filters.private)
async def tagall_request(client, message: Message):
    if message.from_user.id not in get_partnergcs():
        await message.reply("Hanya partnergc yang disetujui yang bisa meminta tagall.")
        return

    text = message.text.split(None, 1)[1] if len(message.text.split()) > 1 else ""
    group_id = message.chat.id

    # Kirimkan permintaan tagall kepada admin dan pemilik bot
    for admin_id in get_approved_admins() + [CREATOR_ID]:
        await bot.send_message(
            admin_id,
            f"Ada permintaan tagall dari @{message.from_user.username}: {text}\n\nKetik /oktag untuk menyetujui atau /notag untuk menolak."
        )

    save_tagall_request(message.from_user.id, group_id, text)

# Perintah untuk menyetujui tagall
@bot.on_message(filters.command("oktag") & filters.private)
async def approve_tagall(client, message: Message):
    if message.from_user.id not in get_approved_admins() and message.from_user.id != CREATOR_ID:
        await message.reply("Hanya admin yang dapat menyetujui tagall.")
        return
    
    if message.reply_to_message:
        request = requests_collection.find_one({"user_id": message.reply_to_message.from_user.id, "status": "pending"})
        if request:
            update_tagall_request_status(request["_id"], "approved")
            await message.reply(f"Permintaan tagall dari @{message.reply_to_message.from_user.username} telah disetujui.")
            active_members = await track_active_members(message.reply_to_message)
            await perform_tagall(request["chat_id"], request["message_text"], active_members)
            # Mengirim laporan selesai ke partnergc dan admin
            for admin_id in get_approved_admins() + [CREATOR_ID]:
                await bot.send_message(admin_id, f"Permintaan tagall @{message.reply_to_message.from_user.username} telah selesai.")
            await bot.send_message(request["user_id"], "Permintaan tagall telah selesai.")
        else:
            await message.reply("Permintaan tagall ini tidak ditemukan atau sudah diproses.")
    else:
        await message.reply("Balas ke permintaan tagall untuk menyetujui.")

# Perintah untuk menolak tagall
@bot.on_message(filters.command("notag") & filters.private)
async def reject_tagall(client, message: Message):
    if message.from_user.id not in get_approved_admins() and message.from_user.id != CREATOR_ID:
        await message.reply("Hanya admin yang dapat menolak tagall.")
        return

    if message.reply_to_message:
        request = requests_collection.find_one({"user_id": message.reply_to_message.from_user.id, "status": "pending"})
        if request:
            update_tagall_request_status(request["_id"], "rejected")
            await message.reply(f"Permintaan tagall dari @{message.reply_to_message.from_user.username} telah ditolak.")
            await bot.send_message(request["user_id"], "Maaf, permintaan tagall Anda ditolak. Coba lagi nanti.")
        else:
            await message.reply("Permintaan tagall ini tidak ditemukan atau sudah diproses.")
    else:
        await message.reply("Balas ke permintaan tagall untuk menolak.")

# Perintah untuk menghentikan tagall
@bot.on_message(filters.command("stop") & filters.private)
async def stop_tagall(client, message: Message):
    await message.reply("Tagall dihentikan.")

# Perintah untuk menghapus akses partnergc
@bot.on_message(filters.command("delpt") & filters.private)
async def delete_partnergc(client, message: Message):
    if message.from_user.id != CREATOR_ID:
        await message.reply("Hanya pemilik bot yang dapat menghapus partnergc.")
        return

    if message.reply_to_message:
        user_id = message.reply_to_message.from_user.id
        users_collection.update_one(
            {"user_id": user_id},
            {"$set": {"role": None}},
            upsert=True
        )
        await message.reply(f"Partnergc @{message.reply_to_message.from_user.username} telah dihapus.")
    else:
        await message.reply("Balas ke pesan pengguna yang ingin dihapus.")

# Perintah untuk cek daftar partnergc
@bot.on_message(filters.command("cekpt") & filters.private)
async def cek_partnergc(client, message: Message):
    if message.from_user.id != CREATOR_ID:
        await message.reply("Hanya pemilik bot yang dapat melihat daftar partnergc.")
        return

    partnergcs = get_partnergcs()
    if partnergcs:
        users = [f"@{user}" for user in partnergcs]
        await message.reply(f"Partnergc yang terdaftar:\n" + "\n".join(users))
    else:
        await message.reply("Tidak ada partnergc yang terdaftar.")

# Perintah untuk cek daftar admin
@bot.on_message(filters.command("cekad") & filters.private)
async def cek_admin(client, message: Message):
    if message.from_user.id != CREATOR_ID:
        await message.reply("Hanya pemilik bot yang dapat melihat daftar admin.")
        return

    admins = get_approved_admins()
    if admins:
        users = [f"@{user}" for user in admins]
        await message.reply(f"Admin yang disetujui:\n" + "\n".join(users))
    else:
        await message.reply("Tidak ada admin yang disetujui.")

# Perintah bantuan (help)
@bot.on_message(filters.command("help"))
async def help(client, message: Message):
    help_text = """
    *Panduan Penggunaan Bot:*

    1. /start - Menampilkan sambutan dari bot.
    2. /help - Menampilkan panduan penggunaan bot.
    3. /jadipt - Untuk menjadi partnergc.
    4. /jadiadm - Untuk mengajukan diri menjadi admin bot.
    5. /tagin [text] - Untuk meminta proses tagall.
    6. /setuju - Untuk menyetujui permintaan admin.
    7. /batal - Untuk menolak permintaan admin.
    8. /stop - Untuk menghentikan proses tagall.
    9. /delpt - Untuk menghapus partnergc yang terdaftar.
    10. /cekpt - Melihat daftar partnergc.
    11. /cekad - Melihat daftar admin bot.

    *Catatan:*
    - Hanya pemilik dan admin bot yang dapat menyetujui dan menolak permintaan tagall.
    - Proses tagall dapat dihentikan kapan saja oleh admin atau pemilik bot.
    """

    await message.reply(help_text)

# Jalankan bot
bot.run()
