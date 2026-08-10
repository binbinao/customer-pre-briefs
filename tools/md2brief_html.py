#!/usr/bin/env python3
"""
md2brief_html.py — 把 customer-pre-brief 的 .md 转成 iv-clay-serif 视觉的 .html

设计语言沿用 ~/customer-pre-briefs/index.html 的 token：
  bg=#F8F7F4  clay=#D97757  olive=#788C5D  rust=#B04A3F  sky=#5B8BA0  purple=#8B6B9E
  圆角 12px, 1.5px 边, system-ui + 微软雅黑

5 个 H2 章节 → 横幅卡片,每章独立配色:
  §1 公司速览     sky
  §2 组织与股权   olive
  §3 近期动态     rust
  §4 拜访要点     clay (高亮)
  §5 数据来源     gray

表格 → 卡片网格(每行一张卡,dim/key/value/源 列布局,hover clay 边)
blockquote → 提示 banner:
  ⚡ / 高优      clay gradient
  🚫 / 阻塞     rust 边
  🟢🟡🔴 信心    sky / olive / rust
source 链接 → inline-card,域名显示
TOC 浮窗:右侧 sticky,scroll-spy 高亮当前章节

用法:
  python3 tools/md2brief_html.py <input.md> [<output.html>]
  # 不传 output → 在同目录生成同名 .html

依赖:仅 Python 3.10+ 标准库,无外部包
"""
from __future__ import annotations
import re
import sys
import html
import urllib.parse
from pathlib import Path

# ---------------- 设计 token (与 index.html 一致) ----------------
TOKENS = {
    "bg": "#F8F7F4",
    "card": "#FFFFFF",
    "text": "#141413",
    "clay": "#D97757",
    "olive": "#788C5D",
    "rust": "#B04A3F",
    "sky": "#5B8BA0",
    "purple": "#8B6B9E",
    "gray100": "#EEECE6",
    "gray300": "#D1CFC5",
    "gray500": "#87867F",
    "gray700": "#3D3D3A",
}

# ---------------- 章节配色 (按 H2 序号) ----------------
SECTION_PALETTE = ["sky", "olive", "rust", "clay", "gray500"]
SECTION_ICONS = ["🏢", "👥", "📰", "⚡", "📚"]
SECTION_LABELS = ["公司速览", "组织与股权", "近期动态", "拜访要点", "数据来源"]

# ---------------- markdown 子集解析 ----------------
TABLE_SEP = re.compile(r"^\s*\|?\s*:?-+:?(\s*\|\s*:?-+:?)+\s*\|?\s*$")


