"""Optional official MCP v1 adapter. Fake-only. No listener or credential loading."""
import contextlib
import json
from core import MailService, NOTICE
from fixtures import FakeIMAP
from http_guard import Guard

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
    from mcp.types import Tool, ToolAnnotations, TextContent, CallToolResult
    from starlette.applications import Starlette
    from starlette.routing import Route
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
    return Guard(app, token)

if __name__ == '__main__':
    raise SystemExit('No automatic startup. Read README.md; SDK review and integration approval required.')
