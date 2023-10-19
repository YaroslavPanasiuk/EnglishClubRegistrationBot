from __future__ import print_function

import collections
import json
import os
import os.path
import time
import traceback
import pandas as pd

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup, ParseMode, \
    ReplyKeyboardRemove
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
        self.name = values[1]
        self.phone = values[2]
        self.nickname = values[3]
        self.sex = values[4]
        self.uni = values[5]
        self.course = values[6]
        self.visited = values[7]
        self.specified_visited = values[8]
        self.how_come = values[9]
        self.english_level = values[10]
        self.religious = values[11]


def read_config(value) -> str:
    file = open('config.txt', encoding='UTF-8')
    lines = file.readlines()
    file.close()
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


def get_spreadsheets_data():
    try:
        service = build('sheets', 'v4', credentials=connect_to_spreadsheets())
        sheet = service.spreadsheets()
        registered_users = sheet.values().get(spreadsheetId=read_config("SAMPLE_SPREADSHEET_ID"),
                                              range='Реєстрація!A1:R500').execute().get('values', [])
        tutor_times = sheet.values().get(spreadsheetId=read_config("SAMPLE_SPREADSHEET_ID"),
                                         range='Tutor time!A1:H60').execute().get('values', [])
        if not registered_users:
            print('No users found.')
            return
        if not tutor_times:
            print('No tutor_times found.')
            return
        users_df = pd.DataFrame(registered_users)
        users_df.columns = users_df.iloc[0]
        users_df = users_df[1:]
        tutor_times_df = pd.DataFrame(tutor_times)
        tutor_times_df.columns = tutor_times_df.iloc[0]
        tutor_times_df = tutor_times_df[1:]
        return {'registered_users': users_df, 'tutor_times': tutor_times_df}

    except HttpError as err:
        print(err)


def add_student(data: []):
    try:
        service = build('sheets', 'v4', credentials=connect_to_spreadsheets())
        sheet = service.spreadsheets()
        students = sheet.values().get(spreadsheetId=read_config("SAMPLE_SPREADSHEET_ID"),
                                      range=read_config("SAMPLE_RANGE_NAME")).execute()
        data_range = 'A{0}:L{0}'.format(str(len(students.get('values', [])) + 1))
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


def available_tutor_times():
    df = get_spreadsheets_data().get('tutor_times')
    mask = ((df['Student'] == '') | (df['Student'].isna())) & (df['Date and time'] != '') & (df['Date and time'].notna())
    return list(collections.OrderedDict.fromkeys(df.loc[mask, 'Date and time']))


def find_student(telegram_id):
    df = get_spreadsheets_data().get('registered_users')
    if not df.loc[df['id'] == str(telegram_id)].values.flatten().tolist():
        return None
    return Student(df.loc[df['id'] == str(telegram_id)].values.flatten().tolist())


def when_student_has_tutor_time(student: Student):
    df = get_spreadsheets_data().get('tutor_times')
    mask = ((df['Student'] == student.name) & (df["Student's phone number "] == student.phone) &
            ((df['telegram'] == student.nickname) | ((df['telegram'].isna()) & (student.nickname == ''))))
    if len(df.loc[mask, "Date and time"]) == 0:
        return ''
    return str(df.loc[mask.idxmax(), "Date and time"])


def add_student_to_tutor_time(student: Student, tutor_time: str):
    try:
        service = build('sheets', 'v4', credentials=connect_to_spreadsheets())
        df = get_spreadsheets_data().get('tutor_times')
        mask = (df['Date and time'] == tutor_time) & (df['Student'].isna())
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


def update_texts():
    service = build('sheets', 'v4', credentials=connect_to_spreadsheets())
    sheet = service.spreadsheets()
    questions = (sheet.values().get(spreadsheetId=read_config("SAMPLE_SPREADSHEET_ID"),
                                    range='Питання!A1:B50').execute()).get('values', [])
    file = open("texts.json", "w", encoding='UTF-8')
    data = pd.DataFrame(questions).values
    dictionary = {}
    for row in data:
        dictionary[row[0]] = row[1]
    file.write(json.dumps(dictionary, indent=4, ensure_ascii=False))
    file.close()


