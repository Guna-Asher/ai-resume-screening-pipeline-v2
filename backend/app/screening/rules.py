"""Configurable rule data for the screening engine.

Everything the engine "knows" lives here as plain data, so extending
detection (a new framework, a new depth signal) is a one-line change.
Nothing in this module is mutated at runtime.
"""

import re
from dataclasses import dataclass
from enum import StrEnum

from app.models import EvidenceCategory

_I = re.IGNORECASE


def rx(pattern: str, flags: int = _I) -> re.Pattern[str]:
    return re.compile(pattern, flags)


# --------------------------------------------------------------------------- #
# Line context: decides whether a mention is real implementation evidence
# --------------------------------------------------------------------------- #

# Verbs that describe actually doing the work. They override "tutorial"-style
# negatives ("Built a RAG app after following a tutorial").
ACTION_VERBS = rx(
    r"\b(?:built|build|building|developed|developing|develop|implemented|implementing|implement|"
    r"created|creating|designed|designing|engineered|deployed|integrated|architected|wrote|"
    r"written|authored|automated|launched|shipped|delivered|optimi[sz]ed|migrated|refactored|"
    r"trained|fine-tuned|orchestrated|led)\b"
)
# Weaker cues that still indicate usage (counted outside project/work sections only).
IMPLEMENTATION_CUES = rx(
    r"\b(?:using|powered by|based on|written in|stack|back-?end|api|developer|engineer|"
    r"programmer|intern|internship)\b"
)
# Learning / passive-consumption context, which is not implementation evidence.
NEGATIVE_CONTEXT = rx(
    r"\b(?:tutorials?|watch(?:ed|ing)|courses?|coursework|coursera|udemy|bootcamp|webinars?|"
    r"workshops?|seminars?|learning|learn|studying|interested in|curious|exploring|"
    r"plan(?:ning)? to|want(?:ed)? to|hope to)\b"
)
# "machine learning" etc. contain "learning" but are not learning-context.
LEARNING_FALSE_FRIENDS = rx(
    r"\b(?:machine|deep|reinforcement|transfer|supervised|unsupervised|federated|"
    r"representation|ensemble)[ -]learning\b|\bscikit-learn\b"
)

# --------------------------------------------------------------------------- #
# Python evidence
# --------------------------------------------------------------------------- #

PYTHON_PATTERN = rx(r"\bpython(?:\s?3(?:\.\d+)?)?\b")

# Libraries that only exist in the Python ecosystem. Count as (weaker) Python
# evidence when used in a project / job; never from a skills list alone.
PYTHON_ECOSYSTEM = (
    ("FastAPI", rx(r"\bfastapi\b")),
    ("Django", rx(r"\bdjango\b")),
    ("Flask", rx(r"\bflask\b")),
    ("Pandas", rx(r"\bpandas\b")),
    ("NumPy", rx(r"\bnumpy\b")),
    ("PyTorch", rx(r"\bpytorch\b")),
    ("scikit-learn", rx(r"\b(?:scikit-learn|sklearn)\b")),
    ("Pydantic", rx(r"\bpydantic\b")),
    ("SQLAlchemy", rx(r"\bsqlalchemy\b")),
    ("Streamlit", rx(r"\bstreamlit\b")),
    ("pytest", rx(r"\bpytest\b")),
    ("asyncio", rx(r"\basyncio\b")),
    ("Celery", rx(r"\bcelery\b")),
)

# --------------------------------------------------------------------------- #
# AI / LLM / RAG / agentic evidence
# --------------------------------------------------------------------------- #


class AIKind(StrEnum):
    FRAMEWORK = "framework"  # named framework / SDK
    TECHNIQUE = "technique"  # specific technique (RAG, embeddings, tool calling...)
    GENERIC = "generic"  # LLM / provider / chatbot usage; weaker on its own


