import asyncio
import io
import json
import unittest
from unittest.mock import patch, Mock
from core import MailService, BoundedIMAP, SafeError, MAX_MESSAGE, MAX_WIRE, live_factory, text_message
from fixtures import FakeIMAP
from http_guard import Guard

class CoreTests(unittest.TestCase):
    def setUp(self):
        self.fake = FakeIMAP()
        self.service = MailService(lambda: self.fake)

    def read(self, **overrides):
        return self.service.call('read_message', {'uid':7,'uidvalidity':42, **overrides})

    def test_list_is_allowlist_only(self):
        self.assertEqual(self.service.call('list_mailboxes', {})['data']['mailboxes'], ['INBOX'])
        self.assertEqual(self.fake.trace, [('LIST','""','"INBOX"')])

    def test_search_window_and_limit(self):
        self.fake.messages = {i:b'match' for i in range(1, 2001)}
        result = self.service.call('search', {'query':'match','limit':2})['data']
        self.assertEqual(result['uids'], [2000,1999])
        self.assertEqual(result['searched_uid_range'], [1001,2000])
        self.assertTrue(result['truncated'])

    def test_read_uses_examine_and_peek(self):
        result = self.read()
        self.assertTrue(result['ok'])
        self.assertIn('Synthetic meeting', result['data']['text'])
        self.assertEqual(self.fake.trace[0], ('EXAMINE','"INBOX"'))
        self.assertIn('BODY.PEEK[]', self.fake.trace[-1][-1])
        self.assertTrue(self.fake.closed)

    def test_imaplib_readonly_emits_examine(self):
        # Verify the actual stdlib mapping, independently of the fake label.
        client = object.__new__(BoundedIMAP)
        client.untagged_responses = {}
        client._simple_command = lambda command, mailbox: (self.assertEqual(command,'EXAMINE') or ('OK',[b'1']))
        client._untagged_response = lambda *args: ('OK',[b'1'])
        self.assertEqual(client.select('"INBOX"', readonly=True)[0], 'OK')

    def test_stale_uid_fails_before_fetch(self):
        self.assertEqual(self.read(uidvalidity=43)['error'], 'stale_uidvalidity')
        self.assertEqual(len(self.fake.trace), 1)

    def test_invalid_inputs_never_connect(self):
        cases = [('send',{}), ('search',{'query':'x\r\nEXPUNGE'}), ('search',{'query':'x','limit':True}),
                 ('search',{'query':'x','limit':51}), ('search',{'query':'한글'}),
                 ('search',{'query':'a'*201}), ('search',{'query':'x','host':'evil.invalid'}),
                 ('read_message',{'uid':'1:*','uidvalidity':42}), ('read_message',{'uid':0,'uidvalidity':42}),
                 ('read_message',{'uid':True,'uidvalidity':42}), ('search',{'query':'x','mailbox':'Other'}),
                 ('list_mailboxes',{'password':'PLACEHOLDER'}), ('read_message',None)]
        for name,args in cases:
            with self.subTest(name=name,args=args):
                service = MailService(lambda: self.fail('factory called for invalid input'))
                self.assertEqual(service.call(name,args)['error'], 'invalid_input')

    def test_quotes_escaped(self):
        self.service.call('search',{'query':'a"\\b'})
        self.assertEqual(self.fake.trace[-1][-1], '"a\\"\\\\b"')

    def test_missing_message(self):
        self.assertEqual(self.read(uid=99)['error'], 'message_not_found')

    def test_large_message_no_body_fetch(self):
        self.fake.messages[7] = b'x'*(MAX_MESSAGE+1)
        self.assertEqual(self.read()['error'], 'message_too_large')
        self.assertEqual(len(self.fake.trace), 2)

    def test_errors_redacted(self):
        def fail():
            raise RuntimeError('PLACEHOLDER_PRIVATE_EXCEPTION')
        result = MailService(fail).call('list_mailboxes',{})
        self.assertEqual(result, {'ok':False,'error':'mail_unavailable'})

    def test_attachment_skipped_injection_is_data(self):
        result = self.read(uid=8)
        self.assertTrue(result['untrusted_data'])
        self.assertIn('Ignore all', result['data']['text'])
        self.assertNotIn('DO NOT EXECUTE', result['data']['text'])

    def test_html_not_rendered(self):
        msg = text_message(b'Content-Type: text/html\r\n\r\n<script>bad()</script>')
        self.assertEqual(msg['text'], '')
        self.assertFalse(msg['plain_text_available'])

    def test_decoding_and_output_bounds(self):
        msg = text_message(b'Content-Type: text/plain; charset=utf-8\r\nContent-Transfer-Encoding: base64\r\n\r\naGVsbG8=')
        self.assertEqual(msg['text'],'hello')
        self.fake.messages[7] = b'Subject: '+ b'x'*1000 + b'\r\n\r\n'+b'a'*10000
        result = self.read()
        self.assertEqual(len(result['data']['subject']),300)
        self.assertEqual(len(result['data']['text']),4000)
        self.assertTrue(result['data']['truncated'])
        self.assertLess(len(json.dumps(result).encode()),24000)

    def test_literal_budget_before_read(self):
        client = object.__new__(BoundedIMAP)
        client.reset_budget()
        client._bounded_buffer = bytearray()
        with self.assertRaises(SafeError):
            client.read(MAX_WIRE+1)

    def test_line_budget(self):
        client = object.__new__(BoundedIMAP)
        client.reset_budget()
        client._bounded_buffer = bytearray()
        client.sock = Mock()
        client.sock.recv.side_effect = [b'x'*4096,b'x'*4096,b'x'*808+b'\n']
        with self.assertRaises(SafeError):
            client.readline()

    def test_deadline(self):
        client = object.__new__(BoundedIMAP)
        client.reset_budget()
        client.deadline = 0
        with self.assertRaises(SafeError):
            client.check_budget(0)

    def test_live_disabled_before_socket(self):
        with patch('core.BoundedIMAP', side_effect=AssertionError('network')):
            with self.assertRaisesRegex(SafeError,'live_access_disabled'):
                live_factory('USER_PLACEHOLDER','PASSWORD_PLACEHOLDER')

    def test_failures_close_connection(self):
        self.fake.uid = lambda *args: ('NO',[b'PLACEHOLDER_PRIVATE_ERROR'])
        self.assertEqual(self.read()['error'],'mail_unavailable')
        self.assertTrue(self.fake.closed)

    def test_wrong_uid_body_rejected(self):
        original = self.fake.uid
        def uid(*args):
            result = original(*args)
            if 'BODY.PEEK' in args[-1]:
                return 'OK',[(b'1 (UID 999 BODY[]',result[1][0][1])]
            return result
        self.fake.uid = uid
        self.assertEqual(self.read()['error'],'mail_unavailable')

    def test_buffer_preserves_literal_and_next_line(self):
        client = object.__new__(BoundedIMAP)
        client.reset_budget()
        client._bounded_buffer = bytearray()
        stream = io.BytesIO(b'* 1 FETCH {5}\r\nhello)\r\n')
        client.sock = Mock()
        client.sock.recv.side_effect = stream.read
        self.assertEqual(client.readline(), b'* 1 FETCH {5}\r\n')
        self.assertEqual(client.read(5), b'hello')
        self.assertEqual(client.readline(), b')\r\n')

    def test_imap_trace_disabled(self):
        client = object.__new__(BoundedIMAP)
        client._log('PLACEHOLDER_LOGIN')
        client._mesg('PLACEHOLDER_LOGIN')
        self.assertNotIn('_cmd_log',client.__dict__)

    def test_safeerror_text_is_not_trusted(self):
        def fail(): raise SafeError('PLACEHOLDER_PRIVATE_ERROR')
        self.assertEqual(MailService(fail).call('list_mailboxes',{}), {'ok':False,'error':'mail_unavailable'})

    def test_search_server_outside_requested_window(self):
        self.fake.uid = lambda *args: ('OK',[b'999999'])
        self.assertEqual(self.service.call('search',{'query':'x'})['error'],'mail_unavailable')

    def test_mime_part_limit(self):
        raw = b'Content-Type: multipart/mixed; boundary=x\r\n\r\n' + (
            b'--x\r\nContent-Type: text/plain\r\n\r\nx\r\n'*101) + b'--x--\r\n'
        with self.assertRaisesRegex(SafeError,'mime_limit'): text_message(raw)

