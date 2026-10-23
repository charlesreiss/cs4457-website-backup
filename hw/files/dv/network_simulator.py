import bisect
import copy
import math
import random
import sys

# Local modules
import entity


class SimulationException(Exception):
    pass


class NetworkSimulator:
    '''
    The main simulator responsible for scheduling and delivering packets
    sent between entities in the network.
    '''

    def __init__(self, entity_links, seed=500, debug=0):
        '''
        Create and configure the simulator.

        Arguments:
        - `entity_links`: Array of entities containing (destination, cost)
                          tuples for all valid links in the network. See
                          project.py for examples.
        - `seed`:         Number to seed the random number generator with.
        - `debug`:        Debugging level (0-3).
        '''

        self.debug = debug

        # List of entities (nodes) in the network
        self.entities = []

        # Sorted list of packets traveling in the system.
        self.packets = []

        # Current time of the simulator
        self.time = 0.0

        # Setup random seed
        random.seed(seed)

        # Instantiate all of the entities
        self.entity_links = copy.deepcopy(entity_links)
        number_of_entities = len(entity_links)
        for i in range(number_of_entities):
            new_entity = entity.Entity(i, number_of_entities)
            self.entities.append(new_entity)

        # Supply each entity with its neighbor costs
        for i,ent in enumerate(self.entities):
            to_send = ent.initialize_costs(copy.deepcopy(entity_links[i]))
            self._to_layer2(i, to_send)

    def add_link(self, source, destination, cost):
        '''
        Add a new link
        '''
        self.entity_links[source].append((destination, cost))
        self._to_layer2(source, self.entities[source].add_neighbor(destination, cost))

    def delete_link(self, source, destination):
        '''
        Delete a link
        '''
        self.entity_links[source] = list(
            filter(lambda link: link[0] != destination, self.entity_links[source])
        )
        self._to_layer2(source, self.entities[source].delete_neighbor(destination))

    def trigger_periodic_updates(self):
        for i, entity in enumerate(self.entities):
            self._to_layer2(i, entity.periodic_update())

    def _to_layer2(self, entity_index, packets):
        '''
        Internal function used to schedule packet transmissions.
        '''

        for packet in packets:
            # Verify packet is valid.

            # Check the length of the costs value
            if len(packet.get_costs()) != len(self.entities):
                raise SimulationException('Invalid packet with incorrect number of cost values.')

            # Check that the destination is valid (i.e. it is a neighbor
            # of the sending node).
            for neighbor,cost in self.entity_links[entity_index]:
                if packet.get_destination() == neighbor:
                    break
            else:
                raise SimulationException(
                    f'Invalid packet (from {entity_index} to {packet.get_destination()}) '
                    f'with destination not one-hop.')

            # Check that the packet is not being sent to the sender.
            if packet.get_destination() == entity_index:
                raise SimulationException('Source and destination the same.')

            # Set the packet source.
            packet.set_source(entity_index)

            # Now actually send the packet by adding it to the queue with the
            # correct send time.
            if self.debug > 2:
                print('Sending Packet {} -> {}; contents: {}'.format(
                    packet.get_source(), packet.get_destination(), packet.get_costs()))

            # This packet should arrive sometime after the last packet with the same
            # source and destination. So, we need to find the latest packet with the
            # same source and destination.
            latest_time = self.time
            for packet_time, past_packet in self.packets:
                if packet.get_source() == past_packet.get_source() and \
                   packet.get_destination() == past_packet.get_destination():
                    latest_time = packet_time

            # Now we can calculate some time in the future for the packet time.
            arrival_time = latest_time + 1.0 + (random.uniform(0.0, 1.0) * 9.0)

            # Now we need to insert the packet into the array of packets correctly.
            bisect.insort(self.packets, (arrival_time, packet))

    def run(self):
        '''
        Run the actual simulator and stop when there are no more packets left.
        '''

        # Loop until there is nothing left to do
        while True:
            # No more packets means we are done
            if len(self.packets) == 0:
                break

            # Get the earliest packet in the system
            packet_time, next_packet = self.packets.pop(0)

            if self.debug > 1:
                print('')
                print('Handling packet at time={}'.format(packet_time))
                print('    {} -> {}  containing: {}'.format(
                    next_packet.get_source(),
                    next_packet.get_destination(),
                    next_packet.get_costs()))

            # Update our simulator time to when this packet happens
            self.time = packet_time

            # Pass the packet to the correct entity
            destination = next_packet.get_destination()
            to_send = self.entities[destination].update(next_packet)
            self._to_layer2(destination, to_send)

        # If we get here then we are done with the simulation
        if self.debug > 0:
            print('Simulation finished at time t={}'.format(self.time))


    def display_forwarding_table(self, entity_index):
        '''
        Print a forwarding table for a given entity for every destination in the
        network. Show the cost to that destination and the next hop.

        For example, an example forwarding table for entity 0 is:

            E0 | Cost | Next Hop
            ---+------+---------
            0  |    0 |        0
            1  |    1 |        1
            2  |    2 |        1
            3  |    4 |        1

        The first column contains the destinations.

        Arguments:
        - `entity_index`: The node to print the forwarding table for.
        '''

        final_costs = self.entities[entity_index].get_all_costs()

        print('E{} | Cost | Next Hop'.format(entity_index, ))
        print('---+------+---------')
        for i in range(len(self.entities)):
            print('{}  | {:>4} | {:>8}'.format(i, final_costs[i][1], str(final_costs[i][0])))

    def get_all_next_hops(self):
        return [
            [self.entities[i].forward_next_hop(j) for j in range(len(self.entities))]
                for i in range(len(self.entities))
        ]


    def route_packet(self, source, destination):
        '''
        Generate an array of hops, including the source and destination, for a
        packet traversing with the lowest cost through the network.
        '''

        hops = [source]
        while hops[-1] != destination:
            hops.append(self.entities[hops[-1]].forward_next_hop(destination))
        return hops

