"""
给梅梅用的文档 / 表格 / 演示 / 视频工具。

设计原则：让 4B 的小模型只负责它最擅长的部分 —— 输出 Markdown 文本，
排版交给这里的代码。之前试过让它自己写 python-pptx 脚本再跑，
结果是脚本经常跑不起来（少 import、缩进错、路径是编的），
所以这里把「写脚本」这一步彻底去掉：一句话 -> 一次工具调用 -> 一个真文件。

对外只暴露四个函数，agent_server.py 直接调：
    build_pptx(path, content, title="", subtitle="")
    build_docx(path, content, title="")
    build_xlsx(path, content)
    edit_video(action, inputs, output, **opt)

返回的字符串**第一行**是"照这句说：..."，因为小模型有时会把整段工具输出
念给用户听，第一行给结论最稳妥。
"""

import os
import re
import shutil
import subprocess
import tempfile


def run_hidden(args, **kwargs):
    kwargs["creationflags"] = kwargs.get("creationflags", 0) | getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return subprocess.run(args, **kwargs)

# ---------------------------------------------------------------- 公共小工具

# 界面一个色系：青蓝偏绿
ACCENT_HEX = "2FB89B"
ACCENT_DARK = "1C7F6B"
FONT = "微软雅黑"

# 视频转换用的 ffmpeg。优先用装好的完整版，退回 PATH 里的。
FFMPEG_CANDIDATES = [
    r"G:\ai\ffmpeg\ffmpeg-9.0.2-essentials_build\bin\ffmpeg.exe",
    r"C:\ffmpeg\bin\ffmpeg.exe",
]


def find_ffmpeg():
    for p in FFMPEG_CANDIDATES:
        if os.path.isfile(p):
            return p
    for name in ("ffmpeg.exe", "ffmpeg"):
        p = shutil.which(name)
        if p:
            return p
    return ""


FFMPEG = find_ffmpeg()
FFPROBE = os.path.join(os.path.dirname(FFMPEG), "ffprobe.exe") if FFMPEG else ""


def ensure_ext(path, ext):
    """模型经常忘了写扩展名（传个「汇报」进来），这里补上。"""
    if not path.lower().endswith(ext):
        path = path + ext
    return path


def ensure_parent(path):
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)


def human_size(path):
    n = os.path.getsize(path)
    return ("%.1f KB" % (n / 1024)) if n < 1024 * 1024 else ("%.1f MB" % (n / 1048576.0))


def parse_md(content):
    """
    把 Markdown 粗切成页 / 段。
    认这几种写法：
        # 标题            -> 新的一页，标题行
        ---               -> 新的一页，无标题
        - 要点 / * 要点    -> 列表项
        1. 要点            -> 列表项（有序）
        其它非空行         -> 普通段落（每页第一句会当成副标题）
    """
    pages = []
    cur = None

    def new_page(title=""):
        nonlocal cur
        cur = {"title": title.strip(), "sub": "", "items": [], "texts": []}
        pages.append(cur)

    for raw in (content or "").replace("\r\n", "\n").split("\n"):
        line = raw.rstrip()
        s = line.strip()
        if not s:
            continue
        if re.match(r"^[-*_=]{3,}$", s):          # --- 分页
            new_page()
            continue
        if s.startswith("#"):
            new_page(s.lstrip("#").strip())
            continue
        if cur is None:
            new_page()
        m = re.match(r"^\s*(?:[-*+•]|\d+[.)])\s+(.*)$", line)
        if m:
            cur["items"].append(m.group(1).strip())
            continue
        if not cur["items"] and not cur["texts"] and not cur["sub"]:
            cur["sub"] = s
        else:
            cur["texts"].append(s)
    return [p for p in pages if p["title"] or p["sub"] or p["items"] or p["texts"]]


def clean_inline(text):
    """去掉行内 Markdown 记号，只留能看的文字。"""
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"(?<!\*)\*(?!\s)(.+?)(?<!\s)\*(?!\*)", r"\1", text)
    text = re.sub(r"`(.+?)`", r"\1", text)
    text = re.sub(r"\[(.+?)\]\(.+?\)", r"\1", text)
    return text.strip()


# ---------------------------------------------------------------- PPT

