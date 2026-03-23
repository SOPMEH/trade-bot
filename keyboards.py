from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from typing import List, Dict


# ── REPLY KEYBOARDS (главное меню) ─────────────────────────────────────────

def main_menu_buyer() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup([
        [KeyboardButton("📦 Каталог товаров"), KeyboardButton("📝 Создать заявку")],
        [KeyboardButton("📋 Мои заявки"),      KeyboardButton("👤 Мой профиль")],
    ], resize_keyboard=True)


def main_menu_supplier() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup([
        [KeyboardButton("🆕 Новые заявки"),  KeyboardButton("📋 Мои заявки")],
        [KeyboardButton("👤 Мой профиль")],
    ], resize_keyboard=True)


def main_menu_admin() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup([
        [KeyboardButton("📦 Управление товарами"), KeyboardButton("👥 Пользователи")],
        [KeyboardButton("📋 Все заявки"),           KeyboardButton("👤 Мой профиль")],
    ], resize_keyboard=True)


def get_main_menu(role: str) -> ReplyKeyboardMarkup:
    if role == "admin":
        return main_menu_admin()
    if role == "supplier":
        return main_menu_supplier()
    return main_menu_buyer()


# ── REGISTRATION ───────────────────────────────────────────────────────────

def role_selection() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🛒 Покупатель", callback_data="role_buyer")],
        [InlineKeyboardButton("🏭 Поставщик",  callback_data="role_supplier")],
    ])


# ── CATALOG ────────────────────────────────────────────────────────────────

def products_keyboard(products: List[Dict]) -> InlineKeyboardMarkup:
    rows = []
    for p in products:
        price = f"{p['base_price']} руб/{p['unit']}" if p.get("base_price") else "Договорная"
        rows.append([InlineKeyboardButton(f"{p['name']} — {price}", callback_data=f"product_{p['id']}")])
    return InlineKeyboardMarkup(rows)


def back_to_catalog_btn() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад к каталогу", callback_data="back_catalog")]])


# ── ORDER CREATION ─────────────────────────────────────────────────────────

def products_for_order(products: List[Dict], selected_ids: List[int]) -> InlineKeyboardMarkup:
    rows = []
    for p in products:
        mark = "✅ " if p["id"] in selected_ids else ""
        rows.append([InlineKeyboardButton(
            f"{mark}{p['name']} ({p['unit']})",
            callback_data=f"sel_prod_{p['id']}"
        )])
    rows.append([InlineKeyboardButton("✔️ Готово", callback_data="order_products_done")])
    return InlineKeyboardMarkup(rows)


def confirm_order_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Подтвердить", callback_data="confirm_order")],
        [InlineKeyboardButton("❌ Отменить",    callback_data="cancel_order")],
    ])


# ── ORDERS LIST ────────────────────────────────────────────────────────────

STATUS_ICONS = {
    "new":       "🆕",
    "reviewing": "👀",
    "accepted":  "✅",
    "rejected":  "❌",
    "completed": "✔️",
}


def orders_list_kb(orders: List[Dict], cb_prefix: str) -> InlineKeyboardMarkup:
    rows = []
    for o in orders:
        icon = STATUS_ICONS.get(o["status"], "📋")
        rows.append([InlineKeyboardButton(
            f"{icon} Заявка #{o['id']}  {o['created_at'][:10]}",
            callback_data=f"{cb_prefix}{o['id']}"
        )])
    return InlineKeyboardMarkup(rows)


# ── SUPPLIER ───────────────────────────────────────────────────────────────

def order_actions_supplier(order_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Принять",    callback_data=f"sup_accept_{order_id}")],
        [InlineKeyboardButton("❌ Отклонить",  callback_data=f"sup_reject_{order_id}")],
        [InlineKeyboardButton("◀️ Назад",      callback_data="back_new_orders")],
    ])


def order_complete_kb(order_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✔️ Отметить выполненной", callback_data=f"sup_complete_{order_id}")],
        [InlineKeyboardButton("◀️ Назад", callback_data="back_sup_orders")],
    ])


def back_btn(cb: str, label: str = "◀️ Назад") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton(label, callback_data=cb)]])


# ── ADMIN ──────────────────────────────────────────────────────────────────

def admin_products_kb(products: List[Dict]) -> InlineKeyboardMarkup:
    rows = []
    for p in products:
        icon = "✅" if p["is_available"] else "❌"
        rows.append([InlineKeyboardButton(f"{icon} {p['name']}", callback_data=f"adm_prod_{p['id']}")])
    rows.append([InlineKeyboardButton("➕ Добавить товар", callback_data="adm_add_product")])
    return InlineKeyboardMarkup(rows)


def admin_product_actions_kb(product_id: int, is_available: bool) -> InlineKeyboardMarkup:
    toggle = "❌ Скрыть" if is_available else "✅ Показать"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(toggle,     callback_data=f"adm_toggle_{product_id}")],
        [InlineKeyboardButton("◀️ Назад", callback_data="back_adm_products")],
    ])


def admin_users_kb(users: List[Dict]) -> InlineKeyboardMarkup:
    icons = {"buyer": "🛒", "supplier": "🏭", "admin": "⚙️"}
    rows = []
    for u in users:
        icon = icons.get(u["role"], "👤")
        uname = f"@{u['username']}" if u.get("username") else "—"
        rows.append([InlineKeyboardButton(
            f"{icon} {u['full_name']} ({uname})",
            callback_data=f"adm_user_{u['id']}"
        )])
    return InlineKeyboardMarkup(rows)


def admin_change_role_kb(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🛒 Покупатель",      callback_data=f"adm_setrole_{user_id}_buyer")],
        [InlineKeyboardButton("🏭 Поставщик",       callback_data=f"adm_setrole_{user_id}_supplier")],
        [InlineKeyboardButton("⚙️ Администратор",   callback_data=f"adm_setrole_{user_id}_admin")],
        [InlineKeyboardButton("◀️ Назад",           callback_data="back_adm_users")],
    ])
