(()=>{
 const css=document.createElement('style');
 css.textContent='#mvs-image-panel{margin-top:15px;background:#101d31;border:1px solid #2b405e;border-radius:14px;padding:16px}#mvs-image-panel textarea{width:100%;min-height:100px;background:#091526;color:#eef5ff;border:1px solid #395171;border-radius:8px;padding:10px}#mvs-image-panel button{border:0;border-radius:8px;padding:10px 13px;margin:5px;background:linear-gradient(90deg,#37e0cb,#8ae7d5);font-weight:bold}#mvs-image-gallery{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:10px;margin-top:12px}#mvs-image-gallery img{width:100%;border-radius:10px}#mvs-image-status{color:#37e0cb;min-height:22px}';
 document.head.appendChild(css);
 const workspace=document.getElementById('workspace'); if(!workspace)return;
 const panel=document.createElement('section'); panel.id='mvs-image-panel';
 panel.innerHTML='<h2>🖼️ AI Scene Image Generator</h2><p class="small">Gemini Nano Banana 2.1 • Vertical 9:16</p><label class="small">Scene Number</label><input id="mvs-scene-no" type="number" min="1" max="20" value="1"><label class="small">Scene Image Prompt</label><textarea id="mvs-image-prompt" placeholder="Scene Agent मधील एका सीनचा visual prompt paste करा..."></textarea><button id="mvs-gen-one">Generate Scene Image</button><button id="mvs-load-images">Refresh Gallery</button><div id="mvs-image-status"></div><div id="mvs-image-gallery"></div>';
 workspace.parentNode.insertBefore(panel,workspace.nextSibling);
 const status=panel.querySelector('#mvs-image-status'), gallery=panel.querySelector('#mvs-image-gallery');
 const pid=()=>document.getElementById('project')?.value||'';
 async function load(){if(!pid()){status.textContent='आधी project निवडा.';return}try{const r=await fetch('/api/image/list/'+encodeURIComponent(pid()));const j=await r.json();gallery.innerHTML=(j.images||[]).map(x=>'<a href="'+x.url+'" target="_blank"><img src="'+x.url+'" alt="'+x.name+'"><div class="small">'+x.name+'</div></a>').join('')}catch(e){status.textContent=e.message}}
 panel.querySelector('#mvs-gen-one').onclick=async()=>{
  const prompt=panel.querySelector('#mvs-image-prompt').value.trim(), scene=panel.querySelector('#mvs-scene-no').value;
  if(!pid()){status.textContent='आधी project निवडा.';return} if(!prompt){status.textContent='Scene prompt लिहा किंवा paste करा.';return}
  status.textContent='Image तयार होत आहे... थोडा वेळ थांबा.';
  try{const r=await fetch('/api/image/generate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:pid(),prompt,scene})});const j=await r.json();if(!r.ok)throw Error(j.error||'Image generation failed');status.textContent='Scene '+j.scene+' image तयार झाली.';await load()}catch(e){status.textContent=e.message}
 };
 panel.querySelector('#mvs-load-images').onclick=load;
 document.getElementById('project')?.addEventListener('change',load);
})();\n