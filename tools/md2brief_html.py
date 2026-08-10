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

        # H2 (章节) — 进入新章节前先闭合上一节,保证 DOM 是真兄弟而非嵌套
        if line.startswith("## "):
            heading = line[3:].strip()
            # 先闭合上一节(若有)
            if section_idx > 0:
                out.append('</div></section>')
            section_idx += 1
            sid = f"sec-{section_idx}"
            color_key = SECTION_PALETTE[min(section_idx - 1, len(SECTION_PALETTE) - 1)]
            icon = SECTION_ICONS[min(section_idx - 1, len(SECTION_ICONS) - 1)]
            label = SECTION_LABELS[min(section_idx - 1, len(SECTION_LABELS) - 1)] if section_idx <= len(SECTION_LABELS) else f"§{section_idx}"
            # heading 兼容 "⚡ 4. 拜访要点 3 条" 这种
            toc.append((sid, heading, icon))
            # SPA: §1 默认显示, 其余加 .inactive (无 JS 时 CSS 用 .no-js 强制恢复)
            active_cls = "" if section_idx == 1 else " inactive"
            out.append(
                f'<section id="{sid}" role="tabpanel" aria-labelledby="tab-{sid}" class="brief-section sec-{color_key}{active_cls}" data-sec="{section_idx}">'
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
                        f'<div class="tl-item" tabindex="0">'
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
                        f'<div class="dim-card{extra_cls}" tabindex="0">'
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
        # 状态机: 持续吞入数字条目 + 子条目, 直到遇见 非空/非数字/非子项 行才一次性 emit
        if re.match(r"^\s*\d+[\.、]\s", line):
            items: list = []
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
                    # 空行:若下一行仍是数字/子条目/子项,继续; 否则停
                    nxt = lines[i + 1]
                    if re.match(r"^\s*\d+[\.、]\s", nxt) or re.match(r"^\s*[-*]\s", nxt):
                        i += 1  # 跳过空行, 继续
                    else:
                        # 出口: 不前进 i, 让外层重新处理这条空行(走"空行"分支)
                        break
                elif ln.strip() == "":
                    i += 1
                else:
                    # 续行(非数字非子项非空)
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
                        f'<div class="visit-num">{vi + 1:02d}</div>'
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
    # 每节都已在 H2 进入时显式闭合,这里只需补最末一节(若有)
    if section_idx > 0:
        body += '</div></section>'
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
def classify_customer_industry(name: str) -> tuple[str, str, str]:
    """简易关键词匹配: 返回 (industry_key, emoji, label)"""
    n = name.lower()
    if any(k in n for k in ("汽车", "车", "汽")):
        return ("auto", "🚗", "汽车 Tier 1")
    if any(k in n for k in ("芯", "半导", "ic")):
        return ("chip", "🔌", "芯片 / 半导体")
    if any(k in n for k in ("电池", "能源", "锂", "光伏")):
        return ("energy", "⚡", "能源 / 电池")
    return ("other", "🏢", "其他客户")


def build_customer_nav(root_dir: Path, current_slug: str, current_date: str) -> str:
    """扫 root_dir 下的客户子目录, 按行业分组渲染导航, 当前简报对应客户 .active"""
    if not root_dir.is_dir():
        return ""
    customers: list[dict] = []
    for entry in sorted(root_dir.iterdir(), key=lambda p: p.name):
        if not entry.is_dir() or entry.name.startswith(".") or entry.name in ("tools", ".git"):
            continue
        # 找最新的简报日期
        dates = sorted(
            [p.stem for p in entry.iterdir()
             if p.is_file() and re.match(r"^\d{4}-\d{2}-\d{2}\.md$", p.name)],
            reverse=True,
        )
        if not dates:
            continue
        latest = dates[0]
        ind_key, ind_emoji, ind_label = classify_customer_industry(entry.name)
        customers.append({
            "slug": entry.name,
            "name": entry.name,
            "industry_key": ind_key,
            "industry_emoji": ind_emoji,
            "industry_label": ind_label,
            "latest": latest,
            "active": (entry.name == current_slug and latest == current_date),
        })
    if not customers:
        return ""
    # 按行业分组 (顺序: auto, chip, energy, other)
    order = [("auto", "🚗", "汽车 Tier 1"),
             ("chip", "🔌", "芯片 / 半导体"),
             ("energy", "⚡", "能源 / 电池"),
             ("other", "🏢", "其他客户")]
    parts: list[str] = []
    for ind_key, ind_emoji, ind_label in order:
        in_group = [c for c in customers if c["industry_key"] == ind_key]
        if not in_group:
            continue
        parts.append(f'<div class="nav-group-label">{ind_emoji} {html.escape(ind_label)}</div>')
        parts.append('<ul class="nav-list">')
        for c in in_group:
            cls = "nav-link active" if c["active"] else "nav-link"
            aria = ' aria-current="page"' if c["active"] else ""
            href = f"/customer-pre-briefs/{urllib.parse.quote(c['slug'])}/{c['latest']}.html"
            parts.append(
                f'<li><a class="{cls}"{aria} href="{href}">'
                f'<span class="nav-emoji">{ind_emoji}</span>'
                f'<span class="nav-name">{html.escape(c["name"])}</span>'
                f'<span class="nav-date">{html.escape(c["latest"])}</span>'
                f'</a></li>'
            )
        parts.append('</ul>')
    return "".join(parts)


def render_sec_tabs(toc: "list[tuple[str, str, str]]") -> str:
    """顶部 tab 条:与左 sidebar toc 双重入口, 与 section 一一对应"""
    if not toc:
        return ""
    items = []
    for i, (sid, heading, icon) in enumerate(toc):
        short = re.sub(r"^\s*(?:[\W_]*\d+[\.、]?\s*)+", "", heading).strip() or heading
        cls = "sec-tab active" if i == 0 else "sec-tab"
        aria = ' aria-selected="true"' if i == 0 else ' aria-selected="false"'
        tab_id = f"tab-{sid}"
        items.append(
            f'<button type="button" id="{tab_id}" class="{cls}" role="tab" data-target="{sid}"{aria} aria-controls="{sid} tabpanel-{sid}">'
            f'<span class="sec-tab-icon">{icon}</span>'
            f'<span class="sec-tab-label">{html.escape(short)}</span>'
            f'</button>'
        )
    return f'<nav class="sec-tabs" role="tablist" aria-label="章节导航">{ "".join(items) }</nav>'


def render_page(body_html: str, title: str, meta: dict, toc: "list[tuple[str, str, str]]",
                source_date: str, source_slug: str, root_dir: Path | None = None) -> str:
    """meta: {生成时间, 调研档位, 有效期, 上一次调研, 主体确认}"""
    meta_block = render_meta_block(meta)
    toc_block = render_toc(toc)
    if root_dir is None:
        root_dir = Path(__file__).resolve().parent.parent
    customer_nav_html = build_customer_nav(root_dir, source_slug, source_date)
    sec_tabs_html = render_sec_tabs(toc)

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

<aside class="sidebar" aria-label="详情页导航">
  <div class="sidebar-inner">
    <section class="sidebar-block sidebar-toc">
      <div class="sidebar-label">📑 章节</div>
      {toc_block}
    </section>
    <section class="sidebar-block sidebar-nav">
      <div class="sidebar-label">📂 客户导航</div>
      {customer_nav_html}
    </section>
    <section class="sidebar-block sidebar-back">
      <a class="sidebar-back-link" href="https://binbinao.github.io/customer-pre-briefs/">🔙 返回主页</a>
    </section>
  </div>
</aside>

<nav class="toc-rail" aria-label="目录">
  <div class="toc-rail-inner">
    <div class="toc-label">目录</div>
    {toc_block}
  </div>
</nav>

<main class="brief-body">
{sec_tabs_html}
{body_html}
</main>

<footer class="brief-foot">
  <p>本简报由 Hermes Agent <code>customer-pre-brief</code> skill 自动生成 · 7 天有效期 · 适合销售/BD 拜访前 5 分钟速读</p>
  <p class="muted">Generated at {html.escape(source_date)} · 视觉与索引站保持一致</p>
</footer>

</div>
<noscript>
  <style>
    /* 无 JS 时: 隐藏顶部 tab 条, 强制所有章节显示 (退化到 v2 行为) */
    .sec-tabs {{ display: none !important; }}
    .brief-section.inactive {{ display: block !important; }}
  </style>
</noscript>
<script>
// ============= SPA 章节切换 + URL hash 路由 + 双重入口联动 =============
(function(){{
  const sections = Array.from(document.querySelectorAll('.brief-section'));
  const tabs = Array.from(document.querySelectorAll('.sec-tab'));
  const tocLinks = Array.from(document.querySelectorAll('.toc-rail a, .sidebar-toc a'));
  const firstId = sections.length ? sections[0].id : 'sec-1';

  function showSection(secId){{
    secId = secId || firstId;
    // 找不到目标时回落第一章节
    if (!document.getElementById(secId)) secId = firstId;

    // 1. 切 section 显示
    sections.forEach(s => {{
      if (s.id === secId) {{
        s.classList.remove('inactive');
        s.setAttribute('aria-hidden', 'false');
      }} else {{
        s.classList.add('inactive');
        s.setAttribute('aria-hidden', 'true');
      }}
    }});

    // 2. 切顶部 tab 激活态 + aria-selected
    tabs.forEach(t => {{
      const isActive = t.dataset.target === secId;
      t.classList.toggle('active', isActive);
      t.setAttribute('aria-selected', isActive ? 'true' : 'false');
      t.setAttribute('tabindex', isActive ? '0' : '-1');
    }});

    // 3. 切左/右 TOC anchor 激活态 + aria-current
    const hash = '#' + secId;
    tocLinks.forEach(a => {{
      const isActive = a.getAttribute('href') === hash;
      a.classList.toggle('active', isActive);
      if (isActive) a.setAttribute('aria-current', 'location');
      else a.removeAttribute('aria-current');
    }});

    // 4. 同步 URL hash (用 replaceState 避免污染历史)
    if (location.hash !== hash) {{
      try {{ history.replaceState(null, '', hash); }} catch (e) {{ location.hash = hash; }}
    }}

    // 5. SPA 模式下把目标 section 滚到顶 (左侧 sidebar 旁能看到), 仅在 section 距顶部较远时
    const target = document.getElementById(secId);
    if (target) {{
      const rect = target.getBoundingClientRect();
      // 只在 main 已滚动过 / 目标不在可视区内时滚动, 避免初次加载跳动
      if (Math.abs(rect.top) > 120) {{
        target.scrollIntoView({{ behavior: 'smooth', block: 'start' }});
      }}
    }}
  }}

  // ---- 顶部 tab 点击 ----
  tabs.forEach(btn => {{
    btn.addEventListener('click', () => showSection(btn.dataset.target));
  }});

  // ---- 左/右 sidebar TOC 点击 ----
  tocLinks.forEach(a => {{
    a.addEventListener('click', e => {{
      const href = a.getAttribute('href') || '';
      if (!href.startsWith('#')) return;
      e.preventDefault();
      const secId = href.slice(1);
      showSection(secId);
    }});
  }});

  // ---- URL hash 变化 (前进/后退 / 手动改) ----
  window.addEventListener('hashchange', () => {{
    showSection((location.hash || '').replace('#', '') || firstId);
  }});

  // ---- 键盘左右切换 (在 tab 上按 ←/→/Home/End) ----
  tabs.forEach((tab, idx) => {{
    tab.addEventListener('keydown', e => {{
      let next = null;
      if (e.key === 'ArrowRight') next = tabs[(idx + 1) % tabs.length];
      else if (e.key === 'ArrowLeft') next = tabs[(idx - 1 + tabs.length) % tabs.length];
      else if (e.key === 'Home') next = tabs[0];
      else if (e.key === 'End') next = tabs[tabs.length - 1];
      if (next) {{
        e.preventDefault();
        next.focus();
        showSection(next.dataset.target);
      }}
    }});
  }});

  // ---- 初始: 读 URL hash, 否则第一章节 ----
  const initial = (location.hash || '').replace('#', '') || firstId;
  showSection(initial);
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
        # 仅剥掉开头的章节编号 "1." / "2." / "⚡ 4." 等,不破坏括号内的数字
        short = re.sub(r"^\s*(?:[\W_]*\d+[\.、]?\s*)+", "", heading).strip()
        short = short or heading
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
    --r-sm: 8px;     /* dim-card / tl-item / quote-banner */
    --r-md: 14px;    /* visit-card / sec-body li 重点卡 */
    --r-lg: 18px;    /* visit-card 当前已 14, 保留 */
    --r-pill: 999px; /* meta-item / btn */
    --ease: cubic-bezier(0.16, 1, 0.3, 1);
    --dur-fast: 150ms;
    --dur-base: 250ms;
  }}

  /* ===== a11y: 全局 :focus-visible 描边 (skill 强制要求) ===== */
  *:focus-visible {{
    outline: 2px solid var(--clay);
    outline-offset: 2px;
  }}
  /* 不改 border-radius (skill 警告:会破坏 pill 几何) */
  a:focus-visible, button:focus-visible, .toc-link:focus-visible, .btn:focus-visible {{
    outline-offset: 3px;
  }}

  /* ===== a11y: 前庭敏感用户关闭所有过渡 ===== */
  @media (prefers-reduced-motion: reduce) {{
    html {{ scroll-behavior: auto; }}
    *, *::before, *::after {{
      animation-duration: 0.01ms !important;
      animation-iteration-count: 1 !important;
      transition-duration: 0.01ms !important;
      scroll-behavior: auto !important;
    }}
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
  /* SPA 隐藏非激活章节 (无 JS 走 <noscript> 强制恢复) */
  .brief-section.inactive {{ display:none; }}
  .brief-section::before {{ content:""; position:absolute; top:0; left:0; width:4px; height:100%; background:var(--section-color, var(--gray-300)); }}

  /* 顶部 tab 条 — SPA 双重入口 */
  .sec-tabs {{
    display:flex; gap:8px; align-items:center;
    background:var(--card); border:var(--border); border-radius:var(--radius);
    padding:6px; margin:0 0 18px;
    overflow-x:auto; -webkit-overflow-scrolling:touch;
    scroll-snap-type:x proximity; scrollbar-width:thin;
  }}
  .sec-tabs::-webkit-scrollbar {{ height:4px; }}
  .sec-tabs::-webkit-scrollbar-thumb {{ background:var(--gray-300); border-radius:2px; }}
  .sec-tab {{
    flex:0 0 auto; min-width:max-content; max-width:220px;
    display:inline-flex; align-items:center; gap:6px;
    padding:8px 12px; border-radius:var(--r-pill);
    background:transparent; border:0; cursor:pointer;
    color:var(--gray-700); font:inherit; font-size:13px; font-weight:500;
    scroll-snap-align:start;
    transition: background var(--dur-fast) var(--ease), color var(--dur-fast) var(--ease), transform var(--dur-fast) var(--ease), box-shadow var(--dur-fast) var(--ease);
  }}
  .sec-tab:hover {{ background:rgba(217,119,87,.10); color:var(--clay); }}
  .sec-tab:focus-visible {{ outline:2px solid var(--clay); outline-offset:2px; }}
  .sec-tab-icon {{ font-size:14px; line-height:1; }}
  .sec-tab-label {{ white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
  .sec-tab.active {{
    background:var(--clay); color:var(--card); font-weight:600;
    transform:translateY(-1px);
    box-shadow:0 4px 12px rgba(217,119,87,.32), inset 0 1px 0 rgba(255,255,255,.15);
  }}
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
  .md-p strong, .tl-event strong, .visit-text strong, .dim-val strong {{ color:var(--text); font-weight:600; }}

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
  .dim-card:hover, .dim-card:focus-within {{ border-color:var(--clay); background:var(--card); }}
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
  .visit-card {{ display:grid; grid-template-columns:60px 1fr; gap:14px; padding:16px 18px;
                 margin-bottom:12px; border-radius:14px;
                 background:linear-gradient(135deg, rgba(217,119,87,.14), rgba(217,119,87,.04));
                 border:2px solid rgba(217,119,87,.45);
                 box-shadow:0 4px 14px rgba(217,119,87,.08);
                 position:relative; transition:transform var(--dur-fast) var(--ease), box-shadow var(--dur-fast) var(--ease); }}
  .visit-card:hover, .visit-card:focus-within {{ border-color:var(--clay); box-shadow:0 8px 22px rgba(217,119,87,.18); transform:translateY(-1px); }}
  .visit-num {{ font-family:"Georgia",serif; font-size:42px; font-weight:700; color:var(--clay); line-height:1; padding-top:2px; letter-spacing:-.02em; }}
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
  /* 来源区文字提亮到 gray-700 (4.5:1 AA 通过,原 gray-500 只有 3.0:1) */
  .sec-body ul.md-list li, .sec-body ul.md-list li * {{ color:var(--gray-700); }}
  .sec-body .md-link {{ color:var(--sky); }}

  /* footer */
  .brief-foot {{ text-align:center; margin-top:40px; padding-top:24px; border-top:var(--border); color:var(--gray-500); font-size:13px; }}
  .brief-foot .muted {{ margin-top:6px; font-size:11px; }}
  .brief-foot code {{ background:var(--gray-100); padding:1px 6px; border-radius:4px; font-size:12px; color:var(--gray-700); }}

  /* responsive */
  /* 中等屏幕: dim-card 中间档 */
  @media (max-width:980px) {{
    .dim-card {{ grid-template-columns:100px 1fr 160px; }}
    .toc-rail {{ width:min(200px, 22vw); }}
  }}

  /* ===========================
   * 桌面 ≥1024px: 左右两栏布局
   * =========================== */
  @media (min-width:1024px) {{
    .page {{ max-width:1180px; display:grid; grid-template-columns:320px 1fr; column-gap:40px; row-gap:0; align-items:start; padding-top:8px; }}
    .brief-header {{ grid-column:1/-1; }}
    .brief-body {{ grid-column:2; max-width:760px; min-width:0; }}

    /* 桌面隐藏右侧浮动 TOC (章节搬到左侧 sidebar) */
    .toc-rail {{ display:none; }}

    /* 桌面: 顶部 tab 条 sticky 在 main 头部, 跟随滚动, 章节切换更稳 */
    .sec-tabs {{
      position:sticky; top:0; z-index:10;
      margin:0 0 18px;
      background:rgba(248,247,244,.92);
      backdrop-filter:saturate(180%) blur(10px);
      -webkit-backdrop-filter:saturate(180%) blur(10px);
      box-shadow:0 1px 0 var(--gray-300);
    }}

    /* sidebar 在桌面独占左列 */
    .sidebar {{
      grid-column:1;
      position:sticky;
      top:24px;
      align-self:start;
      max-height:calc(100vh - 48px);
      overflow-y:auto;
      padding-right:4px;
      margin-bottom:32px;
    }}
    .sidebar-inner {{
      display:flex;
      flex-direction:column;
      gap:18px;
    }}
    .sidebar-block {{
      background:var(--card);
      border:var(--border);
      border-radius:var(--radius);
      padding:14px 14px;
    }}
    .sidebar-label {{
      font-size:11px;
      color:var(--gray-500);
      text-transform:uppercase;
      letter-spacing:.15em;
      margin-bottom:10px;
      padding:0 4px;
      font-weight:600;
    }}

    /* 章节 toc-link (复用现有样式, 在 sidebar 内显示) */
    .sidebar-toc .toc-link {{ display:flex; }}

    /* 客户导航 */
    .sidebar-nav .nav-group-label {{
      font-size:11px;
      color:var(--gray-700);
      font-weight:600;
      letter-spacing:.04em;
      padding:6px 6px 4px;
      margin-top:4px;
    }}
    .sidebar-nav .nav-list {{ list-style:none; padding:0; margin:0 0 4px; }}
    .sidebar-nav .nav-list li {{ margin:0; }}
    .nav-link {{
      display:grid;
      grid-template-columns:18px 1fr auto;
      align-items:center;
      gap:8px;
      padding:7px 8px;
      border-radius:8px;
      font-size:13px;
      color:var(--gray-700);
      text-decoration:none;
      transition:all .15s;
    }}
    .nav-link:hover {{ background:var(--gray-100); color:var(--text); }}
    .nav-link.active {{ background:rgba(217,119,87,.12); color:var(--clay); font-weight:600; }}
    .nav-link.active .nav-emoji {{ filter:drop-shadow(0 0 1px rgba(217,119,87,.5)); }}
    .nav-emoji {{ font-size:14px; }}
    .nav-name {{ overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }}
    .nav-date {{ font-family:monospace; font-size:11px; color:var(--gray-500); }}

    /* 返回主页块 */
    .sidebar-back {{ padding:10px 12px; }}
    .sidebar-back-link {{
      display:flex; align-items:center; justify-content:center;
      gap:6px;
      padding:10px 14px;
      background:var(--bg);
      border:1.5px solid var(--gray-300);
      border-radius:10px;
      color:var(--gray-700);
      font-size:13px;
      font-weight:500;
      text-decoration:none;
      transition:all .15s;
    }}
    .sidebar-back-link:hover {{ border-color:var(--clay); color:var(--clay); background:var(--gray-100); }}

    /* footer 跨两列 */
    .brief-foot {{ grid-column:1/-1; }}
  }}

  /* 移动端: 顶部 tab 横滑 + 隐藏旧底部 tab bar (改由顶部 tab 承担) */
  @media (max-width:820px) {{
    /* 桌面 sidebar 在移动端隐藏 */
    .sidebar {{ display:none; }}

    /* 顶部 tab 条: 横滑 + scroll-snap, 替代旧底部 tab bar */
    .sec-tabs {{
      position:sticky; top:0; z-index:20;
      margin:0 -14px 16px;  /* 顶到屏幕边缘, 更横滑可见 */
      padding:6px 14px;
      background:rgba(248,247,244,.95);
      backdrop-filter:saturate(180%) blur(10px);
      -webkit-backdrop-filter:saturate(180%) blur(10px);
      box-shadow:0 1px 0 var(--gray-300);
      border-radius:0;
      border-left:0; border-right:0;
      overflow-x:auto; overflow-y:hidden;
      scroll-snap-type:x mandatory;
      -webkit-overflow-scrolling:touch;
    }}
    .sec-tab {{ scroll-snap-align:start; }}
    .sec-tab-icon {{ font-size:15px; }}

    /* 旧移动底部 tab bar 不再需要 (顶部 tab 已统一入口) */
    .toc-rail {{ display:none; }}
    body {{ padding-bottom:32px; }}
    .dim-card {{ grid-template-columns:1fr; }}
    .dim-key {{ padding-top:0; }}
    .dim-src {{ grid-column:auto; padding-top:0; }}
    .timeline::before {{ left:14px; }}
    .tl-item {{ grid-template-columns:1fr; gap:4px; }}
    .tl-item::before {{ display:none; }}
    .tl-src {{ padding-left:0; grid-column:auto; }}
  }}
  @media (max-width:600px) {{
    body {{ padding:20px 14px 100px; }}
    .brief-title {{ font-size:22px; }}
    .brief-section {{ padding:18px 18px; }}
    .visit-card {{ grid-template-columns:1fr; }}
    .visit-num {{ font-size:24px; }}
  }}
"""


# ---------------- header meta 解析 ----------------
META_RE = re.compile(r"^>\s*\*\*([^*]+)\*\*:\s*(.+)$")


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