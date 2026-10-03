# Release checklist

1. **Permissions.** Confirm that every file in the packages may be redistributed (original author, third-party art,
   Bethesda assets). Do not publish a package until this is settled.
2. **Version.** Set `$Version` in `build.ps1` and add a section to `CHANGELOG.md`.
3. **Build.** Run `.\build.ps1`; the packages land in `dist\`.
4. **Check the packages.**
   - `7z t` passes on both archives.
   - The archive root holds the plugin, `meshes`, `textures`, `Scripts` and `Source` (no `Data` folder level).
   - Both packages share the same plugin, meshes and script; only the textures differ.
   - DDS headers: BC7 with full mip chains, 4096 px (2K) and 8192 px (4K).
   - Install one package in Mod Organizer 2 and test in game: third and first person, all sizes, the enchantment,
     the recipes.
5. **Release.** Tag `v<version>` and attach both packages:

   ```powershell
   gh release create v1.0 --title "Mannoroth Shield 1.0" --notes-file notes.md `
       "dist\Mannoroth Shield SE (2K) - 1.0.7z#Mannoroth Shield SE (2K) - 1.0.7z" `
       "dist\Mannoroth Shield SE (4K) - 1.0.7z#Mannoroth Shield SE (4K) - 1.0.7z"
   ```

   GitHub replaces spaces and brackets in asset file names; the text after `#` keeps the readable name as the label.
   Read the final download URLs with `gh release view v1.0 --json assets`.
6. **README.** Replace "not released yet" in the Downloads section with the release and asset links, and add the
   external pages (Dwemer Mods and others) once they exist.
