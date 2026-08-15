from .contract import BundleContract

CONTRACT = BundleContract(
    version=1,
    record_kinds=frozenset({"memory", "link", "profile"}),
    timestamp_mode="legacy-iso",
    allow_unknown_record_kinds=True,
    require_acl_clock=False,
)
