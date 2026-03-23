from supabase import create_client, Client
from config import SUPABASE_URL, SUPABASE_KEY
from typing import Optional, List, Dict
import logging

logger = logging.getLogger(__name__)

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


class Database:

    # ── USERS ──────────────────────────────────────────────────────────────

    @staticmethod
    def get_user(telegram_id: int) -> Optional[Dict]:
        try:
            res = supabase.table("users").select("*").eq("id", telegram_id).execute()
            return res.data[0] if res.data else None
        except Exception as e:
            logger.error(f"get_user error: {e}")
            return None

    @staticmethod
    def create_user(telegram_id: int, username: str, full_name: str,
                    role: str, company: str = "") -> Optional[Dict]:
        try:
            res = supabase.table("users").insert({
                "id": telegram_id,
                "username": username or "",
                "full_name": full_name,
                "role": role,
                "company": company,
            }).execute()
            return res.data[0] if res.data else None
        except Exception as e:
            logger.error(f"create_user error: {e}")
            return None

    @staticmethod
    def update_user(telegram_id: int, **kwargs) -> bool:
        try:
            supabase.table("users").update(kwargs).eq("id", telegram_id).execute()
            return True
        except Exception as e:
            logger.error(f"update_user error: {e}")
            return False

    @staticmethod
    def get_all_users() -> List[Dict]:
        try:
            res = supabase.table("users").select("*").order("created_at", desc=True).execute()
            return res.data or []
        except Exception as e:
            logger.error(f"get_all_users error: {e}")
            return []

    # ── PRODUCTS ───────────────────────────────────────────────────────────

    @staticmethod
    def get_products(available_only: bool = True) -> List[Dict]:
        try:
            q = supabase.table("products").select("*")
            if available_only:
                q = q.eq("is_available", True)
            res = q.order("name").execute()
            return res.data or []
        except Exception as e:
            logger.error(f"get_products error: {e}")
            return []

    @staticmethod
    def get_product(product_id: int) -> Optional[Dict]:
        try:
            res = supabase.table("products").select("*").eq("id", product_id).execute()
            return res.data[0] if res.data else None
        except Exception as e:
            logger.error(f"get_product error: {e}")
            return None

    @staticmethod
    def create_product(name: str, description: str, unit: str,
                       min_quantity: float, base_price: Optional[float]) -> Optional[Dict]:
        try:
            res = supabase.table("products").insert({
                "name": name,
                "description": description,
                "unit": unit,
                "min_quantity": min_quantity,
                "base_price": base_price,
                "is_available": True,
            }).execute()
            return res.data[0] if res.data else None
        except Exception as e:
            logger.error(f"create_product error: {e}")
            return None

    @staticmethod
    def toggle_product_availability(product_id: int) -> bool:
        try:
            cur = supabase.table("products").select("is_available").eq("id", product_id).execute()
            if cur.data:
                new_val = not cur.data[0]["is_available"]
                supabase.table("products").update({"is_available": new_val}).eq("id", product_id).execute()
                return True
            return False
        except Exception as e:
            logger.error(f"toggle_product error: {e}")
            return False

    # ── ORDERS ─────────────────────────────────────────────────────────────

    @staticmethod
    def create_order(buyer_id: int, delivery_address: str,
                     desired_date: str, buyer_comment: str) -> Optional[Dict]:
        try:
            res = supabase.table("orders").insert({
                "buyer_id": buyer_id,
                "status": "new",
                "delivery_address": delivery_address,
                "desired_date": desired_date or None,
                "buyer_comment": buyer_comment,
            }).execute()
            return res.data[0] if res.data else None
        except Exception as e:
            logger.error(f"create_order error: {e}")
            return None

    @staticmethod
    def get_order(order_id: int) -> Optional[Dict]:
        try:
            res = supabase.table("orders").select("*").eq("id", order_id).execute()
            return res.data[0] if res.data else None
        except Exception as e:
            logger.error(f"get_order error: {e}")
            return None

    @staticmethod
    def get_orders_by_buyer(buyer_id: int) -> List[Dict]:
        try:
            res = (supabase.table("orders").select("*")
                   .eq("buyer_id", buyer_id)
                   .order("created_at", desc=True).execute())
            return res.data or []
        except Exception as e:
            logger.error(f"get_orders_by_buyer error: {e}")
            return []

    @staticmethod
    def get_new_orders() -> List[Dict]:
        try:
            res = (supabase.table("orders").select("*")
                   .eq("status", "new")
                   .order("created_at", desc=True).execute())
            return res.data or []
        except Exception as e:
            logger.error(f"get_new_orders error: {e}")
            return []

    @staticmethod
    def get_supplier_orders(supplier_id: int) -> List[Dict]:
        try:
            res = (supabase.table("orders").select("*")
                   .eq("supplier_id", supplier_id)
                   .in_("status", ["reviewing", "accepted", "completed"])
                   .order("created_at", desc=True).execute())
            return res.data or []
        except Exception as e:
            logger.error(f"get_supplier_orders error: {e}")
            return []

    @staticmethod
    def update_order_status(order_id: int, status: str, supplier_id: int = None,
                            supplier_comment: str = None, total_amount: float = None) -> bool:
        try:
            data: Dict = {"status": status}
            if supplier_id is not None:
                data["supplier_id"] = supplier_id
            if supplier_comment is not None:
                data["supplier_comment"] = supplier_comment
            if total_amount is not None:
                data["total_amount"] = total_amount
            supabase.table("orders").update(data).eq("id", order_id).execute()
            return True
        except Exception as e:
            logger.error(f"update_order_status error: {e}")
            return False

    @staticmethod
    def get_all_orders() -> List[Dict]:
        try:
            res = supabase.table("orders").select("*").order("created_at", desc=True).execute()
            return res.data or []
        except Exception as e:
            logger.error(f"get_all_orders error: {e}")
            return []

    # ── ORDER ITEMS ────────────────────────────────────────────────────────

    @staticmethod
    def add_order_item(order_id: int, product_id: int, product_name: str,
                       quantity: float, unit: str) -> bool:
        try:
            supabase.table("order_items").insert({
                "order_id": order_id,
                "product_id": product_id,
                "product_name": product_name,
                "quantity": quantity,
                "unit": unit,
            }).execute()
            return True
        except Exception as e:
            logger.error(f"add_order_item error: {e}")
            return False

    @staticmethod
    def get_order_items(order_id: int) -> List[Dict]:
        try:
            res = supabase.table("order_items").select("*").eq("order_id", order_id).execute()
            return res.data or []
        except Exception as e:
            logger.error(f"get_order_items error: {e}")
            return []


db = Database()
