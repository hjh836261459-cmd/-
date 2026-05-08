#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import email.utils
import html
import os
import re
import smtplib
import ssl
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from email.message import EmailMessage
from pathlib import Path

DEFAULT_MAIL = "hjh836261459@qq.com"
OUT_DIR = Path("out")
TZ = dt.timezone(dt.timedelta(hours=8))

GROUPS = [
    "头条要闻",
    "中国 AI/AIGC 动态",
    "产品与公司动态",
    "研究与开源",
    "政策与监管",
    "投融资与产业",
]

CHINA_MARKERS = [
    "中国", "国内", "北京", "上海", "深圳", "杭州", "阿里", "百度", "腾讯", "华为", "字节", "豆包",
    "通义", "文心", "混元", "盘古", "Kimi", "月之暗面", "智谱", "阶跃星辰", "MiniMax", "商汤",
    "科大讯飞", "寒武纪", "机器之心", "量子位", "36氪", "晚点", "雷峰网", "网信办", "工信部",
]

QUERIES = [
    ("产品与公司动态", "en", '(OpenAI OR Anthropic OR DeepMind OR "Google AI" OR Microsoft OR Meta OR Nvidia) when:1d'),
    ("研究与开源", "en", '("generative AI" OR "large language model" OR LLM OR "AI model" OR "open source AI") when:1d'),
    ("政策与监管", "en", '("AI regulation" OR "AI safety" OR "AI policy" OR "AI copyright" OR "AI governance") when:1d'),
    ("投融资与产业", "en", '("AI startup" OR "AI funding" OR "AI chip" OR "AI data center" OR "AI investment") when:1d'),
    ("中国 AI/AIGC 动态", "zh", '(人工智能 OR AIGC OR 生成式AI OR 大模型) when:1d'),
    ("中国 AI/AIGC 动态", "zh", '(国产大模型 OR 多模态模型 OR 开源模型 OR 智能体) when:1d'),
    ("中国 AI/AIGC 动态", "zh", '(AI 算力 OR 智算中心 OR AI 芯片 OR 国产大模型) when:1d'),
    ("中国 AI/AIGC 动态", "zh", '(网信办 人工智能 OR 工信部 人工智能 OR AI 监管 OR 生成式AI 备案) when:1d'),
    ("投融资与产业", "zh", '(AI 融资 OR 大模型 融资 OR AIGC 投融资 OR AI 应用) when:1d'),
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
    summary: str
    group: str
    locale: str


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, "").strip() or default


def now_cn() -> dt.datetime:
    return dt.datetime.now(TZ)


def rss_url(query: str, locale: str) -> str:
    if locale == "zh":
        params = {"q": query, "hl": "zh-CN", "gl": "CN", "ceid": "CN:zh-Hans"}
    else:
        params = {"q": query, "hl": "en-US", "gl": "US", "ceid": "US:en"}
    return "https://news.google.com/rss/search?" + urllib.parse.urlencode(params)


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


def source_from(node: ET.Element, title: str) -> str:
    source = node.find("source")
    if source is not None and source.text:
        return clean(source.text)
    if " - " in title:
        return clean(title.rsplit(" - ", 1)[-1])
    return "Google News"


def summary_from(title: str, description: str) -> str:
    description = clean(description)
    if description:
        return description[:360]
    return f"这条动态与 AI/AIGC 相关，建议结合原文进一步查看细节：{title}"


def fetch_items(group: str, locale: str, query: str, limit: int = 12) -> list[NewsItem]:
    request = urllib.request.Request(
        rss_url(query, locale),
        headers={"User-Agent": "Mozilla/5.0 ai-aigc-news-mailer/1.0"},
    )
    with urllib.request.urlopen(request, timeout=25) as response:
        root = ET.fromstring(response.read())

    items: list[NewsItem] = []
    for node in root.findall("./channel/item")[:limit]:
        title = clean(node.findtext("title") or "")
        link = clean(node.findtext("link") or "")
        if not title or not link:
            continue
        items.append(
            NewsItem(
                title=title,
                source=source_from(node, title),
                published=parse_date(node.findtext("pubDate")),
                link=link,
                summary=summary_from(title, node.findtext("description") or ""),
                group=group,
                locale=locale,
            )
        )
    return items


def key_for(title: str) -> str:
    title = title.lower()
    title = re.sub(r"\s+-\s+[^-]{2,80}$", "", title)
    title = re.sub(r"[^\w\u4e00-\u9fff]+", "", title)
    return title[:120]


def is_china(item: NewsItem) -> bool:
    text = f"{item.title} {item.source} {item.summary}"
    return item.locale == "zh" or any(marker.lower() in text.lower() for marker in CHINA_MARKERS)


