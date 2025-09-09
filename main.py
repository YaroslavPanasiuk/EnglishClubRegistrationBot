from __future__ import print_function

import collections
import json
import os
import os.path
import re
import time
import traceback
import pandas as pd
import telegram.error

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup, ParseMode, \
    ReplyKeyboardRemove, Update
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackQueryHandler, ConversationHandler, \
    ContextTypes
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

(ENTER_NAME, ENTER_PHONE, ENTER_SEX, ENTER_UNI, ENTER_COURSE, ENTER_VISITED, SPECIFY_VISITED, ENTER_HOW_COME,
 ENTER_ENGLISH_LEVEL, ENTER_RELIGIOUS, EXIT_CONVERSATION) = range(11)


class Student:
    def __init__(self, values: []):
        self.id = values[0]
        self.name = values[1]
        if len(values) < 3:
            return
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
                                              range=read_config('REGISTRATION_RANGE_NAME')).execute().get('values', [])
        #tutor_times = sheet.values().get(spreadsheetId=read_config("SAMPLE_SPREADSHEET_ID"),
        #                                 range=read_config('TUTOR_TIME_RANGE_NAME')).execute().get('values', [])
        users_to_spam = sheet.values().get(spreadsheetId=read_config("SAMPLE_SPREADSHEET_ID"),
                                           range=read_config('SPAM_RANGE_NAME')).execute().get('values', [])
        if not registered_users:
            print('No users found.')
            return
        #if not tutor_times:
        #    print('No tutor_times found.')
        #    return
        users_df = pd.DataFrame(registered_users)
        users_df.columns = users_df.iloc[0]
        users_df = users_df[1:]
        #tutor_times_df = pd.DataFrame(tutor_times)
        #tutor_times_df.columns = tutor_times_df.iloc[0]
        #tutor_times_df = tutor_times_df[1:]
        users_to_spam_df = pd.DataFrame(users_to_spam)
        users_to_spam_df.columns = users_to_spam_df.iloc[0]
        users_to_spam_df = users_to_spam_df[1:]
        return {'registered_users': users_df, 'users_to_spam': users_to_spam_df}

    except HttpError as err:
        print(err)


def add_student(data: []):
    service = build('sheets', 'v4', credentials=connect_to_spreadsheets())
    students = service.spreadsheets().values().get(spreadsheetId=read_config("SAMPLE_SPREADSHEET_ID"),
                                                   range=read_config("REGISTRATION_RANGE_NAME")).execute()
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


def available_tutor_times():
    df = get_spreadsheets_data().get('tutor_times')
    mask = ((df['Student'] == '') | (df['Student'].isna())) & (df['Date and time'] != '') & (
        df['Date and time'].notna())
    return list(collections.OrderedDict.fromkeys(df.loc[mask, 'Date and time']))


def find_student(telegram_id: int):
    data = get_spreadsheets_data()
    df = pd.concat([data.get('registered_users'), data.get('users_to_spam')], ignore_index=True)
    if not df.loc[df['id'] == str(telegram_id)].values.flatten().tolist():
        return None
    return Student(df.loc[df['id'] == str(telegram_id)].values.flatten().tolist())


def backup_table():
    data = get_spreadsheets_data().get('registered_users').values.tolist()
    range_body_values = {
        'value_input_option': 'USER_ENTERED',
        'data': [
            {
                'majorDimension': 'ROWS',
                'range': 'Reserve!A1:L1000',
                'values': data
            },
        ]}
    service = build('sheets', 'v4', credentials=connect_to_spreadsheets())
    service.spreadsheets().values().batchUpdate(spreadsheetId=read_config("SAMPLE_SPREADSHEET_ID"),
                                                body=range_body_values).execute()


