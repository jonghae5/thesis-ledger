from enum import Enum


class SourceType(str, Enum):
    FACT = "FACT"
    ESTIMATE = "ESTIMATE"
    MODEL_OUTPUT = "MODEL_OUTPUT"
    LLM_INFERENCE = "LLM_INFERENCE"
    USER_ASSUMPTION = "USER_ASSUMPTION"


class Decision(str, Enum):
    STRONG_BUY = "STRONG_BUY"
    ACCUMULATE = "ACCUMULATE"
    HOLD = "HOLD"
    WATCH = "WATCH"
    REDUCE = "REDUCE"
    EXIT = "EXIT"


class ProviderStatus(str, Enum):
    OK = "OK"
    SKIPPED = "SKIPPED"
    ERROR = "ERROR"
