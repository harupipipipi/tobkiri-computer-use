import test from "node:test";
import assert from "node:assert/strict";
import { defaults, motionIds, validatePack } from "../src/config.js";
import { poseFor, Character, drawCharacter } from "../src/engine.js";
import protocol from "../protocol.cjs";
import { extraMotions, extraPose, idleMotion } from "../src/motions.js";

test("48 distinct, finite, continuous skeletal animations", () => {
  assert.equal(motionIds.length, 48);
  const shapes = new Set();
  for (const action of motionIds) {
    shapes.add(JSON.stringify(poseFor(action, 0.23)));
    for (let t = 0; t < 3; t += 0.016) {
      const pose = poseFor(action, t),
        next = poseFor(action, t + 0.001);
      assert.equal(pose.length, 10);
      for (let i = 0; i < pose.length; i++)
        for (let j = 0; j < 2; j++) {
          assert.ok(Number.isFinite(pose[i][j]));
          assert.ok(Math.abs(pose[i][j] - next[i][j]) < 2);
        }
    }
  }
  assert.equal(shapes.size, 48);
});
test("new movement phrases loop smoothly and hip lift returns to its feet", () => {
  for (const [action] of extraMotions) {
    for (let t = 0; t < 8; t += 0.008) {
      const a = extraPose(action, t),
        b = extraPose(action, t + 0.001);
      for (let i = 0; i < 10; i++)
        for (let j = 0; j < 2; j++)
          assert.ok(Math.abs(a[i][j] - b[i][j]) < 2, `${action} at ${t}`);
    }
  }
  const standing = poseFor("hip_pop", 0),
    raised = poseFor("hip_pop", 0.32 * 2.1);
  assert.ok(
    raised[2][1] < standing[2][1] - 60,
    "Pelvis leads the upward movement",
  );
  assert.deepEqual(poseFor("hip_pop", 2.1), standing);
  assert.equal(idleMotion(12.1), "hip_pop");
});
test("pet-only mode hides arrow, ring and trail without changing the input anchor", () => {
  assert.equal(validatePack({ version: 1, cursor: "star" }).displayMode, "pet");
  assert.throws(() => validatePack({ ...defaults, displayMode: "invalid" }));
  const translations = [];
  const ctx = new Proxy(
    { translate: (...p) => translations.push(p) },
    { get: (obj, k) => obj[k] ?? (() => {}) },
  );
  const c = new Character({ ...defaults, displayMode: "pet" }, 350, 300);
  c.play("click");
  c.draw(ctx);
  assert.ok(!translations.some((p) => p[0] === 350 && p[1] === 300));
  c.pack = { ...c.pack, displayMode: "both" };
  c.draw(ctx);
  assert.ok(translations.some((p) => p[0] === 350 && p[1] === 300));
  assert.deepEqual([c.tx, c.ty], [350, 300]);
});
test("frame-rate independent motion settles without overshoot", () => {
  const a = new Character(defaults, 0, 0),
    b = new Character(defaults, 0, 0);
  a.tx = b.tx = 500;
  a.ty = b.ty = 300;
  for (let i = 0; i < 60; i++) a.update(1 / 60);
  for (let i = 0; i < 144; i++) b.update(1 / 144);
  assert.ok(Math.abs(a.x - b.x) < 0.001);
  assert.ok(a.x < 500 && a.x > 499);
  assert.ok(a.y < 300);
});

test("idle life and reduced motion keep the input hotspot fixed", () => {
  const c = new Character({ ...defaults, reducedMotion: true }, 20, 20);
  c.tx = 40;
  c.ty = 50;
  c.update(0.016);
  assert.deepEqual([c.x, c.y, c.tx, c.ty], [40, 50, 40, 50]);
  for (let i = 0; i < 500; i++) c.update(0.016);
  assert.equal(c.action, "peek");
  assert.deepEqual([c.tx, c.ty], [40, 50]);
  assert.equal(c.trail.length, 0);
});

test("a small direction reversal turns without an 84px body teleport", () => {
  const c = new Character(defaults, 400, 300);
  const before = c.x - 42 * c.facingBlend;
  c.tx = 388;
  c.update(1 / 60);
  assert.ok(Math.abs(c.x - 42 * c.facingBlend - before) < 20);
  assert.ok(c.facingBlend > -1 && c.facingBlend < 1);
  assert.equal(c.tx, 388);
  for (let i = 0; i < 60; i++) c.update(1 / 60);
  assert.ok(c.facingBlend < -0.999);
});

test("the head remains round at the midpoint of a turn", () => {
  const arcs = [];
  const ctx = new Proxy(
    { arc: (...args) => arcs.push(args) },
    { get: (target, key) => target[key] ?? (() => {}) },
  );
  drawCharacter(
    ctx,
    poseFor("idle", 0),
    { ...defaults, eyes: false, accessory: "none" },
    "idle",
    0,
    { facing: 0, shadow: false },
  );
  assert.equal(arcs[0][2], defaults.head);
});
test("hotspot is exact while character eases; hidden sessions retire", () => {
  const c = new Character(defaults, 10, 20);
  c.receive({ point: [200, 300], phase: "start", action: "type" });
  c.update(0.016);
  assert.equal(c.tx, 200);
  assert.ok(c.x < 200);
  assert.equal(c.action, "type");
  c.receive({
    point: [200, 300],
    phase: "end",
    action: "type",
    outcome: "refused",
  });
  assert.equal(c.action, "confused");
  c.receive({ point: [200, 300], phase: "hide" });
  assert.equal(c.hidden, true);
});
test("custom poses interpolate and malicious / unbounded packs are rejected", () => {
  const first = poseFor("idle", 0),
    second = poseFor("wave", 0);
  const pack = validatePack({ ...defaults, clips: { idle: [first, second] } });
  assert.deepEqual(poseFor("idle", 0, pack), first);
  assert.deepEqual(poseFor("idle", 0.5, pack), second);
  for (const change of [
    { version: 2 },
    { size: Infinity },
    { color: "url(x)" },
    { hotspot: [-1, 2] },
    { sprites: { idle: { image: "https://x", frames: 2, fps: 30 } } },
    {
      clips: {
        idle: [
          [1, 2],
          [3, 4],
        ],
      },
    },
  ])
    assert.throws(() => validatePack({ ...defaults, ...change }));
});
test("protocol rejects oversized or invalid datagrams and strips extra data", () => {
  const event = {
    version: 1,
    source: "test",
    session: "one",
    seq: 1,
    action: "click",
    phase: "start",
    space: "physical",
    point: [-1920, 100],
    text: "never forward me",
  };
  const parse = (e) => protocol.parseEvent(Buffer.from(JSON.stringify(e)));
  assert.equal(parse(event).text, undefined);
  assert.deepEqual(parse(event).point, [-1920, 100]);
  for (const change of [
    { point: [null, 0] },
    { seq: -1 },
    { space: "screenshot" },
    { phase: "exec" },
    { action: "shell" },
    { session: [] },
    { point: [1e20, 0] },
  ])
    assert.equal(parse({ ...event, ...change }), null);
  assert.equal(protocol.parseEvent(Buffer.alloc(4097)), null);
});