def md_to_html(md: str, slug_hint: str = "") -> tuple[str, list[tuple[str, str, str]]]:
    """核心:解析精简 markdown 子集 → 渲染 token-aware HTML 片段"""
    lines = md.splitlines()
    out: list[str] = []
    i = 0
    n = len(lines)

    # 用于 TOC 收集
    toc: list[tuple[str, str, str]] = []  # (id, label, icon)
    section_idx = 0

    # ---- 预处理:转义特殊符号
    def esc(s: str) -> str:
        return html.escape(s)

    # ---- 内联解析
    def inline(s: str) -> str:
        s = esc(s)
        # 链接 [text](url) — 单独处理以拿到 URL 列表
        return s

    # ---- 处理单行
    while i < n:
        line = lines[i]

        # H1 (title)
        if line.startswith("# "):
            title = line[2:].strip()
            out.append(f'<h1 class="brief-title">{esc(title)}</h1>')
            i += 1
            continue

        # H2 (章节)
        if line.startswith("## "):
            heading = line[3:].strip()
            section_idx += 1
            sid = f"sec-{section_idx}"
            color_key = SECTION_PALETTE[min(section_idx - 1, len(SECTION_PALETTE) - 1)]
            icon = SECTION_ICONS[min(section_idx - 1, len(SECTION_ICONS) - 1)]
            label = SECTION_LABELS[min(section_idx - 1, len(SECTION_LABELS) - 1)] if section_idx <= len(SECTION_LABELS) else f"§{section_idx}"
            # heading 兼容 "⚡ 4. 拜访要点 3 条" 这种
            toc.append((sid, heading, icon))
            out.append(
                f'<section id="{sid}" class="brief-section sec-{color_key}" data-sec="{section_idx}">'
                f'<header class="sec-head">'
                f'<span class="sec-icon">{icon}</span>'
                f'<span class="sec-num">§{section_idx}</span>'
                f'<h2 class="sec-title">{esc(heading)}</h2>'
                f'<span class="sec-tag">{esc(label)}</span>'
                f'</header>'
                f'<div class="sec-body">'
            )
            i += 1
            continue

        # H3 (子章节,在 §5 数据来源下出现)
        if line.startswith("### "):
            sub = line[4:].strip()
            out.append(f'<h3 class="sub-head">{esc(sub)}</h3>')
            i += 1
            continue

        # H4
        if line.startswith("#### "):
            sub = line[5:].strip()
            out.append(f'<h4 class="micro-head">{esc(sub)}</h4>')
            i += 1
            continue

        # HR
        if line.strip() == "---":
            i += 1
            continue

        # 表格: 表头 | 分隔行 | N 数据行
        if "|" in line and i + 1 < n and TABLE_SEP.match(lines[i + 1]):
            header_cells = [c.strip() for c in line.strip().strip("|").split("|")]
            i += 2  # 跳过分隔行
            rows = []
            while i < n and "|" in lines[i] and lines[i].strip():
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                rows.append(cells)
                i += 1
            # 渲染
            is_visit_section = (section_idx == 4)
            is_recent = (section_idx == 3)
            if is_visit_section:
                # 拜访要点:数字 list
                out.append('<ol class="visit-list">')
                for ri, row in enumerate(rows):
                    title_txt = row[0] if len(row) > 0 else ""
                    body_txt = " ".join(row[1:]) if len(row) > 1 else ""
                    out.append(
                        f'<li class="visit-card">'
                        f'<div class="visit-num">0{ri + 1}</div>'
                        f'<div class="visit-body">'
                        f'<div class="visit-title">{inline_md(title_txt)}</div>'
                        f'<div class="visit-text">{inline_md(body_txt)}</div>'
                        f'</div>'
                        f'</li>'
                    )
                out.append('</ol>')
            elif is_recent and len(header_cells) >= 4:
                # 近期动态:时间线卡片
                out.append('<div class="timeline">')
                for row in rows:
                    t = row[0] if len(row) > 0 else ""
                    cat = row[1] if len(row) > 1 else ""
                    ev = row[2] if len(row) > 2 else ""
                    src = row[3] if len(row) > 3 else ""
                    cat_color = classify_category(cat)
                    out.append(
                        f'<div class="tl-item">'
                        f'<div class="tl-date">{esc(t)}</div>'
                        f'<div class="tl-cat cat-{cat_color}">{esc(cat)}</div>'
                        f'<div class="tl-event">{inline_md(ev)}</div>'
                        f'<div class="tl-src">{esc(src)}</div>'
                        f'</div>'
                    )
                out.append('</div>')
            elif len(header_cells) >= 3 and header_cells[-1] in ("来源", "Source", "source"):
                # 通用 dim/key/value/源 卡片
                # §2 组织股权:按字段自动归类 (gov=治理 / cap=资本) 加左侧色条
                gov_keys = ("法定代表人", "董事长", "总经理", "党委副书记", "高管", "CEO", "总裁", "管理")
                cap_keys = ("注册资本", "股权", "股东", "出资", "融资", "估值", "资本")
                org_keys = ("总部", "地址", "成立", "员工", "规模", "组织")
                out.append('<div class="dim-grid">')
                for row in rows:
                    dim = row[0] if len(row) > 0 else ""
                    val = row[1] if len(row) > 1 else ""
                    src = row[2] if len(row) > 2 else ""
                    extra_cls = ""
                    group_tag = ""
                    if section_idx == 2:
                        if any(k in dim for k in gov_keys):
                            extra_cls = " gov"
                            group_tag = '<span class="dim-group">治理</span>'
                        elif any(k in dim for k in cap_keys):
                            extra_cls = " cap"
                            group_tag = '<span class="dim-group">资本</span>'
                        elif any(k in dim for k in org_keys):
                            group_tag = '<span class="dim-group">组织</span>'
                    out.append(
                        f'<div class="dim-card{extra_cls}">'
                        f'<div class="dim-key">{group_tag}{esc(dim)}</div>'
                        f'<div class="dim-val">{inline_md(val)}</div>'
                        f'<div class="dim-src">{esc(src)}</div>'
                        f'</div>'
                    )
                out.append('</div>')
            else:
                # 兜底:原样 <table>
                out.append('<div class="raw-table-wrap"><table class="raw-table">')
                out.append('<thead><tr>' + ''.join(f'<th>{esc(h)}</th>' for h in header_cells) + '</tr></thead>')
                out.append('<tbody>')
                for row in rows:
                    out.append('<tr>' + ''.join(f'<td>{inline_md(c)}</td>' for c in row) + '</tr>')
                out.append('</tbody></table></div>')
            continue

        # blockquote (含 🚫/⚡/🟢🟡🔴)
        if line.startswith(">"):
            buf = []
            while i < n and lines[i].startswith(">"):
                buf.append(lines[i].lstrip(">").lstrip())
                i += 1
            joined = " ".join(buf).strip()
            banner_class, banner_icon = classify_quote(joined)
            out.append(
                f'<div class="quote-banner {banner_class}">'
                f'<span class="q-icon">{banner_icon}</span>'
                f'<div class="q-body">{inline_md(joined)}</div>'
                f'</div>'
            )
            continue

        # 列表
        if re.match(r"^\s*[-*]\s", line):
            items = []
            while i < n and re.match(r"^\s*[-*]\s", lines[i]):
                items.append(re.sub(r"^\s*[-*]\s", "", lines[i]))
                i += 1
            out.append('<ul class="md-list">' + ''.join(f'<li>{inline_md(it)}</li>' for it in items) + '</ul>')
            continue

        # 数字列表(支持子条目 - 或   -)—— 用于拜访要点结构
        if re.match(r"^\s*\d+[\.、]\s", line):
            items = []
            current = None
            while i < n:
                ln = lines[i]
                if re.match(r"^\s*\d+[\.、]\s", ln):
                    if current is not None:
                        items.append(current)
                    current = {"main": re.sub(r"^\s*\d+[\.、]\s", "", ln), "subs": []}
                    i += 1
                elif re.match(r"^\s*[-*]\s", ln) and current is not None:
                    current["subs"].append(re.sub(r"^\s*[-*]\s", "", ln))
                    i += 1
                elif ln.strip() == "" and i + 1 < n:
                    # 空行: 下一行是新主条目 / 子条目 / 新章节, 则停
                    nxt = lines[i + 1]
                    if re.match(r"^\s*\d+[\.、]\s", nxt) or re.match(r"^\s*[-*]\s", nxt) or nxt.startswith("#"):
                        i += 1
                        break
                    else:
                        i += 1
                elif ln.strip() == "":
                    i += 1
                else:
                    # 续行(本行不是新条目开头也没空行)
                    if current is not None:
                        if current["subs"]:
                            current["subs"][-1] += " " + ln.strip()
                        else:
                            current["main"] += " " + ln.strip()
                    i += 1
            if current is not None:
                items.append(current)
            # §4 拜访要点渲染:大数字 + 标题 + 子项
            if section_idx == 4:
                out.append('<ol class="visit-list">')
                for vi, item in enumerate(items):
                    title_txt = item["main"]
                    sub_html = "".join(f'<div class="visit-sub">{inline_md(s)}</div>' for s in item["subs"])
                    out.append(
                        f'<li class="visit-card">'
                        f'<div class="visit-num">0{vi + 1}</div>'
                        f'<div class="visit-body">'
                        f'<div class="visit-title">{inline_md(title_txt)}</div>'
                        f'{sub_html}'
                        f'</div>'
                        f'</li>'
                    )
                out.append('</ol>')
            else:
                # 普通数字列表
                out.append('<ol class="md-list num">' + "".join(f'<li>{inline_md(it["main"])}</li>' for it in items) + '</ol>')
            continue

        # 空行
        if not line.strip():
            i += 1
            continue

        # 段落
        buf = []
        while i < n and lines[i].strip() and not (
            lines[i].startswith("#") or lines[i].startswith(">") or
            lines[i].startswith("---") or "|" in lines[i] and i + 1 < n and TABLE_SEP.match(lines[i + 1] if i + 1 < n else "")
        ):
            buf.append(lines[i])
            i += 1
        if buf:
            para = " ".join(buf)
            out.append(f'<p class="md-p">{inline_md(para)}</p>')

    # 关闭 § 段最后一个 sec-body / section
    body = "".join(out)
    # 找最后一个 <section 的 div.sec-body,补 close
    body = body.replace('<div class="sec-body">', '<div class="sec-body">', 0)
    # 简易 close:在文件末尾添加缺失的闭合
    open_secs = body.count('<section ')
    close_secs = body.count('</section>')
    if open_secs > close_secs:
        body += ('</div>' * (open_secs - close_secs)) + ('</section>' * (open_secs - close_secs))
    return body, toc