@dataclass(frozen=True)
class AITerm:
    name: str
    pattern: re.Pattern[str]
    kind: AIKind

    @property
    def category(self) -> EvidenceCategory:
        return {
            AIKind.FRAMEWORK: EvidenceCategory.AI_FRAMEWORK,
            AIKind.TECHNIQUE: EvidenceCategory.AI_TECHNIQUE,
            AIKind.GENERIC: EvidenceCategory.LLM_USAGE,
        }[self.kind]


_F, _T, _G = AIKind.FRAMEWORK, AIKind.TECHNIQUE, AIKind.GENERIC

# A bare "AI" or "agent" is deliberately NOT a term: "AI" alone and
# "insurance agent" / "user agent" are not evidence of an AI implementation.
AI_TERMS: tuple[AITerm, ...] = (
    # frameworks
    AITerm("LangChain", rx(r"\blang-?chain\b"), _F),
    AITerm("LangGraph", rx(r"\blang-?graph\b"), _F),
    AITerm("Google ADK", rx(r"\bgoogle adk\b|\bagent development kit\b|(?-i:\bADK\b)"), _F),
    AITerm("LlamaIndex", rx(r"\bllama[- ]?index\b"), _F),
    AITerm("CrewAI", rx(r"\bcrew ?ai\b"), _F),
    AITerm("AutoGen", rx(r"\bautogen\b"), _F),
    AITerm("Semantic Kernel", rx(r"\bsemantic kernel\b"), _F),
    AITerm("DSPy", rx(r"\bdspy\b"), _F),
    AITerm("PydanticAI", rx(r"\bpydantic[- ]?ai\b"), _F),
    # retrieval
    AITerm("RAG", rx(r"(?-i:\bRAG\b)|\bretrieval[- ]augmented(?: generation)?\b"), _T),
    AITerm("retrieval pipeline", rx(r"\bretrieval (?:pipeline|system|layer)s?\b"), _T),
    AITerm("semantic search", rx(r"\bsemantic search\b"), _T),
    AITerm("vector search", rx(r"\bvector (?:search|database|db|store|index|retrieval)s?\b"), _T),
    AITerm("embeddings", rx(r"\bembeddings?\b"), _T),
    AITerm(
        "vector database",
        rx(r"\b(?:faiss|chroma(?:db)?|pinecone|qdrant|weaviate|milvus|pgvector)\b"),
        _T,
    ),
    AITerm("reranking", rx(r"\bre-?rank\w*\b"), _T),
    # agents / tools / orchestration
    AITerm("agentic workflow", rx(r"\bagentic\b|\bagent (?:workflow|loop|framework|orchestration)s?\b"), _T),
    AITerm("multi-agent", rx(r"\bmulti[- ]agents?\b"), _T),
    AITerm("AI agent", rx(r"\b(?:ai|llm|autonomous|intelligent|conversational) agents?\b"), _T),
    AITerm("tool calling", rx(r"\btool[- ](?:calling|use)\b"), _T),
    AITerm("function calling", rx(r"\bfunction[- ]calling\b"), _T),
    AITerm("MCP", rx(r"\bmodel context protocol\b|(?-i:\bMCP\b)"), _T),
    AITerm(
        "orchestration",
        rx(r"\b(?:agent|llm|ai|workflow)s? orchestration\b|\borchestrat\w+ (?:of )?(?:llms?|agents?|tools)\b"),
        _T,
    ),
    # evaluation
    AITerm(
        "evaluation pipeline",
        rx(r"\b(?:llm |rag |agent )?evaluation (?:pipeline|harness|framework|suite)s?\b|\bllm evaluation\b|\bragas\b|\bllm[- ]as[- ]a[- ]judge\b"),
        _T,
    ),
    AITerm("LLM application", rx(r"\bllm[- ](?:application|app|based|pipeline|workflow)s?\b"), _T),
    # generic LLM usage
    AITerm("LLM", rx(r"\bllms?\b|\blarge language models?\b"), _G),
    AITerm("OpenAI API", rx(r"\bopenai\b|\bchat-?gpt\b|\bgpt-?[345]\w*\b"), _G),
    AITerm("Gemini", rx(r"\bgoogle gemini\b|\bgemini (?:api|pro|flash|\d)"), _G),
    AITerm("Anthropic/Claude", rx(r"\banthropic\b|\bclaude (?:api|\d|sonnet|opus|haiku)"), _G),
    AITerm("Hugging Face", rx(r"\bhugging ?face\b"), _G),
    AITerm("local LLM runtime", rx(r"\b(?:ollama|vllm)\b"), _G),
    AITerm("chatbot", rx(r"\bchat-?bots?\b"), _G),
    AITerm("generative AI", rx(r"\b(?:generative|gen) ?ai\b"), _G),
    AITerm("AI-powered app", rx(r"\bai[- ](?:powered|driven|based|assistant|application|app|system|pipeline|tool)s?\b"), _G),
    AITerm("prompt engineering", rx(r"\bprompt(?:s| engineering| templates?)\b"), _G),
    AITerm("fine-tuning", rx(r"\bfine[- ]?tun\w+\b"), _G),
)

