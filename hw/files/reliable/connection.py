from util import Message, Packet, now, trace, error
from collections import deque
import config

"""
Implements the simulator logic for connections, including handling calls
from the Sender/Receiver.

Tracks how fast messages are received, whether mesages are dropped, average latencies,
etc.

Also has (currently unimplemented) placeholder to check sent packets for
protocol consistency properties.
"""
class Connection:
    def __init__(self, simulator, label, sender, receiver, forward_link, backward_link,
                 missing_is_error, check_packets, check_timeout_limit):
        self._simulator = simulator
        self._label = label
        self._missing_is_error = missing_is_error
        self._check_packets = check_packets
        self._check_timeout_limit = check_timeout_limit
        self._check_timeout = (check_timeout_limit != None)
        self._check_timeout_timers = {}
        if self._check_timeout and not self._check_packets:
            error('check_timeout_limit only supported with check_packets')
        self._check_next_seq = 0
        self._check_max_seq = None
        self._check_last_sent_seq_time = {}
        self._check_last_recv_seq_time = {}
        self._check_recv_not_ack = set()
        self._check_last_sent_seq = None
        self._check_last_sent_ack = None
        self._check_last_recv_ack = None
        self._check_no_first_recv_ack = None
        self._check_can_ack = None
        self._check_last_dup_ack_time = None
        self._check_first_sent_seq = None
        self._total_sent = 0
        self._total_received = 0
        self._total_received_latency = 0.0
        self._total_received_latency_squared = 0.0
        self._pending_messages = deque()
        self._in_flight_messages = deque()
        self._corrupt_message_count = 0
        self._skip_message_count = 0
        self._sender = sender
        self._sender.ready_for_more_from_application = lambda: self.send_pending()
        self._sender.to_network = lambda packet: self._enqueue_forward(packet)
        self._sender._label = label
        self._receiver = receiver
        self._receiver.to_application = lambda m: self.record_received(m)
        self._receiver.to_network = lambda packet: self._enqueue_backward(packet)
        self._receiver._label = label
        self._start_time = float('inf')
        self._finish_time = None
        self._forward_link = forward_link
        self._backward_link = backward_link
        self._generate_rate = 0
        self._generate_max = 0
        self._generate_count = 0
        if config.MODE == 'one-zero':
            maximum_window = 1
        elif config.MODE == 'sliding-window' or config.MODE == 'sliding':
            maximum_window = config.INITIAL_WINDOW
            assert maximum_window != None
        elif config.MODE == 'variable-sliding':
            maximum_window = config.MAXIMUM_WINDOW
            assert maximum_window != None
        elif self._check_packets:
            assert False, f"unknown mode {config.MODE}"
            maximum_window = None
        self._check_maximum_window = maximum_window
        self._check_wraparound = None

    """generate messages at an exponentially distributed rate instead of using pending message logic"""
    def generate_messages(self, rate, total_messages):
        self._generate_max = total_messages
        self._generate_rate = rate
        self._generate_next()

    """internal function for generate_messages()"""
    def _generate_next(self)-> None:
        if self._generate_max == None or self._generate_count < self._generate_max:
            self._generate_count += 1
            msg = Message(
                data=f'C{self._label:4s}M{self._generate_count:#015x}',
                is_end=self._generate_count == self._generate_max
            )
            trace('generate-next', f'data = {msg.data}')
            self.send_messages([msg])
            if not msg.is_end:
                self._simulator.create_timer(
                    self._simulator.get_rng().expovariate(self._generate_rate),
                    lambda: self._generate_next(),
                    f'generate message for {self._label} (after {self._generate_count})',
                )

    def _check_next(self, seq):
        if self._check_wraparound:
            return (seq + 1) % self._check_wraparound
        else:
            return seq + 1

    def _check_prev(self, seq):
        if self._check_wraparound:
            return (seq - 1 + self._check_wraparound) % self._check_wraparound
        else:
            return seq - 1

    def _check_delta(self, seq1, seq2):
        if self._check_wraparound:
            delta = (self._check_wraparound + seq1 - seq2) % self._check_wraparound
            if delta > self._check_wraparound / 2:
                delta -= self._check_wraparound
            assert(delta < self._check_wraparound and delta > -self._check_wraparound)
            return delta
        else:
            return seq2 - seq1

    def _check_update_last_sent_seq(self, seq_num):
        if self._check_last_sent_seq == None:
            self._check_last_sent_seq = seq_num
            return
        if self._check_last_recv_ack != None:
            delta = self._check_delta(self._check_last_recv_ack + 1, seq_num)
            trace('check', f'update last sent seq for {seq_num}, delta {delta}')
        else:
            delta = None
            trace('check', f'update last sent seq for {seq_num} (no previous ACK)')
        if self._check_wraparound == None:
            if delta != None:
                if self._check_maximum_window and abs(delta) > self._check_maximum_window:
                    # FIXME(cr4bd): this assumes that first seq_num after wraparound is 0
                    if seq_num == 0:
                        self._check_wraparound = self._check_last_recv_ack + 1
                        trace(
                            'check', 
                            f'presuming wraparound at {self._check_wraparound}')
                        assert(self._check_wraparound > 1)
                        self._check_last_sent_seq = 0
                    else:
                        error(f'sent {seq_num} with last received ack of {self._check_last_recv_ack}, '
                              f'which suggests window size of at least {abs(delta)} > '
                              f'expected maximum {self._check_maximum_window}')
        elif delta == None or abs(delta) < self._check_maximum_window:
            if seq_num > self._check_last_sent_seq:
                self._check_last_sent_seq = seq_num
        elif self._check_last_recv_ack != None:
            delta = self._check_delta(seq_num, self._check_last_recv_ack)
            if abs(delta) > self._check_maximum_window:
                error(f'sent {seq_num} after {self._check_last_sent_seq_num}, '
                      f'which suggests window size of at least {abs(delta)} '
                      f'(assuming with wraparound {self._check_wraparound} becomes 0), '
                      f'but expected maximum window {self._check_maximum_window}')
            if delta > 0:
                self._check_last_sent_seq = seq_num
        else:
            delta = self._check_delta(self._check_first_sent_seq, seq_num)
            if abs(delta) > self._check_maximum_window:
                error(f'sent {seq_num} after {self._check_last_sent_seq_num}, '
                      f'which suggests window size of at least {abs(delta)} '
                      f'(assuming with wraparound {self._check_wraparound} becomes 0), '
                      f'but expected maximum window {self._check_maximum_window}')
            if delta > 0:
                self._check_last_sent_seq = seq_num

    def _check_forward_start(self, packet: Packet) -> None:
        if self._check_packets:
            if packet.ack_num != None:
                error('source -> receiver packet with ack_num set')
            if packet.seq_num == None:
                error('source -> receiver packet with seq_num not set')
            else:
                if self._check_first_sent_seq == None:
                    self._check_first_sent_seq = packet.seq_num
                self._check_last_sent_seq_time[packet.seq_num] = now()
                self._check_update_last_sent_seq(packet.seq_num)
                if self._check_last_recv_ack != None:
                    ack_delta = self._check_delta(self._check_last_recv_ack, packet.seq_num)
                    if ack_delta != None and ack_delta < 0:
                        error(f'resending seq #{packet.seq_num}, which was already acknowledged (last recv ack {self._check_last_recv_ack})')
        if self._check_timeout:
            if packet.seq_num in self._check_timeout_timers:
                self._check_timeout_timers[packet.seq_num].canceled = True
            self._check_timeout_timers[packet.seq_num] = self._simulator.create_timer(
                self._check_timeout_limit,
                lambda: error(f'#{packet.seq_num} not resent after {self._check_timeout_limit} and did not see relevant ACK'),
                f'verify that timeout exists for #{packet.seq_num}'
            )


    def _check_advance_ack(self):
        if self._check_can_ack == None:
            if self._check_first_sent_seq not in self._check_recv_not_ack:
                trace('check', f'no expected ack number since first packet not received')
                return
            else:
                self._check_can_ack = self._check_first_sent_seq
                trace('check', f'initializing first expected ack to {self._check_can_ack}')
        while True:
            trace('check', f'trying to advance expeced ack from {self._check_can_ack}')
            next_ack = self._check_next(self._check_can_ack)

            # cannot acknowledge packets not received
            if next_ack not in self._check_recv_not_ack:
                trace('check', f'rejecting: {next_ack} not received')
                break

            if self._check_last_sent_ack != None:
                # cannot acknowledge outside window starting at last sent ack
                    # we assume last_sent_ack is initialized to the first seq# - 1
                    # which is done by _check_forward_end
                last_delta = self._check_delta(self._check_last_sent_ack + 1, next_ack)
                trace('check', f'{next_ack} is {last_delta} away from one-past last ACK {self._check_last_sent_ack + 1} [{self._check_wraparound}]')
                if self._check_maximum_window and last_delta >= self._check_maximum_window or last_delta < 0:
                    trace('check', f'rejecting: {next_ack} would be out of window '
                        f'[{self._check_last_sent_ack + 1}, '
                        f'{self._check_last_sent_ack + 1 + self._check_maximum_window})')
                    break
            else:
                pass

            self._check_can_ack = next_ack

    def _check_forward_end(self, packet: Packet) -> None:
        if self._check_packets:
            if packet.seq_num != None:
                self._check_last_recv_seq_time[packet.seq_num] = now()
                self._check_recv_not_ack.add(packet.seq_num)
                self._check_advance_ack()

    def _enqueue_forward(self, packet: Packet) -> None:
        packet.label = self._label
        self._check_forward_start(packet)
        self._forward_link.enqueue(packet, self._to_receiver_from_network)

    def _to_receiver_from_network(self, packet: Packet) -> None:
        self._check_forward_end(packet)
        self._receiver.from_network(packet)

    def _check_backward_start(self, packet: Packet) -> None:
        if self._check_packets:
            if packet.seq_num != None:
                error('receiver -> source packet with seq_num sent')
            if packet.ack_num == None:
                error('receiver -> source packet without ack_num set')
            else:
                if self._check_can_ack != None:
                    prev_ack = self._check_last_sent_ack
                    self._check_last_sent_ack = packet.ack_num
                    delta = self._check_delta(packet.ack_num, self._check_can_ack)
                    if packet.ack_num not in self._check_last_recv_seq_time:
                        if self._check_last_recv_seq_time.get(self._check_first_sent_seq, None) != None:
                            error(f'sending ack #{packet.ack_num}, but seq #{packet.seq_num} never received')
                        else:
                            # ACK indicating first packet not received can have arbitrary number
                            pass
                    elif delta > 0:
                        if packet.ack_num < self._check_can_ack:
                            error(f'sending ack #{packet.ack_num} (~ '
                                  f'{packet.ack_num + self._check_wraparound} after '
                                  f' accounting for apparent wraparound at {self._check_wraparound})'
                                  f', but can only acknowledge up to seq #{self._check_can_ack}')
                        else:
                            error(f'sending ack #{packet.ack_num}, but can only acknowledge up to seq #{self._check_can_ack}')
                    elif delta < 0:
                        if packet.ack_num > self._check_can_ack:
                            error(f'sending ack #{packet.ack_num}, but could ack '
                                  f'#{self._check_can_ack} (delta {delta})' +
                                  f'(~ #{self._check_can_ack + self._check_wraparound} '
                                  f'accounting for apparent wraparound at {self._check_wraparound})')
                        else:
                            error(f'sending ack #{packet.ack_num}, but could ack #{self._check_can_ack} (delta {delta})')
                    else:
                        trace('check', f'got ACK {packet.ack_num} after ACK {prev_ack}')
                        if prev_ack != None:
                            to_mark_seq = prev_ack
                            while to_mark_seq != packet.ack_num:
                                trace('check', f'prev_ack = {prev_ack}; / current {packet.ack_num} ; seq {to_mark_seq} / {self._check_wraparound}')
                                self._check_recv_not_ack.discard(to_mark_seq)
                                to_mark_seq = self._check_next(to_mark_seq)
                        else:
                            if self._check_delta(self._check_first_sent_seq, packet.ack_num) > self._check_maximum_window:
                                error(f'first ACK #{packet.ack_num} too far away from first sent sequence number {self._check_first_sent_seq}')
                            to_mark_seq = packet.ack_num
                        self._check_recv_not_ack.discard(to_mark_seq)
                        self._check_advance_ack()
                else:
                    if self._check_no_first_recv_ack == None:
                        self._check_no_first_recv_ack = packet.ack_num
                    elif packet.ack_num != self._check_no_first_recv_ack:
                        error(f'sending ack #{packet.ack_num} when first sequence number sent '
                              f'(#{packet.seq_num}) not yet received, '
                              f'previously sent #{self._check_no_first_recv_ack}')
                             

    def _check_backward_end(self, packet: Packet) -> None:
        if self._check_packets:
            if packet.ack_num != None:
                prev_ack = None
                if self._check_last_recv_ack != None:
                    delta = self._check_delta(self._check_last_recv_ack, packet.ack_num)
                    trace('check', f'processing ACK {packet.ack_num}: delta = {delta}')
                    if delta > 0:
                        prev_ack = self._check_last_recv_ack
                        self._check_last_recv_ack = packet.ack_num
                elif self._check_can_ack != None:
                    prev_ack = self._check_first_sent_seq
                    self._check_last_recv_ack = packet.ack_num
                if self._check_timeout and prev_ack != None:
                    current = prev_ack
                    while True:
                        if current in self._check_timeout_timers:
                            self._check_timeout_timers[current].canceled = True
                        if current == packet.ack_num:
                            break
                        current = self._check_next(current)

    def _enqueue_backward(self, packet: Packet) -> None:
        packet.label = self._label
        self._check_backward_start(packet)
        self._backward_link.enqueue(packet, self._to_sender_from_network)

    def _to_sender_from_network(self, packet: Packet) -> None:
        self._check_backward_end(packet)
        self._sender.from_network(packet)

    def send_messages(self, messages: list[Message]) -> None:
        self._start_time = min(self._start_time, now())
        self._pending_messages.extend(messages)
        self.send_pending()

    def send_pending(self) -> None:
        while len(self._pending_messages) > 0:
            result = self._sender.from_application(self._pending_messages[0])
            if result == None:
                error('from_application() in sender did not return True or False')
            if result:
                message = self._pending_messages.popleft()
                self._total_sent += 1
                trace('conn-sent', f'{self._label}: sent message #{self._total_sent} ({message})')
                self._in_flight_messages.append((now(), message))
            else:
                break

    def record_received(self, actual_message: Message) -> None:
        if len(self._in_flight_messages) == 0:
            self._corrupt_message_count += 1
            error(f'received excess message when none expected')
            return
        timestamp, expect_message = self._in_flight_messages.popleft()
        self._total_received += 1
        if expect_message == actual_message:
            time_delta = now() - timestamp
        else:
            skip = 1
            found = False
            for timestamp, item in self._in_flight_messages:
                if actual_message == item:
                    found = True
                    break
                skip += 1
            if found:
                for _ in range(skip):
                    self._in_flight_messages.popleft()
                if self._missing_is_error:
                    error(f'missing {skip} messages before received message #{self._total_received}')
                self._skip_message_count += skip
                time_delta = now() - timestamp
            else:
                time_delta = None
                if self._missing_is_error:
                    error(f'received message #{self._total_received} corrupted; got {actual_message}, expected {expect_message}')
                self._corrupt_message_count += 1
        if time_delta != None:
            self._total_received_latency += time_delta
            self._total_received_latency_squared += time_delta * time_delta
        trace('link', f'received message #{self._total_received} ({actual_message})')

    def _latency_mean_and_variance(self):
        if self._total_received > 0:
            latency_mean = self._total_received_latency / self._total_received
            latency_variance = (self._total_received_latency_squared / self._total_received) - \
                latency_mean * latency_mean
        else:
            latency_mean = float('nan')
            latency_variance = float('nan')
        return latency_mean, latency_variance

    def print_statistics(self):
        unfinished = (self._finish_time == None)
        if unfinished:
            end_time = now()
        else:
            end_time = self._finish_time
        if self._generate_rate:
            print(f'{self._label}: generated {self._generate_rate:.1f} packets/sec')
        print(f"{self._label}: received {self._total_received} in {end_time - self._start_time:.1f} ({self._total_received / (end_time - self._start_time):.1f} messages/time unit)")
        latency_mean, latency_variance = self._latency_mean_and_variance()
        print(f"{self._label}: latency: mean {latency_mean:.2f} "
              f" +/- sd {math.sqrt(latency_variance):.2f}")
        if len(self._in_flight_messages) > 0 or self._skip_message_count > 0 or \
                self._corrupt_message_count > 0:
            print(f"{self._label}: {self._skip_message_count} messages skipped, {len(self._in_flight_messages)} not received at end, {self._corrupt_message_count} corrupt or received out-of-order")

    def json_info(self):
        unfinished = (self._finish_time == None)
        if unfinished:
            end_time = now()
        else:
            end_time = self._finish_time
        latency_mean, latency_variance = self._latency_mean_and_variance()
        return {
            'generate_rate': self._generate_rate,
            'received': self._total_received,
            'time': end_time - self._start_time,
            'received_rate': self._total_received / (end_time - self._start_time),
            'skipped': self._skip_message_count,
            'corrupt': self._corrupt_message_count,
            'in_flight': len(self._in_flight_messages),
            'latency_mean': latency_mean,
            'latency_sd': math.sqrt(latency_variance),
        }
