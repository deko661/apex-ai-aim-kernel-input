import ctypes, time, sys, os, traceback
def _hook(t, v, tb):
    with open("crash.log","a") as f:
        f.write(time.strftime("[%H:%M:%S] ") + "".join(traceback.format_exception(t,v,tb)) + "\n")
    print("CRASH see crash.log:", v)
    try: input("ENTER to close...")
    except Exception: pass
sys.excepthook = _hook
try:
    is_admin = ctypes.windll.shell32.IsUserAnAdmin()
except:
    is_admin = False
if not is_admin:
    print("[*] relaunching as admin (UAC)...")
    ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, f'"{os.path.abspath(__file__)}"', None, 1)
    sys.exit(0)
import numpy as np
import mss
import win32api

DEVICE = r"\\.\FU0aDYj2AB39H2TbABkFOdpof2a4k42FOD"
IOCTL = 0x22D04C
GENERIC_RW = 0xC0000000
OPEN_EXISTING = 3

k32 = ctypes.windll.kernel32
h = k32.CreateFileW(DEVICE, GENERIC_RW, 0, None, OPEN_EXISTING, 0, None)
if h == -1:
    err = k32.GetLastError()
    print(f"[!] CreateFileW failed err={err} (2=driver not loaded, 5=not admin, 32=DriverTest open)")
    try: input("ENTER to close...")
    except Exception: pass
    raise SystemExit(1)
print("[+] driver OK")

class Req(ctypes.Structure):
    _pack_ = 1
    _fields_ = [("dx", ctypes.c_long), ("dy", ctypes.c_ulong), ("flags", ctypes.c_ushort)]

def move(dx, dy):
    r = Req(int(dx), int(dy) & 0xFFFFFFFF, 0)
    ret = ctypes.c_ulong()
    ok = k32.DeviceIoControl(h, IOCTL, ctypes.byref(r), ctypes.sizeof(r), None, 0, ctypes.byref(ret), None)
    return ok

import onnxruntime as ort
opts = ort.SessionOptions()
opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
def list_models():
    import glob as _g
    return sorted(_g.glob("models/*.onnx"))
import threading as _mth
_model_lock = _mth.Lock()
def load_model(path):
    global sess, IN, IS_V10, MW, MH
    _s = ort.InferenceSession(path, sess_options=opts, providers=["DmlExecutionProvider", "CPUExecutionProvider"])
    _in = _s.get_inputs()[0].name
    _ish = _s.get_inputs()[0].shape
    _mh, _mw = int(_ish[2]), int(_ish[3])
    _osh = _s.get_outputs()[0].shape
    _v10 = len(_osh) == 3 and _osh[2] == 6
    with _model_lock:
        sess, IN, IS_V10, MW, MH = _s, _in, _v10, _mw, _mh
    print("[+] model:", path, _ish, "V10:", _v10, flush=True)
    return True
MW, MH = 640, 640

