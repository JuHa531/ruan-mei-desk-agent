# -*- coding: utf-8 -*-
r"""
梅梅 本地 Agent —— 会动手的版本（不只是聊天）。

和 server.py 的区别
-------------------
server.py    纯聊天：你问，它答
本文件        会调用工具：能列目录、读文件、写文件、执行命令、搜文件，
              然后根据结果继续推理，直到给出结论（这就是 agent 循环）

用法
----
    D:\ai\envs\llm\python.exe app\agent_server.py --workdir "G:\我的项目"
    浏览器打开 http://127.0.0.1:7788

外观（背景图/视频、图标）
------------------------
把素材丢进 app\assets\ 就行，两种方式任选：

  A. 改名法（最省事）
       背景图/背景视频 ->  bg.jpg / bg.png / bg.mp4 ...
       图标           ->  icon.png / icon.ico / icon.svg ...
     服务启动时自动认，什么都不用配。

  B. 配置文件法
       写 app\appearance.json：{"bg_type":"image","bg_file":"assets/x.jpg","icon":"assets/y.png"}

两种都不用重启也能改：界面右上角「外观」里可以现场切换，
改完会写回 appearance.json。

界面里还能直接把别处的文件（比如 D:\图片\a.png）导入素材库。
"""

import argparse
import collections
import datetime
import glob
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
import urllib.parse
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from local_security import LocalRequestHandler, canonical_path, path_within, bounded_matches

import office_tools          # 同目录：PPT / Word / Excel / 视频这几个产出型工具

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

# Windows 上，从一个"没有控制台"的进程里起一个控制台程序（powershell / cmd /
# tasklist / nvidia-smi …），系统默认会给它开一个新的控制台窗口 —— 用户看到的就是
# 黑框一闪、或者一直挂在桌面上（实测抓到的窗口标题正是
# "C:\WINDOWS\System32\WindowsPowerShell\v1.0\powershell.exe"）。
# 这个标志的意思是"给它控制台，但别显示窗口"。
# 项目里所有起子进程的地方都统一走 run_hidden()。
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)


def run_hidden(args, **kw):
    """subprocess.run 的包装：一律不弹控制台窗口。"""
    kw["creationflags"] = kw.get("creationflags", 0) | CREATE_NO_WINDOW
    return subprocess.run(args, **kw)
ASSETS_DIR = os.path.join(HERE, "assets")
APPEARANCE_FILE = os.path.join(HERE, "appearance.json")

# 主人交代过的习惯/偏好。放在 data\ 里（不在沙箱工作目录内），
# 有意做成 Markdown：梅梅能自己往里写，你也能直接打开改。
HABITS_FILE = os.path.join(ROOT, "data", "习惯.md")
REMINDERS_FILE = os.path.join(ROOT, "data", "提醒.json")
FIRED_FILE = os.path.join(ROOT, "data", "提醒记录.json")
LISTEN_FILE = os.path.join(ROOT, "data", "听歌记录.json")
RUANMEI_STORY_FILE = os.path.join(ROOT, "data", "阮梅角色故事.md")
RUANMEI_MODELFILE = os.path.join(ROOT, "ruanmei.Modelfile")

# 到点提醒 = 服务器自己合成语音 + 用这台机器的音箱放出来。
# 为什么不靠页面：页面没开（或者最小化）也得响，这才是"日用"。
WAKE_WORD = "亲爱的"
HABITS_HEADER = """# 主人的习惯

> 这个文件每次对话都会读给梅梅听。写"以后都这样"的长期偏好，别写一次性的临时要求。
> 梅梅自己也能改：它注意到你的习惯时会用 remember 记进来；你直接编辑这个文件也一样生效。

"""

IMAGE_EXT = (".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp")
VIDEO_EXT = (".mp4", ".webm", ".m4v", ".mov")
ICON_EXT = IMAGE_EXT + (".ico", ".svg")

# see_image 能处理的图片格式
READ_IMAGE_EXT = IMAGE_EXT + (".tif", ".tiff")
OCR_SCRIPT = os.path.join(HERE, "ocr_image.ps1")

# 一条命令拿到整机状态：CPU（型号/使用率/温度）、内存、显卡、占用最高的进程。
# 为什么要专门做这个工具：nvidia-smi 只给显卡信息，用户问"某个监控里 CPU 显示 -1"时，
# 模型拿 nvidia-smi 的结果答不了，就会退回成"建议你重装驱动"。给个一次到位的工具，
# 它就能拿到 CPU 那部分数据（包括"Windows 不提供 CPU 温度"这件事本身）。
SYSINFO_SCRIPT = """
$ErrorActionPreference = "SilentlyContinue"
$out = New-Object System.Collections.ArrayList
$cpu = Get-CimInstance Win32_Processor | Select-Object -First 1
[void]$out.Add("CPU 型号: " + $cpu.Name)
[void]$out.Add("逻辑核心: " + $cpu.NumberOfLogicalProcessors + "，当前主频: " + $cpu.CurrentClockSpeed + " MHz")
$load = (Get-CimInstance Win32_Processor | Measure-Object -Property LoadPercentage -Average).Average
$loadTxt = [string][math]::Round($load,1)
[void]$out.Add("CPU 使用率: " + $loadTxt + " %  （读到了）")
$tz = Get-CimInstance -Namespace root/wmi -ClassName MSAcpi_ThermalZoneTemperature -ErrorAction SilentlyContinue
$tempTxt = ""
if ($tz) {
    $t = ($tz | ForEach-Object { ($_.CurrentTemperature / 10) - 273.15 } | Measure-Object -Average).Average
    $tempTxt = [string][math]::Round($t,1) + " 摄氏度（读到了）"
} else {
    $tempTxt = "读不到（不是故障：Windows 默认不允许普通程序读 CPU 温度，要装 LibreHardwareMonitor 这类带驱动的工具才读得到）"
}
[void]$out.Add("CPU 温度: " + $tempTxt)
$os = Get-CimInstance Win32_OperatingSystem
[void]$out.Add("内存: 共 " + [math]::Round($os.TotalVisibleMemorySize/1MB,1) + " GB，可用 " + [math]::Round($os.FreePhysicalMemory/1MB,1) + " GB")
$gpus = Get-CimInstance Win32_VideoController | Where-Object { $_.Name -match "NVIDIA|AMD|Intel|显卡" }
foreach ($g in $gpus) { [void]$out.Add("显卡: " + $g.Name + "（驱动 " + $g.DriverVersion + "）") }
$names = @()
Get-Process | Sort-Object CPU -Descending | Select-Object -First 3 |
    ForEach-Object { $names += ($_.ProcessName + "（占内存 " + [math]::Round($_.WorkingSet64/1MB) + " MB）") }
[void]$out.Add("占资源最多的进程: " + ($names -join "、"))
$head = "照这句说：实测 CPU 使用率是 " + $loadTxt + "%，这个能读到（对方那边显示 -1 是他那个软件没读到，不是没有数据）；CPU 温度" + $tempTxt + "。"
("[系统信息] " + $head) + "`n——下面是从这台机器直接读到的实测明细 ——`n" + ($out -join "`n")
"""


def system_info(timeout=120):
    """跑一段 PowerShell 收集整机状态。"""
    r = run_hidden(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
                        "-Command", SYSINFO_SCRIPT],
                       capture_output=True, timeout=timeout)
    txt = r.stdout.decode("utf-8", "replace").strip()
    if not txt:
        txt = "[系统信息] 没取到。" + r.stderr.decode("utf-8", "replace")[:300]
    return ("[系统信息]\n" + txt +
            "\n\n（回答时请照抄这里的实测值。如果用户说某个数值是 -1，"
            "而这里显示读到了，就直接告诉他实测是多少、并说明他那边的 -1 是数据源的问题。）")


# 显卡 / 显示器 / 叠加层这一摊事，问的都是同一批数据。单独做一个工具，
# 是因为之前它只会跑 nvidia-smi，然后从那串"进程列表"里瞎猜原因
# （实测它给出的结论是"这些程序占用了 GPU 导致 FPS 显示 N/A" —— 站不住脚）。
# FPS 计数器真正要看的：谁在渲染、谁在输出到显示器、叠加层进程在不在、
# 每个程序的显卡偏好是什么、硬件加速 GPU 计划开没开。
GPU_SCRIPT = r"""
$ErrorActionPreference = "SilentlyContinue"
$adapters = @(Get-CimInstance Win32_VideoController | ForEach-Object {
    [pscustomobject]@{ name = $_.Name; driver = $_.DriverVersion
                       w = $_.CurrentHorizontalResolution; h = $_.CurrentVerticalResolution
                       hz = $_.CurrentRefreshRate } })
$prefs = @()
$gpuPref = Get-ItemProperty "HKCU:\Software\Microsoft\DirectX\UserGpuPreferences"
foreach ($n in (($gpuPref | Get-Member -MemberType NoteProperty).Name | Where-Object { $_ -like "*exe" })) {
    $prefs += [pscustomobject]@{ exe = (Split-Path $n -Leaf); value = $gpuPref.$n }
}
$obj = [pscustomobject]@{
    adapters = $adapters
    prefs    = $prefs
    hags     = (Get-ItemProperty "HKLM:\SYSTEM\CurrentControlSet\Control\GraphicsDrivers" -Name HwSchMode).HwSchMode
    nvproc   = @(Get-Process | Where-Object { $_.ProcessName -match "NVIDIA|nvcontainer" } |
                 ForEach-Object { $_.ProcessName })
    nvapp    = (Get-ChildItem "C:\Program Files\NVIDIA Corporation" -Recurse -Filter "NVIDIA app.exe" -ErrorAction SilentlyContinue |
                Select-Object -First 1).VersionInfo.FileVersion
}
$obj | ConvertTo-Json -Depth 4 -Compress
"""


def gpu_check(timeout=180):
    """
    显卡 / 显示器 / 叠加层的实测状态，一次查完 —— 并且**在这里就把结论算出来**。

    为什么不把"怎么解读"丢给模型：实测过。把解读要点写在工具输出里，4B 模型会
    原样抄成"可能的原因有四点…"，一条对应它自己的机器都不落地。所以这里用代码判断
    拓扑（哪块卡在带显示器、叠加层在不在、HAGS 开没开），把结论摆在第一行，
    模型只负责复述 —— 这就是这个项目里 SYSINFO 那套"照这句说"的做法。
    """
    info, raw = {}, []
    try:
        r = run_hidden(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
                            "-Command", GPU_SCRIPT], capture_output=True, timeout=timeout)
        txt = r.stdout.decode("utf-8", "replace").strip()
        if txt:
            info = json.loads(txt.lstrip("\ufeff"))
    except Exception as e:
        raw.append("(PowerShell 那段没取到：%s)" % e)

    smi = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"),
                       "System32", "nvidia-smi.exe")
    if not os.path.isfile(smi):
        smi = "nvidia-smi"
    smi_txt = ""
    try:
        r = run_hidden([smi, "--query-gpu=name,driver_version,display_active,"
                            "display_attached,utilization.gpu,memory.used,memory.total,"
                            "pcie.link.gen.current,pcie.link.width.current",
                            "--format=csv"], capture_output=True, timeout=60)
        smi_txt = r.stdout.decode("utf-8", "replace").strip()
    except Exception as e:
        smi_txt = "(nvidia-smi 跑不动：%s)" % e

    adapters = info.get("adapters") or []
    if isinstance(adapters, dict):
        adapters = [adapters]
    nv_proc = info.get("nvproc") or []
    if isinstance(nv_proc, str):
        nv_proc = [nv_proc]
    hags = info.get("hags")

    def drives_display(a):
        try:
            return int(a.get("w") or 0) > 0 and int(a.get("h") or 0) > 0
        except (TypeError, ValueError):
            return False

    igpu = [a for a in adapters if re.search(r"Intel|AMD|Radeon", a.get("name") or "", re.I)]
    dgpu = [a for a in adapters if re.search(r"NVIDIA|GeForce|RTX|GTX", a.get("name") or "", re.I)]
    igpu_on = [a for a in igpu if drives_display(a)]
    dgpu_on = [a for a in dgpu if drives_display(a)]

    # ---- 结论（放在最前面，让模型照抄）
    concl = []
    if igpu and dgpu:
        concl.append("这台是双显卡机器")
        if igpu_on:
            a = igpu_on[0]
            concl.append("而且有显示器是核显（%s）在带：%sx%s @%sHz"
                         % (a.get("name"), a.get("w"), a.get("h"), a.get("hz")))
        if dgpu_on:
            a = dgpu_on[0]
            concl.append("另一路是独显直连：%sx%s @%sHz"
                         % (a.get("w"), a.get("h"), a.get("hz")))
        if igpu_on and dgpu_on:
            concl.append("NVIDIA 的 FPS 计数器靠采集「这张卡呈现画面的时刻」来算帧数；"
                         "当游戏在独显渲染、画面却由核显输出到那块屏幕时，它经常采不到，"
                         "显示的 N/A 就是这个原因 —— 不是驱动坏了")
            concl.append("能做的：① 用机器自带控制中心切到「独显直连/独显输出」再试；"
                         "② 或者在直连独显的那台显示器上玩")
        elif igpu_on and not dgpu_on:
            concl.append("所有显示器都由核显输出，独显只做渲染 —— 这种「混合输出」下"
                         "NVIDIA 的 FPS 计数器基本读不到，N/A 是必然的")
    if not nv_proc:
        concl.append("NVIDIA 的叠加层进程一个都没在跑，那一定显示不出帧数，"
                     "先在 NVIDIA App 里把叠加层打开")
    if hags != 2:
        concl.append("另外「硬件加速 GPU 计划」(HAGS) 当前没开，"
                     "可以在系统设置里打开再重启试一次")
    if concl:
        concl.append("剩下这些步骤只能你自己做：它们都是图形界面里的开关"
                     "（控制中心的显示模式、系统设置的 HAGS），命令行改不了，我也做不了")
        concl.append("做完回游戏里开一次叠加层看帧数出不出来，就知道有没有好")
    if not concl:
        concl.append("没找到明显的拓扑问题，需要看下面的明细")

    lines = ["== 显示适配器（显示器由谁驱动）=="]
    for a in adapters:
        lines.append("- %s | 驱动 %s | %sx%s @%sHz"
                     % (a.get("name"), a.get("driver"), a.get("w"), a.get("h"), a.get("hz")))
    lines.append("== 每个程序的显卡偏好（Windows 设置 → 屏幕 → 显示卡）==")
    seen = {}
    for p in (info.get("prefs") or []):
        v = str(p.get("value") or "")
        friendly = ("省电(走核显)" if "GpuPreference=1" in v else
                    "高性能(走独显)" if "GpuPreference=2" in v else v.replace("\n", " "))
        seen["%s -> %s" % (p.get("exe"), friendly)] = True
    lines += ["- " + k for k in sorted(seen)] or ["(没有任何程序被单独设置过)"]
    lines.append("== 硬件加速 GPU 计划 (HAGS) ==")
    lines.append("HwSchMode = %s%s" % (hags, "（已开启）" if hags == 2 else "（未开启）"))
    lines.append("== NVIDIA 相关进程 ==")
    lines.append("、".join(sorted(set(nv_proc))) if nv_proc else "(一个都没在跑)")
    if info.get("nvapp"):
        lines.append("NVIDIA app 版本 = %s" % info["nvapp"])
    lines.append("== nvidia-smi 摘要 ==")
    lines.append(smi_txt or "(没取到)")

    head = ("照这句说：%s。\n" % "；".join(concl)) if concl else ""
    return ("[显卡与显示]\n" + head +
            "==== 实测明细 ====\n" + clip("\n".join(lines), head=1600, tail=400))


def asset_kind(name):
    low = name.lower()
    for e in VIDEO_EXT:
        if low.endswith(e):
            return "video"
    for e in IMAGE_EXT:
        if low.endswith(e):
            return "image"
    if low.endswith((".ico", ".svg")):
        return "icon"
    return "other"


def list_assets():
    """素材库里的文件清单，给界面上的下拉框用。"""
    out = []
    if os.path.isdir(ASSETS_DIR):
        for n in sorted(os.listdir(ASSETS_DIR)):
            fp = os.path.join(ASSETS_DIR, n)
            if not os.path.isfile(fp):
                continue
            kind = asset_kind(n)
            if kind == "other":
                continue
            out.append({"name": n, "path": "assets/" + n, "kind": kind,
                        "size": os.path.getsize(fp)})
    return out


CFG = {}          # main() 里填，定时提醒线程要用（TTS 地址、音色）


# ---------------------------------------------------------------------------
# 定时提醒：服务器自己看着表，到点合成她的声音 + 本机放出来
# ---------------------------------------------------------------------------

