from eventmanager import Evt
from .gfpvlink import GFPVLink

#
# @author Arnaud Morin <arnaud.morin@gmail.com>
#

def initialize(rhapi):
    gfpvlink = GFPVLink(rhapi)

    # Startup init
    rhapi.events.on(Evt.STARTUP, gfpvlink.startup)

    # We need to re-init ui when on class event to make sure the select options are good
    rhapi.events.on(Evt.CLASS_ADD, gfpvlink.init_ui)
    rhapi.events.on(Evt.CLASS_DUPLICATE, gfpvlink.init_ui)
    rhapi.events.on(Evt.CLASS_ALTER, gfpvlink.init_ui)
    rhapi.events.on(Evt.CLASS_DELETE, gfpvlink.init_ui)

    # We want to be notified when heat frequencies are defined
    # This will happen on HEAT_ALTER
    rhapi.events.on(Evt.HEAT_ALTER, gfpvlink.heat_alter)

    # We want to be notified when a heat is selected to be run
    rhapi.events.on(Evt.HEAT_SET, gfpvlink.heat_set)

    # We want to be notified when a heat is deleted
    rhapi.events.on(Evt.HEAT_DELETE, gfpvlink.heat_delete)

    # Send results given by RH
    rhapi.events.on(Evt.CACHE_READY, gfpvlink.cache_ready, priority=500)
