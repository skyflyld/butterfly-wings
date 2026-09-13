#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""蝶翼之间 / 隐形的纪元 —— 站点生成器（唯一入口）

    源：butterfly-wings-r16.md（手写，唯一真相源）
    产物：r16-enhanced.html（跨页阅读）· r16-flipbook.html（翻页书）· index.html（入口跳转）

    用法：
        python3 build.py            # 生成 + 自检（自检不过则不落盘）
        python3 build.py --check    # 只自检

渲染规则（与 enhanced 模板里的 mdToHTML 同一套，由 parity.js 机械比对）：
    `#####`→h5 `####`→h4 `###`→h3 `##`→h2  |  `---`→hr  |  `> `→blockquote
    `` `x` ``→<code>  |  `**x**`→<strong>  |  `*x*`→<em>
    其余每个非空行 → 一个 <p>；>200 汉字的长段插入 smartBreak 停顿标记 <span class="pb">
    ⚠️ md 在浏览器里是「JS 模板字符串」，故 \n 会解义为换行、\\ 解义为 \、\` 解义为 `
       —— build.py 用同一套解义（js_unescape），否则两版内容会漂移。

翻页书分页规则（明文化，替代原产物的不可复现手工分页）：
    ① 每个标题行必开新页（act 标题后紧跟章标题 → 自然得到「只有标题」的一页，与原产物一致）
    ② 页内累积渲染字符 ≥ PAGE_BUDGET 时在行边界断页（不切断段落）
    ③ 总页 = 封面1 + 目录1 + 正文 + 封底1；TOC 的 data-pg = 正文页序号(0基)，前端 show(pg+2)
