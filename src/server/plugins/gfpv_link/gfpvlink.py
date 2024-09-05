import json
import requests
import logging
from RHUI import UIField, UIFieldType, UIFieldSelectOption

#
# @author Arnaud Morin <arnaud.morin@gmail.com>
#

class GFPVLink():
    """This class handles communication with GFPV Link server and RH"""
    version = "0.1.0"
    endpoint = "https://link.gfpv.fr"
    enabled = False
    connected = False
    needupdate = False
    eventid = None
    bracketid = None

    def __init__(self, rhapi):
        self.logger = logging.getLogger(__name__)
        self._rhapi = rhapi
        self.dm = GFPVDataManager(self._rhapi)
        
    def startup(self, args):
        """Callback when plugin starts"""
        self.do_checks()

        if not self.enabled:
            self.logger.warning("GFPV Link is disabled. Please enable at Settings tab")
        elif not self.eventid:
            self.logger.warning("GFPV Link event ID is missing. Please register at https://link.gfpv.fr/register")
        elif not self.bracketid:
            self.logger.warning("GFPV Link bracket is not set. Please set in Settings tab")
        elif not self.connected:
            self.logger.warning("GFPV Link cannot connect to internet. Check connection and try again.")
        elif self.needupdate:
            self.logger.warning("GFPV Link requires a mandatory update. Please update and restart the timer. No results will be synced for now.")
        
        # Init UI
        self.init_ui(args)

        # Resync
        if self.enabled and self.connected and self.eventid and not self.needupdate:
            self.logger.info("GFPV Link is ready")
        
    def init_ui(self, args):
        """Build UI in settings tab"""
        # Get all classes, we need that to select the correct class for bracket
        classes = self.dm.get_all_classes()

        ui = self._rhapi.ui
        # Add our panel under settings
        ui.register_panel("gfpv-link", "GFPV Link", "settings")

        # Add some options
        enabled = UIField(
            name='gfpv-link-enabled',
            label='Enable GFPV Link Plugin',
            field_type=UIFieldType.CHECKBOX,
            desc="Enable or disable this plugin. Unchecking this box will stop all communication with the GFPV Link server.",
        )
        eventid = UIField(
            name='gfpv-link-eventid',
            label='Event ID',
            field_type=UIFieldType.TEXT,
            desc="Event must be registered at link.gfpv.fr/register",
        )

        options = []
        for c in classes:
            options.append(UIFieldSelectOption(c,classes[c]))
        bracketid = UIField(
            name='gfpv-link-bracketid',
            label='Bracket',
            field_type=UIFieldType.SELECT,
            options=options,
            desc="Bracket used to view race results",
        )

        fields = self._rhapi.fields
        fields.register_option(enabled, "gfpv-link")
        fields.register_option(eventid, "gfpv-link")
        fields.register_option(bracketid, "gfpv-link")

    def do_checks(self):
        # Check if plugin is enabled
        self.enabled = self.is_enabled()
        self.eventid = self.get_eventid()
        self.bracketid = self.get_bracketid()
        # Check if we can reach internet
        # This will also check if version is OK
        if self.enabled:
            self.connected, self.needupdate = self.is_connected()

    def all_good(self):
        if self.enabled and self.connected and self.eventid and self.bracketid and not self.needupdate:
            return True
        return False

    def heat_alter(self, args):
        """Callback when a heat frequency selection is done"""
        self.do_checks()

        if self.all_good():
            if 'heat_id' in args:
                # Collect info from DB
                heat = self.dm.get_heat(args['heat_id'])

                # Check if we are monitoring this class
                if self.bracketid != heat.class_id:
                    return

                # We work only when heat are CONFIRMED
                if heat.status != 2:
                    return

                self.logger.info("GFPV Link syncing from HEAT_ALTER event...")

                # Build data to be sent
                if heat.name:
                    name = heat.name
                else:
                    name = heat.auto_name
                pilots = self.dm.get_heat_pilots(heat)

                data = {
                    "action": "alter",
                    "heat": {
                        "id": heat.id,
                        "name": name,
                        "pilots": pilots
                    },
                }

                # Send data
                if self.send_data(data):
                    self.logger.info("GFPV Link sync OK")
                else:
                    self.logger.warning("GFPV Link sync failed")

    def heat_set(self, args):
        """Callback when a heat is selected to be run"""
        self.do_checks()

        if self.all_good():
            if 'heat_id' in args:
                # Collect info from DB
                heat = self.dm.get_heat(args['heat_id'])

                # Check if we are monitoring this class
                if self.bracketid != heat.class_id:
                    return

                # We work only when heat are CONFIRMED
                if heat.status != 2:
                    return

                self.logger.info("GFPV Link syncing from HEAT_SET event...")

                # Build data to be sent
                if heat.name:
                    name = heat.name
                else:
                    name = heat.auto_name
                pilots = self.dm.get_heat_pilots(heat)

                data = {
                    "action": "alter",
                    "heat": {
                        "id": heat.id,
                        "name": name,
                        "pilots": pilots
                    },
                }

                # Send data
                if self.send_data(data):
                    self.logger.info("GFPV Link sync OK")
                else:
                    self.logger.warning("GFPV Link sync failed")

    def heat_delete(self, args):
        """Callback when a heat is deleted"""
        self.do_checks()

        if self.all_good():
            if 'heat_id' in args:

                self.logger.info("GFPV Link syncing from HEAT_DELETE event...")

                data = {
                    "action": "delete",
                    "heat": {
                        "id": args['heat_id'],
                    },
                }

                # Send data
                if self.send_data(data):
                    self.logger.info("GFPV Link sync OK")
                else:
                    self.logger.warning("GFPV Link sync failed")

    def cache_ready(self, args):
        """Callback when cache is ready"""
        # Cache is a heavy data dict that contains classes results
        self.do_checks()

        if self.all_good():
            # Get our class result
            results = self.dm.get_cache()

            # Stop here if the class is not having any results
            if self.bracketid not in results['heats_by_class']:
                return

            # Loop over heats
            for heat in results['heats'].values():
                # Discard heats that are not from our event
                if heat['heat_id'] not in results['heats_by_class'][self.bracketid]:
                    continue

                for rnd in heat['rounds']:
                    # Store position for each pilots
                    positions = {}
                    if "leaderboard" in rnd and "meta" in rnd["leaderboard"] and "primary_leaderboard" in rnd["leaderboard"]["meta"]:
                            primary_leaderboard	= rnd["leaderboard"]["meta"]["primary_leaderboard"]
                    if "leaderboard" in rnd and primary_leaderboard in rnd["leaderboard"]:
                        for pilot in rnd["leaderboard"][primary_leaderboard]:
                            if "callsign" in pilot and pilot["callsign"]:
                                positions[pilot["callsign"]] = pilot["position"]

                    # Now loop over nodes to send rounds for each pilot
                    for node in rnd['nodes']:
                        if not node['callsign']:
                            continue
                        all_laps = []
                        if 'laps' in node:
                            for lap in node['laps']:
                                if not lap['deleted']:
                                    all_laps.append(lap['lap_time_formatted'])
                        # Always discard the first lap, which is when the timer trigger
                        if len(all_laps) > 1:
                            laps = all_laps[1:]
                        else:
                            laps = []

                        # Send data
                        data = {
                            "round": {
                                "id": rnd['id'],
                                "heat_id": heat['heat_id'],
                                "pilot": node['callsign'],
                                "laps": laps,
                                "position": positions[node['callsign']] if node['callsign'] in positions else 0,
                            }
                        }
                        if self.send_data(data):
                            self.logger.info(f"GFPV Link round sent OK ({node['callsign']})")
                        else:
                            self.logger.warning(f"GFPV Link round sent FAILED ({node['callsign']})")

            class_results = results['classes'][self.bracketid]
            pilots = []

            # For now, what we looking for is the ranking computed by the 3-best-laps plugin, if available
            if class_results['ranking'] and class_results['ranking']['meta']['method_label'] == 'Best 3 Laps':
                for pilot in class_results['ranking']['ranking']:
                    if pilot['callsign']:
                        pilots.append([pilot['callsign'], pilot['avg_time_laps']])
            elif class_results['ranking'] and class_results['ranking']['meta']['method_label'] == 'Best 3 Laps (Consecutives)':
                for pilot in class_results['ranking']['ranking']:
                    if pilot['callsign']:
                        pilots.append([pilot['callsign'], pilot['time']])
            elif class_results['ranking'] and class_results['ranking']['meta']['method_label'] == 'FAI':
                for pilot in class_results['ranking']['ranking']:
                    if pilot['callsign']:
                        pilots.append([pilot['callsign'], pilot['position']])
            #else:
            #    # If 3-best-laps not available, use by_consecutives, which is the other FAI official way of computing
            #    for pilot in class_results['leaderboard']['by_consecutives']:
            #        pilots.append([pilot['callsign'], pilot['consecutives']])

            data = {"ranks": pilots}

            # Send data
            if self.send_data(data):
                self.logger.info("GFPV Link ranks sync OK")
            else:
                self.logger.warning("GFPV Link ranks sync failed")


    def send_data(self, data):
        """Send data to GFPV Link"""
        # Add some extra
        data["eventid"] = self.eventid
        x = requests.post(self.endpoint+"/push", json = data)
        if x.status_code == requests.codes.ok:
            return True
        else:
            return False

    def is_connected(self):
        needupdate = False
        try:
            x = requests.get(self.endpoint+'/healthcheck', timeout=15).json()
            if self.version != x["version"]:
                needupdate = True
            return True, needupdate
        except requests.ConnectionError:
            return False, needupdate
    
    def is_enabled(self):
        enabled = self._rhapi.db.option("gfpv-link-enabled")

        if enabled == "1":
            return True
        else:
            return False

    def get_eventid(self):
        return self._rhapi.db.option("gfpv-link-eventid")

    def get_bracketid(self):
        try:
            b = int(self._rhapi.db.option("gfpv-link-bracketid"))
        except Exception:
            b = None
        return b



