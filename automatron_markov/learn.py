from automatron_markov import encode, CLEANUP_RE, PHRASE_RE, PRE_CLEAN_RE, PREFIX_RE


def parse_line(line):
    match = PREFIX_RE.match(line)
    if match:
        line = match.group(1)

    return [
        CLEANUP_RE.sub(' ', s).strip()
        for s in PHRASE_RE.split(PRE_CLEAN_RE.sub(' ', line))
        if s and s.strip()
    ]


def learn_phrase(chain_length, pipeline, prefix, phrase):
    words = [w.lower() for w in phrase.split()]
    if len(words) < chain_length + 1:
        return pipeline

    for word in words:
        pipeline.hincrby(prefix + ':frequency', word, 1)

    reversed_words = list(reversed(words))
    words.append(None)
    reversed_words.append(None)

    for i in range(len(words) - chain_length):
        key = words[i: i + chain_length]
        next_word = words[i + chain_length]
        key_encoded = encode(key)

        # Metadata
        pipeline.sadd(prefix + ':entry', key_encoded)
        for keyword in key:
            pipeline.lpush(prefix + ':query:' + keyword, key_encoded)

        # Forward chain
        pipeline.lpush(prefix + ':forward:' + key_encoded, encode(next_word))

        # Reverse chain
        key = tuple(reversed_words[i: i + chain_length])
        next_word = reversed_words[i + chain_length]
        pipeline.lpush(prefix + ':reverse:' + encode(key), encode(next_word))

    return pipeline
