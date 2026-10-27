"""
把梅梅当成一个真正的桌面应用打开 —— 不用浏览器，不用 Google Chrome。

为什么可以不用浏览器：Windows 10/11 自带一个叫 WebView2 的运行时（Edge 的内核，
但它是系统组件，不需要你打开 Edge、也不需要装 Chrome）。pywebview 把它嵌进一个
普通窗口里，所以界面还是这套网页，但你看到的已经是一个独立窗口：有自己的标题、
图标、任务栏按钮，没有地址栏，关掉它也不影响你平时上网的浏览器。

它跟旧的浏览器启动方式（已挪到 archive/old-browser-launcher/）做同样的事，
只是把最后一步"用浏览器打开"换成了"开自己的窗口"：
  1. 语音链路（9880 GPT-SoVITS / 9881 适配器 / 9882 识别）没开就后台开
  2. 应用本体（7788）没开就后台开
  3. 等端口就绪
  4. 开窗口

用法（双击桌面「梅梅」其实跑的就是它）：
    D:\\ai\\envs\\llm\\python.exe app\\desktop.py
可选参数：
    --workdir <目录>   梅梅能改的文件范围，默认 C:\\Users\\qqqqq\\Documents\\rm-workspace
    --port 7788        换个端口
    --debug            开右键菜单和 DevTools（按 F12）
    --no-voice         不动语音那三个服务（调试界面时快一点）
    --selftest         只做自检：开窗、检查麦克风/存储/界面，打印结果后自动关窗
"""

import argparse
import ctypes
import os
import socket
import subprocess
import sys
import threading
import time
from local_security import trusted_desktop_origin

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
LOGS = os.path.join(ROOT, "logs")

# 无边框窗口：顶部不再有 Windows 原生黑色标题栏。
# 拖动由页面里的 .pywebview-drag-region 负责，最小化/最大化/关闭由页面按钮调用 WindowCtl。
FRAMELESS = True
PYTHON = sys.executable

# 双击两次不该开出两个窗口，所以用一个只在本机占用的端口当"互斥锁"。
# 进程退出时系统自动释放，不会留下脏状态。
LOCK_PORT = 7791
_lock_socket = None


def take_single_instance_lock():
    """拿到锁返回 True；已经有另一个梅梅在跑就返回 False。"""
    global _lock_socket
    s = socket.socket()
    try:
        s.bind(("127.0.0.1", LOCK_PORT))
        s.listen(1)
    except OSError:
        s.close()
        return False
    _lock_socket = s
    return True


def focus_existing_window(title="梅梅"):
    """把已经在跑的那个窗口拉到最前面（不用弹框打扰你）。"""
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        found = []
        proto = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)

        def cb(hwnd, _):
            buf = ctypes.create_unicode_buffer(512)
            user32.GetWindowTextW(hwnd, buf, 512)
            if buf.value == title:
                found.append(hwnd)
            return True

        user32.EnumWindows(proto(cb), 0)
        for h in found:
            user32.ShowWindow(h, 9)          # SW_RESTORE：最小化的也还原
            user32.SetForegroundWindow(h)
        return bool(found)
    except Exception as e:
        print("[启动] 想把你已有的窗口拉到前面，但没成功：%s" % e)
        return False


def apply_dark_titlebar(title="梅梅"):
    """
    把窗口自带的那条标题栏改成深色。

    为什么需要这个：Windows 11 下传统的 Win32 窗口（WinForms 就是）默认永远是浅色标题栏，
    哪怕系统是深色主题也不跟随 —— 于是深色界面顶上顶着一条白的，很扎眼。
    要走 DWM 的"沉浸式深色"开关（属性 20，旧版本系统是 19）才会变深。
    """
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        dwmapi = ctypes.WinDLL("dwmapi", use_last_error=True)
        me = os.getpid()
        found = []
        proto = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)

        def cb(hwnd, _):
            buf = ctypes.create_unicode_buffer(512)
            user32.GetWindowTextW(hwnd, buf, 512)
            if buf.value == title:
                wpid = wintypes.DWORD()
                user32.GetWindowThreadProcessId(hwnd, ctypes.byref(wpid))
                if wpid.value == me:          # 只动自己这个进程的窗口
                    found.append(hwnd)
            return True

        user32.EnumWindows(proto(cb), 0)
        done = []
        for h in found:
            for attr in (20, 19):
                val = ctypes.c_int(1)
                rc = dwmapi.DwmSetWindowAttribute(
                    wintypes.HWND(h), ctypes.c_uint(attr),
                    ctypes.byref(val), ctypes.sizeof(val))
                if rc == 0:
                    done.append(attr)
                    break
            # 让窗口按新属性重画一次边框
            user32.SetWindowPos(wintypes.HWND(h), None, 0, 0, 0, 0, 0x0020 | 0x0002 | 0x0001)
        return done
    except Exception as e:
        print("[窗口] 深色标题栏没设上：%s" % e)
        return []


