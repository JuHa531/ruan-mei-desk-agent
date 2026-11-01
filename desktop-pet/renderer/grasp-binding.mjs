/** Authored contact points and digit silhouettes in the original artwork. */
export const FORK_ART=Object.freeze({scale:.5,grip:[552,1274],tip:[552,1110]});
export const CUP_ART=Object.freeze({scale:76/112,pivot:[205,1275],grip:[301,1240],base:[179,1369]});
export const SUPPORT_PALM=Object.freeze({wrist:[145,280],grip:[388,294],contact:[440,267]});
export const HAND_GRASPS=Object.freeze({
 fork:{anatomicalSide:'left',view:'dorsal-ulnar',frontDigits:['index','middle'],farDigits:['thumb'],farGrip:[[331,356],[370,344],[405,361],[430,392],[404,434],[354,461],[326,413]],grip:[435,342],front:[
  [[123,352],[244,262],[365,204],[650,212],[816,286],[825,365],[618,380],[445,319],[260,365],[140,405]],
  [[392,389],[535,359],[702,385],[789,451],[639,520],[503,535],[378,479]],
 ]},
 cup:{grip:[1198,214],front:[
  [[1106,153],[1190,142],[1240,168],[1243,193],[1194,207],[1127,209],[1096,187]],
  [[1100,211],[1167,204],[1200,220],[1232,237],[1220,260],[1142,263],[1098,244]],
 ]},
});
export function insideContour(point,polygon){
 let inside=false;
 for(let i=0,j=polygon.length-1;i<polygon.length;j=i++){
  const a=polygon[i],b=polygon[j];
  if((a[1]>point[1])!==(b[1]>point[1])&&point[0]<(b[0]-a[0])*(point[1]-a[1])/(b[1]-a[1])+a[0])inside=!inside;
 }
 return inside;
}
