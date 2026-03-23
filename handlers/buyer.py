import logging
import re
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes, ConversationHandler
from database import db
from keyboards import (
    products_keyboard, back_to_catalog_btn,
    products_for_order, confirm_order_kb,
    orders_list_kb, back_btn,
    main_menu_buyer,
)

logger = logging.getLogger(__name__)

# ── Conversation states ────────────────────────────────────────────────────
(ORDER_SELECT_PRODUCTS,
 ORDER_QUANTITIES,
 ORDER_ADDRESS,
 ORDER_DATE,
 ORDER_COMMENT,
 ORDER_CONFIRM) = range(6)


# ── Helpers ────────────────────────────────────────────────────────────────

def format_order(order: dict, items: list) -> str:
    status_map = {
        "new":       "🆕 Новая",
        "reviewing": "👀 На рассмотрении",
        "accepted":  "✅ Принята",
        "rejected":  "❌ Отклонена",
        "completed": "✔️ Выполнена",
    }
    items_text = "\n".join(
        f"  • {i['product_name']}: {i['quantity']} {i['unit']}" for i in items
    ) or "  —"

    text = (
        f"📋 *Заявка #{order['id']}*\n\n"
        f"Статус: {status_map.get(order['status'], order['status'])}\n"
        f"Дата: {order['created_at'][:10]}\n\n"
        f"*Товары:*\n{items_text}\n"
    )
    if order.get("delivery_address"):
        text += f"\n📍 Адрес: {order['delivery_address']}"
    if order.get("desired_date"):
        text += f"\n📅 Дата поставки: {order['desired_date']}"
    if order.get("buyer_comment"):
        text += f"\n💬 Комментарий: {order['buyer_comment']}"
    if order.get("supplier_comment"):
        text += f"\n📝 Ответ поставщика: {order['supplier_comment']}"
    if order.get("total_amount"):
        text += f"\n💰 Сумма: {order['total_amount']} руб."
    return text


# ── Catalog ────────────────────────────────────────────────────────────────

