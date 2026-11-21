import win32gui, win32con, win32api
import threading, time

boxes, fov = [], 80
draw_fov, draw_esp = True, True
running = True

def _own_window():
    import ctypes
    wc = win32gui.WNDCLASS()
    wc.lpfnWndProc = lambda h,m,w,l: win32gui.DefWindowProc(h,m,w,l)
    wc.lpszClassName = "ApexAI_OV"
    try: win32gui.RegisterClass(wc)
    except Exception: pass
    sw, sh = win32api.GetSystemMetrics(0), win32api.GetSystemMetrics(1)
    h = win32gui.CreateWindowEx(win32con.WS_EX_LAYERED|win32con.WS_EX_TRANSPARENT|win32con.WS_EX_TOPMOST|win32con.WS_EX_NOACTIVATE,
        "ApexAI_OV","ApexAI_OV",win32con.WS_POPUP,0,0,sw,sh,None,None,None,None)
    win32gui.SetLayeredWindowAttributes(h, 0, 255, win32con.LWA_ALPHA)
    ctypes.windll.dwmapi.DwmExtendFrameIntoClientArea(h, ctypes.byref(ctypes.c_int(-1)))
    win32gui.ShowWindow(h, win32con.SW_SHOW)
    print("[ov] fallback own window (detectable screen, stable)")
    return h

def get_overlay():
    h = win32gui.FindWindow("Chrome_WidgetWin_1", "Discord Overlay")
    if not h:
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, "Enable Discord overlay (Settings > Game Overlay), then relaunch the game.\nAim keeps running without overlay.", "Apex AI - Discord Overlay not found", 0x40)
        print("[!] no Discord overlay -> aim without overlay")
        return None
    ex = win32gui.GetWindowLong(h, win32con.GWL_EXSTYLE)
    win32gui.SetWindowLong(h, win32con.GWL_EXSTYLE, ex | win32con.WS_EX_LAYERED | win32con.WS_EX_TRANSPARENT)
    win32gui.SetLayeredWindowAttributes(h, 0, 255, win32con.LWA_ALPHA)
    import ctypes
    ctypes.windll.dwmapi.DwmExtendFrameIntoClientArea(h, ctypes.byref(ctypes.c_int(-1)))
    try:
        r = win32gui.GetWindowRect(h)
        vis = win32gui.IsWindowVisible(h)
        print(f"[ov] Discord rect={r} visible={vis}")
        if (r[2]-r[0]) < 100 or not vis:
            print("[ov] Discord hidden -> fallback own window")
            return _own_window()
    except Exception as e:
        print("[ov] rect err", e)
    return h

def draw_loop(h):
    dc = win32gui.GetDC(h)
    prev = []
    prev_fov = None
    while running:
        rect = win32gui.GetWindowRect(h)
        w, hgt = rect[2]-rect[0], rect[3]-rect[1]
        cx, cy = w//2, hgt//2
        brush_black = win32gui.GetStockObject(4)
        pen_black = win32gui.CreatePen(0, 1, 0x000000)
        ob, op = win32gui.SelectObject(dc, brush_black), win32gui.SelectObject(dc, pen_black)
        for x0,y0,x1,y1 in prev:
            win32gui.Rectangle(dc, int(x0)-2, int(y0)-2, int(x1)+2, int(y1)+2)
        win32gui.SelectObject(dc, ob); win32gui.SelectObject(dc, op)
        win32gui.DeleteObject(pen_black)
        cx, cy = w//2, hgt//2
        pen = win32gui.CreatePen(0, 1, 0xFFFFFF)
        brush = win32gui.GetStockObject(5)
        old_pen = win32gui.SelectObject(dc, pen)
        old_brush = win32gui.SelectObject(dc, brush)
        cur_fov = (cx, cy, fov) if draw_fov else None
        if prev_fov and prev_fov != cur_fov:
            _px, _py, _pr = prev_fov
            _bp = win32gui.CreatePen(0, 2, 0x000000)
            _ob = win32gui.SelectObject(dc, _bp)
            win32gui.Ellipse(dc, _px-_pr-2, _py-_pr-2, _px+_pr+2, _py+_pr+2)
            win32gui.SelectObject(dc, _ob)
            win32gui.DeleteObject(_bp)
        if draw_fov:
            win32gui.Ellipse(dc, cx-fov, cy-fov, cx+fov, cy+fov)
        if draw_esp:
            cur = []
            for x0,y0,x1,y1 in boxes:
                sx, sy = cx-120, cy-120
                r = (int(sx+x0), int(sy+y0), int(sx+x1), int(sy+y1))
                win32gui.Rectangle(dc, *r)
                cur.append(r)
        else:
            cur = []
        prev = cur
        prev_fov = (cx, cy, fov) if draw_fov else None
        win32gui.SelectObject(dc, old_pen)
        win32gui.SelectObject(dc, old_brush)
        win32gui.DeleteObject(pen)
        time.sleep(0.033)

def start():
    h = get_overlay()
    if h:
        print("[+] overlay Discord hijack OK")
        threading.Thread(target=draw_loop, args=(h,), daemon=True).start()
    return h
