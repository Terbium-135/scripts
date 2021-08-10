__version__ = "$Rev: 19 $"
module_version = "1.700"
module_name = "CharacterInfo"
'''
This script tries to gather as much info as possible right after login of a playercharacter.
For hell and abyss tags the 'skull' must be used.
'''

# TODO:
# Make tags and their lookuptext an ordered dictionary (build from a set with tuples) and calculate the BITPOS

#---------------------------------------
# Don't mess with these please
schema_version = "4.1"
schema_notes = "CharacterInfo goes public"
update_schema = False
#---------------------------------------

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

from System.Threading import Thread, ThreadStart
clr.AddReference("System.Windows.Forms")

import locale
locale.setlocale(locale.LC_ALL, '')

try:
	from versionInfo import add_module_info
except ImportError:
	add_module_info = None

try:
	from update_characters import update_sql
except ImportError:
	update_sql = None

try:
	import System
	import time
	from overlay import UserOverlay
	overlay_available = True
except ImportError:
	overlay_available = False

from time import clock
import threading

from collections import OrderedDict

def seconds_to_str(secs):
	return "%d:%02d:%02d.%03d" % \
		reduce(lambda ll,b : divmod(ll[0],b) + ll[1:], [(secs*1000,),1000,60,60])

def set_clipboard_text(text):
	def thread_proc():
		System.Windows.Forms.Clipboard.SetText(text)

	t = Thread(ThreadStart(thread_proc))
	t.ApartmentState = System.Threading.ApartmentState.STA
	t.Start()

#setup logger
logger = NLog.LogManager.GetLogger(__file__)

# setup db connection
db_name = 'characters.db'
sqlite_connection_string = 'data source=' + db_name + '; foreign_keys = true;'
sqlite_connection_string_RO = sqlite_connection_string + "Read Only=True;"
db_connection = None

# preset versioned sql files
versioned_db = True
limit_saved_sql_dbs_to = 10
db_archive_path = 'characters/'

debug = False
#debug = True

deferred_commands = None
deferred_commands_default = False
commands_deferred = False

delayed_commands = None
delayed_commands_default = False
delay_by = None
delay_by_default = 10

output_to_overlay_enabled = None
output_to_overlay_enabled_default = True
multiple_accounts = None
multiple_accounts_default = False
verbose = None
verbose_default = False

accomplishments_text_legendary = [
"You have defeated Xulrae.",
"You have banished Lolth from this plane.",
"You have slain the Mother of All Dragons.",
"You have slain Dach'xilith'az'ichityl.",
"You have slain King Myxo Dreamcaller in his deep realm.",
"You have slain Moha-Go, the Herald of Ragnorra.",
"You have bathed in the blood of Ssssy'is.",
"You have disassembled the Toymaker.",
"You have slain Deacon Raholla, the Herald of Father Llymic.",
"You have slain Dustbone.",
"You have slain Uroboros, Scourge of the North.",
"You have ended Dulvuroth's unlife.",
"You have slain the Locathah Matriarch beneath the sea.",
"You have mastered the Illithid Overmind.",
"You have banished the Hand of Mydianchlarus from this plane.",
"You have permanently blinded Zorbgot.",
"You have sent the Black Pharaoh to his final rest.",
"You have defeated the Hive Overmind, ending the omni-rat menace.",
"You have ventured into Rona and defeated Rashla'El.",
"You have proven Your mastery of celestial essence.",
"You have conquered the madness of the Eldest.",
]

tags = {
"xul":			0,
"lolth":		1,
"moad":			2,
"dachy":		3,
"myco":			4,
"sissy":		5,
"toyshop":		6,
"db":			7,
"uro":			8,
"dulv":			9,
"loca":			10,
"thids":		11,
"pom":			12,
"beholder":		13,
"pyramid":		14,
"hive":			15,
"rona":			16,
"ely":			17,
"abo":			18,
"moha":			19,
"deacon":		20
}

accomplishments_text_pre_legendary = [
"You have defeated the Half-Orc Bandit Chief in his cave.",
"You have bested the Dragon Disciple in his tower.",
"You have slain a Hive Mother Beetle.",
"You have bested the Kuo-Toa Chief in his hut.",
"You have slain the Goblin Commander in his tent.",
"You have defeated the Kobold Reanimator.",
"You have put the Crypt Thing in a crypt of its own.",
"You have acquired a Hero Crystal.",
"You have mastered the Kennel Master in the goblin mines.",
"You have defeated the Rat King in the Sewers.",
"You have stolen the life of the Bandit Chief on the East Road.",
"You have defeated the Ice Kobold King.",
"You have toppled the Ogre Lord in his caverns.",
"You have defeated the Minotaur Chieftain in his maze.",
"You have defeated the dragon Cesspool.",
"You have reunited the Staff of Anduin and sundered it again.",
"You have stopped the mad schemes of the Corpse Lord.",
"You have defeated the Formian Matriarch.",
"You have killed the Render Queen of the Tainted Vale.",
"You have defeated the Lava King.",
"You have defeated the Dracolich.",
"You have defeated Hendron in his sanctum.",
"You have blinded an Elder Orb.",
"You have defeated the dragon Kardkildontar.",
"You have defeated the Spawn of the Deep One.",
"You have defeated the Spawn of Uroboros.",
"You have defeated the dragon Asimathas.",
"You have defeated the hags of the Blood Moors.",
"You have ended the reign of the Cave Troll King.",
"You have defeated the Mother of the Corn.",
"You have sent the lich Razhid to his final rest.",
"You have defeated the dragon Bloodpool.",
"You have defeated the dragon Grehnaxas.",
"You have defeated the dragon Lithiucshas.",
"You have shown the Shadow Lord the final shade of death.",
"You have defeated Captain Angus Materi.",
"You have defeated Elanna Nightstar.",
"You have defeated Hel, daughter of Loki, and her cohorts.",
"You have defeated the Queen Spider in the Web.",
"You have defeated the Shadow Pontiff.",
"You have defiled the corpse of Solis Gaobin.",
"You have defeated Queen Zerya.",
"You have vanquished the Black Dragon Knight on the slopes of Mount P'reeth.",
"You have defeated the Water Shrike Nest Mother.",
"You have sent the lich Axilar to his final rest.",
"You have defeated the Ancient Kings beneath the Crypts.",
"You have defeated the dragon Deadpool.",
"You have defeated the Drider Chief.",
"You have collected the head of the Drow Headmaster.",
"You have defeated the dragon Glithildhoul.",
"You have sent Lolth's Handmaiden back to the Demonweb.",
"You have ended the machinations of Matron De'nat.",
"You have stilled the black heart of Matron Fen'liss.",
"You have silenced the dark prayers of Matron Gur'atsz.",
"You have foiled the schemes of Matron Khur'aan.",
"You have shattered the crown of the Queen Matron Mat'lis'sk.",
"You have defeated the dragon Wastalgraniq.",
"You have defeated the Mother of All Dragons without immortal aid.",
"You have defeated Xulrae without immortal aid.",
"You have defeated Lolth without immortal aid.",
"You have defeated the Immortal.",
"You have given the Headmaster his final exam.",
]