def tell_error(msg):
    """用 pythonw 启动时没有控制台，出错只能弹框，否则你什么都看不到。"""
    print(msg)
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, msg, "梅梅 · 启动失败", 0x30)
    except Exception:
        pass


def use_log_file():
    """pythonw 启动时 sys.stdout 是 None，把输出接到 logs\\desktop.log。"""
    if sys.stdout is not None and sys.stderr is not None:
        return
    os.makedirs(LOGS, exist_ok=True)
    f = open(os.path.join(LOGS, "desktop.log"), "a", encoding="utf-8", buffering=1)
    sys.stdout = sys.stderr = f


def port_open(port, host="127.0.0.1"):
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex((host, port)) == 0


def wait_port(port, timeout=90):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if port_open(port):
            return True
        time.sleep(0.4)
    return False


def start_background(args, log_name):
    """后台起一个进程，输出丢进 logs\\ 里，不弹控制台窗口。"""
    os.makedirs(LOGS, exist_ok=True)
    log = open(os.path.join(LOGS, log_name), "ab", buffering=0)
    flags = 0
    if os.name == "nt":
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
    return subprocess.Popen(args, cwd=ROOT, stdout=log, stderr=log,
                            stdin=subprocess.DEVNULL, creationflags=flags)


def ensure_services(port, workdir, with_voice=True):
    """需要谁就把谁拉起来；已经在跑的不管。"""
    started = []
    if with_voice and not all(port_open(p) for p in (9880, 9881, 9882)):
        start_background(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
                          "-WindowStyle", "Hidden", "-File",
                          os.path.join(ROOT, "启动语音.ps1")], "voice.log")
        started.append("语音链路")
    if not port_open(port):
        start_background([PYTHON, os.path.join(HERE, "agent_server.py"),
                          "--no-browser", "--port", str(port), "--workdir", workdir], "agent_server.log")
        started.append("应用服务")
    return started


def install_permission_patch(port=7788):
    """
    WebView2 默认不会替网页回答「能不能用麦克风」，不处理就等于拒绝，
    于是界面上的 🎙 语音输入会直接失败。这里在窗口初始化完成时挂上事件，
    仅为本应用的精确本机来源放行麦克风；其他来源与摄像头走默认权限流程。
    """
    try:
        from webview.platforms import edgechromium as ec
        from Microsoft.Web.WebView2.Core import CoreWebView2PermissionState
    except Exception as e:
        print("[窗口] 权限补丁没装上（%s），🎙 语音输入可能用不了" % e)
        return False

    def on_permission(sender, e):
        try:
            kind = str(e.PermissionKind)
            if "Microphone" in kind and trusted_desktop_origin(str(e.Uri),port):
                e.State = CoreWebView2PermissionState.Allow
        except Exception:
            pass

    orig = ec.EdgeChrome.on_webview_ready

    def patched(self, sender, args):
        orig(self, sender, args)
        try:
            if getattr(args, "IsSuccess", False):
                sender.CoreWebView2.PermissionRequested += on_permission
                print("[窗口] 已允许网页使用麦克风")
        except Exception as e:
            print("[窗口] 挂权限事件失败：%s" % e)

    ec.EdgeChrome.on_webview_ready = patched
    return True


