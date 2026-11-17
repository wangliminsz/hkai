"""PDF post-processing for generated proposal PDFs.

Two edits, every page:
  1. Footer: replace the agency line
        "此建議書由BRANCH 01 - WISE FORTUNE ADVISORS LIMITED 建立 [聯絡電話: ]"
     with
        "此建議書由 YF Life 建立"
  2. Remove the "建議書編號 :XXXX_YYYY+" line entirely.

Approach: locate the exact text spans by position (NOT a blanket text replace),
white-out the region, and redraw the replacement with a CJK-capable font.
We never touch the similarly-prefixed line
"此建議書由列印日期起計算，有效期為30日...".
"""
from __future__ import annotations

import re
from pathlib import Path

import pymupdf

# Must match the agency footer specifically (has "BRANCH" + "建立").
AGENCY_FOOTER_RE = re.compile(r"此建議書由.*BRANCH.*建立")
PROPOSAL_NO_RE = re.compile(r"^\s*建議書編號")

NEW_FOOTER = "此建議書由 YF Life 建立"
FOOTER_SIZE = 8.0
CJK_FONT = "china-ss"     # Droid Sans Fallback: CJK glyphs
LATIN_FONT = "helv"       # Helvetica: clean Latin for "YF Life"

# Segments of the replacement footer: (text, is_latin)
FOOTER_SEGMENTS = [
    ("此建議書由 ", False),
    ("YF Life", True),
    (" 建立", False),
]


def _line_text(line: dict) -> str:
    return "".join(s["text"] for s in line["spans"])


def process_pdf(src: Path, dst: Path) -> dict:
    """Apply footer/number edits. Returns a small report."""
    doc = pymupdf.open(str(src))
    report = {"pages": len(doc), "footer_edits": 0, "number_removals": 0}
    cjk = pymupdf.Font(CJK_FONT)
    latin = pymupdf.Font(LATIN_FONT)

    for page in doc:
        d = page.get_text("dict")
        targets: list[tuple[str, tuple]] = []   # (kind, bbox)
        for block in d["blocks"]:
            if block.get("type") != 0:
                continue
            for line in block["lines"]:
                text = _line_text(line)
                if AGENCY_FOOTER_RE.search(text):
                    targets.append(("footer", line["bbox"]))
                elif PROPOSAL_NO_RE.match(text):
                    targets.append(("number", line["bbox"]))

        for kind, bbox in targets:
            # Tight redaction rect. IMPORTANT: the 建議書編號 line sits directly
            # left of the page number ("1/8") at the same vertical band, so we
            # must NOT over-pad to the right or above, or we clip the page number.
            x0, y0, x1, y1 = bbox
            rect = pymupdf.Rect(x0 - 0.5, y0 + 0.3, x1 + 0.2, y1 - 0.3)
            page.add_redact_annot(rect, fill=(1, 1, 1))
            if kind == "footer":
                report["footer_edits"] += 1
            else:
                report["number_removals"] += 1

        if targets:
            page.apply_redactions()

        # Redraw the replacement footer at the original baseline, advancing x
        # per segment and using the right font for CJK vs Latin.
        for kind, bbox in targets:
            if kind != "footer":
                continue
            baseline_y = bbox[3] - 1.5
            x = bbox[0]
            for seg_text, is_latin in FOOTER_SEGMENTS:
                fnt = latin if is_latin else cjk
                fname = LATIN_FONT if is_latin else CJK_FONT
                page.insert_text(
                    pymupdf.Point(x, baseline_y),
                    seg_text,
                    fontname=fname,
                    fontsize=FOOTER_SIZE,
                    color=(0, 0, 0),
                )
                x += fnt.text_length(seg_text, fontsize=FOOTER_SIZE)

    doc.save(str(dst), garbage=3, deflate=True)
    doc.close()
    return report


if __name__ == "__main__":
    import sys
    src = Path(sys.argv[1])
    dst = Path(sys.argv[2]) if len(sys.argv) > 2 else src.with_name(src.stem + "_edited.pdf")
    print(process_pdf(src, dst))
    print("saved:", dst)
