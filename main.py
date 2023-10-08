from __future__ import print_function
import os

import os.path
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackQueryHandler, ConversationHandler
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

ENTER_NAME, ENTER_PHONE, ENTER_SEX, ENTER_UNI, ENTER_COURSE, ENTER_VISITED, ENTER_HOW_COME, ENTER_ENGLISH_LEVEL, ENTER_RELIGIOUS, EXIT_CONVERSATION = range(10)


class Student:
    def __init__(self):
        self.name = '-'
        self.phone = '-'
        self.nickname = '-'
        self.sex = '-'
        self.uni = '-'
        self.course = '-'
        self.id = '-'
        self.visited = '-'
        self.how_come = '-'
        self.english_level = '-'

    def to_str(self):
        return self.id + ', ' + self.name + ', ' + self.phone + ', ' + self.nickname + ', ' + self.sex + ', ' + self.uni + ', ' + self.course + ', ' + self.visited + ', ' + self.how_come + ', ' + self.english_level


user = Student()


def print_jobs(update, context):
    if update.message.chat_id != int(read_config('ADMIN_ID')):
        context.bot.send_message(chat_id=update.message.chat_id, text='This command is for admin only')
        return
    text = '{:d} jobs active:\n'.format(len(context.job_queue.jobs()))
    for i in range(len(context.job_queue.jobs())):
        text += context.job_queue.jobs()[i].name + ';\n'
    context.bot.send_message(chat_id=update.message.chat_id, text=text)


def read_config(value) -> str:
    file = open('config.txt', encoding='UTF-8')
    lines = file.readlines()
    for line in lines:
        if line.split(" = ")[0] == value:
            result_lines = line.split(" = ")[1].strip().split('\\n')
            result = ''
            for result_line in result_lines:
                result += result_line + '\n'
            return result[:len(result) - 1]
    return ''


def add_to_spreadsheets(data: str):
    creds = None
    scopes = [read_config("SCOPES")]
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', scopes)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials.json', scopes)
            creds = flow.run_local_server(port=0)
        with open('token.json', 'w') as token:
            token.write(creds.to_json())

    try:
        service = build('sheets', 'v4', credentials=creds)
        sheet = service.spreadsheets()
        values = data.split(', ')
        students = sheet.values().get(spreadsheetId=read_config("SAMPLE_SPREADSHEET_ID"),
                                      range=read_config("SAMPLE_RANGE_NAME")).execute()
        data_range = 'A{0}:J{0}'.format(str(len(students.get('values', [])) + 1))
        range_body_values = {
            'value_input_option': 'USER_ENTERED',
            'data': [
                {
                    'majorDimension': 'ROWS',
                    'range': data_range,
                    'values': [
                        [values[0], values[1], values[2], values[3], values[4], values[5], values[6], values[7], values[8], values[9]]
                    ]
                },
            ]}
        service.spreadsheets().values().batchUpdate(spreadsheetId=read_config("SAMPLE_SPREADSHEET_ID"), body=range_body_values).execute()
    except HttpError as err:
        print(err)


def link_to_spreadsheets(update, context):
    link = 'https://docs.google.com/spreadsheets/d/%s' % read_config('SAMPLE_SPREADSHEET_ID')
    context.bot.send_message(chat_id=update.message.chat_id, text=link)


def build_menu(button_names):
    buttons = []
    for i in range(len(button_names)):
        buttons.append([])
        for element in button_names[i]:
            buttons[i].append(InlineKeyboardButton(text=element, callback_data=element))
    return buttons


def stop_messaging_in_church_chat(update, context):
    if update.message.chat_id != int(read_config('ADMIN_ID')):
        return
    jobs_to_delete = context.job_queue.get_jobs_by_name(read_config('CHURCH_CHAT_ID'))
    for i in range(len(jobs_to_delete)):
        jobs_to_delete[i].schedule_removal()


def get_chat_id(update, context):
    if update.message.chat_id != int(read_config('ADMIN_ID')):
        return
    context.bot.send_message(chat_id=update.message.chat_id, text=str(update.message.chat_id))


def start_command(update, context):
    keyboard = [[KeyboardButton('Зареєструватись🙌')]]
    context.bot.send_message(chat_id=update.message.chat_id, text=read_config('INTRODUCTION_TEXT'),
                             reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True))


def message_handler(update, context):
    match update.message.text:
        case 'get_id':
            context.bot.send_message(chat_id=update.message.chat_id, text=str(update.message.chat_id))


def register(update, context):
    keyboard = [[KeyboardButton('Yes!')]]
    context.bot.send_message(chat_id=update.message.chat_id, text=read_config('REGISTER_TEXT'),
                             reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True))
    user.id = str(update.message.chat_id)
    return ENTER_NAME


def ask_name(update, context):
    user.nickname = update.message.from_user.username
    update.message.reply_text('Окей, тоді почнемо. Напиши своє прізвище та ім’я у форматі “Ім`я Прізвище”')
    return ENTER_PHONE


def ask_phone(update, context):
    name = update.message.text.split()
    if len(name) < 2 or (not (name[0].isalpha() and name[1].isalpha())):
        return ask_name(update, context)
    user.name = update.message.text
    update.message.reply_text('Номер телефону у форматі "380938351301"')
    return ENTER_SEX


