import os
import logging
import ibm_watson
from functools import wraps
from dotenv import load_dotenv
from telegram.ext import CommandHandler
from telegram.ext import MessageHandler, Filters
from telegram.ext import Updater
from telegram import ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.chataction import ChatAction
from ibm_cloud_sdk_core.authenticators import IAMAuthenticator
from ibm_cloud_sdk_core.api_exception import ApiException

load_dotenv()
assistant_id = os.getenv('ASSISTANT_ID')
apikey = os.getenv('APIKEY')

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)
logger = logging.getLogger()
logger.setLevel(logging.DEBUG)

authenticator = IAMAuthenticator(apikey)
service = ibm_watson.AssistantV2(
    version='2019-02-28',
    authenticator=authenticator)

service.set_service_url(os.getenv('URL'))

session_ids = {}

updater = Updater(token=os.getenv('TOKEN'), use_context=True)
dispatcher = updater.dispatcher


def send_action(action):
    def decorator(func):
        @wraps(func)
        def command_func(update, context, *args, **kwargs):
            context.bot.send_chat_action(chat_id=update.effective_message.chat_id, action=action)
            return func(update, context, *args, **kwargs)

        return command_func

    return decorator


def new_session(user_id):
    assistant_session_id = service.create_session(
        assistant_id=assistant_id
    ).get_result()['session_id']
    session_ids[user_id] = assistant_session_id


@send_action(ChatAction.TYPING)
def start(update, context):
    user_id = update.message.from_user.id
    new_session(user_id)
    response = service.message(
        assistant_id,
        session_ids[user_id]
    ).get_result()
    reply_text = ''
    try:
        reply_text = response['output']['generic'][0]['text']
    except IndexError:
        reply_text = 'Watson Assistant is unavailable now :('
    reply_markup = ReplyKeyboardRemove()
    context.bot.send_message(chat_id=update.effective_chat.id, text=reply_text, reply_markup=reply_markup)
    context.bot.send_message(chat_id=update.effective_chat.id, text='Помощь: /help')


@send_action(ChatAction.TYPING)
def help_user(update, context):
    help_message = """
    Команды бота:
    Помощь: /help
    Начало диалога: /start\n
    
    После отправки команды /start создается новая сессия с Watson Assistant.
    """
    context.bot.send_message(chat_id=update.effective_chat.id, text=help_message)


@send_action(ChatAction.TYPING)
def wa_reply(update, context):
    user_id = update.message.from_user.id
    if user_id not in session_ids:
        new_session(user_id)
    try:
        response = service.message(
            assistant_id,
            session_ids[user_id],
            input={'text': update.message.text}
        ).get_result()
    except ApiException:
        new_session(user_id)
        response = service.message(assistant_id, session_ids[user_id], input={'text': update.message.text}).get_result()

    logger.debug(response)
    reply_text = ''
    labels = []
    button_list = []
    try:
        for response_part in response['output']['generic']:
            if response_part['response_type'] == 'text':
                reply_text += response_part['text'] + '\n'
            elif response_part['response_type'] == 'option':
                reply_text += response_part['title']
                labels = [option['label'] for option in response_part['options']]

        button_list = [[s] for s in labels]
    except IndexError:
        reply_text = 'Watson Assistant is unavailable now :('
    except KeyError:
        reply_text = 'Ошибка обработки текста'

    if len(button_list) > 0:
        reply_markup = ReplyKeyboardMarkup(button_list)
    else:
        reply_markup = ReplyKeyboardRemove()
    context.bot.send_message(chat_id=update.effective_chat.id, text=reply_text, reply_markup=reply_markup)


def unknown(update, context):
    context.bot.send_message(chat_id=update.effective_chat.id, text="Sorry, I didn't understand that command.")


start_handler = CommandHandler('start', start)
dispatcher.add_handler(start_handler)

help_handler = CommandHandler('help', help_user)
dispatcher.add_handler(help_handler)

unknown_handler = MessageHandler(Filters.command, unknown)
dispatcher.add_handler(unknown_handler)

message_handler = MessageHandler(Filters.text, wa_reply)
dispatcher.add_handler(message_handler)

updater.start_polling()
