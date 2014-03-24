from twisted.internet import defer
from automatron.core.event import STOP
from automatron.core.util import parse_user
from automatron_markov import build_prefix, DEFAULT_CHAIN_LENGTH
from automatron_markov.learn import learn_phrase, parse_line
from automatron_markov.reply import build_reply
from automatron_redis.txredisapi import lazyConnection
from zope.interface import classProvides, implements
from automatron.controller.client import IAutomatronMessageHandler
from automatron.controller.command import IAutomatronCommandHandler
from automatron.controller.plugin import IAutomatronPluginFactory
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

    def on_command(self, client, user, command, args):
        if command != 'markov':
            return

        if not args:
            self._help(client, user)
        else:
            subcommand, args = args[0], args[1:]
            self._on_subcommand(client, user, subcommand, args)

        return STOP

    def _help(self, client, user):
        for line in '''Syntax: markov <task> <args...>
Available tasks:
markov learn <true/false> <channel...>
markov reply <true/false> <channel...>
markov namespace <true/false> <channel...>'''.split('\n'):
            client.msg(user, line)

    @defer.inlineCallbacks
    def _on_subcommand(self, client, user, subcommand, args):
        if subcommand in ('learn', 'reply') and len(args) >= 2 and args[0] in ('true', 'false'):
            if (yield self._verify_permissions(client, user, args[1:])):
                self._on_update_setting(client, user, args[1:], subcommand, args[0])
        elif subcommand == 'namespace' and len(args) >= 2:
            if (yield self._verify_permissions(client, user, args[1:])):
                self._on_update_setting(client, user, args[1:], subcommand, args[0])

    @defer.inlineCallbacks
    def _verify_permissions(self, client, user, channels):
        for channel in channels:
            if not (yield self.controller.config.has_permission(client.server, channel, user, 'youtube-playlist')):
                client.msg(user, 'You\'re not authorized to change settings for %s' % channel)
                defer.returnValue(False)

        defer.returnValue(True)

    def _on_update_setting(self, client, user, channels, key, value):
        for channel in channels:
            self.controller.config.update_plugin_value(
                self,
                client.server,
                channel,
                key,
                value
            )

        client.msg(user, 'OK')

    def on_message(self, client, user, channel, message):
        return self._on_message(client, user, channel, message)

    @defer.inlineCallbacks
    def _on_message(self, client, user, channel, message):
        config = yield self.controller.config.get_plugin_section(self, client.server, channel)
        prefix = build_prefix(config.get('namespace'))

        if config.get('reply', 'false') == 'true' and \
                channel != client.nickname and \
                message.startswith(client.nickname + ':'):
            nickname = parse_user(user)[0]
            d = build_reply(self.redis, prefix, message.split(':', 1)[1].strip())
            d.addCallback(lambda reply: client.msg(channel, '%s: %s' % (nickname, reply or 'I got nothing...')))
            defer.returnValue(STOP)

        if config.get('learn', 'false') == 'true':
            self._learn(prefix, message)
            return

    @defer.inlineCallbacks
    def _learn(self, prefix, message):
        for phrase in parse_line(message):
            yield learn_phrase(self.chain_length, self.redis, prefix, phrase)
