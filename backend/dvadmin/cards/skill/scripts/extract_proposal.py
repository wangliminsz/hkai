#!/usr/bin/env python3
"""extract_proposal.py - 计划书 PDF -> 3 个 markdown 数据文件

策略：
  1. pypdfium2 提取纯文本 + pdfplumber 提取表格
  2. 首页信息：文本 + 表格（首页）
  3. 所有保单年：包含「所有保單年」关键字的页，只提取表格
  4. 不同投资回报：包含「不同投資回報下的說明」关键字的页，提取表格+标题

注意：仅适用于【原生带文字 PDF】且表格有边框线。扫描件请使用 OCR 流程。

支持 --detect-only: 只读首页检测产品类型, 立即输出 JSON 并退出 (<2s).
  用于前端上传 PDF 后立即决定出哪几张卡的覆盖输入框, 避免硬编码 11 张
  但实际只有 10 张 (PWL/joy) 或 11 张 (CI) 的错位问题.
"""

import argparse
import os
import re
import sys
import time

import pypdfium2 as pdfium
import pdfplumber


# ── 表格清理工具 ──────────────────────────────────────────────


def _clean_cell(cell):
    if cell is None:
        return ""
    return str(cell).replace("\n", " ").strip()


def _is_numeric(s):
    s = str(s).strip().replace(",", "")
    if not s:
        return False
    try:
        float(s)
        return True
    except ValueError:
        return False


def _is_data_row(row):
    for cell in row:
        if cell is None:
            continue
        for val in str(cell).split("\n"):
            if _is_numeric(val.strip()):
                return True
    return False


def _merge_header(header_rows, ncols):
    merged = []
    for j in range(ncols):
        parts = []
        for row in header_rows:
            val = _clean_cell(row[j] if j < len(row) else None)
            if val and val not in parts:
                parts.append(val)
        merged.append(" ".join(parts))
    return merged


def _expand_data_row(row, ncols):
    split_cells = []
    max_count = 1
    for j in range(ncols):
        raw = row[j] if j < len(row) else None
        if raw is None or str(raw).strip() == "":
            split_cells.append([""])
        else:
            vals = [v.strip() for v in str(raw).split("\n")]
            split_cells.append(vals)
            max_count = max(max_count, len(vals))
    result = []
    for i in range(max_count):
        new_row = []
        for j in range(ncols):
            vals = split_cells[j]
            new_row.append(vals[i] if i < len(vals) else (vals[-1] if vals else ""))
        result.append(new_row)
    return result


def _to_markdown(header, data_rows):
    ncols = len(header)
    if ncols == 0 or not data_rows:
        return ""
    all_rows = [header] + data_rows
    col_widths = [
        max(len(str(r[j]) if j < len(r) else "") for r in all_rows) for j in range(ncols)
    ]
    col_widths = [max(w, 3) for w in col_widths]

    def fmt(row):
        return "| " + " | ".join(
            str(row[j] if j < len(row) else "").ljust(col_widths[j]) for j in range(ncols)
        ) + " |"

    lines = [fmt(header)]
    lines.append("| " + " | ".join("-" * w for w in col_widths) + " |")
    for row in data_rows:
        lines.append(fmt(row))
    return "\n".join(lines)


def clean_table(table):
    if not table:
        return ""
    ncols = max(len(r) for r in table)
    header_rows = []
    data_rows = []
    for row in table:
        if _is_data_row(row):
            data_rows.append(row)
        else:
            header_rows.append(row)
    if not data_rows:
        return ""
    if header_rows:
        header = _merge_header(header_rows, ncols)
    else:
        header = [_clean_cell(c) for c in data_rows[0]]
        data_rows = data_rows[1:]
    if not data_rows:
        return ""
    expanded = []
    for row in data_rows:
        expanded.extend(_expand_data_row(row, ncols))
    return _to_markdown(header, expanded)


# ── pypdfium2 纯文本清理（首页信息用）──────────────────────────


