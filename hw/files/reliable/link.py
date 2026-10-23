import copy
import config

from util import now, trace

class RandomDropRule():
    def __init__(self, simulator, drop_chance):
        self._rng = simulator.get_rng()
        self._drop_chance = drop_chance

    def drop_for(self, packet):
        return self._rng.uniform(0.0, 1.0) < self._drop_chance

    def to_json(self):
        return {
            'type': 'random',
            'chance': self._drop_chance,
        }

def _normalize_seqs(x):
    if x == None:
        return None
    else:
        result = {}
        for k, v in x.items():
            result[k] = list(reversed(v))
        return result

class FixedDropRule():
    def __init__(self, simulator, drop_seqs, drop_acks):
        self._simulator = simulator
        self._drop_seqs = _normalize_seqs(drop_seqs)
        self._drop_acks = _normalize_seqs(drop_acks)
        self._original_drop_seqs = copy.copy(self._drop_seqs)
        self._original_drop_acks = copy.copy(self._drop_acks)

    def _check_dict(self, num, pattern_dict):
        if pattern_dict == None:
            return False
        if num in pattern_dict:
            value = pattern_dict[num]
            result = value.pop()
            if len(value) == 0:
                del pattern_dict[num]
            return result
        else:
            return False

    def drop_for(self, packet):
        return self._check_dict(packet.seq_num, self._drop_seqs) or \
               self._check_dict(packet.ack_num, self._drop_acks)

    def to_json(self):
        return {
            'type': 'fixed',
            'seqs': self._original_drop_seqs,
            'acks': self._original_drop_acks,
        }

class RandomDelayRule():
    def __init__(self, simulator, delay_base, delay_variance):
        self._rng = simulator.get_rng()
        self._delay_base = delay_base
        self._delay_variance = delay_variance

    def delay_for(self, packet):
        if self._delay_variance > 0:
            extra = self._rng.expovariate(self._delay_variance)
        else:
            extra = 0.0
        return self._delay_base + extra

    def to_json(self):
        return {
            'base': self._delay_base,
            'variance': self._delay_variance,
        }

class Link:
    def __init__(self, simulator, buffer_obj, bandwidth, delay_rule, drop_rules, label):
        self._simulator = simulator
        self._bandwidth = bandwidth
        self._buffer = buffer_obj
        self._delay_rule = delay_rule
        self._drop_rules = drop_rules
        self._pending_transmit = None
        self._label = label
        self._total_sent = 0
        self._maximum_buffer = 0
        self._last_buffer_measure_time = 0.0
        self._buffer_time_occ = 0.0
        self._wrong_seq_num = 0

    def _transmit(self, packet):
        for drop_rule in self._drop_rules:
            if drop_rule.drop_for(packet):
                trace('link', f'sending {packet} on {self._label} link [dropped]')
                return
        delay = self._delay_rule.delay_for(packet)
        self._simulator.trace('link', f'sending {packet} on {self._label} link [{delay} transmission time]')
        self._simulator.create_timer(
            delay,
            lambda: packet._hidden_destination(packet),
            f'receiving {packet} on {self._label} link'
        )

    def transmit_next(self):
        packet = self._buffer.dequeue()
        if packet != None:
            self._transmit(packet)
            self._pending_transmit = self._simulator.create_timer(
                1.0 / self._bandwidth,
                lambda: self.transmit_next(),
                f'dequeue from buffer on {self._label} link',
            )
        else:
            self._pending_transmit = None

    def enqueue(self, packet, destination):
        packet = copy.copy(packet)
        self._total_sent += 1
        packet._hidden_destination = destination
        if packet.seq_num != None and packet.seq_num > config.MAXIMUM_SEQUENCE:
            error(f'packet had seq_num {packet.seq_num} > MAXIMUM_SEQUENCE = {config.MAXIMUM_SEQUENCE}')
            self._wrong_seq_num += 1
        self._buffer.enqueue(packet)
        try:
            used = self._buffer.get_current_used_count()
            self._maximum_buffer = max(used, self._maximum_buffer)
            time_delta = now() - self._last_buffer_measure_time
            self._buffer_time_occ += time_delta * used
            self._last_buffer_measure_time = now()
        except AttributeError:
            self._maximum_buffer = -1
        except TypeError:
            self._maximum_buffer = -1
        if self._pending_transmit == None:
            self.transmit_next()

    def json_info(self):
        return {
            'label': self._label,
            'total_dropped': getattr(self._buffer, '_drop_count', -1),
            'total_sent': self._total_sent,
            'buffer_size': getattr(self._buffer, '_capacity', -1),
            'maximum_buffer_used': self._maximum_buffer,
            'mean_buffer_used': self._buffer_time_occ / max(1.0, self._last_buffer_measure_time),
            'delay': self._delay_rule.to_json(),
            'drop_rules': list(map(lambda x: x.to_json(), self._drop_rules)),
            'wrong_seq_num': self._wrong_seq_num,
        }
