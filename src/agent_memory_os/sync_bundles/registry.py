from __future__ import annotations

from .contract import BundleContract
from .v001 import CONTRACT as V001
from .v002 import CONTRACT as V002
from .v003 import CONTRACT as V003
from .v004 import CONTRACT as V004

CONTRACTS: dict[int, BundleContract] = {
    contract.version: contract
    for contract in (V001, V002, V003, V004)
}
CURRENT_BUNDLE_VERSION = V004.version
SUPPORTED_BUNDLE_VERSIONS = frozenset(CONTRACTS)


def contract_for(version: object) -> BundleContract:
    if not isinstance(version, int) or isinstance(version, bool):
        raise ValueError("bundle version must be an integer")
    try:
        return CONTRACTS[version]
    except KeyError as exc:
        raise ValueError(f"unsupported bundle version: {version}") from exc
