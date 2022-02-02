__version__ = "$Rev: 5 $"
module_version = "0.050"
module_name = "trackEquippedItems"

# track the equipped items of the player character, update on player change

# TODO:
# Nothing yet

import hgx
#import Hgx.Modules
#import Hgx.Core
import NLog
import re

#import clr
#clr.AddReference("Hgx.Modules")

from System.Collections.Generic import List, SortedList, Dictionary, SortedDictionary

try:
	from versionInfo import add_module_info
	versionInfo_loaded = True
except ImportError:
	versionInfo_loaded = False 

# get a logger for the script
logger = NLog.LogManager.GetLogger(__file__)

name_of_dictionary = "playerEquippedItems"


def on_lineread(sender, e):

#Your equipment:
#    Head: Visor of Vigilance
#    Chest: Chorus of the Damned
#    Boots: Styxwalkers
#    Arms: Six-Fingered Gloves
#    Right Hand: Harp of the Axerian Grandmaster
#    Left Hand: Bastion of Cormyr
#    Cloak: Resin Soaked Cloak
#    Left Ring: Quaternary Exotica
#    Right Ring: Lliira's Stimulating Scream
#    Neck: Ygrette's Evanescent Locket of the Vigilant Dove
#    Belt: Mystical Inspiration of the Stake
#    Bullets: Mote of Practiced Perception

	if "Your equipment:" in e.Line:
		try:
			for single_line in e.Line.split("\n"):
#				logger.Info ("Tracking line: *{0}*", single_line)
				if len (single_line) > 0:
					result = body_part_item_pattern.search(single_line)
					if result:
						body_part, item = result.groups()
#						logger.Info ("Found: {0}, {1} on: *{2}*", body_part, item, hgx.Encounters.PlayerCharacter)
						hgx.Statistics.CustomData[name_of_dictionary][hgx.Encounters.PlayerCharacter][body_part] = item
						continue
		except KeyError:
			logger.Error ("trackEquippedItems: UNEXPECTED Key Error")
		logger.Info ("Player *{0}* added with {1} items eqipped", hgx.Encounters.PlayerCharacter, hgx.Statistics.CustomData[name_of_dictionary][hgx.Encounters.PlayerCharacter].Count)
		hgx.GameEvents.LogEntryRead -= on_lineread

def on_mapchange(sender, e):

	pass


def on_killed(sender, e):

	pass


def on_resting(sender, e):

	pass


def on_playerchanged(sender, e):


	player = hgx.Encounters.PlayerCharacter
	#ignore test characters
	if "[test]" not in player.lower():
		if not hgx.Statistics.CustomData[name_of_dictionary].ContainsKey (player):
			hgx.Statistics.CustomData[name_of_dictionary][player] = Dictionary[str, str]()
		hgx.GameEvents.LogEntryRead += on_lineread
		hgx.Messages.Chat("!list equipped")


def on_spellcasting(sender, e):

	pass


def command_handler (sender, e):

	pass


def on_killed(sender, e):

	pass


def on_damaged(sender, e):

	pass


if __name__ == "__main__":

	body_part_item_pattern = re.compile (r"(.*): (.*)")

	if name_of_dictionary not in hgx.Statistics.CustomData:
		hgx.Statistics.CustomData[name_of_dictionary] = Dictionary[str, Dictionary[str, str]]()

	hgx.Encounters.PlayerChanged += on_playerchanged

#	hgx.Party.PlayerChanged += on_playerchanged
#	hgx.GameEvents.AreaChanged += on_mapchange
#	hgx.UserEvents.ChatCommand += command_handler
#	hgx.GameEvents.Killed += on_killed
#	hgx.GameEvents.Damaged += on_damaged

	if versionInfo_loaded:
		add_module_info (module_name, module_version, __version__)
