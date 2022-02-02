__version__ = "$Rev: 21 $"
module_version = "1.400"
module_name = "ItemTracker(.NET)"

'''
	FINAL BETA
	Tracks items put into / removed from bankchests and players
	
	BETTER DON'T USE FOR HC BANKCHESTS
'''
# Switched to .NET sqlite
# All queries are using a single connection (again), opened and closed by a map change event
# The map change event is also adding/removing the on_lineread event
# Changes to sql database like inserts, updates and deletes are committed after each item
#
# Command parameters need a leading '*' from now on

# KNOWN PROBLEMS/BUGS:
# Using an item which is adding or removing other items from the user's inventory WILL BUG the chest content when doing this
# while a chest is opened
# 
#
# Using bank chests NEXT to another player bugs the DB as well. The script is reading the messages in log which are meant for
# the other player.....

# TODO:
# Try to handle error condition: saving to an existing chest
# Implement a rollback function? What does it give at all?
# Implement some HC chest handling. The problem is: They are character name based and deleted on death
# Make the search function active even when tracking is disabled?

# Active only if chest is opened:
# open:
# [CHAT WINDOW TEXT] [Thu Feb 05 10:07:28] 0 items successfully loaded from transfer chest 'staves-sorc-3'
# close:
# [CHAT WINDOW TEXT] [Thu Feb 05 10:08:03] 9 items successfully saved to transfer chest 'staves-sorc'
# CHAT WINDOW TEXT] [Thu Feb 05 10:08:45] Chest empty. No items saved.

#try
#	transaction.Rollback();
#except SQLiteException, e:
#	logger.Error ("Rollback Exception Type: {0}", e.GetType())
#	logger.Error ("   Message: {0}", e.Message)

# Timing info:
# insert inventory:
# 	110 item = 17.252s (each INSERT within a single transaction)
# 	110 item =  0.982s (bulk insert)
#
# !list contents
# 	42 item 5.251s (each INSERT witin a single transaction)
# 	        0.272s (bulk insert)

#CHANGES:
# Proper handling of !list contents (saves to DB right after command is issued)
# Added: handling synccount after a !list contents
# Fixed: Moving items to player after a !list contents
# Fixed: search was still active even if the main functionality was disabled, creating an uncaught exception that way

import hgx
import NLog
import re
import sys
import os
import errno
import glob
import filecmp
from datetime import datetime
from shutil import copyfile

import clr
clr.AddReference("System.Data.SQLite")
from System.Data.SQLite import *
from System import DBNull
from Microsoft.Practices.ServiceLocation import ServiceLocator

from collections import defaultdict
from System.Collections.Generic import Dictionary

try:
	from versionInfo import add_module_info
	versionInfo_loaded = True
except ImportError:
	versionInfo_loaded = False 

try:
	import System
	import time
	from Overlay import UserOverlay
	from OverlayExtensions import ClickableOverlay
	overlay_available = True
except ImportError:
	overlay_available = False

from time import clock
starttime = None

def seconds_to_string(secs):
	return "%d:%02d:%02d.%03d" % \
		reduce(lambda ll,b : divmod(ll[0],b) + ll[1:], [(secs*1000,),1000,60,60])

# get a logger for the script
logger = NLog.LogManager.GetLogger(__file__)


#---------------------------------------------------------------------------------------------------------------------------
# USER: Change in case you have to
#---------------------------------------------------------------------------------------------------------------------------

sqlite_connection_string = 'data source=chests.db;'
sqlite_connection_string_RO = sqlite_connection_string + "Read Only=True;"

# Item tracking will be AUTO enabled on the following maps:
active_on_maps = ["Bank of Waukeen", "Forge of Ixion", "Guild Dark Templars - Interior"]

debug = True
# debug = False

#script_version = "Old"
script_version = "New"

versioned_chests = True
limit_saved_chests_dbs_to = 20
chests_path = 'chests/'

#---------------------------------------------------------------------------------------------------------------------------


tracking_enabled = False
list_content = False
replace_content = False
listing_chests = False

db_connection = None
in_list = defaultdict(int)
out_list= defaultdict(int)
chests_found = set()
active_chest = None
new_chest = None
original_chest_name = None

max_empty_lines = 0
listing_inventory = False
listing_equipment = False

active_player = None
bulk_insert = None

HC_chest_detected = False
chests_scheduled_to_get_deleted = False
chests_selected = set()

chest_opened = False

#-------------------------------------------------------------------------------------------------------------------
# Persistant variables here
#-------------------------------------------------------------------------------------------------------------------
verbose = None
verbose_default = True

output_to_overlay_enabled = None
output_to_overlay_enabled_default = True
#-------------------------------------------------------------------------------------------------------------------

overlays_locked = False


def create_db_tables():

	items_table_ddl = '''
	CREATE TABLE if not exists ITEMS (
	ID integer primary key autoincrement not null,
	NAME text not null,
	TIMESTAMP datetime DEFAULT CURRENT_TIMESTAMP
	)
	'''

	chests_table_ddl = '''
	CREATE TABLE if not exists CHESTS (
	ID integer primary key autoincrement not null,
	NAME text not null,
	TIMESTAMP datetime DEFAULT CURRENT_TIMESTAMP,
	SYNCCOUNT integer DEFAULT 0,
	TYPE integer DEFAULT 0
	)
	'''

	chests_table_alter1 = '''
	alter table CHESTS add column SYNCCOUNT integer DEFAULT 0
	'''

	contents_table_ddl = '''
	CREATE TABLE if not exists CONTENTS (
	ID integer primary key autoincrement not null,
	CHEST_ID integer not null references CHESTS(ID) ON DELETE CASCADE,
	ITEM_ID integer not null references ITEMS(ID) ON DELETE CASCADE,
	TIMESTAMP datetime DEFAULT CURRENT_TIMESTAMP
	)
	'''

	idx1_ddl = '''
	create unique index if not exists IDX_CHESTS_NAME on CHESTS (NAME asc);
	'''

	idx2_ddl = '''
	create unique index if not exists IDX_ITEMS_NAME on ITEMS (NAME asc);
	'''

	try:
		conn = SQLiteConnection(sqlite_connection_string)
		conn.Open()
		command = conn.CreateCommand()
		command.CommandText = items_table_ddl
		command.ExecuteNonQuery()
		command.CommandText = chests_table_ddl
		command.ExecuteNonQuery()
		command.CommandText = contents_table_ddl
		command.ExecuteNonQuery()
		command.CommandText = idx1_ddl
		command.ExecuteNonQuery()
		command.CommandText = idx2_ddl
		command.ExecuteNonQuery()

		command.CommandText = chests_table_alter1
		command.ExecuteNonQuery()
	except SQLiteException, e:
		if not "duplicate column name: SYNCCOUNT" in e.Message:
			logger.Error ("create_db_tables() - SQlite Error: {0}", e.Message)
	finally:
		command.Dispose()
		conn.Close()
		if debug:
			logger.Info("create_db_tables() - After closing connection")

	if versioned_chests:
		try:
			os.makedirs(chests_path)
		except OSError as exception:
			if exception.errno != errno.EEXIST:
				logger.Error ("create_db_tables() - create directory failed")
				raise

		# Get latest archived chest.db and compare to current, only save if different
		pattern = re.compile(r"chests-\d{4}-\d\d-\d\dT\d{6}.db")
		chest_copy_to = chests_path + datetime.now().strftime("chests-%Y-%m-%dT%H%M%S.db")