def load_reminders():
    try:
        with open(REMINDERS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        items = data.get("items") if isinstance(data, dict) else data
        return items or []
    except Exception:
        return []


def save_reminders(items):
    os.makedirs(os.path.dirname(REMINDERS_FILE), exist_ok=True)
    with open(REMINDERS_FILE, "w", encoding="utf-8") as f:
        json.dump({"items": items}, f, ensure_ascii=False, indent=2)


def load_fired(limit=40):
    try:
        with open(FIRED_FILE, "r", encoding="utf-8") as f:
            recs = json.load(f)
        return recs[-limit:] if isinstance(recs, list) else []
    except Exception:
        return []


def remember_fired(item, when, ok, note=""):
    recs = load_fired(200)
    recs.append({"at": when, "text": item.get("text", ""), "ok": bool(ok), "note": note})
    os.makedirs(os.path.dirname(FIRED_FILE), exist_ok=True)
    with open(FIRED_FILE, "w", encoding="utf-8") as f:
        json.dump(recs[-200:], f, ensure_ascii=False, indent=2)


def _norm_time(s):
    """把 7:5 / 07:05 / 7点05 这类写法统一成 HH:MM。"""
    m = re.fullmatch(r"\s*(\d{1,2})\s*[:：点]\s*(\d{1,2})?\s*分?\s*", str(s or ""))
    if not m:
        return ""
    h, mi = int(m.group(1)), int(m.group(2) or 0)
    if h > 23 or mi > 59:
        return ""
    return "%02d:%02d" % (h, mi)


def reminder_add(text, at, repeat="daily", days=None, date=""):
    text = " ".join(str(text or "").split())
    if not text:
        return "[工具出错] 要提醒的内容是空的。"
    hhmm = _norm_time(at)
    if not hhmm:
        return "[工具出错] 时间看不懂（%s）。写成 23:00 这种 24 小时制就行。" % at
    repeat = (repeat or "daily").strip().lower()
    alias = {"每天": "daily", "每日": "daily", "工作日": "weekdays", "weekly": "weekly",
             "每周": "weekly", "一次": "once", "once": "once", "daily": "daily",
             "weekdays": "weekdays", "工作日一至五": "weekdays"}
    repeat = alias.get(repeat, repeat)
    if repeat not in ("daily", "weekdays", "weekly", "once"):
        repeat = "daily"
    ds = []
    for d in (days or []):
        try:
            n = int(d)
            if 1 <= n <= 7:
                ds.append(n)
        except (TypeError, ValueError):
            pass
    items = load_reminders()
    item = {"id": "r%d" % int(time.time() * 1000), "text": text, "time": hhmm,
            "repeat": repeat, "days": ds, "date": str(date or "").strip(),
            "voice": True, "enabled": True, "last_fired": ""}
    items.append(item)
    save_reminders(items)
    when = {"daily": "每天", "weekdays": "工作日", "weekly": "每周%s" % (
        "/".join("一二三四五六日"[d - 1] for d in ds) if ds else ""),
        "once": "只响一次（%s）" % (item["date"] or "今天")}[repeat]
    return ("定了：%s %s 提醒「%s」（id=%s）。到点我会用她的声音念出来 —— "
            "前提是梅梅在运行（窗口开着）。" % (when, hhmm, text, item["id"]))


def reminder_list():
    items = load_reminders()
    if not items:
        return "现在没有任何提醒。要加就说清「几点 + 提醒什么 + 重复方式」。"
    cn = {"daily": "每天", "weekdays": "工作日", "weekly": "每周", "once": "一次"}
    out = []
    for it in items:
        extra = ("，周" + "/".join("一二三四五六日"[d - 1] for d in it.get("days") or [])
                 if it.get("days") else "")
        out.append("- %s %s%s%s ｜ %s" % (it.get("time"), cn.get(it.get("repeat"), it.get("repeat")),
                                          extra, "" if it.get("enabled", True) else "（已暂停）",
                                          it.get("text")))
    fired = load_fired(3)
    tail = ""
    if fired:
        tail = "\n最近响过：" + "；".join("%s %s" % (r.get("at"), r.get("text")) for r in fired)
    return "\n".join(out) + tail


def reminder_del(keyword):
    keyword = str(keyword or "").strip()
    if not keyword:
        return "[工具出错] 说个关键词，我才知道删哪条。"
    items = load_reminders()
    kept = [it for it in items
            if keyword not in str(it.get("text", "")) and keyword != str(it.get("id", ""))]
    if len(kept) == len(items):
        return "没找到含「%s」的提醒。现在是：\n%s" % (keyword, reminder_list())
    save_reminders(kept)
    return "删掉了 %d 条。剩下的：\n%s" % (len(items) - len(kept), reminder_list())


SMTC_SCRIPT = os.path.join(HERE, "smtc.ps1")
MUSIC_EXE_CANDIDATES = [
    r"D:\夸克\QQ\QQMusic\QQMusic.exe",
    r"C:\Program Files\Tencent\QQMusic\QQMusic.exe",
    r"C:\Program Files (x86)\Tencent\QQMusic\QQMusic.exe",
]
MUSIC_ACTIONS = ("status", "play", "pause", "toggle", "next", "prev",
                 "vol_up", "vol_down", "mute", "open", "taste", "limits",
                 "play_query")

# 自动点播失败时的标准答复。为什么不写"永远做不到"：现在能按歌名/歌单试，
# 但 QQ音乐 没登录、歌曲要 VIP、或者界面改版时仍会失败，失败必须如实说。
MUSIC_LIMITS_TEXT = ("这次没能自动点播 —— 可能是 QQ音乐 没登录、这首歌要 VIP，"
                     "或者搜索没结果。你先在 App 里手动点开那首歌/歌单，"
                     "之后暂停、切歌、调音量、看现在放的是哪首，我都能帮你。")


def parse_music_request(text):
    """
    把"放一首周杰伦的晴天 / 播放我喜欢歌单里的歌"拆成：
        (kind, 搜索词, 主标题)
    kind=song/playlist。拆不出来就返回 None，交给模型正常处理。
    """
    t = str(text or "").strip()
    if not t:
        return None
    if parse_music_command(t):
        return None
    # 别把「播放视频 / 打开 PPT」这类请求误当成点歌。
    if (re.search(r"视频|电影|电视剧|动画|文件|图片|照片|PPT|幻灯片|录音|直播|节目|播客", t)
            and not re.search(r"歌|曲|音乐|原声|专辑", t)):
        return None
    verb = r"(播放|放一首|放首|来一首|来首|换成|切到|放一下|听一首|听首|想听|给我放|帮我放)"
    if not re.search(verb, t):
        return None

    # “最近爱听/最近常听”不是歌名。先从真实听歌记录里挑一首歌，
    # 绝不能把整句需求原样打进 QQ 音乐搜索框。
    if re.search(r"最近.{0,6}(爱听|喜欢听|常听|听的歌|听什么)", t):
        pick = music_taste_pick(recent=True)
        if pick:
            return pick
        return ("playlist", "我喜欢", "我喜欢")

    if re.search(r"歌单|播放列表|收藏|我喜欢|喜欢听|最近播放", t):
        if "我喜欢" in t or "喜欢听" in t:
            return ("playlist", "喜欢", "喜欢")
        if "最近播放" in t:
            return ("playlist", "最近播放", "最近播放")
        if "收藏" in t:
            return ("playlist", "收藏歌单", "收藏歌单")
        m = re.search(r"(?:自建歌单|收藏歌单|歌单)[\s:：]*(.+)$", t)
        if m:
            name = m.group(1).strip(" ，。！？!?、,.《》「」\"'“”‘’")
            if name and name not in ("这个", "那个", "里的歌", "里的"):
                return ("playlist", name, name)
        m = re.search(r"(?:播放|放|听|打开|来)(?:一下|一首|首)?(?:我的|这个|那个)?"
                      r"[《「\"']?([^《》「」\"'，。！？\s]{1,30}?)[》」\"']?(?:这个|那个)?歌单", t)
        if m:
            name = m.group(1).strip(" 的")
            if name and name not in ("我", "我的", "里", "里面", "这个", "那个"):
                return ("playlist", name, name)
        return None

    q = re.sub(verb, "", t, count=1)
    q = re.sub(r"^(一下|一首|首|点|个|我的|我想要|我要|想|我)+", "", q)
    q = re.sub(r"(这首歌|的歌|吧|好吗|好不好|谢谢|一下|听听)$", "", q)
    q = q.strip(" ，。！？!?、,.《》「」\"'“”‘’")
    q = re.sub(r"\s+", " ", q).strip()
    if not q or q in ("歌", "首歌", "音乐", "歌吧", "点歌", "歌曲", "一首歌", "点音乐",
                      "这个", "那个", "它", "这首", "那首", "刚才那首", "刚刚那首"):
        return None
    if len(q) < 2:
        return None

    title = q
    if "的" in q:
        artist, name = q.rsplit("的", 1)
        if artist.strip() and name.strip():
            q = artist.strip() + " " + name.strip()
            title = name.strip()
    elif " " in q:
        title = q.split()[0]
    return ("song", q, title)


def wants_specific_music(text):
    """他是不是在点名要某首歌/某个歌单 —— 能拆出来就由服务端直接点播。"""
    return parse_music_request(text) is not None


def find_music_exe():
    """找 QQ音乐 的 exe：先看几个常见位置，再读它自己注册的文件关联命令。"""
    for p in MUSIC_EXE_CANDIDATES:
        if os.path.isfile(p):
            return p
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Classes\QQMusic.qmc0\shell\open\command") as k:
            cmd = winreg.QueryValueEx(k, "")[0]
        m = re.match(r'\s*"([^"]+\.exe)"', cmd or "", re.I)
        if m and os.path.isfile(m.group(1)):
            return m.group(1)
    except Exception:
        pass
    return ""


def _uia_walk(ctrl, depth=0):
    """深度优先遍历 UI 自动化树。Qt/自绘界面有时层级很深，限一下防止卡死。"""
    yield ctrl
    if depth > 40:
        return
    try:
        children = ctrl.GetChildren()
    except Exception:
        return
    for child in children:
        yield from _uia_walk(child, depth + 1)


def _uia_window(auto, need_edit=False):
    """找 QQ音乐 的主窗口。它有时会多出一个空的 TXGuiFoundation 窗口，要挑有内容的。"""
    import psutil
    pids = [p.pid for p in psutil.process_iter(["name"])
            if p.info.get("name") and p.info["name"].lower() == "qqmusic.exe"]
    if not pids:
        return None
    wins = [w for w in auto.GetRootControl().GetChildren()
            if w.ProcessId in pids and w.Name]
    if not wins:
        return None
    best, best_score = None, -1
    for w in wins:
        ctrls = list(_uia_walk(w))
        score = len(ctrls)
        if need_edit and not any(c.ControlTypeName == "EditControl" for c in ctrls):
            score -= 1000
        if score > best_score:
            best, best_score = w, score
    return best


def _ensure_qqmusic():
    """QQ音乐 没开就先拉起来。返回 (ok, 原因)。"""
    exe = find_music_exe()
    if not exe:
        return False, "没找到 QQ音乐 的可执行文件"
    running = run_hidden(["tasklist", "/FI", "IMAGENAME eq QQMusic.exe"],
                         capture_output=True, text=True,
                         encoding="utf-8", errors="replace").stdout or ""
    if "QQMusic.exe" in running:
        return True, ""
    subprocess.Popen([exe], cwd=os.path.dirname(exe), creationflags=CREATE_NO_WINDOW)
    for _ in range(20):
        time.sleep(1)
        running = run_hidden(["tasklist", "/FI", "IMAGENAME eq QQMusic.exe"],
                             capture_output=True, text=True,
                             encoding="utf-8", errors="replace").stdout or ""
        if "QQMusic.exe" in running:
            time.sleep(2)
            return True, ""
    return False, "QQ音乐 没能启动"


def _music_match_score(name, tokens, primary):
    """给搜索结果排序：主标题完全相等 > 开头相同 > 包含 > 只包含其它词。"""
    if not name or name.startswith(("歌手", "专辑", "歌曲")):
        return -1
    if name == primary:
        return 100
    if primary and name.startswith(primary):
        return 85
    if primary and primary in name:
        return 70
    if any(t and t in name for t in tokens):
        return 50
    return -1


def _focus_music_search(edit):
    """让搜索框取得键盘焦点，但不移动或点击鼠标。"""
    try:
        return bool(edit.GetLegacyIAccessiblePattern().Select(3))
    except Exception:
        return False


def _clear_and_type(edit, text):
    """清空 QQ 音乐搜索框并输入文字，全程只发键盘事件。"""
    try:
        old = edit.GetValuePattern().Value or ""
    except Exception:
        old = ""
    for _ in range(max(8, len(old) + 4)):
        edit.SendKeys("{Back}", waitTime=0)
    edit.SendKeys(str(text), interval=0.10)


_MUSIC_UI_LOCK = threading.RLock()


def parse_music_command(text):
    """常用短命令直接执行，避免小模型只承诺却不调用播放器。"""
    q = re.sub(r"[\s，。！？!?、,.]", "", str(text or "")).lower()
    q = re.sub(r"^(?:亲爱的|梅梅|阮梅)?(?:请|麻烦)?(?:帮我|给我)?", "", q)
    q = re.sub(r"(?:一下|吧|好吗|谢谢)$", "", q)
    aliases = {
        "放歌": "play", "放首歌": "play", "放一首歌": "play", "放音乐": "play",
        "放点音乐": "play", "播放音乐": "play", "播放歌曲": "play",
        "来点音乐": "play", "听会歌": "play", "想听歌": "play",
        "暂停": "pause", "暂停音乐": "pause", "暂停播放": "pause", "别放了": "pause",
        "继续播放": "play", "继续放歌": "play", "继续音乐": "play",
        "换一首": "next", "换首歌": "next", "下一首": "next", "切歌": "next",
        "上一首": "prev", "音乐小声点": "vol_down", "小声点": "vol_down",
        "音乐大声点": "vol_up", "大声点": "vol_up", "现在放什么": "status",
    }
    if q in aliases:
        return aliases[q]
    if (re.search(r"听歌(?:习惯|喜好|口味|记录)|最近(?:都)?听(?:了)?什么|我(?:平时)?爱听什么", q)
            and not re.search(r"记住|以后|忘记|播放|放一首|想听", q)):
        return "taste"
    return None


def qqmusic_play(query, kind="song", title=""):
    try:
        import uiautomation as auto
        # HTTP handlers run in worker threads, where COM is not initialized.
        with _MUSIC_UI_LOCK, auto.UIAutomationInitializerInThread():
            result = _qqmusic_play_impl(query, kind, title)
            d = music_control("status", "QQMusic")
            if d.get("STATUS") == "Playing":
                note_playing(d.get("TITLE"), d.get("ARTIST"), d.get("ALBUM"))
            return result
    except Exception as e:
        print("[music] %s: %s" % (type(e).__name__, e), file=sys.stderr)
        return "照这句说：这次没能在 QQ音乐 里完成点播：%s" % str(e)[:120]


def _qqmusic_play_impl(query, kind="song", title=""):
    """
    在 QQ音乐 里按歌名/歌单点播。

    QQ 音乐没有公开的在线点歌接口，因此仍用 UI Automation，但只调用控件语义：
    取键盘焦点和 InvokePattern，不移动鼠标，也不依赖固定坐标。搜索后先选自动
    补全；需要结果页时再按标题匹配并 Invoke，不再双击。完成后会最小化 QQ 音乐
    并把前台窗口还给操作前的应用。
    """
    q = str(query or "").strip()
    if not q:
        return "照这句说：" + MUSIC_LIMITS_TEXT
    ok, why = _ensure_qqmusic()
    if not ok:
        print("[music] %s" % why, file=sys.stderr)
        return "照这句说：" + MUSIC_LIMITS_TEXT
    try:
        import uiautomation as auto
    except Exception as e:
        print("[music] uiautomation 不可用：%s" % e, file=sys.stderr)
        return "照这句说：" + MUSIC_LIMITS_TEXT

    import ctypes
    from ctypes import wintypes
    prev = ctypes.windll.user32.GetForegroundWindow()
    old_cursor = wintypes.POINT()
    try:
        ctypes.windll.user32.GetCursorPos(ctypes.byref(old_cursor))
    except Exception:
        pass
    hwnd = 0
    win = None
    try:
        win = _uia_window(auto, need_edit=(kind != "playlist"))
        if not win:
            return "照这句说：" + MUSIC_LIMITS_TEXT
        hwnd = win.NativeWindowHandle
        try:
            ctypes.windll.user32.ShowWindow(hwnd, 9)
            win.SetActive()
        except Exception:
            pass
        time.sleep(0.8)
        before = music_control("status", "QQMusic")
        before_title = before.get("TITLE") or ""
        ctrls = list(_uia_walk(win))

        if kind == "playlist":
            target = None
            for c in ctrls:
                name = c.Name or ""
                if not name or q not in name:
                    continue
                try:
                    if c.BoundingRectangle.left >= win.BoundingRectangle.left + 320:
                        continue
                except Exception:
                    continue
                target = c
                break
            if not target:
                print("[music] 左侧没找到歌单：%s" % q, file=sys.stderr)
                return "照这句说：" + MUSIC_LIMITS_TEXT
            focused = False
            for pattern_name in ("GetSelectionItemPattern", "GetLegacyIAccessiblePattern"):
                try:
                    pattern = getattr(target, pattern_name)()
                    if pattern_name == "GetSelectionItemPattern":
                        pattern.Select()
                    else:
                        pattern.Select(3)
                    focused = True
                    break
                except Exception:
                    continue
            if not focused:
                print("[music] 歌单项目不支持后台选择", file=sys.stderr)
                return "照这句说：" + MUSIC_LIMITS_TEXT
            auto.SendKeys("{Enter}")
            time.sleep(2.0)

            play_btn = None
            for c in _uia_walk(win):
                if c.ControlTypeName != "ButtonControl":
                    continue
                if re.match(r"^(播放|播放全部|继续播放)", c.Name or ""):
                    play_btn = c
                    break
            if not play_btn:
                print("[music] 没找到播放按钮", file=sys.stderr)
                return "照这句说：" + MUSIC_LIMITS_TEXT
            try:
                play_btn.GetInvokePattern().Invoke()
            except Exception:
                print("[music] 播放按钮不支持后台 Invoke", file=sys.stderr)
                return "照这句说：" + MUSIC_LIMITS_TEXT
            time.sleep(2.5)
            d = music_control("status", "QQMusic")
            if d.get("STATUS") != "Playing":
                music_control("play", "QQMusic")
                time.sleep(1)
                d = music_control("status", "QQMusic")
            if d.get("STATUS") != "Playing":
                return "照这句说：" + MUSIC_LIMITS_TEXT
            now_title = d.get("TITLE") or ""
            artist = d.get("ARTIST") or ""
            return ("照这句说：已经在 QQ音乐 里放上「%s」歌单了，现在放的是《%s》%s。"
                    % (q, now_title or "第一首", (" — " + artist) if artist else ""))

        edit = next((c for c in ctrls if c.ControlTypeName == "EditControl"), None)
        if not edit:
            print("[music] 没找到搜索框", file=sys.stderr)
            return "照这句说：" + MUSIC_LIMITS_TEXT
        if not _focus_music_search(edit):
            print("[music] 搜索框不支持后台聚焦", file=sys.stderr)
            return "照这句说：" + MUSIC_LIMITS_TEXT
        _clear_and_type(edit, q)
        time.sleep(0.9)
        # QQ 音乐当前版本的自动补全可用键盘直接选中第一条并播放。
        edit.SendKeys("{Down}", waitTime=0.15)
        edit.SendKeys("{Enter}", waitTime=0.2)
        time.sleep(3.2)

        tokens = [t for t in re.split(r"[\s的]+", q) if t]
        primary = str(title or (tokens[0] if tokens else q)).strip()
        d = music_control("status", "QQMusic")
        now_title = d.get("TITLE") or ""
        artist = d.get("ARTIST") or ""
        matched = bool(now_title and (
            now_title == primary or primary in now_title or now_title in primary
            or _music_match_score(now_title, tokens, primary) >= 50))
        if (kind != "playlist" and d.get("STATUS") == "Playing"
                and matched):
            return ("照这句说：已经在 QQ音乐 里放上《%s》了%s。"
                    % (now_title or primary, (" — " + artist) if artist else ""))

        # 自动补全没有直接播放时再找结果页；这里同样只调用语义 Invoke。
        deadline = time.time() + 12
        best, best_key = None, None
        while time.time() < deadline:
            links = [c for c in _uia_walk(win)
                     if c.ControlTypeName == "HyperlinkControl"]
            artists = []
            for c in links:
                name = c.Name or ""
                if name.startswith("歌手："):
                    artists.append((name[3:].strip(), c.BoundingRectangle))
            rows = []
            for c in links:
                name = c.Name or ""
                base = _music_match_score(name, tokens, primary)
                if base < 0:
                    continue
                rect = c.BoundingRectangle
                artist = ""
                for aname, arect in artists:
                    if abs(arect.top - rect.top) <= 25 and arect.left > rect.left:
                        artist = aname
                        break
                rows.append((name, artist, rect, base, c))
            artist_count = collections.Counter(a for _, a, _, _, _ in rows if a)
            for name, artist, rect, base, c in rows:
                score = base
                if artist:
                    if any(t and t in artist for t in tokens):
                        score += 30
                    score += min(20, artist_count[artist] * 5)
                key = (-score, len(name), rect.top)
                if best_key is None or key < best_key:
                    best, best_key = c, key
            if best and best_key[0] <= -100:
                break
            time.sleep(0.8)
        if not best:
            print("[music] 搜索没匹配到：%s" % q, file=sys.stderr)
            return "照这句说：" + MUSIC_LIMITS_TEXT

        target_name = best.Name
        try:
            best.GetInvokePattern().Invoke()
        except Exception:
            try:
                best.GetLegacyIAccessiblePattern().Select(3)
                auto.SendKeys("{Enter}")
            except Exception:
                print("[music] 搜索结果不支持后台激活", file=sys.stderr)
                return "照这句说：" + MUSIC_LIMITS_TEXT
        time.sleep(3.2)
        d = music_control("status", "QQMusic")
        if d.get("STATUS") != "Playing":
            music_control("play", "QQMusic")
            time.sleep(1)
            d = music_control("status", "QQMusic")
        now_title = d.get("TITLE") or ""
        artist = d.get("ARTIST") or ""
        matched = bool(now_title and (now_title == target_name
                                     or target_name in now_title
                                     or now_title in target_name))
        if d.get("STATUS") != "Playing" or not matched:
            print("[music] 点了但没放起来：%s -> %s" % (target_name, now_title),
                  file=sys.stderr)
            return "照这句说：" + MUSIC_LIMITS_TEXT
        return ("照这句说：已经在 QQ音乐 里放上《%s》了%s。"
                % (now_title or target_name, (" — " + artist) if artist else ""))
    except Exception as e:
        print("[music] 点播异常：%s: %s" % (type(e).__name__, e), file=sys.stderr)
        return "照这句说：" + MUSIC_LIMITS_TEXT
    finally:
        try:
            ctypes.windll.user32.SetCursorPos(old_cursor.x, old_cursor.y)
        except Exception:
            pass
        try:
            if prev and hwnd and prev != hwnd:
                ctypes.windll.user32.SetForegroundWindow(prev)
        except Exception:
            pass
        try:
            if hwnd:
                ctypes.windll.user32.ShowWindow(hwnd, 6)
        except Exception:
            pass


def _load_listen():
    try:
        with open(LISTEN_FILE, "r", encoding="utf-8") as f:
            d = json.load(f)
        if isinstance(d, dict):
            d.setdefault("tracks", [])
            return d
    except Exception:
        pass
    return {"tracks": [], "last_key": "", "hours": {}}


def _save_listen(d):
    os.makedirs(os.path.dirname(LISTEN_FILE), exist_ok=True)
    tmp = LISTEN_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)
    os.replace(tmp, LISTEN_FILE)


_LISTEN_LOCK = threading.Lock()


def note_playing(title, artist="", album=""):
    with _LISTEN_LOCK:
        return _note_playing(title, artist, album)


def _note_playing(title, artist="", album=""):
    """
    记一笔"现在在放这首"。只有曲子**换了**才算一次新的播放 ——
    不然暂停继续、拖进度都会重复计数。
    """
    title = (title or "").strip()
    if not title:
        return False
    key = (title + "|" + (artist or "")).lower()
    d = _load_listen()
    if d.get("last_key") == key:
        for track in d["tracks"]:
            if (str(track.get("title", "")) + "|" + str(track.get("artist", ""))).lower() == key:
                if track.get("source") != "QQMusic":
                    track["source"] = "QQMusic"
                    _save_listen(d)
                break
        return False
    d["last_key"] = key
    now = datetime.datetime.now()
    stamp = now.strftime("%Y-%m-%d %H:%M")
    d.setdefault("hours", {})
    h = str(now.hour)
    d["hours"][h] = int(d["hours"].get(h, 0)) + 1
    for t in d["tracks"]:
        if (str(t.get("title", "")) + "|" + str(t.get("artist", ""))).lower() == key:
            t["plays"] = int(t.get("plays", 1)) + 1
            t["last"] = stamp
            t["source"] = "QQMusic"
            break
    else:
        d["tracks"].append({"title": title, "artist": artist or "", "album": album or "",
                            "plays": 1, "first": stamp, "last": stamp, "source": "QQMusic"})
    _save_listen(d)
    return True


def music_taste(limit=5):
    """把听歌记录说成人话：常听谁、最近放过什么、一般什么时间听。"""
    d = _load_listen()
    tracks = [t for t in d.get("tracks") or [] if t.get("title")]
    if not tracks:
        return ("我还没记到你在听什么（记录是空的）。放一首歌我就能开始记了；"
                "你也可以直接说「记住：我爱听周杰伦」，那种写进习惯里更准。")
    total = sum(int(t.get("plays", 1)) for t in tracks)
    artists = {}
    for t in tracks:
        a = str(t.get("artist") or "").strip()
        if a:
            artists[a] = artists.get(a, 0) + int(t.get("plays", 1))
    top_artists = sorted(artists.items(), key=lambda kv: -kv[1])[:limit]
    top_tracks = sorted(tracks, key=lambda t: -int(t.get("plays", 1)))[:limit]
    recent = sorted(tracks, key=lambda t: str(t.get("last") or ""))[-limit:][::-1]
    hours = sorted((d.get("hours") or {}).items(), key=lambda kv: -int(kv[1]))[:3]
    lines = ["一共记下 %d 首 / 播放 %d 次" % (len(tracks), total)]
    if top_artists:
        lines.append("常听的歌手：" + "、".join("%s（%d 次）" % (a, n) for a, n in top_artists))
    lines.append("听得最多的：" + "、".join("《%s》" % t["title"] for t in top_tracks))
    lines.append("最近放过：" + "；".join("%s - %s" % (t["title"], t.get("artist") or "未知")
                                        for t in recent))
    if hours:
        lines.append("一般在这些时段听：" + "、".join("%s 点" % h for h, _ in hours))
    return "\n".join(lines)


