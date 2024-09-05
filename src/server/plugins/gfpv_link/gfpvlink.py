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
        
    def init_plugin(self, args):
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
            self.resync(args)
            self.logger.info("GFPV Link is ready")
        
    def init_ui(self, args):
        """Build UI in settings tab"""
        # Get all classes, we need that to select the correct class for bracket
        classes = self.dm.get_all_classes()

        ui = self._rhapi.ui
        # Add our panel under settings
        ui.register_panel("gfpv-link", "GFPV Link", "settings")

        # Add a button to resync
        ui.register_quickbutton("gfpv-link", "send-all-button", "Resync", self.resync)

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

    def resync(self, args):
        self.logger.info("GFPV Link syncing...")
        self.do_checks()
        data = {}

        if self.all_good():
            ui = self._rhapi.ui
            ui.message_notify("GFPV Link sync in progress...")

            data["heats"] = self.dm.get_heats_from_class(self.bracketid)
            data |= self.dm.get_races_from_class(self.bracketid)

            # Send data
            if self.send_data(data):
                self.logger.info("GFPV Link sync OK")
                ui.message_notify("GFPV Link sync done.")
            else:
                self.logger.warning("GFPV Link sync failed")
                ui.message_notify("GFPV Link sync failed!")

    def laps_save(self, args):
        """Callback when a race data is stored"""
        # Check args
        if not "race_id" in args:
            return

        self.do_checks()

        if self.all_good():
            # Get race data
            race = self.dm.get_race(args["race_id"])

            # Check if we are monitoring this class
            if self.bracketid != race.class_id:
                return

            self.logger.info("GFPV Link syncing from LAPS_SAVE event...")

            # Get all races and laps from this heat
            # We need to do that because maybe we are marshalling a race which is not the latest one for this round.
            data = self.dm.get_races_from_heat(race.heat_id)

            # Send data
            if self.send_data(data):
                self.logger.info("GFPV Link sync OK")
            else:
                self.logger.warning("GFPV Link sync failed")

    def heat_alter(self, args):
        """Callback when a heat is altered"""
        self.do_checks()

        if self.all_good():
            if args["_eventName"] != "heatDelete":
                # Avoid working if not needed
                # Collect info from DB
                heat = self.dm.get_heat(args['heat_id'])

                # Check if we are monitoring this class
                if self.bracketid != heat.class_id:
                    return

            self.logger.info("GFPV Link syncing from HEAT_(ALTER|ADD|DELETE) event...")

            # Build data to be sent
            data = {"heats": self.dm.get_heats_from_class(self.bracketid)}

            # Send data
            if self.send_data(data):
                self.logger.info("GFPV Link sync OK")
            else:
                self.logger.warning("GFPV Link sync failed")

    def cache_ready(self, args):
        """Callback when cache is ready"""
        # Cache is a heavy data dict that contains classes results
        # For now, we are using the cache for qualifications overall results
        # Races and chronos are handled from other callbacks

        self.do_checks()

        if self.all_good():
            # Work only on qualification kind of class
            if self.dm.get_class_type(self.bracketid) != 'qualifier':
                return

            # Get our class result
            results = self.dm.get_cache()
            class_results = results['classes'][self.bracketid]
            pilots = []

            # For now, what we looking for is the ranking computed by the 3-best-laps plugin, if available
            if class_results['ranking'] and class_results['ranking']['meta']['method_label'] == 'Best 3 Laps':
                for pilot in class_results['ranking']['ranking']:
                    pilots.append([pilot['callsign'], pilot['avg_time_laps']])
            else:
                # If 3-best-laps not available, use by_consecutives, which is the other FAI official way of computing
                for pilot in class_results['leaderboard']['by_consecutives']:
                    pilots.append([pilot['callsign'], pilot['consecutives']])

            data = {"ranks": pilots}

            # Send data
            if self.send_data(data):
                self.logger.info("GFPV Link sync OK")
            else:
                self.logger.warning("GFPV Link sync failed")


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

    def get_class_type(self, bracketid):
        classes = self.get_all_classes()
        # Yes, this is hacky, but every developer has its own dark side
        if 'qualif' in classes[bracketid].lower():
            return 'qualifier'
        else:
            return 'bracket'

    def get_class_format(self, bracketid):
        cls = self._rhapi.db.raceclass_by_id(bracketid)
        return self._rhapi.db.raceformat_by_id(cls.format_id)

    def get_race(self, race_id):
        """Get a race from ID"""
        return self._rhapi.db.race_by_id(race_id)

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

    def get_pilot_by_id(self, pilot_id):
        return self._rhapi.db.pilot_by_id(pilot_id)

    def get_frequencies(self):
        """Get list of frequencies registered in for all nodes"""
        nodes = []
        f = json.loads(self._rhapi.race.frequencyset.frequencies)
        for i, b in enumerate(f['b']):
            nodes.append(f'{b}{f["c"][i]}')
        return nodes

    def get_races_from_class(self, class_id):
        """Get all races for a class"""
        races = self._rhapi.db.races_by_raceclass(class_id)
        return self.build_races_result(races)

    def get_heats_from_class(self, class_id):
        """Get all heats for a class"""
        heats = self._rhapi.db.heats_by_class(class_id)
        results = {}
        for heat in heats:
            pilots = self.get_heat_pilots(heat)
            if heat.name:
                name = heat.name
            else:
                name = heat.auto_name
            results[name] = pilots
        return results

    def get_races_from_heat(self, heat_id):
        """Get all races for a heat"""
        races = self._rhapi.db.races_by_heat(heat_id)
        return self.build_races_result(races)

    def build_races_result(self, races):
        """Build a race result from races list"""
        # Races are sorted from DB, but better safe than sorry, let's sort them again now
        sorted_races = [race for race in sorted(races, key=lambda r: r.id)]

        # Maybe we do not have races yet
        if not sorted_races:
            return {}

        # Get class info from first race
        # type is qualifier or bracket
        class_type = self.get_class_type(sorted_races[0].class_id)
        # format is used later for StartBehavior (HOLESHOT etc.)
        class_format = self.get_class_format(sorted_races[0].class_id)

        # We will store races results in that
        results = {'races': {}, 'laps': {}}

        # Depending if we are in a qualifier or bracket, we will loop differently
        if class_type == 'qualifier':
            # Qualifier type
            # We will store all laps per pilot in this dict
            combined_laps = {}
            # Ok, let's loop over our recorded races we need all laps
            for race in sorted_races:
                # For qualifier, we want race laps
                # RHapi is complex about this, we must grab the pilotrun first
                runs = self._rhapi.db.pilotruns_by_race(race.id)
                for run in runs:
                    if run.pilot_id not in combined_laps:
                        combined_laps[run.pilot_id] = []

                    # start_behavior == 2 is STAGGERED
                    # For HOLESHOT and first lap, we discard only the first lap
                    start_lap = 2 if class_format and class_format.start_behavior == 2 else 1

                    laps = self._rhapi.db.laps_by_pilotrun(run.id)
                    # Remove all "deleted" laps, we don't need them
                    laps = [x for x in laps if not x.deleted]
                    for lap in laps[start_lap:]:
                        combined_laps[run.pilot_id].append(f"Round {race.round_id}: {lap.lap_time_formatted}")

            # Lets build our results now that we have all laps by pilot
            for pilot_id, laps in combined_laps.items():
                # Grab pilot from id (because we will need callsign)
                pilot = self.get_pilot_by_id(pilot_id)
                if not pilot:
                    continue
                results['laps'][pilot.callsign] = laps
        else:
            # Bracket type
            # Ok, let's loop over our recorded races
            for race in sorted_races:
                raceresults = []

                # Get heat (for name)
                heat = self._rhapi.db.heat_by_id(race.heat_id)

                # Grab the race result
                r = self._rhapi.db.race_results(race.id)
                if r != None:
                    # For bracket, what is important for us is position more than laps
                    # Take only the results that are used to make progress
                    filteredresults = r[r["meta"]["primary_leaderboard"]]

                    for result in filteredresults:
                        allresults = result['position']
                        # For final, also keep position from previous races
                        if heat.name == "Final":
                            if heat.name in results['races']:
                                for r in results['races'][heat.name]:
                                    if r[0] == result["callsign"]:
                                        # We build the position using previous position and the new one separated by a |
                                        allresults = f"{r[1]}|{result['position']}"
                        # We keep only pilot and position
                        raceresults.append([result["callsign"], allresults])
                # Add this result, this may override a previous race that was done
                # for the same heat ID, but that's fine, we are looping over race in
                # ordered way so we should have the latest one always
                results['races'][heat.name] = raceresults
        # Clean empty lists
        results = {k: v for k, v in results.items() if v not in (None, '', [], {})}
        return results

    def get_cache(self):
        results = self._rhapi.eventresults.results
        return results
