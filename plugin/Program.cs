using System.Drawing;
using System.Text.Json;
using Mutagen.Bethesda;
using Mutagen.Bethesda.Plugins;
using Mutagen.Bethesda.Plugins.Assets;
using Mutagen.Bethesda.Plugins.Records;
using Mutagen.Bethesda.Skyrim;
using Mutagen.Bethesda.Skyrim.Assets;
using Noggog;

// Builds "[Tinesh] Mannoroth Shield.esp" (Skyrim SE, ESL-flagged) from the Skyrim LE original.
// args: <original MannorothShield.esp> <Skyrim.esm> <output folder> <meshes report.json>
var originalPath = args[0];
var skyrimPath = args[1];
var outDir = args[2];
using var meshReport = JsonDocument.Parse(File.ReadAllText(args[3]));
(P3Int16, P3Int16) Bounds(string size)
{
    var o = meshReport.RootElement.GetProperty("sizes").GetProperty(size).GetProperty("bounds").GetProperty("obnd").EnumerateArray().Select(e => (short)e.GetInt32()).ToArray();
    return (new P3Int16(o[0], o[1], o[2]), new P3Int16(o[3], o[4], o[5]));
}

var skyrimKey = ModKey.FromFileName("Skyrim.esm");
var modKey = ModKey.FromFileName("[Tinesh] Mannoroth Shield.esp");
FormKey Sk(uint id) => new(skyrimKey, id);
FormKey Mine(uint id) => new(modKey, id);
const SkyrimRelease release = SkyrimRelease.SkyrimSE;

using var original = SkyrimMod.CreateFromBinaryOverlay(originalPath, SkyrimRelease.SkyrimLE);
using var skyrim = SkyrimMod.CreateFromBinaryOverlay(skyrimPath, release);

var origArmor = original.Armors.Single();
var origAddon = original.ArmorAddons.Single();
var origTemper = original.ConstructibleObjects.Single(c => c.EditorID == "TemperArmorMannorothShield");
var origRecipe = original.ConstructibleObjects.Single(c => c.EditorID == "RecipeArmorMannorothShield");

var mod = new SkyrimMod(modKey, release);
mod.ModHeader.Flags |= SkyrimModHeader.HeaderFlag.Small;
mod.ModHeader.Author = "SamyFrench (original), Tinesh (SE/AE port)";
mod.ModHeader.Description = "Tusk of Mannoroth standalone shield by SamyFrench, ported to Skyrim Special Edition and Anniversary Edition by Tinesh.";

// --- fel fire visuals: the vanilla fire hit shader with a green palette ---------------------------
var felShader = skyrim.EffectShaders.First(e => e.FormKey == Sk(0x01B212)).Duplicate(Mine(0xD73));
felShader.EditorID = "MannorothShieldFelFireFXShader";
felShader.FormVersion = 44;
felShader.MembranePaletteTexture = new AssetLink<SkyrimTextureAssetType>(@"Effects\Gradients\GradGreenEnch.dds");
felShader.ParticlePaletteTexture = new AssetLink<SkyrimTextureAssetType>(@"Effects\Gradients\GradGreenEnch.dds");
felShader.EdgeEffectColor = Color.FromArgb(0, 70, 200, 30);
mod.EffectShaders.Add(felShader);

// --- magic effects -------------------------------------------------------------------------------
var felFire = skyrim.MagicEffects.First(m => m.FormKey == Sk(0x04605A)).Duplicate(Mine(0xD71));
felFire.EditorID = "MannorothShieldFelFireDamage";
felFire.Name = "Fel Fire";
felFire.Description = "Fel fire burns the target for <mag> points.";
felFire.TargetType = TargetType.TargetActor;
felFire.Flags = MagicEffect.Flag.Hostile | MagicEffect.Flag.Detrimental | MagicEffect.Flag.NoArea | MagicEffect.Flag.NoDeathDispel;
felFire.MagicSkill = ActorValue.None;
felFire.MinimumSkillLevel = 0;
felFire.CastingSoundLevel = SoundLevel.Silent;
felFire.HitShader.SetTo(felShader.FormKey);
felFire.EnchantShader.Clear();
felFire.ImpactData.Clear();
felFire.MenuDisplayObject.Clear();
mod.MagicEffects.Add(felFire);

