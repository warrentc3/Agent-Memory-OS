from .contract import BundleContract

CONTRACT = BundleContract(
    version=3,
    record_kinds=frozenset(
        {
            "memory",
            "link",
            "profile",
            "tombstone",
            "team",
            "project",
            "org_tombstone",
        }
    ),
    timestamp_mode="legacy-iso",
    allow_unknown_record_kinds=True,
    require_acl_clock=False,
)