def build_pptx(path, content, title="", subtitle=""):
    from lxml import etree
    from pptx import Presentation
    from pptx.dml.color import RGBColor
    from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
    from pptx.oxml.ns import qn
    from pptx.util import Emu, Inches, Pt

    path = ensure_ext(path, ".pptx")
    ensure_parent(path)

    pages = parse_md(content)
    if title:
        if not pages:
            pages = [{"title": "", "sub": "", "items": [], "texts": []}]
        # 标题行没写进 # 里时，用第一个非空行当标题
        if not pages[0]["title"]:
            pages[0]["title"] = title
    if not pages:
        return "[工具出错] content 是空的，没东西可做。先写 # 标题 和 - 要点 再调用。"

    accent = RGBColor.from_string(ACCENT_HEX)
    dark = RGBColor.from_string(ACCENT_DARK)
    ink = RGBColor.from_string("1F2933")
    muted = RGBColor.from_string("7B8794")

    def set_font(run, size, bold=False, color=ink, name=FONT):
        run.font.name = name
        run.font.size = Pt(size)
        run.font.bold = bold
        run.font.color.rgb = color
        rPr = run._r.get_or_add_rPr()
        for tag in ("a:latin", "a:ea", "a:cs"):
            el = rPr.find(qn(tag))
            if el is None:
                el = etree.SubElement(rPr, qn(tag))
            el.set("typeface", name)

    def textbox(slide, x, y, w, h):
        tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
        tf = tb.text_frame
        tf.word_wrap = True
        tf.margin_left = tf.margin_right = 0
        tf.margin_top = tf.margin_bottom = 0
        return tf

    def rect(slide, x, y, w, h, color):
        from pptx.enum.shapes import MSO_SHAPE
        sh = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(x), Inches(y),
                                    Inches(w), Inches(h))
        sh.fill.solid()
        sh.fill.fore_color.rgb = color
        sh.line.fill.background()
        sh.shadow.inherit = False
        return sh

    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    blank = prs.slide_layouts[6]

    # ---- 封面
    # 什么时候要封面：调用方给了标题/副标题，或者第一段本来就是封面写法
    # （# 标题 后面跟一行副标题、没有要点）。反过来，如果第一段直接就是
    # "# 小节标题 + - 要点"，那就别硬加封面 —— 否则同一句话会出现两次。
    first = pages[0]
    want_cover = bool(title or subtitle) or not (first["items"] or first["texts"])
    body_pages = []
    if want_cover:
        s = prs.slides.add_slide(blank)
        rect(s, 0, 0, 0.32, 7.5, accent)
        tf = textbox(s, 1.25, 2.35, 11.0, 1.6)
        p = tf.paragraphs[0]
        r = p.add_run()
        r.text = clean_inline(title or first["title"] or "演示文稿")
        set_font(r, 40, bold=True, color=ink)
        sub = clean_inline(subtitle or first["sub"] or "")
        if sub:
            tf2 = textbox(s, 1.28, 3.95, 10.5, 0.7)
            r2 = tf2.paragraphs[0].add_run()
            r2.text = sub
            set_font(r2, 17, color=muted)
        tf3 = textbox(s, 1.28, 6.5, 8.0, 0.4)
        r3 = tf3.paragraphs[0].add_run()
        r3.text = "梅梅 · 本地生成"
        set_font(r3, 11, color=muted)
        # 第一段自己的要点也带上（如果它既当封面又有要点）
        if first["items"] or first["texts"]:
            body_pages.append({"title": first["title"] or (title or "概述"),
                               "sub": "", "items": first["items"], "texts": first["texts"]})
        body_pages += [dict(p) for p in pages[1:]]
    else:
        body_pages = [dict(p) for p in pages]

    # ---- 正文：一页超过 8 条就自动拆成两页，免得挤成一坨
    made = []
    for pg in body_pages:
        bullets = [clean_inline(x) for x in pg["items"]] or \
                  [clean_inline(x) for x in pg["texts"]]
        if not bullets:
            continue
        chunks = [bullets[i:i + 8] for i in range(0, len(bullets), 8)]
        for ci, chunk in enumerate(chunks):
            s = prs.slides.add_slide(blank)
            rect(s, 0, 0, 0.22, 7.5, accent)
            head = pg["title"] or (title or "内容")
            if len(chunks) > 1:
                head = "%s（%d/%d）" % (head, ci + 1, len(chunks))
            tf = textbox(s, 1.0, 0.62, 11.4, 0.9)
            r = tf.paragraphs[0].add_run()
            r.text = head
            set_font(r, 27, bold=True, color=dark)
            rect(s, 1.0, 1.55, 1.5, 0.045, accent)

            size = 19 if sum(len(b) for b in chunk) < 260 else 16.5
            tf = textbox(s, 1.0, 1.95, 11.3, 4.9)
            for i, b in enumerate(chunk):
                p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
                p.space_after = Pt(11)
                p.line_spacing = 1.18
                r = p.add_run()
                r.text = "·  " + b
                set_font(r, size)
            made.append(head)

    if not made:
        return "[工具出错] 只有标题没有正文。正文要写成 - 要点 的样子。"

    prs.save(path)
    head = "照这句说：演示文稿做好了，%d 页（含封面），文件在 %s。" % (
        len(prs.slides._sldIdLst), os.path.basename(path))
    lines = [head, "绝对路径：%s" % path, "大小：%s" % human_size(path), "页面："]
    lines += ["  · " + t for t in made]
    return "\n".join(lines)

# ---------------------------------------------------------------- 上课日规划表

