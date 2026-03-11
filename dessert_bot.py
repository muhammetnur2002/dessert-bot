import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from telegram.request import HTTPXRequest

# ========== НАСТРОЙКИ ==========
BOT_TOKEN = "8793875193:AAFoIJ30lxAF1EKOQtdHhylW6wTwBjc3nMM"   # Ваш токен

# ВНИМАНИЕ: ID группы должен быть отрицательным числом, например -1001234567890.
# Получите его через @getidsbot.
GROUP_ID = -1003871557312   # ЗАМЕНИТЕ НА РЕАЛЬНЫЙ ОТРИЦАТЕЛЬНЫЙ ID ГРУППЫ

# Прокси (если не нужен, оставить None)
PROXY = None   # или "socks5://127.0.0.1:9150" при использовании Tor
# ================================

# Настройка HTTP-клиента
request = HTTPXRequest(
    proxy=PROXY,
    connect_timeout=30,
    read_timeout=30,
    write_timeout=30,
    pool_timeout=30,
    http_version="1.1"
)

# Логирование
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ---------- КАТАЛОГ ТОВАРОВ ----------
# Категории и товары в каждой категории (название, callback_data)
CATEGORIES = {
    "cat_desserts": "🍰 Десерты",
    "cat_home":     "🧼 Хозяйственные товары",
    "cat_metro":    "🏪 Товары из Метро"
}

ITEMS = {
    "cat_desserts": [
        ("🍰 Тирамису", "tiramisu"),
        ("🧁 Капкейк", "cupcake"),
        ("🍫 Брауни", "brownie"),
        ("🍮 Панна-котта", "panna_cotta")
    ],
    "cat_home": [
        ("🧼 Мыло", "soap"),
        ("🧴 Шампунь", "shampoo"),
        ("🧽 Губки", "sponge"),
        ("🧹 Веник", "broom")
    ],
    "cat_metro": [
        ("🥩 Колбаса", "sausage"),
        ("🧀 Сыр", "cheese"),
        ("🥛 Молоко", "milk"),
        ("🍞 Хлеб", "bread")
    ]
}

# Для быстрого получения названия товара по callback_data
ITEM_NAME = {}
for cat, items in ITEMS.items():
    for name, cb in items:
        ITEM_NAME[cb] = name

# ---------- ХРАНИЛИЩЕ ДАННЫХ ----------
user_orders = {}          # {user_id: {callback: quantity}}
user_temp_item = {}       # временно хранит выбранный товар перед выбором количества
user_temp_edit = {}       # для редактирования

# ---------- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ----------
def format_cart(user_id: int) -> str:
    """Формирует сообщение с корзиной в требуемом формате."""
    cart = user_orders.get(user_id, {})
    if not cart:
        return "Ваша корзина пуста."
    lines = ["Добрый день !", 'Заявка "Спартак":']
    for item_cb, qty in cart.items():
        item_name = ITEM_NAME.get(item_cb, item_cb)  # на случай, если не найдётся
        lines.append(f"• {item_name}: {qty} шт.")
    return "\n".join(lines)

def categories_keyboard():
    """Клавиатура с категориями."""
    keyboard = []
    for cat_cb, cat_name in CATEGORIES.items():
        keyboard.append([InlineKeyboardButton(cat_name, callback_data=cat_cb)])
    return InlineKeyboardMarkup(keyboard)

def items_keyboard(category_cb: str):
    """Клавиатура с товарами выбранной категории."""
    items = ITEMS.get(category_cb, [])
    keyboard = [[InlineKeyboardButton(name, callback_data=cb)] for name, cb in items]
    keyboard.append([InlineKeyboardButton("🔙 Назад к категориям", callback_data="back_to_categories")])
    return InlineKeyboardMarkup(keyboard)

def cart_keyboard(user_id: int):
    """Клавиатура для просмотра корзины (подтвердить / редактировать)."""
    keyboard = [
        [InlineKeyboardButton("✏️ Редактировать", callback_data="edit_order")],
        [InlineKeyboardButton("✅ Подтвердить заказ", callback_data="confirm_order")]
    ]
    return InlineKeyboardMarkup(keyboard)

def edit_list_keyboard(user_id: int):
    """Клавиатура со списком товаров для редактирования."""
    cart = user_orders.get(user_id, {})
    keyboard = []
    for item_cb in cart:
        item_name = ITEM_NAME.get(item_cb, item_cb)
        keyboard.append([InlineKeyboardButton(f"✏️ {item_name}", callback_data=f"edit_{item_cb}")])
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="back_to_cart")])
    return InlineKeyboardMarkup(keyboard)

def item_edit_keyboard(item_cb: str):
    """Клавиатура для изменения количества конкретного товара."""
    keyboard = [
        [
            InlineKeyboardButton("➕ +1", callback_data=f"chg_{item_cb}_+1"),
            InlineKeyboardButton("➖ -1", callback_data=f"chg_{item_cb}_-1")
        ],
        [InlineKeyboardButton("🗑 Удалить", callback_data=f"del_{item_cb}")],
        [InlineKeyboardButton("🔙 Назад", callback_data="back_to_edit_list")]
    ]
    return InlineKeyboardMarkup(keyboard)