# ---------------- inline markdown: 粗体 / 链接 ----------------
LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
BOLD_RE = re.compile(r"\*\*([^*]+)\*\*")
EMOJI_RE = re.compile(r"([\U0001F300-\U0001FAFF\U00002600-\U000027BF])")


def inline_md(text: str) -> str:
    if not text:
        return ""
    # 先 escape,但保留 markdown 标记
    s = text
    # 链接:把 [text](url) 替换成 <a> 同时收集源 url 用于 source 列表 (这里仅渲染)
    def link_sub(m: re.Match) -> str:
        t, u = m.group(1), m.group(2)
        domain = url_to_domain(u)
        return f'<a class="md-link" href="{html.escape(u)}" target="_blank" rel="noopener">{html.escape(t)}<span class="md-link-domain"> · {html.escape(domain)}</span></a>'
    s = LINK_RE.sub(link_sub, s)
    # 粗体
    s = BOLD_RE.sub(r'<strong>\1</strong>', s)
    # 其他字符 escape(但保留已转义的标签)
    parts = re.split(r"(<a class=\"md-link\".*?</a>|<strong>.*?</strong>)", s)
    out_parts = []
    for p in parts:
        if p.startswith("<a ") or p.startswith("<strong>"):
            out_parts.append(p)
        else:
            out_parts.append(html.escape(p).replace("\n", "<br>"))
    return "".join(out_parts)