# --------------------------------------------------------------------------- #
# Other skills surfaced as "matched skills" (information only; never
# used for eligibility - Java / React etc. must not cause rejection).
# --------------------------------------------------------------------------- #

SUPPORTING_SKILLS = (
    ("FastAPI", rx(r"\bfastapi\b")),
    ("Flask", rx(r"\bflask\b")),
    ("Django", rx(r"\bdjango\b")),
    ("PostgreSQL", rx(r"\bpostgres(?:ql)?\b")),
    ("Redis", rx(r"\bredis\b")),
    ("Docker", rx(r"\bdocker\b")),
    ("Kubernetes", rx(r"\bkubernetes\b|\bk8s\b")),
    ("GCP", rx(r"\bgcp\b|\bgoogle cloud\b")),
    ("AWS", rx(r"\baws\b")),
    ("Azure", rx(r"\bazure\b")),
    ("React", rx(r"\breact(?:\.?js)?\b")),
    ("Next.js", rx(r"\bnext\.?js\b")),
    ("TypeScript", rx(r"\btypescript\b")),
    ("JavaScript", rx(r"\bjavascript\b")),
    ("Java", rx(r"\bjava\b")),
)

# --------------------------------------------------------------------------- #
# AI project depth signals (scored per project / work entry)
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class DepthSignal:
    name: str
    points: int
    strong: bool  # "strong" signals prove the project is more than an API wrapper
    pattern: re.Pattern[str]
    explanation: str


