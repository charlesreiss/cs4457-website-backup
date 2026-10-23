from collections import deque
from util import trace, error

import config

class DropTailBuffer:
    def __init__(self, capacity, bandwidth, label):
        self._queue = deque()
        self._capacity = capacity
        self._label = label
        self._drop_count = 0

    def enqueue(self, packet):
        if len(self._queue) < self._capacity:
            trace('buffer-enqueue', f'buffering {packet} to {self._label} (buffer size {len(self._queue)}/{self._capacity})')
            self._queue.append(packet)
        else:
            self._drop_count += 1
            if config.BUFFER_DROP_IS_ERROR:
                error('buffer-drop', f'dropping {packet} to {self._label} due to full buffer; and buffer drops considered errors')
            else:
                trace('buffer-drop', f'dropping {packet} to {self._label} due to full buffer')

    def dequeue(self):
        if len(self._queue) == 0:
            return None
        else:
            packet = self._queue.popleft()
            trace('buffer-dequeue', f'unbuffering {packet} for {self._label}')
            return packet


    def get_current_used_count(self):
        # for statistics only
        return len(self._queue)