var felStagger = new MagicEffect(Mine(0xD72), release)
{
    EditorID = "MannorothShieldFelStagger",
    Name = "Fel Stagger",
    Archetype = new MagicEffectArchetype { Type = MagicEffectArchetype.TypeEnum.Stagger, ActorValue = ActorValue.None },
    CastType = CastType.FireAndForget,
    TargetType = TargetType.TargetActor,
    Flags = MagicEffect.Flag.Hostile | MagicEffect.Flag.HideInUI | MagicEffect.Flag.NoArea | MagicEffect.Flag.NoDuration,
    MagicSkill = ActorValue.None,
    ResistValue = ActorValue.None,
    SecondActorValue = ActorValue.None,
    CastingSoundLevel = SoundLevel.Silent,
    DualCastScale = 1,
};
mod.MagicEffects.Add(felStagger);

var rebukeSpell = new Spell(Mine(0xD70), release)
{
    EditorID = "MannorothShieldFelRebukeSpell",
    Name = "Fel Rebuke",
    Description = "",
    Type = SpellType.Spell,
    CastType = CastType.FireAndForget,
    TargetType = TargetType.TargetActor,
    Flags = SpellDataFlag.ManualCostCalc | SpellDataFlag.NoAbsorbOrReflect,
    BaseCost = 0,
};
rebukeSpell.EquipmentType.SetTo(Sk(0x013F44));
rebukeSpell.Effects.Add(new Effect { BaseEffect = felFire.ToNullableLink(), Data = new EffectData { Magnitude = 100 } });
rebukeSpell.Effects.Add(new Effect { BaseEffect = felStagger.ToNullableLink(), Data = new EffectData { Magnitude = 50 } });
mod.Spells.Add(rebukeSpell);

var rebukeEffect = new MagicEffect(Mine(0xD6F), release)
{
    EditorID = "EnchMannorothShieldFelRebuke",
    Name = "Fel Rebuke",
    Description = "Blocking a melee attack has a 60% chance to engulf the attacker in fel fire, staggering them and dealing 100 points of fire damage.",
    Archetype = new MagicEffectArchetype { Type = MagicEffectArchetype.TypeEnum.Script, ActorValue = ActorValue.None },
    CastType = CastType.ConstantEffect,
    TargetType = TargetType.Self,
    Flags = MagicEffect.Flag.NoDuration | MagicEffect.Flag.NoMagnitude | MagicEffect.Flag.NoArea,
    BaseCost = 20,
    MagicSkill = ActorValue.None,
    ResistValue = ActorValue.None,
    SecondActorValue = ActorValue.None,
    CastingSoundLevel = SoundLevel.Silent,
    DualCastScale = 1,
    VirtualMachineAdapter = new VirtualMachineAdapter
    {
        Scripts =
        {
            new ScriptEntry
            {
                Name = "MannorothShieldFelRebukeScript",
                Flags = ScriptEntry.Flag.Local,
                Properties =
                {
                    new ScriptObjectProperty { Name = "FelRebukeSpell", Flags = ScriptProperty.Flag.Edited, Object = rebukeSpell.ToLink<ISkyrimMajorRecordGetter>() },
                    new ScriptObjectProperty { Name = "DGIntimidateFaction", Flags = ScriptProperty.Flag.Edited, Object = new FormLink<ISkyrimMajorRecordGetter>(Sk(0x04CFA6)) },
                },
            },
        },
    },
};
rebukeEffect.MenuDisplayObject.SetTo(Sk(0x0435A5));
mod.MagicEffects.Add(rebukeEffect);

var enchantment = new ObjectEffect(Mine(0xD6E), release)
{
    EditorID = "EnchArmorMannorothShield",
    Name = "Blood of Mannoroth",
    CastType = CastType.ConstantEffect,
    TargetType = TargetType.Self,
    EnchantType = ObjectEffect.EnchantTypeEnum.Enchantment,
    Flags = ObjectEffect.Flag.NoAutoCalc,
    EnchantmentCost = 500,
    EnchantmentAmount = 500,
};
enchantment.WornRestrictions.SetTo(Sk(0x10CD14));
enchantment.Effects.Add(new Effect { BaseEffect = new FormLinkNullable<IMagicEffectGetter>(Sk(0x07A0F3)), Data = new EffectData { Magnitude = 20 } });
enchantment.Effects.Add(new Effect { BaseEffect = rebukeEffect.ToNullableLink(), Data = new EffectData() });
mod.ObjectEffects.Add(enchantment);

