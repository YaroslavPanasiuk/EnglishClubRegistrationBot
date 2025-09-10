from __future__ import print_function

import collections
import json
import os
import os.path
import re
from pathlib import Path
import time
import traceback
import pandas as pd
import sys
import telegram.error
import asyncio
import socket

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup, \
    ReplyKeyboardRemove, Update
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler, \
    ConversationHandler, ContextTypes
from google.auth.transport import requests as google_requests
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from typing import List, Dict, Any

(ENTER_NAME, ENTER_PHONE, ENTER_SEX, ENTER_UNI, ENTER_COURSE, ENTER_VISITED, SPECIFY_VISITED, ENTER_HOW_COME,
 ENTER_ENGLISH_LEVEL, ENTER_RELIGIOUS, EXIT_CONVERSATION, SPAM_MESSAGE) = range(12)
REGISTRATION_IS_CLOSED = False


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

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'name': self.name,
            'phone': self.phone,
            'nickname': self.nickname,
            'sex': self.sex,
            'uni': self.uni,
            'course': self.course,
            'visited': self.visited,
            'specified_visited': self.specified_visited,
            'how_come': self.how_come,
            'english_level': self.english_level,
            'religious': self.religious
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Student':
        return cls([
            data["id"],
            data["name"],
            data["phone"],
            data["nickname"],
            data["sex"],
            data["uni"],
            data["course"],
            data["visited"],
            data["specified_visited"],
            data["how_come"],
            data["english_level"],
            data["religious"]
        ])


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
    
    # Force IPv4 for this connection
    socket.setdefaulttimeout(30)
    
    if os.path.exists('token.json'):
        try:
            creds = Credentials.from_authorized_user_file('token.json', scopes)
        except Exception as e:
            print(f"Error loading credentials: {e}")
            os.remove('token.json')
    
    if not creds or not creds.valid:
        try:
            if creds and creds.expired and creds.refresh_token:
                # Create a custom request with IPv4 forcing
                ipv4_request = google_requests.Request()
                creds.refresh(ipv4_request)
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    'credentials.json', scopes)
                # For the local server flow, we need to handle this differently
                creds = flow.run_local_server(port=0, open_browser=False)
            
            with open('token.json', 'w') as token:
                token.write(creds.to_json())
                
        except Exception as e:
            print(f"Authentication failed: {e}")
            raise
    
    return creds


def get_students_from_spreadsheets(service=None):
    try:
        if service is None:
            service = build('sheets', 'v4', credentials=connect_to_spreadsheets())
        sheet = service.spreadsheets()
        registered_users = sheet.values().get(spreadsheetId=read_config("SAMPLE_SPREADSHEET_ID"),
                                              range=read_config('REGISTRATION_RANGE_NAME')).execute().get('values', [])
        if not registered_users:
            print('No users found.')
            users_df = pd.DataFrame([])
        else:
            users_df = pd.DataFrame(registered_users)
            users_df.columns = users_df.iloc[0]
            users_df = users_df[1:]
        return users_df

    except HttpError as err:
        print(err)


def get_students_to_spam_from_spreadsheets():
    try:
        service = build('sheets', 'v4', credentials=connect_to_spreadsheets())
        sheet = service.spreadsheets()
        users_to_spam = sheet.values().get(spreadsheetId=read_config("SAMPLE_SPREADSHEET_ID"),
                                           range=read_config('SPAM_RANGE_NAME')).execute().get('values', [])
        if not users_to_spam:
            print('No users found.')
            users_to_spam_df = pd.DataFrame([])
        else:
            users_to_spam_df = pd.DataFrame(users_to_spam)
            users_to_spam_df.columns = users_to_spam_df.iloc[0]
            users_to_spam_df = users_to_spam_df[1:]
        return users_to_spam_df

    except HttpError as err:
        print(err)


def add_student(data: []):
    service = build('sheets', 'v4', credentials=connect_to_spreadsheets())
    df = get_students_from_spreadsheets(service)
    data_range = 'A{0}:L{0}'.format(str(len(df) + 2))
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
    
    new_row = pd.DataFrame([data], columns=df.columns)
    df = pd.concat([df, new_row], axis=0)
    df.to_csv('data/students.csv', index=False)


def load_students_fromc_csv(filename: str) -> List[Student]:
    df = pd.read_csv('data/students.csv')
    return [Student([*row[0:12]]) for _, row in df.iterrows()]


