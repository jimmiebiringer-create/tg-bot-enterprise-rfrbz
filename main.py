import os
import asyncio
import sqlite3
from datetime import datetime
import pytz
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from groq import Groq

# ----------------- الإعدادات والبيانات الأساسية -----------------
API_ID = int(os.getenv("API_ID", "32492582"))
API_HASH = os.getenv("API_HASH", "d7737a28a39c86f3bb82777d0a1aea6e")
OWNER_ID = int(os.getenv("OWNER_ID", "1443724632"))

# توكن بوت التحكم والإشعارات #
BOT_TOKEN ="8954408117:AAHpwxwMSxLSlQL_7nHVMHMWAHk4mcE6SZM"

# تعريف app:
app = Client(
    "my_support_session",
    api_id=API_ID,
    api_hash=API_HASH,
    session_string=os.getenv("STRING_SESSION")
)

# تعريف notifier كبوت رسمي باستخدام التوكن:
notifier = Client(
    "bot_notification_session",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)


BAGHDAD_TZ = pytz.timezone("Asia/Baghdad")

def get_baghdad_time():
    now = datetime.now(BAGHDAD_TZ)
    return now.strftime("%Y-%m-%d | %I:%M:%S %p")

DB_FILE = "support_bot_supreme_master.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users_state (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            is_whitelisted INTEGER DEFAULT 0,
            is_paused INTEGER DEFAULT 0,
            is_active_ai INTEGER DEFAULT 0
        )
    """)
    # التأكد من وجود عمود username إذا كانت القاعدة قديمة
    try:
        cursor.execute("ALTER TABLE users_state ADD COLUMN username TEXT")
    except Exception:
        pass

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS chat_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            role TEXT,
            message TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS api_keys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            api_key TEXT UNIQUE,
            status TEXT DEFAULT 'active'
        )
    """)
    conn.commit()
    conn.close()

init_db()

def get_next_active_key():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT id, api_key FROM api_keys WHERE status = 'active' LIMIT 1")
    row = cursor.fetchone()
    conn.close()
    if row:
        return row[0], row[1]
    return None, None

def mark_key_as_dead(key_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("UPDATE api_keys SET status = 'dead' WHERE id = ?", (key_id,))
    conn.commit()
    conn.close()

def add_api_keys(keys_text):
    raw_keys = keys_text.split()
    valid_keys = []
    for k in raw_keys:
        clean_k = k.strip()
        if clean_k.startswith("gsk_") and len(clean_k) > 20:
            valid_keys.append(clean_k)

    added_count = 0
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    for k in valid_keys:
        try:
            cursor.execute("INSERT OR IGNORE INTO api_keys (api_key, status) VALUES (?, 'active')", (k,))
            if cursor.rowcount > 0:
                added_count += 1
        except Exception:
            pass
    conn.commit()
    conn.close()
    return added_count

def get_keys_stats():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM api_keys")
    total = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM api_keys WHERE status = 'active'")
    active = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM api_keys WHERE status = 'dead'")
    dead = cursor.fetchone()[0]
    conn.close()
    return total, active, dead

def delete_all_keys():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM api_keys")
    conn.commit()
    conn.close()

def get_panel_keyboard():
    total, active, dead = get_keys_stats()
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"📦 إجمالي المفاتيح: {total}", callback_data="noop")],
        [
            InlineKeyboardButton(f"🟢 الشغالة: {active}", callback_data="noop"),
            InlineKeyboardButton(f"🔴 المتعطلة: {dead}", callback_data="noop")
        ],
        [
            InlineKeyboardButton("➕ إضافة مفتاح", callback_data="keys_add"),
            InlineKeyboardButton("🗑️ حذف الكل", callback_data="keys_del")
        ]
    ])

