from trello import TrelloClient
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
import os.path
import pickle
import datetime
import json

API_KEY = os.getenv('TRELLO_API_KEY')
API_TOKEN = os.getenv('TRELLO_API_TOKEN')

BOARD_ID = os.getenv('TRELLO_BOARD_ID')
WORKING_LIST_ID = os.getenv('TRELLO_WORKING_LIST_ID')
DONE_LIST_ID = os.getenv('TRELLO_DONE_LIST_ID')
REVIEW_LIST_ID = os.getenv('TRELLO_REVIEW_LIST_ID')

CALENDAR_ID = os.getenv('GOOGLE_CALENDAR_ID')


# Trello API Setup
trello = TrelloClient(
    api_key=API_KEY,
    token=API_TOKEN
)


board_id = BOARD_ID
lists = [WORKING_LIST_ID, DONE_LIST_ID, REVIEW_LIST_ID]


def get_todays_tasks_from_trello():
    """Get all Trello cards assigned to the user and due today from specified lists."""
    board = trello.get_board(board_id)

    # Combine cards from both lists
    all_cards = []

    for list_id in lists:
        list_raw = board.get_list(list_id)
        all_cards += list_raw.list_cards()

    # Filter cards assigned to the user with a due date of today
    today = datetime.datetime.now().date()
    todays_tasks = [
        card for card in all_cards if card.due_date and card.due_date.date() == today]

    return todays_tasks


# Google API Setup
SCOPES = ['https://www.googleapis.com/auth/calendar']


def google_authenticate():
    """Authenticate and return the Google API service."""
    creds = None

    # Use the credentials from the environment variable
    if os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as token:
            creds = pickle.load(token)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            # Load credentials from environment variable
            credentials_json = os.getenv('GOOGLE_CREDENTIALS_JSON')
            credentials_info = json.loads(credentials_json)

            flow = InstalledAppFlow.from_client_config(
                credentials_info, SCOPES)
            creds = flow.run_local_server(port=0)

        # Save the credentials for the next run
        with open('token.pickle', 'wb') as token:
            pickle.dump(creds, token)

    return creds


def check_if_task_exists_in_calendar(task_id, creds):
    """Check if a Trello task already exists in Google Calendar."""
    service = build('calendar', 'v3', credentials=creds)
    events_result = service.events().list(calendarId=CALENDAR_ID).execute()
    events = events_result.get('items', [])
    for event in events:
        if 'description' in event and event['description'] == task_id:
            return event  # Return the existing event
    return None


def update_google_calendar_event(event, task, creds):
    """Update an existing Google Calendar event with the new details from Trello."""
    service = build('calendar', 'v3', credentials=creds)
    start = datetime.datetime.now().isoformat()
    end = (datetime.datetime.now() + datetime.timedelta(hours=1)).isoformat()
    task_due = convert_trello_date_to_calendar(
        task.badges.get('due')) if task.badges.get('due') else None
    task_start = convert_trello_date_to_calendar(
        task.badges.get('start')) if task.badges.get('start') else None
    if task_due and task_start:
        start = task_start.isoformat()
        end = task_due.isoformat()
    elif task_due:
        end = task_due.isoformat()
    elif task_start:
        start = task_start.isoformat()
        end = (task_start + datetime.timedelta(hours=1)).isoformat()
    event['summary'] = task.name
    event['start'] = {
        'dateTime': start,
        'timeZone': 'UTC',
    }
    event['end'] = {
        'dateTime': end,
        'timeZone': 'UTC',
    }
    service.events().update(calendarId=CALENDAR_ID,
                            eventId=event['id'], body=event).execute()


def add_task_to_google_calendar(task, creds):
    service = build('calendar', 'v3', credentials=creds)
    start = datetime.datetime.now().isoformat()
    end = (datetime.datetime.now() + datetime.timedelta(hours=1)).isoformat()
    task_due = convert_trello_date_to_calendar(
        task.badges.get('due')) if task.badges.get('due') else None
    task_start = convert_trello_date_to_calendar(
        task.badges.get('start')) if task.badges.get('start') else None
    if task_due and task_start:
        start = task_start.isoformat()
        end = task_due.isoformat()
    elif task_due:
        end = task_due.isoformat()
    elif task_start:
        start = task_start.isoformat()
        end = (task_start + datetime.timedelta(hours=1)).isoformat()
    event = {
        'summary': task.name,
        'description': task.id,  # Use Trello card ID as description to avoid duplicates
        'start': {
            'dateTime': start,
            'timeZone': 'UTC',
        },
        'end': {
            'dateTime': end,
            'timeZone': 'UTC',
        }
    }
    service.events().insert(calendarId=CALENDAR_ID, body=event).execute()


def check_if_task_exists_in_sheet(task_id, creds):
    """Check if a Trello task already exists in Google Sheets."""
    service = build('sheets', 'v4', credentials=creds)
    sheet = service.spreadsheets()
    result = sheet.values().get(
        spreadsheetId='YOUR_SPREADSHEET_ID',
        range='Sheet1!A:A'
    ).execute()
    values = result.get('values', [])
    for row in values:
        if task_id in row:
            return True
    return False


def add_task_to_google_sheets(task, creds):
    service = build('sheets', 'v4', credentials=creds)
    sheet = service.spreadsheets()
    values = [[task.id, task.name, task.list_id]]  # Include Trello card ID
    body = {'values': values}
    result = sheet.values().append(
        spreadsheetId='YOUR_SPREADSHEET_ID',
        range='Sheet1!A1',
        valueInputOption='RAW',
        body=body
    ).execute()


def convert_trello_date_to_calendar(trello_date):
    """Convert Trello date to Google Calendar ISO 8601 format."""
    if not trello_date:
        return None
    dt = datetime.datetime.strptime(trello_date, '%Y-%m-%dT%H:%M:%S.%fZ')

    return dt


def main():
    creds = google_authenticate()
    tasks = get_todays_tasks_from_trello()

    for task in tasks:
        event = check_if_task_exists_in_calendar(task.id, creds)
        # Check if task already exists in Calendar and Sheets
        if event is None:
            # Add task to Google Calendar and Sheets
            add_task_to_google_calendar(task, creds)
        else:
            # Update task in Google Calendar
            event = check_if_task_exists_in_calendar(task.id, creds)
            update_google_calendar_event(event, task, creds)


if __name__ == '__main__':
    if API_KEY and API_TOKEN and BOARD_ID and WORKING_LIST_ID and DONE_LIST_ID and REVIEW_LIST_ID and CALENDAR_ID:
        main()
    else:
        print('Missing environment variables.')
