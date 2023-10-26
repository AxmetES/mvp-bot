import logging
import redis
from io import BytesIO

import requests
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from telegram.ext import Filters, Updater
from telegram.ext import CallbackQueryHandler, CommandHandler, MessageHandler

from config import settings
import handlers

_database = None


logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    filename='fish_bot.log'
)
logger = logging.getLogger(__name__)


def start(update, context):
    if update.message:
        chat_id = str(update.message.chat.id)
    return "HANDLE_MENU"


def echo(update, context):
    """
    Хэндлер для состояния ECHO.

    Бот отвечает пользователю тем же, что пользователь ему написал.
    Оставляет пользователя в состоянии ECHO.
    """
    users_reply = update.message.text
    update.message.reply_text(users_reply)
    return "ECHO"


def handle_menu(update, context):
    if update.message:
        chat_id = update.message.chat.id
        message_id = update.message.message_id
    else:
        chat_id = update.callback_query.message.chat.id
        message_id = update.callback_query.message.message_id

    products = handlers.get_products()

    keyboard = [
        [
            InlineKeyboardButton(
                products["data"][x]["attributes"]["title"],
                callback_data=products["data"][x]["id"],
            )
        ]
        for x in range(len(products["data"]))
    ]
    keyboard.append([InlineKeyboardButton("Моя корзина  🛒", callback_data="/go_cart")])
    reply_markup = InlineKeyboardMarkup(keyboard)

    context.bot.delete_message(chat_id=chat_id, message_id=message_id)

    if update.message:
        update.message.reply_text("Please choose:", reply_markup=reply_markup)
    else:
        context.bot.send_message(
            chat_id=chat_id, text="Please choose:", reply_markup=reply_markup
        )

    return "HANDLE_DESCRIPTION"