def music_taste_brief(max_artists=3):
    """给系统提示用的一行短摘要（不占上下文）。"""
    d = _load_listen()
    tracks = [t for t in d.get("tracks") or [] if t.get("title")]
    if len(tracks) < 3:          # 样本太少就别急着下结论
        return ""
    artists = {}
    for t in tracks:
        a = str(t.get("artist") or "").strip()
        if a:
            artists[a] = artists.get(a, 0) + int(t.get("plays", 1))
    top = sorted(artists.items(), key=lambda kv: -kv[1])[:max_artists]
    if not top:
        return ""
    return ("他最近常听的歌手是：%s（这是从他实际播放里记下来的，共 %d 首）。"
            % ("、".join(a for a, _ in top), len(tracks)))


def music_taste_pick(recent=True):
    """从听歌记录里挑一首真实歌曲，作为“最近爱听/常听”对应的搜索词。"""
    d = _load_listen()
    tracks = [t for t in d.get("tracks") or []
              if t.get("title") and t.get("artist")]
    if not tracks:
        return None
    key = ((lambda t: (str(t.get("last") or ""), int(t.get("plays", 1))))
           if recent else
           (lambda t: (int(t.get("plays", 1)), str(t.get("last") or ""))))
    track = max(tracks, key=key)
    title = str(track["title"]).strip()
    artist = str(track["artist"]).strip()
    return ("song", "%s %s" % (artist, title), title)


def music_log_loop(every=15):
    """每隔一会儿看一眼在放什么，顺手记进听歌记录。"""
    time.sleep(5)
    while True:
        try:
            d = music_control("status", "QQMusic")
            if d.get("COUNT", "0") != "0" and d.get("STATUS") == "Playing":
                if note_playing(d.get("TITLE"), d.get("ARTIST"), d.get("ALBUM")):
                    print("[听歌] 记下：%s - %s" % (d.get("TITLE"), d.get("ARTIST")))
        except Exception as e:
            print("[听歌] 记录失败：%s" % e, file=sys.stderr)
        time.sleep(max(10, int(every)))


# ---------------------------------------------------------------------------
# 用别的 App：启动 / 切窗口 / 按键
# ---------------------------------------------------------------------------
VK = {
    "ctrl": 0x11, "alt": 0x12, "shift": 0x10, "win": 0x5B,
    "space": 0x20, "enter": 0x0D, "esc": 0x1B, "tab": 0x09,
    "backspace": 0x08, "delete": 0x2E, "home": 0x24, "end": 0x23,
    "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27,
    "pageup": 0x21, "pagedown": 0x22,
    "play_pause": 0xB3, "next": 0xB0, "prev": 0xB1, "stop": 0xB2,
    "vol_up": 0xAF, "vol_down": 0xAE, "mute": 0xAD,
}
for _c in "abcdefghijklmnopqrstuvwxyz":
    VK[_c] = ord(_c.upper())
for _d in "0123456789":
    VK[_d] = ord(_d)


def _user32():
    import ctypes
    return ctypes.WinDLL("user32", use_last_error=True)


def list_windows():
    """当前可见的顶层窗口标题。"""
    import ctypes
    from ctypes import wintypes
    user32 = _user32()
    out = []
    proto = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)

    def cb(h, _):
        try:
            if user32.IsWindowVisible(h):
                n = user32.GetWindowTextLengthW(h)
                if n > 0:
                    buf = ctypes.create_unicode_buffer(n + 2)
                    user32.GetWindowTextW(h, buf, n + 2)
                    t = buf.value.strip()
                    if t:
                        out.append((int(h), t))
        except Exception:
            pass
        return True

    user32.EnumWindows(proto(cb), 0)
    return out


def focus_window(keyword):
    """把标题里含 keyword 的窗口拉到前台。返回窗口标题或空串。"""
    kw = str(keyword or "").strip().lower()
    if not kw:
        return ""
    user32 = _user32()
    for h, title in list_windows():
        if kw in title.lower():
            try:
                user32.ShowWindow(h, 9)            # SW_RESTORE
                user32.SetForegroundWindow(h)
                return title
            except Exception:
                continue
    return ""


def send_keys(keys):
    """按白名单里的键（支持 ctrl+s 这种组合）。非白名单的直接忽略并汇报。"""
    user32 = _user32()
    done, skipped = [], []
    for k in str(keys or "").split():
        parts = [p.lower() for p in k.split("+") if p]
        if not parts or any(p not in VK for p in parts):
            skipped.append(k)
            continue
        codes = [VK[p] for p in parts]
        for c in codes[:-1]:
            user32.keybd_event(c, 0, 0, 0)
        user32.keybd_event(codes[-1], 0, 0, 0)
        user32.keybd_event(codes[-1], 0, 2, 0)
        for c in reversed(codes[:-1]):
            user32.keybd_event(c, 0, 2, 0)
        done.append(k)
        time.sleep(0.08)
    return done, skipped


def installed_shortcuts(limit=400):
    """开始菜单里的快捷方式（= 能启动的应用）。纯 Python 扫目录，避免编码问题。"""
    dirs = [os.path.join(os.environ.get("APPDATA", ""),
                         r"Microsoft\Windows\Start Menu\Programs"),
            os.path.join(os.environ.get("ProgramData", r"C:\ProgramData"),
                         r"Microsoft\Windows\Start Menu\Programs")]
    hits = []
    for d in dirs:
        if not os.path.isdir(d):
            continue
        for root, _dirs, files in os.walk(d):
            for f in files:
                if f.lower().endswith(".lnk"):
                    hits.append((os.path.splitext(f)[0], os.path.join(root, f)))
                    if len(hits) >= limit:
                        return hits
    return hits


def start_apps(limit=400):
    """
    系统自己的「开始菜单应用清单」（Get-StartApps）。

    为什么不扫 .lnk：Win11 的 UWP 应用（计算器/记事本/画图/相机/设置）没有 .lnk，
    扫目录根本找不到 —— 实测"打开计算器"会回"没找到"。这个清单里 Win32 和 UWP 都有，
    而且带 AppID，可以直接用 shell:AppsFolder\\<AppID> 启动。
    """
    fd, tmp = tempfile.mkstemp(suffix=".json", prefix="meimei_apps_")
    os.close(fd)
    try:
        ps = ("Get-StartApps | Select-Object Name,AppID | ConvertTo-Json -Compress | "
              "Out-File -FilePath '%s' -Encoding utf8" % tmp)
        run_hidden(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
                    "-Command", ps], timeout=60)
        with open(tmp, "r", encoding="utf-8-sig", errors="replace") as f:
            data = json.load(f)
        if isinstance(data, dict):
            data = [data]
        return [(str(d.get("Name") or ""), str(d.get("AppID") or ""))
                for d in data if d.get("Name")][:limit]
    except Exception:
        return []
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass


def launch_app(name):
    """按名字启动应用：绝对路径直接开；否则在系统应用清单里找最匹配的那个。"""
    raw = str(name or "").strip().strip('"')
    if not raw:
        return "[工具出错] 要启动哪个应用？给个名字就行，比如 剪映专业版。"
    if os.path.isfile(raw):
        try:
            os.startfile(raw)
            return "照这句说：已经帮你打开 %s 了。" % os.path.basename(raw)
        except Exception as e:
            return "[工具出错] 打不开 %s：%s" % (raw, e)

    low = raw.lower()
    cands = start_apps() or installed_shortcuts()
    pick = None
    for nm, appid in cands:                       # 先精确
        if nm.lower() == low:
            pick = (nm, appid)
            break
    if not pick:
        for nm, appid in cands:                   # 再"名字里包含"
            if low in nm.lower():
                pick = (nm, appid)
                break
    if not pick:
        for nm, appid in cands:                   # 最后反着包含（"QQ音乐" vs "QQ音乐 - 快捷方式"）
            if nm.lower() in low:
                pick = (nm, appid)
                break
    if not pick:
        names = "、".join(n for n, _ in cands[:40])
        return ("[工具出错] 应用清单里没找到「%s」。能启动的有这些（前 40 个）：\n%s"
                % (raw, names))
    try:
        # AppID 走 shell:AppsFolder；拿到的是 .lnk 路径就直接 startfile
        if pick[1].lower().endswith(".lnk"):
            os.startfile(pick[1])
        else:
            subprocess.Popen(["explorer.exe", "shell:AppsFolder\\" + pick[1]],
                             creationflags=CREATE_NO_WINDOW)
    except Exception as e:
        return "[工具出错] 启动 %s 失败：%s" % (pick[0], e)
    time.sleep(3)
    return "照这句说：已经帮你打开「%s」了。" % pick[0]


def app_tool(action, name="", title="", keys=""):
    act = str(action or "windows").strip().lower()
    if act in ("list", "apps", "能开什么"):
        cands = start_apps() or installed_shortcuts()
        if not cands:
            return "[工具出错] 没在开始菜单里找到任何快捷方式。"
        names = [n for n, _ in cands]
        return ("[可启动的应用] 共 %d 个（前 80 个）：\n%s"
                % (len(names), "、".join(names[:80])))
    if act in ("windows", "窗口"):
        wins = list_windows()
        if not wins:
            return "[窗口] 现在一个可见窗口都没有。"
        return "[窗口] 现在开着这些：\n" + "\n".join("- " + t for _, t in wins[:60])
    if act in ("launch", "open", "启动", "打开"):
        return launch_app(name or title)
    if act in ("focus", "switch", "切换"):
        got = focus_window(title or name)
        if got:
            return "照这句说：已经切到「%s」了。" % got
        return ("[工具出错] 没找到标题含「%s」的窗口。先用 action=windows 看看现在开着什么。"
                % (title or name))
    if act in ("press", "keys", "按键"):
        target = title or name
        if not target:
            return ("[工具出错] 按键必须指定窗口（title），不然会打到别的窗口上。"
                    "先用 action=windows 看标题。")
        got = focus_window(target)
        if not got:
            return "[工具出错] 没找到标题含「%s」的窗口，没按键。" % target
        done, skipped = send_keys(keys)
        msg = "照这句说：在「%s」里按了 %s。" % (got, "、".join(done) if done else "（没有）")
        if skipped:
            msg += "\n（这些键不在白名单里，没按：%s）" % "、".join(skipped)
        return msg
    if act in ("close", "关闭"):
        target = title or name
        if not target:
            return "[工具出错] 要关哪个窗口？给个标题关键词。"
        got = focus_window(target)
        if not got:
            return "[工具出错] 没找到标题含「%s」的窗口。" % target
        import ctypes
        from ctypes import wintypes
        user32 = _user32()
        hwnd = None
        for h, t in list_windows():
            if t == got:
                hwnd = h
                break
        if hwnd is None:
            return "[工具出错] 拿不到那个窗口的句柄。"
        user32.PostMessageW(wintypes.HWND(hwnd), 0x0010, 0, 0)     # WM_CLOSE
        return "照这句说：已经让「%s」自己关了（如果它弹保存框，需要你确认一下）。" % got
    return ("[工具出错] 不认识的 action：%s。可用：list / launch / windows / focus / press / close。"
            % action)


def music_control(action, app="QQMusic", steps=1):
    """
    跑一次 smtc.ps1，把 KEY=VALUE 收成 dict。

    结果让它写进一个临时文件、我们按 UTF-8 读 —— 不走管道。原因是实测：
    服务进程没有控制台，PowerShell 往管道写时用 OEM 代码页（GBK），
    歌名到 python 这边就成了 《????》（同一个脚本在终端里跑却正常，很难查）。
    """
    fd, tmp = tempfile.mkstemp(suffix=".txt", prefix="meimei_music_")
    os.close(fd)
    try:
        r = run_hidden(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
                            "-File", SMTC_SCRIPT, "-Action", action, "-App", app,
                            "-Steps", str(max(1, min(20, int(steps or 1)))),
                            "-OutFile", tmp],
                           capture_output=True, timeout=180)
        try:
            with open(tmp, "r", encoding="utf-8", errors="replace") as f:
                out = f.read()
        except Exception:
            out = ""
        if not out.strip():
            out = r.stdout.decode("utf-8", "replace")
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass
    data = {}
    for line in out.splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            data[k.strip()] = v.strip()
    if not data:
        data["_raw"] = (out + r.stderr.decode("utf-8", "replace"))[:300]
    return data


def _music_line(d, after=False):
    """把 KEY=VALUE 拼成一句人话。"""
    title = d.get("AFTER_TITLE") if after else d.get("TITLE")
    artist = d.get("AFTER_ARTIST") if after else d.get("ARTIST")
    status = d.get("AFTER_STATUS") if after else d.get("STATUS")
    cn = {"Playing": "正在播放", "Paused": "已暂停", "Opened": "已打开但没在放",
          "Stopped": "已停止", "Closed": "已收起"}
    parts = []
    if title:
        parts.append("《%s》%s" % (title, ("— " + artist) if artist else ""))
    if status:
        parts.append(cn.get(status, status))
    if parts:
        app = (d.get("APP") or "").replace(".exe", "")
        return "：" + "，".join(parts) + ("（%s）" % app if app else "")
    return "。"


def _start_music_without_session(action):
    """QQ Music creates its SMTC session only after its first playback."""
    import uiautomation as auto
    ok, why = _ensure_qqmusic()
    if not ok:
        return why
    with _MUSIC_UI_LOCK, auto.UIAutomationInitializerInThread():
        win = _uia_window(auto)
        if not win:
            return "没有找到 QQ音乐 主窗口"
        controls = list(_uia_walk(win))
        wanted = {"play": ("播放", "播放全部"), "toggle": ("播放", "暂停"),
                  "next": ("下一曲",), "prev": ("上一曲",)}.get(action, ())
        for name in wanted:
            candidates = [c for c in controls if c.ControlTypeName == "ButtonControl" and c.Name == name]
            if candidates:
                candidates[-1].GetInvokePattern().Invoke()
                time.sleep(1.5)
                return ""
    return "播放器没有可用的播放按钮，请先登录并选择歌曲"


def music(action, app="QQMusic", steps=1, query="", kind="song", title=""):
    """
    放 / 停 / 切歌 / 看现在放什么 —— 走 Windows 的媒体会话（SMTC）。

    为什么不用模拟按键：媒体键只打到"当前活动会话"，QQ音乐 在后台时经常没反应；
    SMTC 是系统自己的会话表，能按应用名精确指定，还能反过来说出正在放哪首歌。
    """
    act = str(action or "status").strip().lower()
    alias = {"放歌": "play", "放音乐": "play", "播放": "play", "继续": "play",
             "暂停": "pause", "停一下": "pause", "停": "pause", "别放了": "pause",
             "下一首": "next", "换一首": "next", "上一首": "prev",
             "切换": "toggle", "现在放什么": "status", "在放什么": "status",
             "打开qq音乐": "open", "打开QQ音乐": "open", "启动": "open",
             "小声点": "vol_down", "音量大点": "vol_up", "静音": "mute",
             "听歌喜好": "taste", "听歌口味": "taste", "我爱听什么": "taste",
             "听歌记录": "taste", "最近听什么": "taste",
             "歌单": "limits", "能做什么": "limits", "做不到": "limits"}
    act = alias.get(act, act)
    if act in ("play_query", "search_play", "点播", "播放指定"):
        return qqmusic_play(query, kind or "song", title)
    if act not in MUSIC_ACTIONS:
        return ("[工具出错] 不认识的 action：%s。能用的是：%s。"
                % (action, " / ".join(MUSIC_ACTIONS)))

    if act == "open":
        exe = find_music_exe()
        if not exe:
            return "[工具出错] 没找到 QQ音乐 的可执行文件。"
        running = run_hidden(["tasklist", "/FI", "IMAGENAME eq QQMusic.exe"],
                                 capture_output=True, text=True,
                                 encoding="utf-8", errors="replace").stdout or ""
        if "QQMusic.exe" in running:
            d = music_control("status", app)
            return "QQ音乐 已经在运行了。%s" % _music_line(d)
        subprocess.Popen([exe], cwd=os.path.dirname(exe), creationflags=CREATE_NO_WINDOW)
        time.sleep(12)
        d = music_control("status", app)
        if d.get("COUNT", "0") != "0":
            return "已经打开 QQ音乐 了%s" % _music_line(d)
        return "已经打开 QQ音乐 了（它还没准备好播放会话）。"

    if act in ("vol_up", "vol_down", "mute"):
        d = music_control(act, app, steps)
        what = {"vol_up": "调大了一点", "vol_down": "调小了一点",
                "mute": "切换了一次静音"}[act]
        return "照这句说：音量%s。%s" % (what, _music_line(d))

    if act in ("taste", "history", "喜好", "口味"):
        return "照这句说：\n" + music_taste()

    if act in ("limits", "can", "能做什么", "歌单"):
        return ("照这句说：我可以按歌名或歌单试着在 QQ音乐 里点播；"
                "如果没登录、要 VIP 或者搜不到，就得你先手动点一下。")

    d = music_control(act, app)
    # 顺手记一笔：她这次读到的曲目也算一次"听到"
    try:
        st = d.get("AFTER_STATUS") or d.get("STATUS")
        if d.get("COUNT", "0") != "0" and st == "Playing":
            note_playing(d.get("AFTER_TITLE") or d.get("TITLE"),
                         d.get("AFTER_ARTIST") or d.get("ARTIST"))
    except Exception:
        pass
    # 没有会话但用户就是想听歌 → 先把 QQ音乐 拉起来再试一次
    if d.get("COUNT", "0") == "0" and act in ("play", "toggle", "next", "prev"):
        try:
            why = _start_music_without_session(act)
            d = music_control("status", app)
        except Exception as e:
            why = str(e)[:160]
        if d.get("COUNT", "0") == "0":
            return "照这句说：QQ音乐 还没开始播放，%s。" % (why or "请检查是否需要登录或 VIP")
    if d.get("COUNT", "0") == "0":
        return ("现在没有任何东西在放（Windows 的媒体会话是空的）。"
                "要我打开 QQ音乐 开始放吗？说一句「放首歌」就行。")
    if d.get("RESULT", "").lower() == "false":
        return "照这句说：QQ音乐 没有接受这次操作%s" % _music_line(d, after=True)
    if act in ("play", "toggle", "next", "prev"):
        current = music_control("status", app)
        if current.get("STATUS") == "Playing":
            note_playing(current.get("TITLE"), current.get("ARTIST"), current.get("ALBUM"))

    verb = {"play": "开始放了", "pause": "暂停了", "toggle": "切换了一下",
            "next": "切到下一首了", "prev": "回上一首了", "status": "现在在放"}.get(act, "好了")
    return "照这句说：%s%s" % (verb, _music_line(d, after=bool(d.get("AFTER_STATUS"))))


