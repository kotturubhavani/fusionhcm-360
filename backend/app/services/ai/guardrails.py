"""Input screening supplements structural tool and authorization boundaries."""
import re
import unicodedata

def normalize(value):
    return ''.join(c for c in unicodedata.normalize('NFKC',value) if unicodedata.category(c)!='Cf').casefold()

DOCUMENT_INJECTION = re.compile(
    r'ignore\s+(?:all\s+|previous\s+|system\s+)*instructions|system\s+prompt|developer\s+message|'
    r'(?:override|bypass|disable)\s+(?:\w+\s+){0,3}(?:permissions|authorization|guardrails|safety)|'
    r'(?:call|invoke|execute|run)\s+(?:the\s+)?(?:tool|function|sql|python|shell)|'
    r'(?:reveal|print|expose|show|give|dump)\s+(?:\w+\s+){0,4}(?:secret|api[ _-]?key|password|system prompt)|'
    r'<\|(?:system|im_start)',re.I)
UNSAFE = re.compile(
    r'\b(?:select\b.+\bfrom|drop\s+table|delete\s+from|insert\s+into|update\s+\w+\s+set|execute\s+sql|raw\s+sql)\b|'
    r'\b(?:read|open|load)\s+(?:the\s+)?(?:file|\.env|/etc|[a-z]:\\)|'
    r'https?://|file://|\b(?:curl|wget|eval\(|exec\(|os\.environ|environment variable)\b|'
    r'\b(?:reveal|show|print|give|dump)\b.{0,50}\b(?:prompt|api[ _-]?key|secret|credentials|password)\b|'
    r'\b(?:change|update|delete|terminate|hire|transfer|process|submit)\s+(?:my|the|this|that|all|worker|employee)\b',re.I)

def unsafe(value):
    q=normalize(value)
    return bool(DOCUMENT_INJECTION.search(q) or UNSAFE.search(q))