def collect_news() -> list[NewsItem]:
    collected: list[NewsItem] = []
    for group, locale, query in QUERIES:
        try:
            collected.extend(fetch_items(group, locale, query))
        except Exception as exc:
            print(f"warn: failed query {query}: {exc}", file=sys.stderr)

    if sum(1 for item in collected if is_china(item)) < 5:
        for query in FALLBACK_CHINA_QUERIES:
            try:
                collected.extend(fetch_items("中国 AI/AIGC 动态", "zh", query))
            except Exception as exc:
                print(f"warn: failed fallback query {query}: {exc}", file=sys.stderr)

    seen: set[str] = set()
    unique: list[NewsItem] = []
    for item in sorted(collected, key=lambda x: x.published or dt.datetime.min.replace(tzinfo=TZ), reverse=True):
        key = key_for(item.title)
        if key and key not in seen:
            seen.add(key)
            unique.append(item)
    return unique


def score(item: NewsItem) -> int:
    text = f"{item.title} {item.summary}".lower()
    points = sum(2 for word in ["openai", "anthropic", "google", "microsoft", "nvidia", "大模型", "人工智能", "算力", "监管", "融资"] if word in text)
    if item.published:
        age = max(0, int((now_cn() - item.published).total_seconds() // 3600))
        points += max(0, 24 - age) // 6
    if is_china(item):
        points += 1
    return points


def assign_groups(items: list[NewsItem]) -> dict[str, list[NewsItem]]:
    groups = {name: [] for name in GROUPS}
    ranked = sorted(items, key=score, reverse=True)
    groups["头条要闻"] = ranked[:6]
    for item in ranked:
        target = "中国 AI/AIGC 动态" if is_china(item) else item.group
        groups.setdefault(target, []).append(item)
    for name in GROUPS:
        groups[name] = groups[name][:8 if name == "中国 AI/AIGC 动态" else 6]
    return groups


def format_date(value: dt.datetime | None) -> str:
    return value.strftime("%Y-%m-%d %H:%M") if value else "时间未标注"


def trends(groups: dict[str, list[NewsItem]]) -> list[str]:
    china = groups.get("中国 AI/AIGC 动态", [])
    policy = groups.get("政策与监管", [])
    funding = groups.get("投融资与产业", [])
    research = groups.get("研究与开源", [])
    product = groups.get("产品与公司动态", [])
    result = []
    if china:
        result.append("中国市场需要单独观察：国产大模型、算力、应用落地和监管节奏会与国际模型发布共同影响产业机会。")
    else:
        result.append("过去 24 小时中国相关新闻相对较少，简报已用近 72 小时窗口补充国内动态，后续仍会保持中国来源优先检索。")
    result.append("国内 AI 产业长期竞争会回到算力成本、模型备案、行业数据和企业真实部署能力，而不只是模型榜单。")
    if policy:
        result.append("监管与安全议题正在前置，模型能力、内容版权、数据合规和网络安全会越来越影响产品节奏。")
    if funding:
        result.append("资本继续向算力基础设施、行业应用和能产生现金流的 AI 公司集中，纯概念型项目会更难获得持续关注。")
    if research:
        result.append("研究和开源重点正在从参数规模转向推理效率、多模态、智能体和端侧部署，开发者生态会因此加速迭代。")
    if product:
        result.append("产品竞争正在从聊天框扩展到语音、视频、多模态和行业工作流，AI 厂商会更强调完整任务闭环。")
    return result[:5]


def render(groups: dict[str, list[NewsItem]], generated_at: dt.datetime) -> str:
    today = generated_at.date().isoformat()
    lines = [
        f"# AI/AIGC 每日新闻简报 - {today}",
        "",
        f"生成时间：{generated_at.strftime('%Y-%m-%d %H:%M')}（Asia/Shanghai）",
        "",
        "覆盖范围：过去 24 小时全球与中国 AI/AIGC 新闻；若中国相关新闻不足，会补充近 72 小时内的重要国内动态。",
        "",
    ]
    for group in GROUPS:
        lines.extend([f"## {group}", ""])
        items = groups.get(group, [])
        if not items:
            lines.extend(["本期未检索到足够高相关度的新闻。", ""])
            continue
        for index, item in enumerate(items, 1):
            lines.extend([
                f"### {index}. {item.title}",
                "",
                f"来源：{item.source}  ",
                f"发布时间：{format_date(item.published)}  ",
                "",
                item.summary,
                "",
                f"链接：{item.link}",
                "",
            ])
    lines.extend(["## 今日最值得关注的 5 条趋势", ""])
    for index, item in enumerate(trends(groups), 1):
        lines.append(f"{index}. {item}")
    lines.append("")
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
    groups = assign_groups(items)
    markdown = render(groups, generated_at)
    OUT_DIR.mkdir(exist_ok=True)
    output_path = OUT_DIR / f"AI-AIGC-news-{generated_at.date().isoformat()}.md"
    output_path.write_text(markdown, encoding="utf-8")
    subject = f"AI/AIGC 每日新闻简报 - {generated_at.date().isoformat()}"
    send_mail(subject, markdown, output_path)
    print(f"Sent {subject} to {env('MAIL_TO', DEFAULT_MAIL)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
