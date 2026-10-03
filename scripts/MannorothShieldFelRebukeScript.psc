Scriptname MannorothShieldFelRebukeScript extends ActiveMagicEffect
{Blocking a melee attack can engulf the attacker in fel fire.}

Spell Property FelRebukeSpell Auto
Faction Property DGIntimidateFaction Auto
Float Property ProcChance = 0.6 Auto
Float Property Cooldown = 3.0 Auto

Actor Wearer

Event OnEffectStart(Actor akTarget, Actor akCaster)
	Wearer = akTarget
EndEvent

Event OnHit(ObjectReference akAggressor, Form akSource, Projectile akProjectile, Bool abPowerAttack, Bool abSneakAttack, Bool abBashAttack, Bool abHitBlocked)
	If !abHitBlocked || akProjectile || (akSource && !(akSource as Weapon))
		Return
	EndIf
	Actor attacker = akAggressor as Actor
	If !attacker || !Wearer || attacker == Wearer || attacker.IsDead()
		Return
	EndIf
	If attacker.IsInFaction(DGIntimidateFaction) || !attacker.IsHostileToActor(Wearer)
		Return
	EndIf
	If Utility.RandomFloat() >= ProcChance
		Return
	EndIf
	GoToState("Cooldown")
	FelRebukeSpell.Cast(Wearer, attacker)
	RegisterForSingleUpdate(Cooldown)
EndEvent

Event OnUpdate()
	GoToState("")
EndEvent

State Cooldown
	Event OnHit(ObjectReference akAggressor, Form akSource, Projectile akProjectile, Bool abPowerAttack, Bool abSneakAttack, Bool abBashAttack, Bool abHitBlocked)
	EndEvent
EndState