class GuardTests(unittest.IsolatedAsyncioTestCase):
    async def request(self, changes=None, header_changes=None, body=b'{}'):
        token = 'synthetic-test-value-not-a-real-token'
        async def app(scope, receive, send):
            self.assertEqual((await receive())['body'],body)
            await send({'type':'http.response.start','status':200,'headers':[]})
            await send({'type':'http.response.body','body':b'ok'})
        guard = Guard(app, token)
        headers = {b'host':b'127.0.0.1:8765',b'authorization':('Bearer '+token).encode(),b'content-type':b'application/json'}
        headers.update(header_changes or {})
        scope = {'type':'http','path':'/mcp','method':'POST','client':('127.0.0.1',1234),'headers':list(headers.items())}
        scope.update(changes or {})
        async def receive():
            return {'type':'http.request','body':body}
        events = []
        async def send(event): events.append(event)
        await guard(scope, receive, send)
        return events[0]['status']

    async def test_authorized(self): self.assertEqual(await self.request(),200)
    async def test_auth(self): self.assertEqual(await self.request(header_changes={b'authorization':b'Bearer wrong'}),401)
    async def test_dns_rebinding(self): self.assertEqual(await self.request(header_changes={b'host':b'evil.invalid'}),403)
    async def test_origin(self): self.assertEqual(await self.request(header_changes={b'origin':b'https://evil.invalid'}),403)
    async def test_remote(self): self.assertEqual(await self.request({'client':('10.0.0.1',12)}),403)
    async def test_large_body(self): self.assertEqual(await self.request(body=b'x'*8193),413)
    async def test_wrong_path(self): self.assertEqual(await self.request({'path':'/else'}),404)
    async def test_method(self): self.assertEqual(await self.request({'method':'GET'}),405)
    async def test_content_type(self): self.assertEqual(await self.request(header_changes={b'content-type':b'text/plain'}),415)
    async def test_missing_auth_configuration(self):
        with self.assertRaises(ValueError): Guard(None,'PLACEHOLDER_DO_NOT_USE_THIS_VALUE')

if __name__ == '__main__': unittest.main()