def url_to_domain(url: str) -> str:
    try:
        u = urllib.parse.urlparse(url)
        host = u.netloc or u.path
        return host.replace("www.", "")
    except Exception:
        return url


# ---------------- blockquote 分类 ----------------
def classify_quote(text: str) -> tuple[str, str]:
    if any(c in text for c in ("🚫", "未找到", "阻塞", "失败", "无法")):
        return "q-rust", "🚫"
    if any(c in text for c in ("⚡", "钩子", "拜访钩子", "重点", "现场")):
        return "q-clay", "⚡"
    if "🟢" in text:
        return "q-sky", "🟢"
    if "🟡" in text:
        return "q-olive", "🟡"
    if "🔴" in text:
        return "q-rust", "🔴"
    if "💡" in text:
        return "q-olive", "💡"
    if "📌" in text:
        return "q-sky", "📌"
    if "✅" in text:
        return "q-olive", "✅"
    if "❗" in text or "❕" in text:
        return "q-clay", "❗"
    # 默认
    return "q-sky", "💬"


# ---------------- 近期动态分类着色 ----------------
def classify_category(cat: str) -> str:
    cat = cat.strip()
    rules = [
        (("战略", "Strategic"), "rust"),
        (("融资", "投资", "Finance", "Funding"), "olive"),
        (("产品", "Product"), "clay"),
        (("产能", "里程碑", "Capacity"), "purple"),
        (("供应链", "定点", "Supply"), "sky"),
        (("人事", "高管", "People"), "olive"),
        (("AI", "数字化", "Tech"), "sky"),
        (("合规", "危机", "Compliance"), "rust"),
        (("行业地位", "Brand"), "olive"),
        (("合作", "Partnership"), "sky"),
        (("行业活动", "Event"), "gray500"),
    ]
    for keys, color in rules:
        if any(k in cat for k in keys):
            return color
    return "gray500"


# ---------------- 完整页面模板 ----------------
def render_page(body_html: str, title: str, meta: dict, toc: "list[tuple[str, str, str]]", source_date: str, source_slug: str) -> str:
    """meta: {生成时间, 调研档位, 有效期, 上一次调研, 主体确认}"""
    meta_block = render_meta_block(meta)
    toc_block = render_toc(toc)

    css = build_css()

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)} · 客户尽调简报</title>
<style>{css}</style>
</head>
<body>
<div class="page">

<header class="brief-header">
  <div class="brief-kicker">📋 Customer Pre-Visit Briefing</div>
  <h1 class="brief-title">{html.escape(title)}</h1>
  <div class="brief-meta">
    {meta_block}
  </div>
  <div class="brief-actions">
    <a class="btn btn-ghost" href="https://github.com/binbinao/customer-pre-briefs/tree/main/{source_slug}/{source_date}.md">📝 查看 Markdown 源</a>
    <a class="btn btn-ghost" href="https://github.com/binbinao/customer-pre-briefs/commit/main" target="_blank" rel="noopener">🔗 提交历史</a>
    <a class="btn btn-ghost" href="/customer-pre-briefs/">← 返回简报索引</a>
  </div>
