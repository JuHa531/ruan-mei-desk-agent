"""
office_tools 的自检：把每个工具真跑一遍，看有没有产出文件。

用法：D:\\ai\\envs\\llm\\python.exe scripts\\smoke_office_tools.py [输出目录]
默认输出到 C:\\Users\\qqqqq\\Documents\\rm-workspace\\_selftest（就是梅梅能写的那个工作目录）。
"""

import os
import subprocess
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")      # 免得中文在 GBK 控制台里变乱码
except Exception:
    pass

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "app"))
import office_tools  # noqa: E402

OUT = sys.argv[1] if len(sys.argv) > 1 else r"C:\Users\qqqqq\Documents\rm-workspace\_selftest"
os.makedirs(OUT, exist_ok=True)

PP = """# 本地 AI 助手进展
梅梅 · 本周进度
---
# 已经跑通的部分
- 性格：Qwen3-4B + 154 条人工校对台词微调
- 语音：GPT-SoVITS 零样本克隆，calm / warm / wry 三套语气
- 识别：SenseVoiceSmall 离线转写，说话就能下命令
- 联动：Tailscale 打通手机，HTTPS 反代到本机 7788
# 接下来
- 把文档、表格、视频这几件事变成一句话就能做
- 语音回复要更连贯，少一点合成感
"""

DOC = """# 背景
现在所有的推理都在本机完成，不联网也能用。
## 训练数据
- 主线剧情里截出来的对话样本
- 人工校对过的 154 条台词
## 注意
> 参考音频必须 3~10 秒，否则后端会拒绝。
1. 先校对，再训练
2. 先小样本试听，再全量
"""

SHEET = """日期,项目,耗时(分钟),状态
2026-10-06,性格模型微调,95,完成
2026-10-07,语音接口,120,完成
2026-10-10,手机联动,60,完成
# 语气参数
语气,参考音频,时长(秒)
calm,ruanmei_v3.wav,9.44
warm,ruanmei_warm.wav,8.12
wry,ruanmei_wry_c.wav,5.40
"""

results = []


def check(label, ret, *paths):
    ok = all(os.path.isfile(p) and os.path.getsize(p) > 0 for p in paths) \
        and "[工具出错]" not in ret
    size = ""
    if paths and os.path.isfile(paths[0]):
        size = office_tools.human_size(paths[0])
    results.append((ok, label, size))
    print("[%s] %-22s %s" % ("OK" if ok else "FAIL", label, size))
    if not ok:
        print(ret)


# ---------------------------------------------------------------- 文档类

p1 = os.path.join(OUT, "自检演示.pptx")
check("make_pptx", office_tools.build_pptx(p1, PP, "本地 AI 助手进展", "梅梅 · 自检"), p1)

p2 = os.path.join(OUT, "自检文档.docx")
check("make_docx", office_tools.build_docx(p2, DOC, "本地 AI 实现说明"), p2)

p3 = os.path.join(OUT, "自检表格.xlsx")
check("make_xlsx", office_tools.build_xlsx(p3, SHEET), p3)

# 模型有时候会忘了写扩展名，这里确认补扩展名这套没坏
p4 = os.path.join(OUT, "没有扩展名")
ret = office_tools.build_docx(p4, """# 标题
- 一条要点
""", "")
check("扩展名自动补全", ret, p4 + ".docx")

# ---------------------------------------------------------------- 视频类

ff = office_tools.FFMPEG
print("\nffmpeg =", ff or "(没找到)")
print("ffprobe =", office_tools.FFPROBE or "(没找到)")

