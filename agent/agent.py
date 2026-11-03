#!/usr/bin/env python3
"""Mac mini 上執行的 Agent：擷取螢幕 -> 傳給伺服器；接收滑鼠/鍵盤指令 -> 執行。
用法： python3 agent.py ws://localhost:8080 <AGENT_KEY>
"""
import asyncio, io, json, subprocess, sys, zlib
import mss, pyautogui, websockets
from PIL import Image

pyautogui.PAUSE = 0
pyautogui.FAILSAFE = False

URL = (sys.argv[1] if len(sys.argv) > 1 else "ws://localhost:8080").rstrip("/")
KEY = sys.argv[2] if len(sys.argv) > 2 else ""

settings = {"quality": 60, "fps": 12, "maxw": 1600}
viewers = 0

KEYMAP = {
    "Enter": "enter", "Backspace": "backspace", "Tab": "tab", "Escape": "esc", " ": "space",
    "ArrowLeft": "left", "ArrowRight": "right", "ArrowUp": "up", "ArrowDown": "down",
    "Delete": "delete", "Home": "home", "End": "end", "PageUp": "pageup", "PageDown": "pagedown",
    "Shift": "shift", "Control": "ctrl", "Alt": "option", "Meta": "command", "CapsLock": "capslock",
}
KEYMAP.update({f"F{i}": f"f{i}" for i in range(1, 13)})


def screen_pts():
    return pyautogui.size()  # 以「點」為單位（Retina 下小於實際像素）


def grab_jpeg(sct):
    shot = sct.grab(sct.monitors[1])
    img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
    if img.width > settings["maxw"]:
        h = int(img.height * settings["maxw"] / img.width)
        img = img.resize((settings["maxw"], h), Image.BILINEAR)
    sig = zlib.adler32(img.tobytes())
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=settings["quality"])
    return sig, buf.getvalue(), img.size


def paste_text(text):
    subprocess.run(["pbcopy"], input=text.encode("utf-8"), check=False)
    pyautogui.hotkey("command", "v")


def handle(m):
    t = m.get("t")
    w, h = screen_pts()
    if t in ("move", "down", "up"):
        x, y = int(m["x"] * w), int(m["y"] * h)
        btn = {0: "left", 1: "middle", 2: "right"}.get(m.get("b", 0), "left")
        if t == "move":
            if m.get("drag"):
                pyautogui.dragTo(x, y, button=btn, _pause=False)
            else:
                pyautogui.moveTo(x, y, _pause=False)
        elif t == "down":
            pyautogui.mouseDown(x, y, button=btn, _pause=False)
        else:
            pyautogui.mouseUp(x, y, button=btn, _pause=False)
    elif t == "dblclick":
        pyautogui.doubleClick(int(m["x"] * w), int(m["y"] * h), _pause=False)
    elif t == "wheel":
        pyautogui.scroll(int(-m.get("dy", 0) / 4), _pause=False)
        if m.get("dx"):
            pyautogui.hscroll(int(-m["dx"] / 4), _pause=False)
    elif t in ("kd", "ku"):
        k = m.get("k", "")
        k = KEYMAP.get(k, k.lower() if len(k) == 1 else None)
        if k:
            try:
                (pyautogui.keyDown if t == "kd" else pyautogui.keyUp)(k, _pause=False)
            except Exception as e:
                print("key error", k, e)
    elif t == "text":
        paste_text(m.get("s", ""))
    elif t == "settings":
        settings["quality"] = max(20, min(95, int(m.get("quality", settings["quality"]))))
        settings["fps"] = max(1, min(30, int(m.get("fps", settings["fps"]))))
        settings["maxw"] = max(640, min(2560, int(m.get("maxw", settings["maxw"]))))
    elif t == "viewers":
        global viewers
        viewers = m.get("n", 0)


async def capture_loop(ws):
    last = None
    sent_info = False
    with mss.mss() as sct:
        while True:
            if viewers <= 0:
                last = None; sent_info = False
                await asyncio.sleep(0.3)
                continue
            t0 = asyncio.get_event_loop().time()
            sig, data, (iw, ih) = await asyncio.to_thread(grab_jpeg, sct)
            if not sent_info:
                await ws.send(json.dumps({"t": "info", "w": iw, "h": ih}))
                sent_info = True
            if sig != last:  # 畫面沒變就不傳，省頻寬
                last = sig
                await ws.send(data)
            dt = asyncio.get_event_loop().time() - t0
            await asyncio.sleep(max(0.005, 1 / settings["fps"] - dt))


async def recv_loop(ws):
    async for msg in ws:
        if isinstance(msg, str):
            try:
                await asyncio.to_thread(handle, json.loads(msg))
            except Exception as e:
                print("handle error:", e)


async def main():
    while True:
        try:
            async with websockets.connect(f"{URL}/agent?key={KEY}", max_size=None, ping_interval=20) as ws:
                print("已連上伺服器，等待控制端…")
                await asyncio.gather(capture_loop(ws), recv_loop(ws))
        except Exception as e:
            print("連線中斷，3 秒後重試：", e)
            await asyncio.sleep(3)


if __name__ == "__main__":
    asyncio.run(main())
