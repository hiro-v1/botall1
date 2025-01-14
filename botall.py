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

# Perintah untuk menyetujui atau menolak permintaan admin
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

# Perintah untuk menghapus akses admin
@bot.on_message(filters.command("deladm") & filters.private)
async def delete_admin(client, message: Message):
    if message.from_user.id != CREATOR_ID:
        await message.reply("Hanya pemilik bot yang dapat menghapus admin.")
        return

    if message.reply_to_message:
        user_id = message.reply_to_message.from_user.id
        users_collection.update_one(
            {"user_id": user_id},
            {"$set": {"role": None}},
            upsert=True
        )
        await message.reply(f"Admin @{message.reply_to_message.from_user.username} telah dihapus.")
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
    *Panduan Penggunaan Bot*:
    
    1. **Mendaftar sebagai Partnergc**: Kirim perintah /jadipt untuk mendaftar sebagai partnergc (menunggu persetujuan admin).
    2. **Mengajukan Diri sebagai Admin**: Kirim perintah /jadiadm untuk mengajukan diri menjadi admin bot.
    3. **Menyetujui Admin**: Pemilik bot dapat menyetujui admin dengan perintah /setuju.
    4. **Menyetujui Partnergc**: Admin atau pemilik bot dapat menyetujui partnergc dengan perintah /setuju.
    5. **Meminta Tagall**: Partnergc yang disetujui dapat mengirim perintah /all [pesan] untuk meminta tagall.
    6. **Menyetujui Tagall**: Admin dapat menyetujui permintaan tagall dengan perintah /oktag.
    7. **Menghentikan Tagall**: Admin dapat menghentikan permintaan tagall dengan perintah /stop.
    8. **Menghapus Akses Partnergc**: Pemilik bot dapat menghapus akses partnergc dengan perintah /delpt.
    9. **Menghapus Akses Admin**: Pemilik bot dapat menghapus akses admin dengan perintah /deladm.
    10. **Cek Partnergc**: Pemilik bot dapat melihat daftar partnergc dengan perintah /cekpt.
    11. **Cek Admin**: Pemilik bot dapat melihat daftar admin dengan perintah /cekad.
    
    Silakan ikuti petunjuk di atas untuk menggunakan bot ini.
    """
    await message.reply(help_text)

# Menjalankan bot
if __name__ == "__main__":
    bot.run()
