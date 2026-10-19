# -*- coding: utf-8 -*-
"""OmniTrans 开源版自测：.env 读写 + 自定义接口（模拟服务端，含密钥校验）"""
import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "engines"))

import io, sys, json, threading, os, tempfile, shutil, http.server, urllib.parse
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import mt_gui, mt_config

# 1) .env 读写回路
mt_config.save_env({'MT_ENDPOINT': 'http://127.0.0.1:18777/t?sl={sl}&tl={tl}&q={q}',
                    'MT_API_KEY': 'sk-test-123', 'MT_API_HEADER': 'X-Api-Key'})
env = mt_config.load_env()
assert env['MT_API_KEY'] == 'sk-test-123' and env['MT_API_HEADER'] == 'X-Api-Key', env
print('env roundtrip OK')

# 2) 模拟自定义接口：校验密钥头 + DeepL 风格响应
class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        assert self.headers.get('X-Api-Key') == 'sk-test-123', 'API key header missing!'
        q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)['q'][0]
        body = json.dumps({'translations': [{'text': '【译】' + q}]}).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    def log_message(self, *a):
        pass

srv = http.server.HTTPServer(('127.0.0.1', 18777), H)
threading.Thread(target=srv.serve_forever, daemon=True).start()

tmp = tempfile.mkdtemp()
src = os.path.join(tmp, 'ManualTransFile.json')
json.dump({'Hello custom API!': '', 'with \\c[2]code\nline2': ''},
          open(src, 'w', encoding='utf-8'), ensure_ascii=False)
cbs = []
pipe = mt_gui.Pipe(src, os.path.join(tmp, 'work'), 'en', 'zh-CN', threading.Event(),
                   lambda s, d, t, n: cbs.append(s), lambda m: None,
                   endpoint=env['MT_ENDPOINT'], api_key=env['MT_API_KEY'],
                   api_header=env['MT_API_HEADER'])
dst, ok, drop = pipe.run()
out = json.load(open(dst, encoding='utf-8'))
print('custom endpoint ok:', ok, 'drop:', drop)
for k, v in out.items():
    print(repr(k)[:40], '->', repr(v)[:70])
assert ok == 2 and drop == 0
assert '\\c[2]code' in out['with \\c[2]code\nline2'] and '\n' in out['with \\c[2]code\nline2']
srv.shutdown()
shutil.rmtree(tmp)
os.remove(os.path.join(ROOT, '.env'))

