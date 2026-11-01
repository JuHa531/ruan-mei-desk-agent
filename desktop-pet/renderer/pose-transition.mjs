/** Action selection: one body with moving limbs, rather than full-sprite handoff. */
import {ACTIONS,actionClock,startAction} from './action-motion.mjs';
export const POSE_IDS=ACTIONS;
export const poseIsChanging=s=>!!s.poseMotion&&actionClock(s)<s.poseMotion.startedAt+s.poseMotion.duration;
export const changePose=startAction;
export const dominantPose=()=> 'idle';
export const poseSources=()=>['idle'];
export const poseWeights=()=>({idle:1});
export const poseGesture=()=>({});
export const transitionBlink=()=>0;
