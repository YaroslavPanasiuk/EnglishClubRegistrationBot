from __future__ import print_function

import asyncio
import collections
import os
import os.path
import random
import time
import traceback
import pandas as pd

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup, ParseMode
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackQueryHandler, ConversationHandler
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

ENTER_NAME, ENTER_PHONE, ENTER_SEX, ENTER_UNI, ENTER_COURSE, ENTER_VISITED, SPECIFY_VISITED, ENTER_HOW_COME, ENTER_ENGLISH_LEVEL, ENTER_RELIGIOUS, EXIT_CONVERSATION = range(
    11)


class Student:
    def __init__(self, values: []):
        self.id = values[0]
        self.nickname = values[1]
        self.name = values[2]
        self.phone = values[3]
        self.sex = values[4]
        self.uni = values[5]
        self.course = values[6]
        self.visited = values[7]
        self.how_come = values[8]
        self.english_level = values[9]
        self.religious = values[10]


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


def connect_to_spreadsheets():
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
    return creds


def add_to_spreadsheets(data: []):
    try:
        service = build('sheets', 'v4', credentials=connect_to_spreadsheets())
        sheet = service.spreadsheets()
        students = sheet.values().get(spreadsheetId=read_config("SAMPLE_SPREADSHEET_ID"),
                                      range=read_config("SAMPLE_RANGE_NAME")).execute()
        data_range = 'A{0}:K{0}'.format(str(len(students.get('values', [])) + 1))
        range_body_values = {
            'value_input_option': 'USER_ENTERED',
            'data': [
                {
                    'majorDimension': 'ROWS',
                    'range': data_range,
                    'values': [data]
                },
            ]}
        service.spreadsheets().values().batchUpdate(spreadsheetId=read_config("SAMPLE_SPREADSHEET_ID"),
                                                    body=range_body_values).execute()
    except HttpError as err:
        print(err)


def get_questions():
    try:
        service = build('sheets', 'v4', credentials=connect_to_spreadsheets())
        sheet = service.spreadsheets()
        questions = sheet.values().get(spreadsheetId=read_config("SAMPLE_SPREADSHEET_ID"),
                                       range='Питання!B2:B30').execute()
        values = questions.get('values', [])

        if not values:
            print('No data found.')
            return
        result = []
        for value in values:
            result.append(value[0])
        return result

    except HttpError as err:
        print(err)


def available_tutor_times():
    try:
        service = build('sheets', 'v4', credentials=connect_to_spreadsheets())
        sheet = service.spreadsheets()
        questions = sheet.values().get(spreadsheetId=read_config("SAMPLE_SPREADSHEET_ID"),
                                       range='Tutor time!A1:H60').execute()
        values = questions.get('values', [])

        if not values:
            print('No data found.')
            return
        for i in range(len(values)):
            if len(values[i]) > 0 and i > 0 and values[i][0] == '':
                values[i][0] = values[i - 1][0]
        df = pd.DataFrame(values)
        df.columns = df.iloc[0]
        df = df[1:]
        mask = ((df['Student'] == '') | (df['Student'].isna())) & (df['Date and time'] != '') & (df['Date and time'].notna())
        return list(collections.OrderedDict.fromkeys(df.loc[mask, 'Date and time']))

    except HttpError as err:
        print(err)


def find_student(telegram_id):
    try:
        service = build('sheets', 'v4', credentials=connect_to_spreadsheets())
        sheet = service.spreadsheets()
        questions = sheet.values().get(spreadsheetId=read_config("SAMPLE_SPREADSHEET_ID"),
                                       range='Реєстрація!A1:K500').execute()
        values = questions.get('values', [])

        if not values:
            print('No data found.')
            return
        df = pd.DataFrame(values)
        df.columns = df.iloc[0]
        df = df[1:]
        return Student(df.loc[df['id'] == str(telegram_id)].values.flatten().tolist())

    except HttpError as err:
        print(err)


