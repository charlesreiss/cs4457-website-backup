import config
import copy
from util import Packet, Message, create_timer, cancel_timer, now, trace, error
from buffer import DropTailBuffer
from link import Link
from connection import Connection
import util

import argparse
import json
import random
import re
import sys
import math
from collections import deque
from dataclasses import dataclass
from heapq import heappush, heappop
from typing import Optional

@dataclass
class Event:
    time: float
    action: callable
    description: str
    index: int = 0
    canceled: bool = False

    def __lt__(self, other) -> bool:
        if self.time == other.time:
            return self.index < other.index
        else:
            return self.time < other.time

class Simulator:
    def __init__(self, args):
        self._args = args
        self._rng = random.Random(42)
        self._event_list = []
        self._connections = {}
        self._links = {}
        self._next_index = 0
        self._lsat_time = self._time = 0.0
        self._in_run_event = False
        self.done = False

    def get_rng(self):
        return self._rng

    def time(self) -> float:
        return self._time

    def add_event(self, event: Event) -> None:
        event.index = self._next_index
        self._next_index += 1
        heappush(self._event_list, event)

    def _pop_event(self) -> Optional[Event]:
        if len(self._event_list) > 0:
            return heappop(self._event_list)
        else:
            return None
 
    def error(self, description):
        if len(config.TRACE) > 0:
            print(f"ERROR: at time={self._time:9.1f}: {description}")
        else:
            print(f"ERROR: at time={self._time:9.1f}: {description}", file=sys.stderr)
        if config.ERROR_IS_CRASH:
            sys.exit(1)

    def trace(self, label, description):
        if label in config.TRACE or 'all' in config.TRACE:
            print(f"at time={self._time:9.1f}: [{label}] {description}")

    def new_link(self, label, bandwidth, buffer_size, delay_rule, buffer_cls=DropTailBuffer, drop_rules=None):
        buffer_obj = buffer_cls(buffer_size, bandwidth, label)
        link = self._links[link._label] = Link(
            simulator=self,
            bandwidth=bandwidth,
            buffer_obj=buffer_obj,
            delay_rule=delay_rule,
            drop_rules=drop_rules,
            label=label,
        )
        return link

    def new_connection(self, label, sender, receiver, forward_link_name,
                       backward_link_name, missing_is_error=True,
                       check_packets=False, check_timeout_limit=None):
        result = self._connections[label] = Connection(
            simulator=self,
            label=label,
            sender=sender,
            receiver=receiver,
            forward_link=self._links[forward_link_name],
            backward_link=self._links[backward_link_name],
            missing_is_error=missing_is_error,
            check_packets=check_packets,
            check_timeout_limit=check_timeout_limit,
        )
        result._generate_next()
        return result

    def _run_next(self) -> bool:
        assert not self._in_run_event
        event = self._pop_event()
        if event != None:
            self._time = max(self._time, event.time)
            if not event.canceled:
                self._last_time = self._time
                self._in_run_event = True
                trace('events', f"running {event.description}")
                event.action()
                self._in_run_event = False
            return True
        else:
            return False

    def run(self, time_limit=None):
        assert util._simulator == self
        while not self.done and self._run_next():
            if time_limit != None and self._time > time_limit:
                self.done = True

    def _finish_send_back(self, to, destination, packet):
        destination.from_network(packet)
        self._scheduled_by_link[to] -= 1

    def send_packet(self, packet, to=None):
        if to not in self._links:
            raise Exception(f'internal error, invalid packet destination {to}')
        self._links[to].enqueue(packet)

    def create_timer(self, timeout, function, description) -> Event:
        event = Event(
            time = self.time() + timeout,
            action = function,
            description = description
        )
        self.add_event(event)
        return event

    def last_time(self):
        return self._last_time
