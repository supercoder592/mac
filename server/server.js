// 中繼伺服器：提供網頁、驗證密碼、在 Agent(Mac mini) 與 Viewer(瀏覽器) 之間轉送資料
const http = require('http');
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const { WebSocketServer } = require('ws');

const CONFIG_FILE = path.join(__dirname, 'config.json');
let cfg = {};
try { cfg = JSON.parse(fs.readFileSync(CONFIG_FILE, 'utf8')); } catch {}
if (!cfg.password) cfg.password = crypto.randomBytes(6).toString('base64url');
if (!cfg.agentKey) cfg.agentKey = crypto.randomBytes(24).toString('hex');
fs.writeFileSync(CONFIG_FILE, JSON.stringify(cfg, null, 2));
const PASSWORD = process.env.VIEWER_PASSWORD || cfg.password;
const AGENT_KEY = process.env.AGENT_KEY || cfg.agentKey;
const PORT = process.env.PORT || 8080;

const html = () => fs.readFileSync(path.join(__dirname, 'public', 'index.html'));
const server = http.createServer((req, res) => {
  if (req.url === '/' || req.url.startsWith('/index.html')) {
    res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'no-store' });
    res.end(html());
  } else { res.writeHead(404); res.end('Not found'); }
});

const wss = new WebSocketServer({ noServer: true, maxPayload: 8 * 1024 * 1024 });
let agent = null;
const viewers = new Set();
const fails = new Map(); // ip -> {n, until}

const ipOf = (req) => req.headers['cf-connecting-ip'] || req.headers['x-forwarded-for']?.split(',')[0].trim() || req.socket.remoteAddress;
const safeEq = (a, b) => {
  const x = Buffer.from(String(a)), y = Buffer.from(String(b));
  return x.length === y.length && crypto.timingSafeEqual(x, y);
};
const send = (ws, o) => ws.readyState === 1 && ws.send(JSON.stringify(o));
const notifyAgent = () => agent && send(agent, { t: 'viewers', n: [...viewers].filter(v => v.authed).length });
const notifyViewers = () => viewers.forEach(v => v.authed && send(v, { t: 'agent', online: !!agent }));

server.on('upgrade', (req, sock, head) => {
  const p = req.url.split('?')[0];
  if (p !== '/agent' && p !== '/viewer') return sock.destroy();
  wss.handleUpgrade(req, sock, head, (ws) => { ws.role = p.slice(1); ws.ip = ipOf(req); wss.emit('connection', ws, req); });
});

wss.on('connection', (ws, req) => {
  if (ws.role === 'agent') {
    const key = new URL(req.url, 'http://x').searchParams.get('key') || '';
    if (!safeEq(key, AGENT_KEY)) return ws.close(4001, 'bad key');
    if (agent) try { agent.close(); } catch {}
    agent = ws;
    console.log('[agent] connected');
    notifyViewers(); notifyAgent();
    ws.on('message', (data, isBinary) => {
      if (isBinary) { for (const v of viewers) if (v.authed && v.bufferedAmount < 2e6) v.send(data, { binary: true }); }
      else for (const v of viewers) if (v.authed) v.send(data.toString());
    });
    ws.on('close', () => { if (agent === ws) agent = null; console.log('[agent] disconnected'); notifyViewers(); });
    return;
  }
  // viewer
  viewers.add(ws);
  ws.authed = false;
  ws.on('message', (data, isBinary) => {
    if (isBinary) return;
    let m; try { m = JSON.parse(data.toString()); } catch { return; }
    if (!ws.authed) {
      if (m.t !== 'auth') return;
      const f = fails.get(ws.ip) || { n: 0, until: 0 };
      if (Date.now() < f.until) return send(ws, { t: 'authfail', msg: '嘗試次數過多，請稍後再試' });
      if (safeEq(m.pw || '', PASSWORD)) {
        fails.delete(ws.ip); ws.authed = true;
        send(ws, { t: 'authok' }); send(ws, { t: 'agent', online: !!agent }); notifyAgent();
        console.log('[viewer] login', ws.ip);
      } else {
        f.n++; if (f.n >= 5) { f.until = Date.now() + 60_000; f.n = 0; }
        fails.set(ws.ip, f); send(ws, { t: 'authfail', msg: '密碼錯誤' });
      }
      return;
    }
    if (agent) send(agent, m); // 轉送輸入事件給 Agent
  });
  ws.on('close', () => { viewers.delete(ws); notifyAgent(); });
});

setInterval(() => wss.clients.forEach(c => { if (c.isAlive === false) return c.terminate(); c.isAlive = false; c.ping(); }), 20000);
wss.on('connection', ws => { ws.isAlive = true; ws.on('pong', () => ws.isAlive = true); });

server.listen(PORT, () => {
  console.log(`\n遙控伺服器啟動：http://localhost:${PORT}`);
  console.log(`網頁登入密碼：${PASSWORD}`);
  console.log(`Agent 金鑰  ：${AGENT_KEY}\n`);
});