def when_student_has_tutor_time(student: Student):
    try:
        service = build('sheets', 'v4', credentials=connect_to_spreadsheets())
        sheet = service.spreadsheets()
        questions = sheet.values().get(spreadsheetId=read_config("SAMPLE_SPREADSHEET_ID"),
                                       range='Tutor time!A1:G60').execute()
        values = questions.get('values', [])
        if not values:
            print('No data found.')
            return
        for i in range(len(values)):
            if len(values[i]) == 0:
                continue
            if values[i][0] == '' and i > 0:
                values[i][0] = values[i-1][0]
        df = pd.DataFrame(values)
        df.columns = df.iloc[0]
        df = df[1:]
        mask = ((df['Student'] == student.name) & (df["Student's phone number "] == student.phone) &
                (df['telegram'] == student.nickname))
        if len(df.loc[mask, "Date and time"]) == 0:
            return ''
        return str(df.loc[mask.idxmax(), "Date and time"])

    except HttpError as err:
        print(err)


def add_student_to_tutor_time(student: Student, time: str):
    try:
        service = build('sheets', 'v4', credentials=connect_to_spreadsheets())
        sheet = service.spreadsheets()
        questions = sheet.values().get(spreadsheetId=read_config("SAMPLE_SPREADSHEET_ID"),
                                       range='Tutor time!A1:G60').execute()
        values = questions.get('values', [])
        if not values:
            print('No data found.')
            return
        for i in range(len(values)):
            if len(values[i]) > 0 and i > 0 and values[i][0] == '':
                values[i][0] = values[i - 1][0]
        df = pd.DataFrame(values)
        df.columns = df.iloc[0]
        df = df[1:]
        mask = (df['Date and time'] == time) & (df['Student'].isna())
        df.loc[mask.idxmax(), ['Student', "Student's phone number ", 'telegram']] = [student.name, student.phone, student.nickname]
        range_body_values = {
            'value_input_option': 'USER_ENTERED',
            'data': [
                {
                    'majorDimension': 'ROWS',
                    'range': 'Tutor time!E2:G60',
                    'values': df[['Student', "Student's phone number ", 'telegram']].values.tolist()
                },
            ]}
        service.spreadsheets().values().batchUpdate(spreadsheetId=read_config("SAMPLE_SPREADSHEET_ID"),
                                                    body=range_body_values).execute()

    except HttpError as err:
        print(err)


INTRODUCTION_TEXT, REGISTRATION_TEXT, ASK_NAME_TEXT, ASK_PHONE_TEXT, ASK_SEX_TEXT, ASK_UNI_TEXT, ASK_COURSE_TEXT, ASK_VISITED_TEXT, SPECIFY_VISITED_TEXT, ASK_HOW_COME_TEXT, ASK_ENGLISH_LEVEL_TEXT, ASK_RELIGIOUS_TEXT, END_REGISTRATION_TEXT, LOCATION_TEXT, SCHEDULE_TEXT, INTERVIEW_TEXT, TUTOR_TIME_TEXT, ABOUT_US_TEXT, CONNECT_TEXT, INVALID_REGISTRATION_TEXT, TUTOR_TIME_REGISTRATION_TEXT, TUTOR_TIME_REGISTERED_TEXT, INVALID_TUTOR_TIME_REGISTRATION_TEXT = get_questions()


def get_chats():
    try:
        service = build('sheets', 'v4', credentials=connect_to_spreadsheets())
        sheet = service.spreadsheets()
        questions = sheet.values().get(spreadsheetId=read_config("SAMPLE_SPREADSHEET_ID"),
                                       range='Реєстрація!A2:A1000').execute()
        values = questions.get('values', [])

        if not values:
            print('No data found.')
            return
        result = []
        for value in values:
            result.append(value[0])
        return set(result)

    except HttpError as err:
        print(err)