#		logger.Info("create_db_tables() - matching files with pattern: '{0}'", pattern.pattern)
		preselected_archives = glob.glob('chests/chests-*.db')

		# Make sure its a archived chest
		archives = [k for k in preselected_archives if re.search(pattern, k)]
		if len(archives) > 0:
			if verbose:
				for item in archives:
					logger.Info("create_db_tables() - found file: {0}", item)
			logger.Info("create_db_tables() - selected file for compare: {0}", archives[-1])
			if not filecmp.cmp ("chests.db",archives[-1], shallow = False):
				if verbose:
					logger.Info("create_db_tables() - file content differs, archiving actual chests db file")
				copyfile("chests.db", chest_copy_to)
				if len(archives) >= limit_saved_chests_dbs_to and limit_saved_chests_dbs_to > 0:
					if verbose:
						logger.Info("create_db_tables() - limiting saved SQL DBs to {0}", limit_saved_chests_dbs_to)
					for db_file in archives[0:len(archives)-limit_saved_chests_dbs_to]:
						if verbose:
							logger.Info("create_db_tables() - scheduled for delete: {0}", db_file)
						os.remove(db_file)
		else:
			if verbose:
				logger.Info("create_db_tables() - no matched files, archiving actual chests db file")
			copyfile("chests.db", chest_copy_to)


def is_player_chest (name):

	try:
		select_chest = db_connection.CreateCommand()
		select_chest.CommandText = "select type from chests where name=:name"
		select_chest.Parameters.Add(SQLiteParameter('name', name))
		type = select_chest.ExecuteScalar()
	except SQLiteException, e:
		logger.Error ("is_player_chest() - SQlite Error: {0}", e.Message)
#	logger.Error ("is_player_chest() - name: *{0}* type: {1}", name, type)
	if type == DBNull.Value:
		# Something went totally wrong. The name MUST be in the SQL db at this point
		logger.Error ("is_player_chest() - The name: *{0}* is not in the DB table", name)
		return -1
	elif type is None:
		return -1
	else:
		return (type&1)


def set_chest_name(raw_text):

	text = raw_text.strip()
	logger.Error ("name: *{0}* ", text)
	if is_player_chest(text) < 0:
		hgx.Messages.Show("Chest not found in DB anymore!")
	elif is_player_chest(text) == 1:
		hgx.Messages.Show("Player inventory. That's only a virtual chest.")
	else:
		if len(text) <= 16 and re.match(r"^[\w-]+$", text.strip()):
			hgx.Messages.Chat("!bc {0}", text.strip())
		else:
			hgx.Messages.Show("Malformed chest name")


def search_item (item):
	""" Search for an item.
	Displays a list of chests (sorted alphabetically) containing a matching item and item count.
	
	"""

	sql = '''
	SELECT c.name as chest, i.name as item, count(i.name) as itemcount FROM contents
	join chests c on chest_id=c.id
	join items i on item_id=i.id and i.name like :pattern
	group by c.name, i.name
	order by c.name, i.name asc
	'''

	hgx.Messages.Show("DEBUGSTATUS: *{0}*", debug)
	hgx.Messages.Show("ITEM: *{0}*", item)
	if db_connection is None:
		logger.Info("search_item() - NO connection to the database")
		return

	count_chests = 0
	count_items = 0

	# Only chests listed - check for length of 'chest', switch to a wider display in case there are also player names in
	chests_only = True

	old_chest = ""
	hgx.Messages.Show("DEBUGSTATUS: *{0}*", debug)
	hgx.Messages.Show("ITEM: *{0}*", item)

	pattern = "%" + item.strip('"') + "%"
	if debug:
		hgx.Messages.Show("PATTERN: *{0}*", pattern)
		logger.Info("search_item() - search pattern: *{0}*", pattern)

	if overlay_available and output_to_overlay_enabled:
		out_msg = 'Chest\tItem\tCount'
		output_template = "\n {0}\t{1}\t{2}"
		tabs = [110, 500, 70, 70]
		width = 650
	else:
		out_msg = ''
		output_template = "   {0:16} {1:20} {2}\n"
		tabs = None
		width = None

	try:
		command = db_connection.CreateCommand()
		command.CommandText = sql
		command.Parameters.Add(SQLiteParameter('pattern', pattern))
		reader = command.ExecuteReader()
		while reader.Read():
			out_msg += output_template.format(reader['chest'], reader['item'], reader['itemcount'])
			if str(reader['chest']) != old_chest:
				count_chests += 1
				old_chest = str(reader['chest'])
			count_items += int(reader['itemcount'])
			if len(reader['chest']) > 16:
				chests_only = False
		reader.Close()
		reader.Dispose()

		if not chests_only:
			#adjust tab positions in case player names are detected
			tabs = [200, 500, 70, 70]
			width = 740
		display_result ("Search results for *{0}*:".format(item),
		out_msg,
		"Total of {0:5} chest{1} found with {2:5} {3}.".format(count_chests, ("s", "")[count_chests == 1], count_items, ("items", "item")[count_items == 1]),
		tabs,
		width,
		active_column=0,
		result_column=1,
		callback=set_chest_name)

	except SQLiteException, e:
		logger.Error ("search_item() - SQlite Error: {0}", e.Message)
	finally:
		if debug:
			logger.Info("search_item() - Right before disposing command")
		command.Dispose()
		if debug:
			logger.Info("search_item() - After disposing command")


def status_report (params):
	""" Item tracker status report.
	Displays a list of chests (sorted alphabetically) which aren't tracked yet.
	As well as a few totals.
	
	"""


	tracked_chests = set()

	sql = '''
	select name from chests
	order by name
	'''

	try:
		if chests_found:
			command = db_connection.CreateCommand()
			command.CommandText = sql
			reader = command.ExecuteReader()
			while reader.Read():
				tracked_chests.add(reader['name'])
				#logger.Info ("status_report() - Item tracked: *{0}*", reader['name'])
			reader.Close()
			reader.Dispose()
			missed_chests = chests_found - tracked_chests
			if missed_chests:
				out_msg = 'Status report:\n'
				for chest in sorted(missed_chests):
					out_msg += "{0}\n".format(chest)
				hgx.Messages.Show(out_msg)
				hgx.Messages.Show("{0} total chests found.".format(len(chests_found)))
				hgx.Messages.Show("{0} total chests tracked.".format(len(tracked_chests)))
				hgx.Messages.Show("{0} total chests missed.".format(len(missed_chests)))
			else:
				hgx.Messages.Show("ALL chests tracked.")
		else:
			hgx.Messages.Show("Rebuilding list of chests.\nReissue command please after a few seconds.")
			hgx.Messages.Chat("!bc list")
	except SQLiteException, e:
		logger.Error ("status_report() - SQlite Error: {0}", e.Message)
	finally:
		command.Dispose()
		if debug:
			logger.Info("status_report() - After closing connection")


def list_chest_by_date (count=None):

	sql = '''select c.name as chest, i.name as item from contents
	join chests c on c.id=chest_id 
	join items i on i.id=item_id 
	order by contents.timestamp desc limit :count
	'''

	count_chests = 0
	count_items = 0
	out_msg = 'Chests by date:\n'
	if count is None:
		count = 10
	logger.Error ("Count seen as: *{0}*", count)

	try:
		command = db_connection.CreateCommand()
		command.CommandText = sql
		command.Parameters.Add(SQLiteParameter('count', count))
		reader = command.ExecuteReader()
		while reader.Read():
			out_msg += "{0:2}: {1}\n".format(int(reader['chest']), reader['item'])
			count_chests += 1
			count_items += int(reader['item'])
		reader.Close()
		reader.Dispose()
		hgx.Messages.Show(out_msg)
#		hgx.Messages.Show("Total of {0:5} chests found with {1:5} {2}.".format(count_chests, count_items, ("items", "item")[count_items == 1]))
	except SQLiteException, e:
		logger.Error ("list_chest_by_date() - SQlite Error: {0}", e.Message)
	finally:
		command.Dispose()
		if debug:
			logger.Info("list_chest_by_date() - After closing connection")