def _parse_slots(text, default_minutes=120):
    """把「10:30-12:30 上课」/「15:30 上课」这类行解析成 (开始分, 结束分, 名称, 备注)。"""
    out = []
    for raw in str(text or "").replace("；", "\n").replace(";", "\n").split("\n"):
        line = raw.strip().lstrip("-·* ").strip()
        if not line:
            continue
        m = re.match(r"^(\d{1,2}\s*[:：点]\s*\d{0,2})\s*[-–~—到至]{1,2}\s*"
                     r"(\d{1,2}\s*[:：点]\s*\d{0,2})\s*(.*)$", line)
        if m:
            a, b = _hm(m.group(1)), _hm(m.group(2))
            if a and b:
                out.append((_mins(a), _mins(b), (m.group(3) or "上课").strip(), ""))
            continue
        m = re.match(r"^(\d{1,2}\s*[:：点]\s*\d{0,2})\s*(.*)$", line)
        if m and _hm(m.group(1)):
            a = _mins(_hm(m.group(1)))
            out.append((a, a + default_minutes, (m.group(2) or "上课").strip(), ""))
    return sorted(out, key=lambda x: x[0])


def _write_plan(path, title, rows, notes=None, header=("时段", "安排", "备注")):
    """把 (开始分, 结束分, 安排, 备注) 列表写成一个好看的 xlsx。"""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill

    path = ensure_ext(path, ".xlsx")
    ensure_parent(path)
    wb = Workbook()
    ws = wb.active
    ws.title = "规划"
    head_font = Font(name=FONT, bold=True, color="FFFFFF")
    head_fill = PatternFill("solid", fgColor=ACCENT_DARK)
    body_font = Font(name=FONT)
    time_font = Font(name=FONT, bold=True)

    ws.append([title])
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=3)
    c = ws.cell(row=1, column=1)
    c.font = Font(name=FONT, bold=True, size=14)
    c.alignment = Alignment(horizontal="center", vertical="center")

    ws.append(list(header))
    hdr = ws.max_row
    for col in range(1, 4):
        cc = ws.cell(row=hdr, column=col)
        cc.font = head_font
        cc.fill = head_fill
        cc.alignment = Alignment(horizontal="center", vertical="center")

    for a, b, what, note in rows:
        span = "%s–%s" % (_fmt(a), _fmt(b)) if a != b else _fmt(a)
        ws.append([span, what, note])
        r = ws.max_row
        ws.cell(row=r, column=1).font = time_font
        ws.cell(row=r, column=2).font = body_font
        ws.cell(row=r, column=3).font = body_font
        ws.cell(row=r, column=3).alignment = Alignment(wrap_text=True, vertical="center")

    if notes:
        ws.append([])
        ws.append(["随时要做的", "\n".join(notes), ""])
        ws.cell(row=ws.max_row, column=1).font = time_font
        ws.cell(row=ws.max_row, column=2).alignment = Alignment(wrap_text=True)

    ws.column_dimensions["A"].width = 14
    ws.column_dimensions["B"].width = 34
    ws.column_dimensions["C"].width = 40
    ws.freeze_panes = "A%d" % (hdr + 1)
    wb.save(path)
    return path


