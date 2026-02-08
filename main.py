from __future__ import print_function
from telegram.error import BadRequest, Forbidden, NetworkError, TimedOut
from datetime import datetime, time as dtime
import json
import os
import os.path
import re
from pathlib import Path
import time
import traceback
import pandas as pd
import sys
import pytz
import socket
import requests
from urllib.parse import quote
from config import *

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup, \
    ReplyKeyboardRemove, Update
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler, \
    ConversationHandler, ContextTypes, JobQueue
from google.auth.transport.requests import Request
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
        self.registration_time = values[12]

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
            'religious': self.religious,
            'registration_time': self.registration_time
        }


#def read_config(value) -> str:
#    file = open('config.txt', encoding='UTF-8')
#    lines = file.readlines()
#    file.close()
#    for line in lines:
#        if line.split(" = ")[0] == value:
#            result_lines = line.split(" = ")[1].strip().split('\\n')
#            result = ''
#            for result_line in result_lines:
#                result += result_line + '\n'
#            return result[:len(result) - 1]
#    return ''


def connect_to_spreadsheets():
    creds = None
    scopes = [SCOPES]
    if os.path.exists('token.json'):
        try:
            creds = Credentials.from_authorized_user_file('token.json', scopes)
        except Exception as e:
            print(f"Error loading credentials: {e}")
            creds = None
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception as e:
                print(f"Error refreshing credentials: {e}")
                creds = None
        else:
            try:
                flow = InstalledAppFlow.from_client_secrets_file('credentials.json', scopes)
                creds = flow.run_local_server(port=0)
            except Exception as e:
                print(f"Error during OAuth flow: {e}")
                raise
    
    return creds


def get_sheets_values(spreadsheet_id, range_name):
    """Get values from Google Sheets using requests directly."""
    creds = connect_to_spreadsheets()
    if not creds or not creds.valid:
        print("No valid credentials available")
        return None
        
    access_token = creds.token
    # URL encode the range name to handle special characters
    encoded_range = quote(range_name)
    url = f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}/values/{encoded_range}"
    
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    
    try:
        # Force IPv4 to avoid IPv6 issues
        original_getaddrinfo = socket.getaddrinfo
        socket.getaddrinfo = lambda *args, **kwargs: original_getaddrinfo(*args, **kwargs)[:1]  # Force IPv4
        response = requests.get(url, headers=headers, timeout=30)
        socket.getaddrinfo = original_getaddrinfo  # Restore original function
    except Exception as e:
        print(f"Request to Sheets API failed: {e}")
        return None
        
    if response.status_code == 200:
        return response.json()
    else:
        print(f"Sheets API error: {response.status_code} - {response.text}")
        return None


def get_students_from_spreadsheets():
    try:
        spreadsheet_id = SAMPLE_SPREADSHEET_ID
        range_name = REGISTRATION_RANGE_NAME
        
        data = get_sheets_values(spreadsheet_id, range_name)
        if not data or 'values' not in data:
            print('No users found.')
            return pd.DataFrame([])
            
        registered_users = data['values']
        users_df = pd.DataFrame(registered_users)
        users_df.columns = users_df.iloc[0]
        users_df = users_df[1:]
        return users_df

    except Exception as err:
        print(f"Error getting students: {err}")
        return pd.DataFrame([])


def get_students_to_spam_from_spreadsheets():
    try:
        spreadsheet_id = SAMPLE_SPREADSHEET_ID
        range_name = SPAM_RANGE_NAME
        
        data = get_sheets_values(spreadsheet_id, range_name)
        if not data or 'values' not in data:
            print('No users found.')
            return pd.DataFrame([])
            
        registered_users = data['values']
        users_df = pd.DataFrame(registered_users)
        users_df.columns = users_df.iloc[0]
        users_df = users_df[1:]
        return users_df

    except Exception as err:
        print(f"Error getting students: {err}")
        return pd.DataFrame([])


def get_students_to_spam_from_spreadsheets():
    try:
        spreadsheet_id = SAMPLE_SPREADSHEET_ID
        range_name = SPAM_RANGE_NAME
        
        data = get_sheets_values(spreadsheet_id, range_name)
        if not data or 'values' not in data:
            print('No users found.')
            return pd.DataFrame([])
            
        users_to_spam = data['values']
        users_to_spam_df = pd.DataFrame(users_to_spam)
        users_to_spam_df.columns = users_to_spam_df.iloc[0]
        users_to_spam_df = users_to_spam_df[1:]
        return users_to_spam_df

    except Exception as err:
        print(f"Error getting spam users: {err}")
        return pd.DataFrame([])