def get_keyboard():
    keyboard = [[KeyboardButton(get_text('REGISTRATION_BUTTON')), KeyboardButton(get_text('LOCATION_BUTTON'))],
                [KeyboardButton(get_text('SCHEDULE_BUTTON')), KeyboardButton(get_text('INTERVIEW_BUTTON'))],
                [KeyboardButton(get_text('TUTOR_TIME_BUTTON')), KeyboardButton(get_text('ABOUT_US_BUTTON'))],
                [KeyboardButton(get_text('GOT_QUESTIONS_BUTTON'))]]
    return ReplyKeyboardMarkup(keyboard)


def get_text(text: str):
    file = open('texts.json', encoding='UTF-8')
    content = json.load(file)
    file.close()
    if content.get(text) is not None:
        return content.get(text)
    return ''


def get_chats():
    df = get_spreadsheets_data().get('registered_users')
    return df.loc[(df['id'] != '') & (df['id'].notna()), 'id'].values


def start_command(update, context):
    keyboard = [[KeyboardButton(get_text('REGISTRATION_BUTTON'))]]
    context.bot.send_message(chat_id=update.message.chat_id, text=get_text('INTRODUCTION'), parse_mode=ParseMode.HTML,
                             reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True))


def ask_name(update, context):
    if get_chats().__contains__(str(update.message.chat_id)):
        context.bot.send_message(chat_id=update.message.chat_id, text=get_text('INVALID_REGISTRATION'),
                                 reply_markup=get_keyboard())
        update_texts()
        return ConversationHandler.END
    context.user_data.clear()
    context.user_data['id'] = update.message.chat_id
    context.bot.send_message(chat_id=update.message.chat_id, text=get_text('ASK_NAME'),
                             parse_mode=ParseMode.HTML, reply_markup=ReplyKeyboardRemove())
    update_texts()
    return ENTER_PHONE


def ask_phone(update, context):
    if context.user_data.get('phone') is None:
        name = update.message.text.split()
        if len(name) < 2:
            return ask_name(update, context)
        context.user_data['name'] = update.message.text
    update.message.reply_text(get_text('ASK_PHONE'))
    return ENTER_SEX


def ask_sex(update, context):
    phone = update.message.text
    context.user_data['phone'] = phone
    if not (len(phone) == 12 and phone.isdigit()):
        return ask_phone(update, context)
    context.user_data['nickname'] = update.message.from_user.username
    keyboard = [[KeyboardButton('Чол'), KeyboardButton('Жін')]]
    context.bot.send_message(chat_id=update.message.chat_id, text=get_text('ASK_SEX'),
                             reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True))
    return ENTER_UNI


def ask_uni(update, context):
    context.user_data['sex'] = update.message.text
    keyboard = [[KeyboardButton('Національний Університет "Львівська Політехніка"')],
                [KeyboardButton('Львівський Національний Університет ім. І.Франка')],
                [KeyboardButton('Національний Лісотехнічний Університет України')],
                [KeyboardButton('Львівський державний університет внутрішніх справ МВС України')],
                [KeyboardButton('Національний Університет Ветеринарної медицини та біотехнологій ім. С.Ґжицького')],
                [KeyboardButton('Українська Академія Друкарства')],
                ]
    context.bot.send_message(chat_id=update.message.chat_id,
                             text=get_text('ASK_UNI'),
                             reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True))
    return ENTER_COURSE


def ask_course(update, context):
    context.user_data['uni'] = update.message.text
    keyboard = [[KeyboardButton('1'), KeyboardButton('2'), KeyboardButton('3')],
                [KeyboardButton('4'), KeyboardButton('5'), KeyboardButton('6')],
                [KeyboardButton('Закінчив'), KeyboardButton('Школяр')]]
    context.bot.send_message(chat_id=update.message.chat_id, text=get_text('ASK_COURSE'),
                             reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True))
    return ENTER_VISITED


