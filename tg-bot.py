import os
import requests
import time
import telegram
import logging
import redis
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Filters, Updater
from telegram.ext import CallbackQueryHandler, CommandHandler, MessageHandler

DATABASE = None
MOLTIN_API_URL = 'https://api.moltin.com/v2'
MOLTIN_API_OAUTH_URL = 'https://api.moltin.com/oauth/access_token'

def get_access_token(client_id, client_secret, grant_type):
    data = {
      'client_id': client_id,
      'client_secret': client_secret,
      'grant_type': grant_type
    }
    response = requests.post(MOLTIN_API_OAUTH_URL, data=data)
    answer = response.json()
    
    access_token = answer['access_token']
    token_type = answer['token_type']
    authentication_token = '{} {}'.format(token_type, access_token)
    
    return authentication_token

def get_keyboard_with_product():
    response = requests.get('{}/products'.format(MOLTIN_API_URL), headers=headers)
    answer = response.json()
    products_data = answer['data']
    
    button_keyboard = list()
    keyboard = InlineKeyboardMarkup(button_keyboard)
    
    for product in products_data:
        product_name = product['name']
        product_id = product['id']
        button = [InlineKeyboardButton('{}'.format(product_name), callback_data='{}'.format(product_id))]
        button_keyboard.append(button)
        
    return keyboard

def get_product_picture_link(photo_id):
    response = requests.get('{}/files/{}'.format(MOLTIN_API_URL, photo_id), headers=headers)
    answer = response.json()
    picture_link = answer['data']['link']['href']
    
    return picture_link

def get_full_description_product(user_choice_product_id):
    response = requests.get('{}/products/{}'.format(MOLTIN_API_URL, user_choice_product_id), headers=headers)
    product = response.json()
    
    product_name = product['data']['name']
    product_description = product['data']['description']
    product_price = product['data']['meta']['display_price']['with_tax']['formatted']
    product_availability = product['data']['meta']['stock']['availability']
    product_availability_count = product['data']['meta']['stock']['level']
    photo_id = product['data']['relationships']['main_image']['data']['id']


    
    product_caption = '{}\n\nОписание:\n{}\n\nСтоимость в месяц: {},\n {}, количество: {}'.format(product_name, 
                                                                                   product_description,
                                                                                   product_price,
                                                                                   product_availability,
                                                                                   product_availability_count)
    
    product_picture_link = get_product_picture_link(photo_id)
    
    return product_caption, product_picture_link

def get_user_card(chat_id):
    description_card = ''
    button_keyboard = list()
    
    response = requests.get('{}/carts/{}/items'.format(MOLTIN_API_URL, chat_id), headers=headers)
    client_basket = response.json()
    pruducts_in_basket = client_basket['data']
        
    for product in pruducts_in_basket:
        product_id = product['id']
        product_name = product['name']
        product_quantity = product['quantity']
        product_description = product['description']
        product_price = product['meta']['display_price']['with_tax']['value']['formatted']

        product_description = 'Название продукта: {}\nКоличество: {}\nСтоимость: {}\n\n'.format(product_name, product_quantity, product_price)
        description_card += product_description
            
        button = [InlineKeyboardButton('Удалить {} из корзины'.format(product_name), callback_data='/delete,{}'.format(product_id))]
        button_keyboard.append(button)


    response = requests.get('{}/carts/{}/'.format(MOLTIN_API_URL, chat_id), headers=headers)
    answer = response.json()
    total_sum = answer['data']['meta']['display_price']['with_tax']['formatted']
    
    if total_sum != '0':
        description_card+='Общая стоимость: {}'.format(total_sum)
        button_keyboard.append([InlineKeyboardButton('{}'.format('Вернуться к списку продуктов'), callback_data='/back_to_list_products')])
        button_keyboard.append([InlineKeyboardButton('{}'.format('Перейти к оплате'), callback_data='/pay')])
    else:
        description_card+='Ваша корзина пуста'
        button_keyboard.append([InlineKeyboardButton('{}'.format('Вернуться к списку продуктов'), callback_data='/back_to_list_products')])
    keyboard = InlineKeyboardMarkup(button_keyboard)
    
    return description_card, keyboard

def get_user_state(user_reply, chat_id):
    reply_to_start = ['/start', '/back_to_list_products']
    reply_to_card = ['/card']
    replt_to_pay = ['/pay']
    
    if user_reply in reply_to_start:
        user_state = 'START'
    elif user_reply in reply_to_card:
        user_state = 'HANDLE_CARD'
    elif user_reply in replt_to_pay:
        user_state = 'WAITING_EMAIL'
    else:
        user_state = DATABASE.get(chat_id).decode("utf-8")
        if user_state == 'START':
            user_state = 'HANDLE_MENU'
            
    return user_state

def create_customer(chat_id, email):
    data = {'data': {
            'type': 'customer',
            'name': str(chat_id),
            'email': str(email)}}
            
    response = requests.post('{}/customers'.format(MOLTIN_API_URL), headers=headers, json=data)
    answer = response.json()
    
    return answer
            
def get_customer(customer_id):
    response = requests.get('{}/customers/{}'.format(MOLTIN_API_URL, customer_id), headers=headers)
    answer = response.json()
    
    return answer

def start(bot, update):
    keyboard = get_keyboard_with_product()
    if update.message:
        update.message.reply_text('Доступные услуги для заказа:', reply_markup=keyboard)
    elif update.callback_query:
        chat_id = update.callback_query.message.chat_id
        message_id = update.callback_query.message.message_id
        bot.delete_message(chat_id=chat_id, message_id = message_id)
        bot.send_message(text='Доступные услуги для заказа:', chat_id=chat_id, reply_markup=keyboard)
        
    return "HANDLE_MENU"

