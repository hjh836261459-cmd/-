#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
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

GROUPS = [
    "头条要闻",
    "技术前沿与新模型",
    "产品与 AIGC 应用",
    "中国 AI/AIGC 动态",
    "经济、产业与资本",
    "政治、政策与国际竞争",
    "发展计划与基础设施",
]

PRODUCT_KEYWORDS = [
    "openai",
    "anthropic",
    "claude",
    "chatgpt",
    "gemini",
    "deepmind",
    "microsoft",
    "google",
    "meta",
    "apple",
    "amazon",
    "字节",
    "豆包",
    "阿里",
    "通义",
    "百度",
    "文心",
    "腾讯",
    "混元",
    "华为",
    "盘古",
    "kimi",
    "月之暗面",
    "智谱",
    "阶跃星辰",
    "minimax",
    "商汤",
]

RESEARCH_KEYWORDS = [
    "research",
    "paper",
    "benchmark",
    "open source",
    "open-source",
    "github",
    "model release",
    "arxiv",
    "论文",
    "开源",
    "基准",
    "评测",
    "模型发布",
    "多模态",
    "推理",
]

POLICY_KEYWORDS = [
    "regulation",
    "policy",
    "safety",
    "governance",
    "copyright",
    "antitrust",
    "senate",
    "white house",
    "congress",
    "government",
    "geopolitics",
    "export control",
    "national security",
    "election",
    "eu ai act",
    "nist",
    "监管",
    "政策",
    "治理",
    "网信办",
    "工信部",
    "科技部",
    "国家数据局",
    "政府",
    "国际竞争",
    "出口管制",
    "国家安全",
    "人工智能法案",
    "版权",
]

FUNDING_KEYWORDS = [
    "funding",
    "raises",
    "valuation",
    "ipo",
    "acquisition",
    "investment",
    "revenue",
    "layoff",
    "chip",
    "gpu",
    "nvidia",
    "融资",
    "估值",
    "上市",
    "并购",
    "投资",
    "裁员",
    "算力",
    "芯片",
    "智算中心",
]

ECONOMY_KEYWORDS = [
    "economy",
    "economic",
    "productivity",
    "employment",
    "labor market",
    "jobs",
    "trade",
    "energy demand",
    "data center",
    "semiconductor",
    "supply chain",
    "经济",
    "生产力",
    "就业",
    "劳动力",
    "贸易",
    "能源",
    "数据中心",
    "半导体",
    "供应链",
]

DEVELOPMENT_KEYWORDS = [
    "roadmap",
    "development plan",
    "strategy",
    "initiative",
    "infrastructure plan",
    "investment plan",
    "national ai plan",
    "action plan",
    "路线图",
    "发展计划",
    "行动计划",
    "国家战略",
    "基础设施规划",
    "投资计划",
    "人工智能战略",
]

CHINA_MARKERS = [
    "中国",
    "国内",
    "北京",
    "上海",
    "深圳",
    "杭州",
    "广州",
    "香港",
    "阿里",
    "百度",
    "腾讯",
    "华为",
    "字节",
    "豆包",
    "通义",
    "文心",
    "混元",
    "盘古",
    "kimi",
    "月之暗面",
    "智谱",
    "阶跃星辰",
    "minimax",
    "商汤",
    "科大讯飞",
    "寒武纪",
    "36氪",
    "机器之心",
    "量子位",
    "晚点",
    "雷峰网",
]


@dataclass
class NewsItem:
    title: str
    source: str
    published: dt.datetime | None
    link: str
    summary: str
    query_group: str
    locale: str


@dataclass
class InlineImage:
    cid: str
    caption: str
    data: bytes
    subtype: str
    filename: str


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, "").strip() or default


def now_shanghai() -> dt.datetime:
    return dt.datetime.now(dt.timezone(dt.timedelta(hours=8)))


def google_news_rss_url(query: str, locale: str) -> str:
    if locale == "zh":
        params = {
            "q": query,
            "hl": "zh-CN",
            "gl": "CN",
            "ceid": "CN:zh-Hans",
        }
    else:
        params = {
            "q": query,
            "hl": "en-US",
            "gl": "US",
            "ceid": "US:en",
        }
    return "https://news.google.com/rss/search?" + urllib.parse.urlencode(params)


