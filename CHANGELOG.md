# Changelog

Skyrim SE/AE port of [Tusk of Mannoroth standalone shield](https://www.nexusmods.com/skyrim/mods/74030) by
SamyFrench, based on the Skyrim LE file `MannorothShield-74030-1-1.rar` (version 1.1, 2016-03-06).

## 1.0 — 2026-09-30

First release of the port, in two packages: 2K (4096 px textures) and 4K (8192 px textures).

### Added
- Three sizes: Small (0.8x), Medium (the original size) and Large (1.25x), each with its own mesh, collision,
  armor addon, first-person model, forge recipe and tempering recipe.
- Handle taken from the vanilla iron shield, its posts fitted to the back of each size.
- First-person models: the shield turned in its own plane, centred on the handle and placed per size so its rim
  and tusk show at the lower left at rest and its back covers the view when blocking; the curled lower plate that
  wraps back towards the arm is left out there, where it would sit in front of the camera. Checked against 178
  vanilla first-person animations.
- Fel fire in the skull's eyes: flickering glow in both sockets and green flames rising out of them (crossed,
  scrolling flame cards and a soft halo; additive effect shaders with vanilla textures).
- Blood of Mannoroth enchantment: Fortify Block 20% and Fel Rebuke (60% chance on a blocked melee hit to stagger the
  attacker and deal 100 fire damage with a green fel fire effect; 3 second cooldown; skips allies, non-hostile actors
  and brawls). Script: `MannorothShieldFelRebukeScript`.
- Simple crafting: all three sizes at any forge for 2 Orichalcum Ingots, no perk needed.
- Upscaled textures in two packages: diffuse upscaled from 512 px, normal map rebuilt from the cavity map,
  environment mask and glow map rebuilt; BC7 with full mipmaps.

### Fixed
- Mesh converted to Skyrim SE; welded triangle soup and rebuilt normals (the stored normals did not match the faces).
- Collision rebuilt from the mesh (the original used the vanilla ebony shield's collision).
- Absolute texture paths made relative.
- Normal map replaced (the original was the vanilla ebony shield's normal map, unrelated to this texture).
- Armor addon race list includes the vampire races; object bounds set from the meshes.

### Changed
- Mesh subdivided with creases (922 to 19,728 triangles): rounded tusk and base, sharp spikes and rim.
- Plugin rebuilt for Skyrim SE as `[Tinesh] Mannoroth Shield.esp`: form version 44, ESL-flagged, original FormIDs of
  the shield, its armor addon and both recipes kept.
- Stats rebalanced to the ebony/daedric tier (original: 76 armor, weight 28, value 5750).
- Item names carry the size: "Mannoroth Shield (Small/Medium/Large)".

## Test builds before 1.0 (not released)

- 1.1.0.1 (2026-09-26): SE conversion, three sizes, enchantment (25% / 20 damage).
- 1.1.0.2 (2026-09-29): subdivided mesh, iron shield handle, first-person model, 4096 px textures, Fel Rebuke 60% / 100.
- 1.1.0.3 (2026-09-30): eye glow, plugin renamed, packages with 2048, 4096 and 8192 px textures, first-person tweak.
- 1.1.0.4 (2026-09-30): fel fire flames, per-size first-person placement.