def remove_student(telegram_id):
    df = get_spreadsheets_data().get('registered_users')
    data = df.loc[df['id'] != str(telegram_id)].values.tolist()
    data.append(['']*12)
    range_body_values = {
        'value_input_option': 'USER_ENTERED',
        'data': [
            {
                'majorDimension': 'ROWS',
                'range': 'A2:L1000',
                'values': data
            },
        ]}
    service = build('sheets', 'v4', credentials=connect_to_spreadsheets())
    service.spreadsheets().values().batchUpdate(spreadsheetId=read_config("SAMPLE_SPREADSHEET_ID"),
                                                body=range_body_values).execute()


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
        df.loc[mask.idxmax(), ['Student', "Student's phone number ", 'telegram']] = [student.name, student.phone,
                                                                                     student.nickname]
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
                                    range=read_config('TEXTS_RANGE_NAME')).execute()).get('values', [])
    file = open("texts.json", "w", encoding='UTF-8')
    data = pd.DataFrame(questions).values
    dictionary = {}
    for row in data:
        dictionary[row[0]] = row[1]
    file.write(json.dumps(dictionary, indent=4, ensure_ascii=False))
    file.close()


def get_menu_markup():
    keyboard = get_keyboard([
        get_text('REGISTRATION_BUTTON'), get_text('LOCATION_BUTTON'), get_text('SCHEDULE_BUTTON'),
        get_text('INTERVIEW_BUTTON'), get_text('TUTOR_TIME_BUTTON'), get_text('ABOUT_US_BUTTON'),
        get_text('GOT_QUESTIONS_BUTTON')
    ], 2)
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def get_text(text: str):
    file = open('texts.json', encoding='UTF-8')
    content = json.load(file)
    file.close()
    if content.get(text) is not None:
        return content.get(text)
    return ''


def get_keyboard(button_names: [], columns=1):
    buttons = []
    full_rows_count = len(button_names) // columns
    last_row_size = len(button_names) % columns
    for i in range(full_rows_count):
        row = []
        for j in range(columns):
            row.append(KeyboardButton(button_names[i * columns + j]))
        buttons.append(row)
    row = []
    for i in range(last_row_size):
        row.append(KeyboardButton(button_names[i + columns * full_rows_count]))
    buttons.append(row)
    return buttons


def get_inline_keyboard(button_names: [], callbacks: [], columns=1):
    buttons = []
    full_rows_count = len(button_names) // columns
    last_row_size = len(button_names) % columns
    for i in range(full_rows_count):
        row = []
        for j in range(columns):
            index = i * columns + j
            row.append(InlineKeyboardButton(button_names[index], callback_data=callbacks[index]))
        buttons.append(row)
    row = []
    for i in range(last_row_size):
        index = i + columns * full_rows_count
        row.append(InlineKeyboardButton(button_names[index], callback_data=callbacks[index]))
    buttons.append(row)
    return buttons


def get_chats():
    df = get_spreadsheets_data().get('users_to_spam')
    return df.loc[(df['id'] != '') & (df['id'].notna()), 'id'].values


def get_default_visited_text(sex):
    if sex == get_text('FEMALE'):
        return get_text('DEFAULT_FEMALE_VISITED')
    return get_text('DEFAULT_MALE_VISITED')


def get_ask_how_come_text(sex):
    if sex == get_text('FEMALE'):
        return get_text('ASK_HOW_COME_FEMALE')
    return get_text('ASK_HOW_COME_MALE')


def get_visited_text(sex):
    if sex == get_text('FEMALE'):
        return get_text('ASK_VISITED_FEMALE')
    return get_text('ASK_VISITED_MALE')


def start_command(update, context):
    keyboard = [[KeyboardButton(get_text('REGISTRATION_BUTTON'))]]
    context.bot.send_message(chat_id=update.message.chat_id, text=get_text('INTRODUCTION'), parse_mode=ParseMode.HTML,
                             reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True))


def ask_name(update, context):
    if find_student(update.message.chat_id) is not None:
        context.bot.send_message(chat_id=update.message.chat_id, text=get_text('INVALID_REGISTRATION'),
                                 reply_markup=get_menu_markup())
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
        if len(name) < 2 or re.search('\\w', name[1]) is None:
            return ask_name(update, context)
        name = update.message.text
        context.user_data['name'] = name
        context.bot.send_message(chat_id=update.message.chat_id,
                                 text=get_text('RESTART_REGISTRATION_INFO').format(name.split()[0]))
    update.message.reply_text(get_text('ASK_PHONE'))
    return ENTER_SEX