"""
import re, sys, os, json, hashlib, subprocess

D = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(D, "butterfly-wings-r16.md")
PAGE_BUDGET = 840      # 每页渲染字符预算（对齐 R15 产物 ~169 正文页的节奏）

# ---------------------------------------------------------------- 渲染规则
HEAD = [(r"^##### (.+)$", "h5"), (r"^#### (.+)$", "h4"),
        (r"^### (.+)$", "h3"), (r"^## (.+)$", "h2")]
PAGE_HEADS = ("h2", "h3")     # 会开新页并进目录的层级（与原产物 42 行目录一致）
SMART_BREAK = [  # 与 enhanced 模板 smartBreak 的 18 条模式逐条对应
    r"([。！？])(他后来在笔记本上[写记])", r"([。！？])(他在笔记[本中]上[写记])",
    r"([。！？])(那天[下午晚早晨夜])", r"([。！？])(第[二三四五六七八九十]天[早午晚])",
    r"([。！？])([一二三四五六七八九]月[。，初底中日])", r"([。！？])([一二三四五六七八九]年后)",
    r"([。！？])(窗外——)", r"([。！？])(门外——)", r"([。！？])(走廊[里外]——)",
    r"([。！？])(他[想起记]起)", r"([。！？])(莉娜[说站走坐])", r"([。！？])(苏遥[没看站回坐转])",
    r"([。！？])(奥兰德[在坐走看])", r"([。！？])(诺亚[在走站])", r"([。！？])(贝克尔)",
    r"([。！？])(卡斯特罗)", r"([。！？])(埃克哈特)", r"([。！？])(她[没在站走])",
]


JS_SIMPLE = {"n": "\n", "t": "\t", "r": "\r", "b": "\b", "f": "\f",
             "v": "\v", "0": "\0", "\\": "\\", "`": "`", "$": "$",
             "'": "'", '\"': '\"'}


def js_unescape(t):
    """忠实模拟 JS 模板字符串解义：
       \\n→换行  \\t→制表  \\\\→反斜杠  \\`→反引号  \\\$→$  \\xNN/\\uNNNN/\\u{...}→字符
       \\+换行 → 行接续（反斜杠与换行一起删掉，两行拼接）—— 原稿里有 14 处，
       不理解这条会让本生成器与浏览器里的 enhanced 版内容漂移。
       未知转义（如 \\{）→ 丢弃反斜杠只留字符。
    """
    out, i, n = [], 0, len(t)
    while i < n:
        c = t[i]
        if c == "\\" and i + 1 < n:
            d = t[i + 1]
            if d == "\r" or d == "\n":                     # 行接续
                i += 3 if (d == "\r" and i + 2 < n and t[i + 2] == "\n") else 2
                continue
            if d in JS_SIMPLE:
                out.append(JS_SIMPLE[d]); i += 2; continue
            if d == "x" and i + 3 < n + 1:
                out.append(chr(int(t[i + 2:i + 4], 16))); i += 4; continue
            if d == "u":
                if t[i + 2:i + 3] == "{":
                    j = t.index("}", i + 3)
                    out.append(chr(int(t[i + 3:j], 16))); i = j + 1; continue
                out.append(chr(int(t[i + 2:i + 6], 16))); i += 6; continue
            out.append(d); i += 2; continue                        # 未知转义：去掉反斜杠
        out.append(c); i += 1
    return "".join(out)


def render_line(line, prev_quote=False):
    """单行 → (html, 是否块级标题行)。规则与 enhanced 的 mdToHTML 逐条对齐：
       ① 标题 → h2..h5  ②`---`→hr  ③`> `→blockquote（相邻行合并）
       ④ 行内 `code` / **bold** / *em*
       ⑤ 转换后以 `<` 开头的行“裸”输出（不再包 <p>）—— 这是原渲染器的实际行为，
          也是独立斜体句/独立粗体句不落在 <p> 里的原因
       ⑥ 其余行包 <p>；>200 汉字的长行插入 smartBreak 停顿标记
    """
    for pat, tag in HEAD:
        m = re.match(pat, line)
        if m:
            return (f'<{tag} class="{"ch-title" if tag in PAGE_HEADS else "ch-sub"}">'
                    f"{m.group(1)}</{tag}>", tag in PAGE_HEADS)
    if re.match(r"^---$", line):
        return "<hr>", False
    m = re.match(r"^> (.+)$", line)
    if m:
        return ("" if prev_quote else "<blockquote>") + m.group(1) + "</blockquote>", False
    x = re.sub(r"`([^`\n]+)`", r"<code>\1</code>", line)
    x = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", x)
    x = re.sub(r"\*(.+?)\*", r"<em>\1</em>", x)
    if x.startswith("<"):
        return x, False
    if len(re.findall(r"[\u4e00-\u9fff]", x)) > 200:
        for pat in SMART_BREAK:
            x = re.sub(pat, r'\1<span class="pb"></span>\2', x)
    return f"<p>{x}</p>", False


def render_blocks(md):
    """md（已按浏览器语义解义）→ [{'head': html|None, 'body': [frag,…]}]，按标题分块"""
    pages, head, body, used, prev_quote = [], None, [], 0, False

    def flush():
        nonlocal head, body, used
        if head is not None or body:
            pages.append({"head": head, "body": body})
        head, body, used = None, [], 0

    for line in md.split("\n"):
        if not line.strip():
            prev_quote = False
            continue
        frag, is_head = render_line(line, prev_quote)
        prev_quote = line.startswith("> ")
        if is_head:
            flush()
            head = frag
            continue
        if (head is not None or body) and used >= PAGE_BUDGET:
            flush()
        body.append(frag)
        used += len(re.sub(r"<[^>]+>", "", frag))
    flush()
    return pages


def page_html(p):
    return (f'<div class="book-page content-page">{(p["head"] or "")}'
            f'<div class="pg-body">{"".join(p["body"])}</div></div>')


def tag_seq(html):
    return [m.group(1) for m in re.finditer(r"<(h[1-5]|p|hr|blockquote)(?:\s|>)", html)]


def main():
    raw = open(SRC, encoding="utf-8").read()
    m = re.search(r"^> 隐形的纪元 (R\d+) · (\d{4}-\d{2}-\d{2})", raw, re.M)
    if not m:
        sys.exit("✗ md 头部缺少 `> 隐形的纪元 RXX · YYYY-MM-DD` 版本行")
    ver, date = m.group(1), m.group(2)
    md = js_unescape(raw)                     # 浏览器侧看到的内容
    h = hashlib.md5(raw.encode()).hexdigest()[:8]

    pages = render_blocks(md)
    rows = [(i, "幕" if p["head"].startswith("<h2") else "·",
             re.sub(r"<[^>]+>", "", p["head"]))
            for i, p in enumerate(pages) if p["head"]]
    total = 2 + len(pages) + 1

    enh = (open(os.path.join(D, "templates/enhanced.html"), encoding="utf-8").read()
           .replace("__EMBEDDED_MD__", raw.replace("`", "\\`"))
           .replace("__VER__", ver).replace("__DATE__", date).replace("__HASH__", h))
    toc_html = "".join(f'<button type="button" class="toc-row" data-pg="{i}">'
                       f'<span class="toc-lv">{lv}</span><span class="toc-name">{name}</span></button>'
                       for i, lv, name in rows)
    flip = (open(os.path.join(D, "templates/flipbook.html"), encoding="utf-8").read()
            .replace("__TOC_ROWS__", toc_html)
            .replace("__PAGES__", "".join(page_html(p) for p in pages))
            .replace("__PAGECOUNT__", str(total)).replace("__VER__", ver))
    idx = (open(os.path.join(D, "templates/index.html"), encoding="utf-8").read()
           .replace("__TARGET__", f"r{ver[1:]}-enhanced.html"))

    # ------------------------------------------------------------ 自检
    errs = []
    mine = tag_seq("".join((p["head"] or "") + "".join(p["body"]) for p in pages))
    heads = re.findall(r"^#{2,3} ", md, re.M)
    if not all(x[1] == "p" or True for x in []):
        pass
    want_count = sum(1 for l in md.split("\n") if re.match(r"^#{2,3} ", l))
    if len(rows) != want_count:
        errs.append(f"TOC 行数 {len(rows)} ≠ 标题行数 {want_count}")
    for k, (i, lv, name) in enumerate(rows):
        if f'<span class="toc-name">{name}</span>' not in toc_html:
            errs.append(f"TOC 第{k}行缺失：{name}")
        if f">{name}</h" not in page_html(pages[i]):
            errs.append(f"TOC 第{k}行 data-pg={i} 未指向标题「{name}」所在页")
    dom_pages = flip.count('class="book-page')
    if f"var pages = {total};" not in flip or dom_pages != total:
        errs.append(f"页数不一致：声明 {total} / DOM {dom_pages}")
    mm = re.search(r"const BW_EMBEDDED_MD = `(.*?)`;", enh, re.S)
    if not mm or js_unescape(mm.group(1)) != md:
        errs.append("enhanced 嵌入 md 往返不一致")
    for bad in ("</script>", "${"):
        if bad in raw:
            errs.append(f"md 含危险序列 {bad}")
    if f"butterfly-pages-{ver}-{h}" not in enh:
        errs.append("缓存键未含 版本+内容哈希")

    # 一致性探针：用 enhanced 模板里的真实渲染器渲染同一份 md，比对块级标签序列
    try:
        probe = json.loads(subprocess.run(["node", os.path.join(D, "parity.js")],
                                          capture_output=True, text=True, timeout=120,
                                          check=True).stdout)
        if probe["seq"] != mine:
            diff = [(a, b) for a, b in zip(probe["seq"], mine) if a != b][:5]
            errs.append(f"两版渲染标签序列不一致（长度 {len(probe['seq'])} vs {len(mine)}；"
                        f"前几处差异 {diff}）")
    except Exception as e:
        errs.append(f"一致性探针失败：{e}")

    print(f"源 {os.path.basename(SRC)} | {ver} · {date} | md5 {h}")
    print(f"正文页 {len(pages)} | 总页 {total}（封面1+目录1+正文{len(pages)}+封底1） | "
          f"标题 {want_count} | TOC {len(rows)}")
    print(f"块级标签序列：{len(mine)} 个（h2 {mine.count('h2')} / h3 {mine.count('h3')} / "
          f"h4 {mine.count('h4')} / h5 {mine.count('h5')} / p {mine.count('p')} / "
          f"hr {mine.count('hr')} / blockquote {mine.count('blockquote')}）")
    if errs:
        print("✗ 自检失败：")
        for e in errs:
            print("   -", e)
        sys.exit(1)
    print("✓ 自检全过：TOC 对应 / 页数一致 / 嵌入往返 / JS 安全 / 缓存键 / 两版渲染一致性（node 探针）")
    if "--check" in sys.argv:
        return
    for name, txt in ((f"r{ver[1:]}-enhanced.html", enh), (f"r{ver[1:]}-flipbook.html", flip),
                      ("index.html", idx)):
        open(os.path.join(D, name), "w", encoding="utf-8").write(txt)
        print(f"✅ {name} {os.path.getsize(os.path.join(D, name))} B")


if __name__ == "__main__":
    main()