</header>

<aside class="toc-rail" aria-label="目录">
  <div class="toc-rail-inner">
    <div class="toc-label">目录</div>
    {toc_block}
  </div>
</aside>

<main class="brief-body">
{body_html}
</main>

<footer class="brief-foot">
  <p>本简报由 Hermes Agent <code>customer-pre-brief</code> skill 自动生成 · 7 天有效期 · 适合销售/BD 拜访前 5 分钟速读</p>
  <p class="muted">Generated at {html.escape(source_date)} · 视觉与索引站保持一致</p>
</footer>

</div>
<script>
// scroll-spy for TOC
(function(){{
  const secs = document.querySelectorAll('.brief-section');
  const links = document.querySelectorAll('.toc-rail a');
  const map = new Map();
  secs.forEach(s => map.set(s.id, links));
  function spy(){{
    const y = window.scrollY + 120;
    let active = null;
    secs.forEach(s => {{
      if (s.offsetTop <= y) active = s.id;
    }});
    links.forEach(a => a.classList.toggle('active', a.getAttribute('href') === '#' + active));
  }}
  window.addEventListener('scroll', spy, {{ passive: true }});
  spy();
}})();
</script>
</body>
</html>
"""


def render_meta_block(meta: dict) -> str:
    items = []
    order = [("生成时间", "🕐"), ("调研档位", "🔬"), ("有效期", "📅"), ("上一次调研", "🔁"), ("主体确认", "🎯")]
    for k, icon in order:
        if k in meta and meta[k]:
            items.append(
                f'<div class="meta-item"><span class="meta-icon">{icon}</span>'
                f'<span class="meta-key">{html.escape(k)}</span>'
                f'<span class="meta-val">{html.escape(meta[k])}</span></div>'
            )
    return "".join(items)


def render_toc(toc: list) -> str:
    if not toc:
        return ""
    items = []
    for sid, heading, icon in toc:
        # 截短章节标题做 toc label
        short = re.sub(r"^[\W_]+", "", heading)
        short = re.sub(r"\s+\d+(\.\d+)*\s*", " ", short)
        items.append(f'<a href="#{sid}" class="toc-link"><span class="toc-icon">{icon}</span><span class="toc-text">{html.escape(short)}</span></a>')
    return "".join(items)


def build_css() -> str:
    t = TOKENS
    return f"""
  :root {{
    --bg: {t['bg']}; --card: {t['card']}; --text: {t['text']};
    --clay: {t['clay']}; --olive: {t['olive']}; --rust: {t['rust']};
    --sky: {t['sky']}; --purple: {t['purple']};
    --gray-100: {t['gray100']}; --gray-300: {t['gray300']};
    --gray-500: {t['gray500']}; --gray-700: {t['gray700']};
    --border: 1.5px solid var(--gray-300);
    --radius: 12px;
  }}
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  html {{ scroll-behavior: smooth; }}
  body {{ background:var(--bg); color:var(--text); font-family:system-ui,-apple-system,"Microsoft YaHei",sans-serif;
         font-size:15px; line-height:1.65; padding:32px 20px 80px; }}
  .page {{ max-width:980px; margin:0 auto; position:relative; }}

  /* header */
  .brief-header {{ text-align:center; margin-bottom:32px; padding-bottom:24px; border-bottom:var(--border); }}
  .brief-kicker {{ font-size:12px; letter-spacing:.18em; color:var(--gray-500); text-transform:uppercase; margin-bottom:8px; }}
  .brief-title {{ font-size:30px; font-weight:600; color:var(--text); margin-bottom:14px; line-height:1.3; }}
  .brief-meta {{ display:flex; flex-wrap:wrap; gap:10px 18px; justify-content:center; margin-bottom:18px; }}
  .meta-item {{ display:inline-flex; align-items:center; gap:6px; padding:6px 12px; background:var(--card); border:var(--border); border-radius:20px; font-size:13px; }}
  .meta-icon {{ font-size:13px; }}
  .meta-key {{ color:var(--gray-500); font-size:12px; }}
  .meta-val {{ color:var(--text); font-weight:500; }}
  .brief-actions {{ display:flex; gap:8px; justify-content:center; flex-wrap:wrap; }}
  .btn {{ display:inline-block; padding:6px 14px; border-radius:18px; font-size:13px; text-decoration:none; transition:all .2s; }}
  .btn-ghost {{ background:var(--card); border:var(--border); color:var(--gray-700); }}
  .btn-ghost:hover {{ border-color:var(--clay); color:var(--clay); background:var(--gray-100); }}

  /* TOC rail */
  .toc-rail {{ position:sticky; top:24px; float:right; width:200px; margin:0 0 24px 24px; z-index:5; }}
  .toc-rail-inner {{ background:var(--card); border:var(--border); border-radius:var(--radius); padding:14px 12px; }}
  .toc-label {{ font-size:11px; color:var(--gray-500); text-transform:uppercase; letter-spacing:.15em; margin-bottom:10px; padding-left:4px; }}
  .toc-link {{ display:flex; align-items:center; gap:8px; padding:7px 8px; border-radius:8px; font-size:13px; color:var(--gray-700); text-decoration:none; transition:all .15s; }}
  .toc-link:hover {{ background:var(--gray-100); color:var(--text); }}
  .toc-link.active {{ background:rgba(217,119,87,.1); color:var(--clay); font-weight:600; }}
  .toc-icon {{ flex-shrink:0; font-size:14px; }}
  .toc-text {{ overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }}

  /* main */
  .brief-body {{ max-width:740px; }}

  /* sections */
  .brief-section {{ background:var(--card); border:var(--border); border-radius:var(--radius);
                    padding:22px 26px; margin-bottom:24px; position:relative; overflow:hidden; }}
  .brief-section::before {{ content:""; position:absolute; top:0; left:0; width:4px; height:100%; background:var(--section-color, var(--gray-300)); }}
  .sec-sky {{ --section-color: var(--sky); }}
  .sec-olive {{ --section-color: var(--olive); }}
  .sec-rust {{ --section-color: var(--rust); }}
  .sec-clay {{ --section-color: var(--clay); }}
  .sec-gray500 {{ --section-color: var(--gray-500); }}

  .sec-head {{ display:flex; align-items:center; gap:10px; margin-bottom:16px; padding-bottom:12px; border-bottom:1px dashed var(--gray-300); }}
  .sec-icon {{ font-size:22px; flex-shrink:0; }}
  .sec-num {{ font-size:11px; color:var(--gray-500); font-family:monospace; letter-spacing:.1em; padding:3px 7px; background:var(--gray-100); border-radius:4px; }}
  .sec-title {{ font-size:20px; font-weight:600; color:var(--text); flex:1; }}
  .sec-tag {{ font-size:11px; color:var(--gray-500); padding:3px 8px; border:1px solid var(--gray-300); border-radius:10px; }}
  .sec-body {{ color:var(--text); }}

  .sub-head {{ font-size:16px; font-weight:600; color:var(--text); margin:18px 0 10px; padding-left:10px; border-left:3px solid var(--sky); }}
  .micro-head {{ font-size:14px; font-weight:600; color:var(--gray-700); margin:14px 0 6px; }}

  /* paragraphs */
  .md-p {{ margin-bottom:10px; color:var(--gray-700); }}
  .md-p strong {{ color:var(--text); font-weight:600; }}

  /* md links */
  .md-link {{ color:var(--sky); text-decoration:none; border-bottom:1px solid rgba(91,139,160,.3); transition:all .15s; }}
  .md-link:hover {{ color:var(--clay); border-bottom-color:var(--clay); }}
  .md-link-domain {{ font-size:11px; color:var(--gray-500); margin-left:2px; }}

  /* lists */
  .md-list {{ padding-left:20px; margin:8px 0; color:var(--gray-700); }}
  .md-list li {{ margin-bottom:4px; }}
  .md-list.num {{ padding-left:24px; }}

  /* blockquote banners */
  .quote-banner {{ display:flex; gap:12px; align-items:flex-start; padding:12px 16px; border-radius:10px;
                   margin:12px 0; font-size:14px; line-height:1.6; border:1.5px solid; }}
  .quote-banner .q-icon {{ font-size:18px; flex-shrink:0; line-height:1.6; }}
  .quote-banner .q-body {{ flex:1; }}
  .q-sky {{ background:rgba(91,139,160,.08); border-color:rgba(91,139,160,.4); color:var(--text); }}
  .q-olive {{ background:rgba(120,140,93,.08); border-color:rgba(120,140,93,.4); color:var(--text); }}
  .q-clay {{ background:rgba(217,119,87,.1); border-color:rgba(217,119,87,.5); color:var(--text); font-weight:500; }}
  .q-rust {{ background:rgba(176,74,63,.08); border-color:rgba(176,74,63,.4); color:var(--text); }}
  .q-clay strong, .q-rust strong {{ color:inherit; }}

  /* dim grid (§1 §2) */
  .dim-grid {{ display:grid; gap:10px; margin-top:8px; }}
  .dim-card {{ display:grid; grid-template-columns:120px 1fr 200px; gap:14px;
               padding:14px 16px; background:var(--bg); border-radius:8px; border:1px solid var(--gray-100);
               transition:all .15s; align-items:start; min-height:64px; }}
  .dim-card:hover {{ border-color:var(--clay); background:var(--card); }}
  .dim-card .dim-group {{ display:inline-block; font-size:10px; padding:1px 6px; border-radius:3px;
                          background:var(--gray-100); color:var(--gray-500); margin-bottom:4px; }}
  .dim-card.gov {{ border-left:3px solid var(--olive); }}
  .dim-card.cap {{ border-left:3px solid var(--purple); }}
  .dim-key {{ color:var(--sky); font-weight:600; font-size:13px; padding-top:2px; }}
  .dim-val {{ color:var(--text); font-size:14px; line-height:1.65; }}
  .dim-val strong {{ color:var(--clay); }}
  .dim-src {{ color:var(--gray-500); font-size:11px; padding-top:4px; font-family:monospace;
              word-break:break-all; }}

  /* timeline (§3) */
  .timeline {{ position:relative; padding-left:8px; margin-top:6px; }}
  .timeline::before {{ content:""; position:absolute; left:80px; top:8px; bottom:8px; width:2px; background:var(--gray-300); }}
  .tl-item {{ display:grid; grid-template-columns:74px 110px 1fr; gap:14px;
              padding:10px 12px; margin-bottom:8px; border-radius:8px; transition:all .15s;
              align-items:start; position:relative; }}
  .tl-item:hover {{ background:var(--bg); }}
  .tl-item::before {{ content:""; position:absolute; left:78px; top:16px; width:8px; height:8px; border-radius:50%; background:var(--clay); border:2px solid var(--card); }}
  .tl-date {{ font-family:monospace; color:var(--sky); font-weight:600; font-size:13px; padding-top:1px; }}
  .tl-cat {{ font-size:11px; padding:3px 8px; border-radius:10px; display:inline-block; text-align:center; font-weight:500; }}
  .cat-rust {{ background:rgba(176,74,63,.12); color:var(--rust); }}
  .cat-clay {{ background:rgba(217,119,87,.12); color:var(--clay); }}
  .cat-olive {{ background:rgba(120,140,93,.12); color:var(--olive); }}
  .cat-sky {{ background:rgba(91,139,160,.12); color:var(--sky); }}
  .cat-purple {{ background:rgba(139,107,158,.12); color:var(--purple); }}
  .cat-gray500 {{ background:var(--gray-100); color:var(--gray-500); }}
  .tl-event {{ color:var(--text); font-size:14px; line-height:1.6; }}
  .tl-event strong {{ color:var(--clay); }}
  .tl-src {{ grid-column:1/-1; padding-left:200px; color:var(--gray-500); font-size:11px; font-family:monospace; }}

  /* visit list (§4) */
  .visit-list {{ list-style:none; padding:0; margin:0; counter-reset:visit; }}
  .visit-card {{ display:grid; grid-template-columns:60px 1fr; gap:14px; padding:14px 16px;
                 margin-bottom:10px; border-radius:10px; background:linear-gradient(135deg, rgba(217,119,87,.06), rgba(217,119,87,.02));
                 border:1.5px solid rgba(217,119,87,.3); position:relative; }}
  .visit-card:hover {{ border-color:var(--clay); box-shadow:0 2px 8px rgba(217,119,87,.1); }}
  .visit-num {{ font-family:"Georgia",serif; font-size:32px; font-weight:700; color:var(--clay); line-height:1; padding-top:2px; }}
  .visit-body {{ color:var(--text); }}
  .visit-title {{ font-weight:600; font-size:15px; color:var(--text); margin-bottom:6px; }}
  .visit-text {{ font-size:13.5px; color:var(--gray-700); line-height:1.7; }}
  .visit-text strong {{ color:var(--clay); }}
  .visit-sub {{ font-size:13px; color:var(--gray-700); line-height:1.7; margin-top:6px; padding-left:10px; border-left:2px solid rgba(217,119,87,.3); }}
  .visit-sub strong {{ color:var(--clay); }}
  .visit-sub::before {{ content:"· "; color:var(--clay); font-weight:bold; margin-right:4px; }}

  /* raw table fallback */
  .raw-table-wrap {{ overflow-x:auto; margin:10px 0; }}
  .raw-table {{ width:100%; border-collapse:collapse; font-size:13px; }}
  .raw-table th, .raw-table td {{ padding:8px 10px; border:1px solid var(--gray-300); text-align:left; }}
  .raw-table th {{ background:var(--gray-100); font-weight:600; }}

  /* source link styles (§5) */
  .sec-body ul.md-list {{ list-style:none; padding:0; }}
  .sec-body ul.md-list li {{ padding:10px 14px; margin-bottom:8px; background:var(--bg); border-radius:8px; border:1px solid var(--gray-100); }}
  .sec-body ul.md-list li:hover {{ border-color:var(--sky); }}

  /* footer */
  .brief-foot {{ text-align:center; margin-top:40px; padding-top:24px; border-top:var(--border); color:var(--gray-500); font-size:13px; }}
  .brief-foot .muted {{ margin-top:6px; font-size:11px; }}
  .brief-foot code {{ background:var(--gray-100); padding:1px 6px; border-radius:4px; font-size:12px; color:var(--gray-700); }}

  /* responsive */
  @media (max-width:820px) {{
    .toc-rail {{ display:none; }}
    .dim-card {{ grid-template-columns:1fr; }}
    .dim-key {{ padding-top:0; }}
    .dim-src {{ grid-column:auto; padding-top:0; }}
    .timeline::before {{ left:14px; }}
    .tl-item {{ grid-template-columns:1fr; gap:4px; }}
    .tl-item::before {{ display:none; }}
    .tl-src {{ padding-left:0; grid-column:auto; }}
  }}
  @media (max-width:600px) {{
    body {{ padding:20px 14px 60px; }}
    .brief-title {{ font-size:22px; }}
    .brief-section {{ padding:18px 18px; }}
    .visit-card {{ grid-template-columns:1fr; }}
    .visit-num {{ font-size:24px; }}
  }}
