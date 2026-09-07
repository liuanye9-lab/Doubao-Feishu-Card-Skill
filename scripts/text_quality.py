"""Provider-independent text presentation; never mutate canonical source."""
import re

EDITOR_NOTE = re.compile(r'^\s*(?:按钮文案|制作备注|排版备注|生成备注)\s*[：:]')


def clean_display(value):
    text = '\n'.join(str(x) for x in value) if isinstance(value, list) else str(value or '')
    return '\n'.join(line for line in text.splitlines() if not EDITOR_NOTE.match(line)).strip()


def concise(value, max_chars=120, max_lines=2):
    """Select whole sentences; oversized indivisible text stays for QA to flag."""
    lines = clean_display(value).splitlines()
    result = []
    for line in lines:
        line = line.strip()
        if len(line) > max_chars:
            sentences = [s.strip() for s in re.split(r'(?<=[。！？])', line) if s.strip()]
            selected = []
            for sentence in sentences:
                if len(''.join(selected) + sentence) > max_chars:
                    break
                selected.append(sentence)
            line = ''.join(selected) or line
        if line:
            result.append(line)
        if len(result) >= max_lines:
            break
    return '\n'.join(result)


def hierarchy(value, prefix='•'):
    result = []
    for line in clean_display(value).splitlines():
        # Preserve original numbering, nesting and URLs/Markdown links.
        indent = line[:len(line)-len(line.lstrip())]
        text = line.strip()
        if not text:
            continue
        if re.match(r'^(?:\d+[.)、]|第[一二三四五六七八九十\d]+步)', text):
            result.append(indent + text)
            continue
        pieces = [text] if re.search(r'https?://|\[[^]]*\]\(', text) else re.split(r'(?<=；)\s*', text)
        for piece in pieces:
            piece = re.sub(r'^[-*•·▪◦]\s+', '', piece).strip()
            if piece:
                result.append(indent + prefix + ' ' + piece)
    return '\n'.join(result)


def prepare_blocks(blocks):
    """Normalize prose/long facts in a render copy, including resumed specs."""
    result = []
    for original in blocks:
        block = dict(original)
        kind = block.get('type')
        for field in ('content', 'body', 'text'):
            if field in block and isinstance(block[field], (str, list)):
                block[field] = clean_display(block[field])
        if kind in ('text', 'markdown', 'div'):
            block['type'] = 'highlight'
        if kind == 'section' and block.get('body', block.get('content')):
            block['highlight'] = True
        if kind in ('facts', 'metrics'):
            items = block.get('items', block.get('facts', block.get('metrics', [])))
            # Long dates and descriptions belong in readable single-column modules.
            if any(len(str(i.get('value', ''))) > 24 for i in items if isinstance(i, dict)):
                for item in items:
                    result.append({'type': 'highlight', 'title': item.get('label', ''),
                                   'content': clean_display(item.get('value')), 'tone': 'neutral'})
                continue
        result.append(block)
    return result