def list_chest_by_name (name):

	sql = '''
	select name, used from (select c.name, count(*) as used  from contents
	join chests c on c.id=chest_id and c.name like :pattern
	group by c.name)
	'''

	logger.Error("Params: *{0}*", name)
	count_chests = 0
	count_items = 0
	out_msg = ''

	pattern = "%" + name.strip() + "%"
	if debug:
		hgx.Messages.Show("PATTERN: *{0}*", pattern)

	try:
		command = db_connection.CreateCommand()
		command.CommandText = sql
		command.Parameters.Add(SQLiteParameter('pattern', pattern))
		reader = command.ExecuteReader()
		while reader.Read():
			out_msg += "{0:2}: {1}\n".format(int(reader['used']), reader['name'])
			count_chests += 1
			count_items += int(reader['used'])
		reader.Close()
		reader.Dispose()
		hgx.Messages.Show(out_msg)
		hgx.Messages.Show("Total of {0:5} chests found with {1:5} {2}.".format(count_chests, count_items, ("items", "item")[count_items == 1]))
	except SQLiteException, e:
		logger.Error ("list_chest_by_name() - SQlite Error: {0}", e.Message)
	finally:
		command.Dispose()
		if debug:
			logger.Info("list_chest_by_name() -  After closing connection")


def list_chest_by_content_count (item_count=None):

	sql = '''
	select name, used from (select c.name, count(*) as used  from contents
	join chests c on c.id=chest_id
	group by c.name)
	where used < :count
	'''

	count_chests = 0
	count_items = 0
	out_msg = 'Chests by count:\n'
	if item_count is None:
		item_count = 999

	try:
		command = db_connection.CreateCommand()
		command.CommandText = sql
		command.Parameters.Add(SQLiteParameter('count', item_count))
		reader = command.ExecuteReader()
		while reader.Read():
			out_msg += "{0:2}: {1}\n".format(reader['used'], reader['name'])
			count_chests += 1
			count_items += int(reader['used'])
		reader.Close()
		reader.Dispose()
		hgx.Messages.Show(out_msg)
		hgx.Messages.Show("Total of {0:5} chest{1} found with {2:5} {3}.".format(count_chests, ("s", "")[count_chests == 1], count_items, ("items", "item")[count_items == 1]))
	except SQLiteException, e:
		logger.Error ("list_chest_by_content_count() - SQlite Error: {0}", e.Message)
	finally:
		command.Dispose()
		if debug:
			logger.Info("list_chest_by_content_count() - After closing connection")


def list_chest_by_sync (params):

	sql = '''
	select name, synccount from chests
	where synccount != 0
	order by name
	'''

	count_chests = 0
	out_msg = 'Chests out of sync:\n'

	try:
		command = db_connection.CreateCommand()
		command.CommandText = sql
		reader = command.ExecuteReader()
		while reader.Read():
			out_msg += "{0:2}: {1}\n".format(reader['name'], reader['synccount'])
			count_chests += 1
		reader.Close()
		reader.Dispose()
		hgx.Messages.Show(out_msg)
		hgx.Messages.Show("Total of {0:5} chest{1} found.".format(count_chests, ("s", "")[count_chests == 1]))
	except SQLiteException, e:
		logger.Error ("list_chest_by_sync() - SQlite Error: {0}", e.Message)
	finally:
		command.Dispose()
		if debug:
			logger.Info("list_chest_by_sync() - After closing connection")


def count_items_for_chest (name):

	try:
		command = db_connection.CreateCommand()
		command.CommandText = "select count (*) from contents join chests c on chest_id=c.id and c.name = :name"
		command.Parameters.Add(SQLiteParameter('name', name))
		result = command.ExecuteScalar()
	except SQLiteException, e:
		logger.Error ("open_chest() - SQlite Error: {0}", e.Message)
	finally:
		command.Dispose()
		if debug:
			logger.Info("open_chest() - After closing connection")
		return int(result)


def open_chest (name):

	global original_chest_name
	global new_chest

	new_chest = None
	original_chest_name = name
	return count_items_for_chest(name)


def close_chest (name):

	global original_chest_name

	original_chest_name = None



def rename_chest (oldName, newName):

	try:
		trans = db_connection.BeginTransaction()
		command = db_connection.CreateCommand()
		command.CommandText = "UPDATE chests set name=:new where name = :old"
		command.Parameters.Add(SQLiteParameter('new', newName))
		command.Parameters.Add(SQLiteParameter('old', oldName))
		command.ExecuteNonQuery()
		if chests_found:
			chests_found.discard(oldName)
			chests_found.add(newName)
		hgx.Messages.Show("rename_chest() - CHEST renamed: {0} => {1}", oldName, newName)
	except SQLiteException, e:
		logger.Error ("rename_chest() - SQlite Error: {0}", e.Message)
	finally:
		command.Dispose()
		trans.Commit()
		trans.Dispose()
		if debug:
			logger.Info("rename_chest() - After closing connection")


def delete_content (name):

	try:
		trans = db_connection.BeginTransaction()
		command = db_connection.CreateCommand()
		command.CommandText = "delete from contents where contents.id in (select contents.id from contents join chests c on c.id = chest_id and c.name = :name)"
		command.Parameters.Add(SQLiteParameter('name', name))
		command.ExecuteNonQuery()
		if debug:
			hgx.Messages.Show("delete_content() - CONTENT removed: {0}", name)
	except SQLiteException, e:
		logger.Error ("delete_content() - SQlite Error: {0}", e.Message)
	finally:
		command.Dispose()
		trans.Commit()
		trans.Dispose()
		if debug:
			logger.Info("delete_content() - After closing connection")


def delete_chest (name):

	try:
		trans = db_connection.BeginTransaction()
		command = db_connection.CreateCommand()
		command.CommandText = "DELETE from chests where name = :name"
		command.Parameters.Add(SQLiteParameter('name', name))
		command.ExecuteNonQuery()
		if debug:
			hgx.Messages.Show("delete_chest() - CHEST removed: {0}", name)
	except SQLiteException, e:
		logger.Error ("delete_chest() - SQlite Error: {0}", e.Message)
	finally:
		command.Dispose()
		trans.Commit()
		trans.Dispose()
		if debug:
			logger.Info("delete_chest() - After closing connection")


def update_sync_count(chest, count_there, count_here):

	try:
		trans = db_connection.BeginTransaction()
		command = db_connection.CreateCommand()
		command.CommandText = "UPDATE chests set synccount=:diff where name = :name"
		command.Parameters.Add(SQLiteParameter('name', chest))
		command.Parameters.Add(SQLiteParameter('diff', count_there-count_here))
		command.ExecuteNonQuery()
		if debug:
			hgx.Messages.Show("update_sync_count() - CHEST count updated: {0}", name)
	except SQLiteException, e:
		logger.Error ("update_sync_count() - SQlite Error: {0}", e.Message)
	finally:
		command.Dispose()
		trans.Commit()
		trans.Dispose()
		if debug:
			logger.Info("update_sync_count() - After closing connection")


