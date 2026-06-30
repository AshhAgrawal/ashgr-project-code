from __future__ import annotations

import json
import os
import re
from typing import Any

from .store import ASSIGNMENT_TODAY, RetailStore
from .tools import TOOL_SCHEMAS, ToolRunner


SYSTEM_PROMPT = f"""
You are a command-line AI agent for a small retail store.
Use tools for every store action, calculation, lookup, sale, return, promotion, reorder, or report.
Do not invent prices, margins, refunds, or inventory numbers.
All money amounts in tool results are already final for that field. Never recalculate, reinterpret, or apply an additional discount in the final answer.
For sale receipts, use line_total and total exactly as returned by the tool. If unit_price is lower than retail_price, that already reflects the active item promotion.
For multi-step requests that create a promotion and then ring up a sale, create the promotion before calling ring_up_sale.
Never set order_discount_pct to represent a promotion or "X% off" sale; that is handled only by create_promotion. order_discount_pct is solely for an explicit whole-order discount the customer is given at checkout, and defaults to 0.
The assignment's "today" is {ASSIGNMENT_TODAY}. "Last month" is May 2026.
When a product variant is ambiguous, call the tool with the available details and report the tool's clarification/error.
Keep final answers concise and receipt-like when appropriate.
""".strip()


class RetailAgent:
    def __init__(self, store: RetailStore, provider: str | None = None) -> None:
        self.store = store
        self.tool_runner = ToolRunner(store)
        try:
            from dotenv import load_dotenv

            load_dotenv()
        except Exception:
            pass
        self.provider = provider or ("groq" if os.getenv("GROQ_API_KEY") else "rules")
        self.messages: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}]
        self.client = None
        if self.provider == "groq":
            from groq import Groq

            self.client = Groq(api_key=os.getenv("GROQ_API_KEY"))

    def handle(self, user_text: str) -> str:
        if _is_promotion_sale_request(user_text):
            self._ensure_promotion_for_combined_sale(user_text)
        if self.provider == "groq":
            try:
                return self._handle_with_groq(user_text)
            except Exception as exc:
                if _is_rate_limit_error(exc):
                    fallback = self._handle_with_rules(user_text)
                    return (
                        "Groq rate limit reached, so I handled this with the local fallback parser.\n"
                        f"{fallback}"
                    )
                if _is_tool_validation_error(exc):
                    return _format_tool_validation_fallback(self._handle_with_rules(user_text))
                raise
        return self._handle_with_rules(user_text)

    def _handle_with_groq(self, user_text: str) -> str:
        assert self.client is not None
        self.messages.append({"role": "user", "content": user_text})
        successful_tool_signatures = set()
        for _ in range(5):
            response = self.client.chat.completions.create(
                model=os.getenv("GROQ_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct"),
                messages=self.messages,
                tools=TOOL_SCHEMAS,
                tool_choice="auto",
                temperature=0,
            )
            message = response.choices[0].message
            tool_calls = message.tool_calls or []
            if not tool_calls:
                self.messages.append(message.model_dump(exclude_none=True))
                return message.content or ""

            duplicate_success = False
            for call in tool_calls:
                signature = (call.function.name, call.function.arguments)
                if signature in successful_tool_signatures:
                    duplicate_success = True
                    break
            if duplicate_success:
                return self._summarize_without_more_tools()

            self.messages.append(message.model_dump(exclude_none=True))
            for call in tool_calls:
                signature = (call.function.name, call.function.arguments)
                result = self.tool_runner.run(call.function.name, call.function.arguments)
                if "error" not in result:
                    successful_tool_signatures.add(signature)
                if call.function.name == "ring_up_sale" and "error" not in result:
                    self.messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call.id,
                            "name": call.function.name,
                            "content": json.dumps(result),
                        }
                    )
                    final = _format_sale_receipt(result)
                    self.messages.append({"role": "assistant", "content": final})
                    return final
                self.messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "name": call.function.name,
                        "content": json.dumps(result),
                    }
                )
        return "I stopped after several tool calls to avoid an infinite loop. Please rephrase the request."

    def _ensure_promotion_for_combined_sale(self, user_text: str) -> None:
        result = self._rule_create_promotion(user_text)
        if "error" in result:
            return
        self.messages.append({"role": "system", "content": f"Promotion already created before sale: {json.dumps(result)}"})

    def _summarize_without_more_tools(self) -> str:
        assert self.client is not None
        response = self.client.chat.completions.create(
            model=os.getenv("GROQ_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct"),
            messages=self.messages
            + [
                {
                    "role": "user",
                    "content": "The tool action already succeeded. Do not call any more tools. Summarize the successful result concisely.",
                }
            ],
            temperature=0,
        )
        final = response.choices[0].message.content or ""
        self.messages.append({"role": "assistant", "content": final})
        return final

    def _handle_with_rules(self, text: str) -> str:
        lowered = text.lower()
        if "top" in lowered and "margin" in lowered:
            return _pretty(self.tool_runner.run("top_products_by_margin", {}))
        if "revenue" in lowered or "after returns" in lowered:
            return _pretty(self.tool_runner.run("revenue_report", {}))
        if "stock out" in lowered or "stockout" in lowered:
            return _pretty(self.tool_runner.run("stockout_report", {}))
        if "reorder" in lowered:
            return _pretty(self.tool_runner.run("reorder_low_stock", {}))
        if "promotion" in lowered or "% off" in lowered or "20% off" in lowered:
            result = self._rule_create_promotion(text)
            if "ring up" not in lowered:
                return _pretty(result)
        if "return" in lowered or "refund" in lowered:
            return _pretty(self._rule_return(text))
        if "receive" in lowered or "arrived" in lowered:
            return _pretty(self._rule_receive(text))
        if "ring up" in lowered:
            return _pretty(self._rule_sale(text))
        if "inventory" in lowered or "stock" in lowered:
            return _pretty(self.tool_runner.run("inventory_report", {}))
        return "I can ring up sales, process returns, create promotions, reorder stock, receive purchase orders, and report margins or stockout risk."

    def _rule_sale(self, text: str) -> dict[str, Any]:
        lowered = text.lower()
        items = []
        if "classic tee" in lowered:
            qty = _quantity_before(lowered, "classic")
            items.append({"product_name": "Classic Tee", "color": _color(lowered), "size": _size(lowered), "quantity": qty})
        if "canvas tote" in lowered or "totes" in lowered:
            qty = _quantity_before(lowered, "canvas")
            items.append({"product_name": "Canvas Tote", "quantity": qty})
        if "hoodie" in lowered:
            qty = _quantity_before(lowered, "hoodie")
            items.append({"product_name": "Pullover Hoodie", "color": _color(lowered), "size": _size(lowered), "quantity": qty})
        if "mug" in lowered:
            items.append({"product_name": "Ceramic Mug", "quantity": _quantity_before(lowered, "mug")})
        if "sock" in lowered:
            items.append({"product_name": "Wool Socks", "quantity": _quantity_before(lowered, "sock")})
        dates = _dates(text)
        date = dates[-1] if dates else ASSIGNMENT_TODAY
        return self.tool_runner.run(
            "ring_up_sale",
            {
                "items": items,
                "customer_name": _customer(text),
                "payment_method": "card" if "card" in lowered else "cash",
                "date": date,
            },
        )

    def _rule_return(self, text: str) -> dict[str, Any]:
        lowered = text.lower()
        order_match = re.search(r"O-\d+", text, re.IGNORECASE)
        sku_match = re.search(r"\b[A-Z]+-[A-Z]+-[A-Z]+\b|\bTOTE\b|\bMUG\b|\bSOCK\b", text, re.IGNORECASE)
        product_name = None
        if "hoodie" in lowered:
            product_name = "Pullover Hoodie"
        elif "canvas tote" in lowered or "tote" in lowered:
            product_name = "Canvas Tote"
        elif "tee" in lowered:
            product_name = "Classic Tee"
        return self.tool_runner.run(
            "return_item",
            {
                "order_id": order_match.group(0).upper() if order_match else None,
                "sku": sku_match.group(0).upper() if sku_match else None,
                "product_name": product_name,
                "color": _color(lowered),
                "size": _size(lowered),
                "quantity": _quantity_any(lowered),
                "condition": "damaged" if "damaged" in lowered else "good",
                "date": _date(text) or ASSIGNMENT_TODAY,
            },
        )

    def _rule_create_promotion(self, text: str) -> dict[str, Any]:
        lowered = text.lower()
        percent_match = re.search(r"(\d+)\s*%", text)
        scope_ref = "apparel"
        scope_type = "category"
        if "hoodie" in lowered:
            scope_ref = "Pullover Hoodie"
            scope_type = "product"
        elif "tee" in lowered:
            scope_ref = "Classic Tee"
            scope_type = "product"
        dates = re.findall(r"\d{4}-\d{2}-\d{2}", text)
        return self.tool_runner.run(
            "create_promotion",
            {
                "description": text,
                "percent_off": int(percent_match.group(1)) if percent_match else 0,
                "scope_type": scope_type,
                "scope_ref": scope_ref,
                "start_date": dates[0] if dates else ASSIGNMENT_TODAY,
                "end_date": dates[1] if len(dates) > 1 else ASSIGNMENT_TODAY,
            },
        )

    def _rule_receive(self, text: str) -> dict[str, Any]:
        nums = [int(n) for n in re.findall(r"\b\d+\b", text)]
        ordered_qty = nums[0] if nums else 0
        received_qty = nums[1] if len(nums) > 1 else ordered_qty
        return self.tool_runner.run(
            "receive_purchase_order",
            {
                "product_name": "Canvas Tote" if "tote" in text.lower() else "Ceramic Mug",
                "supplier_name": "Northwind" if "northwind" in text.lower() else "Pioneer",
                "ordered_qty": ordered_qty,
                "received_qty": received_qty,
                "date": _date(text) or ASSIGNMENT_TODAY,
            },
        )


