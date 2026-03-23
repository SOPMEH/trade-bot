import logging
from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler
from database import db
from keyboards import orders_list_kb, order_actions_supplier, order_complete_kb, back_btn
from handlers.buyer import format_order

logger = logging.getLogger(__name__)

# Conversation state
REJECT_COMMENT = 0


def _check_supplier(user) -> bool:
    return user and user["role"] in ("supplier", "admin")


# ── New orders ─────────────────────────────────────────────────────────────

async def new_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = db.get_user(update.effective_user.id)
    if not _check_supplier(user):
        await update.message.reply_text("Нет доступа.")
        return
    orders = db.get_new_orders()
    if not orders:
        await update.message.reply_text("Новых заявок нет. ✅")
        return
    await update.message.reply_text(
        f"🆕 *Новые заявки* ({len(orders)} шт.):",
        parse_mode="Markdown",
        reply_markup=orders_list_kb(orders, "sup_view_"),
    )


async def view_new_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    oid = int(query.data.replace("sup_view_", ""))
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
    await query.edit_message_text(text, parse_mode="Markdown",
                                  reply_markup=order_actions_supplier(oid))


async def back_new_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    orders = db.get_new_orders()
    if not orders:
        await query.edit_message_text("Новых заявок нет. ✅")
        return
    await query.edit_message_text(
        f"🆕 *Новые заявки* ({len(orders)} шт.):",
        parse_mode="Markdown",
        reply_markup=orders_list_kb(orders, "sup_view_"),
    )


# ── Accept ─────────────────────────────────────────────────────────────────

async def accept_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    oid = int(query.data.replace("sup_accept_", ""))
    order = db.get_order(oid)
    db.update_order_status(oid, "accepted", supplier_id=update.effective_user.id)
    await query.edit_message_text(f"✅ Заявка #{oid} принята!")
    if order:
        supplier = db.get_user(update.effective_user.id)
        name = supplier["full_name"] if supplier else "Поставщик"
        try:
            await context.bot.send_message(
                order["buyer_id"],
                f"✅ *Ваша заявка #{oid} принята!*\n\nПоставщик: {name}\nОжидайте поставку.",
                parse_mode="Markdown",
            )
        except Exception as e:
            logger.warning(f"Cannot notify buyer: {e}")


# ── Reject conversation ────────────────────────────────────────────────────

async def reject_order_ask(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    oid = int(query.data.replace("sup_reject_", ""))
    context.user_data["reject_oid"] = oid
    await query.edit_message_text(
        f"❌ Отклонение заявки #{oid}\n\nУкажите причину:"
    )
    return REJECT_COMMENT


async def reject_order_comment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    comment = update.message.text.strip()
    oid = context.user_data.pop("reject_oid", None)
    if not oid:
        await update.message.reply_text("Ошибка. Попробуйте снова.")
        return ConversationHandler.END

    order = db.get_order(oid)
    db.update_order_status(oid, "rejected",
                           supplier_id=update.effective_user.id,
                           supplier_comment=comment)
    await update.message.reply_text(f"❌ Заявка #{oid} отклонена.")

    if order:
        try:
            await context.bot.send_message(
                order["buyer_id"],
                f"❌ *Ваша заявка #{oid} отклонена.*\n\nПричина: {comment}",
                parse_mode="Markdown",
            )
        except Exception as e:
            logger.warning(f"Cannot notify buyer: {e}")
    return ConversationHandler.END


# ── My orders (supplier) ───────────────────────────────────────────────────

async def my_orders_supplier(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = db.get_user(update.effective_user.id)
    if not _check_supplier(user):
        await update.message.reply_text("Нет доступа.")
        return
    orders = db.get_supplier_orders(update.effective_user.id)
    if not orders:
        await update.message.reply_text("У вас нет активных заявок.")
        return
    await update.message.reply_text(
        f"📋 *Ваши заявки* ({len(orders)} шт.):",
        parse_mode="Markdown",
        reply_markup=orders_list_kb(orders, "sup_ord_"),
    )


async def view_supplier_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    oid = int(query.data.replace("sup_ord_", ""))
    order = db.get_order(oid)
    items = db.get_order_items(oid)
    if not order:
        await query.edit_message_text("Заявка не найдена.")
        return
    kb = order_complete_kb(oid) if order["status"] == "accepted" else back_btn("back_sup_orders")
    await query.edit_message_text(
        format_order(order, items), parse_mode="Markdown", reply_markup=kb
    )


async def complete_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    oid = int(query.data.replace("sup_complete_", ""))
    order = db.get_order(oid)
    db.update_order_status(oid, "completed")
    await query.edit_message_text(f"✔️ Заявка #{oid} отмечена как выполненная!")
    if order:
        try:
            await context.bot.send_message(
                order["buyer_id"],
                f"✔️ *Ваша заявка #{oid} выполнена!*\n\nСпасибо за сотрудничество.",
                parse_mode="Markdown",
            )
        except Exception as e:
            logger.warning(f"Cannot notify buyer: {e}")


async def back_sup_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    orders = db.get_supplier_orders(update.effective_user.id)
    if not orders:
        await query.edit_message_text("У вас нет активных заявок.")
        return
    await query.edit_message_text(
        f"📋 *Ваши заявки* ({len(orders)} шт.):",
        parse_mode="Markdown",
        reply_markup=orders_list_kb(orders, "sup_ord_"),
    )
