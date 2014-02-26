import random
from twisted.internet import defer
from twisted.python import log
from automatron_markov import decode, encode, CLEANUP_RE, PHRASE_RE


@defer.inlineCallbacks
def build_reply(redis, prefix, message):
    query_words = sorted([
        (word, int(frequency))
        for word, frequency in [
            (word, (yield redis.hget(':'.join((prefix, 'frequency')), word)))
            for word in _parse_input(message)
        ]
        if frequency and int(frequency)
    ], key=lambda word_frequency: word_frequency[1])

    if query_words:
        query = random.choice([word for word, f in query_words if f == query_words[0][1]])
        query_key = prefix + ':query:' + query
        query_index = random.randint(0, (yield redis.llen(query_key)) - 1)
        start = decode((yield redis.lindex(query_key, query_index)))
    else:
        entrypoint = yield redis.srandmember(':'.join((prefix, 'entry')))
        if not entrypoint:
            log.msg('Markov database is empty.')
            return
        start = decode(entrypoint)

    rev = yield _walk_chain(redis, ':'.join((prefix, 'reverse')), start[::-1])
    fwd = yield _walk_chain(redis, ':'.join((prefix, 'forward')), start)
    reply = u' '.join(rev[::-1] + fwd[len(start):])
    defer.returnValue(reply.encode('UTF-8'))


def _parse_input(query):
    phrases = [CLEANUP_RE.sub(' ', s).strip() for s in PHRASE_RE.split(query)]
    return [w.strip() for w in ' '.join(phrases).split(' ') if w.strip()]


@defer.inlineCallbacks
def _walk_chain(redis, chain, start):
    chain_length = len(start)

    phrase = list(start)
    while True:
        key = encode(phrase[-chain_length:])
        candidates = (yield redis.lrange(':'.join((chain, key)), 0, -1))
        next_word = decode(random.choice(candidates))
        if next_word is None:
            break
        phrase.append(next_word)
    defer.returnValue(phrase)
