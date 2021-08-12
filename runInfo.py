# coding: utf-8
__version__ = "$Rev: 7 $"
module_version = "0.100"
module_name = "RunInfo"

#
#

# TODO:
# Nothing yet

import hgx
import NLog
import re
import xml.etree.ElementTree as ET
import locale

import clr
clr.AddReference("System.Windows.Forms")
import System
from System.Windows.Forms import Clipboard
from System.Threading import Thread, ThreadStart


try:
	from versionInfo import add_module_info
except ImportError:
	add_module_info = None

locale.setlocale(locale.LC_ALL, '')

logger = NLog.LogManager.GetLogger(__file__)

public_announce = None
public_announce_default = False

info_tree = None
info_dict = {}
info_dict_nicks = {}


def set_clipboard_text(text):
	def thread_proc():
		System.Windows.Forms.Clipboard.Clear()
		System.Windows.Forms.Clipboard.SetText(text)

	t = Thread(ThreadStart(thread_proc))
	t.ApartmentState = System.Threading.ApartmentState.STA
	t.Start()
	t.Join()


def command_handler (sender, e):

	global public_announce

	if e.Command.startswith("info"):
		if e.Parameters:
			sub_command = e.Parameters[0]
			splits = sub_command.split (" ", 1)
			command = splits[0]
			params = splits[1] if len(splits) > 1 else None
			if command == "*private":
				public_announce = False
				hgx.Settings.SetValue("UserData.{0}.public_announce".format(module_name), public_announce)
				hgx.Messages.Show("Public display layer: {0}", ("OFF", "ON")[public_announce])
			elif command == "*public":
				public_announce = True
				hgx.Settings.SetValue("UserData.{0}.public_announce".format(module_name), public_announce)
				hgx.Messages.Show("Public display layer: {0}", ("OFF", "ON")[public_announce])
			else:
				#check nick names
				nicks_found = [k for k in info_dict_nicks if k.lower().startswith(command.lower())]
				if len(nicks_found) == 1:
					runs_found = [info_dict_nicks[nicks_found[0]]]
				else:
					runs_found = [k for k in info_dict if k.lower().startswith(command.lower())]
				if len(runs_found) > 0:
					if len(runs_found) == 1:
						out_str = u"\nRun info for {0}:\nIMM: {1}".format(runs_found[0].upper(), info_dict[runs_found[0]])
						doc = info_tree.getroot()
						# layer has NOHIT info?
						elem = doc.find(".//layer[@name='{0}'][@nohit]".format(runs_found[0]))
						if elem is not None:
							text = elem.get('nohit')
							# there is a tag, make sure its not empty
							if len(text) > 0:
								out_str = out_str + "\nNOHIT: " + text
						# layer has a note added?
						elem = doc.find(".//layer[@name='{0}'][@note]".format(runs_found[0]))
						if elem is not None:
							text = elem.get('note')
							# there is a tag, make sure its not empty
							if len(text) > 0:
								out_str = out_str + "\nNOTE: " + text
						set_clipboard_text(out_str)
						if public_announce:
							hgx.Messages.Chat("/p {0}", out_str)
						else:
							hgx.Messages.Show("{0}", out_str)
					else:
						hgx.Messages.Show("Ambigious runs matching: {0}", ','.join(runs_found))
				else:
					hgx.Messages.Show("Run not found: {0}", command)


def get_layer_info():

	global info_tree
	global info_dict
	global info_dict_nicks

	filename = "./data/layer.xml"
	try:
		info_tree = ET.parse(filename)
	except IOError:
		logger.Error("{0}: xml file {1} not found", module_name, filename)
	finally:
		doc = info_tree.getroot()
		layer_count = 0
		for elem in doc.findall('layer'):
			layer_name = elem.get('name')
			layer_nickname = elem.get('nickname')
			layer_count +=1
			info_dict[layer_name] = elem.get('immunities')
			if layer_nickname is not None:
				info_dict_nicks[layer_nickname] = layer_name
		logger.Info("{0}: {1} layer loaded from {2}", module_name, layer_count, filename)


if __name__ == "__main__":
	public_announce = hgx.Settings.GetBool("UserData.{0}.public_announce".format(module_name))
	if public_announce is None:
		public_announce = public_announce_default
		hgx.Settings.SetValue("UserData.{0}.public_announce".format(module_name), public_announce)

	get_layer_info()

	hgx.UserEvents.ChatCommand += command_handler

	if add_module_info:
		add_module_info (module_name, module_version, __version__)
