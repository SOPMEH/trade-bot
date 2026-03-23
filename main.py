import logging
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ConversationHandler, filters,
)
from config import BOT_TOKEN, WEBHOOK_URL, PORT
from database import db

# Handlers
from handlers.common import (
    start, register_name, register_role, register_company, profile,
    REGISTER_NAME, REGISTER_ROLE, REGISTER_COMPANY,
)
from handlers.buyer import (
    show_catalog, show_product_detail, back_to_catalog,
    start_order, toggle_product_selection, finish_product_selection,
    enter_quantity, enter_address, enter_date, enter_comment,
    confirm_order_handler, cancel_order, my_orders_buyer,
    view_buyer_order, back_buyer_orders,
    ORDER_SELECT_PRODUCTS, ORDER_QUANTITIES, ORDER_ADDRESS,
    ORDER_DATE, ORDER_COMMENT, ORDER_CONFIRM,
)
from handlers.supplier import (
    new_orders, view_new_order, accept_order,
    reject_order_ask, reject_order_comment,
    my_orders_supplier, view_supplier_order, complete_order,
    back_new_orders, back_sup_orders,
    REJECT_COMMENT,
)
from handlers.admin import (
    admin_products, admin_view_product, toggle_product, back_adm_products,
    start_add_product, add_name, add_desc, add_unit, add_min_qty, add_price,
    cancel_add_product,
    admin_users, admin_view_user, set_user_role, back_adm_users,
    all_orders, admin_view_order, back_adm_orders,
    ADD_NAME, ADD_DESC, ADD_UNIT, ADD_MIN_QTY, ADD_PRICE,
)

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


# ── Router: "Мои заявки" — разный смысл для buyer и supplier ──────────────

async def my_orders_router(update: Update, context):
    user = db.get_user(update.effective_user.id)
    if not user:
        await update.message.reply_text("Используйте /start для регистрации.")
        return
    if user["role"] == "buyer":
        await my_orders_buyer(update, context)
    else:
        await my_orders_supplier(update, context)