def build_study_plan(path, classes, wake_before="30", lunch="150", dinner="30",
                     sleep_range="01:00-04:00", extras="", title="上课日规划"):
    """
    上课日的规划表 —— 和 build_dayplan 的"上班族模板"是两回事。

    学生的一天不是"起床→通勤→朝九晚五"，而是"课表 + 课与课之间的空档 + 大块自由时间"。
    实测按上班族模板套她的作息，出来的表完全不对（12:00 午饭、13:30 上班这种硬编码时间
    跟她 12:30 下课、15:30 才上课的节奏对不上）。所以按课表来排：
      起床（第一节课 - wake_before）→ 上午课 → 午饭+午睡 → 下午课 → 晚饭 → 自由活动 → 睡觉
    课与课之间超过 20 分钟的空档会单独列出来。
    """
    slots = _parse_slots(classes)
    if not slots:
        return "[工具出错] 没解析出课表。写成「10:30-12:30 上课」这样，一节课一行。"
    wb_min = int(re.sub(r"[^\d]", "", str(wake_before)) or 30)
    lunch_min = int(re.sub(r"[^\d]", "", str(lunch)) or 150)
    dinner_min = int(re.sub(r"[^\d]", "", str(dinner)) or 30)
    sr = _parse_slots(sleep_range or "", 240)
    sleep_a, sleep_b = (sr[0][0], sr[0][1]) if sr else (60, 240)   # 默认 01:00–04:00

    rows = []
    wake = slots[0][0] - wb_min
    rows.append((wake, slots[0][0], "起床 · 洗漱" + ("（比第一节课早 %d 分钟）" % wb_min),
                 "有课的日子就这个点起"))
    for a, b, name, note in slots:
        rows.append((a, b, name, note))

    # 午饭+午睡：接在"上午最后一节"后面（结束时间落在 11:00–14:30 的那节）
    morning_end = max([b for a, b, _, _ in slots if 11 * 60 <= b <= 14 * 60 + 30] + [12 * 60 + 30])
    lunch_win = (morning_end, morning_end + lunch_min)
    rows.append((lunch_win[0], lunch_win[1], "午饭 + 午睡",
                 "这一觉是你下午能不能打起精神的关键"))

    # 晚饭：接在"傍晚那节"后面（结束时间落在 16:00–19:30 的那节）
    eve_end = max([b for a, b, _, _ in slots if 16 * 60 <= b <= 19 * 60 + 30] + [17 * 60 + 30])
    dinner_win = (eve_end, eve_end + dinner_min)
    rows.append((dinner_win[0], dinner_win[1], "晚饭", ""))

    # 课间空档（>=20 分钟）—— 但要把已经被午饭/晚饭占掉的那段挖掉。
    # 实测踩过：12:30 下课、15:30 才上下一节，直接算出来一个"12:30–15:30 空档"，
    # 跟"12:30–15:00 午饭+午睡"整块重叠，表就自相矛盾了。
    def _subtract(seg, cut):
        out = []
        for s, e in seg:
            if e <= cut[0] or s >= cut[1]:
                out.append((s, e))
                continue
            if s < cut[0]:
                out.append((s, cut[0]))
            if e > cut[1]:
                out.append((cut[1], e))
        return out

    for i in range(len(slots) - 1):
        pieces = [(slots[i][1], slots[i + 1][0])]
        pieces = _subtract(pieces, lunch_win)
        pieces = _subtract(pieces, dinner_win)
        for s, e in pieces:
            if e - s >= 20:
                rows.append((s, e, "空档", "回宿舍 / 自习 / 处理杂事都行"))

    # 自由活动：晚饭后一直到睡觉
    free_a, free_b = eve_end + dinner_min, sleep_a + (24 * 60 if sleep_a < eve_end else 0)
    if free_b - free_a >= 30:
        rows.append((free_a, free_b, "自由活动",
                     "健身就按路上+训练约 2.5 小时算；不健身就是游戏 / 学习"))

    extra_rows, notes = [], []
    for raw in str(extras or "").replace("；", "\n").replace(";", "\n").split("\n"):
        line = raw.strip().lstrip("-·* ").strip()
        if not line:
            continue
        m = re.match(r"^(\d{1,2}\s*[:：点]\s*\d{0,2})\s*(.*)$", line)
        if m and _hm(m.group(1)):
            at = _mins(_hm(m.group(1)))
            extra_rows.append((at, at + 60, m.group(2) or "（自己填）", "你加的固定安排"))
        else:
            notes.append(line)
    rows = sorted(rows + extra_rows, key=lambda r: r[0] if r[0] >= wake else r[0] + 24 * 60)

    sleep_note = "时间不定，落在这一段里（你通常是 1 点到 4 点之间）"
    rows.append((sleep_a, sleep_b, "睡觉（不定时）", sleep_note))

    _write_plan(path, title, rows, notes)
    body = ["  %s–%s  %s" % (_fmt(a), _fmt(b), what) for a, b, what, _ in rows]
    return ("照这句说：上课日规划排好了，%d 个时段，文件在 %s。\n"
            "绝对路径：%s\n大小：%s\n%s\n"
            "（课表变了就告诉我新的上课时间，我重排；这几个固定点也可以顺手做成提醒。）"
            % (len(rows), os.path.basename(path), path, human_size(path), "\n".join(body)))


# ---------------------------------------------------------------- 日常规划表

def _hm(text, default=""):
    """把 7:30 / 07:30 / 7点30 这类写法统一成 "HH:MM"；认不出来就用默认值。"""
    m = re.fullmatch(r"\s*(\d{1,2})\s*[:：点]\s*(\d{1,2})?\s*分?\s*", str(text or ""))
    if not m:
        return default
    h = int(m.group(1))
    mi = int(m.group(2) or 0)
    if h > 23 or mi > 59:
        return default
    return "%02d:%02d" % (h, mi)