def _pretty(result: dict[str, Any]) -> str:
    if "error" in result:
        return f"Error: {result['error']}"
    return json.dumps(result, indent=2)


def _format_sale_receipt(result: dict[str, Any]) -> str:
    lines = [
        f"Order #{result['order_id']}",
        result["date"],
        result["customer"],
        result["payment_method"],
        "",
    ]
    for line in result["lines"]:
        variant = " ".join(part for part in [line["product_name"], line.get("color"), line.get("size")] if part)
        price_note = ""
        if line.get("retail_price") and line["retail_price"] != line["unit_price"]:
            price_note = f" (list ${line['retail_price']}, charged ${line['unit_price']})"
        lines.append(f"{variant} x{line['quantity']}  ${line['line_total']}{price_note}")
    lines.extend(
        [
            "",
            f"Subtotal: ${result['subtotal']}",
            f"Order discount: {result['order_discount_pct']}%",
            f"Total: ${result['total']}",
        ]
    )
    return "\n".join(lines)


def _is_rate_limit_error(exc: Exception) -> bool:
    return exc.__class__.__name__ == "RateLimitError" or "rate_limit" in str(exc).lower()


def _is_tool_validation_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return "tool call validation failed" in text or "tool_use_failed" in text


def _format_tool_validation_fallback(fallback: str) -> str:
    try:
        result = json.loads(fallback)
    except json.JSONDecodeError:
        return fallback
    if isinstance(result, dict) and "order_id" in result and "lines" in result:
        return _format_sale_receipt(result)
    return fallback


