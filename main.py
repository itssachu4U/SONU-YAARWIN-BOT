import asyncio
import logging
import os
import sqlite3
import time

from telegram import Update
from telegram.error import BadRequest, Forbidden, NetworkError, RetryAfter, TimedOut
from telegram.ext import (
    Application,
    ChatJoinRequestHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)
from telethon import TelegramClient
from telethon.errors import (
    FloodWaitError,
    PhoneCodeExpiredError,
    PhoneCodeInvalidError,
    SessionPasswordNeededError,
)
from telethon.sessions import StringSession

# =============================================================================
#  BOT TOKEN
# =============================================================================
BOT_TOKEN = "8911897518:AAHnsDz5LtOrbluzP8d_cLSwrqo-ZVYHZbQ"

# =============================================================================
#  TELEGRAM API CREDENTIALS
#  Get from: https://my.telegram.org → API Development Tools
#
#  To add more accounts in future, copy a block and add to the list.
#  The FIRST entry is always the active one.
#  To switch: move another to position 1, then /logout + /login
# =============================================================================
TELEGRAM_ACCOUNTS = [
    {
        "api_id":   36250534,
        "api_hash": "342c1a0671b188527b16a1644556dea0",
        "label":    "Main Account",
    },
    # ── Add more accounts below ──────────────────────────────────────────────
    # {
    #     "api_id":   12345678,
    #     "api_hash": "abcdef1234567890abcdef1234567890",
    #     "label":    "Account 2",
    # },
    # {
    #     "api_id":   98765432,
    #     "api_hash": "fedcba9876543210fedcba9876543210",
    #     "label":    "Account 3",
    # },
]

_ACTIVE  = TELEGRAM_ACCOUNTS[0]
API_ID   = _ACTIVE["api_id"]
API_HASH = _ACTIVE["api_hash"]

# =============================================================================
#  ADMIN IDs
# =============================================================================
ADMIN_IDS = [
    8749071857,
    # 1234567890,
]

# =============================================================================
#  CHANNEL CONFIG
# =============================================================================
SUPERVISOR_CHANNEL_ID = -1003035303902

TARGET_CHANNEL_IDS = [
    -1003192266753,
    -1003926870297,
    -1003640308371,
    -1003959429271,
    -1002483412243,
    -1002317625845,
]

# =============================================================================
#  FILE PATHS
# =============================================================================
APK_PATH   = "𝐘𝐀𝐀𝐑𝐖𝐈𝐍 𝐍𝐔𝐌𝐁𝐄𝐑 𝐓𝐎𝐎𝐋.apk"
VOICE_PATH = "VOICEHACK.ogg"
VIDEO_PATH = "BIITU-YAAR.mp4"
DB_NAME    = "users.db"

# =============================================================================

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

LOGIN_PHONE    = 1
LOGIN_OTP      = 2
LOGIN_PASSWORD = 3

# =============================================================================
#  DATABASE
# =============================================================================
conn   = sqlite3.connect(DB_NAME, check_same_thread=False)
cursor = conn.cursor()

cursor.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, joined_at TEXT)")
cursor.execute(
    """
    CREATE TABLE IF NOT EXISTS message_map (
        supervisor_msg_id INTEGER,
        target_chat_id    INTEGER,
        target_msg_id     INTEGER,
        PRIMARY KEY (supervisor_msg_id, target_chat_id)
    )
    """
)
cursor.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
conn.commit()


def add_user(user_id: int):
    try:
        cursor.execute(
            "INSERT OR IGNORE INTO users (user_id, joined_at) VALUES (?, datetime('now'))",
            (user_id,),
        )
        conn.commit()
    except Exception as e:
        logger.error(f"add_user error: {e}")


def get_all_users():
    cursor.execute("SELECT user_id FROM users")
    return [row[0] for row in cursor.fetchall()]


def get_user_count() -> int:
    cursor.execute("SELECT COUNT(*) FROM users")
    return cursor.fetchone()[0]


def user_exists(user_id: int) -> bool:
    cursor.execute("SELECT 1 FROM users WHERE user_id=?", (user_id,))
    return cursor.fetchone() is not None


def save_msg_mapping(sup_msg_id: int, target_chat_id: int, target_msg_id: int):
    try:
        cursor.execute(
            "INSERT OR REPLACE INTO message_map "
            "(supervisor_msg_id, target_chat_id, target_msg_id) VALUES (?, ?, ?)",
            (sup_msg_id, target_chat_id, target_msg_id),
        )
        conn.commit()
    except Exception as e:
        logger.error(f"save_msg_mapping error: {e}")


