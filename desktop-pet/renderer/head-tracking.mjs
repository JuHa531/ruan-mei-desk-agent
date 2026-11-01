/** Look input drives fixed-length neck and head bones; it never scales a surface. */
const clamp=x=>Number.isFinite(x)?Math.max(-1,Math.min(1,x)):0;
export function lookAngles(head={},pose='idle'){
 const x=clamp(head.x),y=clamp(head.y);
 const down=Math.max(0,y);
 const yaw=x*(1-down*.25);
 // Counter-rotate the skull as the fixed-length neck bends: a small downward
 // arc of the head, without dragging the chest or squashing the illustration.
 return{neck:yaw*.012+y*.025+down*.155,head:yaw*.022-y*.021-down*.147};
}
export function lookAngleLimits(pose='idle'){
 return{neck:.192,head:.190,combined:.046};
}
export function neckLandmarks(pose='idle'){
 const positions={
  idle:{neck:[520,642],head:[536,619]},
  cake:{neck:[542,629],head:[557,599]},
  tea:{neck:[520,633],head:[536,601]},
 };
 return positions[pose]||positions.idle;
}