def ask_sex(update, context):
    phone = update.message.text
    context.user_data['phone'] = phone
    if not (len(phone) == 12 and phone.isdigit()):
        return ask_phone(update, context)
    context.user_data['nickname'] = update.message.from_user.username
    keyboard = get_keyboard([get_text('MALE'), get_text('FEMALE')], 2)
    context.bot.send_message(chat_id=update.message.chat_id, text=get_text('ASK_SEX'),
                             reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True))
    return ENTER_UNI


def ask_uni(update, context):
    context.user_data['sex'] = update.message.text
    buttons = get_keyboard(get_text('UNIVERSITIES').split('; '))
    context.bot.send_message(chat_id=update.message.chat_id,
                             text=get_text('ASK_UNI'),
                             reply_markup=ReplyKeyboardMarkup(buttons, one_time_keyboard=True))
    return ENTER_COURSE


def ask_course(update, context):
    context.user_data['uni'] = update.message.text
    keyboard = get_keyboard(get_text('COURSES').split('; '), 3)
    context.bot.send_message(chat_id=update.message.chat_id, text=get_text('ASK_COURSE'),
                             reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True))
    return ENTER_VISITED


def ask_visited(update, context):
    context.user_data['course'] = update.message.text
    keyboard = get_keyboard([get_text('YES'), get_text('NO')], 2)
    context.bot.send_message(chat_id=update.message.chat_id, text=get_visited_text(context.user_data['sex']),
                             reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True))
    return SPECIFY_VISITED


def specify_visited(update, context):
    context.user_data['visited'] = update.message.text
    context.user_data['specified_visited'] = get_default_visited_text(context.user_data['sex'])
    if not (context.user_data['visited'] == get_text('YES')):
        return ask_how_come(update, context)
    button_names = get_text('OUR_EVENTS').split("; ")
    buttons = get_inline_keyboard(button_names, range(len(button_names)), 2)
    buttons.append([InlineKeyboardButton(text=get_text('INPUT_EVENTS'), callback_data='next')])
    keyboard = InlineKeyboardMarkup(buttons)
    context.bot.send_message(chat_id=update.message.chat_id, text=get_text('SPECIFY_VISITED'),
                             reply_markup=keyboard)
    return ENTER_HOW_COME


def button_how_come(update, context):
    query = update.callback_query
    answer = query.data
    if answer != 'next':
        markup = query.message.reply_markup
        result = ''
        for row in markup.inline_keyboard:
            for button in row:
                if button.callback_data == answer:
                    words = button.text.split()
                    button.text = button.text[:-2] if words[-1] == '✅' else button.text + ' ✅'
                if button.text.split()[-1] == '✅':
                    result = result + button.text[:-2] + '; '
        sex = context.user_data['sex']
        context.user_data['specified_visited'] = get_default_visited_text(sex) if result == '' else result
        query.edit_message_reply_markup(markup)
    else:
        query.edit_message_text(text=query.message.text +
                                get_text('SPECIFY_VISITED_ANSWER').format(context.user_data["specified_visited"]),
                                reply_markup=None)
        return ask_how_come(query, context)


def ask_how_come(update, context):
    keyboard = get_keyboard(get_text('ADVERTISEMENTS').split('; '), 2)
    context.bot.send_message(chat_id=update.message.chat_id, text=get_ask_how_come_text(context.user_data['sex']),
                             reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True))
    return ENTER_ENGLISH_LEVEL


def ask_english_level(update, context):
    context.user_data['how_come'] = update.message.text
    keyboard = get_keyboard(get_text('ENGLISH_LEVELS').split('; '))
    context.bot.send_message(chat_id=update.message.chat_id, text=get_text('ASK_ENGLISH_LEVEL'),
                             reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True))
    return ENTER_RELIGIOUS


