from twisted.internet import defer
from automatron.core.event import STOP
from automatron.core.util import parse_user
from automatron_markov import build_prefix, DEFAULT_CHAIN_LENGTH
from automatron_markov.learn import learn_phrase, parse_line
from automatron_markov.reply import build_reply
from automatron_redis.txredisapi import lazyConnection
from zope.interface import classProvides, implements
from automatron.controller.client import IAutomatronMessageHandler
from automatron.backend.command import IAutomatronCommandHandler
from automatron.backend.plugin import IAutomatronPluginFactory
from automatron_redis import build_redis_config


class AutomatronMarkovPlugin(object):
    classProvides(IAutomatronPluginFactory)
    implements(IAutomatronMessageHandler, IAutomatronCommandHandler)

    name = 'markov'
    priority = 100

    def __init__(self, controller):
        self.controller = controller
        redis_config = build_redis_config(controller.config_file, 'markov')
        self.chain_length = int(redis_config.pop('chain_length', DEFAULT_CHAIN_LENGTH))
        self.redis = lazyConnection(**redis_config)

    def on_command(self, server, user, command, args):
        if command != 'markov':
            return

        if not args:
            self._help(server, user)
        else:
            subcommand, args = args[0], args[1:]
            self._on_subcommand(server, user, subcommand, args)

        return STOP

    def _help(self, server, user):
        for line in '''Syntax: markov <task> <args...>
Available tasks:
markov learn <true/false> <channel...>
markov reply <true/false> <channel...>
markov namespace <true/false> <channel...>'''.split('\n'):
            self.controller.message(server['server'], user, line)

    @defer.inlineCallbacks
    def _on_subcommand(self, server, user, subcommand, args):
        if subcommand in ('learn', 'reply') and len(args) >= 2 and args[0] in ('true', 'false'):
            if (yield self._verify_permissions(server, user, args[1:])):
                self._on_update_setting(server, user, args[1:], subcommand, args[0])
        elif subcommand == 'namespace' and len(args) >= 2:
            if (yield self._verify_permissions(server, user, args[1:])):
                self._on_update_setting(server, user, args[1:], subcommand, args[0])

    @defer.inlineCallbacks
    def _verify_permissions(self, server, user, channels):
        for channel in channels:
            if not (yield self.controller.config.has_permission(server['server'], channel, user, 'markov')):
                self.controller.message(server['server'], user,
                                        'You\'re not authorized to change settings for %s' % channel)
                defer.returnValue(False)

        defer.returnValue(True)

    def _on_update_setting(self, server, user, channels, key, value):
        for channel in channels:
            self.controller.config.update_plugin_value(
                self,
                server['server'],
                channel,
                key,
                value
            )

        self.controller.message(server['server'], user, 'OK')

    def on_message(self, server, user, channel, message):
        return self._on_message(server, user, channel, message)

    @defer.inlineCallbacks
    def _on_message(self, server, user, channel, message):
        config = yield self.controller.config.get_plugin_section(self, server['server'], channel)
        prefix = build_prefix(config.get('namespace'))

        if config.get('reply', 'false') == 'true' and \
                channel != server['nickname'] and \
                message.startswith(server['nickname'] + ':'):
            nickname = parse_user(user)[0]
            reply = yield build_reply(self.redis, prefix, message.split(':', 1)[1].strip())
            self.controller.message(server['server'], channel, '%s: %s' % (nickname, reply or 'I got nothing...'))
            defer.returnValue(STOP)

        if config.get('learn', 'false') == 'true':
            self._learn(prefix, message)
            return

    @defer.inlineCallbacks
    def _learn(self, prefix, message):
        for phrase in parse_line(message):
            yield learn_phrase(self.chain_length, self.redis, prefix, phrase)