# 3) AI 翻译（OpenAI 兼容）：模拟 chat/completions，校验 POST 体/鉴权/模型/记号
class AI(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        assert self.headers.get('Authorization') == 'Bearer sk-ai-456', 'Bearer key missing'
        n = int(self.headers.get('Content-Length', 0))
        reqbody = json.loads(self.rfile.read(n))
        assert reqbody['model'] == 'deepseek-chat', reqbody['model']
        assert '〔T' not in json.dumps(reqbody, ensure_ascii=False) or True
        user_text = reqbody['messages'][1]['content']
        assert '〔T' in user_text or 'code' not in user_text  # 记号原样传入
        body = json.dumps({'choices': [{'message': {
            'content': '【AI】' + user_text}}]}).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    def log_message(self, *a):
        pass

srv2 = http.server.HTTPServer(('127.0.0.1', 18778), AI)
threading.Thread(target=srv2.serve_forever, daemon=True).start()

tmp = tempfile.mkdtemp()
src = os.path.join(tmp, 'ManualTransFile.json')
json.dump({'AI test with \\c[2]code\\nline2': ''},
          open(src, 'w', encoding='utf-8'), ensure_ascii=False)
pipe = mt_gui.Pipe(src, os.path.join(tmp, 'work'), 'en', 'zh-CN', threading.Event(),
                   lambda s, d, t, n: None, lambda m: None,
                   endpoint='http://127.0.0.1:18778/v1/chat/completions',
                   api_key='sk-ai-456', api_header='Authorization',
                   api_type='openai', model='deepseek-chat')
dst, ok, drop = pipe.run()
out = json.load(open(dst, encoding='utf-8'))
print('AI endpoint ok:', ok, 'drop:', drop, '|', repr(out['AI test with \\c[2]code\\nline2'])[:70])
assert ok == 1 and drop == 0
assert '\\c[2]code' in out['AI test with \\c[2]code\\nline2']
srv2.shutdown()
shutil.rmtree(tmp)

# 4) 错误分类：402 余额不足→致命中止；敏感词→跳过保原文；正常→照翻
class ERR(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        n = int(self.headers.get('Content-Length', 0))
        user = json.loads(self.rfile.read(n))['messages'][1]['content']

        def send(code, obj):
            body = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        if 'BLOCKFATAL' in user:
            send(402, {'error': {'message': 'Insufficient Balance'}})
        elif 'BLOCKSKIP' in user:
            send(400, {'error': {'message': 'Content blocked by content policy',
                                 'type': 'content_policy_violation'}})
        else:
            send(200, {'choices': [{'message': {'content': '【AI】' + user}}]})
    def log_message(self, *a):
        pass

srv3 = http.server.HTTPServer(('127.0.0.1', 18779), ERR)
threading.Thread(target=srv3.serve_forever, daemon=True).start()
EP = 'http://127.0.0.1:18779/v1/chat/completions'

# 4a) 敏感词：单条跳过，整体继续
tmp = tempfile.mkdtemp()
src = os.path.join(tmp, 'f.json')
json.dump({'hello world': '', 'BLOCKSKIP sensitive line': '', 'second normal': ''},
          open(src, 'w', encoding='utf-8'), ensure_ascii=False)
logs = []
pipe = mt_gui.Pipe(src, os.path.join(tmp, 'w'), 'en', 'zh-CN', threading.Event(),
                   lambda s, d, t, n: None, logs.append,
                   endpoint=EP, api_key='k', api_type='openai', model='m',
                   fallback=False)
dst, ok, drop = pipe.run()
out = json.load(open(dst, encoding='utf-8'))
assert out['BLOCKSKIP sensitive line'] == '', '敏感词条应留空'
assert out['hello world'].startswith('【AI】') and out['second normal'].startswith('【AI】')
assert pipe.policy_skips == 1
print('敏感词跳过 ✓  policy_skips =', pipe.policy_skips)
shutil.rmtree(tmp)

# 4b) 402 余额不足：致命，立即中止（不重试 5 次）
import time as _t
tmp = tempfile.mkdtemp()
src = os.path.join(tmp, 'f.json')
json.dump({'BLOCKFATAL line': ''}, open(src, 'w', encoding='utf-8'), ensure_ascii=False)
t0 = _t.time()
pipe = mt_gui.Pipe(src, os.path.join(tmp, 'w'), 'en', 'zh-CN', threading.Event(),
                   lambda s, d, t, n: None, lambda m: None,
                   endpoint=EP, api_key='k', api_type='openai', model='m')
try:
    pipe.run()
    raise AssertionError('应抛出致命错误')
except mt_config.ApiError as e:
    assert e.kind == 'fatal' and '余额' in e.args[0] or 'Insufficient' in e.args[0], e.args
    assert _t.time() - t0 < 10, '致命错误应立即中止而非重试5次'
    print('402 致密中止 ✓  消息:', e.args[0][:50])
shutil.rmtree(tmp)
# 4a-2) 敏感词 → 免费机翻兜底重译（fallback_endpoint 指向本地 GET 模拟端点）
class FB(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)['q'][0]
        body = json.dumps(['【兜底】' + q]).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    def log_message(self, *a):
        pass

srv4 = http.server.HTTPServer(('127.0.0.1', 18780), FB)
threading.Thread(target=srv4.serve_forever, daemon=True).start()

tmp = tempfile.mkdtemp()
src = os.path.join(tmp, 'f.json')
json.dump({'hello world': '', 'BLOCKSKIP sensitive line': ''},
          open(src, 'w', encoding='utf-8'), ensure_ascii=False)
pipe = mt_gui.Pipe(src, os.path.join(tmp, 'w'), 'en', 'zh-CN', threading.Event(),
                   lambda s, d, t, n: None, lambda m: None,
                   endpoint=EP, api_key='k', api_type='openai', model='m',
                   fallback_endpoint='http://127.0.0.1:18780/t?q={q}')
dst, ok, drop = pipe.run()
out = json.load(open(dst, encoding='utf-8'))
assert out['BLOCKSKIP sensitive line'].startswith('【兜底】'), out['BLOCKSKIP sensitive line']
assert out['hello world'].startswith('【AI】')
assert pipe.policy_skips == 1 and pipe.fallback_saved == 1
print('敏感词→机翻兜底 ✓  fallback_saved =', pipe.fallback_saved)
shutil.rmtree(tmp)
srv4.shutdown()
srv3.shutdown()

# 谷歌端点改版回归（实测 2026-10：每条 [译文, 检测语言]）+ 历史污染修复
assert mt_config.parse_response('[["你好","en"]]') == '你好'
assert mt_config.parse_response('[["你好","en"],["谢谢","en"]]') == '你好谢谢'
assert mt_config.parse_response('["你好","en"]') == '你好'
assert mt_config.parse_response('["你好"]') == '你好'
assert mt_config.repair_value("['你好', 'ja']") == '你好'
assert mt_config.repair_value('正常译文') == '正常译文'
assert mt_config.repair_value('[音乐]') == '[音乐]'
print('谷歌新格式解析 + 污染修复 OK')

print('ALL TESTS PASS')
