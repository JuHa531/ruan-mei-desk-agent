"""
端到端自检：真的把一句话丢给 ruanmei 模型，看它会不会**调用新工具**把文件做出来。

比 scripts/smoke_office_tools.py 更靠后一步：那个测的是"工具本身能不能用"，
这个测的是"模型知不知道要用工具"（历史教训：4B 模型经常只给建议不动手）。

用法：D:\\ai\\envs\\llm\\python.exe scripts\\test_agent_office.py
"""

import json
import os
import sys
import urllib.error

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "app"))
import agent_server as srv  # noqa: E402

WORKDIR = r"C:\Users\qqqqq\Documents\rm-workspace"
BASE = "http://127.0.0.1:11434"
MODEL = "ruanmei:latest"

CASES = [
    ("做 PPT", "帮我做一份 PPT，文件名 自检周报.pptx，内容是这周做的三件事："
               "性格模型微调完成、语音接口通了、手机联动打通。"
               "每件事写两句要点，最后加一页下一步计划。"),
    ("做表格", "把这三笔支出记成一个 Excel，文件名 自检支出.xlsx："
               "10月8日 买菜 128.5 元，10月9日 打车 46 元，10月10日 电费 210 元。"
               "表头用 日期、项目、金额。"),
    ("做文档", "写一份 Word 文档，文件名 自检说明.docx，标题《梅梅使用说明》，"
               "分三节：它能做什么、怎么用、注意什么，每节两三条要点。"),
]


def run_case(label, prompt):
    messages = [{"role": "user", "content": prompt}]
    called = []
    print("\n== %s ==\n用户：%s" % (label, prompt))
    for step in range(6):
        try:
            resp = srv.ollama_chat(BASE, {
                "model": MODEL, "messages": messages, "tools": srv.TOOLS,
                "stream": False, "think": False,
                "options": {"temperature": 0.4},
            })
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")
            print("  [Ollama 返回 %d] %s" % (e.code, body[:400]))
            print("  发出去的消息（截断）：%s" % json.dumps(messages, ensure_ascii=False)[:600])
            break
        msg = resp.get("message", {}) or {}
        calls = msg.get("tool_calls") or []
        content = (msg.get("content") or "").strip()
        if content:
            print("  它说：%s" % content.replace("\n", " ")[:150])
        if not calls:
            break
        messages.append(msg)
        for c in calls:
            fn = c.get("function", {}) or {}
            name = fn.get("name")
            args = fn.get("arguments") or {}
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except Exception:
                    args = {}
            called.append(name)
            print("  调用工具：%s  参数：%s" % (name, json.dumps(args, ensure_ascii=False)[:160]))
            out = srv.exec_tool(name, args, WORKDIR)
            print("  工具返回：%s" % out.replace("\n", " ")[:200])
            messages.append({"role": "tool", "name": name, "content": out})
    return called


def main():
    expect = {"做 PPT": "make_pptx", "做表格": "make_xlsx", "做文档": "make_docx"}
    fails = []
    for label, prompt in CASES:
        called = run_case(label, prompt)
        want = expect[label]
        ok = want in called
        print("  -> %s" % ("OK 用对了 " + want if ok else "没调用 " + want + "（调了：%s）" % called))
        if not ok:
            fails.append(label)
    print("\n%d 个用例，%d 个失败" % (len(CASES), len(fails)))
    for label in fails:
        print("  失败：", label)
    return 1 if fails else 0


sys.exit(main())
