# Release checklist

1. **Credits.** Check the credits and permissions of every file in the packages, and credit the original author and
   every asset source in the README and the release notes.
2. **Version.** Set `$Version` in `build.ps1` and add a section to `CHANGELOG.md`.
3. **Build.** Run `.\build.ps1`; the packages land in `dist\` as `Mannoroth Shield SE (<res>) - <version>.7z`.
4. **Check the packages.**
   - `7z t` passes on both archives.
   - The archive root holds the plugin, `meshes`, `textures`, `Scripts` and `Source` (no `Data` folder level).
   - Both packages share the same plugin, meshes and script; only the textures differ.
   - DDS headers: BC7 with full mip chains, 4096 px (2K) and 8192 px (4K).
   - Install one package in Mod Organizer 2 and test in game: third and first person, all sizes, the enchantment,
     the recipes.
5. **Release assets.** Copy the tested packages to `dist\` as `Mannoroth-Shield-SE-2K-<version>.7z` and
   `Mannoroth-Shield-SE-4K-<version>.7z` (GitHub turns spaces and brackets in asset names into dots), and note their
   SHA-256 (`Get-FileHash`).
6. **Release.** Tag `v<version>` on `main` with installation notes and the checksums:

   ```powershell
   gh release create v1.0 --target main --title "Mannoroth Shield 1.0" --notes-file notes.md `
       "dist\Mannoroth-Shield-SE-2K-1.0.7z#Mannoroth Shield SE (2K) - 1.0" `
       "dist\Mannoroth-Shield-SE-4K-1.0.7z#Mannoroth Shield SE (4K) - 1.0"
   ```

7. **README.** Point the Downloads table at the new assets
   (`https://github.com/71Kevin/mannoroth-shield-se/releases/download/v<version>/<file>`) and keep the Mod pages
   table up to date.
8. **Verify.** Signed out (or with `curl`), open the release page, download both assets and compare their SHA-256 with
   the tested packages.
