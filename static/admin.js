const $=id=>document.getElementById(id);
let token=sessionStorage.getItem("rp_admin_token")||"",catalogData=null;
function status(x){$("status").textContent=typeof x==="string"?x:JSON.stringify(x,null,2)}
async function api(path,method="GET",body){
 const headers={};if(token)headers.Authorization="Bearer "+token;
 if(body!==undefined)headers["Content-Type"]="application/json";
 const r=await fetch("/api"+path,{method,headers,body:body===undefined?undefined:JSON.stringify(body)});
 const d=await r.json().catch(()=>({}));if(!r.ok)throw Error(d.detail||"Request failed: "+r.status);return d
}
function parse(id){try{return JSON.parse($(id).value)}catch(e){throw Error("JSON ไม่ถูกต้อง ("+id+"): "+e.message)}}
function esc(v){return String(v??"—").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]))}
function n(v,unit=""){return v===null||v===undefined?"—":Number(v).toLocaleString("en-US")+unit}
function renderCatalog(data){
 catalogData=data;
 const root=$("catalog");const rockets=data.rockets||[],versions=data.versions||[];
 if(!rockets.length){root.innerHTML='<p class="empty">ยังไม่มีข้อมูลจรวด</p>';return}
 root.innerHTML=rockets.map(r=>{
  const vs=versions.filter(v=>v.rocket_id===r.id);
  return '<article class="rocket-entry"><div class="rocket-head"><div><h3>'+esc(r.name)+'</h3><p>'+esc(r.manufacturer)+' · '+esc(r.country)+' · '+esc(r.vehicle_type)+'</p><code>'+esc(r.slug)+'</code></div><span class="pill">'+vs.length+' revision</span></div>'+
   (vs.length?vs.map(v=>{
    const stages=(data.stages||[]).filter(x=>x.version_id===v.id);
    const boosters=(data.boosters||[]).filter(x=>x.version_id===v.id);
    const sources=(data.sources||[]).filter(x=>x.version_id===v.id);
    const conf=v.confidence||"—";
    return '<section class="version-entry"><div class="version-head"><strong>Revision '+esc(v.revision)+'</strong><span class="pill draft">'+esc(v.status)+' · '+esc(conf)+'</span></div>'+
     '<div class="metric-grid"><div><small>Payload mass</small><b>'+n(v.payload_mass_kg,' kg')+'</b></div><div><small>LEO capacity</small><b>'+n(v.payload_capacity_leo_kg,' kg')+'</b></div><div><small>Fairing mass</small><b>'+n(v.fairing_mass_kg,' kg')+'</b></div><div><small>Fairing jettison</small><b>'+n(v.fairing_jettison_alt_km,' km')+'</b></div></div>'+
     '<p class="note">'+esc(v.notes||"ไม่มีหมายเหตุ")+'</p>'+
     '<h4>Stages ('+stages.length+')</h4>'+(stages.length?'<div class="table-wrap"><table><thead><tr><th>Stage</th><th>Thrust SL/Vac (kN)</th><th>ISP SL/Vac (s)</th><th>Propellant (kg)</th><th>Dry (kg)</th><th>Burn (s)</th></tr></thead><tbody>'+stages.map(s=>'<tr><td>'+esc(s.stage_number)+'. '+esc(s.name)+'</td><td>'+n(s.thrust_sl_kn)+' / '+n(s.thrust_vac_kn)+'</td><td>'+n(s.isp_sl_s)+' / '+n(s.isp_vac_s)+'</td><td>'+n(s.prop_mass_kg)+'</td><td>'+n(s.dry_mass_kg)+'</td><td>'+n(s.burn_time_s)+'</td></tr>').join("")+'</tbody></table></div>':'<p class="muted">ไม่มีข้อมูล Stage</p>')+
     '<h4>Boosters ('+boosters.length+')</h4>'+(boosters.length?'<div class="table-wrap"><table><thead><tr><th>ชื่อ</th><th>จำนวน</th><th>Thrust SL/Vac (kN)</th><th>Propellant (kg)</th><th>Burn (s)</th><th>Ignition (s)</th></tr></thead><tbody>'+boosters.map(b=>'<tr><td>'+esc(b.name)+'</td><td>'+n(b.quantity)+'</td><td>'+n(b.thrust_sl_kn)+' / '+n(b.thrust_vac_kn)+'</td><td>'+n(b.prop_mass_kg)+'</td><td>'+n(b.burn_time_s)+'</td><td>'+n(b.ignite_t_s)+'</td></tr>').join("")+'</tbody></table></div>':'<p class="muted">ไม่มี Booster</p>')+
     '<h4>Sources ('+sources.length+')</h4>'+(sources.length?'<ul class="source-list">'+sources.map(s=>'<li><strong>'+esc(s.title)+'</strong> · '+esc(s.publisher)+' · '+esc(s.confidence)+'<br><small>'+esc(s.source_type)+' · '+(s.source_url?'<a href="'+esc(s.source_url)+'" target="_blank" rel="noopener">เปิดแหล่งข้อมูล</a>':"ไม่มี URL")+'</small><p>'+esc(s.notes)+'</p></li>').join("")+'</ul>':'<p class="muted">ไม่มีแหล่งอ้างอิง</p>')+
     '<div class="version-actions"><button type="button" data-rocket="'+esc(r.id)+'" data-version="'+esc(v.id)+'">เลือก Revision นี้เพื่อจัดการ</button><span>สถานะ: '+esc(v.status)+(v.is_current?' · Current':'')+'</span></div></section>'
   }).join(""):'<p class="muted">ยังไม่มี Revision</p>')+'</article>'
 }).join("");
 root.querySelectorAll("[data-version]").forEach(btn=>btn.addEventListener("click",()=>{
  $("rocket-id").value=btn.dataset.rocket;$("version-id").value=btn.dataset.version;
  status("เลือก Rocket และ Revision แล้ว");$("version-id").scrollIntoView({behavior:"smooth",block:"center"})
 }));
}
async function load(){
 const me=await api("/admin/me");$("who").textContent=me.user.email+" · ADMIN";
 const data=await api("/admin/rockets");renderCatalog(data);
 status("เชื่อมต่อฐานข้อมูลแล้ว · "+(data.rockets||[]).length+" rockets / "+(data.versions||[]).length+" revisions")
}
function show(){$("login-panel").classList.toggle("hidden",!!token);$("workspace").classList.toggle("hidden",!token)}
$("login").onclick=async()=>{try{const r=await fetch("/api/admin/login",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({email:$("email").value,password:$("password").value})});const d=await r.json();if(!r.ok)throw Error(d.detail||"Login failed");token=d.access_token;sessionStorage.setItem("rp_admin_token",token);$("password").value="";show();await load()}catch(e){alert(e.message)}};
$("logout").onclick=()=>{token="";sessionStorage.removeItem("rp_admin_token");show()};
$("refresh").onclick=()=>load().catch(e=>status(e.message));
$("inspect-schema").onclick=async()=>{try{status("กำลังอ่านโครงสร้างตารางจาก Supabase...");const schema=await api("/admin/schema");status(schema)}catch(e){status("ตรวจ Schema ไม่สำเร็จ: "+e.message)}};
$("create-rocket").onclick=async()=>{try{const d=await api("/admin/rockets","POST",parse("rocket-json"));$("rocket-id").value=d.id||"";status({created:d});await load()}catch(e){status(e.message)}};
$("create-version").onclick=async()=>{try{const id=$("rocket-id").value.trim();if(!id)throw Error("กรุณาระบุ Rocket ID");const d=await api("/admin/rockets/"+encodeURIComponent(id)+"/versions","POST",parse("version-json"));$("version-id").value=d.id||"";status({draft_created:d});await load()}catch(e){status(e.message)}};
$("add-child").onclick=async()=>{try{const id=$("version-id").value.trim();if(!id)throw Error("กรุณาระบุ Version ID");const d=await api("/admin/versions/"+encodeURIComponent(id)+"/"+$("child-table").value,"POST",parse("child-json"));status({inserted:d});await load()}catch(e){status(e.message)}};
$("publish").onclick=async()=>{try{const id=$("version-id").value.trim();if(!id)throw Error("กรุณาระบุ Version ID");if(!confirm("ยืนยันเผยแพร่ Revision นี้?"))return;const d=await api("/admin/versions/"+encodeURIComponent(id)+"/publish","POST");status({published:d});await load()}catch(e){status(e.message)}};
show();if(token)load().catch(e=>{status(e.message);token="";sessionStorage.removeItem("rp_admin_token");show()});
