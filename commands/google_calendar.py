import os
import json
from google.oauth2 import service_account
from googleapiclient.discovery import build
from datetime import datetime, timedelta, timezone

SCOPES = ['https://www.googleapis.com/auth/calendar']
JST = timezone(timedelta(hours=9))

class GoogleCalendarManager:
    def __init__(self):
        # Renderの環境変数からJSONを読み込む
        creds_json = os.getenv("GOOGLE_CREDENTIALS_JSON")
        if creds_json:
            info = json.loads(creds_json)
            self.creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
            self.service = build('calendar', 'v3', credentials=self.creds)
        else:
            self.service = None

    def get_todays_events(self, calendar_id):
        if not self.service: return []
        
        now = datetime.now(JST)
        start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        end_of_day = now.replace(hour=23, minute=59, second=59, microsecond=0).isoformat()

        events_result = self.service.events().list(
            calendarId=calendar_id, timeMin=start_of_day,
            timeMax=end_of_day, singleEvents=True,
            orderBy='startTime'
        ).execute()
        return events_result.get('items', [])

    def add_event(self, calendar_id, title, start_dt):
        if not self.service: return
        
        event = {
            'summary': title,
            'start': {'dateTime': start_dt.isoformat(), 'timeZone': 'Asia/Tokyo'},
            'end': {'dateTime': (start_dt + timedelta(hours=1)).isoformat(), 'timeZone': 'Asia/Tokyo'},
        }
        return self.service.events().insert(calendarId=calendar_id, body=event).execute()