def start_command(update, context):
    keyboard = [[KeyboardButton('Зареєструватись🙌')]]
    context.bot.send_message(chat_id=update.message.chat_id, text=INTRODUCTION_TEXT,
                             reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True))


def register(update, context):
    if get_chats().__contains__(str(update.message.chat_id)):
        context.bot.send_message(chat_id=update.message.chat_id, text=INVALID_REGISTRATION_TEXT)
        return ConversationHandler.END
    keyboard = [[KeyboardButton('Так!')]]
    context.bot.send_message(chat_id=update.message.chat_id, text=REGISTRATION_TEXT,
                             reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True))
    context.user_data['id'] = str(update.message.chat_id)
    return ENTER_NAME


def ask_name(update, context):
    context.user_data['nickname'] = update.message.from_user.username
    update.message.reply_text(ASK_NAME_TEXT)
    return ENTER_PHONE


def ask_phone(update, context):
    if context.user_data.get('name') is None:
        name = update.message.text.split()
        if len(name) < 2:
            return ask_name(update, context)
        context.user_data['name'] = update.message.text
    update.message.reply_text(ASK_PHONE_TEXT)
    return ENTER_SEX


def ask_sex(update, context):
    if context.user_data.get('phone') is None:
        phone = update.message.text
        if not (len(phone) == 12 and phone.isdigit()):
            return ask_phone(update, context)
        context.user_data['phone'] = phone
    keyboard = [[KeyboardButton('Чол'), KeyboardButton('Жін')]]
    context.bot.send_message(chat_id=update.message.chat_id, text=ASK_SEX_TEXT,
                             reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True))
    return ENTER_UNI


def ask_uni(update, context):
    sex = update.message.text
    if sex != 'Чол' and sex != 'Жін':
        return ask_sex(update, context)
    context.user_data['sex'] = sex
    keyboard = [[KeyboardButton('Національний Університет "Львівська Політехніка"')],
                [KeyboardButton('Львівський Національний Університет ім. І.Франка')],
                [KeyboardButton('Національний Лісотехнічний Університет України')],
                [KeyboardButton('Львівський державний університет внутрішніх справ МВС України')],
                [KeyboardButton('Національний Університет Ветеринарної медицини та біотехнологій ім. С.Ґжицького')],
                [KeyboardButton('Українська Академія Друкарства')],
                ]
    context.bot.send_message(chat_id=update.message.chat_id,
                             text=ASK_UNI_TEXT,
                             reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True))
    return ENTER_COURSE


def ask_course(update, context):
    context.user_data['uni'] = update.message.text
    keyboard = [[KeyboardButton('1'), KeyboardButton('2'), KeyboardButton('3')],
                [KeyboardButton('4'), KeyboardButton('5'), KeyboardButton('6')],
                [KeyboardButton('Закінчив'), KeyboardButton('Школяр')]]
    context.bot.send_message(chat_id=update.message.chat_id, text=ASK_COURSE_TEXT,
                             reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True))
    return ENTER_VISITED


def ask_visited(update, context):
    context.user_data['course'] = update.message.text
    keyboard = [[KeyboardButton('Так'), KeyboardButton('НІ')]]
    context.bot.send_message(chat_id=update.message.chat_id, text=ASK_VISITED_TEXT,
                             reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True))
    return SPECIFY_VISITED


def specify_visited(update, context):
    context.user_data['visited'] = update.message.text
    if not (context.user_data['visited'] == 'Так'):
        return ask_how_come(update, context)
    context.bot.send_message(chat_id=update.message.chat_id, text=SPECIFY_VISITED_TEXT)
    return ENTER_HOW_COME


def ask_how_come(update, context):
    if context.user_data['visited'] == 'Так':
        context.user_data['visited'] = update.message.text
    keyboard = [[KeyboardButton('Флаєр')], [KeyboardButton('Постер')], [KeyboardButton('Друзі запросили')],
                [KeyboardButton('Реклама Instagram')], [KeyboardButton('Реклама Telegram')]]
    context.bot.send_message(chat_id=update.message.chat_id, text=ASK_HOW_COME_TEXT,
                             reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True))
    return ENTER_ENGLISH_LEVEL


