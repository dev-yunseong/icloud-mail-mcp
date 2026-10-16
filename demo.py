"""Offline demo. Never reads credentials or opens network connections."""
import json
from core import MailService
from fixtures import FakeIMAP

if __name__ == '__main__':
    service = MailService(FakeIMAP)
    for name, args in [('list_mailboxes', {}), ('search', {'query': 'meeting'}),
                       ('read_message', {'uid': 7, 'uidvalidity': 42})]:
        print(json.dumps({'tool': name, 'result': service.call(name, args)}, ensure_ascii=False))