def _mins(hhmm):
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def _fmt(mins):
    mins = int(mins) % (24 * 60)
    return "%02d:%02d" % (mins // 60, mins % 60)


def build_dayplan(path, wake="07:30", sleep="23:30", work_start="09:00",
                  work_end="18:00", commute="40", extras="", title="日常规划表"):
    """
    排一张真正的时间表（不是把你给的数字抄成一行）。

    为什么要专门写：实测让模型自己排，它会把你说的"7:30 起床 / 8:30 到公司 / 18:00 下班"
    原样抄成一行表格就交差 —— 4B 模型不擅长"按约束生成结构化排程"。
    所以骨架（起床→早餐→通勤→上下午→午休→下班→晚饭→自由时间→洗漱→睡觉）在这里算好，
    模型只负责把你说的零碎安排塞进 extras。
    """
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    path = ensure_ext(path, ".xlsx")
    ensure_parent(path)

    w_wake = _hm(wake, "07:30")
    w_sleep = _hm(sleep, "23:30")
    w_start = _hm(work_start, "09:00")
    w_end = _hm(work_end, "18:00")
    try:
        cm = int(re.sub(r"[^\d]", "", str(commute)) or 40)
    except ValueError:
        cm = 40
    cm = max(0, min(240, cm))

    rows = []          # (开始, 结束, 安排, 备注)

    def add(a, b, what, note=""):
        if a is None or b is None or b <= a:
            return
        rows.append((_fmt(a), _fmt(b), what, note))

    leave = _mins(w_start) - cm                    # 出门时间
    home = _mins(w_end) + cm                       # 到家时间
    if _mins(w_wake) >= leave:                     # 起得比出门还晚，就压掉早餐
        leave = _mins(w_wake) + 20
    add(_mins(w_wake), min(leave, _mins(w_wake) + 45), "起床 · 洗漱早饭",
        "早饭别省")
    # 备注留空：别把"通勤方式"这种个人习惯写死在工具里（想要就写进 data\习惯.md，
    # 或者用 extras 传进来）。之前这里误留了一句从测试数据里来的"地铁优先…"。
    add(leave, _mins(w_start), "通勤（路上 %d 分钟）" % cm, "")
    add(_mins(w_start), 12 * 60, "上午工作", "先啃最难的那件事")
    add(12 * 60, 13 * 60 + 30, "午饭 · 休息", "")
    add(13 * 60 + 30, _mins(w_end), "下午工作", "")
    add(_mins(w_end), home, "下班 · 通勤回家", "")
    add(home, home + 45, "晚饭 · 缓一缓", "")
    add(max(home + 45, _mins(w_sleep) - 150), _mins(w_sleep) - 60,
        "自由时间（学习 / 剪片 / 游戏）", "这块是你一天里唯一能自己支配的")
    add(_mins(w_sleep) - 60, _mins(w_sleep), "洗漱 · 准备睡", "手机放远一点")
    add(_mins(w_sleep), _mins(w_sleep) + 1, "睡觉", "")

    # 用户另外说的固定安排：能认出时间就插进对应位置，认不出就放备注
    extra_rows, notes = [], []
    for raw in str(extras or "").replace("；", "\n").replace(";", "\n").split("\n"):
        line = raw.strip().lstrip("-·* ").strip()
        if not line:
            continue
        m = re.match(r"^(\d{1,2}\s*[:：点]\s*\d{0,2})\s*[~\-—到至]{0,1}\s*(.*)$", line)
        if m and _hm(m.group(1)):
            at = _mins(_hm(m.group(1)))
            extra_rows.append((_fmt(at), _fmt(at + 60), m.group(2) or "（自己填）", "你加的固定安排"))
        else:
            notes.append(line)

    rows = sorted(rows + extra_rows, key=lambda r: _mins(r[0]))

    wb = Workbook()
    ws = wb.active
    ws.title = "日常规划"
    head_font = Font(name=FONT, bold=True, color="FFFFFF")
    head_fill = PatternFill("solid", fgColor=ACCENT_DARK)
    body_font = Font(name=FONT)
    time_font = Font(name=FONT, bold=True)

    ws.append([title])
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=4)
    c = ws.cell(row=1, column=1)
    c.font = Font(name=FONT, bold=True, size=14)
    c.alignment = Alignment(horizontal="center", vertical="center")

    ws.append(["时段", "安排", "备注", ""])
    hdr = ws.max_row
    for col in range(1, 4):
        cc = ws.cell(row=hdr, column=col)
        cc.font = head_font
        cc.fill = head_fill
        cc.alignment = Alignment(horizontal="center", vertical="center")

    for a, b, what, note in rows:
        span = "%s–%s" % (a, b) if a != b else a
        ws.append([span, what, note])
        r = ws.max_row
        ws.cell(row=r, column=1).font = time_font
        ws.cell(row=r, column=2).font = body_font
        ws.cell(row=r, column=3).font = body_font
        ws.cell(row=r, column=3).alignment = Alignment(wrap_text=True, vertical="center")

    if notes:
        ws.append([])
        ws.append(["随时要做的", "\n".join(notes), ""])
        ws.cell(row=ws.max_row, column=1).font = time_font
        ws.cell(row=ws.max_row, column=2).alignment = Alignment(wrap_text=True)

    ws.column_dimensions["A"].width = 14
    ws.column_dimensions["B"].width = 34
    ws.column_dimensions["C"].width = 40
    ws.freeze_panes = "A%d" % (hdr + 1)
    wb.save(path)

    body = ["  %s–%s  %s" % (a, b, what) for a, b, what, _ in rows]
    return ("照这句说：日常规划表做好了，一共 %d 个时段，文件在 %s。\n"
            "绝对路径：%s\n大小：%s\n"
            "骨架：起床 %s / 上班 %s / 下班 %s / 睡觉 %s（通勤单程 %d 分钟）\n%s\n"
            "（这些时间是按你给的约束算出来的。哪一段不合适，直接说「挪哪儿」，"
            "我改表重出；想让它到点提醒你，我也可以顺手把固定时间做成提醒。）"
            % (len(rows), os.path.basename(path), path, human_size(path),
               w_wake, w_start, w_end, w_sleep, cm, "\n".join(body)))


# ---------------------------------------------------------------- Word

