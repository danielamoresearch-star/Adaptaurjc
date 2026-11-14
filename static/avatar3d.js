/* Lightweight procedural WebGL 3D NOVA. CSS avatar remains the fallback. */
import * as THREE from 'https://cdn.jsdelivr.net/npm/three@0.170.0/build/three.module.js';
const mount=document.querySelector('#mentorToggle');
if(mount && window.WebGLRenderingContext && !window.matchMedia('(prefers-reduced-motion: reduce)').matches){
 try{
 const scene=new THREE.Scene(),camera=new THREE.PerspectiveCamera(35,1,0.1,100);
 camera.position.set(0,0,6.7);
 const renderer=new THREE.WebGLRenderer({alpha:true,antialias:true,powerPreference:'low-power'});
 renderer.setPixelRatio(Math.min(window.devicePixelRatio||1,1.5));renderer.setSize(160,160);
 renderer.domElement.className='nova-three';renderer.domElement.setAttribute('aria-hidden','true');
 mount.appendChild(renderer.domElement);
 scene.add(new THREE.HemisphereLight(0xffffff,0x53638d,2));
 const key=new THREE.DirectionalLight(0xffffff,3);key.position.set(-2,4,5);scene.add(key);
 const red=new THREE.MeshStandardMaterial({color:0xc40030,metalness:.45,roughness:.26});
 const pearl=new THREE.MeshStandardMaterial({color:0xffe6ed,metalness:.12,roughness:.34});
 const navy=new THREE.MeshStandardMaterial({color:0x17283f,roughness:.3});
 const glow=new THREE.MeshStandardMaterial({color:0x73e5ff,emissive:0x39a8d7,emissiveIntensity:.7});
 const root=new THREE.Group();scene.add(root);
 function ball(x,y,z,sx,sy,sz,mat){const m=new THREE.Mesh(new THREE.SphereGeometry(1,24,16),mat);m.position.set(x,y,z);m.scale.set(sx,sy,sz);root.add(m);return m}
 ball(0,-.88,0,.76,.72,.5,red);ball(0,-.58,.38,.42,.3,.14,pearl);
 ball(0,.43,0,.75,.85,.64,pearl);ball(0,.89,.16,.69,.29,.56,red);
 ball(-.31,.5,.56,.13,.17,.08,navy);ball(.31,.5,.56,.13,.17,.08,navy);
 ball(-.28,.54,.635,.05,.065,.02,glow);ball(.34,.54,.635,.05,.065,.02,glow);
 const mouth=ball(0,.08,.625,.18,.045,.035,navy);
 ball(-.68,-.56,0,.22,.5,.25,red);ball(.68,-.56,0,.22,.5,.25,red);
 const clock=new THREE.Clock();
 let last=0;
 function animate(){requestAnimationFrame(animate);if(document.hidden||mount.closest('[hidden]'))return;
 const t=clock.getElapsedTime();root.position.y=Math.sin(t*1.5)*.09;root.rotation.y=Math.sin(t*.55)*.18;
 root.rotation.z=Math.sin(t*.7)*.035;
 mouth.scale.y=mount.closest('.speaking')?.classList.contains('speaking')? .09+Math.abs(Math.sin(t*12))*.09:.04;
 renderer.render(scene,camera)}
 mount.classList.add('has-three');animate();
 }catch(e){/* CSS avatar fallback */}
}