class GFPVDataManager():
    """This class is used by GFPVLink to talk to RH DB"""
    def __init__(self,rhapi):
        self.logger = logging.getLogger(__name__)
        self._rhapi = rhapi

    def get_all_classes(self):
        """Get all classes"""
        results = {}
        raceclasses = self._rhapi.db.raceclasses
        for c in raceclasses:
            if not c.name:
                name = f"Class {c.id}"
            else:
                name = c.name
            results[c.id] = name

        return results

    def get_heat(self, heat_id):
        """Get a heat from ID"""
        heat = self._rhapi.db.heat_by_id(heat_id)
        return heat

    def get_heat_pilots(self, heat):
        """Get pilots from a heat"""
        pilots = []
        # Grab frequencies
        frequencies = self.get_frequencies()
        # Grab heat pilots
        for slot in self._rhapi.db.slots_by_heat(heat.id):
            # Grab pilot callsign, we only need that
            pilot = self._rhapi.db.pilot_by_id(slot.pilot_id)
            if pilot:
                freq = ""
                # Real frequencies are set only on CONFIRMED|2 or PROJECTED|1
                if heat.status != 0:
                    freq = frequencies[slot.node_index]
                pilots.append([pilot.callsign, freq])
        return pilots

    def get_frequencies(self):
        """Get list of frequencies registered in for all nodes"""
        nodes = []
        f = json.loads(self._rhapi.race.frequencyset.frequencies)
        for i, b in enumerate(f['b']):
            nodes.append(f'{b}{f["c"][i]}')
        return nodes

    def get_cache(self):
        results = self._rhapi.eventresults.results
        return results