def find_student(telegram_id: int):
    df = get_students_from_spreadsheets()
    if not df.loc[df['id'] == telegram_id].values.flatten().tolist():
        return None
    return Student(df.loc[df['id'] == telegram_id].values.flatten().tolist())


def sync_local_students():
    df = get_students_from_spreadsheets()
    df.to_csv('data/students.csv', index=False)
    

def find_student_local(telegram_id: int):
    df = pd.read_csv('data/students.csv')
    if not df.loc[df['id'] == telegram_id].values.flatten().tolist():
        return None
    return Student(df.loc[df['id'] == telegram_id].values.flatten().tolist())


def backup_table():
    data = get_students_from_spreadsheets().values.tolist()
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
    df = get_students_from_spreadsheets()
    df = df.loc[df['id'] != str(telegram_id)]
    data = df.values.tolist()
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
    df.to_csv('data/students.csv', index=False)


def update_texts():
    service = build('sheets', 'v4', credentials=connect_to_spreadsheets()) 
    sheet = service.spreadsheets()
    questions = (sheet.values().get(spreadsheetId=read_config("SAMPLE_SPREADSHEET_ID"),
                                    range=read_config('TEXTS_RANGE_NAME')).execute()).get('values', [])
    file = open("data/texts.json", "w", encoding='UTF-8')
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
    file = open('data/texts.json', encoding='UTF-8')
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
    df = get_students_to_spam_from_spreadsheets()
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


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[KeyboardButton(get_text('REGISTRATION_BUTTON'))]]
    await context.bot.send_message(chat_id=update.effective_chat.id, text=get_text('INTRODUCTION'), parse_mode=ParseMode.HTML,
                             reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True))


async def ask_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if REGISTRATION_IS_CLOSED:
        await context.bot.send_message(chat_id=update.effective_chat.id, text=get_text('REGISTRAION_IS_STOPPED'),
                                 reply_markup=get_menu_markup())
        update_texts()
        return ConversationHandler.END
    if find_student_local(update.effective_chat.id) is not None:
        await context.bot.send_message(chat_id=update.effective_chat.id, text=get_text('INVALID_REGISTRATION'),
                                 reply_markup=get_menu_markup())
        update_texts()
        return ConversationHandler.END
    context.user_data.clear()
    context.user_data['id'] = update.effective_chat.id
    await context.bot.send_message(chat_id=update.effective_chat.id, text=get_text('ASK_NAME'),
                             parse_mode=ParseMode.HTML, reply_markup=ReplyKeyboardRemove())
    update_texts()
    return ENTER_PHONE


async def ask_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get('phone') is None:
        name = update.message.text.split()
        if len(name) < 2 or re.search('\\w', name[1]) is None:
            return await ask_name(update, context)
        name = update.message.text
        context.user_data['name'] = name
        await context.bot.send_message(chat_id=update.effective_chat.id,
                                 text=get_text('RESTART_REGISTRATION_INFO').format(name.split()[0]))
    await update.message.reply_text(get_text('ASK_PHONE'))
    return ENTER_SEX


async def ask_sex(update: Update, context: ContextTypes.DEFAULT_TYPE):
    phone = update.message.text
    context.user_data['phone'] = phone
    if not (len(phone) == 12 and phone.isdigit()):
        return await ask_phone(update, context)
    context.user_data['nickname'] = update.message.from_user.username
    keyboard = get_keyboard([get_text('MALE'), get_text('FEMALE')], 2)
    await context.bot.send_message(chat_id=update.effective_chat.id, text=get_text('ASK_SEX'),
                             reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True))
    return ENTER_UNI