async def show_catalog(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not db.get_user(update.effective_user.id):
        await update.message.reply_text("Используйте /start для регистрации.")
        return
    products = db.get_products(available_only=True)
    if not products:
        await update.message.reply_text("Каталог пока пуст.")
        return
    await update.message.reply_text(
        "📦 *Каталог товаров*\n\nВыберите товар для подробностей:",
        parse_mode="Markdown",
        reply_markup=products_keyboard(products),
    )


async def show_product_detail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    product_id = int(query.data.replace("product_", ""))
    p = db.get_product(product_id)
    if not p:
        await query.edit_message_text("Товар не найден.")
        return
    price = f"{p['base_price']} руб/{p['unit']}" if p.get("base_price") else "Договорная"
    await query.edit_message_text(
        f"📦 *{p['name']}*\n\n"
        f"{p.get('description') or 'Описание отсутствует'}\n\n"
        f"📏 Единица: {p['unit']}\n"
        f"📊 Мин. кол-во: {p['min_quantity']} {p['unit']}\n"
        f"💰 Цена: {price}",
        parse_mode="Markdown",
        reply_markup=back_to_catalog_btn(),
    )


async def back_to_catalog(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    products = db.get_products(available_only=True)
    await query.edit_message_text(
        "📦 *Каталог товаров*\n\nВыберите товар:",
        parse_mode="Markdown",
        reply_markup=products_keyboard(products),
    )


# ── Create order conversation ──────────────────────────────────────────────

async def start_order(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not db.get_user(update.effective_user.id):
        await update.message.reply_text("Используйте /start для регистрации.")
        return ConversationHandler.END
    products = db.get_products(available_only=True)
    if not products:
        await update.message.reply_text("Каталог пуст — создать заявку невозможно.")
        return ConversationHandler.END

    context.user_data["order"] = {"items": {}, "products": products}
    await update.message.reply_text(
        "📝 *Создание заявки — шаг 1/4*\n\n"
        "Выберите товары (можно несколько), затем нажмите *Готово*:",
        parse_mode="Markdown",
        reply_markup=products_for_order(products, []),
    )
    return ORDER_SELECT_PRODUCTS


async def toggle_product_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    product_id = int(query.data.replace("sel_prod_", ""))
    order = context.user_data["order"]
    if product_id in order["items"]:
        del order["items"][product_id]
    else:
        p = next((x for x in order["products"] if x["id"] == product_id), None)
        if p:
            order["items"][product_id] = {"name": p["name"], "unit": p["unit"], "qty": None}
    await query.edit_message_reply_markup(
        reply_markup=products_for_order(order["products"], list(order["items"].keys()))
    )
    return ORDER_SELECT_PRODUCTS


async def finish_product_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    order = context.user_data["order"]
    if not order["items"]:
        await query.answer("Выберите хотя бы один товар!", show_alert=True)
        return ORDER_SELECT_PRODUCTS
    await query.answer()

    context.user_data["order"]["qty_list"] = list(order["items"].keys())
    context.user_data["order"]["qty_index"] = 0
    first_id = context.user_data["order"]["qty_list"][0]
    info = order["items"][first_id]

    await query.edit_message_text(
        f"📊 *Шаг 2/4 — количество*\n\n"
        f"Товар: *{info['name']}*\nЕд. изм.: {info['unit']}\n\n"
        "Введите количество:",
        parse_mode="Markdown",
    )
    return ORDER_QUANTITIES


async def enter_quantity(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip().replace(",", ".")
    try:
        qty = float(text)
        if qty <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("Введите корректное положительное число:")
        return ORDER_QUANTITIES

    order = context.user_data["order"]
    idx = order["qty_index"]
    cur_id = order["qty_list"][idx]
    order["items"][cur_id]["qty"] = qty
    idx += 1
    order["qty_index"] = idx

    if idx < len(order["qty_list"]):
        next_id = order["qty_list"][idx]
        info = order["items"][next_id]
        await update.message.reply_text(
            f"Товар: *{info['name']}*\nЕд. изм.: {info['unit']}\n\nВведите количество:",
            parse_mode="Markdown",
        )
        return ORDER_QUANTITIES

    await update.message.reply_text(
        "📍 *Шаг 3/4 — адрес доставки*\n\n"
        "Введите адрес (или «-» для самовывоза):",
        parse_mode="Markdown",
    )
    return ORDER_ADDRESS


async def enter_address(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    addr = update.message.text.strip()
    context.user_data["order"]["address"] = "Самовывоз" if addr == "-" else addr
    await update.message.reply_text(
        "📅 *Шаг 4/4 — желаемая дата поставки*\n\n"
        "Формат: ДД.ММ.ГГГГ (или «-» если не важно):",
        parse_mode="Markdown",
    )
    return ORDER_DATE


async def enter_date(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    date_iso = None
    if text != "-":
        if not re.match(r"^\d{2}\.\d{2}\.\d{4}$", text):
            await update.message.reply_text("Неверный формат. Введите ДД.ММ.ГГГГ или «-»:")
            return ORDER_DATE
        d, m, y = text.split(".")
        date_iso = f"{y}-{m}-{d}"
    context.user_data["order"]["date"] = date_iso
    await update.message.reply_text("💬 Добавьте комментарий к заявке (или «-» если нет):")
    return ORDER_COMMENT


async def enter_comment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    comment = update.message.text.strip()
    context.user_data["order"]["comment"] = "" if comment == "-" else comment

    order = context.user_data["order"]
    items_text = "\n".join(
        f"  • {v['name']}: {v['qty']} {v['unit']}" for v in order["items"].values()
    )
    date_disp = order["date"].replace("-", ".") if order.get("date") else "Не указана"
    if order.get("date"):
        y, m, d = order["date"].split("-")
        date_disp = f"{d}.{m}.{y}"

    text = (
        f"📋 *Подтверждение заявки*\n\n"
        f"*Товары:*\n{items_text}\n\n"
        f"📍 Адрес: {order['address']}\n"
        f"📅 Дата: {date_disp}\n"
    )
    if order.get("comment"):
        text += f"💬 Комментарий: {order['comment']}\n"
    text += "\nПодтвердить?"

    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=confirm_order_kb())
    return ORDER_CONFIRM


async def confirm_order_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    if query.data == "cancel_order":
        context.user_data.clear()
        await query.edit_message_text("❌ Создание заявки отменено.")
        return ConversationHandler.END

    order = context.user_data["order"]
    rec = db.create_order(
        buyer_id=update.effective_user.id,
        delivery_address=order.get("address", ""),
        desired_date=order.get("date") or "",
        buyer_comment=order.get("comment", ""),
    )
    if not rec:
        await query.edit_message_text("Ошибка при создании заявки. Попробуйте снова.")
        return ConversationHandler.END

    order_id = rec["id"]
    for pid, info in order["items"].items():
        db.add_order_item(order_id, pid, info["name"], info["qty"], info["unit"])

    await query.edit_message_text(
        f"✅ *Заявка #{order_id} создана!*\n\n"
        "Поставщики получили уведомление.\n"
        "Вы получите сообщение при смене статуса.",
        parse_mode="Markdown",
    )
    await _notify_suppliers(context, order_id, order["items"], order.get("address", ""))
    context.user_data.clear()
    return ConversationHandler.END


async def cancel_order(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await update.message.reply_text("❌ Создание заявки отменено.", reply_markup=main_menu_buyer())
    return ConversationHandler.END


async def _notify_suppliers(context: ContextTypes.DEFAULT_TYPE, order_id: int,
                             items: dict, address: str):
    users = db.get_all_users()
    targets = [u for u in users if u["role"] in ("supplier", "admin")]
    items_text = "\n".join(f"  • {v['name']}: {v['qty']} {v['unit']}" for v in items.values())
    msg = (
        f"🆕 *Новая заявка #{order_id}*\n\n"
        f"*Товары:*\n{items_text}\n\n"
        f"📍 Адрес: {address}\n\n"
        "Откройте «Новые заявки» для обработки."
    )
    for t in targets:
        try:
            await context.bot.send_message(t["id"], msg, parse_mode="Markdown")
        except Exception as e:
            logger.warning(f"Cannot notify supplier {t['id']}: {e}")


# ── My orders ──────────────────────────────────────────────────────────────

async def my_orders_buyer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    orders = db.get_orders_by_buyer(update.effective_user.id)
    if not orders:
        await update.message.reply_text("У вас пока нет заявок. Создайте первую!")
        return
    await update.message.reply_text(
        f"📋 *Ваши заявки* ({len(orders)} шт.):\n\nВыберите для просмотра:",
        parse_mode="Markdown",
        reply_markup=orders_list_kb(orders, "buyer_ord_"),
    )


async def view_buyer_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    oid = int(query.data.replace("buyer_ord_", ""))
    order = db.get_order(oid)
    items = db.get_order_items(oid)
    if not order:
        await query.edit_message_text("Заявка не найдена.")
        return
    await query.edit_message_text(
        format_order(order, items),
        parse_mode="Markdown",
        reply_markup=back_btn("back_buyer_orders"),
    )


async def back_buyer_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    orders = db.get_orders_by_buyer(update.effective_user.id)
    await query.edit_message_text(
        f"📋 *Ваши заявки* ({len(orders)} шт.):",
        parse_mode="Markdown",
        reply_markup=orders_list_kb(orders, "buyer_ord_"),
    )
