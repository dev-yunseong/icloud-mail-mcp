"""Dependency-free ASGI boundary, testable without starting a listener."""
import asyncio
import contextvars
import secrets

PRIVATE_REQUEST = contextvars.ContextVar('private_mail_request', default=False)

class Guard:
    def __init__(self, app, token, validate_body=None):
        if type(token) is not str or len(token) < 32 or not token.isascii() or token.startswith('PLACEHOLDER'):
            raise ValueError('authentication_required')
        self.app, self.token = app, token
        self.validate_body = validate_body
        self.busy = False

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        async def reject(status):
            await send({'type':'http.response.start','status':status,
                        'headers':[(b'content-type',b'text/plain'),(b'cache-control',b'no-store')]})
            await send({'type':'http.response.body','body':b'request_rejected'})
        headers = scope.get('headers', [])
        values = {}
        for name, value in headers:
            name = name.lower()
            if name in values:
                return await reject(400)
            values[name] = value
        if scope.get('client', ('',))[0] not in ('127.0.0.1', '::1'):
            return await reject(403)
        if values.get(b'host') != b'127.0.0.1:8765' or b'origin' in values:
            return await reject(403)
        supplied = values.get(b'authorization', b'')
        if not secrets.compare_digest(supplied, ('Bearer ' + self.token).encode()):
            return await reject(401)
        if scope.get('path') != '/mcp' or scope.get('query_string', b''):
            return await reject(404)
        if scope.get('method') != 'POST':
            return await reject(405)
        if values.get(b'content-type', b'').split(b';')[0] != b'application/json':
            return await reject(415)
        if self.busy:
            return await reject(429)
        self.busy = True
        context_token = PRIVATE_REQUEST.set(True)
        try:
            body = bytearray()
            async with asyncio.timeout(5):
                while True:
                    event = await receive()
                    if event['type'] != 'http.request':
                        return await reject(400)
                    body.extend(event.get('body', b''))
                    if len(body) > 8192:
                        return await reject(413)
                    if not event.get('more_body', False):
                        break
            if self.validate_body is not None and not self.validate_body(bytes(body)):
                return await reject(400)
            delivered = False
            async def replay():
                nonlocal delivered
                if not delivered:
                    delivered = True
                    return {'type':'http.request', 'body':bytes(body), 'more_body':False}
                return await receive()
            await self.app(scope, replay, send)
        except TimeoutError:
            await reject(408)
        finally:
            PRIVATE_REQUEST.reset(context_token)
            self.busy = False
