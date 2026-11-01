/** One continuous arm texture: volume-preserving blending across the elbow. */
const clamp=v=>Math.max(0,Math.min(1,v));
const smooth=v=>{v=clamp(v);return v*v*(3-2*v);};
const point=(m,x,y)=>[m[0]*x+m[2]*y+m[4],m[1]*x+m[3]*y+m[5]];
export function armSourceRow(part,y){
 const a=y<=part.elbow[1]?part.a:part.elbow,b=y<=part.elbow[1]?part.elbow:part.b,t=(y-a[1])/(b[1]-a[1]);
 const cx=a[0]+(b[0]-a[0])*t,span=Math.min(part.elbow[1]-part.a[1],part.b[1]-part.elbow[1])*.14;
 return{cx,weight:smooth((y-part.elbow[1]+span)/(2*span))};
}
export function armSurface(part,upper,fore){
 const a=Math.atan2(upper[1],upper[0]),b=Math.atan2(fore[1],fore[0]),angle=Math.atan2(Math.sin(b-a),Math.cos(b-a));
 return{part,upper,fore,normal:[a,angle,Math.hypot(upper[0],upper[1]),Math.hypot(fore[0],fore[1])]};
}
export function skinArmPoint(surface,x,y){
 const{part,upper,fore,normal}=surface,{cx,weight:w}=armSourceRow(part,y),a=point(upper,cx,y),b=point(fore,cx,y),angle=normal[0]+normal[1]*w,width=(normal[2]*(1-w)+normal[3]*w)*(x-cx);
 return[a[0]*(1-w)+b[0]*w+Math.cos(angle)*width,a[1]*(1-w)+b[1]*w+Math.sin(angle)*width];
}
const COLS=20,ROWS=112;
function vertices(p){
 const result=[],add=(i,j)=>{const x=i*p.image.width/COLS,y=j*p.image.height/ROWS,{cx,weight}=armSourceRow(p,y);result.push(x,y,cx,weight);};
 for(let j=0;j<ROWS;j++)for(let i=0;i<COLS;i++){add(i,j);add(i+1,j);add(i,j+1);add(i+1,j);add(i+1,j+1);add(i,j+1);}return new Float32Array(result);
}
const vertex=`precision highp float;attribute vec2 a_source;attribute vec2 a_row;uniform mat3 u_upper;uniform mat3 u_fore;uniform vec4 u_normal;uniform vec2 u_size;varying vec2 v_uv;void main(){
 float w=a_row.y;vec3 c=vec3(a_row.x,a_source.y,1.0);vec2 centre=mix((u_upper*c).xy,(u_fore*c).xy,w);
 float angle=u_normal.x+u_normal.y*w,width=mix(u_normal.z,u_normal.w,w)*(a_source.x-a_row.x);vec2 p=centre+vec2(cos(angle),sin(angle))*width;
 gl_Position=vec4(p/vec2(1090.0,1443.0)*vec2(2.0,-2.0)+vec2(-1.0,1.0),0.0,1.0);v_uv=a_source/u_size;}`;
