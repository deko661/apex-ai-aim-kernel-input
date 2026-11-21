import time, threading
import win32api

from recoil_pat import PATTERNS
enabled, strength = True, 1.0
_move = None
_firing = False
_cfg = None

def bind(move_fn, cfg=None):
    global _move, _cfg
    _move = move_fn; _cfg = cfg

def loop(get_weapon):
    global _firing
    idx = 0
    ox, oy = 0.0, 0.0
    while True:
        _game = _cfg.get("game", "apex") if _cfg else "apex"
        lmb = bool(win32api.GetAsyncKeyState(0x01) & 0x8000) and _game == "apex"
        try:
            if _cfg and _cfg.get("rc_on", True):
                pass
        except Exception: pass
        on = (_cfg.get("rc_on", True) if _cfg else enabled)
        if isinstance(on, str): on = (on == "true")
        fx = float(_cfg.get("rc_x", 100))/100.0 if _cfg else 1.0
        fy = float(_cfg.get("rc_y", 100))/100.0 if _cfg else strength
        if on and lmb and _move:
            w = get_weapon().lower()
            p = PATTERNS.get(w)
            if p:
                if not _firing:
                    idx, _firing, ox, oy = 0, True, 0.0, 0.0
                    if p.get("delay", 0) > 0:
                        time.sleep(p["delay"]/1000.0)
                if idx >= len(p["steps"]):
                    time.sleep(1.0/p["hz"]); continue
                s = p["steps"][idx]
                ox += s[0]*fx; oy += s[1]*fy
                ix, iy = int(ox), int(oy)
                ox -= ix; oy -= iy
                if ix or iy: _move(ix, iy)
                try:
                    import __main__ as _m
                    _m.STATS["log"] = f"rc {w} #{idx}"
                except Exception: pass
                if idx % 6 == 0:
                    print(f"[rc] {w} #{idx} dx={ix} dy={iy} fx={fx:.2f} fy={fy:.2f}", flush=True)
                idx += 1
                _ms = s[2] if len(s) > 2 and s[2] else 0
                time.sleep((_ms/1000.0) if _ms else (1.0/p["hz"]))
                continue
        _firing, idx = False, 0
        time.sleep(0.005)

def start(get_weapon):
    threading.Thread(target=lambda: loop(get_weapon), daemon=True).start()
