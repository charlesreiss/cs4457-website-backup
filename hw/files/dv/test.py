import argparse
import io
import json
import math
import os
import re
import sys

import network_simulator

from util import print_next_hop_table, print_next_hop_table_delta

def run_and_get_next_hops(
        links,
        link_adjustments,
        trigger_periodic_updates,
        seed,
        debug,
):
    simulator = network_simulator.NetworkSimulator(links, seed=seed, debug=debug)
    simulator.run()
    if link_adjustments != None:
        for source, destination, new_cost in link_adjustments:
            if new_cost == math.inf:
                simulator.delete_link(source, destination)
            else:
                simulator.add_link(source, destination, new_cost)
        simulator.run()
    if trigger_periodic_updates:
        simulator.trigger_periodic_updates()
        simulator.run()
    return simulator.get_all_next_hops()

def normalize_next_hops(next_hops):
    """
    Convert a next-hops table to a canonical form to make comparison simpler.
    
    Replaces lists with immutable tuples and replaces -1 with None
    """
    if next_hops == None:
        return None
    def normalize_row(row):
        return tuple(map(lambda x: x if x != -1 else None, row))
    return tuple(map(normalize_row, next_hops))

def run_test(
    label,
    links,
    diagram,
    expected_next_hops,
    out_fh,
    link_adjustments=None,
    trigger_periodic_updates=False,
    verbose=True,
    type=None,
    debug=0,
    seed=500,
):
    print(f"----")
    print(f"For test {label}", file=out_fh)
    # use of tuple is to make sure == works
    try:
        actual_next_hops = run_and_get_next_hops(
            links=links, link_adjustments=link_adjustments,
            trigger_periodic_updates=trigger_periodic_updates,
            seed=seed, debug=debug,
        )
    except:
        import traceback
        print("EXCEPTION OCCURRED DURING SIMULATION",file=out_fh)
        print("---------",file=out_fh)
        traceback.print_exc(file=out_fh)
        print("---------",file=out_fh)
        actual_next_hops = None
    actual_next_hops = normalize_next_hops(actual_next_hops)
    expected_next_hops = normalize_next_hops(expected_next_hops)
    mismatch = actual_next_hops != expected_next_hops
    if verbose or mismatch:
        print(f"Network diagram:\n{diagram}", file=out_fh)
        print("Expected next hop table:", file=out_fh)
        print_next_hop_table(expected_next_hops, out_fh)
        print("Actual next hop table:", file=out_fh)
        if actual_next_hops != None:
            print_next_hop_table(actual_next_hops, out_fh)
        else:
            print("  <not available>", file=out_fh)
    if mismatch:
        if actual_next_hops != None:
            print_next_hop_table_delta(actual_next_hops, expected_next_hops, out_fh)
        passed = False
    else:
        print(f"Passed test {label}\n")
        passed = True
    return {
        'type': type,
        'label': label,
        'passed': passed,
        'actual_next_hops': actual_next_hops,
        'expected_next_hops': expected_next_hops,
    }

