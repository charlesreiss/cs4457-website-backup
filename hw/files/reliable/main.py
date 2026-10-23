import argparse
import config
import ends
import json
import re
import util
import sys

from util import Message
from simulator import Simulator, Event
from link import RandomDropRule, FixedDropRule, RandomDelayRule

from util import trace

def run(args, messages):
    sender = ends.MySender()
    receiver = ends.MyReceiver()
    _simulator = util._simulator = Simulator(args)
    seqack_drop_rule = FixedDropRule(_simulator, args.drop_seq, args.drop_ack)
    random_forward_drop_rule = RandomDropRule(_simulator, args.drop_forward)
    _simulator.new_link(
        bandwidth=args.bandwidth_forward,
        buffer_size=args.buffer,
        delay_rule=RandomDelayRule(_simulator, args.delay, args.delay_variance),
        drop_rules=[random_forward_drop_rule, seqack_drop_rule],
        label='forward'
    )
    random_backward_drop_rule = RandomDropRule(_simulator, args.drop_backward)
    _simulator.new_link(
        bandwidth=args.bandwidth_backward,
        buffer_size=args.buffer,
        delay_rule=RandomDelayRule(_simulator, args.delay, args.delay_variance),
        drop_rules=[random_backward_drop_rule, seqack_drop_rule],
        label='backward'
    )
    if args.check_timeout:
        check_timeout_limit = args.check_timeout
    else:
        check_timeout_limit = max(
                args.delay * 2 + args.delay_variance * 2 +
                min(args.buffer, len(messages)) / args.bandwidth_forward * 2 +
                min(args.buffer, len(messages)) / args.bandwidth_backward * 2  + 1,
                config.INITIAL_TIMEOUT + 1,
            )
        if config.MODE.startswith('sliding'):
            # Sloppy way to permit assumption that we only retransmit first missing packet,
            # so we'll need extra round-trips in worst-case loss scenario
            check_timeout_limit *= config.INITIAL_WINDOW
    connection = _simulator.new_connection(
        label='main',
        sender=sender,
        receiver=receiver,
        forward_link_name='forward',
        backward_link_name='backward',
        check_packets=args.check_packets,
        check_timeout_limit=check_timeout_limit,
    )
    _simulator.add_event(
        Event(
            time=0,
            action=lambda: connection.send_messages(messages),
            description='initial data send'
        ),
    )
    _simulator.run()
    if args.json:
        json.dump({
            'corrupt_message_count': connection._corrupt_message_count,
            'skip_message_count': connection._skip_message_count,
            'pending_messages_at_end': len(connection._pending_messages),
            'in_flight_messages_at_end': len(connection._in_flight_messages),
            'sent_messages': connection._total_sent,
            'messages': connection._total_received,
            'mode': config.MODE,
            'initial_window': config.INITIAL_WINDOW,
            'initial_timeout': config.INITIAL_TIMEOUT,
            'time': _simulator.last_time(),
            'receiver_link': _simulator._links['forward'].json_info(),
            'sender_link': _simulator._links['backward'].json_info(),
        }, fp=sys.stdout, indent=2)
        sys.stdout.write('\n')
    else:
        if connection._skip_message_count > 0 or connection._corrupt_message_count > 0:
            print(f'ERROR --- one or more messages corrupted or missing')
        if len(connection._pending_messages) > 0:
            print(f'ERROR --- did not get a chance to send {len(connection._pending_messages)}')
        if len(connection._in_flight_messages) > 0:
            print(f'ERROR --- {len(connection._in_flight_messages)} messages sent but not received')
        print(f'received {connection._total_received} messages; finished after {_simulator.time()} time units')
        print(f"{_simulator._links['forward']._total_sent} frames sent to receiver; {_simulator._links['backward']._total_sent} frames sent to sender")

def _convert_bool(s: str) -> bool:
    if s == 'true' or s == 'True':
        return True
    elif s == 'false' or s == 'False':
        return False
    else:
        raise ValueError

_convert_bool.__name__ = 'bool'

def _convert_set(s: str) -> set[str]:
    if s == '':
        return set([])
    else:
        return set(map(lambda x: x.strip(), s.split(',')))

_convert_set.__name__ = 'comma-separted set of strings'

def _convert_drop_list(s: str) -> dict[int, list[bool]] | None:
    if s == None or s == '':
        return None
    else:
        result = {}
        parts = s.split(',')
        for part in parts:
            if '=' in part:
                k, v_raw = part.split('=')
                if '+' in v_raw or '-' in v_raw:
                    v = list(map(lambda x: x == '-', v_raw))
                else:
                    v = [True] * int(v_raw)
            else:
                k = part
                v = [True]
            result[int(k)] = v
        return result