def build_docx(path, content, title=""):
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml.ns import qn
    from docx.shared import Pt, RGBColor

    path = ensure_ext(path, ".docx")
    ensure_parent(path)
    if not (content or "").strip():
        return "[工具出错] content 是空的，没东西可写。"

    doc = Document()

    # 正文默认字体（中文字体必须走 eastAsia，只设 font.name 只管西文）
    normal = doc.styles["Normal"]
    normal.font.name = FONT
    normal.font.size = Pt(11)
    normal._element.rPr.rFonts.set(qn("w:eastAsia"), FONT)
    for sname in ("Heading 1", "Heading 2", "Heading 3", "Title"):
        st = doc.styles[sname]
        st.font.name = FONT
        try:
            st._element.rPr.rFonts.set(qn("w:eastAsia"), FONT)
        except Exception:
            pass

    made = []
    if title:
        h = doc.add_heading(clean_inline(title), level=0)
        h.alignment = WD_ALIGN_PARAGRAPH.CENTER
        made.append("标题：" + clean_inline(title))

    for raw in content.replace("\r\n", "\n").split("\n"):
        s = raw.strip()
        if not s:
            continue
        if re.match(r"^[-*_=]{3,}$", s):
            doc.add_page_break()
            continue
        m = re.match(r"^(#{1,6})\s+(.*)$", s)
        if m:
            level = min(len(m.group(1)), 4)
            if title and level == 1 and clean_inline(m.group(2)) == clean_inline(title):
                continue        # 标题已经写过了，不要重复
            txt = clean_inline(m.group(2))
            doc.add_heading(txt, level=level)
            made.append("小标题：" + txt)
            continue
        m = re.match(r"^\s*[-*+•]\s+(.*)$", raw)
        if m:
            doc.add_paragraph(clean_inline(m.group(1)), style="List Bullet")
            continue
        m = re.match(r"^\s*(\d+)[.)]\s+(.*)$", raw)
        if m:
            doc.add_paragraph(clean_inline(m.group(2)), style="List Number")
            continue
        if s.startswith(">"):
            p = doc.add_paragraph(clean_inline(s.lstrip("> ").strip()))
            p.style = doc.styles["Intense Quote"]
            continue
        doc.add_paragraph(clean_inline(s))

    doc.save(path)
    words = len(re.sub(r"\s", "", content))
    lines = ["照这句说：文档写好了，%d 字，文件在 %s。" % (words, os.path.basename(path)),
             "绝对路径：%s" % path, "大小：%s" % human_size(path)]
    if made:
        lines.append("结构：" + "；".join(made[:12]))
    return "\n".join(lines)


# ---------------------------------------------------------------- Excel

def _cell_value(s):
    t = s.strip()
    if not t:
        return None
    if re.fullmatch(r"-?\d+", t):
        return int(t)
    if re.fullmatch(r"-?\d*\.\d+", t):
        return float(t)
    if t.endswith("%") and re.fullmatch(r"-?\d*\.?\d+%", t):
        try:
            return float(t[:-1]) / 100.0
        except ValueError:
            return t
    return t


def build_xlsx(path, content):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    path = ensure_ext(path, ".xlsx")
    ensure_parent(path)
    if not (content or "").strip():
        return "[工具出错] content 是空的，没东西可写。"

    def split_row(line):
        if "\t" in line:
            return [c for c in line.split("\t")]
        if "|" in line:                        # Markdown 表格
            cells = [c for c in line.strip().strip("|").split("|")]
            return [c.strip() for c in cells]
        return [c for c in line.split(",")]

    wb = Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    sheets = [ws]
    rows = {}                                  # 每张表的行数
    rows[ws.title] = 0

    for raw in content.replace("\r\n", "\n").split("\n"):
        s = raw.strip()
        if not s:
            continue
        if s.startswith("#"):                  # # 表名 -> 新建工作表
            name = re.sub(r"[\\/*?:\[\]]", "", s.lstrip("#").strip())[:28] or "Sheet%d" % (len(sheets) + 1)
            if name in rows:
                name = "%s_%d" % (name, len(sheets) + 1)
            w = wb.create_sheet(name)
            sheets.append(w)
            rows[name] = 0
            continue
        if re.match(r"^[-*_=]{3,}$", s) or re.fullmatch(r"[\|\s:\-]+", s):
            continue                           # Markdown 表格的分隔行
        vals = [_cell_value(c) for c in split_row(s)]
        if not any(v is not None for v in vals):
            continue
        cur = sheets[-1]
        cur.append(vals)
        rows[cur.title] += 1

    total_rows = sum(rows.values())
    if total_rows == 0:
        return "[工具出错] 没解析出任何表格行。每行写成 表头1,表头2 的样子，逗号或 Tab 分隔。"

    head_font = Font(name=FONT, bold=True, color="FFFFFF")
    head_fill = PatternFill("solid", fgColor=ACCENT_DARK)
    body_font = Font(name=FONT)
    meta = []
    for w in sheets:
        if w.max_row == 0:
            continue
        for c in range(1, w.max_column + 1):
            cell = w.cell(row=1, column=c)
            cell.font = head_font
            cell.fill = head_fill
            cell.alignment = Alignment(horizontal="center", vertical="center")
        for r in range(2, w.max_row + 1):
            for c in range(1, w.max_column + 1):
                w.cell(row=r, column=c).font = body_font
        # 列宽：按内容里最长的那个来，中文按 2 个字宽算
        for c in range(1, w.max_column + 1):
            width = 8
            for r in range(1, w.max_row + 1):
                v = w.cell(row=r, column=c).value
                if v is None:
                    continue
                txt = str(v)
                wlen = sum(2 if ord(ch) > 0x2E80 else 1 for ch in txt)
                width = max(width, min(wlen + 3, 60))
            w.column_dimensions[get_column_letter(c)].width = width
        pct_cols = [c for c in range(1, w.max_column + 1)
                    if isinstance(w.cell(row=2, column=c).value, float)]
        for c in pct_cols:
            col = get_column_letter(c)
            for r in range(2, w.max_row + 1):
                w.cell(row=r, column=c).number_format = "0.0%"
        w.freeze_panes = "A2"
        meta.append("%s：%d 行 × %d 列" % (w.title, w.max_row, w.max_column))

    if len(sheets) > 1 and sheets[0].max_row == 0:
        wb.remove(sheets[0])          # 多表时把自动建的那张空表去掉
    wb.save(path)
    lines = ["照这句说：表格做好了，共 %d 行，文件在 %s。" % (total_rows, os.path.basename(path)),
             "绝对路径：%s" % path, "大小：%s" % human_size(path),
             "工作表：" + "；".join(meta)]
    return "\n".join(lines)


