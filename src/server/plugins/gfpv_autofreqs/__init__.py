import copy
import json
import logging
from eventmanager import Evt

#
# @author Arnaud Morin <arnaud.morin@gmail.com>
#

class GFPVAutoFreqs():
    """This class handles update of RH nodes freqs"""
    version = "0.1.0"

    def __init__(self, rhapi):
        self.logger = logging.getLogger(__name__)
        self.rhapi = rhapi
        self.racecontext = rhapi._racecontext
        self.mapping = {
            'D': {
                'c': [1, 2, 6, 7, None, None, None, None],
                'f': [5660, 5695, 5878, 5914, 0, 0, 0, 0],
            },
            'O': {
                'c': [1, 2, 6, 7, None, None, None, None],
                'f': [5669, 5705, 5876, 5912, 0, 0, 0, 0],
            },
        }
        self.default_freqs = {
            'b': ['R', 'R', 'R', 'R', None, None, None, None],
            'c': [1, 2, 7, 8, None, None, None, None],
            'f': [5658, 5695, 5880, 5917, 0, 0, 0, 0]
        }

    def startup(self, args):
        """ Prepare all nodes to Raceband """
        self.set_all_frequencies(self.default_freqs)

    def switch(self, freqs, dest):
        """ Switch a freq from freqs from R to D or O """
        for i, freq in enumerate(freqs['b']):
            # Switch only from a R freq
            if freq == 'R':
                # Make sure we have a corresponding dest value
                # (O3 is not available)
                if self.mapping[dest]['c'][i] is None:
                    continue
                # Ok, let's switch
                freqs['b'][i] = dest
                freqs['c'][i] = self.mapping[dest]['c'][i]
                freqs['f'][i] = self.mapping[dest]['f'][i]
                return

    def callback(self, args):
        if 'heat_id' not in args:
            return

        payload = copy.deepcopy(self.default_freqs)

        for slot in self.rhapi.db.slots_by_heat(args['heat_id']):
            prefered_band = self.racecontext.rhdata.get_pilot_attribute_value(slot.pilot_id, 'prefered_band')
            if prefered_band == 'dji':
                self.switch(payload, 'D')
            elif prefered_band == 'djio3':
                self.switch(payload, 'O')

        # Update freqs on nodes
        self.set_all_frequencies(payload)

    def set_all_frequencies(self, freqs):
        ''' Set frequencies for all nodes '''
        # Set also in DB to be consistent
        profile = self.racecontext.race.profile
        profile_freqs = json.loads(profile.frequencies)

        self.logger.info("Sending frequency values to nodes: " + str(freqs["f"]))
        for idx in range(self.racecontext.race.num_nodes):
            profile_freqs["b"][idx] = freqs["b"][idx]
            profile_freqs["c"][idx] = freqs["c"][idx]
            profile_freqs["f"][idx] = freqs["f"][idx]
            self.racecontext.interface.set_frequency(idx, freqs["f"][idx])
            self.logger.info('Frequency set: Node {0} B:{1} Ch:{2} Freq:{3}'.format(idx+1, freqs["b"][idx], freqs["c"][idx], freqs["f"][idx]))

        profile = self.racecontext.rhdata.alter_profile({
            'profile_id': profile.id,
            'frequencies': profile_freqs
        })
        self.racecontext.race.profile = profile
        self.racecontext.rhui.emit_frequency_data()


def initialize(rhapi):
    ## Disable for now
    return
    ##
    gfpvautofreqs = GFPVAutoFreqs(rhapi)
    rhapi.events.on(Evt.STARTUP, gfpvautofreqs.startup)
    # NOTE(arnaud) we need to set a pretty lower priority to make sure the nodes freqs is set before the heat seed is done
    rhapi.events.on(Evt.HEAT_AUTOFREQUENCY_INIT, gfpvautofreqs.callback, priority=10)
    # We need to be trigger each time a current heat is set
    rhapi.events.on(Evt.HEAT_SET, gfpvautofreqs.callback, priority=10)
