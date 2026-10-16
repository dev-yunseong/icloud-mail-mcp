"""Optional official MCP v1 adapter. Fake-only. No listener or credential loading."""
import contextlib
import json
import logging
from core import MailService, NOTICE
from fixtures import FakeIMAP
from http_guard import Guard, PRIVATE_REQUEST

class PrivateRequestFilter(logging.Filter):
    def filter(self, record):
        if PRIVATE_REQUEST.get():
            record.msg, record.args = 'Private MCP event (details redacted)', ()
            record.exc_info = record.exc_text = record.stack_info = None
        return True

SCHEMAS = {
    'list_mailboxes': {},
    'search': {'mailbox': {'type':'string','enum':['INBOX']},
               'query': {'type':'string','minLength':1,'maxLength':200,'pattern':'^[ -~]+$'},
               'limit': {'type':'integer','minimum':1,'maximum':50}},
    'read_message': {'mailbox': {'type':'string','enum':['INBOX']},
                     'uid': {'type':'integer','minimum':1,'maximum':4294967295},
                     'uidvalidity': {'type':'integer','minimum':1,'maximum':4294967295}}
}

def create_app(token):
    # Import only when explicitly requested; no dependency installation side effects.
    from mcp.server.lowlevel import Server
    from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
    from mcp.types import Tool, ToolAnnotations, TextContent, CallToolResult, ClientRequest, ClientNotification, JSONRPCMessage
    from starlette.applications import Starlette
    from starlette.routing import Route
    # Only this application's request context is redacted, not unrelated SDK use.
    for name in ('mcp.server.lowlevel.server','mcp.server.streamable_http',
                 'mcp.server.streamable_http_manager'):
        logger = logging.getLogger(name)
        if not any(isinstance(f, PrivateRequestFilter) for f in logger.filters):
            logger.addFilter(PrivateRequestFilter())
    service = MailService(FakeIMAP)
    server = Server('icloud-readonly-fake-demo', instructions=NOTICE)

    @server.list_tools()
    async def list_tools():
        return [Tool(name=name, description='FAKE DATA ONLY. Bounded read-only mail operation. ' + NOTICE,
                     inputSchema={'type':'object','properties':props,'additionalProperties':False,
                                  'required': {'search':['query'],'read_message':['uid','uidvalidity']}.get(name, [])},
                     annotations=ToolAnnotations(readOnlyHint=True,destructiveHint=False,
                                                 idempotentHint=True,openWorldHint=False))
                for name, props in SCHEMAS.items()]

    @server.call_tool(validate_input=False)
    async def call_tool(name, arguments):
        result = service.call(name, arguments)
        return CallToolResult(isError=not result['ok'],
                              content=[TextContent(type='text',text=json.dumps(result, ensure_ascii=False))])

    manager = StreamableHTTPSessionManager(app=server, event_store=None,
                                           json_response=True, stateless=True)
    @contextlib.asynccontextmanager
    async def lifespan(app):
        async with manager.run():
            yield
    class Endpoint:
        async def __call__(self, scope, receive, send):
            await manager.handle_request(scope, receive, send)
    app = Starlette(debug=False, routes=[Route('/mcp', endpoint=Endpoint(),
                                              methods=['POST'])], lifespan=lifespan)
    def validate_body(body):
        # Validate before SDK diagnostic logging can include malformed inputs.
        def unique_pairs(pairs):
            result = {}
            for key, value in pairs:
                if key in result: raise ValueError('duplicate_key')
                result[key] = value
            return result
        try:
            data = json.loads(body, object_pairs_hook=unique_pairs,
                              parse_constant=lambda value: (_ for _ in ()).throw(ValueError()))
            JSONRPCMessage.model_validate(data)
            if type(data) is not dict: return False
            method = data.get('method')
            if method == 'notifications/initialized':
                ClientNotification.model_validate(data)
                return 'id' not in data
            if method not in ('initialize','ping','tools/list','tools/call'): return False
            if 'id' not in data: return False
            ClientRequest.model_validate(data)
            if method == 'tools/call' and data['params']['name'] not in SCHEMAS: return False
            return True
        except Exception:
            return False
    return Guard(app, token, validate_body)

if __name__ == '__main__':
    raise SystemExit('No automatic startup. Read README.md; SDK review and integration approval required.')