def clean_text(text):
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = text.split("\n")
    result = []
    skip = False
    skip_kind = None

    for line in lines:
        s = line.strip()
        clean = re.sub(r"\s+", "", s)
        if not clean:
            continue

        if skip:
            # Terminate "important" skip on PWL markers OR the shared content
            # markers that appear in both PWL and 危疾加護保 (e.g. 受保人姓名,
            # 受保人資料, 基本計劃). Without these extra terminators the skip
            # would eat the entire first page of non-PWL proposals.
            if skip_kind == "important" and (
                "尚裕終身壽險" in clean
                or "建議書摘要" in clean
                or "受保人姓名" in clean
                or "受保人資料" in clean
                or "基本計劃" in clean
            ):
                skip = False
                skip_kind = None
                # re-process this line (it's real content, not boilerplate)
            elif skip_kind == "fee" and ("列印日期" in clean or "建議書編號" in clean):
                skip = False
                skip_kind = None
            else:
                continue

        if clean.startswith("保單編號："):
            skip = True
            skip_kind = "important"
            continue
        if clean.startswith("列印日期:"):
            skip = True
            skip_kind = "important"
            continue
        if clean.startswith("重要事項：") or clean.startswith("重要事項:"):
            skip = True
            skip_kind = "important"
            continue
        if clean.startswith("徵費"):
            skip = True
            skip_kind = "fee"
            continue
        if clean.startswith("徵費是應"):
            skip = True
            skip_kind = "fee"
            continue
        if clean.startswith("此建議書由列印日期"):
            continue
        if clean.startswith("建議書編號"):
            continue
        if clean.startswith("此建議書由"):
            continue
        if re.match(r"\d+/\d+$", clean):
            continue
        if clean == "SIS":
            continue

        result.append(s)
    return "\n".join(result)


# ── 各模块提取 ────────────────────────────────────────────────


def extract_first_page(pdf_path, out_path):
    """首页：pdfplumber 表格 + pypdfium2 文本（去表格重复）。"""
    tables_md = []
    table_cell_texts = set()
    with pdfplumber.open(pdf_path) as pdf:
        page = pdf.pages[0]
        raw_tables = page.extract_tables()
        for raw in raw_tables:
            md = clean_table(raw)
            if md:
                tables_md.append(md)
                for row in raw:
                    for cell in row:
                        if cell:
                            for val in str(cell).split("\n"):
                                v = re.sub(r"\s+", "", val.strip())
                                if v:
                                    table_cell_texts.add(v)

    doc = pdfium.PdfDocument(pdf_path)
    page = doc[0]
    text_page = page.get_textpage()
    raw_text = text_page.get_text_range()
    text_page.close()
    page.close()
    doc.close()

    if len(raw_text.strip()) < 10:
        return False

    if table_cell_texts:
        lines = raw_text.split("\n")
        deduped = []
        for line in lines:
            s = line.strip()
            if not s:
                deduped.append(line)
                continue
            clean_line = re.sub(r"\s+", "", s)
            if clean_line in table_cell_texts:
                continue
            deduped.append(line)
        raw_text = "\n".join(deduped)

    cleaned = clean_text(raw_text)
    parts = [cleaned] if cleaned.strip() else []
    parts.extend(tables_md)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n\n".join(parts))
    return True


def find_target_pages(pdf_path, keywords, exclude_keywords=None):
    """Find pages whose cleaned text contains ALL `keywords` and NONE of
    `exclude_keywords`. Used to scope the years table: 危疾加護保's main
    "說明摘要（現時假設基礎）" page must be picked up while the rider
    "推廣優惠額外保障" pages (which also contain "說明摘要") are excluded.
    """
    exclude_keywords = exclude_keywords or []
    doc = pdfium.PdfDocument(pdf_path)
    total_pages = len(doc)
    target_pages = []
    page_titles = {}
    first_text = ""
    for i in range(total_pages):
        page = doc[i]
        text_page = page.get_textpage()
        text = text_page.get_text_range()
        text_page.close()
        page.close()
        if i == 0:
            first_text = text.strip()
        clean = re.sub(r"\s+", "", text)
        if all(k in clean for k in keywords) and not any(
            k in clean for k in exclude_keywords
        ):
            target_pages.append(i + 1)
            page_titles[i + 1] = _extract_title(text, keywords)
    doc.close()
    return target_pages, total_pages, first_text, page_titles


