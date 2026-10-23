import config
from util import Packet, Message, now, trace

class MySender:
    def __init__(self):
        pass

    def from_application(self, message):
        packet = Packet()
        packet.data = message.data
        packet.is_end = message.is_end
        packet.seq_num = 0
        self.to_network(packet)
        return True

    def from_network(self, packet):
        pass

class MyReceiver:
    def __init__(self):
        pass

    def from_network(self, packet):
        message = Message(data=packet.data, is_end=packet.is_end)
        self.to_application(message)
