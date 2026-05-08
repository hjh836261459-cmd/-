#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import email.utils
import html
import json
import os
import re
import smtplib
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from email.message import EmailMessage
from pathlib import Path

DEFAULT_MAIL = "hjh836261459@qq.com"
OUT_DIR = Path("out")
TZ = dt.timezone(dt.timedelta(hours=8))

CATEGORIES = [
    "今日要点",
    "技术与模型",
    "公司与产品新闻",
    "中国 AI/AIGC 动态",
    "政策、监管与安全",
    "投融资与产业",
    "应用与生态",
    "编辑观察",
]

CHINA_MARKERS = [
    "中国", "国内", "北京", "上海", "深圳", "杭州", "广州", "香港", "阿里", "百度", "腾讯", "华为",
    "字节", "豆包", "通义", "文心", "混元", "盘古", "Kimi", "月之暗面", "智谱", "阶跃星辰",
    "MiniMax", "商汤", "科大讯飞", "寒武纪", "机器之心", "量子位", "36氪", "晚点", "雷峰网",
    "网信办", "工信部", "科技部", "国家数据局", "新华社", "财新", "第一财经",
]

LOW_QUALITY_MARKERS = [
    "stock", "stocks", "price target", "downgrade", "upgrade", "shares", "nasdaq", "nyse",
    "coupon", "deal", "discount", "sponsored", "press release", "opinion", "horoscope",
]

QUERIES = [
    ("technology", "en", '("large language model" OR "AI model" OR "generative AI" OR "AI agent" OR "open source AI") when:1d'),
    ("company", "en", '(OpenAI OR Anthropic OR DeepMind OR "Google AI" OR Microsoft OR Meta OR Nvidia OR Apple) when:1d'),
    ("policy", "en", '("AI regulation" OR "AI safety" OR "AI policy" OR "AI copyright" OR "AI governance") when:1d'),
    ("industry", "en", '("AI startup" OR "AI funding" OR "AI chip" OR "AI data center" OR "AI investment") when:1d'),
    ("china", "zh", '(人工智能 OR AIGC OR 生成式AI OR 大模型) when:1d'),
    ("china", "zh", '(国产大模型 OR 多模态模型 OR 开源模型 OR 智能体) when:1d'),
    ("china", "zh", '(AI 算力 OR 智算中心 OR AI 芯片 OR 国产大模型) when:1d'),
    ("china", "zh", '(网信办 人工智能 OR 工信部 人工智能 OR AI 监管 OR 生成式AI 备案) when:1d'),
    ("industry", "zh", '(AI 融资 OR 大模型 融资 OR AIGC 投融资 OR AI 应用) when:1d'),
]

FALLBACK_CHINA_QUERIES = [
    '(人工智能 OR AIGC OR 大模型 OR 生成式AI) when:3d',
    '(阿里 通义 OR 百度 文心 OR 腾讯 混元 OR 字节 豆包 OR Kimi OR 智谱) when:3d',
    '(AI 算力 OR AI 芯片 OR 智算中心 OR 国产大模型) when:3d',
]

@dataclass
class NewsItem:
    title: str
    source: str
    published: dt.datetime | None
    link: str
    snippet: str
    query_group: str
    locale: str

    def record(self) -> dict[str, str]:
        return {
            "title": self.title,
            "source": self.source,
            "published": format_date(self.published),
            "link": self.link,
            "snippet": self.snippet,
            "query_group": self.query_group,
            "locale": self.locale,
        }


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, "").strip() or default


def now_cn() -> dt.datetime:
    return dt.datetime.now(TZ)


