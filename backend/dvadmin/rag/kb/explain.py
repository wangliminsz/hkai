from __future__ import annotations

from .config import chat_model, llm_credentials

PLAIN_SYSTEM = (
    "你是保險術語「翻譯員」，專門把專業內容翻成超級大白話。"
    "假設讀者完全不懂保險。請遵守：\n"
    "1) 語言：用**標準書面中文（繁體）**，即普通話式的白話文，兩岸三地一般人都看得懂；"
    "**嚴禁粵語口語**——不得出現「唔、嘅、喺、啲、仲、邊、睇、揀、咁、俾、嘢、嘥、咗、咪、冇、乜」等粵語字詞。\n"
    "2) 先用一句話講清楚「這是什麼」；\n"
    "3) 再給一個生活化的例子（存錢、看醫生、買手機那種場景）；\n"
    "4) 全程用大白話，不要用法律黑話；萬不得已用到專業詞，馬上用括號解釋；\n"
    "5) 總長度 180 字以內，不要條列太多、不要客套。"
)


def explain_plain(term: str, context: str | None = None, tenant_id=None) -> str:
    term = (term or "").strip()
    if not term:
        raise ValueError("term 不能為空")

    user = term
    if context:
        user = f"要解釋的內容：{term}\n\n（背景參考，來自產品問答，可忽略不相關部分）：{context[:600]}"

    import litellm

    creds = llm_credentials(tenant_id)
    messages = [
        {"role": "system", "content": PLAIN_SYSTEM},
        {"role": "user", "content": user},
    ]
    base = {
        "model": chat_model(tenant_id),
        "messages": messages,
        "api_key": creds.get("api_key"),
        "base_url": creds.get("base_url"),
        "temperature": 0.3,
        "max_tokens": 2048,
    }
    try:
        resp = litellm.completion(reasoning_effort="low", **base)
    except Exception:
        resp = litellm.completion(**base)

    message = resp.choices[0].message
    return (message.content or message.get("reasoning_content") or "").strip()