def db_get_user_state_by_id(user_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT is_whitelisted, is_paused, is_active_ai FROM users_state WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return {"whitelisted": bool(row[0]), "paused": bool(row[1]), "active_ai": bool(row[2])}
    return {"whitelisted": False, "paused": False, "active_ai": False}

def db_get_user_state_by_username(username):
    clean_username = username.lstrip("@").lower()
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, is_whitelisted, is_paused, is_active_ai FROM users_state WHERE LOWER(username) = ?", (clean_username,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return row[0], {"whitelisted": bool(row[1]), "paused": bool(row[2]), "active_ai": bool(row[3])}
    return None, None

def db_set_state(user_id, username=None, whitelisted=None, paused=None, active_ai=None):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT username, is_whitelisted, is_paused, is_active_ai FROM users_state WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    
    curr_username = username if username else (row[0] if row and row[0] else "")
    w = whitelisted if whitelisted is not None else (row[1] if row else 0)
    p = paused if paused is not None else (row[2] if row else 0)
    a = active_ai if active_ai is not None else (row[3] if row else 0)
    
    cursor.execute("""
        INSERT OR REPLACE INTO users_state (user_id, username, is_whitelisted, is_paused, is_active_ai) 
        VALUES (?, ?, ?, ?, ?)
    """, (user_id, curr_username, int(w), int(p), int(a)))
    conn.commit()
    conn.close()

def db_add_message(user_id, role, text):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO chat_history (user_id, role, message) VALUES (?, ?, ?)", (user_id, role, text))
    conn.commit()
    conn.close()

def db_get_history(user_id, limit=6):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT role, message FROM chat_history WHERE user_id = ? ORDER BY id DESC LIMIT ?", (user_id, limit))
    rows = cursor.fetchall()
    conn.close()
    rows.reverse()
    messages = []
    for role, msg in rows:
        r = "user" if role == "user" else "assistant"
        messages.append({"role": r, "content": msg})
    return messages

def db_clear_history(user_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM chat_history WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

SYSTEM_INSTRUCTION = (
    "أنتِ ليلى، ممثلة الدعم الفني الذكية لحساب الشخص (حربي). "
    "قواعد صارمة جداً:\n"
    "1. لا تقومي أبداً بتحويل المحادثة لمجرد ذكر اسم 'حربي' في كلام المستخدم العادي (مثل: من هو حربي؟ أو أين حربي يعمل؟).\n"
    "2. يجب أن يتم تحويل المحادثة حصراً وفقط إذا طلب المستخدم صراحة وبشكل قاطع التحدث مع حربي أو شخص بشري (مثل: 'حولني لحربي'، 'أريد التحدث مع حربي'، 'كلمني بشري').\n"
    "3. إذا طلب المستخدم التحويل صراحة بالشروط السابقة، ابدئي ردك حصراً بـ: [ACTION_TRANSFER].\n"
    "4. كوني طبيعية، ذكية، ولبقة، واجيبي على أسئلته بشكل طبيعي طالما لم يطلب التحويل صراحة."
)

async def ask_groq_master(user_id, user_message, message_obj):
    db_add_message(user_id, "user", user_message)
    history = db_get_history(user_id, limit=6)

    messages = [{"role": "system", "content": SYSTEM_INSTRUCTION}]
    messages.extend(history)

    max_retries = 3
    for _ in range(max_retries):
        key_id, api_key_str = get_next_active_key()
        if not api_key_str:
            return None

        try:
            temp_client = Groq(api_key=api_key_str)
            response = await asyncio.to_thread(
                temp_client.chat.completions.create,
                model="llama-3.3-70b-versatile",
                messages=messages,
                max_tokens=300,
                temperature=0.7
            )
            reply = response.choices[0].message.content.strip()
            break
        except Exception as e:
            err_str = str(e)
            if "401" in err_str or "invalid_api_key" in err_str or "rate_limit" in err_str.lower():
                mark_key_as_dead(key_id)
                try:
                    masked_key = api_key_str[:10] + "..." + api_key_str[-4:]
                    await notifier.send_message(
                        OWNER_ID, 
                        f"⚠️ **تنبيه: تعطل مفتاح Groq!**\n\n🔑 **المفتاح:** `{masked_key}`\n🆔 **رقم الـ ID في القاعدة:** `{key_id}`"
                    )
                except Exception:
                    pass
                continue
            else:
                return "أهلاً بك، تفضل بطرح رسالتك وسأجيبك فوراً! 🌸"
    else:
        return None

    user_info = message_obj.from_user
    name = user_info.first_name or "بدون اسم"
    username = f"@{user_info.username}" if user_info.username else "لا يوجد"
    req_time = get_baghdad_time()

    if reply and "[ACTION_TRANSFER]" in reply:
        db_set_state(user_id, username=user_info.username, paused=True, active_ai=False)
        try:
            notif_text = f"🚨 **طلب تحويل جديد للبشري!**\n\n👤 **الاسم:** {name}\n🔗 **اليوزر:** {username}\n🆔 **الايدي:** `{user_id}`\n⏰ **الوقت:** {req_time}"
            await notifier.send_message(OWNER_ID, notif_text)
        except Exception as err:
            print(f"Notification Error: {err}")
        return "تم تحويل طلبك إلى حربي، سيتم الرد عليك قريباً ✅"

    if reply:
        db_add_message(user_id, "assistant", reply)
    return reply

@app.on_message(filters.private & ~filters.me & ~filters.bot & (filters.text | filters.photo | filters.voice | filters.audio))
async def incoming_handler(client, message):
        if not message.from_user:
            return
        user_id = message.from_user.id
        username = message.from_user.usernam
        state = db_get_user_state_by_id(user_id)

        if username:
             db_set_state(user_id, username=username)

        if state["whitelisted"] or state["paused"]:
            return

        _, active_count, _ = get_keys_stats()
        if active_count == 0:
            db_set_state(user_id, username=username, paused=True, active_ai=False)
            try:
                user_info = message.from_user
                name = user_info.first_name or "بدون اسم"
                usr = f"@{user_info.username}" if user_info.username else "لا يوجد"
                notif_text = f"🚨 **رسالة ومفاتيح فارغة (الدعم مغلق)!**\n\n👤 **الاسم:** {name}\n🔗 **اليوزر:** {usr}\n🆔 **الايدي:** `{user_id}`\n⏰ **الوقت:** {get_baghdad_time()}"
                await notifier.send_message(OWNER_ID, notif_text)
            except Exception:
                pass
            await message.reply("الدعم الفني حالياً مغلق سيتم تحويلك الى حربي في وقتاً لاحق")
            return

        if not state["active_ai"] and not state["paused"]:
            db_set_state(user_id, username=username, active_ai=True)
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("نكمل المحادثة مع بعض 🤝", callback_data=f"ai_cont_{user_id}")],
                [InlineKeyboardButton("قم بتحويلي إلى حربي (مالك الحساب) 👤", callback_data=f"ai_trans_{user_id}")]
        ])
            await message.reply(
            "مرحباً! أنا ليلى، ممثلة الدعم الفني لحساب الشخص (حربي). "
            "أنا هنا لمساعدتك والإجابة على استفساراتك. "
            "هل ترغب في أن نكمل المحادثة معاً، أم تفضل تحويل طلبك لـ (حربي) ليدخل إلى الدردشة بنفسه؟",
                reply_markup=keyboard
        )
            return

        if state["active_ai"]:
            user_text = message.text or message.caption or "مرحباً"
            if message.voice or message.audio:
                user_text = "[رسالة صوتية من المستخدم]"
            elif message.photo:
                user_text = "[أرسل صورة]"

            ai_reply = await ask_groq_master(user_id, user_text, message)
            if ai_reply is None:
                db_set_state(user_id, username=username, paused=True, active_ai=False)
                await message.reply("الدعم الفني حالياً مغلق سيتم تحويلك الى حربي في وقتاً لاحق")
                return
                await message.reply(ai_reply)