def add_item (active_chest, item, flush=True, chest_type=0):
	""" Add an item to a chest.

	In case the chest is NOT in the database the chest is created and the item is inserted
	"""

	try:
		if flush:
			trans = db_connection.BeginTransaction()
		if debug:
			logger.Info("add_item() -Adding item: {0} to chest {1}", item, active_chest)

		if active_chest is not None:
			#get chest id
			select_chest = db_connection.CreateCommand()
			select_chest.CommandText = "select id from chests where name=:name"
			select_chest.Parameters.Add(SQLiteParameter('name', active_chest))
			chest_ID = select_chest.ExecuteScalar()
			if chest_ID:
				if debug:
					logger.Info("add_item() - CHEST found: {0}", chest_ID)
			else:
				#create chest and get id
				if debug:
					logger.Info("add_item() - Creating chest: {0}", active_chest)
				insert_chest = db_connection.CreateCommand()
				insert_chest.CommandText = "INSERT INTO chests (name, type) VALUES (:activeChest, :type)"
				insert_chest.Parameters.Add(SQLiteParameter('activeChest', active_chest))
				insert_chest.Parameters.Add(SQLiteParameter('type', chest_type))
				insert_chest.ExecuteNonQuery()
				chest_ID = db_connection.LastInsertRowId
				insert_chest.Dispose()
			if debug:
				logger.Info("add_item() - chest_id {0}", chest_ID)

			#get item id
			select_item = db_connection.CreateCommand()
			select_item.CommandText = "select id from items where name=:item"
			select_item.Parameters.Add(SQLiteParameter('item', item))
			item_ID = select_item.ExecuteScalar()
			if item_ID:
				if debug:
					logger.Info("add_item() - open_chest: ITEM found: {0}", item_ID)
			else:
				#create item and get id
				if debug:
					logger.Info("add_item() - Creating item: {0}", item)
				insert_item = db_connection.CreateCommand()
				insert_item.CommandText = "INSERT INTO items (name) VALUES (:item)"
				insert_item.Parameters.Add(SQLiteParameter('item', item))
				insert_item.ExecuteNonQuery()
				item_ID = db_connection.LastInsertRowId
				insert_item.Dispose()

			if debug:
				hgx.Messages.Show("insert_item: Before adding contents")
			insert_contents = db_connection.CreateCommand()
			insert_contents.CommandText = "INSERT INTO contents (chest_id, item_id) VALUES (:c_id, :i_id)"
			insert_contents.Parameters.Add(SQLiteParameter('c_id', chest_ID))
			insert_contents.Parameters.Add(SQLiteParameter('i_id', item_ID))
			insert_contents.ExecuteNonQuery()
			if debug:
				hgx.Messages.Show("insert_item: Item added: {0}", item)

	except SQLiteException, e:
		logger.Error ("add_item() - SQlite Error: {0}", e.Message)
	finally:
		if active_chest is not None:
			select_chest.Dispose()
			select_item.Dispose()
			insert_contents.Dispose()
		if flush:
			trans.Commit()
			trans.Dispose()
		if debug:
			logger.Info("add_item() - After closing connection")


def remove_item (active_chest, item):
	""" Remove a single item from a chest.

	In case the chest is NOT in the database further processing is skipped
	Same for an item which isnt tracked yet
	"""

	try:
		trans = db_connection.BeginTransaction()
		if debug:
			logger.Info("remove_item() - Removing item: {0} from chest {1}", item, active_chest)
		if active_chest is not None:
			#get chest id
			select_chest = db_connection.CreateCommand()
			select_chest.CommandText = "select id from chests where name=:name"
			select_chest.Parameters.Add(SQLiteParameter('name', active_chest))
			chest_ID = select_chest.ExecuteScalar()
			if chest_ID:
				#get item id
				select_item = db_connection.CreateCommand()
				select_item.CommandText = "select id from items where name=:item"
				select_item.Parameters.Add(SQLiteParameter('item', item))
				item_ID = select_item.ExecuteScalar()
				select_item.Dispose()
				if item_ID:
					if debug:
						logger.Info("remove_item() - Preparing SQL: chest {0}, item {1}", chest_ID, item_ID)
					delete_item = db_connection.CreateCommand()
					delete_item.CommandText = "DELETE from contents where rowid = (select rowid from contents where chest_id = :c_id and item_id = :i_id limit 1)"
					delete_item.Parameters.Add(SQLiteParameter('c_id', chest_ID))
					delete_item.Parameters.Add(SQLiteParameter('i_id', item_ID))
					delete_item.ExecuteNonQuery()
					if debug:
						logger.Info("remove_item() - Item removed: {0}", item)
					if debug:
						hgx.Messages.Show("Item removed: {0}", item)
					delete_item.Dispose()

	except SQLiteException, e:
		logger.Error ("remove_item() - SQlite Error: {0}", e.Message)
	finally:
		if active_chest is not None:
			select_chest.Dispose()
		trans.Commit()
		trans.Dispose()
		if debug:
			logger.Info("remove_item() - After closing connection")


def display_parsing_results(type, item, counter, quantifier):

	logger.Info ("\tType:\t\t*{0}*",			type if type is not None else "None")
	logger.Info ("\tItem:\t\t*{0}*",			item if item is not None else "None")
	logger.Info ("\tCounter:\t*{0}*",			counter if counter is not None else "None")
	logger.Info ("\tQuantifier:\t*{0}*",	quantifier if quantifier is not None else "None")


def process_inventory_line (line):

	global max_empty_lines
	global bulk_insert
	global listing_inventory

# lines to test:
#    Saving Pen
#    Scroll of the Miser [x3]
#    Thieves' Tools +18 (x49)
#    Rod: Greater Rod of Stone to Flesh (50 charges) [x2]
#	if ':' not in line and not line.startswith("* Unidentified"):
	if not line.startswith("* Unidentified"):
		new_item = line.strip()
		if len(new_item) > 0:

			# OLD pattern used:
			# ^([^(|^[]*)(?:\((?:x)?(\d*)(?: charges)?\))?(?: \[x(\d*)\])?$
			# result = inventory_pattern.search(new_item)

			# NEW pattern used:
			# ^(?:(Ability|Potion|Rod|Scroll|Wand): )?(.+?)(?: \((?:x)?(\d+)(?: charges)?\))?(?: \[x(\d+)\])?$
#			logger.Info ("Item to parse: *{0}*", new_item)
			result = inventory_pattern_new.match(new_item)
			if result:
				type, item, counter, quantifier = result.groups()
				item = item.strip()
				if quantifier is None:
					if counter is not None:
						item = "{0} ({1} uses)".format(item, counter)
#					display_parsing_results(type, item, counter, quantifier)
					add_item (active_player, item, False, chest_type=1)
				else:
					if counter is not None:
						item = "{0} ({1} uses)".format(item, counter)
					for i in range(int(quantifier)):
#						display_parsing_results(type, item, counter, quantifier)
						add_item (active_player, item, False, chest_type=1)
		else:
			# we got an empty line: ONE empty line(s) as end of command
			if script_version != "New":
				max_empty_lines -= 1
				if max_empty_lines <= 0:
					endtime = clock()
					elapsed = endtime - starttime
					logger.Info ("INSERTING character inventory into sql db done - elapsed time: {0}", seconds_to_string(elapsed))
					bulk_insert.Commit()
					listing_inventory = False

def on_lineread(sender, e):
	""" Read each line in log and search for events which are relevant for tracking items.
	Only active if tracking is auto-enabled on certain maps or enabled manually by user
	
	"""

	global in_list
	global out_list
	global active_chest
	global new_chest
	global list_content
	global replace_content
	global listing_chests
	global chests_found
	global max_empty_lines
	global listing_inventory
	global listing_equipment

	global chest_opened

	global bulk_insert
	global starttime

	global HC_chest_detected

	if tracking_enabled:

		#logger.Info ("Tracking line: *{0}*", e.Line)
		#logger.Debug("EXTRA HANDLER ACTIVE T:{0}, C:{1}, LEN: {2}", e.HasChatWindowTag, e.Continued, len(e.Line))
		#logger.Debug("Line: [{0}]", e.Line)

		line=e.Line