TESTS = [
    {
        "label": "all 1 weights, triangle",
        "type": "direct",
        "links": [
            [(1, 1), (2, 1)],         # E0
            [(0, 1), (2, 1)],         # E1
            [(0, 1), (1, 1)],        # E2
        ],
        "diagram": r"""
                    E0 
                    | \    
                    |  \   
                    |1  \1 
                    |    \ 
                    |     \
                    E2 --- E1
                        1
        """,
        "expected_next_hops": [
            # E0
            (0, 1, 2),
            # E1
            (0, 1, 2),
            # E2
            (0, 1, 2),
        ],
    },
    {
        "label": "all 1 weights, 5 fully connected",
        "type": "direct",
        "links": [
            [(1, 1), (2, 1), (3, 1), (4, 1)],         # E0
            [(0, 1), (2, 1), (3, 1), (4, 1)],         # E1
            [(0, 1), (1, 1), (3, 1), (4, 1)],         # E2
            [(0, 1), (1, 1), (2, 1), (4, 1)],         # E3
            [(0, 1), (1, 1), (2, 1), (3, 1)],         # E4
        ],
        "diagram": r"""

            all links weight 1:

              /-E0--------E1-\
             /  | \      /|   \
             |  |  \    / |    \
             |  |   [E4]  |    |
             |  |  /    \ |    |
             |  | /      \|    |
             |  E2--------E3   |
             \   \        /    /
              \-| \ |----/    /
                   \         /
                    \-------/

        """,
        "expected_next_hops": [
            # E0
            (0, 1, 2, 3, 4),
            # E1
            (0, 1, 2, 3, 4),
            # E2
            (0, 1, 2, 3, 4),
            # E3
            (0, 1, 2, 3, 4),
            # E4
            (0, 1, 2, 3, 4),
        ],
    },
    {
        "label": "5-line",
        "type": "indirect-one",
        "links": [
            [(1, 1)],           # E0
            [(0, 1), (2, 2)],   # E1
            [(1, 2), (3, 1)],   # E2
            [(2, 1), (4, 3)],   # E3
            [(3, 3)],           # E4
        ],
        "diagram": r"""
            E0------E1------E2------E3------E4
                1        2      1       3
        """,
        "expected_next_hops": [
            # E0
            (0, 1, 1, 1, 1),
            # E1
            (0, 1, 2, 2, 2),
            # E2
            (1, 1, 2, 3, 3),
            # E3
            (2, 2, 2, 3, 4),
            # E4
            (3, 3, 3, 3, 4),
        ],
    },
    {
        "label": "5-line with entities out of order",
        "type": "indirect-one",
        "links": [
            [(3, 1)],           # E0
            [(4, 3)],           # E1
            [(3, 2), (4, 1)],   # E2
            [(0, 1), (2, 2)],   # E3
            [(2, 1), (1, 3)],   # E4
        ],
        "diagram": r"""
            E0------E3------E2------E4------E1
                1        2      1       3
        """,
        "expected_next_hops": [
            # E0
            (0, 3, 3, 3, 3),
            # E1
            (4, 1, 4, 4, 4),
            # E2
            (3, 4, 2, 3, 4),
            # E3
            (0, 2, 2, 3, 2),
            # E4
            (2, 1, 2, 2, 4),
        ],
    },
    {
        "label": "complete binary tree with depth 2",
        "type": "indirect-one",
        "links": [
            [(1, 1), (2, 1)],         # E0
            [(0, 1), (3, 2), (4, 2)], # E1
            [(0, 1), (5, 2), (6, 2)], # E2
            [(1, 2)],   # E3
            [(1, 2)],   # E4
            [(2, 2)],   # E5
            [(2, 2)],   # E6
        ],
        "diagram": r"""
                         E0
                      1/    \1
                      /      \
                     E1       E2
                   2/  \2   2/  \2
                   /    \   /    \
                  E3    E4  E5    E6
        """,
        "expected_next_hops": [
            # E0
            (0, 1, 2, 1, 1, 2, 2),
            # E1
            (0, 1, 0, 3, 4, 0, 0),
            # E2
            (0, 0, 2, 0, 0, 5, 6),
            # E3
            (1, 1, 1, 3, 1, 1, 1),
            # E4
            (1, 1, 1, 1, 4, 1, 1),
            # E5
            (2, 2, 2, 2, 2, 5, 2),
            # E6
            (2, 2, 2, 2, 2, 2, 6),
        ],
    },
    {
        "label": "all 1 weights, 5-loop",
        "type": "indirect-choices",
        "links": [
            # E0
            [(1, 1), (4, 1)],
            # E1
            [(0, 1), (2, 1)],
            # E2
            [(1, 1), (3, 1)],
            # E3
            [(2, 1), (4, 1)],
            # E4
            [(3, 1), (0, 1)],
        ],
        "diagram": r"""
                    E0-----E1
                    |   1   \
                    |        \
                    |1        \1
                    |          \
                    |           \
                    E4 --- E3----E2
                        1     1
        """,
        "expected_next_hops": [
            # E0
            (0, 1, 1, 4, 4),
            # E1
            (0, 1, 2, 2, 0),
            # E2
            (1, 1, 2, 3, 3),
            # E3
            (4, 2, 2, 3, 4),
            # E4
            (0, 0, 3, 3, 4),
        ],
    },
    {
        "label": "5-loop, 1 weights + one 3 weight",
        "type": "indirect-choices",
        "links": [
            # E0
            [(1, 1), (4, 1)],
            # E1
            [(0, 1), (2, 3)],
            # E2
            [(1, 3), (3, 1)],
            # E3
            [(2, 1), (4, 1)],
            # E4
            [(3, 1), (0, 1)],
        ],
        "diagram": r"""
                    E0-----E1
                    |   1   \
                    |        \
                    |1        \3
                    |          \
                    |           \
                    E4 --- E3----E2
                        1     1
        """,
        "expected_next_hops": [
            # E0
            (0, 1, 4, 4, 4),
            # E1
            (0, 1, 2, 0, 0),
            # E2
            (3, 1, 2, 3, 3),
            # E3
            (4, 4, 2, 3, 4),
            # E4
            (0, 0, 3, 3, 4),
        ],
    },
    {
        "label": "network0",
        "type": "indirect-choices",
        "links": [
            [(1, 2), (2, 7)],         # E0
            [(0, 2), (2, 1)],         # E1
            [(0, 7), (1, 1 )],        # E2
        ],
        "diagram": r"""
                    E0 
                    | \    
                    |  \   
                    |7  \2 
                    |    \ 
                    |     \
                    E2 --- E1
                        1
        """,
        "expected_next_hops": [
            # E0
            (0, 1, 1),
            # E1
            (0, 1, 2),
            # E2
            (1, 1, 2),
        ]
    },
    {
        "label": "network1",
        "links": [
            [(1, 1), (2, 3), (3, 7)], # E0
            [(0, 1), (2, 1)],         # E1
            [(0, 3), (1, 1), (3, 2)], # E2
            [(0, 7), (2, 2)],         # E3
        ],
        "diagram": r"""
               1
            E0 --- E1
            | \    |
            |  \   |
            |7  \3 | 1
            |    \ |
            |     \|
            E3 --- E2
                2
        """,
        "expected_next_hops": [
            # E0
            (0, 1, 1, 1),
            # E1
            (0, 1, 2, 2),
            # E2
            (1, 1, 2, 3),
            # E3
            (2, 2, 2, 3),
        ]
    },
    {
        "label": "network2",
        "type": "indirect-choices",
        "links": [
            [(1, 1), (3, 5), (5, 3)], # E0
            [(0, 1), (2, 2), (3, 3)], # E1
            [(1, 2), (4, 1)],         # E2
            [(0, 5), (1, 3)],         # E3
            [(2, 1), (5, 8)],         # E4
            [(0, 3), (4, 8)],         # E5
        ],
        "diagram": r"""

                     1      2
                 E0 --- E1 --- E2
                 | \    |      |
                 |  \5  |3     |1
                 |   \  |      |
                 |3   \-E3     E4
                 |            /
                 E5 ---------/
                          8
        """,
        "expected_next_hops": [
            # E0
            (0, 1, 1, 1, 1, 5),
            # E1
            (0, 1, 2, 3, 2, 0),
            # E2
            (1, 1, 2, 1, 4, 1),
            # E3
            (1, 1, 1, 3, 1, 1),
            # E4
            (2, 2, 2, 2, 4, 2),
            # E5
            (0, 0, 0, 0, 0, 5)
        ],
    },
    {
        "label": "line, then add link",
        "type": "add-link",
        "links": [
            [(1, 1)], # E0
            [(0, 1), (2, 1)], # E1
            [(1, 1)], # E2
        ],
        "link_adjustments": [
            (0, 2, 1), # 0->2, 1
            (2, 0, 1),
        ],
        "trigger_periodic_updates": False,
        "diagram": r"""

                    INITIALLY:              CHANGED TO:
                    ==========              ===========
                     1      1                1      1   
                 E0 --- E1 --- E2        E0 --- E1 --- E2
                                          \            /
                                           \----------/
                                                1
        """,
        "expected_next_hops": [
            # E0
            (0, 1, 2),
            # E1
            (0, 1, 2),
            # E2
            (0, 1, 2),
        ],
    },
    {
        "label": "network2, but add link to create",
        "type": "add-link",
        "links": [
            [(1, 1), (3, 5)], # E0
            [(0, 1), (2, 2), (3, 3)], # E1
            [(1, 2), (4, 1)],         # E2
            [(0, 5), (1, 3)],         # E3
            [(2, 1), (5, 8)],         # E4
            [(4, 8)],         # E5
        ],
        "link_adjustments": [
            (0, 5, 3),
            (5, 0, 3),
        ],
        "diagram": r"""

                     1      2
                 E0 --- E1 --- E2
                 * \    |      |
                 *  \5  |3     |1
                 *   \  |      |
                 *3   \-E3     E4
                 *            /
                 E5 ---------/
                          8

                Link marked with *s is added later
        """,
        "expected_next_hops": [
            # E0
            (0, 1, 1, 1, 1, 5),
            # E1
            (0, 1, 2, 3, 2, 0),
            # E2
            (1, 1, 2, 1, 4, 1),
            # E3
            (1, 1, 1, 3, 1, 1),
            # E4
            (2, 2, 2, 2, 4, 2),
            # E5
            (0, 0, 0, 0, 0, 5)
        ],
    },
    {
        "label": "triangle, then remove link, no periodic updates",
        "type": "remove-link",
        "links": [
            [(1, 1), (2, 1)], # E0
            [(0, 1), (2, 1)], # E1
            [(0, 1), (1, 1)], # E2
        ],
        "link_adjustments": [
            (0, 2, math.inf),
            (2, 0, math.inf),
        ],
        "trigger_periodic_updates": False,
        "diagram": r"""

                    INITIALLY:              CHANGED TO:
                    ==========              ===========
                     1      1                1      1   
                 E0 --- E1 --- E2        E0 --- E1 --- E2
                  \            /          
                   \----------/           
                        1                        

                without periodic updates, so E2 and E0 should not know how to reach other,
                lacking an additional update for E1. Since E1's routing table never changes,
                it does not have a reason to remind E0 or E2 about its route.
        """,
        "expected_next_hops": [
            # E0
            (0, 1, None),
            # E1
            (0, 1, 2),
            # E2
            (None, 1, 2),
        ],
    },
    {
        "label": "triangle, then remove link, then periodic updates",
        "type": "remove-link",
        "links": [
            [(1, 1), (2, 1)], # E0
            [(0, 1), (2, 1)], # E1
            [(0, 1), (1, 1)], # E2
        ],
        "link_adjustments": [
            (0, 2, math.inf),
            (2, 0, math.inf),
        ],
        "trigger_periodic_updates": True,
        "diagram": r"""

                    INITIALLY:              CHANGED TO:
                    ==========              ===========
                     1      1                1      1   
                 E0 --- E1 --- E2        E0 --- E1 --- E2
                  \            /          
                   \----------/           
                        1                        

                followed by periodic updates, so E0 and E2 will figure out
                the new (longer) route to each other
        """,
        "expected_next_hops": [
            # E0
            (0, 1, 1),
            # E1
            (0, 1, 2),
            # E2
            (1, 1, 2),
        ],
    },
    {
        "label": "network2 + remove link + periodic updates",
        "type": "remove-link",
        "links": [
            [(1, 1), (3, 5), (5, 3)], # E0
            [(0, 1), (2, 2), (3, 3)], # E1
            [(1, 2), (4, 1)],         # E2
            [(0, 5), (1, 3)],         # E3
            [(2, 1), (5, 8)],         # E4
            [(0, 3), (4, 8)],         # E5
        ],
        'link_adjustments': [
            (1, 3, math.inf),
            (3, 1, math.inf),
        ],
        'trigger_periodic_updates': True,
        "diagram": r"""

                     1      2
                 E0 --- E1 --- E2
                 | \    *      |
                 |  \5  *3     |1
                 |   \  *      |
                 |3   \-E3     E4
                 |            /
                 E5 ---------/
                          8

            Link from E1 to E3 (labeled with *s) is initially present, then
            removed.
        """,
        "expected_next_hops": [
            # E0
            (0, 1, 1, 3, 1, 5),
            # E1
            (0, 1, 2, 0, 2, 0),
            # E2
            (1, 1, 2, 1, 4, 1),
            # E3
            (0, 0, 0, 3, 0, 0),
            # E4
            (2, 2, 2, 2, 4, 2),
            # E5
            (0, 0, 0, 0, 0, 5)
        ],
    },
]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--verbose-tests', action='store_true',
        help='show test cases and expected/actual next hops arrays')
    parser.add_argument('--exclude-link-changes', action='store_true',
        help='exclude tests that change which links exist during the test')
    parser.add_argument('--debug', default=2, help='debug level for NetworkSimulator (default: 2; 0 = no messages; 3 = most messages)', type=int)
    parser.add_argument('--only-test', default=None, help='only run tests whose labels match a pattern')
    parser.add_argument('--keep-going', default=False, action='store_true', help='keep going after first failed test')
    parser.add_argument('--json', default=False, action='store_true', help='json format output and redirect normal output to stderr (for grading)')
    args = parser.parse_args()

    if args.json:
        sys.stdout.flush()
        old_stdout = os.dup(1)
        os.dup2(2, 1)
    failed = False
    results = []
    for test in TESTS:
        if args.only_test and not re.match(args.only_test, test['label']):
            continue
        if args.exclude_link_changes and test.get('link_adjustments'):
            continue
        if args.json:
            out_fh = io.StringIO()
        else:
            out_fh = sys.stdout
        current = run_test(out_fh=out_fh, debug=args.debug, verbose=args.verbose_tests, **test)
        if args.json:
            current['messages'] = out_fh.getvalue()
        results.append(current)
        if not current['passed']:
            failed = True
            if not args.keep_going:
                break
    if not args.json:
        if failed:
            print("*** Failed at least one test")
        else:
            print("*** All tests passed")
    if args.json:
        sys.stdout.flush()
        os.dup2(old_stdout, 1)
        json.dump(results, fp=sys.stdout)

if __name__ == '__main__':
    main()