// --- shields -------------------------------------------------------------------------------------
var races = new uint[]
{
    0x013740, 0x08883A, 0x013741, 0x08883C, 0x097A3D, 0x013742, 0x08883D, 0x0F71DC, 0x000D53, 0x067CD8, 0x0A82BA,
    0x013743, 0x088840, 0x013744, 0x088844, 0x013745, 0x088845, 0x10760A, 0x013746, 0x088794, 0x013747, 0x0A82B9,
    0x013748, 0x088846, 0x013749, 0x088884,
};

var sizes = new[]
{
    new { Name = "Small", Armor = 0xD66u, Addon = 0xD67u, Recipe = 0xD68u, Temper = 0xD69u, Nif = @"weapons\mannoroth\mannorothshield_small.nif", FirstPerson = @"weapons\mannoroth\1stpersonmannorothshield_small.nif",
          Rating = 30f, Weight = 12f, Value = 900u, Ingots = 1, Bounds = Bounds("small") },
    new { Name = "Medium", Armor = origArmor.FormKey.ID, Addon = origAddon.FormKey.ID, Recipe = origRecipe.FormKey.ID, Temper = origTemper.FormKey.ID,
          Nif = origAddon.WorldModel!.Male!.File.DataRelativePath.ToString().Replace(@"meshes\", "", StringComparison.OrdinalIgnoreCase),
          FirstPerson = @"weapons\mannoroth\1stpersonmannorothshield.nif",
          Rating = 34f, Weight = 16f, Value = 1100u, Ingots = 2, Bounds = Bounds("medium") },
    new { Name = "Large", Armor = 0xD6Au, Addon = 0xD6Bu, Recipe = 0xD6Cu, Temper = 0xD6Du, Nif = @"weapons\mannoroth\mannorothshield_large.nif", FirstPerson = @"weapons\mannoroth\1stpersonmannorothshield_large.nif",
          Rating = 38f, Weight = 21f, Value = 1300u, Ingots = 3, Bounds = Bounds("large") },
};

foreach (var s in sizes)
{
    var suffix = s.Name == "Medium" ? "" : s.Name;

    var addon = new ArmorAddon(Mine(s.Addon), release)
    {
        EditorID = "MannorothShield" + suffix,
        BodyTemplate = new BodyTemplate { FirstPersonFlags = BipedObjectFlag.Shield, ArmorType = ArmorType.Clothing, ActsLike44 = true },
        Priority = new GenderedItem<byte>(0, 0),
        WeightSliderEnabled = new GenderedItem<bool>(false, false),
        WorldModel = new GenderedItem<Model?>(new Model { File = s.Nif }, new Model { File = s.Nif }),
        FirstPersonModel = new GenderedItem<Model?>(new Model { File = s.FirstPerson }, new Model { File = s.FirstPerson }),
    };
    addon.Race.SetTo(Sk(0x000019));
    foreach (var r in races)
        addon.AdditionalRaces.Add(new FormLink<IRaceGetter>(Sk(r)));
    mod.ArmorAddons.Add(addon);

    var armor = new Armor(Mine(s.Armor), release)
    {
        EditorID = "ArmorMannorothShield" + suffix,
        Name = $"Mannoroth Shield ({s.Name})",
        MajorFlags = Armor.MajorFlag.Shield,
        ObjectBounds = new ObjectBounds { First = s.Bounds.Item1, Second = s.Bounds.Item2 },
        BodyTemplate = new BodyTemplate { FirstPersonFlags = BipedObjectFlag.Shield, ArmorType = ArmorType.HeavyArmor, ActsLike44 = true },
        WorldModel = new GenderedItem<ArmorModel?>(new ArmorModel { Model = new Model { File = s.Nif } }, null),
        ArmorRating = s.Rating,
        Weight = s.Weight,
        Value = s.Value,
        Keywords = new ExtendedList<IFormLinkGetter<IKeywordGetter>>
        {
            new FormLink<IKeywordGetter>(Sk(0x06BBD8)),
            new FormLink<IKeywordGetter>(Sk(0x08F959)),
            new FormLink<IKeywordGetter>(Sk(0x0965B2)),
            new FormLink<IKeywordGetter>(Sk(0x0C27BD)),
        },
    };
    armor.EquipmentType.SetTo(Sk(0x0141E8));
    armor.BashImpactDataSet.SetTo(Sk(0x0183FE));
    armor.AlternateBlockMaterial.SetTo(Sk(0x016979));
    armor.Race.SetTo(Sk(0x000019));
    armor.ObjectEffect.SetTo(enchantment.FormKey);
    armor.Armature.Add(addon.ToLink());
    mod.Armors.Add(armor);

    var recipe = new ConstructibleObject(Mine(s.Recipe), release)
    {
        EditorID = "RecipeArmorMannorothShield" + suffix,
        CreatedObjectCount = 1,
        Items = new ExtendedList<ContainerEntry>
        {
            new() { Item = new ContainerItem { Item = new FormLink<IItemGetter>(Sk(0x05AD99)), Count = 2 } },
        },
    };
    recipe.CreatedObject.SetTo(armor.FormKey);
    recipe.WorkbenchKeyword.SetTo(Sk(0x088105));
    mod.ConstructibleObjects.Add(recipe);

    var temper = new ConstructibleObject(Mine(s.Temper), release)
    {
        EditorID = "TemperArmorMannorothShield" + suffix,
        CreatedObjectCount = 1,
        Items = new ExtendedList<ContainerEntry>
        {
            new() { Item = new ContainerItem { Item = new FormLink<IItemGetter>(Sk(0x05AD99)), Count = s.Ingots } },
        },
    };
    temper.CreatedObject.SetTo(armor.FormKey);
    temper.WorkbenchKeyword.SetTo(Sk(0x0ADB78));
    temper.Conditions.Add(new ConditionFloat
    {
        CompareOperator = CompareOperator.NotEqualTo, ComparisonValue = 1, Flags = Condition.Flag.OR,
        Data = new EPTemperingItemIsEnchantedConditionData(),
    });
    var arcane = new HasPerkConditionData();
    arcane.Perk.Link.SetTo(Sk(0x05218E));
    temper.Conditions.Add(new ConditionFloat { CompareOperator = CompareOperator.EqualTo, ComparisonValue = 1, Data = arcane });
    mod.ConstructibleObjects.Add(temper);
}

mod.ModHeader.Stats.NextFormID = 0xD74;
mod.ModHeader.Stats.Version = 1.7f;

Directory.CreateDirectory(outDir);
var outPath = Path.Combine(outDir, modKey.FileName);
mod.BeginWrite.ToPath(outPath).WithNoLoadOrder().Write();
Console.WriteLine($"WROTE {outPath} ({new FileInfo(outPath).Length} bytes)");

using var back = SkyrimMod.CreateFromBinaryOverlay(outPath, release);
Console.WriteLine($"HEADER ESL={back.ModHeader.Flags.HasFlag(SkyrimModHeader.HeaderFlag.Small)} version={back.ModHeader.Stats.Version} next={back.ModHeader.Stats.NextFormID:X} records={back.ModHeader.Stats.NumRecords} masters={string.Join(",", back.ModHeader.MasterReferences.Select(m => m.Master.FileName))} author='{back.ModHeader.Author}'");
foreach (var rec in back.EnumerateMajorRecords())
    Console.WriteLine($"  {rec.FormKey.ID:X6} {rec.GetType().Name.Replace("BinaryOverlay", ""),-24} {rec.EditorID,-34} formVersion={rec.FormVersion}");
foreach (var a in back.Armors)
    Console.WriteLine($"  ARMO {a.EditorID}: '{a.Name?.String}' AR={a.ArmorRating} W={a.Weight} V={a.Value} ench={a.ObjectEffect.FormKey} nif={a.WorldModel?.Male?.Model?.File} bounds={a.ObjectBounds.First}/{a.ObjectBounds.Second} kw={a.Keywords?.Count}");
foreach (var aa in back.ArmorAddons)
    Console.WriteLine($"  ARMA {aa.EditorID}: races={aa.AdditionalRaces.Count} male={aa.WorldModel?.Male?.File} female={aa.WorldModel?.Female?.File} firstPerson={aa.FirstPersonModel?.Male?.File}/{aa.FirstPersonModel?.Female?.File} modelData={(aa.WorldModel?.Male?.Data == null ? "none" : "present")}");
foreach (var sp in back.Spells)
    Console.WriteLine($"  SPEL {sp.EditorID}: {string.Join(", ", sp.Effects.Select(e => $"{e.BaseEffect.FormKey.ID:X}={e.Data?.Magnitude}"))}");
foreach (var c in back.ConstructibleObjects)
    Console.WriteLine($"  COBJ {c.EditorID}: bench={c.WorkbenchKeyword.FormKey} items={string.Join("+", c.Items!.Select(i => $"{i.Item.Count}x{i.Item.Item.FormKey.ID:X}"))} conditions={c.Conditions.Count}");