#------------------------------------------------------------------------------------------------------------------------------
# chest opened
#------------------------------------------------------------------------------------------------------------------------------
		if "items successfully loaded from" in line:
			chest_opened = True
			logger.Info("Chest opened.")
			#return

#------------------------------------------------------------------------------------------------------------------------------
# chest closed
#------------------------------------------------------------------------------------------------------------------------------
		if "items successfully saved to" in line or "Chest empty. No items saved." in line:
			chest_opened = False
			logger.Info("Chest closed.")
			#return

#------------------------------------------------------------------------------------------------------------------------------
# !bc list
#
#	new logic - counting empty lines no longer needed
#------------------------------------------------------------------------------------------------------------------------------
		if script_version == "New":
			if 'Your CD key has transfer chests named:' in line:
				if debug:
					logger.Info ("command: !bc list detected")
				# clear old list
				chests_found.clear()
				for single_line in line.split("\n"):
					if ':' not in single_line:
						new_item = single_line.strip()
						if len(new_item) > 0:
							chests_found.add(new_item)
							#logger.Info ("item added: *{0}*", new_item)
				return

		if script_version != "New":
			if 'Your CD key has transfer chests named:' in line:
				#process a "!bc list" command
				listing_chests = True
				max_empty_lines = 2
				# clear old list
				chests_found.clear()
				return

		if script_version != "New":
			if listing_chests:
				if e.Continued:
					if ':' not in line:
						new_item = line.strip()
						if len(new_item) > 0:
							chests_found.add(new_item)
							#logger.Info ("item added: *{0}*", new_item)
						else:
							#empty line, 2 consecutive empty lines as end of command
							max_empty_lines -= 1
							if max_empty_lines <= 0:
								listing_chests = False
				else:
					listing_chests = False
					#logger.Info ("collected chests {0}", len(chests_found))
				return


#------------------------------------------------------------------------------------------------------------------------------
# !list contents
#------------------------------------------------------------------------------------------------------------------------------
		if line.startswith('Contents of Persistent Transfer Chest:') or line.startswith('Contents of Persistent Storage Chest:'):
			list_content = True
			# clear "chest inlist" since we are replacing contents
			replace_content = True
			in_list.clear()
			return

		if line.endswith(("items listed.", "item listed.", "No items found.")):
			list_content = False
			if not line.endswith("No items found."):
				# write contents to DB to ensure the next in and outs are working properly
				delete_content (active_chest)
				# do a bulk insert
				xbulk_insert = db_connection.BeginTransaction()
				starttime = clock()
				for item in in_list:
					if in_list[item] > 0:
						for i in range (0, in_list[item]):
							add_item (active_chest, item, False)
#							logger.Info ("Adding item list contents: {0}", item)
				endtime = clock()
				elapsed = endtime - starttime
				try:
					xbulk_insert.Commit()
				except SQLiteException, e:
					logger.Error ("lineread() saving chest - SQlite Error: {0}", e.Message)
				else:
					xbulk_insert.Dispose()
					logger.Info ("SAVING chest done (list contents) - elapsed time: {0}, {1} items added to chest {2}", seconds_to_string(elapsed), sum(in_list.itervalues()), active_chest)
			return

		if list_content:
			if script_version == "New":
				logger.Info("Processing line: *{0}*", line)
				for single_line in line.split("\n"):
					if not single_line.endswith(":"):
						new_item = single_line.strip()
						if len(new_item) > 0:
							#hgx.Messages.Show("Found: *{0}*", new_item)
							#put onto list so item gets save if chest is closed
							in_list[new_item] += 1
				return
			else:
				if not line.endswith(":"):
					new_item = line.strip()
					if len(new_item) > 0:
						#hgx.Messages.Show("Found: *{0}*", new_item)
						#put onto list so item gets save if chest is closed
						in_list[new_item] += 1
				return


#------------------------------------------------------------------------------------------------------------------------------
# open chest
#------------------------------------------------------------------------------------------------------------------------------
		result = re.match(r"^(\d+) items successfully loaded from transfer chest '(.+)'", line)
		if result:
			item_count_nwn, active_chest = result.groups()
			if debug:
				logger.Info("OPEN Chest: {0} - Items: {1}", active_chest, item_count_nwn)
				hgx.Messages.Show("OPEN Chest: {0} - Items: {1}", active_chest, item_count_nwn)
			if active_chest == 'personal':
				active_chest += " - " + str(active_player)
				if debug:
					hgx.Messages.Show("Personal chest detected, adding player name {0}", active_chest)

			item_count_nwn = 0 if item_count_nwn is None else int(item_count_nwn)
			item_count_sql = open_chest (active_chest)
			if item_count_sql == 0:
				if debug:
					logger.Info("Chest NOT in DB: {0}", active_chest)
					hgx.Messages.Show("Chest NOT in DB: {0}", active_chest)
			elif item_count_sql != item_count_nwn:
				if debug:
					logger.Info("Out of sync! There: {0}, Here: {1}", item_count_nwn, item_count_sql)
				hgx.Messages.Show("{0} - Out of sync! There: {1}, Here: {2}", active_chest, item_count_nwn, item_count_sql)
				hgx.Messages.Show("Do a '!list contents' while chest is open to resync.")
				update_sync_count(active_chest, item_count_nwn, item_count_sql)
			return

#------------------------------------------------------------------------------------------------------------------------------
# open HC chest
#------------------------------------------------------------------------------------------------------------------------------
		result = re.match(r"^(\d+) items successfully loaded. Items loaded from HC vaults", line)
		if result:
			item_count_nwn = result.group(1)
			HC_chest_detected = True
			return

#------------------------------------------------------------------------------------------------------------------------------
# close chest
#------------------------------------------------------------------------------------------------------------------------------
		result = re.match(r"^(\d+) items successfully saved to transfer chest '(.+)'", line)
		if result:
			item_count_nwn, saved_chest = result.groups()
			if HC_chest_detected:
				#TODO:
				# some naming conventions for HC chests to keep them separate from normal (CD-Key) bound ones
				active_chest = saved_chest
			if replace_content:
#				if len(in_list) != count_items_for_chest(active_chest):
#					hgx.Messages.Show("REPLACE {0} - will be out of sync!\nThere: {1}, Here: {2}", active_chest, item_count_nwn, count_items_for_chest(active_chest))
				'''
				if debug:
					hgx.Messages.Show("REPLACING contents Chest: {0} - Items: {1}", active_chest, result[0][0])
				#delete old content
				starttime = clock()
				delete_content (active_chest)
				endtime = clock()
				elapsed = endtime - starttime
				logger.Info ("delete_content() done - elapsed time: {0}", seconds_to_string(elapsed))

				# do a bulk insert
				xbulk_insert = db_connection.BeginTransaction()
				starttime = clock()
				for item in in_list:
					if in_list[item] > 0:
						for i in range (0, in_list[item]):
							add_item (active_chest, item, False)
				endtime = clock()
				elapsed = endtime - starttime
				try:
					xbulk_insert.Commit()
				except SQLiteException, e:
					logger.Error ("lineread() saving chest - SQlite Error: {0}", e.Message)
				finally:
					xbulk_insert.Dispose()
					logger.Info ("SAVING Chest done - elapsed time: {0}", seconds_to_string(elapsed))
				logger.Info ("lineread()  saving chest after !list content, commit done")

				#clear async count
				update_sync_count (active_chest, 0, 0)
				'''
				replace_content = False
			else:
				if debug:
					hgx.Messages.Show("SAVING Chest: {0} - Items: {1}", active_chest, result[0][0])
				for item in in_list:
					if in_list[item] > 0:
						for i in range (0, in_list[item]):
							add_item (active_chest, item)
				for item in out_list:
					if out_list[item] > 0:
						for i in range (0, out_list[item]):
							remove_item (active_chest, item)
			if int(item_count_nwn) != count_items_for_chest(active_chest):
				hgx.Messages.Show("{0} - will be out of sync!\nThere: {1}, Here: {2}", active_chest, item_count_nwn, count_items_for_chest(active_chest))
			else:
				# chest is in sync, remove chest from async table by updating synccount with same values for counts
				update_sync_count (active_chest, 0, 0)

			# chest renamed?
			if new_chest is not None:
				if new_chest != original_chest_name:
					rename_chest(active_chest, new_chest)
				new_chest = None
			close_chest (active_chest)
			in_list.clear()
			out_list.clear()
			active_chest = None
			HC_chest_detected = False
			new_chest = None
			return