search_tags_preLL = {
"bandit chief":				0,
"dragon diciple":			1,
"kuo-toa":					2,
"goblin commander":			3,
"reanimator":				4,
"crypt thing":				5,
"hero crystal":				6,
"kennel master":			7,
"rat king":					8,
"bandit chief":				9,
"kobold king":				10,
"ogre lord":				11,
"mino maze":				12,
"cesspool":					13,
"staff":					14,
"corpse lord":				15,
"formian":					16,
"grey renderer":			17,
"lava king":				18,
"dracolich":				19,
"hendron":					20,
"beholder":					21,
"deep one":					22,
"urospawn":					23,
"asimathas":				24,
"hags":						25,
"troll king":				26,
"mother of corn":			27,
"razhid":					28,
"bloodpool":				29,
"grehnaxas":				30,
"lithiucshas":				31,
"shadow lord":				32,
"angus materi":				33,
"elanna nightstar":			34,
"hel":						35,
"queen spider":				36,
"shadow pontiff":			37,
"solis gaobin":				38,
"queen zerya":				39,
"black dragon knight":		40,
"shrike mother":			41,
"axilar":					42,
"ancient kings":			43,
"deadpool":					44,
"drider chief":				45,
"drow headmaster":			46,
"glithildhoul":				47,
"handmaiden":				48,
"matron de'nat":			49,
"matron fen'liss":			50,
"matron gur'atsz":			51,
"matron khur'aan":			52,
"queen matron mat'lis'sk":	53,
"wastalgraniq":				54,
"mother of all dragons":	55,
"xulrae":					56,
"lolth":					57,
"immortal":					58,
"headmaster":				59,
}

accomplishments_text_limbo = [
"You have defeated the Keeper of the Unbroken Circle in Limbo.",
"You have crushed the Guardian of the Stone in Limbo.",
"You have bested the Lord of Entropy, Ygorl.",
"You have conquered the Lord of Madness, Ssendam."
]

search_tags_limbo = {
"keeper":                0,
"guardian":                1,
"ygorl":                2,
"ssendam":                3,
}
#-----------------------------------------------------------------------------------------------------------------
map_abyss_boss_to_run = {
"Demogorgon":	"Gaping Maw",
"Graz'zt":		"Azzagrat",
"Juiblex":		"Shedaklah",
"Obox-ob":		"Zionyn",
"Orcus":		"Thanatos"
}

display_abyss_run_as = {
"Gaping Maw":	"GM",
"Azzagrat":		"Azz",
"Shedaklah":	"Shed",
"Zionyn":		"Zio",
"Thanatos":		"Than"
}

#INFO:
#next_layer = hell_runs[(actual + 1) % len(hell_runs)]
hell_runs = ["Avernus", "Dispater", "Minauron", "Phlegethos", "Stygia", "Malbolge", "Maladomini", "Cania", "Nessus"]

abyss_tags_known = ["Belcheresk", "Oixhacual", "Kargoth the Betrayer", "Demogorgon", "Orwantz", "Zhelamiss", "Thraxxia", "Graz'zt", "Cctchk'tik'ca", "Malphas", "Fo-oon-fol", "Obox-ob", "Glyphimhor", "Fulgoz", "Harthoon", "Orcus", "the Teratomorph", "Qolsorron", "Darkness Given Hunger", "Juiblex", "Pazuzu", "Pelor"]
abyss_tags_handled = abyss_tags_known

hell_tags_known = ["Tiamat", "Dispater", "Quimath", "Belial", "the Nameless Pit Fiend", "the Ancient Baatorian", "Baalzebul", "Mephistopheles", "Asmodeus"]
hell_tags_handled = hell_tags_known

limbo_tags_known = ["Who knows"]
limbo_tags_handled = limbo_tags_known

#--------------------------------------------------------------------------------------------------------------

def set_clipboard_text(text):
	def thread_proc():
		System.Windows.Forms.Clipboard.SetText(text)

	t = Thread(ThreadStart(thread_proc))
	t.ApartmentState = System.Threading.ApartmentState.STA
	t.Start()


def needs_upgrade ():

	try:
		column_list = []
		with SQLiteConnection(sqlite_connection_string_RO) as conn:
			conn.Open()
			with conn.CreateCommand() as command:
				command.CommandText = 'PRAGMA table_info(tags);'
				with command.ExecuteReader() as reader:
					while reader.Read():
						column_list.append(reader['name'])
	except SQLiteException, e:
		logger.Error ("needs_upgrade() - SQlite Error: {0}", e.Message)
#	logger.Info ("result list: {0}", ", ".join(sorted(column_list)))
	if update_schema:
		logger.Info("Schema upgrade needed.")
	return update_schema


def create_db_tables():

	schema_migration = '''
	create table if not exists schema_migrations (
	version text not null primary key,
	notes text default '',
	applied_at timestamp not null default CURRENT_TIMESTAMP
	)
	'''

	tags_table_ddl = '''
	CREATE TABLE if not exists TAGS (
	ID integer primary key autoincrement not null,
	NAME text not null,
	LAYER text,
	PAZUNIA BOOLEAN DEFAULT 0 CHECK (PAZUNIA IN (0,1)),
	PAZUZU BOOLEAN DEFAULT 0 CHECK (PAZUZU IN (0,1)),
	TIMESTAMP datetime DEFAULT CURRENT_TIMESTAMP,
	last_update datetime,
	PANDECT BOOLEAN DEFAULT 0 CHECK (PANDECT IN (0,1)),
	TOME BOOLEAN DEFAULT 0 CHECK (TOME IN (0,1)),
	TAGS_LL integer DEFAULT 0,
	TAGS_PRELL integer DEFAULT 0,
	TAGS_ABYSS integer DEFAULT 0,
	TAGS_HELL integer DEFAULT 0,
	TAGS_LIMBO integer DEFAULT 0,
	DEMI_COUNT integer DEFAULT 0,
	PELOR BOOLEAN DEFAULT 0 CHECK (PELOR IN (0,1)),
	all_pre_LL BOOLEAN DEFAULT 0 CHECK (all_pre_LL IN (0,1)),
	PRINCE_WINS text DEFAULT null,
	PLAYERNAME text DEFAULT '',
	CD_KEY text DEFAULT '',
	IP text DEFAULT '',
	LEVEL interger DEFAULT 0,
	XP integer DEFAULT 0,
	XP_TNL integer DEFAULT 0,
	DEITY text DEFAULT '',
	SUBRACE text DEFAULT ''
	);
	'''

	abyss_table_ddl = '''
	CREATE TABLE if not exists ABYSS (
	ID integer primary key autoincrement not null,
	TAGS_ID integer not null references TAGS(ID) ON DELETE CASCADE,
	RUN text,
	PART integer,
	TIMESTAMP datetime DEFAULT CURRENT_TIMESTAMP
	)
	'''

	idx_ddl = '''
	create unique index if not exists IDX_TAGS_NAME on TAGS (NAME asc);
	'''

	trigger_tags_ddl = '''
	create trigger if not exists tags_updated after update on tags
	begin
		update tags set last_update = datetime('now') where id = new.id;
	end;
	'''

	try:
		conn = SQLiteConnection(sqlite_connection_string)
		conn.Open()
		command = conn.CreateCommand()
		command.CommandText = schema_migration
		command.ExecuteNonQuery()
		command.CommandText = tags_table_ddl
		command.ExecuteNonQuery()
		command.CommandText = abyss_table_ddl
		command.ExecuteNonQuery()
		command.CommandText = idx_ddl
		command.ExecuteNonQuery()
		command.CommandText = trigger_tags_ddl
		command.ExecuteNonQuery()
	except SQLiteException, e:
		# explicitely considering a 'duplicate column name' here
		if not "duplicate column name: " in e.Message:
			logger.Error ("create_db_tables() - SQlite Error: {0}", e.Message)
	finally:
		command.Dispose()
		conn.Close()
		conn.Dispose()

	# greater change in table layout done via copying
	if needs_upgrade() and update_sql:
		update_sql

	if versioned_db:
		try:
			os.makedirs(db_archive_path)
		except OSError as exception:
			if exception.errno != errno.EEXIST:
				logger.Error ("create_db_tables() - create directory failed")
				raise

		# Get latest archived sql db and compare to current, only save if different
		pattern = re.compile(r"characters-\d{4}-\d\d-\d\dT\d{6}.db")
		db_copy_to = db_archive_path + datetime.now().strftime("characters-%Y-%m-%dT%H%M%S.db")
		preselected_archives = glob.glob(db_archive_path + 'characters-*.db')

		# Make sure its a archived sql db for real
		archives = [k for k in preselected_archives if re.search(pattern, k)]
		if len(archives) > 0:
			if verbose:
				logger.Info("create_db_tables() - selected file for compare: {0}", archives[-1])
			if not filecmp.cmp (db_name,archives[-1], shallow = False):
				if verbose:
					logger.Info("create_db_tables() - file content differs, archiving actual sql db file")
				copyfile(db_name, db_copy_to)
				if len(archives) >= limit_saved_sql_dbs_to and limit_saved_sql_dbs_to > 0:
					if verbose:
						logger.Info("create_db_tables() - limiting saved SQL DBs to {0}", limit_saved_sql_dbs_to)
					for db_file in archives[0:len(archives)-limit_saved_sql_dbs_to]:
						if verbose:
							logger.Info("create_db_tables() - scheduled for delete: {0}", db_file)
						os.remove(db_file)
		else:
			if verbose:
				logger.Info("create_db_tables() - no matched files, archiving actual chests db file")
			copyfile(db_name, db_copy_to)


