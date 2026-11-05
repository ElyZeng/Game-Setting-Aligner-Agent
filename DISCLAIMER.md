# Disclaimer / 免責聲明

> Draft wording. Have it reviewed through your organisation's legal / open-source review process before relying on it.
> 草稿用語，正式使用前請經過法務或 open source 審查流程確認。

## English

Game Setting Aligner ("Game Tuner") reads and, when you allow it, **modifies the settings files of games installed on your PC**. By enabling writes you accept the following:

1. **What a write changes.** Game Tuner only changes the settings it shows for a game, and only to values offered in that game's own settings menu. It does not modify game executables, save games, online services or server-side data.
2. **Support levels mean different things.**
   - *Write-safe*: Game Tuner has verified that it can write the value, read it back and restore the original file byte-for-byte. It has **not** confirmed that the game applies or keeps the value.
   - *Persistence-verified*: the value is still present after the game was started and closed normally.
   - *Fully verified*: the value was also confirmed in the game's own menu.
   A game may support different settings at different levels.
3. **Backups.** Before every write Game Tuner copies the affected files. The copy taken before Game Tuner's first write to a game is kept permanently and can be restored at any time ("Restore Original" in the app, or `game-tuner restore-original <game> --confirm`). If a write cannot be verified, the original files are restored automatically.
4. **Close the game first.** Writes are refused while the game is running. Cloud sync (for example Steam Cloud) or the game itself may later overwrite changed settings.
5. **Anti-cheat.** Writes are disabled for games where anti-cheat software is detected, unless that specific game has been reviewed by the maintainers and approved for the listed settings. A review records the maintainers' assessment only; it is **not** a statement or endorsement by the game's publisher or the anti-cheat vendor.
6. **Game updates.** A game update can change how its settings are stored. Game Tuner limits writes on unverified game versions, but cannot guarantee behaviour after an update.
7. **Your responsibility.** You are responsible for complying with each game's end-user licence agreement and terms of service.
8. **No warranty.** The software is provided "as is", without warranty of any kind, as stated in the [LICENSE](LICENSE). The authors are not liable for any damage, data loss, account action or other consequence arising from its use.

## 中文（繁體）

Game Setting Aligner（Game Tuner）會讀取你電腦上已安裝遊戲的設定檔；在你允許時，也會**修改這些設定檔**。開啟寫入功能即表示你了解並同意以下事項：

1. **寫入會改什麼。** Game Tuner 只會修改它對該遊戲顯示的設定，而且只寫入遊戲自己的設定選單裡本來就能選的值。它不會修改遊戲執行檔、存檔、線上服務或伺服器端資料。
2. **支援等級的意義不同。**
   - *寫入安全*：已驗證 Game Tuner 能寫入該值、讀回，並把原檔逐位元組還原；**尚未**確認遊戲會套用或保留這個值。
   - *保留已驗證*：遊戲正常啟動再關閉後，該值仍然存在。
   - *完整驗證*：另外也在遊戲內的選單確認過。
   同一款遊戲的不同設定可能處於不同等級。
3. **備份。** 每次寫入前都會先複製受影響的檔案。Game Tuner 第一次寫入某款遊戲前的那份備份會永久保留，隨時可以還原（app 裡的「Restore Original」，或 `game-tuner restore-original <遊戲> --confirm`）。寫入結果無法驗證時，會自動還原原檔。
4. **請先關閉遊戲。** 遊戲執行中會拒絕寫入。雲端同步（例如 Steam Cloud）或遊戲本身之後仍可能覆蓋修改過的設定。
5. **反作弊。** 偵測到反作弊軟體的遊戲預設停用寫入；只有經維護者逐款審查並核准的遊戲與設定項目才會開放。審查結果只代表維護者的評估，**不代表**遊戲發行商或反作弊廠商的立場或背書。
6. **遊戲更新。** 遊戲更新可能改變設定的儲存方式。Game Tuner 會限制對未驗證版本的寫入，但無法保證更新後的行為。
7. **使用者責任。** 你須自行遵守各遊戲的使用者授權合約（EULA）與服務條款。
8. **不提供擔保。** 本軟體依 [LICENSE](LICENSE) 以「現況」提供，不附任何形式的擔保。作者不對使用本軟體所造成的任何損害、資料遺失、帳號處分或其他後果負責。