@app.on_callback_query()
async def callback_handler(client, callback_query: CallbackQuery):
    data = callback_query.data
    
    if data.startswith("ai_cont_"):
        target_user = int(data.split("_")[2])
        db_set_state(target_user, active_ai=True, paused=False)
        await callback_query.answer("تفضل، أنا أستمع إليك.", show_alert=False)
        await callback_query.message.edit_text("تم اختيار متابعة المحادثة مع ليلى 🤖\nتفضل بكتابة استفسارك وسأجيبك بكل تفصيل.")
    elif data.startswith("ai_trans_"):
        target_user = int(data.split("_")[2])
        db_set_state(target_user, paused=True, active_ai=False)
        await callback_query.answer("تم إرسال الطلب لحربي ✅", show_alert=True)
        await callback_query.message.edit_text("تم إرسال طلب إلى حربي للدخول إلى هذه الدردشة ✅")
        try:
            user_info = callback_query.from_user
            notif_text = f"🚨 **طلب تحويل عبر الزر الشفاف!**\n\n👤 **الاسم:** {user_info.first_name}\n🆔 **الايدي:** `{target_user}`\n⏰ **الوقت:** {get_baghdad_time()}"
            await notifier.send_message(OWNER_ID, notif_text)
        except Exception as err:
            print(f"Notification Error: {err}")