def speak_out_loud(text, voice=None, timeout=300):
    """
    用本机音箱把一句话念出来：先向本地 TTS 适配器要 wav，再用 PowerShell 的
    SoundPlayer 同步播放（不用额外装播放器，WAV 直接放）。
    """
    tts = (CFG.get("tts") or "").rstrip("/")
    if not tts:
        return False, "还没拿到 TTS 地址"
    v = voice or CFG.get("voice") or "ruanmei"
    try:
        req = urllib.request.Request(
            tts + "/v1/audio/speech",
            data=json.dumps({"input": text, "voice": v + ":calm",
                             "response_format": "wav"}, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as up:
            wav = up.read()
    except Exception as e:
        return False, "合成失败：%s" % e
    path = os.path.join(tempfile.gettempdir(), "meimei_reminder.wav")
    try:
        with open(path, "wb") as f:
            f.write(wav)
        ps = ("(New-Object Media.SoundPlayer '%s').PlaySync()" % path)
        r = run_hidden(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
                            "-Command", ps], capture_output=True, timeout=timeout)
        if r.returncode != 0:
            return False, "播放失败：%s" % r.stderr.decode("utf-8", "replace")[:150]
        return True, ""
    except Exception as e:
        return False, "播放失败：%s" % e


def _due_now(item, now):
    """该不该现在响。返回 True 表示"这一分这一秒正好到点"。"""
    hhmm = item.get("time") or ""
    if not item.get("enabled", True) or not hhmm:
        return False
    try:
        h, mi = [int(x) for x in hhmm.split(":")]
    except Exception:
        return False
    target = now.replace(hour=h, minute=mi, second=0, microsecond=0)
    delta = (now - target).total_seconds()
    # 超过 90 秒就算错过了（关机/睡眠期间积压的提醒不要一股脑全放出来）
    if delta < 0 or delta > 90:
        return False
    stamp = target.strftime("%Y-%m-%d %H:%M")
    if item.get("last_fired") == stamp:
        return False
    rep = item.get("repeat") or "daily"
    if rep == "weekdays" and now.weekday() >= 5:
        return False
    if rep == "weekly":
        if not item.get("days") or (now.isoweekday() not in item["days"]):
            return False
    if rep == "once":
        d = item.get("date") or ""
        if d and d != now.strftime("%Y-%m-%d"):
            return False
    return True


def reminder_loop(stop_evt=None):
    """每 20 秒看一次表。"""
    while not (stop_evt and stop_evt.is_set()):
        try:
            now = datetime.datetime.now()
            items = load_reminders()
            changed = False
            for it in items:
                if _due_now(it, now):
                    text = "提醒你：" + str(it.get("text") or "")
                    ok, note = (False, "语音关着") if not it.get("voice", True) else speak_out_loud(text)
                    it["last_fired"] = now.strftime("%Y-%m-%d %H:%M")
                    if it.get("repeat") == "once":
                        it["enabled"] = False
                    changed = True
                    remember_fired(it, now.strftime("%Y-%m-%d %H:%M"), ok, note)
                    print("[提醒] %s -> %s（%s）"
                          % (now.strftime("%H:%M"), it.get("text"), "已念出来" if ok else note))
            if changed:
                save_reminders(items)
        except Exception as e:
            print("[提醒] 出错：%s" % e)
        time.sleep(20)


def load_habits():
    try:
        with open(HABITS_FILE, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return ""


def save_habits(text):
    os.makedirs(os.path.dirname(HABITS_FILE), exist_ok=True)
    with open(HABITS_FILE, "w", encoding="utf-8") as f:
        f.write(text)


HABIT_HINTS = {
    "剪视频": ("视频", "剪辑", "转码", "ffmpeg", "素材", "片头", "分辨率",
               "帧率", "动图", "背景视频"),
    "语音": ("语音", "朗读", "声音", "音色", "语气", "tts", "麦克风", "语速", "鼻音"),
    "界面": ("界面", "背景", "主题", "颜色", "图标", "外观", "面板"),
    "做PPT": ("ppt", "幻灯片", "演示", "汇报"),
    "作息": ("作息", "睡觉", "起床", "上课", "下课", "午睡", "早上", "晚上",
             "规划", "日程", "时间表", "安排"),
    "吃饭": ("吃饭", "午饭", "晚饭", "午餐", "晚餐", "外卖", "吃什么"),
    "出门与通勤": ("出门", "通勤", "路上", "公交", "地铁", "开车", "打车"),
    "健康": ("健康", "生病", "医院", "药", "运动", "健身", "睡眠"),
    "花钱与购物": ("花钱", "购物", "预算", "买", "价格", "省钱"),
    "娱乐": ("娱乐", "游戏", "健身", "自由活动", "放松", "玩"),
    "音乐": ("音乐", "歌", "歌单", "听歌", "qq音乐", "播放"),
}
CORE_HABIT_SECTIONS = ("干活的方式",)


def _habit_sections(raw):
    """把习惯 Markdown 拆成 ## / ### 小节，保留原文条目。"""
    out, cur = [], None
    for ln in (raw or "").splitlines():
        m = re.match(r"^(#{2,3})\s+(.+?)\s*$", ln)
        if m:
            cur = {"level": len(m.group(1)), "title": m.group(2).strip(), "lines": []}
            out.append(cur)
            continue
        if cur is None or not ln.strip() or ln.lstrip().startswith(">"):
            continue
        cur["lines"].append(ln.rstrip())
    return out


RUANMEI_STORY_HINTS = {
    "角色故事一：童年与「爱」": (
        "童年", "小时候", "外婆", "母亲", "父亲", "姨妈", "家人", "家",
        "爱", "气味", "戏", "点心", "糕点", "青团", "冰川", "丰饶",
    ),
    "角色故事二：父母、名字与「智识」": (
        "父母", "葬礼", "去世", "死亡", "名字", "昵称", "实验室",
        "火萤", "物种", "智识", "博识尊", "辜负",
    ),
    "角色故事三：隐士与「生命」": (
        "隐居", "隐士", "创造生命", "飞鲸", "游鹿", "生命本质",
        "生命", "星神", "天才俱乐部", "邀请函", "家乡",
    ),
    "角色故事四：模拟宇宙与不信任": (
        "模拟宇宙", "黑塔", "螺丝咕姆", "斯蒂芬", "社交", "朋友",
        "项目", "不信任", "信任", "电饭煲", "温床", "俱乐部",
    ),
}


def ruanmei_setting_text():
    """读取 Modelfile 中的完整 SYSTEM，供带动态资料时一起发送。"""
    try:
        with open(RUANMEI_MODELFILE, "r", encoding="utf-8") as f:
            raw = f.read()
        start = raw.index('SYSTEM """') + len('SYSTEM """')
        end = raw.rindex('"""')
        return raw[start:end].strip()
    except Exception:
        return ""


def ruanmei_lore_for_prompt(user_msg="", limit=800):
    """只挑与当前问题相关的角色亲历段落，避免每轮注入整篇故事。"""
    try:
        with open(RUANMEI_STORY_FILE, "r", encoding="utf-8") as f:
            raw = f.read()
    except Exception:
        return ""
    sections = _habit_sections(raw)
    q = str(user_msg or "").lower()
    if not q:
        return ""
    scored = []
    for idx, sec in enumerate(sections):
        title = sec["title"]
        hints = RUANMEI_STORY_HINTS.get(title, ())
        hits = sum(1 for h in hints if h.lower() in q)
        if hits:
            scored.append((hits, idx, sec))
    if not scored:
        return ""
    scored.sort(key=lambda x: (-x[0], x[1]))
    parts, used = [], 0
    for _, _, sec in scored:
        block = ("## " + sec["title"] + "\n" + "\n".join(sec["lines"])).strip()
        if parts and used + len(block) + 2 > limit:
            break
        if not parts and len(block) > limit:
            block = block[:limit]
        parts.append(block)
        used += len(block) + 2
        if used >= limit:
            break
    if not parts:
        return ""
    return ("【本轮相关亲历记忆】下面只用于回答当前问题。可以自然转述，"
            "不要逐字背诵，也不要把未出现的段落自行补全。\n\n"
            + "\n\n".join(parts))


def habits_for_prompt(user_msg="", limit=1400):
    """
    只注入这轮相关的习惯小节，而不是每次把整份文件塞进 context。

    结构仍然是 data\\习惯.md 的 Markdown（方便人编辑、也方便程序按标题取），
    这里按标题关键词挑小节；挑不到才回退到整份。
    """
    raw = load_habits().strip()
    if not raw:
        return ""
    sections = _habit_sections(raw)
    if not sections:
        return clip(raw, head=max(200, limit - 300), tail=300)

    q = str(user_msg or "").lower()
    picked = []
    if q:
        scored = []
        for idx, sec in enumerate(sections):
            title = sec["title"]
            hits = sum(1 for h in HABIT_HINTS.get(title, ()) if h.lower() in q)
            if any(c in title for c in CORE_HABIT_SECTIONS):
                hits += 3
            if hits:
                scored.append((hits, idx, sec))
        if scored:
            scored.sort(key=lambda x: (-x[0], x[1]))
            picked = [sec for _, _, sec in scored]
            # 排日程/作息时，把生活习惯下面几节一起带上，否则会漏吃饭/通勤/娱乐。
            if any(k in q for k in ("作息", "日程", "规划", "时间表", "安排",
                                    "睡觉", "起床", "上课", "下课")):
                for sec in sections:
                    if sec["title"] in ("作息", "吃饭", "出门与通勤", "健康",
                                        "花钱与购物", "娱乐"):
                        if sec not in picked:
                            picked.append(sec)
    if not picked:
        picked = sections

    parts, used = [], 0
    for sec in picked:
        block = ("#" * sec["level"] + " " + sec["title"] + "\n"
                 + "\n".join(sec["lines"])).strip()
        if not block:
            continue
        if parts and used + len(block) + 2 > limit:
            break
        parts.append(block)
        used += len(block) + 2
    text = "\n\n".join(parts)
    if not text:
        return ""
    if len(picked) < len(sections):
        text = ("（以下只列这次对话相关的习惯；没列出的不代表没有，"
                "别自行补。）\n" + text)
    return text[:limit]


def habits_life_empty():
    """「生活习惯」那几节是不是一条都没写。
    用来决定要不要提醒模型"排日程前先问清楚"——空着还硬编一份作息表，等于瞎猜。"""
    raw = load_habits()
    if "## 生活习惯" not in raw:
        return True
    seg = raw.split("## 生活习惯", 1)[1]
    seg = seg.split("\n## ", 1)[0]          # 只看这一大节里的内容
    return not any(ln.strip().startswith("- ") for ln in seg.split("\n"))


def habits_add(text, section=""):
    """往习惯文件里加一条。有同名小节就插到那一节末尾，没有就新建一节。"""
    text = " ".join((text or "").split())
    if not text:
        return "[工具出错] 要记的内容是空的。"
    raw = load_habits()
    if not raw.strip():
        raw = HABITS_HEADER
    lines = raw.rstrip("\n").split("\n")
    bullet = "- " + text
    if any(ln.strip().lower() == bullet.lower() for ln in lines):
        return "这条已经记过了：%s" % text
    sec = (section or "").strip().lstrip("#").strip()
    if sec:
        # 小节标题可能是 ## 也可能是 ###（生活习惯下面那几节就是 ###），
        # 所以按"名字对得上"来找，不写死井号个数。
        start = next((i for i, ln in enumerate(lines)
                      if re.fullmatch(r"#{2,4}\s*" + re.escape(sec) + r"\s*", ln.strip())), None)
        if start is None:
            save_habits(raw.rstrip("\n") + "\n\n## " + sec + "\n" + bullet + "\n")
            return "记住了（新建「%s」一节）：%s" % (sec, text)
        level = len(lines[start]) - len(lines[start].lstrip("#"))
        end = len(lines)
        for i in range(start + 1, len(lines)):
            m = re.match(r"^(#{2,4})\s", lines[i].strip())
            if m and len(m.group(1)) <= level:      # 碰到同级或更高级的标题就到头了
                end = i
                break
        at = end
        while at > start + 1 and not lines[at - 1].strip():
            at -= 1
        lines.insert(at, bullet)
    else:
        lines.append(bullet)
    save_habits("\n".join(lines).rstrip("\n") + "\n")
    return "记住了：%s" % text


def habits_forget(keyword):
    keyword = (keyword or "").strip()
    if not keyword:
        return "[工具出错] 要说清删哪一条，给个关键词就行。"
    lines = load_habits().split("\n")
    kept, removed = [], []
    for ln in lines:
        if ln.strip().startswith("- ") and keyword in ln:
            removed.append(ln.strip())
        else:
            kept.append(ln)
    if not removed:
        return ("没找到含「%s」的那条。现在记着的是：\n%s"
                % (keyword, "\n".join(kept).strip() or "(还什么都没记)"))
    save_habits("\n".join(kept).rstrip("\n") + "\n")
    return "删掉了：\n" + "\n".join(removed)


def _auto_appearance():
    """没有 appearance.json 时，靠文件名自动判断背景和图标。"""
    bg_type, bg_file, icon = "none", "", ""
    if os.path.isdir(ASSETS_DIR):
        names = os.listdir(ASSETS_DIR)
        for kind, exts, want in (("video", VIDEO_EXT, ("bg", "background")),
                                 ("image", IMAGE_EXT, ("bg", "background"))):
            for n in sorted(names):
                stem, ext = os.path.splitext(n.lower())
                if ext in exts and stem in want:
                    bg_type, bg_file = kind, "assets/" + n
                    break
            if bg_type != "none":
                break
        for n in sorted(names):
            stem, ext = os.path.splitext(n.lower())
            if ext in ICON_EXT and stem in ("icon", "favicon", "logo", "avatar"):
                icon = "assets/" + n
                break
    return {"bg_type": bg_type, "bg_file": bg_file, "icon": icon,
            "bg_dim": 70, "sidebar_blend": 55,
            "side_opacity": 78, "foot_opacity": 78, "head_opacity": 78,
            "extra_read": []}


def load_appearance():
    if os.path.exists(APPEARANCE_FILE):
        try:
            with open(APPEARANCE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            def lvl(key, default):
                """0~100 的百分比参数，脏数据一律夹回范围里。"""
                try:
                    return max(0, min(100, int(data.get(key, default) or 0)))
                except (TypeError, ValueError):
                    return default

            return {"bg_type": str(data.get("bg_type") or "none"),
                    "bg_file": str(data.get("bg_file") or ""),
                    "icon": str(data.get("icon") or ""),
                    "bg_dim": lvl("bg_dim", 70),
                    "sidebar_blend": lvl("sidebar_blend", 55),
                    "side_opacity": lvl("side_opacity", 78),
                    "foot_opacity": lvl("foot_opacity", 78),
                    "head_opacity": lvl("head_opacity", 78),
                    "extra_read": [str(x) for x in (data.get("extra_read") or [])
                                   if os.path.isdir(str(x))]}
        except Exception:
            pass
    return _auto_appearance()


def save_appearance(cfg):
    with open(APPEARANCE_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# 工具定义（告诉模型它有哪些能力）
# ---------------------------------------------------------------------------
TOOLS = [
    {"type": "function", "function": {
        "name": "list_dir",
        "description": "列出某个目录下的文件和子目录。用户说了具体目录（例如 F:\\某文件夹）就必须传那个路径，"
                       "绝对路径可以直接用。回答时只能照抄这里返回的真实路径。",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string", "description": "要列的目录，如 F:\\qqqqq\\Documents 或相对路径"}},
            "required": []}}},
    {"type": "function", "function": {
        "name": "read_file",
        "description": "读取一个文本文件的内容（图片、压缩包这类二进制文件读不了，图片要用 see_image）",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string", "description": "文件相对路径"},
            "max_chars": {"type": "integer", "description": "最多读多少字符，默认 4000"}},
            "required": ["path"]}}},
    {"type": "function", "function": {
        "name": "write_file",
        "description": "创建或覆盖一个文本文件。要新建文件、写内容，一律用这个，"
                       "不要用 run_cmd 拼 echo 命令（那样写进去的是命令本身，不是内容）。",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string", "description": "文件相对路径"},
            "content": {"type": "string", "description": "要写入的完整正文，换行用 \\n"}},
            "required": ["path", "content"]}}},
    {"type": "function", "function": {
        "name": "run_cmd",
        "description": "在工作目录里执行一条命令，输出会返回给你。查看系统/硬件/进程状态、"
                       "跑脚本、装依赖都用它。例如：nvidia-smi（看显卡）、tasklist（看进程）、"
                       "systeminfo、python xxx.py。用户说某个设备不识别、某条命令报错、"
                       "想看某样东西的运行情况时，先自己跑一条命令去看，不要让他自己去试。",
        "parameters": {"type": "object", "properties": {
            "command": {"type": "string", "description": "要执行的命令，如 nvidia-smi"}},
            "required": ["command"]}}},
    {"type": "function", "function": {
        "name": "system_info",
        "description": "查这台电脑的整体状态：CPU 型号/使用率/温度、内存、显卡型号和驱动、占用最高的进程。"
                       "用户问“电脑怎么样/为什么卡/温度多少/某个监控数值不对/设备没被识别”这类问题时，"
                       "先用它（它比 nvidia-smi 全，nvidia-smi 只有显卡，没有 CPU）。",
        "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {
        "name": "gpu_check",
        "description": "查显卡和显示器这条链路：有哪几块显卡、显示器由哪块驱动、每个程序的显卡偏好、"
                       "硬件加速 GPU 计划开没开、NVIDIA 叠加层进程在不在、驱动版本。"
                       "用户问“英伟达的 FPS 检测显示 N/A / 叠加层不显示帧数 / 游戏跑在核显还是独显 / "
                       "GPU 没被识别 / 显存占满”这类问题时**必须用这个**，不要只跑 nvidia-smi —— "
                       "nvidia-smi 只有显卡自己那点信息，答不了「画面是谁在输出」这种问题。",
        "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {
        "name": "install_app",
        "description": "查或装软件（走 winget）。用户让你“修复/解决”某个问题、而修复需要装工具时用它。"
                       "action=search 只查包（比如 LibreHardwareMonitor.LibreHardwareMonitor），"
                       "查到之后要问用户是否同意安装；只有用户明确说“装吧”这类话之后，"
                       "才可以再调一次并带 action=install。",
        "parameters": {"type": "object", "properties": {
            "action": {"type": "string", "description": "search 查；install 装"},
            "query": {"type": "string", "description": "软件名或 winget 包 ID，如 LibreHardwareMonitor.LibreHardwareMonitor"}},
            "required": ["action", "query"]}}},
    {"type": "function", "function": {
        "name": "android",
        "description": "操作连在这台电脑上的安卓手机 / 华为平板（走 adb）。"
                       "action 可填：devices（看连没连上）、screenshot（截屏到工作目录，"
                       "之后可以用 see_image 看图）、pull（从手机拉文件）、push（往手机传文件）、"
                       "apps（列已装应用）、launch（arg=包名，打开应用）、shell（arg=命令）。"
                       "用户让你看手机屏幕、把手机里的照片拿过来、往手机传文件、"
                       "在手机上执行操作时用它。",
        "parameters": {"type": "object", "properties": {
            "action": {"type": "string", "description": "devices/screenshot/pull/push/apps/launch/shell"},
            "arg": {"type": "string", "description": "动作的参数：包名、手机端路径、命令等"},
            "save_as": {"type": "string", "description": "截图或拉文件时存到工作目录的文件名"},
            "target": {"type": "string", "description": "push 时的手机目标目录，默认 /sdcard/Download/"},
            "serial": {"type": "string", "description": "设备序列号，多设备时必须指定；devices 可查看"}},
            "required": ["action"]}}},
    {"type": "function", "function": {
        "name": "search_files",
        "description": "按文件名通配符搜索文件，比如 *.jpg 或 *.py。"
                       "用户指定了目录时，必须把那个目录填进 path，否则会搜错地方。",
        "parameters": {"type": "object", "properties": {
            "pattern": {"type": "string", "description": "通配符，如 *.jpg"},
            "path": {"type": "string", "description": "在哪个目录里搜，如 F:\\qqqqq\\Documents；留空则搜工作目录"}},
            "required": ["pattern"]}}},
    {"type": "function", "function": {
        "name": "see_image",
        "description": "看一张图片（截图、照片、扫描件）：先识别图上的文字，"
                       "再描述画面里有什么。问图片相关的问题必须用这个，不要用 read_file。",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string", "description": "图片路径"},
            "question": {"type": "string", "description": "想从这张图里知道什么，可留空"}},
            "required": ["path"]}}},
    {"type": "function", "function": {
        "name": "make_pptx",
        "description": "生成一份 PPT（.pptx 文件）到工作目录。用户说“做个 PPT / 演示 / "
                       "幻灯片 / 汇报材料 / 路演稿”时用它，一句话就能出文件。"
                       "content 写 Markdown：# 开头是新的一页标题，- 开头是这一页的要点，"
                       "--- 也可以手动分页。**不要自己写 python 脚本，也不要用 run_cmd 调 "
                       "python-pptx** —— 直接调用这个工具，排版它自己会做。",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string", "description": "输出文件名，如 项目汇报.pptx"},
            "content": {"type": "string", "description": "正文 Markdown，# 分页，- 要点"},
            "title": {"type": "string", "description": "封面标题，可留空"},
            "subtitle": {"type": "string", "description": "封面副标题，可留空"}},
            "required": ["path", "content"]}}},
    {"type": "function", "function": {
        "name": "make_dayplan",
        "description": "排一份**日常规划表 / 作息时间表 / 日程表**（生成 xlsx）。"
                       "用户说「帮我写日常规划表 / 排个作息 / 做张时间表」时用它。"
                       "时间骨架由它自己算（起床→早饭→通勤→上午→午休→下午→下班→晚饭→"
                       "自由时间→洗漱→睡觉），所以**你只需要把他说的约束填进去**，"
                       "不要自己一段段写时间、更不要用 make_xlsx 手写整个表。"
                       "他没说到的参数别瞎编：先问清起床、上班/上课、下班、路上要多久、"
                       "晚上几点想停，问到了再调这个工具。",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string", "description": "输出文件名，如 我的日常规划.xlsx"},
            "wake": {"type": "string", "description": "几点起床，如 7:30"},
            "sleep": {"type": "string", "description": "几点睡，如 23:30"},
            "work_start": {"type": "string", "description": "几点到公司/到教室，如 8:30"},
            "work_end": {"type": "string", "description": "几点下班/放学，如 18:00"},
            "commute": {"type": "string", "description": "单程路上多少分钟，如 40"},
            "classes": {"type": "string", "description": "**上课日必须用这个**：课表，一节课一行，"
                        "写成「10:30-12:30 上课」；给了它就走「课表 + 空档 + 自由时间」的排法，"
                        "不用再传 work_start/work_end/commute"},
            "wake_before": {"type": "string", "description": "比第一节课早多少分钟起床，默认 30"},
            "lunch": {"type": "string", "description": "午饭+午睡多少分钟，默认 150"},
            "sleep_range": {"type": "string", "description": "睡觉时间区间，如 01:00-04:00"},
            "extras": {"type": "string", "description": "另外要排进去的固定安排，每行一条，"
                        "带时间最好，例如「20:00 健身」；没有就留空"},
            "title": {"type": "string", "description": "表头标题，默认「日常规划表」"}},
            "required": ["path"]}}},
    {"type": "function", "function": {
        "name": "make_docx",
        "description": "生成一份 Word 文档（.docx）到工作目录。用户说“写个文档 / 报告 / "
                       "说明 / 方案 / 合同草稿”时用它。content 写 Markdown："
                       "# 是一级标题，- 是项目符号，1. 是编号，> 是引用。"
                       "**不要用 run_cmd 调 python-docx**，直接调用这个工具。",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string", "description": "输出文件名，如 方案.docx"},
            "content": {"type": "string", "description": "正文 Markdown"},
            "title": {"type": "string", "description": "文档标题，可留空"}},
            "required": ["path", "content"]}}},
    {"type": "function", "function": {
        "name": "make_xlsx",
        "description": "生成一份 Excel 表格（.xlsx）到工作目录。用户说“做个表格 / 台账 / "
                       "预算表 / 清单”或者让你把数据整理成 Excel 时用它。content 每行一条记录，"
                       "用逗号或 Tab 分隔；第一行自动当表头；数字会自动变成数值（带 % 的按百分比）；"
                       "以 # 开头的行表示新建一张工作表。**不要用 run_cmd 调 openpyxl**。",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string", "description": "输出文件名，如 预算.xlsx"},
            "content": {"type": "string", "description": "表格正文，一行一条，逗号或 Tab 分隔"}},
            "required": ["path", "content"]}}},
    {"type": "function", "function": {
        "name": "edit_video",
        "description": "剪视频（走 ffmpeg，本机离线）。用户说“把这段剪一下 / 去掉片头 / "
                       "把这几段拼起来 / 抽出音频 / 转成动图 / 加速慢放 / 去掉声音 / 改分辨率”时用它。"
                       "input 是源文件路径（多个用竖线 | 分隔），output 是输出文件名。",
        "parameters": {"type": "object", "properties": {
            "action": {"type": "string", "description": "trim 剪一段 / concat 拼接 / "
                        "extract_audio 抽音频 / to_gif 转动图 / speed 变速 / mute 静音 / scale 改分辨率"},
            "input": {"type": "string", "description": "源视频，多个用 | 分隔"},
            "output": {"type": "string", "description": "输出文件名，如 成片.mp4"},
            "start": {"type": "string", "description": "开始时间，秒数或 00:01:30"},
            "end": {"type": "string", "description": "结束时间，秒数或 00:02:00"},
            "width": {"type": "string", "description": "scale/to_gif 的目标宽度，如 1280"},
            "fps": {"type": "string", "description": "to_gif 的帧率，默认 12"},
            "speed": {"type": "string", "description": "speed 的倍数，如 1.5 或 0.8"}},
            "required": ["action", "input", "output"]}}},
    {"type": "function", "function": {
        "name": "remember",
        "description": "把主人的一条长期习惯/偏好记进「习惯」文件，以后每次对话都会自动读到。"
                       "**干活的和生活的都记**：干活类（剪视频 / 做PPT / 语音 / 界面 / 干活的方式），"
                       "生活类（作息 / 吃饭 / 出门 / 健康 / 花钱 / 娱乐 / 音乐）。"
                       "什么时候用：他说「以后都这样 / 记住 / 我喜欢这样 / 我一般 / 我习惯」这类"
                       "**面向以后**的话；或者同一件事他纠正过两次以上。"
                       "**一次性的临时要求不要记**（比如这次导出到哪个目录、今天几点出门）。"
                       "记的时候要写成能直接照办的句子，带上具体数值和时间点，例如"
                       "「做 PPT 用深色主题，每页不超过 5 条要点」「一般 23:30 睡、7:30 起」。",
        "parameters": {"type": "object", "properties": {
            "text": {"type": "string", "description": "一句话说清这条习惯，要具体到能照办"},
            "section": {"type": "string", "description": "归到哪一类：作息 / 吃饭 / 出门与通勤 / 健康 / "
                        "花钱与购物 / 娱乐 / 音乐 / 剪视频 / 做PPT / 语音 / 界面；不确定就留空"}},
            "required": ["text"]}}},
    {"type": "function", "function": {
        "name": "forget",
        "description": "从「习惯」文件里删掉某一条。主人说「这个不用记了 / 忘掉刚才那条」时用它，"
                       "给个能定位到那条的关键词就行。",
        "parameters": {"type": "object", "properties": {
            "keyword": {"type": "string", "description": "要删的那条里的关键词"}},
            "required": ["keyword"]}}},
    {"type": "function", "function": {
        "name": "app",
        "description": "操作别的程序（不只是音乐）：列出能启动的应用、按名字启动、列出/切换窗口、"
                       "往指定窗口发按键。用户说「打开剪映 / 打开微信 / 切到浏览器 / "
                       "在 XX 里按空格 / 关掉 XX 窗口」时用它。"
                       "press 必须带 title（窗口关键词），否则会打到别的窗口上；"
                       "只支持白名单键（方向键、空格、回车、esc、tab、媒体键、音量、ctrl+字母）。"
                       "close 前确认用户确实想关（可能丢未保存内容）。",
        "parameters": {"type": "object", "properties": {
            "action": {"type": "string", "description": "list / launch / windows / focus / press / close"},
            "name": {"type": "string", "description": "launch 时：应用名，如 剪映专业版"},
            "title": {"type": "string", "description": "focus / press / close 时：窗口标题关键词"},
            "keys": {"type": "string", "description": "press 时的键，空格分隔，如 space 或 down down enter"}},
            "required": ["action"]}}},
    {"type": "function", "function": {
        "name": "music",
        "description": "控制 QQ音乐 的播放（Windows 媒体会话，能读也能控）。"
                       "action 可选：status / play / pause / toggle / next / prev / "
                       "vol_up / vol_down / mute / open / taste / limits / play_query。"
                       "play_query 使用后台 UI Automation（键盘焦点和控件 Invoke）， "
                       "不会移动或点击主人的鼠标；完成后会最小化 QQ音乐。"
                       "· 放歌、暂停、切歌、看现在放什么、调音量、打开软件 → 用对应 action；"
                       "· 他问「我爱听什么 / 我的听歌喜好」→ action=taste；"
                       "· 他点名要**某个歌单或某首歌**（比如「播放周杰伦的晴天」「我喜欢歌单」）"
                       "→ 调 action=play_query，query 填歌名或歌单名，kind 填 song 或 playlist；"
                       "如果它返回「照这句说：…」，就照那句说，不要自己另编；"
                       "· 他说「记住：我爱听 X」这种长期偏好 → 用 remember(section=音乐)。",
        "parameters": {"type": "object", "properties": {
            "action": {"type": "string", "description": "status / play / pause / toggle / next / "
                        "prev / vol_up / vol_down / mute / open / play_query"},
            "query": {"type": "string", "description": "play_query 时：歌名、歌手+歌名或歌单名"},
            "kind": {"type": "string", "description": "play_query 时：song 或 playlist"},
            "title": {"type": "string", "description": "play_query 时：主标题，可留空"},
            "steps": {"type": "integer", "description": "音量那几个动作按几次，默认 1"}},
            "required": ["action"]}}},
    {"type": "function", "function": {
        "name": "remind",
        "description": "管定时提醒：到点由梅梅自己用语音念出来（这台机器的音箱），不用页面开着。"
                       "主人说「提醒我 / 每天几点叫我 / 到点告诉我」时用它。"
                       "action=add 要同时给 text（提醒内容，写成一句能直接念的话）和 at（24 小时制的"
                       "HH:MM，比如 23:00），repeat 填 daily（每天）/ weekdays（工作日）/ weekly（每周，"
                       "再给 days 数组，1=周一）/ once（只响一次，再给 date=YYYY-MM-DD）。"
                       "action=list 列出来；action=delete 用 keyword 删。"
                       "注意：这是一次性的排程，**不要**用 remember 记它。",
        "parameters": {"type": "object", "properties": {
            "action": {"type": "string", "description": "add / list / delete"},
            "text": {"type": "string", "description": "提醒内容，例如「该睡觉了」"},
            "at": {"type": "string", "description": "24 小时制时间，如 23:00"},
            "repeat": {"type": "string", "description": "daily / weekdays / weekly / once"},
            "days": {"type": "array", "items": {"type": "integer"},
                     "description": "repeat=weekly 时用，1=周一 … 7=周日"},
            "date": {"type": "string", "description": "repeat=once 时用，YYYY-MM-DD"},
            "keyword": {"type": "string", "description": "action=delete 时用来定位那条"}},
            "required": ["action"]}}},
]

