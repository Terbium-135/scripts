__version__ = "$Rev: 15 $"
module_version = "0.000"
module_name = "BalanceGold"

# Make sure there is not more than 'amount_to_keep' gold on the player character.
# Either after a player character change or on entering a 'No PVP' map

# If active_balancing is enabled keep gold in inventory at that level by sending '!wallet with' commands
# Added limit gold per player character
# TODO:
# Nothing yet

import hgx
import NLog
import re

try:
	from versionInfo import add_module_info
except ImportError:
	add_module_info = None

import locale
locale.setlocale(locale.LC_ALL, '')

# get a logger for the script
logger = NLog.LogManager.GetLogger(__file__)

amount_to_keep_default = 200000000
threshold = 10000000
amount_to_keep = None
active_balancing_default = True
active_balancing = None
exclude_maps = ["Parallel Pocket Dimension"]

exclude_list = []
limits = {}


def balance (line):

#Wallet balances:
#  You are carrying 12,925,219 GP.
#  You have 9,316,831,758 GP in your main wallet.

	for single_line in line.split("\n"):
		result = re.search("You are carrying ([\d\,]+) GP\.", single_line)
		if result:
			amount_found = int(result.group(1).replace(",",""))
		result = re.search("You have ([\d\,]+) GP in", single_line)
		if result:
			amount_in_wallet = int(result.group(1).replace(",",""))
	if hgx.Encounters.PlayerCharacter in limits:
		# set to user defined limit
		balance = int(limits[hgx.Encounters.PlayerCharacter])
	else:
		# use default limit
		balance = amount_to_keep
	if amount_found > balance:
		if (amount_found - balance) > threshold:
			hgx.Messages.Chat("!wallet dep {0}", amount_found - balance)
	if amount_found < balance and active_balancing:
		if amount_in_wallet >= (balance - amount_found):
			if (balance - amount_found) > threshold:
				hgx.Messages.Chat("!wallet with {0}", balance - amount_found)


def on_lineread(sender, e):

	if "Wallet balances:" in e.Line:
		if hgx.Encounters.PlayerCharacter is not None:
			if not "[test]" in hgx.Encounters.PlayerCharacter.lower():
				if not hgx.Encounters.PlayerCharacter in exclude_list:
					balance(e.Line)


def on_mapchange(sender, e):

	if hgx.Encounters.PlayerCharacter is not None:
		if not "[test]" in hgx.Encounters.PlayerCharacter.lower():
			if e.AreaType == "No PVP":
				if e.AreaName not in exclude_maps:
					if hgx.Encounters.PlayerCharacter not in exclude_list:
						hgx.Messages.Chat("!wallet bal")


def on_playerchanged(sender, e):

	if hgx.Encounters.PlayerCharacter is not None:
		if not "[test]" in hgx.Encounters.PlayerCharacter.lower():
			if hgx.Encounters.PlayerCharacter not in exclude_list:
				hgx.Messages.Chat("!wallet bal")


def exclude_pc(name):

	global exclude_list

	hgx.Messages.Show("Start Excluded.")
	if not "[test]" in name.lower():
		hgx.Messages.Show("Name ok. exclude_list: {0}", ", ".join(exclude_list))
		if name == "*this":
			name = hgx.Encounters.PlayerCharacter
		exclude_list.append(name)
		hgx.Settings.SetValue("UserData.{0}.exclude_list".format(module_name), ", ".join(exclude_list))
		hgx.Messages.Show("{0} excluded.", name)

def include_pc(name):

	global exclude_list

	hgx.Messages.Show("Start Included.")
	if not "[test]" in name.lower():
		hgx.Messages.Show("Name ok. exclude_list: {0}", ", ".join(exclude_list))
		if name == "*this":
			name = hgx.Encounters.PlayerCharacter
		if name in exclude_list:
			exclude_list.remove(name)
			hgx.Settings.SetValue("UserData.{0}.exclude_list".format(module_name), ", ".join(exclude_list))
			hgx.Messages.Show("{0} included.", name)
		else:
			hgx.Messages.Show("{0} already included.", name)