def update_player (abyss_tags, layer, pazunia, flush = True):
	""" insert or UPDATE a player's character.
	
	"""

	starttime = clock()
	try:
		if flush:
			trans = db_connection.BeginTransaction()
		if debug:
			logger.Info("update_player() - started")

		if hgx.Encounters.PlayerCharacter is not None and "[test]" not in hgx.Encounters.PlayerCharacter:
			if debug:
				logger.Info("update_player() - for player *{0}*", hgx.Encounters.PlayerCharacter)
			command = db_connection.CreateCommand()
			command.CommandText = "UPDATE tags set layer=:layer, pazunia=:pazunia WHERE name=:name"
			command.Parameters.Add(SQLiteParameter('name', hgx.Encounters.PlayerCharacter))
			command.Parameters.Add(SQLiteParameter('layer', layer))
			command.Parameters.Add(SQLiteParameter('pazunia', pazunia))
			rows_affected = command.ExecuteNonQuery()

			if rows_affected==0:
				command.CommandText = "INSERT INTO tags (name, layer, pazunia) VALUES (:name, :layer, :pazunia)"
				command.Parameters.Add(SQLiteParameter('name', hgx.Encounters.PlayerCharacter))
				command.Parameters.Add(SQLiteParameter('layer', layer))
				command.Parameters.Add(SQLiteParameter('pazunia', pazunia))
				command.ExecuteNonQuery()

			command.CommandText = "SELECT id from tags where name=:name"
			command.Parameters.Add(SQLiteParameter('name', hgx.Encounters.PlayerCharacter))
			tag_ID_used = int(command.ExecuteScalar())

			#delete OLD abyss tags
			command.CommandText = "delete from abyss where abyss.id in (select abyss.id from abyss join tags t on t.id = tags_id and t.name = :name)"
			command.Parameters.Add(SQLiteParameter('name', hgx.Encounters.PlayerCharacter))
			command.ExecuteNonQuery()

			if debug:
				logger.Info("update_player() - using tag: {0}", tag_ID_used)

			#insert NEW abyss tags
			command.CommandText = "INSERT INTO abyss (tags_id, run, part) VALUES (:tags_id, :run, :part)"
			command.Parameters.Add(SQLiteParameter('name', hgx.Encounters.PlayerCharacter))
			command.Parameters.Add(SQLiteParameter('tags_id', tag_ID_used))
			for run in abyss_tags:
				command.Parameters.Add(SQLiteParameter('run', run))
				command.Parameters.Add(SQLiteParameter('part', abyss_tags[run]))
				command.ExecuteNonQuery()

			command.Dispose()

	except SQLiteException, e:
		logger.Error ("update_player() - SQlite Error: {0}", e.Message)

	finally:
		if flush:
			trans.Commit()
			trans.Dispose()
		if debug:
			logger.Info("update_player() - After closing connection")
	endtime = clock()
	elapsed = endtime - starttime
	if verbose:
		logger.Info ("INSERT/UPDATE player into sql db done - elapsed time: {0}", seconds_to_str(elapsed))


def update_accomplishments_preLL (tags_preLL, all_pre_LL, flush = True):

	starttime = clock()
	try:
		if flush:
			trans = db_connection.BeginTransaction()
		if debug:
			logger.Info("update_accomplishments_preLL() - started")

		if hgx.Encounters.PlayerCharacter is not None and "[test]" not in hgx.Encounters.PlayerCharacter:
			if debug:
				logger.Info("update_player() - for player *{0}*", hgx.Encounters.PlayerCharacter)
			command = db_connection.CreateCommand()
			command.CommandText = "UPDATE tags set tags_preLL=:tags_preLL, all_pre_LL=:all_pre_LL WHERE name=:name"
			command.Parameters.Add(SQLiteParameter('name', hgx.Encounters.PlayerCharacter))
			command.Parameters.Add(SQLiteParameter('tags_preLL', tags_preLL))
			command.Parameters.Add(SQLiteParameter('all_pre_LL', all_pre_LL))
			rows_affected = command.ExecuteNonQuery()

			if rows_affected==0:
				command.CommandText = "INSERT INTO tags (name, tags_preLL, all_pre_LL) VALUES (:name, :tags_preLL, :all_pre_LL)"
				command.Parameters.Add(SQLiteParameter('name', hgx.Encounters.PlayerCharacter))
				command.Parameters.Add(SQLiteParameter('tags_preLL', tags_preLL))
				command.Parameters.Add(SQLiteParameter('all_pre_LL', all_pre_LL))
				command.ExecuteNonQuery()

			command.Dispose()

	except SQLiteException, e:
		logger.Error ("update_accomplishments_preLL() - SQlite Error: {0}", e.Message)

	finally:
		if flush:
			trans.Commit()
			trans.Dispose()
		if debug:
			logger.Info("update_accomplishments_preLL() - After closing connection")
	endtime = clock()
	elapsed = endtime - starttime
	if verbose:
		logger.Info ("UPDATING pre LL accomplishments done - elapsed time: {0}", seconds_to_str(elapsed))