def get_msg_mappings(sup_msg_id: int):
    cursor.execute(
        "SELECT target_chat_id, target_msg_id FROM message_map WHERE supervisor_msg_id=?",
        (sup_msg_id,),
    )
    return cursor.fetchall()


def get_setting(key: str):
    cursor.execute("SELECT value FROM settings WHERE key=?", (key,))
    row = cursor.fetchone()
    return row[0] if row else None


def set_setting(key: str, value: str):
    cursor.execute(
        "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value)
    )
    conn.commit()


# =============================================================================
#  USERBOT (TELETHON)
# =============================================================================
_userbot_client = None


async def get_userbot():
    global _userbot_client

    if _userbot_client and _userbot_client.is_connected():
        return _userbot_client

    session_str = get_setting("telethon_session")
    if not session_str:
        return None

    try:
        client = TelegramClient(StringSession(session_str), API_ID, API_HASH)
        await client.connect()
        if await client.is_user_authorized():
            _userbot_client = client
            logger.info("✅ Userbot reconnected from saved session.")
            return _userbot_client
        else:
            logger.warning("Saved session is no longer authorised.")
            return None
    except Exception as e:
        logger.error(f"get_userbot error: {e}")
        return None


# =============================================================================
#  WELCOME PACKAGE
# =============================================================================
async def send_welcome_package(user, context: ContextTypes.DEFAULT_TYPE):
    add_user(user.id)

    try:
        await context.bot.send_message(
            chat_id=user.id,
            text=(
                f"👋🏻 𝐖𝐄𝐋𝐂𝐎𝐌𝐄 {user.mention_html()} 𝐁𝐑𝐎𝐓𝐇𝐄𝐑 "
                "𝐓𝐎 𝗢𝗨𝗥 - 𝐘𝐀𝐀𝐑𝐖𝐈𝐍 𝐏𝐑𝐈𝐕𝐀𝐓𝐄 𝐇𝐀𝐂𝐊 𝐒𝐄𝐑𝐕𝐄𝐑 🤑"
            ),
            parse_mode="HTML",
        )
    except Exception:
        return

    if os.path.exists(VIDEO_PATH):
        try:
            with open(VIDEO_PATH, "rb") as f:
                await context.bot.send_video(
                    chat_id=user.id,
                    video=f,
                    caption=(
                        "Panel Activate Guide 𝐘𝐀𝐀𝐑𝐖𝐈𝐍 𝐍𝐔𝐌𝐁𝐄𝐑 𝐓𝐎𝐎𝐋 activate\n"
                        "करने का तरीका इस video मे है. पहले video देखे फिर start करें,"
                    ),
                )
        except Exception as e:
            logger.error(f"Video send error: {e}")

    if os.path.exists(APK_PATH):
        try:
            with open(APK_PATH, "rb") as f:
                await context.bot.send_document(
                    chat_id=user.id,
                    document=f,
                    caption=(
                        "📂 ☆𝟏𝟎𝟎% 𝐍𝐔𝐌𝐁𝐄𝐑 𝐇𝐀𝐂𝐊💸\n\n"
                        "(केवल प्रीमियम उपयोगकर्ताओं के लिए)💎\n"
                        "(𝟏𝟎𝟎% नुकसान की भरपाई की गारंटी)🧬\n\n"
                        "♻सहायता के लिए @HORNETLIVE\n"
                        "🔴हैक का उपयोग कैसे करें\n"
                        "https://t.me/+xm59-mP4i0RiOTk9"
                    ),
                )
        except Exception as e:
            logger.error(f"APK send error: {e}")

    if os.path.exists(VOICE_PATH):
        try:
            with open(VOICE_PATH, "rb") as f:
                await context.bot.send_voice(
                    chat_id=user.id,
                    voice=f,
                    caption=(
                        "🎙 सदस्य 9X गुना लाभ का प्रमाण 👇🏻\n"
                        "https://yaarwin3.com/#/register?invitationCode=73618119062\n\n"
                        "♻सहायता के लिए @HORNETLIVE\n"
                        "लगातार नंबर पे नंबर जीतना 🤑♻👑"
                    ),
                )
        except Exception as e:
            logger.error(f"Voice send error: {e}")


# =============================================================================
#  /start
# =============================================================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_welcome_package(update.effective_user, context)


