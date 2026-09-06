#!/usr/bin/env python3
"""Generate a human-editable style.md from project facts and card copy.

The generator is deliberately modest: it can infer a safe visual direction
from supplied facts, but it never pretends that an unverified brand detail was
researched.  An agent may enrich the ``research_notes``/``sources`` fields
after doing an actual project or brand review.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Dict, Optional, Sequence


PALETTE = {
    "纸白": "#F5F5F3",
    "墨黑": "#111111",
    "信号蓝": "#0A84FF",
    "静灰": "#6E6E73",
    "细线": "#D8D8D3",
}

TEMPLATE_ALIASES = {
    "oriental-ink": "apple-minimal",
    "pioneer-red": "swiss-grid",
    "blueprint-blue": "data-narrative",
    "olive-editorial": "modern-editorial",
    "black-gold-stage": "product-showcase",
}


def _context(text: str, brand_context: str = "") -> str:
    return f"{brand_context}\n{text}".strip()


def infer_style(text: str, brand_context: str = "", preset: Optional[str] = None) -> Dict[str, Any]:
    context = _context(text, brand_context)
    lowered = context.lower()
    oriental_brand = any(word in context for word in ("象上汇", "洗浴", "温泉", "水疗", "东方美学", "水墨", "古典"))
    pioneer = any(word in context for word in ("AI 先锋", "AI先锋", "比赛", "大赛", "先锋", "PIONEER", "赛事"))
    timeline = any(word.lower() in lowered for word in ("时间线", "流程", "日程", "timeline", "节点"))
    visual = any(word.lower() in lowered for word in ("作品", "案例", "展示", "图片", "海报", "视觉", "图文", "动图", "gif"))

    if preset:
        selected = preset
    elif oriental_brand and pioneer:
        selected = "product-showcase"
    elif oriental_brand:
        selected = "modern-editorial"
    elif pioneer:
        selected = "product-showcase"
    elif visual:
        selected = "modern-editorial"
    else:
        selected = "apple-minimal"

    template_id = TEMPLATE_ALIASES.get(selected, selected)

    subject = "象上汇东方美学 × AI 先锋赛事" if oriental_brand and pioneer else (
        "象上汇东方美学" if oriental_brand else "AI 先锋赛事" if pioneer else "当前项目"
    )
    if timeline:
        image_role = "信息型时间线首图/信息图：由 Seedream 5.0 Pro 在整图中直接写出日期、节点、路径和阶段关系，帮助理解"
    elif visual:
        image_role = "作品/案例信息图或主图：承载案例结构、场景关系或视觉气质，不只是装饰"
    else:
        image_role = "可选主题首图：只做方向与氛围；核心事实仍保留在 Card 文本中"
    return {
        "style_id": selected,
        "template_id": template_id,
        "subject": subject,
        "facts": [
            "来源事实：" + (brand_context.strip() if brand_context.strip() else "未提供独立品牌资料"),
            "输入信号：" + ("、".join([label for label, hit in (("东方/洗浴", oriental_brand), ("先锋/赛事", pioneer), ("时间线", timeline), ("图片/作品", visual)) if hit]) or "普通通知"),
        ],
        "research_status": "仅依据本次输入与 brand_context 推导；未联网核验品牌规范。需要外部研究时，把来源 URL 和结论补入本文件，不得把推测写成事实。",
        "palette": PALETTE,
        "image_role": image_role,
        "font_stack": "飞书 Card：优先系统中文黑体/苹方/思源黑体回退；本地预览使用 system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif；不把本地字体名写成 Card 必然能力。",
        "timeline_first": timeline,
    }


def render_style(style: Dict[str, Any], *, sources: Optional[str] = None, research_notes: Optional[str] = None) -> str:
    palette_rows = "\n".join(
        f"| {name} | `{hex_value}` | {role} |"
        for (name, hex_value), role in zip(
            style["palette"].items(),
            ("背景基底", "标题与正文", "唯一强调色", "次级文字", "分隔线"),
        )
    )
    sources_block = sources.strip() if sources and sources.strip() else "- 暂无外部来源；当前为输入事实驱动的安全默认风格。"
    notes_block = research_notes.strip() if research_notes and research_notes.strip() else "- 暂无补充研究笔记。"
    return f"""# {style['subject']} · Card Style

> 由飞书 AI 先锋大赛卡片排版 Skill 根据输入事实生成。此文件是图片提示词、Card 2.0 字体/颜色/排版和人工微调的共同约束；它不是品牌事实库。

## 1. 风格决策

- `style_id`: `{style['style_id']}`
- `template_id`: `{style['template_id']}`
- 信息第一：先让用户看懂“是什么、何时、做什么、如何完成”，再安排氛围和装饰。
- 单卡单焦点：时间线卡先看日期/节点/动作，提醒卡先看截止/必须完成事项，案例卡先看作品结论或入口。
- 视觉气质：Apple 官网式现代主义的层级纪律 + 高级信息设计材质；克制配色、舒展留白、现代无衬线、通栏模块和细横线，允许透明磨砂玻璃、动态模糊与低饱和渐变建立空间层次，拒绝廉价科技感和封闭卡片墙。

## 2. 事实与研究状态

{chr(10).join('- ' + fact for fact in style['facts'])}

{style['research_status']}

外部研究来源：

{sources_block}

研究笔记：

{notes_block}

## 3. 中性克制语义色板