def update_accomplishments (prince_wins, demi_count, pelor, pazuzu, tags_LL, bitmap_abyss_tags, bitmap_hell_tags, bitmap_limbo, tome, pandect, flush = True):

	starttime = clock()
	try:
		if flush:
			trans = db_connection.BeginTransaction()
		if debug:
			logger.Info("update_accomplishments() - started")

		if hgx.Encounters.PlayerCharacter is not None and "[test]" not in hgx.Encounters.PlayerCharacter:
			if debug:
				logger.Info("update_player() - for player *{0}*", hgx.Encounters.PlayerCharacter)
			command = db_connection.CreateCommand()
			command.CommandText = "UPDATE tags set pazuzu=:pazuzu, pelor=:pelor, demi_count=:demi_count, prince_wins=:prince_wins, tags_LL=:tags_LL, tome=:tome, pandect=:pandect, tags_abyss=:tags_abyss, tags_hell=:tags_hell, tags_limbo=:tags_limbo WHERE name=:name"
			command.Parameters.Add(SQLiteParameter('name', hgx.Encounters.PlayerCharacter))
			command.Parameters.Add(SQLiteParameter('pazuzu', pazuzu))
			command.Parameters.Add(SQLiteParameter('pelor', pelor))
			command.Parameters.Add(SQLiteParameter('demi_count', demi_count))
			command.Parameters.Add(SQLiteParameter('prince_wins', ', '.join(prince_wins)))
			command.Parameters.Add(SQLiteParameter('tags_LL', tags_LL))
			command.Parameters.Add(SQLiteParameter('pandect', pandect))
			command.Parameters.Add(SQLiteParameter('tome', tome))
			command.Parameters.Add(SQLiteParameter('tags_abyss', bitmap_abyss_tags))
			command.Parameters.Add(SQLiteParameter('tags_hell', bitmap_hell_tags))
			command.Parameters.Add(SQLiteParameter('tags_limbo', bitmap_limbo))
			rows_affected = command.ExecuteNonQuery()

			if rows_affected==0:
				command.CommandText = "INSERT INTO tags (name, pazuzu, pelor, demi_count, prince_wins, tags_LL, tome, pandect, tags_abyss, tags_hell, tags_limbo) VALUES (:name, :pazuzu, :pelor, :demi_count, :prince_wins, :tags_LL, :tome, :pandect, :tags_abyss, :tags_hell, :tags_limbo)"
				command.Parameters.Add(SQLiteParameter('name', hgx.Encounters.PlayerCharacter))
				command.Parameters.Add(SQLiteParameter('pazuzu', pazuzu))
				command.Parameters.Add(SQLiteParameter('pelor', pelor))
				command.Parameters.Add(SQLiteParameter('demi_count', demi_count))
				command.Parameters.Add(SQLiteParameter('prince_wins', ', '.join(prince_wins)))
				command.Parameters.Add(SQLiteParameter('tags_LL', tags_LL))
				command.Parameters.Add(SQLiteParameter('pandect', pandect))
				command.Parameters.Add(SQLiteParameter('tome', tome))
				command.Parameters.Add(SQLiteParameter('tags_abyss', bitmap_abyss_tags))
				command.Parameters.Add(SQLiteParameter('tags_hell', bitmap_hell_tags))
				command.Parameters.Add(SQLiteParameter('tags_limbo', bitmap_limbo))
				command.ExecuteNonQuery()

			command.Dispose()

	except SQLiteException, e:
		logger.Error ("update_accomplishments() - SQlite Error: {0}", e.Message)

	finally:
		if flush:
			trans.Commit()
			trans.Dispose()
		if debug:
			logger.Info("update_accomplishments() - After closing connection")
	endtime = clock()
	elapsed = endtime - starttime
	if verbose:
		logger.Info ("UPDATING accomplishments done - elapsed time: {0}", seconds_to_str(elapsed))


def update_playerinfo(player_name, cd_key, ip, level, xp, xp_tnl, deity, subrace, flush = True):

	starttime = clock()
	try:
		if flush:
			trans = db_connection.BeginTransaction()
		if debug:
			logger.Info("update_playerinfo() - started")

		if hgx.Encounters.PlayerCharacter is not None and "[test]" not in hgx.Encounters.PlayerCharacter:
			if debug:
				logger.Info("update_playerinfo() - for player *{0}*", hgx.Encounters.PlayerCharacter)
			command = db_connection.CreateCommand()
			command.CommandText = "UPDATE tags set playername=:playername, cd_key=:cd_key, xp=:xp, xp_tnl=:xp_tnl, subrace=:subrace, ip=:ip, level=:level, deity=:deity WHERE name=:name"
			command.Parameters.Add(SQLiteParameter('name', hgx.Encounters.PlayerCharacter))
			command.Parameters.Add(SQLiteParameter('playername', player_name))
			command.Parameters.Add(SQLiteParameter('cd_key', cd_key))
			command.Parameters.Add(SQLiteParameter('ip', ip))
			command.Parameters.Add(SQLiteParameter('level', level))
			command.Parameters.Add(SQLiteParameter('deity', deity))
			command.Parameters.Add(SQLiteParameter('xp', xp))
			command.Parameters.Add(SQLiteParameter('xp_tnl', xp_tnl))
			command.Parameters.Add(SQLiteParameter('subrace', subrace))
			rows_affected = command.ExecuteNonQuery()

			if rows_affected==0:
				command.CommandText = "INSERT INTO tags (name, playername, cd_key, ip, level, xp, xp_tnl, deity, subrace) VALUES (:name, :playername, :cd_key, :ip, :level, :xp, :xp_tnl, :deity, :subrace)"
				command.Parameters.Add(SQLiteParameter('name', hgx.Encounters.PlayerCharacter))
				command.Parameters.Add(SQLiteParameter('playername', player_name))
				command.Parameters.Add(SQLiteParameter('cd_key', cd_key))
				command.Parameters.Add(SQLiteParameter('ip', ip))
				command.Parameters.Add(SQLiteParameter('level', level))
				command.Parameters.Add(SQLiteParameter('deity', deity))
				command.Parameters.Add(SQLiteParameter('xp', xp))
				command.Parameters.Add(SQLiteParameter('xp_tnl', xp_tnl))
				command.Parameters.Add(SQLiteParameter('subrace', subrace))
				command.ExecuteNonQuery()

			command.Dispose()

	except SQLiteException, e:
		logger.Error ("update_playerinfo() - SQlite Error: {0}", e.Message)

	finally:
		if flush:
			trans.Commit()
			trans.Dispose()
		if debug:
			logger.Info("update_playerinfo() - After closing connection")
	endtime = clock()
	elapsed = endtime - starttime
	if verbose:
		logger.Info ("UPDATING playerinfo done - elapsed time: {0}", seconds_to_str(elapsed))


def on_lineread(sender, e):

	global commands_deferred

	#Salek's Last D: I am ready to face my destiny. No one knows what the future holds, but my time is at an end. Let my spirit pass to a new generation.

	# Handle a few delete character events automatic
	# Reincarnation
	if ": I am ready to face my destiny. No one knows what the future holds, but my time is at an end. Let my spirit pass to a new generation." in e.Line:
		res = re.search(r"(.+):", e.Line)
		if res:
			to_delete = res.group(1)
			logger.Info ("scheduled for delete *{0}*", to_delete)
			delete (to_delete)
		return

	# Delete at Rowan's Guardian
	if ": Bottoms up!" in e.Line:
		res = re.search(r"(.+):", e.Line)
		if res:
			to_delete = res.group(1)
			logger.Info ("scheduled for delete *{0}*", to_delete)
			delete (to_delete)
		return

	# Using !delete command
	if "Deletion confirmed! Character will be booted for deletion momentarily." in e.Line:
		if hgx.Encounters.PlayerCharacter is not None:
			if "[test]" not in hgx.Encounters.PlayerCharacter.lower():
				to_delete = hgx.Encounters.PlayerCharacter
				logger.Info ("scheduled for delete *{0}*", to_delete)
				delete (to_delete)
		return

#-------------------------------------------------------------------------------------------------------------------------
	# deferred_commands: defer commands until player hide acquired
	if 'Acquired Item: Player Hide' in e.Line and commands_deferred:
		commands_deferred = False
		hgx.Messages.Chat('/t "{0}" !playerinfo'.format(hgx.Encounters.PlayerCharacter))
		hgx.Messages.Chat("!list acc")
		hgx.Messages.Chat("!list acc prell")
		return