# =============================================================================
#  JOIN REQUEST
# =============================================================================
async def approve_and_send(update: Update, context: ContextTypes.DEFAULT_TYPE):
    request = update.chat_join_request
    if request:
        await send_welcome_package(request.from_user, context)


# =============================================================================
#  /users
# =============================================================================
async def users_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("❌ Only admins can use this command.")
        return

    total = get_user_count()

    try:
        cursor.execute(
            "SELECT COUNT(*) FROM users WHERE joined_at >= datetime('now', '-7 days')"
        )
        recent = cursor.fetchone()[0]
    except Exception:
        recent = "N/A"

    try:
        cursor.execute(
            "SELECT COUNT(*) FROM users WHERE joined_at >= datetime('now', '-1 day')"
        )
        today = cursor.fetchone()[0]
    except Exception:
        today = "N/A"

    userbot = await get_userbot()
    userbot_status = "🟢 Active" if userbot else "🔴 Not logged in"

    text = (
        "👥 <b>USER DATABASE REPORT</b>\n\n"
        f"📊 <b>Total Users:</b> <code>{total}</code>\n"
        f"📅 <b>Joined Today:</b> <code>{today}</code>\n"
        f"📆 <b>Last 7 Days:</b> <code>{recent}</code>\n\n"
        f"🤖 <b>Userbot Status:</b> {userbot_status}\n"
        f"📡 <b>Target Channels:</b> <code>{len(TARGET_CHANNEL_IDS)}</code>\n"
        f"🔑 <b>Active API Account:</b> {_ACTIVE['label']}\n"
        f"📋 <b>Total API Accounts:</b> <code>{len(TELEGRAM_ACCOUNTS)}</code>"
    )

    await update.message.reply_text(text, parse_mode="HTML")


# =============================================================================
#  /login CONVERSATION
# =============================================================================
async def login_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("❌ Only admins can use this command.")
        return ConversationHandler.END

    userbot = await get_userbot()
    if userbot:
        me = await userbot.get_me()
        await update.message.reply_text(
            f"✅ <b>Userbot already active!</b>\n\n"
            f"👤 Logged in as: <b>{me.first_name}</b> (@{me.username})\n"
            f"📱 ID: <code>{me.id}</code>\n\n"
            f"✨ Premium emoji forwarding is ON 🎉\n\n"
            f"Use /logout to log out.",
            parse_mode="HTML",
        )
        return ConversationHandler.END

    await update.message.reply_text(
        "📱 <b>Userbot Login — Step 1</b>\n\n"
        "अपना मोबाइल नंबर भेजो (country code के साथ):\n\n"
        "<code>+919876543210</code>\n\n"
        "⚡ OTP आपके Telegram app पर आएगा.\n\n"
        "/cancel — रोकने के लिए",
        parse_mode="HTML",
    )
    return LOGIN_PHONE


async def login_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    phone = update.message.text.strip()
    context.user_data["login_phone"] = phone

    await update.message.reply_text("⏳ OTP भेज रहे हैं...")

    try:
        client = TelegramClient(StringSession(), API_ID, API_HASH)
        await client.connect()
        result = await client.send_code_request(phone)
        context.user_data["login_client"]    = client
        context.user_data["login_code_hash"] = result.phone_code_hash

        await update.message.reply_text(
            "📲 <b>OTP भेज दिया!</b>\n\n"
            "✅ अपना Telegram app open करो\n"
            "✅ वहाँ आया हुआ OTP यहाँ भेजो\n\n"
            "Format: <code>12345</code> या <code>1 2 3 4 5</code>\n\n"
            "/cancel — रोकने के लिए",
            parse_mode="HTML",
        )
        return LOGIN_OTP

    except FloodWaitError as e:
        await update.message.reply_text(
            f"⏳ Telegram ने wait करने को कहा.\n"
            f"{e.seconds} seconds बाद /login से try करो."
        )
        return ConversationHandler.END
    except Exception as e:
        logger.error(f"send_code_request error: {e}")
        await update.message.reply_text(
            f"❌ OTP नहीं भेजा जा सका.\nError: {e}\n\n"
            f"Phone number check करो और /login से दोबारा try करो."
        )
        return ConversationHandler.END


