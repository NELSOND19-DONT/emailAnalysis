"""Read-only Gmail import; no mailbox mutations or attachment fetches."""
import base64
import hashlib
import tempfile
from datetime import datetime, timedelta
from email.message import EmailMessage
from email.utils import format_datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from core import ROOT

SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

def connect():
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
    except ImportError as e:
        raise RuntimeError('Run SETUP_GMAIL.cmd to install Gmail dependencies, then restart START.cmd.') from e
    private = ROOT / 'private'; private.mkdir(exist_ok=True)
    token = private / 'gmail-token.json'
    client = private / 'gmail-client.json'
    credentials = Credentials.from_authorized_user_file(str(token), SCOPES) if token.exists() else None
    if credentials and set(credentials.scopes or []) != set(SCOPES):
        raise RuntimeError('Remove private/gmail-token.json and sign in again with read-only permissions.')
    if not credentials or not credentials.valid:
        if credentials and credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())
        else:
            if not client.exists():
                raise RuntimeError('Create a Google OAuth Desktop client and save its downloaded JSON as private/gmail-client.json. See README.')
            flow = InstalledAppFlow.from_client_secrets_file(str(client), SCOPES)
            credentials = flow.run_local_server(host='localhost', port=0, timeout_seconds=180)
        token.write_text(credentials.to_json(), encoding='utf-8')
    return build('gmail', 'v1', credentials=credentials, cache_discovery=False)

def query_for(config):
    # Epoch boundaries avoid Gmail's default Pacific-time date interpretation.
    zone = ZoneInfo('Europe/Berlin')
    terms = ['in:inbox']
    if config.get('start_date'):
        start = datetime.fromisoformat(config['start_date']).replace(tzinfo=zone)
        terms.append(f'after:{int(start.timestamp()) - 1}')
    if config.get('end_date'):
        end = datetime.fromisoformat(config['end_date']).replace(tzinfo=zone) + timedelta(days=1)
        terms.append(f'before:{int(end.timestamp())}')
    return ' '.join(terms)

def body_parts(payload):
    if payload.get('filename'):
        return []
    headers = {h['name'].lower(): h['value'] for h in payload.get('headers', [])}
    if headers.get('content-disposition', '').lower().startswith('attachment'):
        return []
    parts = []
    mime = payload.get('mimeType', '')
    data = payload.get('body', {}).get('data')
    if mime in ('text/plain', 'text/html') and data:
        decoded = base64.urlsafe_b64decode(data + '=' * (-len(data) % 4))
        import re
        charset = re.search(r'charset=["\x27]?([^;"\x27\s]+)', headers.get('content-type', ''), re.I)
        try:
            content = decoded.decode(charset[1] if charset else 'utf-8', errors='replace')
        except LookupError:
            content = decoded.decode('utf-8', errors='replace')
        parts.append((mime, content))
    for part in payload.get('parts', []):
        parts.extend(body_parts(part))
    return parts

def import_gmail(store, service=None, progress=None):
    service = service or connect()
    account = service.users().getProfile(userId='me').execute()['emailAddress']
    api = service.users().messages()
    query = query_for(store.config)
    token = None
    totals = dict(added=0, duplicates=0, skipped=0, errors=0, examined=0, limit_reached=False)
    with tempfile.TemporaryDirectory() as temporary:
        path = Path(temporary) / 'message.eml'
        while True:
            page = api.list(userId='me', q=query, maxResults=100, pageToken=token).execute()
            for item in page.get('messages', []):
                limit = store.config.get('max_emails')
                if limit is not None and totals['examined'] >= limit:
                    totals['limit_reached'] = True
                    return totals
                totals['examined'] += 1
                data = api.get(userId='me', id=item['id'], format='full').execute()
                headers = {h['name'].lower(): h['value'] for h in data['payload'].get('headers', [])}
                message = EmailMessage()
                for key in ['from', 'subject', 'message-id', 'references', 'in-reply-to']:
                    if headers.get(key): message[key] = headers[key]
                if not message.get('Message-ID'):
                    account_id = hashlib.sha256(account.encode()).hexdigest()[:24]
                    message['Message-ID'] = f"<gmail-{account_id}-{item['id']}@email-analysis.local>"
                date = datetime.fromtimestamp(int(data['internalDate']) / 1000, ZoneInfo('Europe/Berlin'))
                message['Date'] = format_datetime(date)
                parts = body_parts(data['payload'])
                plain = [content for mime, content in parts if mime == 'text/plain']
                content = '\n'.join(plain or [content for mime, content in parts if mime == 'text/html'])
                message.set_content(content, subtype='plain' if plain else 'html')
                path.write_bytes(message.as_bytes())
                result = store.import_files([path])
                for key in ['added', 'duplicates', 'skipped', 'errors']: totals[key] += result[key]
                # Gmail provides authoritative thread IDs; preserve corrections on repeat import.
                mid = str(message['Message-ID'])
                store.db.execute('UPDATE emails SET thread=? WHERE id IN (SELECT email_id FROM message_ids WHERE message_id=?)', (f"gmail:{account}:{data['threadId']}", mid))
                store.db.commit()
                if progress: progress(totals.copy())
            token = page.get('nextPageToken')
            if not token: break
    return totals
