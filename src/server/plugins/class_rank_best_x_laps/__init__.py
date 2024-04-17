''' Class ranking method: Best X laps (average) '''

import logging
import RHUtils
from eventmanager import Evt
from RHRace import StartBehavior
from Results import RaceClassRankMethod
from RHUI import UIField, UIFieldType, UIFieldSelectOption

logger = logging.getLogger(__name__)

def rank_best_laps(rhapi, race_class, args):
    if 'laps' not in args or not args['laps'] or int(args['laps']) < 1:
        return False, {}

    lap_limit = int(args['laps'])

    race_format = rhapi.db.raceformat_by_id(race_class.format_id)
    heats = rhapi.db.heats_by_class(race_class.id)
    time_format = rhapi.config.get_item('UI', 'timeFormat')

    combined_laps = {}
    for heat in heats:
        races = rhapi.db.races_by_heat(heat.id)

        for race in races:
            runs = rhapi.db.pilotruns_by_race(race.id)

            for run in runs:
                if run.pilot_id not in combined_laps:
                    combined_laps[run.pilot_id] = []
    
                start_lap = 2 if race_format and race_format.start_behavior == StartBehavior.STAGGERED else 1
    
                laps = rhapi.db.laps_by_pilotrun(run.id)
                # Remove all "deleted" laps, we don't need them
                laps = [x for x in laps if not x.deleted]
                for lap in laps[start_lap:]:
                    combined_laps[run.pilot_id].append(lap)

    leaderboard = []
    for pilot_id, laps in combined_laps.items():
        pilot = rhapi.db.pilot_by_id(pilot_id)
        if pilot:
            new_pilot_result = {}
            new_pilot_result['pilot_id'] = pilot.id
            new_pilot_result['callsign'] = pilot.callsign
            new_pilot_result['team_name'] = pilot.team

            laps = sorted(laps, key = lambda x: (
                x.lap_time
            ))
            laps = laps[:lap_limit]

            if len(laps):
                new_pilot_result['total_time_laps_raw'] = sum(l.lap_time for l in laps)
                new_pilot_result['avg_time_laps_raw'] = int(new_pilot_result['total_time_laps_raw'] / float(len(laps)))
                new_pilot_result['laps_base'] = len(laps)
                new_pilot_result['avg_time_laps'] = RHUtils.time_format(new_pilot_result['avg_time_laps_raw'], time_format)

                leaderboard.append(new_pilot_result)

    leaderboard = sorted(leaderboard, key = lambda x: (
        -x['laps_base'], x['avg_time_laps_raw'],
    ))

    # determine ranking
    last_rank = None
    last_rank_laps = 0
    last_rank_time = 0
    for i, row in enumerate(leaderboard, start=1):
        pos = i
        if last_rank_laps == row['laps_base'] and last_rank_time == row['avg_time_laps_raw']:
            pos = last_rank
        last_rank = pos
        last_rank_laps = row['laps_base']
        last_rank_time = row['avg_time_laps_raw']

        row['position'] = pos

    meta = {
        'method_label': F"Best {lap_limit} Laps",
        'rank_fields': [{
            'name': 'avg_time_laps',
            'label': F"{lap_limit}-Lap Average"
        }, {
            'name': 'laps_base',
            'label': "Base"
        }]
    }

    return leaderboard, meta

def register_handlers(args):
    args['register_fn'](
        RaceClassRankMethod(
            "Best X Laps (Average)",
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

