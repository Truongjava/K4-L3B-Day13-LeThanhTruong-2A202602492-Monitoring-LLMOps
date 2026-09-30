from __future__ import annotations

import os
import time
from contextlib import nullcontext
from dataclasses import dataclass

from . import metrics
from .mock_llm import FakeLLM
from .mock_rag import retrieve
from .pii import hash_user_id, summarize_text
from .prompt_management import resolve_prompt
from .tracing import get_langfuse_client, observe, propagate_attributes, tracing_enabled


@dataclass
class AgentResult:
    answer: str
    latency_ms: int
    ttft_ms: int
    tokens_in: int
    tokens_out: int
    cost_usd: float
    quality_score: float


class LabAgent:
    def __init__(self, model: str = "claude-sonnet-4-5") -> None:
        self.model = model
        self.llm = FakeLLM(model=model)

    @observe(name="lab-agent-run", as_type="agent", capture_input=False, capture_output=False)
    def run(
        self,
        user_id: str,
        feature: str,
        session_id: str,
        message: str,
        correlation_id: str,
    ) -> AgentResult:
        langfuse_client = get_langfuse_client()
        with propagate_attributes(
            user_id=hash_user_id(user_id),
            session_id=session_id,
            tags=["lab", feature, self.model],
            trace_name="day13-agent-request",
            environment=os.getenv("APP_ENV", "dev"),
            metadata={
                "feature": feature,
                "model": self.model,
                "correlation_id": correlation_id,
            },
        ):
            started = time.perf_counter()
            start_observation = getattr(langfuse_client, "start_as_current_observation", None)

            retrieval_context = (
                start_observation(
                    name="retrieval",
                    as_type="retriever",
                    input={"query_preview": summarize_text(message)},
                    metadata={"correlation_id": correlation_id},
                )
                if callable(start_observation)
                else nullcontext()
            )
            with retrieval_context as retrieval_obs:
                docs = retrieve(message)
                if retrieval_obs is not None:
                    retrieval_obs.update(output={"doc_count": len(docs)})

            prompt = resolve_prompt(
                langfuse_client,
                feature=feature,
                docs=docs,
                message=message,
                enabled=tracing_enabled(),
            )
            langfuse_client.update_current_span(
                metadata={
                    "doc_count": len(docs),
                    "query_preview": summarize_text(message),
                    "prompt_name": prompt.name,
                    "prompt_label": prompt.label,
                    "prompt_version": prompt.version,
                    "prompt_source": prompt.source,
                    "prompt_fetch_error": prompt.fetch_error or "",
                },
                version=prompt.version,
            )

            generation_context = (
                start_observation(
                    name="llm-generate",
                    as_type="generation",
                    model=self.model,
                    input={"prompt_preview": summarize_text(prompt.text)},
                    metadata={
                        "correlation_id": correlation_id,
                        "prompt_name": prompt.name,
                        "prompt_label": prompt.label,
                        "prompt_version": prompt.version,
                    },
                    prompt=prompt.managed_prompt,
                )
                if callable(start_observation)
                else nullcontext()
            )
            with propagate_attributes(prompt=prompt.managed_prompt):
                with generation_context as generation_obs:
                    response = self.llm.generate(prompt.text)
                    usage = response.usage
                    input_cost, output_cost = self._cost_breakdown(
                        usage.input_tokens, usage.output_tokens
                    )
                    if generation_obs is not None:
                        generation_obs.update(
                            output=summarize_text(response.text),
                            usage_details={
                                "prompt_tokens": usage.input_tokens,
                                "completion_tokens": usage.output_tokens,
                                "total_tokens": usage.input_tokens + usage.output_tokens,
                            },
                            cost_details={
                                "input_cost": input_cost,
                                "output_cost": output_cost,
                                "total_cost": round(input_cost + output_cost, 6),
                            },
                            metadata={"ttft_ms": response.ttft_ms},
                        )
            quality_score = self._heuristic_quality(message, response.text, docs)
            latency_ms = int((time.perf_counter() - started) * 1000)
            cost_usd = round(input_cost + output_cost, 6)

        metrics.record_request(
            latency_ms=latency_ms,
            ttft_ms=response.ttft_ms,
            cost_usd=cost_usd,
            tokens_in=response.usage.input_tokens,
            tokens_out=response.usage.output_tokens,
            quality_score=quality_score,
        )

        return AgentResult(
            answer=response.text,
            latency_ms=latency_ms,
            ttft_ms=response.ttft_ms,
            tokens_in=response.usage.input_tokens,
            tokens_out=response.usage.output_tokens,
            cost_usd=cost_usd,
            quality_score=quality_score,
        )

    def _cost_breakdown(self, tokens_in: int, tokens_out: int) -> tuple[float, float]:
        input_cost = (tokens_in / 1_000_000) * 3
        output_cost = (tokens_out / 1_000_000) * 15
        return round(input_cost, 6), round(output_cost, 6)

    def _heuristic_quality(self, question: str, answer: str, docs: list[str]) -> float:
        score = 0.5
        if docs:
            score += 0.2
        if len(answer) > 40:
            score += 0.1
        if question.lower().split()[0:1] and any(token in answer.lower() for token in question.lower().split()[:3]):
            score += 0.1
        if "[REDACTED" in answer:
            score -= 0.2
        return round(max(0.0, min(1.0, score)), 2)
