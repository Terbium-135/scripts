import hgx

import System.Drawing

import Hgx.Modules
import NLog

from Hgx.Core import AttackMode

CHARACTERS_TO_WATCH = ["Salek's Really Last BK", "Salek's Last Rogue"]

logger = NLog.LogManager.GetLogger(__file__)
active = False
visible = False
sneak = None
info_area = None

class SneakInformation(Hgx.Modules.IInformation):
	__metaclass__ = hgx.clrtype.ClrClass
	
	PriorityAttribute = hgx.clrtype.attribute(Hgx.Modules.InformationPriorityAttribute)
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
		g.DrawString(
			"Sneak",
			System.Drawing.Font(System.Drawing.SystemFonts.DefaultFont.FontFamily.Name, 10, System.Drawing.FontStyle.Bold),
#			System.Drawing.SystemFonts.DefaultFont,
			System.Drawing.Brushes.Red,
			0, 0)
		
	def CompareTo(self, other):
		if other is SneakInformation:
			return 0
		else:
			return -1

def on_playerchanged(sender, e):
	'''Check for a character to display if it's doing sneak attacks'''
	global active

	if hgx.Encounters.PlayerCharacter in CHARACTERS_TO_WATCH:
		active = True
	else:
		info_area.Remove(sneak)
		active = False

def on_attacked(sender, e):
	'''
	[Flags]
    public enum AttackMode
    {
        None = 0,
        SneakAttack = 1 << 0,
        DeathAttack = 1 << 1,
        OffHand = 1 << 2,
        AttackOfOpportunity = 1 << 3,
        Expertise = 1 << 4,
        ImprovedExpertise = 1 << 5,
        PowerAttack = 1 << 6,
        ImprovedPowerAttack = 1 << 7,
        FlurryOfBlows = 1 << 8,
        RapidShot = 1 << 9,
        DefensiveStance = 1 << 10,
        Cleave = 1 << 11,
        DirtyFighting = 1 << 12
    }

    public enum HitType
    {
        None = 0,
        Miss = 1,
        TargetConcealed = 2,
        Parried = 3,
        Hit = 4,
        CriticalAttempt = 5,
        CriticalHit = 6
    }

    public sealed class AttackEventArgs : ParseEventArgs
    {
        public AttackEventArgs(DateTime timestamp)
            : base(timestamp)
        {
        }

        public string Attacker { get; set; }
        public string Defender { get; set; }
        public AttackMode AttackMode { get; set; }
        public HitType HitType { get; set; }
        public double Concealment { get; set; }
        public int AttackBonus { get; set; }
        public int Roll { get; set; }
        public int? ThreatRoll { get; set; }
    }

	So these EventArgs are available in IronPython as e.Attacker, e. Defender...
	'''

	global visible
	
	if active:
		if e.AttackMode & AttackMode.SneakAttack:
			if visible:
				info_area.Remove(sneak)
				visible = False
		else:
			if not visible:
				info_area.Add(sneak)
				visible = True

if __name__ == "__main__":
	info_area = hgx.ServiceLocator.Current.GetInstance[Hgx.Modules.InformationOverlay]()
	sneak = SneakInformation()
				
	hgx.Encounters.PlayerChanged += on_playerchanged

	# subscribe to the attack event
	hgx.GameEvents.Attacked += on_attacked