def clean(value: str) -> str:
    value = html.unescape(value or "")
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def parse_date(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    try:
        parsed = email.utils.parsedate_to_datetime(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        return parsed.astimezone(TZ)
    except Exception:
        return None


def format_date(value: dt.datetime | None) -> str:
    return value.strftime("%Y-%m-%d %H:%M") if value else "时间未标注"


def rss_url(query: str, locale: str) -> str:
    if locale == "zh":
        params = {"q": query, "hl": "zh-CN", "gl": "CN", "ceid": "CN:zh-Hans"}
    else:
        params = {"q": query, "hl": "en-US", "gl": "US", "ceid": "US:en"}
    return "https://news.google.com/rss/search?" + urllib.parse.urlencode(params)


def source_from(node: ET.Element, title: str) -> str:
    source = node.find("source")
    if source is not None and source.text:
        return clean(source.text)
    if " - " in title:
        return clean(title.rsplit(" - ", 1)[-1])
    return "Google News"


def fetch_items(group: str, locale: str, query: str, limit: int = 14) -> list[NewsItem]:
    request = urllib.request.Request(
        rss_url(query, locale),
        headers={"User-Agent": "Mozilla/5.0 ai-aigc-news-editor/2.0"},
    )
    with urllib.request.urlopen(request, timeout=25) as response:
        root = ET.fromstring(response.read())

    items: list[NewsItem] = []
    for node in root.findall("./channel/item")[:limit]:
        title = clean(node.findtext("title") or "")
        link = clean(node.findtext("link") or "")
        snippet = clean(node.findtext("description") or "")[:520]
        if not title or not link:
            continue
        items.append(
            NewsItem(
                title=title,
                source=source_from(node, title),
                published=parse_date(node.findtext("pubDate")),
                link=link,
                snippet=snippet,
                query_group=group,
                locale=locale,
            )
        )
    return items


def key_for(title: str) -> str:
    title = title.lower()
    title = re.sub(r"\s+-\s+[^-]{2,80}$", "", title)
    title = re.sub(r"[^\w\u4e00-\u9fff]+", "", title)
    return title[:120]


def contains_any(text: str, markers: list[str]) -> bool:
    text = text.lower()
    return any(marker.lower() in text for marker in markers)


def is_china(item: NewsItem) -> bool:
    return item.locale == "zh" or contains_any(f"{item.title} {item.source} {item.snippet}", CHINA_MARKERS)


def is_low_quality(item: NewsItem) -> bool:
    text = f"{item.title} {item.source} {item.snippet}".lower()
    if contains_any(text, LOW_QUALITY_MARKERS):
        return True
    if len(item.title) < 8:
        return True
    return False


def score(item: NewsItem) -> int:
    text = f"{item.title} {item.source} {item.snippet}".lower()
    points = 0
    high_signal = [
        "openai", "anthropic", "deepmind", "google", "microsoft", "nvidia", "meta", "apple",
        "model", "agent", "benchmark", "open source", "regulation", "safety", "funding", "chip", "data center",
        "大模型", "人工智能", "生成式", "智能体", "多模态", "开源", "算力", "芯片", "监管", "融资", "备案",
    ]
    points += sum(2 for word in high_signal if word in text)
    if is_china(item):
        points += 3
    if item.published:
        age = max(0, int((now_cn() - item.published).total_seconds() // 3600))
        points += max(0, 36 - age) // 6
    if is_low_quality(item):
        points -= 8
    return points


def collect_news() -> list[NewsItem]:
    collected: list[NewsItem] = []
    for group, locale, query in QUERIES:
        try:
            collected.extend(fetch_items(group, locale, query))
        except Exception as exc:
            print(f"warn: failed query {query}: {exc}", file=sys.stderr)

    if sum(1 for item in collected if is_china(item)) < 8:
        for query in FALLBACK_CHINA_QUERIES:
            try:
                collected.extend(fetch_items("china", "zh", query))
            except Exception as exc:
                print(f"warn: failed fallback query {query}: {exc}", file=sys.stderr)

    seen: set[str] = set()
    unique: list[NewsItem] = []
    for item in sorted(collected, key=score, reverse=True):
        key = key_for(item.title)
        if not key or key in seen or is_low_quality(item):
            continue
        seen.add(key)
        unique.append(item)
    return unique


def editor_instructions() -> str:
    return """
你是一名资深 AI 产业与技术新闻编辑，写给一位希望快速理解 AI/AIGC 行业变化的中文读者。
你的任务不是罗列链接，而是从候选新闻中筛选真正有价值的信息，翻译、归并、总结成高质量中文简报。

硬性要求：
1. 全文必须使用中文。英文标题和英文摘要必须翻译并重写为自然中文。
2. 只选择 10-16 条高价值新闻。忽略重复、低信息量、SEO、股票短线、软文、纯观点、没有事实增量的内容。
3. 每条新闻必须说明：发生了什么、为什么重要、可能影响谁/哪个方向。
4. 不要把链接当正文。链接只放在每条末尾作为来源。
5. 不要编造候选新闻里没有的数字、融资金额、公司结论或发布时间。信息不足时写“基于来源摘要判断”。
6. 输出 Markdown，结构固定如下：

# AI/AIGC 每日高质量简报 - YYYY-MM-DD

## 今日要点
用 3-5 条短句概括今天最值得关注的变化。

## 技术与模型
每条格式：
### 中文标题
来源：来源｜时间：时间
摘要：2-3 句中文总结。
影响：1 句说明它对技术路线、开发者或行业的意义。
链接：URL

## 公司与产品新闻
同上。

## 中国 AI/AIGC 动态
同上。必须优先保留中国相关动态。

## 政策、监管与安全
同上。

## 投融资与产业
同上。

## 应用与生态
同上。

## 编辑观察
给出 4-6 条趋势判断，其中至少 2 条必须结合中国市场、政策或产业环境。

如果某个分类没有高质量新闻，可以省略该分类。不要输出“候选新闻列表”。
""".strip()


def extract_response_text(data: dict) -> str:
    if isinstance(data.get("output_text"), str) and data["output_text"].strip():
        return data["output_text"].strip()
    parts: list[str] = []
    for output in data.get("output", []) or []:
        for content in output.get("content", []) or []:
            text = content.get("text") or content.get("output_text")
            if isinstance(text, str):
                parts.append(text)
    if parts:
        return "\n".join(parts).strip()
    raise RuntimeError("OpenAI response did not contain text output.")


def build_editor_brief(items: list[NewsItem], generated_at: dt.datetime) -> str | None:
    api_key = env("OPENAI_API_KEY")
    if not api_key:
        return None

    model = env("OPENAI_MODEL", "gpt-5-mini")
    candidates = [item.record() for item in sorted(items, key=score, reverse=True)[:55]]
    payload = {
        "model": model,
        "instructions": editor_instructions(),
        "input": "生成日期：{}\n候选新闻 JSON：\n{}".format(
            generated_at.date().isoformat(),
            json.dumps(candidates, ensure_ascii=False, indent=2),
        ),
        "max_output_tokens": int(env("OPENAI_MAX_OUTPUT_TOKENS", "7000")),
    }
    request = urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:1000]
        raise RuntimeError(f"OpenAI API failed: HTTP {exc.code}: {detail}") from exc
    return extract_response_text(data)


def fallback_category(item: NewsItem) -> str:
    text = f"{item.title} {item.source} {item.snippet}".lower()
    if is_china(item):
        return "中国 AI/AIGC 动态"
    if contains_any(text, ["research", "benchmark", "open source", "model", "agent", "论文", "开源", "模型", "智能体", "多模态"]):
        return "技术与模型"
    if contains_any(text, ["regulation", "safety", "policy", "copyright", "监管", "政策", "安全", "版权"]):
        return "政策、监管与安全"
    if contains_any(text, ["funding", "investment", "chip", "data center", "融资", "投资", "芯片", "算力"]):
        return "投融资与产业"
    return "公司与产品新闻"


def build_rule_brief(items: list[NewsItem], generated_at: dt.datetime, note: str = "") -> str:
    selected = sorted(items, key=score, reverse=True)[:18]
    groups: dict[str, list[NewsItem]] = {category: [] for category in CATEGORIES}
    for item in selected:
        groups.setdefault(fallback_category(item), []).append(item)

    date = generated_at.date().isoformat()
    lines = [
        f"# AI/AIGC 每日高质量简报 - {date}",
        "",
    ]
    if note:
        lines.extend([f"> 说明：{note}", ""])
    lines.extend([
        "## 今日要点",
        "",
        "- 本期已过滤重复、低信息量和明显营销化内容，优先保留模型、产品、政策、投融资和中国市场相关动态。",
        "- 建议配置 OPENAI_API_KEY，以启用真正的编辑级中文筛选、翻译和深度总结。",
        "- 以下为规则版简报，已尽量避免只堆链接，但总结深度低于模型编辑版。",
        "",
    ])

    for category in ["技术与模型", "公司与产品新闻", "中国 AI/AIGC 动态", "政策、监管与安全", "投融资与产业", "应用与生态"]:
        rows = groups.get(category, [])[:5]
        if not rows:
            continue
        lines.extend([f"## {category}", ""])
        for item in rows:
            title = re.sub(r"\s+-\s+[^-]{2,80}$", "", item.title).strip()
            lines.extend([
                f"### {title}",
                f"来源：{item.source}｜时间：{format_date(item.published)}",
                f"摘要：{item.snippet or '基于标题判断，这是一条与 AI/AIGC 相关的动态，建议结合来源查看细节。'}",
                "影响：这条动态值得关注，因为它可能影响 AI 技术路线、产品竞争、产业投入或监管环境。",
                f"链接：{item.link}",
                "",
            ])

    lines.extend([
        "## 编辑观察",
        "",
        "1. 国内外 AI 新闻需要分开看：海外更常见模型、算力和平台发布，中国市场更受政策、备案、行业落地和国产算力影响。",
        "2. AIGC 的重点正在从单点工具转向工作流，真正有价值的新闻通常会体现成本、效率、场景或监管变化。",
        "3. 后续应优先关注模型能力、推理成本、数据合规、行业应用和投融资质量，而不是单纯发布数量。",
        "",
    ])
    return "\n".join(lines)


def send_mail(subject: str, body: str, output_path: Path) -> None:
    smtp_user = env("QQ_SMTP_USER", DEFAULT_MAIL)
    auth_code = env("QQ_SMTP_AUTH_CODE")
    recipient = env("MAIL_TO", DEFAULT_MAIL)
    if not auth_code:
        raise RuntimeError("Missing GitHub secret: QQ_SMTP_AUTH_CODE")

    message = EmailMessage()
    message["From"] = smtp_user
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content(body, subtype="plain", charset="utf-8")
    message.add_attachment(output_path.read_text(encoding="utf-8"), subtype="markdown", filename=output_path.name)

    context = ssl.create_default_context()
    with smtplib.SMTP_SSL("smtp.qq.com", 465, context=context, timeout=30) as server:
        server.login(smtp_user, auth_code)
        server.send_message(message)


def main() -> int:
    generated_at = now_cn()
    items = collect_news()
    if not items:
        raise RuntimeError("No AI/AIGC news items collected from RSS sources.")

    note = ""
    try:
        markdown = build_editor_brief(items, generated_at)
    except Exception as exc:
        note = f"OpenAI 编辑模型调用失败，已降级为规则版：{exc}"
        print(f"warn: {note}", file=sys.stderr)
        markdown = None
    if not markdown:
        note = note or "未配置 OPENAI_API_KEY，已降级为规则版。"
        markdown = build_rule_brief(items, generated_at, note)

    OUT_DIR.mkdir(exist_ok=True)
    date = generated_at.date().isoformat()
    output_path = OUT_DIR / f"AI-AIGC-news-{date}.md"
    output_path.write_text(markdown, encoding="utf-8")
    subject = f"AI/AIGC 每日高质量简报 - {date}"
    send_mail(subject, markdown, output_path)
    print(f"Sent {subject} to {env('MAIL_TO', DEFAULT_MAIL)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