def _is_promotion_sale_request(text: str) -> bool:
    lowered = text.lower()
    return "ring up" in lowered and ("% off" in lowered or "promotion" in lowered or "discount" in lowered)


def _date(text: str) -> str | None:
    dates = _dates(text)
    return dates[0] if dates else None


def _dates(text: str) -> list[str]:
    return re.findall(r"\d{4}-\d{2}-\d{2}", text)


def _customer(text: str) -> str | None:
    for name in ["Sarah Chen", "Marcus Reed", "Priya Patel", "Tom Becker"]:
        if name.lower() in text.lower():
            return name
    return None


def _color(text: str) -> str | None:
    for color in ["blue", "black", "gray", "navy"]:
        if color in text:
            return color.title()
    return None


def _size(text: str) -> str | None:
    for word, size in [("small", "S"), ("medium", "M"), ("large", "L"), (" s ", "S"), (" m ", "M"), (" l ", "L")]:
        if word in f" {text} ":
            return size
    return None


def _quantity_before(text: str, marker: str) -> int:
    number_words = {
        "one": 1,
        "two": 2,
        "three": 3,
        "four": 4,
        "five": 5,
        "six": 6,
        "seven": 7,
        "eight": 8,
        "nine": 9,
        "ten": 10,
    }
    prefix = text[: text.find(marker)] if marker in text else text
    digit_matches = re.findall(r"\b\d+\b", prefix)
    if digit_matches:
        return int(digit_matches[-1])
    for word, value in number_words.items():
        if re.search(rf"\b{word}\b", prefix):
            return value
    return 1


def _quantity_any(text: str) -> int:
    for word, value in {
        "one": 1,
        "two": 2,
        "three": 3,
        "four": 4,
        "five": 5,
        "six": 6,
        "seven": 7,
        "eight": 8,
        "nine": 9,
        "ten": 10,
    }.items():
        if re.search(rf"\b{word}\b", text):
            return value
    for match in re.finditer(r"\b\d+\b", text):
        number = int(match.group(0))
        prefix = text[max(0, match.start() - 2) : match.start()]
        if prefix == "o-" or number > 100:
            continue
        return number
    return 1
