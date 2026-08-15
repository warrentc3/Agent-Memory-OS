from .contract import BundleContract

CONTRACT = BundleContract(
    version=4,
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
    timestamp_mode="stamp",
    allow_unknown_record_kinds=False,
    require_acl_clock=True,
)