def ask_visited(update, context):
    context.user_data['course'] = update.message.text
    keyboard = [[KeyboardButton('Так'), KeyboardButton('Ні')]]
    context.bot.send_message(chat_id=update.message.chat_id, text=get_text('ASK_VISITED'),
                             reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True))
    return SPECIFY_VISITED


def specify_visited(update, context):
    context.user_data['visited'] = update.message.text
    if not (context.user_data['visited'] == 'Так'):
        return ask_how_come(update, context)
    context.bot.send_message(chat_id=update.message.chat_id, text=get_text('SPECIFY_VISITED'))
    return ENTER_HOW_COME


def ask_how_come(update, context):
    context.user_data['specified_visited'] = '-'
    if context.user_data['visited'] == 'Так':
        context.user_data['specified_visited'] = update.message.text
    keyboard = [[KeyboardButton('Флаєр')], [KeyboardButton('Постер')], [KeyboardButton('Друзі запросили')],
                [KeyboardButton('Реклама Instagram')], [KeyboardButton('Реклама Telegram')]]
    context.bot.send_message(chat_id=update.message.chat_id, text=get_text('ASK_HOW_COME'),
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
    context.bot.send_message(chat_id=update.message.chat_id, text=get_text('ASK_ENGLISH_LEVEL'),
                             reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True))
    return ENTER_RELIGIOUS


def ask_religious(update, context):
    context.user_data['english_level'] = update.message.text
    keyboard = [[KeyboardButton('Позитивно')],
                [KeyboardButton('Негативно')],
                [KeyboardButton('Нейтрально')], ]
    context.bot.send_message(chat_id=update.message.chat_id, text=get_text('ASK_RELIGIOUS'),
                             reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True))
    return EXIT_CONVERSATION


def exit_conversation(update, context):
    context.user_data['religious'] = update.message.text
    update.message.reply_text(get_text('END_REGISTRATION'))
    try:
        add_student(list(context.user_data.values()))
    except:
        context.bot.send_message(chat_id=int(read_config('ADMIN_ID')), text=traceback.format_exc())
        context.bot.send_message(chat_id=int(read_config('ADMIN_ID')), text=f'failed to register. user is {context.user_data.get("name")}')
    finally:
        show_menu(update, context)
        return ConversationHandler.END


def finish_conversation(update, context):
    print('end')
    return ConversationHandler.END


def spam_message(update, context):
    if update.message.chat_id != int(read_config('ADMIN_ID')) and update.message.chat_id != int(
            read_config('COADMIN_ID')) and update.message.chat_id != int(read_config('COADMIN_ID_2')):
        return ConversationHandler.END
    chats = get_chats()
    context.bot.send_message(chat_id=update.message.chat_id,
                             text='Введіть повідомлення для розсилки {n} людям {chats}'.format(n=len(chats),
                                                                                               chats=chats))
    return 0


def ask_spam_message_text(update, context):
    chats = get_chats()
    try:
        for chat in chats:
            context.bot.send_message(chat_id=int(chat), text=update.message.text)
            time.sleep(1)
            student = find_student(chat)
            context.bot.send_message(chat_id=update.message.chat_id, text=f'sent to {student.name}, id = {student.id}')
            time.sleep(1)
        context.bot.send_message(chat_id=update.message.chat_id, text='sentAll')
    except:
        context.bot.send_message(chat_id=int(read_config('ADMIN_ID')), text=traceback.format_exc())
    finally:
        return ConversationHandler.END


def show_menu(update, context):
    context.bot.send_message(chat_id=update.message.chat_id, text='Меню', reply_markup=get_keyboard())


def send_location(update, context):
    context.bot.send_message(chat_id=update.message.chat_id, text=get_text('LOCATION'), parse_mode=ParseMode.HTML)


def send_schedule(update, context):
    context.bot.send_message(chat_id=update.message.chat_id, text=get_text('SCHEDULE'))


