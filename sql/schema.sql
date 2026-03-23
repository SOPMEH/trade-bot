-- ============================================================
--  Схема БД для системы договорной торговли (Supabase / PostgreSQL)
--  Выполните этот SQL в разделе SQL Editor на supabase.com
-- ============================================================

-- Пользователи (синхронизируются с Telegram)
CREATE TABLE IF NOT EXISTS users (
    id          BIGINT PRIMARY KEY,          -- Telegram user ID
    username    TEXT DEFAULT '',
    full_name   TEXT NOT NULL,
    role        TEXT NOT NULL DEFAULT 'buyer'
                    CHECK (role IN ('buyer', 'supplier', 'admin')),
    company     TEXT DEFAULT '',
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- Каталог товаров
CREATE TABLE IF NOT EXISTS products (
    id           SERIAL PRIMARY KEY,
    name         TEXT NOT NULL,
    description  TEXT DEFAULT '',
    unit         TEXT NOT NULL DEFAULT 'шт',  -- единица измерения
    min_quantity NUMERIC NOT NULL DEFAULT 1,
    base_price   NUMERIC,                      -- NULL = договорная цена
    is_available BOOLEAN NOT NULL DEFAULT TRUE,
    created_at   TIMESTAMPTZ DEFAULT NOW()
);

-- Заявки на товары
CREATE TABLE IF NOT EXISTS orders (
    id               SERIAL PRIMARY KEY,
    buyer_id         BIGINT NOT NULL REFERENCES users(id),
    supplier_id      BIGINT REFERENCES users(id),
    status           TEXT NOT NULL DEFAULT 'new'
                         CHECK (status IN ('new','reviewing','accepted','rejected','completed')),
    delivery_address TEXT DEFAULT '',
    desired_date     DATE,
    buyer_comment    TEXT DEFAULT '',
    supplier_comment TEXT DEFAULT '',
    total_amount     NUMERIC,
    created_at       TIMESTAMPTZ DEFAULT NOW(),
    updated_at       TIMESTAMPTZ DEFAULT NOW()
);

-- Позиции заявки (товары в заявке)
CREATE TABLE IF NOT EXISTS order_items (
    id           SERIAL PRIMARY KEY,
    order_id     INT NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    product_id   INT REFERENCES products(id),
    product_name TEXT NOT NULL,   -- снимок названия на момент заявки
    quantity     NUMERIC NOT NULL,
    unit         TEXT NOT NULL,
    price        NUMERIC,         -- согласованная цена (заполняет поставщик)
    created_at   TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
--  Демо-данные: несколько товаров для тестирования
-- ============================================================
INSERT INTO products (name, description, unit, min_quantity, base_price) VALUES
    ('Цемент М500',   'Портландцемент марки М500, мешок 50 кг', 'мешок', 10,  650),
    ('Арматура Ø12',  'Стальная арматура диаметром 12 мм, длина 12 м', 'т', 1, 68000),
    ('Кирпич М150',   'Одинарный строительный кирпич', 'шт', 1000, 12),
    ('Доска обрезная','Сосна, 150×50×6000 мм', 'м³', 1, 28000),
    ('Щебень фр. 20-40', 'Гранитный щебень фракции 20-40 мм', 'т', 5, NULL);
