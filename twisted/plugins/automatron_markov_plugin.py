from twisted.internet import defer
from automatron_markov import build_prefix
from automatron_markov.learn import learn_phrase, parse_line
from automatron_markov.reply import build_reply
from automatron_redis.txredisapi import lazyConnection
from zope.interface import classProvides, implements
from automatron.client import IAutomatronMessageHandler
from automatron.command import IAutomatronCommandHandler
from automatron.plugin import IAutomatronPluginFactory, STOP
from automatron_redis import build_redis_config


class AutomatronMarkovPlugin(object):
    classProvides(IAutomatronPluginFactory)
    implements(IAutomatronMessageHandler, IAutomatronCommandHandler)

    name = 'markov'
    priority = 100

    def __init__(self, controller):
        self.controller = controller
        redis_config = build_redis_config(controller.config_file, 'markov')
        self.redis = lazyConnection(**redis_config)

    def on_command(self, client, user, command, args):
        nickname = client.parse_user(user)[0]

        if command == 'markov-learn':
            if len(args) != 2 or args[1] not in ('true', 'false'):
                client.msg(nickname, 'Syntax: markov-learn <channel> <true/false>')
            else:
                self._update_config(client, user, args[0], 'learn', args[1])
            return STOP
        elif command == 'markov-reply':
            if len(args) != 2 or args[1] not in ('true', 'false'):
                client.msg(nickname, 'Syntax: markov-reply <channel> <true/false>')
            else:
                self._update_config(client, user, args[0], 'reply', args[1])
            return STOP
        elif command == 'markov-namespace':
            if len(args) != 2:
                client.msg(nickname, 'Syntax: markov-namespace <channel> <namespace>')
            else:
                self._update_config(client, user, args[0], 'namespace', args[1])
            return STOP

    @defer.inlineCallbacks
    def _update_config(self, client, user, channel, key, value):
        nickname = client.parse_user(user)[0]
        if not (yield self.controller.config.has_permission(client.server, channel, user, 'markov')):
            client.msg(nickname, 'You\'re not authorized to do that.')
            defer.returnValue(STOP)

        self.controller.config.update_plugin_value(self, client.server, channel, key, value)
        client.msg(nickname, 'OK')

    def on_message(self, client, user, channel, message):
        return self._on_message(client, user, channel, message)

    @defer.inlineCallbacks
    def _on_message(self, client, user, channel, message):
        config = yield self.controller.config.get_plugin_section(self, client.server, channel)
        prefix = build_prefix(config.get('namespace'))

        if config.get('learn', 'false') == 'true':
            self._learn(prefix, message)
            return

        if config.get('reply', 'false') == 'true' and \
                channel != client.nickname and \
                message.startswith(client.nickname + ':'):
            nickname = client.parse_user(user)[0]
            d = build_reply(self.redis, prefix, message.split(':', 1)[1].strip())
            d.addCallback(lambda reply: client.msg(channel, '%s: %s' % (nickname, reply or 'I got nothing...')))
            defer.returnValue(STOP)

    @defer.inlineCallbacks
    def _learn(self, prefix, message):
        for phrase in parse_line(message):
            yield learn_phrase(self.redis, prefix, phrase)
