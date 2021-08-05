__version__ = "$Rev: 3 $"
module_version = "0.070"
module_name = "SkillCheck"

# Description
# Tries to show the real roll for a disable trap or open lock check for an unsuccesful attempt

# Quick explanation:
# Using 8bit signed integers
#      binary 01111111 = 127
# increment by 1 gives
#      binary 10000000 = -1
# That's all....

# Using a lockpick and your open lock skill goes over 127 and is displayed as a negative skill in the skill check output
#
# Chest DC are shown without a leading sign, they seem to be a (small) positive,  but if your check fails against that small number
# and is not supposed to, it's very likely the DC is > 127
#
# Disable trap checks only can bug at the trap DC, the skill can't exceed 127 at all


# Example:
# Salek's Last Rogue : Open Lock : *success not possible* : (20 - 108 = -88 vs. DC: 43)
# is in fact:
# Salek's Last Rogue : Open Lock : *success not possible* : (20 + 147 = 167 vs. DC: 171)
#
# So either I was missing point(s) in open lock skill OR was using a lockpick 4 points to low

# TODO:
# 	Nothing yet

import hgx
import Hgx.Modules
import Hgx.Core
import NLog
import re

import locale
locale.setlocale(locale.LC_ALL, '') # default setting

try:
	from versionInfo import add_module_info
except ImportError:
	add_module_info = None

#---------------------------------
# User changes here
debug = True
color_success = "Lime"
color_failure = "Magenta"
#---------------------------------

qualify = None
skills = []
skills_for_class = None

# Using the bugged DC values here
known_lockpicks = {
	43: 24,
	40: 21,
	37: 18,
	34: 15,
}

logger = NLog.LogManager.GetLogger(__file__)

def real_skill (base):

	return 255-base


def real_DC (DC):

	return 128+DC


def lockpick (DC):

	# 147 is Take 20 + maxed rogue skill of 127
	return 128+DC-147


def on_lineread(sender, e):

	if " : Open Lock : " in e.Line:
		result = check_pattern.search(e.Line)
		if result:
			success, roll, bugged, skill, calculated, DC = result.groups()
			if success != "Success":
				roll = int(roll)
				skill = int(skill)
				DC = int(DC)
				if bugged == "-":
					missing = real_DC(DC)-(roll+real_skill(skill))
					if missing > 0:
						missed_by_string = "<color={0}>Missing {1}</color>".format(color_failure, real_DC(DC)-(roll+real_skill(skill)))
					else:
						missed_by_string = "<color={0}>Success</color>".format(color_success)
					if DC in known_lockpicks:
						known = "Known lockpick {0} chest:\n".format(known_lockpicks[DC])
					else:
						known = ""
					if debug:
						logger.Info("Open lock, bugged roll => {1} + {2} = {3} vs. DC: {4}\tMissing {5}", lockpick(DC), roll, real_skill(skill), roll+real_skill(skill), real_DC(DC), missed_by_string)
					hgx.Messages.Show("Open lock\n{0}Roll translates to => {1} + {2} = {3} vs. DC: {4} {5}", known, roll, real_skill(skill), roll+real_skill(skill), real_DC(DC), missed_by_string)
				elif bugged == "+":
					# Not a bugged roll but still a failed one: perhaps a low level rogue trying a high DC trap
					missing = real_DC(DC)-(roll+skill)
					if missing > 0:
						missed_by_string = "<color={0}>Missing {1}</color>".format(color_failure, real_DC(DC)-(roll+skill))
					else:
						missed_by_string = "Something else went wrong."
					if DC in known_lockpicks:
						known = "Known lockpick {0} chest:\n".format(known_lockpicks[DC])
					else:
						known = ""
					if debug:
						logger.Info("Open lock\t{0}Roll translates to => {1} + {2} = {3} vs. DC: {4} {5}", known, roll, skill, roll+skill, real_DC(DC), missed_by_string)
					hgx.Messages.Show("Open lock\n{0}Roll translates to => {1} + {2} = {3} vs. DC: {4} {5}", known, roll, skill, roll+skill, real_DC(DC), missed_by_string)
		return

	if " : Disable Trap : " in e.Line:
		result = check_pattern.search(e.Line)
		if result:
			success, roll, bugged, skill, calculated, DC = result.groups()
			if success != "Success":
				roll = int(roll)
				skill = int(skill)
				DC = int(DC)
				missing = real_DC(DC)-(roll+real_skill(skill))
				if missing > 0:
					missed_by_string = "<color={0}>Missing {1}</color>".format(color_failure, real_DC(DC)-(roll+real_skill(skill)))
				else:
					missed_by_string = "<color={0}>Success</color>".format(color_success)
				if debug:
					logger.Info("Disable trap:\tRoll translates to => {0} + {1} = {2} vs. DC: {3} {4}", roll, skill, roll+skill, real_DC(DC), missed_by_string)
				hgx.Messages.Show("Disable trap:\nRoll translates to => {0} + {1} = {2} vs. DC: {3} {4}", roll, skill, roll+skill, real_DC(DC), missed_by_string)
		return


def on_lineread_check_skills(sender, e):

	global qualify
	global skills

	if " : Disable Trap : " in e.Line:
		qualify &= "127 = " in e.Line
		result = baseskill_pattern.search(e.Line)
		if result:
			skills.append(result.group(1))
		return

	if " : Open Lock : " in e.Line:
		qualify &= "127 = " in e.Line
		result = baseskill_pattern.search(e.Line)
		if result:
			skills.append(result.group(1))
		return

	if " : Search : " in e.Line:
		qualify &= "127 = " in e.Line
		hgx.GameEvents.LogEntryRead -= on_lineread_check_skills
		result = baseskill_pattern.search(e.Line)
		if result:
			skills.append(result.group(1))
		hgx.Messages.Show("Skillchecks {0}: ({1}) {2}", skills_for_class.upper(), "/".join(skills), ("<color={0}>FAILED</color>".format(color_failure), "<color={0}>PASSED</color>".format(color_success))[qualify])
		return


def command_handler (sender, e):

	global qualify
	global skills
	global skills_for_class

	if e.Command.lower().startswith(("skillcheck", "check")):
		if e.Parameters:
			sub_command = e.Parameters[0]
			if sub_command.startswith("rogue"):
				qualify = True
				skills = []
				skills_for_class = "Rogue"
				hgx.GameEvents.LogEntryRead += on_lineread_check_skills
				send_commands()
		else:
			# Default is skill check rogue
			qualify = True
			skills = []
			skills_for_class = "Rogue"
			hgx.GameEvents.LogEntryRead += on_lineread_check_skills
			send_commands()


def send_commands():

	# This is rogue, more to come
	hgx.Messages.Chat("!skillcheck 2 127")
	hgx.Messages.Chat("!skillcheck 9 127")
	hgx.Messages.Chat("!skillcheck 14 127")


if __name__ == "__main__":

	baseskill_pattern = re.compile (r"\+(\d*) = ")
	check_pattern = re.compile(r"\: \*(.+)\* \: \((\d*) (\+|\-) (\d*) = (-?\d*) (?:vs\. DC\:|\/) (\d*)\)$")

	# Setup event handling
	hgx.UserEvents.ChatCommand += command_handler
	hgx.GameEvents.LogEntryRead += on_lineread

	if add_module_info:
		add_module_info (module_name, module_version, __version__)
