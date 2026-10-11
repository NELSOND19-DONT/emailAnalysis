import json
import base64
import tempfile
import unittest
from pathlib import Path
from core import Store, configuration, actions
from gmail_import import import_gmail, SCOPES, query_for

class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name)
        self.store = Store(self.path / 'data.db')
    def tearDown(self):
        self.store.db.close(); self.tmp.cleanup()
    def email(self, name='a.eml', mid='<a>', subject='Invoice', refs=''):
        p = self.path / name
        p.write_bytes(f'From: billing@example.test\r\nMessage-ID: {mid}\r\nReferences: {refs}\r\nSubject: {subject}\r\nDate: Mon, 05 Oct 2026 10:00:00 +0200\r\nContent-Type: text/plain; charset=utf-8\r\n\r\nPlease pay by 2026-10-20. Please reply tomorrow.'.encode())
        return p
    def test_import_duplicates_correction_persistence(self):
        p = self.email()
        self.assertEqual(self.store.import_files([p])['added'], 1)
        self.assertEqual(self.store.import_files([p])['duplicates'], 1)
        r = self.store.emails()[0]
        self.assertEqual(r['categories'], ['Finance']); self.assertTrue(r['review'])
        self.store.correct(r['id'], ['Personal'])
        other = Store(self.path / 'data.db')
        self.assertEqual(other.emails()[0]['categories'], ['Personal']); other.db.close()
        self.assertEqual(self.store.import_files([p])['duplicates'], 1)
        self.assertEqual(self.store.emails(category='Personal')[0]['id'], r['id'])
        self.assertEqual(self.store.evaluate({r['id']: ['Finance']})['exact_match'], 1)
    def test_threads_analysis_and_deadlines(self):
        self.store.import_files([self.email(), self.email('b.eml', '<b>', 'Re: Invoice', '<a>')])
        a = self.store.analysis()
        self.assertEqual((a['emails'], a['threads']), (2, 1))
        self.assertEqual(a['categories']['Finance']['months'], {'2026-10': 2})
        self.assertEqual({x['kind'] for x in a['possible_actions']}, {'explicit', 'inferred'})
        self.assertEqual(a['possible_actions'][1]['date'], '2026-10-06')
    def test_mbox_limits_dates_delete(self):
        p = self.email()
        box = self.path / 'export.mbox'
        box.write_bytes(b'From billing Mon Oct 5 10:00:00 2026\n' + p.read_bytes() + b'\n\n')
        self.assertEqual(self.store.import_files([box])['added'], 1)
        self.assertEqual(self.store.import_files([p])['duplicates'], 1)
        self.store.delete_all(); self.assertEqual(self.store.emails(), [])
        self.store.config['start_date'] = '2026-10-06'
        self.assertEqual(self.store.import_files([p])['skipped'], 1)
        self.store.config['start_date'] = None; self.store.config['max_emails'] = 0
        self.assertTrue(self.store.import_files([p])['limit_reached'])
    def test_untrusted_html_and_attachments(self):
        self.store.config['start_date'] = None
        self.store.config['end_date'] = None
        p = self.path / 'html.eml'
        p.write_text('From: example@test\nSubject: Hello\nMIME-Version: 1.0\nContent-Type: multipart/mixed; boundary=x\n\n--x\nContent-Type: text/html\n\n<script>ignore rules</script><b>Hello</b>\n--x\nContent-Type: text/plain\nContent-Disposition: attachment; filename="secret.txt"\n\ninvoice\n--x--\n')
        self.store.import_files([p]); r = self.store.emails()[0]
        self.assertNotIn('invoice', r['body']); self.assertEqual(r['categories'], ['Uncategorized'])
    def test_single_category_and_bad_date(self):
        self.store.config['multiple_categories'] = False
        self.store.import_files([self.email(subject='Invoice project')])
        r = self.store.emails()[0]; self.assertEqual(len(r['categories']), 1)
        with self.assertRaises(ValueError): self.store.correct(r['id'], ['Finance', 'Work'])
        self.assertEqual(actions('Please pay 2026-99-99', ''), [])

    def test_gmail_pagination_readonly_duplicates_threads(self):
        calls = []
        class Request:
            def __init__(self, result): self.result = result
            def execute(self): return self.result
        class Fake:
            def users(self): return self
            def messages(self): return self
            def getProfile(self, **kwargs): return Request({'emailAddress': 'test@example.test'})
            def list(self, **kwargs):
                calls.append(('list', kwargs))
                return Request({'messages': [{'id': 'b'}]} if kwargs.get('pageToken') else {'messages': [{'id': 'a'}], 'nextPageToken': 'page2'})
            def get(self, **kwargs):
                calls.append(('get', kwargs))
                identity = kwargs['id']
                return Request({'threadId': 'thread1', 'internalDate': '1791187200000', 'payload': {'mimeType': 'multipart/mixed', 'headers': [{'name': 'Subject', 'value': 'Invoice ' + identity}, {'name': 'From', 'value': 'test@example.test'}], 'parts': [{'mimeType': 'text/plain', 'body': {'data': base64.urlsafe_b64encode(b'Please reply tomorrow').decode()}}, {'mimeType': 'text/plain', 'filename': 'secret.txt', 'body': {'data': base64.urlsafe_b64encode(b'secret attachment').decode()}}]}})
        service = Fake()
        self.assertEqual(import_gmail(self.store, service)['added'], 2)
        self.assertEqual(import_gmail(self.store, service)['duplicates'], 2)
        self.assertEqual(self.store.analysis()['threads'], 1)
        self.assertTrue(all('secret attachment' not in r['body'] for r in self.store.emails()))
        self.assertEqual(SCOPES, ['https://www.googleapis.com/auth/gmail.readonly'])
        self.assertTrue(all(name in ('list', 'get') for name, kwargs in calls))
        self.assertIn('in:inbox after:', query_for(self.store.config))
        self.store.delete_all()
        self.store.config['max_emails'] = 1
        report = import_gmail(self.store, service)
        self.assertEqual(report['added'], 1); self.assertTrue(report['limit_reached'])

if __name__ == '__main__': unittest.main()