_convert_drop_list.__name__ = 'drop pattern information'

class SetBothBandwidth(argparse.Action):
    def __call__(self, parser, args, values, option_string):
        setattr(args, 'bandwidth_forward', values)
        setattr(args, 'bandwidth_backward', values)

class SetBothDrop(argparse.Action):
    def __call__(self, parser, args, values, option_string):
        setattr(args, 'drop_forward', values)
        setattr(args, 'drop_backward', values)

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--json', help='enable JSON-format output', default=False, action='store_true')
    config_group = parser.add_argument_group('config.py settings')
    config_items = []
    for item in dir(config):
        if re.match(r'[A-Z]+', item):
            the_type = type(config.__dict__[item])
            normalized_option= item.replace('_', '-').lower()
            if the_type == bool:
                the_type = _convert_bool
            elif the_type == set:
                the_type = _convert_set
            config_group.add_argument(f'--{normalized_option}', f'--{item}',
                action='store',
                dest=item,
                type=the_type,
                default=config.__dict__[item],
                help=f'set config.{item}',
            )
            config_items.append(item)

    input_group = parser.add_argument_group('simulated input settings')
    input_group.add_argument('--generate-input', type=int, help='generate input of this number of messages', metavar='COUNT', required=True)

    sim_group = parser.add_argument_group('simulated link settings')
    sim_group.add_argument('--drop', metavar='DROP-RATE',
        help='simulated random drop rate in both directions (in addition to drops from buffer limit)',
        type=float, action=SetBothDrop)
    sim_group.add_argument('--drop-forward', metavar='DROP-RATE',
        help='simulated random drop rate sender to receiver (default: 0.0)', default=0.0, type=float)
    sim_group.add_argument('--drop-backward', metavar='DROP-RATE',
        help='simulated random drop rate receiver to sender (default: 0.0)', default=0.0, type=float)
    sim_group.add_argument('--drop-seq', metavar='SEQ-NUM', type=_convert_drop_list,
        help='list of sequence numbers with either:\n'
             '  * a number of times to drop them before not dropping, or\n'
             '  * a list of +s and -s where a + indicates not dropping and - indicates dropping (and then the sequence number is not dropped)\n'
             'example: 1=4,3=--+-,5=6 will drop sequence number of 1 four times;\n'
             '         drop sequence number 3 two times, then not drop it, then drop it, then not drop it\n'
             '         and drop sequence number 5 six times\n'
             'These drops are in addition to random drops and drops from full buffers.')
    sim_group.add_argument('--drop-ack', metavar='SEQ-NUM', type=_convert_drop_list,
        help='list of ack numbers to drop (backward only) and how many times. Same format as --drop-seq-num\n')
    sim_group.add_argument('--delay', help='minimum simulated link delay (default: 1 time unit)', default=1.0, type=float,
        metavar='TIME')
    sim_group.add_argument('--delay-variance', help='average extra random delay; total transmission delay will be the delay setting + an exponentially distributed extra delay (default: 0 extra delay)', default=0.0, type=float,
        metavar='TIME')
    sim_group.add_argument('--bandwidth', help='set simulated link bandwidth in both directions',
        type=float, default=None, action=SetBothBandwidth)
    sim_group.add_argument('--bandwidth-forward', help='simulated link bandwidth to receiver in packets per time unit (default: infinite)',
        default=float('inf'), type=float)
    sim_group.add_argument('--bandwidth-backward', help='simulated link bandwidth to sender in packets per time unit (default: infinite)',
        default=float('inf'), type=float)
    sim_group.add_argument('--buffer', help='simulated link buffer size in packets (default: 1 million)',
        default=1000000, type=float)
    sim_group.add_argument('--check-packets', help='check contents of packets for conformance', action='store_true', default=True)
    sim_group.add_argument('--no-check-packets', help='check contents of packets for conformance', action='store_false', dest='check-packets')
    sim_group.add_argument('--check-timeout', help='assume maximum timeout when checking packets (defualt: based on initial timeout + delay + delay-variance + min(queuing delay, time to transmit all messages))', type=float, default=None)

    args = parser.parse_args()
    for item in config_items:
        config.__dict__[item] = args.__dict__[item]
    messages = []
    for i in range(args.generate_input):
        messages.append(Message(
            data=f'M{i:#019x}'.encode('utf-8'),
            is_end = (i == args.generate_input - 1)
        ))
    run(args,  messages)