#------------------------------------------------------------------------------------------------------------------------------
# item taken from chest
#------------------------------------------------------------------------------------------------------------------------------
		result = re.findall(r'^Acquired Item: (.+)', line)
		if result:
			if active_chest is not None:
				item_out = result[0]
				if debug:
					hgx.Messages.Show("Item taken from chest: {0}", item_out)
				#out_list[item_out] += 1
				remove_item (active_chest, item_out)
				# ADD item to player inventory 'chest'
				# BUG: sometimes active player is not set properly
				add_item (hgx.Encounters.PlayerCharacter, item_out)
				#add_item (active_player, item_out)
			else:
				if result[0] != "Player Hide":
					logger.Info("Unkown source for acquiration")
			return

#------------------------------------------------------------------------------------------------------------------------------
# item placed into chest
#------------------------------------------------------------------------------------------------------------------------------
		result = re.findall(r'^Lost Item: (.+)', line)
		if result:
			if active_chest is not None:
				item_in = result[0]
				if debug:
					hgx.Messages.Show("Item into Chest: {0}", item_in)
					logger.Info("Item into Chest: C:{0} I:{1}", active_chest, item_in)
				#in_list[item_in] += 1
				add_item (active_chest, item_in)
				# REMOVE item from player inventory 'chest'
				remove_item (active_player, item_in)
			return

#------------------------------------------------------------------------------------------------------------------------------
# rename (an open) chest
#------------------------------------------------------------------------------------------------------------------------------
		result = re.findall(r"^You are now using bank chest '(.+)'\.", line)
		if result:
			if active_chest is not None:
				if result[0] is not active_chest:
					new_chest = result[0]
					if debug:
						hgx.Messages.Show("Chest renamed: {0}", new_chest)
				else:
					new_chest = None
			return

#------------------------------------------------------------------------------------------------------------------------------
# saving an empty chest
#------------------------------------------------------------------------------------------------------------------------------
		elif "Chest empty" in line:
			delete_chest (active_chest)
			if chests_found:
				chests_found.discard(active_chest)
			in_list.clear()
			out_list.clear()
			active_chest = None
			return

#------------------------------------------------------------------------------------------------------------------------------
# Chest not loading because of an existing one
#------------------------------------------------------------------------------------------------------------------------------
		elif "There are already items in this chest." in line:
			return

#------------------------------------------------------------------------------------------------------------------------------
# Chest not saved because of an existing one
#------------------------------------------------------------------------------------------------------------------------------
		elif "**WARNING** You already have items in a transfer chest with that name." in line:
			pass

#------------------------------------------------------------------------------------------------------------------------------
# (Try to) handle player character inventory
#------------------------------------------------------------------------------------------------------------------------------

#[CHAT WINDOW TEXT] [Fri Dec 27 16:03:39] [Server] Your inventory:
#    Corroded Signet of Set
#    Eye of the Remorhaz
#    Hel's Fury
#    Band of Anubis
#    Caustic Healings Band
#    Conservancy
#    Eldouin Scourge
#    Inferno's Chill
#    Insulated Corona of Origen
#    Signet of Mammon
#    Loki's Loop
#    Sunbringer's Hellfire's Focus
#    Audacious Provocation
#    Chillflame's Folly
#    Knight's Helm of Zeal
#    Mallek's Rebuke
#    Manipulative Masterful Performance of the Hearkening Mouse
#    Amulet of the Pharaoh
#    Beldoin's Spellturner
#    Belt of Eternal Preservation (7 charges)
#    Booming Pyre's Circle
#    Cold Bahamut's Ruination
#    Dueling Drum
#    Empyrean Indulgence
#    Mercurial Greatsword Wielder's Titan's Top
#    Seal of Divinity
#    Bellicose Lion's Mane
#    Belt of Legendary Resilience
#    Benediction
#    Coalwalker
#    Corruption
#    Insulated Origen's Precaution
#    Katana Wielder's Chillflame's Folly of the Diva
#    Scholar's Heavenly Haunt's Necklace
#    Amorian Berries (50 charges)
#    Apport Arcane (x6)
#    Azzagrat Hall of Mirrors Center Key
#    Bag of Holding [x12]
#    Biorevivifier [x3]
#    Bountiful Beaker of Healing
#    Box of Holding [x3]
#    Brazier of Painful Truth (21 charges)
#    Breach Ball (x50)
#    Command Targeter
#    Gem of Teleportation [x7]
#    Guildmaster's Glint
#    Lathar's Last Belt
#    Lens of Detection
#    Life Transference Rod [x3]
#    Magic Electrifier
#    Moderately Escapable Forcecage (11 charges)
#    Obi of the Geisha
#    PC Scrying Device
#    Pouch of Holding [x6]
#    Pouch of Perpetual Nature's Spite
#    Ring of Firewalking
#    Ring of Levitation
#    Ring of Passwall
#    Ring of Water Breathing
#    Saving Pen
#    Scroll of the Miser [x3]
#    Skull
#    Stillsound
#    Stone of Succor
#    Thieves' Tools +18 (x49)
#    Thieves' Tools +21 (x47)
#    Thieves' Tools +24 (x7)
#    Visor of Cursed Chaos
#    Zerial's Token
#    Ability: Autocaster
#    Ability: Breath of the Beast
#    Ability: Dirge of the Deathless (41 charges)
#    Ability: Hear Me Roar (41 charges)
#    Ability: Illusory Army (3 charges)
#    Ability: Pipes of Gesh'tak
#    Ability: Possum's Farce (10 charges)
#    Ability: Ring of the Planar Traveler (19 charges)
#    Ability: Unbowed, Unbent, Unbroken (41 charges)
#    Potion: Hostile Environment Potion (x19)
#    Potion: Potion of Etherealness (x35)
#    Potion: Potion of Life Unbound (x16)
#    Potion: Potion of Negative Energy Protection (x25)
#    Potion: Potion of the Third Eye (x17)
#    Potion: Unlimited Heal Pack (x50)
#    Rod: Greater Rod of Clarity (50 charges)
#    Rod: Greater Rod of Disaster (50 charges)
#    Rod: Greater Rod of Disease Removal (50 charges)
#    Rod: Greater Rod of Fear Removal (50 charges)
#    Rod: Greater Rod of Resurrection (50 charges)
#    Rod: Greater Rod of Stone to Flesh (50 charges)
#    Rod: Greater Rod of the Four Winds (50 charges)
#    Rod: Mallek's Test (47 charges)
#    Scroll: Greater Sanctuary (x15)
#    Scroll: Mind Blank (x40)
#    * Unidentified Gem