"""


# ---------------- header meta 解析 ----------------
META_RE = re.compile(r"^>\s*\*\*([^:]+):\*\*\s*(.+)$")


def extract_meta(md_text: str) -> tuple[dict, str]:
    """从 md 头部提取 metadata blockquote,返回 (meta_dict, 剩余 markdown)"""
    lines = md_text.splitlines()
    meta = {}
    end = 0
    for idx, line in enumerate(lines):
        if line.startswith("# "):
            continue
        if line.strip() == "":
            end = idx + 1
            continue
        if not line.startswith(">"):
            break
        m = META_RE.match(line)
        if m:
            meta[m.group(1).strip()] = m.group(2).strip()
        end = idx + 1
    return meta, "\n".join(lines[end:])


# ---------------- 主流程 ----------------
def main():
    if len(sys.argv) < 2:
        print("用法: python3 md2brief_html.py <input.md> [<output.html>]", file=sys.stderr)
        sys.exit(2)
    src = Path(sys.argv[1])
    if not src.is_file():
        print(f"找不到输入文件: {src}", file=sys.stderr)
        sys.exit(2)
    out = Path(sys.argv[2]) if len(sys.argv) >= 3 else src.with_suffix(".html")
    md_text = src.read_text(encoding="utf-8")
    meta, body_md = extract_meta(md_text)
    body_html, toc = md_to_html(body_md)
    # title 取第一个 H1
    title_m = re.search(r"^#\s+(.+)$", md_text, re.M)
    title = title_m.group(1).strip() if title_m else src.stem
    # source_date 取 md 文件名日期
    source_date = src.stem  # 默认是 YYYY-MM-DD
    slug = src.parent.name
    page = render_page(body_html, title, meta, toc, source_date, slug)
    out.write_text(page, encoding="utf-8")
    print(f"✅ {src} → {out}  ({len(page):,} chars, {len(toc)} sections)")


if __name__ == "__main__":
    main()