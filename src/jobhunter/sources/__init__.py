"""Job sources package. Importing this package registers all built-in sources."""

from jobhunter.sources.arbeitnow import ArbeitnowSource
from jobhunter.sources.fourdayweek import FourDayWeekSource
from jobhunter.sources.remoteok import RemoteOKSource
from jobhunter.sources.wwr import WeWorkRemotelySource

__all__ = [
    "ArbeitnowSource",
    "FourDayWeekSource",
    "RemoteOKSource",
    "WeWorkRemotelySource",
]