TOOLS.append({"type": "function", "function": {
    "name": "recall",
    "description": "查看已记录的长期习惯。用户问记住了什么、平常的作息或其他偏好时用它；不会修改记录。",
    "parameters": {"type": "object", "properties": {
        "query": {"type": "string", "description": "要查看的习惯主题，留空查看全部摘要"}}, "required": []}}})
TOOL_BY_NAME = {t["function"]["name"]: t for t in TOOLS}
TOOL_GROUPS = {
    "file": ("list_dir", "read_file", "write_file", "search_files"),
    "system": ("run_cmd", "system_info", "gpu_check", "install_app"),
    "app": ("app",),
    "android": ("android",),
    "image": ("see_image",),
    "docx": ("make_docx",),
    "xlsx": ("make_xlsx",),
    "pptx": ("make_pptx",),
    "dayplan": ("make_dayplan",),
    "video": ("edit_video",),
    "memory": ("remember", "forget", "recall"),
    "reminder": ("remind",),
    "music": ("music",),
}
TOOL_TRIGGERS = {
    "file": ("文件", "文件夹", "目录", "路径", "读取", "写入", "新建", "创建",
             "修改", "查找", "搜索", "代码", "日志", "截图"),
    "system": ("电脑", "系统", "显卡", "gpu", "cpu", "内存", "温度", "进程",
               "驱动", "安装", "卸载", "修复", "报错", "错误", "端口", "服务",
               "命令", "诊断", "检查"),
    "app": ("打开", "启动", "切换", "关闭", "窗口", "应用", "程序"),
    "android": ("手机", "平板", "安卓", "android", "adb"),
    "image": ("图片", "照片", "看图", "图像", "识别", "ocr", "扫描件", "这张", "图中", "图里", "图上"),
    "docx": ("word", "docx", "文档", "报告", "方案", "合同"),
    "xlsx": ("excel", "xlsx", "表格", "台账", "预算", "清单"),
    "pptx": ("ppt", "幻灯片", "演示", "汇报"),
    "dayplan": ("日程", "作息", "时间表", "规划表", "安排一下", "规划一下", "计划表"),
    "video": ("视频", "剪辑", "片头", "片尾", "动图", "分辨率", "抽音频",
              "拼接", "变速", "静音", "剪短", "剪掉", "慢放", "加速"),
    "memory": ("记住", "忘掉", "忘记", "习惯", "以后都", "长期", "我一般", "记了什么", "偏好"),
    "reminder": ("提醒", "每天", "工作日", "每周", "叫我"),
    "music": ("音乐", "歌单", "歌曲", "听歌", "点歌", "切歌",
              "下一首", "上一首", "音量", "qq音乐", "换一首", "换首歌"),
}
GENERAL_TOOLS = ("list_dir", "read_file", "write_file", "run_cmd", "app")


def select_tools(user_msg, history=None):
    """按本轮意图只发送相关工具，减少每次请求的固定 schema token。"""
    q = str(user_msg or "").lower()
    if not q:
        return []
    groups = set()
    for group, words in TOOL_TRIGGERS.items():
        if any(w in q for w in words):
            groups.add(group)
    if re.search(r"刚才|接着|继续|那段|这个|它|换一首", q):
        for msg in reversed((history or [])[-6:]):
            if msg.get("role") != "user" or msg.get("content") == user_msg:
                continue
            prev = str(msg.get("content") or "").lower()
            for group, words in TOOL_TRIGGERS.items():
                if any(w in prev for w in words):
                    groups.add(group)
            break
    if (("播放" in q or "暂停" in q)
            and not any(w in q for w in ("视频", "电影", "电视", "录音", "播客"))):
        groups.add("music")
    if re.search(r"(?:^|[\s\"'])(?:[a-z]:\\|/)", q):
        groups.add("file")
    if groups:
        names = []
        for group in TOOL_GROUPS:
            if group not in groups:
                continue
            names.extend(TOOL_GROUPS[group])
        if groups & {"image", "video"}:
            names.extend(TOOL_GROUPS["file"])
        unique = list(dict.fromkeys(names))
        return [TOOL_BY_NAME[n] for n in unique if n in TOOL_BY_NAME]
    if re.search(r"帮我|处理|操作|看一下|看看|用过|完成|执行|生成|创建|搜索|查询", q):
        return [TOOL_BY_NAME[n] for n in GENERAL_TOOLS]
    return []


CASUAL_GREETINGS = (
    "早安", "早上好", "上午好", "中午好", "下午好", "晚上好", "晚安",
)
CASUAL_CHAT_HINTS = CASUAL_GREETINGS + (
    "天气", "点心", "早餐", "午饭", "晚饭", "吃什么", "今天过得", "今天想做什么",
    "想做什么", "在吗", "忙吗", "陪我", "聊天", "无聊", "好累", "有点累",
    "开心", "难过",
)
REALTIME_TOPIC_WORDS = (
    "天气", "气温", "温度", "下雨", "下雪", "空气质量", "pm2.5", "外面冷", "外面热",
)
REALTIME_CLAIM_PATTERNS = (
    r"(?:今天|现在|外面|当前).{0,10}(?:天气|气温|温度|晴朗?|阴天?|下雨|下雪|空气质量)",
    r"(?:天气|气温|空气质量).{0,8}(?:不错|很好|真好|晴朗|阴沉|下雨|降温|升温|\d+\s*(?:度|℃))",
    r"(?:pm2\.5|空气)(?:指数|质量).{0,8}\d+",
)


def is_casual_chat_turn(user_msg):
    """日常寒暄和生活闲聊不调用工具，需要单独的质量约束。"""
    q = re.sub(r"\s+", "", str(user_msg or ""))
    if not q:
        return False
    return any(word in q for word in CASUAL_CHAT_HINTS)


def asks_for_realtime_fact(user_msg):
    q = str(user_msg or "").lower()
    return any(word in q for word in REALTIME_TOPIC_WORDS)


def _visible_reply_len(text):
    """去掉称呼、标点和空白后估算中文回复长度，避免把格式误算成内容。"""
    s = str(text or "").replace(WAKE_WORD, "")
    return len(re.sub(r"[\W_]+", "", s, flags=re.UNICODE))


def has_ungrounded_realtime_claim(text):
    """当前没有天气工具；带结论的天气/温度表述一律视为无依据。"""
    s = str(text or "")
    return any(re.search(pattern, s) for pattern in REALTIME_CLAIM_PATTERNS)


def casual_reply_issue(user_msg, reply):
    """返回日常回复的问题标签；空字符串表示无需重写。"""
    if not is_casual_chat_turn(user_msg):
        return ""
    issues = []
    if _visible_reply_len(reply) < 18:
        issues.append("回复过短")
    if has_ungrounded_realtime_claim(reply):
        issues.append("无工具依据的实时事实")
    return "；".join(issues)


def casual_reply_guidance(messages, user_msg):
    """
    检测最近几轮是否形成了“只回一句”的短回复习惯，并把本轮要求写进 system。
    习惯检测只影响闲聊，不影响文件、系统等任务回复。
    """
    if not is_casual_chat_turn(user_msg):
        return ""
    recent = [
        str(m.get("content") or "") for m in (messages or [])[-8:]
        if isinstance(m, dict) and m.get("role") == "assistant"
    ][-4:]
    short_count = sum(1 for item in recent if _visible_reply_len(item) < 18)
    habit_note = ""
    if short_count >= 2:
        habit_note = ("检测到最近连续出现简短敷衍的日常回复。本轮要主动改掉这个习惯，"
                      "不要只答一句。")
    return (
        "【日常回复习惯】这是闲谈或寒暄，不是任务。仍保持阮·梅的克制，但回复用 3 到 5 个"
        "自然短句：先正常回应，再给一个具体的当前场景细节，最后邀请主人尝点心、喝茶、"
        "坐下聊两句，或用一句自然问话接住话题。可结合下面给出的生活习惯和听歌偏好，"
        "但不要背清单、不要写成客服套话。点心、茶等可以写成陪伴场景中的细节。"
        "没有工具结果时，禁止声称已经查到天气、气温、空气质量或外面的实时情况；"
        "涉及这些内容就直说没有接入相应程序。" + habit_note
    )


CASUAL_REWRITE_NUDGE = (
    "（系统检测到上一版不符合当前闲聊要求：要么太短，要么把没有工具依据的天气等"
    "实时情况说成了事实。不要解释检测过程，直接重写一遍。保持「亲爱的」开头，"
    "用 3 到 5 个自然短句，加入具体场景细节和自然邀请；可结合已知习惯。"
    "没有工具依据时不得报天气、气温或空气质量。）"
)


def _casual_habit_ending(now=None):
    """用已经注入的生活习惯选一句不冒犯、不过度推断的收尾。"""
    now = now or datetime.datetime.now()
    hour = now.hour
    habits = load_habits()
    if 12 <= hour < 17 and "课" in habits:
        return "你下午通常还有课，若时间紧，就晚些再来尝。"
    if 17 <= hour < 23 and "健身" in habits:
        return "你晚餐后通常要去健身；若今晚不去，我们就慢慢分着吃。"
    if hour >= 1 and hour < 6 and "凌晨" in habits:
        return "你又忙到这个点了，吃完记得早点休息。"
    return "你若现在不忙，就过来坐一会儿吧。"


def fallback_casual_reply(user_msg, now=None):
    """模型连续重写仍不合格时的角色化兜底，不声称任何实时外部事实。"""
    q = str(user_msg or "")
    if asks_for_realtime_fact(q):
        return (
            "亲爱的，我没有接入天气程序，不能替你确认外面的天气。"
            "要出门的话，先看一眼天气应用吧。"
            "回来得早，我留一块点心给你。"
        )
    if "点心" in q or "吃什么" in q:
        return (
            "亲爱的，我想试做一小盘桂花酥，再配一壶清茶。"
            "要是你今晚不去健身，我们就慢慢分着吃。"
            "你若赶着出门，我也可以替你留一小盒点心。"
        )
    if any(word in q for word in ("好累", "有点累", "难过")):
        return (
            "亲爱的，那就先停一会儿，不必急着把每件事都做完。"
            "我把茶温着，点心也放在一旁。"
            "你若愿意，就和我说说今天哪里最费神。"
        )
    if any(word in q for word in ("在吗", "忙吗")):
        return (
            "亲爱的，在的。"
            "我刚把一小盘点心端出来，茶也还温着。"
            "你说吧，我在听。"
        )
    greeting = next((item for item in CASUAL_GREETINGS if item in q), "")
    if not greeting:
        hour = (now or datetime.datetime.now()).hour
        greeting = ("早上好" if hour < 11 else "下午好" if hour < 18 else "晚上好")
    return (
        "亲爱的，%s。"
        "我刚把一小盘点心端出来，茶也还温着。"
        "%s" % (greeting, _casual_habit_ending(now))
    )


def safe_path(workdir, rel, extra_read=()):
    """
    把路径解析到工作目录内，越界就拒绝（防止模型读写系统文件）。
    读操作额外允许访问 extra_read 里列的目录（比如放图片、素材的盘）。
    """
    p = canonical_path(os.path.join(workdir, rel or "."))
    wd = canonical_path(workdir)
    # Resolve symlinks/junctions before checking containment, including new files.
    if os.name=='nt' and ':' in os.path.splitdrive(p)[1]:
        raise ValueError('不允许使用NTFS备用数据流路径')
    if path_within(p,wd):
        return p
    if os.path.isabs(rel or ""):
        for d in extra_read or ():
            d = canonical_path(d)
            if d and path_within(p,d):
                return p
    # 报错要把「到底能用哪些目录」说清楚，否则模型只会放弃，不会自己改路径
    allowed = [wd] + [os.path.abspath(d) for d in (extra_read or ())
                      if os.path.isdir(d)]
    raise ValueError(
        "路径越界：%s 不在允许范围内。\n可用的目录是：\n  - %s\n"
        "请改用上面这些目录里的路径（工作目录可以写；只读目录只能读）。"
        % (rel, "\n  - ".join(allowed)))


# ---------------------------------------------------------------------------
# 看图：先本地 OCR（离线），再用视觉模型描述画面
# ---------------------------------------------------------------------------
_CJK = "\u3400-\u4dbf\u4e00-\u9fff\u3000-\u303f\uff00-\uffef\u00b7\u30fb"


def ocr_image_file(path, timeout=180):
    """用 Windows 自带 OCR 引擎识别图片里的文字。先放大，识别率明显更高。"""
    from PIL import Image

    im = Image.open(path)
    w, h = im.size
    scale = max(1.0, min(3.0, 1200.0 / max(1, h)))
    if scale > 1.01:
        im = im.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
    tmp = os.path.join(tempfile.gettempdir(),
                       "rm_ocr_%d_%d.png" % (os.getpid(), abs(hash(path)) % 99991))
    im.convert("RGB").save(tmp)
    try:
        r = run_hidden(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
                            "-File", OCR_SCRIPT, "-Path", tmp],
                           capture_output=True, timeout=timeout)
        txt = r.stdout.decode("utf-8", "replace")
        if not txt.strip():
            txt = "[OCR 没有输出]" + (r.stderr.decode("utf-8", "replace")[:300])
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass
    # Windows 的 OCR 会把汉字之间也塞进空格，这里还原。
    # 只吃空格和制表符，别碰换行——否则每一行的行尾会跟下一行的行首粘在一起。
    txt = re.sub(r"(?<=[%s])[ \t]+(?=[%s])" % (_CJK, _CJK), "", txt)
    txt = "\n".join(line.rstrip() for line in txt.splitlines())
    return txt.strip()


def vision_model_name(ollama_base, timeout=6):
    """
    看看 ollama 里装了哪个视觉模型，没有就返回空。

    优先选名字里带 cpu 的版本：这台机器上，视觉编码器走 CUDA 会输出废数据，
    表现为「只要带图就报 prediction aborted / token repeat limit reached」，
    而同一个模型纯文字完全正常、换成 CPU 跑图片也完全正常。
    CPU 慢一些（一张图十几秒），但它是对的；而且不跟语言模型抢显存。
    """
    try:
        with urllib.request.urlopen(ollama_base.rstrip("/") + "/api/tags",
                                    timeout=timeout) as r:
            tags = json.loads(r.read().decode("utf-8"))
    except Exception:
        return ""
    names = [m.get("name", "") for m in tags.get("models", [])]
    vision_hint = ("vl", "vision", "minicpm-v", "moondream", "llava", "gemma3")
    for n in names:
        low = n.lower()
        if "cpu" in low and any(k in low for k in vision_hint):
            return n
    for want in ("minicpm-v", "moondream", "llava", "qwen2.5vl", "qwen2.5-vl", "gemma3"):
        for n in names:
            if n.startswith(want):
                return n
    return ""


