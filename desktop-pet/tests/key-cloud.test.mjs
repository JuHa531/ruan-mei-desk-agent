/** Printable-input boundaries, replacement and expiry of the single-character display. */
import test from 'node:test';
import assert from 'node:assert/strict';
import {KEY_CLOUD,KEY_EFFECT_BOUNDS,isDisplayCharacter,createKeyDisplay,keyCloudFrame} from '../renderer/key-cloud.mjs';

test('printable keys include both cases, every ASCII punctuation key and space',()=>{
 for(let n=32;n<=126;n++)assert.equal(isDisplayCharacter(String.fromCharCode(n)),true);
 for(const value of ['，','。','？','！','“','”','、','；'])assert.equal(isDisplayCharacter(value),true,value);
 for(const value of ['Enter','Control','Shift','Backspace','Tab','F1','ArrowLeft','Dead','Unidentified','\n','\t','\u007f','\u200b','你好','aA','猫','😀','',null,42])assert.equal(isDisplayCharacter(value),false,String(value));
});

test('a burst replaces the preceding glyph, preserves case and has no queue',()=>{
 const display=createKeyDisplay();assert.equal(display.snapshot(0),null);
 display.receive('a',10);display.receive('A',11);display.receive('!',12);
 assert.deepEqual(display.snapshot(12),{character:'!',age:0,opacity:1});
 assert.equal(display.receive('Control',13),false);
 assert.equal(display.snapshot(14).character,'!');
 display.receive(' ',15);assert.equal(display.snapshot(16).character,' ');
 display.receive('a',20);display.receive('a',1500);
 assert.equal(display.snapshot(1600).opacity,1,'Key repeat refreshes visibility');
});

test('one-second lifetime holds through 700ms, fades for 300ms and expires at exactly 1000ms',()=>{
 assert.equal(KEY_CLOUD.holdSeconds,.7);assert.equal(KEY_CLOUD.fadeSeconds,.3);
 const display=createKeyDisplay();display.receive('Q',1000);
 assert.equal(display.snapshot(1699).opacity,1);assert.equal(display.snapshot(1700).opacity,1);
 assert.ok(Math.abs(display.snapshot(1850).opacity-.5)<1e-9);
 assert.ok(display.snapshot(1999).opacity>0&&display.snapshot(1999).opacity<.01);
 assert.equal(display.snapshot(2000),null);assert.equal(display.snapshot(10000),null);
});

test('clearing or expiry discards the previous character, and repeat starts a new full second',()=>{
 const display=createKeyDisplay();display.receive('a',1000);display.receive('A',1900);
 assert.equal(display.snapshot(2500).opacity,1);assert.equal(display.snapshot(2500).character,'A');
 assert.equal(display.snapshot(2900),null);
 display.receive('8',10000);display.clear();assert.equal(display.snapshot(10000),null);
 assert.equal(display.receive('a',NaN),false);
});

test('supported poses hold the cloud in place while the character fades',()=>{
 for(const pose of ['idle','tea','cake']){
  const start=keyCloudFrame({character:'A',age:0,opacity:1},pose);
  const end=keyCloudFrame({character:'A',age:.9,opacity:1/3},pose);
  assert.equal(start.x,KEY_CLOUD.x);assert.equal(start.y,KEY_CLOUD.y);
  assert.equal(end.x,start.x);assert.equal(end.y,start.y);assert.equal(end.scale,start.scale);
  assert.ok(Math.abs(end.opacity-1/3)<1e-9);
 }
});
