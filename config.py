import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "")
PORT = int(os.getenv("PORT", 8000))

ADMIN_IDS = []
if os.getenv("ADMIN_IDS"):
    ADMIN_IDS = [int(x.strip()) for x in os.getenv("ADMIN_IDS").split(",") if x.strip().isdigit()]