def ask_religious(update, context):
    context.user_data['english_level'] = update.message.text
    keyboard = get_keyboard(get_text('ATTITUDES').split('; '))
    context.bot.send_message(chat_id=update.message.chat_id, text=get_text('ASK_RELIGIOUS'),
                             reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True))
    return EXIT_CONVERSATION


def exit_conversation(update, context):
    context.user_data['religious'] = update.message.text
    update.message.reply_text(get_text('END_REGISTRATION'))
    try:
        add_student(list(context.user_data.values()))
    except:
        context.bot.send_message(chat_id=int(read_config('ADMIN_ID')), text=traceback.format_exc())
        context.bot.send_message(chat_id=int(read_config('ADMIN_ID')),
                                 text=f'failed to register. user is '
                                      f'{context.user_data.get("name")}; {context.user_data.get("nickname")}')
    finally:
        show_menu(update, context)
        return ConversationHandler.END


def cancel_conversation(update: Update, context: ContextTypes.context):
    context.bot.send_message(chat_id=update.message.chat_id, text='successfully canceled')
    return ConversationHandler.END


def finish_conversation(update: Update, context: ContextTypes.context):
    keyboard = [[KeyboardButton(get_text('REGISTRATION_BUTTON'))]]
    context.bot.send_message(chat_id=update.effective_chat.id, text=get_text('RESTART_REGISTRATION'),
                             reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True))
    remove_student(update.effective_chat.id)
    return ConversationHandler.END


def spam_message(update, context):
    if update.message.chat_id != int(read_config('ADMIN_ID')) and update.message.chat_id != int(
            read_config('ADMIN_ID_3')) and update.message.chat_id != int(read_config('ADMIN_ID_2')):
        return ConversationHandler.END
    students = get_spreadsheets_data().get('users_to_spam').values.tolist()
    receivers = ''
    for student in students:
        receivers = receivers + f"{student[0]} - {student[1]}\n"
        if len(receivers) > 3500:
            context.bot.send_message(chat_id=update.message.chat_id,
                                     text=get_text('MESSAGE_TO_SPAM').format(len(students), receivers))
            receivers = ''
    context.bot.send_message(chat_id=update.message.chat_id,
                             text=get_text('MESSAGE_TO_SPAM').format(len(students), receivers))
    return 0


def ask_spam_message_text(update, context):
    chats = get_chats()
    current_chat_id = update.message.chat_id
    try:
        for chat in chats:
            student = find_student(chat)
            try:
                context.bot.send_message(chat_id=int(chat), text=update.message.text)
                time.sleep(1)
                context.bot.send_message(chat_id=current_chat_id, text=f'sent to {student.name}, id = {student.id}')
                time.sleep(1)
            except telegram.error.Unauthorized:
                report_error(context.bot, current_chat_id, f'{student.name} has blocked me((')
            except telegram.error.BadRequest:
                report_error(context.bot, current_chat_id, f'{student.name} has not yet contacted me')
        context.bot.send_message(chat_id=current_chat_id, text='sentAll')
    except:
        context.bot.send_message(chat_id=int(read_config('ADMIN_ID')), text=traceback.format_exc())
        if current_chat_id != int(read_config('ADMIN_ID')):
            time.sleep(1)
            context.bot.send_message(chat_id=update.message.chat_id, text=traceback.format_exc())
    finally:
        return ConversationHandler.END


def report_error(bot, chat_id, msg):
    bot.send_message(chat_id=int(read_config('ADMIN_ID')), text=msg)
    if chat_id != int(read_config('ADMIN_ID')):
        time.sleep(1)
        bot.send_message(chat_id=chat_id, text=msg)


def show_menu(update, context):
    context.bot.send_message(chat_id=update.message.chat_id, text=get_text('MENU'), reply_markup=get_menu_markup())


def send_location(update, context):
    context.bot.send_message(chat_id=update.message.chat_id, text=get_text('LOCATION'), parse_mode=ParseMode.HTML)


