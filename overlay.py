import win32gui, win32con, win32api
import threading, time
import ctypes

boxes, fov = [], 80
draw_fov, draw_esp = True, True
running = True

class MARGINS(ctypes.Structure):
    _fields_ = [("cxLeftWidth", ctypes.c_int), ("cxRightWidth", ctypes.c_int), ("cyTopHeight", ctypes.c_int), ("cyBottomHeight", ctypes.c_int)]

def _own_window():
    wc = win32gui.WNDCLASS()
    wc.lpfnWndProc = lambda h,m,w,l: win32gui.DefWindowProc(h,m,w,l)
    wc.lpszClassName = "ApexAI_OV"
    try:
        win32gui.RegisterClass(wc)
    except Exception:
        pass
    sw, sh = win32api.GetSystemMetrics(0), win32api.GetSystemMetrics(1)
    h = win32gui.CreateWindowEx(
        win32con.WS_EX_LAYERED | win32con.WS_EX_TRANSPARENT | win32con.WS_EX_TOPMOST | win32con.WS_EX_NOACTIVATE,
        "ApexAI_OV", "ApexAI_OV", win32con.WS_POPUP, 0, 0, sw, sh, None, None, None, None
    )
    if not h:
        print("[!] CreateWindowEx failed")
        return None
    win32gui.SetLayeredWindowAttributes(h, 0, 255, win32con.LWA_ALPHA)
    try:
        margins = MARGINS(-1, -1, -1, -1)
        ctypes.windll.dwmapi.DwmExtendFrameIntoClientArea(h, ctypes.byref(margins))
    except Exception as e:
        print("[ov] DwmExtendFrameIntoClientArea failed:", e)
    win32gui.ShowWindow(h, win32con.SW_SHOW)
    win32gui.UpdateWindow(h)
    print("[ov] fallback own window created")
    return h

def get_overlay():
    h = win32gui.FindWindow("Chrome_WidgetWin_1", "Discord Overlay")
    if not h:
        print("[!] Discord overlay not found -> using own window")
        return _own_window()
    ex = win32gui.GetWindowLong(h, win32con.GWL_EXSTYLE)
    win32gui.SetWindowLong(h, win32con.GWL_EXSTYLE, ex | win32con.WS_EX_LAYERED | win32con.WS_EX_TRANSPARENT)
    win32gui.SetLayeredWindowAttributes(h, 0, 255, win32con.LWA_ALPHA)
    try:
        margins = MARGINS(-1, -1, -1, -1)
        ctypes.windll.dwmapi.DwmExtendFrameIntoClientArea(h, ctypes.byref(margins))
    except Exception as e:
        print("[ov] DwmExtendFrameIntoClientArea failed:", e)
    try:
        r = win32gui.GetWindowRect(h)
        vis = win32gui.IsWindowVisible(h)
        print(f"[ov] Discord rect={r} visible={vis}")
        if (r[2] - r[0]) < 100 or not vis:
            print("[ov] Discord hidden -> fallback own window")
            return _own_window()
    except Exception as e:
        print("[ov] rect err:", e)
        return _own_window()
    return h

def draw_loop(h):
    if not h:
        print("[!] draw_loop: no window handle")
        return
    prev = []
    prev_fov = None
    while running:
        try:
            dc = win32gui.GetDC(h)
            if not dc:
                time.sleep(0.1)
                continue
            try:
                rect = win32gui.GetWindowRect(h)
                if not rect:
                    break
                w, hgt = rect[2] - rect[0], rect[3] - rect[1]
                if w <= 0 or hgt <= 0:
                    time.sleep(0.033)
                    continue
                cx, cy = w // 2, hgt // 2

                # Clear previous drawings
                brush_black = win32gui.GetStockObject(4)
                pen_black = win32gui.CreatePen(0, 1, 0x000000)
                ob = win32gui.SelectObject(dc, brush_black)
                op = win32gui.SelectObject(dc, pen_black)
                for x0, y0, x1, y1 in prev:
                    win32gui.Rectangle(dc, int(x0) - 2, int(y0) - 2, int(x1) + 2, int(y1) + 2)
                if prev_fov:
                    _px, _py, _pr = prev_fov
                    win32gui.Ellipse(dc, _px - _pr - 2, _py - _pr - 2, _px + _pr + 2, _py + _pr + 2)
                win32gui.SelectObject(dc, ob)
                win32gui.SelectObject(dc, op)
                win32gui.DeleteObject(pen_black)

                # Draw new
                pen = win32gui.CreatePen(0, 1, 0xFFFFFF)
                brush = win32gui.GetStockObject(5)
                old_pen = win32gui.SelectObject(dc, pen)
                old_brush = win32gui.SelectObject(dc, brush)

                if draw_fov:
                    win32gui.Ellipse(dc, cx - fov, cy - fov, cx + fov, cy + fov)
                    prev_fov = (cx, cy, fov)
                else:
                    prev_fov = None

                cur = []
                if draw_esp:
                    for box in boxes:
                        if len(box) < 4:
                            continue
                        x0, y0, x1, y1 = box[:4]
                        # Boxes are relative to capture center (CW/2, CH/2)
                        # Scale to screen center
                        r = (int(cx + x0 - 120), int(cy + y0 - 120), int(cx + x1 - 120), int(cy + y1 - 120))
                        if r[0] >= 0 and r[1] >= 0 and r[2] > r[0] and r[3] > r[1]:
                            win32gui.Rectangle(dc, *r)
                            cur.append(r)
                prev = cur

                win32gui.SelectObject(dc, old_pen)
                win32gui.SelectObject(dc, old_brush)
                win32gui.DeleteObject(pen)
            finally:
                win32gui.ReleaseDC(h, dc)
            time.sleep(0.033)
        except Exception as e:
            print("[ov] draw error:", e)
            time.sleep(0.1)

def start():
    h = get_overlay()
    if h:
        print("[+] overlay started")
        t = threading.Thread(target=draw_loop, args=(h,), daemon=True)
        t.start()
        return h
    else:
        print("[!] overlay failed to start")
        return None