# Points sum to 44; one fully-featured project is capped at the 40-point category max.
DEPTH_SIGNALS: tuple[DepthSignal, ...] = (
    DepthSignal(
        "retrieval", 7, True,
        rx(r"(?-i:\bRAG\b)|\bretriev\w+|\bsemantic search\b|\bvector (?:search|database|db|store|index)\b|\brerank\w*|\bsimilarity search\b"),
        "retrieval / RAG over a knowledge source",
    ),
    DepthSignal(
        "embeddings_vector_store", 4, True,
        rx(r"\bembeddings?\b|\b(?:faiss|chroma(?:db)?|pinecone|qdrant|weaviate|milvus|pgvector)\b|\bvector (?:database|db|store|index)\b|\bchunk\w*"),
        "embeddings / vector store / chunking",
    ),
    DepthSignal(
        "tool_calling", 5, True,
        rx(r"\btool[- ](?:calling|use)\b|\bfunction[- ]calling\b|\bmodel context protocol\b|(?-i:\bMCP\b)|\bcustom tools\b"),
        "tool / function calling",
    ),
    DepthSignal(
        "agents", 6, True,
        rx(r"\bagentic\b|\bmulti[- ]agents?\b|\b(?:ai|llm|autonomous|intelligent|conversational) agents?\b|\bagent (?:workflow|loop|framework)s?\b|\bcrew ?ai\b|\bautogen\b|\bgoogle adk\b|\bagent development kit\b|\blang-?graph\b"),
        "agents / multi-agent workflow",
    ),
    DepthSignal(
        "orchestration_state", 5, True,
        rx(r"\borchestrat\w+|\blang-?graph\b|\bstateful\b|\bstate (?:management|machine|graph)\b|\bconversation(?:al)? (?:memory|state)\b|\bmulti[- ]step\b|\bhuman[- ]in[- ]the[- ]loop\b|\bcheckpoint\w*|\b(?:agent|llm|ai) workflows?\b"),
        "orchestration / state management",
    ),
    DepthSignal(
        "evaluation", 5, True,
        rx(r"\bevaluation (?:pipeline|harness|framework|suite|metrics)\b|\bevaluat(?:ed|ing) (?:the )?(?:llm|rag|retrieval|agent|model|response|answer)s?\b|\bragas\b|\bllm[- ]as[- ]a[- ]judge\b|\bbenchmark\w*|\bhallucination\w*|\bprecision@|\brecall@|(?-i:\bMRR\b)|\bgolden (?:set|dataset)\b"),
        "evaluation of LLM / retrieval quality",
    ),
    DepthSignal(
        "data_product_logic", 4, False,
        rx(r"\bingest\w*|\bpars(?:e|er|ing)\b|\bcitations?\b|\bdata (?:processing|pipeline|cleaning)\b|\betl\b|\bpreprocess\w*|\bstructured (?:output|extraction)\b|\bschema validation\b|\branking\b|\bscor(?:ing|e)\b|\bbusiness logic\b|\bclassification\b|\bdeduplicat\w*"),
        "data processing / product logic around the model",
    ),
    DepthSignal(
        "backend_integration", 3, False,
        rx(r"\bfastapi\b|\bflask\b|\bdjango\b|\brest(?:ful)? api\b|\bback-?end\b|\bpostgres(?:ql)?\b|\bmysql\b|\bmongodb\b|\bredis\b|\bsqlalchemy\b|\bmicroservices?\b|\bdatabase\b|\bcelery\b|\bwebsockets?\b"),
        "backend / persistence integration",
    ),
)
BASELINE_SIGNAL = "ai_application"
BASELINE_POINTS = 5  # any AI term in a project/work unit

EXTRA_PROJECT_THRESHOLD = 10  # another AI project must reach this to add breadth credit
EXTRA_PROJECT_POINTS = 2
EXTRA_PROJECT_CAP = 6
SKILLS_CLAIM_CAP = 3  # points for AI frameworks/techniques that appear only in a skills list
CLAIMS_UNIT_CAP = 10  # AI mentions outside project/work sections ("claims") are capped

# Shallow-project penalty: by number of *supporting* signals (data/product logic,
# backend integration) when no unit has any strong signal.
SHALLOW_PENALTY_BY_SUPPORT = {0: 15, 1: 10}
SHALLOW_PENALTY_DEFAULT = 5  # two supporting signals, still no retrieval/agents/tools/eval/state

# --------------------------------------------------------------------------- #
# Python & backend / cloud / engineering signals
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class SignalRule:
    name: str
    category: EvidenceCategory
    pattern: re.Pattern[str]
    applied_points: int  # evidence in a project / work entry
    skills_points: int  # keyword only in a skills list
    explanation: str


BACKEND_SIGNALS: tuple[SignalRule, ...] = (
    SignalRule("web_framework", EvidenceCategory.BACKEND, rx(r"\bfastapi\b|\bflask\b|\bdjango\b|\buvicorn\b"), 5, 2, "Python web framework (FastAPI/Flask/Django)"),
    SignalRule("async", EvidenceCategory.BACKEND, rx(r"\basync(?:io)?\b|\baiohttp\b|\basync/await\b"), 3, 1, "async programming"),
    SignalRule("database", EvidenceCategory.BACKEND, rx(r"\bpostgres(?:ql)?\b|\bmysql\b|\bmongodb\b|\bsqlite\b|\bsqlalchemy\b|\bsql\b|\bdynamodb\b|\bfirestore\b"), 4, 2, "database (PostgreSQL/SQL/NoSQL)"),
    SignalRule("redis", EvidenceCategory.BACKEND, rx(r"\bredis\b"), 3, 1, "Redis"),
    SignalRule("backend_implementation", EvidenceCategory.BACKEND, rx(r"\bback-?end\b|\brest(?:ful)? apis?\b|\bapi (?:endpoint|server|service|design|gateway)s?\b|\bendpoints?\b|\bmicroservices?\b|\bserver-side\b|\bjwt\b|\boauth\b|\bauthentication\b"), 3, 1, "backend implementation (APIs, services)"),
)
PYTHON_BASE_POINTS = 4  # any qualifying Python evidence (a skills mention is enough)
PYTHON_PROJECT_POINTS = 5  # + Python used in a project
PYTHON_WORK_POINTS = 3  # + Python used in work / internship

