from __future__ import annotations

import contextvars
import json
import logging
import os
import threading
import time
import uuid
from collections import defaultdict
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, ClassVar

request_id_context: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="")
trace_id_context: contextvars.ContextVar[str] = contextvars.ContextVar("trace_id", default="")


class JsonFormatter(logging.Formatter):
    RESERVED: ClassVar[frozenset[str]] = frozenset(
        {
            "name",
            "msg",
            "args",
            "levelname",
            "levelno",
            "pathname",
            "filename",
            "module",
            "exc_info",
            "exc_text",
            "stack_info",
            "lineno",
            "funcName",
            "created",
            "msecs",
            "relativeCreated",
            "thread",
            "threadName",
            "processName",
            "process",
            "taskName",
        }
    )

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname.lower(),
            "logger": record.name,
            "message": record.getMessage(),
        }
        if request_id := request_id_context.get():
            payload["request_id"] = request_id
        if trace_id := trace_id_context.get():
            payload["trace_id"] = trace_id
        for key, value in record.__dict__.items():
            if key not in self.RESERVED and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str, ensure_ascii=False)


def configure_logging(environment: str) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.DEBUG if environment == "development" else logging.INFO)


@dataclass(slots=True)
class HistogramState:
    bucket_counts: list[int]
    count: int = 0
    total: float = 0.0


@dataclass(slots=True)
class MetricRegistry:
    buckets: tuple[float, ...] = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5)
    counters: dict[tuple[str, tuple[tuple[str, str], ...]], float] = field(
        default_factory=lambda: defaultdict(float)
    )
    histograms: dict[tuple[str, tuple[tuple[str, str], ...]], HistogramState] = field(
        default_factory=dict
    )
    _lock: threading.RLock = field(default_factory=threading.RLock)

    @staticmethod
    def _key(name: str, labels: dict[str, Any] | None) -> tuple[str, tuple[tuple[str, str], ...]]:
        values = tuple(sorted((key, str(value)) for key, value in (labels or {}).items()))
        return name, values

    def increment(
        self, name: str, labels: dict[str, Any] | None = None, amount: float = 1.0
    ) -> None:
        with self._lock:
            self.counters[self._key(name, labels)] += amount

    def observe(self, name: str, value: float, labels: dict[str, Any] | None = None) -> None:
        with self._lock:
            key = self._key(name, labels)
            state = self.histograms.get(key)
            if state is None:
                state = HistogramState([0] * len(self.buckets))
                self.histograms[key] = state
            observation = float(value)
            state.count += 1
            state.total += observation
            for index, bucket in enumerate(self.buckets):
                if observation <= bucket:
                    state.bucket_counts[index] += 1

    @staticmethod
    def _labels(labels: tuple[tuple[str, str], ...], extra: tuple[str, str] | None = None) -> str:
        items = list(labels)
        if extra:
            items.append(extra)
        if not items:
            return ""
        escaped = [
            f'{key}="{value.replace(chr(92), chr(92) + chr(92)).replace(chr(34), chr(92) + chr(34))}"'
            for key, value in items
        ]
        return "{" + ",".join(escaped) + "}"

    def render(self) -> str:
        lines: list[str] = []
        with self._lock:
            for (name, labels), value in sorted(self.counters.items()):
                lines.append(f"{name}{self._labels(labels)} {value:g}")
            for (name, labels), state in sorted(self.histograms.items()):
                for bucket, cumulative in zip(self.buckets, state.bucket_counts, strict=True):
                    lines.append(
                        f"{name}_bucket{self._labels(labels, ('le', str(bucket)))} {cumulative}"
                    )
                lines.append(f"{name}_bucket{self._labels(labels, ('le', '+Inf'))} {state.count}")
                lines.append(f"{name}_sum{self._labels(labels)} {state.total:g}")
                lines.append(f"{name}_count{self._labels(labels)} {state.count}")
        return "\n".join(lines) + "\n"


class Tracer:
    """Optional OpenTelemetry bridge; remains a no-op with no exporter endpoint."""

    def __init__(self, service_name: str, service_version: str):
        self._tracer: Any | None = None
        endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
        try:
            from opentelemetry import trace

            if endpoint:
                from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
                from opentelemetry.sdk.resources import Resource
                from opentelemetry.sdk.trace import TracerProvider
                from opentelemetry.sdk.trace.export import BatchSpanProcessor

                provider = TracerProvider(
                    resource=Resource.create(
                        {"service.name": service_name, "service.version": service_version}
                    )
                )
                # Let the exporter interpret OTEL_EXPORTER_OTLP_ENDPOINT as a
                # base URL and append the signal-specific /v1/traces path.
                provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
                trace.set_tracer_provider(provider)
            self._tracer = trace.get_tracer(service_name, service_version)
        except ImportError:
            self._tracer = None

    @contextmanager
    def span(self, name: str, attributes: dict[str, Any] | None = None) -> Iterator[Any]:
        if self._tracer is None:
            yield None
            return
        with self._tracer.start_as_current_span(name, attributes=attributes or {}) as span:
            context = span.get_span_context()
            token = trace_id_context.set(
                format(context.trace_id, "032x") if context.is_valid else ""
            )
            try:
                yield span
            finally:
                trace_id_context.reset(token)


def new_request_id(supplied: str | None = None) -> str:
    if (
        supplied
        and 1 <= len(supplied) <= 100
        and all(character.isalnum() or character in "._:-" for character in supplied)
    ):
        return supplied
    return str(uuid.uuid4())


@contextmanager
def stage_timer(target: dict[str, float], name: str) -> Iterator[None]:
    started = time.perf_counter()
    try:
        yield
    finally:
        target[name] = round((time.perf_counter() - started) * 1000, 3)
