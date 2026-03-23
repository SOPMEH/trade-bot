import logging
from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler
from database import db
from keyboards import role_selection, get_main_menu
from config import ADMIN_IDS

logger = logging.getLogger(__name__)

# ── Conversation states ────────────────────────────────────────────────────
REGISTER_NAME, REGISTER_ROLE, REGISTER_COMPANY = range(3)

ROLE_LABELS = {
    "buyer":    "Покупатель 🛒",
    "supplier": "Поставщик 🏭",
    "admin":    "Администратор ⚙️",
}


# ── /start ─────────────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    tg = update.effective_user
    user = db.get_user(tg.id)

    if user:
        await update.message.reply_text(
            f"С возвращением, {user['full_name']}! 👋\n"
            f"Роль: {ROLE_LABELS.get(user['role'], user['role'])}",
            reply_markup=get_main_menu(user["role"]),
        )
        return ConversationHandler.END

    await update.message.reply_text(
        "👋 Добро пожаловать в систему договорной торговли!\n\n"
        "Для начала работы нужно зарегистрироваться.\n"
        "Введите ваше полное имя (ФИО):"
    )
    return REGISTER_NAME


async def register_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    name = update.message.text.strip()
    if len(name) < 2:
        await update.message.reply_text("Введите корректное имя (минимум 2 символа):")
        return REGISTER_NAME

    context.user_data["reg_name"] = name
    await update.message.reply_text(
        f"Отлично, {name}! 👍\n\nВыберите вашу роль:",
        reply_markup=role_selection(),
    )
    return REGISTER_ROLE


async def register_role(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    role = query.data.replace("role_", "")
    context.user_data["reg_role"] = role

    await query.edit_message_text(
        f"Роль: {ROLE_LABELS.get(role)} ✅\n\n"
        "Введите название вашей компании (или «-» если нет):"
    )
    return REGISTER_COMPANY


async def register_company(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    company = update.message.text.strip()
    if company == "-":
        company = ""

    tg = update.effective_user
    role = context.user_data.get("reg_role", "buyer")
    if tg.id in ADMIN_IDS:
        role = "admin"

    user = db.create_user(
        telegram_id=tg.id,
        username=tg.username or "",
        full_name=context.user_data.get("reg_name", ""),
        role=role,
        company=company,
    )

    if user:
        company_line = f"\nКомпания: {company}" if company else ""
        await update.message.reply_text(
            f"✅ Регистрация завершена!\n\n"
            f"Имя: {user['full_name']}\n"
            f"Роль: {ROLE_LABELS.get(role)}{company_line}\n\n"
            "Используйте меню ниже для навигации.",
            reply_markup=get_main_menu(role),
        )
    else:
        await update.message.reply_text("Ошибка регистрации. Попробуйте /start")

    return ConversationHandler.END


# ── Profile ────────────────────────────────────────────────────────────────

async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = db.get_user(update.effective_user.id)
    if not user:
        await update.message.reply_text("Вы не зарегистрированы. Напишите /start")
        return

    uname = f"@{user['username']}" if user.get("username") else "—"
    company = f"\n🏢 Компания: {user['company']}" if user.get("company") else ""

    await update.message.reply_text(
        f"👤 *Ваш профиль*\n\n"
        f"Имя: {user['full_name']}\n"
        f"Username: {uname}\n"
        f"Роль: {ROLE_LABELS.get(user['role'], user['role'])}{company}\n"
        f"Дата регистрации: {user['created_at'][:10]}",
        parse_mode="Markdown",
    )