def handle_description(update, context):
    query = update.callback_query.data
    chat_id = update.callback_query.message.chat.id
    message_id = update.callback_query.message.message_id
    pic = handlers.get_picture(query)
    pic_url = pic["data"]["attributes"]["picture"]["data"][0]["attributes"]["formats"][
        "small"
    ]["url"]
    response = handlers.get_api_handler("get", pic_url)
    image_data = BytesIO(response.content)

    product = handlers.get_product(query)
    title = product["data"]["attributes"]["title"]
    price = product["data"]["attributes"]["price"]
    description = product["data"]["attributes"]["description"]

    keyboard = [
        [InlineKeyboardButton("Добавить в корзину", callback_data=f"{query}")],
        [InlineKeyboardButton("Моя корзина  🛒", callback_data="/go_cart")],
        [InlineKeyboardButton("Назад", callback_data="/back_to_menu")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    context.bot.delete_message(chat_id=chat_id, message_id=message_id)

    context.bot.send_photo(
        chat_id=chat_id,
        photo=image_data,
        caption=f"{title} ({price} руб.):\n\n{description}",
        reply_markup=reply_markup,
    )

    return "HANDLE_ADD_TO_CART"


def handle_add_to_cart(update, context):
    query = update.callback_query
    chat_id = update.callback_query.message.chat_id
    data = query.data
    message_id = update.callback_query.message.message_id

    order = handlers.create_order(data)
    cart = handlers.get_or_create_cart(str(chat_id), order)

    keyboard = [
        [InlineKeyboardButton("Моя корзина  🛒", callback_data="/go_cart")],
        [InlineKeyboardButton("Назад", callback_data="/back_to_menu")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    context.bot.delete_message(chat_id=chat_id, message_id=message_id)
    context.bot.send_message(
        chat_id=chat_id, text="Please choose:", reply_markup=reply_markup
    )
    return "HANDLE_MENU"


def handle_cart(update, context):
    chat_id = update.callback_query.message.chat_id
    message_id = update.callback_query.message.message_id

    orders = handlers.get_orders(chat_id)
    message = ""
    for order in orders:
        message += "".join(
            f"""{order['attributes']['product']['data']['attributes']['title']}\n"""
            + f"""цена: {order['attributes']['product']['data']['attributes']['price']}\n"""
            + f"""вес: {order['attributes']['weight']}\n\n"""
        )
    keyboard = [
        [InlineKeyboardButton("В меню", callback_data="/back_to_menu")],
        [InlineKeyboardButton("Оплатить", callback_data="/pay")],
        [InlineKeyboardButton("Отказ от товаров", callback_data="/del_products")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    context.bot.delete_message(chat_id=chat_id, message_id=message_id)
    context.bot.send_message(
        chat_id=chat_id,
        text=message if message else "Корзина пуста",
        reply_markup=reply_markup,
    )
    return "HANDLE_MENU"


def handle_empty_cart(update, context):
    chat_id = update.callback_query.message.chat_id
    message_id = update.callback_query.message.message_id

    orders = handlers.get_orders(chat_id)
    for order in orders:
        handlers.del_order(order["id"])
    keyboard = [
        [InlineKeyboardButton("В меню", callback_data="/back_to_menu")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    context.bot.delete_message(chat_id=chat_id, message_id=message_id)
    context.bot.send_message(
        chat_id=chat_id,
        text="Корзина пуста",
        reply_markup=reply_markup,
    )
    return "HANDLE_MENU"


def handle_pay(update, context):
    chat_id = update.callback_query.message.chat_id
    message_id = update.callback_query.message.message_id
    context.bot.delete_message(chat_id=chat_id, message_id=message_id)
    context.bot.send_message(chat_id=chat_id, text="Отправьте свою почту для оплаты.")
    return "WAITING_EMAIL"


def handle_email(update, context):
    try:
        chat_id = str(update.message.chat_id)
        message_id = update.message.message_id
        username = update.effective_user.username
        context.bot.delete_message(chat_id=chat_id, message_id=message_id)
        users_reply = update.message.text
        cart = handlers.add_user_to_cart(chat_id, users_reply, username)
        update.message.reply_text("Пользователь сохранен в CMS.")
    except Exception as err:
        update.message.reply_text("something wrong.")
    finally:
        return "HANDLE_MENU"


def handle_users_reply(update, context):
    db = get_database_connection()
    if update.message:
        user_reply = update.message.text
        chat_id = str(update.message.chat_id)
    elif update.callback_query:
        user_reply = update.callback_query.data
        chat_id = str(update.callback_query.message.chat_id)
    else:
        return
    if user_reply == "/start" or user_reply == "/back_to_menu":
        user_state = "HANDLE_MENU"
        # user_state = 'START'
    elif user_reply == "/go_cart":
        user_state = "HANDLE_CART"
    elif user_reply == "/del_products":
        user_state = "HANDLE_EMPTY_CART"
    elif user_reply == "/pay":
        user_state = "HANDLE_PAY"
    else:
        user_state = db.get(chat_id).decode("utf-8")

    states_functions = {
        "START": start,
        "ECHO": echo,
        "HANDLE_MENU": handle_menu,
        "HANDLE_DESCRIPTION": handle_description,
        "HANDLE_ADD_TO_CART": handle_add_to_cart,
        "HANDLE_CART": handle_cart,
        "HANDLE_EMPTY_CART": handle_empty_cart,
        "HANDLE_PAY": handle_pay,
        "WAITING_EMAIL": handle_email,
    }
    state_handler = states_functions[user_state]
    try:
        next_state = state_handler(update, context)
        db.set(chat_id, next_state)
    except Exception as err:
        logger.exception(err)


def get_database_connection():
    """
    Возвращает конекшн с базой данных Redis, либо создаёт новый, если он ещё не создан.
    """
    global _database
    if _database is None:
        database_host = settings.DATABASE_HOST
        database_port = settings.DATABASE_PORT
        database_password = settings.DATABASE_PASSWORD
        _database = redis.Redis(
            host=database_host, port=database_port, password=database_password
        )
    return _database


if __name__ == "__main__":
    updater = Updater(settings.BOT_TOKEN)
    dispatcher = updater.dispatcher
    dispatcher.add_handler(CallbackQueryHandler(handle_users_reply))
    dispatcher.add_handler(MessageHandler(Filters.text, handle_users_reply))
    dispatcher.add_handler(CommandHandler("start", handle_users_reply))
    updater.start_polling()
    updater.idle()