CLOUD_SIGNALS: tuple[SignalRule, ...] = (
    SignalRule("cloud_provider", EvidenceCategory.CLOUD, rx(r"\bgcp\b|\bgoogle cloud\b|\bcloud run\b|\bvertex ai\b|\bbigquery\b|\bfirebase\b|\baws\b|\bamazon web services\b|\bec2\b|\bs3\b|\baws lambda\b|\bazure\b|\bcloud functions\b|\bapp engine\b"), 4, 2, "cloud platform (GCP/AWS/Azure)"),
    SignalRule("containers", EvidenceCategory.CLOUD, rx(r"\bdocker\w*|\bkubernetes\b|\bk8s\b|\bcontainer(?:s|ized|ised)?\b"), 3, 1, "containerisation (Docker/Kubernetes)"),
    SignalRule("deployment", EvidenceCategory.CLOUD, rx(r"\bdeploy\w*|\bci/?cd\b|\bgithub actions\b|\bvercel\b|\bheroku\b|\bnetlify\b|\brailway\b|\bhosted on\b|\bin production\b"), 4, 1, "deployment / CI-CD"),
    SignalRule("frontend", EvidenceCategory.FULLSTACK, rx(r"\breact(?:\.?js)?\b|\bnext\.?js\b|\bvue(?:\.?js)?\b|\bangular\b|\bsvelte\b|\bfront-?end\b"), 2, 1, "frontend framework as part of the system"),
    SignalRule("end_to_end", EvidenceCategory.FULLSTACK, rx(r"\bend-to-end\b|\bfull[- ]?stack\b|\bfront-?end and back-?end\b|\bweb (?:app|application)s?\b"), 2, 0, "end-to-end / full-stack system"),
)

ENGINEERING_SIGNALS: tuple[SignalRule, ...] = (
    SignalRule("testing", EvidenceCategory.ENGINEERING, rx(r"\bpytest\b|\bunit tests?\b|\bintegration tests?\b|\btest coverage\b|\btdd\b|\btest suites?\b|\bautomated tests?\b"), 1, 0, "automated testing"),
    SignalRule("architecture", EvidenceCategory.ENGINEERING, rx(r"\barchitecture\b|\bmodular\b|\bmicroservices?\b|\bdesign patterns?\b|\bsystem design\b|\bclean architecture\b|\bevent-driven\b"), 1, 0, "architecture / design"),
    SignalRule("caching_queues", EvidenceCategory.ENGINEERING, rx(r"\bcach(?:e|ing|ed)\b|\bqueues?\b|\bcelery\b|\brabbitmq\b|\bkafka\b|\bpub/?sub\b|\bbackground (?:jobs?|tasks?|workers?)\b"), 1, 0, "caching / queues"),
    SignalRule("concurrency", EvidenceCategory.ENGINEERING, rx(r"\bconcurren\w+|\bmulti-?threading\b|\bmulti-?processing\b|\bparallel\w*|\brate[- ]limit\w*|\bbatch processing\b"), 1, 0, "concurrency / throughput"),
    SignalRule("reliability_observability", EvidenceCategory.ENGINEERING, rx(r"\blogging\b|\bmonitoring\b|\bobservability\b|\bretr(?:y|ies)\b|\berror handling\b|\bfault[- ]toleran\w+|\btracing\b|\bmetrics\b|\bgraceful\w*|\bfailure handling\b|\bidempoten\w+"), 1, 0, "logging / observability / failure handling"),
)