def main():
    app = Application.builder().token(BOT_TOKEN).build()

    # ── Registration ────────────────────────────────────────────────────────
    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            REGISTER_NAME:    [MessageHandler(filters.TEXT & ~filters.COMMAND, register_name)],
            REGISTER_ROLE:    [CallbackQueryHandler(register_role, pattern=r"^role_")],
            REGISTER_COMPANY: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_company)],
        },
        fallbacks=[CommandHandler("start", start)],
    ))

    # ── Create order ────────────────────────────────────────────────────────
    app.add_handler(ConversationHandler(
        entry_points=[MessageHandler(filters.Regex(r"^📝 Создать заявку$"), start_order)],
        states={
            ORDER_SELECT_PRODUCTS: [
                CallbackQueryHandler(toggle_product_selection, pattern=r"^sel_prod_"),
                CallbackQueryHandler(finish_product_selection, pattern=r"^order_products_done$"),
            ],
            ORDER_QUANTITIES: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_quantity)],
            ORDER_ADDRESS:    [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_address)],
            ORDER_DATE:       [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_date)],
            ORDER_COMMENT:    [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_comment)],
            ORDER_CONFIRM:    [CallbackQueryHandler(confirm_order_handler,
                                                    pattern=r"^(confirm_order|cancel_order)$")],
        },
        fallbacks=[MessageHandler(filters.Regex(r"^❌"), cancel_order)],
    ))

    # ── Reject order (supplier) ─────────────────────────────────────────────
    app.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(reject_order_ask, pattern=r"^sup_reject_")],
        states={
            REJECT_COMMENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, reject_order_comment)],
        },
        fallbacks=[CommandHandler("cancel", lambda u, c: ConversationHandler.END)],
    ))

    # ── Add product (admin) ─────────────────────────────────────────────────
    app.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(start_add_product, pattern=r"^adm_add_product$")],
        states={
            ADD_NAME:    [MessageHandler(filters.TEXT & ~filters.COMMAND, add_name)],
            ADD_DESC:    [MessageHandler(filters.TEXT & ~filters.COMMAND, add_desc)],
            ADD_UNIT:    [MessageHandler(filters.TEXT & ~filters.COMMAND, add_unit)],
            ADD_MIN_QTY: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_min_qty)],
            ADD_PRICE:   [MessageHandler(filters.TEXT & ~filters.COMMAND, add_price)],
        },
        fallbacks=[CommandHandler("cancel", cancel_add_product)],
    ))

    # ── Reply keyboard buttons ──────────────────────────────────────────────
    app.add_handler(MessageHandler(filters.Regex(r"^👤 Мой профиль$"), profile))
    app.add_handler(MessageHandler(filters.Regex(r"^📦 Каталог товаров$"), show_catalog))
    app.add_handler(MessageHandler(filters.Regex(r"^📋 Мои заявки$"), my_orders_router))
    app.add_handler(MessageHandler(filters.Regex(r"^🆕 Новые заявки$"), new_orders))
    app.add_handler(MessageHandler(filters.Regex(r"^📦 Управление товарами$"), admin_products))
    app.add_handler(MessageHandler(filters.Regex(r"^👥 Пользователи$"), admin_users))
    app.add_handler(MessageHandler(filters.Regex(r"^📋 Все заявки$"), all_orders))

    # ── Inline buttons ──────────────────────────────────────────────────────
    # Catalog
    app.add_handler(CallbackQueryHandler(show_product_detail, pattern=r"^product_"))
    app.add_handler(CallbackQueryHandler(back_to_catalog, pattern=r"^back_catalog$"))

    # Buyer orders
    app.add_handler(CallbackQueryHandler(view_buyer_order, pattern=r"^buyer_ord_"))
    app.add_handler(CallbackQueryHandler(back_buyer_orders, pattern=r"^back_buyer_orders$"))

    # Supplier
    app.add_handler(CallbackQueryHandler(view_new_order, pattern=r"^sup_view_"))
    app.add_handler(CallbackQueryHandler(accept_order, pattern=r"^sup_accept_"))
    app.add_handler(CallbackQueryHandler(view_supplier_order, pattern=r"^sup_ord_"))
    app.add_handler(CallbackQueryHandler(complete_order, pattern=r"^sup_complete_"))
    app.add_handler(CallbackQueryHandler(back_new_orders, pattern=r"^back_new_orders$"))
    app.add_handler(CallbackQueryHandler(back_sup_orders, pattern=r"^back_sup_orders$"))

    # Admin — products
    app.add_handler(CallbackQueryHandler(admin_view_product, pattern=r"^adm_prod_"))
    app.add_handler(CallbackQueryHandler(toggle_product, pattern=r"^adm_toggle_"))
    app.add_handler(CallbackQueryHandler(back_adm_products, pattern=r"^back_adm_products$"))

    # Admin — users
    app.add_handler(CallbackQueryHandler(admin_view_user, pattern=r"^adm_user_"))
    app.add_handler(CallbackQueryHandler(set_user_role, pattern=r"^adm_setrole_"))
    app.add_handler(CallbackQueryHandler(back_adm_users, pattern=r"^back_adm_users$"))

    # Admin — orders
    app.add_handler(CallbackQueryHandler(admin_view_order, pattern=r"^adm_ord_"))
    app.add_handler(CallbackQueryHandler(back_adm_orders, pattern=r"^back_adm_orders$"))

    # ── Run ─────────────────────────────────────────────────────────────────
    if WEBHOOK_URL:
        logger.info(f"Starting webhook mode on port {PORT}")
        app.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            url_path=BOT_TOKEN,
            webhook_url=f"{WEBHOOK_URL}/{BOT_TOKEN}",
        )
    else:
        logger.info("Starting polling mode...")
        app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