def fetch_url(url: str, timeout: int = 20) -> bytes:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 AI-AIGC-news-mailer/1.0",
            "Accept": "application/rss+xml, application/xml, text/xml;q=0.9, */*;q=0.8",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read()


def parse_pubdate(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    try:
        parsed = email.utils.parsedate_to_datetime(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        return parsed.astimezone(dt.timezone(dt.timedelta(hours=8)))
    except Exception:
        return None


def clean_text(value: str) -> str:
    value = html.unescape(value or "")
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def normalize_title(title: str) -> str:
    title = title.lower()
    title = re.sub(r"\s+-\s+[^-]{2,80}$", "", title)
    title = re.sub(r"[^\w\u4e00-\u9fff]+", "", title)
    return title[:120]


def source_from_item(item: ET.Element, title: str) -> str:
    source_node = item.find("source")
    if source_node is not None and source_node.text:
        return clean_text(source_node.text)
    if " - " in title:
        return title.rsplit(" - ", 1)[-1].strip()
    return "Google News"


def summary_from_item(title: str, description: str) -> str:
    description = clean_text(description)
    if description:
        pieces = re.split(r"(?<=[。！？.!?])\s+", description)
        short = " ".join(pieces[:2]).strip()
        if short:
            return short[:360]
    return f"这条动态与 AI/AIGC 相关，建议结合原文进一步查看细节：{title}"


def fetch_google_news(query: str, locale: str, query_group: str, limit: int = 12) -> list[NewsItem]:
    url = google_news_rss_url(query, locale)
    data = fetch_url(url)
    root = ET.fromstring(data)
    items: list[NewsItem] = []
    for node in root.findall("./channel/item")[:limit]:
        title = clean_text(node.findtext("title") or "")
        link = clean_text(node.findtext("link") or "")
        description = node.findtext("description") or ""
        source = source_from_item(node, title)
        published = parse_pubdate(node.findtext("pubDate"))
        if not title or not link:
            continue
        items.append(
            NewsItem(
                title=title,
                source=source,
                published=published,
                link=link,
                summary=summary_from_item(title, description),
                query_group=query_group,
                locale=locale,
            )
        )
    return items


def collect_news(lookback_hours: int, china_fallback_hours: int) -> list[NewsItem]:
    days = max(1, lookback_hours // 24)
    intl_queries = [
        (f'("new AI model" OR "model release" OR "large language model" OR multimodal OR "AI agent") when:{days}d', "technology"),
        (f'("AI research" OR "open source AI" OR benchmark OR reasoning OR inference) when:{days}d', "technology"),
        (f'(OpenAI OR Anthropic OR DeepMind OR "Google AI" OR Microsoft OR Meta OR Nvidia) when:{days}d', "product"),
        (f'("generative AI" OR AIGC) (product OR platform OR application) when:{days}d', "product"),
        (f'("AI economy" OR "AI productivity" OR "AI jobs" OR "AI investment" OR "AI funding") when:{days}d', "economy"),
        (f'("AI chip" OR "AI data center" OR "AI energy" OR semiconductor OR "AI supply chain") when:{days}d', "economy"),
        (f'("AI policy" OR "AI regulation" OR "AI safety" OR "AI copyright" OR "AI law") when:{days}d', "politics"),
        (f'("AI export controls" OR "AI national security" OR "national AI strategy" OR "AI action plan") when:{days}d', "politics"),
        (f'("AI roadmap" OR "AI development plan" OR "AI infrastructure plan" OR "AI initiative") when:{days}d', "development"),
    ]
    china_queries = [
        (f"(国产大模型 OR 多模态模型 OR 开源模型 OR 智能体 OR 模型发布) when:{days}d", "china-technology"),
        (f"(人工智能 OR AIGC OR 生成式AI) (产品 OR 应用 OR 平台) when:{days}d", "china-product"),
        (f"(AI 经济 OR 人工智能 生产力 OR AI 就业 OR 大模型 融资 OR AI 投资) when:{days}d", "china-economy"),
        (f"(AI 算力 OR 智算中心 OR AI 芯片 OR 数据中心 OR 半导体) when:{days}d", "china-economy"),
        (f"(网信办 人工智能 OR 工信部 人工智能 OR AI 监管 OR 生成式AI 备案) when:{days}d", "china-politics"),
        (f"(人工智能 发展规划 OR AI 行动计划 OR 人工智能 战略 OR 算力 基础设施规划) when:{days}d", "china-development"),
    ]

    all_items: list[NewsItem] = []
    for query, group in intl_queries:
        all_items.extend(fetch_google_news(query, "en", group))
    for query, group in china_queries:
        all_items.extend(fetch_google_news(query, "zh", group))

    china_count = sum(1 for item in all_items if item.locale == "zh" or is_china_item(item))
    if china_count < 5:
        fallback_days = max(2, china_fallback_hours // 24)
        fallback_queries = [
            (f"(人工智能 OR AIGC OR 大模型 OR 生成式AI) when:{fallback_days}d", "china-technology"),
            (f"(阿里 通义 OR 百度 文心 OR 腾讯 混元 OR 字节 豆包 OR Kimi OR 智谱) when:{fallback_days}d", "china-product"),
            (f"(AI 算力 OR AI 芯片 OR 智算中心 OR 人工智能 发展规划) when:{fallback_days}d", "china-development"),
        ]
        for query, group in fallback_queries:
            all_items.extend(fetch_google_news(query, "zh", group))

    return dedupe_items(all_items)


def dedupe_items(items: list[NewsItem]) -> list[NewsItem]:
    seen: set[str] = set()
    result: list[NewsItem] = []
    for item in sorted(items, key=lambda x: x.published or dt.datetime.min.replace(tzinfo=dt.timezone.utc), reverse=True):
        key = normalize_title(item.title)
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def contains_any(text: str, keywords: list[str]) -> bool:
    text_lower = text.lower()
    return any(keyword.lower() in text_lower for keyword in keywords)


def is_china_item(item: NewsItem) -> bool:
    text = f"{item.title} {item.source} {item.summary}"
    return item.locale == "zh" or contains_any(text, CHINA_MARKERS)


def rank_item(item: NewsItem) -> int:
    text = f"{item.title} {item.summary}".lower()
    score = 0
    for keyword in ["openai", "anthropic", "google", "microsoft", "nvidia", "regulation", "safety", "funding", "大模型", "人工智能", "算力", "监管"]:
        if keyword in text:
            score += 2
    if item.published:
        hours_old = max(0, (now_shanghai() - item.published).total_seconds() / 3600)
        score += max(0, 24 - int(hours_old)) // 6
    return score


def assign_groups(items: list[NewsItem]) -> dict[str, list[NewsItem]]:
    groups = {name: [] for name in GROUPS}
    ordered = sorted(items, key=rank_item, reverse=True)

    for item in ordered[:6]:
        groups["头条要闻"].append(item)

    for item in ordered:
        text = f"{item.title} {item.source} {item.summary}"
        if is_china_item(item):
            groups["中国 AI/AIGC 动态"].append(item)
        elif item.query_group == "technology" or contains_any(text, RESEARCH_KEYWORDS):
            groups["技术前沿与新模型"].append(item)
        elif item.query_group == "product" or contains_any(text, PRODUCT_KEYWORDS):
            groups["产品与 AIGC 应用"].append(item)
        elif item.query_group == "development" or contains_any(text, DEVELOPMENT_KEYWORDS):
            groups["发展计划与基础设施"].append(item)
        elif item.query_group == "politics" or contains_any(text, POLICY_KEYWORDS):
            groups["政治、政策与国际竞争"].append(item)
        elif item.query_group == "economy" or contains_any(text, ECONOMY_KEYWORDS + FUNDING_KEYWORDS):
            groups["经济、产业与资本"].append(item)
        else:
            groups["产品与 AIGC 应用"].append(item)

    for key in GROUPS:
        groups[key] = groups[key][:6]
    return groups


def format_date(value: dt.datetime | None) -> str:
    if value is None:
        return "时间未标注"
    return value.strftime("%Y-%m-%d %H:%M")


def trend_observations(groups: dict[str, list[NewsItem]]) -> list[str]:
    china_items = groups.get("中国 AI/AIGC 动态", [])
    policy_items = groups.get("政治、政策与国际竞争", [])
    funding_items = groups.get("经济、产业与资本", [])
    research_items = groups.get("技术前沿与新模型", [])
    product_items = groups.get("产品与 AIGC 应用", [])
    development_items = groups.get("发展计划与基础设施", [])

    trends = []
    if china_items:
        top_sources = ", ".join(sorted({item.source for item in china_items[:5]})[:3])
        trends.append(f"中国市场仍是单独观察主线：今日国内动态覆盖 {top_sources or '多类来源'}，说明国产模型、应用落地和政策环境需要与国际模型新闻并行跟踪。")
    else:
        trends.append("中国相关新闻在过去 24 小时内相对较少，后续简报会继续用近 72 小时窗口补齐国内政策、国产模型和产业应用变化。")

    if any(contains_any(f"{item.title} {item.summary}", ["算力", "芯片", "智算中心", "gpu", "nvidia"]) for item in china_items + funding_items):
        trends.append("中国 AI 产业的关键约束仍在算力和芯片：国内云厂商、智算中心和国产芯片生态的进展，会直接影响大模型落地节奏。")
    else:
        trends.append("国内 AI 应用需要继续观察算力成本：即使新闻焦点在产品发布，长期竞争仍会回到推理成本、云资源和行业部署能力。")

    if policy_items:
        trends.append("监管与安全正在前置：模型发布、内容生成、版权和网络安全议题越来越多地影响产品节奏，而不只是事后合规。")
    if funding_items:
        trends.append("资本继续向基础设施和可规模化应用集中：融资、并购和算力投入会筛选出更能进入企业流程的 AI 公司。")
    if research_items:
        trends.append("研究与开源的重点从单纯参数规模转向效率、推理、多模态和工具使用，开发者生态会因此出现更快的产品迭代。")
    if product_items:
        trends.append("产品竞争正在从聊天框扩展到智能体、语音、多模态和行业模板，AI 厂商会更强调完整工作流而不是单个模型能力。")
    if development_items:
        trends.append("各国与大型科技公司的 AI 发展计划正在从模型竞赛转向算力、能源、数据和人才的长期基础设施布局。")

    return trends[:5]


def render_markdown(groups: dict[str, list[NewsItem]], today: dt.date, generated_at: dt.datetime) -> str:
    lines = [
        f"# AI/AIGC 技术、经济与政策每日简报 - {today.isoformat()}",
        "",
        f"生成时间：{generated_at.strftime('%Y-%m-%d %H:%M')}（Asia/Shanghai）",
        "",
        "覆盖范围：过去 24 小时全球与中国 AI/AIGC 技术、经济、政治政策与发展计划；若中国相关新闻不足，会补充近 72 小时内的重要国内动态。",
        "",
    ]

    for group in GROUPS:
        lines.append(f"## {group}")
        lines.append("")
        items = groups.get(group, [])
        if not items:
            if group == "中国 AI/AIGC 动态":
                lines.append("过去 24 小时未检索到足够高相关度的中国 AI/AIGC 新闻，本期已在其他分组中保留近 72 小时内的相关动态。")
            else:
                lines.append("本期未检索到足够高相关度的新闻。")
            lines.append("")
            continue
        for index, item in enumerate(items, start=1):
            lines.extend(
                [
                    f"### {index}. {item.title}",
                    "",
                    f"来源：{item.source}  ",
                    f"发布时间：{format_date(item.published)}  ",
                    "",
                    item.summary,
                    "",
                    f"链接：{item.link}",
                    "",
                ]
            )

    lines.append("## 今日最值得关注的 5 条趋势")
    lines.append("")
    for index, trend in enumerate(trend_observations(groups), start=1):
        lines.append(f"{index}. {trend}")
    lines.append("")
    return "\n".join(lines)


def candidate_bucket(item: NewsItem) -> str:
    text = f"{item.title} {item.summary}"
    if is_china_item(item):
        return "china"
    if item.query_group == "technology" or contains_any(text, RESEARCH_KEYWORDS):
        return "technology"
    if item.query_group == "economy" or contains_any(text, ECONOMY_KEYWORDS + FUNDING_KEYWORDS):
        return "economy"
    if item.query_group == "politics" or contains_any(text, POLICY_KEYWORDS):
        return "politics"
    if item.query_group == "development" or contains_any(text, DEVELOPMENT_KEYWORDS):
        return "development"
    return "product"


def select_editor_candidates(items: list[NewsItem]) -> list[NewsItem]:
    ranked = sorted(items, key=rank_item, reverse=True)
    limits = {
        "technology": 3,
        "product": 1,
        "economy": 2,
        "politics": 2,
        "development": 1,
        "china": 3,
    }
    selected: list[NewsItem] = []
    selected_ids: set[str] = set()

    for bucket, limit in limits.items():
        matches = [item for item in ranked if candidate_bucket(item) == bucket]
        for item in matches[:limit]:
            key = normalize_title(item.title)
            if key and key not in selected_ids:
                selected.append(item)
                selected_ids.add(key)

    for item in ranked:
        if len(selected) >= 12:
            break
        key = normalize_title(item.title)
        if key and key not in selected_ids:
            selected.append(item)
            selected_ids.add(key)
    return selected[:12]


def editor_prompt(items: list[NewsItem], date: str) -> str:
    candidates = [
        {
            "title": item.title,
            "source": item.source,
            "published": format_date(item.published),
            "summary": item.summary,
            "link": item.link,
            "topic": candidate_bucket(item),
        }
        for item in select_editor_candidates(items)
    ]
    return f"""
你是一名资深 AI 技术、产业、经济和政策新闻编辑。请把候选新闻整理成一份面向中文读者的高质量每日简报。

硬性要求：
1. 全文使用自然中文；英文标题和摘要必须翻译、归并和重写。
2. 选择 6-8 条最重要且不重复的新闻，优先保留有事实增量的内容。
3. 必须兼顾以下主题：新模型与技术突破、AIGC 产品应用、AI 对经济/就业/资本/算力的影响、政治监管与国际竞争、中国 AI 动态、国家或公司的发展计划。
4. 分类可使用：技术前沿与新模型、产品与 AIGC 应用、经济产业与资本、政治政策与国际竞争、中国 AI/AIGC 动态、发展计划与基础设施。
5. 每条新闻包含：中文标题、来源与时间、2-3 句摘要、1 句“为什么重要”、原始链接。
6. 不得把一般经济或一般政治新闻混入；每条都必须与 AI/AIGC 有直接关系。
7. 不编造候选新闻中没有的数据、金额、发布日期或结论。链接仅作为来源，不得代替正文。
8. 末尾给出 3-5 条“编辑观察”，说明技术、经济和政策之间的联系。

输出 Markdown，标题为：# AI/AIGC 技术、经济与政策每日简报 - {date}

候选新闻 JSON：
{json.dumps(candidates, ensure_ascii=False, indent=2)}
""".strip()


def extract_chat_completion_text(data: dict) -> str:
    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError("AgnesAI response did not contain choices.")
    content = choices[0].get("message", {}).get("content")
    if isinstance(content, str) and content.strip():
        return content.strip()
    raise RuntimeError("AgnesAI response did not contain text output.")


def build_agnes_brief(items: list[NewsItem], generated_at: dt.datetime) -> str:
    api_key = env("AGNES_API_KEY") or env("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("Missing AGNES_API_KEY/OPENAI_API_KEY.")
    base_url = env("AGNES_BASE_URL", "https://apihub.agnes-ai.com/v1").rstrip("/")
    payload = {
        "model": env("AGNES_MODEL", "agnes-2.0-flash"),
        "messages": [{"role": "user", "content": editor_prompt(items, generated_at.date().isoformat())}],
        "temperature": 0.2,
        "max_tokens": int(env("AGNES_MAX_OUTPUT_TOKENS", "2200")),
        "stream": False,
    }
    request = urllib.request.Request(
        f"{base_url}/chat/completions",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            return extract_chat_completion_text(json.loads(response.read().decode("utf-8")))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:1200]
        raise RuntimeError(f"AgnesAI HTTP {exc.code}: {detail}") from exc


def image_topic_prompt(label: str, items: list[NewsItem]) -> tuple[str, str]:
    titles = [re.sub(r"\s+-\s+[^-]{2,80}$", "", item.title).strip() for item in items[:3]]
    subject = "；".join(titles)
    prompt = (
        f"Editorial data-journalism illustration for an AI news briefing. Theme: {label}. "
        f"Visualize these developments without copying logos or identifiable people: {subject}. "
        "Use a clear wide composition with concrete visual metaphors, restrained blue, green, red and neutral colors, "
        "professional newspaper infographic style, high information clarity, no text, no letters, no logos, no watermark."
    )
    return prompt, f"{label}：{subject}。AI 生成示意图，仅用于辅助理解。"


def download_image(url: str) -> tuple[bytes, str]:
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 AI-news-mailer/2.0"})
    with urllib.request.urlopen(request, timeout=90) as response:
        data = response.read(12 * 1024 * 1024 + 1)
        if len(data) > 12 * 1024 * 1024:
            raise RuntimeError("Generated image exceeded 12 MB.")
        content_type = response.headers.get_content_type()
    subtype = content_type.split("/", 1)[1] if content_type.startswith("image/") else "png"
    return data, subtype.replace("jpg", "jpeg")


def generate_agnes_image(prompt: str, caption: str, index: int) -> InlineImage:
    api_key = env("AGNES_API_KEY") or env("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("Missing AgnesAI API key for image generation.")
    base_url = env("AGNES_BASE_URL", "https://apihub.agnes-ai.com/v1").rstrip("/")
    payload = {
        "model": env("AGNES_IMAGE_MODEL", "agnes-image-2.1-flash"),
        "prompt": prompt,
        "size": env("AGNES_IMAGE_SIZE", "1024x768"),
    }
    request = urllib.request.Request(
        f"{base_url}/images/generations",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:1000]
        raise RuntimeError(f"AgnesAI image HTTP {exc.code}: {detail}") from exc

    rows = result.get("data") or []
    if not rows:
        raise RuntimeError("AgnesAI image response did not contain data.")
    if rows[0].get("b64_json"):
        data = base64.b64decode(rows[0]["b64_json"])
        subtype = "png"
    elif rows[0].get("url"):
        data, subtype = download_image(rows[0]["url"])
    else:
        raise RuntimeError("AgnesAI image response did not contain a URL or base64 image.")
    return InlineImage(
        cid=f"ai-news-image-{index}@daily-brief",
        caption=caption,
        data=data,
        subtype=subtype,
        filename=f"ai-news-illustration-{index}.{subtype.replace('jpeg', 'jpg')}",
    )


def generate_news_images(items: list[NewsItem]) -> list[InlineImage]:
    if env("ENABLE_NEWS_IMAGES", "1").lower() not in {"1", "true", "yes", "on"}:
        return []
    candidates = select_editor_candidates(items)
    tech = [item for item in candidates if candidate_bucket(item) in {"technology", "product", "china"}]
    context = [item for item in candidates if candidate_bucket(item) in {"economy", "politics", "development"}]
    topics = []
    if tech:
        topics.append(image_topic_prompt("技术前沿、新模型与 AIGC 应用", tech))
    if context:
        topics.append(image_topic_prompt("AI 对经济、产业、政策与国际竞争的影响", context))

    limit = max(0, min(2, int(env("NEWS_IMAGE_COUNT", "2"))))
    images = []
    for index, (prompt, caption) in enumerate(topics[:limit], start=1):
        try:
            images.append(generate_agnes_image(prompt, caption, index))
        except Exception as exc:
            print(f"warn: image {index} skipped: {exc}", file=sys.stderr)
    return images


def inline_html(value: str) -> str:
    markdown_links = []

    def stash_link(match: re.Match[str]) -> str:
        markdown_links.append((match.group(1), match.group(2)))
        return f"@@MAIL_LINK_{len(markdown_links) - 1}@@"

    value = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", stash_link, value)
    escaped = html.escape(value)
    escaped = re.sub(
        r"(https?://[^\s<]+)",
        lambda match: f'<a href="{match.group(1)}" style="color:#0b6bcb;word-break:break-all">查看来源</a>',
        escaped,
    )
    for index, (label, url) in enumerate(markdown_links):
        link_label = "查看来源" if label.startswith("http") else html.escape(label)
        escaped = escaped.replace(
            f"@@MAIL_LINK_{index}@@",
            f'<a href="{html.escape(url, quote=True)}" style="color:#0b6bcb;word-break:break-all">{link_label}</a>',
        )
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)
    return escaped


def markdown_to_html(markdown: str) -> str:
    parts = []
    list_type = ""

    def close_list() -> None:
        nonlocal list_type
        if list_type:
            parts.append(f"</{list_type}>")
            list_type = ""

    for raw_line in markdown.splitlines():
        line = raw_line.strip()
        if not line:
            close_list()
            continue
        if line.startswith("### "):
            close_list()
            parts.append(f"<h3>{inline_html(line[4:])}</h3>")
        elif line.startswith("## "):
            close_list()
            parts.append(f"<h2>{inline_html(line[3:])}</h2>")
        elif line.startswith("# "):
            close_list()
            parts.append(f"<h1>{inline_html(line[2:])}</h1>")
        elif line.startswith("- ") or re.match(r"^\*\s+", line):
            if list_type != "ul":
                close_list()
                parts.append("<ul>")
                list_type = "ul"
            list_item = re.sub(r"^(?:-|\*)\s+", "", line)
            parts.append(f"<li>{inline_html(list_item)}</li>")
        elif re.match(r"^\d+\.\s+", line):
            if list_type != "ol":
                close_list()
                parts.append("<ol>")
                list_type = "ol"
            list_item = re.sub(r"^\d+\.\s+", "", line)
            parts.append(f"<li>{inline_html(list_item)}</li>")
        elif line.startswith("> "):
            close_list()
            parts.append(f"<blockquote>{inline_html(line[2:])}</blockquote>")
        else:
            close_list()
            parts.append(f"<p>{inline_html(line)}</p>")
    close_list()
    return "\n".join(parts)


def build_html_document(markdown: str, images: list[InlineImage]) -> str:
    image_blocks = "".join(
        (
            '<figure style="margin:24px 0">'
            f'<img src="cid:{image.cid}" alt="{html.escape(image.caption)}" '
            'style="display:block;width:100%;max-width:720px;height:auto;border-radius:6px">'
            f'<figcaption style="margin-top:8px;color:#667085;font-size:13px;line-height:1.6">{html.escape(image.caption)}</figcaption>'
            "</figure>"
        )
        for image in images
    )
    return f"""<!doctype html>
<html><head><meta charset="utf-8"></head>
<body style="margin:0;background:#eef1f4;color:#17202a;font-family:Arial,'Microsoft YaHei',sans-serif">
  <div style="max-width:760px;margin:0 auto;background:#ffffff;padding:28px 30px">
    <div style="border-top:5px solid #c9372c;padding-top:18px">
      <div style="font-size:12px;color:#667085;text-transform:uppercase">Daily Intelligence Brief</div>
    </div>
    {image_blocks}
    <main style="font-size:15px;line-height:1.75">
      <style>
        h1{{font-size:27px;line-height:1.3;margin:12px 0 22px;color:#111827}}
        h2{{font-size:20px;line-height:1.4;margin:30px 0 12px;padding-bottom:7px;border-bottom:2px solid #e5e7eb;color:#13315c}}
        h3{{font-size:17px;line-height:1.45;margin:22px 0 8px;color:#1f2937}}
        p{{margin:7px 0}} li{{margin:6px 0}} blockquote{{margin:15px 0;padding:10px 14px;background:#f4f7fa;border-left:4px solid #0f8b8d;color:#344054}}
      </style>
      {markdown_to_html(markdown)}
    </main>
    <footer style="margin-top:34px;padding-top:14px;border-top:1px solid #d0d5dd;color:#667085;font-size:12px">
      图片由 AgnesAI 生成，仅作概念示意；新闻事实以正文来源为准。
    </footer>
  </div>
</body></html>"""


def send_mail(subject: str, body: str, output_path: Path, images: list[InlineImage] | None = None) -> None:
    smtp_user = env("QQ_SMTP_USER", DEFAULT_MAIL)
    auth_code = env("QQ_SMTP_AUTH_CODE")
    recipient = env("MAIL_TO", DEFAULT_MAIL)
    smtp_host = env("QQ_SMTP_HOST", "smtp.qq.com")
    smtp_port = int(env("QQ_SMTP_PORT", "465"))

    if not auth_code:
        raise RuntimeError("Missing QQ_SMTP_AUTH_CODE secret.")

    message = EmailMessage()
    message["From"] = smtp_user
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content(body, subtype="plain", charset="utf-8")
    images = images or []
    message.add_alternative(build_html_document(body, images), subtype="html", charset="utf-8")
    html_part = message.get_payload()[-1]
    for image in images:
        html_part.add_related(
            image.data,
            maintype="image",
            subtype=image.subtype,
            cid=f"<{image.cid}>",
            filename=image.filename,
        )
    message.add_attachment(
        output_path.read_text(encoding="utf-8"),
        subtype="markdown",
        filename=output_path.name,
    )

    context = ssl.create_default_context()
    with smtplib.SMTP_SSL(smtp_host, smtp_port, context=context, timeout=30) as server:
        server.login(smtp_user, auth_code)
        server.send_message(message)


def self_test() -> None:
    sample = NewsItem(
        title="国产大模型发布新一代多模态能力 - 示例来源",
        source="示例来源",
        published=now_shanghai(),
        link="https://example.com",
        summary="这是一条用于验证分组与渲染的示例新闻。",
        query_group="china",
        locale="zh",
    )
    groups = assign_groups([sample])
    rendered = render_markdown(groups, now_shanghai().date(), now_shanghai())
    if "中国 AI/AIGC 动态" not in rendered:
        raise AssertionError("Self-test failed: missing China section.")
    html_body = build_html_document(rendered, [])
    if "技术、经济与政策" not in html_body:
        raise AssertionError("Self-test failed: missing HTML brief title.")
    print("self-test ok")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--no-send", action="store_true", help="Generate the brief without sending email.")
    args = parser.parse_args(argv)

    if args.self_test:
        self_test()
        return 0

    generated_at = now_shanghai()
    today = generated_at.date()
    lookback_hours = int(env("NEWS_LOOKBACK_HOURS", "24"))
    china_fallback_hours = int(env("CHINA_FALLBACK_HOURS", "72"))

    items = collect_news(lookback_hours, china_fallback_hours)
    if not items:
        raise RuntimeError("No AI/AIGC news items were collected.")

    try:
        markdown = build_agnes_brief(items, generated_at)
        provider = "AgnesAI"
    except Exception as exc:
        provider = "rules"
        groups = assign_groups(items)
        markdown = (
            f"> 说明：AgnesAI 编辑调用失败，已降级为规则版：{exc}\n\n"
            + render_markdown(groups, today, generated_at)
        )
        print(f"warn: AgnesAI brief generation failed: {exc}", file=sys.stderr)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = OUT_DIR / f"AI-AIGC-news-{today.isoformat()}.md"
    output_path.write_text(markdown, encoding="utf-8")

    subject = f"AI/AIGC 技术、经济与政策每日简报 - {today.isoformat()}"
    if args.no_send:
        print(f"Generated {output_path} with {provider}")
        return 0

    images = generate_news_images(items)
    send_mail(subject, markdown, output_path, images)
    print(f"Sent {subject} with {provider} and {len(images)} inline image(s) to {env('MAIL_TO', DEFAULT_MAIL)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