def get_reserve_from_spreadsheets():
    try:
        spreadsheet_id = SAMPLE_SPREADSHEET_ID
        range_name = RESERVE_RANGE_NAME
        
        data = get_sheets_values(spreadsheet_id, range_name)
        if not data or 'values' not in data:
            print('No users found.')
            return pd.DataFrame([])
            
        users_to_spam = data['values']
        users_to_spam_df = pd.DataFrame(users_to_spam)
        users_to_spam_df.columns = users_to_spam_df.iloc[0]
        users_to_spam_df = users_to_spam_df[1:]
        return users_to_spam_df

    except Exception as err:
        print(f"Error getting spam users: {err}")
        return pd.DataFrame([])


def add_student(data: []):
    try:
        creds = connect_to_spreadsheets()
        if not creds:
            print("No credentials for adding student")
            return
            
        access_token = creds.token
        spreadsheet_id = SAMPLE_SPREADSHEET_ID
        
        # First get current data to determine where to append
        current_data = get_sheets_values(spreadsheet_id, REGISTRATION_RANGE_NAME)
        if current_data and 'values' in current_data:
            next_row = len(current_data['values']) + 1
        else:
            next_row = 2  # Header row + first data row
            
        range_name = f"A{next_row}:M{next_row}"
        url = f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}/values/{range_name}?valueInputOption=USER_ENTERED"
        
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
        
        body = {
            "values": [data]
        }
        
        # Force IPv4
        original_getaddrinfo = socket.getaddrinfo
        socket.getaddrinfo = lambda *args, **kwargs: original_getaddrinfo(*args, **kwargs)[:1]
        response = requests.put(url, headers=headers, json=body, timeout=30)
        socket.getaddrinfo = original_getaddrinfo
        
        if response.status_code == 200:
            print("Student added successfully")
            # Also update local CSV
            df = pd.read_csv('data/students.csv') if os.path.exists('data/students.csv') else pd.DataFrame(columns=[
                'id', 'name', 'phone', 'nickname', 'sex', 'uni', 'course', 
                'visited', 'specified_visited', 'how_come', 'english_level', 'religious'
            ])
            new_row = pd.DataFrame([data], columns=df.columns)
            df = pd.concat([df, new_row], ignore_index=True)
            df.to_csv('data/students.csv', index=False)
        else:
            print(f"Failed to add student: {response.status_code} - {response.text}")
            
    except Exception as e:
        print(f"Error in add_student: {e}")


def load_students_fromc_csv(filename: str) -> List[Student]:
    df = pd.read_csv('data/students.csv')
    return [Student([*row[0:13]]) for _, row in df.iterrows()]


def find_student(telegram_id: int):
    df = pd.concat([get_students_from_spreadsheets(), get_students_to_spam_from_spreadsheets()], ignore_index=True)
    if df.empty or not df.loc[df['id'] == telegram_id].values.flatten().tolist():
        return None
    return Student(df.loc[df['id'] == telegram_id].values.flatten().tolist())


def sync_local_students():
    try:
        df = get_students_from_spreadsheets()
        df.to_csv('data/students.csv', index=False)
    except Exception as e:
        print(f"Sync failed: {e}")
        # Continue with existing local data
    

def find_student_local(telegram_id: int):
    if not os.path.exists('data/students.csv'):
        return None
    df = pd.read_csv('data/students.csv')
    if df.empty or not df.loc[df['id'] == telegram_id].values.flatten().tolist():
        return None
    return Student(df.loc[df['id'] == telegram_id].values.flatten().tolist())


def backup_table():
    try:
        new_data = get_students_from_spreadsheets()
        if new_data.empty:
            print("No data to backup")
            return
        original_data = get_reserve_from_spreadsheets()
        original_data.loc[-1] = original_data.columns
        original_data.index = original_data.index + 1
        original_data = original_data.sort_index()    
        original_data.columns = new_data.columns

        final_data = pd.concat([original_data, new_data], ignore_index=True)
        final_data = final_data.drop_duplicates(subset='id', keep="last")
        empty_rows = pd.DataFrame({col: [""]*len(original_data) for col in final_data.columns})
        final_data = pd.concat([final_data, empty_rows], ignore_index=True)
        
        creds = connect_to_spreadsheets()
        if not creds:
            print("No credentials for backup")
            return
            
        access_token = creds.token
        spreadsheet_id = SAMPLE_SPREADSHEET_ID
        range_name = RESERVE_RANGE_NAME
        url = f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}/values/{range_name}?valueInputOption=USER_ENTERED"
        
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
        
        body = {
            "values": final_data.values.tolist()
        }
        
        # Force IPv4
        original_getaddrinfo = socket.getaddrinfo
        socket.getaddrinfo = lambda *args, **kwargs: original_getaddrinfo(*args, **kwargs)[:1]
        response = requests.put(url, headers=headers, json=body, timeout=30)
        socket.getaddrinfo = original_getaddrinfo
        
        if response.status_code == 200:
            print("Backup successful")
        else:
            print(f"Backup failed: {response.status_code} - {response.text}")
            
    except Exception as e:
        print(f"Error in backup_table: {e}")