def send_schedule(update, context):
    context.bot.send_message(chat_id=update.message.chat_id, text=get_text('SCHEDULE'))


def send_interview(update, context):
    context.bot.send_message(chat_id=update.message.chat_id, text=get_text('INTERVIEW'))


def send_tutor_time(update, context):
    # reply_markup = InlineKeyboardMarkup(
    #    [[InlineKeyboardButton(get_text('TUTOR_TIME_REGISTRATION_BUTTON'), callback_data='tutor_time_register')]])
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
    query.edit_message_text(query.message.text + '\n\n' + get_text('TUTOR_TIME_REGISTRATION'),
                            reply_markup=reply_markup)


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
    backup_table()
    updater = Updater(read_config("TEST_BOT_TOKEN"), use_context=True)
    dispatcher = updater.dispatcher
    dispatcher.add_handler(CommandHandler('start', start_command))
    dispatcher.add_handler(CommandHandler('menu', show_menu))
    dispatcher.add_handler(MessageHandler(Filters.regex(f"^{get_text('LOCATION_BUTTON')}$"), send_location))
    dispatcher.add_handler(MessageHandler(Filters.regex(f"^{get_text('SCHEDULE_BUTTON')}$"), send_schedule))
    dispatcher.add_handler(MessageHandler(Filters.regex(f"^{get_text('INTERVIEW_BUTTON')}$"), send_interview))
    dispatcher.add_handler(MessageHandler(Filters.regex(f"^{get_text('TUTOR_TIME_BUTTON')}$"), send_tutor_time))
    dispatcher.add_handler(MessageHandler(Filters.regex(f"^{get_text('ABOUT_US_BUTTON')}$"), send_about_us))
    dispatcher.add_handler(MessageHandler(Filters.regex(f"^{get_text('GOT_QUESTIONS_BUTTON')}$"), send_connect))
    send_spam_conversation_handler = ConversationHandler(
        entry_points=[MessageHandler(Filters.text('spam_message'), spam_message)],
        states={
            0: [MessageHandler(Filters.text & (~ Filters.command), ask_spam_message_text)],
        },
        fallbacks=[CommandHandler('cancel', cancel_conversation)]
    )
    register_conversation_handler = ConversationHandler(
        entry_points=[MessageHandler(Filters.text(get_text('REGISTRATION_BUTTON')), ask_name)],
        states={
            ENTER_PHONE: [MessageHandler(Filters.text & (~ Filters.command), ask_phone)],
            ENTER_SEX: [MessageHandler(Filters.text & (~ Filters.command), ask_sex)],
            ENTER_UNI: [MessageHandler(Filters.text & (~ Filters.command), ask_uni)],
            ENTER_COURSE: [MessageHandler(Filters.text & (~ Filters.command), ask_course)],
            ENTER_VISITED: [MessageHandler(Filters.text & (~ Filters.command), ask_visited)],
            SPECIFY_VISITED: [MessageHandler(Filters.text & (~ Filters.command), specify_visited)],
            ENTER_HOW_COME: [CallbackQueryHandler(button_how_come, pattern='next|\\d')],
            ENTER_ENGLISH_LEVEL: [MessageHandler(Filters.text & (~ Filters.command), ask_english_level)],
            ENTER_RELIGIOUS: [MessageHandler(Filters.text & (~ Filters.command), ask_religious)],
            EXIT_CONVERSATION: [MessageHandler(Filters.text & (~ Filters.command), exit_conversation)]
        },
        fallbacks=[CommandHandler('restart_registration', finish_conversation)]
    )
    dispatcher.add_handler(register_conversation_handler)
    dispatcher.add_handler(CommandHandler('restart_registration', finish_conversation))
    dispatcher.add_handler(send_spam_conversation_handler)
    dispatcher.add_handler(CallbackQueryHandler(tutor_time_register, pattern='tutor_time_register'))
    dispatcher.add_handler(CallbackQueryHandler(record_tutor_time))
    updater.start_polling()
    updater.idle()


if __name__ == '__main__':
    main()
