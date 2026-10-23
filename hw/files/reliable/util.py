import config

import traceback
from dataclasses import dataclass
from typing import Optional

"""The active simulator; set by simulator.py."""
_simulator = None

"""Get current simulated time."""
def now():
    return _simulator.time()

"""Output a message with label 'label' if that label is in config.TRACE or 'all' is config.TRACE."""
def trace(label, message):
    _simulator.trace(label, message)

"""Output an error message."""
def error(message):
    _simulator.error(message)

"""Represents a packet."""
@dataclass
class Packet:
    data: Optional[bytes] = None
    is_end: bool = False
    seq_num: Optional[int] = None
    ack_num: Optional[int] = None
    timestamp: Optional[float] = None

    # for optional implementation of selective acknowledgments
    sack: Optional[list[int] | list[(int, int)]] = None

    # used on 'schedule' assignment
    label: str = '(unset)'

    # internal simulator use only, do not change
    _hidden_destination = None

@dataclass
class Message:
    data: bytes
    is_end: bool = False

def create_timer(timeout, function, description=None):
    if description == None:
        the_stack = traceback.extract_stack()
        description = f'timer created on {the_stack[-2][0]} line {the_stack[-2][1]} (in {the_stack[-2][2]})'
    return _simulator.create_timer(timeout, function, description)

def cancel_timer(timer):
    timer.canceled = True

class SenderBase:
    def to_network(self, packet: Packet) -> None:
        self._simulator.send_packet(packet, to='receiver')

    def ready_for_more_from_application(self):
        self._simulator.send_pending()

class ReceiverBase:
    def to_application(self, message: Message) -> None:
        self._simulator.record_received(message)

    def to_network(self, packet: Packet) -> None:
        self._simulator.send_packet(packet, to='sender')