def remove_student(telegram_id):
    try:
        df = get_students_from_spreadsheets()
        df = df.loc[df['id'] != str(telegram_id)]
        empty_rows = pd.DataFrame({col: [""]*10 for col in df.columns})
        final_data = pd.concat([df, empty_rows], ignore_index=True)
        print(final_data)

        
        # Update the entire sheet
        creds = connect_to_spreadsheets()
        if not creds:
            print("No credentials for remove_student")
            return
            
        access_token = creds.token
        spreadsheet_id = SAMPLE_SPREADSHEET_ID
        range_name = REGISTRATION_RANGE_NAME
        url = f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}/values/{range_name}?valueInputOption=USER_ENTERED"
        
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
        
        # Prepare data with header
        values = [final_data.columns.tolist()] + final_data.values.tolist()
        body = {
            "values": values
        }
        
        # Force IPv4
        original_getaddrinfo = socket.getaddrinfo
        socket.getaddrinfo = lambda *args, **kwargs: original_getaddrinfo(*args, **kwargs)[:1]
        response = requests.put(url, headers=headers, json=body, timeout=30)
        socket.getaddrinfo = original_getaddrinfo
        
        if response.status_code == 200:
            print("Student removed successfully")
            # Update local CSV
            df.to_csv('data/students.csv', index=False)
        else:
            print(f"Failed to remove student: {response.status_code} - {response.text}")
            
    except Exception as e:
        print(f"Error in remove_student: {e}")


def update_texts():
    try:
        spreadsheet_id = SAMPLE_SPREADSHEET_ID
        range_name = TEXTS_RANGE_NAME
        
        data = get_sheets_values(spreadsheet_id, range_name)
        if not data or 'values' not in data:
            print("No data found in the specified range")
            use_cached_texts()
            return
            
        questions = data['values']
        os.makedirs('data', exist_ok=True)
        with open("data/texts.json", "w", encoding='UTF-8') as file:
            data_df = pd.DataFrame(questions)
            dictionary = {}
            for row in data_df.values:
                if len(row) >= 2:
                    dictionary[row[0]] = row[1]
            json.dump(dictionary, file, indent=4, ensure_ascii=False)
        print("Texts updated successfully")
        
    except Exception as e:
        print(f"Error in update_texts: {e}")
        use_cached_texts()


def use_cached_texts():
    """Use locally cached texts if Google Sheets is unavailable"""
    try:
        if os.path.exists('data/texts.json'):
            print("Using cached texts from previous successful update")
            return True
        else:
            print("No cached texts available.")
            return False
    except Exception as e:
        print(f"Failed to use cached texts: {e}")
        return False


