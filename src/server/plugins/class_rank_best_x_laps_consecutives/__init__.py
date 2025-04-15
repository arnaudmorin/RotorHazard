''' Class ranking method: Best X laps (consecutives) '''

import logging
from eventmanager import Evt
from RHRace import StartBehavior
from Results import RaceClassRankMethod
from RHUI import UIField, UIFieldType

#
# @author Arnaud Morin <arnaud.morin@gmail.com>
#

logger = logging.getLogger(__name__)

def rank_best_laps(rhapi, race_class, args):
    """ Rank based on consecutive laps """
    if 'laps' not in args or not args['laps'] or int(args['laps']) < 1:
        return False, {}

    lap_limit = int(args['laps'])

    meta = {
        'method_label': F"Best {lap_limit} Laps (Consecutives)",
        'rank_fields': [
            {
                'name': 'time',
                'label': F"Best {lap_limit} Laps (Consecutives)"
            }, 
            {
                'name': 'laps',
                'label': "Base"
            },
        ]
    }

    # Collect pilot data
    pilot_consecutives = {}

    race_format = rhapi.db.raceformat_by_id(race_class.format_id)

    # Loop over all heats of this class
    heats = rhapi.db.heats_by_class(race_class.id)
    for heat in heats:
        # Loop over races for this heat
        races = rhapi.db.races_by_heat(heat.id)
        for race in races:
            # Loop over runs
            runs = rhapi.db.pilotruns_by_race(race.id)
            for run in runs:
                # Keep track of this pilot
                if run.pilot_id not in pilot_consecutives:
                    pilot_consecutives[run.pilot_id] = []

                start_lap = 2 if race_format and race_format.start_behavior == StartBehavior.STAGGERED else 1
                laps = rhapi.db.laps_by_pilotrun(run.id)

                # Remove all "deleted" laps, we don't need them
                laps = [x for x in laps if not x.deleted]

                # Remove start laps
                laps = laps[start_lap:]
                
                # Check if we have enough laps
                for limit in range(1, lap_limit + 1):
                    if len(laps) >= limit:
                        # Loop over the laps windows
                        for i in range(len(laps) - (limit - 1)):
                            # Store the sum of laps for this window
                            pilot_consecutives[run.pilot_id].append({
                                'laps': limit,
                                'time': sum([data.lap_time for data in laps[i : i + limit]])
                            })

    # Now build leaderboard from collected data
    leaderboard = []
    for pilot_id, laps in pilot_consecutives.items():
        pilot = rhapi.db.pilot_by_id(pilot_id)
        if pilot:
            new_pilot_result = {}
            new_pilot_result['pilot_id'] = pilot.id
            new_pilot_result['callsign'] = pilot.callsign
            laps = sorted(laps, key = lambda x: (
                -x['laps'],
                x['time']
            ))
            if len(laps):
                new_pilot_result['laps'] = laps[0]['laps']
                new_pilot_result['time'] = rhapi.utils.format_time_to_str(laps[0]['time'])
                leaderboard.append(new_pilot_result)

    # Sort the leaderboard
    leaderboard = sorted(leaderboard, key = lambda x: (-x['laps'], x['time']))

    # determine ranking
    for i, row in enumerate(leaderboard, start=1):
        row['position'] = i

    return leaderboard, meta

def register_handlers(args):
    args['register_fn'](
        RaceClassRankMethod(
            "Best X Laps (Consecutives)",
            rank_best_laps,
            {
                'laps': 3
            },
            [
                UIField('laps', "Number of laps", UIFieldType.BASIC_INT, placeholder="3"),
            ]
        )
    )

def initialize(rhapi):
    rhapi.events.on(Evt.CLASS_RANK_INITIALIZE, register_handlers)