def infer_dml(rgb):
    import cv2
    with _model_lock:
        _sess, _in, _v10, _mw, _mh = sess, IN, IS_V10, MW, MH
    if rgb.shape[1] == _mw and rgb.shape[0] == _mh:
        img = rgb
    else:
        img = cv2.resize(rgb, (_mw, _mh))
    blob = (img.astype("float32") / 255.0).transpose(2, 0, 1)[None]
    raw = _sess.run(None, {_in: np.ascontiguousarray(blob)})[0]
    if _v10:
        dets = raw[0]
        keep = []
        for r in dets:
            if r[4] < CONF:
                continue
            sx, sy = CW/_mw, CH/_mh
            keep.append((float(r[0]*sx), float(r[1]*sy), float(r[2]*sx), float(r[3]*sy), float(r[4])))
            if len(keep) >= 10:
                break
        return keep
    out = raw[0]
    nc = out.shape[0] - 4
    if nc == 1:
        conf = 1/(1+np.exp(-out[4]))
        cls = np.zeros_like(conf, dtype=int)
    else:
        probs = 1/(1+np.exp(-out[4:4+nc]))
        cls = probs.argmax(axis=0)
        conf = probs.max(axis=0)
    m = (conf > CONF) & (cls == 1 if nc > 1 else True)
    if not np.any(m):
        return []
    cx, cy, w, h = out[0][m], out[1][m], out[2][m], out[3][m]
    cf = conf[m]
    x0, y0 = (cx-w/2)*(CW/_mw), (cy-h/2)*(CH/_mh)
    x1, y1 = (cx+w/2)*(CW/_mw), (cy+h/2)*(CH/_mh)
    order = np.argsort(-cf)
    keep = []
    for i in order[:50]:
        b = (float(x0[i]), float(y0[i]), float(x1[i]), float(y1[i]), float(cf[i]))
        ok = True
        for k in keep:
            inter = max(0,min(b[2],k[2])-max(b[0],k[0]))*max(0,min(b[3],k[3])-max(b[1],k[1]))
            union = (b[2]-b[0])*(b[3]-b[1])+(k[2]-k[0])*(k[3]-k[1])-inter
            if union > 0 and inter/union > 0.5:
                ok = False; break
        if ok:
            keep.append(b)
            if len(keep) >= 10:
                break
    return keep
sct = mss.MSS()
mon = sct.monitors[1]
import queue, threading
import json as _js
CFG = {"conf":0.55,"fov":80,"zone":240,"gain":1.4,"spd":0.45,"sm":1.0,"bone":"0.05","key":"all","running":True,"draw_fov":True,"draw_esp":True,"zoom":1.0,"autoz":True,"rc_on":True,"rc_x":100,"rc_y":100,"model":"models/Apex5k.200.onnx","game":"apex"}
try:
    _saved = _js.load(open("config.json"))
    for _k in list(CFG):
        if _k in _saved: CFG[_k] = _saved[_k]
    print("[cfg] loaded config.json")
except Exception:
    pass
def save_cfg():
    try: open("config.json","w").write(_js.dumps(CFG))
    except Exception: pass
import atexit; atexit.register(save_cfg)

# --- HTTP server for panel ---
import http.server, socketserver, threading as _http_th, webbrowser as _wb, os as _os
PANEL_PORT = 17521
class PanelHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format, *args): pass
    def do_GET(self):
        if self.path == '/api/config':
            self._send_json(CFG)
        elif self.path == '/api/models':
            self._send_json(list_models())
        elif self.path == '/api/stats':
            self._send_json(STATS)
        elif self.path == '/' or self.path == '/index.html':
            self.path = '/panel.html'
            return http.server.SimpleHTTPRequestHandler.do_GET(self)
        else:
            return http.server.SimpleHTTPRequestHandler.do_GET(self)
    def do_POST(self):
        if self.path == '/api/config':
            length = int(self.headers.get('Content-Length', 0))
            data = self.rfile.read(length)
            try:
                updates = _js.loads(data)
                for k, v in updates.items():
                    if k in CFG:
                        CFG[k] = v
                        if k == 'running':
                            print(f"[panel] running={v}")
                save_cfg()
                self._send_json({"ok": True})
            except Exception as e:
                self._send_json({"ok": False, "err": str(e)})
        else:
            self._send_json({"ok": False, "err": "unknown endpoint"})
    def _send_json(self, obj):
        import json as _j
        data = _j.dumps(obj).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', len(data))
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(data)

def _start_panel_server():
    try:
        _os.chdir(_os.path.dirname(_os.path.abspath(__file__)))
        handler = PanelHandler
        httpd = socketserver.TCPServer(("127.0.0.1", PANEL_PORT), handler)
        t = _http_th.Thread(target=httpd.serve_forever, daemon=True)
        t.start()
        print(f"[panel] serving on http://127.0.0.1:{PANEL_PORT}")
        threading.Timer(1.0, lambda: _wb.open(f"http://127.0.0.1:{PANEL_PORT}")).start()
        return httpd
    except Exception as e:
        print(f"[!] panel server failed: {e}")
        return None