def _extract_title(text, keywords):
    if not text:
        return ""
    lines = text.split("\n")
    candidates = []
    for line in lines:
        s = line.strip()
        if not s:
            continue
        clean = re.sub(r"\s+", "", s)
        if all(k in clean for k in keywords):
            candidates.append(s)
    if not candidates:
        return ""
    for s in candidates:
        if s.endswith(keywords[0]):
            return s
    return min(candidates, key=len)


def extract_pages_tables(pdf_path, keywords, out_path, with_titles=False, exclude_keywords=None):
    target_pages, total_pages, first_text, page_titles = find_target_pages(
        pdf_path, keywords, exclude_keywords=exclude_keywords
    )
    if total_pages > 0 and len(first_text) < 10:
        return False

    parts = []
    table_count = 0
    with pdfplumber.open(pdf_path) as pdf:
        for page_no in sorted(target_pages):
            page = pdf.pages[page_no - 1]
            tables = page.extract_tables()
            page.close()
            page_md = []
            for table in tables:
                md = clean_table(table)
                if md:
                    table_count += 1
                    page_md.append(md)
            if page_md:
                block = f"<!-- Page {page_no} / {total_pages} -->\n\n"
                if with_titles:
                    title = page_titles.get(page_no, "")
                    if title:
                        block += f"## {title}\n\n"
                block += "\n\n".join(page_md)
                parts.append(block)

    if not parts:
        return False
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n\n---\n\n".join(parts))
    return True


def detect_product(first_text):
    """Identify the product family from page-1 text so we can pick the right
    extraction keywords.

    数据驱动：委托给 product_registry（遍历所有 products/<id>/parser.json 的
    signature.keywords），这样新产品只要添加 parser.json 即可被识别，无需改代码。
    返回 product id（'unknown' 表示未匹配）。
    """
    import sys as _sys
    from pathlib import Path as _Path
    _sys.path.insert(0, str(_Path(__file__).resolve().parent))
    try:
        import product_registry
        product, _plan = product_registry.detect_product(first_text or "")
        return product
    except Exception as exc:
        print(f"[detect] product_registry fallback failed: {exc}", file=_sys.stderr)
        return "unknown"