v1 = os.path.join(OUT, "素材A.mp4")      # 有画面 + 有声音
v2 = os.path.join(OUT, "素材B.mp4")      # 只有画面，用来验证"没有音轨的段落补静音"
if ff:
    subprocess.run([ff, "-hide_banner", "-y", "-f", "lavfi", "-i",
                    "testsrc=size=640x360:rate=30", "-f", "lavfi", "-i",
                    "sine=frequency=440:sample_rate=44100", "-t", "4",
                    "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-shortest", v1],
                   capture_output=True)
    subprocess.run([ff, "-hide_banner", "-y", "-f", "lavfi", "-i",
                    "testsrc2=size=800x600:rate=25", "-t", "3",
                    "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", v2],
                   capture_output=True)

    print("\n素材信息:", office_tools._probe(v1), "有无声音:", office_tools._has_audio(v1))
    print("素材B 有无声音:", office_tools._has_audio(v2))

    cases = [
        ("trim", dict(action="trim", inputs=[v1], output=os.path.join(OUT, "剪切.mp4"),
                      start="1", end="2.5")),
        ("concat", dict(action="concat", inputs=[v1, v2],
                        output=os.path.join(OUT, "拼接.mp4"))),
        ("extract_audio", dict(action="extract_audio", inputs=[v1],
                               output=os.path.join(OUT, "音轨.m4a"))),
        ("to_gif", dict(action="to_gif", inputs=[v1],
                        output=os.path.join(OUT, "动图.gif"), start="0", end="1.5",
                        width=320, fps=10)),
        ("speed", dict(action="speed", inputs=[v1],
                       output=os.path.join(OUT, "加速.mp4"), speed=1.5)),
        ("mute", dict(action="mute", inputs=[v1],
                      output=os.path.join(OUT, "静音.mp4"))),
        ("scale", dict(action="scale", inputs=[v1],
                       output=os.path.join(OUT, "缩小.mp4"), width=320)),
    ]
    for name, kw in cases:
        ret = office_tools.edit_video(**kw)
        check("edit_video/" + name, ret, kw["output"])
else:
    print("没找到 ffmpeg，视频部分跳过")

# ---------------------------------------------------------------- 汇总

print("\n---- 打开产物看内容对不对（光看文件大小不算数）----")

from pptx import Presentation                      # noqa: E402
from docx import Document                          # noqa: E402
from openpyxl import load_workbook                 # noqa: E402

prs = Presentation(p1)
titles = []
for sl in prs.slides:
    txt = [sh.text_frame.text.strip() for sh in sl.shapes
           if sh.has_text_frame and sh.text_frame.text.strip()]
    titles.append(txt[0].replace("\n", " / ") if txt else "(空页)")
print("pptx 共 %d 页：%s" % (len(prs.slides._sldIdLst), " | ".join(titles[:4])))
check("pptx 页数与文案", "" if len(prs.slides._sldIdLst) >= 3 and "已经跑通" in " ".join(titles) else "[工具出错] 页数不对",
      p1)

d = Document(p2)
heads = [x.text for x in d.paragraphs if x.style.name.startswith("Heading")]
bullets = [x for x in d.paragraphs if x.style.name == "List Bullet"]
print("docx 段落 %d 个，标题 %d 个：%s；项目符号 %d 条"
      % (len(d.paragraphs), len(heads), " / ".join(heads[:4]), len(bullets)))
check("docx 结构", "" if len(heads) >= 3 and len(bullets) >= 2 else "[工具出错] 结构不对", p2)

wb = load_workbook(p3)
cells = {}
for w in wb.worksheets:
    cells[w.title] = w.max_row
print("xlsx 工作表：", cells)
check("xlsx 工作表与行数",
      "" if len(wb.worksheets) == 2 and all(v >= 4 for v in cells.values()) else "[工具出错] 行数不对",
      p3)

if ff:
    for name, want in [("剪切.mp4", 1.5), ("拼接.mp4", 7.0), ("加速.mp4", 4 / 1.5),
                       ("缩小.mp4", 4.0), ("音轨.m4a", 4.0)]:
        f = os.path.join(OUT, name)
        info = office_tools._probe(f) or {}
        got = round(info.get("duration") or 0, 2)
        ok = abs(got - want) < 0.6
        print("%-12s 时长 %.2fs（预期约 %.2fs）%s" % (name, got, want, "OK" if ok else "偏了"))
        results.append((ok, "时长 " + name, "%.2fs" % got))
    silenced = office_tools._has_audio(os.path.join(OUT, "静音.mp4"))
    print("静音.mp4 还有没有音轨:", silenced)
    results.append((not silenced, "静音版确实没有音轨", ""))
    gif = os.path.getsize(os.path.join(OUT, "动图.gif"))
    results.append((gif > 10240, "动图不是空文件", office_tools.human_size(os.path.join(OUT, "动图.gif"))))

bad = [r for r in results if not r[0]]
print("\n%d 项里 %d 项通过" % (len(results), len(results) - len(bad)))
for _, label, _ in bad:
    print("  失败:", label)
sys.exit(1 if bad else 0)