#   Wand: *clarity (16 charges)
#   Rod: Greater Rod of Stone to Flesh (50 charges) [x2]

		if script_version == "New":
			if 'Your inventory:' in line:
				delete_content (active_player)
				delete_chest (active_player)
				xbulk_insert = db_connection.BeginTransaction()
				starttime = clock()
				for single_line in line.split("\n"):
					if len (single_line) > 0:
						process_inventory_line(single_line)
				endtime = clock()
				elapsed = endtime - starttime
				try:
					xbulk_insert.Commit()
				except SQLiteException, e:
					logger.Error ("lineread() saving chest - SQlite Error: {0}", e.Message)
				finally:
					xbulk_insert.Dispose()
					logger.Info ("INSERTING character inventory into sql db done - elapsed time: {0}", seconds_to_string(elapsed))
				logger.Info ("lineread()  saving chest after !list content, commit done")
				return

		if script_version != "New":
			if 'Your inventory:' in line:
				listing_inventory = True
				bulk_insert = db_connection.BeginTransaction()
				starttime = clock()
				max_empty_lines = 1
				# clear old list
				delete_content (active_player)
				delete_chest (active_player)
				return

		if script_version != "New":
			if listing_inventory:
				if e.Continued:
					process_inventory_line(line)
				else:
					logger.Warn ("ABORTING with line: *{0}*", line)
					listing_inventory = False
				return

#------------------------------------------------------------------------------------------------------------------------------
# (Try to) handle equipped items on player character
#------------------------------------------------------------------------------------------------------------------------------

#[CHAT WINDOW TEXT] [Tue Dec 31 11:06:33] [Server] Your equipment:
#    Head: Deadening Visor of Vigilance
#    Chest: Chorus of the Damned
#    Boots: Legendary Boots of Defense of Precision Light Hammer-Work
#    Arms: Masterful Performance
#    Right Hand: Maarek's Molder
#    Left Hand: Cold Bastion of Cormyr
#    Cloak: Kyton's Cover
#    Left Ring: Crest of Vile Darkness
#    Right Ring: Corona of Origen
#    Neck: Elemental of the Worm
#    Belt: Graz'zt's Demonic Codpiece
#    Bullets: Mote of Cold Deflection

		if script_version == "New":
			if 'Your equipment:' in line:
				xbulk_insert = db_connection.BeginTransaction()
				starttime = clock()
				for single_line in line.split("\n"):
					if len (single_line) > 0:
						result = body_part_item_pattern.search(single_line)
						if result:
							body_part, item = result.groups()
							item = item.strip()
#							logger.Info ("Found: {0}, {1}", body_part, item)
							if len(item) > 0:
								add_item (active_player, item, False, chest_type=1)
				endtime = clock()
				elapsed = endtime - starttime
				try:
					xbulk_insert.Commit()
				except SQLiteException, e:
					logger.Error ("lineread()  handling equipment - SQlite Error: {0}", e.Message)
				finally:
					xbulk_insert.Dispose()
					logger.Info ("INSERTING equipped items into sql db done - elapsed time: {0}", seconds_to_string(elapsed))
				logger.Info ("Handling items, after commit")
				return

		if script_version != "New":
			if 'Your equipment:' in line:
				listing_equipment = True
				bulk_insert = db_connection.BeginTransaction()
				starttime = clock()
				max_empty_lines = 1
				return

		if script_version != "New":
			if listing_equipment:
				if e.Continued:
					if len(line) > 0:
						result = body_part_item_pattern.search(line)
						if result:
							body_part, item = result.groups()
#							logger.Info ("Found: {0}, {1}", body_part, item)
							add_item (active_player, item, False, chest_type=1)
					else:
						# we got an empty line: ONE empty line(s) as end of command
						max_empty_lines -= 1
						if max_empty_lines <= 0:
							endtime = clock()
							elapsed = endtime - starttime
							logger.Info ("INSERTING equipped items into sql db done - elapsed time: {0}", seconds_to_string(elapsed))
							bulk_insert.Commit()
							listing_equipment = False
				else:
					logger.Warn ("ABORTING with line: *{0}*", line)
					listing_equipment = False
				return


def enable_tracker(params):

	global tracking_enabled
	global db_connection

	if not tracking_enabled:
		tracking_enabled = True
		hgx.GameEvents.LogEntryRead += on_lineread
		if db_connection is None:
			try:
#				db_connection = SQLiteConnection(sqlite_connection_string_RO)
				db_connection = SQLiteConnection(sqlite_connection_string)
				db_connection.Open()
				cmd = db_connection.CreateCommand()
				cmd.CommandText = "PRAGMA foreign_keys = true;"
				cmd.ExecuteNonQuery()
				cmd.Dispose()
			except SQLiteException, e:
				logger.Error ("enable_tracker() - SQlite Error: {0}", e.Message)
			finally:
				if debug:
					logger.Info("enable_tracker() - connection opened")
	hgx.Messages.Show("Item tracking: {0}", ("Off", "On")[tracking_enabled])


def disable_tracker(params):

	global tracking_enabled
	global db_connection

	if debug:
		logger.Info ("disable_tracker: Start {0}", ("Off", "On")[tracking_enabled])
	if tracking_enabled:
		tracking_enabled = False
		in_list.clear()
		out_list.clear()
		active_chest = None
		hgx.GameEvents.LogEntryRead -= on_lineread
		if db_connection is not None:
			try:
				db_connection.Close()
				db_connection.Dispose()
				db_connection = None
			except SQLiteException, e:
				logger.Error ("disable_tracker() - SQlite Error: {0}", e.Message)
			finally:
				if debug:
					logger.Info("disable_tracker() - connection closed")
	hgx.Messages.Show("Item tracking: {0}", ("Off", "On")[tracking_enabled])


def on_mapchange(sender, e):

#	logger.Info ("Map: *{0}*", e.AreaName)
	if e.AreaName in active_on_maps:
		enable_tracker(None)
		hgx.Messages.Chat("!list inventory")
		hgx.Messages.Chat("!list equip")

	elif tracking_enabled:
		disable_tracker(None)


def on_playerchanged(sender, e):

	global active_player

	if script_version == "New":
		active_player = hgx.Encounters.PlayerCharacter
	else:
		active_player = hgx.Party.PlayerCharacter


def select_chests(chests):

	global chests_scheduled_to_get_deleted
	global chests_selected

	sql = '''
	SELECT name FROM chests where name like :pattern order by name
	'''

	chests_selected.clear()
	pattern = chests.strip('"') + "%"

	try:
		command = db_connection.CreateCommand()
		command.CommandText = sql
		command.Parameters.Add(SQLiteParameter('pattern', pattern))
		reader = command.ExecuteReader()
		while reader.Read():
			chests_selected.add(reader['name'])
			#logger.Info ("status_report() - Item tracked: *{0}*", reader['name'])
		reader.Close()
		reader.Dispose()
		if len(chests_selected) > 0:
			out_msg = ''
			for chest in sorted(chests_selected):
				out_msg += "{0}\n".format(chest)
			hgx.Messages.Show(out_msg)
			hgx.Messages.Show("{0} total chests found.".format(len(chests_selected)))
			chests_scheduled_to_get_deleted = True
		else:
			hgx.Messages.Show("No matching chests found.")
			chests_scheduled_to_get_deleted = False
	except SQLiteException, e:
		logger.Error ("select_chests() - SQlite Error: {0}", e.Message)
	finally:
		command.Dispose()
		if debug:
			logger.Info("select_chests() - After closing connection")


def delete_selected_chests():

	global chests_selected

	for chest in chests_selected:
		delete_content (chest)
		delete_chest (chest)
	chests_selected.clear()


def toggle_verbose (parameter):

	global verbose

	verbose = not verbose
	hgx.Settings.SetValue("UserData.{0}.verbose".format(module_name), verbose)
	hgx.Messages.Show("Verbose: {0}", ("OFF", "ON")[verbose])


