from hypothesis import given, settings
from hypothesis import strategies as st

from broker.ttc import chains, find_cycles, ttc
from sim.oracle import cycles_by_subsets, max_conflicts_solved


def test_hero_ring_needs_a_second_round():
    owner_of = {"ana-tue": "ana", "ben-thu": "ben", "dev-fri": "dev"}
    # round 1: Ana is unsure about Dev's Fri (her gym slot) and passes, so nothing closes
    r1 = {"ana": None, "ben": "ana-tue", "dev": "ben-thu"}
    assert find_cycles(r1, owner_of) == []
    # after asking Ana, her mascot counter-offers
    r2 = {"ana": "dev-fri", "ben": "ana-tue", "dev": "ben-thu"}
    assert find_cycles(r2, owner_of) == [["ana", "dev", "ben"]]


def test_two_cycle_is_a_plain_swap():
    owner_of = {"x": "a", "y": "b"}
    assert find_cycles({"a": "y", "b": "x"}, owner_of) == [["a", "b"]]


def test_chain_ends_with_someone_dropping():
    owner_of = {"ana-tue": "ana", "ben-thu": "ben", "dev-fri": "dev"}
    out = chains({"priya": ["ben-thu"]}, {"ben": ["ana-tue"], "ana": ["dev-fri"], "dev": []},
                 set(owner_of), owner_of)
    assert out == [["priya", "ben", "ana", "dev"]]


agents = st.lists(st.sampled_from(list("abcdefgh")), min_size=2, max_size=8, unique=True)


@st.composite
def pick_graph(draw):
    names = draw(agents)
    owner_of = {f"i_{a}": a for a in names}
    items = list(owner_of) + [None]
    points = {a: draw(st.sampled_from(items)) for a in names}
    return points, owner_of


@settings(max_examples=300, deadline=None)
@given(pick_graph())
def test_find_cycles_matches_brute_force(g):
    points, owner_of = g
    got = {frozenset(c) for c in find_cycles(points, owner_of)}
    assert got == cycles_by_subsets(points, owner_of)


@st.composite
def pref_profile(draw):
    names = draw(agents)
    owner_of = {f"i_{a}": a for a in names}
    prefs = {}
    for a in names:
        others = [i for i, o in owner_of.items() if o != a]
        prefs[a] = draw(st.lists(st.sampled_from(others), unique=True, max_size=len(others))) if others else []
    return prefs, owner_of


@settings(max_examples=300, deadline=None)
@given(pref_profile())
def test_ttc_invariants(p):
    prefs, owner_of = p
    cycles, _ = ttc(prefs, owner_of)
    members = [a for c in cycles for a in c]
    assert len(members) == len(set(members)), "an agent is in two cycles"
    item_of = {o: i for i, o in owner_of.items()}
    for c in cycles:
        for j, a in enumerate(c):
            gets = item_of[c[(j + 1) % len(c)]]
            assert gets in prefs[a], "everyone in a ring only gets a shift they picked"
    acceptable = {a: set(v) for a, v in prefs.items()}
    assert len(members) <= max_conflicts_solved(acceptable, owner_of, max_len=8)
