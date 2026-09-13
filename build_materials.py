#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""素材候选清单 → 网页（与 build.py 同一套纪律：md 唯一真相源、确定性、自检不过不落盘）

用法：
    python3 build_materials.py            # 生成 materials-2026-09-13.html
    python3 build_materials.py --check    # 只自检不写盘
"""
import re, os, sys, hashlib, html

ROOT = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(ROOT, "materials", "material-candidates-2026-09-13.md")
OUT = os.path.join(ROOT, "materials-2026-09-13.html")
NOVEL = "https://k286c7hg65-hub.github.io/butterfly-wings/"
GRADES = ("Green", "Yellow", "Red")


# ---------- 内联格式（与 build.py 同一套规则，保证两处渲染一致） ----------
def inline(s):
    s = html.escape(s, quote=False)
    codes = []
    def stash(m):
        codes.append(m.group(1))
        return f"\x00{len(codes) - 1}\x00"
    s = re.sub(r"`([^`]+)`", stash, s)                       # 代码段先摘出来，避免被链接正则咬到
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"(?<![\*\w])\*([^*\n]+)\*(?!\*)", r"<em>\1</em>", s)
    s = re.sub(r"(https?://[^\s，。）)】\"'<]+)", r'<a href="\1" target="_blank" rel="noopener">\1</a>', s)
    def restore(m):
        c = codes[int(m.group(1))]
        if re.fullmatch(r"https?://\S+", c):                 # 裸 URL 的代码段 → 带链接
            return f'<a href="{c}" target="_blank" rel="noopener"><code>{c}</code></a>'
        return f"<code>{c}</code>"
    return re.sub(r"\x00(\d+)\x00", restore, s)


def slug(s):
    return "s-" + hashlib.md5(s.encode()).hexdigest()[:8]


# ---------- 解析 ----------
def parse(text):
    lines = text.split("\n")
    doc = {"title": "", "lede": [], "sections": []}
    sec = grp = item = None
    quote = table = None
    fence = None

    def flush():
        nonlocal quote, table
        quote = table = None

    for ln in lines:
        if ln.startswith("```"):
            if fence is None:
                flush()
                fence = {"type": "pre", "lines": []}
                (item or grp or sec or doc)["blocks" if item else "lede"].append(fence)
            else:
                fence = None
            continue
        if fence is not None:
            fence["lines"].append(ln); continue
        if ln.startswith("# "):
            doc["title"] = ln[2:].strip(); flush(); continue
        if ln.startswith("## "):
            flush()
            sec = {"h2": ln[3:].strip(), "lede": [], "groups": []}
            doc["sections"].append(sec); grp = item = None; continue
        if ln.startswith("### "):
            flush()
            grp = {"h3": ln[4:].strip(), "lede": [], "items": []}
            (sec or doc).setdefault("groups", []).append(grp) if sec else None
            item = None; continue
        if ln.startswith("#### "):
            flush()
            item = {"h4": ln[5:].strip(), "blocks": []}
            grp["items"].append(item); continue

        tgt = item or grp or sec or doc
        if ln.strip() in ("---", "***"):
            flush(); continue
        if ln.startswith(">") or (quote is not None and ln.strip() == "" and False):
            if quote is None:
                quote = {"type": "quote", "lines": []}
                tgt["blocks" if item else "lede"].append(quote)
            quote["lines"].append(ln.lstrip("> ").rstrip())
            continue
        if ln.strip() == "":
            flush(); continue
        if ln.startswith("|"):
            cells = [c.strip() for c in ln.strip().strip("|").split("|")]
            if all(re.fullmatch(r":?-{2,}:?", c) for c in cells):
                continue
            if table is None:
                table = {"type": "table", "rows": []}
                tgt["blocks" if item else "lede"].append(table)
            table["rows"].append(cells)
            continue
        if ln.startswith("- "):
            flush()
            tgt["blocks" if item else "lede"].append({"type": "li", "text": ln[2:].strip()})
            continue
        flush()
        tgt["blocks" if item else "lede"].append({"type": "p", "text": ln.strip()})
    return doc


FIELD = re.compile(r"^\*\*([①②③④⑤⑥][^*]{0,20})\*\*\s*[：:]?\s*(.*)$")


def split_item(it):
    """把条目的段落分成 事实/来源/接口/等级/拟稿 五个槽位"""
    out = {"name": it["h4"], "id": "", "title": "", "fact": [], "src": [],
           "hook": [], "grade": "Yellow", "draft": [], "other": []}
    m = re.match(r"^([A-B]-\d+)\.\s*(.+)$", it["h4"])
    if m:
        out["id"], out["title"] = m.group(1), m.group(2)
    else:
        out["title"] = it["h4"]
    KEY = {"①": "fact", "②": "src", "③": "hook", "④": "grade_raw", "⑤": "draft"}
    for b in it["blocks"]:
        if b["type"] == "p":
            m = FIELD.match(b["text"])
            if m and m.group(1)[0] in KEY:
                slot = KEY[m.group(1)[0]]
                vals = {"label": m.group(1), "text": m.group(2)}
                if slot == "grade_raw":
                    found = []
                    for g in re.findall(r"\*\*(Green|Yellow|Red)\*\*|\b(Green|Yellow|Red)\b", m.group(2)):
                        g = g[0] or g[1]
                        if g and g not in found:
                            found.append(g)
                    # 混合条目取「最差」等级（含 Yellow 部分就不能标 Green）
                    worst = "Green"
                    for g in found:
                        if GRADES.index(g) > GRADES.index(worst):
                            worst = g
                    out["grades"] = found or ["Yellow"]
                    out["grade"] = worst
                    out["other"].append(vals)
                elif slot == "draft":          # ⑤ 的标题行留在正文，紧跟的引用块才是拟稿
                    out["other"].append(vals)
                else:
                    out[slot].append(vals)
                    if slot == "src":
                        u = re.search(r"(https?://[^\s，。）)】\"']+)", m.group(2))
                        out["url"] = u.group(1) if u else out.get("url")
            else:
                out["other"].append({"label": None, "text": b["text"]})
        elif b["type"] == "quote":
            out["draft"].append(b)
        elif b["type"] == "pre":
            out["other"].append(b)
        elif b["type"] in ("li", "table"):
            out["other"].append(b)
    return out


# ---------- 渲染 ----------
CHIP = {"Green": "绿 · 已核验", "Yellow": "黄 · 待复核", "Red": "红 · 禁入正文"}


def render_item(it):
    d = split_item(it)
    cls = d["grade"].lower()
    label = "/".join(d.get("grades") or [d["grade"]])
    h = [f'<article class="item g-{cls}" id="{slug(d["name"])}">']
    h.append('<div class="item-top">')
    h.append(f'<span class="chip c-{cls}" title="{CHIP[d["grade"]]}">{label}</span>')
    h.append(f'<h3><span class="iid">{d["id"]}</span>{html.escape(d["title"])}</h3>')
    h.append("</div>")
    for blk in d["fact"]:
        h.append(f'<p class="fact">{inline(blk["text"])}</p>')
    for blk in d["src"]:
        h.append(f'<p class="src"><span class="lbl">来源</span>{inline(blk["text"])}</p>')
    for blk in d["hook"]:
        h.append(f'<p class="hook"><span class="lbl">小说接口</span>{inline(blk["text"])}</p>')
    for blk in d["other"]:
        if isinstance(blk, dict) and blk.get("type") == "li":
            h.append(f'<li>{inline(blk["text"])}</li>')
        elif isinstance(blk, dict) and blk.get("type") == "table":
            h.append(render_table(blk))
        elif blk.get("label") is None:
            h.append(f'<p class="misc">{inline(blk["text"])}</p>')
        elif isinstance(blk, dict) and blk.get("type") == "pre":
            h.append(render_pre(blk))
        elif blk["label"] and blk["label"].startswith("④"):
            h.append(f'<p class="grade-note"><span class="lbl">验证</span>{inline(blk["text"])}</p>')
        else:
            h.append(f'<p class="misc"><strong>{blk["label"]}</strong>{inline(blk["text"])}</p>')
    for q in d["draft"]:
        h.append('<div class="draft"><span class="lbl">拟稿</span>')
        for l in q["lines"]:
            if not l.strip():
                continue
            c = ""
            if l.startswith("媒体写的是"):
                c = ' class="q-media"'
            elif l.startswith("没有人写"):
                c = ' class="q-nobody"'
            elif l.startswith("不是新闻框架"):
                c = ' class="q-why"'
            elif l.startswith("苏遥"):
                c = ' class="q-note"'
            h.append(f"<p{c}>{inline(l)}</p>")
        h.append("</div>")
    h.append("</article>")
    return "\n".join(h)


def render_table(t):
    h = ['<div class="tw"><table>']
    for i, r in enumerate(t["rows"]):
        tag = "th" if i == 0 else "td"
        h.append("<tr>" + "".join(f"<{tag}>{inline(c)}</{tag}>" for c in r) + "</tr>")
    h.append("</table></div>")
    return "\n".join(h)


def render_prose(blocks, cls=""):
    h = []
    for b in blocks:
        if isinstance(b, dict) and b.get("type") == "quote":
            h.append('<blockquote class="prose-q">')
            for l in b["lines"]:
                if l.strip():
                    h.append(f"<p>{inline(l)}</p>")
            h.append("</blockquote>")
        elif isinstance(b, dict) and b.get("type") == "pre":
            h.append(render_pre(b))
        elif isinstance(b, dict) and b.get("type") == "table":
            h.append(render_table(b))
        elif isinstance(b, dict) and b.get("type") == "li":
            h.append(f'<li>{inline(b["text"])}</li>')
        elif isinstance(b, dict):
            h.append(f'<p>{inline(b["text"])}</p>')
    return "\n".join(h)


def render_pre(b):
    body = html.escape("\n".join(b["lines"])).strip("\n")
    return f'<pre class="fence"><code>{body}</code></pre>'


CSS = """
:root{--ink:#151A1F;--ink2:#3D4855;--mut:#6B7683;--line:#C9CED6;--bg:#EEF0F2;
--card:#FAFBFC;--green:#1E7A4B;--yellow:#8A6100;--red:#9E2B22;}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--ink);
font:15px/1.75 "Noto Sans CJK SC","Source Han Sans SC",-apple-system,"PingFang SC",sans-serif;}
.wrap{max-width:860px;margin:0 auto;padding:34px 22px 90px}
header.top{border-bottom:2px solid var(--ink);padding-bottom:16px;margin-bottom:26px}
.stamp{font:600 11.5px/1.6 ui-monospace,"JetBrains Mono",Menlo,monospace;letter-spacing:.14em;
color:var(--ink);text-transform:uppercase;margin:0 0 10px}
h1{font-size:27px;line-height:1.34;margin:0 0 10px;letter-spacing:.01em}
header.top .lede{color:var(--ink2);font-size:14.5px}
header.top .lede p{margin:.35em 0}
.legend{display:flex;flex-wrap:wrap;gap:8px 18px;margin:18px 0 0;padding:12px 14px;
background:var(--card);border:1px solid var(--line);border-radius:3px;font-size:13px;color:var(--ink2)}
.legend b{font:600 12px/1 ui-monospace,monospace}
.dot{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:6px;vertical-align:middle}
.d-g{background:var(--green)}.d-y{background:var(--yellow)}.d-r{background:var(--red)}
nav.toc{margin:22px 0 34px;font-size:14px;border-left:3px solid var(--line);padding:2px 0 2px 16px}
nav.toc a{display:block;color:var(--ink2);text-decoration:none;padding:2px 0}
nav.toc a:hover{color:var(--ink);text-decoration:underline}
nav.toc .g{color:var(--mut);margin-top:8px;font-size:13px}
h2.sec{font-size:20px;margin:52px 0 14px;padding:0 0 8px;border-bottom:1px solid var(--line)}
h2.sec .num{color:var(--mut);font-weight:400;margin-right:8px}
h3.grp{font-size:15px;margin:34px 0 12px;padding:7px 12px;background:var(--ink);color:#fff;
border-radius:2px;letter-spacing:.02em}
.g-lede{font-size:13.5px;color:var(--mut);border-left:3px solid var(--line);padding:2px 0 2px 14px;margin:12px 0 20px}
.g-lede p{margin:.3em 0}
article.item{background:var(--card);border:1px solid var(--line);border-left:4px solid var(--mut);
border-radius:3px;padding:16px 18px 6px;margin:0 0 18px}
article.g-green{border-left-color:var(--green)}
article.g-yellow{border-left-color:var(--yellow)}
article.g-red{border-left-color:var(--red)}
.item-top{display:flex;align-items:baseline;gap:10px;flex-wrap:wrap;margin-bottom:10px}
.item-top h3{font-size:17px;margin:0;line-height:1.5}
.iid{font:700 13px/1 ui-monospace,"JetBrains Mono",monospace;color:var(--ink2);margin-right:9px;
letter-spacing:.04em}
.chip{font:600 11px/1 ui-monospace,monospace;padding:4px 7px;border-radius:2px;letter-spacing:.06em;
border:1px solid currentColor}
.c-green{color:var(--green)}.c-yellow{color:var(--yellow)}.c-red{color:var(--red)}
article.item p{margin:.62em 0}
p.fact{font-size:15.5px}
p.src,p.hook,p.grade-note,p.misc{font-size:13.5px;color:var(--ink2)}
.lbl{display:inline-block;font:600 11px/1.5 ui-monospace,monospace;letter-spacing:.1em;color:var(--mut);
margin-right:8px;padding:2px 6px;background:#E6E9EC;border-radius:2px}
code{font:13px/1.5 ui-monospace,"JetBrains Mono",Menlo,monospace;background:#E6E9EC;
padding:1px 5px;border-radius:2px;word-break:break-all}
a{color:var(--ink);text-decoration:none;border-bottom:1px solid #8D97A3;word-break:break-all}
a:hover{border-bottom-color:var(--ink);background:#E4E7EA}
.draft{margin:16px 0 14px;padding:12px 14px;background:#F2F4F6;border:1px dashed var(--line);border-radius:3px}
.draft p{margin:.42em 0;font-family:"Noto Serif CJK SC","Source Han Serif SC",Georgia,serif;font-size:15px}
p.q-media{color:var(--mut)}
p.q-nobody{color:var(--ink);font-weight:600;border-left:3px solid var(--ink);padding-left:10px}
p.q-why{color:var(--mut);font-size:13.5px}
p.q-note{color:var(--ink2);font-style:italic}
blockquote.prose-q{margin:14px 0;padding:2px 0 2px 16px;border-left:3px solid var(--line);
font-family:"Noto Serif CJK SC",Georgia,serif;color:var(--ink2)}
blockquote.prose-q p{margin:.4em 0}
.tw{overflow-x:auto;margin:14px 0}
pre.fence{background:#1B232B;color:#E8EDF1;padding:14px 16px;border-radius:3px;overflow-x:auto;
font:13px/1.7 ui-monospace,"JetBrains Mono",Menlo,monospace;margin:14px 0}
pre.fence code{background:none;color:inherit;padding:0}
table{border-collapse:collapse;width:100%;font-size:13.5px;background:var(--card)}
th,td{border:1px solid var(--line);padding:7px 9px;text-align:left;vertical-align:top}
th{background:#E6E9EC;font-weight:600}
li{margin:.3em 0}
footer.end{margin-top:56px;padding-top:16px;border-top:1px solid var(--line);
font-size:12.5px;color:var(--mut)}
footer.end a{color:var(--mut)}
@media (max-width:560px){
 .wrap{padding:22px 14px 60px}
 h1{font-size:22px}
 article.item{padding:13px 13px 4px}
 p.fact{font-size:15px}
}
"""


def build():
    md = open(SRC, encoding="utf-8").read()
    doc = parse(md)
    parts = []
    for i, sec in enumerate(doc["sections"]):
        h2 = sec["h2"]
        num, _, rest = h2.partition("、")
        parts.append(f'<h2 class="sec" id="{slug(h2)}">'
                     f'<span class="num">{html.escape(num)}</span>{inline(rest or num)}</h2>')
        if sec["lede"]:
            parts.append('<div class="g-lede">' + render_prose(sec["lede"]) + "</div>")
        for g in sec.get("groups", []):
            parts.append(f'<h3 class="grp" id="{slug(g["h3"])}">{inline(g["h3"])}</h3>')
            if g["lede"]:
                parts.append('<div class="g-lede">' + render_prose(g["lede"]) + "</div>")
            for it in g["items"]:
                parts.append(render_item(it))

    toc = ['<nav class="toc">']
    for sec in doc["sections"]:
        toc.append(f'<a href="#{slug(sec["h2"])}">{html.escape(sec["h2"])}</a>')
    for sec in doc["sections"]:
        for g in sec.get("groups", []):
            toc.append(f'<a class="g" href="#{slug(g["h3"])}">{html.escape(g["h3"])}</a>')
    toc.append("</nav>")

    n_items = sum(len(g["items"]) for s in doc["sections"] for g in s.get("groups", []))
    out = f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>素材候选清单 · 《蝶翼之间》· 2026-09-13</title>
<meta name="description" content="《蝶翼之间》2026 年缺口（七月/八月）的素材候选清单：14 条，每条标一手来源与证据等级。">
<style>{CSS}</style></head><body><div class="wrap">
<header class="top">
<p class="stamp">CSB-2026-ARCHIVE / INTERNAL-LEVEL4 · 编辑室文件 · {n_items} 条候选</p>
<h1>{html.escape(doc["title"].replace("·", "·", 1))}</h1>
<div class="lede">{render_prose(doc["lede"])}</div>
<div class="legend">
<span><span class="dot d-g"></span><b>Green</b> 一手页面已直抓核验，可直接入稿</span>
<span><span class="dot d-y"></span><b>Yellow</b> 转引或数字待复核，入稿前需再验</span>
<span><span class="dot d-r"></span><b>Red</b> 无可直抓原始 URL，禁入正文</span>
</div>
</header>
{''.join(toc)}
{''.join(parts)}
<footer class="end">
<p>源文档 <code>materials/{os.path.basename(SRC)}</code> · 本页由 <code>build_materials.py</code> 生成（md 唯一真相源，确定性渲染）· 一手页面存档见 <code>materials/sources/</code></p>
<p>小说正本：<a href="{NOVEL}">《蝶翼之间 · 隐形的纪元》R16</a> · 制作 Ariste · 2026-09-13</p>
</footer>
</div></body></html>"""
    return out, doc, n_items


def checks(out, doc, n_items):
    errs = []
    if n_items != 14:
        errs.append(f"候选条数 {n_items} ≠ 14")
    a = sum(len(g["items"]) for s in doc["sections"] for g in s.get("groups", []) if g["h3"].startswith("【A"))
    b = sum(len(g["items"]) for s in doc["sections"] for g in s.get("groups", []) if g["h3"].startswith("【B"))
    if (a, b) != (6, 8):
        errs.append(f"A/B 组条数 {a}/{b} ≠ 6/8")
    n_url = len(set(re.findall(r'href="(https?://[^"]+)', out)))
    if n_url < 6:
        errs.append(f"页面外链只有 {n_url} 个，疑似来源丢失")
    # 每个条目必须有来源行（或显式标注「同 A-x」）
    for art in re.findall(r"<article.*?</article>", out, re.S):
        if 'class="src"' not in art:
            errs.append("有条目缺来源行：" + re.search(r'<h3>(.*?)</h3>', art).group(1)[:40])
    for g in GRADES:
        if f'>{g}<' not in out:
            errs.append(f"缺少 {g} 等级条目")
    if "**" in re.sub(r"<[^>]+>", "", out):
        errs.append("正文残留 ** 标记")
    if "${" in out or "`" in out:
        errs.append("残留 JS 模板字符")
    if out.count("<article") != 14:
        errs.append(f"article 数 {out.count('<article')} ≠ 14")
    return errs


if __name__ == "__main__":
    out, doc, n_items = build()
    errs = checks(out, doc, n_items)
    print(f"源 {os.path.basename(SRC)} | 章节 {len(doc['sections'])} | 条目 {n_items}")
    print(f"产出 {len(out.encode())} B | 外链 {len(re.findall(r'href=.https?://', out))} 个")
    if errs:
        print("✗ 自检失败：")
        for e in errs:
            print("   -", e)
        sys.exit(1)
    print("✓ 自检全过：条数 / 分组 / 等级齐备 / 外链 / 无残留标记")
    if "--check" not in sys.argv:
        open(OUT, "w", encoding="utf-8").write(out)
        print("✅ " + os.path.basename(OUT), len(out.encode()), "B")
