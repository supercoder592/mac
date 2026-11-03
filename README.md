# Mac mini 遠端遙控

網頁控制端放在 GitHub Pages（`index.html`），Mac mini 上跑「中繼伺服器 + Agent」。

> GitHub Pages 只能放靜態網頁，無法執行伺服器，所以 `server/` 與 `agent/` 要在 Mac mini 上跑。

## 結構
- `index.html` — 網頁控制端（部署到 GitHub Pages）
- `server/` — Node 中繼伺服器（驗證密碼、轉送畫面與輸入）
- `agent/agent.py` — 擷取螢幕、執行滑鼠鍵盤指令

## Mac mini 安裝
```bash
cd server && npm install
pip3 install mss pyautogui pillow websockets
```
系統設定 → 隱私權與安全性：把「螢幕與系統錄音」「輔助使用」開給終端機，重開終端機。

## 啟動
```bash
node server/server.js            # 印出網頁密碼與 Agent 金鑰
python3 agent/agent.py ws://localhost:8080 <Agent 金鑰>
cloudflared tunnel --url http://localhost:8080   # brew install cloudflared；得到 https://xxxx.trycloudflare.com
```

## 使用
開啟 GitHub Pages 網址，輸入 `xxxx.trycloudflare.com` 和密碼即可。
也可用 `?server=xxxx.trycloudflare.com` 直接帶入位址。

## 安全
外網務必走 HTTPS Tunnel；密碼可在 `server/config.json` 改長一點；連錯 5 次鎖 60 秒。