# ---------------------------------------------------------------- 视频

def _run_ffmpeg(args, timeout=1800):
    if not FFMPEG:
        return 1, "找不到 ffmpeg（看的路径：%s）" % "；".join(FFMPEG_CANDIDATES)
    r = run_hidden([FFMPEG, "-hide_banner", "-y"] + args,
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=timeout)
    tail = "\n".join((r.stderr or "").strip().split("\n")[-8:])
    return r.returncode, tail


def _probe(path):
    """拿时长和分辨率，没 ffprobe 就返回 None 让调用方走保守分支。"""
    if not FFPROBE or not os.path.isfile(FFPROBE):
        return None
    r = run_hidden([FFPROBE, "-v", "error", "-select_streams", "v:0",
                        "-show_entries", "stream=width,height:format=duration",
                        "-of", "csv=p=0", path],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=120)
    if r.returncode != 0:
        return None
    info = {"width": 0, "height": 0, "duration": 0.0}
    for line in (r.stdout or "").strip().split("\n"):
        parts = [p for p in line.strip().split(",") if p != ""]
        if len(parts) >= 2 and parts[0].isdigit():
            info["width"], info["height"] = int(parts[0]), int(parts[1])
        elif len(parts) == 1:
            try:
                info["duration"] = float(parts[0])
            except ValueError:
                pass
    return info


def _has_audio(path):
    if not FFPROBE or not os.path.isfile(FFPROBE):
        return True
    r = run_hidden([FFPROBE, "-v", "error", "-select_streams", "a",
                        "-show_entries", "stream=index", "-of", "csv=p=0", path],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=120)
    return bool((r.stdout or "").strip())


def _seconds(v, default=None):
    if v is None or str(v).strip() == "":
        return default
    s = str(v).strip()
    if re.fullmatch(r"\d+(\.\d+)?", s):
        return float(s)
    m = re.fullmatch(r"(?:(\d+):)?(\d+):(\d+(?:\.\d+)?)", s)
    if m:
        h = int(m.group(1) or 0)
        return h * 3600 + int(m.group(2)) * 60 + float(m.group(3))
    return default


