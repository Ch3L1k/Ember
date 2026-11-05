/* Ember contributors, GPL-3.0-or-later. */
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { shortSession } = require('../../ember/web/library_stats.js');
const now = 1800000000;
const details = { unAppID: 42, nPlaytimeForever: 0, rtLastTimePlayed: now - 30 };
const overview = { appid: 42, rt_last_time_locally_played: now - 29 };
test('shows a real sub-minute session without increasing playtime', () => {
  assert.equal(shortSession(details, overview, ['42'], now), now - 30);
  assert.equal(details.nPlaytimeForever, 0);
});
test('leaves normal statistics and other games to Steam', () => {
  assert.equal(shortSession({...details, nPlaytimeForever: 17}, overview, ['42'], now), null);
  assert.equal(shortSession(details, overview, ['99'], now), null);
});
test('installation timestamps and incomplete data do not count as played', () => {
  assert.equal(shortSession(details, {...overview, rt_last_time_locally_played: 0}, ['42'], now), null);
  assert.equal(shortSession(null, overview, ['42'], now), null);
  assert.equal(shortSession({...details, rtLastTimePlayed: NaN}, overview, ['42'], now), null);
  assert.equal(shortSession({...details, rtLastTimePlayed: now + 100000}, overview, ['42'], now), null);
  assert.equal(shortSession(details, {...overview, appid: 99}, ['42'], now), null);
});
