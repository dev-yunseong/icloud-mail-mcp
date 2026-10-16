"""Real SDK Streamable HTTP round trips over in-process ASGI; no listening sockets."""
import asyncio
import contextlib
import io
import json
import logging
import unittest
from unittest.mock import patch
import httpx
from server import create_app

TOKEN = 'synthetic-test-value-not-a-real-token'

class ProtocolTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.guard = create_app(TOKEN)
        self.started, self.stop = asyncio.Event(), asyncio.Event()
        async def lifetime():
            async with self.guard.app.router.lifespan_context(self.guard.app):
                self.started.set()
                await self.stop.wait()
        self.lifetime = asyncio.create_task(lifetime())
        await asyncio.wait_for(self.started.wait(),10)
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.guard,client=('127.0.0.1',1234)),
            base_url='http://127.0.0.1:8765',
            headers={'Authorization':'Bearer '+TOKEN,'Accept':'application/json, text/event-stream'})

    async def asyncTearDown(self):
        await self.client.aclose()
        self.stop.set()
        await self.lifetime

    async def rpc(self, method, params=None):
        message = {'jsonrpc':'2.0','id':1,'method':method}
        if params is not None: message['params'] = params
        return await self.client.post('/mcp',json=message)

    async def test_initialize(self):
        response = await self.rpc('initialize', {'protocolVersion':'2025-11-25',
            'capabilities':{},'clientInfo':{'name':'offline-test','version':'1'}})
        self.assertEqual(response.status_code,200,response.text)
        result = response.json()['result']
        self.assertEqual(result['serverInfo']['name'],'icloud-readonly-fake-demo')
        self.assertIn('tools',result['capabilities'])
        self.assertNotIn('prompts',result['capabilities'])
        self.assertNotIn('resources',result['capabilities'])

    async def test_only_readonly_tools_exposed(self):
        response = await self.rpc('tools/list')
        self.assertEqual(response.status_code,200,response.text)
        tools = response.json()['result']['tools']
        self.assertEqual({x['name'] for x in tools},{'list_mailboxes','search','read_message'})
        for tool in tools:
            self.assertTrue(tool['annotations']['readOnlyHint'])
            self.assertFalse(tool['annotations']['destructiveHint'])
            self.assertFalse(tool['inputSchema']['additionalProperties'])

    async def tool(self, name, args):
        response = await self.rpc('tools/call', {'name':name,'arguments':args})
        self.assertEqual(response.status_code,200,response.text)
        result = response.json()['result']
        data = json.loads(result['content'][0]['text'])
        return result,data

    async def test_three_tool_round_trips(self):
        with patch('core.BoundedIMAP', side_effect=AssertionError('live access forbidden')):
            _,listing = await self.tool('list_mailboxes',{})
            self.assertEqual(listing['data']['mailboxes'],['INBOX'])
            _,search = await self.tool('search',{'query':'meeting'})
            uid = search['data']['uids'][0]
            _,message = await self.tool('read_message',{'uid':uid,'uidvalidity':search['data']['uidvalidity']})
            self.assertIn('Synthetic meeting',message['data']['text'])
            self.assertTrue(message['untrusted_data'])

    async def test_tool_validation_redacts_input(self):
        result,data = await self.tool('search',{'query':'PRIVATE_SENTINEL\r\nEXPUNGE'})
        self.assertTrue(result['isError'])
        self.assertEqual(data,{'ok':False,'error':'invalid_input'})
        self.assertNotIn('PRIVATE_SENTINEL',json.dumps(result))

    async def test_backend_errors_redacted(self):
        with patch('fixtures.FakeIMAP.select',side_effect=RuntimeError('PRIVATE_SENTINEL')):
            result,data = await self.tool('search',{'query':'meeting'})
        self.assertEqual(data,{'ok':False,'error':'mail_unavailable'})
        self.assertNotIn('PRIVATE_SENTINEL',json.dumps(result))

    async def test_bounded_output(self):
        with patch.dict('fixtures.MESSAGES',{7:b'Subject: demo\r\n\r\n'+b'x'*10000}):
            _,data = await self.tool('read_message',{'uid':7,'uidvalidity':42})
        self.assertEqual(len(data['data']['text']),4000)
        self.assertTrue(data['data']['truncated'])
        self.assertLess(len(json.dumps(data).encode()),24000)

    async def test_http_boundaries(self):
        for headers,status in [({'Authorization':'Bearer wrong'},401),
                               ({'Host':'evil.invalid'},403),
                               ({'Origin':'https://evil.invalid'},403)]:
            with self.subTest(headers=headers):
                response = await self.client.post('/mcp',json={},headers=headers)
                self.assertEqual(response.status_code,status)
                self.assertEqual(response.text,'request_rejected')

    async def test_oversized_request(self):
        response = await self.client.post('/mcp',content=b'x'*8193,headers={'Content-Type':'application/json'})
        self.assertEqual(response.status_code,413)

    async def test_malformed_protocol_redaction(self):
        for payload in [b'{PRIVATE_SENTINEL', b'{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":123,"arguments":{"secret":"PRIVATE_SENTINEL"}}}']:
            with self.subTest(payload=payload):
                with self.assertNoLogs(level='WARNING'):
                    response = await self.client.post('/mcp',content=payload,headers={'Content-Type':'application/json'})
                self.assertEqual(response.status_code,400)
                self.assertNotIn('PRIVATE_SENTINEL',response.text)

    async def test_write_tool_absent(self):
        response = await self.rpc('tools/call',{'name':'delete','arguments':{}})
        self.assertEqual(response.status_code,400)
        self.assertEqual(response.text,'request_rejected')

    async def test_initialized_notification(self):
        response = await self.client.post('/mcp',json={'jsonrpc':'2.0','method':'notifications/initialized'})
        self.assertEqual(response.status_code,202,response.text)

    async def test_official_sdk_client(self):
        from mcp import ClientSession
        from mcp.client.streamable_http import streamable_http_client
        async with streamable_http_client('http://127.0.0.1:8765/mcp',
                                          http_client=self.client,terminate_on_close=False) as (read,write,_):
            async with ClientSession(read,write) as session:
                initialized = await session.initialize()
                self.assertEqual(initialized.serverInfo.name,'icloud-readonly-fake-demo')
                tools = await session.list_tools()
                self.assertEqual(len(tools.tools),3)
                found = await session.call_tool('search',{'query':'meeting'})
                data = json.loads(found.content[0].text)['data']
                message = await session.call_tool('read_message',{'uid':data['uids'][0],
                                                                 'uidvalidity':data['uidvalidity']})
                self.assertFalse(message.isError)
                self.assertIn('Synthetic meeting',message.content[0].text)

    async def test_sdk_debug_logs_redacted(self):
        with self.assertLogs('mcp.server.lowlevel.server',level=logging.DEBUG) as captured:
            await self.tool('search',{'query':'PRIVATE_SENTINEL'})
        self.assertNotIn('PRIVATE_SENTINEL','\n'.join(captured.output))

    async def test_duplicate_json_keys_rejected(self):
        response = await self.client.post('/mcp',content=b'{"jsonrpc":"2.0","id":1,"method":"ping","method":"tools/list"}',
                                          headers={'Content-Type':'application/json'})
        self.assertEqual(response.status_code,400)

    async def test_unsupported_actions_and_batch_rejected(self):
        for method in ('logging/setLevel','resources/read','sampling/createMessage','tasks/cancel'):
            response = await self.rpc(method,{})
            self.assertEqual(response.status_code,400)
        response = await self.client.post('/mcp',json=[{'jsonrpc':'2.0','id':1,'method':'ping'}])
        self.assertEqual(response.status_code,400)

if __name__ == '__main__': unittest.main()