# ---------- ОБРАБОТЧИКИ ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Главное меню с выбором категории."""
    await update.message.reply_text(
        "🛒 Выберите категорию товаров:",
        reply_markup=categories_keyboard()
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data

    # ---------- ВЫБОР КАТЕГОРИИ ----------
    if data in CATEGORIES:
        await query.edit_message_text(
            f"{CATEGORIES[data]}\nВыберите товар:",
            reply_markup=items_keyboard(data)
        )

    # ---------- НАЗАД К КАТЕГОРИЯМ ----------
    elif data == "back_to_categories":
        await query.edit_message_text(
            "🛒 Выберите категорию товаров:",
            reply_markup=categories_keyboard()
        )

    # ---------- ВЫБОР ТОВАРА (из категории) ----------
    elif data in ITEM_NAME:  # callback_data товара
        user_temp_item[user_id] = data
        # Кнопки количества (1-5)
        keyboard = [
            [InlineKeyboardButton(str(i), callback_data=f"qty_{i}") for i in range(1, 4)],
            [InlineKeyboardButton(str(i), callback_data=f"qty_{i}") for i in range(4, 6)]
        ]
        await query.edit_message_text(
            "Сколько штук?",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    # ---------- ВЫБОР КОЛИЧЕСТВА ----------
    elif data.startswith("qty_"):
        qty = int(data.split("_")[1])
        item_cb = user_temp_item.pop(user_id, None)
        if item_cb:
            if user_id not in user_orders:
                user_orders[user_id] = {}
            user_orders[user_id][item_cb] = user_orders[user_id].get(item_cb, 0) + qty
            # Меню после добавления
            keyboard = [
                [InlineKeyboardButton("🍩 Продолжить выбор", callback_data="continue")],
                [InlineKeyboardButton("🛒 Оформить заказ", callback_data="checkout")]
            ]
            await query.edit_message_text(
                "✅ Товар добавлен в корзину!",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )

    # ---------- ПРОДОЛЖИТЬ ВЫБОР ----------
    elif data == "continue":
        await query.edit_message_text(
            "🛒 Выберите категорию товаров:",
            reply_markup=categories_keyboard()
        )

    # ---------- ПОКАЗАТЬ КОРЗИНУ ----------
    elif data == "checkout":
        if user_id not in user_orders or not user_orders[user_id]:
            await query.edit_message_text("Ваша корзина пуста. Начните с /start")
            return
        await query.edit_message_text(
            format_cart(user_id),
            reply_markup=cart_keyboard(user_id)
        )

    # ---------- ПОДТВЕРДИТЬ ЗАКАЗ ----------
    elif data == "confirm_order":
        if user_id not in user_orders or not user_orders[user_id]:
            await query.edit_message_text("Корзина пуста.")
            return
        cart_text = format_cart(user_id)
        try:
            logger.info(f"Отправка в группу {GROUP_ID}")
            await context.bot.send_message(
                chat_id=GROUP_ID,
                text=f"🛎 Новый заказ от {query.from_user.first_name}:\n\n{cart_text}"
            )
        except Exception as e:
            logger.error(f"Ошибка отправки: {e}", exc_info=True)
            await query.edit_message_text(
                f"❌ Ошибка: {e}\nПроверьте ID группы и права бота."
            )
            return
        # Очищаем корзину
        del user_orders[user_id]
        await query.edit_message_text(f"{cart_text}\n\n✅ Заказ отправлен!")

    # ---------- РЕДАКТИРОВАТЬ ЗАКАЗ (список позиций) ----------
    elif data == "edit_order":
        if user_id not in user_orders or not user_orders[user_id]:
            await query.edit_message_text("Корзина пуста.")
            return
        await query.edit_message_text(
            "Выберите товар для изменения:",
            reply_markup=edit_list_keyboard(user_id)
        )

    # ---------- ВЫБОР КОНКРЕТНОГО ТОВАРА ДЛЯ РЕДАКТИРОВАНИЯ ----------
    elif data.startswith("edit_"):
        item_cb = data.replace("edit_", "")
        user_temp_edit[user_id] = item_cb
        current_qty = user_orders[user_id].get(item_cb, 0)
        item_name = ITEM_NAME.get(item_cb, item_cb)
        await query.edit_message_text(
            f"{item_name}\nТекущее количество: {current_qty} шт.\nЧто делаем?",
            reply_markup=item_edit_keyboard(item_cb)
        )

    # ---------- ИЗМЕНЕНИЕ КОЛИЧЕСТВА ----------
    elif data.startswith("chg_"):
        parts = data.split("_")
        item_cb = parts[1]
        delta = int(parts[2])
        if user_id in user_orders and item_cb in user_orders[user_id]:
            new_qty = user_orders[user_id][item_cb] + delta
            if new_qty >= 1:
                user_orders[user_id][item_cb] = new_qty
            else:
                del user_orders[user_id][item_cb]
        # Возврат к списку редактирования
        if not user_orders.get(user_id):
            await query.edit_message_text("Корзина пуста. /start")
            return
        await query.edit_message_text(
            "✅ Количество изменено. Выберите товар:",
            reply_markup=edit_list_keyboard(user_id)
        )

    # ---------- УДАЛЕНИЕ ПОЗИЦИИ ----------
    elif data.startswith("del_"):
        item_cb = data.replace("del_", "")
        if user_id in user_orders and item_cb in user_orders[user_id]:
            del user_orders[user_id][item_cb]
        if not user_orders.get(user_id):
            await query.edit_message_text("Корзина пуста. /start")
            return
        await query.edit_message_text(
            "✅ Позиция удалена. Выберите товар:",
            reply_markup=edit_list_keyboard(user_id)
        )

    # ---------- НАЗАД К КОРЗИНЕ ----------
    elif data == "back_to_cart":
        await query.edit_message_text(
            format_cart(user_id),
            reply_markup=cart_keyboard(user_id)
        )

    # ---------- НАЗАД К СПИСКУ РЕДАКТИРОВАНИЯ ----------
    elif data == "back_to_edit_list":
        await query.edit_message_text(
            "Выберите товар для изменения:",
            reply_markup=edit_list_keyboard(user_id)
        )

    else:
        logger.warning(f"Неизвестный callback: {data}")

def main():
    app = Application.builder().token(BOT_TOKEN).request(request).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    print("Бот запущен...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
