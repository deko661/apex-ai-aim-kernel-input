import cv2, glob, os, time, threading
import numpy as np, mss

GAMES = {
    "apex": dict(rx=0.8073, ry=0.8843, rw=0.0885, rh=0.0463, tpl="templates_apex"),
}
game = "apex"
NORM_W, NORM_H, THRESH = 160, 46, 0.50
current, score = "off", 0.0
_running = True

def _load():
    g = GAMES.get(game, GAMES["apex"])
    t = {}
    for p in glob.glob(f"{g['tpl']}/*.png"):
        name = os.path.splitext(os.path.basename(p))[0].upper()
        img = cv2.imread(p, cv2.IMREAD_GRAYSCALE)
        if img is None: continue
        img = cv2.resize(img, (NORM_W, NORM_H))
        _, img = cv2.threshold(img, 180, 255, cv2.THRESH_BINARY)
        t[name] = img
    return t

TMPLS = _load()
print(f"[weapon] {len(TMPLS)} templates")

def set_game(g):
    global game, TMPLS, current, score
    game = g
    TMPLS = _load()
    current, score = "off", 0.0
    print(f"[weapon] game={g} templates={len(TMPLS)}")

def detect_once():
    global current, score
    g = GAMES.get(game, GAMES["apex"])
    with mss.MSS() as s:
        m = s.monitors[1]
        sw, sh = m["width"], m["height"]
        box = {"left": int(m["left"]+g["rx"]*sw), "top": int(m["top"]+g["ry"]*sh),
               "width": int(g["rw"]*sw), "height": int(g["rh"]*sh)}
        shot = np.array(s.grab(box))[:, :, 2::-1]
    g = cv2.cvtColor(shot, cv2.COLOR_RGB2GRAY)
    g = cv2.resize(g, (NORM_W, NORM_H))
    _, mask = cv2.threshold(g, 180, 255, cv2.THRESH_BINARY)
    best, bv = "off", 0.0
    for name, tm in TMPLS.items():
        r = cv2.matchTemplate(mask, tm, cv2.TM_CCOEFF_NORMED)
        v = float(r.max())
        if v > bv: bv, best = v, name
    score = bv
    current = best.lower() if bv >= THRESH else "off"
    return current, bv

def loop():
    while _running:
        try: detect_once()
        except Exception: pass
        time.sleep(1.0)

threading.Thread(target=loop, daemon=True).start()