async def login_otp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    otp       = update.message.text.strip().replace(" ", "")
    phone     = context.user_data.get("login_phone")
    client    = context.user_data.get("login_client")
    code_hash = context.user_data.get("login_code_hash")

    if not client or not phone or not code_hash:
        await update.message.reply_text("❌ Session expire हो गया. /login से try करो.")
        return ConversationHandler.END

    try:
        await client.sign_in(phone, otp, phone_code_hash=code_hash)

        session_str = client.session.save()
        set_setting("telethon_session", session_str)

        global _userbot_client
        _userbot_client = client

        me = await client.get_me()
        await update.message.reply_text(
            f"✅ <b>Login हो गया!</b>\n\n"
            f"👤 Name: <b>{me.first_name}</b>\n"
            f"📱 Phone: <code>{phone}</code>\n"
            f"🆔 ID: <code>{me.id}</code>\n\n"
            f"🎉 <b>Premium emoji forwarding ACTIVE है!</b>\n"
            f"Supervisor channel → Target channels को posts\n"
            f"अब original premium emojis के साथ भेजे जाएंगे.",
            parse_mode="HTML",
        )
        return ConversationHandler.END

    except PhoneCodeInvalidError:
        await update.message.reply_text(
            "❌ OTP गलत है!\n\nSahi OTP भेजो (Telegram app check करो):"
        )
        return LOGIN_OTP

    except PhoneCodeExpiredError:
        await update.message.reply_text(
            "❌ OTP expire हो गया.\n\n/login से दोबारा try करो."
        )
        return ConversationHandler.END

    except SessionPasswordNeededError:
        await update.message.reply_text(
            "🔒 <b>2-Step Verification चालू है.</b>\n\n"
            "अपना Telegram password भेजो:",
            parse_mode="HTML",
        )
        return LOGIN_PASSWORD

    except Exception as e:
        logger.error(f"sign_in error: {e}")
        await update.message.reply_text(
            f"❌ Login failed.\nError: {e}\n\n/login से दोबारा try करो."
        )
        return ConversationHandler.END


async def login_2fa_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    password = update.message.text.strip()
    client   = context.user_data.get("login_client")

    if not client:
        await update.message.reply_text("❌ Session expire हो गया. /login से try करो.")
        return ConversationHandler.END

    try:
        await client.sign_in(password=password)

        session_str = client.session.save()
        set_setting("telethon_session", session_str)

        global _userbot_client
        _userbot_client = client

        me = await client.get_me()
        await update.message.reply_text(
            f"✅ <b>Login हो गया! (2FA)</b>\n\n"
            f"👤 Name: <b>{me.first_name}</b>\n"
            f"🆔 ID: <code>{me.id}</code>\n\n"
            f"🎉 Premium emoji forwarding ACTIVE है!",
            parse_mode="HTML",
        )
        return ConversationHandler.END

    except Exception as e:
        logger.error(f"2FA error: {e}")
        await update.message.reply_text(
            f"❌ Password गलत है.\nError: {e}\n\n/login से दोबारा try करो."
        )
        return ConversationHandler.END


async def login_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    client = context.user_data.get("login_client")
    if client:
        try:
            await client.disconnect()
        except Exception:
            pass
    await update.message.reply_text("🚫 Login cancel किया गया.")
    return ConversationHandler.END


# =============================================================================
#  /logout
# =============================================================================
async def logout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("❌ Only admins can use this command.")
        return

    global _userbot_client
    if _userbot_client:
        try:
            await _userbot_client.log_out()
        except Exception:
            pass
        _userbot_client = None

    cursor.execute("DELETE FROM settings WHERE key='telethon_session'")
    conn.commit()

    await update.message.reply_text(
        "🔓 <b>Userbot Logout हो गया.</b>\n\n"
        "Session delete कर दिया गया.\n\n"
        "⚠️ अब posts copy mode में जाएंगी (premium emojis नहीं होंगे).\n"
        "Premium emoji forwarding के लिए /login करो.",
        parse_mode="HTML",
    )


# =============================================================================
#  /status
# =============================================================================
async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("❌ Only admins can use this command.")
        return

    userbot     = await get_userbot()
    total_users = get_user_count()

    if userbot:
        try:
            me = await userbot.get_me()
            ubot_text = (
                f"🟢 <b>ACTIVE</b>\n"
                f"   👤 {me.first_name} (@{me.username})\n"
                f"   🆔 <code>{me.id}</code>"
            )
        except Exception:
            ubot_text = "🟡 Session exists (could not fetch user info)"
    else:
        ubot_text = "🔴 <b>NOT ACTIVE</b> — run /login"

    accounts_text = "\n".join(
        f"   {'✅' if i == 0 else '  '} {acc['label']} (ID: {acc['api_id']})"
        for i, acc in enumerate(TELEGRAM_ACCOUNTS)
    )

    text = (
        "📊 <b>BOT STATUS</b>\n\n"
        f"🤖 <b>Userbot:</b>\n{ubot_text}\n\n"
        f"👥 <b>Total Users in DB:</b> <code>{total_users}</code>\n"
        f"📡 <b>Target Channels:</b> <code>{len(TARGET_CHANNEL_IDS)}</code>\n\n"
        f"🔑 <b>API Accounts ({len(TELEGRAM_ACCOUNTS)}):</b>\n{accounts_text}"
    )

    await update.message.reply_text(text, parse_mode="HTML")


