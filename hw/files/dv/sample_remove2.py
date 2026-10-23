'''
Sample file for manually running the simulator.
This sample
'''

import network_simulator

# Network 0
#
#    
# E0 
# | \    
# |  \   
# |1  \1 
# |    \ 
# |     \
# E2 --- E1
#     1
#
network0 = [
	[(1, 1), (2, 1)],         # E0
	[(0, 1), (2, 1)],         # E1
	[(0, 1), (1, 1)],        # E2
]

simulator = network_simulator.NetworkSimulator(network0, 499, 3)
simulator.run()
simulator.display_forwarding_table(0)
simulator.display_forwarding_table(1)
simulator.display_forwarding_table(2)
print("Ran initial simulation without link deleted....")
if input("Continue? (Y/n)") == 'N':
    sys.exit(0)
simulator.delete_link(0, 1)
simulator.delete_link(1, 0)
simulator.run()
simulator.display_forwarding_table(0)
simulator.display_forwarding_table(1)
simulator.display_forwarding_table(2)
print("Ran simulation after deleting link, but without periodic update....")
if input("Continue? (Y/n)") == 'N':
    sys.exit(0)
simulator.trigger_periodic_updates()
simulator.run()
simulator.display_forwarding_table(0)
simulator.display_forwarding_table(1)
simulator.display_forwarding_table(2)
print("Triggered periodic update....")
if input("Continue? (Y/n)") == 'N':
    sys.exit(0)

#######################################################################
# EXPECTED RESULTS
#######################################################################
# 
# Before link deleted:
#----------------------
# E0 | Cost | Next Hop
# ---+------+---------
# 0  |    0 |        0
# 1  |    1 |        1
# 2  |    1 |        2
# E1 | Cost | Next Hop
# ---+------+---------
# 0  |    2 |        0
# 1  |    0 |        1
# 2  |    1 |        2
# E2 | Cost | Next Hop
# ---+------+---------
# 0  |    1 |        0
# 1  |    1 |        1
# 2  |    0 |        2

# After link deleted, before periodic update:
#----------------------
# E0 | Cost | Next Hop
# ---+------+---------
# 0  |    0 |        0
# 1  |  inf |     None
# 2  |    1 |        2
# E1 | Cost | Next Hop
# ---+------+---------
# 0  |  inf |     None
# 1  |    0 |        1
# 2  |    1 |        2
# E2 | Cost | Next Hop
# ---+------+---------
# 0  |    1 |        0
# 1  |    1 |        1
# 2  |    0 |        2

# After peridoic update:
#----------------------
# E0 | Cost | Next Hop
# ---+------+---------
# 0  |    0 |        0
# 1  |    2 |        2
# 2  |    1 |        2
# E1 | Cost | Next Hop
# ---+------+---------
# 0  |    2 |        2
# 1  |    0 |        1
# 2  |    1 |        2
# E2 | Cost | Next Hop
# ---+------+---------
# 0  |    1 |        0
# 1  |    1 |        1
# 2  |    0 |        2
