import re
try:
    import ujson as json
except ImportError:
    import json


CHAIN_LENGTH = 3
PREFIX_RE = re.compile(r'\S+:\s+(.*)')
PRE_CLEAN_RE = re.compile(r'https?:\S+')
PHRASE_RE = re.compile(r'(?<!mr|st|ms)(?<!mrs)\.\s|!|\? |--|;', re.I)
CLEANUP_RE = re.compile(r'''[.",*()?:-]|\s'|'\s''')

COMMON_PREFIX = 'automatron-markov:'
DEFAULT_NAMESPACE = 'default'


def encode(arg):
    return json.dumps(arg, ensure_ascii=False)


def decode(arg):
    return json.loads(arg)


def build_prefix(namespace):
    return COMMON_PREFIX + (namespace or 'default')
