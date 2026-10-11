"""Offline email analysis. Email text is data; no code or AI execution."""
import hashlib
import html
import json
import mailbox
import re
import sqlite3
from collections import Counter
from datetime import datetime, timedelta
from email import policy
from email.parser import BytesParser
from email.utils import parsedate_to_datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent

def configuration(path=None):
    return json.loads(Path(path or (ROOT / 'config.json' if (ROOT / 'config.json').exists() else ROOT / 'config.example.json')).read_text(encoding='utf-8'))

def classify(sender, subject, body, config):
    matches = []
    for category, rules in config['categories'].items():
        hits = [(field, term) for field, value in [('sender', sender), ('subject', subject), ('body', body)]
                for term in rules.get(field, []) if term.casefold() in value.casefold()]
        if hits:
            confidence = min(.95, .55 + .15 * len(hits))
            matches.append((category, confidence, '; '.join(f'{field} contains {term!r}' for field, term in hits)))
    matches.sort(key=lambda item: (-item[1], item[0]))
    if not config['multiple_categories']:
        matches = matches[:1]
    return matches or [('Uncategorized', 0., 'No rule matched')]

def actions(body, date):
    result = []
    for sentence in re.split(r'[\n.!?]+', body):
        if not re.search(r'\b(please|must|due|deadline|respond|reply|submit|pay|action required)\b', sentence, re.I):
            continue
        explicit = re.findall(r'\b\d{4}-\d{2}-\d{2}\b', sentence)
        for value in explicit:
            try:
                datetime.fromisoformat(value)
            except ValueError:
                continue
            result.append({'text': sentence.strip(), 'date': value, 'kind': 'explicit'})
        if not explicit:
            relative = re.search(r'\b(today|tomorrow)\b', sentence, re.I)
            inferred = None
            if relative and date:
                inferred = (datetime.fromisoformat(date) + timedelta(days=relative[1].lower() == 'tomorrow')).date().isoformat()
            result.append({'text': sentence.strip(), 'date': inferred, 'kind': 'inferred' if inferred else 'undated'})
    return result