async def ask_uni(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['sex'] = update.message.text
    buttons = get_keyboard(get_text('UNIVERSITIES').split('; '))
    await context.bot.send_message(chat_id=update.effective_chat.id,
                             text=get_text('ASK_UNI'),
                             reply_markup=ReplyKeyboardMarkup(buttons, one_time_keyboard=True))
    return ENTER_COURSE


async def ask_course(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['uni'] = update.message.text
    keyboard = get_keyboard(get_text('COURSES').split('; '), 3)
    await context.bot.send_message(chat_id=update.effective_chat.id, text=get_text('ASK_COURSE'),
                             reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True))
    return ENTER_VISITED


async def ask_visited(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['course'] = update.message.text
    keyboard = get_keyboard([get_text('YES'), get_text('NO')], 2)
    await context.bot.send_message(chat_id=update.effective_chat.id, text=get_visited_text(context.user_data['sex']),
                             reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True))
    return SPECIFY_VISITED


async def specify_visited(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['visited'] = update.message.text
    context.user_data['specified_visited'] = get_default_visited_text(context.user_data['sex'])
    if not (context.user_data['visited'] == get_text('YES')):
        return await ask_how_come(update, context)
    button_names = get_text('OUR_EVENTS').split("; ")
    buttons = get_inline_keyboard(button_names, range(len(button_names)), 2)
    buttons.append([InlineKeyboardButton(text=get_text('INPUT_EVENTS'), callback_data='next')])
    keyboard = InlineKeyboardMarkup(buttons)
    await context.bot.send_message(chat_id=update.effective_chat.id, text=get_text('SPECIFY_VISITED'),
                             reply_markup=keyboard)
    return ENTER_HOW_COME


async def button_how_come(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    answer = query.data
    
    if answer != 'next':
        # Get the current markup
        markup = query.message.reply_markup
        result = ''
        
        # Create a new keyboard with updated buttons
        new_keyboard = []
        for row in markup.inline_keyboard:
            new_row = []
            for button in row:
                if button.callback_data == answer:
                    # Toggle the checkmark for the clicked button
                    words = button.text.split()
                    if words[-1] == '✅':
                        new_text = button.text[:-2]
                    else:
                        new_text = button.text + ' ✅'
                    new_button = InlineKeyboardButton(text=new_text, callback_data=button.callback_data)
                else:
                    new_button = button
                
                new_row.append(new_button)
                
                # Check if this button has a checkmark for the result
                button_words = new_button.text.split()
                if button_words[-1] == '✅':
                    result = result + new_button.text[:-2] + '; '
            
            new_keyboard.append(new_row)
        
        # Add the "next" button
        #new_keyboard.append([InlineKeyboardButton(text=get_text('INPUT_EVENTS'), callback_data='next')])
        
        sex = context.user_data['sex']
        context.user_data['specified_visited'] = get_default_visited_text(sex) if result == '' else result
        
        # Update the message with the new keyboard
        new_markup = InlineKeyboardMarkup(new_keyboard)
        await query.edit_message_reply_markup(reply_markup=new_markup)
    else:
        # User clicked "next"
        await query.edit_message_text(
            text=query.message.text + '\n\n' + get_text('SPECIFY_VISITED_ANSWER').format(context.user_data["specified_visited"]),
            reply_markup=None
        )
        return await ask_how_come(update, context)


async def ask_how_come(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = get_keyboard(get_text('ADVERTISEMENTS').split('; '), 2)
    await context.bot.send_message(chat_id=update.effective_chat.id, text=get_ask_how_come_text(context.user_data['sex']),
                             reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True))
    return ENTER_ENGLISH_LEVEL


async def ask_english_level(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['how_come'] = update.message.text
    keyboard = get_keyboard(get_text('ENGLISH_LEVELS').split('; '))
    await context.bot.send_message(chat_id=update.effective_chat.id, text=get_text('ASK_ENGLISH_LEVEL'),
                             reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True))
    return ENTER_RELIGIOUS


async def ask_religious(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['english_level'] = update.message.text
    keyboard = get_keyboard(get_text('ATTITUDES').split('; '))
    await context.bot.send_message(chat_id=update.effective_chat.id, text=get_text('ASK_RELIGIOUS'),
                             reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True))
    return EXIT_CONVERSATION


async def exit_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['religious'] = update.message.text
    await update.message.reply_text(get_text('END_REGISTRATION'))
    try:
        add_student(list(context.user_data.values()))
    except:
        await context.bot.send_message(chat_id=int(read_config('SUPER_ADMIN_ID')), text=traceback.format_exc())
        await context.bot.send_message(chat_id=int(read_config('SUPER_ADMIN_ID')),
                                 text=f'failed to register. user is '
                                      f'{context.user_data.get("name")}; {context.user_data.get("nickname")}')
        await context.bot.send_message(chat_id=int(read_config('SUPER_ADMIN_ID')),
                                 text=f'full user data: '
                                      f'{context.user_data.get("id")} {context.user_data.get("name")} {context.user_data.get("phone")} {context.user_data.get("nickname")} {context.user_data.get("sex")} {context.user_data.get("uni")} {context.user_data.get("course")} {context.user_data.get("visited")} {context.user_data.get("specified_visited")} {context.user_data.get("how_come")} {context.user_data.get("english_level")} {context.user_data.get("religious")}')

    finally:
        await show_menu(update, context)
        return ConversationHandler.END


async def cancel_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(chat_id=update.effective_chat.id, text='successfully canceled')
    return ConversationHandler.END


async def finish_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[KeyboardButton(get_text('REGISTRATION_BUTTON'))]]
    await context.bot.send_message(chat_id=update.effective_chat.id, text=get_text('RESTART_REGISTRATION'),
                             reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True))
    remove_student(update.effective_chat.id)
    return ConversationHandler.END


def is_admin(id: int):
    admins = read_config("ADMIN_IDS").split(" ")
    for i in range(len(admins)):
        if int(admins[i]) == id:
            return True
    return False


async def spam_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_chat.id):
        print("not admin")
        return ConversationHandler.END
    students = get_students_to_spam_from_spreadsheets().values.tolist()
    receivers = ''
    for student in students:
        receivers = receivers + f"{student[0]} - {student[1]}\n"
        if len(receivers) > 3500:
            await context.bot.send_message(chat_id=update.effective_chat.id,
                                     text=get_text('MESSAGE_TO_SPAM').format(len(students), receivers))
            receivers = ''
    await context.bot.send_message(chat_id=update.effective_chat.id,
                             text=get_text('MESSAGE_TO_SPAM').format(len(students), receivers))
    return SPAM_MESSAGE


