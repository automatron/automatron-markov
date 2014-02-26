from automatron_markov import encode, CHAIN_LENGTH, CLEANUP_RE, PHRASE_RE, PRE_CLEAN_RE, PREFIX_RE


def parse_line(line):
    match = PREFIX_RE.match(line)
    if match:
        line = match.group(1)

    return [
        CLEANUP_RE.sub(' ', s).strip()
        for s in PHRASE_RE.split(PRE_CLEAN_RE.sub(' ', line))
        if s and s.strip()
    ]


def learn_phrase(pipeline, prefix, phrase):
    words = [w.lower() for w in phrase.split()]
    if len(words) < CHAIN_LENGTH + 1:
        return pipeline

    for word in words:
        pipeline.hincrby(prefix + ':frequency', word, 1)

    reversed_words = list(reversed(words))
    words.append(None)
    reversed_words.append(None)

    for i in range(len(words) - CHAIN_LENGTH):
        key = words[i: i + CHAIN_LENGTH]
        next_word = words[i + CHAIN_LENGTH]
        key_encoded = encode(key)

        # Metadata
        pipeline.sadd(prefix + ':entry', key_encoded)
        for keyword in key:
            pipeline.lpush(prefix + ':query:' + keyword, key_encoded)

        # Forward chain
        pipeline.lpush(prefix + ':forward:' + key_encoded, encode(next_word))

        # Reverse chain
        key = tuple(reversed_words[i: i + CHAIN_LENGTH])
        next_word = reversed_words[i + CHAIN_LENGTH]
        pipeline.lpush(prefix + ':reverse:' + encode(key), encode(next_word))

    return pipeline