def ask_english_level(update, context):
    context.user_data['how_come'] = update.message.text
    keyboard = [[KeyboardButton('повний нуль 🙂')],
                [KeyboardButton('щось розумію, сказати нічого не зможу')],
                [KeyboardButton('можу скласти кілька речень на загальні теми')],
                [KeyboardButton('можу вести діалог, але слово consciousness буду гуглити')],
                [KeyboardButton('дивлюсь серіали англійською без субтитрів')],
                [KeyboardButton('англійська майже як рідна')]]
    context.bot.send_message(chat_id=update.message.chat_id, text=ASK_ENGLISH_LEVEL_TEXT,
                             reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True))
    return ENTER_RELIGIOUS


def ask_religious(update, context):
    context.user_data['english_level'] = update.message.text
    keyboard = [[KeyboardButton('Позитивно')],
                [KeyboardButton('Негативно')],
                [KeyboardButton('Нейтрально')], ]
    context.bot.send_message(chat_id=update.message.chat_id, text=ASK_RELIGIOUS_TEXT,
                             reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True))
    return EXIT_CONVERSATION


def exit_conversation(update, context):
    context.user_data['religious'] = update.message.text
    update.message.reply_text(END_REGISTRATION_TEXT)
    add_to_spreadsheets(list(context.user_data.values()))
    show_menu(update, context)
    return ConversationHandler.END


def spam_message(update, context):
    if update.message.chat_id != int(read_config('ADMIN_ID')) and update.message.chat_id != int(
            read_config('COADMIN_ID')):
        return ConversationHandler.END
    chats = get_chats()
    context.bot.send_message(chat_id=update.message.chat_id,
                             text='Введіть повідомлення для розсилки {n} людям {chats}'.format(n=len(chats),
                                                                                               chats=chats))
    return 0


def ask_spam_message_text(update, context):
    chats = get_chats()
    print(chats)
    try:
        for chat in chats:
            context.bot.send_message(chat_id=int(chat), text=update.message.text)
            time.sleep(1)
        context.bot.send_message(chat_id=update.message.chat_id, text='sent')
    except:
        context.bot.send_message(chat_id=int(read_config('ADMIN_ID')), text=traceback.format_exc())
    finally:
        return ConversationHandler.END


def show_menu(update, context):
    keyboard = [[KeyboardButton('Зареєструватись🙌'), KeyboardButton('Локація🧭')],
                [KeyboardButton('Розклад📅'), KeyboardButton('Співбесіда')],
                [KeyboardButton('Tutor time'), KeyboardButton('Про нас')],
                [KeyboardButton("Зв'язок📱")]]
    context.bot.send_message(chat_id=update.message.chat_id, text='Меню', reply_markup=ReplyKeyboardMarkup(keyboard))


def send_location(update, context):
    context.bot.send_message(chat_id=update.message.chat_id, text=LOCATION_TEXT, parse_mode=ParseMode.HTML)


def send_schedule(update, context):
    context.bot.send_message(chat_id=update.message.chat_id, text=SCHEDULE_TEXT)


def send_interview(update, context):
    context.bot.send_message(chat_id=update.message.chat_id, text=INTERVIEW_TEXT)


def send_tutor_time(update, context):
    reply_markup = InlineKeyboardMarkup(
        [[InlineKeyboardButton('Зареєструватись на тютор тайм', callback_data='tutor_time_register')]])
    context.bot.send_message(chat_id=update.message.chat_id, text=TUTOR_TIME_TEXT, reply_markup=reply_markup)


def send_about_us(update, context):
    context.bot.send_message(chat_id=update.message.chat_id, text=ABOUT_US_TEXT)


def send_connect(update, context):
    context.bot.send_message(chat_id=update.message.chat_id, text=CONNECT_TEXT)