def send_interview(update, context):
    context.bot.send_message(chat_id=update.message.chat_id, text=get_text('INTERVIEW'))


def send_tutor_time(update, context):
    reply_markup = InlineKeyboardMarkup(
        [[InlineKeyboardButton(get_text('TUTOR_TIME_REGISTRATION_BUTTON'), callback_data='tutor_time_register')]])
    context.bot.send_message(chat_id=update.message.chat_id, text=get_text('TUTOR_TIME'), reply_markup=None)


def send_about_us(update, context):
    context.bot.send_message(chat_id=update.message.chat_id, text=get_text('ABOUT_US'), parse_mode=ParseMode.HTML)


def send_connect(update, context):
    context.bot.send_message(chat_id=update.message.chat_id, text=get_text('GOT_QUESTIONS'))


def tutor_time_register(update, context):
    query = update.callback_query
    student = find_student(query.message.chat_id)
    if student is None:
        text = get_text('UNREGISTERED_TUTOR_TIME_REGISTRATION')
        query.answer(text)
        context.bot.send_message(query.message.chat_id, text=text)
        return
    if when_student_has_tutor_time(student) != '':
        text = f'{get_text("INVALID_TUTOR_TIME_REGISTRATION")} {when_student_has_tutor_time(student)}'
        query.answer(text)
        context.bot.send_message(query.message.chat_id, text=text)
        return
    query.answer()
    button_names = available_tutor_times()
    buttons = []
    for element in button_names:
        buttons.append([InlineKeyboardButton(text=element, callback_data=element)])
    reply_markup = InlineKeyboardMarkup(buttons)
    query.edit_message_text(query.message.text + '\n\n' + get_text('TUTOR_TIME_REGISTRATION'), reply_markup=reply_markup)


def record_tutor_time(update, context):
    query = update.callback_query
    text = f'{get_text("TUTOR_TIME_REGISTERED")} {query.data}'
    add_student_to_tutor_time(find_student(query.message.chat_id), query.data)
    query.answer(text=text)
    query.edit_message_reply_markup(reply_markup=None)
    context.bot.send_message(query.message.chat_id, text=text)


def main():
    print("start")
    update_texts()
    updater = Updater(read_config("BOT_TOKEN"), use_context=True)
    dispatcher = updater.dispatcher
    dispatcher.add_handler(CommandHandler('start', start_command))
    dispatcher.add_handler(CommandHandler('menu', show_menu))
    dispatcher.add_handler(MessageHandler(Filters.text(get_text('LOCATION_BUTTON')), send_location))
    dispatcher.add_handler(MessageHandler(Filters.text(get_text('SCHEDULE_BUTTON')), send_schedule))
    dispatcher.add_handler(MessageHandler(Filters.text(get_text('INTERVIEW_BUTTON')), send_interview))
    dispatcher.add_handler(MessageHandler(Filters.text(get_text('TUTOR_TIME_BUTTON')), send_tutor_time))
    dispatcher.add_handler(MessageHandler(Filters.text(get_text('ABOUT_US_BUTTON')), send_about_us))
    dispatcher.add_handler(MessageHandler(Filters.text(get_text('GOT_QUESTIONS_BUTTON')), send_connect))
    send_spam_conversation_handler = ConversationHandler(
        entry_points=[MessageHandler(Filters.text('spam_message'), spam_message)],
        states={
            0: [MessageHandler(Filters.all, ask_spam_message_text)],
        },
        fallbacks=[]
    )
    register_conversation_handler = ConversationHandler(
        entry_points=[MessageHandler(Filters.text(get_text('REGISTRATION_BUTTON')), ask_name)],
        states={
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
        fallbacks=[]
    )
    dispatcher.add_handler(register_conversation_handler)
    dispatcher.add_handler(send_spam_conversation_handler)
    dispatcher.add_handler(CallbackQueryHandler(tutor_time_register, pattern='tutor_time_register'))
    dispatcher.add_handler(CallbackQueryHandler(record_tutor_time))
    updater.start_polling()
    updater.idle()


if __name__ == '__main__':
    main()