# --- نظام التحكم وإدارة الأوامر عبر بوت المالك (Notifier Bot) ---
user_adding_keys = set()

@notifier.on_message(filters.private & filters.user(OWNER_ID) & filters.text)
async def notifier_text_handler(client, message):
    global user_adding_keys
    user_id = message.chat.id
    text = message.text.strip()

    if user_id in user_adding_keys:
        if text.startswith("/"):
            user_adding_keys.remove(user_id)
        else:
            added = add_api_keys(text)
            user_adding_keys.remove(user_id)
            if added > 0:
                await message.reply(f"✅ **تمت إضافة المفاتيح بنجاح!**\n- عدد المفاتيح الحقيقية المضافة: `{added}`")
            else:
                await message.reply(f"❌ **لم يتم إضافة أي مفتاح!**\nالرجاء إرسال مفتاح Groq صالح يبدأ بـ `gsk_` وطوله صحيح.")
            
            await message.reply("⚙️ **لوحة تحكم مفاتيح الذكاء الاصطناعي (Groq):**", reply_markup=get_panel_keyboard())
            return

    if text == "/panel" or text == "لوحة التحكم" or text == "/start":
        help_text = (
            "⚙️ **لوحة تحكم بوت الدعم الذكي - الأوامر المتاحة:**\n\n"
            "1️⃣ `/panel` أو `لوحة التحكم`:\n"
            "   - تعرض لوحة تحكم مفاتيح الذكاء الاصطناعي (Groq) مع الأزرار الحية وإحصائياتها.\n\n"
            "2️⃣ `/yes [الايدي أو المعرف]`:\n"
            "   - لإضافة شخص للقائمة البيضاء، ليتمكن من مراسلتك والتواصل معك مباشرة في كل الأوقات دون أن يظهر له الذكاء الاصطناعي إطلاقاً.\n"
            "   - *مثال:* `/yes 6000552936` أو `/yes @iiinnc`\n\n"
            "3️⃣ `/no [الايدي أو المعرف]`:\n"
            "   - لإزالة الشخص من القائمة البيضاء، ليعود الذكاء الاصطناعي للرد عليه بشكل اعتيادي.\n"
            "   - *مثال:* `/no 6000552936` أو `/no @iiinnc`\n\n"
            "4️⃣ `/lest`:\n"
            "   - تعرض قائمة بجميع الأشخاص المفعلة لديهم ميزة التواصل المباشر معك."
        )
        await message.reply(help_text, reply_markup=get_panel_keyboard())
        return

    if text.startswith("/yes"):
        parts = text.split(maxsplit=1)
        if len(parts) < 2:
            await message.reply("❌ يرجى كتابة الايدي أو المعرف بعد الأمر.\n*مثال:* `/yes 6000552936` أو `/yes @iiinnc`")
            return
        
        target = parts[1].strip()
        uid = None
        if target.isdigit():
            uid = int(target)
        else:
            uid, _ = db_get_user_state_by_username(target)

        if uid:
            db_set_state(uid, whitelisted=1)
            await message.reply(f"✅ تم تفعيل التواصل المباشر بنجاح للمستخدم (`{uid}`). لن يظهر له الذكاء الاصطناعي بعد الآن.")
        else:
            if target.isdigit():
                uid = int(target)
                db_set_state(uid, whitelisted=1)
                await message.reply(f"✅ تم تفعيل التواصل المباشر بنجاح للمستخدم (`{uid}`).")
            else:
                await message.reply("❌ لم يتم العثور على هذا المستخدم في قاعدة البيانات. تأكد من الايدي أو المعرف.")
        return

    if text.startswith("/no"):
        parts = text.split(maxsplit=1)
        if len(parts) < 2:
            await message.reply("❌ يرجى كتابة الايدي أو المعرف بعد الأمر.\n*مثال:* `/no 6000552936` أو `/no @iiinnc`")
            return
        
        target = parts[1].strip()
        uid = None
        if target.isdigit():
            uid = int(target)
        else:
            uid, _ = db_get_user_state_by_username(target)

        if uid:
            db_set_state(uid, whitelisted=0)
            await message.reply(f"✅ تم إلغاء ميزة التواصل المباشر عن المستخدم (`{uid}`). سيعود الذكاء الاصطناعي للرد عليه.")
        else:
            await message.reply("❌ لم يتم العثور على هذا المستخدم في القاعدة.")
        return

    if text == "/lest":
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, username FROM users_state WHERE is_whitelisted = 1")
        rows = cursor.fetchall()
        conn.close()

        if not rows:
            await message.reply("📭 لا يوجد أي شخص في القائمة البيضاء حالياً (لا يوجد مستخدمون بتواصل مباشر).")
            return

        resp_msg = "📋 **قائمة الأشخاص في التواصل المباشر (القائمة البيضاء):**\n\n"
        for idx, (uid, uname) in enumerate(rows, 1):
            usr_str = f"@{uname}" if uname else "لا يوجد"
            resp_msg += f"{idx}. الايدي: `{uid}` | اليوزر: {usr_str}\n"
        
        await message.reply(resp_msg)
        return

