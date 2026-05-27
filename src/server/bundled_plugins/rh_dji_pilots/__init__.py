"""Pilot Preferred Band Selector."""

import logging

from eventmanager import Evt
from RHUI import UIField, UIFieldSelectOption, UIFieldType

logger = logging.getLogger(__name__)


class PilotPreferredBandSelector:
    """Pilot Preferred Band Selector."""

    def __init__(self, rhapi: any) -> None:
        """Init."""
        self._rhapi = rhapi
        self.enabled = True

    def initialize(self, _args: any) -> None:
        """Init wrapper."""
        logger.info("Initializing Pilot Preferred Band Selector")
        options = [
            UIFieldSelectOption("raceband", "RACEBAND"),
            UIFieldSelectOption("dji", "DJI"),
            UIFieldSelectOption("djio3", "DJI O3"),
        ]
        self._rhapi.fields.register_pilot_attribute(
            UIField(
                "preferred_band",
                "Preferred Band",
                UIFieldType.SELECT,
                options=options,
                value="raceband",
            )
        )


def initialize(rhapi: any) -> None:
    """Init plugin."""
    s = PilotPreferredBandSelector(rhapi)
    rhapi.events.on(Evt.STARTUP, s.initialize)
