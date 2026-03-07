"""AI 服务层。调用外部大模型 API 解析用户语音/文本输入。"""

import json
from dataclasses import dataclass
from typing import Optional

import httpx
from loguru import logger

from core.security import load_api_key
from core.config import DEFAULT_CATEGORIES
from repositories.category_repo import get_all_categories


@dataclass
class AIParseResult:
    """AI 解析结果。"""
    amount: float = 0.0
    category: str = "其他"
    is_reimbursable: bool = False
    confidence: float = 0.0
    summary: str = ""
    error: Optional[str] = None
    fallback: bool = False


def _build_prompt(user_text: str, category_names: list[str]) -> str:
    """构建发送给 AI 的 Prompt。"""
    categories_str = json.dumps(category_names, ensure_ascii=False)
    return f"""你是一个个人财务助手。请从用户的输入中提取信息，并从给定的分类列表中选择最合适的一项，返回严格的 JSON 格式。
用户输入: "{user_text}"
可选分类: {categories_str}

请返回:
{{
  "amount": float,
  "category": string,
  "is_reimbursable": boolean,
  "confidence": float,
  "summary": string
}}

规则：
1. amount: 金额，若未提及则为 0
2. category: 必须从可选分类中选择
3. is_reimbursable: 是否建议从奖金扣除（根据语境判断，如用户说"算奖金"则为 true，说"不算奖金"则为 false）
4. confidence: 0.0-1.0 置信度
5. summary: 简短摘要

注意：如果用户明确说"不算奖金"，则 is_reimbursable 必须为 false。如果用户说"算奖金里"、"用奖金"等，则为 true。"""


async def analyze_text(
    text: str,
    api_base_url: str,
    model_name: str,
) -> AIParseResult:
    """调用 AI API 解析用户输入文本。

    Args:
        text: 用户输入的文本（语音转写或手动输入）
        api_base_url: API 基础 URL
        model_name: 模型名称

    Returns:
        AIParseResult: 解析结果
    """
    api_key = load_api_key()
    if not api_key:
        return AIParseResult(
            error="未配置 API Key，请在设置中填写",
            fallback=True,
        )

    # 获取分类列表
    try:
        categories = await get_all_categories()
        category_names = [c.name for c in categories]
    except Exception:
        category_names = DEFAULT_CATEGORIES

    prompt = _build_prompt(text, category_names)
    url = f"{api_base_url.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model_name,
        "messages": [{"role": "user", "content": prompt}],
        "response_format": {"type": "json_object"},
    }

    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(
                url, json=payload, headers=headers, timeout=15.0
            )
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            parsed = json.loads(content)

            # 校验分类是否在可选列表中
            category = parsed.get("category", "其他")
            if category not in category_names:
                category = "其他"

            return AIParseResult(
                amount=float(parsed.get("amount", 0)),
                category=category,
                is_reimbursable=bool(parsed.get("is_reimbursable", False)),
                confidence=float(parsed.get("confidence", 0)),
                summary=str(parsed.get("summary", "")),
            )
        except httpx.HTTPStatusError as e:
            logger.error(f"AI API HTTP 错误: {e.response.status_code} - {e}")
            return AIParseResult(
                error=f"API 请求失败 ({e.response.status_code})",
                fallback=True,
            )
        except httpx.ConnectError:
            logger.error("AI API 连接失败: 网络不可用")
            return AIParseResult(error="网络连接失败", fallback=True)
        except httpx.TimeoutException:
            logger.error("AI API 请求超时")
            return AIParseResult(error="请求超时", fallback=True)
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logger.error(f"AI 响应解析失败: {e}")
            return AIParseResult(error="AI 响应格式异常", fallback=True)
        except Exception as e:
            logger.error(f"AI 服务未知错误: {e}")
            return AIParseResult(error=str(e), fallback=True)
