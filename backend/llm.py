import asyncio
import logging
from typing import AsyncGenerator

import anthropic

from .config import ANTHROPIC_API_KEY, LLM_MODEL
from .knowledge_base import get_system_prompt

logger = logging.getLogger(__name__)

client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)


class LLMStream:
    """Streaming Claude conversation with cancellation support."""

    def __init__(self):
        self.conversation_history: list[dict] = []
        self._cancelled = False

    def cancel(self):
        """Cancel the current generation (for barge-in)."""
        self._cancelled = True

    async def generate(self, user_text: str) -> AsyncGenerator[str, None]:
        """Stream a response from Claude given user input.

        Yields text tokens as they arrive. Respects cancellation.
        """
        self._cancelled = False

        self.conversation_history.append({
            "role": "user",
            "content": user_text,
        })

        full_response = ""

        try:
            async with client.messages.stream(
                model=LLM_MODEL,
                max_tokens=300,
                system=get_system_prompt(),
                messages=self.conversation_history,
            ) as stream:
                async for text in stream.text_stream:
                    if self._cancelled:
                        logger.info("LLM generation cancelled (barge-in)")
                        break
                    full_response += text
                    yield text

        except asyncio.CancelledError:
            logger.info("LLM task cancelled")
        except Exception:
            logger.exception("Error in LLM generation")
            yield "I'm sorry, I encountered an issue. Could you repeat that?"
            full_response = "I'm sorry, I encountered an issue. Could you repeat that?"

        # Store whatever we generated (even partial) for conversation context
        if full_response:
            self.conversation_history.append({
                "role": "assistant",
                "content": full_response,
            })

        # Keep history manageable — last 20 turns
        if len(self.conversation_history) > 20:
            self.conversation_history = self.conversation_history[-20:]
