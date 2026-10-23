'''
Sample file for manually running the simulator.
This sample
'''

import network_simulator

# Network 0
#
#    
# E0 
# | 
# | 
# |7
# | 
# | 
# E2 --- E1
#     1
#
network0 = [
	[(2, 7)],         # E0
	[(2, 1)],         # E1
	[(0, 7), (1, 1 )],        # E2
]

simulator = network_simulator.NetworkSimulator(network0, 499, 3)
simulator.run()
simulator.display_forwarding_table(0)
simulator.display_forwarding_table(1)
simulator.display_forwarding_table(2)
print("route from 0 to 2", simulator.route_packet(0, 2))
print("Ran initial simulation without link addded ...")
if input("Continue? (Y/n)") == 'N':
    sys.exit(0)
#    
# E0 
# | *
# |  * 2
# |7  *
# |    *
# |     *
# E2 --- E1
#     1
#
simulator.add_link(source=0, destination=1, cost=2)
simulator.add_link(source=1, destination=0, cost=2)
simulator.run()
simulator.display_forwarding_table(0)
simulator.display_forwarding_table(1)
simulator.display_forwarding_table(2)

#######################################################################
# EXPECTED RESULTS
#######################################################################
# 
# Before link added:
#----------------------
# E0 | Cost | Next Hop
# ---+------+---------
# 0  |    0 |        0
# 1  |    8 |        2
# 2  |    7 |        2
# E1 | Cost | Next Hop
# ---+------+---------
# 0  |    8 |        2
# 1  |    0 |        1
# 2  |    1 |        2
# E2 | Cost | Next Hop
# ---+------+---------
# 0  |    7 |        0
# 1  |    1 |        1
# 2  |    0 |        2
#
# After link added:
#----------------------
# E0 | Cost | Next Hop
# ---+------+---------
# 0  |    0 |        0
# 1  |    2 |        1
# 2  |    3 |        1
# E1 | Cost | Next Hop
# ---+------+---------
# 0  |    2 |        0
# 1  |    0 |        1
# 2  |    1 |        2
# E2 | Cost | Next Hop
# ---+------+---------
# 0  |    3 |        1
# 1  |    1 |        1
# 2  |    0 |        2

