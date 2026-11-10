import pytest

from fabops.authz.policy import can_see, scope_of_user, visible
from fabops.authz.scope import SYSTEM_SCOPE, Scope

ENG_FX1_ETCH = Scope.of(["FX1"], ["etch"], 1)


def doc(fab="FX1", department="etch", clearance=1):
    return {"fab": fab, "department": department, "clearance": clearance}


@pytest.mark.parametrize(
    ("resource", "expected"),
    [
        (doc(), True),
        (doc(clearance=0), True),
        (doc(clearance=2), False),  # clearance too low
        (doc(fab="FX2"), False),  # same clearance, other fab
        (doc(department="litho"), False),  # same clearance and fab, other department
        (doc(department="shared"), True),  # shared is visible to every department
        (doc(fab="FX2", department="shared"), False),  # shared does not cross fabs
        (doc(department="shared", clearance=2), False),  # nor clearance
    ],
)
def test_visibility_rule(resource, expected):
    assert visible(ENG_FX1_ETCH, resource) is expected


def test_system_scope_sees_nothing():
    assert not can_see(SYSTEM_SCOPE, fab="FX1", department="etch", clearance=0)


def test_scope_of_user_matches_cache_scope():
    user = {"fabs": ["FX1"], "departments": ["etch"], "clearance": 1}
    assert scope_of_user(user) == ENG_FX1_ETCH
    assert scope_of_user(user).key() == ENG_FX1_ETCH.key()
