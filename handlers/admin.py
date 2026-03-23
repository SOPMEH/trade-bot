import logging
from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler
from database import db
from keyboards import (
    admin_products_kb, admin_product_actions_kb,
    admin_users_kb, admin_change_role_kb,
    orders_list_kb, back_btn,
)
from handlers.buyer import format_order

logger = logging.getLogger(__name__)

# States for add-product conversation
(ADD_NAME, ADD_DESC, ADD_UNIT, ADD_MIN_QTY, ADD_PRICE) = range(5)

ROLE_LABELS = {"buyer": "Покупатель 🛒", "supplier": "Поставщик 🏭", "admin": "Администратор ⚙️"}


def _check_admin(user) -> bool:
    return user and user["role"] == "admin"


# ── Products management ────────────────────────────────────────────────────

async def admin_products(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = db.get_user(update.effective_user.id)
    if not _check_admin(user):
        await update.message.reply_text("Нет доступа.")
        return
    products = db.get_products(available_only=False)
    await update.message.reply_text(
        f"📦 *Управление товарами* ({len(products)} шт.):",
        parse_mode="Markdown",
        reply_markup=admin_products_kb(products),
    )


async def admin_view_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    pid = int(query.data.replace("adm_prod_", ""))
    p = db.get_product(pid)
    if not p:
        await query.edit_message_text("Товар не найден.")
        return
    price = f"{p['base_price']} руб/{p['unit']}" if p.get("base_price") else "Договорная"
    status = "✅ Доступен" if p["is_available"] else "❌ Скрыт"
    await query.edit_message_text(
        f"📦 *{p['name']}*\n\n"
        f"Описание: {p.get('description') or '—'}\n"
        f"Единица: {p['unit']}\n"
        f"Мин. кол-во: {p['min_quantity']}\n"
        f"Цена: {price}\n"
        f"Статус: {status}",
        parse_mode="Markdown",
        reply_markup=admin_product_actions_kb(pid, p["is_available"]),
    )


async def toggle_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    pid = int(query.data.replace("adm_toggle_", ""))
    db.toggle_product_availability(pid)
    p = db.get_product(pid)
    if not p:
        await query.edit_message_text("Товар не найден.")
        return
    price = f"{p['base_price']} руб/{p['unit']}" if p.get("base_price") else "Договорная"
    status = "✅ Доступен" if p["is_available"] else "❌ Скрыт"
    await query.edit_message_text(
        f"📦 *{p['name']}*\n\nЦена: {price}\nСтатус: {status}",
        parse_mode="Markdown",
        reply_markup=admin_product_actions_kb(pid, p["is_available"]),
    )


async def back_adm_products(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    products = db.get_products(available_only=False)
    await query.edit_message_text(
        f"📦 *Управление товарами* ({len(products)} шт.):",
        parse_mode="Markdown",
        reply_markup=admin_products_kb(products),
    )


# ── Add product conversation ───────────────────────────────────────────────

async def start_add_product(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data["np"] = {}
    await query.edit_message_text(
        "➕ *Добавление товара — шаг 1/5*\n\nВведите название товара:",
        parse_mode="Markdown",
    )
    return ADD_NAME


async def add_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    name = update.message.text.strip()
    if len(name) < 2:
        await update.message.reply_text("Название слишком короткое:")
        return ADD_NAME
    context.user_data["np"]["name"] = name
    await update.message.reply_text(
        f"*{name}* ✅\n\nШаг 2/5: Введите описание (или «-»):",
        parse_mode="Markdown",
    )
    return ADD_DESC


async def add_desc(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    desc = update.message.text.strip()
    context.user_data["np"]["desc"] = "" if desc == "-" else desc
    await update.message.reply_text("Шаг 3/5: Единица измерения (шт, кг, л, м, т …):")
    return ADD_UNIT


async def add_unit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["np"]["unit"] = update.message.text.strip()
    await update.message.reply_text("Шаг 4/5: Минимальное количество для заказа:")
    return ADD_MIN_QTY


async def add_min_qty(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip().replace(",", ".")
    try:
        qty = float(text)
        if qty <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("Введите корректное число:")
        return ADD_MIN_QTY
    context.user_data["np"]["min_qty"] = qty
    await update.message.reply_text("Шаг 5/5: Базовая цена за единицу (или «-» для договорной):")
    return ADD_PRICE


async def add_price(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip().replace(",", ".")
    price = None
    if text != "-":
        try:
            price = float(text)
            if price < 0:
                raise ValueError
        except ValueError:
            await update.message.reply_text("Введите корректную цену или «-»:")
            return ADD_PRICE

    np = context.user_data.pop("np", {})
    product = db.create_product(
        name=np.get("name", ""),
        description=np.get("desc", ""),
        unit=np.get("unit", "шт"),
        min_quantity=np.get("min_qty", 1),
        base_price=price,
    )
    if product:
        price_str = f"{price} руб/{np['unit']}" if price else "Договорная"
        await update.message.reply_text(
            f"✅ *Товар добавлен!*\n\n"
            f"Название: {product['name']}\n"
            f"Единица: {product['unit']}\n"
            f"Цена: {price_str}",
            parse_mode="Markdown",
        )
    else:
        await update.message.reply_text("Ошибка при добавлении товара.")
    return ConversationHandler.END


async def cancel_add_product(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.pop("np", None)
    await update.message.reply_text("Добавление товара отменено.")
    return ConversationHandler.END


# ── Users management ───────────────────────────────────────────────────────

async def admin_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = db.get_user(update.effective_user.id)
    if not _check_admin(user):
        await update.message.reply_text("Нет доступа.")
        return
    users = db.get_all_users()
    await update.message.reply_text(
        f"👥 *Пользователи* ({len(users)} чел.):",
        parse_mode="Markdown",
        reply_markup=admin_users_kb(users),
    )


async def admin_view_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = int(query.data.replace("adm_user_", ""))
    u = db.get_user(uid)
    if not u:
        await query.edit_message_text("Пользователь не найден.")
        return
    uname = f"@{u['username']}" if u.get("username") else "—"
    await query.edit_message_text(
        f"👤 *{u['full_name']}*\n\n"
        f"Username: {uname}\n"
        f"Роль: {ROLE_LABELS.get(u['role'], u['role'])}\n"
        f"Компания: {u.get('company') or '—'}\n"
        f"С нами с: {u['created_at'][:10]}\n\n"
        "Изменить роль:",
        parse_mode="Markdown",
        reply_markup=admin_change_role_kb(uid),
    )


async def set_user_role(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    # callback_data = adm_setrole_{user_id}_{role}
    parts = query.data.replace("adm_setrole_", "").rsplit("_", 1)
    uid, new_role = int(parts[0]), parts[1]
    db.update_user(uid, role=new_role)
    u = db.get_user(uid)
    name = u["full_name"] if u else str(uid)
    await query.edit_message_text(
        f"✅ Роль пользователя *{name}* изменена на {ROLE_LABELS.get(new_role, new_role)}",
        parse_mode="Markdown",
    )


async def back_adm_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    users = db.get_all_users()
    await query.edit_message_text(
        f"👥 *Пользователи* ({len(users)} чел.):",
        parse_mode="Markdown",
        reply_markup=admin_users_kb(users),
    )


# ── All orders ─────────────────────────────────────────────────────────────

async def all_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = db.get_user(update.effective_user.id)
    if not _check_admin(user):
        await update.message.reply_text("Нет доступа.")
        return
    orders = db.get_all_orders()
    if not orders:
        await update.message.reply_text("Заявок пока нет.")
        return
    await update.message.reply_text(
        f"📋 *Все заявки* ({len(orders)} шт.):",
        parse_mode="Markdown",
        reply_markup=orders_list_kb(orders, "adm_ord_"),
    )


async def admin_view_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    oid = int(query.data.replace("adm_ord_", ""))
    order = db.get_order(oid)
    items = db.get_order_items(oid)
    if not order:
        await query.edit_message_text("Заявка не найдена.")
        return
    text = format_order(order, items)
    buyer = db.get_user(order["buyer_id"])
    if buyer:
        text += f"\n\n👤 Покупатель: {buyer['full_name']}"
        if buyer.get("company"):
            text += f" ({buyer['company']})"
    if order.get("supplier_id"):
        sup = db.get_user(order["supplier_id"])
        if sup:
            text += f"\n🏭 Поставщик: {sup['full_name']}"
    await query.edit_message_text(
        text, parse_mode="Markdown", reply_markup=back_btn("back_adm_orders")
    )


async def back_adm_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    orders = db.get_all_orders()
    await query.edit_message_text(
        f"📋 *Все заявки* ({len(orders)} шт.):",
        parse_mode="Markdown",
        reply_markup=orders_list_kb(orders, "adm_ord_"),
    )