@notifier.on_callback_query()
async def notifier_callback(client, callback_query: CallbackQuery):
    global user_adding_keys
    data = callback_query.data
    user_id = callback_query.from_user.id

    if user_id != OWNER_ID:
        await callback_query.answer("هذه اللوحة خاصة بمالك البوت فقط!", show_alert=True)
        return

    if data == "noop":
        await callback_query.answer()
    elif data == "keys_add":
        user_adding_keys.add(user_id)
        await callback_query.answer()
        await callback_query.message.reply("➕ **أرسل الآن مفتاح أو مجموعة مفاتيح (Groq API Keys)** في رسالة واحدة، وسيتم التحقق منها وحقنها فوراً:")
    elif data == "keys_del":
        delete_all_keys()
        await callback_query.answer("تم حذف جميع المفاتيح بنجاح!", show_alert=True)
        await callback_query.message.edit_text("⚙️ **لوحة تحكم مفاتيح الذكاء الاصطناعي (Groq):**\nاختر الإجراء المطلوب:", reply_markup=get_panel_keyboard())

# أوامر حسابك الشخصي الصامتة فقط
@app.on_message(filters.private & filters.me)
async def owner_commands(client, message):
    if not message.text:
        return
    text = message.text.strip()
    user_id = message.chat.id

    if text == "/1":
        db_set_state(user_id, paused=True, active_ai=False)
        db_clear_history(user_id)
        try:
            await message.delete()
        except Exception:
            pass
        return

    elif text == "/back":
        db_set_state(user_id, paused=False, active_ai=True)
        db_clear_history(user_id)
        try:
            await message.delete()
        except Exception:
            pass
        return

if __name__ == "__main__":
    print("Starting Bot & Notifier with Full Commands System...")
    app.start()
    notifier.start()
    print("Bot is running successfully!")
    from pyrogram import idle
    idle()
    app.stop()
    notifier.stop()