def handle_menu(bot, update):
    query = update.callback_query
    user_reply = update.callback_query.data
    chat_id = update.callback_query.message.chat_id
    message_id = update.callback_query.message.message_id
        
    product_caption, product_picture_link  = get_full_description_product(user_reply)
    
    button = [[InlineKeyboardButton("1 ядро", callback_data='{},1'.format(user_reply)),
                InlineKeyboardButton("2 ядра", callback_data='{},2'.format(user_reply)),
                InlineKeyboardButton("4 ядра", callback_data='{},4'.format(user_reply))],
             [InlineKeyboardButton('{}'.format('Назад'), callback_data='/back_to_list_products')],
             [InlineKeyboardButton('{}'.format('Корзина'), callback_data='/card')]]
    keyboard = InlineKeyboardMarkup(button)

    bot.delete_message(chat_id=chat_id, message_id = message_id)
    bot.send_photo(chat_id=chat_id, photo=product_picture_link, caption=product_caption, reply_markup=keyboard)
    
    return "HANDLE_DESCRIPTION"

def handle_description(bot, update):
    user_reply = update.callback_query.data
    user_reply = user_reply.split(',')
    product_id = user_reply[0]
    product_quantity = int(user_reply[1])
    chat_id = update.callback_query.message.chat_id

    data = {"data": {"id": "{}".format(product_id) ,"type":"cart_item","quantity": product_quantity}}

    response = requests.post('{}/carts/{}/items'.format(MOLTIN_API_URL, chat_id), headers=headers, json=data)
    message = 'Товар успешно добавлен в корзину. Для просмотра содержимого нажмите кнопку "Корзина" или добавьте еще один товар'
    bot.send_message(text=message, chat_id=chat_id)

    return "HANDLE_DESCRIPTION"

def handle_card(bot, update):
    chat_id = update.callback_query.message.chat_id
    user_reply = update.callback_query.data
    message_id = update.callback_query.message.message_id
    
    if user_reply == '/card':
        card_description, keyboard = get_user_card(chat_id)
        bot.delete_message(chat_id=chat_id, message_id = message_id)
        bot.send_message(text=card_description, chat_id=chat_id, reply_markup=keyboard)
        
        return "HANDLE_CARD"
    
    else:
        user_reply = user_reply.split(',')
        product_id = str(user_reply[1])
        response = requests.delete('{}/carts/{}/items/{}'.format(MOLTIN_API_URL, chat_id, product_id), headers=headers)
        
        card_description, keyboard = get_user_card(chat_id)
        bot.send_message(text=card_description, chat_id=chat_id, reply_markup=keyboard)
        
        return "HANDLE_CARD"
    
def waiting_email(bot, update):
    if update.message:
        user_reply = update.message.text
        chat_id = update.message.chat_id
        customer_data = create_customer(chat_id, user_reply)
        try:
            customer_data['errors'][0]['title'] == 'Failed Validation'
            update.message.reply_text('Введи электронную почту'.format(user_reply))
            
            return "WAITING_EMAIL"
        
        except:
            customer_id = customer_data['data']['id']
            customer_data = get_customer(customer_id)
            customer_email = customer_data['data']['email']
            update.message.reply_text('Ваш электронный ящик: {}. Мы вам скоро напишем. Для нового заказа введите команду /start'.format(user_reply))
        
            return "START"
        
    elif update.callback_query:
        user_reply = update.callback_query.data
        chat_id = update.callback_query.message.chat_id
        message = 'Введите свою электронную почту для связи'
        bot.send_message(text=message, chat_id=chat_id)
        
        return "WAITING_EMAIL"

def handle_users_reply(bot, update):
    DATABASE = get_database_connection()
    
    if update.message:
        user_reply = update.message.text
        chat_id = update.message.chat_id
    elif update.callback_query:
        user_reply = update.callback_query.data
        chat_id = update.callback_query.message.chat_id
    else:
        return
    
    user_state = get_user_state(user_reply, chat_id)
    
    states_functions = {
        'START': start,
        'HANDLE_MENU': handle_menu,
        'HANDLE_DESCRIPTION': handle_description,
        'HANDLE_CARD': handle_card,
        'WAITING_EMAIL': waiting_email
    }
    state_handler = states_functions[user_state]

    try:
        next_state = state_handler(bot, update)
        DATABASE.set(chat_id, next_state)
    except Exception as err:
        print(err)

def get_database_connection():
    global DATABASE
    if DATABASE is None:
        database_password = os.environ['REDIS_PASSWORD']
        database_host = os.environ['REDIS_HOST']
        database_port = os.environ['REDIS_PORT']
        DATABASE = redis.Redis(host=database_host, port=database_port, password=database_password)
    return DATABASE

if __name__ == '__main__':
    client_id_moltin = os.environ['CLIENT_ID_MOLTIN']
    client_secret_moltin = os.environ['CLIENT_SECRET_MOLTIN']
    grant_type_moltin = 'client_credentials'
    authentication_token = get_access_token(client_id_moltin, client_secret_moltin, grant_type_moltin)        
    headers = {'Authorization': authentication_token}        
            
    telegram_token = os.environ['TELEGRAM_TOKEN']
    updater = Updater(telegram_token)
    dispatcher = updater.dispatcher
    dispatcher.add_handler(CallbackQueryHandler(handle_users_reply))
    dispatcher.add_handler(MessageHandler(Filters.text, handle_users_reply))
    dispatcher.add_handler(CommandHandler('start', handle_users_reply))
    updater.start_polling()
    updater.idle()