def set_limit_pc(amount):

	global limits
	if hgx.Encounters.PlayerCharacter is not None:
		if not "[test]" in hgx.Encounters.PlayerCharacter.lower():
			limits[hgx.Encounters.PlayerCharacter] = amount
			hgx.Messages.Show("Limit for {0} set to {1}", hgx.Encounters.PlayerCharacter, locale.format("%d", amount, grouping=True))
			hgx.Messages.Chat("!wallet bal")
			temp_list = []
			for key, value in limits.iteritems():
				temp_list.append(":".join([key, str(value)]))
			hgx.Settings.SetValue("UserData.{0}.limit_list".format(module_name), ", ".join(temp_list))


def command_handler (sender, e):

	global amount_to_keep
	global active_balancing

	if e.Command.startswith(("balancegold", "bg")):
		if e.Parameters:
			parameter = e.Parameters[0]
			if parameter.isdigit():
				amount_to_keep = int(parameter)
				hgx.Settings.SetValue("UserData.{0}.amount_to_keep".format(module_name), amount_to_keep)
				hgx.Messages.Show("Gold limit set to: {0}", amount_to_keep)
			elif parameter == "balance":
				if not active_balancing:
					active_balancing = True
					hgx.Settings.SetValue("UserData.{0}.active_balancing".format(module_name), active_balancing)
					hgx.GameEvents.AreaChanged += on_mapchange
					hgx.Messages.Show("Active balancing ON")
			elif parameter == "no_balance":
				if active_balancing:
					active_balancing = False
					hgx.Settings.SetValue("UserData.{0}.active_balancing".format(module_name), active_balancing)
					hgx.GameEvents.AreaChanged -= on_mapchange
					hgx.Messages.Show("Active balancing OFF")
			elif parameter.startswith("exclude"):
				splits = parameter.split (" ", 1)
				name = splits[1] if len(splits) > 1 else None
				if name is not None:
					exclude_pc(name)
			elif parameter.startswith("include"):
				splits = parameter.split (" ", 1)
				name = splits[1] if len(splits) > 1 else None
				if name is not None:
					include_pc(name)
			elif parameter.startswith("limit"):
				splits = parameter.split (" ", 1)
				new_limit = splits[1] if len(splits) > 1 else None
				if new_limit is not None and new_limit.isdigit():
					amount = int(new_limit)
					set_limit_pc(amount)
		else:
			hgx.Messages.Show("Limit gold set to: {0}, active balancing is {1}", locale.format("%d", amount_to_keep, grouping=True), ("OFF", "ON")[active_balancing])


def on_damaged(sender, e):

	pass


def on_killed(sender, e):

	pass


def on_spellcasting(sender, e):

	pass


def on_resting(sender, e):

	pass


if __name__ == "__main__":
	amount_to_keep = hgx.Settings.GetInt("UserData.{0}.TEST", 100)

	amount_to_keep = hgx.Settings.GetInt("UserData.{0}.amount_to_keep".format(module_name))
	if amount_to_keep is None:
		amount_to_keep = amount_to_keep_default
		hgx.Settings.SetValue("UserData.{0}.amount_to_keep".format(module_name), amount_to_keep)

	active_balancing = hgx.Settings.GetBool("UserData.{0}.active_balancing".format(module_name))
	if active_balancing is None:
		active_balancing = active_balancing_default
		hgx.Settings.SetValue("UserData.{0}.active_balancing".format(module_name), active_balancing)
	if active_balancing:
		hgx.GameEvents.AreaChanged += on_mapchange

	exclude_list_str = hgx.Settings.GetString("UserData.{0}.exclude_list".format(module_name))
	if exclude_list_str is None:
		exclude_list = []
		hgx.Settings.SetValue("UserData.{0}.exclude_list".format(module_name), "")
	else:
		exclude_list = exclude_list_str.split(", ")

	limit_list_str = hgx.Settings.GetString("UserData.{0}.limit_list".format(module_name))
	if limit_list_str is None:
		limits = {}
		hgx.Settings.SetValue("UserData.{0}.limit_list".format(module_name), "")
	else:
#		limit_list = []
		limit_list = limit_list_str.split(", ")
		for limit in limit_list:
			if len(limit.split(":")) > 1:
				name, value = limit.split(":")
				limits[name] = value

	hgx.GameEvents.LogEntryRead += on_lineread
#	hgx.Encounters.PlayerChanged += on_playerchanged
	hgx.UserEvents.ChatCommand += command_handler

	if add_module_info:
		add_module_info (module_name, module_version, __version__)

	logger.Info("Default setting: Maximum gold on player character limited to: {0}, active balancing is {1}", locale.format("%d", amount_to_keep, grouping=True), ("OFF", "ON")[active_balancing])
