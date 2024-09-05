from eventmanager import Evt
from .gfpvlink import GFPVLink

#
# @author Arnaud Morin <arnaud.morin@gmail.com>
#

def initialize(rhapi):
    gfpvlink = GFPVLink(rhapi)
    rhapi.events.on(Evt.STARTUP, gfpvlink.init_plugin)
    rhapi.events.on(Evt.LAPS_SAVE, gfpvlink.laps_save, priority=500)
    rhapi.events.on(Evt.LAPS_RESAVE, gfpvlink.laps_save, priority=500)
    rhapi.events.on(Evt.RACE_FINISH, gfpvlink.laps_save, priority=500)
    # We need to re-init ui when on class event to make sure the select options
    # are good
    rhapi.events.on(Evt.CLASS_ADD, gfpvlink.init_ui)
    rhapi.events.on(Evt.CLASS_DUPLICATE, gfpvlink.init_ui)
    rhapi.events.on(Evt.CLASS_ALTER, gfpvlink.init_ui)
    rhapi.events.on(Evt.CLASS_DELETE, gfpvlink.init_ui)
    # We want to be notified when heat are altered (plan)
    rhapi.events.on(Evt.HEAT_ALTER, gfpvlink.heat_alter, priority=500)
    rhapi.events.on(Evt.HEAT_ADD, gfpvlink.heat_alter, priority=500)
    rhapi.events.on(Evt.HEAT_DELETE, gfpvlink.heat_alter, priority=500)
    rhapi.events.on(Evt.CACHE_READY, gfpvlink.cache_ready, priority=500)