def edit_video(action, inputs, output, start=None, end=None, width=None,
               fps=None, speed=None):
    """
    action 说明：
        trim          剪一段       需要 start / end
        concat        拼多段       需要 inputs 里多个文件
        extract_audio 抽音轨       output 建议 .m4a 或 .mp3
        to_gif        转动图       start/end 可选
        speed         变速         speed=倍速（0.5~2.0 之外会拆成多段处理）
        mute          去掉声音
        scale         改分辨率     width=目标宽度，高度按比例
    """
    action = (action or "").strip().lower()
    files = [f for f in (inputs or []) if str(f).strip()]
    if not files:
        return "[工具出错] 没给输入文件。input 填视频路径（相对工作目录的也行）。"
    missing = [f for f in files if not os.path.isfile(f)]
    if missing:
        return "[工具出错] 找不到这些文件：%s" % "；".join(missing[:3])
    if action == "to_gif":
        output = ensure_ext(output, ".gif")
    elif action == "extract_audio":
        if not os.path.splitext(output)[1]:
            output += ".m4a"
    else:
        output = ensure_ext(output, ".mp4")
    if any(os.path.normcase(os.path.realpath(output)) == os.path.normcase(os.path.realpath(f)) for f in files):
        return "[工具出错] 输出路径不能与输入相同，请换一个文件名。"
    ensure_parent(output)

    for label, value in (("start", start), ("end", end), ("speed", speed)):
        if value is not None and str(value).strip() and _seconds(value) is None:
            return "[工具出错] %s 格式不正确，请使用秒数或时:分:秒。" % label
    if action in ("trim", "to_gif") and end is not None and str(end).strip():
        if _seconds(end) <= _seconds(start, 0):
            return "[工具出错] 结束时间必须大于开始时间。"

    if action == "trim":
        st = _seconds(start, 0.0)
        en = _seconds(end, None)
        args = ["-ss", str(st), "-i", files[0]]
        if en is not None and en > st:
            args += ["-t", "%.3f" % (en - st)]
        args += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                 "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", output]
        rc, log = _run_ffmpeg(args)
        tip = "（本机没有 ffprobe，时长没校验）" if not FFPROBE else ""
        return _ok(rc, log, output, "剪好了 %s 的这一段%s" % (os.path.basename(files[0]), tip))

    if action == "concat":
        if len(files) < 2:
            return "[工具出错] 拼接至少要两个文件。"
        info = _probe(files[0]) or {}
        w, h = info.get("width") or 1280, info.get("height") or 720
        if h % 2:
            h -= 1
        if w % 2:
            w -= 1
        cmd = []
        filters = []
        for i, f in enumerate(files):
            cmd += ["-i", f]
        idx = len(files)
        for i, f in enumerate(files):
            if not _has_audio(f):
                d = (_probe(f) or {}).get("duration") or 1
                cmd += ["-f", "lavfi", "-t", "%.3f" % max(d, 0.01),
                        "-i", "anullsrc=r=44100:cl=stereo"]
                filters.append("[v%d][%d:a]" % (i, idx))
                idx += 1
            else:
                filters.append("[v%d][%d:a]" % (i, i))
        graph = ""
        for i in range(len(files)):
            graph += "[%d:v]scale=%d:%d:force_original_aspect_ratio=decrease," \
                     "pad=%d:%d:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30,setpts=PTS-STARTPTS[v%d];" % (
                         i, w, h, w, h, i)
        graph += "".join(filters) + "concat=n=%d:v=1:a=1[v][a]" % len(files)
        args = cmd + ["-filter_complex", graph, "-map", "[v]", "-map", "[a]",
                      "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                      "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", output]
        rc, log = _run_ffmpeg(args)
        return _ok(rc, log, output, "拼好了 %d 段（统一成 %dx%d / 30fps，没有声音的段落补了静音）"
                   % (len(files), w, h))

    if action == "extract_audio":
        ext = os.path.splitext(output)[1].lower() or ".m4a"
        if ext in (".mp3", ".wav"):
            ac = ["-c:a", "libmp3lame" if ext == ".mp3" else "pcm_s16le", "-vn"]
        else:
            ac = ["-c:a", "aac", "-b:a", "192k", "-vn"]
        rc, log = _run_ffmpeg(["-i", files[0]] + ac + [output])
        return _ok(rc, log, output, "音轨抽出来了（%s）" % os.path.basename(output))

    if action == "to_gif":
        st = _seconds(start, 0.0)
        en = _seconds(end, None)
        args = []
        if st:
            args += ["-ss", str(st)]
        args += ["-i", files[0]]
        if en is not None and en > st:
            args += ["-t", "%.3f" % (en - st)]
        w = int(width or 480)
        chain = "fps=%s,scale=%d:-1:flags=lanczos" % (fps or 12, w)
        args += ["-vf", chain, "-loop", "0", output]
        rc, log = _run_ffmpeg(args)
        return _ok(rc, log, output, "动图转好了（%d 宽 / %s fps）" % (w, fps or 12))

    if action == "speed":
        sp = _seconds(speed, 1.0)
        if sp <= 0 or sp == 1.0 or not 0.05 <= sp <= 20:
            return "[工具出错] speed 要填一个不等于 1 的倍速，比如 1.5 或 0.8。"
        # atempo 只能 0.5~2.0，超出就串起来
        rest = sp
        chain = []
        while rest > 2.0:
            chain.append("atempo=2.0")
            rest /= 2.0
        while rest < 0.5:
            chain.append("atempo=0.5")
            rest /= 0.5
        chain.append("atempo=%.4f" % rest)
        has_audio = _has_audio(files[0])
        graph = "[0:v]setpts=(PTS-STARTPTS)/%.4f[v]" % sp
        if has_audio:
            graph += ";[0:a]%s[a]" % ",".join(chain)
        rc, log = _run_ffmpeg(["-i", files[0], "-filter_complex", graph,
                               "-map", "[v]"] + (["-map", "[a]"] if has_audio else []) + ["-c:v", "libx264",
                               "-preset", "veryfast", "-crf", "20", "-c:a", "aac", output])
        return _ok(rc, log, output, "变速做完了，%s 倍（音频跟着一起变）" % sp)

    if action == "mute":
        rc, log = _run_ffmpeg(["-i", files[0], "-an", "-c:v", "copy", output])
        return _ok(rc, log, output, "静音版输出好了（画面是直接复制，没有重压）")

    if action == "scale":
        w = int(width or 1280)
        if w % 2:
            w -= 1
        rc, log = _run_ffmpeg(["-i", files[0], "-vf", "scale=%d:-2" % w,
                               "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                               "-c:a", "copy", output])
        return _ok(rc, log, output, "改好分辨率了，宽度 %d" % w)

    return ("[工具出错] 不认识的 action：%s。可用的有 trim / concat / extract_audio / "
            "to_gif / speed / mute / scale。" % action)


def _ok(rc, log, output, what):
    if rc != 0 or not os.path.isfile(output):
        return "[工具出错] ffmpeg 返回 %d，没做出文件。最后几行日志：\n%s" % (rc, log)
    lines = ["照这句说：%s，文件在 %s。" % (what, os.path.basename(output)),
             "绝对路径：%s" % output, "大小：%s" % human_size(output)]
    return "\n".join(lines)