def make_icon():
    """把素材里的图标转成窗口能用的 .ico（转失败就返回 None，不影响启动）。"""
    import json
    ico = os.path.join(HERE, "assets", "window.ico")
    if os.path.isfile(ico):
        return ico
    try:
        cfg = json.load(open(os.path.join(HERE, "appearance.json"), encoding="utf-8"))
        src = cfg.get("icon") or ""
        src = os.path.join(HERE, src) if src else ""
        if not src or not os.path.isfile(src):
            return None
        from PIL import Image
        img = Image.open(src).convert("RGBA")
        side = min(img.size)
        img = img.crop(((img.width - side) // 2, (img.height - side) // 2,
                        (img.width + side) // 2, (img.height + side) // 2))
        img.save(ico, sizes=[(256, 256), (64, 64), (48, 48), (32, 32), (16, 16)])
        return ico
    except Exception as e:
        print("[窗口] 图标没转成 .ico（%s），先用默认图标" % e)
        return None


def selftest(url):
    """
    自动验证这个窗口里该能用的东西是不是真能用：麦克风、播放器、本地存储。
    结果打到控制台，不靠肉眼看界面。
    """
    import webview

    time.sleep(1.0)
    window = webview.windows[0]
    # 注意：evaluate_js 不会等 Promise，所以让页面把结果写进 window.__r，Python 这边轮询
    probe = """
    window.__r = '';
    (async () => {
      const out = {};
      out.title = document.title;
      out.ready = document.readyState;
      out.menuBtn = !!document.getElementById('menu');
      out.assets = !!document.getElementById('bglayer');
      try {
        const ac = new (window.AudioContext || window.webkitAudioContext)();
        out.audioCtx = ac.state;
        await ac.close();
      } catch (e) { out.audioCtx = 'fail:' + e.name; }
      try {
        localStorage.setItem('rm_probe', 'ok');
        out.storage = localStorage.getItem('rm_probe') === 'ok' ? 'ok' : 'lost';
      } catch (e) { out.storage = 'fail:' + e.name; }
      try {
        const st = await navigator.mediaDevices.getUserMedia({audio: true});
        st.getTracks().forEach(t => t.stop());
        out.mic = 'ok';
      } catch (e) { out.mic = 'fail:' + e.name + ':' + e.message; }
      window.__r = JSON.stringify(out);
    })();
    'started'
    """
    try:
        print("[自检] 页面 =", window.get_current_url())
        window.evaluate_js(probe)
        res = ""
        for _ in range(40):                     # 麦克风授权可能要等两三秒
            time.sleep(0.5)
            res = window.evaluate_js("window.__r || ''")
            if res:
                break
        print("[自检] 结果 =", res or "(页面没回结果)")
    except Exception as e:
        print("[自检] 失败：%s" % e)
    time.sleep(0.5)
    window.destroy()


class WindowCtl:
    """给页面里的自定义标题栏按钮用：最小化 / 最大化还原 / 关闭。"""

    def _hwnd(self):
        return ctypes.windll.user32.FindWindowW(None, "梅梅")

    def minimize(self):
        h = self._hwnd()
        if h:
            ctypes.windll.user32.ShowWindow(h, 6)      # SW_MINIMIZE

    def toggle_max(self):
        h = self._hwnd()
        if h:
            if ctypes.windll.user32.IsZoomed(h):
                ctypes.windll.user32.ShowWindow(h, 9)  # SW_RESTORE
            else:
                ctypes.windll.user32.ShowWindow(h, 3)  # SW_MAXIMIZE

    def close(self):
        h = self._hwnd()
        if h:
            ctypes.windll.user32.PostMessageW(h, 0x0010, 0, 0)  # WM_CLOSE


def on_start(url, do_selftest=False):
    """窗口出现后要做的事：先把标题栏涂深，需要自检就顺便自检一遍。"""
    if not FRAMELESS:
        for _ in range(24):             # 窗口要等一会儿才真正创建出来
            time.sleep(0.25)
            if apply_dark_titlebar():
                print("[窗口] 标题栏已切成深色")
                break
    else:
        print("[窗口] 无边框模式：使用页面内悬浮窗口按钮")
    if do_selftest:
        selftest(url)


def watch_backend(port, workdir, url, window, with_voice=True, every=6):
    """
    看护应用服务：挂了就拉起来，并把窗口重新加载一遍。

    为什么需要：这是跑在本机的小服务，没有任何人看着。实测遇到过一次
    agent_server 进程凭空消失 —— 日志最后一行还是成功的请求、系统日志里也没有
    崩溃记录 —— 结果就是页面还开着、背景视频卡在最后一帧不动，
    看起来像"界面卡住了"，其实是后端已经没了（视频是流式从后端取的，后端一没，
    播放器要不到下一段数据就停在那儿）。
    现在由窗口进程负责看护：发现端口不在监听就重新拉起，然后让窗口重新加载页面。
    """
    while True:
        time.sleep(every)
        try:
            if port_open(port):
                continue
            print("[看护] %s 不在监听了，正在重新拉起" % port)
            ensure_services(port, workdir, with_voice=with_voice)
            if wait_port(port, timeout=90):
                print("[看护] 后端已恢复")
                try:
                    # 用 evaluate_js 让页面自己 reload：实测 window.load_url()
                    # 从别的线程调过去不一定生效（日志里看不到 GET /），
                    # 而 evaluate_js 是可靠的。
                    window.evaluate_js("location.reload()")
                    print("[看护] 已让窗口重新加载")
                except Exception as e:
                    print("[看护] 重新加载窗口失败：%s" % e)
            else:
                print("[看护] 拉不起来，90 秒后再试（看 logs\\agent_server.log）")
                time.sleep(30)
        except Exception as e:
            print("[看护] 出错：%s" % e)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workdir", default=os.path.join(os.path.expanduser("~"),
                                                     "Documents", "rm-workspace"))
    ap.add_argument("--port", type=int, default=7788)
    ap.add_argument("--debug", action="store_true")
    ap.add_argument("--no-voice", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--startup-delay", type=int, default=0,
                    help="开机自启时先等几秒再拉服务（登录瞬间机器很忙）")
    opts = ap.parse_args()          # 注意别叫 args：webview.start 自己也有个 args 参数

    use_log_file()

    if opts.startup_delay > 0:
        print("[启动] 开机自启模式：先等 %d 秒，避开登录瞬间的拥堵" % opts.startup_delay)
        time.sleep(opts.startup_delay)

    if not take_single_instance_lock():
        focus_existing_window()
        print("[启动] 已经有一个梅梅在跑了，把它的窗口拉到前面就好，不重复开。")
        return 0

    os.makedirs(opts.workdir, exist_ok=True)
    # 带版本参数启动，避免 WebView2 复用上一次的 agent.html 缓存：
    # 之前出现过“第一次打开还是旧排版，最大化再缩回才正常”。
    url = "http://127.0.0.1:%d/?v=%d" % (opts.port, int(time.time()))

    started = ensure_services(opts.port, opts.workdir, with_voice=not opts.no_voice)
    if started:
        print("[启动] 拉起来了：%s" % "、".join(started))
    if not wait_port(opts.port, timeout=120):
        tell_error("应用服务没起来，可能是端口被占或者脚本报错了。\n"
                   "日志：%s\\agent_server.log\n\n"
                   "想要看得见的报错窗口，就双击 toolkit 目录里的「启动阮梅.bat」。" % LOGS)
        return 1

    import webview
    install_permission_patch(opts.port)
    webview.settings["OPEN_EXTERNAL_LINKS_IN_BROWSER"] = True
    webview.settings["DRAG_REGION_DIRECT_TARGET_ONLY"] = True
    if opts.debug:
        webview.settings["REMOTE_DEBUGGING_PORT"] = 9223

    window = webview.create_window(
        "梅梅", url, width=1280, height=860, min_size=(900, 620),
        background_color="#07100e", text_select=True,
        frameless=FRAMELESS, easy_drag=True, shadow=True,
        js_api=WindowCtl(),
    )
    print("[启动] 窗口开了：%s（内核 WebView2，不经过浏览器）" % url)

    storage = os.path.join(HERE, "desktop-profile")
    # 看护线程：后台服务挂了就拉起来 + 重新加载页面
    threading.Thread(target=watch_backend,
                     args=(opts.port, opts.workdir, url, window),
                     kwargs={"with_voice": not opts.no_voice},
                     daemon=True).start()

    # start 的回调在另一个线程里跑，所以里面只做 Win32 调用和窗口方法，别直接碰界面控件
    webview.start(on_start, args=(url, opts.selftest),
                  debug=opts.debug, private_mode=False, storage_path=storage,
                  icon=make_icon(), gui="edgechromium")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception:
        import traceback
        tb = traceback.format_exc()
        tell_error("梅梅没起来：\n\n%s\n\n日志：%s\\desktop.log" % (tb[-1200:], LOGS))
        sys.exit(1)
