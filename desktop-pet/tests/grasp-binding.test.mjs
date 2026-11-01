import test from 'node:test';
import assert from 'node:assert/strict';
import {FORK_ART,CUP_ART,HAND_GRASPS,insideContour} from '../renderer/grasp-binding.mjs';
const front=(kind,p)=>HAND_GRASPS[kind].front.some(poly=>insideContour(p,poly));
test('gripping silhouettes follow index and thumb pads, leaving the palm behind the utensil',()=>{
 assert.equal(front('fork',[310,280]),true);assert.equal(front('fork',[460,430]),true);assert.equal(front('fork',[950,600]),false);
 assert.equal(front('cup',[1140,230]),true);assert.equal(front('cup',[1140,180]),true);assert.equal(front('cup',[1320,300]),false);
});
test('the fork uses a dorsal anatomical left hand with the thumb behind the shaft',()=>{
 assert.equal(HAND_GRASPS.fork.anatomicalSide,'left');assert.equal(HAND_GRASPS.fork.view,'dorsal-ulnar');assert.deepEqual(HAND_GRASPS.fork.frontDigits,['index','middle']);assert.deepEqual(HAND_GRASPS.fork.farDigits,['thumb']);assert.equal(front('fork',[355,375]),false,'The visible far-thumb fragment never occludes the handle');
});
test('the fork binds to its narrow stem and cup binds inside its handle rather than the outside rim',()=>{
 assert.ok(FORK_ART.grip[1]>1220&&FORK_ART.grip[1]<1300,'Grip the narrow shaft between the neck and floral end');assert.ok(CUP_ART.grip[0]>285&&CUP_ART.grip[0]<315&&CUP_ART.grip[1]>1225&&CUP_ART.grip[1]<1260);
 assert.equal(FORK_ART.scale,.5);assert.equal(CUP_ART.scale,76/112);
});
