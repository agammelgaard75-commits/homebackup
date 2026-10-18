"""Short, verified Player Core condition summaries. Full text lives at AoN."""

# name, page, AoN ID, valued, summary, penalty/restriction, usual ending/reminder
ROWS = [
    ("Broken", 442, 60, False, "An item is damaged past its Broken Threshold.", "It usually cannot be used for its normal function. Broken armor has special AC penalties.", "Repair the item or follow its rules."),
    ("Blinded", 442, 59, False, "You cannot see.", "Vision-based Perception checks critically fail; normal terrain is difficult terrain. If vision is your only precise sense, –4 status to Perception.", "Ends when the causing effect ends; overrides Dazzled."),
    ("Clumsy", 442, 61, True, "Your coordination is impaired.", "Status penalty equal to value on Dexterity-based rolls and DCs, including AC and Reflex.", "Follow the causing effect."),
    ("Concealed", 442, 62, False, "Some creatures have trouble seeing you.", "Those creatures need a DC 5 flat check to target you; area effects are exempt.", "Depends on concealment and observer."),
    ("Confused", 442, 63, False, "You act without clear judgment.", "Off-Guard; cannot Delay, Ready, or react. The GM determines random offensive targets.", "A DC 11 flat check after attack or spell damage can end it."),
    ("Controlled", 442, 64, False, "Another creature directs your actions.", "The controller chooses your actions, including reactions.", "Follow the causing effect."),
    ("Dazzled", 442, 65, False, "Your sight is overstimulated.", "If vision is your only precise sense, everything is Concealed to you.", "Follow the causing effect; Blinded overrides it."),
    ("Deafened", 443, 66, False, "You cannot hear.", "Hearing-only Perception critically fails; –2 status to sound-related Perception with other senses; DC 5 flat check for auditory actions.", "Follow the causing effect."),
    ("Doomed", 443, 67, True, "Your death threshold is reduced.", "Dying threshold falls by the value; use the Phase 7 death rules for details.", "Decreases by 1 after a full night's rest."),
    ("Drained", 443, 68, True, "Your vitality is reduced.", "Status penalty equal to value on Constitution rolls and DCs; current and maximum HP are also reduced by level × value (minimum level 1). Manage HP manually.", "Decreases by 1 after a full night's rest; lost HP are not automatically healed."),
    ("Dying", 443, 69, True, "You are at death's door.", "You are Unconscious; recovery checks occur at turn start. Use Phase 7 for death mechanics.", "Follow recovery and healing rules manually."),
    ("Encumbered", 443, 70, False, "You carry too much.", "Clumsy 1 and –10 feet to Speeds, minimum 5 feet.", "Ends when your load is reduced."),
    ("Enfeebled", 443, 71, True, "Your strength is reduced.", "Status penalty equal to value on Strength-based rolls and DCs, including melee attacks and Athletics.", "Follow the causing effect."),
    ("Fascinated", 443, 72, False, "Your attention is fixed on a subject.", "–2 status to Perception and skill checks; concentrate actions must relate to the subject.", "Hostile action against you or an ally ends it."),
    ("Fatigued", 444, 73, False, "You are exhausted.", "–1 status to AC and saves; cannot use exploration activities while traveling.", "A full night's rest normally ends it."),
    ("Friendly", 444, 75, False, "A creature likes someone.", "This attitude can make simple, safe Requests more likely.", "Attitude can change through interaction."),
    ("Fleeing", 444, 74, False, "You must escape the source.", "Spend actions fleeing as quickly as possible; cannot Delay or Ready.", "Follow the causing effect."),
    ("Frightened", 444, 76, True, "Fear shakes your resolve.", "Status penalty equal to value on all checks and DCs.", "Normally decreases by 1 at the end of each of your turns."),
    ("Grabbed", 444, 77, False, "Another creature holds you.", "Also Off-Guard and Immobilized; DC 5 flat check to use a manipulate action.", "Escape or follow the causing effect; Restrained overrides it."),
    ("Helpful", 444, 78, False, "A creature wants to help someone.", "It may accept reasonable Requests that do not harm its goals.", "Attitude can change through interaction."),
    ("Hidden", 444, 79, False, "A creature knows your space but not your exact location.", "That creature needs a DC 11 flat check to target you; area effects are exempt. It is Off-Guard to you.", "Depends on observer and detection."),
    ("Hostile", 444, 80, False, "A creature wants to harm someone.", "It does not necessarily attack immediately.", "Attitude can change through interaction."),
    ("Immobilized", 444, 81, False, "You cannot move from your space.", "Cannot use actions with the move trait.", "Follow the holding effect or Escape."),
    ("Indifferent", 444, 82, False, "A creature has no strong feeling about someone.", "This is the usual default attitude unless otherwise stated.", "Attitude can change through interaction."),
    ("Invisible", 444, 83, False, "Others cannot see you.", "Usually Undetected, or Hidden to someone who saw you become invisible; special senses may change this.", "Follow the causing effect."),
    ("Observed", 444, 84, False, "You are in plain view to an observer.", "A detection state relative to that observer.", "Can change through Hide, Sneak, or other effects."),
    ("Off-Guard", 445, 58, False, "Your defense is exposed.", "–2 circumstance penalty to AC; can apply only against specified creatures or attacks.", "Follow the source or remove the causing condition."),
    ("Paralyzed", 445, 85, False, "You cannot move your body.", "Off-Guard; only mental actions such as Recall Knowledge are available as GM determines.", "Follow the causing effect."),
    ("Persistent Damage", 445, 86, False, "Damage continues at the end of your turns.", "Apply damage manually, then attempt a recovery flat check, normally DC 15. Same damage types do not add.", "A successful recovery check ends it; GM can determine when it runs its course."),
    ("Petrified", 445, 87, False, "You have become stone.", "Cannot act or sense; special object and HP rules apply.", "Follow the causing effect."),
    ("Prone", 445, 88, False, "You are on the ground.", "Off-Guard; –2 circumstance to attack rolls; normally only Crawl or Stand move actions.", "Stand normally ends it; Take Cover can improve AC against ranged attacks."),
    ("Quickened", 446, 89, False, "You gain one extra action at turn start.", "The extra action may be restricted by its source; multiple sources still grant only one.", "Follow the causing effect."),
    ("Restrained", 446, 90, False, "You are tightly held.", "Off-Guard and Immobilized; cannot attack or manipulate except Escape or Force Open.", "Escape or follow the cause; overrides Grabbed."),
    ("Sickened", 446, 91, True, "You feel ill.", "Status penalty equal to value on all checks and DCs; cannot willingly ingest anything.", "Retching (1 action) and succeeding at the effect's Fortitude DC reduces it; critical success reduces by 2."),
    ("Slowed", 446, 92, True, "You regain fewer actions at turn start.", "Lose actions equal to value when regaining actions; no immediate action loss mid-turn.", "Follow the causing effect; Stunned overrides it, counting only the larger action loss."),
    ("Stunned", 446, 93, True, "You cannot act while stunned.", "Valued Stunned consumes actions as you regain them; Stunned overrides Slowed rather than adding to it.", "Value falls by actions lost at turn start; follow any duration instead of a value."),
    ("Stupefied", 446, 94, True, "Your thoughts are clouded.", "Status penalty equal to value on mental rolls and DCs; casting a spell requires flat check DC 5 + value.", "Follow the causing effect."),
    ("Unconscious", 446, 95, False, "You are unaware and cannot act.", "–4 status to AC, Perception and Reflex; Blinded and Off-Guard. You fall Prone and drop held items unless the cause says otherwise.", "Waking depends on the cause; use Phase 7 for death interactions."),
    ("Undetected", 447, 96, False, "An observer does not know your space.", "Detection and targeting depend on the observer and Seek.", "Changes when detected."),
    ("Unfriendly", 447, 97, False, "A creature dislikes someone.", "Attitude affects social interaction, as GM determines.", "Changes through interaction or effects."),
    ("Unnoticed", 447, 98, False, "An observer is unaware you are present.", "A detection state relative to that observer.", "Changes when noticed."),
    ("Wounded", 447, 99, True, "Past near-death makes further dying riskier.", "Affects the dying condition; use Phase 7 for the detailed calculation.", "Ends after successful Treat Wounds, or full HP plus 10 minutes' rest."),
]

LIBRARY = {}
for name, page, aon_id, valued, summary, effects, ending in ROWS:
    slug = name.lower().replace(" ", "-")
    LIBRARY[slug] = dict(slug=slug, name=name, valued=valued, summary=summary,
                         effects=effects, ending=ending, source_book="Player Core",
                         source_page=page, source_url=f"https://2e.aonprd.com/Conditions.aspx?ID={aon_id}")