| 角色 | HEX | 用法 |
| --- | --- | --- |
{palette_rows}

约束：颜色只服务内容层级、状态或空间深度；默认仅保留一个强调色及其低饱和材质变体。允许有信息作用的磨砂玻璃、光晕和渐变，但禁止廉价高饱和色堆叠、硬边重阴影和密集卡片墙；宁可留白，也不为填满模板补造组件。

## 4. 字体与层级

- 字体：{style['font_stack']}
- L1：单一主标题或关键结论，`heading`，只出现一个最大焦点。
- L2：日期、截止、阶段和唯一主动作，`heading-3/heading-4` + Markdown 粗体 + 语义色。
- L3：普通解释，`normal_v2`，不自动给每个段落添加 Emoji；只保留原文显式 Emoji 或少量结构标记。
- L4：眉题、来源、脚注，`notation`，低对比但不低到不可读。
- 下划线：只在本地编辑预览中作为辅助标记；Card 2.0 默认用粗体、颜色、字号和结构块安全表达，避免写入不稳定 CSS。

## 5. 排版与交互

- 手机单列优先；时间线每个节点满宽，日期在上、事项在下，日期统一显示为“几月几日”；垂直间距按基础值放大约 1.5 倍。
- 不把长文案塞进卡片或折叠面板；卡片只留摘要、3–5 个关键点、指标/图表和 CTA，完整原文留在 source.txt。
- 图片必须有信息角色：{style['image_role']}。
- GIF 只做慢速轨道、节点呼吸或光线移动；第一帧必须完整静态可读，日期/截止信息不得只存在于 GIF，图片内不得出现按钮或伪 CTA。
- 真实 URL 才生成 `open_url` 按钮；最多一个主按钮加两个次按钮。需要页面状态、表单、按点击者更新时使用 application-bot callback 和后端，不把 HTML/JS 塞进 Card JSON。
- 按钮文字是 UI 标签，不替换原文事实；原文全文、日期原写法和每次变换都留在 `.spec.json` 的 `analysis` 中。

## 6. 图片生成提示词约束

```text
{style['subject']}，{('清晰的时间节点与单条阅读路径' if style['timeline_first'] else '一个明确主体与通栏信息关系')}，纸白/墨黑/单一信号色基底，Apple 官网式现代主义的层级纪律，舒展留白，垂直间距约 1.5 倍，标题中等字重现代无衬线，正文与数字轻盈；加入 1–3 个有信息作用的透明磨砂玻璃层、柔和动态模糊、低饱和渐变光晕和细横线，让图文有呼吸、有节奏而不简陋；移动端安全区，主体不压满画面；请在同一次 Seedream 5.0 Pro 生成中只直接写出 information_allocation.image.include 中的来源锁定标题、关系节点、指标和短 quote，严禁按钮、CTA 标签、按钮形矩形、带动作标签的箭头和任何伪交互；原生 Card 只保留精简摘要、关键点、图表和真实行动，完整源文案留在 source.txt，不得留空白占位，也不得交给任何后续文字或图片处理。
```

生成图片后必须先取得真实飞书 `img_key` 再回填 spec；本地路径、HTTP URL、data URI 和假 key 都不能写入 Card。

## 7. 人工微调清单

- [ ] 只保留一个最大焦点，首屏能回答“什么时候做什么”。
- [ ] 所有日期已统一为“几月几日”，原始写法仍可在 provenance 中核对。
- [ ] 重要动作/截止已粗体或语义高亮，普通说明没有全部抢重点。
- [ ] 普通段落没有被自动补 Emoji；显式 Emoji 和少量结构标记有明确来源。
- [ ] 图片确实承载结构/场景信息，最终 PNG 的功能标签来自来源锁定计划，核心事实没有移出文本。
- [ ] URL、按钮、callback、权限与目标页面均已核对；未授权不发送。
- [ ] 在官方 CardKit/真实飞书客户端复核字体、图片、GIF、移动端排版和交互。
"""


def build_style_document(text: str, *, brand_context: str = "", preset: Optional[str] = None, sources: Optional[str] = None, research_notes: Optional[str] = None) -> str:
    return render_style(infer_style(text, brand_context, preset), sources=sources, research_notes=research_notes)


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(allow_abbrev=False, description="Generate an editable style.md for a Feishu card project")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--text")
    source.add_argument("--text-file")
    parser.add_argument("--brand-context", default="", help="verified project or brand facts supplied by the caller")
    parser.add_argument("--brand-context-file")
    parser.add_argument("--preset")
    parser.add_argument("--sources", help="newline-separated research sources to record, not fetched by this script")
    parser.add_argument("--research-notes", help="research notes to record")
    parser.add_argument("--output", default="style.md")
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    try:
        text = args.text if args.text is not None else Path(args.text_file).read_text(encoding="utf-8")
        brand_context = args.brand_context or (Path(args.brand_context_file).read_text(encoding="utf-8") if args.brand_context_file else "")
        document = build_style_document(text, brand_context=brand_context, preset=args.preset, sources=args.sources, research_notes=args.research_notes)
        output = Path(args.output).expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(document, encoding="utf-8")
        inferred = infer_style(text, brand_context, args.preset)
        print(json.dumps({"style": str(output), "style_id": inferred["style_id"], "template_id": inferred["template_id"]}, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, TypeError) as exc:
        print(f"generate_style.py: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