def tutor_time_register(update, context):
    query = update.callback_query
    student = find_student(query.message.chat_id)
    if when_student_has_tutor_time(student) != '':
        text = f'{INVALID_TUTOR_TIME_REGISTRATION_TEXT} {when_student_has_tutor_time(student)}'
        query.answer(text)
        context.bot.send_message(query.message.chat_id, text=text)
        return
    query.answer()
    button_names = available_tutor_times()
    buttons = []
    for element in button_names:
        buttons.append([InlineKeyboardButton(text=element, callback_data=element)])
    reply_markup = InlineKeyboardMarkup(buttons)
    query.edit_message_text(query.message.text + '\n\n' + TUTOR_TIME_REGISTRATION_TEXT, reply_markup=reply_markup)


def record_tutor_time(update, context):
    query = update.callback_query
    text = f'{TUTOR_TIME_REGISTERED_TEXT} {query.data}'
    add_student_to_tutor_time(find_student(query.message.chat_id), query.data)
    query.answer(text=text)
    query.edit_message_reply_markup(reply_markup=None)
    context.bot.send_message(query.message.chat_id, text=text)


def main():
    print("start")
    updater = Updater(read_config("BOT_TOKEN"), use_context=True)
    dispatcher = updater.dispatcher
    dispatcher.add_handler(CommandHandler('start', start_command))
    dispatcher.add_handler(CommandHandler('menu', show_menu))
    dispatcher.add_handler(MessageHandler(Filters.text('Локація🧭'), send_location))
    dispatcher.add_handler(MessageHandler(Filters.text('Розклад📅'), send_schedule))
    dispatcher.add_handler(MessageHandler(Filters.text('Співбесіда'), send_interview))
    dispatcher.add_handler(MessageHandler(Filters.text('Tutor time'), send_tutor_time))
    dispatcher.add_handler(MessageHandler(Filters.text('Про нас'), send_about_us))
    dispatcher.add_handler(MessageHandler(Filters.text("Зв'язок📱"), send_connect))
    send_spam_conversation_handler = ConversationHandler(
        entry_points=[MessageHandler(Filters.text('spam_message'), spam_message)],
        states={
            0: [MessageHandler(Filters.all, ask_spam_message_text)],
        },
        fallbacks=[]
    )
    register_conversation_handler = ConversationHandler(
        entry_points=[MessageHandler(Filters.text('Зареєструватись🙌'), register)],
        states={
            ENTER_NAME: [MessageHandler(Filters.all, ask_name)],
            ENTER_PHONE: [MessageHandler(Filters.all, ask_phone)],
            ENTER_SEX: [MessageHandler(Filters.all, ask_sex)],
            ENTER_UNI: [MessageHandler(Filters.all, ask_uni)],
            ENTER_COURSE: [MessageHandler(Filters.all, ask_course)],
            ENTER_VISITED: [MessageHandler(Filters.all, ask_visited)],
            SPECIFY_VISITED: [MessageHandler(Filters.all, specify_visited)],
            ENTER_HOW_COME: [MessageHandler(Filters.all, ask_how_come)],
            ENTER_ENGLISH_LEVEL: [MessageHandler(Filters.all, ask_english_level)],
            ENTER_RELIGIOUS: [MessageHandler(Filters.all, ask_religious)],
            EXIT_CONVERSATION: [MessageHandler(Filters.all, exit_conversation)]
        },
        fallbacks=[CommandHandler('start', exit_conversation)]
    )
    dispatcher.add_handler(register_conversation_handler)
    dispatcher.add_handler(send_spam_conversation_handler)
    dispatcher.add_handler(CallbackQueryHandler(tutor_time_register, pattern='tutor_time_register'))
    dispatcher.add_handler(CallbackQueryHandler(record_tutor_time))
    updater.start_polling()
    updater.idle()


if __name__ == '__main__':
    main()