def toggle_overlay (parameter):

	global output_to_overlay_enabled

	if overlays_locked:
		hgx.Messages.Show("Output to overlay permanently disabled due to an error.\n")
	else:
		output_to_overlay_enabled = not output_to_overlay_enabled
		hgx.Settings.SetValue("UserData.{0}.output_to_overlay_enabled".format(module_name), output_to_overlay_enabled)
		hgx.Messages.Show("Output to overlay: {0}", ("OFF", "ON")[output_to_overlay_enabled])


def list_version(parameter):

	version_minor = re.findall('Rev: (\d*)', __version__)
	complete_version = float(module_version) + float(version_minor[0])/1000
	hgx.Messages.Show("{0} - version: {1:.3f}".format(module_name, complete_version))


def command_handler (sender, e):
	""" Command handler only fully functional if tracking is ENABLED using '#tr *on'.
	
	"""

	global tracking_enabled
	global chests_scheduled_to_get_deleted

	if e.Command.startswith(("tracking", "tr")):
		chests_scheduled_to_get_deleted = False

		if e.Parameters:
			sub_command = e.Parameters[0]
			if debug:
				hgx.Messages.Show("Sub command: >{0}<", sub_command)
			if sub_command.startswith("*"):
				splits = sub_command.split (" ", 1)
				command = splits[0]
				params = splits[1] if len(splits) > 1 else None
				commands_found = [k for k in dispatch_table if k.startswith(command)]
				if len(commands_found) > 0:
					if len(commands_found) == 1:
						dispatch_table[commands_found[0]][0](params)
					else:
						hgx.Messages.Show("Ambigious command matching: {0}", ','.join(commands_found))
				else:
					hgx.Messages.Show("Unknown command\n{0}", usage)
			else:
				if debug:
					hgx.Messages.Show("Starting search for: >{0}<", sub_command)
				search_item (sub_command)
		else:
			hgx.Messages.Show(usage)

# delete chests, primary used for HC toons
	if e.Command.startswith(("delete", "del")):
		if tracking_enabled:
			if e.Parameters:
				options = e.Parameters[0]
				parameters = options.split (" ", 1)
				if parameters[0] == "chests":
					if parameters[1] is not None:
						chests_to_delete = parameters[1]
						select_chests(chests_to_delete)
				elif parameters[0] == "confirm" and chests_scheduled_to_get_deleted:
					delete_selected_chests()
					hgx.Messages.Show("Chests deleted.")
					chests_scheduled_to_get_deleted = False
				else:
					chests_scheduled_to_get_deleted = False
		else:
			hgx.Messages.Show("Command ignored. Tracking disabled.")


def display_result (title, result, footer, tabs = [100, 100, 100, 100], width=None, alignments=None, button_table=None, active_column=-1, result_column=0, callback=None):

	if overlay_available and output_to_overlay_enabled:
		user_overlay.clear_messages()
		user_overlay.title = title
		user_overlay.set_tabs(tabs)
		user_overlay.set_max_width(width)
		user_overlay.set_tabs_alignments(alignments)
		for line in result.split("\n"):
			user_overlay.WriteString(line)
		user_overlay.bottom_info = footer
		user_overlay.set_buttons (button_table)
		user_overlay.set_active_column (active_column)
		user_overlay.set_result_column (result_column)
		user_overlay.set_callback_function(callback)
		user_overlay.Visible = True
	else:
		hgx.Messages.Show(title)
		hgx.Messages.Show(result)
		hgx.Messages.Show(footer)


def on_lineread_track_delete(sender, e):

	# Handle a few delete character events automatic
	# Reincarnation
	if ": I am ready to face my destiny. No one knows what the future holds, but my time is at an end. Let my spirit pass to a new generation." in e.Line:
		res = re.search(r"(.+):", e.Line)
		if res:
			to_delete = res.group(1)
			logger.Info ("scheduled for delete by reincarnation light: *{0}*", to_delete)
			delete_content (to_delete)
			delete_chest (to_delete)
		return

	# Delete at Rowan's Guardian
	if ": Bottoms up!" in e.Line:
		res = re.search(r"(.+):", e.Line)
		if res:
			to_delete = res.group(1)
			logger.Info ("scheduled for delete using rowan' guardian npc: *{0}*", to_delete)
			delete_content (to_delete)
			delete_chest (to_delete)
		return

	# Using !delete command
	if "Deletion confirmed! Character will be booted for deletion momentarily." in e.Line:
		if hgx.Encounters.PlayerCharacter is not None:
			if "[test]" not in hgx.Encounters.PlayerCharacter.lower():
				to_delete = hgx.Encounters.PlayerCharacter
				logger.Info ("scheduled for delete by simtool command: *{0}*", to_delete)
				delete_content (to_delete)
				delete_chest (to_delete)
		return


if __name__ == "__main__":

	dispatch_table = {
		'*on':		(enable_tracker,				'Enable item tracking'),
		'*off':		(disable_tracker,				'Disable item tracking'),
		'*status':	(status_report,					'Show some statistic about the used bankchests'),
		'*count':	(list_chest_by_content_count,	'List chests by content count'),
		'*latest':	(list_chest_by_date,			'List chests by date'),
		'*name':	(list_chest_by_name,			'List chests by name'),
		'*overlay':	(toggle_overlay,				'Toggle alternative output to a separate overlay.'),
		'*verbose':	(toggle_verbose,				'Toggles script to be more/less verbose'),
		'*help':	(help,							'help!'),
		'*async':	(list_chest_by_sync,			'List chests out of sync'),
		'*version':	(list_version,					'Display version')
		}

	# setup persistant variables
	verbose = hgx.Settings.GetBool("UserData.{0}.verbose".format(module_name))
	if verbose is None:
		verbose = verbose_default
		hgx.Settings.SetValue("UserData.{0}.verbose".format(module_name), verbose)

	output_to_overlay_enabled = hgx.Settings.GetBool("UserData.{0}.output_to_overlay_enabled".format(module_name))
	if output_to_overlay_enabled is None:
		output_to_overlay_enabled = output_to_overlay_enabled_default
		hgx.Settings.SetValue("UserData.{0}.output_to_overlay_enabled".format(module_name), output_to_overlay_enabled)

	overlay_status_str = ("OFF", "ON")[output_to_overlay_enabled] if overlay_available else "Not available"
	usage = "Usage: #tr {0}\nSearch for item: #tr ITEMNAME\n Output to overlay: {1}".format(' | '.join(sorted(dispatch_table)), overlay_status_str)

	create_db_tables()

	inventory_pattern = re.compile (r"^([^(|^[]*)(?:\((?:x)?(\d*)(?: charges)?\))?(?: \[x(\d*)\])?$")
	inventory_pattern_new = re.compile(ur'^(?:(Ability|Potion|Rod|Scroll|Wand): )?(.+?)(?: \((?:x)?(\d+)(?: charges)?\))?(?: \[x(\d+)\])?$')

	body_part_item_pattern = re.compile (r"(.*): (.*)")

	hgx.UserEvents.ChatCommand += command_handler
	hgx.GameEvents.AreaChanged += on_mapchange

#	hgx.GameEvents.LogEntryRead += on_lineread

	#ALWAYS track player character deletes:
	hgx.GameEvents.LogEntryRead += on_lineread_track_delete

	if script_version == "New":
		hgx.Encounters.PlayerChanged += on_playerchanged
		active_player = hgx.Encounters.PlayerCharacter
	else:
		hgx.Party.PlayerChanged += on_playerchanged
		active_player = hgx.Party.PlayerCharacter

	if overlay_available:
		try:
			user_overlay = ClickableOverlay(hgx)
		except AttributeError:
			logger.Error ("Error while creating ClickableOverlay - FORCED disabling user overlays")
			output_to_overlay_enabled = False
			overlays_locked = True

	if versionInfo_loaded:
		add_module_info (module_name, module_version, __version__)
