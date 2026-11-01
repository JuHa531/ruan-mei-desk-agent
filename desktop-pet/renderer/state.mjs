/** @fileoverview Independent face, pose and skin selections plus time-based animation. */
import { motionAmplitude, motionSpeed, motionTime } from './motion-settings.mjs';
import {blinkClosure,BLINK_DURATION,facialTarget} from './facial-rig.mjs';
import {changePose,transitionBlink} from './pose-transition.mjs';
import {actionClock,actionSpeed} from './action-motion.mjs';
export const EXPRESSIONS = [
  ['blush', '含蓄', '1', '♡'], ['angry', '生气', '2', '╬'],
  ['sleep', '睡觉', '3', '☾'], ['surprise', '惊讶', '4', '!'],
  ['dizzy', '晕', '5', '◎'], ['wink', 'Wink', '6', '✧'],
  ['cry', '伤心', '7', '◡'], ['heart', '认可', '8', '♥'],
  ['smile', '微笑', '9', '☺'], ['awkward', '囧', '0', '囧'],
].map(([id, label, key, icon]) => ({ id, label, key, icon }));

export const SKINS = [
  ['cat', '猫猫形态', 'F1', '♧'], ['glasses', '眼镜', 'F2', '⌘'],
].map(([id, label, key, icon]) => ({ id, label, key, icon }));

export const POSES = [
  ['idle', '日常待机', 'F3', '♡'],
  ['cake', '吃蛋糕', 'F5', '♜'], ['tea', '喝清茶', 'F6', '◒'],
].map(([id, label, key, icon]) => ({ id, label, key, icon }));

/** Creates independent renderer state; expression changes never alter desktop preferences. */
export function createPetState() {
  return { expression: null, pose: 'idle', cat: false, glasses: false, gaze: { x: 0, y: 0 },
    target: { x: 0, y: 0 }, head:{x:0,y:0}, time: 0, motionTime: null, blink: 0, nextBlink: 3.2, blinkAge: -1,
    hair: 0, hairVelocity: 0, actionAge: 0, actionTime:0, actionStartedAt:0, poseMotion:null, facial:facialTarget(null) };
}

/** Faces toggle to neutral; poses are exclusive selections and skins are independent switches. */
export function applyAction(state, action, settings={}) {
  if (!action || typeof action !== 'object') return state;
  if (action.type === 'expression' && EXPRESSIONS.some(item => item.id === action.id)) {
    state.expression = state.expression === action.id ? null : action.id;
    state.actionAge = 0;
  } else if (action.type === 'pose' && POSES.some(item => item.id === action.id)) {
    changePose(state,action.id,settings);
    state.actionAge = 0;
  } else if (action.type === 'toggle-skin' && SKINS.some(item => item.id === action.id)) {
    state[action.id] = !state[action.id];
    state.actionAge = 0;
  } else if (action.type === 'reset') {
    state.expression = null;
    changePose(state,'idle',settings);
    state.cat = false;
    state.glasses = false;
    state.actionAge = 0;
  }
  return state;
}

/** Numeric keys select faces; F keys select skins / poses after the Space prefix. */
export function actionForKey(code) {
  if (typeof code !== 'string') return null;
  if (code === 'Backspace') return { type: 'reset' };
  const key = code.startsWith('Digit') ? code.slice(5) : code.startsWith('Numpad') ? code.slice(6) : code;
  const item = EXPRESSIONS.find(expression => expression.key === key);
  if (item) return { type: 'expression', id: item.id };
  const skin = SKINS.find(item => item.key === key);
  if (skin) return { type: 'toggle-skin', id: skin.id };
  const pose = POSES.find(item => item.key === key);
  return pose ? { type: 'pose', id: pose.id } : null;
}

const gazeCoordinate=value=>Number.isFinite(value)?Math.max(-1,Math.min(1,value)):0;

/** Store just the newest bounded cursor target, never a queue of intermediate motion. */
export function setGazeTarget(state,x,y){
  state.target.x=gazeCoordinate(x);state.target.y=gazeCoordinate(y);
}

/** Apply the latest cursor on this paint; decorative motion keeps its independent clock. */
export function advance(state, elapsed, settings = {}) {
  // A slow paint still advances by real time; only suspend/resume gaps are capped.
  const dt = Number.isFinite(elapsed)?Math.min(Math.max(elapsed, 0), 0.25):0;
  // Integrate only this clock: changing speed must not jump to time * newSpeed
  // or change blink timing, input effects, gaze response or drag behavior.
  state.motionTime = motionTime(state, settings) + dt * motionSpeed(settings);
  state.time += dt;
  state.actionTime=actionClock(state)+dt*actionSpeed(settings);
  state.actionAge += dt;
  // The former exponential filter took roughly 256 ms to reach 90% of a new
  // target. Direct sampling responds on the next frame, including reversals.
  state.gaze.x = settings.eyeTracking === false ? 0 : gazeCoordinate(state.target.x);
  state.gaze.y = settings.eyeTracking === false ? 0 : gazeCoordinate(state.target.y);
  // Eyes lead; the connected head and neck settle gently behind the glance.
  state.head??={x:0,y:0};
  const headBlend=1-Math.exp(-dt*7);
  for(const axis of ['x','y'])state.head[axis]+=((settings.headTracking===false||settings.eyeTracking===false?0:state.gaze[axis])-state.head[axis])*headBlend;
  const facial=facialTarget(state.expression),blend=1-Math.exp(-dt*16);
  state.facial??=facialTarget(null);
  for(let i=0;i<facial.length;i++)state.facial[i]+=(facial[i]-state.facial[i])*blend;
  const targetHair = Math.sin(state.motionTime * 1.05) * 0.032 * motionAmplitude(settings);
  // Substep the spring rather than slowing every animation clock for stability.
  for(let remaining=dt;remaining>1e-9;){const step=Math.min(remaining,.02);state.hairVelocity+=((targetHair-state.hair)*65-state.hairVelocity*9)*step;state.hair+=state.hairVelocity*step;remaining-=step;}
  state.blink=0;
  if (state.time >= state.nextBlink && state.blinkAge < 0) state.blinkAge = 0;
  if (state.blinkAge >= 0) {
    state.blinkAge += dt;
    state.blink = blinkClosure(state.blinkAge);
    if (state.blinkAge >= BLINK_DURATION) {
      state.blinkAge = -1;
      state.blink = 0;
      state.nextBlink = state.time + 3.2 + Math.sin(state.time * 3.4) * 1.3;
    }
  }
  if(state.poseMotion&&(settings.poseTransition===false||state.actionTime>=state.poseMotion.startedAt+state.poseMotion.duration))state.poseMotion=null;
  state.blink=Math.max(state.blink,transitionBlink(state));
  return state;
}
