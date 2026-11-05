# Public game activity on Linux

Ember's local library integration does not currently provide verified public activity under an added game's original Steam App ID. A successful launch, a working library page and a server-side playing session do not by themselves establish what friends see.

## Checks on 5 November 2026

Tested with Steam client build `1792618285` and the installed SLSsteam integration.

| Check | Observed result |
| --- | --- |
| Launch 60 Seconds! (`368360`) registered through Ember | The game runs, but the returned persona has game ID `0`. |
| Inspect the outgoing game activity message | The original App ID reaches the send path. The local activity filter does not suppress it. |
| Inspect the playing-session response | Steam reports the session for `368360` without a playing-session block. This is separate from public persona activity. |
| Run DDNet (`412220`) as a control | The returned persona contains `412220`. |
| Supply the game title without changing its App ID | No public game activity for the tested title. |
| Use SLSsteam's idle status with `368360` | The returned persona remains at game ID `0`. |

The idle-status check used a short-lived sleeping process in place of the game executable. The probe's start and exit were confirmed from Steam's process log. The original launch options and idle-status settings were restored afterwards.

These results narrow the failure to the public activity path after local launch reporting. They do not identify Steam's exact server-side decision or prove the same result for every account and game. The idle-status experiment did not independently capture the final outgoing packet.

## Upstream behavior

In [SLSsteam issue #34](https://github.com/AceSLS/SLSsteam/issues/34), the maintainer describes displaying a title through `FakeAppIds` and `GameTitles`. That route substitutes another App ID. It is not evidence that the original game ID will be published. A non-Steam shortcut is also a different result.

No such substitution is enabled by this investigation. A fix for the original-ID behavior needs a reproducible working reference or evidence of a different reporting path. Historical reports about Windows SteamTools have not yet been reproduced here.

## Verifying a future fix

Check the returned persona and an independent viewer, not just the local library or Friends window. Confirm the actual App ID, then close the game and confirm that activity clears. Repeat with another registered game and a normally licensed control. Do not treat a renamed shortcut or another game's ID as a passing result.

Steam Cloud and Discord recognition are separate from this check. No Cloud settings, game saves or Discord configuration were changed.
