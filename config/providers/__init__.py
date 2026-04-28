"""Provider modules used by the site config loader."""

from . import beeline, domru, megafon, mts, rostelecom, t2, ttk

PROVIDER_MODULES = {
    beeline.PROVIDER: beeline,
    domru.PROVIDER: domru,
    megafon.PROVIDER: megafon,
    mts.PROVIDER: mts,
    rostelecom.PROVIDER: rostelecom,
    t2.PROVIDER: t2,
    ttk.PROVIDER: ttk,
}