#-------------------------------------------------------------------------------------------------------------------------
	if 'Player Information:' in e.Line:
		player_name = ""
		cd_key = ""
		ip = ""
		level = 0
		xp = 0
		xp_tnl = 0
		deity = ""
		subrace = ""
		starttime = clock()
		for single_line in e.Line.split("\n"):
			line = single_line.strip()
			if len (line) > 0:
				#result = playerinfo_pattern.search(line)
				#if result:
				#	playerinfo_key, playerinfo_value = result.groups()
				splits = line.split(': ',1)
				if len(splits) > 1:
					playerinfo_key = splits[0]
					playerinfo_value = splits[1]
					if verbose:
						logger.Info ("Key *{0}* Value: *{1}*", playerinfo_key, playerinfo_value)
					if playerinfo_key == "Playername":
						player_name = playerinfo_value
					elif playerinfo_key == "CD Key":
						cd_key = playerinfo_value
					elif playerinfo_key == "IP":
						ip = playerinfo_value
					elif playerinfo_key == "Classes":
						pass
						# res = re.search("Total Levels: (\d*)", playerinfo_value)
						# if res:
						# level = int(res.group(1))
						# if verbose:
							# logger.Info ("scanned *{0}* result: {1}", playerinfo_value, level)
					elif playerinfo_key == "Experience":
						xp = int(playerinfo_value)
					elif playerinfo_key == "Experience Needed for Next Level":
						xp_tnl = int(playerinfo_value)
					elif playerinfo_key == "Area":
						pass
					elif playerinfo_key == "Party":
						res = re.search(r"(.+) \[Level (\d+)\]", playerinfo_value)
						if res:
							p_name, p_level = res.groups()
							if p_name == hgx.Encounters.PlayerCharacter:
								if p_level is not None and p_level.isdigit():
									level = int(p_level)
					elif playerinfo_key == "Deity":
						deity = playerinfo_value
					elif playerinfo_key == "Subrace":
						subrace = playerinfo_value
					elif playerinfo_key == "Gold":
						pass
					elif playerinfo_key == "Gold + Inventory Value":
						pass
		endtime = clock()
		elapsed = endtime - starttime
		if verbose:
			hgx.Messages.Show("Processing playerinfo done in {0}.", seconds_to_str(elapsed))
			logger.Info("Player info collected: {0}, {1}, {2}, {3}, {4} in {5}.", player_name, cd_key, xp, xp_tnl, subrace, seconds_to_str(elapsed))
		update_playerinfo(player_name, cd_key, ip, level, xp, xp_tnl, deity, subrace)
		return

#-------------------------------------------------------------------------------------------------------------------------
	if 'You have the following accomplishments:' in e.Line:
		accomplishment_LL_runs = False
		demi = 0
		pelor = False
		pazuzu = False
		pazunia = False
		tome = False
		pandect = False
		bitmap_LL = 0
		bitmap_preLL = 0
		bitmap_limbo = 0
		all_pre_LL = False
		prince_wins = ""
		bitmap_abyss_tags = 0
		bitmap_hell_tags = 0
		starttime = clock()
		for single_line in e.Line.split("\n"):
			line = single_line.strip()
			#logger.Info ("Line: *{0}*", line)

			# If next line is discovered the 
			if "(Use '!list acc preLL' to list pre-legendary accomplishments)" in line:
				accomplishment_LL_runs = True

			# process pre LL runs
			if line in lookup_table_accomplishments_pre_legendary:
				bitmap_preLL |= (1 << accomplishments_text_pre_legendary.index(line))
				continue

			# process LL runs
			if line in lookup_table_accomplishments_legendary:
				bitmap_LL |= (1 << accomplishments_text_legendary.index(line))
				continue

			# process limbo runs
			if line in lookup_table_accomplishments_limbo:
				bitmap_limbo |= (1 << accomplishments_text_limbo.index(line))
				continue

			if "You have earned all pre-legendary accomplishments." in line:
				all_pre_LL = True
				continue

			# tome
			if "You have studied a Wondrous Tome of Ancient Lore." in line:
				tome = True
				continue

			# pandect
			if "You have studied a Pandect of Darkest Secrets." in line:
				pandect = True
				continue

			#abyss tags
			#old:
			#if any(word in line for word in abyss_tags_handled):
			#faster this way (?)
			found = False
			for word in abyss_tags_handled:
				if word in line:
					found = True
					break
			if found:
				sentences = delimiter_pattern.split(line)
				for sentence in sentences:
					#logger.Info ("Sentence: *{0}*", sentence)
					abyss_tags = tag_pattern.findall(sentence)
					if len(abyss_tags) > 0:
						for bitpos in (abyss_tags_known.index(tag) for tag in abyss_tags if tag in abyss_tags_known):
							bitmap_abyss_tags |= (1 << bitpos)
				if verbose:
					logger.Info ("abyss bitmap: *{0}*", bin(bitmap_abyss_tags))
				if "Pazuzu" in line:
					pazuzu = True
				if "You have brought the Wand of Orcus to Pelor." in line:
					pelor = True
				prince_wins = re.findall(" (\S+) \(as Prince", line)
				if prince_wins:
					prince_wins.sort()
				continue

			#hell tags and demi iteration
			#if any(word in line for word in hell_tags_handled):
			found = False
			for word in hell_tags_handled:
				if word in line:
					found = True
					break
			if found:
				sentences = delimiter_pattern.split(line)
				for sentence in sentences:
					if debug:
						logger.Info ("Hell Sentence: *{0}*", sentence)
					hell_tags = tag_pattern.findall(sentence)
					if len(hell_tags) > 0:
						# Handling Asmodeus is way to ugly for a single regex: twice, thrice, 4 times and so on
						if "Asmodeus" in sentence:
							hell_tags.append("Asmodeus")
							if "and Asmodeus." in sentence:
								demi = 1
							else:
								result = re.findall("Asmodeus (\w+)(?: times)?\.$", sentence)
								if result:
									if result[0] == "twice":
										demi = 2
									elif result[0] == "thrice":
										demi = 3
									elif result[0].isdigit():
										demi = int(result[0])
						for bitpos in (hell_tags_known.index(tag) for tag in hell_tags if tag in hell_tags_known):
							bitmap_hell_tags |= (1 << bitpos)
				if verbose:
					logger.Info ("hell bitmap: *{0}*", bin(bitmap_hell_tags))
				continue

		# accomplishments done at this point
		endtime = clock()
		elapsed = endtime - starttime
		if accomplishment_LL_runs:
			if verbose:
				logger.Info ("Processing LL accomplishments done in {0}", seconds_to_str(elapsed))
				hgx.Messages.Show("Processing LL accomplishments done in {0}.", seconds_to_str(elapsed))
			update_accomplishments (prince_wins, demi, pelor, pazuzu, bitmap_LL, bitmap_abyss_tags, bitmap_hell_tags, bitmap_limbo, tome, pandect, True)
		else:
			if verbose:
				logger.Info ("Processing pre LL accomplishments done in {0}", seconds_to_str(elapsed))
				hgx.Messages.Show("Processing pre LL accomplishments done in {0}.", seconds_to_str(elapsed))
			update_accomplishments_preLL (bitmap_preLL, all_pre_LL, True)
		return

#-------------------------------------------------------------------------------------------------------------------------
	if 'You are tagged up to ' in e.Line:
		hgx.Messages.Show("Skull used.")
		#ONLY these variables are used and updated
		hell_layer = ""
		abyss_runs = {}
		flag_pazunia = False

		for single_line in e.Line.split("\n"):
			line = single_line.strip()

			result = re.match(r"^You are tagged up to (\w+)", line)
			if result:
				hell_layer = result.group(1)
				continue

			if line == 'You can visit Pazunia in the Abyss.':
				flag_pazunia = True
				continue

			result = re.match(r"^You have attuned to the (\w+) portal in (.+)\.", line)
			if result:
				portal, run = result.groups()
				abyss_runs[run] = 1 if portal=="first" else 2
				continue

			result = re.match(r"^You have acquired a Wand fragment from (.+)\.", line)
			if result:
				abyss_boss = result.group(1)
				abyss_runs[map_abyss_boss_to_run[abyss_boss]] = 3
				continue

		#save/update collected character info into sqlite db
		update_player (abyss_runs, hell_layer, flag_pazunia, True)

		return