class Store:
    def __init__(self, path=None, config=None):
        self.config = config or configuration()
        path = Path(path or ROOT / 'private' / 'emails.db')
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript('''CREATE TABLE IF NOT EXISTS emails (
          id TEXT PRIMARY KEY, message_id TEXT, thread TEXT, sender TEXT, subject TEXT,
          date TEXT, body TEXT, classification TEXT, correction TEXT, actions TEXT);
          CREATE TABLE IF NOT EXISTS message_ids (message_id TEXT PRIMARY KEY, email_id TEXT);''')

    def import_files(self, paths):
        added = duplicates = skipped = errors = 0
        examined = 0
        for path in paths:
            path = Path(path)
            box = None
            try:
                if path.suffix.lower() == '.mbox':
                    box = mailbox.mbox(path, factory=lambda f: BytesParser(policy=policy.default).parse(f), create=False)
                    messages = iter(box)
                elif path.suffix.lower() == '.eml':
                    messages = [BytesParser(policy=policy.default).parsebytes(path.read_bytes())]
                else:
                    skipped += 1
                    continue
                for msg in messages:
                    if self.config['max_emails'] is not None and examined >= self.config['max_emails']:
                        return dict(added=added, duplicates=duplicates, skipped=skipped, errors=errors, limit_reached=True)
                    examined += 1
                    try:
                        sender, subject = str(msg.get('From', '')), str(msg.get('Subject', ''))
                        try:
                            date = parsedate_to_datetime(str(msg.get('Date', ''))).isoformat()
                        except (ValueError, TypeError, OverflowError):
                            date = ''
                        if any(self.config.get(k) and (not date or (date[:10] < self.config[k] if k == 'start_date' else date[:10] > self.config[k])) for k in ['start_date', 'end_date']):
                            skipped += 1
                            continue
                        part = msg.get_body(preferencelist=('plain', 'html'))
                        body = part.get_content() if part else ''
                        if part and part.get_content_type() == 'text/html':
                            body = html.unescape(re.sub('<[^>]+>', ' ', body))
                        mid = str(msg.get('Message-ID', '')).strip()
                        identity = hashlib.sha256(json.dumps([sender, subject, date, body], ensure_ascii=False).encode()).hexdigest()
                        if self.db.execute('SELECT 1 FROM emails WHERE id=?', (identity,)).fetchone() or (mid and self.db.execute('SELECT 1 FROM message_ids WHERE message_id=?', (mid,)).fetchone()):
                            duplicates += 1
                            continue
                        refs = re.findall(r'<[^>]+>', str(msg.get('References', '') or msg.get('In-Reply-To', '')))
                        thread = refs[0] if refs else mid or identity
                        self.db.execute('INSERT INTO emails VALUES (?,?,?,?,?,?,?,?,NULL,?)', (identity, mid, thread, sender, subject, date, body, json.dumps(classify(sender, subject, body, self.config)), json.dumps(actions(body, date))))
                        if mid:
                            self.db.execute('INSERT INTO message_ids VALUES (?,?)', (mid, identity))
                        added += 1
                    except (ValueError, TypeError, LookupError, UnicodeError):
                        errors += 1
            finally:
                if box is not None:
                    box.close()
                self.db.commit()
        return dict(added=added, duplicates=duplicates, skipped=skipped, errors=errors, limit_reached=False)

    def correct(self, identity, categories):
        if not categories or any(c not in self.config['categories'] and c != 'Uncategorized' for c in categories):
            raise ValueError('Choose configured categories')
        if not self.config['multiple_categories'] and len(categories) != 1:
            raise ValueError('Configuration allows one category')
        self.db.execute('UPDATE emails SET correction=? WHERE id=?', (json.dumps(list(dict.fromkeys(categories))), identity))
        self.db.commit()

    def emails(self, query='', category='', sender='', start='', end='', review=False):
        result = []
        for row in self.db.execute('SELECT * FROM emails ORDER BY date DESC'):
            row = dict(row)
            predicted = json.loads(row['classification'])
            row['categories'] = json.loads(row['correction']) if row['correction'] else [p[0] for p in predicted]
            row['review'] = not row['correction'] and any(p[1] < self.config['review_threshold'] for p in predicted)
            row['explanation'] = 'Manual correction' if row['correction'] else '; '.join(f'{p[0]} ({p[1]:.0%}): {p[2]}' for p in predicted)
            row['actions'] = json.loads(row['actions'])
            if query.casefold() not in (row['subject'] + row['body']).casefold() or sender.casefold() not in row['sender'].casefold(): continue
            if category and category not in row['categories']: continue
            if start and (not row['date'] or row['date'][:10] < start): continue
            if end and (not row['date'] or row['date'][:10] > end): continue
            if review and not row['review']: continue
            result.append(row)
        return result

    def analysis(self, rows=None):
        rows = self.emails() if rows is None else rows
        categories = {}
        for c in ['Uncategorized', *self.config['categories']]:
            supporting = [r for r in rows if c in r['categories']]
            categories[c] = {'emails': len(supporting), 'threads': len({r['thread'] for r in supporting}), 'common_senders': Counter(r['sender'] for r in supporting).most_common(5), 'months': dict(sorted(Counter(r['date'][:7] or 'Unknown' for r in supporting).items())), 'summary': [{'email_id': r['id'], 'subject': r['subject'], 'excerpt': r['body'][:180]} for r in supporting[:5]]}
        return {'emails': len(rows), 'threads': len({r['thread'] for r in rows}), 'categories': categories, 'possible_actions': [{'email_id': r['id'], **a} for r in rows for a in r['actions']]}

    def evaluate(self, labels):
        if not isinstance(labels, dict):
            raise ValueError('Labels must be an object mapping email IDs to category arrays')
        for expected in labels.values():
            if not isinstance(expected, list) or not expected or any(not isinstance(c, str) or c not in [*self.config['categories'], 'Uncategorized'] for c in expected):
                raise ValueError('Fill each label array with configured categories; use Uncategorized when appropriate')
        rows = {r['id']: r for r in self.emails()}
        tp = fp = fn = exact = count = 0
        unknown = []
        for identity, expected in labels.items():
            if identity not in rows:
                unknown.append(identity)
                continue
            # Evaluate the automatic prediction, never the stored human correction.
            predicted = {p[0] for p in json.loads(rows[identity]['classification'])}
            expected = set(expected)
            tp += len(predicted & expected); fp += len(predicted - expected); fn += len(expected - predicted)
            exact += predicted == expected; count += 1
        return {'sample_size': count, 'exact_match': exact / count if count else None, 'micro_precision': tp / (tp + fp) if tp + fp else None, 'micro_recall': tp / (tp + fn) if tp + fn else None, 'unknown_ids': unknown}

    def delete_all(self):
        self.db.executescript('DELETE FROM emails; DELETE FROM message_ids; VACUUM;')