def main():
    parser = argparse.ArgumentParser(description="计划书 PDF -> 3 个 markdown 数据文件")
    parser.add_argument("pdf", type=str, help="计划书 PDF 路径")
    parser.add_argument("--output-dir", type=str, default="output", help="输出目录")
    parser.add_argument("--detect-only", action="store_true",
                        help="只检测产品类型, 立即输出 JSON {product, plan_name, ...} 并退出 (用于前端快速决定卡数)")
    args = parser.parse_args()

    if not os.path.isfile(args.pdf):
        print(f"PDF not found: {args.pdf}")
        sys.exit(1)

    # ── 快速检测模式: 只读首页, 输出 JSON, 退出 (<2s) ─────────
    if args.detect_only:
        import json
        try:
            doc = pdfium.PdfDocument(args.pdf)
            first_text = doc[0].get_textpage().get_text_range() if len(doc) > 0 else ""
            doc.close()
        except Exception as exc:
            print(f"[detect-only] PDF read failed: {exc}", file=sys.stderr)
            sys.exit(2)
        product = detect_product(first_text)
        # 尝试提取 plan_name (用于 UI 展示) —— 数据驱动：product_registry 会
        # 返回含 signature 关键字的首行作为 plan_name。
        plan_name = ""
        import sys as _sys
        from pathlib import Path as _Path
        _sys.path.insert(0, str(_Path(__file__).resolve().parent))
        try:
            import product_registry
            _product, _plan = product_registry.detect_product(first_text)
            if _product == product:
                plan_name = _plan
        except Exception:
            pass
        if not plan_name:
            for line in first_text.splitlines():
                line = line.strip()
                # 通用兜底：取第一条含「計劃 / 计划 / Plan」的行
                if any(k in line for k in ("計劃", "计划", "Plan")):
                    plan_name = line
                    break
        out = {
            "product": product,
            "plan_name": plan_name,
            "first_page_chars": len(first_text),
        }
        # 关键: 必须用 sys.stdout.write 而不是 print, 避免混入任何调试输出
        sys.stdout.write(json.dumps(out, ensure_ascii=False))
        sys.exit(0)

    os.makedirs(args.output_dir, exist_ok=True)
    base = os.path.splitext(os.path.basename(args.pdf))[0]

    # Peek at page 1 to pick product-specific keywords for the years table.
    # PWL: "所有保單年".  CI & 尚悅人生 (joy): prefer the 附加說明文件 (rider)
    # years table — it includes the 推廣優惠額外人壽保障 rider death benefit
    # that the main-plan 利益說明文件 page omits (e.g. year 1 death = 225,000
    # vs 150,000 on the main page). If the proposal has no rider, fall back to
    # the main-plan 說明摘要 (現時假設基礎) page.
    doc = pdfium.PdfDocument(args.pdf)
    first_text = doc[0].get_textpage().get_text_range() if len(doc) > 0 else ""
    doc.close()
    product = detect_product(first_text)
    print(f"[detect] product={product}")

    years_path = os.path.join(args.output_dir, f"{base}-所有保单年.md")
    if product.startswith("ci") or product == "joy":
        years_ok = extract_pages_tables(args.pdf, ["附加說明文件", "現時假設基礎"], years_path)
        if not years_ok:
            years_ok = extract_pages_tables(
                args.pdf, ["說明摘要", "現時假設基礎"], years_path, exclude_keywords=["推廣優惠"]
            )
    elif product == "aia":
        years_ok = extract_pages_tables(args.pdf, ["說明摘要"], years_path)
    else:
        years_ok = extract_pages_tables(args.pdf, ["所有保單年"], years_path)

    results = {
        "首页信息": extract_first_page(args.pdf, os.path.join(args.output_dir, f"{base}-首页信息.md")),
        "所有保单年": years_ok,
        "不同投资回报": extract_pages_tables(
            args.pdf,
            ["不同投資回報下的說明"],
            os.path.join(args.output_dir, f"{base}-不同投资回报.md"),
            with_titles=True,
        ),
    }

    print("=" * 50)
    for name, ok in results.items():
        status = "OK " if ok else "FAIL"
        print(f"  [{status}] {name}: {os.path.join(args.output_dir, base + '-' + name + '.md')}")
    print("=" * 50)

    # ── 友好错误提示: 缺关键表格很可能是上传了产品介绍/合同条款/产品手册, ──
    # 而非真正的「计划书」(带保单年度演示 + 投资回报情景). 计划书才包含
    # 「所有保单年」和「不同投资回报下的说明」这两张关键表, 产品介绍/合同
    # 条款等不包含. 把诊断写到 stderr 并 exit 2, 让上游 pipeline 包成更
    # 清晰的错误 (用户看到「请上传计划书, 不是产品介绍」而不是生硬的
    # 「缺少数据文件: years, scenario」).
    missing_sections = [name for name, ok in results.items() if not ok]
    if missing_sections:
        hint = (
            f"\n[extract_proposal] 警告: PDF 中没有提取到以下关键表格: {missing_sections}\n"
            f"  本系统只处理「计划书」(policy illustration), 通常文件名包含「计划书」\n"
            f"  且正文包含「所有保单年」+「不同投资回报下的说明」等表格.\n"
            f"  如果你上传的是「产品介绍」「产品手册」「合同条款」「单张宣传页」等\n"
            f"  营销/法律文件, 它们不含演示数据, 无法生成保单摘要卡片.\n"
            f"  请从万通保险顾问系统重新下载带数据表的「计划书」PDF 后再上传.\n"
        )
        print(hint, file=sys.stderr)
        # exit 2 → 上游 pipeline 会把 stderr 拼进 PipelineError 抛给前端
        sys.exit(2)


if __name__ == "__main__":
    main()