# =============================================================================
#  CHANNEL RELAY — sends as NEW post (no "Forwarded from" header)
#  Premium/custom emojis preserved via Telethon userbot ✅
# =============================================================================
async def handle_supervisor_and_channels(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    post = update.channel_post
    if not post:
        return

    chat_id = post.chat.id

    if chat_id == SUPERVISOR_CHANNEL_ID:
        userbot = await get_userbot()

        # Fetch full message via Telethon (carries custom emoji entities)
        original_msg = None
        if userbot:
            try:
                original_msg = await userbot.get_messages(
                    SUPERVISOR_CHANNEL_ID, ids=post.message_id
                )
            except Exception as e:
                logger.error(f"Could not fetch original message via userbot: {e}")

        for target_channel in TARGET_CHANNEL_IDS:
            try:
                if userbot and original_msg:
                    # Send as NEW message — no forward header, emojis intact ✅
                    sent = await userbot.send_message(
                        entity=target_channel,
                        message=original_msg.message or "",
                        formatting_entities=original_msg.entities,
                        file=original_msg.media if original_msg.media else None,
                        link_preview=False,
                    )
                    if sent:
                        save_msg_mapping(post.message_id, target_channel, sent.id)
                else:
                    # Fallback: Bot API copy (no premium emojis)
                    copied = await post.copy(chat_id=target_channel)
                    save_msg_mapping(post.message_id, target_channel, copied.message_id)

                await asyncio.sleep(0.05)
            except Exception as e:
                logger.error(f"Relay error → {target_channel}: {e}")

        # Broadcast to all user DMs
        users = get_all_users()
        for user_id in users:
            try:
                await post.copy(chat_id=user_id)
            except Exception:
                pass
            await asyncio.sleep(0.04)

    elif chat_id in TARGET_CHANNEL_IDS:
        users = get_all_users()
        for user_id in users:
            try:
                await post.copy(chat_id=user_id)
            except Exception:
                pass
            await asyncio.sleep(0.04)


async def handle_edited_channel_post(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    edited_post = update.edited_channel_post
    if not edited_post or edited_post.chat.id != SUPERVISOR_CHANNEL_ID:
        return

    mappings = get_msg_mappings(edited_post.message_id)
    for target_chat_id, target_msg_id in mappings:
        try:
            if edited_post.text:
                await context.bot.edit_message_text(
                    chat_id=target_chat_id,
                    message_id=target_msg_id,
                    text=edited_post.text,
                    parse_mode=edited_post.parse_mode,
                )
            elif edited_post.caption:
                await context.bot.edit_message_caption(
                    chat_id=target_chat_id,
                    message_id=target_msg_id,
                    caption=edited_post.caption,
                    parse_mode=edited_post.parse_mode,
                )
        except Exception as e:
            logger.error(f"Edit sync failed for {target_chat_id}: {e}")


# =============================================================================
#  /broadcast
# =============================================================================
async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return

    if not update.message.reply_to_message:
        await update.message.reply_text(
            "⚠️ किसी message / media को reply करके /broadcast भेजो."
        )
        return

    status_msg = await update.message.reply_text("⏳ Broadcast चल रहा है...")

    users       = get_all_users()
    total_users = len(users)
    delivered   = 0
    failed      = 0
    start_time  = time.time()

    for user_id in users:
        success = False
        while not success:
            try:
                await update.message.reply_to_message.copy(chat_id=user_id)
                delivered += 1
                success = True
            except RetryAfter as e:
                await asyncio.sleep(e.retry_after + 1)
            except (Forbidden, BadRequest) as e:
                failed += 1
                logger.warning(f"Delivery failed for {user_id}: {e}")
                success = True
            except (TimedOut, NetworkError):
                await asyncio.sleep(2)
                try:
                    await update.message.reply_to_message.copy(chat_id=user_id)
                    delivered += 1
                except Exception:
                    failed += 1
                success = True
            except Exception as e:
                failed += 1
                logger.error(f"Broadcast failure for {user_id}: {e}")
                success = True
        await asyncio.sleep(0.04)

    elapsed = round(time.time() - start_time, 2)
    report = (
        "📊 <b><u>BROADCAST ANNOUNCEMENT REPORT</u></b>\n\n"
        f"👥 <b>Total Target Users:</b> {total_users}\n"
        f"✅ <b>Successfully Delivered:</b> {delivered}\n"
        f"❌ <b>Failed / Blocked:</b> {failed}\n"
        f"🛡 <b>Database Deletions:</b> 0 (All users preserved permanently)\n"
        f"⏱ <b>Execution Time:</b> {elapsed} seconds\n\n"
        "🎉 <i>Broadcast completed!</i>"
    )

    try:
        await status_msg.edit_text(report, parse_mode="HTML")
    except Exception:
        await update.message.reply_text(report, parse_mode="HTML")


# =============================================================================
#  USER MESSAGE CAPTURE
# =============================================================================
async def capture_user_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user    = update.effective_user
    message = update.message

    if not user or not message or message.from_user.is_bot:
        return
    if user.id in ADMIN_IDS:
        return

    is_new = not user_exists(user.id)
    if is_new:
        add_user(user.id)

    username_str        = f"@{user.username}" if user.username else "N/A"
    direct_contact_link = f"tg://openmessage?user_id={user.id}"
    status_label = (
        "🚨 <b>NEW USER DETECTED</b> 🚨" if is_new
        else "📩 <b>USER MEDIA/MESSAGE RECEIVED</b>"
    )

    admin_notification_text = (
        f"{status_label}\n\n"
        f"👤 <b>TELEGRAM ID:</b> <code>{user.id}</code>\n"
        f"🏷 <b>TELEGRAM USER NAME:</b> {username_str}\n"
        f"🔗 <b>DIRECT OPENID LINK:</b> "
        f"<a href='{direct_contact_link}'>Click to Chat directly with User</a>"
    )

    for admin_id in ADMIN_IDS:
        try:
            await context.bot.send_message(
                chat_id=admin_id,
                text=admin_notification_text,
                parse_mode="HTML",
                disable_web_page_preview=True,
            )
            await message.copy(chat_id=admin_id)
        except Exception as e:
            logger.error(f"Admin notification failed for {admin_id}: {e}")


# =============================================================================
#  STARTUP
# =============================================================================
async def on_startup(app: Application):
    userbot = await get_userbot()
    if userbot:
        try:
            me = await userbot.get_me()
            logger.info(f"✅ Userbot auto-connected: {me.first_name} (@{me.username})")
        except Exception as e:
            logger.warning(f"Userbot startup reconnect failed: {e}")
    else:
        logger.info("No userbot session found. Admin can run /login.")


# =============================================================================
#  MAIN
# =============================================================================
def main():
    app = Application.builder().token(BOT_TOKEN).post_init(on_startup).build()

    login_conv = ConversationHandler(
        entry_points=[CommandHandler("login", login_start)],
        states={
            LOGIN_PHONE:    [MessageHandler(filters.TEXT & ~filters.COMMAND, login_phone)],
            LOGIN_OTP:      [MessageHandler(filters.TEXT & ~filters.COMMAND, login_otp)],
            LOGIN_PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, login_2fa_password)],
        },
        fallbacks=[CommandHandler("cancel", login_cancel)],
        per_user=True,
        per_chat=True,
    )

    app.add_handler(login_conv)
    app.add_handler(CommandHandler("logout",    logout))
    app.add_handler(CommandHandler("status",    status_cmd))
    app.add_handler(CommandHandler("users",     users_cmd))
    app.add_handler(CommandHandler("broadcast", broadcast))
    app.add_handler(CommandHandler("start",     start))
    app.add_handler(ChatJoinRequestHandler(approve_and_send))

    app.add_handler(
        MessageHandler(
            filters.ChatType.CHANNEL & ~filters.UpdateType.EDITED_CHANNEL_POST,
            handle_supervisor_and_channels,
        )
    )
    app.add_handler(
        MessageHandler(
            filters.ChatType.CHANNEL & filters.UpdateType.EDITED_CHANNEL_POST,
            handle_edited_channel_post,
        )
    )
    app.add_handler(
        MessageHandler(
            filters.ALL & ~filters.COMMAND & filters.ChatType.PRIVATE,
            capture_user_message,
        )
    )

    app.run_polling()


if __name__ == "__main__":
    main()
