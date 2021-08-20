'''
Arcane Fletches Arcane Archer abilities below are powered by Arcane Fletches Arcane Archers receive Arcane Fletches equal to 3 times the Arcane Archer's level including Legendary Levels, beginning at Arcane Archer level 4.

Example output of a '!playerinfo' command
Classes: Wizard: 1, Ranger: 9, Arcane Archer: 30, Legendary Levels [Arcane Archer]: 20, Total Levels: 60


This script tries to do the following:

* Add the character name to CHARACTERS_TO_WATCH to activate this script for. Preferable these should be Arcane Archers...

* On login a !playerinfo command is issued and the AA levels are calculated

* The max amount is displayed after resting

* If the script running in a newer HGX version (> 2.8.6.1)
	* an internal HGX variable is set to the max amount of arcane fletchings calculated by this script
	* no function is hooked to the line read event (because HGX handles it internal)

* Running on an old HGX version (like the 'Limbo Edition') the line read event is hooked up to and
  arcane fletchings are handled by this script

* There is just one command implemented, to rescan and set the AA levels:
  #setaf - issues a !playerinfo command and recalculate the max amount of arcane fletchings

TODO:
	* Autodetect AA
'''

import hgx

import System.Drawing

import Hgx.Modules
import NLog
import re

from Hgx.Core import AttackMode


try:
	from Hgx.Core import ArcaneFletchingsMaxAmount
except ImportError:
	ArcaneFletchingsMaxAmount = None

CHARACTERS_TO_WATCH = ["Your toon name here"]

logger = NLog.LogManager.GetLogger(__file__)

active = False
visible = False
arcane_fletchings = None
info_area = None

arcane_archer_levels = 0
arcane_archer_fletchings_left = 0


class ArcaneFletchingsInformation(Hgx.Modules.IInformation):
	__metaclass__ = hgx.clrtype.ClrClass

	PriorityAttribute = hgx.clrtype.attribute(
		Hgx.Modules.InformationPriorityAttribute)
	_clrnamespace = "Something.Funny"
	_clrclassattribs = [PriorityAttribute(5)]

	@property
	def IsVisible(self):
		return True

	@property
	def ContentUpdated(self):
		return False

	@property
	def AutoRemove(self):
		return False

	def Draw(self, g):
		rect = System.Drawing.Rectangle.Truncate(g.VisibleClipBounds)
		rectText = System.Drawing.Rectangle(rect.X, rect.Y, rect.Width * 2 / 3, rect.Height)
		rectValue = System.Drawing.Rectangle(rectText.Right, rect.Y, rect.Width - rectText.Width, rect.Height)

		string_format_text = System.Drawing.StringFormat(
			Trimming = System.Drawing.StringTrimming.EllipsisCharacter
		)

		string_format_value = System.Drawing.StringFormat(
			Alignment = System.Drawing.StringAlignment.Far,
		)

		g.DrawString(
			"Arcane Fletchings",
			System.Drawing.Font("Segoe UI", 10, System.Drawing.FontStyle.Regular),
			System.Drawing.Brushes.Gold,
			rectText, string_format_text)

		g.DrawString(
			str(arcane_archer_fletchings_left),
			System.Drawing.Font("Segoe UI", 10, System.Drawing.FontStyle.Regular),
			System.Drawing.Brushes.Gold,
			rectValue, string_format_value)

	def CompareTo(self, other):
		if other is ArcaneFletchingsInformation:
			return 0
		else:
			return -1


def on_playerchanged(sender, e):
	'''Check if the player character is one to display an arcane fletchings counter for'''
	global active

	if hgx.Encounters.PlayerCharacter in CHARACTERS_TO_WATCH:
		active = True
	else:
		info_area.Remove(arcane_fletchings)
		active = False


def on_lineread_check_aa_levels(sender, e):

	global arcane_archer_levels
	global arcane_archer_fletchings_left
	global ArcaneFletchingsMaxAmount

	if "Player Information:" in e.Line:
		arcane_archer_levels = 0
		arcane_archer_fletchings_left = 0
		# check if the player character is an AA
		result = arcane_archer_pattern.search(e.Line)
		if result:
			arcane_archer_levels = int(result.group(1))
			# Get the legendary levels of the AA
			result = legendary_arcane_archer_pattern.search(e.Line)
			if result:
				arcane_archer_levels += int(result.group(1))

		# logger.Info("Arcane archer levels:\t => {0}", arcane_archer_levels)
		if arcane_archer_levels >=4:
			arcane_archer_fletchings_left = 3*arcane_archer_levels

			# Running within a new HGX with Arcane Fletching support
			if ArcaneFletchingsMaxAmount:
				ArcaneFletchingsMaxAmount = 3*arcane_archer_levels

		# unhook this function to ease the load
		hgx.GameEvents.LogEntryRead -= on_lineread_check_aa_levels


def on_lineread(sender, e):

	global arcane_archer_fletchings_left
	global active

	if active:
		result = fletchings_pattern.search(e.Line)
		if result:
			arcane_archer_fletchings_left = int(result.group(1))
			info_area.Remove(arcane_fletchings)
			info_area.Add(arcane_fletchings)


def send_commands():

	hgx.Messages.Chat('/t "{0}" !playerinfo'.format(hgx.Encounters.PlayerCharacter))


def command_handler(sender, e):

	if e.Command.lower().startswith(("setaf", "sf")):
		hgx.GameEvents.LogEntryRead += on_lineread_check_aa_levels
		send_commands()


def on_resting(sender, e):

	if e.Finished:
		info_area.Add(arcane_fletchings)


if __name__ == "__main__":
	info_area = hgx.ServiceLocator.Current.GetInstance[Hgx.Modules.InformationOverlay]()
	arcane_fletchings = ArcaneFletchingsInformation()

	arcane_archer_pattern = re.compile(r"Arcane Archer: (\d+)")
	legendary_arcane_archer_pattern = re.compile(r"Legendary Levels \[Arcane Archer\]: (\d+)")
	fletchings_pattern = re.compile(r"^You have (\d+) Arcane Fletchings Remaining\.$")

	# Setup event handling
	hgx.UserEvents.ChatCommand += command_handler
	hgx.Encounters.PlayerChanged += on_playerchanged
	hgx.GameEvents.Resting += on_resting

	# If ArcaneFletchingsMaxAmount is not defined, this script runs in an old HGX environment without Arcane Fletchings support
	if not ArcaneFletchingsMaxAmount:
		logger.Info("Running within an old environment: ArcaneFletchingsMaxAmount not found!")
		hgx.GameEvents.LogEntryRead += on_lineread