async def ask_spam_message_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chats = get_chats()
    current_chat_id = update.effective_chat.id
    message_type = "text"
    message_caption = update.message.caption
    if len(update.message.photo) > 0:
        message_type = "photo"
    if update.message.video:
        print(update.message.video.get_file().file_id)
        message_type = "video"
    try:
        for chat in chats:
            student = find_student(chat)
            try:
                match message_type:
                    case "text":
                        await context.bot.send_message(chat_id=int(chat), text=update.message.text)
                    case "photo":
                        await context.bot.send_photo(chat_id=int(chat), photo=update.message.photo[-1].file_id,
                                               caption=message_caption)
                    case "video":
                        video_file = update.message.video.get_file()
                        await context.bot.send_video(chat_id=int(chat), video=video_file.file_id,
                                               caption=message_caption)
                    case _:
                        return await context.bot.send_message(chat_id=current_chat_id, text="invalid message type")
                time.sleep(1)
                await context.bot.send_message(chat_id=current_chat_id, text=f'sent to {student.name}, id = {student.id}')
                time.sleep(1)
            except telegram.error.Unauthorized:
                await report_error(context.bot, current_chat_id, f'{student.name} has blocked me((')
            except telegram.error.BadRequest:
                await report_error(context.bot, current_chat_id, f'{student.name} has not yet contacted me')
        await context.bot.send_message(chat_id=current_chat_id, text='sentAll')
    except:
        await context.bot.send_message(chat_id=int(read_config('SUPER_ADMIN_ID')), text=traceback.format_exc())
        if current_chat_id != int(read_config('SUPER_ADMIN_ID')):
            time.sleep(1)
            await context.bot.send_message(chat_id=update.effective_chat.id, text=traceback.format_exc())
    finally:
        return ConversationHandler.END


async def report_error(bot, chat_id, msg):
    await bot.send_message(chat_id=int(read_config('SUPER_ADMIN_ID')), text=msg)
    if chat_id != int(read_config('SUPER_ADMIN_ID')):
        time.sleep(1)
        await bot.send_message(chat_id=chat_id, text=msg)


async def show_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(chat_id=update.effective_chat.id, text=get_text('MENU'), reply_markup=get_menu_markup())


async def send_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(chat_id=update.effective_chat.id, text=get_text('LOCATION'), parse_mode=ParseMode.HTML)


async def send_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(chat_id=update.effective_chat.id, text=get_text('SCHEDULE'))


