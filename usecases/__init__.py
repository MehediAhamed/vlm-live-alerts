import importlib, pkgutil
from .base import UseCase


def load():
    found = {}
    for m in pkgutil.iter_modules(__path__):
        if m.ispkg:
            uc = importlib.import_module(f"{__name__}.{m.name}").USECASE
            found[uc.name] = uc
    return dict(sorted(found.items()))