def ask_sex(update, context):
    phone = update.message.text
    if not (len(phone) == 12 and phone.isdigit()):
        return ask_phone(update, context)
    user.phone = phone
    keyboard = [[KeyboardButton('Чол')], [KeyboardButton('Жін')]]
    context.bot.send_message(chat_id=update.message.chat_id, text="Стать",
                             reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True))
    return ENTER_UNI


def ask_uni(update, context):
    sex = update.message.text
    if sex != 'Чол' and sex != 'Жін':
        return ask_sex(update, context)
    user.sex = sex
    keyboard = [[KeyboardButton('Національний Університет "Львівська Політехніка"')],
                [KeyboardButton('Львівський Національний Університет ім. І.Франка')],
                [KeyboardButton('Національний Лісотехнічний Університет України')],
                [KeyboardButton('Львівський державний університет внутрішніх справ МВС України')],
                [KeyboardButton('Національний Університет Ветеринарної медицини та біотехнологій ім. С.Ґжицького')],
                [KeyboardButton('Українська Академія Друкарства')],
                ]
    context.bot.send_message(chat_id=update.message.chat_id,
                             text="Оберіть свій універ. Якщо вашого навчального закладу немає у списку - впишіть його вручну",
                             reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True))
    return ENTER_COURSE


def ask_course(update, context):
    user.uni = update.message.text
    keyboard = [[KeyboardButton('1')], [KeyboardButton('2')], [KeyboardButton('3')],
                [KeyboardButton('4')], [KeyboardButton('5')], [KeyboardButton('6')]]
    context.bot.send_message(chat_id=update.message.chat_id, text="курс",
                             reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True))
    return ENTER_VISITED


def ask_visited(update, context):
    course = update.message.text
    if not course.isdigit():
        return ask_course(update, context)
    user.course = course
    user.course = update.message.text
    keyboard = [[KeyboardButton('Так')], [KeyboardButton('НІ')]]
    context.bot.send_message(chat_id=update.message.chat_id, text="чи відвідував поекти?",
                             reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True))
    return ENTER_HOW_COME


def ask_how_come(update, context):
    user.visited = update.message.text
    keyboard = [[KeyboardButton('Флаєр')], [KeyboardButton('Постер')], [KeyboardButton('Друзі запросили')],
                [KeyboardButton('Реклама Instagram')], [KeyboardButton('Реклама Telegram')]]
    context.bot.send_message(chat_id=update.message.chat_id, text="як дізнався про ак?",
                             reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True))
    return ENTER_ENGLISH_LEVEL


def ask_english_level(update, context):
    user.how_come = update.message.text
    keyboard = [[KeyboardButton('повний нуль 🙂')],
                [KeyboardButton('щось розумію, сказати нічого не зможу')],
                [KeyboardButton('можу скласти кілька речень на загальні теми')],
                [KeyboardButton('можу вести діалог, але слово consciousness буду гуглити')],
                [KeyboardButton('дивлюсь серіали англійською без субтитрів')],
                [KeyboardButton('англійська майже як рідна')]]
    context.bot.send_message(chat_id=update.message.chat_id, text="Який рівень англ?",
                             reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True))
    return ENTER_RELIGIOUS


def ask_religious(update, context):
    user.how_come = update.message.text
    keyboard = [[KeyboardButton('Позитивно')],
                [KeyboardButton('Негативно')],
                [KeyboardButton('Нейтрально')],]
    context.bot.send_message(chat_id=update.message.chat_id, text="Який рівень англ?",
                             reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True))
    return EXIT_CONVERSATION


def exit_conversation(update, context):
    user.english_level = update.message.text
    update.message.reply_text(user.to_str())
    add_to_spreadsheets(user.to_str())
    return ConversationHandler.END


def main():
    print("start")
    updater = Updater(read_config("BOT_TOKEN"), use_context=True)
    dispatcher = updater.dispatcher
    dispatcher.add_handler(CommandHandler('start', start_command))
    dispatcher.add_handler(CommandHandler('print_jobs', print_jobs))
    dispatcher.add_handler(CommandHandler('link_to_spreadsheets', link_to_spreadsheets))
    # dispatcher.add_handler(MessageHandler(Filters.text, message_handler))
    conversation_handler = ConversationHandler(
        entry_points=[MessageHandler(Filters.text('Зареєструватись🙌'), register)],
        states={
            ENTER_NAME: [MessageHandler(Filters.all, ask_name)],
            ENTER_PHONE: [MessageHandler(Filters.all, ask_phone)],
            ENTER_SEX: [MessageHandler(Filters.all, ask_sex)],
            ENTER_UNI: [MessageHandler(Filters.all, ask_uni)],
            ENTER_COURSE: [MessageHandler(Filters.all, ask_course)],
            ENTER_VISITED: [MessageHandler(Filters.all, ask_visited)],
            ENTER_HOW_COME: [MessageHandler(Filters.all, ask_how_come)],
            ENTER_ENGLISH_LEVEL: [MessageHandler(Filters.all, ask_english_level)],
            ENTER_RELIGIOUS: [MessageHandler(Filters.all, ask_religious)],
            EXIT_CONVERSATION: [MessageHandler(Filters.all, exit_conversation)]
        },
        fallbacks=[CommandHandler('start', exit_conversation)]
    )
    dispatcher.add_handler(conversation_handler)
    updater.start_polling()
    updater.idle()


if __name__ == '__main__':
    main()