async def send_interview(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(chat_id=update.effective_chat.id, text=get_text('INTERVIEW'))


async def send_tutor_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(chat_id=update.effective_chat.id, text=get_text('TUTOR_TIME'), reply_markup=None)


async def send_about_us(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(chat_id=update.effective_chat.id, text=get_text('ABOUT_US'), parse_mode=ParseMode.HTML)


async def send_connect(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(chat_id=update.effective_chat.id, text=get_text('GOT_QUESTIONS'))


async def close_registration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_chat.id):
        return
    global REGISTRATION_IS_CLOSED
    REGISTRATION_IS_CLOSED = True
    await context.bot.send_message(chat_id=update.effective_chat.id, text=get_text('REGISTRATION_CLOSED'))


async def open_registration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_chat.id):
        return
    global REGISTRATION_IS_CLOSED
    REGISTRATION_IS_CLOSED = False
    await context.bot.send_message(chat_id=update.effective_chat.id, text=get_text('REGISTRATION_OPENED'))


async def restart_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_chat.id):
        return
    await context.bot.send_message(chat_id=update.effective_chat.id, text=get_text('RESTART_BOT'))
    os.execv(sys.executable, [sys.executable] + sys.argv)


def main():
    print("start")
    update_texts()
    sync_local_students()
    backup_table()
    print('ready')
    
    application = Application.builder().token(read_config("BOT_TOKEN")).build()
    
    application.add_handler(CommandHandler('start', start_command))
    application.add_handler(CommandHandler('menu', show_menu))
    application.add_handler(MessageHandler(filters.Regex(f"^{get_text('LOCATION_BUTTON')}$"), send_location))
    application.add_handler(MessageHandler(filters.Regex(f"^{get_text('SCHEDULE_BUTTON')}$"), send_schedule))
    application.add_handler(MessageHandler(filters.Regex(f"^{get_text('INTERVIEW_BUTTON')}$"), send_interview))
    application.add_handler(MessageHandler(filters.Regex(f"^{get_text('TUTOR_TIME_BUTTON')}$"), send_tutor_time))
    application.add_handler(MessageHandler(filters.Regex(f"^{get_text('ABOUT_US_BUTTON')}$"), send_about_us))
    application.add_handler(MessageHandler(filters.Regex(f"^{get_text('GOT_QUESTIONS_BUTTON')}$"), send_connect))
    
    send_spam_conversation_handler = ConversationHandler(
        entry_points=[CommandHandler('spam_message', spam_message)],
        states={
            SPAM_MESSAGE: [MessageHandler(filters.TEXT & (~ filters.COMMAND), ask_spam_message_text)],
        },
        fallbacks=[CommandHandler('cancel', cancel_conversation)]
    )
    
    register_conversation_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex(f"^{get_text('REGISTRATION_BUTTON')}$"), ask_name)],
        states={
            ENTER_PHONE: [MessageHandler(filters.TEXT & (~ filters.COMMAND), ask_phone)],
            ENTER_SEX: [MessageHandler(filters.TEXT & (~ filters.COMMAND), ask_sex)],
            ENTER_UNI: [MessageHandler(filters.TEXT & (~ filters.COMMAND), ask_uni)],
            ENTER_COURSE: [MessageHandler(filters.TEXT & (~ filters.COMMAND), ask_course)],
            ENTER_VISITED: [MessageHandler(filters.TEXT & (~ filters.COMMAND), ask_visited)],
            SPECIFY_VISITED: [MessageHandler(filters.TEXT & (~ filters.COMMAND), specify_visited)],
            ENTER_HOW_COME: [CallbackQueryHandler(button_how_come, pattern='next|\\d')],
            ENTER_ENGLISH_LEVEL: [MessageHandler(filters.TEXT & (~ filters.COMMAND), ask_english_level)],
            ENTER_RELIGIOUS: [MessageHandler(filters.TEXT & (~ filters.COMMAND), ask_religious)],
            EXIT_CONVERSATION: [MessageHandler(filters.TEXT & (~ filters.COMMAND), exit_conversation)]
        },
        fallbacks=[CommandHandler('restart_registration', finish_conversation)],
    )
    
    application.add_handler(register_conversation_handler)
    application.add_handler(CommandHandler('restart_registration', finish_conversation))
    application.add_handler(CommandHandler('close_registration', close_registration))
    application.add_handler(CommandHandler('open_registration', open_registration))
    application.add_handler(CommandHandler('restart_bot', restart_bot))
    application.add_handler(send_spam_conversation_handler)
    
    application.run_polling()

if __name__ == '__main__':
    main()