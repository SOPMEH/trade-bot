import asyncio
import hashlib
import hmac
import json
import logging
from typing import Optional, List
from urllib.parse import unquote

import uvicorn
from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, Update, WebAppInfo
from telegram.ext import Application, CommandHandler

from config import ADMIN_IDS, BOT_TOKEN, PORT, WEBHOOK_URL
from database import db

logging.basicConfig(format="%(asctime)s | %(levelname)s | %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Договорная торговля API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

ptb_app: Optional[Application] = None


# ── Telegram initData validation ───────────────────────────────────────────

def validate_init_data(init_data: str) -> dict:
    """Проверяет подпись Telegram WebApp initData и возвращает данные пользователя."""
    if not init_data:
        raise HTTPException(status_code=401, detail="Отсутствуют данные авторизации Telegram")

    raw_parts: dict[str, str] = {}
    for item in init_data.split("&"):
        if "=" in item:
            k, v = item.split("=", 1)
            raw_parts[k] = v

    hash_str = raw_parts.pop("hash", None)
    if not hash_str:
        raise HTTPException(status_code=401, detail="Отсутствует hash")

    data_check = "\n".join(f"{k}={raw_parts[k]}" for k in sorted(raw_parts))
    secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
    expected = hmac.new(secret_key, data_check.encode(), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(expected, hash_str):
        raise HTTPException(status_code=401, detail="Неверная подпись initData")

    return json.loads(unquote(raw_parts.get("user", "{}")))


async def get_current_user(request: Request) -> dict:
    init_data = request.headers.get("X-Telegram-Init-Data", "")
    tg_user = validate_init_data(init_data)
    user = db.get_user(tg_user["id"])
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не зарегистрирован")
    return user


# ── Auth ───────────────────────────────────────────────────────────────────

class AuthBody(BaseModel):
    init_data: str
    role: Optional[str] = None
    full_name: Optional[str] = None
    company: Optional[str] = None


@app.post("/api/auth")
async def auth(body: AuthBody):
    tg_user = validate_init_data(body.init_data)
    uid = tg_user["id"]

    user = db.get_user(uid)
    if user:
        return user

    if not body.role or not body.full_name:
        return {
            "registered": False,
            "telegram_id": uid,
            "first_name": tg_user.get("first_name", ""),
            "username": tg_user.get("username", ""),
        }

    role = "admin" if uid in ADMIN_IDS else body.role

    return db.create_user(
        telegram_id=uid,
        username=tg_user.get("username", ""),
        full_name=body.full_name,
        role=role,
        company=body.company or "",
    )


# ── Products ───────────────────────────────────────────────────────────────

@app.get("/api/products")
async def get_products(user: dict = Depends(get_current_user)):
    return db.get_products(available_only=True)


@app.get("/api/admin/products")
async def admin_get_products(user: dict = Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(403)
    return db.get_products(available_only=False)


class ProductCreate(BaseModel):
    name: str
    description: str = ""
    unit: str = "шт"
    min_quantity: float = 1
    base_price: Optional[float] = None


@app.post("/api/admin/products")
async def create_product(body: ProductCreate, user: dict = Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(403)
    p = db.create_product(body.name, body.description, body.unit, body.min_quantity, body.base_price)
    if not p:
        raise HTTPException(500, "Ошибка создания товара")
    return p


@app.patch("/api/admin/products/{product_id}/toggle")
async def toggle_product(product_id: int, user: dict = Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(403)
    db.toggle_product_availability(product_id)
    return db.get_product(product_id)


# ── Orders ─────────────────────────────────────────────────────────────────

class OrderItemModel(BaseModel):
    product_id: int
    product_name: str
    quantity: float
    unit: str


class OrderCreate(BaseModel):
    items: List[OrderItemModel]
    delivery_address: str = ""
    desired_date: str = ""
    buyer_comment: str = ""


@app.post("/api/orders")
async def create_order(body: OrderCreate, user: dict = Depends(get_current_user)):
    if user["role"] != "buyer":
        raise HTTPException(403, "Только покупатели могут создавать заявки")

    order = db.create_order(
        buyer_id=user["id"],
        delivery_address=body.delivery_address,
        desired_date=body.desired_date,
        buyer_comment=body.buyer_comment,
    )
    if not order:
        raise HTTPException(500, "Ошибка создания заявки")

    for item in body.items:
        db.add_order_item(order["id"], item.product_id, item.product_name, item.quantity, item.unit)

    await _notify_new_order(order["id"])
    return order


@app.get("/api/orders")
async def get_my_orders(user: dict = Depends(get_current_user)):
    if user["role"] == "buyer":
        orders = db.get_orders_by_buyer(user["id"])
    else:
        orders = db.get_supplier_orders(user["id"])
    return [_with_items(o) for o in orders]


@app.get("/api/orders/new")
async def get_new_orders(user: dict = Depends(get_current_user)):
    if user["role"] not in ("supplier", "admin"):
        raise HTTPException(403)
    result = []
    for o in db.get_new_orders():
        enriched = _with_items(o)
        enriched["buyer"] = db.get_user(o["buyer_id"])
        result.append(enriched)
    return result


class OrderUpdate(BaseModel):
    status: str
    supplier_comment: str = ""
    total_amount: Optional[float] = None


@app.patch("/api/orders/{order_id}")
async def update_order(order_id: int, body: OrderUpdate, user: dict = Depends(get_current_user)):
    if user["role"] not in ("supplier", "admin"):
        raise HTTPException(403)
    order = db.get_order(order_id)
    if not order:
        raise HTTPException(404)
    db.update_order_status(
        order_id=order_id,
        status=body.status,
        supplier_id=user["id"],
        supplier_comment=body.supplier_comment,
        total_amount=body.total_amount,
    )
    await _notify_buyer(order["buyer_id"], order_id, body.status, body.supplier_comment)
    return db.get_order(order_id)


@app.get("/api/admin/orders")
async def admin_get_orders(user: dict = Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(403)
    result = []
    for o in db.get_all_orders():
        enriched = _with_items(o)
        enriched["buyer"] = db.get_user(o["buyer_id"])
        result.append(enriched)
    return result


def _with_items(order: dict) -> dict:
    return {**order, "items": db.get_order_items(order["id"])}


# ── Admin users ────────────────────────────────────────────────────────────

@app.get("/api/admin/users")
async def get_users(user: dict = Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(403)
    return db.get_all_users()


class UserUpdate(BaseModel):
    role: str


@app.patch("/api/admin/users/{user_id}")
async def update_user_role(user_id: int, body: UserUpdate, user: dict = Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(403)
    db.update_user(user_id, role=body.role)
    return db.get_user(user_id)


# ── Notifications ──────────────────────────────────────────────────────────

async def _notify_new_order(order_id: int):
    bot = Bot(token=BOT_TOKEN)
    items = db.get_order_items(order_id)
    items_text = "\n".join(f"  • {i['product_name']}: {i['quantity']} {i['unit']}" for i in items)
    msg = f"🆕 *Новая заявка #{order_id}*\n\n*Товары:*\n{items_text}\n\nОткройте приложение для обработки."
    for u in db.get_all_users():
        if u["role"] in ("supplier", "admin"):
            try:
                await bot.send_message(u["id"], msg, parse_mode="Markdown")
            except Exception as e:
                logger.warning(f"Notify supplier {u['id']}: {e}")


async def _notify_buyer(buyer_id: int, order_id: int, status: str, comment: str):
    bot = Bot(token=BOT_TOKEN)
    status_map = {"accepted": "✅ принята", "rejected": "❌ отклонена", "completed": "✔️ выполнена"}
    msg = f"📋 *Заявка #{order_id} {status_map.get(status, status)}*"
    if comment:
        msg += f"\n\n💬 {comment}"
    try:
        await bot.send_message(buyer_id, msg, parse_mode="Markdown")
    except Exception as e:
        logger.warning(f"Notify buyer {buyer_id}: {e}")


# ── Bot lifecycle ──────────────────────────────────────────────────────────

@app.on_event("startup")
async def startup():
    global ptb_app
    ptb_app = Application.builder().token(BOT_TOKEN).build()

    async def start_cmd(update: Update, ctx):
        webapp_url = WEBHOOK_URL or "https://your-app.railway.app"
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("🚀 Открыть приложение", web_app=WebAppInfo(url=webapp_url))
        ]])
        await update.message.reply_text(
            "👋 Добро пожаловать в систему договорной торговли!\n\n"
            "Нажмите кнопку ниже, чтобы открыть приложение:",
            reply_markup=kb,
        )

    ptb_app.add_handler(CommandHandler("start", start_cmd))
    await ptb_app.initialize()

    if WEBHOOK_URL:
        await ptb_app.bot.set_webhook(f"{WEBHOOK_URL}/webhook/{BOT_TOKEN}")
        logger.info("Webhook установлен")
    else:
        await ptb_app.start()
        asyncio.create_task(ptb_app.updater.start_polling())
        logger.info("Polling запущен")


@app.on_event("shutdown")
async def shutdown():
    if ptb_app:
        if not WEBHOOK_URL and ptb_app.updater:
            await ptb_app.updater.stop()
        await ptb_app.stop()
        await ptb_app.shutdown()


@app.post("/webhook/{token}")
async def webhook(token: str, request: Request):
    if token != BOT_TOKEN:
        raise HTTPException(403)
    data = await request.json()
    update = Update.de_json(data, ptb_app.bot)
    await ptb_app.process_update(update)
    return {"ok": True}


# ── Static files ───────────────────────────────────────────────────────────

app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
async def root():
    return FileResponse("static/index.html")


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=PORT)