def get_menu_markup():
    keyboard = get_keyboard([
        get_text('REGISTRATION_BUTTON'), get_text('LOCATION_BUTTON'), get_text('SCHEDULE_BUTTON'),
        get_text('INTERVIEW_BUTTON'), get_text('TUTOR_TIME_BUTTON'), get_text('ABOUT_US_BUTTON'),
        get_text('GOT_QUESTIONS_BUTTON')
    ], 2)
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def get_text(text: str):
    try:
        if os.path.exists('data/texts.json'):
            with open('data/texts.json', encoding='UTF-8') as file:
                content = json.load(file)
                if content.get(text) is not None:
                    return content.get(text)
        return f"[{text}]"  # Return the key if not found
    except:
        return f"[{text}]"


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
        return ConversationHandler.END
    if find_student_local(update.effective_chat.id) is not None:
        await context.bot.send_message(chat_id=update.effective_chat.id, text=get_text('INVALID_REGISTRATION'),
                                 reply_markup=get_menu_markup())
        return ConversationHandler.END
    context.user_data.clear()
    context.user_data['id'] = update.effective_chat.id
    await context.bot.send_message(chat_id=update.effective_chat.id, text=get_text('ASK_NAME'),
                             parse_mode=ParseMode.HTML, reply_markup=ReplyKeyboardRemove())
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
            text=query.message.text + get_text('SPECIFY_VISITED_ANSWER').format(context.user_data["specified_visited"]),
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
    context.user_data['registration_time'] = str(datetime.now().strftime("%d.%m.%Y %H:%M"))
    await update.message.reply_text(get_text('END_REGISTRATION'))
    try:
        add_student(list(context.user_data.values()))
    except:
        await context.bot.send_message(chat_id=int(SUPER_ADMIN_ID), text=traceback.format_exc())
        await context.bot.send_message(chat_id=int(SUPER_ADMIN_ID),
                                 text=f'failed to register. user is '
                                      f'{context.user_data.get("name")}; {context.user_data.get("nickname")}')
        await context.bot.send_message(chat_id=int(SUPER_ADMIN_ID),
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
    admins = ADMIN_IDS.split(" ")
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
    message = update.message
    
    try:
        for chat in chats:
            student = find_student(chat)
            try:
                if message.photo:
                    await context.bot.send_photo(
                        chat_id=int(chat), 
                        photo=message.photo[-1].file_id,
                        caption=message.caption
                    )
                elif message.video:
                    await context.bot.send_video(
                        chat_id=int(chat), 
                        video=message.video.file_id,
                        caption=message.caption
                    )
                elif message.text:
                    await context.bot.send_message(
                        chat_id=int(chat), 
                        text=message.text
                    )        

                time.sleep(0.1)
                await context.bot.send_message(
                    chat_id=current_chat_id, 
                    text=f'sent to {student.name}, id = {student.id}'
                )
                time.sleep(0.1)
                
            except Forbidden as e:
                error_msg = f'{student.name} has blocked me' if "bot was blocked" in str(e).lower() else f'Permission error with {student.name}: {e}'
                await report_error(context.bot, current_chat_id, error_msg)
                
            except BadRequest as e:
                error_msg = f'{student.name} has not yet contacted me' if "chat not found" in str(e).lower() else f'Bad request for {student.name}: {e}'
                await report_error(context.bot, current_chat_id, error_msg)
                
            except Exception as e:
                await report_error(context.bot, current_chat_id, f'Error sending to {student.name}: {e}')
                
        await context.bot.send_message(chat_id=current_chat_id, text='sentAll')
        
    except Exception as e:
        await context.bot.send_message(chat_id=int(SUPER_ADMIN_ID), text=traceback.format_exc())
        if current_chat_id != int(SUPER_ADMIN_ID):
            await context.bot.send_message(chat_id=update.effective_chat.id, text=f"Error: {str(e)}")
    return ConversationHandler.END


async def report_error(bot, chat_id, msg):
    await bot.send_message(chat_id=int(SUPER_ADMIN_ID), text=msg)
    if chat_id != int(SUPER_ADMIN_ID):
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


async def send_daily_reminder(context: ContextTypes.DEFAULT_TYPE):
    message = "🌞 Good morning! Bot is running normally!"
    await context.bot.send_message(chat_id=int(SUPER_ADMIN_ID), text=message,parse_mode=ParseMode.HTML)


async def list_scheduled_jobs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_chat.id):
        await update.message.reply_text("Only admins can use this command.")
        return
    
    job_queue = context.application.job_queue
    if job_queue and job_queue.jobs():
        message = "📋 Scheduled Jobs:\n"
        for i, job in enumerate(job_queue.jobs()):
            message += f"{i+1}. {job.name} - Next run: {job.next_t}\n"
        await update.message.reply_text(message)
    else:
        await update.message.reply_text("No scheduled jobs running.")


def get_utc_time(hour: int, minute: int, timezone_str: str = "Europe/Kiev"):
    """Convert local time to UTC"""
    local_tz = pytz.timezone(timezone_str)
    local_time = dtime(hour, minute)
    naive_dt = datetime.combine(datetime.now(), local_time)
    local_dt = local_tz.localize(naive_dt)
    utc_time = local_dt.astimezone(pytz.UTC).time()
    return utc_time


def main():
    print("start")
    # Ensure data directory exists
    os.makedirs('data', exist_ok=True)
    
    # Update texts and sync students
    update_texts()
    backup_table()
    sync_local_students()
    
    print('ready')
    
    application = Application.builder().token(BOT_TOKEN).build()

    job_queue = application.job_queue

    if job_queue:
        job_queue.run_daily(send_daily_reminder, time=get_utc_time(9, 0), days=tuple(range(7)))
        job_queue.run_daily(send_daily_reminder, time=get_utc_time(21, 0), days=tuple(range(7)))

        print("Scheduled messages initialized")
    
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
            SPAM_MESSAGE: [MessageHandler(filters.ALL & (~ filters.COMMAND), ask_spam_message_text)],
        },
        fallbacks=[CommandHandler('cancel', cancel_conversation)],
        per_message=False
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
        per_message=False
    )
    
    application.add_handler(register_conversation_handler)
    application.add_handler(CommandHandler('restart_registration', finish_conversation))
    application.add_handler(CommandHandler('close_registration', close_registration))
    application.add_handler(CommandHandler('open_registration', open_registration))
    application.add_handler(CommandHandler('restart_bot', restart_bot))
    application.add_handler(send_spam_conversation_handler)
    application.add_handler(CommandHandler('list_jobs', list_scheduled_jobs))
    
    application.run_polling()

if __name__ == '__main__':
    main()