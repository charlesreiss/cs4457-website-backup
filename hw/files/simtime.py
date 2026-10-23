"""
This module contains tools for implementing simulated time, so the emulation
can be run in realtime or accelerated time.

To use this module, one first calls either set_real_time() or set_fake_time(),
choosing whether the simulated time will track real time or not.

In order to properly advance fake time, this module relies on all threads
using sleep() or Queue.get() to wait for events.

After that is set, this module provides:
*  sleep() and time() functions, which are like the time module's functions.
*  a Queue class, which wraps the queue module.
"""

from dataclasses import dataclass, field
import heapq
import queue
from collections import deque
import time as _realtime
import threading

DEBUG = False

_impl = None

"""
Enable using real time.
"""
def set_real_time():
    global _impl
    _impl = RealTime()

"""
Enable using fake time.
"""
def set_fake_time():
    global _impl
    _impl = FakeTime()

def _check_impl():
    global _impl
    if _impl == None:
        raise Exception("Calling simtime function without calling set_real_time() or set_fake_time() first.")

def time():
    global _impl
    _check_impl()
    return _impl.time()

def sleep(s):
    global _impl
    _check_impl()
    return _impl.sleep(s)

def _mark_waiting():
    global _impl
    _check_impl()
    return _impl.mark_waiting()

def _mark_not_waiting():
    global _impl
    _check_impl()
    return _impl.mark_not_waiting()

def _mark_wake_from_trigger():
    global _impl
    _check_impl()
    return _impl.mark_wake_from_trigger()

def _mark_triggered_other():
    global _impl
    _check_impl()
    return _impl.mark_triggered_other()


class RealTime():
    """trivial implementation for using real-time"""
    def sleep(self, secs):
        _realtime.sleep(secs)

    def time(self):
        return _realtime.time()

    def mark_waiting(self):
        pass

    def mark_not_waiting(self):
        pass

    def mark_triggered_other(self):
        pass

    def mark_wake_from_trigger(self):
        pass

    def get_lock(self):
        return threading.Lock()

@dataclass(order=True)
class PendingQueue():
    triggered: bool = field(compare=False)
    cv: threading.Condition = field(compare=False)

_next_queue_id = 0

class Queue:
    def __init__(self):
        global _next_queue_id
        self._real_queue = deque()
        self._get_queue = deque()
        self._mutex = threading.Lock()
        self._id = _next_queue_id
        _next_queue_id += 1

    def get(self):
        with self._mutex:
            if DEBUG:
                print(f"sim_time: {threading.current_thread().name} Queue.get start {self._id}")
            while len(self._real_queue) == 0:
                pending = PendingQueue(
                    triggered=False,
                    cv=threading.Condition(self._mutex),
                )
                self._get_queue.append(pending)
                _mark_waiting()
                while not pending.triggered:
                    pending.cv.wait()
                _mark_wake_from_trigger()
                _mark_not_waiting()
            result = self._real_queue.popleft()
            if DEBUG:
                print(f"sim_time: {threading.current_thread().name} Queue.get done {self._id}: {result}")
            return result

    def put(self, data):
        with self._mutex:
            if DEBUG:
                print(f"sim_time: {threading.current_thread().name} Queue.put {self._id}: {data}")
            self._real_queue.append(data)
            if len(self._get_queue) > 0:
                if DEBUG:
                    print(f"sim_time: {threading.current_thread().name} Queue.put wake {self._id}")
                pending = self._get_queue.popleft()
                _mark_triggered_other()
                pending.triggered = True
                pending.cv.notify()

@dataclass(order=True)
class PendingSleep():
    target_time: float
    index: int
    triggered: bool = field(compare=False)
    cv: threading.Condition = field(compare=False)

# how close threads can be before we consider them "tied" for how much they are sleeping
SLEEP_EPSILON = 0


class FakeTime():
    def __init__(self):
        self._mutex = threading.Lock()
        self._current_time = 0.0
        self._next_index = 0
        self._pending_heap = []
        self._waiting_threads = set()
        self._triggered_not_woken = 0

    def time(self):
        with self._mutex:
            return self._current_time

    def _trigger(self, entry):
        entry.triggered = True
        assert self._current_time <= entry.target_time
        self._current_time = max(self._current_time, entry.target_time)
        entry.cv.notify()
        self._triggered_not_woken += 1

    def mark_triggered_other(self):
        with self._mutex:
            self._triggered_not_woken += 1

    def _wake_from_trigger(self):
        self._triggered_not_woken -= 1
        assert self._triggered_not_woken >= 0

    def mark_wake_from_trigger(self):
        with self._mutex:
            self._wake_from_trigger()

    def _dequeue_next(self):
        old_time = self._current_time
        if len(self._pending_heap) > 0:
            next_dequeue = heapq.heappop(self._pending_heap)
            self._trigger(next_dequeue)
        while len(self._pending_heap) > 0 and \
                self._pending_heap[0].target_time <= self._current_time + SLEEP_EPSILON:
            next_dequeue = heapq.heappop(self._pending_heap)
            self._trigger(next_dequeue)
        if DEBUG:
            print(f"sim_time: advanced from {old_time} to {self._current_time}")

    def mark_waiting_locked(self):
        assert(threading.get_ident() not in self._waiting_threads)
        self._waiting_threads.add(threading.get_ident())
        if len(self._waiting_threads) - self._triggered_not_woken == threading.active_count():
            if DEBUG:
                print(f"sim_time: all waiting, advance time")
            self._dequeue_next()

    def mark_not_waiting_locked(self):
        assert(threading.get_ident() in self._waiting_threads)
        self._waiting_threads.remove(threading.get_ident())

    def mark_waiting(self):
        with self._mutex:
            self.mark_waiting_locked()

    def mark_not_waiting(self):
        with self._mutex:
            self.mark_not_waiting_locked()

    def sleep(self, secs):
        if DEBUG:
            print(f"sim_time: {threading.current_thread().name} sleep {secs}")
            expect = self._current_time + secs
        with self._mutex:
            sleep_tracker = PendingSleep(
                target_time=self._current_time + secs,
                index = self._next_index,
                triggered = False,
                cv=threading.Condition(self._mutex),
            )
            if DEBUG:
                print(f"sim_time: {expect} versus {sleep_tracker.target_time}")
            self._next_index += 1
            heapq.heappush(self._pending_heap, sleep_tracker)
            self.mark_waiting_locked()
            while not sleep_tracker.triggered:
                sleep_tracker.cv.wait()
            self.mark_not_waiting_locked()
            self._wake_from_trigger()