def list_hell_layer(parameter):

	sql = '''select name, layer, demi_count from tags
	order by
	 case layer
	 when "Avernus" then 1
	 when "Dis" then 2
	 when "Minauron" then 3
	 when "Phlegethos" then 4
	 when "Stygia" then 5
	 when "Malbolge" then 6
	 when "Maladomini" then 7
	 when "Cania" then 8
	 when "Nessus" then 9
	 else 0
	 end
	'''

	characters_found = 0
	out_msg = ''

	try:
		if overlay_available and output_to_overlay_enabled:
			output_template = "{0}x\t{1}\t{2}\n"
			tabs = [40, 250]
			width = 450
		else:
			output_template = "  {0}x {1}: {2}\n"
			tabs = None
			width = None

		with db_connection.CreateCommand() as command:
			command.CommandText = sql
			with command.ExecuteReader() as reader:
				while reader.Read():
					out_msg += output_template.format(reader['demi_count'],reader['name'], reader['layer'])
					characters_found += 1
		display_result ("Next hell layer needed:", out_msg, characters_found, tabs, width, None)
	except SQLiteException, e:
		logger.Error ("list_hell_layer() - SQlite Error: {0}", e.Message)


def list_abyss_tags(parameter):
	sql = '''Select name,
	GROUP_CONCAT(a.run || ' ' || a.part) as parts_done,
	(select count (b.part) from abyss b where b.tags_id=a.tags_id and b.part=3) as wands
	from abyss a
	join tags on tags.id=tags_id
	group by name
	order by name, run
	'''

	characters_found = 0
	out_msg = ''

	try:
		runs_sorted = sorted(display_abyss_run_as.values())
		if overlay_available and output_to_overlay_enabled:
			output_template = " {0}\t{1}\t{2}\n"
			tabs = [20, 200, 70, 70, 70, 70, 70]
			width = 580
		else:
			output_template = "  {0} {1}: {2}\n"
			tabs = None
			width = None
		with db_connection.CreateCommand() as command:
			command.CommandText = sql
			with command.ExecuteReader() as reader:
				while reader.Read():
					parts = reader['parts_done']
					parts = [x.strip() for x in parts.split(',')]
					parts.sort()
					parts_shortened = [x.replace(x[:-2],display_abyss_run_as[x[:-2]]) for x in parts]
					parts_as_table = [next((z for z in parts_shortened if z.startswith(x)), None) if any(y.startswith(x) for y in parts_shortened) else "" for x in runs_sorted]
					if overlay_available and output_to_overlay_enabled:
						out_msg += output_template.format((" ", "x")[reader['wands']==5], reader['name'], '\t'.join(parts_as_table))
					else:
						out_msg += output_template.format((" ", "x")[reader['wands']==5], reader['name'], ', '.join(parts_shortened))
					characters_found += 1
		display_result ("Abyss parts finished:", out_msg, characters_found, tabs, width)
	except SQLiteException, e:
		logger.Error ("list_abyss_tags() - SQlite Error: {0}", e.Message)


def list_prince_wins(parameter):
	sql = '''SELECT name, prince_wins, pelor FROM tags WHERE prince_wins IS NOT NULL and prince_wins <> '' or pelor <> 0 order by name
	'''

	characters_found = 0
	out_msg = ''

	try:
		if overlay_available and output_to_overlay_enabled:
			output_template = "{0}:\t{1} {2}\n"
			tabs = [250]
			width = 450
		else:
			output_template = "  {0}: {1} {2}\n"
			tabs = None
			width = None
		with db_connection.CreateCommand() as command:
			command.CommandText = sql
			with command.ExecuteReader() as reader:
				while reader.Read():
					out_msg += output_template.format(reader['name'], reader['prince_wins'] if reader['prince_wins'] != DBNull.Value else "NONE", ("", " Pelor")[reader['pelor']])
					characters_found += 1
		display_result ("Prince wins:", out_msg, characters_found, tabs, width)
	except SQLiteException, e:
		logger.Error ("list_prince_wins() - SQlite Error: {0}", e.Message)


def list_pandects (parameter):

	sql = '''SELECT name FROM tags WHERE pandect > 0 order by name
	'''

	characters_found = 0
	out_msg = ''

	try:
		tabs = None
		width = 200
		with db_connection.CreateCommand() as command:
			command.CommandText = sql
			with command.ExecuteReader() as reader:
				while reader.Read():
					out_msg += "  {0}\n".format(reader['name'])
					characters_found += 1
		display_result ("Characters used a pandect:", out_msg, characters_found, tabs, width)
	except SQLiteException, e:
		logger.Error ("list_pandects() - SQlite Error: {0}", e.Message)


def list_tomes (parameter):

	sql = '''SELECT name FROM tags WHERE TOME > 0 order by name
	'''

	characters_found = 0
	out_msg = ''

	try:
		tabs = None
		width = 200
		with db_connection.CreateCommand() as command:
			command.CommandText = sql
			with command.ExecuteReader() as reader:
				while reader.Read():
					out_msg += "  {0}\n".format(reader['name'])
					characters_found += 1
		display_result ("Characters used a tome:", out_msg, characters_found, tabs, width)
	except SQLiteException, e:
		logger.Error ("list_tome() - SQlite Error: {0}", e.Message)


def list_limbo (parameter):

	sql = '''SELECT name FROM tags WHERE TOME > 0 order by name
	'''

	characters_found = 0
	out_msg = ''

	try:
		tabs = None
		width = 200
		with db_connection.CreateCommand() as command:
			command.CommandText = sql
			with command.ExecuteReader() as reader:
				while reader.Read():
					out_msg += "  {0}\n".format(reader['name'])
					characters_found += 1
		display_result ("Characters which finished limbo:", out_msg, characters_found, tabs, width)
	except SQLiteException, e:
		logger.Error ("list_limbo() - SQlite Error: {0}", e.Message)


def list_subraces (parameter):

	sql = '''SELECT name, subrace FROM tags WHERE subrace IS NOT NULL or subrace != '' order by subrace
	'''

	characters_found = 0
	out_msg = ''

	try:
		if overlay_available and output_to_overlay_enabled:
			out_msg = "Subrace\tName\n"
			output_template = "{0}:\t{1}\n"
			tabs = [180, 220]
			width = 350
		else:
			out_msg = ''
			output_template = "  {0:<18s}: {1}\n"
			tabs = None
			width = None
		logger.Info("Message header *{0}*", out_msg)
		with db_connection.CreateCommand() as command:
			command.CommandText = sql
			with command.ExecuteReader() as reader:
				while reader.Read():
					out_msg += output_template.format(reader['subrace'], reader['name'])
					characters_found += 1
		logger.Info("Message header *{0}*", out_msg)
		display_result ("Characters by subrace:", out_msg, characters_found, tabs, width)
	except SQLiteException, e:
		logger.Error ("list_subrace() - SQlite Error: {0}", e.Message)


def list_proxy_needed (parameter):

	sql = '''SELECT name FROM tags WHERE all_pre_LL == 0 order by name
	'''

	characters_found = 0

	try:
		if overlay_available and output_to_overlay_enabled:
			out_msg = "Name\n"
			output_template = "  {0}\n"
			tabs = [200]
			width = 350
		else:
			out_msg = ''
			output_template = "  {0}\n"
			tabs = None
			width = None
		with db_connection.CreateCommand() as command:
			command.CommandText = sql
			with command.ExecuteReader() as reader:
				while reader.Read():
					out_msg += output_template.format(reader['name'])
					characters_found += 1
		display_result ("Characters missing pre LL tags:", out_msg, characters_found, tabs, width)
	except SQLiteException, e:
		logger.Error ("list_proxy_needed() - SQlite Error: {0}", e.Message)