def vlm_describe(path, question, model, ollama_base, timeout=600):
    """让视觉模型描述画面内容。"""
    import base64

    from PIL import Image, ImageOps
    # Bound encoder work on large screenshots; normalize formats Ollama cannot read.
    with Image.open(path) as image:
        image = ImageOps.exif_transpose(image).convert("RGB")
        image.thumbnail((1600, 1600))
        buf = io.BytesIO()
        image.save(buf, format="JPEG", quality=92)
        b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    prompt = question.strip() if question else "用中文简要描述这张图片的内容。"
    payload = {"model": model, "prompt": prompt, "images": [b64],
               "stream": False, "keep_alive": "2m",
               "options": {"temperature": 0.2, "num_predict": 512,
                           **({"num_gpu": 0} if "cpu" in model.lower() else {})}}
    req = urllib.request.Request(ollama_base.rstrip("/") + "/api/generate",
                                 data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json"},
                                 method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return (json.loads(r.read().decode("utf-8")).get("response") or "").strip()


# 明显的灭盘/关机类命令直接拒掉。agent 会自己拼命令，这一步是兜底。
DANGEROUS = (
    "format ", "diskpart", "rm -rf /", "rm -rf /*", "del /f /s /q c:\\",
    "del /f /s /q d:\\", "rd /s /q c:\\", "rd /s /q d:\\",
    "remove-item -recurse c:\\", "remove-item -recurse d:\\",
    "cipher /w", "shutdown", "vssadmin delete", "bcdedit",
    # 重启/关机这类"自己就能解决"的动作必须由用户决定：它一旦自己按下去，
    # 用户当前所有没保存的东西都没了。
    "restart-computer", "stop-computer", "logoff",
    "set-mppreference", "disable-windowsoptionalfeature",
)


def guard_command(cmd):
    low = " ".join((cmd or "").lower().split())
    for bad in DANGEROUS:
        if bad in low:
            raise ValueError("这条命令看着会破坏数据，已拒绝执行：%s" % cmd[:80])


CONFIRM_WORDS = ("确认", "确定", "同意", "执行吧", "可以执行", "就这么做",
                 "按你说的", "删吧", "关吧", "装吧", "安装吧")
HIGH_RISK_CMD = (r"\bdel\b", r"\brd\b", r"\brmdir\b", r"remove-item",
                 r"reg\s+(add|delete)", r"\bsc\b", r"net\s+user", r"taskkill",
                 r"stop-process", r"winget\s+uninstall", r"set-executionpolicy",
                 r"schtasks", r"icacls", r"takeown", r"attrib", r"diskpart",
                 r"\bformat\b")


def is_denied_action(user_msg):
    return bool(re.search(r'不(?:要|许|能|可以|同意|允许|安装|装|关闭|退出|执行|删除|确认|确定|需要|必|用)|无需|不是|没有(?:确认|同意|允许)|别(?:再)?|暂不|取消|未确认',str(user_msg or '')))


def is_confirmed(user_msg):
    t = str(user_msg or "").lower()
    if is_denied_action(t):
        return False
    t=t.strip().strip('。.!！')
    if t in ('确认','确定','同意','允许','按你说的'):
        return True
    return bool(re.search(r'(?:^|[，。！!？?\s])(?:我)?(?:确认执行|确认安装|确认关闭|同意执行|允许执行|执行吧|可以执行|就这么做|按你说的做|删吧|关吧|装吧|安装吧)(?:$|[，。！!？?\s：:])',t))


def is_high_risk_command(cmd):
    low = " ".join(str(cmd or "").lower().split())
    # An arbitrary shell can hide writes/deletions in scripts or child commands;
    # a keyword denylist cannot make it safe. Only fixed inspection commands
    # bypass confirmation; all other shell text needs the existing approval flow.
    return low not in {'pwd','cd','dir','ls','get-location','get-date','hostname',
                       'whoami','ver','systeminfo','ipconfig','nvidia-smi','nvidia-smi -l'}


# 出现这些词，说明用户是在描述现象或让你去查，而不是单纯聊天。
# 注意：这里**不要**放"帮我"这种泛词。实测踩过：一句"帮我写一份日常规划表"因为带"帮我"
# 被判成"该去查"，然后它被逼着调了个 system_info，最后答出来的是 CPU 和显卡温度。
LOOK_WORDS = ("为什么", "怎么回事", "什么原因", "查一下", "查查", "看一下", "看看",
              "是不是", "有没有", "报错", "不识别", "没被", "无法", "失败", "坏了",
              "占用", "有多少", "多大", "列出", "找到", "整理", "统计", "读")


# 反过来：出现这些词是"让我产出一份东西"，**不该**被"该查不查"那条规则拦住。
# 这类请求要的是 make_docx / make_xlsx / make_pptx 或者直接写出来，
# 而不是跑一条命令去看机器状态。
MAKE_WORDS = ("写一份", "写个", "写一篇", "帮我写", "做一份", "做个", "做一张", "生成",
              "拟一份", "拟个", "规划表", "计划表", "清单", "方案", "草稿", "提纲",
              "日程", "规划", "总结成", "整理成", "做成表", "表格", "ppt",
              "幻灯片", "文档", "模板", "文案", "邮件", "稿子")


def needs_look(messages, text):
    """判断这轮回答是不是"该先查一下再说"。"""
    if not text or len(text) < 4:
        return None
    low = text.lower()
    # 产出类请求直接放行：要的是"做出来"，不是"去看实际情况"
    if any(w in low for w in MAKE_WORDS):
        return None
    has_path = bool(re.search(r"[A-Za-z]:[\\/]|\.(png|jpe?g|webp|mp4|csv|json|txt|py|log|pdf)\b",
                              text, re.I))
    hit = any(w in text for w in LOOK_WORDS)
    if not (has_path or hit):
        return None
    img = bool(re.search(r"\.(png|jpe?g|webp|bmp|gif)\b", text, re.I))
    if img:
        return ("（别急着回答。这条消息里有一个图片路径：请先调用 see_image 看那张图，"
                "拿到结果再回答。）")
    return ("（别急着回答。这条消息是在说一个现象或让你去查：请先调用合适的工具"
            "（list_dir / search_files / read_file / run_cmd）看实际情况，再根据结果回答。"
            "不要只列可能的原因。**但如果你判断他要的其实是「产出一份东西」"
            "（写文档、做表格、写规划），那就不要乱调工具、直接做出来。**）")


# 用户明确同意装东西的说法。装软件是对系统的改动，所以没这句就只能"查"不能"装"。
APPROVE_WORDS = ("装吧", "安装吧", "可以装", "直接装", "帮我装", "装一个", "装一下", "装上",
                 "同意", "允许", "确认安装", "开始装", "都行", "可以", "好的装")


# ---- 只查不动手 ----
# 实测过的毛病：用户问"帮我检测一下为什么 FPS 显示 N/A"，它跑了个 nvidia-smi，
# 然后回一段"你可以尝试关闭一些不必要的程序"就结束 —— 查得不对，手也没动。
# 所以加最后一道关：带"修"意的问题，如果它想用建议收尾，就退回去一次，
# 逼它二选一 —— 要么自己动手，要么明确说清哪一步只能用户做、为什么。
FIX_WORDS = ("修复", "解决", "弄好", "搞定", "弄掉", "处理一下", "处理掉", "排查",
             "为什么", "怎么回事", "什么原因", "怎么修", "帮我改", "帮我搞", "帮我弄",
             "检测一下", "查一下", "看一下", "帮我检查")
ADVICE_WORDS = ("你可以尝试", "你可以试", "你可以先", "你可以打开", "你可以检查",
                "建议你", "建议您", "建议先", "需要你", "你需要", "请您", "请尝试",
                "重新安装", "手动")
# 这些工具一调用就等于"动了手"（改了文件、装了东西、出了成品）
ACT_TOOLS = ("write_file", "install_app", "make_pptx", "make_docx", "make_xlsx",
             "edit_video")


def wants_fix(text):
    return bool(text) and any(w in text for w in FIX_WORDS)


def looks_like_advice(answer):
    return bool(answer) and any(w in answer for w in ADVICE_WORDS)


ACTION_NUDGE = ("（这段话只是在给建议，等于把活推回给他。现在二选一，并且**必须按下面的样子说**："
                "\n【A 你能做】直接调用工具做完（装软件 install_app；改设置/跑命令 run_cmd；"
                "查硬件 gpu_check / system_info；建文件 write_file），做完再报结果。"
                "\n【B 你做不了】就以「这一步只能你来做：」开头，一句话说清"
                "① 具体是哪个界面里的哪个开关；② 为什么工具做不到；③ 做完怎么验证。"
                "\n不允许再出现「建议你检查一下」「你可以尝试」这种收尾 —— 那不叫回答。）")


# ---------------------------------------------------------------------------
# 手机联动：adb（安卓手机 / 华为平板都走这个）
# ---------------------------------------------------------------------------
ADB = r"C:\platform-tools\adb.exe" if os.path.exists(r"C:\platform-tools\adb.exe") else "adb"

# 每次请求给模型的上下文窗口。
# 模型自己的默认值是 4096 —— 系统提示词 + 9 个工具的描述 + 一次工具输出就能超，
# 超了 Ollama 直接返回 400（agent 那边表现成"运行出错"）：
#     request (5186 tokens) exceeds the available context size (4096)
# 所以这里显式抬高。代价是 KV cache 变大（4B 模型 8K 上下文大约多吃 1GB 显存），
# 显存紧张就把 RM_NUM_CTX 环境变量调小，或者让它回到 4096 并接受工具输出被砍得更狠。
LLM_NUM_CTX = int(os.environ.get("RM_NUM_CTX", "8192"))
CHAT_NUM_CTX = min(LLM_NUM_CTX, max(2048, int(os.environ.get("RM_CHAT_NUM_CTX", "4096"))))

# 手机上不能被模型随便执行的东西
ADB_DANGEROUS = ("rm -rf /sdcard", "rm -rf /storage", "pm clear", "factory", "wipe",
                 "reboot bootloader", "flash ", "fastboot", "format ", "mkfs",
                 "su -c", "pm uninstall --user 0 android")


def adb_run(args, timeout=120, binary=False, serial=""):
    r = run_hidden([ADB] + (["-s", serial] if serial else []) + args, capture_output=True, timeout=timeout)
    if binary:
        return r.returncode, r.stdout, r.stderr.decode("utf-8", "replace")
    return (r.returncode, (r.stdout or b"").decode("utf-8", "replace")
            + (r.stderr or b"").decode("utf-8", "replace"), "")


def adb_devices():
    rc, out, _ = adb_run(["devices", "-l"])
    if rc:
        return "[手机] ADB 查询失败：" + out[:300]
    body = "\n".join(l for l in out.splitlines() if re.match(r"^\S+\s+(?:device|offline|unauthorized)\b", l))
    if not body.strip():
        return ("[手机] 现在没有连上设备。\n"
                "要连上：① 手机「设置 → 关于手机 → 连点 7 次版本号」打开开发者选项；"
                "② 开发者选项里打开「USB 调试」；③ 用数据线插到这台电脑，手机上点「允许调试」。\n"
                "（华为平板同理；插上后再调一次这个工具就能看到设备。）")
    return "[手机] 设备状态（device=可用，unauthorized=请在设备上允许调试，offline=离线）：\n" + body


def select_android_serial(serial=""):
    rc, out, _ = adb_run(["devices"])
    if rc:
        raise ValueError("ADB 查询失败：" + out[:180])
    rows = [l.split()[:2] for l in out.splitlines() if re.match(r"^\S+\s+(?:device|offline|unauthorized)\b", l)]
    states = dict(rows)
    if serial:
        if states.get(serial) != "device":
            raise ValueError("目标设备未就绪（%s），请检查 USB 调试授权或连接" % states.get(serial, "未连接"))
        return serial
    ready = [s for s, state in rows if state == "device"]
    if len(ready) > 1:
        raise ValueError("连接了多台设备，请指定 serial：" + "、".join(ready))
    if not ready:
        raise ValueError("没有可用设备，请连接手机/平板并在设备上允许 USB 调试")
    return ready[0]


def android_tool(action, args, workdir):
    action = (action or "").strip().lower()
    a = str(args.get("arg") or "").strip()
    save_as = str(args.get("save_as") or "").strip()

    if action == "devices":
        return adb_devices()
    serial = select_android_serial(str(args.get("serial") or "").strip())

    def run_adb(command, **kwargs):
        return adb_run(command, serial=serial, **kwargs)

    if action == "screenshot":
        name = save_as or "手机截图.png"
        p = safe_path(workdir, name)
        rc, data, err = run_adb(["exec-out", "screencap", "-p"], timeout=180, binary=True)
        if rc != 0 or not data:
            return adb_devices() if rc != 0 else "[手机] 截屏失败：%s" % err[:200]
        with open(p, "wb") as f:
            f.write(data)
        return ("[手机] 截屏已存到 %s（%.0f KB）。想看内容就用 see_image 打开它。"
                % (name, len(data) / 1024))

    if action == "apps":
        rc, out, _ = run_adb(["shell", "pm", "list", "packages", "-3"], timeout=180)
        pkgs = [l.replace("package:", "").strip() for l in out.splitlines() if l.startswith("package:")]
        if not pkgs:
            return "[手机] " + (out.strip()[:300] or "没读到应用列表（手机连上了吗？）")
        return "[手机] 第三方应用 %d 个：\n%s" % (len(pkgs), "\n".join(sorted(pkgs)[:60]))

    if action == "launch":
        if not a:
            return "[工具出错] launch 需要 arg=包名，比如 com.tencent.mm"
        if any(x in a for x in (";", "&&", "|", " ")):
            return "[工具出错] 包名不合法"
        rc, out, _ = run_adb(["shell", "monkey", "-p", a, "-c",
                              "android.intent.category.LAUNCHER", "1"], timeout=120)
        ok = "Events injected: 1" in out or rc == 0
        return ("[手机] 已尝试启动 %s%s" % (a, "" if ok else "（可能没装这个包）")) + "\n" + out[:300]

    if action == "pull":
        if not a:
            return "[工具出错] pull 需要 arg=手机上的文件路径，比如 /sdcard/DCIM/Camera/a.jpg"
        name = save_as or os.path.basename(a.rstrip("/")) or "手机文件"
        p = safe_path(workdir, name)
        rc, out, _ = run_adb(["pull", a, p], timeout=600)
        if rc != 0:
            return "[手机] 拉取失败：%s" % out.strip()[:300]
        return "[手机] 已把 %s 拉到工作目录的 %s" % (a, name)

    if action == "push":
        if not a:
            return "[工具出错] push 需要 arg=工作目录里的文件（或 --target 指定手机目录）"
        src = safe_path(workdir, a)
        if not os.path.isfile(src):
            return "[工具出错] 工作目录里没有这个文件：%s" % a
        target = str(args.get("target") or "/sdcard/Download/").strip()
        rc, out, _ = run_adb(["push", src, target], timeout=600)
        if rc != 0:
            return "[手机] 推送失败：%s" % out.strip()[:300]
        return "[手机] 已把 %s 推到手机的 %s" % (a, target)

    if action == "shell":
        if not a:
            return "[工具出错] shell 需要 arg=要执行的命令"
        low = " ".join(a.lower().split())
        for bad in ADB_DANGEROUS:
            if bad in low:
                return "[工具出错] 这条命令会破坏手机数据，已拒绝：%s" % a[:80]
        rc, out, _ = run_adb(["shell", a], timeout=180)
        return "[手机] 退出码 %d\n%s" % (rc, clip(out, head=700, tail=300))

    return ("[工具出错] 不认识的 action：%s。可用：devices（看连了没）、screenshot（截屏）、"
            "pull（从手机拉文件）、push（往手机传文件）、apps（列应用）、"
            "launch（开应用）、shell（执行命令）" % action)


def winget(action, query, user_msg):
    """
    用 winget 查/装软件。
    action=search 只查询；action=install 会真的安装，但要求用户在最近一条消息里
    明确说过"装吧"这类话 —— 装软件是对系统的改动，不能由模型自己决定。
    """
    query = (query or "").strip()
    if not query:
        return "[工具出错] 缺少要查/要装的软件名或包 ID"
    if any(x in (query.lower()) for x in ("&&", "|", ";", ">", "<")):
        return "[工具出错] 软件名里有奇怪的字符，拒绝执行"
    if action == "search":
        cmd = ["winget", "search", query, "--accept-source-agreements"]
        timeout = 180
    else:
        approved = (is_confirmed(user_msg) or bool(re.search(r'帮我(?:安装|装)|安装(?:吧|一下)|装一个|可以装|直接装',user_msg or '')))
        if is_denied_action(user_msg):
            approved=False
        if not approved:
            return ("【需要用户确认】装软件要用户点头。你先把这件事说清楚（装什么、为什么、"
                    "以及装完能解决什么），然后问他一句是否可以。他回复「装吧」之后你再调一次，"
                    "这次带 action=install。\n（供参考：该包在 winget 里的可用性可以用 "
                    "install_app(action=search) 先查。）")
        cmd = ["winget", "install", "--id", query, "-e", "--silent",
               "--accept-package-agreements", "--accept-source-agreements"]
        timeout = 900
    try:
        r = run_hidden(cmd, capture_output=True, timeout=timeout,
                           encoding="utf-8", errors="replace")
    except Exception as e:
        return "[工具出错] winget 执行失败：%s" % str(e)[:200]
    out = ((r.stdout or "") + (r.stderr or "")).strip()
    head = "[winget %s] 退出码 %d\n" % (action, r.returncode)
    return head + clip(out, head=800, tail=300)


def clip(text, head=900, tail=300):
    """
    工具输出太长就砍中间。

    为什么砍中间而不是砍尾巴：这类输出（nvidia-smi、报错日志）有用的信息通常
    在开头（结论、表头）和结尾（错误行），中间往往是一大串重复的列表。
    更重要的原因：这些文字会原样塞进下一次请求的上下文，nvidia-smi 那种带进程
    列表的输出一个人就能顶到 2000 token，直接把 4096 的上下文撑爆 ——
    实测报错是 Ollama 返回 400：request (5186 tokens) exceeds the available context size (4096)。
    """
    text = text or ""
    if len(text) <= head + tail:
        return text
    return ("%s\n...(中间省略 %d 字，太长会撑爆模型上下文)...\n%s"
            % (text[:head], len(text) - head - tail, text[-tail:]))


def compact_tool_result(name, text):
    """回灌给模型的工具结果只留结论和关键上下文；界面仍可显示完整结果。"""
    result = str(text or "")
    if not result:
        return "（工具没有输出）"
    urgent = re.search(r"\[工具出错\]|\[需要确认\]|\[工具提示\]|退出码\s+\d+", result)
    if urgent and urgent.start() < 300:
        prefix = result[:500]
        rest = result[500:]
        return prefix + (("\n" + clip(rest, head=500, tail=200)) if rest else "")
    if name in ("list_dir", "search_files", "app", "android"):
        return clip(result, head=1200, tail=250)
    if name == "read_file":
        return clip(result, head=1100, tail=250) + "\n（如内容不足，请缩小读取范围或分段读取）"
    if name == "run_cmd":
        return clip(result, head=700, tail=300)
    if name.startswith("make_") or name == "write_file":
        return result[:700]
    return clip(result, head=800, tail=250)


def approx_tokens(text):
    """粗估 token：中文约 1.4 字/token，英文/符号约 4 字符/token。"""
    s = str(text or "")
    cjk = len(re.findall(r"[\u3400-\u9fff]", s))
    other = max(0, len(s) - cjk)
    return int(cjk / 1.4 + other / 4.0) + 1


def trim_history(messages, budget_tokens):
    """
    从最旧的开始丢，只保留最近一段连续对话。

    这不是"语义压缩"，只是防止长会话把 num_ctx 撑爆：早期内容如果真的重要，
    让用户重述一遍，比让模型在截断的上下文里硬猜更可靠。
    """
    msgs = []
    for source in messages or []:
        if not isinstance(source, dict):
            continue
        # Attachment paths belong to our API. Ollama's `images` expects base64,
        # so forwarding these paths would break the next ordinary chat turn.
        message = {key: value for key, value in source.items() if key != "images"}
        images = source.get("images")
        if isinstance(images, list) and images:
            message["content"] = str(message.get("content") or "") + "\n[附图路径：" + "、".join(str(p) for p in images[:3]) + "]"
        msgs.append(message)
    if not msgs:
        return [], 0
    kept, used = [], 0
    for m in reversed(msgs):
        cost = approx_tokens(m.get("content") or "") + 8
        if kept and used + cost > budget_tokens:
            break
        kept.append(m)
        used += cost
    kept.reverse()
    dropped = len(msgs) - len(kept)
    if dropped:
        kept.insert(0, {"role": "system", "content":
                        "（为了控制上下文，已省略较早的 %d 条消息。"
                        "如果里面有仍然有效的约束，回答前先向主人确认。）" % dropped})
    return kept, dropped


def exec_tool(name, args, workdir, extras_read=(), ollama_base="", user_msg=""):
    try:
        if name == "list_dir":
            p = safe_path(workdir, args.get("path"), extras_read)
            all_items = sorted(os.listdir(p))
            items = all_items[:200]
            head = "[目录] %s\n[共 %d 项%s]" % (p, len(all_items),
                                             "，只列出前 200 项" if len(all_items) > 200 else "")
            return head + "\n" + ("\n".join(items) or "(空目录)")

        if name == "read_file":
            p = safe_path(workdir, args["path"], extras_read)
            with open(p, "rb") as f:
                head = f.read(4096)
            if b"\x00" in head:
                return ("[工具提示] 这是二进制文件（图片、压缩包、视频等），不能当文本读。"
                        "如果是图片，请改用 see_image。")
            n = int(args.get("max_chars") or 4000)
            with open(p, "r", encoding="utf-8", errors="replace") as f:
                data = f.read(n)
            return clip(data, head=1100, tail=300) + ("\n...(已截断)" if len(data) >= n else "")

        if name == "write_file":
            p = safe_path(workdir, args["path"])
            os.makedirs(os.path.dirname(p) or workdir, exist_ok=True)
            with open(p, "w", encoding="utf-8") as f:
                f.write(args.get("content") or "")
            return "已写入 %s（%d 字）" % (args["path"], len(args.get("content") or ""))

        if name == "see_image":
            p = safe_path(workdir, args.get("path"), extras_read)
            if not os.path.isfile(p):
                return "[工具出错] 找不到这个图片文件：%s" % args.get("path")
            if os.path.splitext(p)[1].lower() not in READ_IMAGE_EXT:
                return "[工具出错] 不像是图片文件：%s" % args.get("path")
            out = []
            try:
                out.append(ocr_image_file(p))
            except Exception as e:
                out.append("[文字识别失败] %s: %s" % (type(e).__name__, str(e)[:200]))
            vmodel = vision_model_name(ollama_base) if ollama_base else ""
            if vmodel:
                try:
                    desc = vlm_describe(p, args.get("question"), vmodel, ollama_base)
                    out.append("[画面描述 · %s]\n%s" % (vmodel, desc or "(模型没有返回内容)"))
                except Exception as e:
                    out.append("[画面描述失败] %s: %s" % (type(e).__name__, str(e)[:200]))
            else:
                out.append("[画面描述] 没装视觉模型，以上只有文字识别结果。"
                           "要让梅梅能描述画面内容，需要拉一个视觉模型（见 README）。")
            return "\n\n".join(out)

        if name == "run_cmd":
            cmd = args.get("command")
            guard_command(cmd)
            if is_high_risk_command(cmd) and not is_confirmed(user_msg):
                return ("[需要确认] 这条命令会修改系统或删除数据，我先没执行：%s\n"
                        "如果确定要执行，请主人明确回复「确认执行」，然后再调一次。"
                        % str(cmd)[:160])
            r = run_hidden(cmd, shell=True, cwd=workdir,
                               capture_output=True, text=True, encoding="utf-8",
                               errors="replace", timeout=120)
            out = (r.stdout or "") + (r.stderr or "")
            return ("退出码 %d\n" % r.returncode) + clip(out)

        if name == "system_info":
            return system_info()

        if name == "gpu_check":
            return gpu_check()

        if name == "recall":
            query = str(args.get("query") or "").strip()
            content = habits_for_prompt(query, limit=4000) if query else load_habits()
            return "[已记录的习惯]\n" + (clip(content, head=3200, tail=600) if content else "还没有记录习惯。")

        if name == "remember":
            return habits_add(str(args.get("text") or ""), str(args.get("section") or ""))

        if name == "forget":
            return habits_forget(str(args.get("keyword") or ""))

        if name == "app":
            act = str(args.get("action") or "windows").lower()
            if act in ('press','keys','按键'):
                keys=str(args.get('keys') or '').lower().split()
                safe={'up','down','left','right','home','end','pageup','pagedown','tab','esc'}
                exact_request=(bool(keys) and bool(re.search(r'按|快捷键',str(user_msg or '')))
                               and all(k in str(user_msg or '').lower() for k in keys))
                if (not set(keys)<=safe and (is_denied_action(user_msg)
                        or not (is_confirmed(user_msg) or exact_request))):
                    return '[需要确认] 这些快捷键可能关闭窗口、粘贴或执行操作，请明确指定按键或回复「确认执行」。'
            if (act in ("close", "关闭")
                    and not (is_confirmed(user_msg) or (
                        re.search(r'关闭|退出|结束|关掉',str(user_msg or ''))
                        and not is_denied_action(user_msg)))):
                return ("[需要确认] 要关哪个窗口，先让主人确认一下（可能丢未保存内容），"
                        "确认后再调。")
            return app_tool(str(args.get("action") or "windows"),
                            str(args.get("name") or ""),
                            str(args.get("title") or ""),
                            str(args.get("keys") or ""))

        if name == "music":
            return music(str(args.get("action") or "status"),
                         steps=args.get("steps") or 1,
                         query=str(args.get("query") or ""),
                         kind=str(args.get("kind") or "song"),
                         title=str(args.get("title") or ""))

        if name == "remind":
            act = str(args.get("action") or "list").strip().lower()
            if act == "add":
                return reminder_add(args.get("text"), args.get("at"),
                                    args.get("repeat") or "daily",
                                    args.get("days") or [], args.get("date") or "")
            if act == "delete" or act == "del":
                return reminder_del(args.get("keyword") or args.get("text"))
            return reminder_list()

        if name == "android":
            if (str(args.get('action') or '').lower()=='shell'
                    and str(args.get('arg') or '').strip().lower() not in ('getprop','wm size','pm list packages','dumpsys battery')
                    and not is_confirmed(user_msg)):
                return '[需要确认] 手机shell命令可能改动设备，请明确回复「确认执行」后再运行。'
            return android_tool(str(args.get("action") or ""), args, workdir)

        if name == "install_app":
            act = str(args.get("action") or "search").strip().lower()
            query = str(args.get("query") or "")
            if (act == "install" and not is_confirmed(user_msg)
                    and not re.search(r"装|安装|下载|更新", str(user_msg or ""))):
                return ("[需要确认] 还没装。先问主人是否同意安装「%s」，"
                        "他明确说装吧之后再调 install。" % query)
            return winget(act, query, user_msg)

        if name in ("make_pptx", "make_docx", "make_xlsx"):
            p = safe_path(workdir, args.get("path"))
            content = str(args.get("content") or "")
            title = str(args.get("title") or "")
            if name == "make_pptx":
                return office_tools.build_pptx(
                    p, content, title, str(args.get("subtitle") or ""))
            if name == "make_docx":
                return office_tools.build_docx(p, content, title)
            return office_tools.build_xlsx(p, content)

        if name == "make_dayplan":
            p = safe_path(workdir, args.get("path") or "日常规划.xlsx")
            classes = str(args.get("classes") or "").strip()
            if classes:
                # 上课日：按课表排（起床 = 第一节课 - wake_before，午饭午睡、晚饭、自由活动）
                return office_tools.build_study_plan(
                    p, classes,
                    wake_before=args.get("wake_before") or "30",
                    lunch=args.get("lunch") or "150",
                    dinner="30",
                    sleep_range=args.get("sleep_range") or "01:00-04:00",
                    extras=args.get("extras") or "",
                    title=args.get("title") or "上课日规划")
            return office_tools.build_dayplan(
                p, wake=args.get("wake") or "07:30", sleep=args.get("sleep") or "23:30",
                work_start=args.get("work_start") or "09:00",
                work_end=args.get("work_end") or "18:00",
                commute=args.get("commute") or "40",
                extras=args.get("extras") or "",
                title=args.get("title") or "日常规划表")

        if name == "edit_video":
            ins = [s.strip() for s in re.split(r"[|;]", str(args.get("input") or "")) if s.strip()]
            if not ins:
                return "[工具出错] input 是空的。把源视频路径填进去（多个用 | 分隔）。"
            files = [safe_path(workdir, f, extras_read) for f in ins]
            out = safe_path(workdir, args.get("output"))
            for f in files:
                if os.path.isdir(f):
                    return "[工具出错] %s 是个目录，不是文件。" % f
            if len(files) == 1 and not os.path.isfile(files[0]):
                # 只给了文件名时，帮它到工作目录和只读目录里找一下
                hits = []
                for base in [workdir] + [d for d in (extras_read or ()) if os.path.isdir(d)]:
                    hits += list(bounded_matches(base,os.path.basename(files[0])))
                hits=[safe_path(workdir,p,extras_read) for p in hits]
                if len(hits) == 1:
                    files = hits
                elif hits:
                    return ("[工具提示] 同名文件找到多个，请写清楚用哪一个：\n" +
                            "\n".join(hits[:10]))
                else:
                    return ("[工具出错] 找不到 %s。先用 list_dir 或 search_files 确认文件名，"
                            "再调用。" % os.path.basename(files[0]))
            return office_tools.edit_video(
                str(args.get("action") or ""), files, out,
                start=args.get("start"), end=args.get("end"),
                width=args.get("width"), fps=args.get("fps"),
                speed=args.get("speed"))

        if name == "search_files":
            pat = args["pattern"]
            if os.path.isabs(pat) or os.path.splitdrive(pat)[0] or '..' in pat.replace('\\','/').split('/'):
                raise ValueError('搜索通配符不能使用绝对路径或上级目录')
            hits = []
            where = args.get("path")
            if where:
                # 指定了目录就只搜那里；越界会被 safe_path 拒绝
                bases = [safe_path(workdir, where, extras_read)]
            else:
                bases = [workdir] + [d for d in (extras_read or ()) if os.path.isdir(d)]
            truncated = False
            for base in bases:
                for p in bounded_matches(base,pat):
                    try:
                        p=safe_path(workdir,p,extras_read)
                    except ValueError:
                        continue
                    hits.append(os.path.relpath(p,workdir) if path_within(p,workdir) else p)
                    if len(hits) >= 100:
                        truncated = True
                        break
                if len(hits) >= 100:
                    break
            head = "[搜索] 在 %s 里找 %s，命中 %d 个%s" % (
                "；".join(bases), pat, len(hits), "（只显示前 100 个）" if truncated else "")
            if not hits:
                return head + "\n(没找到。可以换个通配符，或者用 list_dir 先看看目录里有什么)"
            return head + "\n" + "\n".join(hits)

        return "未知工具：%s" % name
    except Exception as e:
        return "[工具出错] %s: %s" % (type(e).__name__, str(e)[:300])


def ollama_chat(base, payload, timeout=900):
    req = urllib.request.Request(base.rstrip("/") + "/api/chat",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        # 光看到 "HTTP Error 400" 没法查问题：Ollama 会在这里给出真正的原因
        # （角色顺序不对、工具名对不上、上下文超了……），必须把它带出来。
        try:
            detail = e.read().decode("utf-8", "replace")[:600]
        except Exception:
            detail = ""
        raise RuntimeError("Ollama 返回 %d：%s" % (e.code, detail or "(没有说明)")) from None


class Handler(LocalRequestHandler):
    cfg = {}
    appearance = {"bg_type": "none", "bg_file": "", "icon": ""}
    server_version = "RuanMeiAgent/2.0"

    def log_message(self, fmt, *a):
        sys.stderr.write("[%s] %s\n" % (self.log_date_time_string(), fmt % a))

    def _send(self, code, body, ctype):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        # 页面和接口一律不缓存：改完外观刷新就能看到，不会被浏览器喂旧值
        self.send_header("Cache-Control", "no-store, must-revalidate")
        self.send_header("Pragma", "no-cache")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json_body(self):
        n = int(self.headers.get("Content-Length") or 0)
        data=json.loads(self.rfile.read(n).decode("utf-8")) if n else {}
        if not isinstance(data,dict):
            raise ValueError('请求体必须是JSON对象')
        return data

    def do_GET(self):
        p = self.path.split("?")[0]
        if p == "/api/image":
            try:
                query = urllib.parse.parse_qs(self.path.partition("?")[2])
                rel = (query.get("path") or [""])[0]
                if not rel.replace("\\", "/").startswith("attachments/"):
                    raise ValueError("仅提供已上传的图片")
                path = safe_path(self.cfg["workdir"], rel)
                if not path.lower().endswith(".jpg"):
                    raise ValueError("图片格式不支持")
                with open(path, "rb") as f:
                    self._send(200, f.read(), "image/jpeg")
            except (OSError, ValueError) as e:
                self._send(404, str(e), "text/plain; charset=utf-8")
            return
        if p == "/api/taste":
            self._send(200, json.dumps(
                {"text": music_taste(), "file": LISTEN_FILE}, ensure_ascii=False),
                "application/json; charset=utf-8")
            return
        if p == "/api/reminders":
            self._send(200, json.dumps(
                {"items": load_reminders(), "fired": load_fired(20),
                 "wake": WAKE_WORD}, ensure_ascii=False),
                "application/json; charset=utf-8")
            return
        if p == "/api/habits":
            self._send(200, json.dumps(
                {"text": load_habits() or HABITS_HEADER, "file": HABITS_FILE},
                ensure_ascii=False), "application/json; charset=utf-8")
            return
        if p in ("/", "/index.html"):
            path = os.path.join(HERE, "agent.html")
            if not os.path.exists(path):
                path = os.path.join(HERE, "index.html")
            with open(path, "rb") as f:
                self._send(200, f.read(), "text/html; charset=utf-8")
            return
        if p == "/manifest.webmanifest":
            # 让 Chrome/Edge 能把这个页面「安装」成独立应用（任务栏/开始菜单里就是一个 App）
            ic = self.appearance["icon"]
            icons = []
            if ic:
                icons = [{"src": "/assets/icon-192.png", "sizes": "192x192",
                          "type": "image/png", "purpose": "any"},
                         {"src": "/" + ic, "sizes": "512x512",
                          "type": "image/png", "purpose": "any"}]
                if not os.path.isfile(os.path.join(HERE, "assets", "icon-192.png")):
                    icons = [{"src": "/" + ic, "sizes": "512x512",
                              "type": "image/png", "purpose": "any"}]
            self._send(200, json.dumps({
                "name": "梅梅 · 本地 Agent", "short_name": "梅梅",
                "start_url": "/", "scope": "/", "display": "standalone",
                "background_color": "#0b0d12", "theme_color": "#0b0d12",
                "icons": icons}, ensure_ascii=False),
                "application/manifest+json; charset=utf-8")
            return
        if p == "/api/config":
            self._send(200, json.dumps(self._public_config(),
                                       ensure_ascii=False),
                       "application/json; charset=utf-8")
            return
        if p == "/api/status":
            self._send(200, json.dumps({
                "runtime_python": sys.executable,
                "ollama": self._reachable(self.cfg["ollama"] + "/api/tags"),
                "tts": self._reachable(self.cfg["tts"] + "/healthz"),
                "asr": self._reachable(self.cfg["asr"] + "/healthz"),
            }, ensure_ascii=False), "application/json; charset=utf-8")
            return
        if p.startswith("/assets/"):
            # 浏览器会把中文和空格编码成 %XX，这里必须先解回来，否则
            # 素材名里带一个汉字就变成 404（视频背景黑屏就是这么来的）。
            rel = urllib.parse.unquote(p[len("/assets/"):])
            fp = canonical_path(os.path.join(ASSETS_DIR, rel.replace("/", os.sep)))
            if not path_within(fp,ASSETS_DIR):
                self._send(404, "not found", "text/plain; charset=utf-8")
                return
            if os.path.exists(fp) and os.path.isfile(fp):
                ctype = "application/octet-stream"
                low = fp.lower()
                for ext, ct in ((".png", "image/png"), (".jpg", "image/jpeg"),
                                (".jpeg", "image/jpeg"), (".webp", "image/webp"),
                                (".gif", "image/gif"), (".mp4", "video/mp4"),
                                (".webm", "video/webm"), (".ico", "image/x-icon"),
                                (".svg", "image/svg+xml")):
                    if low.endswith(ext):
                        ctype = ct
                        break
                size = os.path.getsize(fp)
                rng = self.headers.get("Range") or ""
                start, end = 0, size - 1
                partial = False
                if rng.startswith("bytes="):
                    try:
                        a, _, b = rng[6:].partition("-")
                        if not a:
                            # "bytes=-500" 是「最后 500 字节」，不是「0~500」。
                            # 以前这里当成前者处理，返回的区间完全不对，
                            # 播放器一旦靠这种请求取片尾就会被带偏。
                            n = int(b)
                            start = max(0, size - n)
                            end = size - 1
                        else:
                            start = int(a)
                            end = int(b) if b else size - 1
                        end = min(end, size - 1)
                        if start < 0 or start > end:
                            raise ValueError
                        partial = True
                    except Exception:
                        partial = False
                        start, end = 0, size - 1
                self.send_response(206 if partial else 200)
                self.send_header("Content-Type", ctype)
                self.send_header("Accept-Ranges", "bytes")
                self.send_header("Cache-Control", "public, max-age=3600")
                if partial:
                    self.send_header("Content-Range",
                                     "bytes %d-%d/%d" % (start, end, size))
                self.send_header("Content-Length", str(end - start + 1))
                self.end_headers()
                # 分块往外写：4K 视频一次读进内存要 150MB+，没必要
                try:
                    with open(fp, "rb") as f:
                        if partial:
                            f.seek(start)
                        left = end - start + 1
                        while left > 0:
                            chunk = f.read(min(256 * 1024, left))
                            if not chunk:
                                break
                            self.wfile.write(chunk)
                            left -= len(chunk)
                except (BrokenPipeError, ConnectionResetError):
                    pass          # 播放器拖进度时会主动断开，正常现象
                return
        self._send(404, "not found", "text/plain; charset=utf-8")

    def _public_config(self):
        ap = self.appearance
        return {"workdir": self.cfg["workdir"],
                "extra_read": list(self.cfg.get("extra_read") or []),
                "vision_model": vision_model_name(self.cfg.get("ollama") or ""),
                "model": self.cfg["model"],
                "assets_dir": ASSETS_DIR,
                "assets": list_assets(),
                "bg_type": ap["bg_type"],
                "bg_file": ap["bg_file"],
                "icon": ap["icon"],
                "bg_dim": ap.get("bg_dim", 70),
                "sidebar_blend": ap.get("sidebar_blend", 55),
                "side_opacity": ap.get("side_opacity", 78),
                "foot_opacity": ap.get("foot_opacity", 78),
                "head_opacity": ap.get("head_opacity", 78)}

    @staticmethod
    def _reachable(url, timeout=4):
        try:
            with urllib.request.urlopen(url, timeout=timeout) as r:
                return 200 <= r.status < 400
        except Exception:
            return False

    def do_POST(self):
        p = self.path.split("?")[0]
        if p == "/api/upload_image":
            try:
                from PIL import Image, ImageOps
                n = int(self.headers.get("Content-Length") or 0)
                if not 0 < n <= 15 * 1024 * 1024:
                    raise ValueError("请选择 15MB 以内的图片")
                data = self.rfile.read(n)
                with Image.open(io.BytesIO(data)) as image:
                    if image.width * image.height > 25000000:
                        raise ValueError("图片像素过大，请先缩小到 2500 万像素以内")
                    image = ImageOps.exif_transpose(image).convert("RGB")
                    image.thumbnail((2000, 2000))
                    rel = "attachments/" + uuid.uuid4().hex + ".jpg"
                    path = safe_path(self.cfg["workdir"], rel)
                    os.makedirs(os.path.dirname(path), exist_ok=True)
                    image.save(path, format="JPEG", quality=94)
                self._send(200, json.dumps({"path": rel}, ensure_ascii=False), "application/json; charset=utf-8")
            except (OSError, ValueError, Image.DecompressionBombError) as e:
                self._send(400, json.dumps({"error": str(e)}, ensure_ascii=False), "application/json; charset=utf-8")
            return

        if p == "/api/appearance":
            try:
                req = self._json_body()
            except Exception as e:
                self._send(400, json.dumps({"error": str(e)}), "application/json")
                return
            bg_type = str(req.get("bg_type", self.appearance["bg_type"]))
            bg_file = str(req.get("bg_file", self.appearance["bg_file"]))
            icon = str(req.get("icon", self.appearance["icon"]))
            if bg_type not in ("none", "image", "video"):
                self._send(400, '{"error":"bg_type 只能是 none/image/video"}',
                           "application/json")
                return
            try:
                bg_dim = int(req.get("bg_dim", self.appearance.get("bg_dim", 70)))
            except (TypeError, ValueError):
                bg_dim = self.appearance.get("bg_dim", 70)
            bg_dim = max(0, min(100, bg_dim))
            def pct(key, default):
                try:
                    return max(0, min(100, int(req.get(key, default))))
                except (TypeError, ValueError):
                    return default

            side = pct("sidebar_blend", self.appearance.get("sidebar_blend", 55))
            side_op = pct("side_opacity", self.appearance.get("side_opacity", 78))
            foot_op = pct("foot_opacity", self.appearance.get("foot_opacity", 78))
            head_op = pct("head_opacity", self.appearance.get("head_opacity", 78))
            for rel in (bg_file, icon):
                if rel and not os.path.isfile(os.path.join(HERE, rel.replace("/", os.sep))):
                    self._send(400, json.dumps({"error": "素材不存在：%s" % rel},
                                               ensure_ascii=False).encode("utf-8"),
                               "application/json; charset=utf-8")
                    return
            if bg_type == "none":
                bg_file = ""
            # 注意：必须写到「类」上。每次请求都是一个新 Handler 实例，
            # 写成 self.appearance 只在这个请求里有效，下一个请求又会读回启动时的旧值。
            type(self).appearance = {"bg_type": bg_type, "bg_file": bg_file,
                                     "icon": icon, "bg_dim": bg_dim,
                                     "sidebar_blend": side,
                                     "side_opacity": side_op,
                                     "foot_opacity": foot_op,
                                     "head_opacity": head_op,
                                     # extra_read 必须带着：以前这里重建字典时漏了它，
                                     # 结果每次改背景都会把"额外只读目录"清空。
                                     "extra_read": list(self.appearance.get("extra_read") or [])}
            try:
                save_appearance(self.appearance)
            except Exception as e:
                sys.stderr.write("[外观] 保存失败：%s\n" % e)
            self._send(200, json.dumps(self._public_config(), ensure_ascii=False),
                       "application/json; charset=utf-8")
            return

        if p == "/api/reminders":
            # 前端「定时提醒」面板用：加 / 删 / 立刻试听
            try:
                req = self._json_body()
            except Exception as e:
                self._send(400, json.dumps({"error": str(e)}), "application/json")
                return
            act = str(req.get("action") or "list").lower()
            if act == "add":
                msg = reminder_add(req.get("text"), req.get("at"),
                                   req.get("repeat") or "daily",
                                   req.get("days") or [], req.get("date") or "")
            elif act in ("delete", "del"):
                msg = reminder_del(req.get("keyword") or req.get("id") or req.get("text"))
            elif act == "toggle":
                items = load_reminders()
                for it in items:
                    if str(it.get("id")) == str(req.get("id")):
                        it["enabled"] = not it.get("enabled", True)
                save_reminders(items)
                msg = "已切换开关"
            elif act == "test":      # 立刻念一条，方便试音色/音量
                ok, note = speak_out_loud(str(req.get("text") or "这是一条测试提醒"))
                msg = "念出来了" if ok else note
            else:
                msg = reminder_list()
            self._send(200, json.dumps(
                {"ok": bool(msg) and "[工具出错]" not in msg, "message": msg,
                 "items": load_reminders(), "fired": load_fired(20)},
                ensure_ascii=False), "application/json; charset=utf-8")
            return

        if p == "/api/habits":
            # 前端用它编辑「习惯」文件（整份覆盖保存）；读取走 GET /api/habits
            try:
                req = self._json_body()
            except Exception as e:
                self._send(400, json.dumps({"error": str(e)}), "application/json")
                return
            text = str(req.get("text") or "")
            if len(text) > 20000:
                self._send(400, '{"error":"习惯文件太长了，控制在 2 万字以内"}',
                           "application/json")
                return
            try:
                save_habits(text if text.strip() else HABITS_HEADER)
            except Exception as e:
                self._send(500, json.dumps({"error": "写文件失败：%s" % e},
                                           ensure_ascii=False).encode("utf-8"),
                           "application/json; charset=utf-8")
                return
            self._send(200, json.dumps({"ok": True, "file": HABITS_FILE},
                                       ensure_ascii=False), "application/json; charset=utf-8")
            return

        if p == "/api/workdir":
            try:
                req = self._json_body()
            except Exception as e:
                self._send(400, json.dumps({"error": str(e)}), "application/json")
                return
            d = os.path.abspath(os.path.expanduser(str(req.get("path") or "")))
            if not os.path.isdir(d):
                self._send(400, json.dumps({"error": "这个目录不存在：%s" % d},
                                           ensure_ascii=False).encode("utf-8"),
                           "application/json; charset=utf-8")
                return
            self.cfg["workdir"] = d
            self._send(200, json.dumps({"workdir": d}, ensure_ascii=False),
                       "application/json; charset=utf-8")
            return

        if p == "/api/readdirs":
            try:
                req = self._json_body()
            except Exception as e:
                self._send(400, json.dumps({"error": str(e)}), "application/json")
                return
            dirs, bad = [], []
            for part in re.split(r"[;\n]", str(req.get("dirs") or "")):
                part = part.strip().strip('"')
                if not part:
                    continue
                d = os.path.abspath(os.path.expanduser(part))
                (dirs if os.path.isdir(d) else bad).append(d)
            if bad:
                self._send(400, json.dumps({"error": "这些目录不存在：%s" % "；".join(bad[:3])},
                                           ensure_ascii=False).encode("utf-8"),
                           "application/json; charset=utf-8")
                return
            self.cfg["extra_read"] = dirs
            self.appearance["extra_read"] = dirs
            try:
                save_appearance(self.appearance)
            except Exception as e:
                sys.stderr.write("[只读目录] 保存失败：%s\n" % e)
            self._send(200, json.dumps(self._public_config(), ensure_ascii=False),
                       "application/json; charset=utf-8")
            return

        if p == "/api/import":
            try:
                req = self._json_body()
            except Exception as e:
                self._send(400, json.dumps({"error": str(e)}), "application/json")
                return
            src = os.path.abspath(os.path.expanduser(str(req.get("src") or "").strip('"')))
            use_as = str(req.get("use_as") or "")
            if not os.path.isfile(src):
                self._send(400, json.dumps({"error": "找不到这个文件：%s" % src},
                                           ensure_ascii=False).encode("utf-8"),
                           "application/json; charset=utf-8")
                return
            ext = os.path.splitext(src)[1].lower()
            if ext not in IMAGE_EXT + VIDEO_EXT + (".ico", ".svg"):
                self._send(400, json.dumps(
                    {"error": "不支持的格式 %s（图片 jpg/png/webp/gif，视频 mp4/webm，图标 ico/svg）"
                     % ext}, ensure_ascii=False).encode("utf-8"),
                    "application/json; charset=utf-8")
                return
            size = os.path.getsize(src)
            if size > 400 * 1024 * 1024:
                self._send(400, '{"error":"文件超过 400MB，太大了"}',
                           "application/json")
                return
            os.makedirs(ASSETS_DIR, exist_ok=True)
            base = os.path.basename(src)
            dst = os.path.join(ASSETS_DIR, base)
            i = 1
            while os.path.exists(dst) and os.path.abspath(dst) != src:
                stem, e = os.path.splitext(base)
                dst = os.path.join(ASSETS_DIR, "%s_%d%s" % (stem, i, e))
                i += 1
            if os.path.abspath(dst) != src:
                import shutil
                shutil.copy2(src, dst)
            rel = "assets/" + os.path.basename(dst)
            if use_as == "bg":
                kind = asset_kind(rel)
                if kind in ("image", "video"):
                    self.appearance["bg_type"] = kind
                    self.appearance["bg_file"] = rel
            elif use_as == "icon":
                self.appearance["icon"] = rel
            try:
                save_appearance(self.appearance)
            except Exception:
                pass
            self._send(200, json.dumps(
                {"ok": True, "path": rel, "size": size,
                 "config": self._public_config()}, ensure_ascii=False),
                "application/json; charset=utf-8")
            return

        if p == "/api/agent":
            try:
                req = self._json_body()
            except Exception as e:
                self._send(400, json.dumps({"error": str(e)}), "application/json")
                return
            raw_messages = req.get("messages") or []
            if not isinstance(raw_messages,list) or len(raw_messages)>1000:
                self._send(400,'{"error":"invalid messages"}','application/json');return
            cleaned=[]
            for message in raw_messages:
                if (not isinstance(message,dict) or message.get('role') not in ('user','assistant')
                        or not isinstance(message.get('content',''),str)):
                    self._send(400,'{"error":"invalid message role or content"}','application/json');return
                item={'role':message['role'],'content':message.get('content','')}
                if message.get('images'):
                    if not isinstance(message['images'],list) or not all(isinstance(p,str) for p in message['images']):
                        self._send(400,'{"error":"invalid images"}','application/json');return
                    item['images']=message['images'][:3]
                cleaned.append(item)
            raw_messages=cleaned
            workdir = self.cfg["workdir"]
            base = self.cfg["ollama"]

            last_user = ""
            attached_images = []
            for m in reversed(raw_messages):
                if isinstance(m, dict) and m.get("role") == "user":
                    last_user = m.get("content") or ""
                    attached_images = m.get("images") or []
                    break
            if not isinstance(attached_images, list):
                attached_images = []
            if not attached_images and re.search(r"图中|图里|图上|这张|刚才那张|上面那张", last_user):
                for previous in reversed(raw_messages[:-1]):
                    if isinstance(previous, dict) and previous.get("role") == "user" and isinstance(previous.get("images"), list) and previous["images"]:
                        attached_images = previous["images"]
                        break
            character_memory = ruanmei_lore_for_prompt(last_user)
            turn_tools = select_tools(last_user, raw_messages)
            turn_num_ctx = LLM_NUM_CTX if turn_tools else CHAT_NUM_CTX

            # 动态资料必须和完整人设合并成“一条” system。Ollama 遇到额外
            # system 消息时会覆盖 Modelfile 里的 SYSTEM，分开插会让人设消失。
            dynamic_parts = []
            casual_guidance = casual_reply_guidance(raw_messages, last_user)
            if casual_guidance:
                dynamic_parts.append(casual_guidance)
            if asks_for_realtime_fact(last_user):
                dynamic_parts.append(
                    "【能力边界】本轮没有天气、气温或空气质量工具。不能确认时直接说明"
                    "「没有接入天气程序」，不要用常识、猜测或角色设定补出一个天气结论。"
                )
            habits = habits_for_prompt(last_user)
            if habits:
                taste = music_taste_brief()
                dynamic_parts.append(
                    "【主人的长期偏好】\n"
                    "主人以前明确交代过的习惯（直接照办，不用每次再问，"
                    "也不要主动把这些念给他听）。\n"
                    "这里面既有干活时的偏好，也有生活习惯（作息、吃饭、出门、健康、"
                    "花钱、娱乐）。他在日常对话里提到「我一般…」「我习惯…」这类"
                    "面向以后的生活安排时，用 remember 记到「生活习惯」下面对应的小节里。\n"
                    + ("" if not habits_life_empty() else
                       "注意：「生活习惯」那几节现在还是空的。他要你排日程、规划表、"
                       "作息安排时，先问清几件事（几点起、通勤/路上多久、每天固定必须做的、"
                       "晚上几点想停）再排；不要凭空编一份通用模板糊弄他。\n")
                    + (taste + "\n" if taste else "")
                    + habits)
            # 唤醒词：他是直接点名叫你，别当成"他在自称亲爱的"，正常答应并按后面的要求做
            if any(WAKE_WORD in str(m.get("content") or "")
                   for m in raw_messages if m.get("role") == "user"):
                dynamic_parts.append(
                    "（这一轮主人用「%s」叫你了 —— 那是在直呼你、点你的名，"
                    "答应一声就好，然后照他后面的要求做。别把它理解成他在自称。）"
                    % WAKE_WORD)
            if character_memory:
                dynamic_parts.append(character_memory)
            setting = ruanmei_setting_text()
            system_text = "\n\n".join(([setting] if setting else []) + dynamic_parts)

            # 历史预算必须扣掉实际人设和本轮工具 schema，而不是拍一个固定值。
            tools_json = json.dumps(turn_tools, ensure_ascii=False, separators=(",", ":"))
            fixed_tokens = approx_tokens(system_text) + approx_tokens(tools_json)
            history_budget = max(400, turn_num_ctx - fixed_tokens - 1200)
            messages, dropped = trim_history(raw_messages, history_budget)
            if dropped:
                print("[上下文] 省略较早的 %d 条消息（预算约 %d token，工具 %d 个）"
                      % (dropped, history_budget, len(turn_tools)))
                system_text += ("\n\n（较早的 %d 条对话已为节省上下文省略；"
                                "若其中可能有仍有效的约束，回答前先向主人确认。）" % dropped)
            if system_text:
                messages = [{"role": "system", "content": system_text}] + [
                    m for m in messages if m.get("role") != "system"
                ]

            self.send_response(200)
            self.send_header("Content-Type", "application/x-ndjson")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()

            def emit(obj):
                self.wfile.write((json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8"))
                self.wfile.flush()

            if dropped:
                emit({"type": "note",
                      "content": "上下文较长，已省略较早的 %d 条消息" % dropped})

            try:
                nudged = False
                nudged_action = 0
                nudged_casual = False
                acted = False          # 这轮有没有真的动过手（写文件/装东西/出成品）
                if attached_images:
                    for image_path in attached_images[:3]:
                        args = {"path": str(image_path), "question": last_user}
                        emit({"type": "tool", "name": "see_image", "args": args})
                        result = exec_tool("see_image", args, workdir,
                                           self.cfg.get("extra_read") or (), base, last_user)
                        emit({"type": "tool_result", "name": "see_image", "result": result[:6000]})
                        marker = re.search(r"\[画面描述 · [^\n]+\]\n", result)
                        answer = result[marker.end():] if marker else (
                            "图中识别到的文字：\n" + result.split("[结果]\n", 1)[1]
                            if "[结果]\n" in result else result)
                        emit({"type": "text", "content": answer + "\n"})
                    emit({"type": "done"})
                    return
                music_action = parse_music_command(last_user)
                if music_action:
                    emit({"type": "tool", "name": "music", "args": {"action": music_action}})
                    result = music(music_action)
                    emit({"type": "tool_result", "name": "music", "result": result})
                    emit({"type": "text", "content": result.removeprefix("照这句说：").strip()})
                    emit({"type": "done"})
                    return
                # 「播放我喜欢的歌单 / 放一首周杰伦的晴天」：服务端直接点播，不叫模型。
                # 这样既快（0 token），也不会让 4B 模型编一句"好的，我将为您播放…"。
                spec = parse_music_request(last_user)
                if spec:
                    kind, query, title = spec
                    if kind == "playlist" and query in ("我喜欢", "最近播放"):
                        emit({"type": "text",
                              "content": "我先按你的听歌记录找找，马上给你放一首。"})
                    emit({"type": "note",
                          "content": "按%s点播：%s" %
                                     ("歌单" if kind == "playlist" else "歌名", query)})
                    answer = qqmusic_play(query, kind, title)
                    if kind == "playlist" and query in ("我喜欢", "最近播放"):
                        answer = answer.removeprefix("照这句说：")
                        if not answer.startswith(("这次没能", "我还没")):
                            answer = "这首是刚从你的听歌记录里挑的。" + answer
                    emit({"type": "text",
                          "content": answer.removeprefix("照这句说：")})
                    emit({"type": "done"})
                    return
                for step in range(8):        # 最多 8 轮工具调用
                    resp = ollama_chat(base, {
                        "model": self.cfg["model"],
                        "messages": messages,
                        **({"tools": turn_tools} if turn_tools else {}),
                        "stream": False,
                        "think": bool(req.get("think", False)),
                        # 工具调用的可靠性对这个很敏感：4B 模型在 0.7 时经常"只说要做什么、
                        # 却不真的调工具"。实测降到 0.4 明显稳定（见 README 的 agent 那节）。
                        "options": {"temperature": 0.4, "num_ctx": turn_num_ctx},
                    })
                    print("[推理] ctx=%d load=%.2fs prompt=%.2fs reply=%.2fs tokens=%s" % (
                        turn_num_ctx, resp.get("load_duration", 0) / 1e9,
                        resp.get("prompt_eval_duration", 0) / 1e9,
                        resp.get("eval_duration", 0) / 1e9,
                        resp.get("eval_count", 0)))
                    msg = resp.get("message", {})
                    calls = msg.get("tool_calls") or []
                    if not calls:
                        # 该查不查：给它一次机会，退回去让它先看实际情况
                        if not nudged and step == 0 and not character_memory:
                            nudge = needs_look(messages, last_user)
                            if nudge:
                                nudged = True
                                emit({"type": "note", "content": "它想直接回答，被退回去先查实际情况"})
                                messages.append({"role": "user", "content": nudge})
                                continue
                        text = msg.get("content", "") or ""
                        # 查了但没动手：带"修"意的问题用建议收尾，就退回去一次，
                        # 逼它二选一 —— 自己做完，或者明确说清哪一步只能用户做。
                        # 最多退回两次：一次常常不够（实测退回一次之后它还会再给一遍建议），
                        # 但也不能无限退，否则会卡在那儿反复自我说服。
                        if (nudged_action < 2 and not acted and step < 6
                                and wants_fix(last_user) and looks_like_advice(text)):
                            nudged_action += 1
                            emit({"type": "note",
                                  "content": "它想用「你可以试试…」收尾，第 %d 次退回：要么动手，要么说清卡点"
                                             % nudged_action})
                            messages.append(msg)
                            messages.append({"role": "user", "content": ACTION_NUDGE})
                            continue
                        casual_issue = casual_reply_issue(last_user, text)
                        if casual_issue and not nudged_casual and step < 3:
                            nudged_casual = True
                            emit({"type": "note",
                                  "content": "检测到日常回复%s，让它按阮·梅的人设重写一次"
                                             % casual_issue})
                            messages.append(msg)
                            messages.append({"role": "user", "content": CASUAL_REWRITE_NUDGE})
                            continue
                        if casual_issue:
                            text = fallback_casual_reply(last_user)
                        emit({"type": "text", "content": text})
                        break
                    messages.append(msg)
                    for tc in calls:
                        fn = tc.get("function", {})
                        name = fn.get("name")
                        args = fn.get("arguments") or {}
                        if isinstance(args, str):
                            try:
                                args = json.loads(args)
                            except Exception:
                                args = {}
                        emit({"type": "tool", "name": name, "args": args})
                        if name in ACT_TOOLS:
                            acted = True
                        result = exec_tool(name, args, workdir,
                                           self.cfg.get("extra_read") or (),
                                           self.cfg.get("ollama") or "",
                                           last_user)
                        emit({"type": "tool_result", "name": name,
                              "result": result[:3000]})
                        messages.append({"role": "tool",
                                         "content": compact_tool_result(name, result)})
                else:
                    emit({"type": "text", "content": "（工具调用已达上限 8 轮，先停在这里）"})
            except Exception as e:
                emit({"type": "error", "content": str(e)[:400]})
            emit({"type": "done"})
            return

        if p == "/api/asr":
            # 语音输入：把浏览器录到的音频转给本地识别服务（9882），拿回文字
            n = int(self.headers.get("Content-Length") or 0)
            data = self.rfile.read(n) if n > 0 else b""
            if not data:
                self._send(400, '{"error":"没有收到音频"}', "application/json")
                return
            fmt = "webm"
            q = self.path.partition("?")[2]
            for kv in q.split("&"):
                if kv.startswith("format="):
                    fmt = kv.split("=", 1)[1]
            try:
                req = urllib.request.Request(
                    self.cfg["asr"].rstrip("/") + "/asr?format=" + fmt,
                    data=data,
                    headers={"Content-Type": "application/octet-stream"},
                    method="POST")
                with urllib.request.urlopen(req, timeout=600) as up:
                    self._send(200, up.read(), "application/json; charset=utf-8")
            except Exception as e:
                self._send(502, json.dumps(
                    {"error": "识别服务没响应（检查 9882 是否在跑）：%s" % str(e)[:150]},
                    ensure_ascii=False).encode("utf-8"),
                    "application/json; charset=utf-8")
            return

        if p == "/api/tts":
            try:
                req = self._json_body()
            except Exception as e:
                self._send(400, json.dumps({"error": str(e)}), "application/json")
                return
            text = (req.get("text") or "").strip()
            if not text:
                self._send(400, '{"error":"text 为空"}', "application/json")
                return
            # 允许前端指定语气（音色名写法 ruanmei:warm），但只放行以配置音色开头的名字，
            # 免得请求体里随便塞一个名字去打后端
            base_voice = self.cfg["voice"]
            want = (req.get("voice") or "").strip()
            voice = want if (want == base_voice
                             or want.startswith(base_voice + ":")) else base_voice
            # 先按请求的语气合成；万一那个语气没有配置（或后端不认），自动回落到默认语气，
            # 保证"一定有声音"比"严格报错"更重要。
            tries = [voice] + ([base_voice] if voice != base_voice else [])
            last_err = None
            for v in tries:
                try:
                    r = urllib.request.Request(
                        self.cfg["tts"].rstrip("/") + "/v1/audio/speech",
                        data=json.dumps({"input": text, "voice": v,
                                         "response_format": "wav"},
                                        ensure_ascii=False).encode("utf-8"),
                        headers={"Content-Type": "application/json"}, method="POST")
                    with urllib.request.urlopen(r, timeout=900) as up:
                        self._send(200, up.read(), up.headers.get("Content-Type", "audio/wav"))
                    return
                except Exception as e:
                    last_err = e
                    if v != voice:
                        sys.stderr.write("[语气] %s 失败，回落到默认语气\n" % voice)
            self._send(502, json.dumps({"error": str(last_err)[:200]},
                                       ensure_ascii=False).encode("utf-8"),
                       "application/json; charset=utf-8")
            return

        self._send(404, "not found", "text/plain; charset=utf-8")


def main():
    # 后台启动（输出重定向到日志文件）时，stdout 默认是全缓冲的，
    # 启动横幅要等缓冲区满了才落盘，看着像"卡住了"。改成按行刷。
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="梅梅 本地 Agent")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=7788)
    ap.add_argument("--model", default="ruanmei")
    ap.add_argument("--voice", default="ruanmei")
    ap.add_argument("--ollama", default="http://127.0.0.1:11434")
    ap.add_argument("--tts", default="http://127.0.0.1:9881")
    ap.add_argument("--asr", default="http://127.0.0.1:9882",
                    help="本地语音识别服务地址（voice/asr_server.py）")
    ap.add_argument("--workdir", default=os.getcwd(),
                    help="agent 能操作的工作目录（写文件/执行命令都限制在这里）")
    ap.add_argument("--extra-read", default="",
                    help="额外允许【读取】的目录，分号分隔（图片、素材放在这些地方）")
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()

    wd = os.path.abspath(args.workdir)
    if not os.path.isdir(wd):
        sys.exit("[错误] 工作目录不存在：%s" % wd)

    extra = [os.path.abspath(p.strip()) for p in re.split(r"[;\n]", args.extra_read)
             if p.strip() and os.path.isdir(os.path.abspath(p.strip()))]
    if not extra:
        # 命令行没给就从设置文件里读（界面里改过的会被记住）
        extra = [d for d in (load_appearance().get("extra_read") or [])
                 if os.path.isdir(d)]
    Handler.cfg = {"model": args.model, "voice": args.voice,
                   "ollama": args.ollama, "tts": args.tts, "asr": args.asr,
                   "workdir": wd,
                   "extra_read": extra}
    CFG.update(Handler.cfg)            # 定时提醒线程要用 tts / voice
    threading.Thread(target=reminder_loop, daemon=True).start()
    threading.Thread(target=music_log_loop, daemon=True).start()   # 顺手记听歌记录
    Handler.appearance = load_appearance()
    os.makedirs(ASSETS_DIR, exist_ok=True)
    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    print("=" * 60)
    print("  梅梅 本地 Agent")
    print("=" * 60)
    print("  界面      http://%s:%d" % (args.host, args.port))
    print("  模型      %s @ %s" % (args.model, args.ollama))
    print("  语音      %s @ %s" % (args.voice, args.tts))
    print("  工作目录  %s" % wd)
    if extra:
        print("  只读目录  %s" % "；".join(extra))
    print("  素材目录  %s" % ASSETS_DIR)
    ap = Handler.appearance
    print("  视觉      %s" % (vision_model_name(args.ollama) or "未安装（只能识别图上文字）"))
    print("  外观      背景=%s%s  图标=%s" % (
        ap["bg_type"], (" (" + ap["bg_file"] + ")") if ap["bg_file"] else "",
        ap["icon"] or "默认"))
    print("")
    print("  agent 只能操作工作目录内的文件，越界会被拒绝。")
    print("  换背景/图标：素材丢进 app\\assets\\，或在界面右上角「外观」里现场改。")
    print("=" * 60)

    if not args.no_browser:
        # 注意：threading / time 已经在文件顶部导入了。这里再写一次局部 import 的话，
        # 整个 main() 里的 threading 都会变成"局部变量"，前面用到它就 UnboundLocalError
        # （实测就是这么崩的）。
        import webbrowser

        def _open():
            time.sleep(1.5)
            webbrowser.open("http://%s:%d" % (args.host, args.port))
        threading.Thread(target=_open, daemon=True).start()

    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n[退出]")


if __name__ == "__main__":
    main()
