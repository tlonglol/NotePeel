"""HTML helpers that mimic the OCR layout pass output (see NoteController._element_to_html).

Used by scripts/seed_demo.py and eval/corpus.py so seeded and evaluation notes
have the same structure as real OCR output: <h2> headers, <p> paragraphs,
◆-bulleted flex rows, and a dashed <hr> between merged pages.
"""

PAGE_DIVIDER = '<hr style="border:none;border-top:2px dashed #FFB74D;margin:24px 0;">'


def h(text: str) -> str:
    return (
        f'<h2 style="font-size:1.4em;color:#FF9800;margin:18px 0 8px;'
        f'text-transform:uppercase;letter-spacing:0.05em;">{text}</h2>'
    )


def p(text: str) -> str:
    return f'<p style="margin:10px 0;line-height:1.75;">{text}</p>'


def bullets(items: list) -> str:
    inner = "".join(
        '<div style="display:flex;gap:10px;margin-bottom:6px;line-height:1.75;">'
        '<span style="color:#FF9800;font-weight:bold;flex-shrink:0;">◆</span>'
        f'<span>{i}</span></div>'
        for i in items
    )
    return f'<div style="margin:12px 0;">{inner}</div>'