_panel_srv = _start_panel_server()

CW, CH = 240, 240
CONF = 0.55
def CFG_FOV(): return int(CFG["fov"])
def CFG_CONF(): return float(CFG["conf"])
last_dx, last_dy = 0, 0
STATS = {"fps":"-","boxes":"-","driver":"OK","log":"-"}
try:
    _m0 = CFG.get("model", "models/Apex5k.200.onnx")
    import os as _o
    if not _o.path.exists(_m0):
        _av = list_models()
        if _av: _m0 = _av[0]
        CFG["model"] = _m0
    load_model(CFG["model"])
except Exception as _e:
    print("[!] model load:", _e)
import overlay as _ov
_ov_handle = _ov.start()
import weapon as _wp
import recoil as _rc
_rc.bind(move, CFG)
_rc.start(lambda: _wp.current)
import queue
import threading
frame_q = queue.Queue(maxsize=1)
def cap_loop():
    sc = mss.MSS()
    mn = sc.monitors[1]
    while True:
        bx = {"left": mn["width"]//2-CW//2, "top": mn["height"]//2-CH//2, "width": CW, "height": CH}
        im = np.array(sc.grab(bx))[:, :, 2::-1]
        try: frame_q.get_nowait()
        except queue.Empty: pass
        try: frame_q.put_nowait(im)
        except queue.Full: pass
threading.Thread(target=cap_loop, daemon=True).start()
def grab():
    try:
        return frame_q.get(timeout=0.5)
    except queue.Empty:
        cx, cy = mon["width"]//2, mon["height"]//2
        box = {"left": cx-CW//2, "top": cy-CH//2, "width": CW, "height": CH}
        img = np.array(sct.grab(box))
        return img[:, :, 2::-1]

import cv2
frame_dbg = 0
locked = None
GAIN = 1.4
SMOOTH_F = 1.0
ema = None
hist = []
PRED_MS = 0
ovx, ovy = 0.0, 0.0
empty_ct = [0]
n = 0
import threading as _th, collections as _col
smooth_q = _col.deque()
def smooth_thread():
    while True:
        if smooth_q:
            sx, sy, dl = smooth_q.popleft()
            move(sx, sy)
            if dl > 0:
                import time as _t; _t.sleep(dl)
        else:
            import time as _t; _t.sleep(0.001)
_th.Thread(target=smooth_thread, daemon=True).start()
def spread_move(idx, idy, period_ms=70):
    import math
    n = max(1, min(16, int(round(period_ms/3))))
    mag = abs(idx)+abs(idy)
    if n > mag and mag > 0:
        n = mag
    if n <= 1:
        move(idx, idy); return
    smooth_q.clear()
    ax = ay = 0
    for i in range(1, n+1):
        tx = int(round(idx*i/n)); ty = int(round(idy*i/n))
        sx, sy = tx-ax, ty-ay
        ax, ay = tx, ty
        if sx or sy:
            smooth_q.append((sx, sy, (period_ms/1000)/n))
while not (win32api.GetAsyncKeyState(0x7B) & 0x8000):
    _base = int(CFG["zone"])
    _z = float(CFG.get("zoom", 1.0))
    if CFG.get("autoz", True) and frame_dbg > 30 and n == 0:
        empty_ct[0] += 1
    else:
        empty_ct[0] = 0
    if CFG.get("autoz", True) and empty_ct[0] > 20:
        _z = 2.0 if (empty_ct[0] // 20) % 2 == 1 else 0.62
    _cw = _ch = max(120, min(480, int(_base / _z)))
    FOV, CONF = int(CFG["fov"]), float(CFG["conf"])
    globals()["CW"], globals()["CH"], globals()["CONF"] = _cw, _ch, CONF
    GAIN, SMOOTH_F = float(CFG["gain"]), float(CFG["sm"])
    SPD, BONE = float(CFG["spd"]), float(CFG["bone"])
    CX, CY = _cw//2, _ch//2

    if not CFG.get("running", True):
        time.sleep(0.05); continue
    t0 = time.time()
    frame = grab()
    dets = infer_dml(frame)
    n = len(dets)
    try:
        _ov.boxes = [(d[0],d[1],d[2],d[3]) for d in dets[:8]]
        _ov.fov = FOV
        _ov.draw_fov = bool(CFG.get("draw_fov", True))
        _ov.draw_esp = bool(CFG.get("draw_esp", True))
    except Exception: pass
    fps = 1.0 / max(0.001, time.time()-t0)
    frame_dbg += 1
    _k = CFG.get("key","all")
    if _k == "rmb": aim_held = bool(win32api.GetAsyncKeyState(0x02)&0x8000)
    elif _k == "x1": aim_held = bool(win32api.GetAsyncKeyState(0x05)&0x8000)
    elif _k == "x2": aim_held = bool(win32api.GetAsyncKeyState(0x06)&0x8000)
    else: aim_held = bool(win32api.GetAsyncKeyState(0x05)&0x8000 or win32api.GetAsyncKeyState(0x06)&0x8000 or win32api.GetAsyncKeyState(0x02)&0x8000)
    STATS.update({"fps":f"{fps:.1f}","boxes":str(n),"weapon":f"{_wp.current} {getattr(_wp,'score',0):.2f}"})
    # Target selection: strict lock on first target found, only switch when it's gone
    if n > 0:
        cands = []
        for x0, y0, x1, y1, c in dets:
            if y0 > 550 or (x1-x0) < 20 or (y1-y0) < 20:
                continue
            hx, hy = (x0+x1)/2, y0+(y1-y0)*BONE
            d_center = ((hx-CX)**2 + (hy-CY)**2) ** 0.5
            if d_center <= FOV:
                cands.append((d_center, hx, hy))
        if not cands:
            locked, best = None, None
            hist = []
        else:
            if locked is not None:
                # STRICT LOCK: keep current target if still in FOV (within 15px tolerance)
                found = False
                for d, hx, hy in cands:
                    if ((hx-locked[0])**2 + (hy-locked[1])**2) ** 0.5 < 15:
                        best = (hx, hy)
                        found = True
                        break
                if not found:
                    # Target lost, pick new closest to center
                    cands.sort(key=lambda c: c[0])
                    best = (cands[0][1], cands[0][2])
                    locked = best
                    hist = []
            else:
                # No locked target, pick closest to center
                cands.sort(key=lambda c: c[0])
                best = (cands[0][1], cands[0][2])
                locked = best
            # Prediction using history
            if best:
                now = time.time()
                hist.append((now, best[0], best[1]))
                hist = hist[-4:]
                if len(hist) >= 2:
                    t0h, x0h, y0h = hist[0]
                    t1h, x1h, y1h = hist[-1]
                    dt = max(0.01, t1h - t0h)
                    vx, vy = (x1h - x0h) / dt, (y1h - y0h) / dt
                    vx = max(-800, min(800, vx))
                    vy = max(-800, min(800, vy))
                    best = (best[0] + vx * (PRED_MS/1000), best[1] + vy * (PRED_MS/1000))
    else:
        locked = None
        best = None
        hist = []
    if aim_held and best:
        if ema is None:
            ema = best
        else:
            ema = (ema[0]*(1-SMOOTH_F)+best[0]*SMOOTH_F, ema[1]*(1-SMOOTH_F)+best[1]*SMOOTH_F)
        dx, dy = (ema[0]-CX)*SPD*GAIN, (ema[1]-CY)*SPD*GAIN
        if abs(dx) < 1 and abs(dy) < 1:
            pass
        else:
            dx += ovx; dy += ovy
            ix, iy = int(round(dx)), int(round(dy))
            ovx, ovy = dx-ix, dy-iy
            if ix != 0 or iy != 0:
                spread_move(ix, iy, period_ms=70)
        if frame_dbg % 10 == 0:
            print(f"  -> direct dx={int(ema[0]-CX)} dy={int(ema[1]-CY)}")
    else:
        if not best:
            ema = None