const fragment=`precision highp float;uniform sampler2D u_image;uniform float u_section;uniform float u_rootEnd;varying vec2 v_uv;void main(){if(u_section<.5&&v_uv.y>u_rootEnd)discard;if(u_section>.5&&u_section<1.5&&v_uv.y<=u_rootEnd)discard;gl_FragColor=texture2D(u_image,v_uv);}`;
const mat=m=>new Float32Array([m[0],m[1],0,m[2],m[3],0,m[4],m[5],1]);
export function createArmSkinRenderer(){
 const canvas=Object.assign(document.createElement('canvas'),{width:1090,height:1443}),gl=canvas.getContext('webgl',{alpha:true,premultipliedAlpha:true,antialias:true,preserveDrawingBuffer:true,depth:false});
 if(!gl)throw new Error('Continuous arm skinning needs WebGL');
 const compile=(type,code)=>{const s=gl.createShader(type);gl.shaderSource(s,code);gl.compileShader(s);if(!gl.getShaderParameter(s,gl.COMPILE_STATUS))throw new Error(gl.getShaderInfoLog(s));return s;};
 const program=gl.createProgram();gl.attachShader(program,compile(gl.VERTEX_SHADER,vertex));gl.attachShader(program,compile(gl.FRAGMENT_SHADER,fragment));gl.linkProgram(program);if(!gl.getProgramParameter(program,gl.LINK_STATUS))throw new Error(gl.getProgramInfoLog(program));gl.useProgram(program);
 const source=gl.getAttribLocation(program,'a_source'),row=gl.getAttribLocation(program,'a_row'),uniform=Object.fromEntries(['upper','fore','normal','size','section','rootEnd'].map(n=>[n,gl.getUniformLocation(program,'u_'+n)])),cache=new WeakMap();
 gl.enableVertexAttribArray(source);gl.enableVertexAttribArray(row);gl.uniform1i(gl.getUniformLocation(program,'u_image'),0);gl.pixelStorei(gl.UNPACK_PREMULTIPLY_ALPHA_WEBGL,true);gl.enable(gl.BLEND);gl.blendFunc(gl.ONE,gl.ONE_MINUS_SRC_ALPHA);gl.clearColor(0,0,0,0);
 return{setResolution(scale=1){canvas.width=Math.max(1,Math.round(1090*scale));canvas.height=Math.max(1,Math.round(1443*scale));},draw(surfaces,section=2){gl.viewport(0,0,canvas.width,canvas.height);gl.clear(gl.COLOR_BUFFER_BIT);gl.uniform1f(uniform.section,section);for(const s of surfaces){let entry=cache.get(s.part);if(!entry){const data=vertices(s.part),buffer=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,buffer);gl.bufferData(gl.ARRAY_BUFFER,data,gl.STATIC_DRAW);const texture=gl.createTexture();gl.bindTexture(gl.TEXTURE_2D,texture);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MIN_FILTER,gl.LINEAR);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MAG_FILTER,gl.LINEAR);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_S,gl.CLAMP_TO_EDGE);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_T,gl.CLAMP_TO_EDGE);gl.texImage2D(gl.TEXTURE_2D,0,gl.RGBA,gl.RGBA,gl.UNSIGNED_BYTE,s.part.image);entry={buffer,texture,count:data.length/4};cache.set(s.part,entry);}
  gl.bindBuffer(gl.ARRAY_BUFFER,entry.buffer);gl.vertexAttribPointer(source,2,gl.FLOAT,false,16,0);gl.vertexAttribPointer(row,2,gl.FLOAT,false,16,8);gl.bindTexture(gl.TEXTURE_2D,entry.texture);gl.uniformMatrix3fv(uniform.upper,false,mat(s.upper));gl.uniformMatrix3fv(uniform.fore,false,mat(s.fore));gl.uniform4fv(uniform.normal,s.normal);gl.uniform2f(uniform.size,s.part.image.width,s.part.image.height);gl.uniform1f(uniform.rootEnd,(s.part.a[1]+110)/s.part.image.height);gl.drawArrays(gl.TRIANGLES,0,entry.count);
 }return canvas;}};
}
export function armHitPoint(surface,x,y){
 const p=surface.part,grid=Array.from({length:ROWS+1},(_,j)=>Array.from({length:COLS+1},(_,i)=>skinArmPoint(surface,i*p.image.width/COLS,j*p.image.height/ROWS)));
 const bary=(a,b,c)=>{const den=(b[1]-c[1])*(a[0]-c[0])+(c[0]-b[0])*(a[1]-c[1]);if(Math.abs(den)<1e-8)return null;const u=((b[1]-c[1])*(x-c[0])+(c[0]-b[0])*(y-c[1]))/den,v=((c[1]-a[1])*(x-c[0])+(a[0]-c[0])*(y-c[1]))/den;return u>=0&&v>=0&&u+v<=1?[u,v,1-u-v]:null;};
 for(let j=ROWS-1;j>=0;j--)for(let i=COLS-1;i>=0;i--)for(const indices of[[[i+1,j],[i+1,j+1],[i,j+1]],[[i,j],[i+1,j],[i,j+1]]]){
  const v=indices.map(([i,j])=>grid[j][i]);if(x<Math.min(...v.map(q=>q[0]))||x>Math.max(...v.map(q=>q[0]))||y<Math.min(...v.map(q=>q[1]))||y>Math.max(...v.map(q=>q[1])))continue;
  const w=bary(...v);if(!w)continue;const sx=Math.floor(indices.reduce((n,[i],k)=>n+i*p.image.width/COLS*w[k],0)),sy=Math.floor(indices.reduce((n,[,j],k)=>n+j*p.image.height/ROWS*w[k],0));if(sx>=0&&sy>=0&&sx<p.image.width&&sy<p.image.height&&p.data[(sy*p.image.width+sx)*4+3]>=32)return sy<p.elbow[1]?'body':'hand';
 }return null;
}