def list_tag (search_tag):
	'''
	search tag - search order is: normal accomplishment, pre LL, abyss, hell
	reporting tags for first matching group
	list those which don't have that tag
	'''
	characters_found = 0
	out_msg = ''

	if any(search_tag in t for t in tags):
		sql = 'select name from tags where tags_LL&:bitMask == 0 order by name'
		bitMask = sum([1<<tags[x] for x in[elem for i,elem in enumerate(tags) if search_tag in elem]])
		tags_processed = ', '.join([x for x in[elem for i,elem in enumerate(tags) if search_tag in elem]])
	elif any(search_tag in t for t in search_tags_preLL):
		sql = 'select name from tags where tags_preLL&:bitMask == 0 order by name'
		bitMask = sum([1<<search_tags_preLL[x] for x in[elem for i,elem in enumerate(search_tags_preLL) if search_tag in elem]])
		tags_processed = ', '.join([x for x in[elem for i,elem in enumerate(search_tags_preLL) if search_tag in elem]])
	elif any(search_tag in t.lower() for t in abyss_tags_known):
		sql = 'select name from tags where tags_abyss&:bitMask == 0 order by name'
		bitMask = sum([1<<x for x in[i for i,elem in enumerate(abyss_tags_known) if search_tag in elem.lower()]])
		tags_processed = ', '.join([x for x in[elem for i,elem in enumerate(abyss_tags_known) if search_tag in elem.lower()]])
	elif any(search_tag in t.lower() for t in hell_tags_known):
		sql = 'select name from tags where tags_hell&:bitMask == 0 order by name'
		bitMask = sum([1<<x for x in[i for i,elem in enumerate(hell_tags_known) if search_tag in elem.lower()]])
		tags_processed = ', '.join([x for x in[elem for i,elem in enumerate(hell_tags_known) if search_tag in elem.lower()]])
	elif any(search_tag in t.lower() for t in limbo_tags_known):
		sql = 'select name from tags where tags_limbo&:bitMask == 0 order by name'
		bitMask = sum([1<<x for x in[i for i,elem in enumerate(limbo_tags_known) if search_tag in elem.lower()]])
		tags_processed = ', '.join([x for x in[elem for i,elem in enumerate(limbo_tags_known) if search_tag in elem.lower()]])
	else:
		hgx.Messages.Show ("*{0}* not found in tags.", search_tag)
		return

	try:
		with db_connection.CreateCommand() as command:
			command.CommandText = sql
			command.Parameters.Add(SQLiteParameter('bitMask', bitMask))
			with command.ExecuteReader() as reader:
				while reader.Read():
					out_msg += "  {0}\n".format(reader['name'])
					characters_found += 1
			display_result ("Characters found in need of *{0}*:".format(tags_processed), out_msg, characters_found)
	except SQLiteException, e:
		logger.Error ("list_tag() - SQlite Error: {0}", e.Message)


def display_result (title, result, characters_found, tabs = [100, 100, 100, 100], width = None, alignments = None, button_table = None):

	if overlay_available and output_to_overlay_enabled:
		user_overlay.clear_messages()
		user_overlay.title = title
		user_overlay.set_tabs(tabs)
		user_overlay.set_max_width(width)
		user_overlay.set_tabs_alignments(alignments)
		for line in result.split("\n"):
			user_overlay.WriteString(line)
		user_overlay.bottom_info = "{0} character{1} found - created at: {2}".format(characters_found, ("s", "")[characters_found == 1], time.strftime("%X"))
		user_overlay.set_buttons (button_table)
		user_overlay.Visible = True
	else:
		hgx.Messages.Show("\n{0}\n<color=ffffff>{1}</color>{2} character{3} found.", title, result, characters_found, ("s", "")[characters_found == 1])


def delete (parameter):

	name = parameter
	try:
		command = db_connection.CreateCommand()
		command.CommandText = "DELETE from tags where name = :name"
		command.Parameters.Add(SQLiteParameter('name', name))
		affected_rows = command.ExecuteNonQuery()
	except SQLiteException, e:
		logger.Error ("delete character() - SQlite Error: {0}", e.Message)
	finally:
		command.Dispose()
		if affected_rows > 0:
			hgx.Messages.Show("*{0}* deleted.", name)
		else:
			hgx.Messages.Show("*{0}* not found.", name)


def list_xp (parameter):

	sql = '''SELECT name, xp, xp_tnl, level FROM tags where xp <> 0 order by xp desc
	'''

	characters_found = 0

	try:
		if overlay_available and output_to_overlay_enabled:
			out_msg = "Lvl\tXP\tXP tnl\tName\n"
			output_template = "{0:>2s}\t{1}\t{2}\t{3}\n"
			tabs = [30, 90, 80, 20]
			width = 450
			alignments = [System.Drawing.StringAlignment.Far,
						System.Drawing.StringAlignment.Far,
						System.Drawing.StringAlignment.Far,
						System.Drawing.StringAlignment.Near,
						]
		else:
			out_msg = ''
			output_template = "  L{0:>2s} {1:>13s} / {2:<10s} {3}\n"
			tabs = None
			width = None
			alignments = None
		with db_connection.CreateCommand() as command:
			command.CommandText = sql
			with command.ExecuteReader() as reader:
				while reader.Read():
					out_msg += output_template.format(str(reader['level']), locale.format("%d", reader['xp'], grouping=True), locale.format("%d", reader['xp_tnl'], grouping=True), reader['name'])
					characters_found += 1
		display_result ("Characters by xp", out_msg, characters_found, tabs, width, alignments)
	except SQLiteException, e:
		logger.Error ("list_xp() - SQlite Error: {0}", e.Message)


def list_level (parameter):

	sql = '''SELECT name, level FROM tags where level <> 0 order by level desc
	'''

	characters_found = 0
	if overlay_available and output_to_overlay_enabled:
		out_msg = "Lvl\tName\n"
		output_template = "{0}\t{1}\n"
		tabs = [30]
		width = 350
	else:
		out_msg = ''
		output_template = "  {0:>4s} / {1}\n"
		tabs = None
		width = None

	try:
		with db_connection.CreateCommand() as command:
			command.CommandText = sql
			with command.ExecuteReader() as reader:
				while reader.Read():
					out_msg += output_template.format(locale.format("%d", reader['level']), reader['name'])
					characters_found += 1
		display_result ("Characters by level", out_msg, characters_found, tabs, width)
	except SQLiteException, e:
		logger.Error ("list_level() - SQlite Error: {0}", e.Message)


def list_time_accessed (parameter):

	sql = '''SELECT name, cast(cast((strftime('%s',datetime('now')) - strftime('%s', last_update)) as real)/60/60/24 as integer) as elapsed FROM tags order by elapsed desc, name asc
	'''

	characters_found = 0
	if overlay_available and output_to_overlay_enabled:
		out_msg = "Days\tName\n"
		output_template = "{0}\t{1}\n"
		tabs = [30]
		width = 350
	else:
		out_msg = ''
		output_template = "  {0:>5s} {1}\n"
		tabs = None
		width = None

	try:
		with db_connection.CreateCommand() as command:
			command.CommandText = sql
			with command.ExecuteReader() as reader:
				while reader.Read():
					out_msg += output_template.format(locale.format("%d", reader['elapsed']), reader['name'])
					characters_found += 1
		display_result ("Characters by last time played:", out_msg, characters_found, tabs, width)
	except SQLiteException, e:
		logger.Error ("list_time_accessed() - SQlite Error: {0}", e.Message)


def toggle_overlay (parameter):

	global output_to_overlay_enabled

	output_to_overlay_enabled = not output_to_overlay_enabled
	hgx.Settings.SetValue("UserData.{0}.output_to_overlay_enabled".format(module_name), output_to_overlay_enabled)
	hgx.Messages.Show("Output to overlay: {0}", ("OFF", "ON")[output_to_overlay_enabled])


def toggle_multi (parameter):

	global multiple_accounts

	multiple_accounts = not multiple_accounts
	hgx.Settings.SetValue("UserData.{0}.multiple_accounts".format(module_name), multiple_accounts)
	hgx.Messages.Show("Multiple accounts: {0}", ("OFF", "ON")[multiple_accounts])


def toggle_verbose (parameter):

	global verbose

	verbose = not verbose
	hgx.Settings.SetValue("UserData.{0}.verbose".format(module_name), verbose)
	hgx.Messages.Show("Verbose: {0}", ("OFF", "ON")[verbose])


def list_version(parameter):

	version_minor = re.findall('Rev: (\d*)', __version__)
	complete_version = float(module_version) + float(version_minor[0])/1000
	hgx.Messages.Show("{0} - version: {1:.3f}, multiple accounts: {2}".format(module_name, complete_version, ("OFF", "ON")[multiple_accounts]))


def help(parameter):

	if len(parameter) > 0:
		hgx.Messages.Show("Help for {0}:", parameter)
		#split on first space, lookup word in dispatch table and display correspondiong help text
		cmd = parameter.split(' ',1)
		if cmd[0] in dispatch_table:
			hgx.Messages.Show("\n<color=a1ff42>{0}</color>", dispatch_table[cmd[0]][1])
		else:
			hgx.Messages.Show("Help for command *{0}* not found.", cmd[0])


def command_handler (sender, e):

	if e.Command.lower().startswith(("characterinfo", "ci")):
		if e.Parameters:
			sub_command = e.Parameters[0]
			if sub_command.startswith("*"):
				list_tag (sub_command[1:].lower())
			else:
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
			hgx.Messages.Show(usage)


def send_commands():

	hgx.Messages.Chat('/t "{0}" !playerinfo'.format(hgx.Encounters.PlayerCharacter))
	hgx.Messages.Chat("!list acc")
	hgx.Messages.Chat("!list acc prell")
	#Next command is not implemented
	#hgx.Messages.Chat("!list skull")


def on_playerchanged(sender, e):

	global commands_deferred

	if "[test]" not in hgx.Encounters.PlayerCharacter.lower():
		if deferred_commands:
			commands_deferred = True
		elif delayed_commands:
			threading.Timer (delay_by, send_commands).start()
		else:
			send_commands()


if __name__ == "__main__":

	dispatch_table = {
		'hell':		(list_hell_layer,			'List characters and hell layer they need next'),
		'abyss':	(list_abyss_tags,			'List abyss parts finished\nAn asterisk marks a character ready for a prince or pelor fight'),
		'prince':	(list_prince_wins,			'All characters with a prince win'),
		'pandects':	(list_pandects,				'All characters which have used a pandect.'),
		'tomes':	(list_tomes,				'All characters which have read a tome'),
		'limbo':	(list_limbo,				'In 3 days'),
		'proxy':	(list_proxy_needed,			'Characters in need of a proxy to get all pre LL tags'),
		'subs':		(list_subraces,				'Display characters sorted by subrace used'),
		'xp':		(list_xp,					'List characters sorted by xp\nAlso lists level and xp needed for next level'),
		'delete':	(delete,					'Delete character with given name'),
		'overlay':	(toggle_overlay,			'Toggle alternative output to a separate overlay. (NOT IN YET)'),
		'multi':	(toggle_multi,				'Toggle support for mulitple accounts\nNo real effect yet.'),
		'verbose':	(toggle_verbose,			'Toggles script to be more/less verbose'),
		'level':	(list_level,				'List characters by level'),
		'help':		(help,						'help!'),
		'time':		(list_time_accessed,		'Last time a character was played(in days)'),
		'version':	(list_version,				'Display version')
		}

	tag_pattern = re.compile (r"(?:You have defeated |, )?(.*?)(?: \(as Prince of Demons\))?(?=,|\.)")
	delimiter_pattern = re.compile (r"[\.\?!](?=[\s])")

	# next regex is buggy, a split on first ', ' does the job for now
	#playerinfo_pattern = re.compile (r"(.*): (.*)")

	# create a few tables to make lookups faster
	lookup_table_accomplishments_pre_legendary = frozenset(accomplishments_text_pre_legendary)
	lookup_table_accomplishments_legendary = frozenset(accomplishments_text_legendary)
	lookup_table_accomplishments_limbo = frozenset(accomplishments_text_limbo)

	#  setup persistant variables
	output_to_overlay_enabled = hgx.Settings.GetBool("UserData.{0}.output_to_overlay_enabled".format(module_name))
	if output_to_overlay_enabled is None:
		output_to_overlay_enabled = output_to_overlay_enabled_default
		hgx.Settings.SetValue("UserData.{0}.output_to_overlay_enabled".format(module_name), output_to_overlay_enabled)

	multiple_accounts = hgx.Settings.GetBool("UserData.{0}.multiple_accounts".format(module_name))
	if multiple_accounts is None:
		multiple_accounts = multiple_accounts_default
		hgx.Settings.SetValue("UserData.{0}.multiple_accounts".format(module_name), multiple_accounts)

	verbose = hgx.Settings.GetBool("UserData.{0}.verbose".format(module_name))
	if verbose is None:
		verbose = verbose_default
		hgx.Settings.SetValue("UserData.{0}.verbose".format(module_name), verbose)

	deferred_commands = hgx.Settings.GetBool("UserData.{0}.deferred_commands".format(module_name))
	if deferred_commands is None:
		deferred_commands = deferred_commands_default
		hgx.Settings.SetValue("UserData.{0}.deferred_commands".format(module_name), deferred_commands)

	delayed_commands = hgx.Settings.GetBool("UserData.{0}.delayed_commands".format(module_name))
	if delayed_commands is None:
		delayed_commands = delayed_commands_default
		hgx.Settings.SetValue("UserData.{0}.delayed_commands".format(module_name), delayed_commands)

	delay_by = hgx.Settings.GetInt("UserData.{0}.delay_by".format(module_name))
	if delay_by is None:
		delay_by = delay_by_default
		hgx.Settings.SetValue("UserData.{0}.delay_by".format(module_name), delay_by)

	overlay_status_str = ("OFF", "ON")[output_to_overlay_enabled] if overlay_available else "Not available"
	usage = "Usage: #ct {0}\nSearch for tag: #ct *TAGNAME\nDelete character: #ct del NAME\n Output to overlay: {1}".format(' | '.join(sorted(dispatch_table)), overlay_status_str)

	create_db_tables()

	if db_connection is None:
		try:
			db_connection = SQLiteConnection(sqlite_connection_string)
			db_connection.Open()
		except SQLiteException, e:
			logger.Error ("enable_tracker() - SQlite Error: {0}", e.Message)
			logger.Error ("{0} disabled.", module_name)
		else:
			if verbose:
				logger.Info("character db() - connection opened")
			hgx.Encounters.PlayerChanged += on_playerchanged
			hgx.UserEvents.ChatCommand += command_handler
			hgx.GameEvents.LogEntryRead += on_lineread

			if overlay_available:
				user_overlay = UserOverlay(hgx)

			if add_module_info:
				add_module_info (module_name, module_version, __version__)
